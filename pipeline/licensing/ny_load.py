#!/usr/bin/env python3
"""ny_load.py — stage New York licensing/inspection sources.

Two disjoint sources (NY State excludes NYC by design):

  nys_licenses — Health Data NY (health.data.ny.gov)
    ACTIVE:   dataset cnih-y5dw "Last Inspection" (one row per
              establishment, 21,601 rows at fetch time)
    INACTIVE: dataset aaxz-j6pj (full inspection history since
              2005, ~1.5M violation rows) deduped to one row per
              nys_health_operation_id keeping the LATEST
              inspection. Presence here + absence from ACTIVE is
              the state's own inactive (closed/lapsed) signal.
    An operation_id present in both resolves to ACTIVE.

  nyc_licenses — NYC Open Data DOHMH inspections (43nn-pn8j,
    ~295k violation rows) deduped to one row per CAMIS keeping
    the LATEST inspection's action/date/grade. The dataset holds
    active establishments only; a closure shows as the latest
    ACTION ("Establishment Closed by DOHMH...") with no later
    reopening inspection.

Staging is evidence, not truth: nothing here touches `venues`.
The crosswalk (ny_match.py) reads these tables.

Run on the host (root MySQL via unix socket):
    python3 ny_load.py
"""
import json
import re
import subprocess
import sys
import time
import urllib.request

PAGE = 50000
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

DDL = """
DROP TABLE IF EXISTS nys_licenses;
CREATE TABLE nys_licenses (
    operation_id     VARCHAR(30) PRIMARY KEY,
    name             VARCHAR(255),
    address          VARCHAR(255),
    city             VARCHAR(100),
    zip              VARCHAR(10),
    county           VARCHAR(100),
    status           VARCHAR(10),
    permit_expiry    DATE NULL,
    last_inspection  DATE NULL,
    source_dataset   VARCHAR(20),
    loaded_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
DROP TABLE IF EXISTS nyc_licenses;
CREATE TABLE nyc_licenses (
    camis            VARCHAR(20) PRIMARY KEY,
    dba              VARCHAR(255),
    address          VARCHAR(255),
    boro             VARCHAR(50),
    zip              VARCHAR(10),
    phone            VARCHAR(30),
    last_action      VARCHAR(255),
    action_closed    TINYINT DEFAULT 0,
    last_inspection  DATE NULL,
    grade            VARCHAR(5),
    loaded_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
"""


def sql_escape(s):
    if s is None:
        return "NULL"
    return "'" + str(s).replace("\\", "\\\\").replace("'", "\\'") + "'"


def parse_date(s):
    s = (s or "")[:10]
    return s if DATE_RE.match(s) else None


