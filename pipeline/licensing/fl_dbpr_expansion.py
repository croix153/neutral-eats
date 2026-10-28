#!/usr/bin/env python3
"""fl_dbpr_expansion.py — FL DBPR expansion pass, FLAGGED TRANCHE.

Executes DBPR-EXPANSION-DESIGN.md (Croix approved option (b),
2026-10-27). Stages:

  funnel   — rebuild the designed set from orphan_survivors.csv,
             asserting every step count in design section 1
             (v1 denylist + tightenings v2-v5). Writes
             designed_set_final.csv. Rule code for v1-v4 is copied
             verbatim from the design pass scripts (analyze.py /
             tighten.py / tighten3.py / tighten4.py); v5 (T15/T16)
             is implemented per design section 1.6.
  rematch  — pilot matcher (transcribed from fl_dbpr_orphans.py)
             vs live venues, active AND inactive. Exclusions land
             in dbpr_rematch_exclusions_20261027. Then self-dedupe
             (design 3.4). Writes post_rematch.csv.
  geocode  — Census batch (pilot transcription), Match + ZIP5 gate,
             then the 50m / name-sim>=0.85 guard vs active venues.
             Writes stage table dbpr_expansion_stage_20261027 and
             geocode_rejects.csv (parked tranche).
  names    — section 5 name-selection pass over staged rows;
             code/shell names diverted to name_review_queue.csv.
             Writes insert_ready.csv.
  insert   — record pre-insert counts, create audit table
             dbpr_additions_20261027, insert, verify counts.
  verify   — live-API checks: gold venues + random spot checks.

Memory discipline: host has 4GB RAM; venue loads follow the pilot's
pattern (FL subset + national phone index) which ran safely before.
"""
import csv
import difflib
import io
import math
import os
import re
import subprocess
import sys
import time
import unicodedata
from collections import Counter, defaultdict

EXEC_DATE = "2026-10-27"
WORK = os.environ.get("NE_WORK", "/root/licensing/expansion")

# ================================================================ shared
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


def fold(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c))


def norm_text(s):
    s = fold(s).upper().replace("&", " AND ")
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return [t for t in s.split() if t]


def title_case(s):
    s = (s or "").strip().lower()
    s = re.sub(r"(^|[\s\-/])([a-z])",
               lambda m: m.group(1) + m.group(2).upper(), s)
    s = s.replace("'S", "'s").replace("’S", "’s")
    return s


def fetch(sql):
    proc = subprocess.run(["mysql", "-uroot", "-N", "-B", "neutraleats",
                           "-e", sql], capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr[:1500], file=sys.stderr)
        raise SystemExit(1)
    out = []
    for line in proc.stdout.splitlines():
        out.append([("" if c == r"\N" else c) for c in line.split("\t")])
    return out


def run_sql(sql):
    proc = subprocess.run(["mysql", "-uroot", "neutraleats"],
                          input=sql, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr[:1500], file=sys.stderr)
        raise SystemExit(1)


def esc(s):
    return "'" + (s or "").replace("\\", "\\\\").replace("'", "\\'") + "'"


def dcol(s):
    # The DBPR extract represents some missing dates as the literal
    # string 'NULL'; normalize those (and zero dates) to SQL NULL.
    return esc(s) if s and s not in ("0000-00-00", "NULL") else "NULL"


def grid_cell(lat, lng):
    # Canonical venues.grid_cell — identical to pipeline/merge_overture.py.
    # The API grid prefilter trusts this column; never insert a venue
    # without it (the 2026-10-27 expansion left 7,556 NULLs behind).
    return "%.3f,%.3f" % (math.floor(lat / 0.02) * 0.02,
                          math.floor(lng / 0.02) * 0.02)


def check(label, actual, expected):
    ok = actual == expected
    print(f"  [{'OK' if ok else 'MISMATCH'}] {label}: {actual} "
          f"(design: {expected})")
    if not ok:
        raise SystemExit(f"ASSERT FAILED: {label}")
    return actual


# ================================================================ funnel
# Rule code for steps 1-6 copied verbatim from the design-pass scripts
# (analyze.py, tighten.py, tighten3.py, tighten4.py) so the rebuild is
# a transcription, not a reinterpretation.

FUNNEL_UNIT = UNIT | {"STAND", "BAY"}


def norm_addr_key(addr, zipc, zip_agnostic_t16=False):
    """Cluster key per design 1.1 (analyze.py). With
    zip_agnostic_t16=True the ZIP5 leaves the key and the street is
    additionally cut at a second embedded address (an 'AND' token or
    a >=4-digit house number followed by more street tokens) —
    design 1.6/T16."""
    seg = (addr or "").split(",")[0]
    toks = [SUFFIX.get(t, t) for t in norm_text(seg)]
    house = ""
    if toks and re.fullmatch(r"\d+[A-Z]?", toks[0]):
        house = toks[0]
        toks = toks[1:]
    street = []
    for i, t in enumerate(toks):
        if t in FUNNEL_UNIT:
            break
        if zip_agnostic_t16:
            if t == "AND":
                break
            if (street and re.fullmatch(r"\d{4,}[A-Z]?", t)
                    and i < len(toks) - 1):
                break
        street.append(t)
    digits = re.sub(r"\D", "", zipc or "")
    zip5 = digits[:5] if len(digits) >= 5 else ""
    if zip_agnostic_t16:
        return (house, " ".join(street))
    return (zip5, house, " ".join(street))


def _txt(r):
    return " " + " ".join(norm_text((r["business_name"] or "") + " " +
                                    (r["licensee_name"] or ""))) + " "


def _name_only(r):
    return " " + " ".join(norm_text(r["business_name"] or "")) + " "


def _licee_only(r):
    return " " + " ".join(norm_text(r["licensee_name"] or "")) + " "


V1_HOTEL_BRANDS = ["MARRIOTT", "HILTON", "HYATT", "RITZ", "FOUR SEASONS",
                   "WESTIN", "SHERATON", "WYNDHAM", "OMNI", "LOEWS",
                   "FAIRMONT", "WALDORF", "INTERCONTINENTAL", "GAYLORD",
                   "DIPLOMAT", "FONTAINEBLEAU", "EDEN ROC", "SETAI",
                   "FAENA", "AUTOGRAPH", "HARD ROCK", "SEMINOLE",
                   "RENAISSANCE", "DOUBLETREE", "EMBASSY SUITES",
                   "CROWNE PLAZA", "HOLIDAY INN", "HAMPTON INN",
                   "RESIDENCE INN", "COURTYARD", "SPRINGHILL"]
V1_CONTRACTORS = ["ARAMARK", "SODEXO", "COMPASS", "CHARTWELLS",
                  "CENTERPLATE", "DELAWARE NORTH", "SPORTSERVICE",
                  "LEVY", "LEGENDS HOSPITALITY", "OVATIONS", "METZ",
                  "MORRISON", "UNIDINE", "BOSTON CULINARY",
                  "CONCESSION", "GUEST SERVICES", "PATINA"]


def _hotel_suboutlet(r):
    li = _licee_only(r)
    if not any(b in li for b in V1_HOTEL_BRANDS):
        return False
    nb = set(norm_text(r["business_name"] or ""))
    nl = set(norm_text(r["licensee_name"] or ""))
    inter = nb & nl
    return len(inter) < 2


