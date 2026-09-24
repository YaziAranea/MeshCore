#!/usr/bin/env python3
"""Exercise the real offline helper bundle without USB or network access."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import package_usb_helper as helper


class HelperPackageTests(unittest.TestCase):
    def test_bundle_contains_protocol_and_ui_without_external_dependencies(self):
        html = helper.render().decode("utf-8")
        self.assertNotIn("/* SMARTUI_HELPER_", html)
        self.assertIn("class ConsoleClient", html)
        self.assertIn("navigator.serial.requestPort()", html)
        self.assertIn("connect-src 'none'", html)
        self.assertNotIn("localStorage", html)

    def test_package_is_deterministic_and_checksums_match(self):
        with tempfile.TemporaryDirectory() as root:
            first = helper.package(Path(root) / "first")
            second = helper.package(Path(root) / "second")
            for a, b in zip(first, second):
                self.assertEqual(a.read_bytes(), b.read_bytes())
            with zipfile.ZipFile(first[1]) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(set(archive.namelist()), {
                    helper.HTML_NAME, "README_RU.md", "LICENSE", "SHA256SUMS.txt"})
                self.assertEqual(archive.read(helper.HTML_NAME), first[0].read_bytes())
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
