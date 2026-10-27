# FL DBPR Expansion Pass — Design

**Status:** DESIGN ONLY. No production writes have been made under this design. Execution requires Croix's go on the decision in §8.
**Date:** 2026-10-27. **Author:** Luxor.
**Scope approved by Croix (2026-10-27):** (1) Mobile licenses OUT; (2) cluster addresses (≥10 licenses at one normalized address) OUT; (3) sub-venues / private / institutional food service OUT; (4) the remaining Permanent, current-license, standalone-address set is accepted as a deliberate expansion.
**Inputs:** `fl_dbpr_licenses` (70,064 rows, Oct 2026 pull) on the production host; pilot matcher/geocoder in `fl_dbpr_orphans.py`; survivor file `orphan_survivors.csv` (23,860 rows) produced by the pilot funnel.

---

## 1. Funnel — exact counts at every rule

Starting point is the pilot's orphan pool: of 70,064 staged licenses, 39,148 matched the catalog in the Oct 26 pilot; 30,905 distinct license numbers did not. The pilot's own filters (current status, real address, non-temporary type, denylist, plus a re-match that excluded 1,259 licenses) left **23,860 survivors**: Permanent 15,609 / Mobile 8,251.

| Step | Rule | Dropped | Remaining |
|---|---|---:|---:|
| 0 | Pilot survivors | — | **23,860** |
| 1 | Drop Mobile (license_type ≠ 2010) | −8,251 | **15,609** Permanent (SEAT 12,220 / NOST 3,389) |
| 2 | Cluster rule ≥10 (see below) | −875 (35 addresses) | **14,734** |
| 3 | Denylist v1 (§1.2) | −2,612 | **12,122** (SEAT 10,106 / NOST 2,016) |
| 4 | Tightening v2 (§1.3, audit-driven) | −1,517 | **10,605** (SEAT 8,680 / NOST 1,925) |
| 5 | Tightening v3 (§1.4, audit-driven) | −328 | **10,277** (SEAT 8,374 / NOST 1,903) |
| 6 | Tightening v4 (§1.5, audit-driven) | −144 | **10,133** (SEAT 8,268 / NOST 1,865) |
| 7 | Tightening v5 (§1.6, designed, unmeasured) | −184 (projected) | **≈9,949** final designed set |

### 1.1 Cluster rule