V1_PATTERNS = [
    ("unit", lambda r: bool(re.search(
        r"STAND\s*#|KIOSK|CONCESSION|\bCART\b", _name_only(r)))),
    ("ballroom", lambda r: bool(re.search(
        r"BALLROOM|BANQUET|PANTRY", _txt(r)))),
    ("hotel_suboutlet", _hotel_suboutlet),
    ("contractor", lambda r: any(c in _licee_only(r)
                                  for c in V1_CONTRACTORS)),
    ("theme_park", lambda r: any(x in _licee_only(r) for x in
                                 ["DISNEY", "UNIVERSAL", "SEAWORLD",
                                  "SEA WORLD", "BUSCH", "LEGOLAND",
                                  "MERLIN", "HERSCHEND"])),
    ("casino", lambda r: bool(re.search(
        r"CASINO|POKER|RACETRACK|GREYHOUND|JAI ALAI", _name_only(r)))),
    ("private_club", lambda r: bool(re.search(
        r"COUNTRY CLUB|YACHT CLUB|BEACH CLUB|TENNIS CLUB|RACQUET CLUB|"
        r"GOLF CLUB|HUNT CLUB|MEMBERS ONLY|PRIVATE CLUB", _txt(r)))),
    ("education", lambda r: bool(re.search(
        r"\bSCHOOL\b|UNIVERSITY|COLLEGE|ACADEMY|CAMPUS|STUDENT UNION|"
        r"CHARTER", _txt(r)))),
    ("healthcare", lambda r: bool(re.search(
        r"HOSPITAL|MEDICAL|NURSING|ASSISTED LIVING|SENIOR|RETIREMENT|"
        r"REHABILITATION|\bREHAB\b|HOSPICE|DIALYSIS|HEALTHCARE|"
        r"HEALTH CARE", _txt(r)))),
    ("faith_charity", lambda r: bool(re.search(
        r"CHURCH|MINISTR| SYNAGOGUE|MOSQUE|FOOD BANK|FOOD PANTRY|"
        r"SOUP KITCHEN|SALVATION ARMY|RESCUE MISSION|\bSHELTER\b",
        _txt(r)))),
    ("cafeteria", lambda r: bool(re.search(
        r"CAFETERIA|(EMPLOYEE|STAFF)\s+(CAFE|DINING|CAFETERIA)",
        _txt(r)))),
    ("commissary", lambda r: bool(re.search(
        r"COMMISSARY|CENTRAL KITCHEN|PRODUCTION KITCHEN|MEAL PREP|"
        r"CATERING|CATERERS|GHOST KITCHEN|COMMERCIAL KITCHEN",
        _txt(r)))),
    ("vending", lambda r: bool(re.search(
        r"VENDING|MICRO MARKET|MICROMARKET|CANTEEN", _txt(r)))),
    ("grocery", lambda r: bool(re.search(
        r"SUPERMARKET|GROCERY", _txt(r)))),
    ("correctional", lambda r: bool(re.search(
        r"CORRECTIONAL|DETENTION|\bJAIL\b|PRISON", _txt(r)))),
]
V1_EXPECTED = {"unit": 138, "ballroom": 173, "hotel_suboutlet": 129,
               "contractor": 386, "theme_park": 147, "casino": 16,
               "private_club": 729, "education": 52, "healthcare": 500,
               "faith_charity": 12, "cafeteria": 93, "commissary": 222,
               "vending": 4, "grocery": 11, "correctional": 0}


def _fold2(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.upper()).strip()


V2_HOTEL_BRANDS = ['MARRIOTT', 'HILTON', 'HYATT', 'RITZ', 'FOUR SEASONS',
                   'WESTIN', 'SHERATON', 'WYNDHAM', 'OMNI', 'LOEWS',
                   'FAIRMONT', 'WALDORF', 'INTERCONTINENTAL', 'GAYLORD',
                   'DIPLOMAT', 'FONTAINEBLEAU', 'EDEN ROC', 'SETAI',
                   'FAENA', 'AUTOGRAPH', 'HARD ROCK', 'SEMINOLE',
                   'RENAISSANCE', 'DOUBLETREE', 'EMBASSY SUITES',
                   'CROWNE PLAZA', 'HOLIDAY INN', 'HAMPTON INN', 'HAMPTON',
                   'RESIDENCE INN', 'COURTYARD', 'SPRINGHILL',
                   'BEST WESTERN', 'LA QUINTA', 'RED ROOF', 'MOTEL 6',
                   'SUPER 8', 'DAYS INN', 'TRAVELODGE', 'COMFORT INN',
                   'QUALITY INN', 'SLEEP INN', 'CLARION', 'BAYMONT',
                   'WINGATE', 'HAWTHORN', 'ALOFT', 'ELEMENT',
                   'FOUR POINTS', 'LE MERIDIEN', 'CONRAD', 'CURIO',
                   'CANOPY', 'HOMEWOOD', 'HOME2 SUITES', 'STAYBRIDGE',
                   'CANDLEWOOD', 'HOTEL INDIGO', 'KIMPTON',
                   'MARGARITAVILLE', 'JW MARRIOTT', 'ST REGIS',
                   'TRU BY HILTON', 'FAIRFIELD', 'TOWNEPLACE',
                   'HYATT PLACE', 'HYATT HOUSE', 'HILTON GARDEN',
                   'HOMEWOOD SUITES']
V2_AIR_LN = ['SSP', 'HMSHOST', 'HMS HOST', 'OTG', 'PARADIES', 'AREAS',
             'HUDSON', 'NEWSLINK', 'DUTY FREE', 'TRAVEL FOOD SERVICE']
V2_SENIOR = ['AMERICAN HOUSE', 'BROOKDALE', 'HARBORCHASE', 'WATERCREST',
             'ELMCROFT', 'SENIOR LIVING', 'MEMORY CARE',
             'INDEPENDENT LIVING', 'FIVE STAR SENIOR', 'SUNRISE SENIOR',
             'DISCOVERY SENIOR', 'ERICKSON LIVING', 'SONATA SENIOR',
             'VI AT', 'THE CARLISLE']
V2_CONTRACT2 = ['RESTAURANT ASSOCIATES', 'FLIK', 'BON APPETIT',
                'PARKHURST', 'CREATIVE DINING', 'SAGE DINING',
                'WHITSONS', 'ALADDIN', 'THOMPSON HOSPITALITY', 'ELIOR',
                'TRUSTED SERVE', 'BATEMAN', 'ABM INDUSTRIES']
V2_FOODISH = ['CAFE', 'CAFETERIA', 'DINING', 'GRILL', 'KITCHEN',
              'RESTAURANT', 'EATERY', 'SNACK', 'JUICE', 'SMOOTHIE',
              'FITNESS', 'DELI', 'BAKERY', 'PIZZA', 'SUSHI', 'BAR']


def v2_reason(r):
    bn = _fold2(r['business_name'])
    ln = _fold2(r['licensee_name'])
    addr = _fold2(r['loc_address'])
    txt = bn + ' ' + ln
    if ('AIRPORT' in txt + ' ' + addr or 'JEFF FUQUA' in addr
            or re.search(r'\b(GATE|GATES|TERMINAL|CONCOURSE|AIRSIDE)\b',
                         bn)
            or any(a in ln for a in V2_AIR_LN)):
        return 'T1'
    if re.search(r'\b(VENDOR|STALL|BOOTH)\b', bn) or 'FOOD HALL' in txt:
        return 'T2'
    if any(b in ln for b in V2_HOTEL_BRANDS):
        return 'T3a'
    if (any(b in bn for b in V2_HOTEL_BRANDS)
            and re.search(r'\b(HOTEL|INN|SUITES|RESORT|MOTEL|LODGE)\b',
                          bn)):
        return 'T3b'
    if re.search(r'\b(HOTEL|RESORT|RESORTS)\b', ln):
        return 'T3c'
    if 'MEMBER' in bn:
        return 'T4a'
    if re.search(r'\bCLUB\b', ln) and any(f in bn for f in V2_FOODISH):
        return 'T4b'
    if ('PADEL' in txt or re.search(
            r'\b(FITNESS|ATHLETIC|SPORTS)\s+(CENTER|CENTRE|CLUB)\b',
            bn)):
        return 'T4c'
    if any(s in txt for s in V2_SENIOR):
        return 'T5'
    if any(c in ln for c in V2_CONTRACT2):
        return 'T6'
    if r['rank'] == 'NOST' and re.match(r'^CHEF\b', bn):
        return 'T7'
    return None


