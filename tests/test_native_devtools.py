"""Regression tests for the small Chromium source overlay.

Run without Chromium's 100GB source checkout:
    python3 -m unittest discover -s tests -v
"""
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "enable_native_devtools.py"
spec = importlib.util.spec_from_file_location("native_overlay", SCRIPT)
overlay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(overlay)

FEATURE_STUB = """
// Another feature.
BASE_FEATURE(kAndroidDevToolsFrontend, base::FEATURE_DISABLED_BY_DEFAULT);
// Keep all other features unchanged.
"""
MENU_STUB = """
class TabbedAppMenuPropertiesDelegate {
    private void populatePageModeMenuWithoutSubmenus(
            MVCListAdapter.ModelList modelList, @Nullable Tab currentTab) {
        // Settings
        modelList.add(buildSettingsItem());
    }

    private void populatePageModeMenuWithSubmenus(
            MVCListAdapter.ModelList modelList, @Nullable Tab currentTab) {
        if (shouldShowMoreToolsItem(currentTab)) {}
    }

    private boolean shouldShowDevToolsItem(@Nullable Tab currentTab) {
        if (!ContentFeatureMap.isEnabled(ContentFeatureList.ANDROID_DEV_TOOLS_FRONTEND)) {
            return false;
        }

        if (!DeviceFormFactor.isNonMultiDisplayContextOnTablet(mContext)) {
            return false;
        }

        if (currentTab == null || currentTab.isNativePage()) {
            return false;
        }
        return DevToolsWindowAndroid.isDevToolsAllowedFor(currentTab.getProfile(), currentTab.getWebContents());
    }

    private ListItem buildDevToolsItem(@Nullable Tab currentTab) {
        return createStandardListItem();
    }
}
"""


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        contents = {
            overlay.FEATURES: FEATURE_STUB,
            overlay.MENU: MENU_STUB,
            overlay.FRONTEND_GN: "enable_devtools_frontend = !is_ios && !is_fuchsia\n",
            overlay.NATIVE_ACTIVITY: "public class DevToolsActivity extends ChromeActivity {}",
        }
        for path, text in contents.items():
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")

    def test_native_feature_enabled(self):
        changes = overlay.planned_updates(self.root)
        self.assertIn(overlay.ENABLED, changes[self.root / overlay.FEATURES])
        self.assertNotIn(overlay.DISABLED, changes[self.root / overlay.FEATURES])

    def test_phone_menu_and_classic_menu(self):
        changes = overlay.planned_updates(self.root)
        menu = changes[self.root / overlay.MENU]
        self.assertNotIn("if (!DeviceFormFactor.isNonMultiDisplayContextOnTablet(mContext))", menu)
        self.assertIn(overlay.PHONE_COMMENT, menu)
        self.assertIn(overlay.CLASSIC_SNIPPET, menu)
        self.assertIn("DevToolsWindowAndroid.isDevToolsAllowedFor", menu)

    def test_idempotent(self):
        first = overlay.planned_updates(self.root)
        for path, content in first.items():
            path.write_text(content, encoding="utf-8")
        second = overlay.planned_updates(self.root)
        for path, content in second.items():
            self.assertEqual(content, path.read_text(encoding="utf-8"))

    def test_fails_closed_when_tablet_gate_changes(self):
        path = self.root / overlay.MENU
        original = path.read_text(encoding="utf-8").replace(
            "isNonMultiDisplayContextOnTablet", "someNewAPI"
        )
        path.write_text(original, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Tablet-only"):
            overlay.planned_updates(self.root)
        self.assertEqual(original, path.read_text(encoding="utf-8"))

    def test_fails_closed_without_native_frontend(self):
        (self.root / overlay.FRONTEND_GN).write_text(
            "enable_devtools_frontend = false\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "frontend build policy"):
            overlay.planned_updates(self.root)


if __name__ == "__main__":
    unittest.main()
