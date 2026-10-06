#!/usr/bin/env python3
"""Check deterministic allowlisted SDK packaging and the 17-asset release layout."""
from pathlib import Path
import hashlib
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import package_smartui_developer_kit as kit
import package_smartui_release as release

COMMIT = "12345678" + "0" * 32


class DeveloperKitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="smartui-developer-kit-test-")
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        for name in kit.SOURCES:
            target = self.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(kit.ROOT / name, target)

    def tearDown(self):
        self.temp.cleanup()

    def test_exact_sources_checksums_manifest_and_offline_links(self):
        path = kit.package(self.root / "out", COMMIT, root=self.source)
        with zipfile.ZipFile(path) as archive:
            expected = set(kit.SOURCES) | {"README.md", kit.MANIFEST_NAME, "SHA256SUMS.txt"}
            self.assertEqual(set(archive.namelist()), expected)
            self.assertEqual(len(archive.namelist()), len(expected))
            for name in kit.SOURCES:
                self.assertEqual(archive.read(name), (self.source / name).read_bytes())
            checksums = dict(line.split("  ", 1)[::-1] for line in archive.read("SHA256SUMS.txt").decode().splitlines())
            self.assertEqual(set(checksums), expected - {"SHA256SUMS.txt"})
            for name, sha in checksums.items():
                self.assertEqual(sha, hashlib.sha256(archive.read(name)).hexdigest())
            manifest = json.loads(archive.read(kit.MANIFEST_NAME))
            self.assertEqual(manifest["source_commit"], COMMIT)
            self.assertEqual(manifest["firmware_version"], release.VERSION)
            self.assertEqual(manifest["api_version"], 1)
            self.assertEqual({f["name"] for f in manifest["files"]}, set(kit.SOURCES) | {"README.md"})
            for entry in manifest["files"]:
                raw = archive.read(entry["name"])
                self.assertEqual((entry["bytes"], entry["sha256"]), (len(raw), hashlib.sha256(raw).hexdigest()))
            for name in ("docs/SMARTUI_API_RU.md", "docs/SMARTUI_API_EN.md"):
                self.assertIn("../../" + name, archive.read("tools/smartui-api/README.md").decode())

    def test_deterministic_bytes_and_exact_source_identity(self):
        first = kit.package(self.root / "one", COMMIT, root=self.source).read_bytes()
        second = kit.package(self.root / "two", COMMIT, root=self.source).read_bytes()
        other = kit.package(self.root / "other", "87654321" + "0" * 32, root=self.source).read_bytes()
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)

    def test_local_secrets_caches_and_unlisted_files_are_excluded(self):
        for name in ("tools/smartui-api/.env", "tools/smartui-api/node_modules/test.js",
                     "tools/smartui-api/__pycache__/test.pyc", "tools/smartui-api/local-notes.md"):
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("local fixture, not for distribution", encoding="utf-8")
        with zipfile.ZipFile(kit.package(self.root / "out", COMMIT, root=self.source)) as archive:
            self.assertFalse(any("local-notes" in n or "node_modules" in n or "__pycache__" in n or n.endswith(".env")
                                 for n in archive.namelist()))

    def test_missing_or_empty_source_is_rejected_without_archive(self):
        source = self.source / kit.SOURCES[0]
        source.unlink()
        for missing in (True, False):
            if not missing:
                source.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "regular nonempty"):
                kit.package(self.root / "out", COMMIT, root=self.source)
            self.assertFalse((self.root / "out" / kit.ZIP_NAME).exists())

    def test_invalid_commit_and_overwrite_are_rejected(self):
        for commit in ("", "12345678", "A" * 40, COMMIT + "+dirty"):
            with self.assertRaisesRegex(ValueError, "exact-source commit"):
                kit.package(self.root / "out", commit, root=self.source)
        path = kit.package(self.root / "out", COMMIT, root=self.source)
        original = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "overwrite"):
            kit.package(self.root / "out", COMMIT, root=self.source)
        self.assertEqual(path.read_bytes(), original)

    def test_release_contains_17_assets_and_kit_in_manifest_and_all_boards_zip(self):
        # Synthetic images only: hardware/image validators have their own tests.
        marker = b"SmartUI-source:" + COMMIT[:8].encode() + b"\0"
        files = []
        for name in release.FIRMWARE_NAMES:
            path = self.root / name
            raw = b"\0" * 32 + marker.ljust(256, b"\xff") + b"\0" * 224 if name.endswith(".uf2") else marker
            path.write_bytes(raw)
            files.append((path, name))
        notes = self.root / release.NOTES_NAME
        notes.write_text(f"SmartUI {release.VERSION} test package\n", encoding="utf-8")
        with patch.object(release, "validate_stage"):
            result = release.package_release(self.root / "release", files, notes, COMMIT)
        output = Path(result["directory"])
        self.assertEqual(len(result["assets"]), 17)
        manifest = json.loads((output / release.MANIFEST_NAME).read_text(encoding="utf-8"))
        self.assertEqual(manifest["asset_count"], 17)
        entry = manifest["developer_kit"]
        self.assertEqual((entry["name"], entry["source_commit"]), (kit.ZIP_NAME, COMMIT))
        self.assertEqual(entry["sha256"], release.digest(output / kit.ZIP_NAME))
        self.assertIn(kit.ZIP_NAME, {f["name"] for f in manifest["files"]})
        with zipfile.ZipFile(output / release.ARCHIVE_NAME) as archive:
            self.assertEqual(len(archive.namelist()), 16)
            self.assertEqual(archive.read(kit.ZIP_NAME), (output / kit.ZIP_NAME).read_bytes())


if __name__ == "__main__":
    unittest.main()
