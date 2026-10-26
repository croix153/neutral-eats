# Neutral Eats — adversarial code review for build 10

**Review baseline:** build 9 code at commit `4738212` (tree also represented by `a9c4867`). Line references below are to that baseline, not to any later build-10 work-in-progress.

**Scope actually reviewed:** all Swift files under `ios/NeutralEats/`, the Xcode project/workflow because `ios/project.yml` does not exist in this repo, `server/minerva/api/venues.php` (there is no repo-root `api/` directory), all five scripts in `pipeline/`, `web/preview.html`, and `PARITY.md`.

## Executive verdict

Build 9's missing map labels are most likely a **presentation/collision failure in the label annotation views**, not a failure to compute the label set. The code creates a second annotation at exactly the same coordinate as each venue dot, gives that annotation an image-less `MKAnnotationView` containing a manually laid-out `UILabel`, and explicitly marks it `.defaultLow` display priority while the paired dot is left at MapKit's higher default priority. That is the only label-specific path that affirmatively tells MapKit the label is disposable.

The most serious product defect elsewhere is server-side: `venues.php` chooses the 500-row subset by source and rating **before** either client re-sorts by distance. In dense areas the clients' “ranked by distance” claim is therefore false for the data they never receive.

---

## Ranked findings

### 1. HIGH — Build 9 labels: separate low-priority, image-less annotation views can all be collision-suppressed

**Files/functions:**

- `ios/NeutralEats/MapView.swift:127–165` — `Coordinator.reconcileLabels`
- `ios/NeutralEats/MapView.swift:179–213` — `mapView(_:viewFor:)`
- `ios/NeutralEats/MapView.swift:230–235` — `mapView(_:regionDidChangeAnimated:)`

#### Execution trace

1. `makeUIView` correctly installs the coordinator as `MKMapView.delegate` at line 39 and starts at `kHomeRegion` (latitude span `0.055`).
2. `updateUIView` calls `syncAnnotations` at line 54; that calls `reconcileLabels` at line 120. At the home span the label set is correctly empty.
3. When the user zooms, `regionDidChangeAnimated` calls `parent.onRegionSettled` and then `reconcileLabels` with the parent's current venues at lines 230–234.
4. Once `latitudeDelta <= 0.0085`, `reconcileLabels` builds up to 80 target IDs and calls `mapView.addAnnotation` for each new `LabelAnnotation` at lines 136–157.
5. `viewFor` returns a plain `MKAnnotationView` for each label. It has **no `image`**. Its only content is a `UILabel` subview. At line 187 it is assigned `displayPriority = .defaultLow`.

So the “annotations are never added” theory is not supported by the control flow. Assuming Croix's dots were present and updating, the delegate, venue data, and region callback were all working. The failure is much more likely after annotation creation, when MapKit decides whether/how to display the label view.

#### Candidate causes, ranked

**1A. MapKit collision/display-priority suppression — most likely.**

Each label annotation is placed at the *exact same coordinate* as its venue's dot annotation (compare lines 107 and 154). The dot branch at lines 205–213 does not lower its priority; the label branch deliberately sets `.defaultLow` at line 187. `displayPriority` is MapKit's collision-triage mechanism: when annotation views collide, lower-priority views may be hidden rather than merely drawn underneath.

Build 9 therefore creates up to 80 pairs of coincident annotations and tells MapKit that, in every pair and in label-to-label collisions, the text is the thing that may disappear. At street zoom in a real restaurant district, label-to-label collisions are also pervasive. There is no compensating setting: no `.required` priority, no collision mode override, no `zPriority`, and no merging of text into the dot's own rendering.

This best explains a complete absence rather than occasional clutter. It is still an inference about MapKit internals, not something source code alone can prove. The discriminating device/simulator test is:

- At street zoom, log or inspect `mapView.annotations.filter { $0 is LabelAnnotation }.count`.
- Pick a label annotation known to be in the visible rect and inspect `mapView.view(for:)`.
- If the annotation exists and `view.isHidden == true`, collision suppression is proven.
- If it exists, is not hidden, and has a sane frame, inspect the subview frame/layer hierarchy next.

**Suggested fix:** do not ship labels as a second coincident annotation. Render the name into the same annotation view/image as the dot, or use a dedicated `MKAnnotationView` subclass for the venue itself whose combined content is intrinsically visible. If separate label annotations are retained, they need required display priority and collision handling explicitly disabled/configured, plus a device test proving that choice. Also add the debug counters above behind a debug/diagnostic flag; build 9 had no way to distinguish “not added” from “added but hidden.”

