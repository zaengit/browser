#!/usr/bin/env bash
# Build a Chromium Android ARM64 APK after running apply_overlay.py.
set -euo pipefail

SRC="${1:-$HOME/chromium/src}"
if [[ ! -f "$SRC/BUILD.gn" ]]; then
  echo "Chromium source not found: $SRC" >&2
  exit 1
fi
command -v gn >/dev/null || { echo "gn not found; add depot_tools to PATH" >&2; exit 1; }
command -v autoninja >/dev/null || { echo "autoninja not found; add depot_tools to PATH" >&2; exit 1; }

cd "$SRC"
gn gen out/Browser --args='target_os="android" target_cpu="arm64" is_debug=false symbol_level=0'
autoninja -C out/Browser chrome_public_apk
printf '\nBuilt APK (if successful): out/Browser/apks/ChromePublic.apk\n'
printf 'Install: out/Browser/bin/chrome_public_apk install\n'