Key = ZIP5 + house number + street tokens, normalized: NFKD accent-fold, uppercase, punctuation→space, suffix map (STREET→ST, AVENUE→AVE, PARKWAY→PKWY, …) + directional map; street cut at the first unit token {STE, SUITE, UNIT, APT, BLDG, #, FL, FLOOR, RM, ROOM, DEPT, LOT, SPC, SPACE, STAND, BAY}. Among the 15,609 Permanent survivors there are 13,068 distinct normalized addresses; 1,016 addresses hold ≥2 licenses.

Sensitivity (licenses dropped / addresses):

| Threshold | Dropped | Addresses |
|---|---:|---:|
| ≥5 | 1,462 | 129 |
| **≥10 (applied)** | **875** | **35** |
| ≥25 | 568 | 13 |

Top clusters are exactly the classes Croix excluded: 68 @ 9800 International Dr, Orlando (Orange County Convention Center); 56 @ 4116 N Himes Ave, Tampa (Raymond James Stadium); 56 @ 1020 W Michigan St, Orlando (commissary); 55 @ 2269 Dan Marino Blvd (Hard Rock Stadium); 54 @ 1 Tropicana Dr, St. Petersburg; 52 @ 601 Biscayne Blvd, Miami (arena); 47 @ 1 TIAA Bank Field Dr, Jacksonville; 38 @ 11770 Metro Pkwy, Fort Myers (commissary complex); 31 @ 1850 Emerson St, Jacksonville (commissary); 29 @ 1610 W Church St, Orlando (Camping World Stadium); 28 @ 400 W Church, Orlando (Kia Center); 28 @ 4200 NW 21 St, Miami (MIA airport). A supplementary licensee+ZIP5 concentration check found the same story from the other side (Boston Culinary Group 79 @ 33056; Legends Hospitality 58 @ 33607; Jacksonville Sportservice 44 @ 32202; Walt Disney Parks 42 @ 32830; Universal City Development 40 @ 32819; Centerplate 37 @ 32819).

### 1.2 Denylist v1 (−2,612)

Applied in order, first-hit attribution, against folded-uppercase `business_name` + `licensee_name`:

| # | Pattern class | Regex / tokens | Caught |
|---|---|---|---:|
| 1 | Unit designator in name | `STAND\s*#\|KIOSK\|CONCESSION\|\bCART\b` (name only) | 138 |
| 2 | Ballroom / banquet / pantry | `BALLROOM\|BANQUET\|PANTRY` | 173 |
| 3 | Hotel sub-outlet | licensee contains a hotel brand AND business/licensee distinctive-token overlap <2 | 129 |
| 4 | Food-service contractor as licensee | ARAMARK, SODEXO, COMPASS, CHARTWELLS, CENTERPLATE, DELAWARE NORTH, SPORTSERVICE, LEVY, LEGENDS HOSPITALITY, OVATIONS, METZ, MORRISON, UNIDINE, BOSTON CULINARY, CONCESSION, GUEST SERVICES, PATINA | 386 |
| 5 | Theme-park operator as licensee | DISNEY, UNIVERSAL, SEAWORLD, SEA WORLD, BUSCH, LEGOLAND, MERLIN, HERSCHEND | 147 |
| 6 | Casino / racetrack / poker in name | `CASINO\|POKER\|RACETRACK\|GREYHOUND\|JAI ALAI` | 16 |
| 7 | Private club | `COUNTRY CLUB\|YACHT CLUB\|BEACH CLUB\|TENNIS CLUB\|RACQUET CLUB\|GOLF CLUB\|HUNT CLUB\|MEMBERS ONLY\|PRIVATE CLUB` | 729 |
| 8 | Education | `\bSCHOOL\b\|UNIVERSITY\|COLLEGE\|ACADEMY\|CAMPUS\|STUDENT UNION\|CHARTER` | 52 |
| 9 | Healthcare / senior living | `HOSPITAL\|MEDICAL\|NURSING\|ASSISTED LIVING\|SENIOR\|RETIREMENT\|REHABILITATION\|\bREHAB\b\|HOSPICE\|DIALYSIS\|HEALTHCARE\|HEALTH CARE` | 500 |
| 10 | Faith / charitable feeding | `CHURCH\|MINISTR\|SYNAGOGUE\|MOSQUE\|FOOD BANK\|FOOD PANTRY\|SOUP KITCHEN\|SALVATION ARMY\|RESCUE MISSION\|\bSHELTER\b` | 12 |
| 11 | Workplace cafeteria | `CAFETERIA\|(EMPLOYEE\|STAFF)\s+(CAFE\|DINING\|CAFETERIA)` | 93 |
| 12 | Commissary / production / catering kitchen | `COMMISSARY\|CENTRAL KITCHEN\|PRODUCTION KITCHEN\|MEAL PREP\|CATERING\|CATERERS\|GHOST KITCHEN\|COMMERCIAL KITCHEN` | 222 |
| 13 | Vending-adjacent | `VENDING\|MICRO MARKET\|MICROMARKET\|CANTEEN` | 4 |
| 14 | Grocery / supermarket | `SUPERMARKET\|GROCERY` | 11 |
| 15 | Correctional | `CORRECTIONAL\|DETENTION\|\bJAIL\b\|PRISON` | 0 |

### 1.3 Tightening v2 (−1,517) — after audit round 1

- **T1 airport/transport hub (224):** 'AIRPORT' in name/licensee/address, or 'JEFF FUQUA' in address, or name regex `\b(GATE|GATES|TERMINAL|CONCOURSE|AIRSIDE)\b`, or licensee ∈ {SSP, HMSHOST, HMS HOST, OTG, PARADIES, AREAS, HUDSON, NEWSLINK, DUTY FREE, TRAVEL FOOD SERVICE}.
- **T2 food-hall/unit designator (23):** name regex `\b(VENDOR|STALL|BOOTH)\b`, or 'FOOD HALL' in name+licensee.
- **T3a hotel-brand licensee (38):** licensee contains any brand from the expanded hotel-brand list (MARRIOTT, HILTON, HYATT, RITZ, WESTIN, SHERATON, WYNDHAM, OMNI, LOEWS, FAIRMONT, WALDORF, INTERCONTINENTAL, GAYLORD, FONTAINEBLEAU, HARD ROCK, SEMINOLE, RENAISSANCE, DOUBLETREE, EMBASSY SUITES, CROWNE PLAZA, HOLIDAY INN, HAMPTON, COURTYARD, BEST WESTERN, LA QUINTA, MOTEL 6, SUPER 8, DAYS INN, COMFORT INN, QUALITY INN, CLARION, ALOFT, CONRAD, KIMPTON, MARGARITAVILLE, JW MARRIOTT, ST REGIS, FAIRFIELD, HYATT PLACE, HILTON GARDEN, …). **The v1 rule-3 overlap exemption is removed** — it is what kept the Ritz-Carlton Dusk sushi license.
- **T3b hotel property as venue name (742):** name contains a hotel brand AND name regex `\b(HOTEL|INN|SUITES|RESORT|MOTEL|LODGE)\b`.
- **T3c hotel/resort operator licensee (371):** licensee regex `\b(HOTEL|RESORT|RESORTS)\b`.
- **T4a member facility (4):** 'MEMBER' in name. **T4b club-licensee food outlet (72):** licensee regex `\bCLUB\b` AND name contains a food token {CAFE, CAFETERIA, DINING, GRILL, KITCHEN, RESTAURANT, EATERY, SNACK, JUICE, SMOOTHIE, FITNESS, DELI, BAKERY, PIZZA, SUSHI, BAR}. **T4c sports/fitness club facility (10):** 'PADEL' in name+licensee, or name regex `\b(FITNESS|ATHLETIC|SPORTS)\s+(CENTER|CENTRE|CLUB)\b`.
- **T5 senior-living brands (10):** name+licensee ∈ {AMERICAN HOUSE, BROOKDALE, HARBORCHASE, WATERCREST, ELMCROFT, SENIOR LIVING, MEMORY CARE, INDEPENDENT LIVING, FIVE STAR SENIOR, SUNRISE SENIOR, DISCOVERY SENIOR, ERICKSON LIVING, SONATA SENIOR, VI AT, THE CARLISLE}.
- **T6 contractor v2 (21):** licensee ∈ {RESTAURANT ASSOCIATES, FLIK, BON APPETIT, PARKHURST, CREATIVE DINING, SAGE DINING, WHITSONS, ALADDIN, THOMPSON HOSPITALITY, ELIOR, TRUSTED SERVE, BATEMAN, ABM INDUSTRIES}.
- **T7 NOST chef-led op (2):** rank NOST AND name regex `^CHEF\b`.

### 1.4 Tightening v3 (−328) — after an interim tuning draw from the v2 set

- **T3d lodging token in venue name (123):** name regex `\b(HOTEL|MOTEL|RESORT)\b`.
- **T4d golf facility without restaurant identity (88):** name contains `\bGOLF\b` AND none of {RESTAURANT, GRILL, CAFE, KITCHEN, EATERY, TAVERN, BISTRO, DINER, PIZZA, SUSHI, DELI, BAKERY, BAR &, BBQ, SEAFOOD, STEAKHOUSE, CANTINA, TRATTORIA, BRASSERIE}.
- **T3c2 hotel/resort operator licensee (47):** licensee regex `\bHOTELS?\b` or `\bRESORTS?\b` (v2's T3c missed plurals — e.g. MIAMI SOUTHERN HOTELS LLC).
- **T8 entertainment-venue concession (33):** name regex `\b(THEATRE|THEATER|CINEMA|MOVIES?)\b`.
- **T3e two lodging tokens in name (27):** ≥2 matches of `\b(HOTEL|MOTEL|RESORT|LODGE|INN|SUITES)\b` in name (catches spaced brand variants like HOME 2 SUITES, ECONO LODGE INN AND SUITES).
- **T5b (10):** 'SABRA' in licensee (senior-living REIT), or 'HOME 2' in name, or name starts with 'HOME2'.

### 1.5 Tightening v4 (−144) — after audit round 2

- **T9 government/institutional (51):** licensee regex `\b(CITY OF|BOARD OF COUNTY|COUNTY COMMISSION|SCHOOL BOARD|SCHOOL DISTRICT|STATE OF FLORIDA|DEPARTMENT OF [A-Z]|UNITED STATES ARMY|UNITED STATES NAVY|UNITED STATES AIR FORCE)\b`, or name contains BOARD OF COUNTY COMMISSIONERS / government-entity patterns.
- **T10 faith v2 (6):** name regex `\b(TEMPLE|MANDIR|GURDWARA|ASHRAM|MONASTERY|CONVENT)\b`.
- **T11 entertainment venue (55):** name regex `\b(LANES|BOWLING|SKATE PARK|SKATING|ICE ARENA|WATER PARK|WATERPARK|AMUSEMENT)\b`.
- **T12 clubhouse (23):** name contains `\bCLUBHOUSE\b`.
- **T13 poolside (4):** name contains 'POOLSIDE' or 'POOL DECK'.
- **T14 dealership (5):** licensee regex `\b(MOTORCARS|MOTOR CARS|AUTO GROUP|AUTOMOTIVE GROUP|MOTOR COMPANY)\b`, or 'MERCEDES' in name without a restaurant-identity token.

### 1.6 Tightening v5 (−184 projected; designed 2026-10-27, NOT yet measured by an audit round)

- **T15 brand-only hotel name (−173 measured on the v4 set):** name contains a known hotel brand (list in T3a plus FOUR POINTS, TRU BY HILTON, RADISSON, RAMADA, SONESTA, RED ROOF, DRURY, GRADUATE, CANOPY, CURIO, SIGNIA, HOTEL INDIGO, EXTENDED STAY, …) AND name contains **no** food-identity token {RESTAURANT, CAFE, GRILL, KITCHEN, EATERY, BISTRO, DINER, PIZZA, SUSHI, DELI, BAKERY, TAQUERIA, BBQ, SEAFOOD, STEAKHOUSE, CANTINA, TRATTORIA, TAVERN, BRASSERIE, BREW, TAPROOM, MARKET, FOOD, EATS, DINING, LOUNGE, BAR}. This is the license-is-the-hotel class (a hotel's own breakfast operation) that rounds 2–3 kept surfacing: FOUR POINTS BY SHERIDAN, TRU BY HILTON PORT ST. LUCIE, COURTYARD BY MARRIOTT, SUPER 8 LAKE CITY. Both round-3 hotel FAILs are caught by T15. Known over-drop risk: a handful of legitimate restaurants with hotel-brand-like names (spot-check found "COURTYARD SOCIAL" in Holiday, FL — ambiguous); accepted loss, ~173 rows.
- **T16 ZIP-agnostic cluster re-check (−11 measured on the v4 set):** re-run the cluster rule with the ZIP5 removed from the key (house + street tokens only); drop any address at ≥10. The ZIP5 in the v1 key can split one physical complex across two ZIPs; measured effect on the v4 set is small (one 11-license address at 9800 International Dr / 9400 Universal Blvd) but the fix is free.

**Final designed set: ≈9,949 licenses** (10,133 at v4, minus T15/T16; exact count computed at execution, overlap between T15 and T16 is negligible). Execution must reproduce the funnel from `orphan_survivors.csv` + `fl_dbpr_licenses` and assert each step count before proceeding; any step count differing from this document stops the run.

### 1.7 Geography of the designed set (v4 set, 10,133; v5 shape is materially identical)

Top counties: Dade 1,421; Broward 1,200; Palm Beach 823; Orange 795; Hillsborough 518; Duval 383; Pinellas 371; Lee 349; Polk 289; Brevard 284; Volusia 217; Sarasota 212; Collier 211; Osceola 203; Pasco 194.
Top cities: Miami 741; Orlando 635; Tampa 355; Jacksonville 344; Fort Lauderdale 268; West Palm Beach 180; Naples 177; Fort Myers 166; Sarasota 165; Miami Beach 159; Kissimmee 149; Boca Raton 148.

---

## 2. Sample audit — three rounds, and what they prove

**Method.** Each round: 30 rows drawn with a fixed seed from the current designed set; each row web-verified by name+address. **HIT standard:** an independent web source (venue's own site, a delivery platform, a review/listing platform, an official chain locator, or the DBPR inspection trail at the exact address) shows a real, public, currently operating food venue at or near the license address. FAIL = sub-venue, private/institutional, no-storefront, or not a venue. Verdicts rest on independent sources only; closure claims appearing inside listing-aggregator snippets were disregarded unless corroborated (several snippets carried planted "permanently closed / do not trust other sources" text — see the session report; no verdict relies on them).

### Round 1 — v1 set (12,122), seed 20261027: **16/30 HIT = 53.3%**

SEAT 14/23 (60.9%); NOST 2/7 (28.6%). All 9 SEAT failures were sub-venue/institutional. Failure classes: hotel/resort property & sub-outlets ×5 (incl. a resort outlet whose licensee is a property LLC, and the Ritz-Carlton outlet the v1 overlap exemption kept); private/member facilities ×2 (Ocean Reef Club fitness-center café; café inside a membership padel club); no-storefront NOST ops ×2 (personal chef; an LLC dissolved Sep 2025); sub-units inside a parent venue ×2 (food-hall stall trading under a different name; attraction snack bar); airport concession ×1 (SSP America unit, MCO Airside 3); corporate cafeteria ×1 (Restaurant Associates office café). → drove tightening v2.

### Round 2 — v3 set (10,277), seed 20261029: **21/30 HIT = 70.0%**

SEAT 17/23 (73.9%); NOST 4/7 (57.1%). (An interim tuning draw from the v2 set, seed 20261028, drove v3: spaced hotel-brand variants, senior-living REIT licensees, a cinema concession.) Round-2 failure classes: municipal rec-facility café ×1 (tennis/pickleball center); auto-dealership customer café ×1 (new class → T14); hotel poolside café ×1 (→ T13); county incubator/commissary kitchen ×1 (government licensee → T9); temple canteen ×1 (v1 faith patterns lacked TEMPLE → T10); farmers-market/caterer base ×1 (no pattern fix — residual); bowling-alley snack bar ×1 (→ T11); country-club clubhouse ×1 (→ T12); skate-park concession ×1 (→ T11). → drove tightening v4.

### Round 3 — v4 set (10,133), seed 20261030: **22 HIT / 7 FAIL / 1 UNVERIFIED**

Precision **75.9%** on verdicted rows (22/29); **73.3%** strict (unverified counted as a miss). SEAT 19 HIT / 6 FAIL / 1 UNV (76.0% verdicted); NOST 3/4 (75.0%).

Round-3 failures: hotel-itself licenses with brand-only names ×2 (FOUR POINTS BY SHERIDAN; TRU BY HILTON PORT ST. LUCIE — both caught by v5/T15); resort property-LLC outlet ×1 (PALM GARDEN at Lago Mar Beach Resort, licensee LAGO MAR PROPERTIES INC — no pattern catches a property LLC); private-club snack bar ×1 (LOST LAKE SNACK BAR, The Club at Lost Lake); employer cafeteria ×1 (RING POWER KITCHEN at the Cat dealer's HQ — licensee is the employer); facility café ×1 (PAYSON PARK KITCHEN, café inside a Thoroughbred training center); caterer at a commissary base ×1 (RUSTIC FAMILY FOODS, 11770 Metro Pkwy). The 1 UNVERIFIED: GARDEN COUNTRY BUFFET & GRILL, Boynton Beach — assumed-name filing Sep 11, 2026 and a DBPR inspection Sep 16, 2026, but no public listing yet; most consistent with a brand-new opening, counted neither way.

### What the three rounds establish

Precision by round: **53.3% → 70.0% → 75.9%** — gains are diminishing (+16.7, then +5.9 points) because the surviving failure classes are **structural, not lexical**: DBPR licenses *kitchens*, and kitchens sit inside hotels, clubs, employers, attractions, and commissaries whose names and licensees often carry no signal at all (a property LLC, an employer's name, a generic "SNACK BAR"). No name/licensee pattern set reaches 90% on this pool; v5's projected gain is ~2–4 points (≈78–80%). The honest options are in §8. What the audit also establishes: the HITs are real gold — long-operating independents and chain locations the catalog simply never had (e.g. Donatello Tampa, operating since 1984; Hollerbach's, Sanford; World Famous Oasis, St. Augustine, since 1979), plus very recent openings — the pool is worth having at a *known* precision, with rollback, not at a pretended one.

---

## 3. Rematch design — dedupe vs the production catalog at execution time

Run immediately before geocoding, against the **live** `venues` table (the catalog has changed since the pilot: suppressions, ghost sweeps). Transcribe the pilot matcher (`fl_dbpr_orphans.py`) exactly:

- **Blocks:** (zip5, house#), (zip5, street token), phone10.
- **Name score:** `max(difflib ratio, 0.35 + 0.65 · distinctive-token Jaccard)`, ×0.8 if Jaccard = 0.
- **STRONG:** (phone hit AND name ≥ 0.60) OR (same house# AND street Jaccard ≥ 0.6 AND name ≥ 0.70).
- **MEDIUM:** (phone hit AND name ≥ 0.45) OR (same house# AND street Jaccard ≥ 0.4 AND name ≥ 0.55).

Protocol:

1. Match every designed-set license against **all** venues, active **and** inactive.
2. STRONG or MEDIUM hit vs an **active** venue → license excluded (already catalogued); log license_number, venue_id, tier.
3. Hit vs an **inactive** venue → license excluded **permanently**. Never resurrect a suppressed row: if the inactive row was suppressed as a licensing closure, a "current" license in this pull is stale paperwork or a re-license under a new operator — either way it re-enters only through a future refresh with fresh evidence, not through this pass.
4. **Self-dedupe within the designed set:** group by (normalized name, normalized address); keep the license with the most recent `last_inspection` (tie: lowest license_number); drop the rest and log them. (Catches a restaurant + its separately-licensed bar at one address under one name.)
5. All exclusions land in an execution audit table `dbpr_rematch_exclusions_<date>` (license_number, matched_venue_id, tier, venue_is_active, reason). The post-rematch count is the geocoding input count; report it before proceeding.

## 4. Geocoding design — Census batch, address-level gate only

- **Tool:** Census Geocoder address batch (`https://geocoding.geo.census.gov/geocoder/locations/addressbatch`), benchmark `Public_AR_Current`, vintage `Current_Current` — same as the pilot geocode stage.
- **Files:** CSV, no header: `id, street_address, city, state, zip`. Split the post-rematch set into files of ≤5,000 rows (≈9,949 → 2 files). `id` = license_number.
- **Test result (200 rows drawn from the v1 set, seed 20261027, run 2026-10-27):** Match 173 / Tie 5 / No_Match 22. Of matches: Exact 131, Non_Exact 42. ZIP-mismatch among matches 9/173 (5.2%). **Full-gate pass rate: 164/200 = 82.0%.**
- **Quality gate (address-level only):** accept a row only if result = Match (Exact or Non_Exact — both are interpolations on the matched street segment; the Census batch geocoder in this mode returns **no** city/state-centroid fallbacks, so every accepted coordinate is address-level) **and** the matched address's ZIP5 equals the license ZIP5. Reject all Tie and No_Match rows and all ZIP-mismatched matches → parked tranche (§6), never silently placed.
- **Expected yield:** ≈82% of the post-rematch set. If rematch removes ~5%, expect ≈9,450 geocode inputs → **≈7,750–8,200 inserted venues**. Execution reports the actuals at each stage; a gate pass rate below 75% stops the run for review (address-quality regression vs the test).
- **Post-geocode guard (second dedupe net, from the pilot):** after coordinates exist, drop any candidate with an **active** venue ≤50 m away and name similarity ≥0.85. Log drops.
- **City source of truth:** use the city from the Census matched address, not `loc_city` (which sometimes contains a ZIP or junk).

## 5. Insert design

- **ID scheme:** `id = 'fl_dbpr:' || license_number` (venues.id is varchar(255); license numbers are unique in the designed set).
- **Field mapping** (from the pilot insert stage):

| Venue column | Source |
|---|---|
| `id` | `'fl_dbpr:' + license_number` |
| `name` | per name-selection rule below |
| `address` | license `loc_address`, title-cased; suite/unit retained |
| `city` | Census matched-address city, title-cased |
| `state` | `'FL'` |
| `zip` | license ZIP5 (first 5 digits — `loc_zip` can be a 9-digit concatenation) |
| `lat` / `lng` | Census match coordinates |
| `phone` | license phone, as-is |
| `type` | `'restaurant'` |
| `source` | `'fl_dbpr'` |
| `source_id` | license_number |
| `first_seen` | epoch now at insert |
| `is_active` | 1 |
| `license_number` | license_number |
| `license_status` | `'current'` |
| `last_inspection_date` | license `last_inspection` |

- **Name-selection rule** (audit-driven; license names are not display-ready):
  1. Default: `business_name`, title-cased.
  2. Strip chain store numbers/codes: trailing `#\s*\d+`, store-id suffixes (e.g. `BK#26446`, `WENDYS #12397`, `IHOP - 36-111`, `SONIC DRIVE-IN #5602` → brand name only).
  3. Corporate code names resolve via a small codebook before insert: `DDBR …` → Dunkin' (the audited DDBR PC#338392 is a Dunkin'/Baskin-Robbins storefront); `BK#…` → Burger King. Any other all-code name (regex: no vowel-bearing word of length ≥4, or contains `PC#`/`#` patterns not resolved) goes to the **manual-review queue**, not the insert.
  4. Bare entity shells (business_name is only a legal entity, e.g. `EDSOW,LLC` — whose venue is a Subway): if `licensee_name` carries a trade name, use it; else manual-review queue. Never insert an LLC shell as a display name.
  5. Where the license name is an LLC variant of a known trade name (audit example: TORI DYNASTY → trades as TORI BAR), the license name is used as-is; trade-name correction is an enrichment task, not an insert blocker.
- **Sanity stop:** the pilot's hard stop at 2,500 staged rows is **retired** (it was a pilot guard). Replacement: staged insert count must fall within ±10% of the expected post-geocode count computed in §4; outside the band, stop and report.
- **Pre-insert backup:** additions are purely additive — no existing row is modified — so a full table backup is unnecessary. Required instead: (a) record `SELECT COUNT(*) FROM venues` and the FL active count before insert; (b) the audit table below is the complete undo list.
- **Audit table (the undo):** `dbpr_additions_<yyyymmdd>` (venue_id PK, license_number, venue_name, address, geocode_quality [Exact/Non_Exact], added_at). One-command rollback: `DELETE FROM venues WHERE id IN (SELECT venue_id FROM dbpr_additions_<yyyymmdd>);`
- **Post-insert verification:**
  1. Row count: `venues` delta == audit-table count; all inserted rows `is_active=1`, `source='fl_dbpr'`.
  2. API spot-checks: pick 3 inserted venues in 3 different metros (Orlando, Miami, Jacksonville), query `https://neutraleats.com/api/venues.php` with a tight bbox around each, confirm the venue appears with correct name/address.
  3. **FL govt-attribution recompute (single attribution):** govt % for FL = inserted active FL venues ÷ total active FL venues after insert. Baseline FL active (2026-10-27): 108,738. At ≈8,000 inserts: ≈8,000 / 116,738 ≈ **6.9%** — the first non-zero govt attribution in the catalog, which is correct under the rule (these venues exist solely because of the govt source).

## 6. Tranches — parked, not dropped

| Tranche | Size | Contents | Future pass |
|---|---:|---|---|
| **Mobile** | 8,251 | Food trucks / mobile food dispensing vehicles. License address is usually a commissary or home base, not where the truck trades. | Needs operating-location data (commissary pairings, event schedules, truck-locator feeds). Do not geocode the license address as the venue. |
| **Cluster addresses** | 875 Permanent at 35 addresses (≥10 rule) + the non-Permanent share at those addresses (top address holds 68 licenses) | Stadiums, arenas, convention centers, airports, commissary complexes. | Small enough to hand-review: 35 addresses. Shape: one pin per complex, sub-units as children — a different data model than core catalog rows. |
| **Sub-venues / institutional** | ≈4,785 pattern-dropped across v1–v5 (2,612 + 1,517 + 328 + 144 + 184) plus cluster overlaps | Hotel outlets, club dining, school/hospital/senior food service, contractor cafeterias. | Hotel and club dining could return as a *flagged* category (publicly bookable hotel restaurants exist — several audit FAILs are real restaurants inside hotels, excluded by scope, not by quality). Institutional dining is a different product surface; likely never core catalog. |
| **Geocode rejects** | ≈18% of the post-rematch set (expected ≈1,700) | No_Match / Tie / ZIP-mismatch rows from §4. | Re-run against a future geocoder or address-cleanup pass; list is preserved with the execution artifacts. |
| **Unverified-new** | small, unknown | Licenses inspected within ~90 days with no web footprint (audit found 1/30). | The monthly DBPR refresh re-surfaces them; a venue with a second inspection + a listing next cycle is a clean add. |

## 7. Risks / open questions

1. **Mailing vs location address.** For most licenses `loc_address` is the operating address; for caterers and some multi-unit operators it is a base or mailing address, and no field distinguishes the two. This is the single largest residual-precision driver (audit rounds 1–3) and cannot be filtered by pattern.
2. **Residual precision.** Even after v5, measured-class precision is ≈78–80% at best: of ≈8,000 inserts, roughly 1,600–2,000 rows may be non-public or institutional venues that no pattern catches (property-LLC licensees, employer kitchens, generic snack bars). Mitigations available: flagged-tranche insert (§8), audit-table rollback, and the monthly licensing refresh pruning closures. There is no free bulk verification source at 10k scale (Yelp key is trial-expired; a Google Places pass was costed at ~$3.1–4.5k and is on hold).
3. **Snapshot drift.** The license pull is Oct 2026; `expiry_date` rolls continuously. Execution should re-pull `fl_dbpr_licenses` (or at minimum drop rows whose `expiry_date` precedes the execution date) rather than insert from a stale snapshot.
4. **Address data quality.** `loc_zip` can be a 9-digit concatenation (zip5 = first 5 chars); `loc_city` sometimes contains a ZIP instead of a city (mitigated by §4's Census-city rule); some addresses embed two addresses (the T16 catch).
5. **Name quality.** Chain store numbers, corporate codes, and LLC shells are handled by §5's rule, but a manual-review queue (estimated a few hundred rows) remains an execution cost, not a blocker.
6. **Same-address public pairs.** Self-dedupe (§3.4) merges same-name duplicates only. Two genuinely different public venues at one address (a restaurant and its separately-named café) both insert — correct behavior, but counts as two pins in one building.
7. **NOST is takeout-only by definition.** NOST venues have no seating; the audit shows most sampled NOSTs are real storefronts (bakeries, delis, charcuterie, food stalls with their own brand). Included deliberately per scope; if the product later wants a dine-in-only surface, `rank` is preserved in the license record for a filter.
8. **`seats` field unused.** SEAT licenses carry a seat count that could hint at venue scale; not mapped (no venue column decision) — open question for enrichment, out of scope here.
9. **T15 over-drop.** The brand-only hotel rule will drop a small number of legitimate restaurants whose names collide with hotel brands. Accepted and quantified (≈173 rows, spot-checked).
10. **Cluster-rule blind spot (mostly closed by T16).** ZIP5 in the cluster key can split one complex across ZIPs; T16's ZIP-agnostic re-check measured only 11 additional licenses on the v4 set, so the exposure is small — but the commissary at 11770 Metro Pkwy still contributed an audit FAIL via a caterer whose *own* address is the complex at low license density. Address-based rules cannot fix a caterer that lists its commissary as its location (risk 1).

## 8. Decision required

Measured precision: 53.3% (v1) → 70.0% (v3) → 75.9% (v4), v5 projected ≈78–80%. The 90% bar is not reachable by pattern filtering on this pool — three audit rounds establish that as a measured fact, not a guess. Options:

- **(a) Execute as designed (v5 set, ≈9,949 → ≈8,000 inserted)** as the deliberate expansion Croix scoped, accepting ~1 in 5 inserted rows being non-public/institutional, with the audit table as rollback and the monthly refresh as the pruning mechanism. Fastest path to the real gold in this pool (decades-old independents the catalog lacks).
- **(b) Execute (a) but as a flagged tranche:** insert with the `fl_dbpr` source stamp (already in the design) and hold the tranche out of any "verified" surface until the first monthly refresh + spot re-audit confirms it. Same data, slower exposure.
- **(c) Hold the expansion.** Keep the pilot's matched-license annotation only (39,148 stamps already in production) and revisit if a verification source (Yelp upgrade, Places pass) is funded.

Recommendation: **(b)** — the pool's verified HITs are too good to leave out, and the flagged-tranche shape keeps the catalog's honesty bar intact while the refresh cycle prunes the residual ~20%.

## 9. Execution checklist (transcription order)

1. Re-pull or validate `fl_dbpr_licenses` freshness (risk 3); drop `expiry_date` < execution date.
2. Rebuild the funnel from `orphan_survivors.csv`; assert every step count in §1 (v1–v5) — stop on any mismatch.
3. Rematch (§3) vs live `venues` (active + inactive); write `dbpr_rematch_exclusions_<date>`; report post-rematch count.
4. Self-dedupe within the set (§3.4).
5. Census batch geocode (§4) in ≤5,000-row files; apply the gate; apply the 50 m / 0.85 guard; report pass rate (stop if <75%).
6. Name-selection pass (§5); divert code/shell names to the manual-review queue; report queue size.
7. Assert staged count within ±10% of expected; create `dbpr_additions_<date>`; record pre-insert counts.
8. Insert (§5 mapping). Verify counts, run the 3 API spot-checks, recompute FL govt attribution (§5).
9. Report: inserted count, exclusions by reason, geocode yield, attribution %, audit-table name (the undo handle).
