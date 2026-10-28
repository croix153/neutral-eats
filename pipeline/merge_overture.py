#!/usr/bin/env python3
"""
Neutral Eats — merge Overture staging into a production-shaped table.

PIPELINE POSITION
-----------------
Runs AFTER extract_overture.py --nationwide has produced a deduped staging
dataset. This script NEVER mutates the production `venues` table. It builds
`venues_merged` (CREATE TABLE LIKE venues) that a reviewed cutover step can
swap in atomically:

    RENAME TABLE venues TO venues_legacy_YYYYMMDD, venues_merged TO venues;

STAGES (run in order; each is idempotent and file-based under --workdir)
------------------------------------------------------------------------
  dedupe   Intra-Overture dedupe of the nationwide staging TSV
           (us_food.tsv -> kept.tsv): same normalized name within 50 m
           under different Overture ids collapses to the most complete row
           (phone/website/address/zip presence, then confidence).
  match    Candidate generation between production venues and kept staging
           rows (DuckDB grid join, haversine), then greedy assignment:
             pass 1: same normalized name, <= 50 m
             pass 2: <= 150 m and name token match (one token set a subset
                     of the other, or token Jaccard >= 0.6)
           Emits pairs.tsv (prod_id, staging_id, pass, distance_m).
  build    Emits venues_merged.tsv with the full production column set:
             - production-only rows: copied verbatim
             - overture-only rows:  built from staging (see FIELD RULES)
             - merged rows:         production row wins; staging fills gaps
           Unmatched production rows are ALL kept (a later cleanup decision
           can use the unmatched-production report this stage prints).
  load     Creates `venues_merged` LIKE `venues` and bulk-loads the TSV as
           the MySQL root user over the local socket (server-side LOAD DATA
           INFILE via secure_file_priv — same pattern as the extractor; the
           app user's credentials are only ever used inside PHP helpers).
  verify   Prints totals by provenance and per-metro bbox counts for
           venues_merged vs the production table.
  cutover  Only with --yes: mysqldump backup to /root/backups/, then the
           atomic RENAME swap, then live-API spot checks over HTTPS.

FIELD RULES (merged-both rows)
------------------------------
  production wins: name, coords, rating, price_level, cuisine text, hours,
    photos, first_seen, is_active, operating_status, and every other
    production-only column.
  staging fills gaps (only where production is NULL/empty): address
    (composed street, city, ST zip), city, state, zip, phone, website,
    brand; cuisine falls back to the humanized Overture category_primary;
    type falls back to the staging type when the production type is not in
    KNOWN_TYPES (legacy data contains junk types such as '0').
  provenance: source becomes '<prod_source>+overture' and metadata gains
    {"merged_from": ["<prod_source>:<prod_source_id>", "overture:<id>"],
     "merge_pass": 1|2}. Overture-only rows get source='overture' and serve
    category_primary (humanized) as cuisine when staging cuisine is empty.

CREDENTIALS: none in this file. Production exports run through a generated
PHP helper that requires the live site config and is deleted after use.

USAGE
-----
    python3 merge_overture.py all       --workdir /root/overture-work/gate2
    python3 merge_overture.py verify    --workdir /root/overture-work/gate2
    python3 merge_overture.py cutover   --workdir /root/overture-work/gate2 --yes
"""

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time

DEFAULT_WORKDIR = "/root/overture-work/gate2"
DEFAULT_PHP_CONFIG = "/var/www/html/minerva/config/database.php"
DUCKDB_CANDIDATES = ("/root/overture-work/duckdb", "duckdb")
KNOWN_TYPES = {"restaurant", "cafe", "bar", "bakery", "fast_food", "pub"}
NULL = "\\N"

# Production `venues` columns, in table order (venues_merged mirrors them).
VENUES_COLS = [
    "id", "name", "lat", "lng", "type", "cuisine", "brand", "source",
    "source_id", "rating", "price_level", "address", "city", "state", "zip",
    "phone", "website", "hours", "photos", "first_seen", "is_active",
    "check_count", "grid_cell", "sub_source", "rating_count", "county",
    "hours_confirmed", "license_number", "license_status",
    "inspection_score", "last_inspection_date", "metadata",
    "confidence_score", "last_verified", "operating_status",
    "data_freshness", "last_updated",
]
# Staging TSV columns (extractor output) + batch_state.
STAGING_COLS = [
    "id", "name", "lat", "lng", "type", "cuisine", "brand", "source",
    "source_id", "address", "city", "state", "zip", "phone", "website",
    "confidence_score", "category_primary", "norm_name", "batch_state",
    "operating_status",
]

