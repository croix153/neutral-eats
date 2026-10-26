#!/usr/bin/env python3
"""
enrich_yelp.py — neutral eats Yelp enrichment fetcher/matcher.

Populates the `enrichment` side table (see DDL at the bottom of this
docstring) with display data from the Yelp Fusion API: rating,
review_count, price_level, table_service (Yelp's RestaurantsTableService
attribute) and is_closed. The production API (api/venues.php) LEFT JOINs
this table: enrichment values win when present, the venues table's own
legacy fields are the fallback, and venues flagged is_closed are
suppressed from results. Enrichment is DISPLAY + CLOSURE data only —
it is never a ranking input; result order stays distance/source based
exactly as venues.php defines it.

The table is keyed by venues.id and lives outside `venues`, so the
monthly Overture refresh (which rebuilds `venues`) never touches it.

======================================================================
API KEY — THE SINGLE CONFIG POINT
======================================================================
The script reads the Yelp Fusion API key from exactly one place, in
this order:

  1. Environment variable  YELP_API_KEY
  2. The file named by environment variable YELP_KEY_FILE
  3. Default file:  /root/.neutral-eats/yelp_api_key   (one line, chmod 600)

When the key arrives from the Muse custom.yelp vault, the ONLY step
needed is to write it to that default file on the host:

    install -d -m 700 /root/.neutral-eats
    printf '%s' '<KEY>' > /root/.neutral-eats/yelp_api_key
    chmod 600 /root/.neutral-eats/yelp_api_key

Until then the script exits cleanly with a "no key configured" message
(exit code 0) and touches nothing. There is no other place the key is
read from, and no key is ever hardcoded here.
======================================================================

Usage:
    enrich_yelp.py --bbox SOUTH WEST NORTH EAST [--limit 200]
    enrich_yelp.py --venue-ids ID,ID,...        [--limit 200]
    enrich_yelp.py --bbox ... --list-candidates # show targets, no API use
    enrich_yelp.py --bbox ... --dry-run         # match but do not write

Options:
    --limit N        Max venues to process this run (default 200).
    --max-calls N    Hard cap on Yelp HTTP calls this run (default 400).
    --delay SECONDS  Pause between Yelp calls (default 0.35).
    --ttl-days N     Days before a row is stale (default 30); also sets
                     refresh_after = fetched_at + ttl for new rows.
    --min-score F    Minimum match score to accept a search match
                     (default 0.55).

Matching strategy per venue:
  (a) If the venue has a phone number, try Yelp phone search first
      (GET /v3/businesses/search/phone) — the most precise matcher.
      The hit is accepted when the names are at least loosely similar
      (recycled numbers happen); otherwise we fall through to (b).
  (b) Name + location search (GET /v3/businesses/search with the venue
      name as term, venue lat/lng, tight 400 m radius) — best-scoring
      candidate wins when it clears --min-score.
  A business-details call (GET /v3/businesses/{id}) then supplies
  rating / review_count / price / attributes / is_closed.
  Venues with no acceptable match get a marker row (yelp_id NULL) with
  refresh_after set, so they are not re-attempted until the TTL lapses.

Stdlib only. DB access mirrors monthly_refresh.py: the `mysql` CLI as
root over the local socket. Run on the host (croix.ai).
"""

import argparse
import difflib
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://api.yelp.com/v3"
KEY_FILE_DEFAULT = "/root/.neutral-eats/yelp_api_key"
USER_AGENT = "neutral-eats-enrich/1.0"

