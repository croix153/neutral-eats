# neutral eats — iOS app

Native SwiftUI + MapKit app (no web wrapper), v1 parity with
`web/preview.html`: dark Tokyo-palette map with venue dots (pink,
selected cyan), brand header + search + cuisine/type chips, a
two-state Map/List content region (see "Layout model" below), venue
detail as a modal sheet with Call / Website / Directions and the
data-source line, and Near-me (the only place location permission
is asked — in context).

- Bundle ID: `ai.croix.neutraleats` — display name **neutral eats** (all lowercase)
- Minimum iOS 16.0, iPhone, no third-party dependencies
- Data: production API `https://neutraleats.com/api/venues.php`
  (same params/envelope as the web preview; ranking is re-sorted to
  pure distance client-side — neutrality is the product)

## Layout model (2026-10-26 redesign)

The main screen is a fixed header + ONE content region with two
states, switched by a Map/List control in the header:

- **Header** — solid panel, always on top: wordmark, search field,
  filter chips, Map/List switch. Content never slides under it.
- **Map state** — the map fills the region; a compact card anchored
  to the region's bottom shows the result count and the nearest
  venue (tap → List state) and carries the Near-me button.
- **List state** — the distance-ranked list fills the entire
  region, from directly under the header to the physical screen
  bottom (standard list insets; no dead band). The "Ranked by
  distance. Nothing is sponsored — ever." line and the 500-cap
  note live at its head.
- **Venue detail** is a modal `.sheet` from both states.

The map layer stays in the view hierarchy underneath the list
layer, so toggling states preserves the camera, the loaded venues,
search text and chip filter — no refetch, no layout negotiation.

This replaced a three-stop bottom sheet (drag stops at
collapsed/peek/full) whose hand-rolled geometry kept colliding
with the top UI and stopping short of the bottom edge. The sheet
was removed, not patched: there is no drag-detent code left.

## Pipeline (mirrors the Creams iOS lane)

GitHub Actions workflow `.github/workflows/ios.yml` (manual dispatch):

1. Imports the shared iOS Distribution certificate (team A4NAM9AA6M)
   from repo secrets into a temporary keychain.
2. Installs the **neutral eats App Store** provisioning profile.
3. `xcodebuild archive` (Release, build number = workflow run number).
4. `xcodebuild -exportArchive` with `ios/ExportOptions.plist`.
5. Verifies the .ipa (bundle id, display name, MinimumOSVersion 16.0,
   location usage string, `codesign --verify`).
6. Uploads the .ipa as a workflow artifact and to App Store Connect
   via `altool` (ASC API key from secrets).

Apple-side state (created via the ASC API, 2026-10-26):

- Bundle ID `ai.croix.neutraleats` registered (id `Y37AWJMF27`)
- App Store profile **neutral eats App Store** (UUID
  `d73b4e34-7215-4478-a2b5-0cd6471db0c1`, ACTIVE), bound to the team's
  existing iOS Distribution certificate (expires 2027-10-21)
- Repo secrets set: `APPLE_IOS_CERTIFICATE`,
  `APPLE_IOS_CERTIFICATE_PASSWORD`, `APPLE_IOS_PROVISIONING_PROFILE`,
  `ASC_API_KEY_P8`, `ASC_API_KEY_ID`, `ASC_API_ISSUER`

## Status (2026-10-26) — IN BETA TESTING ✅

The app is live in TestFlight internal testing. Verified end-to-end
via the ASC API:

- **App record**: "neutral eats", app `6827198241`, bundle
  `ai.croix.neutraleats`, SKU `neutraleats-ios` (created in the ASC
  web UI, 2026-10-26 — the API cannot create records; see below).