METROS = {
    "orlando": (28.45, 28.60, -81.45, -81.25),
    "lake_mary": (28.70, 28.78, -81.38, -81.28),
    "miami": (25.65, 25.95, -80.45, -80.10),
    "nyc": (40.60, 40.85, -74.05, -73.85),
    "chicago": (41.75, 41.95, -87.75, -87.55),
    "la": (33.95, 34.15, -118.35, -118.15),
}


def haversine_m(lat1, lng1, lat2, lng2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(a))


def clean_field(v):
    if v is None or v == NULL:
        return NULL
    s = str(v).replace("\t", " ").replace("\n", " ").replace("\r", " ").replace("\\", " ")
    return s if s != "" else NULL


def is_empty(v):
    return v is None or v == NULL or str(v).strip() == ""


def humanize_category(cat):
    if is_empty(cat):
        return None
    return str(cat).replace("_", " ").strip().title() or None


def grid_cell(lat, lng):
    return "%.3f,%.3f" % (math.floor(lat / 0.02) * 0.02, math.floor(lng / 0.02) * 0.02)


def compose_address(st):
    parts = []
    if not is_empty(st["address"]):
        parts.append(st["address"])
    if not is_empty(st["city"]):
        parts.append(st["city"])
    tail = " ".join(x for x in (st["state"], st["zip"]) if not is_empty(x))
    if tail:
        parts.append(tail)
    return ", ".join(parts) if parts else None


# ---------------------------------------------------------------- dedupe ---
def stage_dedupe(wd):
    src = os.path.join(wd, "us_food.tsv")
    kept_path = os.path.join(wd, "kept.tsv")
    total = 0
    dropped = 0
    groups = 0

    def completeness(fields):
        score = 0
        for idx in (13, 14, 9, 12):  # phone, website, address, zip
            if fields[idx].strip():
                score += 1
        try:
            score += float(fields[15] or 0)
        except ValueError:
            pass
        return score

    def flush(group, out):
        nonlocal dropped, groups
        if not group:
            return
        groups += 1
        if len(group) == 1:
            out.write(group[0][0])
            return
        parent = list(range(len(group)))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        order = sorted(range(len(group)), key=lambda i: (group[i][2], group[i][3]))
        for a_idx in range(len(order)):
            i = order[a_idx]
            for b_idx in range(a_idx + 1, len(order)):
                j = order[b_idx]
                if group[j][2] - group[i][2] > 0.0005:  # > ~55 m of latitude
                    break
                if haversine_m(group[i][2], group[i][3], group[j][2], group[j][3]) <= 50:
                    ri, rj = find(i), find(j)
                    if ri != rj:
                        parent[rj] = ri
        clusters = {}
        for i in range(len(group)):
            clusters.setdefault(find(i), []).append(i)
        for members in clusters.values():
            best = max(members, key=lambda i: completeness(group[i][1]))
            out.write(group[best][0])
            dropped += len(members) - 1

    cur_name = None
    group = []
    with open(src, encoding="utf-8") as fh, open(kept_path, "w", encoding="utf-8") as out:
        for line in fh:
            total += 1
            fields = line.rstrip("\n").split("\t")
            if len(fields) != len(STAGING_COLS):
                sys.exit(f"dedupe: bad column count on line {total}: {len(fields)}")
            name = fields[17]
            if name != cur_name:
                flush(group, out)
                group = []
                cur_name = name
            group.append((line, fields, float(fields[2]), float(fields[3])))
        flush(group, out)
    print(f"[dedupe] input={total} dropped_intra_overture={dropped} "
          f"kept={total - dropped} name_groups={groups}")
    return total - dropped


# ----------------------------------------------------------------- match ---
def find_duckdb():
    for cand in DUCKDB_CANDIDATES:
        if os.path.sep in cand and os.path.exists(cand):
            return cand
    return "duckdb"