**1B. Fragile manual annotation-view geometry — plausible contributor.**

The label view is not a custom subclass with a defined layout lifecycle. `viewFor` creates/reuses a generic view, removes all subviews, creates a label, calls `sizeToFit()`, adds it, then assigns `view.frame` with origin `.zero`, and finally positions the label from the newly assigned frame (lines 183–202). It never sets an image, never explicitly establishes `bounds` in `layoutSubviews`/`prepareForDisplay`, never resets `isHidden`, `alpha`, or collision state on reuse, and never forces a layout pass.

That pattern can work in simple MapKit examples, so I would not call it certainly fatal. But it is unusually dependent on MapKit's annotation-layout behavior, especially for reused views previously hidden by the collision system. It also makes the failure hard to reason about: the annotation view's drawing surface is a side effect of a subview rather than the view's own image/content.

**Suggested fix:** if a view-based label remains, implement a real annotation-view subclass: set content in `prepareForDisplay`, reset visibility/alpha in `prepareForReuse`, give the view a deterministic `bounds`, lay the label out in `layoutSubviews`, and set center offset from the actual bounds. A rendered combined image avoids most of this class of failure.

**1C. Region/state flow can produce a stale reconcile, but it does not explain a permanent failure by itself.**

`regionDidChangeAnimated` first calls `onRegionSettled`, whose closure goes to `VenueStore.regionSettled`; that synchronously mutates `@Published center`, re-sorts `@Published venues`, and schedules another fetch (`VenueStore.swift:32–37`). Only after that does the delegate reconcile labels using `parent`, a value-type snapshot of `VenueMapView` held by the coordinator (lines 230–234). This is re-entrant and more convoluted than necessary.

However, it is not the leading explanation for “never”: a subsequent SwiftUI update calls `syncAnnotations`/`reconcileLabels` again, and a completed fetch publishes a new venue array that triggers the same path. A stale call might remove or delay labels; it should not permanently suppress them after the next render unless the presentation problem in 1A/1B also exists.

**Suggested fix:** make the delegate do one thing — enqueue the settled region. Compute annotation appearance in the representable update from one current inputs snapshot. Avoid two sources of label truth (direct delegate reconcile plus SwiftUI sync).

**1D. Threshold semantics — not the main manual-zoom explanation, but see Finding 6.**

The gate is `latitudeDelta <= 0.0085`. A user who genuinely reaches MapKit's maximum zoom should cross it, so the threshold alone does not explain Croix's report. There is no instrumentation proving what span his device settled at, though. Log the settled span in the same diagnostic described above before spending more cycles theorizing.

**1E. Empty-name/data filtering — unlikely on the reported facts.**

`reconcileLabels` requires a mappable venue and a non-empty `name` (line 139). If the current result set had no names, the list and detail UI would also be visibly broken. Croix's report is specifically that dots show but names do not. No code evidence supports “all names were empty.”

#### What is ruled out

- Delegate registration is present.
- The label branch is checked before the generic venue-dot guard, so label annotations are not accidentally routed to the dot branch.
- `didSelect` handles both annotation classes.
- The coordinator's parent is refreshed in `updateUIView`.
- The label target calculation itself is straightforward and bounded.

---

### 2. HIGH — The API's 500-row subset is selected by source and rating before the clients sort by distance, violating the neutrality/ranking rule

**File:** `server/minerva/api/venues.php:99–103`

```sql
ORDER BY
    FIELD(venues.source, 'overture', 'osm'),
    venues.rating DESC,
    venues.name ASC
LIMIT :limit
```

Both clients then re-sort only the returned page by distance (`ios/NeutralEats/VenueStore.swift:80–82`; `web/preview.html:687–692`). Re-sorting a biased subset does not make the result distance-ranked.

**Concrete failure scenario:** a downtown bbox contains 900 matching venues. A poorly rated or legacy-source venue 0.1 miles from the center can be pushed past row 500 by farther Overture/high-rated venues. It is never sent to the phone, while the UI says “Ranked by distance. Nothing is sponsored — ever.” Conversely, rating—a data-quality/popularity signal at best—directly determines inclusion in the visible universe.

This is not cured by calling rating “data quality.” The stated rule permits distance plus data quality, but the current query gives source priority precedence over distance and applies the cap before distance is ever considered.

