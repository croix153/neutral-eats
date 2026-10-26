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

## Status (2026-10-26)

First CI build **succeeded** — run
[40346265387](https://github.com/croix153/neutral-eats/actions/runs/40346265387)
(48 s): archived, exported, and verified (bundleId
`ai.croix.neutraleats`, displayName `neutral eats`, minOS 16.0,
location string present, signature `iPhone Distribution: Roger
Newson (A4NAM9AA6M)`). The `.ipa` (314,340 bytes) is the run's
`neutraleats-ios-ipa` artifact and is also stashed at
`~/workspace/croixbrains-signing/NeutralEats-1.0-run2.ipa`. The
upload step failed with exactly the expected error — *"No suitable
application records were found"* — i.e. only the app record below is
missing. (First attempt, run 40346053117, failed on a missing
`SDKROOT = iphoneos`; fixed in commit b687167.)

## The one manual step

The ASC API cannot create the **app record** (POST /v1/apps returns
403 for any API key — proven with Creams). Until the record for
`ai.croix.neutraleats` is created once in App Store Connect's web UI
(name "neutral eats", SKU e.g. `neutraleats-ios`), the workflow's
upload step fails with Apple's "no application records found" error
(it is `continue-on-error`; the verified .ipa is still produced).
After the record exists: re-dispatch the workflow, then declare
export compliance (`usesNonExemptEncryption=false`) and attach the
build to the "Internal Testers" group via the ASC API.

Possible wrinkle: ASC app *names* are globally unique — if "neutral
eats" is already taken by another developer, the record will need a
variant name (Creams became "Creams for Teams"). The in-app display
name stays "neutral eats" regardless.
