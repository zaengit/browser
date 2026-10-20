#!/usr/bin/env python3
"""Apply the Browser DevTools overlay to an existing Chromium Android checkout.

Fails closed when upstream anchors do not match. May be run more than once.
"""
from pathlib import Path
import argparse
import shutil
import sys

HERE = Path(__file__).resolve().parent.parent
REL_JAVA = Path("chrome/android/java/src/org/chromium/chrome/browser/devtools/InspectorActivity.java")
GN = Path("chrome/android/chrome_java_sources.gni")
MANIFEST = Path("chrome/android/java/AndroidManifest.xml")
INITIALIZER = Path("chrome/android/java/src/org/chromium/chrome/browser/init/ProcessInitializationHandler.java")
JAVA_ENTRY = '    "java/src/org/chromium/chrome/browser/devtools/InspectorActivity.java",'
MANIFEST_MARK = '<!-- BROWSER_DEVTOOLS_ACTIVITY -->'
ACTIVITY_XML = '''        <!-- BROWSER_DEVTOOLS_ACTIVITY -->
        <activity
            android:name="org.chromium.chrome.browser.devtools.InspectorActivity"
            android:label="Browser DevTools"
            android:exported="true"
            android:theme="@android:style/Theme.Material.Light.NoActionBar">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
'''
ORIGINAL_PREFIX = 'private static final String DEV_TOOLS_SERVER_SOCKET_PREFIX = "chrome";'
FORK_PREFIX = 'private static final String DEV_TOOLS_SERVER_SOCKET_PREFIX = "browserfork";'


def replace_once(text: str, needle: str, replacement: str, path: Path) -> str:
    count = text.count(needle)
    if count != 1:
        raise RuntimeError(f"Unexpected Chromium version: expected one anchor in {path}, got {count}: {needle}")
    return text.replace(needle, replacement, 1)


def plan(root: Path) -> dict[Path, str]:
    required = [GN, MANIFEST, INITIALIZER]
    missing = [str(p) for p in required if not (root / p).is_file()]
    if missing:
        raise RuntimeError(f"Not a compatible Chromium checkout; missing: {', '.join(missing)}")

    changes = {}
    gn_file = root / GN
    gn = gn_file.read_text()
    if JAVA_ENTRY.strip() not in gn:
        anchor = '"java/src/org/chromium/chrome/browser/DevToolsServer.java",'
        lines = gn.splitlines(keepends=True)
        matches = [i for i, line in enumerate(lines) if line.strip() == anchor]
        if len(matches) != 1:
            raise RuntimeError(f"Unexpected Chromium Java source list: {gn_file}")
        index = matches[0]
        indent = lines[index][:len(lines[index]) - len(lines[index].lstrip())]
        lines.insert(index + 1, indent + JAVA_ENTRY.strip() + "\n")
        gn = "".join(lines)
    changes[gn_file] = gn

    manifest_file = root / MANIFEST
    manifest = manifest_file.read_text()
    if MANIFEST_MARK not in manifest:
        manifest = replace_once(manifest, "</application>", ACTIVITY_XML + "</application>", manifest_file)
    changes[manifest_file] = manifest

    init_file = root / INITIALIZER
    init = init_file.read_text()
    if FORK_PREFIX not in init:
        init = replace_once(init, ORIGINAL_PREFIX, FORK_PREFIX, init_file)
    changes[init_file] = init

    source = HERE / "overlay" / "InspectorActivity.java"
    if not source.is_file():
        raise RuntimeError(f"Missing inspector source: {source}")
    changes[root / REL_JAVA] = source.read_text()
    return changes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("chromium_src", type=Path)
    parser.add_argument("--check", action="store_true", help="Validate anchors without writing")
    args = parser.parse_args()
    root = args.chromium_src.resolve()
    try:
        changes = plan(root)
        if args.check:
            print("Overlay compatible; files validated (no changes written).")
            return 0
        for destination, content in changes.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.is_file() and destination.read_text() == content:
                print("unchanged", destination.relative_to(root))
                continue
            destination.write_text(content)
            print("updated", destination.relative_to(root))
        print("Overlay installed. Build chrome_public_apk using GN/autoninja.")
        return 0
    except (OSError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
