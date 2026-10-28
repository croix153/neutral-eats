# Neutral Eats — App Store submission packet (DRAFT, prepared 2026-10-27)

Status: DRAFT for Croix's review. Nothing has been entered in App Store Connect.
ASC app record already exists: "neutral eats", Apple app ID 6827198241,
bundle ai.croix.neutraleats, SKU neutraleats-ios, status Prepare for Submission
(created 2026-10-26). Final build gate: build 19 (Raleway wordmark) smoke test,
plus the dense-area tap-to-snap crash retest carried since build 13/16.

## Listing copy (draft)

- **Name:** neutral eats (already accepted in ASC as-is)
- **Subtitle (30 chars max):** "No ads. No bias. Just food." (27 chars)
- **Promotional text (170 chars max):**
  "Restaurants near you, instead of restaurants promoted near you. Results are
  ranked by distance and data quality only — no venue can pay for placement."
- **Description (draft):**
  "Neutral Eats is an unbiased nearby-restaurant finder.

  Every other food app ranks results by who paid. Neutral Eats can't be paid:
  there are no ads, no sponsored listings, and no promoted placements anywhere
  in the app or in the data pipeline behind it. Results are ranked by distance
  and data quality — that's it.

  - Map and list of restaurants, cafés, bars, fast food, and bakeries near you
  - Ranked by distance from you, never by sponsorship
  - Exact-phrase search — search 'taco bell', get Taco Bell
  - Closed places are excluded using state licensing records where available
  - Day and night themes
  - No account, no ads, no tracking

  1.5 million+ venues across the United States, built from open data
  (Overture Maps) and verified against state licensing records.

  Ranked by distance. Nothing is sponsored — ever."
- **Keywords (100 chars max, draft):**
  "restaurants near me,food finder,no ads,unbiased,nearby food,cafes,bakeries,local food,food map" (97 chars)
