#!/usr/bin/env bash
# Prepare the official Chromium Android checkout and apply the native DevTools overlay.
# Requires Ubuntu/Debian x86-64 and >=100 GB available free storage.
set -euo pipefail

if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
  echo "ERROR: official Chromium Android builds require a Linux x86-64 build host." >&2
  exit 1
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHROMIUM_ROOT="${1:-$HOME/chromium}"
DEPOT_TOOLS="${DEPOT_TOOLS:-$HOME/depot_tools}"

command -v git >/dev/null || { echo "Install git first" >&2; exit 1; }
command -v python3 >/dev/null || { echo "Install python3 first" >&2; exit 1; }

if [[ ! -d "$DEPOT_TOOLS/.git" ]]; then
  git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git "$DEPOT_TOOLS"
fi
export PATH="$DEPOT_TOOLS:$PATH"

if [[ ! -d "$CHROMIUM_ROOT/src/.git" ]]; then
  mkdir -p "$CHROMIUM_ROOT"
  cd "$CHROMIUM_ROOT"
  fetch --no-history --nohooks android
fi

cd "$CHROMIUM_ROOT/src"
build/install-build-deps.sh
gclient runhooks
python3 "$HERE/scripts/enable_native_devtools.py" "$PWD" --check
python3 "$HERE/scripts/enable_native_devtools.py" "$PWD"
git rev-parse HEAD > "$CHROMIUM_ROOT/browser-upstream-sha.txt"
printf '\nPatched Chromium source at: %s\n' "$PWD"
printf 'Recorded upstream SHA in: %s\n' "$CHROMIUM_ROOT/browser-upstream-sha.txt"
printf 'Build with: %s/scripts/build.sh "%s"\n' "$HERE" "$PWD"
