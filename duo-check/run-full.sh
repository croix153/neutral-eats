#!/bin/bash
# Neutral Eats — iPhone Duo check, full phase.
#
# FINDING FROM THE INVENTORY PHASE (same job, results/inventory.txt):
# the hosted macos-26 runner (image 20261021.0445.8) tops out at
# Xcode 26.6 / iOS 26.5 runtimes. There is NO iOS 27 runtime and NO
# iPhone Duo (or any foldable) device type on the box — `simctl list`
# has zero duo/fold matches. The iPhone Duo requires iOS 27, so a
# true Duo simulation cannot run here yet.
#
# Per the check plan, this script therefore runs the FALLBACK:
# the same unsigned Debug build on the two closest size-class
# approximations, clearly labeled APPROXIMATION everywhere:
#   compact -> iPhone 13 mini (5.4" — same diagonal as the Duo cover
#              display, but tall 19.5:9 instead of the Duo's squat
#              4:3; shortest modern iPhone canvas class available)
#   large   -> iPad mini (A17 Pro) (8.3" tablet vs the Duo's 7.6"
#              inner display; the iPhone-only app runs in iPad
#              compatibility mode)
#
# Card states are driven with the DEBUG-only launch-argument hook in
# ContentView.swift (-DuoCheckList / -DuoCheckDetail; #if DEBUG, so
# Release/TestFlight builds are untouched). Location is pre-granted
# and pinned to Winter Park, FL (28.5967,-81.3647) — dense pins.
#
# Resize-storm approximation: there is no fold to toggle. The script
# tries, in order, (1) `simctl ui orientation`, (2) Simulator.app
# rotation via AppleScript, (3) `simctl io screenConfig geometry`
# mode switches — verifies each by screenshot pixel dimensions, uses
# the first mechanism that demonstrably changes the canvas, and runs
# 5 cycles with the populated map. Whatever mechanism (if any) was
# used is logged verbatim; if none works, transitions are reported
# as NOT tested rather than implied.
#
# This script is a measurement tool: failures are findings. It only
# hard-fails if the build itself fails.

set -uo pipefail

OUT="${1:-duo-check/results}"
mkdir -p "$OUT"
LOG="$OUT/full-run.log"
exec > >(tee -a "$LOG") 2>&1

BUNDLE="ai.croix.neutraleats"
LAT="28.5967"; LON="-81.3647"   # Winter Park, FL — dense venue area
DD="${RUNNER_TEMP:-/tmp}/duo-dd"
APP="$DD/Build/Products/Debug-iphonesimulator/NeutralEats.app"

say() { echo; echo "##### $*"; }
note() { echo "[duo-check] $*"; }

say "toolchain"
xcodebuild -version || true
xcrun simctl list runtimes | grep -E "iOS" || true
note "Duo re-check on this runner:"
{ xcrun simctl list devicetypes; xcrun simctl list runtimes; } | grep -iE "duo|fold" \
  || note "confirmed: no Duo/foldable device type, no iOS 27 runtime — FALLBACK MODE"

say "API reachability probe (runner -> production API, Winter Park bbox)"
curl -s --max-time 20 "https://neutraleats.com/api/venues.php?south=28.55&west=-81.42&north=28.65&east=-81.31&limit=3" \
  | head -c 400 || echo "curl failed"
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
note "DuoCheck hook present in Debug binary:"
strings "$APP/NeutralEats" 2>/dev/null | grep -E "DuoCheck(List|Detail)" | sort -u || echo "hook strings NOT found"

RUNTIME="$(xcrun simctl list runtimes | grep -E "^iOS" | tail -1 | sed -E 's/.* - (com\.apple[^ ]*) *$/\1/')"
note "using runtime: $RUNTIME"

shot() { # udid outfile
  xcrun simctl io "$1" screenshot "$2" 2>/dev/null \
    && sips -g pixelWidth -g pixelHeight "$2" 2>/dev/null | grep -E "pixel" | tr '\n' ' ' && echo "<- $2" \
    || echo "SCREENSHOT FAILED: $2"
}

