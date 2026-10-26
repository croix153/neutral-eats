#!/usr/bin/env python3
"""
Neutral Eats — venue-count monitor.

Snapshots the live `venues` table (total row count + per-metro active
counts, using the same bboxes as merge_overture.METROS) and appends one
JSON line per run to the count-history file. A snapshot is an ANOMALY
when the total is 0 or has dropped more than 2% versus the previous
record; anomalies are printed loudly, written to logs/ANOMALY.txt, and
exit with code 2 so cron logs show the failure.

The monthly refresh driver (monthly_refresh.py) calls run_snapshot() at
the end of every run; this script also runs standalone from cron weekly.

USAGE
-----
    python3 venue_monitor.py [--history /root/overture-work/count-history.jsonl]

CREDENTIALS: none. Reads go through the MySQL root socket, same pattern
as the rest of the pipeline.
"""

import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from merge_overture import METROS  # noqa: E402  (same bboxes as the merge verify stage)

BASE = "/root/overture-work"
DEFAULT_HISTORY = os.path.join(BASE, "count-history.jsonl")
DEFAULT_LOGDIR = os.path.join(BASE, "logs")
DROP_THRESHOLD = 0.02  # >2% total drop vs previous record == anomaly


def mysql_one(sql):
    proc = subprocess.run(["mysql", "-u", "root", "-N", "neutraleats", "-e", sql],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"mysql failed: {proc.stderr[-500:]}")
    return proc.stdout.strip()


def snapshot():
    total = int(mysql_one("SELECT COUNT(*) FROM venues"))
    metros = {}
    for name, (s, n, w, e) in METROS.items():
        metros[name] = int(mysql_one(
            f"SELECT COUNT(*) FROM venues WHERE is_active=1 "
            f"AND lat BETWEEN {s} AND {n} AND lng BETWEEN {w} AND {e}"))
    return {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total": total,
        "metros": metros,
    }


def last_record(history_path):
    if not os.path.exists(history_path):
        return None
    last = None
    with open(history_path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                last = json.loads(line)
    return last


def run_snapshot(history_path=DEFAULT_HISTORY, logdir=DEFAULT_LOGDIR):
    """Take a snapshot, append it to history, flag anomalies.

    Returns (record, anomaly_detail_or_None)."""
    rec = snapshot()
    prev = last_record(history_path)
    anomaly = None
    if rec["total"] == 0:
        anomaly = "live venues total is 0"
    elif prev and prev.get("total"):
        drop = (prev["total"] - rec["total"]) / prev["total"]
        if drop > DROP_THRESHOLD:
            anomaly = (f"total dropped {drop:.1%} vs previous record "
                       f"({prev['total']} -> {rec['total']}, threshold {DROP_THRESHOLD:.0%})")
    rec["anomaly"] = anomaly
    os.makedirs(os.path.dirname(history_path), exist_ok=True)
    with open(history_path, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    if anomaly:
        os.makedirs(logdir, exist_ok=True)
        with open(os.path.join(logdir, "ANOMALY.txt"), "w") as fh:
            fh.write(f"VENUE COUNT ANOMALY at {rec['ts']}\n{anomaly}\n"
                     f"record: {json.dumps(rec)}\n")
    return rec, anomaly


def main():
    ap = argparse.ArgumentParser(description="Neutral Eats venue-count monitor")
    ap.add_argument("--history", default=DEFAULT_HISTORY)
    ap.add_argument("--logdir", default=DEFAULT_LOGDIR)
    args = ap.parse_args()
    rec, anomaly = run_snapshot(args.history, args.logdir)
    print(f"[monitor] {rec['ts']} total={rec['total']} "
          f"metros={rec['metros']}")
    if anomaly:
        print(f"[monitor] *** ANOMALY: {anomaly} ***")
        return 2
    print("[monitor] OK (no anomaly)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