V2_EXPECTED = {'T1': 224, 'T2': 23, 'T3a': 38, 'T3b': 742, 'T3c': 371,
               'T4a': 4, 'T4b': 72, 'T4c': 10, 'T5': 10, 'T6': 21,
               'T7': 2}

V3_FOODDESC = ['RESTAURANT', 'GRILL', 'CAFE', 'KITCHEN', 'EATERY',
               'TAVERN', 'BISTRO', 'DINER', 'PIZZA', 'SUSHI', 'DELI',
               'BAKERY', 'BAR &', 'BBQ', 'SEAFOOD', 'STEAKHOUSE',
               'CANTINA', 'TRATTORIA', 'BRASSERIE']


def v3_reason(r):
    bn, ln = _fold2(r['business_name']), _fold2(r['licensee_name'])
    if re.search(r'\bHOTELS?\b', ln) or re.search(r'\bRESORTS?\b', ln):
        return 'T3c2'
    if re.search(r'\b(HOTEL|MOTEL|RESORT)\b', bn):
        return 'T3d'
    toks = len(re.findall(r'\b(HOTEL|MOTEL|RESORT|LODGE|INN|SUITES)\b',
                          bn))
    if toks >= 2:
        return 'T3e'
    if 'SABRA' in ln or 'HOME 2' in bn or bn.startswith('HOME2'):
        return 'T5b'
    if (re.search(r'\bGOLF\b', bn)
            and not any(f in bn for f in V3_FOODDESC)):
        return 'T4d'
    if re.search(r'\b(THEATRE|THEATER|CINEMA|MOVIES?)\b', bn):
        return 'T8'
    return None


V3_EXPECTED = {'T3c2': 47, 'T3d': 123, 'T3e': 27, 'T5b': 10, 'T4d': 88,
               'T8': 33}

V4_FOOD_OK = {'RESTAURANT', 'GRILL', 'CAFE', 'KITCHEN', 'EATERY',
              'TAVERN', 'BISTRO', 'DINER', 'PIZZA', 'SUSHI', 'DELI',
              'BAKERY', 'BBQ', 'SEAFOOD', 'STEAKHOUSE', 'CANTINA',
              'TRATTORIA'}


def _fold3(s):
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return s.upper()


def v4_reason(r):
    B = _fold3(r['business_name'])
    L = _fold3(r['licensee_name'])
    if (re.search(r'\b(CITY OF|BOARD OF COUNTY|COUNTY COMMISSION|'
                  r'SCHOOL BOARD|SCHOOL DISTRICT|STATE OF FLORIDA|'
                  r'DEPARTMENT OF [A-Z]|UNITED STATES ARMY|'
                  r'UNITED STATES NAVY|UNITED STATES AIR FORCE)\b', L)
            or re.search(r'\b(COUNTY|CITY|STATE|BOARD OF COUNTY '
                         r'COMMISSIONERS)\b', B)
            and re.search(r'\b(COUNTY|CITY|STATE|COMMISSION|BOARD)\b',
                          B)
            and ('COMMISSION' in B or 'BOARD OF' in B)):
        return 'T9'
    if (re.search(r'\bBOARD OF COUNTY COMMISSIONERS\b', B)
            or re.search(r'\bCOUNTY BOARD\b', L)):
        return 'T9'
    if re.search(r'\b(TEMPLE|MANDIR|GURDWARA|ASHRAM|MONASTERY|'
                 r'CONVENT)\b', B):
        return 'T10'
    if re.search(r'\b(LANES|BOWLING|SKATE PARK|SKATING|ICE ARENA|'
                 r'WATER PARK|WATERPARK|AMUSEMENT)\b', B):
        return 'T11'
    if B.strip() == 'CLUBHOUSE' or re.search(r'\bCLUBHOUSE\b', B):
        return 'T12'
    if 'POOLSIDE' in B or 'POOL DECK' in B:
        return 'T13'
    if (re.search(r'\b(MOTORCARS|MOTOR CARS|AUTO GROUP|AUTOMOTIVE '
                  r'GROUP|MOTOR COMPANY)\b', L)
            or ('MERCEDES' in B
                and not any(w in B for w in V4_FOOD_OK))):
        return 'T14'
    return None


V4_EXPECTED = {'T9': 51, 'T10': 6, 'T11': 55, 'T12': 23, 'T13': 4,
               'T14': 5}

# --- v5 (design 1.6), implemented for this execution.
# T15: hotel brand in the business NAME (T3a brand list + the 1.6
# additions) AND no food-identity token in the name. Substring
# matching, consistent with every earlier stage.
T15_BRANDS = V2_HOTEL_BRANDS + ['RADISSON', 'RAMADA', 'SONESTA', 'DRURY',
                                'GRADUATE', 'SIGNIA', 'EXTENDED STAY']
T15_FOOD = {'RESTAURANT', 'CAFE', 'GRILL', 'KITCHEN', 'EATERY',
            'BISTRO', 'DINER', 'PIZZA', 'SUSHI', 'DELI', 'BAKERY',
            'TAQUERIA', 'BBQ', 'SEAFOOD', 'STEAKHOUSE', 'CANTINA',
            'TRATTORIA', 'TAVERN', 'BRASSERIE', 'BREW', 'TAPROOM',
            'MARKET', 'FOOD', 'EATS', 'DINING', 'LOUNGE', 'BAR'}


def t15_hit(r):
    bn = _fold2(r['business_name'])
    if not any(b in bn for b in T15_BRANDS):
        return False
    return not any(f in bn for f in T15_FOOD)


def apply_rules(rows, reason_fn, expected, label):
    kept, dropped = [], Counter()
    for r in rows:
        why = reason_fn(r)
        if why:
            dropped[why] += 1
        else:
            kept.append(r)
    for k, v in expected.items():
        check(f"{label} {k}", dropped.get(k, 0), v)
    extra = {k: v for k, v in dropped.items() if k not in expected}
    if extra:
        print(f"  [MISMATCH] {label} unexpected rules fired: {extra}")
        raise SystemExit(f"ASSERT FAILED: {label} unexpected rules")
    check(f"{label} total dropped", sum(dropped.values()),
          sum(expected.values()))
    return kept


LIC_FIELDS = ["license_number", "type", "rank", "business_name",
              "licensee_name", "loc_address", "loc_city", "loc_zip",
              "phone", "expiry_date", "last_inspection"]


def write_lics(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LIC_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in LIC_FIELDS})


