#!/usr/bin/env python3
"""kc_bos_match.py — crosswalk King County + Boston venues to
their staged licensing records (kc_licenses / bos_licenses).

Same engine, tiers, and guards as the FL/NY crosswalks:
  STRONG — same house number, street tokens agree, name agrees
           (or exact phone + name agreement where phones exist).
  MEDIUM — same house number with weaker name/street agreement,
           or exact phone with modest name agreement.
  Live licenses get +0.06 in the greedy assignment (live wins
  near-ties), and a closure candidate is demoted to the
  watchlist when ANY live license operates at the same
  (zip, house number) — the live-successor gate.

Closure candidates (stacked evidence only):
  - KC: the latest inspection's closed_business flag is Yes
    AND that inspection is on/before 2026-04-30 (~6 months
    stale — a flagged business normally reopens or is replaced
    within weeks). Fresher flags are watchlist.
  - Boston: NOT in the active companion file AND (license
    expiry on/before 2024-12-31 OR last inspection on/before
    2024-12-31 or none on record). Not-in-active but fresher
    is watchlist.

Writes audit tables (kc_matches / bos_matches) and prints a
report. NO changes to `venues` — suppression decisions are
reported, not applied, until reviewed.

Run on the host:
    python3 kc_bos_match.py
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


def clean_date(s):
    return None if s in ("", "NULL", "\\N") else s


def run_region(cfg):
    print(f"=== {cfg['label']} ===")
    venues = []
    for row in fetch(cfg["venue_sql"]):
        vid, name, addr, zipc, phone = (row + ["", "", "", "", ""])[:5]
        house, street = parse_street(addr)
        full, dist = norm_name(name)
        venues.append({"id": vid, "name": name, "house": house,
                       "street": street, "zip": (zipc or "")[:5],
                       "phone": phone10(phone), "nfull": full,
                       "ndist": dist})
    print(f"venues: {len(venues)}")

    licenses = []
    for row in fetch(cfg["license_sql"]):
        (key, name, addr, zipc, phone, status, expiry, insp,
         live) = (row + [""] * 9)[:9]
        house, street = parse_street(addr)
        full, dist = norm_name(name)
        licenses.append({"key": key, "name": name, "house": house,
                         "street": street, "zip": (zipc or "")[:5],
                         "phone": phone10(phone), "status": status,
                         "expiry": clean_date(expiry),
                         "insp": clean_date(insp),
                         "live": live == "1",
                         "nfull": full, "ndist": dist})
    print(f"licenses: {len(licenses)}")

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

    candidates = []
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
            if lic["live"]:
                score = min(score + 0.06, 0.999)
            candidates.append((score, 0 if lic["live"] else 1,
                               vi, li, tier))

    candidates.sort(key=lambda c: (-c[0], c[1]))
    used_lic, used_ven, matches = set(), set(), []
    for score, _rank, vi, li, tier in candidates:
        if li in used_lic or vi in used_ven:
            continue
        used_lic.add(li)
        used_ven.add(vi)
        matches.append((vi, li, tier, round(score, 3)))
    print(f"matched pairs: {len(matches)} "
          f"(STRONG {sum(1 for m in matches if m[2] == 'STRONG')}, "
          f"MEDIUM {sum(1 for m in matches if m[2] == 'MEDIUM')})")

    subprocess.run(["mysql", "-uroot", "neutraleats"], input=f"""
