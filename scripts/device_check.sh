#!/usr/bin/env bash
# Preflight an ARM64 Android handset before manually testing Browser DevTools.
# By default this script is read-only. Specify --install to install the supplied APK.
set -euo pipefail

usage() {
  echo "Usage: bash scripts/device_check.sh <path-to-ChromePublic.apk> [--install]"
}

if [[ $# -lt 1 || $# -gt 2 ]]; then
  usage; exit 2
fi
APK="$1"
INSTALL="${2:-}"

if [[ "$INSTALL" != "" && "$INSTALL" != "--install" ]]; then
  usage; exit 2
fi
if ! command -v adb >/dev/null; then
  echo "ERROR: Android Platform Tools (adb) are required." >&2
  exit 1
fi
if [[ ! -s "$APK" ]]; then
  echo "ERROR: APK not found or empty: $APK" >&2
  exit 1
fi

mapfile -t DEVICES < <(adb devices | awk 'NR>1 && $2=="device" {print $1}')
if [[ "${#DEVICES[@]}" -ne 1 ]]; then
  echo "ERROR: connect and authorize exactly one Android handset." >&2
  adb devices
  exit 1
fi
SERIAL="${DEVICES[0]}"
ABI="$(adb -s "$SERIAL" shell getprop ro.product.cpu.abi | tr -d '\r')"
API="$(adb -s "$SERIAL" shell getprop ro.build.version.sdk | tr -d '\r')"
MODEL="$(adb -s "$SERIAL" shell getprop ro.product.model | tr -d '\r')"
echo "Device: $MODEL  API: $API  ABI: $ABI"
case "$ABI" in
  arm64-v8a) ;;
  *) echo "ERROR: ARM64 build requires an arm64-v8a device; detected $ABI" >&2; exit 1 ;;
esac

echo "APK: $APK"
du -h "$APK"
if [[ "$INSTALL" == "--install" ]]; then
  echo "Installing test APK to device $SERIAL..."
  adb -s "$SERIAL" install -r "$APK"
  echo "Install command completed."
  echo "Manual smoke test: launch Chromium; open a webpage; open menu > DevTools."
  echo "Verify Elements, Console, Network; close DevTools and verify tab remains usable."
else
  echo "Read-only checks complete. Use --install to install."
fi