def run_php_export(wd, php_config):
    """Export production venues (light + full TSVs) via a PHP helper."""
    helper = os.path.join(wd, "_export.php")
    code = r"""<?php
[$_s, $cfg, $lightPath, $fullPath] = $argv;
require_once $cfg;
$pdo = getDatabaseConnection();
$pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
function esc($v) {
  if ($v === null) return "\\N";
  return str_replace(["\t", "\n", "\r", "\\"], " ", (string)$v);
}
$light = fopen($lightPath, "w");
$q = $pdo->query("SELECT id, REGEXP_REPLACE(LOWER(TRIM(name)), '[^a-z0-9 ]', '') AS nn, lat, lng FROM venues");
while ($r = $q->fetch(PDO::FETCH_ASSOC)) {
  fwrite($light, implode("\t", [esc($r['id']), esc($r['nn']), $r['lat'], $r['lng']]) . "\n");
}
fclose($light);
$cols = "__COLS__";
$full = fopen($fullPath, "w");
$q = $pdo->query("SELECT " . str_replace("last_updated", "DATE_FORMAT(last_updated, '%Y-%m-%d %H:%i:%s') AS last_updated", $cols) . " FROM venues");
while ($r = $q->fetch(PDO::FETCH_ASSOC)) {
  $row = [];
  foreach (explode(",", "__COLS__") as $c) { $row[] = esc($r[trim($c)]); }
  fwrite($full, implode("\t", $row) . "\n");
}
fclose($full);
echo "exported\n";
"""
    code = code.replace("__COLS__", ",".join(VENUES_COLS))
    with open(helper, "w") as fh:
        fh.write(code)
    try:
        proc = subprocess.run(
            ["php", helper, php_config,
             os.path.join(wd, "prod_light.tsv"), os.path.join(wd, "prod_full.tsv")],
            capture_output=True, text=True)
        sys.stdout.write(proc.stdout)
        if proc.returncode != 0:
            sys.exit(f"export failed:\n{proc.stderr[-1500:]}")
    finally:
        os.unlink(helper)


def stage_match(wd, php_config):
    run_php_export(wd, php_config)
    kept = os.path.join(wd, "kept.tsv")
    stg_light = os.path.join(wd, "stg_light.tsv")
    with open(kept, encoding="utf-8") as fh, open(stg_light, "w", encoding="utf-8") as out:
        for line in fh:
            f = line.rstrip("\n").split("\t")
            out.write("\t".join([f[0], f[17], f[2], f[3]]) + "\n")
    duckdb = find_duckdb()
    sql = f"""
LOAD spatial;
CREATE TABLE prod AS SELECT * FROM read_csv('{wd}/prod_light.tsv', header=false,
  columns={{'id':'VARCHAR','nn':'VARCHAR','lat':'DOUBLE','lng':'DOUBLE'}}, sep='\t', nullstr='\\\\N');
CREATE TABLE stg AS SELECT * FROM read_csv('{wd}/stg_light.tsv', header=false,
  columns={{'id':'VARCHAR','nn':'VARCHAR','lat':'DOUBLE','lng':'DOUBLE'}}, sep='\t', nullstr='\\\\N');
COPY (
  SELECT p.id AS prod_id, s.id AS stg_id,
    6371000 * 2 * asin(sqrt(
      power(sin(radians((s.lat - p.lat) / 2)), 2) +
      cos(radians(p.lat)) * cos(radians(s.lat)) *
      power(sin(radians((s.lng - p.lng) / 2)), 2))) AS dist,
    CASE WHEN p.nn = s.nn AND dist <= 50 THEN 1 ELSE 2 END AS pass,
    p.nn AS prod_nn, s.nn AS stg_nn
  FROM prod p JOIN stg s
    ON floor(s.lat / 0.0016) BETWEEN floor(p.lat / 0.0016) - 1 AND floor(p.lat / 0.0016) + 1
   AND floor(s.lng / 0.0016) BETWEEN floor(p.lng / 0.0016) - 1 AND floor(p.lng / 0.0016) + 1
  WHERE dist <= 150
) TO '{wd}/candidates.tsv' (HEADER true, DELIM '\t');
"""
    proc = subprocess.run([duckdb, "-list", "-noheader"], input=sql,
                          capture_output=True, text=True, cwd=wd)
    if proc.returncode != 0:
        sys.exit(f"duckdb candidate join failed:\n{proc.stderr[-1500:]}")

    def tokens(nn):
        return set(t for t in nn.split(" ") if t)

    def token_match(a, b):
        ta, tb = tokens(a), tokens(b)
        if not ta or not tb:
            return 0.0, False
        inter = len(ta & tb)
        union = len(ta | tb)
        jac = inter / union if union else 0.0
        subset = ta <= tb or tb <= ta
        return jac, subset or jac >= 0.6

    pairs = []
    used_prod, used_stg = set(), set()
    cand = []
    with open(os.path.join(wd, "candidates.tsv"), encoding="utf-8") as fh:
        header = fh.readline()
        for line in fh:
            prod_id, stg_id, dist, pss, pnn, snn = line.rstrip("\n").split("\t")
            cand.append((prod_id, stg_id, float(dist), int(pss), pnn, snn))
    pass1 = sorted((c for c in cand if c[3] == 1), key=lambda c: c[2])
    pass2 = []
    for c in cand:
        if c[3] != 2:
            continue
        jac, ok = token_match(c[4], c[5])
        if ok:
            pass2.append((c, jac))
    pass2 = [c for c, _ in sorted(pass2, key=lambda cj: (-cj[1], cj[0][2]))]
    for prod_id, stg_id, dist, pss, _a, _b in pass1:
        if prod_id in used_prod or stg_id in used_stg:
            continue
        used_prod.add(prod_id); used_stg.add(stg_id)
        pairs.append((prod_id, stg_id, 1, dist))
    n1 = len(pairs)
    for prod_id, stg_id, dist, pss, _a, _b in pass2:
        if prod_id in used_prod or stg_id in used_stg:
            continue
        used_prod.add(prod_id); used_stg.add(stg_id)
        pairs.append((prod_id, stg_id, 2, dist))
    with open(os.path.join(wd, "pairs.tsv"), "w", encoding="utf-8") as out:
        for prod_id, stg_id, pss, dist in pairs:
            out.write(f"{prod_id}\t{stg_id}\t{pss}\t{dist:.1f}\n")
    print(f"[match] candidates={len(cand)} pass1_matches={n1} "
          f"pass2_matches={len(pairs) - n1} total_pairs={len(pairs)}")
    return pairs


