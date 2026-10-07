#!/usr/bin/env python3
"""Exercise the real offline helper bundle without USB or network access."""
import hashlib
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import package_usb_helper as helper


class HelperPackageTests(unittest.TestCase):
    def test_public_melody_names_match_the_production_order(self):
        source = (helper.ROOT / "examples/companion_radio/ui-new/UITask.cpp").read_text(encoding="utf-8")
        tones = source.split("static const NotifyToneDef notify_tones[] = {", 1)[1].split("};", 1)[0]
        expected = re.findall(r'\{"([^"]+)"', tones)
        app = (helper.SOURCE / "app.js").read_text(encoding="utf-8")
        actual = json.loads(re.search(r"const melodyNames = (\[[^\n]+\]);", app).group(1))
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 31)

    def test_bundle_contains_protocol_and_ui_without_external_dependencies(self):
        html = helper.render().decode("utf-8")
        self.assertNotIn("/* SMARTUI_HELPER_", html)
        self.assertIn("class ConsoleClient", html)
        self.assertIn("navigator.serial.requestPort()", html)
        self.assertIn("connect-src 'none'", html)
        self.assertNotIn("localStorage", html)
        self.assertIn("Помощник 1.7", html)
        self.assertIn("Помощник 1.7 · MeshCore", html)
        self.assertIn("SmartUiPresets", html)
        self.assertIn('id="preset-city"', html)
        self.assertIn('id="advert-interval"', html)
        self.assertIn("Для новых настроек нужна SmartUI 0.08", html)
        self.assertIn('id="info-firmware"', html)
        self.assertIn('id="info-board"', html)
        self.assertIn("120 секунд", html)
        self.assertEqual(helper.HTML_NAME, "SmartUI_USB_Helper_1.7.html")
        self.assertEqual(helper.ZIP_NAME, "SmartUI_USB_Helper_1.7.zip")
        self.assertIn("class CliClient", html)
        self.assertIn('id="helper-mode"', html)
        self.assertNotIn('id="api-inbox"', html)
        self.assertNotIn('id="api-sync-enable"', html)
        self.assertIn("smartui_cli:1", html)
        self.assertIn("архивный Helper 1.4", html)
        self.assertIn('id="device-section"', html)
        self.assertIn("Settings protocol: 1", html)
        self.assertIn("saveDeviceSetting", html)
        self.assertIn('id="adc-apply"', html)

    def test_package_is_deterministic_and_checksums_match(self):
        with tempfile.TemporaryDirectory() as root:
            first = helper.package(Path(root) / "first")
            second = helper.package(Path(root) / "second")
            for a, b in zip(first, second):
                self.assertEqual(a.read_bytes(), b.read_bytes())
            with zipfile.ZipFile(first[1]) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(set(archive.namelist()), {
                    helper.HTML_NAME, "README_RU.md", "PRESETS_SOURCE_RU.md", "LICENSE", "SHA256SUMS.txt",
                    "screenshots/settings-desktop.png", "screenshots/settings-mobile.png",
                    "screenshots/dashboard-desktop.png", "screenshots/dashboard-mobile.png",
                    "screenshots/city-desktop.png", "screenshots/city-mobile.png",
                    "screenshots/adc-service-desktop.png", "screenshots/adc-service-mobile.png"})
                self.assertEqual(archive.read(helper.HTML_NAME), first[0].read_bytes())
                for name in ("screenshots/settings-desktop.png", "screenshots/settings-mobile.png",
                             "screenshots/dashboard-desktop.png", "screenshots/dashboard-mobile.png",
                             "screenshots/city-desktop.png", "screenshots/city-mobile.png",
                             "screenshots/adc-service-desktop.png", "screenshots/adc-service-mobile.png"):
                    self.assertTrue(archive.read(name).startswith(b"\x89PNG\r\n\x1a\n"))
                for line in archive.read("SHA256SUMS.txt").decode("ascii").splitlines():
                    digest, name = line.split("  ", 1)
                    self.assertEqual(digest, hashlib.sha256(archive.read(name)).hexdigest())
            with self.assertRaises(ValueError):
                helper.package(Path(root) / "first")

    def test_rejects_external_script_missing_marker_and_script_breakout(self):
        original = Path.read_text
        for target, transform in (
            ("index.html", lambda text: text.replace("<head>", '<head><script src="https://invalid.test/x.js"></script>')),
            ("index.html", lambda text: text.replace("/* SMARTUI_HELPER_CORE */", "")),
            ("core.js", lambda text: text + "\n// </script>"),
        ):
            def changed(path, *args, **kwargs):
                text = original(path, *args, **kwargs)
                return transform(text) if path.name == target else text
            with self.subTest(target=target), patch.object(Path, "read_text", changed):
                with self.assertRaises(ValueError):
                    helper.render()


if __name__ == "__main__":
    unittest.main()