**Suggested fix:** make the server own nearest-first selection. Accept explicit center latitude/longitude parameters (the clients know the map center) and order by a spatial distance expression before `LIMIT`, with a deterministic ID tie-breaker. If search must remain relevance-filtered, use `MATCH` as a filter, not a pre-distance inclusion ranking. Add an integration fixture with >500 rows proving that the returned set is the nearest 500.

---

### 3. HIGH — Database credentials are hardcoded in the tracked PHP endpoint, and database exceptions are returned to clients

**File:** `server/minerva/api/venues.php:25–29, 164–167`

The endpoint contains a literal DB username/password in the repository. At the end, the catch block returns `Database error: ` followed by the raw exception message.

**Concrete failure scenario:** anyone who obtains the repo, an archive, a backup, or a web-server misconfiguration that serves the PHP source obtains working database credentials (assuming the checked-in password is the deployed one; if it is stale, the repo is still teaching the wrong pattern). Separately, SQL errors disclose schema/driver details that help an attacker probe the deployment. The missing-index failure in Finding 5 becomes an information leak as well as an outage.

**Suggested fix:** treat the checked-in password as compromised if it was ever live: rotate it. Load DB configuration from the existing server-side config outside the repo/webroot or from environment variables. Return a generic 500 body to clients and log the exception only server-side.

---

### 4. HIGH — Yelp phone matching can attach the wrong business and cause an open venue to be suppressed as closed

**Files:**

- `pipeline/enrich_yelp.py:230–232` — phone search returns only the first business
- `pipeline/enrich_yelp.py:299–305` — phone match accepted at name ratio `>= 0.40`, with no distance/address check
- `pipeline/enrich_yelp.py:352–368` — resulting `is_closed` is stored
- `server/minerva/api/venues.php:62–63` — any enrichment `is_closed = 1` suppresses the venue

**Concrete failure scenario:** a recycled phone number, call-center number, franchise switchboard, or similarly named location of the same chain returns a closed business as Yelp's first phone result. A weak 0.40 name-similarity check accepts it. The local open venue then disappears from both clients for the enrichment TTL, with no audit field recording why the match was trusted.

Search matching is more careful because it includes coordinate distance in its score; phone matching bypasses that protection entirely.

**Suggested fix:** never let a phone-only match suppress a venue unless it is independently corroborated by coordinates and/or address tokens. Store match score and matched coordinates/address in the enrichment row for audit. Use tiered behavior: high-confidence matches may set `is_closed`; low-confidence matches may display nothing and must not close the venue.

---

### 5. MEDIUM-HIGH — `venues.php` makes an optional enrichment table and a composite FULLTEXT index hard runtime dependencies, but no reviewed schema step guarantees either

**Files:**

- `server/minerva/api/venues.php:81` — four-column `MATCH(...)`
- `server/minerva/api/venues.php:96–98` — unconditional `LEFT JOIN enrichment`
- `pipeline/enrich_yelp.py:87–110, 424` — enrichment DDL exists only inside the enrichment script
- `pipeline/monthly_refresh.py` gates — totals/metros/coords/provenance only; no schema/index assertions

`LEFT JOIN` describes the row relationship, not operational optionality. If the `enrichment` table is absent, the whole venue query fails, not just enrichment. If the composite FULLTEXT index on `(name, cuisine, brand, address)` is absent, MySQL raises error 1191 for every search request; individual indexes on those columns do not satisfy a multi-column `MATCH`.

The monthly refresh creates the replacement table with `CREATE TABLE ... LIKE venues`, which preserves indexes present on the then-live table, but nothing in the reviewed pipeline creates or verifies the search index as an invariant. A restore, manual rebuild, or environment rebuild can therefore produce a table that passes count gates while search is completely broken.

**Concrete failure scenario:** restore the DB from a pre-enrichment backup or rebuild `venues` without the manually added index. Ordinary browsing either 500s on the missing enrichment table or appears healthy until the first user search, at which point every search 500s and Finding 3 leaks the SQL error.

**Suggested fix:** put both the enrichment table and `ft_search` in a versioned schema migration owned by the deployment/refresh path. Add pre-cutover assertions for table existence and the exact index columns. In the API, fail closed with a generic 503 for schema problems rather than leaking the exception.

---

### 6. MEDIUM — The build-9 list-tap flow uses a span that can never satisfy the build-9 label gate

**Files:**