# ----------------------------------------------------------------- build ---
def stage_build(wd):
    now_epoch = int(time.time())
    now_ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now_epoch))
    pairs = {}
    stg_for_prod = {}
    with open(os.path.join(wd, "pairs.tsv"), encoding="utf-8") as fh:
        for line in fh:
            prod_id, stg_id, pss, _d = line.rstrip("\n").split("\t")
            pairs[prod_id] = (stg_id, int(pss))
            stg_for_prod[stg_id] = prod_id

    prod = {}
    with open(os.path.join(wd, "prod_full.tsv"), encoding="utf-8") as fh:
        for line in fh:
            f = line.rstrip("\n").split("\t")
            if len(f) != len(VENUES_COLS):
                sys.exit(f"build: prod row has {len(f)} cols")
            prod[f[0]] = dict(zip(VENUES_COLS, f))

    matched_stg = {}
    if stg_for_prod:
        with open(os.path.join(wd, "kept.tsv"), encoding="utf-8") as fh:
            for line in fh:
                f = line.rstrip("\n").split("\t")
                if f[0] in stg_for_prod:
                    matched_stg[f[0]] = dict(zip(STAGING_COLS, f))

    out_path = os.path.join(wd, "venues_merged.tsv")
    n_prod_only = n_merged = n_ov_only = 0
    unmatched_by_source = {}
    unmatched_by_type = {}
    with open(out_path, "w", encoding="utf-8") as out:

        def emit(row):
            out.write("\t".join(clean_field(row.get(c)) for c in VENUES_COLS) + "\n")

        for prod_id, prow in prod.items():
            if prod_id not in pairs:
                n_prod_only += 1
                unmatched_by_source[prow["source"]] = unmatched_by_source.get(prow["source"], 0) + 1
                unmatched_by_type[prow["type"]] = unmatched_by_type.get(prow["type"], 0) + 1
                # grid_cell: always recompute from the row's own coordinates.
                # Carried legacy values include NULLs and the retired
                # Minerva-era 0.04-degree formats; the API grid prefilter
                # trusts this column (repair census 2026-10-27).
                prow = dict(prow)
                prow["grid_cell"] = grid_cell(float(prow["lat"]), float(prow["lng"]))
                emit(prow)
                continue
            stg_id, pss = pairs[prod_id]
            st = matched_stg[stg_id]
            row = dict(prow)
            # grid_cell: recompute from the row's own coordinates (see the
            # prod-only branch above — never carry a legacy value forward).
            row["grid_cell"] = grid_cell(float(row["lat"]), float(row["lng"]))
            if is_empty(row["address"]):
                row["address"] = compose_address(st)
            for col in ("city", "state", "zip", "phone", "website", "brand"):
                if is_empty(row[col]) and not is_empty(st[col]):
                    row[col] = st[col]
            if is_empty(row["cuisine"]):
                row["cuisine"] = st["cuisine"] if not is_empty(st["cuisine"]) else humanize_category(st["category_primary"])
            if row["type"] not in KNOWN_TYPES:
                row["type"] = st["type"]
            if is_empty(row["confidence_score"]):
                row["confidence_score"] = st["confidence_score"]
            # Status basis (STATUS-BASIS.md): staging operating_status wins
            # when Overture asserts one; permanently_closed suppresses the
            # row. Never force is_active back to 1 here — a licensing-layer
            # suppression already on the production row must survive merges.
            st_status = st.get("operating_status")
            if not is_empty(st_status):
                row["operating_status"] = st_status
                if st_status == "permanently_closed":
                    row["is_active"] = "0"
            row["source"] = f"{prow['source']}+overture"
            meta = {"merged_from": [f"{prow['source']}:{prow['source_id']}", f"overture:{st['source_id']}"],
                    "merge_pass": pss, "merged_at": "2026-10-25"}
            if not is_empty(prow["metadata"]):
                meta["production_metadata"] = prow["metadata"]
            row["metadata"] = json.dumps(meta)
            row["last_updated"] = now_ts
            n_merged += 1
            emit(row)

        with open(os.path.join(wd, "kept.tsv"), encoding="utf-8") as fh:
            for line in fh:
                f = line.rstrip("\n").split("\t")
                st = dict(zip(STAGING_COLS, f))
                if st["id"] in stg_for_prod:
                    continue
                cuisine = st["cuisine"] if not is_empty(st["cuisine"]) else humanize_category(st["category_primary"])
                st_status = st["operating_status"] if not is_empty(st["operating_status"]) else None
                row = {
                    "id": st["id"], "name": st["name"], "lat": st["lat"], "lng": st["lng"],
                    "type": st["type"], "cuisine": cuisine, "brand": st["brand"],
                    "source": "overture", "source_id": st["source_id"], "rating": None,
                    "price_level": None, "address": compose_address(st), "city": st["city"],
                    "state": st["state"], "zip": st["zip"], "phone": st["phone"],
                    "website": st["website"], "hours": None, "photos": None,
                    "first_seen": now_epoch,
                    "is_active": 0 if st_status == "permanently_closed" else 1,
                    "check_count": 1,
                    "grid_cell": grid_cell(float(st["lat"]), float(st["lng"])),
                    "sub_source": None, "rating_count": 0, "county": None,
                    "hours_confirmed": 0, "license_number": None, "license_status": None,
                    "inspection_score": None, "last_inspection_date": None, "metadata": None,
                    "confidence_score": st["confidence_score"], "last_verified": None,
                    "operating_status": st_status, "data_freshness": "high",
                    "last_updated": now_ts,
                }
                n_ov_only += 1
                emit(row)
    print(f"[build] prod_only={n_prod_only} merged_both={n_merged} overture_only={n_ov_only} "
          f"total={n_prod_only + n_merged + n_ov_only}")
    print(f"[build] unmatched production by source: {json.dumps(unmatched_by_source, sort_keys=True)}")
    top_types = sorted(unmatched_by_type.items(), key=lambda kv: -kv[1])[:10]
    print(f"[build] unmatched production by type (top): {json.dumps(top_types)}")
    return {"prod_only": n_prod_only, "merged": n_merged, "overture_only": n_ov_only}


