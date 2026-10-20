# Browser — Chromium Android with Native On-Device DevTools

Source overlay for a **fork of Chromium Android**, targeting ARM64 Android phones. Not WebView, Eruda, or a re-packaged Google Chrome APK. Chromium's source and binary dependencies are downloaded from upstream on the Linux build host, **not committed to this repository**.

> **Status: native DevTools overlay + pinned source + preflight scripts written, but no successful Chromium compilation or physical-phone test yet. No verified APK is available.**

**Pinned Chromium baseline:** [`9657580a7997ca5f023f2c7551e291b91a06f021`](https://chromium.googlesource.com/chromium/src/+/9657580a7997ca5f023f2c7551e291b91a06f021) (recorded in [`UPSTREAM_REVISION`](UPSTREAM_REVISION)). This is a **development snapshot, not a security-supported release**. Avoid logging into sensitive websites until the fork has been updated to a security-patched release and tested.

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
python3 scripts/doctor.py --stage checkout --root "$HOME/chromium"
bash scripts/bootstrap.sh "$HOME/chromium"
bash scripts/build.sh "$HOME/chromium/src"
```

`bootstrap.sh` installs Chromium's depot_tools checkout if needed, fetches upstream Chromium, **switches to the exact pinned revision**, synchronizes the pinned dependencies, installs build prerequisites, applies the native DevTools patch, and records the SHA. It refuses to switch revisions if tracked source files have local modifications. Updating to current upstream `main` is **not** supported by this overlay until the source integration is revalidated.

### Option B — existing Chromium checkout

```bash
cd /path/to/browser
# The checkout MUST already be at the commit in UPSTREAM_REVISION.
python3 scripts/enable_native_devtools.py /path/to/chromium/src --check
python3 scripts/enable_native_devtools.py /path/to/chromium/src
bash scripts/build.sh /path/to/chromium/src
```

The build target is `chrome_public_apk`, `target_os="android"`, `target_cpu="arm64"`, release-style debugging settings (`is_debug=false`, `symbol_level=0`).

### Install and smoke test

```bash
cd "$HOME/chromium/src"
bash /path/to/browser/scripts/device_check.sh out/Browser/apks/ChromePublic.apk
bash /path/to/browser/scripts/device_check.sh out/Browser/apks/ChromePublic.apk --install
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

- **Compile** the APK against the pinned Chromium revision and run the complete smoke test on a physical ARM64 device. Source-only validation is not equivalent to a successful build.
- Fix DevTools UI layout/touch usability on small Android screens where needed.
- Optional: add a docked split-screen DevTools panel, custom naming/icons and release signing.

## Device smoke-test checklist

Use an **arm64-v8a** device, with USB debugging explicitly authorized for the host. Verify a normal HTTPS page loads; **DevTools** opens from the page menu; **Elements** shows DOM; **Console** runs a simple expression (`1 + 1`); **Network** records requests after reload; back navigation and reopening work; the browser remains functional after DevTools closes. Capture `adb logcat` for crashes. On smaller displays, note touch/scrolling or keyboard overlap problems.