- `ios/NeutralEats/ContentView.swift:720–730` — list tap requests span `0.01`
- `ios/NeutralEats/MapView.swift:88, 136` — labels require span `<= 0.0085`

The comment at `ContentView.swift:721–723` says the list tap snaps to street zoom “where its name label shows.” That is mathematically false in build 9: `0.01 > 0.0085`, so after the exact flow meant to showcase the selected venue, its label is prohibited.

This does **not** explain why Croix saw no labels after manually zooming all the way in; Finding 1 covers that. But it is an independent, deterministic defect and a parity/documentation break.

**Suggested fix:** define the street span once and share it. Use the same constant for the label gate and list-tap centering, with the requested span comfortably below the gate rather than on opposite sides of it.

---

### 7. MEDIUM — Map region callbacks synchronously mutate SwiftUI-observed state, while annotation appearance is computed in two places

**Files:**

- `ios/NeutralEats/MapView.swift:50–60, 230–234`
- `ios/NeutralEats/VenueStore.swift:32–37`
- `ios/NeutralEats/ContentView.swift:261–285` (map closure wiring)

`MKMapView` delegate callbacks call a SwiftUI closure that immediately assigns `@Published center` and sorts `@Published venues`. Programmatic centering also flows through `updateUIView` → `setRegion`, which can generate further delegate activity. The coordinator then reconciles annotations both from the delegate and from SwiftUI's representable update.

I did not find a proof that this corrupts a specific field, and the sequence guards in the store prevent stale network responses from winning. The defect is architectural fragility: region state, fetch state, and annotation state have multiple synchronous entry points, making behavior such as the label failure difficult to reproduce or instrument. It also risks SwiftUI “publishing during update” diagnostics when delegate work is initiated from representable updates.

**Suggested fix:** coalesce region events in the store (record region, publish once per settle), and make `VenueMapView` appearance a pure function of one inputs snapshot per update. Keep delegate code limited to forwarding the event.

---

### 8. MEDIUM — Theme state is a mutable global written as a side effect of `ContentView.body`

**Files:**

- `ios/NeutralEats/Theme.swift:20–24` — `NEColor.mode` is a static global defaulting to night
- `ios/NeutralEats/ContentView.swift:45–57` — `body` assigns `NEColor.mode = eff`
- `ios/NeutralEats/MapView.swift` — MapKit delegate/image code reads the same global outside the view body

The header comment in `Theme.swift` says `ThemeStore` sets the mode, but build 9's `ThemeStore` does not; `ContentView.body` does. SwiftUI view bodies are not a safe place for global side effects: they can be evaluated for previews, sheets, transactions, and re-renders in orders that UIKit delegate callbacks do not share. The map's dot/label colors read the global from MapKit callbacks, so the map can observe a different mode from the one used to construct the current SwiftUI values if callbacks interleave with a theme/system-appearance transition.

The ordinary toggle path likely works because changing `preference` triggers a body evaluation. This is a state-model defect, not a claim that every toggle fails.

**Suggested fix:** pass the effective mode explicitly through the view/representable inputs and into image-rendering calls. If a process-wide cache is unavoidable, update it from the preference/system-scheme change handler, not from `body`, and make MapKit read the same value passed as `isDay`.

---

### 9. MEDIUM — iOS builds bounding boxes that fail or return the wrong geography at the antimeridian and at very wide spans

**Files:**

- `ios/NeutralEats/APIClient.swift:11–16`
- `server/minerva/api/venues.php:47–51, 65–70`

The client blindly computes `center ± span/2`. It does not clamp latitude, normalize longitude, or split a box crossing ±180°. The server rejects `west >= east` and otherwise performs a single interval comparison.

**Concrete failure scenarios:**

- Near the Aleutians or other Pacific coverage, a region centered at longitude `-179.9` produces a west edge below `-180`; venues just across the line at `+179.9` are not in the single interval.
- A center at `179.9` produces an east edge above `180`; the query interval misses wrapped venues.
- A very wide/world region can produce nonsensical or rejected bounds and is surfaced as a load failure rather than a bounded result.

**Suggested fix:** normalize and split wrapped longitude intervals, merge the two result sets client- or server-side, clamp latitude to `[-90, 90]`, and cap the span for which a venue query is meaningful.

---

### 10. MEDIUM — Flexible venue decoding converts missing IDs and invalid coordinates into identity collisions and poison values

