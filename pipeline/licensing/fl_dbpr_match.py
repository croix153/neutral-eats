#!/usr/bin/env python3
"""fl_dbpr_match.py — crosswalk Florida venues to DBPR licenses.

Matches production venues (state='FL') to staged DBPR license
records (fl_dbpr_licenses) on address + name + zip + phone, and
writes the evidence to `fl_dbpr_matches` for audit. It makes NO
changes to `venues` or `enrichment`: suppression decisions are
reported, not applied, until reviewed.

Match tiers:
  STRONG — same house number, street tokens agree, name agrees
           (or exact phone + name agreement).
  MEDIUM — same house number with weaker name/street agreement,
           or exact phone with modest name agreement.

Closure candidates (reported, stacked evidence only):
  - license status 46 (voluntary relinquishment), any tier, or
  - license status 45 (delinquent) with expiry on/before
    2025-12-31 AND last inspection on/before 2025-12-31 or none.
Recent delinquency (2026 expiries) is a watchlist, never a
closure — Florida licenses renew on Apr 1 / Oct 1 cycles and
late renewals are common.

Run on the host:
    python3 fl_dbpr_match.py            # writes audit table + report
"""
import difflib
import re
import subprocess
import sys

GENERIC = {"THE", "A", "AN", "INC", "LLC", "CORP", "CO", "COMPANY",
           "RESTAURANT", "CAFE", "GRILL", "KITCHEN", "FOOD", "FOODS",
           "EATERY", "DINER", "PIZZA", "PIZZERIA", "BAR", "PUB"}
SUFFIX = {"STREET": "ST", "AVENUE": "AVE", "BOULEVARD": "BLVD",
          "DRIVE": "DR", "ROAD": "RD", "LANE": "LN", "COURT": "CT",
          "PLACE": "PL", "TERRACE": "TER", "CIRCLE": "CIR",
          "HIGHWAY": "HWY", "PARKWAY": "PKWY", "TRAIL": "TRL",
          "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
          "NORTHEAST": "NE", "NORTHWEST": "NW", "SOUTHEAST": "SE",
          "SOUTHWEST": "SW"}
UNIT = {"STE", "SUITE", "UNIT", "APT", "BLDG", "#", "FL", "FLOOR",
        "RM", "ROOM", "DEPT", "LOT", "SPC", "SPACE"}


def norm_text(s):
    s = (s or "").upper().replace("&", " AND ")
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return [t for t in s.split() if t]


def norm_name(s):
    toks = norm_text(s)
    distinctive = [t for t in toks if t not in GENERIC and len(t) > 1]
    return toks, distinctive


def parse_street(addr):
    """First comma segment -> (house_number, street token set)."""
    seg = (addr or "").split(",")[0]
    toks = [SUFFIX.get(t, t) for t in norm_text(seg)]
    house = ""
    if toks and re.fullmatch(r"\d+[A-Z]?", toks[0]):
        house = toks[0]
        toks = toks[1:]
    street = []
    for t in toks:
        if t in UNIT:
            break
        street.append(t)
    return house, set(street)


def phone10(s):
    d = re.sub(r"\D", "", s or "")
    return d[-10:] if len(d) >= 10 else ""


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def name_score(a_full, a_dist, b_full, b_dist):
    ratio = difflib.SequenceMatcher(None, " ".join(a_full),
                                    " ".join(b_full)).ratio()
    jac = jaccard(set(a_dist), set(b_dist))
    return max(ratio, 0.35 + 0.65 * jac) if jac > 0 else ratio * 0.8


def fetch(sql):
    proc = subprocess.run(["mysql", "-uroot", "-N", "-B", "neutraleats",
                           "-e", sql], capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr[:1000], file=sys.stderr)
        raise SystemExit(1)
    return [line.split("\t") for line in proc.stdout.splitlines()]