- **Build 1.0 (11)** — dot clustering (Croix, on build 10: "many
  dots don't show unless you zoom in further"). Every fetched
  venue always had an annotation; at wide spans MapKit's
  collision system hides overlapping dots, so whole areas read
  as empty. Plain dots now cluster into count bubbles (accent
  disc, dot palette) that zoom apart on tap; labeled views and
  the selected dot never cluster. Uploaded by workflow run
  [40421109855](https://github.com/croix153/neutral-eats/actions/runs/40421109855);
  ASC id `ce6cbc44-2aa8-4e13-9d12-cfacb56e03b3`, VALID, attached
  to Internal Testers; `internalBuildState = IN_BETA_TESTING`
  (API-verified 2026-10-26).
- **Build 1.0 (10)** — labels rebuilt as pixels (the venue name
  rendered into the dot's image at .required priority; build 9's
  separate label views never rendered on device — confirmed by
  an adversarial review of the whole codebase, which also
  produced folds for validated coordinates, identity-safe
  decoding, keep-last-good fetch failures, fresh-fix Near-me,
  and encoded directions URLs) and detail moved in place: the
  map card morphs into the detail card, list rows expand
  inline, the `.sheet` is gone. Uploaded by workflow run
  [40419197337](https://github.com/croix153/neutral-eats/actions/runs/40419197337);
  ASC id `7e721ca7-c41b-42a5-92a1-2e6fd1925541`, VALID, attached
  to Internal Testers; `internalBuildState = IN_BETA_TESTING`
  (API-verified 2026-10-26).
- **Build 1.0 (9)** — Croix's five calls from testing builds 7/8:
  uploaded by workflow run
  [40399060420](https://github.com/croix153/neutral-eats/actions/runs/40399060420),
  all steps green; ASC id `7dcf1acc-7cd6-4263-bb3b-70a0d19e3605`,
  VALID; compliance declared and attached to Internal Testers via
  `asc_build.py`; `internalBuildState = IN_BETA_TESTING`
  (API-verified 2026-10-26).
  (1) Build 8's attribution margin-lift REVERSED — card back to
  38pt, label in its natural spot (his preference). (2) Theme
  default = follow the device: the switcher is now a 3-state cycle
  (auto → day → night), build 8's persisted choice migrated away.
  (3) Street-zoom venue name labels (span ≤ 0.0085, nearest 80,
  tappable) — the last PARITY.md gap, a deliberate v1 deferral
  rather than a removal. (4) List-row tap collapses to the map,
  snaps to the venue at street span, detail opens over it.
  (5) Counts at the server cap read "500+" — app card, list head,
  and web preview alike (the preview change shipped the same day).
- **Build 1.0 (8)** — day/night theme switcher + attribution lift
  (commits `9b5af9b`, `f846558`): uploaded by workflow run
  [40392133724](https://github.com/croix153/neutral-eats/actions/runs/40392133724),
  all steps green; ASC id `b79294eb-b364-4a15-9934-364f4c6b0011`,
  VALID; compliance declared and attached to Internal Testers via
  `asc_build.py`; `internalBuildState = IN_BETA_TESTING`
  (API-verified 2026-10-26).
  The switcher sits top-right of the header (the spot Croix marked);
  palettes are the web's exact hexes in both themes, persisted as
  `ne-theme`, default system → night. The MapKit attribution is
  lifted via the map view's bottom layout margin (150pt) and the
  floating card returns to its 12pt perch — Croix's preference over
  build 7's lifted card; if iOS ignores the margin, build 7's
  arrangement is the fallback.
- **Build 1.0 (7)** — cold-launch locate + attribution clearance
  (commits `62931c8`, `1416f82`): the app had kept the retired
  never-ask-on-launch location rule after the web reversed it
  (Croix's catch) — `launchLocate()` now asks on first open and
  centers on the user, denied → quiet home fallback. Same build:
  Venue decodes the enrichment fields (reviewCount, tableService)
  and renders the web's `★ 4.5 (123) · $$` + "Full service" pill;
  the map card's bottom padding went 12 → 38 so it no longer
  half-covers the Apple Maps attribution. Uploaded by workflow run
  [40391127960](https://github.com/croix153/neutral-eats/actions/runs/40391127960),
  upload succeeded (altool, unmasked); ASC id
  `65c6a5db-9d54-4142-89ae-7682a0ceda17`, VALID;
  `usesNonExemptEncryption=false` declared and attached to Internal
  Testers via `asc_build.py`; `internalBuildState =
  IN_BETA_TESTING` (API-verified). On-device checks are Croix's.
- **Build 1.0 (6)** — Map-state bottom-fill fix (commit `13211cb`):
  Croix's build-5 verdict was "much better", but in Map state the
  map stopped at the bottom safe-area boundary, leaving a dead
  black band under the "places near this spot" card (the list
  layer had `.ignoresSafeArea(edges: .bottom)`; the map layer
  never did). `VenueMapView` now ignores the bottom safe area so
  the map runs full-bleed to the physical screen bottom, and the
  card — still in the safe-area-aware layout — sits at safe-area
  inset + 12pt, just above the home indicator. Uploaded by
  workflow run
  [40365103128](https://github.com/croix153/neutral-eats/actions/runs/40365103128),
  all steps green; upload log *"UPLOAD SUCCEEDED with no errors"*,
  delivery UUID `c05286fa-9907-461d-a41d-2c926e2c2636` (the build's
  ASC id), arriving already VALID; `usesNonExemptEncryption=false`
  declared via API; attached to Internal Testers;
  `internalBuildState = IN_BETA_TESTING` (API-verified). On-device
  confirmation of the fill is Croix's test.
- **Build 1.0 (5)** — the two-state Map/List redesign (commit
  `bbdb700`): uploaded by workflow run
  [40361504905](https://github.com/croix153/neutral-eats/actions/runs/40361504905),
  all steps green; the upload step's log reads *"UPLOAD SUCCEEDED
  with no errors"*, delivery UUID
  `3a4ad178-f158-40a3-8b8d-03c80767c685` (the build's ASC id). Took
  ~12 minutes to become visible in ASC, arriving already VALID;
  `usesNonExemptEncryption=false` declared via API; attached to
  Internal Testers; `internalBuildState = IN_BETA_TESTING`
  (API-verified). On-device feel is UNVERIFIED until Croix
  installs it from TestFlight.
- **Build 1.0 (4)**: uploaded by workflow run
  [40354341480](https://github.com/croix153/neutral-eats/actions/runs/40354341480)
  (attempt 2; attempt 1 was cancelled in GitHub's queue — macOS arm64
  capacity, "job was not acquired by Runner of type hosted"). All
  steps green, and the upload step's own log reads *"UPLOAD SUCCEEDED
  with no errors"*, delivery UUID
  `f829f816-9df0-4d6d-976a-26820fecc9a5` (the build's ASC id).
- Built with **Xcode 26.6 / iPhoneOS 26.5 SDK** on the `macos-26`
  runner. The earlier `macos-14` pin (Xcode 15.4, iOS 17.5 SDK) built
  fine but Apple rejected the upload (run 40351906981) — uploads now
  require the iOS 26 SDK. Fixed in commit `efc7e3e`, which also
  removed `continue-on-error` from the upload step: its failure had
  been masking as a green run.
- ASC processing: build state **VALID**;
  `usesNonExemptEncryption=false` declared via API; build attached
  to the **Internal Testers** group
  (`bd9e8edd-c932-480e-9f8f-253229e45049`); build beta detail
  `internalBuildState = IN_BETA_TESTING`; Croix's tester state
  flipped NOT_INVITED → **INVITED**.

Earlier history: first CI build (run 40346265387) archived/exported/
verified cleanly (`.ipa` stashed at
`~/workspace/croixbrains-signing/NeutralEats-1.0-run2.ipa`) but could
not upload because the app record did not exist yet; the very first
attempt (run 40346053117) failed on a missing `SDKROOT = iphoneos`,
fixed in commit b687167.

## Shipping the next build

1. Dispatch `.github/workflows/ios.yml` (build number = workflow
   run number; an upload failure now fails the run honestly).
2. When the build shows VALID in ASC, declare export compliance and
   attach it to Internal Testers via the ASC API:
   `PATCH /v1/builds/{id}` with `usesNonExemptEncryption=false`,
   then `POST /v1/betaGroups/bd9e8edd-c932-480e-9f8f-253229e45049/relationships/builds`.

## The one manual step (done)

The ASC API cannot create the **app record** (POST /v1/apps returns
403 for any API key — proven with Creams), so the record was created
once in App Store Connect's web UI on 2026-10-26 (name "neutral
eats" was available; SKU `neutraleats-ios`). Nothing else in the
pipeline needs the web UI.
