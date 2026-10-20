# Browser — Chromium Android + On-Device DevTools

A **Chromium Android fork overlay** that adds an on-device developer inspector to
`chrome_public_apk`. This repository does **not** vendor Chromium's enormous source tree.

> Status: **MVP source integration; not yet built or tested on a device**.
> This is a compact native CDP inspector, **not** the full desktop Chrome DevTools UI.
> The inspector launches as a second app icon ("Browser DevTools") within the **same APK**.
> Future iterations can integrate it into Chromium's overflow menu and dock it in a panel.

## Architecture

```
Chromium Android (Blink / V8 / network)
  └── existing DevToolsServer (same browser process)
        └── abstract Unix socket: browserfork_devtools_remote
              └── Java LocalSocket (same app UID)
                    └── Browser DevTools Activity
                          ├── Tabs: choose a page
                          ├── Elements: DOM.getDocument
                          ├── Console: Runtime.consoleAPICalled / Runtime.evaluate
                          └── Network: Network.requestWillBeSent / responseReceived
```

No rooted Android device, PC connection, open TCP debugging port, externally hosted
DevTools frontend, Eruda, or Android WebView is required **at runtime**.

## Linux build host

Chromium's own Android build prerequisites apply: **Linux x86-64**, substantial disk
space (plan for 100GB+ free), RAM and a working Android toolchain. The 100GB relates
to checkout/build artifacts, not the Android APK.

See: https://chromium.googlesource.com/chromium/src/+/main/docs/android_build_instructions.md

### 1. Checkout upstream Chromium

```bash
git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git "$HOME/depot_tools"
export PATH="$HOME/depot_tools:$PATH"
mkdir -p "$HOME/chromium" && cd "$HOME/chromium"
fetch --no-history --nohooks android
cd src
build/install-build-deps.sh
gclient runhooks
```

`fetch` does **not** fork Google's gigantic repository on GitHub. Keep the Chromium
checkout locally and version only the overlay here.

### 2. Apply the Browser modifications

With a checkout of **this** repository:

```bash
python3 path/to/browser/scripts/apply_overlay.py "$HOME/chromium/src"
```

The patching script performs anchor checks and is idempotent. It:
- installs `InspectorActivity.java` into Chromium's Java source tree;
- adds it to `chrome/android/chrome_java_sources.gni`;
- adds a launcher activity to `chrome/android/java/AndroidManifest.xml`;
- gives the fork a distinct CDP abstract socket prefix to prevent collisions with Chrome.

### 3. Build ARM64 APK

```bash
export PATH="$HOME/depot_tools:$PATH"
cd "$HOME/chromium/src"
gn gen out/Browser --args='target_os="android" target_cpu="arm64" is_debug=false symbol_level=0'
autoninja -C out/Browser chrome_public_apk
out/Browser/bin/chrome_public_apk install
```

Open **Chromium**, navigate to an HTTPS page, then launch **Browser DevTools**
from the Android app launcher. Select a `page` target. Make sure Chromium has
finished initialization before opening DevTools.

## MVP capabilities / limitations

| Feature | Code | Verified on device |
|---|---|---|
| Chromium fork build overlay | Yes | No |
| Local Unix socket CDP (no TCP exposure) | Yes | No |
| Enumerate and choose page targets | Yes | No |
| Read document element tree | Yes | No |
| Console events and JS evaluation | Yes | No |
| Network request/response summaries | Yes | No |
| Live CSS style editor | No | No |
| Native element picker overlay | No | No |
| Desktop DevTools frontend (Sources, Performance, Application) | No | No |
| Docked panel / menu entry | No | No |
| Release signing and Play Store packaging | No | No |

Chrome changes its internal Android source layout frequently. If the overlay rejects
an upstream file, inspect the mismatch and update the integration instead of blindly
replacing source text. This repository has not been compiled against a pinned SHA.

## Security

The inspector uses Android's **abstract Unix socket**, the existing Chromium CDP
authorization checks, and a **same-UID** in-app connection. It does **not** bind CDP
to TCP localhost or Wi-Fi. Be aware CDP is high privilege: opening it gives debugging
access to the selected page. Do not use the inspector with untrusted debugging
extensions or expose it via port forward.

## Roadmap

1. Pin a tested Chromium commit, compile and test on a physical ARM64 device.
2. Add menu entry and tab-aware opening; only inspect the current foreground tab.
3. Add a dockable layout and touch element picker using Chromium's content layer.
4. Package a matching, offline DevTools frontend and transport it through an
   authenticated in-process CDP bridge (not a public TCP debugging endpoint).
5. Responsive developer UX, regression tests, release builds and update strategy.

Upstream: https://chromium.googlesource.com/chromium/src
CDP reference: https://chromedevtools.github.io/devtools-protocol/
