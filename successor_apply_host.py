#!/usr/bin/env python3
"""successor_apply_host.py — production apply for the successor sweep.

Runs ON the croix.ai host. Reads successor_apply_set.csv (the v3 set
after ambiguity guards, computed by successor_apply.py) from its own
directory, stages it in MySQL, sanity-gates, backs up, audits, applies
(is_active=0, operating_status='permanently_closed'), and verifies.

Discipline mirrors prior passes (ghost / jittered / DBPR tranche):
re-derive live state, backup table = undo source, audit table = undo
handle, delta must equal applied count exactly. Any gate failure
aborts BEFORE the UPDATE.
"""
import csv
import json
import subprocess
import sys

DB = "neutraleats"
STAGE = "successor_apply_stage_20261027"
BACKUP = "venues_backup_20261027_successor"
AUDIT = "successor_suppressions_20261027"
HABANEROS_ID = "overture:688e947c-c3e2-4e1f-977b-f8dd62afc5b3"
TIANO_ID = "overture:99d46fc3-472c-4403-b80a-f34c3f727285"
TAQ_ID = "overture:c3ebe31a-c2fb-439f-8e4f-927e68aefb83"


def mysql(sql, raw=False):
    cmd = ["mysql", "--default-character-set=utf8mb4", "-B", DB, "-e", sql]
    if raw:
        cmd.insert(2, "-N")
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if p.returncode != 0:
        raise RuntimeError(f"mysql failed: {p.stderr[:800]}\nSQL: {sql[:300]}")
    return p.stdout


def q1(sql):
    out = mysql(sql, raw=True).strip()
    return out.split("\t") if out else []


def esc(s):
    return "'" + str(s if s is not None else "").replace("\\", "\\\\").replace("'", "\\'") + "'"


