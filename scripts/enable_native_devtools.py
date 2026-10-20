#!/usr/bin/env python3
"""Enable Chromium's *native* on-device DevTools on Android phones.

This modifies two Chromium source files. It DOES NOT build Chromium and does
not use WebView, an exported Activity, CDP TCP ports, or a custom debugger.
Always run against a compatible, reviewed Chromium checkout.

Usage: python3 scripts/enable_native_devtools.py /path/to/chromium/src [--check]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

FEATURES = Path("content/public/common/content_features.cc")
MENU = Path("chrome/android/java/src/org/chromium/chrome/browser/tabbed_mode/TabbedAppMenuPropertiesDelegate.java")
FRONTEND_GN = Path("content/browser/devtools/features.gni")
NATIVE_ACTIVITY = Path("chrome/android/java/src/org/chromium/chrome/browser/devtools/DevToolsActivity.java")

DISABLED = "BASE_FEATURE(kAndroidDevToolsFrontend, base::FEATURE_DISABLED_BY_DEFAULT);"
ENABLED = "BASE_FEATURE(kAndroidDevToolsFrontend, base::FEATURE_ENABLED_BY_DEFAULT);"
PHONE_COMMENT = "// Browser fork: expose native DevTools on phone-sized Android devices."
CLASSIC_COMMENT = "// Browser fork: include native DevTools in the classic menu."

GUARD = re.compile(
    r"\n[ \t]*if \(!DeviceFormFactor\.isNonMultiDisplayContextOnTablet\(mContext\)\) \{"
    r"\s*return false;\s*\}\s*\n"
)

CLASSIC_SNIPPET = (
    "        " + CLASSIC_COMMENT + "\n"
    "        if (shouldShowDevToolsItem(currentTab)) {\n"
    "            modelList.add(buildDevToolsItem(currentTab));\n"
    "        }\n\n"
)


def _feature_patch(source: str) -> str:
    if source.count(ENABLED) == 1 and source.count(DISABLED) == 0:
        return source
    if source.count(DISABLED) != 1 or source.count(ENABLED) != 0:
        raise ValueError("Unexpected feature declaration; inspect upstream Chromium first.")
    return source.replace(DISABLED, ENABLED, 1)


def _menu_patch(source: str) -> str:
    start_name = "private boolean shouldShowDevToolsItem("
    end_name = "private ListItem buildDevToolsItem("
    if source.count(start_name) != 1 or source.count(end_name) != 1:
        raise ValueError("Android DevTools menu helpers missing or duplicated.")
    start = source.index(start_name)
    end = source.index(end_name, start)
    method = source[start:end]

    if "ContentFeatureList.ANDROID_DEV_TOOLS_FRONTEND" not in method:
        raise ValueError("Feature gate unexpectedly missing from DevTools menu.")
    if "DevToolsWindowAndroid.isDevToolsAllowedFor" not in method:
        raise ValueError("Permission/policy check unexpectedly missing; refusing to patch.")

    if PHONE_COMMENT in method:
        if "DeviceFormFactor.isNonMultiDisplayContextOnTablet(mContext)" in method:
            raise ValueError("Phone marker found, but tablet gate remains.")
    else:
        method, count = GUARD.subn(
            "\n        " + PHONE_COMMENT + "\n\n",
            method,
            count=1,
        )
        if count != 1:
            raise ValueError("Tablet-only menu gate changed; inspect upstream before modifying.")
    source = source[:start] + method + source[end:]

    # The modern 'More tools' submenu already uses shouldShowDevToolsItem().
    # Older/classic app menus lack that entry, so add one without changing
    # the existing command handler or its policy checks.
    classic_start = "private void populatePageModeMenuWithoutSubmenus("
    classic_end = "private void populatePageModeMenuWithSubmenus("
    if source.count(classic_start) != 1 or source.count(classic_end) != 1:
        raise ValueError("Could not identify classic menu method boundaries.")
    start = source.index(classic_start)
    end = source.index(classic_end, start)
    classic = source[start:end]
    if CLASSIC_COMMENT not in classic:
        anchor = "        // Settings\n        modelList.add(buildSettingsItem());"
        if classic.count(anchor) != 1:
            raise ValueError("Classic menu Settings insertion point changed.")
        classic = classic.replace(anchor, CLASSIC_SNIPPET + anchor, 1)
    else:
        if classic.count(CLASSIC_SNIPPET) != 1:
            raise ValueError("Classic menu is partially patched or unexpectedly changed.")
    return source[:start] + classic + source[end:]


def planned_updates(root: Path) -> dict[Path, str]:
    for path in (FEATURES, MENU, FRONTEND_GN, NATIVE_ACTIVITY):
        if not (root / path).is_file():
            raise ValueError(f"Missing Chromium source file: {path}")

    # Avoid apparently successful builds that compiled without the native UI.
    gn = (root / FRONTEND_GN).read_text(encoding="utf-8")
    if not re.search(r"enable_devtools_frontend\s*=\s*!is_ios\s*&&\s*!is_fuchsia", gn):
        raise ValueError("Chromium frontend build policy differs from the verified 2026 baseline.")
    activity = (root / NATIVE_ACTIVITY).read_text(encoding="utf-8")
    if "class DevToolsActivity" not in activity:
        raise ValueError("Chromium's DevToolsActivity not present.")

    feature_file = root / FEATURES
    menu_file = root / MENU
    return {
        feature_file: _feature_patch(feature_file.read_text(encoding="utf-8")),
        menu_file: _menu_patch(menu_file.read_text(encoding="utf-8")),
    }


def run() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("chromium_src", type=Path)
    parser.add_argument("--check", action="store_true", help="Validate without modifying files")
    args = parser.parse_args()
    root = args.chromium_src.resolve()
    try:
        updates = planned_updates(root)  # No source file is written until every anchor passes.
        for path, content in updates.items():
            changed = path.read_text(encoding="utf-8") != content
            print(("would modify" if args.check else "modifying") if changed else "unchanged",
                  path.relative_to(root))
            if changed and not args.check:
                path.write_text(content, encoding="utf-8")
        print("Native DevTools source overlay validated." if args.check else
              "Native DevTools overlay applied. Compile and test on a physical phone.")
        return 0
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run())
