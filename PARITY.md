# neutral eats — web ⇄ iOS parity

**Rule (Croix, 2026-10-26): the website and the app stay in sync.**
A behavior or feature change is not done until it lands on both
surfaces, or the difference is recorded below as a deliberate
platform-only exception with its reason. Whoever changes one surface
updates this file in the same commit.

Why this file exists: on 2026-10-26 the web preview reversed its
never-ask-on-launch location rule (open centered on the user, ask for
permission as part of the attempt) and the iOS app silently kept the
retired rule — it never asked and never centered, and Croix found it
before we did. Drift like that is what this checklist prevents.

## Shared behaviors

| Behavior | Web (preview.html) | iOS app | Notes |
|---|---|---|---|
| Opens centered on the user; permission asked as part of the first attempt; decision remembered by the OS/browser | ✓ `locateAndCenter(true)` on cold load | ✓ `launchLocate()` on cold launch (build 7+) | Denied → quiet fallback to home; Near-me explains |
| Home fallback view | ✓ Lake Mary, FL (28.713, −81.326) | ✓ same coordinates (`kHomeRegion`) | |
| Near-me manual re-center | ✓ | ✓ | |
| Ranking: distance + data quality only; nothing sponsored, ever; honesty line shown | ✓ | ✓ | Core product rule — never platform-optional |
| Search + type chips (All / Restaurants / Cafés / Bars / Fast Food / Bakeries) | ✓ | ✓ | Same six filters. Bars is a category: the API maps `type=bar` to bar + pub types (server-side, 2026-10-26). Extraction folds pub/wine_bar/etc. into type `bar`, so no `pub` rows exist today — pubs appear under Bars as bars. Tapping the SELECTED chip resets to All (both surfaces, 2026-10-26). Text search is an EXACT PHRASE server-side (2026-10-27): boolean-mode quoted phrase with prefix tolerance on the last word — the old form matched ANY word ("taco bell" → 38,994 venues; phrase → 8,902) |
| Map dot density at wide zoom | Renders all fetched markers (MapLibre GL) | Clusters colliding dots into count bubbles that zoom apart on tap (build 11); labels replace clustering at street zoom | Deliberate presentation adaptation per map engine — same underlying venue set on both surfaces |
| Enrichment render: `★ 4.5 (123) · $$` + "Full service" pill | ✓ | ✓ (build 7+) | Fields are null until the Yelp key lands; both surfaces light up together |
| Closed venues excluded | ✓ server-side (`venues.php` + enrichment `is_closed`) | ✓ server-side | Inherited by both; no client work |
| Opening hours on the venue detail, when the venue has them | ✓ `.dhours` block in the sheet detail | ✓ hours block in the card detail | Data: OSM `opening_hours` backfill 2026-10-27 (FL: 7,524 venues in `venues.hours`; audit `osm_hours_applied_20261027`, backup `venues_backup_20261027_osmhours`). Both surfaces render the raw string split on `;` — one segment per line, verbatim, only when non-empty — with "Hours © OpenStreetMap contributors" beneath |
| User location marker | Just a dot in the theme's location color (`--user`/`--good`): indigo #165E83 by day, neon cyan #38E1FF by night; heavier white ring, a few px larger than a venue dot; no halo, no glow | Same dot, custom MKUserLocation view (build 15) | Croix, 2026-10-26 late: star (gold, then theme-colored) + pulsing halo + a one-build arrow all retired — "just a dot but in a different color to differentiate it" |
| Distances expressed from the user when a fix exists ("0.4 mi from you"); map center is the fallback and still drives ranking order | ✓ `dispDist()` / `distOrigin()` | ✓ `distanceOrigin` / `distanceFromUser` (build 14) | Croix, 2026-10-26: "instead of from map center express distance from user" |
| Meta lines never repeat the type word the cuisine already says ("Restaurant" over "restaurant,…" / "Pizza Restaurant") | ✓ `dedupedType()` | ✓ `Venue.dedupedTypeLabel` (build 13) | Same rule both sides: drop the bare type when a cuisine term equals it or the first term ends with it |
| Selecting a venue lands the camera on it, tight | ✓ list taps pan + zoom to 17 when zoomed out; map taps pan | ✓ any selection snaps to span 0.005 (build 15) | The detail opens in the bottom card/sheet on both surfaces. iOS: a selected venue is pulled OUT of any cluster it sat in (re-dressed unclustered), so the selection is always visible — never hidden inside a number bubble |
| Tapping empty map deselects | ✓ map click closes the detail (timestamp-guarded against the selection tap itself) | ✓ tap recognizer with annotation hit-test → `onDeselect` (build 15) | Croix, 2026-10-26: "tapping anywhere in the map area ought deselect the selected venue" |
| Pure grocery stores are not results | ✓ inherited (data) | ✓ inherited (data) | Server-side suppression, 2026-10-26: 463 venues (cuisine/chain/name rules, zero food-service terms allowed) set `is_active=0`; audit table `grocery_suppressions_20261026` is the one-command undo. Delis, bakeries, food courts and pubs that serve food stay |
| Day/night themes with a header switcher; default follows the device, switcher can pin day or night | ✓ (persisted `ne-theme`) | ✓ (build 9: 3-state auto → day → night cycle) | Same hex values both sides; basemap + dots restyle with the chrome. Day palette realigned 2026-10-26 (web + build 12) to the Creams Tokyo DAY spec: washi #FAF7F2, ai-iro indigo #165E83 (brand/links/selected dot), shu-iro vermillion #EB471F (dots/selected fills), text-grade vermillion #C6360F |
| Brand wordmark typeface: Raleway (bold) | ✓ (Google Fonts, 500/700) | ✓ build 19 (bundled variable font, OFL) | Aligned 2026-10-27 (Croix) — the app wordmark previously wore the system serif (New York). UI text stays on the system font on both surfaces; the app bundles Raleway-Variable.ttf (~312 KB, weights 100–900) registered via UIAppFonts |
| Venue name labels on the map at street zoom | ✓ (zoom ≥ 17, nearest 120) | ✓ (build 9: span ≤ 0.0085, nearest 80) | Labels are tappable, selected venue's label wears the accent. iOS labels are rasterized into the dot image (build 10) and, from build 17, pixel-snapped (ceil'd text box, integral draw origin, 12pt, halo −5) so glyphs land on the pixel grid — fractional origins made them look artifact-y. Web labels are live DOM text, crisp by construction |
| Card honesty tagline ("Ranked by distance. Nothing is sponsored — ever." with shield) | ✓ (sheet head, always visible) | ✓ list head; ✓ summary card from build 17 | Same wording both surfaces; the iOS summary card carried only the failure line until build 17 (Croix) |
| Result count at the server cap reads "500+", never a bare "500" | ✓ | ✓ (build 9) | Both key off the same cap signal (serverCount ≥ limit) |

