# Code rescue — 2026-10-25

This repo held only a README while all production code lived on two servers.
Rescued tonight by Muse (Luxor) at Croix's direction, picking up the project
from Minerva (his OpenClaw agent, Miami Linode), who last tended it ~Mar 2026.

## Layout
- `server/minerva/` — the live neutraleats.com docroot (`/var/www/html/minerva`
  on the croix.ai host): frontend (`neutraleats2.html`), API (`api/venues.php`),
  ingestion scripts, schemas, DEPLOYMENT.md.
- `server/legacy-docroot/` — the earlier croix.ai/neutraleats incarnation
  (static HTML variants + the MySQL `eatery` PHP API).
- `archive/minerva-workspace/` — Minerva's own planning docs and scripts from
  her Miami workspace (`INGESTION_PLAN.md`, Florida ingestion/gap reports).

## Not in git
- Live configs (`config.php`, `config/database.php`) — credential-bearing,
  excluded at rescue; see `*.example` templates.
- SQLite data files (`neutraleats.db`, 31 MB) — held in the local data dir.
- A full MySQL backup of production (21,722 venues) sits on the croix.ai host
  at `/root/backups/neutraleats-2026-10-25.sql.gz`.

## Credential scrub
52 credential redactions were applied across 35 files before the first commit.
The production DB password historically sat in plaintext in dozens of scripts
on two hosts — **rotating it (with the live configs) is queued with the data
rebuild cutover**, since production scripts embed it today.

## State at rescue
- Production DB: 21,722 venues, frozen since ~2026-03-24
  (Yelp 18,943 / OSM 2,453 / Overture 326). API verified live 2026-10-25
  (Lake Mary bbox → 246 venues; Orlando bbox → 277).
- Revival plan: rebuild the backbone on Overture Maps bulk data, merge with
  existing venues (name + 50 m dedupe), monthly unattended refresh, neutral
  ranking only (distance + data quality — no sponsored inputs, ever).