DDL = """
CREATE TABLE IF NOT EXISTS enrichment (
  venue_id      VARCHAR(255) NOT NULL,
  yelp_id       VARCHAR(255) DEFAULT NULL,
  rating        DECIMAL(3,2) DEFAULT NULL,
  review_count  INT UNSIGNED DEFAULT NULL,
  price_level   TINYINT DEFAULT NULL,
  table_service TINYINT(1) DEFAULT NULL,
  is_closed     TINYINT(1) DEFAULT NULL,
  matched_via   ENUM('phone','search') DEFAULT NULL,
  fetched_at    INT UNSIGNED DEFAULT NULL,
  refresh_after INT UNSIGNED DEFAULT NULL,
  PRIMARY KEY (venue_id),
  KEY idx_enrich_yelp (yelp_id),
  KEY idx_enrich_refresh (refresh_after)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


# ---------------------------------------------------------------- key

def load_api_key():
    """Return the Yelp API key from the single config point, or None."""
    key = os.environ.get("YELP_API_KEY", "").strip()
    if key:
        return key
    path = os.environ.get("YELP_KEY_FILE", KEY_FILE_DEFAULT)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            key = fh.read().strip()
    except OSError:
        return None
    return key or None


# ---------------------------------------------------------------- db

def mysql_rows(sql):
    """Run a query via the mysql CLI (root, socket auth) and return the
    stdout split into lines. Caller selects one JSON_OBJECT per row."""
    proc = subprocess.run(
        ["mysql", "-u", "root", "-N", "-B", "neutraleats", "-e", sql],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"mysql failed: {proc.stderr[-500:]}")
    return [ln for ln in proc.stdout.splitlines() if ln.strip()]


def mysql_exec(sql):
    proc = subprocess.run(
        ["mysql", "-u", "root", "neutraleats", "-e", sql],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"mysql failed: {proc.stderr[-500:]}")


def sql_str(value):
    if value is None:
        return "NULL"
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def sql_num(value):
    if value is None:
        return "NULL"
    return repr(float(value)) if isinstance(value, float) else str(int(value))


def select_candidates(args):
    """Venues that are unenriched or stale (refresh_after in the past)."""
    stale = "(e.venue_id IS NULL OR e.refresh_after IS NULL " \
            "OR e.refresh_after < UNIX_TIMESTAMP())"
    if args.venue_ids:
        ids = [i.strip() for i in args.venue_ids.split(",") if i.strip()]
        in_list = ",".join(sql_str(i) for i in ids)
        where = f"v.id IN ({in_list})"
    else:
        s, w, n, e = args.bbox
        where = (f"v.lat >= {s} AND v.lat <= {n} "
                 f"AND v.lng >= {w} AND v.lng <= {e}")
    sql = (
        "SELECT JSON_OBJECT('id', v.id, 'name', v.name, 'lat', v.lat, "
        "'lng', v.lng, 'phone', v.phone, 'address', v.address) "
        "FROM venues v LEFT JOIN enrichment e ON e.venue_id = v.id "
        f"WHERE v.is_active = 1 AND {where} AND {stale} "
        f"ORDER BY v.id LIMIT {int(args.limit)}")
    return [json.loads(ln) for ln in mysql_rows(sql)]


# ------------------------------------------------------------ yelp api

class CallBudget:
    def __init__(self, max_calls, delay):
        self.max_calls = max_calls
        self.delay = delay
        self.used = 0

    def exhausted(self):
        return self.used >= self.max_calls


class Yelp:
    def __init__(self, api_key, budget):
        self.api_key = api_key
        self.budget = budget

    def get(self, path, params=None):
        """One Yelp GET. Returns parsed JSON, or None on any failure.
        Counts against the run budget; sleeps politely before each call;
        backs off once on HTTP 429, then gives up (returns None)."""
        if self.budget.exhausted():
            return None
        url = API_BASE + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={
            "Authorization": "Bearer " + self.api_key,
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        })
        for attempt in (1, 2):
            if self.budget.delay:
                time.sleep(self.budget.delay)
            self.budget.used += 1
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as err:
                if err.code == 429 and attempt == 1:
                    print("  ! Yelp rate-limited (429); backing off 5s",
                          file=sys.stderr)
                    time.sleep(5)
                    continue
                print(f"  ! Yelp HTTP {err.code} for {path}", file=sys.stderr)
                return None
            except Exception as err:  # network, JSON, timeout
                print(f"  ! Yelp call failed for {path}: {err}",
                      file=sys.stderr)
                return None
        return None

    def search_phone(self, phone_e164):
        data = self.get("/businesses/search/phone", {"phone": phone_e164})
        if data and data.get("businesses"):
            return data["businesses"][0]
        return None

    def search_near(self, name, lat, lng):
        data = self.get("/businesses/search", {
            "term": name, "latitude": lat, "longitude": lng,
            "radius": 400, "limit": 5,
        })
        if data:
            return data.get("businesses") or []
        return []

    def details(self, yelp_id):
        return self.get("/businesses/" + urllib.parse.quote(yelp_id, safe=""))


# ------------------------------------------------------------- matching

def normalize_name(name):
    s = (name or "").lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\b(llc|inc|corp|ltd|co)\b", "", s)
    return re.sub(r"\s+", " ", s).strip()


def name_ratio(a, b):
    return difflib.SequenceMatcher(
        None, normalize_name(a), normalize_name(b)).ratio()


def haversine_m(lat1, lng1, lat2, lng2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def candidate_score(venue, biz):
    """0..1: mostly name similarity, distance as a tiebreak/penalty."""
    ratio = name_ratio(venue["name"], biz.get("name", ""))
    coords = biz.get("coordinates") or {}
    dist = None
    if coords.get("latitude") is not None:
        dist = haversine_m(float(venue["lat"]), float(venue["lng"]),
                           float(coords["latitude"]),
                           float(coords["longitude"]))
    dist_score = 1.0 if dist is None else max(0.0, 1.0 - dist / 800.0)
    return 0.7 * ratio + 0.3 * dist_score, ratio


def normalize_phone(raw):
    """Best-effort E.164 for US numbers; None when unusable."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    if str(raw).strip().startswith("+") and len(digits) >= 8:
        return "+" + digits
    return None


