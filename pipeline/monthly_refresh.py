#!/usr/bin/env python3
"""
Neutral Eats — unattended monthly Overture refresh driver (Phase 4).

Runs on the production host from root's crontab (monthly, quiet hours).
One run:

  1. Takes an exclusive flock on /root/overture-work/refresh.lock so two
     runs can never overlap (overlapping pipeline runs corrupted the
     Phase 3 attempts; this is the guard against a repeat).
  2. Compares the latest Overture places release on S3 with the release
     recorded in /root/overture-work/refresh-state.json. No newer
     release -> log it, snapshot counts via venue_monitor, exit 0.
  3. Newer release -> in a fresh per-run workdir
     (/root/overture-work/runs/<release>-<stamp>/gate2):
       extract_overture.py --nationwide  (its own integrity asserts and
                                           per-state reconciliation apply)
       merge_overture.py dedupe | match | build | load   (stage by stage)
       merge_overture.py verify           (output kept in the run log)
     then THIS DRIVER's reconciliation gates against venues_merged:
       G1 merged total > 0
       G2 merged total within [95%, 115%] of the live total
       G3 every metro (is_active=1): merged >= 80% of live and > 0
       G4 no NULL/zero coords or empty names in venues_merged
       G5 >= 90% of merged rows carry Overture provenance
     ANY gate or stage failure -> NO CUTOVER, production untouched,
     loud STATUS: FAILED_* in logs/LATEST-REPORT.txt, exit 1.
  4. All gates pass -> merge_overture.py cutover --yes (that stage takes
     the dated pre-cutover mysqldump in /root/backups/ and does the
     atomic RENAME swap + live-API spot checks itself).
  5. Rotation: drop the PREVIOUS venues_legacy_* table so exactly one
     rollback table is retained; update the state file (release,
     timestamps, before/after counts, legacy table name).
  6. Cleanup: delete the run's S3 parquet mirror (~11 GiB), prune old
     run dirs (keeps the previous run for forensics), run the count
     monitor, and write logs/LATEST-REPORT.txt — the pickup file for the
     main agent — on EVERY full run, success or failure.

--check is read-only: prints recorded vs latest release and exits 0.
It takes no lock and writes nothing.

USAGE
-----
    python3 monthly_refresh.py            # full run (cron)
    python3 monthly_refresh.py --check    # report release status only

CREDENTIALS: none in this file; MySQL via the root socket, pipeline
scripts read the site config themselves, exactly as in Phase 3.
"""

import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import venue_monitor  # noqa: E402

BASE = "/root/overture-work"
PIPELINE_DIR = os.path.join(BASE, "pipeline")
STATE_PATH = os.path.join(BASE, "refresh-state.json")
LOCK_PATH = os.path.join(BASE, "refresh.lock")
LOGDIR = os.path.join(BASE, "logs")
RUNS_DIR = os.path.join(BASE, "runs")
REPORT_PATH = os.path.join(LOGDIR, "LATEST-REPORT.txt")
HISTORY_PATH = os.path.join(BASE, "count-history.jsonl")
S3_BUCKET = "overturemaps-us-west-2"
S3_LIST_URL = (f"https://{S3_BUCKET}.s3.us-west-2.amazonaws.com/"
               "?list-type=2&prefix=release/&delimiter=/")

# Gate thresholds (see module docstring).
G2_MIN, G2_MAX = 0.95, 1.15
G3_MIN = 0.80
G5_MIN = 0.90

_run_log_fh = None


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def log(msg):
    line = f"[{now()}] {msg}"
    print(line, flush=True)
    if _run_log_fh:
        _run_log_fh.write(line + "\n")
        _run_log_fh.flush()


def latest_release():
    """Same S3 prefix listing as extract_overture.latest_release()."""
    with urllib.request.urlopen(S3_LIST_URL, timeout=30) as resp:
        xml = resp.read().decode()
    releases = sorted(re.findall(
        r"<Prefix>release/([0-9]{4}-[0-9]{2}-[0-9]{2}\.[0-9]+)/</Prefix>", xml))
    if not releases:
        raise RuntimeError("could not list Overture releases")
    return releases[-1]


def mysql_one(sql):
    proc = subprocess.run(["mysql", "-u", "root", "-N", "neutraleats", "-e", sql],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"mysql failed: {proc.stderr[-500:]}")
    return proc.stdout.strip()


def legacy_tables():
    out = mysql_one("SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='neutraleats' "
                    "AND table_name LIKE 'venues\\_legacy\\_%' ORDER BY table_name")
    return [ln for ln in out.splitlines() if ln.strip()]


def run_step(name, argv, logfile):
    """Run a pipeline stage, streaming its output into the run log."""
    log(f"--- stage {name}: {' '.join(argv)}")
    with open(logfile, "a") as fh:
        proc = subprocess.run(argv, stdout=fh, stderr=subprocess.STDOUT)
    log(f"--- stage {name}: exit {proc.returncode}")
    return proc.returncode