# ------------------------------------------------------------------ load ---
def mysql_root(wd, sql, database=None):
    cmd = ["mysql", "-u", "root", "-N"]
    if database:
        cmd.append(database)
    cmd += ["-e", sql]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"mysql failed:\n{proc.stderr[-1500:]}")
    return proc.stdout.strip()


def stage_load(wd):
    mysql_root(wd, "DROP TABLE IF EXISTS venues_merged; "
                   "CREATE TABLE venues_merged LIKE venues;",
               database="neutraleats")
    priv = mysql_root(wd, "SELECT @@GLOBAL.secure_file_priv")
    if not priv:
        sys.exit("secure_file_priv empty; cannot LOAD DATA INFILE")
    staged = os.path.join(priv, "venues_merged.tsv")
    subprocess.run(["cp", os.path.join(wd, "venues_merged.tsv"), staged], check=True)
    subprocess.run(["chown", "mysql:mysql", staged], check=True)
    cols = ",".join(f"`{c}`" for c in VENUES_COLS)
    n = mysql_root(wd, f"LOAD DATA INFILE '{staged}' INTO TABLE venues_merged "
                       f"CHARACTER SET utf8mb4 FIELDS TERMINATED BY '\\t' "
                       f"LINES TERMINATED BY '\\n' ({cols}); SELECT ROW_COUNT();",
                   database="neutraleats")
    os.unlink(staged)
    total = mysql_root(wd, "SELECT COUNT(*) FROM venues_merged", database="neutraleats")
    print(f"[load] venues_merged rows loaded: {n}; table count: {total}")


