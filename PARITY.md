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
| Day/night themes with a header switcher; default follows the device, switcher can pin day or night | ✓ (persisted `ne-theme`) | ✓ (build 9: 3-state auto → day → night cycle) | Same hex values both sides; basemap + dots restyle with the chrome |
| Venue name labels on the map at street zoom | ✓ (zoom ≥ 17, nearest 120) | ✓ (build 9: span ≤ 0.0085, nearest 80) | Labels are tappable, selected venue's label wears the accent |
| Result count at the server cap reads "500+", never a bare "500" | ✓ | ✓ (build 9) | Both key off the same cap signal (serverCount ≥ limit) |

## Deliberate surface differences (not gaps)

| Behavior | Web | iOS | Why |
|---|---|---|---|
| Venue detail presentation | Bottom sheet | In place (build 10): map card morphs into the detail card; list rows expand inline | Croix, 2026-10-26: the slide-up sheet "doesn't feel like it interacts organically with the list" — detail now opens where the selection already lives. Content is the same on both surfaces. |

## Known gaps (not yet at parity — Croix's call on priority)

None open as of build 9 (2026-10-26). The street-zoom label gap —
the last one — closed when Croix asked after it; it had been a
deliberate v1 deferral, never a removal: the app simply shipped
without labels while the web had them.
