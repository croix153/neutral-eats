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

**Build 23 replaces the ladder with whole dollars (2026-10-27):**
Croix found cents fussy and cut the ladder to $1/$2/$5/$10/$20/$50/
$100. The seven products below were created in ASC via
`asc_iap_dollars.py` and all sit at READY_TO_SUBMIT with US price
schedules and US availability. **They are the submission set for
build 23.**

**Build 24 trims the ladder to six and is the submission
vehicle (2026-10-27):** Croix cut the $100 rung ("an even number
for symmetry"), so the submission set is d1/d2/d5/d10/d20/d50.
The d100 product was retired in ASC exactly like the cent
ladder (availability removed via the CREATE upsert, record
kept, verified territories=[]). Build 24 also makes the tip
pills compact (14pt label, ~2/3 the build-23 height, 3×2 grid),
trims the thank-you body to "Tips like yours keep the servers
on and the results unsponsored", and dedupes tip processing by
transaction id (StoreKit delivers an in-sheet purchase on both
the purchase() return and Transaction.updates; the first
delivery now finishes and thanks exactly once, duplicates are
no-ops).

| Product ID | US price |
|---|---|
| ai.croix.neutraleats.tip.d1 | $1.00 |
| ai.croix.neutraleats.tip.d2 | $2.00 |
| ai.croix.neutraleats.tip.d5 | $5.00 |
| ai.croix.neutraleats.tip.d10 | $10.00 |
| ai.croix.neutraleats.tip.d20 | $20.00 |
| ai.croix.neutraleats.tip.d50 | $50.00 |

The original cent ladder (created 2026-10-27 via `asc_iap_setup.py`)
is **retired**: availability was removed from all seven in ASC, so
they can never be sold or submitted; the records are kept. Do not
re-enable or submit them.

| Retired product ID | Was |
|---|---|
| ai.croix.neutraleats.tip.d100 | $100.00 |
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
- The six whole-dollar products belong to the **build-24
  submission** (build 23 carried the seven-rung set to
  TestFlight only). (Builds 21 and 22 carried the cent ladder
  to TestFlight only and were never submitted; build 24
  references only the d1–d50 set.)
- When build 24 is submitted, all 6 whole-dollar products must
  be attached to that version's submission (first-time IAPs are
  reviewed with the app version). The retired cent products and
  d100 must NOT be attached.
- Each product's App Store review screenshot starts as the
  packet's 01-summary app screenshot placeholder. For the
  build-24 submission it is replaced with a capture of the
  actual Support sheet (Donate pill -> ladder), taken by the
  dispatch-only support-sheet-capture workflow: a UI test taps
  the pill while the scheme's local StoreKit configuration
  (ios/Products.storekit) supplies the six products, and the
  PNG is exported from the result bundle. If that route fails,
  the placeholder stands and the failure is reported.
- Sandbox behavior: the dollar ladder SERVED and completed
  sandbox tips on Croix's device in build 23 (after the Paid
  Apps Agreement went Active), including the thank-you form —
  the flow is device-verified end to end. Build 24's six-rung
  set drops one already-serving product (d100) and changes
  presentation only.

---

## Submission record — Oct 27, 2026 (builds 25/26)

- **Build 25** (CI run 25, ASC id 430bf2ff-8c76-4f96-99aa-a7e1f1fedf7e):
  the tip polish build — six-rung ladder (d100 retired like the cent
  products, availability zeroed, record kept), compact pills, trimmed
  thank-you, purchase double-handling fix (single dedupe funnel).
  VALID + IN_BETA_TESTING. (Run 24 failed on a SwiftUI/StoreKit
  `Transaction` ambiguity in the new signature; fixed by qualifying
  `StoreKit.Transaction`, shipped as run 25.)
- **Build 26** (CI run 26, ASC id ebbe10d-83ee-4004-9bbc-4fd7806a2bdd):
  adds Croix's map-tap-collapses-keyboard fix (@FocusState on the
  search field, resigned from the map's existing non-consuming tap
  recognizer via `VenueMapView.onMapTap` — fires on every tap,
  including annotation taps; selection/deselect/pan/pinch untouched).
  Device-verified PERFECT by Croix Oct 27 evening. VALID +
  IN_BETA_TESTING, and **attached to version 1.0 as the submission
  build**.
- **Entered and verified via the API:** subtitle, description,
  keywords, promotional text, support/marketing URLs, categories
  (Food & Drink primary, Travel secondary), copyright "2026 Roger
  Newson", MANUAL release, free price schedule, age rating 4+
  (questionnaire all None/false), review details + packet notes,
  content rights (third-party content), five screenshots (6.9" slot —
  API display type APP_IPHONE_67 — all COMPLETE).
- **EU EXCLUDED from the start** (Croix's decision): availability
  created with 148 of 175 territories; the unavailable set is exactly
  the EU-27. DSA trader declaration never touched.
- **IAP review screenshots REPLACED with the real capture**
  (`support-sheet-capture.png` in this repo): the Support sheet with
  the six-rung ladder, rendered by the local StoreKit config in the
  simulator (support-sheet-capture workflow, run 3). All six products
  verified carrying it.
- **SUBMISSION BLOCKED on exactly one remaining item (user-side):**
  1. App Privacy answers must be PUBLISHED — the public ASC API has
     no endpoints for this. ASC web: Apps → neutral eats → App
     Privacy → declare Precise Location / App Functionality / not
     linked / not tracking (option (a)) → Publish.
  2. ✅ RESOLVED 2026-10-27 (late evening): `privacyPolicyUrl` — a
     privacy policy page is now LIVE at
     https://neutraleats.com/privacy (source: server/minerva/
     privacy.html + an exact-match .htaccess rewrite of ^privacy/?$;
     the same files were copied into the Miami staging tree so the
     cutover keeps it). The URL was set on the en-US app-info
     localization (e48a5f5d) via the API — asc_privacy.py, PATCH →
     HTTP 200, read-back verified as
     'https://neutraleats.com/privacy'. The policy matches verified
     app behavior: no accounts, no tracking/analytics/ads, bbox +
     search terms to the API, tips processed entirely by Apple,
     brief standard server logs, contact croixnewson@hey.com.
  An empty reviewSubmission exists (id cf2b0845-248a-4244-a7f0-
  e2eae914a326, READY_FOR_REVIEW, 0 items) ready to reuse. Note: in
  this API version, reviewSubmissionItems rejected every IAP
  relationship name tried (inAppPurchaseV2, inAppPurchase,
  inAppPurchases) — first-time IAPs appear to ride the version
  submission via the ASC web version page's In-App Purchases
  section; select the six tip products there when submitting.
  Version remains PREPARE_FOR_SUBMISSION until the App Privacy
  item clears.