def read_lics(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def cmd_funnel(survivors_path, reference_v4=None):
    rows = read_lics(survivors_path)
    check("pilot survivors", len(rows), 23860)
    perm = [r for r in rows if r["type"] == "2010"]
    mobile = [r for r in rows if r["type"] != "2010"]
    check("step 1 Mobile dropped", len(mobile), 8251)
    check("step 1 Permanent kept", len(perm), 15609)
    rk = Counter(r["rank"] for r in perm)
    check("step 1 SEAT", rk.get("SEAT", 0), 12220)
    check("step 1 NOST", rk.get("NOST", 0), 3389)

    keys = Counter()
    key_of = {}
    for r in perm:
        k = norm_addr_key(r["loc_address"], r["loc_zip"])
        key_of[r["license_number"]] = k
        keys[k] += 1
    after_cluster = [r for r in perm if keys[key_of[r["license_number"]]] < 10]
    check("step 2 cluster >=10 dropped", len(perm) - len(after_cluster),
          875)
    check("step 2 remaining", len(after_cluster), 14734)

    attrib = Counter()
    v1 = []
    for r in after_cluster:
        hit = None
        for pname, fn in V1_PATTERNS:
            if fn(r):
                hit = pname
                break
        if hit:
            attrib[hit] += 1
        else:
            v1.append(r)
    for pname, _ in V1_PATTERNS:
        check(f"step 3 v1 {pname}", attrib.get(pname, 0),
              V1_EXPECTED[pname])
    check("step 3 remaining", len(v1), 12122)

    v2 = apply_rules(v1, v2_reason, V2_EXPECTED, "step 4 v2")
    check("step 4 remaining", len(v2), 10605)
    v3 = apply_rules(v2, v3_reason, V3_EXPECTED, "step 5 v3")
    check("step 5 remaining", len(v3), 10277)
    v4 = apply_rules(v3, v4_reason, V4_EXPECTED, "step 6 v4")
    check("step 6 remaining", len(v4), 10133)

    if reference_v4:
        ref = {r["license_number"] for r in read_lics(reference_v4)}
        mine = {r["license_number"] for r in v4}
        check("step 6 set-equality vs design v4 file", len(mine ^ ref),
              0)

    t15 = [r for r in v4 if t15_hit(r)]
    print(f"  [info] step 7 T15 dropped: {len(t15)} "
          f"(design estimate 173, unmeasured projection)")
    after15 = [r for r in v4 if not t15_hit(r)]
    keys16 = Counter()
    key16_of = {}
    for r in after15:
        k = norm_addr_key(r["loc_address"], r["loc_zip"],
                          zip_agnostic_t16=True)
        key16_of[r["license_number"]] = k
        keys16[k] += 1
    big16 = {k for k, c in keys16.items() if c >= 10}
    final = [r for r in after15 if key16_of[r["license_number"]]
             not in big16]
    t16_dropped = len(after15) - len(final)
    print(f"  [info] step 7 T16 dropped: {t16_dropped} "
          f"(design measured 11) across {len(big16)} address(es)")
    for k in big16:
        print(f"    T16 address: {k} x{keys16[k]}")
    print(f"FINAL designed set: {len(final)} (design: ~9,949)")
    if abs(len(final) - 9949) > 300:
        raise SystemExit("STOP: final set outside +/-300 of design "
                         "9,949")
    os.makedirs(WORK, exist_ok=True)
    out = os.path.join(WORK, "designed_set_final.csv")
    write_lics(out, final)
    print(f"wrote {out}")
    return 0


# ================================================================ rematch
# Matcher transcribed verbatim from fl_dbpr_orphans.py (pilot); the
# only adaptation is that the best-match tier is returned alongside
# the venue so exclusions can be tiered per design section 3.

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


def venue_rec(row):
    vid, name, addr, zipc, phone, active, lat, lng = (row + [""] * 8)[:8]
    house, street = parse_street(addr)
    full, dist = norm_name(name)
    try:
        flat, flng = float(lat), float(lng)
    except (TypeError, ValueError):
        flat = flng = None
    return {"id": vid, "name": name, "house": house, "street": street,
            "zip": (zipc or "")[:5], "phone": phone10(phone),
            "active": active == "1", "lat": flat, "lng": flng,
            "nfull": full, "ndist": dist}


def load_fl_venues():
    rows = fetch("SELECT id, name, address, zip, phone, is_active, lat,"
                 " lng FROM venues WHERE zip LIKE '3%' OR state='FL'")
    return [venue_rec(r) for r in rows]


def load_phone_index():
    rows = fetch("SELECT id, phone FROM venues "
                 "WHERE phone IS NOT NULL AND phone <> ''")
    idx = {}
    for vid, phone in rows:
        p = phone10(phone)
        if p:
            idx.setdefault(p, []).append(vid)
    return idx


def fetch_venues_by_ids(ids):
    out = []
    ids = list(ids)
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        inlist = ",".join("'" + x.replace("'", "\\'") + "'" for x in chunk)
        rows = fetch(f"SELECT id, name, address, zip, phone, is_active,"
                     f" lat, lng FROM venues WHERE id IN ({inlist})")
        out.extend(venue_rec(r) for r in rows)
    return out


def pilot_rematch(orphans, venues, phone_index):
    """Returns (excluded, survivors); excluded items are
    (license_dict, venue_dict, tier_str)."""
    block, phone_block = {}, {}
    by_id = {}
    for vi, v in enumerate(venues):
        by_id[v["id"]] = vi
        if v["zip"] and v["house"]:
            block.setdefault((v["zip"], v["house"]), []).append(vi)
        if v["zip"]:
            for t in v["street"]:
                block.setdefault((v["zip"], "S:" + t), []).append(vi)
        if v["phone"]:
            phone_block.setdefault(v["phone"], []).append(vi)

    orphan_phones = {phone10(o["phone"]) for o in orphans
                     if phone10(o["phone"])}
    extra_ids = set()
    for p in orphan_phones:
        for vid in phone_index.get(p, []):
            if vid not in by_id:
                extra_ids.add(vid)
    if extra_ids:
        extras = fetch_venues_by_ids(extra_ids)
        for v in extras:
            by_id[v["id"]] = len(venues)
            venues.append(v)
            if v["phone"]:
                phone_block.setdefault(v["phone"], []).append(
                    by_id[v["id"]])
        print(f"phone pass added {len(extras)} out-of-subset venues")

    excluded, survivors = [], []
    for lic in orphans:
        house, street = parse_street(lic["addr"])
        full, dist = norm_name(lic["bname"] or lic["licee"])
        zip5 = (lic["zip"] or "")[:5]
        ph = phone10(lic["phone"])
        cand = set()
        if zip5 and house:
            cand.update(block.get((zip5, house), []))
        if zip5:
            for t in street:
                cand.update(block.get((zip5, "S:" + t), []))
        if ph:
            cand.update(phone_block.get(ph, []))
        best = None
        for vi in cand:
            v = venues[vi]
            ns = name_score(full, dist, v["nfull"], v["ndist"])
            sj = jaccard(street, v["street"])
            same_house = house and house == v["house"]
            phone_hit = ph and ph == v["phone"]
            tier = None
            if phone_hit and ns >= 0.60:
                tier = 2
            elif same_house and sj >= 0.6 and ns >= 0.70:
                tier = 2
            elif phone_hit and ns >= 0.45:
                tier = 1
            elif same_house and sj >= 0.4 and ns >= 0.55:
                tier = 1
            if tier and (best is None or tier > best[0]):
                best = (tier, v)
        if best:
            excluded.append((lic, best[1],
                             "STRONG" if best[0] == 2 else "MEDIUM"))
        else:
            survivors.append(lic)
    return excluded, survivors


def cmd_rematch():
    path = os.path.join(WORK, "designed_set_final.csv")
    rows = read_lics(path)
    print(f"designed set in: {len(rows)}")
    exclusions = []  # (num, venue_id, tier, is_active, reason)

    fresh = []
    for r in rows:
        exp = (r.get("expiry_date") or "").strip()
        if exp and exp < EXEC_DATE:
            exclusions.append((r["license_number"], None, None, None,
                               "expired"))
        else:
            fresh.append(r)
    print(f"freshness (design 9.1): dropped {len(rows) - len(fresh)} "
          f"expired-before-{EXEC_DATE}; {len(fresh)} proceed")

    orphans = [{"num": r["license_number"], "type": r["type"],
                "rank": r["rank"], "bname": r["business_name"],
                "licee": r["licensee_name"], "addr": r["loc_address"],
                "city": r["loc_city"], "zip": r["loc_zip"],
                "phone": r["phone"], "expiry": r["expiry_date"],
                "insp": r["last_inspection"]} for r in fresh]
    by_num = {o["num"]: o for o in orphans}

    venues = load_fl_venues()
    print(f"FL venue subset loaded: {len(venues)} "
          f"(active {sum(1 for v in venues if v['active'])})",
          flush=True)
    phone_index = load_phone_index()
    print(f"phone index: {len(phone_index)} numbers", flush=True)
    excluded, survivors = pilot_rematch(orphans, venues, phone_index)
    n_act = sum(1 for _, v, _ in excluded if v["active"])
    n_inact = len(excluded) - n_act
    print(f"rematch excluded: {len(excluded)} (ACTIVE {n_act}, "
          f"INACTIVE {n_inact})")
    for lic, v, tier in excluded:
        exclusions.append((lic["num"], v["id"], tier,
                           1 if v["active"] else 0,
                           "active_match" if v["active"]
                           else "inactive_match"))
    surv_nums = {o["num"] for o in survivors}

    # self-dedupe (design 3.4): group by (normalized name,
    # normalized address); keep most recent last_inspection,
    # tie -> lowest license_number.
    groups = defaultdict(list)
    for o in survivors:
        key = (" ".join(norm_text(o["bname"] or o["licee"])),
               " ".join(norm_text(o["addr"])))
        groups[key].append(o)
    kept = []
    n_self = 0
    for key, g in groups.items():
        if len(g) == 1:
            kept.append(g[0])
            continue
        g_sorted = sorted(g, key=lambda o: o["num"])
        winner = max(g_sorted, key=lambda o: o["insp"] or "")
        kept.append(winner)
        for o in g:
            if o["num"] != winner["num"]:
                n_self += 1
                exclusions.append((o["num"], None, None, None,
                                   "self_dedupe"))
    print(f"self-dedupe dropped: {n_self}")
    print(f"post-rematch set: {len(kept)}")

    run_sql("""
DROP TABLE IF EXISTS dbpr_rematch_exclusions_20261027;
CREATE TABLE dbpr_rematch_exclusions_20261027 (
  license_number VARCHAR(20) PRIMARY KEY,
  matched_venue_id VARCHAR(255) NULL,
  tier VARCHAR(10) NULL,
  venue_is_active TINYINT NULL,
  reason VARCHAR(30),
  excluded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;
""")
    lines = []
    for num, vid, tier, act, reason in exclusions:
        lines.append(f"({esc(num)},"
                     f"{esc(vid) if vid else 'NULL'},"
                     f"{esc(tier) if tier else 'NULL'},"
                     f"{act if act is not None else 'NULL'},"
                     f"{esc(reason)})")
    for i in range(0, len(lines), 500):
        run_sql("INSERT INTO dbpr_rematch_exclusions_20261027 "
                "(license_number, matched_venue_id, tier, "
                "venue_is_active, reason) VALUES "
                + ",".join(lines[i:i + 500]) + ";")
    print(f"exclusions written: {len(lines)}")

    out_rows = []
    for o in kept:
        out_rows.append({"license_number": o["num"],
                         "type": o["type"], "rank": o["rank"],
                         "business_name": o["bname"],
                         "licensee_name": o["licee"],
                         "loc_address": o["addr"],
                         "loc_city": o["city"],
                         "loc_zip": o["zip"], "phone": o["phone"],
                         "expiry_date": o["expiry"],
                         "last_inspection": o["insp"]})
    out = os.path.join(WORK, "post_rematch.csv")
    write_lics(out, out_rows)
    print(f"wrote {out}: {len(out_rows)}")
    return 0


# ================================================================ geocode
def census_geocode(records):
    """Transcribed from fl_dbpr_orphans.py. Returns dict
    num -> (lat, lng, matched_address, match_type) | None |
    ('ZIPMISMATCH', matched_address)."""
    results = {}
    for start in range(0, len(records), 5000):
        chunk = records[start:start + 5000]
        buf = io.StringIO()
        w = csv.writer(buf)
        for i, r in enumerate(chunk):
            addr = re.sub(r"\s+", " ", (r["addr"] or "").strip())
            w.writerow([i, addr, (r["city"] or "").strip(), "FL",
                        (r["zip"] or "")[:5]])
        tmp_in = os.path.join(WORK, "census_in.csv")
        with open(tmp_in, "w") as f:
            f.write(buf.getvalue())
        proc = subprocess.run(
            ["curl", "-s", "-F", f"addressFile=@{tmp_in}",
             "-F", "benchmark=Public_AR_Current",
             "-F", "vintage=Current_Current",
             "https://geocoding.geo.census.gov/geocoder/locations/"
             "addressbatch"],
            capture_output=True, text=True, timeout=1800)
        if proc.returncode != 0 or not proc.stdout.strip():
            print("census error:", proc.stderr[:500], file=sys.stderr)
            raise SystemExit(1)
        # NOTE (execution repair, 2026-10-27): the pilot transcription
        # skipped rows with <8 fields, but Census returns No_Match/Tie
        # rows with exactly 3 fields, silently dropping every reject;
        # and it took the FIRST 5-digit token of the matched address
        # as its ZIP, falsely rejecting every 5-digit house number.
        # Both defects were proven against raw Census responses; the
        # gate below is design section 4 as written: result == Match
        # AND the matched address's ZIP5 (its trailing ZIP component)
        # equals the license ZIP5.
        parsed = 0
        for row in csv.reader(io.StringIO(proc.stdout)):
            if not row:
                continue
            try:
                rec = chunk[int(row[0])]
            except (ValueError, IndexError):
                continue
            parsed += 1
            if len(row) < 6 or row[2].strip() != "Match":
                results[rec["num"]] = None
                continue
            matched_addr = row[4].strip()
            try:
                lng_s, lat_s = row[5].strip().split(",")
                lat, lng = float(lat_s), float(lng_s)
            except ValueError:
                results[rec["num"]] = None
                continue
            zips = re.findall(r"\b(\d{5})\b", matched_addr)
            if not zips or zips[-1] != (rec["zip"] or "")[:5]:
                results[rec["num"]] = ("ZIPMISMATCH", matched_addr)
                continue
            results[rec["num"]] = (lat, lng, matched_addr,
                                   row[3].strip())
        if parsed == 0:
            print("census response parsed ZERO rows; first 300 "
                  "chars of response:", proc.stdout[:300],
                  file=sys.stderr)
            raise SystemExit("STOP: Census response unparseable "
                             "(possible WAF rejection)")
        print(f"geocoded chunk {start}..{start + len(chunk)} "
              f"({parsed} rows)", flush=True)
    return results


def haversine_m(lat1, lng1, lat2, lng2):
    p = math.pi / 180.0
    a = (0.5 - math.cos((lat2 - lat1) * p) / 2
         + math.cos(lat1 * p) * math.cos(lat2 * p)
         * (1 - math.cos((lng2 - lng1) * p)) / 2)
    return 12742 * math.asin(math.sqrt(a)) * 1000


def guard_name_sim(a, b):
    fa = " ".join(norm_text(a))
    fb = " ".join(norm_text(b))
    if not fa or not fb:
        return 0.0
    ratio = difflib.SequenceMatcher(None, fa, fb).ratio()
    ja = jaccard(set(fa.split()), set(fb.split()))
    return max(ratio, ja)


def census_city(matched_addr, fallback):
    # Census matched addresses are "STREET, CITY, FL, ZIP" (state and
    # ZIP as separate trailing parts) or "STREET, CITY, FL ZIP".
    # Strip the trailing ZIP/state parts; the city is what remains
    # last. (First execution took parts[-2] of the 4-part form and
    # stored the state as the city on all 7,556 rows; corrected by a
    # one-time pass over the inserted set — see the report.)
    parts = [p.strip() for p in (matched_addr or "").split(",")
             if p.strip()]
    while parts and (re.fullmatch(r"\d{5}(-\d{4})?", parts[-1])
                     or re.fullmatch(r"[A-Z]{2}", parts[-1])
                     or re.fullmatch(r"[A-Z]{2} \d{5}(-\d{4})?",
                                     parts[-1])):
        parts.pop()
    if parts and not re.match(r"\d", parts[-1]):
        return parts[-1]
    return fallback or ""


def cmd_geocode():
    rows = read_lics(os.path.join(WORK, "post_rematch.csv"))
    recs = [{"num": r["license_number"], "type": r["type"],
             "rank": r["rank"], "bname": r["business_name"],
             "licee": r["licensee_name"], "addr": r["loc_address"],
             "city": r["loc_city"], "zip": r["loc_zip"],
             "phone": r["phone"], "expiry": r["expiry_date"],
             "insp": r["last_inspection"]} for r in rows]
    print(f"post-rematch to geocode: {len(recs)}", flush=True)
    geo = census_geocode(recs)
    ok = {k: v for k, v in geo.items() if v and v[0] != "ZIPMISMATCH"}
    zm = {k: v for k, v in geo.items() if v and v[0] == "ZIPMISMATCH"}
    nm = {k for k, v in geo.items() if v is None}
    gate_rate = len(ok) / len(recs) if recs else 0
    print(f"geocode gate: matched+zip-ok {len(ok)}, zip-mismatch "
          f"{len(zm)}, no-match/tie {len(nm)}; pass rate "
          f"{gate_rate:.1%}")
    if gate_rate < 0.75:
        raise SystemExit("STOP: geocode gate pass rate below 75% "
                         "(design section 4)")

    # 50m / 0.85 guard vs ACTIVE venues (design 4). The pilot ran one
    # bbox query per candidate; this loads the FL active set once
    # into a grid and applies the identical haversine+sim test.
    vrows = fetch("SELECT name, lat, lng FROM venues "
                  "WHERE is_active=1 AND lat BETWEEN 24.0 AND 31.6 "
                  "AND lng BETWEEN -88.6 AND -79.4")
    grid = defaultdict(list)
    for vn, vlat, vlng in vrows:
        try:
            flat, flng = float(vlat), float(vlng)
        except (TypeError, ValueError):
            continue
        grid[(int(flat * 1000), int(flng * 1000))].append(
            (vn, flat, flng))
    print(f"guard universe: {len(vrows)} active FL-area venues")

    final, rejects = [], []
    for k, v in zm.items():
        rejects.append((k, "zip_mismatch", v[1]))
    for k in nm:
        rejects.append((k, "no_match_or_tie", ""))
    n_guard = 0
    for r in recs:
        g = ok.get(r["num"])
        if not g:
            continue
        lat, lng, matched_addr, mtype = g
        name = (r["bname"] or "").strip() or (r["licee"] or "").strip()
        ci, cj = int(lat * 1000), int(lng * 1000)
        hit = False
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for vn, vlat, vlng in grid.get((ci + di, cj + dj), []):
                    d = haversine_m(lat, lng, vlat, vlng)
                    if d <= 50 and guard_name_sim(name, vn) >= 0.85:
                        hit = True
                        break
                if hit:
                    break
            if hit:
                break
        if hit:
            n_guard += 1
            rejects.append((r["num"], "guard_50m_active_venue",
                            matched_addr))
            continue
        final.append((r, lat, lng, matched_addr, mtype))
    print(f"guard drops: {n_guard}")
    print(f"FINAL staged candidates: {len(final)}")

    _load_stage(final)
    with open(os.path.join(WORK, "geocode_rejects.csv"), "w",
              newline="") as f:
        w = csv.writer(f)
        w.writerow(["license_number", "reason", "detail"])
        w.writerows(rejects)
    print(f"staged {len(final)}; rejects {len(rejects)} "
          f"(parked tranche)")
    return 0


def _load_stage(final):
    run_sql("""
DROP TABLE IF EXISTS dbpr_expansion_stage_20261027;
CREATE TABLE dbpr_expansion_stage_20261027 (
  license_number VARCHAR(20) PRIMARY KEY,
  license_type VARCHAR(10), rank_code VARCHAR(10),
  business_name VARCHAR(255), licensee_name VARCHAR(255),
  loc_address VARCHAR(255), loc_city VARCHAR(100), loc_zip VARCHAR(10),
  phone VARCHAR(30), expiry_date DATE NULL, last_inspection DATE NULL,
  lat DECIMAL(10,8), lng DECIMAL(11,8),
  matched_address VARCHAR(500), match_type VARCHAR(20),
  census_city VARCHAR(200)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;
""")
    lines = []
    for r, lat, lng, matched_addr, mtype in final:
        ccity = census_city(matched_addr, r["city"])
        lines.append(
            f"({esc(r['num'])},{esc(r['type'])},{esc(r['rank'])},"
            f"{esc(r['bname'])},{esc(r['licee'])},{esc(r['addr'])},"
            f"{esc(r['city'])},{esc(r['zip'])},{esc(r['phone'])},"
            f"{dcol(r['expiry'])},{dcol(r['insp'])},{lat:.8f},"
            f"{lng:.8f},{esc(matched_addr)},{esc(mtype)},"
            f"{esc(ccity)})")
    for i in range(0, len(lines), 500):
        run_sql("INSERT INTO dbpr_expansion_stage_20261027 VALUES "
                + ",".join(lines[i:i + 500]) + ";")
    print(f"stage table loaded: {len(lines)}")


# ----------------------------------------------------------------
# The Census batch endpoint's WAF rejects requests from the croix.ai
# host IP (verified 2026-10-27: HTML "Request Rejected" page, HTTP
# 200, zero parseable rows), while the identical request succeeds
# from this VM. cmd_geocode_local therefore runs the section-4
# geocode + gate + guard from the VM: Census over HTTPS from here,
# the guard universe pulled from the host DB over SSH in one query.
# Output staged_final.csv is loaded on the host by cmd_loadstage.
# The gate, thresholds and guard test are unchanged.

STAGED_FIELDS = ["num", "type", "rank", "bname", "licee", "addr",
                 "city", "zip", "phone", "expiry", "insp", "lat",
                 "lng", "matched_address", "match_type"]


def host_fetch(sql):
    proc = subprocess.run(
        ["ssh", "-i", "/home/hatch/.ssh/id_ed25519",
         "-o", "StrictHostKeyChecking=accept-new", "root@croix.ai",
         f"mysql -uroot -N -B neutraleats -e \"{sql}\""],
        capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr[:1500], file=sys.stderr)
        raise SystemExit(1)
    out = []
    for line in proc.stdout.splitlines():
        out.append([("" if c == r"\N" else c)
                    for c in line.split("\t")])
    return out


def cmd_geocode_local(post_rematch_path):
    rows = read_lics(post_rematch_path)
    recs = [{"num": r["license_number"], "type": r["type"],
             "rank": r["rank"], "bname": r["business_name"],
             "licee": r["licensee_name"], "addr": r["loc_address"],
             "city": r["loc_city"], "zip": r["loc_zip"],
             "phone": r["phone"], "expiry": r["expiry_date"],
             "insp": r["last_inspection"]} for r in rows]
    print(f"post-rematch to geocode: {len(recs)}", flush=True)
    geo = census_geocode(recs)
    ok = {k: v for k, v in geo.items() if v and v[0] != "ZIPMISMATCH"}
    zm = {k: v for k, v in geo.items() if v and v[0] == "ZIPMISMATCH"}
    nm = {k for k, v in geo.items() if v is None}
    gate_rate = len(ok) / len(recs) if recs else 0
    print(f"geocode gate: matched+zip-ok {len(ok)}, zip-mismatch "
          f"{len(zm)}, no-match/tie {len(nm)}; pass rate "
          f"{gate_rate:.1%}", flush=True)
    if gate_rate < 0.75:
        raise SystemExit("STOP: geocode gate pass rate below 75% "
                         "(design section 4)")

    vrows = host_fetch(
        "SELECT name, lat, lng FROM venues WHERE is_active=1 "
        "AND lat BETWEEN 24.0 AND 31.6 AND lng BETWEEN -88.6 "
        "AND -79.4")
    grid = defaultdict(list)
    for vn, vlat, vlng in vrows:
        try:
            flat, flng = float(vlat), float(vlng)
        except (TypeError, ValueError):
            continue
        grid[(int(flat * 1000), int(flng * 1000))].append(
            (vn, flat, flng))
    print(f"guard universe: {len(vrows)} active FL-area venues")

    final, rejects = [], []
    for k, v in zm.items():
        rejects.append((k, "zip_mismatch", v[1]))
    for k in nm:
        rejects.append((k, "no_match_or_tie", ""))
    n_guard = 0
    for r in recs:
        g = ok.get(r["num"])
        if not g:
            continue
        lat, lng, matched_addr, mtype = g
        name = (r["bname"] or "").strip() or (r["licee"] or "").strip()
        ci, cj = int(lat * 1000), int(lng * 1000)
        hit = False
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for vn, vlat, vlng in grid.get((ci + di, cj + dj), []):
                    d = haversine_m(lat, lng, vlat, vlng)
                    if d <= 50 and guard_name_sim(name, vn) >= 0.85:
                        hit = True
                        break
                if hit:
                    break
            if hit:
                break
        if hit:
            n_guard += 1
            rejects.append((r["num"], "guard_50m_active_venue",
                            matched_addr))
            continue
        final.append((r, lat, lng, matched_addr, mtype))
    print(f"guard drops: {n_guard}")
    print(f"FINAL staged candidates: {len(final)}")

    os.makedirs(WORK, exist_ok=True)
    with open(os.path.join(WORK, "staged_final.csv"), "w",
              newline="") as f:
        w = csv.writer(f)
        w.writerow(STAGED_FIELDS)
        for r, lat, lng, matched_addr, mtype in final:
            w.writerow([r["num"], r["type"], r["rank"], r["bname"],
                        r["licee"], r["addr"], r["city"], r["zip"],
                        r["phone"], r["expiry"], r["insp"], lat, lng,
                        matched_addr, mtype])
    with open(os.path.join(WORK, "geocode_rejects.csv"), "w",
              newline="") as f:
        w = csv.writer(f)
        w.writerow(["license_number", "reason", "detail"])
        w.writerows(rejects)
    print(f"wrote staged_final.csv ({len(final)}) + "
          f"geocode_rejects.csv ({len(rejects)})")
    return 0


def cmd_loadstage():
    path = os.path.join(WORK, "staged_final.csv")
    with open(path) as f:
        rows = list(csv.DictReader(f))
    final = []
    for row in rows:
        rec = {"num": row["num"], "type": row["type"],
               "rank": row["rank"], "bname": row["bname"],
               "licee": row["licee"], "addr": row["addr"],
               "city": row["city"], "zip": row["zip"],
               "phone": row["phone"], "expiry": row["expiry"],
               "insp": row["insp"]}
        final.append((rec, float(row["lat"]), float(row["lng"]),
                      row["matched_address"], row["match_type"]))
    print(f"staged_final in: {len(final)}")
    _load_stage(final)
    return 0


# ================================================================ names
# Design section 5 name-selection rule.

NAME_FOOD = T15_FOOD | {"RESTAURANTS"}


def repair_name(s):
    """Mechanical encoding repairs only: non-breaking space -> space,
    and the mojibake inverted question mark that the DBPR extract
    substituted for apostrophes (e.g. HOLLERBACH?S) -> apostrophe."""
    return (s or "").replace("\u00a0", " ").replace("¿", "'")


def strip_store_numbers(s):
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"\s*-?\s*#?\s*\d+-\d+\s*$", "", s)
        s = re.sub(r"\s*#\s*\d+\s*$", "", s)
        s = s.strip(" -")
    return s.strip()


