#!/usr/bin/env python3
"""fl_dbpr_apply.py — apply the reviewed FL DBPR pilot to `venues`.

Approved by Croix 2026-10-26 (option: "Go, but stamp STRONG +
MEDIUM too"). Two writes, both reversible from the backup table:

  1. STAMP license_number / license_status / last_inspection_date
     on every matched venue (STRONG + MEDIUM tiers), from the
     fl_dbpr_matches audit table. Status codes map 20 -> current,
     45 -> delinquent, 46 -> relinquished.
  2. CLOSE the strict-rule closure set: lic_status 46 (any), or
     lic_status 45 with expiry on/before 2024-12-31 AND no sign
     of life in 2026 (last inspection on/before 2025-12-31 or
     none). Exactly 9 venues. (Rule history: the match audit's
     original flag used a looser 2025 expiry boundary — 70 flags,
     mostly the late-renewal cohort. A first apply draft with an
     OR-form rule counted 23 and aborted on its own guard: it
     swept in 13 venues inspected in 2026 — alive, however stale
     their licenses — plus 1 fresh delinquency. The final rule
     above is the conjunction that matches the set Croix
     approved; this script rewrites the audit flags to it so
     the audit trail stays truthful.)
     Closed venues get is_active=0 + operating_status=
     'permanently_closed' (licensing > Overture authority).

Before any write, every venue row about to be touched is copied
to venues_backup_20261026_fl. Rollback = restore from that table.

Run on the host (root MySQL via unix socket):
    python3 fl_dbpr_apply.py
"""
import subprocess
import sys

BACKUP = "venues_backup_20261026_fl"
JOIN = "v.id = m.venue_id COLLATE utf8mb4_unicode_ci"


def run(sql, capture=True):
    proc = subprocess.run(["mysql", "-uroot", "-N", "-B",
                           "neutraleats", "-e", sql],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr[:1500], file=sys.stderr)
        raise SystemExit(1)
    return proc.stdout.strip()


def main():
    # 0) Refuse to run twice over an existing backup.
    exists = run(f"SELECT COUNT(*) FROM information_schema.tables "
                 f"WHERE table_schema='neutraleats' "
                 f"AND table_name='{BACKUP}'")
    if exists != "0":
        print(f"{BACKUP} already exists — apply already ran; aborting")
        return 1

    # 1) Rewrite audit flags to the STRICT closure rule.
    run("""
UPDATE fl_dbpr_matches SET closure_candidate =
  CASE WHEN lic_status='46' THEN 1
       WHEN lic_status='45' AND expiry_date <= '2024-12-31'
            AND (last_inspection <= '2025-12-31'
                 OR last_inspection IS NULL) THEN 1
       ELSE 0 END;
""")
    run("""
UPDATE fl_dbpr_matches SET watchlist =
  CASE WHEN lic_status='45' AND closure_candidate=0 THEN 1
       ELSE 0 END;
""")
    n_closure = run("SELECT COUNT(*) FROM fl_dbpr_matches "
                    "WHERE closure_candidate=1")
    n_watch = run("SELECT COUNT(*) FROM fl_dbpr_matches "
                  "WHERE watchlist=1")
    print(f"strict closure set: {n_closure} (expect 9); "
          f"watchlist: {n_watch}")
    if n_closure != "9":
        print("closure count is not 9 — aborting before any venue write")
        return 1

    # 2) Backup every venue row we are about to touch.
    run(f"CREATE TABLE {BACKUP} AS "
        f"SELECT v.* FROM venues v JOIN fl_dbpr_matches m ON {JOIN}")
    n_backup = run(f"SELECT COUNT(*) FROM {BACKUP}")
    print(f"backed up venue rows: {n_backup}")

    # 3) Stamp license fields on all matched venues.
    run(f"""
UPDATE venues v JOIN fl_dbpr_matches m ON {JOIN}
SET v.license_number = m.license_number,
    v.license_status = CASE m.lic_status
        WHEN '20' THEN 'current'
        WHEN '45' THEN 'delinquent'
        WHEN '46' THEN 'relinquished'
        ELSE m.lic_status END,
    v.last_inspection_date = m.last_inspection;
""")
    n_stamped = run("SELECT COUNT(*) FROM venues "
                    "WHERE state='FL' AND license_number IS NOT NULL")
    print(f"FL venues stamped with license_number: {n_stamped}")

    # 4) Close the strict-9.
    run(f"""
UPDATE venues v JOIN fl_dbpr_matches m ON {JOIN}
SET v.is_active = 0, v.operating_status = 'permanently_closed'
WHERE m.closure_candidate = 1;
""")
    closed = run(f"""
SELECT v.name, v.city, m.lic_status, m.expiry_date,
       m.last_inspection, m.tier
FROM venues v JOIN fl_dbpr_matches m ON {JOIN}
WHERE m.closure_candidate = 1 ORDER BY v.name;
""")
    print("closed venues:")
    print(closed)
    n_inactive = run("SELECT COUNT(*) FROM venues WHERE state='FL' "
                     "AND is_active=0")
    print(f"FL venues now inactive: {n_inactive} (expect 9)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
