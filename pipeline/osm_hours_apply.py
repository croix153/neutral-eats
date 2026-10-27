#!/usr/bin/env python3
"""FL OSM hours backfill — apply phase (2026-10-27, Croix approved).

Re-derives the probe match set with the probe's exact method
(grid bucket 0.002 deg, haversine <=150 m, folded-name equality OR
difflib SequenceMatcher >= 0.85, nearest candidate wins per POI),
restricted to active FL venues whose hours are currently empty.

When several POIs match the same venue, the venue takes the hours of
its NEAREST matching POI (tie-break: higher name similarity, then
osm_ref) — the per-POI "nearest wins" rule applied symmetrically.

Safety:
  - SANITY BAND: aborts before any DB write if the distinct-venue
    count falls outside +/-10% of the probe's 7,524.
  - Aborts if the backup/audit/stage tables already exist (re-run
    protection — the backup must never be clobbered).
  - Backup of (id, hours, hours_confirmed) for every touched row in
    venues_backup_20261027_osmhours; the apply set + hours written
    are recorded in osm_hours_applied_20261027 (the undo record).
  - UPDATE touches ONLY the hours column, only for staged ids.
    hours_confirmed stays 0 (OSM is community data, not confirmed).

Run on the croix.ai host:  python3 osm_hours_apply.py [--dry-run]
--dry-run performs export + match + band check and writes nothing.
"""
import csv, json, math, re, sys, unicodedata
from difflib import SequenceMatcher

import pymysql

EXPECTED = 7524
BAND_LO = EXPECTED - EXPECTED // 10   # 6772
BAND_HI = EXPECTED + EXPECTED // 10   # 8276
WORKDIR = '/root/osm-hours-probe'
BACKUP_T = 'venues_backup_20261027_osmhours'
AUDIT_T = 'osm_hours_applied_20261027'
STAGE_T = 'osm_hours_stage_20261027'

DRY_RUN = '--dry-run' in sys.argv