def has_vowel_word(s):
    for t in norm_text(s):
        if len(t) >= 4 and re.search(r"[AEIOU]", t):
            return True
    return False


def is_shell(s):
    f = _fold2(s)
    m = re.match(r"^(.*?)[\s,]*(LLC|INC|CORP|CORPORATION|LTD|LLP|LP|"
                 r"COMPANY)\.?$", f)
    if not m:
        return False
    toks = norm_text(m.group(1))
    if not toks:
        return True
    if any(t in NAME_FOOD for t in toks):
        return False
    return len(toks) <= 3


def select_display_name(bname, licee):
    """Returns (display_name, None) or (None, queue_reason)."""
    raw = (bname or "").strip() or (licee or "").strip()
    s = repair_name(raw)
    f = _fold2(s)
    if re.match(r"^BK\s*#", f):
        return "Burger King", None
    if f.startswith("DDBR"):
        return "Dunkin'", None
    if "PC#" in f or "PC #" in f:
        return None, "unresolved_pc_code"
    s = strip_store_numbers(s)
    if "#" in s:
        return None, "unresolved_hash_code"
    if not has_vowel_word(s):
        return None, "code_name_no_vowel_word"
    if is_shell(s):
        alt = repair_name((licee or "").strip())
        if alt and _fold2(alt) != _fold2(s):
            alt = strip_store_numbers(alt)
            if ("#" not in alt and has_vowel_word(alt)
                    and not is_shell(alt)):
                return title_case(alt), None
        return None, "entity_shell"
    return title_case(s), None


