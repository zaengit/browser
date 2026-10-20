#!/usr/bin/env bash
# Build Chromium ARM64 with native Android DevTools enabled.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$(realpath "${1:-$HOME/chromium/src}")"
ROOT="$(dirname "$SRC")"
PIN="$(tr -d '\r\n' < "$HERE/UPSTREAM_REVISION")"
FEATURE="$SRC/content/public/common/content_features.cc"
MENU="$SRC/chrome/android/java/src/org/chromium/chrome/browser/tabbed_mode/TabbedAppMenuPropertiesDelegate.java"

python3 "$HERE/scripts/doctor.py" --stage build --root "$ROOT"

if [[ ! -f "$SRC/BUILD.gn" ]]; then
  echo "ERROR: Chromium source not found: $SRC" >&2
  exit 1
fi
if [[ "$(git -C "$SRC" rev-parse HEAD)" != "$PIN" ]]; then
  echo "ERROR: expected pinned revision $PIN" >&2
  exit 1
fi

python3 "$HERE/scripts/enable_native_devtools.py" "$SRC" --check
if ! grep -Fq 'BASE_FEATURE(kAndroidDevToolsFrontend, base::FEATURE_ENABLED_BY_DEFAULT);' "$FEATURE"; then
  echo "ERROR: native DevTools feature not enabled; apply overlay first." >&2
  exit 1
fi
if ! grep -Fq '// Browser fork: expose native DevTools on phone-sized Android devices.' "$MENU" ||
   ! grep -Fq '// Browser fork: include native DevTools in the classic menu.' "$MENU"; then
  echo "ERROR: Android phone DevTools menu overlay missing." >&2
  exit 1
fi

cd "$SRC"
gn gen out/Browser --args='target_os="android" target_cpu="arm64" is_debug=false symbol_level=0'
autoninja -C out/Browser chrome_public_apk

APK="$SRC/out/Browser/apks/ChromePublic.apk"
if [[ ! -s "$APK" ]]; then
  echo "ERROR: expected nonempty build artifact missing: $APK" >&2
  exit 1
fi
printf '\nOK: Built APK %s\n' "$APK"
printf 'To inspect a connected device: bash %s/scripts/device_check.sh %s\n' "$HERE" "$APK"