## Deliberate surface differences (not gaps)

| Behavior | Web | iOS | Why |
|---|---|---|---|
| Venue detail presentation | Bottom sheet over the map (peek/full stops); list lives in the sheet, detail replaces the list inside it | ONE bottom card over the map, no Map/List switcher (build 13): summary → expanded list → detail, morphed by state | Same interaction model since build 13 (Croix): the map never leaves; one card at the bottom holds list and detail. Stop counts differ per platform idiom (sheet stops vs card forms); content is the same. Supersedes the build 10 in-place design and its inline list expansion |
| Support / donate | Deferred — no web donate surface. The planned Stripe "pay what you want" link is dead: Croix has no Stripe account and doesn't want one (2026-10-27). Revisit only if he opens one | ✓ build 22: an always-rendered "Donate" pill in the header row, immediately left of the theme switcher → the Support sheet (StoreKit 2) with 7 consumable IAP tips. The sheet carries its own loading and unavailable states and re-fetches on open. Build 21 shipped the same jar but gated its entry points on the product fetch resolving — in TestFlight they never appeared — so build 22 removed the gate. **Build 23 (2026-10-27): the ladder is whole dollars only — $1/$2/$5/$10/$20/$50/$100 (tip.d1…d100); the $0.99–$49.99 cent products were retired in ASC (availability removed, records kept)** | **Platform exception by Croix's call (2026-10-27).** Apple IAP is the payment rail he actually has; the web equivalent waits on an account he doesn't. The rule both surfaces keep: a tip buys nothing — the app/site is identical either way, and nothing about results changes |

## Known gaps (not yet at parity — Croix's call on priority)

None open as of build 9 (2026-10-26). The street-zoom label gap —
the last one — closed when Croix asked after it; it had been a
deliberate v1 deferral, never a removal: the app simply shipped
without labels while the web had them.
