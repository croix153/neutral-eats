# neutral eats — iOS app

Native SwiftUI + MapKit app (no web wrapper), v1 parity with
`web/preview.html`: dark Tokyo-palette map with venue dots (pink,
selected cyan), brand header + search + cuisine/type chips, a
three-stop bottom sheet with the distance-ranked list, venue detail
with Call / Website / Directions and the data-source line, and
Near-me (the only place location permission is asked — in context).

- Bundle ID: `ai.croix.neutraleats` — display name **neutral eats** (all lowercase)
- Minimum iOS 16.0, iPhone, no third-party dependencies
- Data: production API `https://neutraleats.com/api/venues.php`
  (same params/envelope as the web preview; ranking is re-sorted to
  pure distance client-side — neutrality is the product)

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
