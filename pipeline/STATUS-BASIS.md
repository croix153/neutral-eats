# Status basis — design + fix plan (2026-10-26)

Decision (Croix): Overture `operating_status` is the dataset's basis
layer for closure status; per-state licensing feeds (DBPR model) are
the gap-closure layer. Authority order: licensing > Overture > unknown.

## What is broken today (verified 2026-10-26)

- The Overture extract SELECTs `operating_status` (extract_overture.py
  lines 165/487) but only to EXCLUDE `permanently_closed` rows
  (lines 206/523/547). The staging table schema
  (`venues_overture_staging_us`, 1,550,844 rows) has NO
  `operating_status` column — the value is read and discarded.
- The merge hardcodes it back: merge_overture.py line 447 sets
  `"operating_status": "open"` for every Overture-only row, and
  matched rows inherit production's value (also "open").
- Result: all 1,551,198 production rows read `operating_status =
  'open'`, including the ~15.7% whose source status was NULL
  (unknown). Confirmed-open and unknown are indistinguishable.
- Because staging dropped the column, NO SQL-only backfill exists.
  Restoring truth requires re-reading release 2026-10-21.0 (an
  id+status-only pull is light) or waiting for the fixed refresh.

## Coverage reality (Florida food slice of the raw pool, measured)

open 62,684 (78.4%) / unknown NULL 12,591 (15.7%) /
permanently_closed 4,685 (5.9%) / temporarily_closed 1.

## Fix plan (refresh pipeline)

1. extract_overture.py: staging DDL gains `operating_status
   VARCHAR(20)` in both CREATE TABLE blocks (~lines 291, 666);
   inserts carry the value. DROP the permanently_closed exclusion
   so closed rows are staged (the merge, not the extract, decides
   suppression).
2. merge_overture.py: STAGING_COLS gains `operating_status`.
   - Overture-only rows: `operating_status` = staging value
     (NULL stays NULL = unknown); `is_active` = 0 when
     permanently_closed, else 1.
   - Matched rows: fresh staging status wins over production's.
   - Legacy-only rows: keep production values untouched.
3. monthly_refresh.py gates: G-counts must be computed on ACTIVE
   rows (closed rows add ~5% to table size); verify gate
   definitions before the first fixed run.
4. venues.php already filters `is_active = 1`, so retained closed
   rows are suppressed with no API change. (The enrichment
   `is_closed` suppression stays as the licensing/API-source
   overlay.)
5. One-time backfill option: id+operating_status pull from
   2026-10-21.0 for all states, UPDATE venues via source_id join,
   restoring open/unknown truth for the current dataset without a
   full refresh. Closed ROWS only arrive with the next fixed
   refresh (they were never loaded).

## Implementation status (2026-10-26 evening)

- Fix-plan steps 1–2 IMPLEMENTED in extract_overture.py +
  merge_overture.py (committed same evening):
  - Both staging DDLs gain `operating_status varchar(50)`; both
    extract SELECTs append it as the LAST TSV column; both
    permanently_closed exclusions dropped (funnel key renamed
    food_open_named -> food_named).
  - Positional landmine found + fixed: the nationwide per-state
    loader grouped rows by split("\t")[-1] (the last column =
    batch_state). It now indexes column 19 explicitly
    (split[18]), since operating_status trails batch_state.
  - Merge: STAGING_COLS gains operating_status (appended last —
    dedupe's field-count check and fixed indexes stay valid).
    Overture-only rows carry the staging value (NULL stays NULL)
    and is_active=0 iff permanently_closed. Matched rows: staging
    status wins when asserted; permanently_closed forces
    is_active=0, but the merge NEVER forces is_active back to 1,
    so a licensing suppression on the production row survives
    later merges. Prod-only rows untouched.
- Step 3 (gates): verified WITHOUT changes — monthly_refresh G3
  and venue_monitor already count is_active=1 rows; G2's merged/
  live band [0.95, 1.15] absorbs the ~+5-6% table growth from
  retained closed rows.
- Step 5 (one-time backfill) still open — Croix's call: run the
  id+status re-pull from 2026-10-21.0 now, or let the Nov 3
  refresh restore truth.

## FL DBPR pilot results (2026-10-26)

70,064 licenses staged (fl_dbpr_licenses); matcher produced
39,148 matches over 109,119 active FL venues (35.9%): STRONG
31,667 / MEDIUM 7,481; 37,704 matched to a Current ('20')
license. Watchlist (recent delinquents): 1,374.

CLOSURE-RULE CORRECTION: the implemented rule (status 45 with
expiry <= 2025-12-31 AND last inspection <= 2025-12-31 or none)
flagged 70 — but ALL 64 status-45 candidates were inspected in
2025 and 61/64 carry 2025 expiries: that is the late-renewal
cohort, not closures. Under a strict rule (status 46 any tier,
OR expiry <= 2024-12-31, OR last inspection <= 2024-12-31 or
none) only 9 survive: 6 voluntary relinquishments + 3 stale
delinquents. The 61 were reclassified to the watchlist.

APPLIED 2026-10-26 on Croix's go — he overrode the STRONG-only
recommendation ("stamp STRONG + MEDIUM too"): all 39,148
matches stamped; exactly the strict-9 closed (the applied rule
adds "no sign of life in 2026" — 13 of a first-pass 23 were
inspected in 2026, i.e. operating on stale licenses); backup
venues_backup_20261026_fl; watchlist now 1,435; verified
through the public API. MEDIUM caution stands as a known
limitation of the stamp (successor-tenant pairings like
Champps Tampa <-> CEVICHE TAPAS BAR can carry the successor's
license number).

## Licensing overlay (gap layer)

Per-state crosswalks (pilot: pipeline/licensing/fl_dbpr_*.py)
populate venues.license_number / license_status /
last_inspection_date and may set operating_status =
'permanently_closed' + is_active = 0 on stacked evidence only
(deliberate: regulator data outranks Overture, but a single weak
signal never closes a venue). Every licensing decision is kept in
a per-source audit table (fl_dbpr_matches) before it is applied.

## Rollout status (2026-10-26 night)

- **NY (audit-only, re-running):** first crosswalk matched
  36,130 but produced 8,343 closure candidates — not credible:
  the NYS inactive file is a 20-year graveyard and venues matched
  dead predecessor records at their own addresses. Fix shipped:
  live licenses get +0.06 in the greedy assignment, and the
  live-successor gate demotes any closure candidate whose
  (zip, house number) has a live license. Re-run in progress;
  NO production writes until the gated numbers are reviewed.
- **King County (audit-only, DONE):** 12,295 licenses staged
  (only 7 carry the closed flag on their latest inspection —
  the flag is precise but rare); 5,180 matched (STRONG 4,112),
  5,176 to live licenses, **0 closure candidates**, 4 watchlist.
- **Boston (audit-only, DONE):** 4,107 licenses staged (1,582
  not in the active companion file); 931 matched (STRONG 714),
  **117 closure candidates** (samples eyeball-verified:
  Erbaluce, Turtle Swamp Brewing — both genuinely closed),
  129 watchlist of which **85 were demoted by the successor
  gate**. Footnote: many Boston rows share batch inspection
  dates (2022-03-15 / 2022-09-14 recur) — the stacked signal
  is Inactive status + expired license + absence from the
  active file, not the date alone.
