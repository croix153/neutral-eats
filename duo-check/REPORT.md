# iPhone Duo rendering check — Neutral Eats

**Date:** 2026-10-27 · **Workflow:** `.github/workflows/duo-check.yml` (new, dispatch-only, simulator-only; `ios.yml` untouched, nothing signed, nothing uploaded to App Store Connect)
**Runs:** inventory [40551137582](https://github.com/croix153/neutral-eats/actions/runs/40551137582) · full [40551653643](https://github.com/croix153/neutral-eats/actions/runs/40551653643)
**Commits:** `ebc7491` (workflow + inventory script), `db14e33` (full-run script + DEBUG hook)

## Bottom line

- **The iPhone Duo itself: COULD NOT VERIFY.** The hosted `macos-26` runner has no iOS 27 runtime and no Duo (or any foldable) device type — its newest Xcode is 26.6 and the Duo needs iOS 27. Evidence in §1.
- **Fallback approximations ran instead** (per plan step 4): iPhone 13 mini as the cover-size approximation, iPad mini (A17 Pro) running the iPhone app in compatibility mode as the large-canvas approximation. **Every card state rendered correctly on both, with a populated dense-area map; zero crashes; zero crash reports.**
- **Fold/unfold transitions: COULD NOT VERIFY.** No headless posture/rotation mechanism exists on this runner — all three attempted mechanisms failed, proven by byte-identical screenshot dimensions across every probe. This is the top open risk for the real device, because fold transitions are resize storms aimed at the app's historically fragile MapKit annotation path.

## 1. Why there is no Duo verdict — runner evidence

From `inventory.txt` (full dump committed alongside this report):

- Runner image `macos26 / 20261021.0445.8`, host macOS **26.6.2** (25G83).
- Xcodes installed: 26.0.1 → **26.6** (selected; build 17F113). Simulator.app 16.0. **No Xcode 27.**
- Runtimes: iOS **26.2 / 26.4.1 / 26.5** — **no iOS 27 runtime**.
- Device types: newest phones are the iPhone 17 family; a grep for `duo|fold` across device types, runtimes and devices returns **"NO duo/fold matches in simctl lists"**.
- The full-phase script re-checked at run time and entered fallback mode on the same evidence.

This is an environment limit, not an app result: the Duo launched 2026-10-23 with iOS 27, and GitHub's hosted image predates iOS 27 simulator support.

## 2. Method (fallback run)

- Unsigned **Debug** build for `iphonesimulator` (`CODE_SIGNING_ALLOWED=NO`) — **BUILD SUCCEEDED** (`build.log`).
- Devices created fresh on the iOS 26.5 runtime: iPhone 13 mini (capture canvas 1080×2340) and iPad mini (A17 Pro) (canvas 1488×2266; the iPhone-only app runs inside a floating compatibility window — see §4).
- Location pre-granted (`simctl privacy grant location`) and pinned to **Winter Park, FL (28.5967, −81.3647)** — dense pins. Captures confirm the app centered on the user dot there with 500+ venues loaded and distances measured from the user (nearest venue: 10 ft).
- **Card states were driven by a DEBUG-only launch-argument hook added to `ios/NeutralEats/ContentView.swift`** — `-DuoCheckList` expands the card, `-DuoCheckDetail` selects the first loaded venue (detail form + the animated street-zoom snap). It is wrapped in `#if DEBUG` with an explanatory comment: Release/TestFlight builds compile it out entirely, and no shipping behavior changed. (The run's `strings` probe for the hook literals reported "not found" — a false negative of that probe; Swift doesn't surface these short literals to `strings`. The hook's firing is proven behaviorally: list and detail states were reached with no touch input.)
- Screenshots: `simctl io screenshot` at native resolution.
- Resize mechanisms attempted in order, each **verified by screenshot pixel dimensions**: (1) `simctl ui orientation` — Xcode 26.6's `simctl ui` supports only `appearance` and `increase_contrast` (help text committed as `*-simctl-ui-help.txt`); (2) Simulator.app rotation via AppleScript keystroke — **blocked (TCC)** on the hosted runner; (3) `simctl io screenConfig geometry` — each device exposes a single integrated display with no alternate geometry modes (`*-io-enumerate.txt`). No mechanism changed the canvas → no cycles could be run → transitions reported as not tested, on evidence.

## 3. Captures and per-state verdicts — APPROXIMATIONS, not Duo verification

| Capture | Shows | Verdict |
|---|---|---|
| `compact-summary.png` | 13 mini, summary card over dense Winter Park map; Raleway wordmark, header, chips (last chip edge-clipped by the horizontal scroll, by design), user dot centered, cluster bubbles + dots, "500+ places in viewport", Near me in its authorized state | **Renders fine** |
| `compact-list.png` | Card expanded (68% of region): headline, full honesty tagline, 500-cap note, distance-ranked rows (Sixty Vines 10 ft, Bulla Gastrobar 30 ft, Kona Grill 120 ft, The Glass Knife 280 ft) with ratings/prices, list continuing below the fold | **Renders fine** |
| `compact-detail.png` | ⚠️ Blank white frame — see §3.1 | **Anomaly (bounded)** |
| `compact-after-storm.png` | ~1 min after the blank capture, same app session, no relaunch-with-args in between: **detail state fully rendered** — Sixty Vines card (rating, cuisine, address, "10 ft from you", Call / No website / Directions, source line), map snapped to street zoom, selected venue's label in the vermillion accent | **Renders fine** |
| `large-summary.png` | iPad mini canvas; app in a floating phone-proportioned compatibility window over the iPad desktop; summary state identical inside the window | **Renders fine** (compat-window caveat, §4) |
| `large-list.png` | List form in the compat window; 3 full rows visible (window is shorter in points than the 13 mini's canvas) | **Renders fine** |
| `large-detail.png`, `large-after-storm.png` | Detail fully rendered (Sixty Vines, all meta, action buttons, source line). The build-20 **hours row is correctly absent** — this venue has no OSM hours and the row is hidden-when-empty by design | **Renders fine** |
| `*-storm-before/probe/after-storm.png` | Byte-identical within each device (md5 `a4f32c44…` compact, `b975df22…` large) — the canvas never changed because no resize mechanism worked; frames show the still-open detail state | **Transitions: could not verify** |

Liveness and crashes: at the end of each device pass, `launchctl list` inside the simulator showed `UIKitApplication:ai.croix.neutraleats` with a live PID, and the final frames show the app (not SpringBoard, not a crash dialog). A sweep of the host's and both devices' DiagnosticReports found **zero NeutralEats crash reports**.

### 3.1 The blank compact-detail capture

`compact-detail.png` (17:38 UTC) is a pure-white frame with only a status bar, taken 12 s after the `-DuoCheckDetail` launch. Three facts bound it:

1. **No crash report exists** for the app on that device.
2. **The same process rendered the detail state correctly ~1 minute later** without being terminated or relaunched with arguments (`compact-storm-before.png` and its byte-identical successors). Had the app crashed and been relaunched by the plain `simctl launch` in the storm phase, it would have come up on the summary state — it came up still holding the Sixty Vines selection.
3. The identical detail launch rendered correctly on the large canvas.

The explanation most consistent with all three: a transient blank frame caught while the animated street-zoom snap, annotation re-dress and refetch cascade was still settling on the @3x canvas in the densest cluster in the dataset (Winter Park's Orlando Ave). The 12 s settle makes that surprising, but the crash and hang alternatives are refuted by (1) and (2). **Recorded as an anomaly to watch, not a verified defect.** A focused re-run (detail captures at +12 s and +20 s, `simctl diagnose` on a repeat) would settle it definitively.

## 4. What the approximations do and don't say about the real Duo

- **Folded (cover, 5.4″, 4:3):** the 13 mini matches the diagonal but is tall 19.5:9; the Duo cover is shorter and wider in points. The layout's only height-sensitive pieces are the map region (shrinks gracefully — fixed header, card overlaid at the bottom) and the list form (68% of region height → fewer rows on a shorter canvas). No fixed-height content exists that could clip. Inference: renders fine with less map visible. **Inference, not capture.**
- **Unfolded (inner, 7.6″):** on the real Duo — an iPhone — the app runs **full-screen**, not in the iPad-style compatibility window the large captures show (that window is iPadOS behavior for iPhone-only apps). The layout is constraint-driven (fixed header, map fills, card anchored to the bottom), so it should stretch: more map, more list rows. **Inference, not capture** — the full-bleed wide-canvas state was never rendered anywhere in this check.
- **Transitions:** nothing learned. On-device, fold/unfold will hammer `regionDidChange` + annotation sync exactly as the build-13 crash did; the build-15+ mitigations (deferred/coalesced syncs, birth-only clustering dress) are the defense, and Croix's build-20 dense-area retest remains the best available proxy until a Duo can be driven.

## 5. Observations (pre-existing, not size-class defects)

- The summary card's honesty tagline **truncates with an ellipsis** at phone width ("Ranked by distance. Nothing is sponsor…") — the build-18 design (lineLimit(1), scale floor 0.75, never wrap). In the list form the same line fits in full. On the Duo's wider 4:3 cover it may fit fully; unverifiable here.
- At street zoom after the snap, **venue name labels overlap** in the dense Orlando Ave cluster (e.g. Lakeside Harvest / Nektar Juice Bar Café / Shake Shack), identically on both canvases — the app's existing label-density behavior at the snap span, independent of screen size.

## 6. ASC screenshot display type — OPEN QUESTION

Whether App Store Connect offers a Duo/foldable screenshot display type for this app's version **could not be determined cheaply**: the ASC API exposes no endpoint enumerating `screenshotDisplayType` values, and Apple's public OpenAPI spec document no longer downloads as JSON (the developer.apple.com URLs return HTML shells). **No ASC writes of any kind were made.** Resolve during the ASC entry step — and note that if ASC does require Duo screenshots, this report's iOS 26 approximation captures would not satisfy it; an iOS 27-capable runner would be needed.

## 7. What unblocks a true Duo verdict

1. GitHub shipping Xcode 27 / an iOS 27 runtime on its macOS images — then re-dispatch `duo-check.yml`. `run-inventory.sh` will prove availability; `run-full.sh` currently implements the fallback branch and needs a Duo branch (same shape: create/boot/install/capture, posture via whatever the iOS 27 simctl exposes) added at that point.
2. A physical iPhone Duo (Croix does not own one).
3. Any local Mac with Xcode 27 — the scripts run outside CI as-is (`RUNNER_TEMP` unset → `/tmp`).

## Files in this directory

- `REPORT.md` — this report · `inventory.txt` — phase-1 runner inventory · `full-run.log` / `build.log` — phase-2 logs
- `compact-*.png` / `large-*.png` — the captures analyzed above · `*-io-enumerate.txt`, `*-simctl-ui-help.txt` — mechanism evidence
- `run-inventory.sh`, `run-full.sh` — the scripts that produced them