def main():
    rows = list(csv.DictReader(open("successor_apply_set.csv", newline="", encoding="utf-8")))
    report = {"csv_rows": len(rows)}

    mysql(f"DROP TABLE IF EXISTS {STAGE}")
    mysql(f"""CREATE TABLE {STAGE} (
        venue_id VARCHAR(255) NOT NULL,
        candidate_name TEXT,
        survivor_id VARCHAR(255),
        survivor_name TEXT,
        license_business TEXT,
        license_number VARCHAR(64),
        street VARCHAR(255),
        zip5 VARCHAR(10),
        INDEX idx_vid (venue_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""")
    for i in range(0, len(rows), 400):
        vals = []
        for r in rows[i:i + 400]:
            vals.append("(" + ",".join(esc(r[k]) for k in (
                "candidate_id", "candidate_name", "survivor_id", "survivor_name",
                "license_business", "license_number", "street", "zip5")) + ")")
        mysql(f"INSERT INTO {STAGE} (venue_id, candidate_name, survivor_id, "
              f"survivor_name, license_business, license_number, street, zip5) "
              f"VALUES {','.join(vals)}")
    report["stage_n"] = int(q1(f"SELECT COUNT(*) FROM {STAGE}")[0])

    # Live re-derivation: skip ids missing from production or already inactive.
    report["missing_n"] = int(q1(
        f"SELECT COUNT(*) FROM {STAGE} s LEFT JOIN venues v ON v.id = s.venue_id "
        f"WHERE v.id IS NULL")[0])
    report["already_inactive_n"] = int(q1(
        f"SELECT COUNT(*) FROM {STAGE} s JOIN venues v ON v.id = s.venue_id "
        f"WHERE v.is_active = 0")[0])
    mysql(f"DELETE s FROM {STAGE} s LEFT JOIN venues v ON v.id = s.venue_id "
          f"WHERE v.id IS NULL OR v.is_active = 0")
    applied = int(q1(f"SELECT COUNT(*) FROM {STAGE}")[0])
    report["to_apply"] = applied
    report["self_survivor_n"] = int(q1(
        f"SELECT COUNT(*) FROM {STAGE} WHERE venue_id = survivor_id")[0])
    hab = int(q1(f"SELECT COUNT(*) FROM {STAGE} WHERE venue_id = {esc(HABANEROS_ID)}")[0])
    report["habaneros_in_apply"] = bool(hab)

    # SANITY GATE
    if not (5000 <= applied <= 7120) or not hab or report["self_survivor_n"]:
        report["GATE"] = "FAIL — aborted, nothing applied"
        print(json.dumps(report, indent=1))
        sys.exit(2)
    report["GATE"] = "pass"

    report["active_before"] = int(q1("SELECT COUNT(*) FROM venues WHERE is_active=1")[0])

    # Backup (full rows of everything we will touch).
    mysql(f"DROP TABLE IF EXISTS {BACKUP}")
    mysql(f"CREATE TABLE {BACKUP} AS SELECT v.* FROM venues v "
          f"JOIN {STAGE} s ON s.venue_id = v.id")
    report["backup_n"] = int(q1(f"SELECT COUNT(*) FROM {BACKUP}")[0])
    if report["backup_n"] != applied:
        report["GATE"] = "FAIL — backup count mismatch, aborted before update"
        print(json.dumps(report, indent=1))
        sys.exit(2)

    # Audit table (undo handle).
    mysql(f"DROP TABLE IF EXISTS {AUDIT}")
    mysql(f"""CREATE TABLE {AUDIT} (
        venue_id VARCHAR(255), name TEXT, address TEXT, survivor_name TEXT,
        license_business TEXT, license_number VARCHAR(64), applied_at DATETIME
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""")
    mysql(f"INSERT INTO {AUDIT} (venue_id, name, address, survivor_name, "
          f"license_business, license_number, applied_at) "
          f"SELECT s.venue_id, v.name, v.address, s.survivor_name, "
          f"s.license_business, s.license_number, NOW() "
          f"FROM venues v JOIN {STAGE} s ON s.venue_id = v.id")
    report["audit_n"] = int(q1(f"SELECT COUNT(*) FROM {AUDIT}")[0])
    if report["audit_n"] != applied:
        report["GATE"] = "FAIL — audit count mismatch, aborted before update"
        print(json.dumps(report, indent=1))
        sys.exit(2)

    # APPLY
    mysql(f"UPDATE venues v JOIN {STAGE} s ON s.venue_id = v.id "
          f"SET v.is_active = 0, v.operating_status = 'permanently_closed'")

    # Verification
    report["applied_now_inactive"] = int(q1(
        f"SELECT COUNT(*) FROM venues v JOIN {STAGE} s ON s.venue_id = v.id "
        f"WHERE v.is_active = 0 AND v.operating_status = 'permanently_closed'")[0])
    report["applied_still_active"] = int(q1(
        f"SELECT COUNT(*) FROM venues v JOIN {STAGE} s ON s.venue_id = v.id "
        f"WHERE v.is_active = 1")[0])
    report["active_after"] = int(q1("SELECT COUNT(*) FROM venues WHERE is_active=1")[0])
    report["delta"] = report["active_before"] - report["active_after"]
    report["survivors_active"] = int(q1(
        f"SELECT COUNT(*) FROM {STAGE} s JOIN venues sv ON sv.id = s.survivor_id "
        f"WHERE sv.is_active = 1")[0])
    arch = q1(f"SELECT id, is_active FROM venues WHERE id IN ({esc(TIANO_ID)}, {esc(TAQ_ID)})")
    report["archetype_exclusions_active"] = arch
    print(json.dumps(report, indent=1))

    # Spot-check payload: 10 random applied rows with coords + same-address actives.
    print("=== SPOT ===")
    out = mysql(
        f"SELECT s.venue_id, b.name, b.address, b.lat, b.lng, s.survivor_name, "
        f"(SELECT COUNT(*) FROM venues x WHERE x.address = b.address AND x.is_active = 1), "
        f"(SELECT GROUP_CONCAT(x.name SEPARATOR ' || ') FROM venues x "
        f" WHERE x.address = b.address AND x.is_active = 1) "
        f"FROM {STAGE} s JOIN {BACKUP} b ON b.id = s.venue_id "
        f"ORDER BY RAND() LIMIT 10", raw=True)
    print(out)


if __name__ == "__main__":
    main()