def gates(live_total):
    """Reconciliation gates over venues_merged. Returns (ok, details)."""
    details = []
    merged_total = int(mysql_one("SELECT COUNT(*) FROM venues_merged"))
    details.append(f"merged_total={merged_total} live_total={live_total}")
    ok = True
    if merged_total <= 0:
        ok = False
        details.append("G1 FAIL: venues_merged is empty")
    ratio = merged_total / live_total if live_total else 0
    if not (G2_MIN <= ratio <= G2_MAX):
        ok = False
        details.append(f"G2 FAIL: merged/live ratio {ratio:.3f} outside "
                       f"[{G2_MIN}, {G2_MAX}]")
    from merge_overture import METROS
    for name, (s, n, w, e) in METROS.items():
        a = int(mysql_one(f"SELECT COUNT(*) FROM venues WHERE is_active=1 "
                          f"AND lat BETWEEN {s} AND {n} AND lng BETWEEN {w} AND {e}"))
        b = int(mysql_one(f"SELECT COUNT(*) FROM venues_merged WHERE is_active=1 "
                          f"AND lat BETWEEN {s} AND {n} AND lng BETWEEN {w} AND {e}"))
        details.append(f"metro {name}: live={a} merged={b}")
        if b <= 0 or (a and b < G3_MIN * a):
            ok = False
            details.append(f"G3 FAIL: metro {name} merged {b} vs live {a}")
    bad = int(mysql_one("SELECT COUNT(*) FROM venues_merged WHERE lat IS NULL "
                        "OR lng IS NULL OR lat=0 OR lng=0 OR name IS NULL OR name=''"))
    details.append(f"bad_rows={bad}")
    if bad:
        ok = False
        details.append(f"G4 FAIL: {bad} rows with bad coords/names")
    prov = int(mysql_one("SELECT COUNT(*) FROM venues_merged WHERE source LIKE '%overture%'"))
    details.append(f"overture_provenance_rows={prov}")
    if merged_total and prov / merged_total < G5_MIN:
        ok = False
        details.append(f"G5 FAIL: overture provenance {prov / merged_total:.3f} < {G5_MIN}")
    return ok, merged_total, details


def write_report(status, lines):
    os.makedirs(LOGDIR, exist_ok=True)
    body = [f"Neutral Eats monthly refresh — {now()}",
            f"STATUS: {status}", ""] + lines
    with open(REPORT_PATH, "w") as fh:
        fh.write("\n".join(body) + "\n")
    for ln in body:
        print(ln)


def finish_with_monitor(report_lines):
    """Append a venue-count snapshot to the report lines (never fatal)."""
    try:
        rec, anomaly = venue_monitor.run_snapshot(HISTORY_PATH, LOGDIR)
        report_lines.append(f"monitor: total={rec['total']} metros={rec['metros']}")
        if anomaly:
            report_lines.append(f"monitor: *** ANOMALY: {anomaly} ***")
    except Exception as exc:  # monitor must never mask the run's outcome
        report_lines.append(f"monitor: FAILED to run ({exc})")
    return report_lines


def fail(status, lines, run_dir=None):
    lines = finish_with_monitor(lines)
    write_report(status, lines)
    cleanup(run_dir)
    return 1


def cleanup(run_dir):
    """Drop the run's S3 mirror and prune old run dirs (keep previous run)."""
    try:
        if run_dir:
            mirror = os.path.join(run_dir, "gate2", "s3")
            if os.path.isdir(mirror):
                shutil.rmtree(mirror, ignore_errors=True)
                log(f"cleanup: removed mirror {mirror}")
        if os.path.isdir(RUNS_DIR):
            runs = sorted(
                (os.path.join(RUNS_DIR, d) for d in os.listdir(RUNS_DIR)
                 if os.path.isdir(os.path.join(RUNS_DIR, d))),
                key=os.path.getmtime)
            for old in runs[:-2]:
                shutil.rmtree(old, ignore_errors=True)
                log(f"cleanup: pruned old run dir {old}")
    except Exception as exc:
        log(f"cleanup: warning ({exc})")


