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
| Search + type chips (All / Restaurants / Cafés / Bars / Fast Food / Bakeries) | ✓ | ✓ | Same six filters. Bars is a category: the API maps `type=bar` to bar + pub types (server-side, 2026-10-26). Extraction folds pub/wine_bar/etc. into type `bar`, so no `pub` rows exist today — pubs appear under Bars as bars |
| Map dot density at wide zoom | Renders all fetched markers (MapLibre GL) | Clusters colliding dots into count bubbles that zoom apart on tap (build 11); labels replace clustering at street zoom | Deliberate presentation adaptation per map engine — same underlying venue set on both surfaces |
| Enrichment render: `★ 4.5 (123) · $$` + "Full service" pill | ✓ | ✓ (build 7+) | Fields are null until the Yelp key lands; both surfaces light up together |
| Closed venues excluded | ✓ server-side (`venues.php` + enrichment `is_closed`) | ✓ server-side | Inherited by both; no client work |
| User location marker | Flat navigation arrow in the theme's location color (`--user`/`--good`): indigo #165E83 by day, neon cyan #38E1FF by night; white keyline; no halo, no glow | Same arrow, custom MKUserLocation view (build 14) | Croix, 2026-10-26 late: the star (gold, then theme-colored) and its pulsing halo both retired — he didn't love the shape or the glow. The arrow's silhouette can't be mistaken for a round venue dot. An earlier gold-star design (#DD8E00/#FFC53D) lived for one evening — gone |
| Distances expressed from the user when a fix exists ("0.4 mi from you"); map center is the fallback and still drives ranking order | ✓ `dispDist()` / `distOrigin()` | ✓ `distanceOrigin` / `distanceFromUser` (build 14) | Croix, 2026-10-26: "instead of from map center express distance from user" |
| Meta lines never repeat the type word the cuisine already says ("Restaurant" over "restaurant,…" / "Pizza Restaurant") | ✓ `dedupedType()` | ✓ `Venue.dedupedTypeLabel` (build 13) | Same rule both sides: drop the bare type when a cuisine term equals it or the first term ends with it |
| Selecting a venue lands the camera on it | ✓ list taps pan + zoom to 16 when zoomed out; map taps pan | ✓ any selection snaps to span 0.008 (build 13) | The detail opens in the bottom card/sheet on both surfaces |
| Pure grocery stores are not results | ✓ inherited (data) | ✓ inherited (data) | Server-side suppression, 2026-10-26: 463 venues (cuisine/chain/name rules, zero food-service terms allowed) set `is_active=0`; audit table `grocery_suppressions_20261026` is the one-command undo. Delis, bakeries, food courts and pubs that serve food stay |
| Day/night themes with a header switcher; default follows the device, switcher can pin day or night | ✓ (persisted `ne-theme`) | ✓ (build 9: 3-state auto → day → night cycle) | Same hex values both sides; basemap + dots restyle with the chrome. Day palette realigned 2026-10-26 (web + build 12) to the Creams Tokyo DAY spec: washi #FAF7F2, ai-iro indigo #165E83 (brand/links/selected dot), shu-iro vermillion #EB471F (dots/selected fills), text-grade vermillion #C6360F |
| Venue name labels on the map at street zoom | ✓ (zoom ≥ 17, nearest 120) | ✓ (build 9: span ≤ 0.0085, nearest 80) | Labels are tappable, selected venue's label wears the accent |
| Result count at the server cap reads "500+", never a bare "500" | ✓ | ✓ (build 9) | Both key off the same cap signal (serverCount ≥ limit) |

## Deliberate surface differences (not gaps)

| Behavior | Web | iOS | Why |
|---|---|---|---|
| Venue detail presentation | Bottom sheet over the map (peek/full stops); list lives in the sheet, detail replaces the list inside it | ONE bottom card over the map, no Map/List switcher (build 13): summary → expanded list → detail, morphed by state | Same interaction model since build 13 (Croix): the map never leaves; one card at the bottom holds list and detail. Stop counts differ per platform idiom (sheet stops vs card forms); content is the same. Supersedes the build 10 in-place design and its inline list expansion |

## Known gaps (not yet at parity — Croix's call on priority)

None open as of build 9 (2026-10-26). The street-zoom label gap —
the last one — closed when Croix asked after it; it had been a
deliberate v1 deferral, never a removal: the app simply shipped
without labels while the web had them.