STAGE_FIELDS = ["license_number", "license_type", "rank_code",
                "business_name", "licensee_name", "loc_address",
                "loc_city", "loc_zip", "phone", "expiry_date",
                "last_inspection", "lat", "lng", "matched_address",
                "match_type", "census_city"]


def cmd_names():
    rows = fetch("SELECT " + ", ".join(STAGE_FIELDS) +
                 " FROM dbpr_expansion_stage_20261027")
    print(f"staged rows: {len(rows)}")
    ready, queue = [], []
    for row in rows:
        rec = dict(zip(STAGE_FIELDS, row))
        name, reason = select_display_name(rec["business_name"],
                                           rec["licensee_name"])
        if name:
            rec["display_name"] = name
            ready.append(rec)
        else:
            queue.append((rec["license_number"],
                          rec["business_name"], rec["licensee_name"],
                          reason, rec["loc_address"], rec["loc_city"],
                          rec["loc_zip"]))
    print("queue by reason:", dict(Counter(q[3] for q in queue)))
    print(f"manual-review queue: {len(queue)}")
    print(f"insert-ready: {len(ready)}")
    with open(os.path.join(WORK, "insert_ready.csv"), "w",
              newline="") as f:
        w = csv.DictWriter(f, fieldnames=STAGE_FIELDS + ["display_name"])
        w.writeheader()
        w.writerows(ready)
    with open(os.path.join(WORK, "name_review_queue.csv"), "w",
              newline="") as f:
        w = csv.writer(f)
        w.writerow(["license_number", "business_name", "licensee_name",
                    "reason", "loc_address", "loc_city", "loc_zip"])
        w.writerows(queue)
    post = read_lics(os.path.join(WORK, "post_rematch.csv"))
    expected = round(len(post) * 0.82)
    print(f"post-rematch: {len(post)}; design-expected inserts "
          f"(x0.82): {expected}; section-5 band: "
          f"[{round(expected * 0.9)}, {round(expected * 1.1)}]; "
          f"task band: [7200, 8800]")
    return 0


