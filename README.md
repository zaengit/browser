# Browser — Chromium Android with Native On-Device DevTools

Source overlay for a **fork of Chromium Android**, targeting ARM64 Android phones. Not WebView, Eruda, or a re-packaged Google Chrome APK. Chromium's source and binary dependencies are downloaded from upstream on the Linux build host, **not committed to this repository**.

> **Status: MVP source patch written, not yet compiled or tested on an Android phone.** No verified APK is available yet.

## Recommended implementation — native Chromium DevTools

Chromium 2026 already has the native DevTools frontend on Android (including `DevToolsActivity` and the menu action). However, the `AndroidDevToolsFrontend` feature is off by default for some Android configurations, and Chromium's Android menu currently limits the entry to tablets.

`scripts/enable_native_devtools.py` patches the existing **Chromium source itself**:

1. Enables `kAndroidDevToolsFrontend` by default in `content/public/common/content_features.cc`.
2. Removes the **tablet-only menu check** in `TabbedAppMenuPropertiesDelegate.java`, allowing a phone to display the menu.
3. Adds DevTools to the **classic app menu**, where the upstream newer "More tools" menu already supports it.
4. Preserves Chromium's native `DevToolsWindowAndroid.isDevToolsAllowedFor(...)` permission/policy check.
5. Checks expected upstream symbols; refuses to patch an incompatible Chromium revision. Safe to run repeatedly.

**No new network socket, exported DevTools activity, or custom Chrome DevTools Protocol bridge is required.** The DevTools frontend comes from Chromium and opens in its own Android activity rather than a docked bottom panel.

Upstream source references:

- [Chromium DevTools feature](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/content/public/common/content_features.cc)
- [Android browser menu](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/chrome/android/java/src/org/chromium/chrome/browser/tabbed_mode/TabbedAppMenuPropertiesDelegate.java)
- [Native DevTools activity](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/chrome/android/java/src/org/chromium/chrome/browser/devtools/DevToolsActivity.java)
- [DevTools GN configuration](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/content/browser/devtools/features.gni)

## Build (Ubuntu / Linux x86-64)

Prepare at least **100 GB disk free** and ideally 16 GB or more RAM. Official Chromium Android builds require Linux x86-64, not compiling on the Android handset. The 100 GB is for source, tools, dependencies and build artifacts, not APK size.

### Option A — automated setup

```bash
git clone https://github.com/zaengit/browser.git
cd browser
bash scripts/bootstrap.sh "$HOME/chromium"
bash scripts/build.sh "$HOME/chromium/src"
```

`bootstrap.sh` installs Chromium's depot_tools checkout if needed, fetches upstream Chromium, runs dependency setup and hooks, applies this fork's native DevTools patch and records the upstream SHA in `$HOME/chromium/browser-upstream-sha.txt`.

### Option B — existing Chromium checkout

```bash
cd /path/to/browser
python3 scripts/enable_native_devtools.py /path/to/chromium/src --check
python3 scripts/enable_native_devtools.py /path/to/chromium/src
bash scripts/build.sh /path/to/chromium/src
```

The build target is `chrome_public_apk`, `target_os="android"`, `target_cpu="arm64"`, release-style debugging settings (`is_debug=false`, `symbol_level=0`).

### Install and smoke test

```bash
cd "$HOME/chromium/src"
out/Browser/bin/chrome_public_apk install
```

Open the built **Chromium** app on an ARM64 phone, visit an ordinary HTTPS page, and check the overflow menu for **DevTools** (possibly under **More tools**). Test the **Elements**, **Console**, **Network**, **Sources**, and **Application** panels separately. DevTools' phone-sized interface is experimental, so some controls may be inaccessible or render poorly until further UI adaptations are made.

Do not assume the feature works until a clean Chromium build and device smoke test pass.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

These unit tests check anchor matching, safety on incompatible upstream code, phone menu changes, and idempotence. They are **not substitutes** for compiling and testing on a physical phone.

## Earlier experimental inspector

The repository also retains the older, experimental CDP inspector proof-of-concept:

- `scripts/apply_overlay.py`
- `overlay/InspectorActivity.java`

It uses Chromium's local abstract Unix domain socket and its own lightweight inspector activity. **It is not part of the recommended native DevTools build path.** Don't apply both overlays to the same checkout unless you are intentionally testing and reviewing that combination. The earlier inspector has not been compiled or validated on a device either.

## Security and maintenance

- No public TCP debugging endpoint is added by the new native overlay.
- The native policy and permission checks remain in place; enterprise restrictions are not bypassed.
- Upstream Chromium changes quickly. Pin and record a tested SHA for releases, validate upstream source changes after every update, and do not present the fork as official Google Chrome.
- Chromium and its third-party libraries retain their upstream license obligations.

## Remaining work

- Build the APK against a pinned Chromium revision and test on a physical ARM64 device.
- Fix DevTools UI layout/touch usability on small Android screens where needed.
- Optional: add a docked split-screen DevTools panel, custom naming/icons and release signing.