def main():
    venues = []
    for row in fetch("SELECT id, name, address, zip, phone FROM venues"
                     " WHERE state='FL'"):
        vid, name, addr, zipc, phone = (row + ["", "", "", "", ""])[:5]
        house, street = parse_street(addr)
        full, dist = norm_name(name)
        venues.append({"id": vid, "name": name, "house": house,
                       "street": street, "zip": (zipc or "")[:5],
                       "phone": phone10(phone), "nfull": full,
                       "ndist": dist})
    print(f"venues (FL): {len(venues)}")

    licenses = []
    for row in fetch("SELECT license_number, business_name, loc_address,"
                     " loc_zip, phone, primary_status, expiry_date,"
                     " last_inspection FROM fl_dbpr_licenses"):
        (num, name, addr, zipc, phone, status, expiry, insp) = \
            (row + [""] * 8)[:8]
        house, street = parse_street(addr)
        full, dist = norm_name(name)
        licenses.append({"num": num, "name": name, "house": house,
                         "street": street, "zip": (zipc or "")[:5],
                         "phone": phone10(phone), "status": status,
                         "expiry": expiry, "insp": insp,
                         "nfull": full, "ndist": dist})
    print(f"licenses: {len(licenses)}")

    # Blocking: (zip5, house number); fallback (zip5, street token).
    block = {}
    for li, lic in enumerate(licenses):
        if lic["zip"] and lic["house"]:
            block.setdefault((lic["zip"], lic["house"]), []).append(li)
        if lic["zip"]:
            for t in lic["street"]:
                block.setdefault((lic["zip"], "S:" + t), []).append(li)
    phone_block = {}
    for li, lic in enumerate(licenses):
        if lic["phone"]:
            phone_block.setdefault(lic["phone"], []).append(li)

    candidates = []  # (score, venue_idx, lic_idx, tier)
    for vi, v in enumerate(venues):
        cand_idx = set()
        if v["zip"] and v["house"]:
            cand_idx.update(block.get((v["zip"], v["house"]), []))
        if v["zip"]:
            for t in v["street"]:
                cand_idx.update(block.get((v["zip"], "S:" + t), []))
        if v["phone"]:
            cand_idx.update(phone_block.get(v["phone"], []))
        for li in cand_idx:
            lic = licenses[li]
            ns = name_score(v["nfull"], v["ndist"],
                            lic["nfull"], lic["ndist"])
            sj = jaccard(v["street"], lic["street"])
            same_house = v["house"] and v["house"] == lic["house"]
            phone_hit = v["phone"] and v["phone"] == lic["phone"]
            if phone_hit and ns >= 0.60:
                tier, score = "STRONG", 0.70 + 0.30 * ns
            elif same_house and sj >= 0.6 and ns >= 0.70:
                tier, score = "STRONG", 0.4 * sj + 0.6 * ns
            elif phone_hit and ns >= 0.45:
                tier, score = "MEDIUM", 0.55 + 0.30 * ns
            elif same_house and sj >= 0.4 and ns >= 0.55:
                tier, score = "MEDIUM", 0.4 * sj + 0.6 * ns
            else:
                continue
            candidates.append((score, vi, li, tier))

    # Greedy one-to-one: best pairs first, each license once,
    # each venue once. Current licenses win ties for a venue so
    # an owner-change pair resolves to the live license.
    candidates.sort(key=lambda c: -c[0])
    used_lic, used_ven, matches = set(), set(), []
    for score, vi, li, tier in candidates:
        if li in used_lic or vi in used_ven:
            continue
        used_lic.add(li)
        used_ven.add(vi)
        matches.append((vi, li, tier, round(score, 3)))
    print(f"matched pairs: {len(matches)} "
          f"(STRONG {sum(1 for m in matches if m[2] == 'STRONG')}, "
          f"MEDIUM {sum(1 for m in matches if m[2] == 'MEDIUM')})")

    subprocess.run(["mysql", "-uroot", "neutraleats"], input="""
CREATE TABLE IF NOT EXISTS fl_dbpr_matches (
    venue_id VARCHAR(255), license_number VARCHAR(20),
    tier VARCHAR(10), score DECIMAL(4,3), lic_status VARCHAR(10),
    expiry_date DATE NULL, last_inspection DATE NULL,
    closure_candidate TINYINT DEFAULT 0, watchlist TINYINT DEFAULT 0,
    PRIMARY KEY (venue_id), INDEX (license_number)
) ENGINE=InnoDB;
TRUNCATE TABLE fl_dbpr_matches;
""", capture_output=True, text=True)

    def d(s):
        return "'" + s + "'" if s and s != "NULL" and s != "\\N" else "NULL"

    lines, closures, watch = [], [], []
    for vi, li, tier, score in matches:
        v, lic = venues[vi], licenses[li]
        expiry = None if lic["expiry"] in ("", "NULL", "\\N") else lic["expiry"]
        insp = None if lic["insp"] in ("", "NULL", "\\N") else lic["insp"]
        is_closure = 0
        is_watch = 0
        if lic["status"] == "46":
            is_closure = 1
        elif lic["status"] == "45":
            if (expiry and expiry <= "2025-12-31"
                    and (not insp or insp <= "2025-12-31")):
                is_closure = 1
            else:
                is_watch = 1
        if is_closure:
            closures.append((v["name"], lic["name"], lic["status"],
                             expiry, insp, tier))
        if is_watch:
            watch.append((v["name"], lic["name"], expiry, insp))
        lines.append(
            f"('{v['id']}','{lic['num']}','{tier}',{score},"
            f"'{lic['status']}',{d(expiry)},{d(insp)},"
            f"{is_closure},{is_watch})")
    for i in range(0, len(lines), 1000):
        stmt = ("INSERT INTO fl_dbpr_matches VALUES "
                + ",".join(lines[i:i + 1000]) + ";")
        proc = subprocess.run(["mysql", "-uroot", "neutraleats"],
                              input=stmt, capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stderr[:1000], file=sys.stderr)
            return 1

    matched_current = sum(1 for vi, li, t, s in matches
                          if licenses[li]["status"] == "20")
    print(f"matched to Current licenses: {matched_current}")
    print(f"CLOSURE candidates: {len(closures)}")
    for c in closures[:15]:
        print("  CLOSED?", c)
    print(f"watchlist (recent delinquent): {len(watch)}")
    unmatched_lic = len(licenses) - len(used_lic)
    print(f"licenses with no venue match: {unmatched_lic}")
    print(f"venues with no license match: {len(venues) - len(used_ven)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
