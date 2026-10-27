# Successor suppression sweep — APPLIED 2026-10-27

Applied the v2 census + v3 containment-guard successor set to
production, after the user-approved ambiguity guards
("Guard the ambiguous classes, then apply", 2026-10-27).
User policy applied throughout: delivery-only / virtual brands among
candidates are acceptable suppressions, not errors.

## Funnel

| Stage | Venues |
|---|---|
| v3 post-containment-guard set | 7,120 (5,142 addresses) |
| Guard (a) multi-brand survivor (comma in survivor name) | −16 |
| Guard (b) generic-only survivor↔license agreement | −11 |
| Already inactive / missing in production at apply time | 0 |
| **Applied** | **7,093** |

Guard (b) uses the pilot's `norm_text`/`GENERIC`
(`pipeline/licensing/fl_dbpr_match.py`) plus GRILLE as a generic
variant of GRILL — both distinctive sets must share a token
(exact, or substring for tokens ≥ 3 chars) or the row is excluded.
Archetypes verified by name before applying:
Taqueria Gonzalez excluded by (a) — survivor "Wd Foods Of
Hillsborough, Hubspot Kitchen, Floribbean Grill";
Tiano's Italian Restaurant excluded by (b) — survivor "The Grille",
license business "GRILLE" (both distinctive sets empty).
The 27 excluded rows stay ACTIVE and are listed in
`successor_ambiguity_review.csv` (workspace) with the guard that fired.

## Apply

- Sanity gate: 7,093 ∈ [5,000, 7,120] ✓; archetype case Habaneros
  Mexican Restaurant (220 Wekiva Springs Rd, Longwood) in the apply
  set ✓.
- Backup: `venues_backup_20261027_successor` — 7,093 full rows.
- Audit / undo handle: `successor_suppressions_20261027` — 7,093 rows
  (venue id, name, address, survivor, license business + number,
  applied_at). Staging table `successor_apply_stage_20261027` retained.
- Change: `is_active=0, operating_status='permanently_closed'` on the
  apply set only.
- Undo: restore rows from `venues_backup_20261027_successor`
  (full-row backup; the audit table alone does not carry the prior
  operating_status).

## Verification (all post-apply, independently re-queried)

- Active venues: **1,555,655 → 1,548,562**; delta = 7,093 = applied
  count exactly.
- Applied ids still active: **0**; all 7,093 carry
  `permanently_closed`. Survivors active: **7,093 / 7,093**.
- Habaneros: inactive/permanently_closed; Frida's Mexican Grill
  active. Both ambiguity archetypes (Tiano's, Taqueria Gonzalez)
  still active.
- 10 random applied addresses spot-checked: at every address the
  survivor is the remaining active venue of the pair (5 of 10 differ
  from the candidate only by ZIP+4 / city-name formatting in the
  stored address string; group-level street+ZIP5 check confirms).
- Live API (neutraleats.com/api/venues.php): Wekiva Springs bbox
  returns Frida's, not Habaneros; Jacksonville Beach (Bubba Gump in,
  Joe's Crab Shack out), Tampa Main St (Venue 2106 in, Guava Grill
  out), Sanford (Taqueria Navarro in, D'sara out); Tiano's and
  Taqueria Gonzalez still returned.

## Anomaly (no data impact)

The host apply script's final spot-check query (correlated
full-table address scans) ran away on the 4 GB host and the SSH
session dropped **after** backup, audit, update, and the primary
count verifications had all completed. The orphaned read-only query
was killed and every figure above was re-derived with efficient
queries afterward; backup/audit/update state was already committed
and mutually consistent (7,093 across staging, backup, audit).

Scripts: `successor_apply.py` (guards, local),
`successor_apply_host.py` (staging/apply/verify, host) — repo root of
the Neutral Eats workspace.
