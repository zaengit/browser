"""Regression tests for overlay integration; no Chromium checkout required."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "apply_overlay.py"
spec = importlib.util.spec_from_file_location("apply_overlay", SCRIPT)
overlay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(overlay)


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.gn = self.root / overlay.GN
        self.manifest = self.root / overlay.MANIFEST
        self.initializer = self.root / overlay.INITIALIZER
        for path in (self.gn, self.manifest, self.initializer):
            path.parent.mkdir(parents=True, exist_ok=True)

        self.gn.write_text('chrome_java_sources = [\n'
            '  "java/src/org/chromium/chrome/browser/DevToolsServer.java",\n'
            ']\n')
        self.manifest.write_text('<manifest><application>\n</application></manifest>\n')
        self.initializer.write_text(
            'class ProcessInitializationHandler {\n  '
            + overlay.ORIGINAL_PREFIX + '\n}\n')

    def tearDown(self):
        self.tmp.cleanup()

    def test_source_manifest_socket_and_idempotency(self):
        changes = overlay.plan(self.root)
        self.assertIn(overlay.REL_JAVA, [
            p.relative_to(self.root) for p in changes])
        self.assertIn('InspectorActivity.java', changes[self.gn])
        self.assertIn('BROWSER_DEVTOOLS_ACTIVITY', changes[self.manifest])
        self.assertIn('browserfork', changes[self.initializer])
        for path, content in changes.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.assertEqual(overlay.plan(self.root), changes)

    def test_rejects_unknown_source_layout(self):
        self.gn.write_text('chrome_java_sources = []\n')
        with self.assertRaises(RuntimeError):
            overlay.plan(self.root)


if __name__ == "__main__":
    unittest.main()
