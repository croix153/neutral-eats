# FL DBPR Expansion Pass — Execution Report

**Date:** 2026-10-27. **Design:** `DBPR-EXPANSION-DESIGN.md`. **Decision executed:** §8 option **(b) — flagged tranche** (Croix, 2026-10-27 ~12:57 ET). Additions are stamped `source='fl_dbpr'` and are removable as a set via the audit table.
**Executor script:** `pipeline/licensing/fl_dbpr_expansion.py` (stages: funnel / rematch / geocode_local / loadstage / names / insert / verify).

## Result

**7,556 venues inserted.** FL active venues: **108,738 → 116,294** (Δ +7,556, exactly the insert count). Total venues: 1,551,198 → 1,558,754. All 7,556 rows `is_active=1`, `operating_status='open'`, `license_status='current'`, with license_number and last_inspection_date stamped.

**FL govt attribution (single-attribution rule): 7,556 ÷ 116,294 = 6.5%** — the catalog's first non-zero govt share, correct under the rule because these venues exist solely from the govt source. (Design projected ≈6.9% at ≈8,000 inserts.)

**Undo:** `DELETE FROM venues WHERE id IN (SELECT venue_id FROM dbpr_additions_20261027);` — the audit table holds all 7,556 (venue_id, license_number, venue_name, address, geocode_quality = Exact/Non_Exact, added_at). Insert mix: SEAT 6,102 / NOST 1,454; geocode quality Exact 6,002 / Non_Exact 1,964 (of the 7,966 staged).

## Funnel — every design count reproduced

The funnel was rebuilt from `orphan_survivors.csv` with per-rule assertions against the design doc; **every asserted count matched exactly**, including all 15 v1 denylist classes, all v2/v3/v4 sub-rules, and set-equality with the design pass's own v4 file.