**File:** `ios/NeutralEats/Models.swift:35–62`

A missing/undecodable `id` becomes `""` rather than causing the row to be rejected. Every malformed row therefore shares the same SwiftUI identity. `isMappable` only checks that `lat` and `lng` are non-nil; it does not require finite values or valid ranges.

**Concrete failure scenario:** two malformed rows in one API response both get ID `""`. `ForEach` sees duplicate identities; the annotation dictionary in `MapView` keeps only one; selecting the surviving empty ID can present the first empty-ID venue rather than the tapped row. An out-of-range coordinate can also produce nonsensical distances and undermine the sort comparator/MapKit behavior.

The flexible string/number handling is otherwise sensible for this API's legacy payloads. The problem is applying it to identity and geometry without validation.

**Suggested fix:** decode rows through a validation step: require a non-empty ID, finite latitude in `[-90, 90]`, and finite longitude in `[-180, 180]`. Drop invalid rows and log/count them in debug rather than manufacturing sentinel identities.

---

### 11. MEDIUM — A transient fetch failure destroys the last good result set and leaves selection/detail state inconsistent

**File:** `ios/NeutralEats/VenueStore.swift:87–95`

On any non-cancellation error, the store sets `venues = []` and `serverCount = 0`. The detail sheet, however, holds a value-type `Venue` snapshot in `ContentView`, so it can continue showing a venue that the store and map no longer contain; `selectedID` is likewise not reconciled against the new empty set.

**Concrete failure scenario:** the user pans across a neighborhood, a request times out, and a fully usable map/list instantly becomes a blank failure state. If a detail sheet is open or a venue was selected, the UI now contains a ghost detail/selection for data the rest of the screen says does not exist.

**Suggested fix:** retain the last successful venues and mark them stale while showing a non-destructive error/retry affordance. Clear data immediately only for an explicit filter/search change, and reconcile `selectedID`/detail against each successful replacement set.

---

### 12. MEDIUM — Yelp enrichment's documented `--min-score` option is dead, and transient failures are cached as 30-day “no match” results

**File:** `pipeline/enrich_yelp.py:299–313, 352–368, 407–465`

The CLI defines `--min-score` and the header says a search candidate must clear it. `match_venue` never receives or reads that argument; it hardcodes a name-ratio threshold of `0.55` and selects by combined score only after that gate.

More importantly, `match_venue` returns `(None, None)` for several indistinguishable cases: genuinely no candidate, Yelp HTTP failure, malformed response, or call-budget exhaustion during matching. `main` converts every `None` into `marker_row`, whose `refresh_after` is 30 days in the future.

**Concrete failure scenario:** a Yelp outage or rate-limit period causes a run to write “attempted/no match” markers for venues it never successfully evaluated. Those venues are then skipped for a month. Separately, an operator who raises/lowers `--min-score` changes nothing.

**Suggested fix:** pass the threshold into the matcher and apply it to the documented combined score. Return a structured outcome (`matched`, `no_match`, `transient_error`, `budget_exhausted`); write long-TTL markers only for a successful evaluation with no match. Transient errors should get no marker or a short retry delay.

---

### 13. MEDIUM — Monthly cutover spot checks cannot fail the cutover

**Files:**

- `pipeline/merge_overture.py:515–542` — `stage_cutover`
- `pipeline/monthly_refresh.py:305–356` — driver treats exit code as the cutover result and then records success

After the rename swap, `stage_cutover` calls the live API for two metros but merely prints the parsed count. If the response is an HTTP 500, invalid JSON, an error envelope, or zero venues, the code sets `got` to a diagnostic string and still exits successfully. The monthly driver then updates the recorded release and can report `SUCCESS`.

**Concrete failure scenario:** the new table breaks the API contract or a required index/enrichment dependency (Finding 5). The spot check prints `unparseable` or `count=0`, but the refresh is recorded as successful and the rollback rotation proceeds.

**Suggested fix:** validate HTTP status, `success == true`, expected venue presence, and at least one search request before declaring cutover healthy. Do not update refresh state or rotate the legacy table when post-cutover checks fail; emit a distinct failure that triggers rollback review. Better still, run equivalent API/schema checks against the staged table before the rename.

---

### 14. MEDIUM — The web map's `move` handler can rebuild a 500-row list repeatedly during a pan, while labels remain stale until the next fetch

**File:** `web/preview.html:711–720, 796–860`

