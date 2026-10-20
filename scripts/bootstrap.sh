#!/usr/bin/env bash
# Checkout the pinned Chromium Android baseline and apply the native DevTools overlay.
# Requires Ubuntu/Debian Linux x86-64 and substantial free disk space.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIN="$(tr -d '\r\n' < "$HERE/UPSTREAM_REVISION")"
CHROMIUM_ROOT="${1:-$HOME/chromium}"
DEPOT_TOOLS="${DEPOT_TOOLS:-$HOME/depot_tools}"
SRC="$CHROMIUM_ROOT/src"

if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
  echo "ERROR: official Chromium Android builds require a Linux x86-64 build host." >&2
  exit 1
fi
if [[ ! "$PIN" =~ ^[0-9a-f]{40}$ ]]; then
  echo "ERROR: invalid 40-character upstream SHA in UPSTREAM_REVISION." >&2
  exit 1
fi
for cmd in git python3; do
  command -v "$cmd" >/dev/null || { echo "ERROR: missing $cmd" >&2; exit 1; }
done

python3 "$HERE/scripts/doctor.py" --stage checkout --root "$CHROMIUM_ROOT"

if [[ ! -d "$DEPOT_TOOLS/.git" ]]; then
  git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git "$DEPOT_TOOLS"
fi
export PATH="$DEPOT_TOOLS:$PATH"

if [[ ! -d "$SRC/.git" ]]; then
  mkdir -p "$CHROMIUM_ROOT"
  ( cd "$CHROMIUM_ROOT" && fetch --no-history --nohooks android )
fi

if [[ ! -d "$SRC/.git" ]]; then
  echo "ERROR: Chromium download did not create $SRC/.git" >&2
  exit 1
fi

CURRENT="$(git -C "$SRC" rev-parse HEAD)"
if [[ "$CURRENT" != "$PIN" ]]; then
  # Never discard local edits or checkout different source over uncommitted work.
  if [[ -n "$(git -C "$SRC" status --porcelain --untracked-files=no)" ]]; then
    echo "ERROR: Chromium checkout has modified tracked files; refusing to switch revision." >&2
    echo "Use a clean Chromium checkout or manually back up/revert its changes." >&2
    exit 1
  fi
  echo "Fetching pinned Chromium revision: $PIN"
  git -C "$SRC" fetch --no-tags --depth=1 origin "$PIN"
  git -C "$SRC" checkout --detach "$PIN"
fi

cd "$SRC"
echo "Syncing pinned DEPS for $PIN..."
gclient sync --revision "src@$PIN" --nohooks
ACTUAL="$(git rev-parse HEAD)"
if [[ "$ACTUAL" != "$PIN" ]]; then
  echo "ERROR: expected $PIN but checkout is $ACTUAL" >&2
  exit 1
fi

build/install-build-deps.sh
gclient runhooks
python3 "$HERE/scripts/enable_native_devtools.py" "$PWD" --check
python3 "$HERE/scripts/enable_native_devtools.py" "$PWD"
printf '%s\n' "$PIN" > "$CHROMIUM_ROOT/browser-upstream-sha.txt"
echo "Chromium revision pinned and patched: $PIN"
echo "Next: bash $HERE/scripts/build.sh $SRC"