CREATE TABLE IF NOT EXISTS {cfg['table']} (
    venue_id VARCHAR(255), license_key VARCHAR(40),
    source VARCHAR(5), tier VARCHAR(10), score DECIMAL(4,3),
    lic_status VARCHAR(20), expiry_date DATE NULL,
    last_inspection DATE NULL,
    closure_candidate TINYINT DEFAULT 0, watchlist TINYINT DEFAULT 0,
    PRIMARY KEY (venue_id), INDEX (license_key)
) ENGINE=InnoDB;
TRUNCATE TABLE {cfg['table']};
""", capture_output=True, text=True)

    def d(s):
        return "'" + s + "'" if s else "NULL"

    live_addr = {(lic["zip"], lic["house"]) for lic in licenses
                 if lic["live"] and lic["zip"] and lic["house"]}

    lines, closures, watch = [], [], []
    gated = 0
    for vi, li, tier, score in matches:
        v, lic = venues[vi], licenses[li]
        is_closure, is_watch = cfg["classify"](lic)
        if is_closure and (lic["zip"], lic["house"]) in live_addr:
            is_closure, is_watch = 0, 1
            gated += 1
        if is_closure:
            closures.append((v["name"], lic["name"], lic["status"],
                             lic["expiry"], lic["insp"], tier))
        if is_watch:
            watch.append((v["name"], lic["name"], lic["status"],
                          lic["insp"]))
        lines.append(
            f"('{v['id']}','{lic['key']}','{cfg['source']}','{tier}',"
            f"{score},'{lic['status']}',{d(lic['expiry'])},"
            f"{d(lic['insp'])},{is_closure},{is_watch})")
    for i in range(0, len(lines), 1000):
        stmt = (f"INSERT INTO {cfg['table']} VALUES "
                + ",".join(lines[i:i + 1000]) + ";")
        proc = subprocess.run(["mysql", "-uroot", "neutraleats"],
                              input=stmt, capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stderr[:1000], file=sys.stderr)
            return 1

    live = sum(1 for vi, li, t, s in matches if licenses[li]["live"])
    print(f"matched to live licenses: {live}")
    print(f"CLOSURE candidates: {len(closures)}")
    for c in closures[:15]:
        print("  CLOSED?", c)
    print(f"watchlist: {len(watch)} (incl. {gated} demoted by the "
          f"live-successor gate)")
    print(f"licenses with no venue match: {len(licenses) - len(used_lic)}")
    print(f"venues with no license match: {len(venues) - len(used_ven)}")
    return 0


def classify_kc(lic):
    if lic["live"]:
        return 0, 0
    if lic["insp"] and lic["insp"] <= "2026-04-30":
        return 1, 0
    return 0, 1


def classify_bos(lic):
    if lic["live"]:
        return 0, 0
    if ((lic["expiry"] and lic["expiry"] <= "2024-12-31")
            or (lic["insp"] and lic["insp"] <= "2024-12-31")
            or not lic["insp"]):
        return 1, 0
    return 0, 1


def main():
    kc = {
        "label": "King County",
        "source": "KC",
        "table": "kc_matches",
        "venue_sql": ("SELECT id, name, address, zip, phone FROM venues"
                      " WHERE state='WA' AND LEFT(zip,5) IN"
                      " (SELECT DISTINCT zip COLLATE utf8mb4_unicode_ci FROM kc_licenses)"),
        "license_sql": ("SELECT CONCAT('KC:', business_id), name,"
                        " address, zip, '',"
                        " IF(closed_flag=1, 'closed', 'open'), NULL,"
                        " last_inspection, IF(closed_flag=1, 0, 1)"
                        " FROM kc_licenses"),
        "classify": classify_kc,
    }
    bos = {
        "label": "Boston",
        "source": "BOS",
        "table": "bos_matches",
        "venue_sql": ("SELECT id, name, address, zip, phone FROM venues"
                      " WHERE state='MA' AND LEFT(zip,5) IN"
                      " (SELECT DISTINCT zip COLLATE utf8mb4_unicode_ci FROM bos_licenses)"),
        "license_sql": ("SELECT CONCAT('BOS:', licenseno), name,"
                        " address, zip, '', licstatus, expiry,"
                        " last_inspection, in_active FROM bos_licenses"),
        "classify": classify_bos,
    }
    rc = run_region(kc)
    if rc:
        return rc
    return run_region(bos)


if __name__ == "__main__":
    raise SystemExit(main())