Every Leaflet `move` event recalculates all distances, sorts the array, and calls `renderList()`. `renderList` has an unchanged-ID optimization, but panning normally changes the order, so it builds and replaces the full list HTML—up to 500 rows—repeatedly during one gesture. Markers and labels are not re-rendered in this handler, so the label layer keeps the pre-pan nearest set until `moveend` schedules a fetch and `render()` runs.

**Concrete failure scenario:** on a phone, a slow pan through a dense area spends the gesture rebuilding DOM and can jank, while the visible labels temporarily belong to the previous center's nearest venues.

**Suggested fix:** throttle move handling with `requestAnimationFrame`, update only distance text/order at settle, or defer list reconstruction to `moveend`. Recompute the label set when the distance order changes, or explicitly accept and document the transient state.

---

### 15. LOW-MEDIUM — Near-me can center on a stale launch fix, and a failed one-shot leaves the centering request armed

**Files:**

- `ios/NeutralEats/LocationManager.swift:51–62`
- `ios/NeutralEats/ContentView.swift:90–100, 775–795`

`LocationManager` stores the last `point` indefinitely. `nearMe()` uses that point immediately if one exists and does not request a fresh fix. The one-shot failure delegate is an empty comment, and `wantsCenter` is cleared only when a point arrives.

**Concrete failure scenario:** the app obtains a fix at launch, the user travels across town while the process remains alive, and Near-me jumps to the old launch location instead of the current one. In the failure case, `wantsCenter` can remain true and a much later location update can unexpectedly move the map.

**Suggested fix:** record fix time/accuracy, treat old fixes as stale, request a fresh one-shot for Near-me when the cached fix is not current, and clear/time-out `wantsCenter` on failure.

---

### 16. LOW — “Bars” silently excludes venues typed `pub`, despite pub being a first-class API/model type

**Files:**

- `ios/NeutralEats/Models.swift` — `VenueFilter.bar.serverType == "bar"`; type labels include `pub`
- `web/preview.html:448–454` — server type map also sends only `bar`
- `server/minerva/api/venues.php:73` — the API accepts `pub`, but only as a separate exact type

Both clients behave the same way, so this is not a web/iOS divergence. It is a taxonomy gap: a pub shown under **All** disappears under **Bars**, even though the API and display model recognize `pub` as a bar-like type.

I am not certain this was unintended; the product may deliberately distinguish pubs from bars. But `PARITY.md` only says the six chips match—it does not document this exclusion.

**Suggested fix:** decide the taxonomy explicitly. If Bars means drinking establishments, let the API accept a set of types (`bar`, `pub`) for that chip. If pubs are intentionally excluded, record that in `PARITY.md` so it is not rediscovered as a bug.

---

### 17. LOW — The API's `count` is only the returned page size, so “500+” can be asserted when exactly 500 venues match

**Files:**

- `server/minerva/api/venues.php:135–140` — `count = count($venues)` after `LIMIT`
- `ios/NeutralEats/ContentView.swift` — `displayCount`
- `web/preview.html:781–799` — `displayCount` / cap note

Neither client receives a total matching count. Both infer “there are more” from reaching the page size. If exactly 500 venues match, the UI can still say `500+` and “zoom in for more,” even though no 501st venue exists.

This is an edge case compared with Finding 2, but it means the build-9 parity statement “both key off the same cap signal” is weaker than it sounds: the signal is ambiguous.

**Suggested fix:** return `totalCount` computed with the same filters (without `LIMIT`) alongside the page `count`, and base the plus/cap note on `totalCount > limit`.

---

### 18. LOW — PHP cache headers and the ETag are internally self-defeating, and error responses inherit public caching

**File:** `server/minerva/api/venues.php:21–23, 135–162`

The response JSON includes `timestamp = time()`, so the payload—and therefore the MD5 ETag—changes every second even when the venue data is unchanged for a month. Once the one-hour cache lifetime expires, conditional revalidation cannot produce a stable 304 for unchanged data.

In addition, `Cache-Control: public, max-age=3600` is emitted before parameter validation and before the database try/catch. Validation and database errors for the same URL therefore carry an explicitly cacheable public header.

**Suggested fix:** remove the per-second timestamp from the cacheable representation or exclude it from the ETag calculation; derive the ETag from stable result content/data version. Send public cache headers only for successful responses, and `no-store` for 4xx/5xx responses.

---

### 19. LOW — iOS directions URLs do not fully encode query delimiters in venue names/addresses

