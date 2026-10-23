#!/usr/bin/env python3
"""Exercise the real offline helper bundle without USB or network access."""
import hashlib
import json
import posixpath
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import package_usb_helper as helper


class HelperPackageTests(unittest.TestCase):
    def test_source_readme_local_links_resolve_in_repository(self):
        readme = helper.SOURCE / "README_RU.md"
        for link in re.findall(r"\]\(([^)]+)\)", readme.read_text(encoding="utf-8")):
            if "://" in link or link.startswith("#"):
                continue
            target = (readme.parent / link.split("#", 1)[0]).resolve()
            self.assertTrue(target.is_file(), f"Broken repository README link: {link}")

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
        # Only the console UI persists explicitly saved, validated macro
        # definitions/favorites. Transport code and session logs do not persist.
        for name in ("core.js", "api.js", "app.js", "dashboard.js", "console_runner.js"):
            self.assertNotIn("localStorage", (helper.SOURCE / name).read_text(encoding="utf-8"), name)
        self.assertIn("Помощник 2.9", html)
        self.assertIn("Помощник 2.9 · MeshCore", html)
        self.assertIn("SmartUiPresets", html)
        self.assertIn('id="preset-city"', html)
        self.assertIn('id="advert-interval"', html)
        self.assertIn("Для новых настроек нужна SmartUI 0.08", html)
        self.assertIn('id="info-firmware"', html)
        self.assertIn('id="info-board"', html)
        self.assertIn("120 секунд", html)
        self.assertEqual(helper.HTML_NAME, "SmartUI_USB_Helper_2.9.html")
        self.assertEqual(helper.ZIP_NAME, "SmartUI_USB_Helper_2.9.zip")
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
                    "docs/CONSOLE_COMMANDS_RU.md", "docs/HELPER_CONSOLE_RU.md", "docs/HELPER_SIMPLE_RU.md",
                    "docs/CLI_BOARD_MATRIX_RU.md",
                    "docs/EXTERNAL_BUZZER_RU.md",
                    "docs/SMARTUI_CLI_RU.md", "docs/REMOTE_CLI_RU.md", "tools/smartui-cli/README.md",
                    "docs/SUPPORTED_BOARDS_RU.md", "docs/MIGRATION_1.18_RU.md", "docs/CONTACT_STORAGE_RU.md",
                    "docs/FLASHING_RU.md", "RELEASE_NOTES_SmartUI_0.22_RU.md",
                    "RELEASE_NOTES_SmartUI_0.21_RU.md",
                    "RELEASE_NOTES_SmartUI_0.20_RU.md",
                    "docs/PROMICRO_GPS_RU.md", "docs/BUILD_RU.md", "docs/VERIFY_RU.md",
                    "variants/promicro/variant.cpp", "tools/usb-helper/README_RU.md",
                    "docs/AUDIT_FIXES_0.06_RU.md", "RELEASE_NOTES_v2.1.0-dev.1_RU.md",
                    "RELEASE_NOTES_v2.1.0-dev_RU.md", "RELEASE_NOTES_v2.1.0-beta.2_RU.md",
                    "docs/assets/ui/wireless-paper-ble-pin.png", "docs/assets/ui/ui006-all-six.png",
                    "docs/assets/ui/ui-overview-three-boards.png", "docs/assets/ui/v4-3-oled-clock.png",
                    "docs/assets/ui/wireless-paper-wood-clock.png",
                    "tools/usb-helper/PRESETS_SOURCE_RU.md",
                    "screenshots/settings-desktop.png", "screenshots/settings-mobile.png",
                    "screenshots/dashboard-desktop.png", "screenshots/dashboard-mobile.png",
                    "screenshots/city-desktop.png", "screenshots/city-mobile.png",
                "screenshots/adc-service-desktop.png", "screenshots/adc-service-mobile.png",
                "screenshots/console-desktop.png", "screenshots/console-mobile.png",
                "screenshots/headless-desktop.png", "screenshots/headless-mobile.png",
                "screenshots/command-tree-desktop.png", "screenshots/command-tree-mobile.png",
                "screenshots/simple-desktop.png", "screenshots/simple-mobile.png"})
                self.assertEqual(archive.read(helper.HTML_NAME), first[0].read_bytes())
                self.assertEqual(archive.read("docs/CONSOLE_COMMANDS_RU.md"),
                                 (helper.ROOT / "docs/CONSOLE_COMMANDS_RU.md").read_bytes())
                for doc in ("docs/HELPER_CONSOLE_RU.md", "docs/HELPER_SIMPLE_RU.md"):
                    source_doc = (helper.ROOT / doc).read_text(encoding="utf-8")
                    self.assertEqual(archive.read(doc).decode("utf-8"),
                                     source_doc.replace("../tools/usb-helper/screenshots/", "../screenshots/"))
                for name in ("docs/CONSOLE_COMMANDS_RU.md", "docs/SMARTUI_CLI_RU.md", "docs/REMOTE_CLI_RU.md", "docs/CLI_BOARD_MATRIX_RU.md",
                             "docs/EXTERNAL_BUZZER_RU.md",
                             "docs/SUPPORTED_BOARDS_RU.md", "docs/MIGRATION_1.18_RU.md",
                             "docs/FLASHING_RU.md", "RELEASE_NOTES_SmartUI_0.22_RU.md",
                             "RELEASE_NOTES_SmartUI_0.21_RU.md",
                             "RELEASE_NOTES_SmartUI_0.20_RU.md",
                             "tools/smartui-cli/README.md"):
                    self.assertEqual(archive.read(name), (helper.ROOT / name).read_bytes())
                # Includes the relocated root README and transitive references,
                # so links cannot work on GitHub while silently breaking offline.
                for name in archive.namelist():
                    if not name.endswith(".md"):
                        continue
                    for link in re.findall(r"\]\(([^)]+)\)", archive.read(name).decode("utf-8")):
                        if "://" in link or link.startswith("#"):
                            continue
                        linked = posixpath.normpath(posixpath.join(posixpath.dirname(name), link.split("#", 1)[0]))
                        self.assertIn(linked, archive.namelist(), f"Broken offline documentation link: {name} -> {link}")
                for name in ("screenshots/settings-desktop.png", "screenshots/settings-mobile.png",
                             "screenshots/dashboard-desktop.png", "screenshots/dashboard-mobile.png",
                             "screenshots/city-desktop.png", "screenshots/city-mobile.png",
                             "screenshots/adc-service-desktop.png", "screenshots/adc-service-mobile.png",
                             "screenshots/command-tree-desktop.png", "screenshots/command-tree-mobile.png",
                             "screenshots/simple-desktop.png", "screenshots/simple-mobile.png"):
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