def match_venue(yelp, venue):
    """Return (business_dict, matched_via) or (None, None)."""
    phone = normalize_phone(venue.get("phone"))
    if phone:
        biz = yelp.search_phone(phone)
        if biz and name_ratio(venue["name"], biz.get("name", "")) >= 0.40:
            return biz, "phone"
    best, best_score = None, 0.0
    for biz in yelp.search_near(venue["name"], venue["lat"], venue["lng"]):
        score, ratio = candidate_score(venue, biz)
        if ratio >= 0.55 and score > best_score:
            best, best_score = biz, score
    if best is not None:
        return best, "search"
    return None, None


# -------------------------------------------------------------- parsing

def parse_price(value):
    """Yelp price is a string like '$$' (details/search) — count the $."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value) or None
    count = str(value).count("$")
    return count if count > 0 else None


def parse_table_service(attrs):
    """Yelp business attributes: find RestaurantsTableService. Shapes
    seen in the wild: flat dict {name: bool}, nested per-group dicts,
    or {name: {'value': bool}}. Returns True/False/None."""
    if not isinstance(attrs, dict):
        return None

    def coerce(v):
        if isinstance(v, bool):
            return v
        if isinstance(v, dict) and "value" in v:
            return coerce(v["value"])
        if isinstance(v, str):
            return {"true": True, "false": False}.get(v.lower())
        return None

    if "RestaurantsTableService" in attrs:
        return coerce(attrs["RestaurantsTableService"])
    for group in attrs.values():
        if isinstance(group, dict) and "RestaurantsTableService" in group:
            return coerce(group["RestaurantsTableService"])
    return None


def row_from_details(venue, biz, via, details, ttl_days):
    merged = dict(biz or {})
    if details:
        merged.update(details)
    now = int(time.time())
    return {
        "venue_id": venue["id"],
        "yelp_id": merged.get("id"),
        "rating": merged.get("rating"),
        "review_count": merged.get("review_count"),
        "price_level": parse_price(merged.get("price")),
        "table_service": parse_table_service(merged.get("attributes")),
        "is_closed": merged.get("is_closed"),
        "matched_via": via,
        "fetched_at": now,
        "refresh_after": now + ttl_days * 86400,
    }


def marker_row(venue, ttl_days):
    now = int(time.time())
    return {
        "venue_id": venue["id"], "yelp_id": None, "rating": None,
        "review_count": None, "price_level": None, "table_service": None,
        "is_closed": None, "matched_via": None,
        "fetched_at": now, "refresh_after": now + ttl_days * 86400,
    }


def bool_or_none(v):
    return None if v is None else (1 if v else 0)


def write_row(row):
    sql = (
        "REPLACE INTO enrichment (venue_id, yelp_id, rating, review_count,"
        " price_level, table_service, is_closed, matched_via, fetched_at,"
        " refresh_after) VALUES ("
        + ", ".join([
            sql_str(row["venue_id"]),
            sql_str(row["yelp_id"]),
            sql_num(row["rating"]),
            sql_num(row["review_count"]),
            sql_num(row["price_level"]),
            sql_num(bool_or_none(row["table_service"])),
            sql_num(bool_or_none(row["is_closed"])),
            sql_str(row["matched_via"]),
            sql_num(row["fetched_at"]),
            sql_num(row["refresh_after"]),
        ]) + ")")
    mysql_exec(sql)


# ----------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description="neutral eats Yelp enrichment")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--bbox", nargs=4, type=float,
                       metavar=("SOUTH", "WEST", "NORTH", "EAST"))
    group.add_argument("--venue-ids", help="comma-separated venue ids")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--max-calls", type=int, default=400)
    ap.add_argument("--delay", type=float, default=0.35)
    ap.add_argument("--ttl-days", type=int, default=30)
    ap.add_argument("--min-score", type=float, default=0.55)
    ap.add_argument("--list-candidates", action="store_true",
                    help="print target venues and exit (no key needed)")
    ap.add_argument("--dry-run", action="store_true",
                    help="match against Yelp but do not write rows")
    args = ap.parse_args(argv)

    mysql_exec(DDL)  # additive; safe to run every time
    candidates = select_candidates(args)
    print(f"candidates: {len(candidates)} unenriched/stale venue(s)")

    if args.list_candidates:
        for v in candidates:
            print(f"  {v['id']}  {v['name']}  "
                  f"phone={'yes' if v.get('phone') else 'no'}")
        return 0

    api_key = load_api_key()
    if not api_key:
        print("no key configured: set YELP_API_KEY or place the Yelp "
              f"Fusion API key in {KEY_FILE_DEFAULT} (see the header of "
              "this script). Nothing was fetched or written.")
        return 0

    budget = CallBudget(args.max_calls, args.delay)
    yelp = Yelp(api_key, budget)
    matched = written = 0
    for venue in candidates:
        if budget.exhausted():
            print(f"call budget exhausted ({budget.used} calls); stopping")
            break
        biz, via = match_venue(yelp, venue)
        if biz is None:
            row = marker_row(venue, args.ttl_days)
            print(f"  no match: {venue['name']}")
        else:
            details = yelp.details(biz["id"])
            row = row_from_details(venue, biz, via, details, args.ttl_days)
            matched += 1
            print(f"  matched via {via}: {venue['name']} -> "
                  f"{biz.get('name')} (rating {row['rating']}, "
                  f"reviews {row['review_count']}, "
                  f"closed {row['is_closed']})")
        if args.dry_run:
            print(f"    dry-run: would write {row}")
        else:
            write_row(row)
            written += 1
    print(f"done: {matched} matched, {written} row(s) written, "
          f"{budget.used} Yelp call(s) used")
    return 0


if __name__ == "__main__":
    sys.exit(main())