**File:** `ios/NeutralEats/Models.swift:185–191`

The place string is encoded with `.urlQueryAllowed`, which permits characters such as `&`, `=`, and `+` that have structural meaning in a query string. A venue name/address containing those characters can truncate or corrupt the `destination_place_name` parameter. The destination coordinates remain intact, so this should not send the user to the wrong coordinates, but the label/context in Google Maps can be wrong.

**Suggested fix:** build the URL with `URLComponents` and `URLQueryItem`, or use a character set that removes query delimiters from the encoded value.

---

### 20. MEDIUM — There is no automated regression gate capable of catching the build-9 label failure or the API schema failures

**Files:**

- `ios/NeutralEats.xcodeproj/project.pbxproj` — app target only; no test target in the reviewed project
- `.github/workflows/ios.yml` — archive/export/verify/upload only; no test step
- Repository tree — no app/API fixture or integration test suite found

The iOS workflow verifies bundle ID, display name, minimum OS, location string, and code signature. Those are packaging checks, not behavior checks. Nothing exercises:

- `MKMapView` annotation appearance at a street-level span;
- the list-tap span versus the label threshold;
- decoding a captured production payload;
- search against a MySQL schema with and without the composite FULLTEXT index;
- the enrichment table's absence;
- the >500-row nearest-selection contract.

That is how build 9 could be marked as closing the label parity gap while the feature never appeared on device, and how `PARITY.md` could move the item from “known gap” to “done” based on code presence rather than observed behavior.

**Suggested fix:** add a small, fast gate before the next TestFlight build: a simulator/device UI or MapKit harness test that loads fixture venues, sets a street span, and asserts both the label annotation count and that its view is not hidden; API integration tests against an ephemeral MySQL instance for search/index/enrichment cases; and a >500-row ranking fixture. Keep the packaging workflow, but do not treat it as QA.

---

## Checked and clean / no defect established

The following areas were specifically inspected; I am not claiming they are perfect, only that the review did not establish a defect there:

- **MapKit delegate wiring:** delegate assignment, label-before-dot branch order, and selection handling are present and coherent.
- **Fetch sequencing:** both iOS (`VenueStore.fetchSeq` plus task cancellation) and web (`fetchSeq` plus `AbortController`) guard against older responses replacing newer ones.
- **PHP SQL parameterization:** bbox, type, limit, and search values in `venues.php` are bound rather than interpolated. I found no SQL injection in that endpoint's reviewed query construction.
- **Enrichment join cardinality:** the enrichment DDL declares `venue_id` as the primary key, so a properly created table cannot multiply venue rows through the `LEFT JOIN`.
- **Location permission basics:** the usage string exists in `Info.plist`; the CI verifies it is packaged; not-determined → prompt → authorization change → one-shot flow is wired; denied Near-me produces an explanatory toast. The stale-fix/timeout issue is Finding 15.
- **Theme persistence mechanics in isolation:** the build-9 preference migration writes the migration marker, invalid stored values fall back to `auto`, and the cycle order is consistent. The separate global-state issue is Finding 8.
- **iOS flexible decoding for common variants:** string/number latitude and longitude, numeric/boolean-ish flags, and `$`-string price levels are handled deliberately. The identity/coordinate validation gap is Finding 10.
- **Web output escaping:** reviewed list, detail, and label rendering paths pass venue text through `esc`; `safeUrl` restricts website links to HTTP/HTTPS. I found no concrete XSS path in those paths.
- **Pipeline overlap protection and major refresh gates:** `monthly_refresh.py` uses an exclusive flock; gates G1–G5 check merged totals, metro floors, bad coordinates/names, and Overture provenance before cutover. The unguarded post-cutover check is Finding 13.
- **Pipeline matching geometry:** the merge candidate grid uses neighboring cells wide enough for its 150 m maximum distance, and the extractor's per-state load counts are reconciled against the transform output.
- **Retain cycles:** no concrete cycle was established in the reviewed Swift task/delegate code; store and location tasks use `[weak self]`, and the MapKit coordinator's `parent` is a value-type representable snapshot rather than a retained view.
- **Project configuration actually present:** deployment target is iOS 16.0 in the Xcode project, bundle ID is `ai.croix.neutraleats`, and the workflow overrides the build number with the GitHub run number. The requested `ios/project.yml` is absent; that absence alone was not treated as a defect because the repo builds from the checked-in `.xcodeproj`.