| Stage | Count |
|---|---:|
| Pilot survivors | 23,860 |
| − Mobile (type ≠ 2010) | 15,609 (SEAT 12,220 / NOST 3,389) |
| − Cluster ≥10 (35 addresses) | 14,734 |
| − Denylist v1 | 12,122 |
| − Tightening v2 | 10,605 |
| − Tightening v3 | 10,277 |
| − Tightening v4 | 10,133 |
| − v5: T15 brand-only hotel names | −180 (design estimate 173; the rule was labeled a projection — +7) |
| − v5: T16 ZIP-agnostic cluster re-check | −11 (exact; the one 11-license dual-address at 9800 International Dr, Orlando) |
| **Designed set** | **9,942** (design ≈9,949) |
| − Freshness (§9.1: expiry_date < 2026-10-27) | −0 (earliest expiry in set: 2026-10-31) |
| − Rematch vs live catalog | −0 (see Deviations) |
| − Self-dedupe (§3.4) | −27 |
| **Geocode input** | **9,915** |
| Census gate: matched + ZIP-verified | 8,253 (**83.2%** pass; design test 82.0%; stop line 75%) |
| − ZIP-mismatch rejects | 386 |
| − No_Match / Tie rejects | 1,276 |
| − 50 m / name-sim ≥0.85 guard (§4) | 287 |
| **Staged** | **7,966** |
| − Name-pass manual-review queue (§5) | 410 (entity shell 289 / code name 105 / unresolved # 13 / unresolved PC# 3) |
| **Inserted** | **7,556** |

Sanity bands: §5 band from post-rematch expectation (9,915 × 0.82 = 8,130 ±10%) = [7,317, 8,943] ✓; task band [7,200, 8,800] ✓. 7,556 is inside both. The naive expectation overshoots because §4's yield math doesn't subtract the guard (287) or the name queue (410).

Parked tranches preserved: geocode rejects (1,949) in `geocode_rejects.csv`; name-review queue (410) in `name_review_queue.csv`; rematch exclusions in table `dbpr_rematch_exclusions_20261027` (27 self-dedupe rows).

## Verification (live API, not just SQL)

`verify` stage against `https://neutraleats.com/api/venues.php`: **ALL OK.**

- **Donatello (Tampa)** — findable as the pre-existing "Donatello Restaurant" row (see Deviations for its license's duplicate row).
- **Hollerbach's (Sanford)** — inserted row `fl_dbpr:SEA6903415` ("Hollerbach's German Restaurant", 205 E 1st St) found (see Deviations).
- **World Famous Oasis (St. Augustine)** — **not inserted, correctly**: the §4 guard dropped it because production already carries it as `overture:878a5c85…` "World Famous Oasis Restaurant", 4000 A1A S, St Augustine Beach; findable via that row. (The rematch missed it on the "A 1A" vs "A1A" street-token split — street Jaccard 0.25 — and the guard caught it downstream. The layered nets worked.)
- 10 random additions (seed 20261027) name-searched in their own areas: **10/10 found**.
- Metro checks (Orlando / Miami / Jacksonville, nearest addition to each center): **3/3 found**.
- SQL: venues Δ = audit rows = FL active Δ = 7,556. FL active count via API is not directly countable (bbox + 500-cap), so the count delta is SQL-verified and presence is API-verified.

## Deviations and repairs (all disclosed; no design gate was changed)

1. **Rematch excluded 0, not the ~5% the design sketched.** Cause, verified: the designed set descends from the pilot's survivors, which by construction already passed this exact matcher against this catalog on 2026-10-27 (funnel excluded 1,259 then); since then the catalog has only *lost* venues (suppressions/sweeps), which cannot create new matches. The design's ~5% was explicitly conditional ("*if* rematch removes ~5%"). Consequence inside the accepted precision envelope: two same-business duplicate pairs (next item). The post-rematch count was reported by the stage before proceeding, per §3.
2. **Two name-variant duplicates the design's nets pass by construction.** (a) **Donatellos** (`fl_dbpr:SEA3904151`, 232 N Dale Mabry, Tampa) inserted ~29 m from the existing "Donatello Restaurant": the pilot name score is 0.533 vs the MEDIUM floor 0.55 (the DONATELLOS/DONATELLO plural gap zeroes the token Jaccard), and the guard's 0.85 similarity is not met (~0.6). (b) **Hollerbach's German Restaurant** inserted at its real address while OSM carries the same business as "Hollerbach's Willow Tree Cafe" (guard sim ~0.55). Both rows are fl_dbpr-flagged and audit-table removable; the monthly refresh + spot re-audit is the designed pruning path for this residual class.
3. **Census geocoding ran from the VM, not the host.** The Census batch endpoint's WAF rejects the croix.ai host IP (HTML "Request Rejected", HTTP 200, zero parseable rows — the first host run's 0.0% "pass rate" was this artifact, and the <75% stop correctly caught it). The identical request succeeds from the VM. Same endpoint, benchmark, vintage, gate and thresholds; only the egress point moved. The guard universe was pulled from the host DB over SSH in one query.
4. **Two latent pilot-parser defects found and fixed** (the pilot geocode stage had never executed): (a) Census returns No_Match/Tie rows with exactly **3 fields**; the transcription's `<8 fields` skip silently dropped every reject — proven against raw responses (300-row diagnostic: 272 Match / 26 No_Match / 2 Tie). (b) The ZIP check took the **first** 5-digit token of the matched address as its ZIP, falsely rejecting every 5-digit house number (49 of 272 matches in the diagnostic); the design's gate is the matched address's ZIP5 — its trailing ZIP component (genuine mismatch rate 4.8%, corroborating the design test's 5.2%). With the parser implementing §4 as written, the full run's gate pass was 83.2% vs the test's 82.0%.
5. **City field corrected post-insert.** My `census_city` took `parts[-2]` of the 4-part Census form ("STREET, CITY, FL, ZIP") and stored "Fl" as the city on all 7,556 rows. Fixed in the script and repaired the same day with a one-time pass over exactly the inserted set (audit-table ids): 0 rows remain wrong, and the city distribution now matches the design geography (Miami 556, Orlando 496, Jacksonville 302, Tampa 285, Fort Lauderdale 198, West Palm Beach 146…). Audit-table address strings and the stage table's census_city were corrected in the same pass.
6. **Missing-date normalization.** 82 licenses carry the literal string `NULL` as last_inspection in the source extract; normalized to SQL NULL rather than inserted as text.
7. **Name-pass residuals (design-literal).** 294 inserted names keep bare trailing store numbers (the "WENDYS 8452" class): §5's strip rule is anchored on `#`/dash codes, so they stand as licensed. The 410-row queue includes a few real venues caught by §5's literal code-name test (e.g. "KFC", "Hen and the Hog") — they await manual review by design, and are preserved in `name_review_queue.csv`, not dropped from the universe. Two mechanical encoding repairs were applied to display names (non-breaking space → space; the extract's `¿`-for-apostrophe mojibake → `'`, e.g. HOLLERBACH¿S → Hollerbach's).
8. **T15 measured 180 vs the design's 173 estimate** (+7 rows). The design's funnel table labels v5 "designed, unmeasured"/projected; the brand list in §1.6 is explicitly open-ended ("…"). Final set 9,942 vs ≈9,949 — immaterial against every gate.

## State left behind

- Tables: `dbpr_additions_20261027` (undo list), `dbpr_rematch_exclusions_20261027`, `dbpr_expansion_stage_20261027`.
- Host workdir: `/root/licensing/expansion/` (designed_set_final.csv, post_rematch.csv, staged_final.csv, insert_ready.csv, logs).
- Monthly refresh cron untouched; no existing venue was modified (the only UPDATEs ran against the inserted fl_dbpr set itself, item 5).
