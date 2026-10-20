#!/usr/bin/env bash
# Build Chromium Android ARM64 with native on-device DevTools enabled.
set -euo pipefail

SRC="${1:-$HOME/chromium/src}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FEATURE="$SRC/content/public/common/content_features.cc"
MENU="$SRC/chrome/android/java/src/org/chromium/chrome/browser/tabbed_mode/TabbedAppMenuPropertiesDelegate.java"

if [[ ! -f "$SRC/BUILD.gn" ]]; then
  echo "ERROR: Chromium source not found: $SRC" >&2
  exit 1
fi
for cmd in python3 gn autoninja; do
  command -v "$cmd" >/dev/null || {
    echo "ERROR: $cmd not found. Install/configure depot_tools and dependencies." >&2
    exit 1
  }
done

python3 "$HERE/scripts/enable_native_devtools.py" "$SRC" --check

if ! grep -Fq 'BASE_FEATURE(kAndroidDevToolsFrontend, base::FEATURE_ENABLED_BY_DEFAULT);' "$FEATURE"; then
  echo "ERROR: Native DevTools feature not enabled. Apply enable_native_devtools.py first." >&2
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
printf '\nBuild completed. APK: %s/out/Browser/apks/ChromePublic.apk\n' "$SRC"
printf 'Install using: %s/out/Browser/bin/chrome_public_apk install\n' "$SRC"