# ================================================================ insert
def cmd_insert():
    with open(os.path.join(WORK, "insert_ready.csv")) as f:
        ready = list(csv.DictReader(f))
    post = read_lics(os.path.join(WORK, "post_rematch.csv"))
    expected = round(len(post) * 0.82)
    band = (round(expected * 0.9), round(expected * 1.1))
    n = len(ready)
    print(f"insert-ready: {n}; expected {expected}; section-5 band "
          f"{band}; task band (7200, 8800)")
    if not (band[0] <= n <= band[1]) or not (7200 <= n <= 8800):
        raise SystemExit("SANITY STOP: insert count outside the "
                         "sanity band — not inserting")

    pre_total = int(fetch("SELECT COUNT(*) FROM venues")[0][0])
    pre_fl = int(fetch("SELECT COUNT(*) FROM venues WHERE state='FL' "
                       "AND is_active=1")[0][0])
    print(f"pre-insert: total venues {pre_total}, FL active {pre_fl}")
    with open(os.path.join(WORK, "pre_insert_counts.txt"), "w") as f:
        f.write(f"total={pre_total}\nfl_active={pre_fl}\n")

    run_sql("""
CREATE TABLE IF NOT EXISTS dbpr_additions_20261027 (
  venue_id VARCHAR(255) PRIMARY KEY,
  license_number VARCHAR(20), venue_name VARCHAR(500),
  address VARCHAR(500), geocode_quality VARCHAR(50),
  added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;
""")
    now = int(time.time())
    vlines, alines = [], []
    for rec in ready:
        num = rec["license_number"]
        vid = f"fl_dbpr:{num}"
        name = rec["display_name"]
        addr_tc = title_case(rec["loc_address"])
        city_tc = title_case(rec["census_city"] or rec["loc_city"])
        zip5 = (rec["loc_zip"] or "")[:5]
        insp = rec["last_inspection"]
        insp_sql = dcol(insp)
        vlines.append(
            f"({esc(vid)},{esc(name)},{rec['lat']},{rec['lng']},"
            f"'restaurant','fl_dbpr',{esc(num)},{esc(addr_tc)},"
            f"{esc(city_tc)},'FL',{esc(zip5)},{esc(rec['phone'])},"
            f"{now},1,'open',{esc(num)},'current',{insp_sql},"
            f"{esc(grid_cell(float(rec['lat']), float(rec['lng'])))})")
        alines.append(
            f"({esc(vid)},{esc(num)},{esc(name)},"
            f"{esc(addr_tc + ', ' + city_tc + ', FL ' + zip5)},"
            f"{esc(rec['match_type'])})")
    for i in range(0, len(vlines), 500):
        run_sql("INSERT INTO venues (id, name, lat, lng, type, source,"
                " source_id, address, city, state, zip, phone,"
                " first_seen, is_active, operating_status,"
                " license_number, license_status, last_inspection_date,"
                " grid_cell)"
                " VALUES " + ",".join(vlines[i:i + 500]) + ";")
        run_sql("INSERT INTO dbpr_additions_20261027 (venue_id,"
                " license_number, venue_name, address,"
                " geocode_quality) VALUES "
                + ",".join(alines[i:i + 500]) + ";")
    print(f"inserted venues: {len(vlines)}")
    post_total = int(fetch("SELECT COUNT(*) FROM venues")[0][0])
    post_fl = int(fetch("SELECT COUNT(*) FROM venues WHERE state='FL'"
                        " AND is_active=1")[0][0])
    n_audit = int(fetch("SELECT COUNT(*) FROM "
                        "dbpr_additions_20261027")[0][0])
    n_src = int(fetch("SELECT COUNT(*) FROM venues "
                      "WHERE source='fl_dbpr' AND is_active=1")[0][0])
    print(f"post-insert: total {post_total} (delta "
          f"{post_total - pre_total}), FL active {post_fl} (delta "
          f"{post_fl - pre_fl}), audit rows {n_audit}, "
          f"fl_dbpr active {n_src}")
    assert post_total - pre_total == len(vlines)
    assert post_fl - pre_fl == len(vlines)
    assert n_audit == len(vlines) and n_src == len(vlines)
    print("count verification: OK")
    return 0


