#!/usr/bin/env python3
"""Check deterministic allowlisted SDK packaging and the 19-asset release layout."""
from pathlib import Path
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import shutil
import subprocess
import sys
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
            self.assertEqual(manifest["cli_version"], 1)
            self.assertEqual(manifest["transport"], "companion-cli")
            self.assertEqual((manifest["command"], manifest["response"]), (66, 29))
            self.assertFalse(manifest["sync"])
            self.assertFalse(manifest["events"])
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["distribution"], "public")
            self.assertEqual(manifest["stage"], "release")
            self.assertNotIn("base_source_commit", manifest)
            self.assertEqual(path.name, kit.ZIP_NAME)
            readme = archive.read("README.md").decode("utf-8")
            self.assertIn("SmartUI 0.16", readme)
            self.assertIn("USB Helper 2.3", readme)
            self.assertIn("[Справочник команд](docs/CONSOLE_COMMANDS_RU.md)", readme)
            self.assertNotIn("LOCAL DEVELOPMENT", readme)
            self.assertEqual({f["name"] for f in manifest["files"]}, set(kit.SOURCES) | {"README.md"})
            for entry in manifest["files"]:
                raw = archive.read(entry["name"])
                self.assertEqual((entry["bytes"], entry["sha256"]), (len(raw), hashlib.sha256(raw).hexdigest()))
            for name in ("docs/SMARTUI_CLI_RU.md",):
                self.assertIn("../../" + name, archive.read("tools/smartui-cli/README.md").decode())

    def test_deterministic_bytes_and_exact_source_identity(self):
        first = kit.package(self.root / "one", COMMIT, root=self.source).read_bytes()
        second = kit.package(self.root / "two", COMMIT, root=self.source).read_bytes()
        other = kit.package(self.root / "other", "87654321" + "0" * 32, root=self.source).read_bytes()
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)

    def test_current_release_and_optional_development_names(self):
        self.assertEqual(kit.VERSION, "0.16")
        self.assertEqual(kit.ZIP_NAME, "SmartUI_Developer_Kit_0.16.zip")
        self.assertEqual(kit.DEVELOPMENT_ZIP_NAME, "SmartUI_Developer_Kit_0.16-development.zip")

    def test_local_secrets_caches_and_unlisted_files_are_excluded(self):
        for name in ("tools/smartui-cli/.env", "tools/smartui-cli/node_modules/test.js",
                     "tools/smartui-cli/__pycache__/test.pyc", "tools/smartui-cli/local-notes.md"):
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

    def test_development_manifest_and_name_do_not_claim_exact_release_source(self):
        # Simulate an edited working-tree file without creating a fake commit.
        edited = self.source / "tools/smartui-cli/smartui_cli.py"
        edited.write_bytes(edited.read_bytes() + b"\n# local development fixture\n")
        path = kit.package(self.root / "dev", COMMIT, root=self.source, development=True)
        self.assertEqual(path.name, kit.DEVELOPMENT_ZIP_NAME)
        self.assertNotEqual(path.name, kit.ZIP_NAME)
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read(kit.MANIFEST_NAME))
            self.assertEqual(manifest["schema_version"], 2)
            self.assertEqual(manifest["stage"], "development")
            self.assertEqual(manifest["distribution"], "local")
            self.assertEqual(manifest["base_firmware_version"], kit.VERSION)
            self.assertEqual(manifest["base_source_commit"], COMMIT)
            self.assertEqual(manifest["source_snapshot"], "working-tree")
            self.assertIs(manifest["exact_source_commit"], False)
            self.assertNotIn("source_commit", manifest)
            self.assertNotIn("firmware_version", manifest)
            self.assertEqual(archive.read("tools/smartui-cli/smartui_cli.py"), edited.read_bytes())
            self.assertIn("tools/smartui-cli/tests/test_smartui_cli.py", archive.namelist())
            readme = archive.read("README.md").decode("utf-8")
            self.assertIn("LOCAL DEVELOPMENT", readme)
            self.assertIn("NOT the exact commit", readme)
            self.assertIn("USB Helper 2.3", readme)
            for entry in manifest["files"]:
                raw = archive.read(entry["name"])
                self.assertEqual((entry["bytes"], entry["sha256"]), (len(raw), hashlib.sha256(raw).hexdigest()))

    def test_development_is_deterministic_and_does_not_overwrite_release(self):
        output = self.root / "both"
        release_path = kit.package(output, COMMIT, root=self.source)
        released = release_path.read_bytes()
        development = kit.package(output, COMMIT, root=self.source, development=True)
        second = kit.package(self.root / "another", COMMIT, root=self.source, development=True)
        self.assertEqual(development.read_bytes(), second.read_bytes())
        self.assertEqual(release_path.read_bytes(), released)
        with self.assertRaisesRegex(ValueError, "overwrite"):
            kit.package(output, COMMIT, root=self.source, development=True)
        self.assertEqual(release_path.read_bytes(), released)
        with self.assertRaisesRegex(ValueError, "base commit"):
            kit.package(self.root / "bad", COMMIT + "+dirty", root=self.source, development=True)

    def test_development_includes_only_allowlist_and_requires_new_sdk_files(self):
        secret = self.source / "tools/smartui-cli/.env"
        secret.write_text("local fixture", encoding="utf-8")
        path = kit.package(self.root / "dev", COMMIT, root=self.source, development=True)
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(set(archive.namelist()), set(kit.SOURCES) | {"README.md", kit.MANIFEST_NAME, "SHA256SUMS.txt"})
            self.assertNotIn("tools/smartui-cli/.env", archive.namelist())
        (self.source / "tools/smartui-cli/smartui_cli.py").unlink()
        with self.assertRaisesRegex(ValueError, "regular nonempty"):
            kit.package(self.root / "missing", COMMIT, root=self.source, development=True)
        self.assertFalse((self.root / "missing" / kit.DEVELOPMENT_ZIP_NAME).exists())

    def test_cli_requires_unambiguous_release_or_development_identity(self):
        for arguments in (["--development", "--commit", COMMIT],
                          ["--base-commit", COMMIT], ["--development"]):
            with self.subTest(arguments=arguments), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                kit.main([str(self.root / "invalid-cli"), *arguments])
            self.assertEqual(caught.exception.code, 2)
        with redirect_stdout(io.StringIO()) as stdout:
            path = kit.main([str(self.root / "cli"), "--development", "--base-commit", COMMIT])
        self.assertEqual(path.name, kit.DEVELOPMENT_ZIP_NAME)
        self.assertIn(kit.DEVELOPMENT_ZIP_NAME, stdout.getvalue())
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(json.loads(archive.read(kit.MANIFEST_NAME))["stage"], "development")

    def test_extracted_development_sdk_tests_are_self_contained(self):
        archive_path = kit.package(self.root / "dev", COMMIT, root=self.source, development=True)
        extracted = self.root / "extracted"
        with zipfile.ZipFile(archive_path) as archive:
            expected = set(kit.SOURCES) | {"README.md", kit.MANIFEST_NAME, "SHA256SUMS.txt"}
            self.assertEqual(set(archive.namelist()), expected)
            archive.extractall(extracted)  # Only the just-verified generated allowlist.
        result = subprocess.run(
            [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tools/smartui-cli/tests", "-q"],
            cwd=extracted, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        javascript = subprocess.run(
            ["node", "--test", "tools/usb-helper/test_api.js"], cwd=extracted,
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(javascript.returncode, 0, javascript.stdout + javascript.stderr)

    def test_release_contains_19_assets_and_kit_in_manifest_and_all_boards_zip(self):
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
        self.assertEqual(len(result["assets"]), 19)
        manifest = json.loads((output / release.MANIFEST_NAME).read_text(encoding="utf-8"))
        self.assertEqual(manifest["asset_count"], 19)
        self.assertEqual(manifest["board_count"], 7)
        self.assertEqual(manifest["firmware_count"], 11)
        self.assertEqual(len(manifest["firmware"]), 11)
        entry = manifest["developer_kit"]
        self.assertEqual((entry["name"], entry["source_commit"]), (kit.ZIP_NAME, COMMIT))
        self.assertEqual(entry["sha256"], release.digest(output / kit.ZIP_NAME))
        self.assertIn(kit.ZIP_NAME, {f["name"] for f in manifest["files"]})
        with zipfile.ZipFile(output / release.ARCHIVE_NAME) as archive:
            self.assertEqual(len(archive.namelist()), 18)
            self.assertEqual(archive.read(kit.ZIP_NAME), (output / kit.ZIP_NAME).read_bytes())


if __name__ == "__main__":
    unittest.main()
