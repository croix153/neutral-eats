#!/usr/bin/env python3
"""fl_dbpr_load.py — stage Florida DBPR H&R licensee extracts.

Reads the seven weekly district files (hrfood1..7.csv, downloaded
from DBPR's public-records page) and loads them into the
`fl_dbpr_licenses` staging table in the neutraleats database.
Staging is evidence, not truth: nothing here touches `venues`.
The crosswalk (fl_dbpr_match.py) reads this table.

Run on the host (root MySQL via unix socket):
    python3 fl_dbpr_load.py /root/licensing/fl
"""
import csv
import glob
import os
import subprocess
import sys

DDL = """
DROP TABLE IF EXISTS fl_dbpr_licenses;
CREATE TABLE fl_dbpr_licenses (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    license_number   VARCHAR(20), INDEX (license_number),
    license_type     VARCHAR(10),
    rank_code        VARCHAR(10),
    licensee_name    VARCHAR(255),
    business_name    VARCHAR(255),
    loc_address      VARCHAR(255),
    loc_city         VARCHAR(100),
    loc_zip          VARCHAR(10),
    loc_county       VARCHAR(100),
    phone            VARCHAR(30),
    primary_status   VARCHAR(10),
    secondary_status VARCHAR(10),
    expiry_date      DATE NULL,
    last_inspection  DATE NULL,
    seats            INT NULL,
    district         VARCHAR(10),
    extract_file     VARCHAR(40),
    loaded_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
"""


def sql_escape(s):
    return "'" + (s or "").replace("\\", "\\\\").replace("'", "\\'") + "'"


def parse_date(s):
    s = (s or "").strip()
    if not s:
        return "NULL"
    parts = s.split("/")
    if len(parts) != 3:
        return "NULL"
    mm, dd, yyyy = parts
    return f"'{yyyy}-{mm.zfill(2)}-{dd.zfill(2)}'"


def main():
    src_dir = sys.argv[1] if len(sys.argv) > 1 else "/root/licensing/fl"
    files = sorted(glob.glob(os.path.join(src_dir, "hrfood*.csv")))
    if not files:
        print("no hrfood*.csv files found in", src_dir)
        return 1
    rows = []
    for path in files:
        with open(path, newline="", encoding="utf-8", errors="replace") as fh:
            for r in csv.DictReader(fh):
                rows.append((r, os.path.basename(path)))
    print(f"parsed {len(rows)} license rows from {len(files)} files")

    out = [DDL, "TRUNCATE TABLE fl_dbpr_licenses;"]
    BATCH = 1000
    for i in range(0, len(rows), BATCH):
        vals = []
        for r, fname in rows[i:i + BATCH]:
            seats = r.get("Number of Seats or Rental Units", "").strip()
            vals.append("(" + ",".join([
                sql_escape(r["License Number"].strip()),
                sql_escape(r["License Type Code"].strip()),
                sql_escape(r["Rank Code"].strip()),
                sql_escape(r["Licensee Name"].strip()[:255]),
                sql_escape(r["Business Name"].strip()[:255]),
                sql_escape((r["Location Street Address"] + " " +
                            r["Location Address Line 2"]).strip()[:255]),
                sql_escape(r["Location City"].strip()[:100]),
                sql_escape(r["Location Zip Code"].strip()[:10]),
                sql_escape(r["Location County"].strip()[:100]),
                sql_escape(r["Secondary Phone Number"].strip()[:30]),
                sql_escape(r["Primary Status Code"].strip()),
                sql_escape(r["Secondary Status Code"].strip()),
                parse_date(r["License Expiry Date"]),
                parse_date(r["Last Inspection Date"]),
                str(int(seats)) if seats.isdigit() else "NULL",
                sql_escape(r["District"].strip()),
                sql_escape(fname),
            ]) + ")")
        out.append(
            "INSERT INTO fl_dbpr_licenses (license_number, license_type,"
            " rank_code, licensee_name, business_name, loc_address,"
            " loc_city, loc_zip, loc_county, phone, primary_status,"
            " secondary_status, expiry_date, last_inspection, seats,"
            " district, extract_file) VALUES " + ",".join(vals) + ";")
    proc = subprocess.run(["mysql", "-uroot", "neutraleats"],
                          input="\n".join(out), capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr[:2000])
        return 1
    check = subprocess.run(
        ["mysql", "-uroot", "-N", "neutraleats", "-e",
         "SELECT COUNT(*) FROM fl_dbpr_licenses;"],
        capture_output=True, text=True)
    print("staged rows:", check.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
