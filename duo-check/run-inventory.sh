#!/bin/bash
# Neutral Eats — iPhone Duo simulator check: environment inventory.
#
# Dumps everything needed to decide HOW to run the Duo check on the
# hosted macos-26 runner: Xcode version, simctl device types and
# runtimes (is there an iPhone Duo? an iOS 27 runtime?), and the full
# simctl help surface (io / privacy / location subcommands) so the
# posture-change mechanism can be chosen from facts, not guesses.
#
# Output: everything is tee'd to $OUT/inventory.txt and individual
# sections are also saved as separate files in $OUT for the artifact.
# This script never fails the job on a missing probe — a missing
# probe IS a finding.

set -uo pipefail

OUT="${1:-duo-check/results}"
mkdir -p "$OUT"
INV="$OUT/inventory.txt"
: > "$INV"

section() { echo; echo "===== $* ====="; }
log() { echo "$@" | tee -a "$INV"; }

{
section "host"
sw_vers || true
uname -a || true
echo "runner: ${RUNNER_OS:-?} / ${ImageOS:-?} / ${ImageVersion:-?}"

section "xcode"
xcode-select -p || true
xcodebuild -version || true
ls /Applications | grep -i xcode || true
XCODE_APP="$(xcode-select -p | sed 's|/Contents/Developer||')"
echo "Xcode app: $XCODE_APP"
if [ -n "$XCODE_APP" ] && [ -f "$XCODE_APP/Contents/Info.plist" ]; then
  /usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "$XCODE_APP/Contents/Info.plist" 2>/dev/null || true
fi
SIMAPP="$XCODE_APP/Contents/Developer/Applications/Simulator.app"
if [ -d "$SIMAPP" ]; then
  echo "Simulator.app present: $SIMAPP"
  /usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "$SIMAPP/Contents/Info.plist" 2>/dev/null || true
else
  echo "Simulator.app NOT found at $SIMAPP"
fi

section "simctl runtimes"
xcrun simctl list runtimes

section "simctl devicetypes (full -> devicetypes.txt)"
xcrun simctl list devicetypes | tee "$OUT/devicetypes.txt"

section "simctl devices available"
xcrun simctl list devices available

section "duo / fold grep across simctl lists"
{ xcrun simctl list devicetypes; xcrun simctl list runtimes; xcrun simctl list devices available; } \
  | grep -iE "duo|fold" || echo "NO duo/fold matches in simctl lists"

section "simctl help (full)"
xcrun simctl help 2>&1 || true

for sub in io privacy location create boot spawn launch install terminate; do
  section "simctl help $sub"
  xcrun simctl help "$sub" 2>&1 || true
done

section "iphonesimulator defaults"
defaults read com.apple.iphonesimulator 2>&1 | head -50 || true

section "fold-related files inside Xcode (bounded)"
find "$XCODE_APP" -iname "*fold*" 2>/dev/null | head -30 || true

section "posture/fold strings in CoreSimulator (bounded)"
CSF="$(xcode-select -p)/Library/PrivateFrameworks/CoreSimulator.framework"
if [ -d "$CSF" ]; then
  find "$CSF" -type f -perm +111 2>/dev/null | head -5 | while read -r bin; do
    echo "-- $bin"
    strings "$bin" 2>/dev/null | grep -iE "posture|foldstate|folded|unfolded" | sort -u | head -20 || true
  done
else
  echo "CoreSimulator.framework not at $CSF"
fi

section "booted devices"
xcrun simctl list devices booted || true
} 2>&1 | tee -a "$INV"

echo
echo "inventory written to $INV"