app_alive() { # udid -> echoes evidence
  local udid="$1"
  xcrun simctl spawn "$udid" launchctl list 2>/dev/null | grep -i "neutraleats" \
    || echo "launchctl: no neutraleats job listed (inconclusive on its own)"
}

collect_crashes() { # udid label
  local udid="$1" label="$2"
  local dest="$OUT/crashes-$label"
  mkdir -p "$dest"
  find "$HOME/Library/Logs/DiagnosticReports" \
       "$HOME/Library/Developer/CoreSimulator/Devices/$udid/data/Library/Logs" \
       -type f \( -iname "*neutraleats*" -o -iname "*neutral eats*" \) -mmin -90 2>/dev/null \
    | while read -r f; do cp "$f" "$dest/" && echo "crash report: $f"; done
  ls "$dest" | grep -q . || echo "no NeutralEats crash reports found for $label"
}

run_device() { # label, then candidate device-type names
  local label="$1"; shift
  say "device class: $label (candidates: $*)"
  local udid="" dtype=""
  for cand in "$@"; do
    udid="$(xcrun simctl create "DuoCheck-$label" "$cand" "$RUNTIME" 2>/dev/null)" && { dtype="$cand"; break; }
    note "create failed for $cand"
  done
  if [ -z "$udid" ]; then note "ALL CANDIDATES FAILED for $label"; return 1; fi
  note "created $dtype -> $udid"
  xcrun simctl boot "$udid" 2>/dev/null || true
  xcrun simctl bootstatus "$udid" -b >/dev/null 2>&1 || note "bootstatus timed out (continuing)"
  xcrun simctl location "$udid" set "$LAT,$LON" || note "location set failed"
  xcrun simctl install "$udid" "$APP" || { note "INSTALL FAILED $label"; return 1; }
  xcrun simctl privacy "$udid" grant location "$BUNDLE" || note "privacy grant failed"
  xcrun simctl io "$udid" enumerate > "$OUT/$label-io-enumerate.txt" 2>&1 || true

  # --- state captures ---
  capture() { # state-name, settle-seconds, [launch args...]
    local name="$1" settle="$2"; shift 2
    xcrun simctl terminate "$udid" "$BUNDLE" >/dev/null 2>&1 || true
    sleep 1
    xcrun simctl launch "$udid" "$BUNDLE" "$@" >/dev/null 2>&1 || note "LAUNCH FAILED $label-$name"
    sleep "$settle"
    shot "$udid" "$OUT/$label-$name.png"
  }
  capture summary 16
  capture list 10 -DuoCheckList
  capture detail 12 -DuoCheckDetail

  # --- resize-storm approximation ---
  say "resize storm on $label"
  xcrun simctl help ui > "$OUT/$label-simctl-ui-help.txt" 2>&1 || true
  cat "$OUT/$label-simctl-ui-help.txt" | head -30
  xcrun simctl launch "$udid" "$BUNDLE" >/dev/null 2>&1 || true
  sleep 10   # populated map, summary state
  shot "$udid" "$OUT/$label-storm-before.png"
  base_dims="$(sips -g pixelWidth -g pixelHeight "$OUT/$label-storm-before.png" 2>/dev/null | grep -E "pixel" | awk '{print $2}' | paste -sd'x' -)"
  note "canvas before storm: $base_dims"

  mech="none"
  # Mechanism 1: simctl ui orientation
  if xcrun simctl ui "$udid" orientation landscape >/dev/null 2>&1; then
    sleep 2
    shot "$udid" "$OUT/$label-storm-probe.png"
    d="$(sips -g pixelWidth -g pixelHeight "$OUT/$label-storm-probe.png" 2>/dev/null | grep -E "pixel" | awk '{print $2}' | paste -sd'x' -)"
    if [ -n "$d" ] && [ "$d" != "$base_dims" ]; then mech="simctl-ui-orientation"; fi
    xcrun simctl ui "$udid" orientation portrait >/dev/null 2>&1 || true
    sleep 2
  fi
  note "after simctl-ui probe: mech=$mech"
  # Mechanism 2: Simulator.app rotation via AppleScript keystroke
  if [ "$mech" = "none" ]; then
    open -a Simulator >/dev/null 2>&1 || true
    sleep 4
    timeout 25 osascript \
      -e 'tell application "Simulator" to activate' \
      -e 'delay 1' \
      -e 'tell application "System Events" to keystroke (ASCII character 29) using {command down}' \
      >/dev/null 2>&1 || note "osascript rotate attempt failed/blocked"
    sleep 2
    shot "$udid" "$OUT/$label-storm-probe.png"
    d="$(sips -g pixelWidth -g pixelHeight "$OUT/$label-storm-probe.png" 2>/dev/null | grep -E "pixel" | awk '{print $2}' | paste -sd'x' -)"
    if [ -n "$d" ] && [ "$d" != "$base_dims" ]; then mech="osascript-simulator-rotate"; fi
    note "after osascript probe: mech=$mech (dims=$d)"
  fi
  # Mechanism 3: screenConfig geometry mode switch
  if [ "$mech" = "none" ]; then
    modes="$(grep -oE "[0-9]{3,4}x[0-9]{3,4}" "$OUT/$label-io-enumerate.txt" 2>/dev/null | sort -u | head -4)"
    note "io enumerate geometries seen: ${modes:-none parsed}"
    for g in $modes; do
      if [ "${g}" != "${base_dims}" ] && xcrun simctl io "$udid" screenConfig geometry "$g" >/dev/null 2>&1; then
        sleep 2
        shot "$udid" "$OUT/$label-storm-probe.png"
        d="$(sips -g pixelWidth -g pixelHeight "$OUT/$label-storm-probe.png" 2>/dev/null | grep -E "pixel" | awk '{print $2}' | paste -sd'x' -)"
        if [ -n "$d" ] && [ "$d" != "$base_dims" ]; then mech="simctl-io-screenConfig-geometry($g)"; break; fi
      fi
    done
    note "after screenConfig probe: mech=$mech"
  fi

  if [ "$mech" != "none" ]; then
    note "running 5 resize cycles via $mech"
    for i in 1 2 3 4 5; do
      case "$mech" in
        simctl-ui-orientation)
          xcrun simctl ui "$udid" orientation landscape >/dev/null 2>&1; sleep 2
          xcrun simctl ui "$udid" orientation portrait  >/dev/null 2>&1; sleep 2 ;;
        osascript-simulator-rotate)
          timeout 25 osascript -e 'tell application "System Events" to keystroke (ASCII character 29) using {command down}' >/dev/null 2>&1 || true; sleep 2
          timeout 25 osascript -e 'tell application "System Events" to keystroke (ASCII character 28) using {command down}' >/dev/null 2>&1 || true; sleep 2 ;;
        simctl-io-screenConfig-geometry*)
          g2="$(echo "$mech" | sed -E 's/.*geometry\(([0-9x]+)\).*/\1/')"
          xcrun simctl io "$udid" screenConfig geometry "$g2" >/dev/null 2>&1; sleep 2
          # back to the first/original mode is unknown; toggle handled by enumerate order — best effort
          xcrun simctl io "$udid" screenConfig geometry "$(echo "$modes" | head -1)" >/dev/null 2>&1; sleep 2 ;;
      esac
      note "cycle $i done"
    done
  else
    note "NO working headless resize mechanism on this runner — transitions NOT tested"
  fi

  shot "$udid" "$OUT/$label-after-storm.png"
  note "liveness after storm:"
  app_alive "$udid"
  collect_crashes "$udid" "$label"
  xcrun simctl shutdown "$udid" >/dev/null 2>&1 || true
  xcrun simctl delete "$udid" >/dev/null 2>&1 || true
}

run_device compact "iPhone 13 mini" "iPhone SE (3rd generation)" "iPhone 16e"
run_device large "iPad mini (A17 Pro)" "iPad mini (6th generation)" "iPad Air 11-inch (M4)"

say "results"
ls -la "$OUT"
note "full phase complete"
