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
| Search + type chips (All / Restaurants / Cafés / Bars / Fast Food / Bakeries) | ✓ | ✓ | Same six filters |
| Enrichment render: `★ 4.5 (123) · $$` + "Full service" pill | ✓ | ✓ (build 7+) | Fields are null until the Yelp key lands; both surfaces light up together |
| Closed venues excluded | ✓ server-side (`venues.php` + enrichment `is_closed`) | ✓ server-side | Inherited by both; no client work |
| User location marker | Custom pulsing halo | Native MapKit blue dot | Deliberate platform idiom — visual only |
| Day/night themes, toggle in the header, choice persisted (`ne-theme`), default = system then night | ✓ | ✓ (build 8+) | Same hex values both sides; basemap + dots restyle with the chrome |

## Known gaps (not yet at parity — Croix's call on priority)

| Gap | Web | iOS | Notes |
|---|---|---|---|
| Venue name labels on the map at street zoom | ✓ (zoom ≥ 17) | ✗ dots only | v1 gap, noted since build 4 |