def fetch_pages(base, select, order):
    """Page a Socrata resource endpoint; yields row dicts."""
    offset = 0
    while True:
        q = (f"?$select={select}&$order={order}"
             f"&$limit={PAGE}&$offset={offset}")
        req = urllib.request.Request(
            base + q,
            headers={"User-Agent": "neutral-eats-licensing/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            rows = json.load(resp)
        if not rows:
            return
        yield from rows
        if len(rows) < PAGE:
            return
        offset += PAGE
        time.sleep(0.3)


def load_nys():
    ops = {}
    # INACTIVE first (full history; latest inspection per operation).
    n_raw = 0
    for r in fetch_pages(
            "https://health.data.ny.gov/resource/aaxz-j6pj.json",
            "nys_health_operation_id,operation_name,permitted_d_b_a,"
            "facility_address,facility_city,facility_postal_zipcode,"
            "county,permit_expiration_date,date_of_inspection",
            "nys_health_operation_id ASC, date_of_inspection DESC"):
        n_raw += 1
        oid = r.get("nys_health_operation_id")
        if not oid or oid in ops:
            continue
        ops[oid] = {
            "name": (r.get("operation_name")
                     or r.get("permitted_d_b_a") or "")[:255],
            "address": (r.get("facility_address") or "")[:255],
            "city": (r.get("facility_city") or "")[:100],
            "zip": (r.get("facility_postal_zipcode") or "")[:10],
            "county": (r.get("county") or "")[:100],
            "status": "inactive",
            "permit_expiry": parse_date(r.get("permit_expiration_date")),
            "last_inspection": parse_date(r.get("date_of_inspection")),
            "source_dataset": "aaxz-j6pj",
        }
    print(f"nys inactive: {n_raw} history rows -> {len(ops)} operations")
    # ACTIVE (one row per establishment) overrides on conflict.
    n_act = 0
    for r in fetch_pages(
            "https://health.data.ny.gov/resource/cnih-y5dw.json",
            "nys_health_operation_id,facility,facility_address,city,"
            "zip_code,county,permit_expiration_date,date",
            "nys_health_operation_id ASC"):
        oid = r.get("nys_health_operation_id")
        if not oid:
            continue
        n_act += 1
        ops[oid] = {
            "name": (r.get("facility") or "")[:255],
            "address": (r.get("facility_address") or "")[:255],
            "city": (r.get("city") or "")[:100],
            "zip": (r.get("zip_code") or "")[:10],
            "county": (r.get("county") or "")[:100],
            "status": "active",
            "permit_expiry": parse_date(r.get("permit_expiration_date")),
            "last_inspection": parse_date(r.get("date")),
            "source_dataset": "cnih-y5dw",
        }
    print(f"nys active: {n_act} establishments; total staged {len(ops)}")
    return ops


def load_nyc():
    places = {}
    n_raw = 0
    for r in fetch_pages(
            "https://data.cityofnewyork.us/resource/43nn-pn8j.json",
            "camis,dba,boro,building,street,zipcode,phone,action,"
            "inspection_date,grade",
            "camis ASC, inspection_date DESC"):
        n_raw += 1
        camis = r.get("camis")
        if not camis or camis in places:
            continue
        action = (r.get("action") or "")[:255]
        addr = ((r.get("building") or "") + " "
                + (r.get("street") or "")).strip()
        places[camis] = {
            "dba": (r.get("dba") or "")[:255],
            "address": addr[:255],
            "boro": (r.get("boro") or "")[:50],
            "zip": (r.get("zipcode") or "")[:10],
            "phone": (r.get("phone") or "")[:30],
            "last_action": action,
            "action_closed": 1 if "closed by dohmh" in action.lower()
            or "re-closed" in action.lower() else 0,
            "last_inspection": parse_date(r.get("inspection_date")),
            "grade": (r.get("grade") or "")[:5],
        }
    print(f"nyc: {n_raw} violation rows -> {len(places)} establishments")
    return places


def insert(table, cols, rows):
    out = []
    BATCH = 1000
    items = list(rows)
    for i in range(0, len(items), BATCH):
        vals = []
        for row in items[i:i + BATCH]:
            vals.append("(" + ",".join(
                sql_escape(row[c]) if not isinstance(row[c], int)
                else str(row[c]) for c in cols) + ")")
        out.append(f"INSERT INTO {table} ({','.join(cols)}) VALUES "
                   + ",".join(vals) + ";")
    return out


def main():
    ops = load_nys()
    places = load_nyc()
    stmts = [DDL]
    stmts += insert(
        "nys_licenses",
        ["operation_id", "name", "address", "city", "zip", "county",
         "status", "permit_expiry", "last_inspection", "source_dataset"],
        [(dict(op, operation_id=oid)) for oid, op in ops.items()])
    stmts += insert(
        "nyc_licenses",
        ["camis", "dba", "address", "boro", "zip", "phone",
         "last_action", "action_closed", "last_inspection", "grade"],
        [(dict(p, camis=c)) for c, p in places.items()])
    proc = subprocess.run(["mysql", "-uroot", "neutraleats"],
                          input="\n".join(stmts),
                          capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr[:2000], file=sys.stderr)
        return 1
    check = subprocess.run(
        ["mysql", "-uroot", "-N", "neutraleats", "-e",
         "SELECT 'nys', status, COUNT(*) FROM nys_licenses"
         " GROUP BY status;"
         "SELECT 'nyc', COUNT(*) FROM nyc_licenses;"
         "SELECT 'nyc_closed_latest', COUNT(*) FROM nyc_licenses"
         " WHERE action_closed=1;"],
        capture_output=True, text=True)
    print(check.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