- **Category:** Primary: Food & Drink. Secondary: Travel (optional, Croix's call)
- **Support URL:** https://neutraleats.com (live)
- **Marketing URL:** https://neutraleats.com (optional)

## Privacy (App Privacy answers, draft — one judgment call flagged)

Code-verified 2026-10-27 from ios/NeutralEats/:
- No accounts, no sign-in, no analytics SDKs, no ad SDKs, no tracking code
  anywhere in the app target.
- Location: When In Use only. Info.plist purpose string: "neutral eats centers
  the map on you to rank nearby places by distance. Your location is only used
  on this phone, for that."
- Network: the app sends only a map bounding box (south/west/north/east),
  an optional category, and an optional search term to
  https://neutraleats.com/api/venues.php (APIClient.swift). No device IDs,
  no user identifiers, no precise user coordinate is sent directly.

JUDGMENT CALL for Croix: the bounding box is derived from the visible map
region (often centered on the user), so coordinates do leave the device as a
query parameter. Two defensible ASC answers:
  (a) Conservative: declare Precise Location — used for App Functionality,
      NOT linked to identity, NOT used for tracking.
  (b) "Data Not Collected" — only if the server does not log/retain the
      query coordinates in a way tied to a user.
Recommendation: (a). It matches the honesty brand and costs nothing.
**DECISION (Croix, 2026-10-27): option (a) — declare Precise Location, used
for App Functionality, NOT linked to identity, NOT used for tracking.**

- **Age rating:** answer all questionnaire items "None" → 4+. No objectionable
  content; venue data is names/categories only.
- **Export compliance:** already handled per-build by asc_build.py
  (uses standard encryption only / exempt — HTTPS).
- **Content rights:** venue data from Overture Maps (open data, ODbL) and
  state licensing records (public records). No third-party copyrighted content.

## Screenshots — CAPTURED Oct 27, staged pending Croix's visual approval

Set: 6.9" iPhone (1320×2868), all five in the repo's `appstore-screenshots/`
(iPhone 17 Pro Max simulator, live production data, Winter Park, FL):
01-summary.png, 02-list.png, 03-detail.png, 04-night.png,
05-search.png ("taco bell" — 2 matches). Zero ASC interaction so far.
Original shot list, for the record:
1. Map centered on user, dense area, card in summary form showing the
   tagline "Ranked by distance. Nothing is sponsored — ever."
2. Expanded list form of the card, distances "from you" visible.
3. Venue detail form (a selected venue, snapped map).
4. Night theme, same map view (shows the theme switcher value).
5. Exact-phrase search results (e.g. a chain search).
Captions (optional, draft): "Ranked by distance. Nothing sponsored.",
"1.5M+ places, nationwide", "No ads. No promoted listings. Ever."

## Review notes (draft for App Review)

"Neutral Eats requires no account or sign-in; all features are available
immediately. Location permission is optional — if denied, the app opens on a
default view of Lake Mary, FL and remains fully usable. Venue data is served
from the production API at neutraleats.com."

## Remaining gates before submit (in order)

1. Croix's build 19 smoke test: Raleway wordmark renders bold + dense-area
   tap-to-snap crash retest (the build 13/15/16 test).
2. Croix approves this packet (privacy judgment call RESOLVED 2026-10-27:
   option (a), declare Precise Location).
3. Enter listing + privacy + screenshots in ASC, select the passing build,
   submit. ASC entry is delivery-side work — this packet is the source.

## Build 21 addition — IAP tip jar (2026-10-27); entry point rebuilt in build 22

Build 21 added the "Support Neutral Eats" tip jar: a ladder of seven
CONSUMABLE in-app purchases bought through a StoreKit 2 sheet.
Tips buy nothing — no features, content, or status — per the
product's neutrality rule.

**Build 21 never surfaced the jar in TestFlight:** its entry points
(the summary card's heart button, the list's last row) rendered only
once the product fetch resolved, and the fetch — made while the
products were minutes old — came back empty and never retried.
Croix never saw a tip control. **Build 22 supersedes it as the
submission vehicle:** the jar is entered from an always-rendered
"Donate" pill in the header row (immediately left of the theme
switcher, every card form), the sheet presents in every store
state (loading spinner; pitch + "Tips aren't available right now —
please try again later" when the store returns nothing), and the
fetch re-runs on every sheet open after a failure. Same products,
same ladder, same sheet.

The seven products were created in ASC on 2026-10-27 via
`asc_iap_setup.py` and all sit at READY_TO_SUBMIT with US price
schedules and US availability:

| Product ID | US price |
|---|---|
| ai.croix.neutraleats.tip.099 | $0.99 |
| ai.croix.neutraleats.tip.199 | $1.99 |
| ai.croix.neutraleats.tip.299 | $2.99 |
| ai.croix.neutraleats.tip.499 | $4.99 |
| ai.croix.neutraleats.tip.999 | $9.99 |
| ai.croix.neutraleats.tip.1999 | $19.99 |
| ai.croix.neutraleats.tip.4999 | $49.99 |

Display name (en-US): "Supporter Tip". Description field (Apple caps
it at 55 characters): "A voluntary tip that buys nothing. Thank you!"

Submission notes:
- These products belong to the **build-22 submission**. They are
  NOT part of the staged build-20 submission above — if build 20 is
  submitted first, the tip products ride along with build 22's
  version submission later. (Build 21 carried them to TestFlight
  only and was never submitted; build 22 supersedes it.)
- When build 22 is submitted, all 7 products must be attached to
  that version's submission (first-time IAPs are reviewed with the
  app version).
- Each product's App Store review screenshot is currently the
  packet's 01-summary app screenshot as a placeholder. Before the
  build-22 submission, replace it with a capture of the actual
  Support sheet so App Review sees the purchase in context.
- Sandbox purchase flow is UNVERIFIED until build 22 is exercised
  on a device with a sandbox Apple ID — CI cannot run StoreKit
  purchases. Build 21's flow was never reached: its entry points
  didn't render (see above).
