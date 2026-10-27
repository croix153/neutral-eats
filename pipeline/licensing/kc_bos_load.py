#!/usr/bin/env python3
"""kc_bos_load.py — stage King County (WA) + Boston licensing.

King County — data.kingcounty.gov Socrata dataset r878-4sxa
(food inspections, one row per violation). Deduped to one row
per business_id keeping the LATEST inspection. This is the
only API source in the inventory with an explicit
`inspection_closed_business` flag — a "Yes" on the latest
inspection is the county's own closure signal.

Boston — data.boston.gov CKAN:
  * Food Establishment Inspections (4582bec6-...), one row
    per violation, filtered to licensecat='FS'; deduped to one
    row per licenseno keeping the latest inspection (status,
    expiry, result from that row).
  * Active Food Establishment Licenses (f1e13724-...) — the
    companion file: presence = currently licensed. It carries
    no licenseno, so the join is on property_id, which the
    inspections file also carries.

Staging is evidence, not truth: nothing here touches `venues`.
The crosswalk (kc_bos_match.py) reads these tables.

Run on the host (root MySQL via unix socket):
    python3 kc_bos_load.py
"""
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

DDL = """
DROP TABLE IF EXISTS kc_licenses;
CREATE TABLE kc_licenses (
    business_id      VARCHAR(30) PRIMARY KEY,
    name             VARCHAR(255),
    address          VARCHAR(255),
    city             VARCHAR(100),
    zip              VARCHAR(10),
    last_inspection  DATE NULL,
    closed_flag      TINYINT DEFAULT 0,
    grade            VARCHAR(20),
    loaded_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
DROP TABLE IF EXISTS bos_licenses;
CREATE TABLE bos_licenses (
    licenseno        VARCHAR(20) PRIMARY KEY,
    name             VARCHAR(255),
    address          VARCHAR(255),
    city             VARCHAR(100),
    zip              VARCHAR(10),
    licstatus        VARCHAR(20),
    expiry           DATE NULL,
    last_result      VARCHAR(30),
    last_inspection  DATE NULL,
    in_active        TINYINT DEFAULT 0,
    property_id      VARCHAR(20),
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


def run_sql(sql):
    proc = subprocess.run(["mysql", "-uroot", "neutraleats"],
                          input=sql, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr[:1000], file=sys.stderr)
        raise SystemExit(1)


def get_json(url, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "neutral-eats-licensing/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read())
        except Exception as e:
            if attempt == retries - 1:
                raise
            print(f"  retry {attempt + 1}: {e}", file=sys.stderr)
            time.sleep(5)


def load_kc():
    base = "https://data.kingcounty.gov/resource/r878-4sxa.json"
    fields = ("name,address,city,zip_code,inspection_date,"
              "inspection_closed_business,business_id,"
              "inspection_serial_num,grade")
    best = {}  # business_id -> row with latest inspection_date
    offset = 0
    page_size = 50000
    while True:
        q = urllib.parse.urlencode({
            "$select": fields, "$limit": page_size, "$offset": offset,
            "$order": "inspection_date"})
        rows = get_json(base + "?" + q)
        for r in rows:
            bid = (r.get("business_id") or "").strip()
            if not bid:
                continue
            d = parse_date(r.get("inspection_date"))
            cur = best.get(bid)
            if cur is None or (d or "") >= (cur["_d"] or ""):
                r["_d"] = d
                best[bid] = r
        print(f"  kc offset {offset}: {len(rows)} rows, "
              f"{len(best)} businesses")
        if len(rows) < page_size:
            break
        offset += page_size
    lines = []
    for bid, r in best.items():
        lines.append("(" + ",".join([
            sql_escape(bid),
            sql_escape((r.get("name") or "").strip()),
            sql_escape((r.get("address") or "").strip()),
            sql_escape((r.get("city") or "").strip()),
            sql_escape((r.get("zip_code") or "")[:5]),
            sql_escape(r["_d"]) if r["_d"] else "NULL",
            "1" if (r.get("inspection_closed_business") == "Yes")
            else "0",
            sql_escape((r.get("grade") or "").strip()),
        ]) + ")")
    for i in range(0, len(lines), 1000):
        run_sql("INSERT INTO kc_licenses (business_id, name, address,"
                " city, zip, last_inspection, closed_flag, grade)"
                " VALUES " + ",".join(lines[i:i + 1000]) + ";")
    closed = sum(1 for r in best.values()
                 if r.get("inspection_closed_business") == "Yes")
    print(f"kc_licenses: {len(best)} businesses, {closed} with "
          f"closed_flag on latest inspection")
    return len(best)


def ckan(resource_id, limit, offset, filters=None):
    params = {"resource_id": resource_id, "limit": limit,
              "offset": offset}
    if filters:
        params["filters"] = json.dumps(filters)
    url = ("https://data.boston.gov/api/3/action/datastore_search?"
           + urllib.parse.urlencode(params))
    return get_json(url)["result"]


def load_bos():
    insp_id = "4582bec6-2b4f-4f9e-bc55-cbaa73117f4c"
    act_id = "f1e13724-284d-478c-b8bc-ef042aa5b70b"
    # Active companion file first: property_id set = licensed now.
    active_props = set()
    offset = 0
    while True:
        res = ckan(act_id, 20000, offset)
        for r in res["records"]:
            pid = str(r.get("property_id") or "").strip()
            if pid:
                active_props.add(pid)
        if offset + len(res["records"]) >= res["total"]:
            break
        offset += len(res["records"])
    print(f"  bos active file: {len(active_props)} properties")

    best = {}  # licenseno -> latest-inspection row
    offset = 0
    while True:
        res = ckan(insp_id, 20000, offset, filters={"licensecat": "FS"})
        for r in res["records"]:
            lic = str(r.get("licenseno") or "").strip()
            if not lic:
                continue
            d = parse_date(r.get("resultdttm"))
            cur = best.get(lic)
            if cur is None or (d or "") >= (cur["_d"] or ""):
                r["_d"] = d
                best[lic] = r
        print(f"  bos offset {offset}: {len(res['records'])} rows, "
              f"{len(best)} licenses (of {res['total']} FS rows)")
        if offset + len(res["records"]) >= res["total"]:
            break
        offset += len(res["records"])
    lines = []
    for lic, r in best.items():
        pid = str(r.get("property_id") or "").strip()
        name = (r.get("dbaname") or r.get("businessname") or "").strip()
        lines.append("(" + ",".join([
            sql_escape(lic),
            sql_escape(name),
            sql_escape((r.get("address") or "").strip()),
            sql_escape((r.get("city") or "").strip()),
            sql_escape((r.get("zip") or "")[:5]),
            sql_escape((r.get("licstatus") or "").strip()),
            sql_escape(parse_date(r.get("expdttm")))
            if parse_date(r.get("expdttm")) else "NULL",
            sql_escape((r.get("result") or "").strip()),
            sql_escape(r["_d"]) if r["_d"] else "NULL",
            "1" if pid in active_props else "0",
            sql_escape(pid),
        ]) + ")")
    for i in range(0, len(lines), 1000):
        run_sql("INSERT INTO bos_licenses (licenseno, name, address,"
                " city, zip, licstatus, expiry, last_result,"
                " last_inspection, in_active, property_id) VALUES "
                + ",".join(lines[i:i + 1000]) + ";")
    inact = sum(1 for lic, r in best.items()
                if str(r.get("property_id") or "").strip()
                not in active_props)
    print(f"bos_licenses: {len(best)} licenses, {inact} not in the "
          f"active companion file")
    return len(best)


def main():
    run_sql(DDL)
    print("loading King County...")
    load_kc()
    print("loading Boston...")
    load_bos()
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
