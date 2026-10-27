#!/bin/bash
# Neutral Eats — App Store screenshot capture (simulator).
#
# Captures the five packet shots (appstore-submission-packet.md,
# "Screenshots still needed") on the largest iPhone simulator the
# runner offers — the 6.9" class, 1320x2868. Same pattern as the
# duo-check job: unsigned Debug build, fresh device, location
# pre-granted and pinned to Winter Park, FL (28.5967,-81.3647),
# captures via `simctl io screenshot`.
#
# Card states are driven by DEBUG-only launch-argument hooks in
# ContentView.swift (#if DEBUG — Release/TestFlight builds compile
# them out entirely):
#   (no args)              summary card
#   -DuoCheckList          list form
#   -DuoCheckDetail        detail form (first = nearest venue)
#   -AppStoreSearch <q>    search applied via the normal onChange
#                          path, results list expanded
# Night is NOT a hook: the theme preference is .auto on a fresh
# install and follows the system, so `simctl ui appearance dark`
# is the mechanism (the capture proves or refutes it).
#
# Blank-frame guard: the duo-check run caught one transient blank
# detail frame (a ~60 KB all-white PNG where a rendered MapKit
# frame is ~1 MB+). Every capture here is size-checked; a frame
# under MINBYTES is re-captured in the SAME session (the duo
# evidence showed the same process renders fine moments later),
# up to 3 attempts, keeping the largest frame.
#
# CAPTURE ONLY: nothing is signed for distribution, nothing is
# uploaded to App Store Connect. PNGs land in $OUT for artifact
# download and human review.

set -uo pipefail

OUT="${1:-appstore-screenshots/results}"
mkdir -p "$OUT"
LOG="$OUT/screenshots-run.log"
exec > >(tee -a "$LOG") 2>&1

BUNDLE="ai.croix.neutraleats"
LAT="28.5967"; LON="-81.3647"   # Winter Park, FL — dense venue area
DD="${RUNNER_TEMP:-/tmp}/asc-shots-dd"
APP="$DD/Build/Products/Debug-iphonesimulator/NeutralEats.app"
MINBYTES=120000

say() { echo; echo "##### $*"; }
note() { echo "[asc-shots] $*"; }

say "inventory"
xcodebuild -version || true
xcrun simctl list runtimes | grep -E "iOS" || true
note "iPhone device types on this runner:"
xcrun simctl list devicetypes | grep -E "iPhone" || true

say "API reachability probe (runner -> production API, Winter Park bbox)"
curl -s --max-time 20 "https://neutraleats.com/api/venues.php?south=28.55&west=-81.42&north=28.65&east=-81.31&limit=3" \
  | head -c 300 || echo "curl failed"
echo
note "taco bell probe in a Winter Park viewport bbox:"
curl -s --max-time 20 "https://neutraleats.com/api/venues.php?south=28.5692&west=-81.3922&north=28.6242&east=-81.3372&limit=500&search=taco%20bell" \
  | head -c 300 || echo "curl failed"
echo

say "build (Debug, iphonesimulator, unsigned)"
xcodebuild build \
  -project ios/NeutralEats.xcodeproj \
  -scheme NeutralEats \
  -configuration Debug \
  -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath "$DD" \
  CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO 2>&1 | tee "$OUT/build.log" | tail -4
if [ ! -d "$APP" ]; then
  note "BUILD FAILED — no .app at $APP"
  exit 1
fi
note "built: $APP"

RUNTIME="$(xcrun simctl list runtimes | grep -E "^iOS" | tail -1 | sed -E 's/.* - (com\.apple[^ ]*) *$/\1/')"
note "using runtime: $RUNTIME"

say "device"
UDID=""; DTYPE=""
for cand in "iPhone 17 Pro Max" "iPhone 16 Pro Max" "iPhone 17 Pro" "iPhone 16 Pro" "iPhone Air" "iPhone 17"; do
  UDID="$(xcrun simctl create "AppStoreShots" "$cand" "$RUNTIME" 2>/dev/null)" && { DTYPE="$cand"; break; }
  note "create failed for $cand"
