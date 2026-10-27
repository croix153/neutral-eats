# venues.php hardening — STAGED, not deployed (2026-10-26)

`venues.php.hardened` is the reviewed replacement for the live
`venues.php`, addressing adversarial-review findings 2, 3, 17,
18. It has NOT been deployed: it changes the live endpoint's
ranking behavior, so it ships on Croix's review, with the
deploy steps below.

## What changes

1. **Server-side distance ordering (finding 2 — neutrality).**
   The live ORDER BY is `FIELD(source,'overture','osm'),
   rating DESC, name ASC`: the 500-row subset is chosen by
   source and rating BEFORE the clients re-sort by distance,
   so a nearer venue can be cut while the UI claims pure
   distance ranking. The hardened version orders by haversine
   distance from the ranking center (explicit `lat`/`lng`
   params, defaulting to the bbox center — exactly what both
   clients rank from), so the capped subset is the NEAREST
   venues and no client change is needed.
2. **Credentials out of the endpoint (finding 3).** The live
   file carries the DB password as a literal, in a tracked
   repo. The hardened version includes the host-side
   `config/database.php` (the include the legacy pages already
   use; it sets $dbHost/$dbName/$dbUser/$dbPass) and contains
   no secret.
3. **Generic 500s (finding 3).** The live catch block returns
   raw PDO exception text. The hardened version logs the
   detail server-side and returns `{"error":"Database error"}`.
4. **`totalCount` (finding 17).** The response gains the full
   match count, so "500+" is data, not client inference.
   Backward-compatible: existing fields unchanged.
5. **ETag fix (finding 18).** The live tag is an md5 of the
   whole JSON including the per-second `timestamp` — it can
   never match, so conditional requests never 304. The tag
   now covers the venues payload, count, and bounds only.

## Rotation scope (bigger than this one file)

The same DB password literal appears in 10 tracked files
(legacy Minerva-era ingestion scripts, `setup.sql`,
`florida_ingest*`). It is in git history: treat the password
as compromised. Recommended sequence:

1. Deploy this endpoint fix.
2. Rotate the `neutraleats_user` password; update ONLY the
   host-side `config/database.php` (and the pipeline scripts
   that read creds from the environment/host config).
3. Scrub or retire the legacy ingestion files in a follow-up
   pass (several are dead; the live ones must move to the
   config include first).

## Deploy + verify (when approved)

1. Back up the live file: `venues.php.bak-hardening-<date>`.
2. Copy `venues.php.hardened` → `/var/www/html/minerva/api/venues.php`.
3. `php -l` on the host copy.
4. Probes: (a) Bonita Springs bbox — closed Buffalo Wild
   Wings absent, Stan's Super Subs present (FL licensing
   regression check); (b) dense bbox (downtown Orlando) with
   limit 500 — verify the returned set is the nearest 500 by
   comparing the farthest returned distance against a SQL
   distance computation over the same bbox; (c) repeat a
   request with If-None-Match → expect 304; (d) type=bar and
   a search query still behave; (e) break-test in staging
   only: bad config path returns the generic 500.
5. Rollback = restore the backup file.

## Perf note

Distance ordering sorts the bbox candidate set (bounded by
the lat/lng WHERE). A composite index on (is_active, lat, lng)
belongs to the perf pass and will help both the filter and
the sort; it is not required for correctness of this change.