def stage_verify(wd):
    def counts(table):
        rows = mysql_root(wd, f"SELECT source, COUNT(*) FROM {table} GROUP BY source ORDER BY 2 DESC",
                          database="neutraleats")
        print(f"  {table} by source:")
        for line in rows.splitlines():
            print(f"    {line}")
        tot = mysql_root(wd, f"SELECT COUNT(*) FROM {table}", database="neutraleats")
        print(f"  {table} total: {tot}")
        return tot

    print("[verify] provenance totals")
    counts("venues")
    counts("venues_merged")
    print("[verify] metro bbox counts (venues -> venues_merged)")
    for name, (s, n, w, e) in METROS.items():
        a = mysql_root(wd, f"SELECT COUNT(*) FROM venues WHERE is_active=1 AND lat BETWEEN {s} AND {n} AND lng BETWEEN {w} AND {e}",
                       database="neutraleats")
        b = mysql_root(wd, f"SELECT COUNT(*) FROM venues_merged WHERE is_active=1 AND lat BETWEEN {s} AND {n} AND lng BETWEEN {w} AND {e}",
                       database="neutraleats")
        print(f"  {name}: {a} -> {b}")


def stage_cutover(wd):
    stamp = time.strftime("%Y%m%d")
    dump = f"/root/backups/neutraleats-precutover-{stamp}.sql.gz"
    os.makedirs("/root/backups", exist_ok=True)
    proc = subprocess.run(
        f"mysqldump --single-transaction neutraleats | gzip > {dump}",
        shell=True, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"mysqldump failed:\n{proc.stderr[-1000:]}")
    print(f"[cutover] backup written: {dump}")
    legacy = f"venues_legacy_{stamp}"
    mysql_root(wd, f"RENAME TABLE venues TO {legacy}, venues_merged TO venues;",
               database="neutraleats")
    print(f"[cutover] swapped: venues -> {legacy}, venues_merged -> venues")
    total = mysql_root(wd, "SELECT COUNT(*) FROM venues", database="neutraleats")
    print(f"[cutover] live venues total: {total}")
    for name in ("lake_mary", "orlando"):
        s, n, w, e = METROS[name]
        url = (f"https://neutraleats.com/api/venues.php?south={s}&west={w}"
               f"&north={n}&east={e}&limit=500")
        proc = subprocess.run(["curl", "-s", "--max-time", "30", url],
                              capture_output=True, text=True)
        try:
            d = json.loads(proc.stdout)
            got = d.get("count", len(d.get("venues", [])))
        except Exception:
            got = f"unparseable: {proc.stdout[:120]}"
        print(f"[cutover] live API {name}: count={got}")


def main():
    ap = argparse.ArgumentParser(description="Neutral Eats Overture merge")
    ap.add_argument("stage", choices=["dedupe", "match", "build", "load", "verify", "cutover", "all"])
    ap.add_argument("--workdir", default=DEFAULT_WORKDIR)
    ap.add_argument("--php-config", default=DEFAULT_PHP_CONFIG)
    ap.add_argument("--yes", action="store_true", help="required for cutover")
    args = ap.parse_args()
    wd = args.workdir
    os.makedirs(wd, exist_ok=True)
    if args.stage in ("dedupe", "all"):
        stage_dedupe(wd)
    if args.stage in ("match", "all"):
        stage_match(wd, args.php_config)
    if args.stage in ("build", "all"):
        stage_build(wd)
    if args.stage in ("load", "all"):
        stage_load(wd)
    if args.stage in ("verify", "all"):
        stage_verify(wd)
    if args.stage == "cutover":
        if not args.yes:
            sys.exit("cutover requires --yes")
        stage_cutover(wd)


if __name__ == "__main__":
    main()
