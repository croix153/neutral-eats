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

- **NY (audit-only, re-run DONE):** first crosswalk matched
  36,130 but produced 8,343 closure candidates — not credible:
  the NYS inactive file is a 20-year graveyard and venues matched
  dead predecessor records at their own addresses. Fix shipped:
  live licenses get +0.06 in the greedy assignment, and the
  live-successor gate demotes any closure candidate whose
  (zip, house number) has a live license. Re-run: 36,125 matched
  (live matches 26,935 → 27,029), **closure candidates 8,343 →
  5,767**, watchlist 3,329 (2,480 gate demotions). Still too
  many to close on one signal — the residue is venues whose
  only licensing trace is a dead record (concentrated in
  1999–2006 records; likely a mix of genuine POI ghosts and
  unmatched live permits). Next step before any NY apply:
  sample-verify ~30 candidates against independent sources to
  estimate precision. NO production writes.
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

## NY precision sample-check (DONE 2026-10-26 night)

12 closure candidates hand-verified against independent sources
(current reviews, delivery platforms, business sites):

- **NYS inactive signal: 2 of 9 correct (22% precision) —
  DISQUALIFIED as a closure source.** False closures: Ole
  Westside Tavern (Elmira — alive; reopened under a new
  operation the matcher missed), Koku Japanese (Armonk —
  thriving), Pennocks Ice Cream (Sackets Harbor — reviewed
  Jun 2026), Paula's Airport Café (Saranac Lake — café
  operating, likely new operator), All That Java (Kingston —
  DoorDash-active), La Bamba (Freeport — open, current hours),
  Garden City Pub (name-ghost: address alive as "Repeal" under
  the same corporation). True closures: Pizza Connection
  (Mamaroneck), Enrico's Pastry Shop (Hartsdale). Root causes:
  (1) county-delegated inspection jurisdictions (Westchester,
  Nassau, others) — state "inactive" often means "the county
  runs it now," not closed; (2) re-permits/rebrands under new
  operation IDs that name+address matching cannot see.
  **Recommendation: demote the entire NYS closure class to
  watchlist permanently; NYS inactive data is stamp-only
  (license metadata), never a closure signal.**
- **NYC DOHMH signal: 2 of 3 correct.** Uptown Slices (Harlem)
  and X Pizza (190 Front St) genuinely closed (DOHMH closure
  actions 2024). False: Taste & Flavor Bakery Cafe (Brooklyn —
  operating, DoorDash-active; matched record was not its live
  operation). Stronger than NYS but a 1-in-3 live-business
  false positive on a small sample is still not apply-grade
  alone. **Recommendation: NYC closures require corroboration
  (DOHMH closure as the latest action for that CAMIS + no live
  successor at the address + ideally a second signal) and a
  larger sample before any apply. Audit-only until then.**
- KC and Boston unchanged: audit-only, awaiting Croix's review
  alongside this verdict. NO production writes anywhere in NY.

## Policy update + one-time closure backfill (2026-10-27)

**Policy (Croix, 2026-10-27): closures no longer require licensing
corroboration.** Overture `operating_status = 'permanently_closed'`
is trusted directly as closure authority — sufficient on its own to
suppress a venue. Licensing remains the higher authority where it
speaks, and the gap layer where Overture is silent, but an Overture
closure signal no longer waits for a second source.

**One-time backfill (fix-plan step 5, closure half) EXECUTED
2026-10-27:**

- Source: the local release capture
  `/root/overture-work/gate2/us_raw.parquet` (release 2026-10-21.0,
  US). Staging still carries no `operating_status`, so the pull
  re-read the release, as this doc prescribed. Pull: **638,268**
  `permanently_closed` feature ids; **259** `temporarily_closed`.
  Loaded to `overture_closed_ids_20261027` /
  `overture_tempclosed_ids_20261027`.
- Match against active production venues: **0** — by
  `id = CONCAT('overture:', feature_id)` and by this doc's step-5
  `source_id` join alike (the two mappings coincide on this
  catalog). Structural, exactly as predicted above:
  `permanently_closed` features were excluded at extract, so they
  were never staged, loaded, or merge-matched; closed rows only
  arrive with the next fixed refresh. Cross-checks that the joins
  are valid: **4** active venues match the `temporarily_closed`
  set (that class was never excluded — Starbucks, San Diego CA;
  Fresh Kitchen Winter Park, FL; Mountain Mike's Pizza, Mansfield
  TX; Starbucks Coffee Company, Flagstaff AZ; counted, NOT
  suppressed), and 5 sampled production features read `open` in
  the release.
- Apply set was empty: backup `venues_backup_20261027_ovtclosed`
  (0 rows) and audit `overture_closure_suppressions_20261027`
  (0 rows) created; no production rows changed; active catalog
  unchanged at 1,550,530.
- Forward effect: under the fixed pipeline (implemented 2026-10-26)
  the Nov 3 refresh stages closed rows and the merge sets
  `is_active = 0` iff `permanently_closed` — under the new policy
  that Overture signal applies directly, no licensing
  corroboration needed. The open/unknown `operating_status`
  relabeling of current rows still rides the Nov 3 refresh.