# ================================================================ verify
import json
import random
import urllib.parse
import urllib.request

API = "https://neutraleats.com/api/venues.php"


def api_query(lat, lng, search, half=0.008, limit=50):
    params = {"south": lat - half, "west": lng - half,
              "north": lat + half, "east": lng + half,
              "search": search, "limit": limit}
    url = API + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_find(vid, lat, lng, search):
    data = api_query(lat, lng, search)
    return any(v.get("id") == vid for v in data.get("venues", []))


def cmd_verify():
    ins = fetch("SELECT id, name, lat, lng FROM venues "
                "WHERE source='fl_dbpr'")
    by_id = {r[0]: r for r in ins}
    print(f"fl_dbpr venues live: {len(ins)}")
    ok = True

    # Gold 1: Donatello, Tampa. Its license is expected to be a
    # rematch exclusion (already catalogued); the venue must be
    # findable through the pre-existing row.
    data = api_query(27.94709750, -82.50579490, "donatello")
    names = [v["name"] for v in data.get("venues", [])]
    hit = any("Donatello" in n for n in names)
    print(f"  gold Donatello (Tampa): {'FOUND' if hit else 'MISSING'}"
          f" via API search -> {names}")
    ok &= hit

    # Gold 2: Hollerbach's, Sanford.
    hid = "fl_dbpr:SEA6903415"
    if hid in by_id:
        r = by_id[hid]
        hit = api_find(hid, float(r[2]), float(r[3]), "hollerbach")
        print(f"  gold Hollerbach's (Sanford): inserted row "
              f"{'FOUND' if hit else 'MISSING'} via API")
    else:
        data = api_query(28.81149470, -81.26669280, "hollerbach")
        names = [v["name"] for v in data.get("venues", [])]
        hit = any("Hollerbach" in n for n in names)
        print(f"  gold Hollerbach's (Sanford): license not inserted "
              f"(rematch/guard); existing row "
              f"{'FOUND' if hit else 'MISSING'} via API -> {names}")
    ok &= hit

    # Gold 3: World Famous Oasis, St. Augustine.
    oid = "fl_dbpr:SEA6500441"
    if oid in by_id:
        r = by_id[oid]
        hit = api_find(oid, float(r[2]), float(r[3]), "oasis")
        print(f"  gold World Famous Oasis (St. Augustine): inserted "
              f"row {'FOUND' if hit else 'MISSING'} via API")
    else:
        # Not inserted: the 50m guard dropped it because an active
        # row already carries it (overture:878a5c85, same name, same
        # address). Findable through that row is the pass condition.
        data = api_query(29.82175108, -81.27011639, "oasis")
        names = [(v["name"], v.get("source"))
                 for v in data.get("venues", [])]
        hit = any("World Famous Oasis" in n for n, _ in names)
        print(f"  gold World Famous Oasis (St. Augustine): guard-"
              f"dropped as already-catalogued; existing row "
              f"{'FOUND' if hit else 'MISSING'} via API -> {names}")
    ok &= hit

    # 10 random additions, name-searched in their own areas.
    random.seed(20261027)
    sample = random.sample(ins, min(10, len(ins)))
    for vid, name, lat, lng in sample:
        lat, lng = float(lat), float(lng)
        found = api_find(vid, lat, lng, name)
        if not found:
            words = " ".join(name.split()[:2])
            found = api_find(vid, lat, lng, words)
        print(f"  spot {vid} '{name}': "
              f"{'FOUND' if found else 'MISSING'}")
        ok &= found

    # 3 metro checks (design 5.2): nearest inserted venue to each
    # metro center, verified through the API.
    for label, clat, clng in (("Orlando", 28.5383, -81.3792),
                              ("Miami", 25.7617, -80.1918),
                              ("Jacksonville", 30.3322, -81.6557)):
        best = min(ins, key=lambda r: (float(r[2]) - clat) ** 2
                   + (float(r[3]) - clng) ** 2)
        vid, name, lat, lng = best
        found = api_find(vid, float(lat), float(lng), name)
        print(f"  metro {label}: nearest addition '{name}' "
              f"({vid}): {'FOUND' if found else 'MISSING'}")
        ok &= found

    print("API verification:", "ALL OK" if ok else "FAILURES ABOVE")
    return 0 if ok else 1


# ================================================================ main
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "funnel":
        ref = sys.argv[3] if len(sys.argv) > 3 else None
        raise SystemExit(cmd_funnel(sys.argv[2], ref))
    if cmd == "rematch":
        raise SystemExit(cmd_rematch())
    if cmd == "geocode":
        raise SystemExit(cmd_geocode())
    if cmd == "names":
        raise SystemExit(cmd_names())
    if cmd == "insert":
        raise SystemExit(cmd_insert())
    if cmd == "verify":
        raise SystemExit(cmd_verify())
    if cmd == "geocode_local":
        raise SystemExit(cmd_geocode_local(sys.argv[2]))
    if cmd == "loadstage":
        raise SystemExit(cmd_loadstage())
    print(__doc__)
    raise SystemExit(2)