done
if [ -z "$UDID" ]; then note "NO DEVICE COULD BE CREATED"; exit 1; fi
note "created $DTYPE -> $UDID"
xcrun simctl boot "$UDID" 2>/dev/null || true
xcrun simctl bootstatus "$UDID" -b >/dev/null 2>&1 || note "bootstatus timed out (continuing)"
xcrun simctl location "$UDID" set "$LAT,$LON" || note "location set failed"
xcrun simctl install "$UDID" "$APP" || { note "INSTALL FAILED"; exit 1; }
xcrun simctl privacy "$UDID" grant location "$BUNDLE" || note "privacy grant failed"
xcrun simctl ui "$UDID" appearance light >/dev/null 2>&1 || note "appearance light failed"

capture() { # final-filename settle-seconds [launch args...]
  local name="$1" settle="$2"; shift 2
  xcrun simctl terminate "$UDID" "$BUNDLE" >/dev/null 2>&1 || true
  sleep 1
  xcrun simctl launch "$UDID" "$BUNDLE" "$@" >/dev/null 2>&1 || note "LAUNCH FAILED $name"
  sleep "$settle"
  local tmp="$OUT/.tmp-$name.png" size=0 bestsize=0
  for try in 1 2 3; do
    xcrun simctl io "$UDID" screenshot "$tmp" 2>/dev/null || true
    size=0; [ -f "$tmp" ] && size=$(stat -f%z "$tmp" 2>/dev/null || echo 0)
    note "$name attempt $try: $size bytes"
    if [ "$size" -gt "$bestsize" ]; then bestsize=$size; cp "$tmp" "$OUT/$name" 2>/dev/null; fi
    [ "$size" -ge "$MINBYTES" ] && break
    note "$name frame under $MINBYTES bytes — likely blank; waiting, re-capturing same session"
    sleep 6
  done
  rm -f "$tmp"
  if [ -f "$OUT/$name" ]; then
    echo -n "FINAL $name: "
    sips -g pixelWidth -g pixelHeight "$OUT/$name" 2>/dev/null | grep -E "pixel" | awk '{print $2}' | paste -sd'x' -
    note "$name final size: $bestsize bytes"
  else
    note "CAPTURE FAILED for $name"
  fi
}

say "captures — day"
# Warm-up launch (discarded): the FIRST launch on a fresh device
# can frame-grab an unloaded map with a settled-but-empty store
# (cold tile cache + the launch centering race) — run 40555790427's
# first 01-summary.png caught exactly that, while every later
# launch rendered fully. One full launch cycle first warms the
# tile cache and the first-fetch path; the real captures follow.
note "warm-up launch (no capture kept)"
xcrun simctl launch "$UDID" "$BUNDLE" >/dev/null 2>&1 || note "warm-up launch failed"
sleep 20
xcrun simctl terminate "$UDID" "$BUNDLE" >/dev/null 2>&1 || true
sleep 1
capture 01-summary.png 20
capture 02-list.png 12 -DuoCheckList
capture 03-detail.png 16 -DuoCheckDetail
capture 05-search.png 20 -AppStoreSearch "taco bell"

say "captures — night (system appearance dark; fresh-install theme preference is .auto -> follows system)"
xcrun simctl ui "$UDID" appearance dark || note "appearance dark FAILED"
sleep 1
capture 04-night.png 16
xcrun simctl ui "$UDID" appearance light >/dev/null 2>&1 || true

say "liveness + crashes"
xcrun simctl spawn "$UDID" launchctl list 2>/dev/null | grep -i "neutraleats" \
  || echo "launchctl: no neutraleats job listed (inconclusive on its own)"
find "$HOME/Library/Logs/DiagnosticReports" \
     "$HOME/Library/Developer/CoreSimulator/Devices/$UDID/data/Library/Logs" \
     -type f \( -iname "*neutraleats*" -o -iname "*neutral eats*" \) -mmin -120 2>/dev/null \
  | while read -r f; do echo "crash report: $f"; done
echo "(no lines above = no NeutralEats crash reports)"

xcrun simctl shutdown "$UDID" >/dev/null 2>&1 || true
xcrun simctl delete "$UDID" >/dev/null 2>&1 || true

say "final files"
for f in 01-summary.png 02-list.png 03-detail.png 04-night.png 05-search.png; do
  if [ -f "$OUT/$f" ]; then
    dims="$(sips -g pixelWidth -g pixelHeight "$OUT/$f" 2>/dev/null | grep -E "pixel" | awk '{print $2}' | paste -sd'x' -)"
    echo "$f  $dims  $(stat -f%z "$OUT/$f") bytes"
  else
    echo "$f  MISSING"
  fi
done
note "screenshot capture complete (device was: $DTYPE, runtime: $RUNTIME)"