def main():
    ap = argparse.ArgumentParser(description="Neutral Eats monthly Overture refresh")
    ap.add_argument("--check", action="store_true",
                    help="read-only: report recorded vs latest release, exit 0")
    args = ap.parse_args()

    with open(STATE_PATH) as fh:
        state = json.load(fh)
    recorded = state["release"]
    latest = latest_release()

    if args.check:
        print(f"recorded release: {recorded}")
        print(f"latest release:   {latest}")
        print("no new release" if latest <= recorded
              else f"new release available: {latest}")
        return 0

    # Exclusive lock for the whole run — overlapping runs are forbidden.
    os.makedirs(LOGDIR, exist_ok=True)
    lock_fh = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print(f"[{now()}] another refresh run holds {LOCK_PATH}; exiting")
        return 3
    lock_fh.write(f"pid {os.getpid()} since {now()}\n")
    lock_fh.flush()

    global _run_log_fh
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    run_log_path = os.path.join(LOGDIR, f"refresh-{stamp}.log")
    _run_log_fh = open(run_log_path, "a")
    log(f"monthly refresh starting; run log: {run_log_path}")
    log(f"recorded release={recorded} latest release={latest}")

    if latest <= recorded:
        lines = [f"recorded_release={recorded}", f"latest_release={latest}",
                 "no new release; production untouched"]
        lines = finish_with_monitor(lines)
        write_report("NO_NEW_RELEASE", lines)
        log("no new release; exiting quietly")
        return 0

    # ---- New release: extract + merge in a fresh per-run workdir. ----
    run_dir = os.path.join(RUNS_DIR, f"{latest}-{stamp}")
    gate_wd = os.path.join(run_dir, "gate2")
    os.makedirs(gate_wd, exist_ok=True)
    lines = [f"recorded_release={recorded}", f"new_release={latest}",
             f"run_dir={run_dir}", f"run_log={run_log_path}"]

    live_total = int(mysql_one("SELECT COUNT(*) FROM venues"))
    lines.append(f"live_total_before={live_total}")
    log(f"new release {latest}; live total before = {live_total}")

    py = sys.executable or "/usr/bin/python3"
    extract = os.path.join(PIPELINE_DIR, "extract_overture.py")
    merge = os.path.join(PIPELINE_DIR, "merge_overture.py")

    if run_step("extract", [py, extract, "--nationwide", "--release", latest,
                            "--workdir", run_dir], run_log_path) != 0:
        log("*** EXTRACT FAILED — production untouched, no cutover ***")
        lines.append("FAILED at extract stage; see run log")
        return fail("FAILED_EXTRACT", lines, run_dir)

    for stage in ("dedupe", "match", "build", "load"):
        if run_step(f"merge-{stage}", [py, merge, stage, "--workdir", gate_wd],
                    run_log_path) != 0:
            log(f"*** MERGE {stage} FAILED — production untouched, no cutover ***")
            lines.append(f"FAILED at merge stage {stage}; see run log")
            return fail(f"FAILED_MERGE_{stage.upper()}", lines, run_dir)

    if run_step("merge-verify", [py, merge, "verify", "--workdir", gate_wd],
                run_log_path) != 0:
        log("*** MERGE verify FAILED — production untouched, no cutover ***")
        lines.append("FAILED at merge verify stage; see run log")
        return fail("FAILED_VERIFY", lines, run_dir)

    ok, merged_total, details = gates(live_total)
    lines += ["gates:"] + [f"  {d}" for d in details]
    if not ok:
        log("*** RECONCILIATION GATES FAILED — NO CUTOVER, production untouched ***")
        lines.append("one or more reconciliation gates failed; NO CUTOVER")
        return fail("FAILED_GATES", lines, run_dir)
    log(f"all gates passed; merged_total={merged_total}")

    # ---- Cut over via the pipeline's own reviewed stage. ----
    if run_step("merge-cutover", [py, merge, "cutover", "--yes",
                                  "--workdir", gate_wd], run_log_path) != 0:
        log("*** CUTOVER STAGE FAILED — CHECK PRODUCTION STATE MANUALLY ***")
        lines.append("cutover stage exited nonzero; production state must "
                     "be checked manually before any retry")
        return fail("FAILED_CUTOVER", lines, run_dir)

    new_total = int(mysql_one("SELECT COUNT(*) FROM venues"))
    lines.append(f"live_total_after={new_total}")
    if new_total != merged_total:
        lines.append(f"WARNING: post-cutover total {new_total} != merged "
                     f"total {merged_total} (expected equal)")

    # ---- Rotate the rollback table: keep exactly one legacy table. ----
    prev_legacy = state.get("legacy_table")
    tables = legacy_tables()
    new_candidates = [t for t in tables if t != prev_legacy]
    rotation_note = "rotation: no previous legacy table found to drop"
    if len(new_candidates) == 1:
        new_legacy = new_candidates[0]
        dropped = []
        for t in tables:
            if t != new_legacy:
                mysql_one(f"DROP TABLE `{t}`")
                dropped.append(t)
        state["legacy_table"] = new_legacy
        rotation_note = (f"rotation: kept {new_legacy}; dropped {dropped or '[]'}")
    else:
        rotation_note = (f"rotation: SKIPPED (candidates={new_candidates}, "
                         f"tables={tables}); no table dropped — resolve manually")
        log(f"*** {rotation_note} ***")
    lines.append(rotation_note)
    log(rotation_note)

    state.update({
        "release": latest,
        "last_run_at": now(),
        "last_cutover_at": now(),
        "last_status": "SUCCESS",
        "venues_count_before": live_total,
        "venues_count_after": new_total,
    })
    with open(STATE_PATH, "w") as fh:
        json.dump(state, fh, indent=2)
    lines.append(f"state updated: release={latest} legacy={state.get('legacy_table')}")
    log(f"refresh complete: {live_total} -> {new_total} venues on release {latest}")

    lines = finish_with_monitor(lines)
    write_report("SUCCESS", lines)
    cleanup(run_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