def fold(s):
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r'[^a-z0-9 ]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def hav(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def main():
    conn = pymysql.connect(unix_socket='/var/run/mysqld/mysqld.sock',
                           user='root', database='neutraleats',
                           charset='utf8mb4')
    cur = conn.cursor()

    # ---- Step 1: fresh export of candidate venues (probe TSV format)
    cur.execute("""
        SELECT id, name, lat, lng FROM venues
        WHERE state='FL' AND is_active=1 AND (hours IS NULL OR hours='')
          AND lat IS NOT NULL AND lng IS NOT NULL
    """)
    rows = cur.fetchall()
    export_path = WORKDIR + '/venues_fl_emptyhours.tsv'
    with open(export_path, 'w', encoding='utf-8') as f:
        for vid, name, lat, lng in rows:
            clean = (name or '').replace('\t', ' ').replace('\r', ' ').replace('\n', ' ')
            f.write(f"{vid}\t{clean}\t{float(lat)}\t{float(lng)}\n")
    print(f"exported candidate venues (active FL, empty hours): {len(rows)}")

    # ---- Step 2: probe matcher, verbatim, plus osm_ref capture
    venues = []  # (id, name, folded, lat, lng)
    grid = {}
    CELL = 0.002
    with open(export_path, encoding='utf-8') as f:
        for line in f:
            parts = line.rstrip('\n').split('\t')
            if len(parts) != 4:
                continue
            vid, name, lat, lng = parts
            try:
                lat = float(lat); lng = float(lng)
            except ValueError:
                continue
            idx = len(venues)
            venues.append((vid, name, fold(name), lat, lng))
            key = (int(math.floor(lat / CELL)), int(math.floor(lng / CELL)))
            grid.setdefault(key, []).append(idx)

    matched_pois = 0
    per_venue = {}   # venue_id -> best (dist, -sim, osm_ref, hours, venue_name, osm_name)
    total_pois = 0
    with open(WORKDIR + '/pois_with_hours.tsv', encoding='utf-8') as f:
        r = csv.DictReader(f, delimiter='\t')
        for row in r:
            total_pois += 1
            try:
                lat = float(row['lat']); lon = float(row['lon'])
            except (TypeError, ValueError):
                continue
            fname = fold(row['name'])
            cx, cy = int(math.floor(lat / CELL)), int(math.floor(lon / CELL))
            best = None  # (dist, venue_idx, sim)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for vi in grid.get((cx + dx, cy + dy), []):
                        vid, vname, vfold, vlat, vlng = venues[vi]
                        d = hav(lat, lon, vlat, vlng)
                        if d > 150:
                            continue
                        if fname == vfold:
                            sim = 1.0
                        else:
                            sim = SequenceMatcher(None, fname, vfold).ratio()
                        if sim >= 0.85 and (best is None or d < best[0]):
                            best = (d, vi, sim)
            if best:
                matched_pois += 1
                d, vi, sim = best
                vid, vname, vfold, vlat, vlng = venues[vi]
                cand = (round(d, 1), round(sim, 3), row['osm_ref'],
                        row['hours'], vname, row['name'])
                cur_best = per_venue.get(vid)
                # nearest POI wins the venue; tie-break higher sim, then osm_ref
                if cur_best is None or (cand[0], -cand[1], cand[2]) < (cur_best[0], -cur_best[1], cur_best[2]):
                    per_venue[vid] = cand

    distinct = len(per_venue)
    print(f"pois with hours: {total_pois}; matched pois: {matched_pois}; "
          f"distinct venues: {distinct} (probe: {EXPECTED}; band {BAND_LO}-{BAND_HI})")

    if not (BAND_LO <= distinct <= BAND_HI):
        print("STOP: distinct-venue count outside sanity band. No writes made.")
        sys.exit(2)
    if DRY_RUN:
        print("dry run: band check passed; no writes.")
        return

    # ---- Step 3: re-run protection, then backup + audit + apply
    cur.execute("SELECT COUNT(*) FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA='neutraleats' AND TABLE_NAME IN (%s,%s,%s)",
                (BACKUP_T, AUDIT_T, STAGE_T))
    if cur.fetchone()[0]:
        print("STOP: backup/audit/stage table already exists. No writes made.")
        sys.exit(3)

    cur.execute(f"""CREATE TABLE {STAGE_T} (
        venue_id VARCHAR(255) COLLATE utf8mb4_unicode_ci PRIMARY KEY,
        osm_poi_id VARCHAR(64),
        hours TEXT,
        dist_m DECIMAL(7,1),
        sim DECIMAL(5,3)
    )""")
    cur.executemany(
        f"INSERT INTO {STAGE_T} (venue_id, osm_poi_id, hours, dist_m, sim) "
        "VALUES (%s,%s,%s,%s,%s)",
        [(vid, c[2], c[3], c[0], c[1]) for vid, c in per_venue.items()])
    conn.commit()
    cur.execute(f"SELECT COUNT(*) FROM {STAGE_T}")
    staged = cur.fetchone()[0]
    assert staged == distinct, (staged, distinct)

    cur.execute(f"""CREATE TABLE {BACKUP_T} AS
        SELECT v.id, v.hours, v.hours_confirmed
        FROM venues v JOIN {STAGE_T} s ON s.venue_id = v.id""")
    cur.execute(f"SELECT COUNT(*) FROM {BACKUP_T}")
    backed = cur.fetchone()[0]
    assert backed == distinct, (backed, distinct)

    cur.execute(f"""CREATE TABLE {AUDIT_T} (
        venue_id VARCHAR(255) COLLATE utf8mb4_unicode_ci,
        osm_poi_id VARCHAR(64),
        hours_applied TEXT,
        dist_m DECIMAL(7,1),
        sim DECIMAL(5,3),
        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute(f"""INSERT INTO {AUDIT_T} (venue_id, osm_poi_id, hours_applied, dist_m, sim)
        SELECT venue_id, osm_poi_id, hours, dist_m, sim FROM {STAGE_T}""")
    conn.commit()

    cur.execute(f"""UPDATE venues v JOIN {STAGE_T} s ON s.venue_id = v.id
        SET v.hours = s.hours""")
    updated = cur.rowcount
    conn.commit()
    print(f"staged {staged}; backup rows {backed}; UPDATE rowcount {updated}")
    assert updated == distinct, (updated, distinct)

    cur.execute(f"DROP TABLE {STAGE_T}")
    conn.commit()

    # ---- Step 4: verify
    cur.execute("SELECT COUNT(*) FROM venues WHERE state='FL' AND is_active=1 "
                "AND hours IS NOT NULL AND hours<>''")
    fl_with_hours = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM venues WHERE hours IS NOT NULL AND hours<>''")
    all_with_hours = cur.fetchone()[0]
    cur.execute(f"""SELECT v.id, v.name, v.hours FROM venues v
        JOIN {AUDIT_T} a ON a.venue_id = v.id LIMIT 3""")
    samples = cur.fetchall()
    summary = {
        'applied': distinct,
        'fl_active_with_hours_after': fl_with_hours,
        'all_venues_with_hours_after': all_with_hours,
        'backup_table': BACKUP_T, 'backup_rows': backed,
        'audit_table': AUDIT_T,
        'samples': [{'id': s[0], 'name': s[1], 'hours': s[2]} for s in samples],
    }
    print(json.dumps(summary, indent=1))
    with open(WORKDIR + '/apply_summary.json', 'w') as f:
        json.dump(summary, f, indent=1)
    assert fl_with_hours == distinct and all_with_hours == distinct
    print("VERIFY OK: applied count == active-FL-with-hours == all-with-hours")
    conn.close()


if __name__ == '__main__':
    main()
