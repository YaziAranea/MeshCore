#!/usr/bin/env python3
"""Verify helper-only packaging rejects altered firmware and false provenance."""
from copy import deepcopy
from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import package_smartui_helper_update as update

HELPER_SHA = "12345678" + "1" * 32


class HelperUpdateTests(unittest.TestCase):
    def setUp(self):
        # Exercise the historical 0.20 operation with its original asset names.
        # The public package now targets a newer release and must never use it.
        historical = self.enterContext(ExitStack())
        firmware_names = tuple(name.replace("_UI_0.21", "_UI_0.20")
                               for name in update.release.FIRMWARE_NAMES)
        historical.enter_context(patch.multiple(update.release, VERSION="0.20", TAG="smartui-0.20",
            NOTES_NAME="RELEASE_NOTES_SmartUI_0.20_RU.md", ARCHIVE_NAME="SmartUI_0.20_all-boards.zip",
            FIRMWARE_NAMES=firmware_names))
        historical.enter_context(patch.multiple(update.developer_kit, VERSION="0.20",
            ZIP_NAME="SmartUI_Developer_Kit_0.20.zip"))
        unchanged = set(firmware_names) | update.CHECKSUMS
        changed = update.NEW_HELPER | {update.developer_kit.ZIP_NAME, update.release.ARCHIVE_NAME,
                                      update.release.NOTES_NAME, update.release.MANIFEST_NAME}
        historical.enter_context(patch.multiple(update, UNCHANGED=unchanged, CHANGED=changed,
            OLD_ASSETS=unchanged | (changed - update.NEW_HELPER) | update.OLD_HELPER,
            NEW_ASSETS=unchanged | changed))
        self.temporary = tempfile.TemporaryDirectory(prefix="smartui-helper-update-test-")
        self.root = Path(self.temporary.name)
        self.base = self.root / "original"
        self.base.mkdir()
        for name in update.OLD_ASSETS - {update.release.MANIFEST_NAME, update.release.ARCHIVE_NAME}:
            marker = b"SmartUI-source:" + update.FIRMWARE_SHA[:8].encode() + b"\0"
            raw = (b"\0" * 32 + marker.ljust(256, b"\xff") + b"\0" * 224
                   if name.endswith(".uf2") else marker if name.endswith(".bin")
                   else ("original " + name).encode())
            (self.base / name).write_bytes(raw)
        firmware = [update.release.record(self.base / name, source_commit=update.FIRMWARE_SHA)
                    for name in sorted(update.release.FIRMWARE_NAMES)]
        self.manifest = {"schema_version": 2, "version": "0.20", "tag": "smartui-0.20",
                         "commit": update.FIRMWARE_SHA, "board_count": 7, "profile_count": 8,
                         "firmware_count": 12, "asset_count": 20, "firmware": firmware,
                         "developer_kit": {"source_commit": update.BASE_HELPER_SHA, "firmware_source_commit": update.FIRMWARE_SHA},
                         "files": [update.release.record(path) for path in sorted(self.base.iterdir())]}
        entries = {x["name"]: x for x in self.manifest["files"]}
        self.manifest.update(helper_version=update.BASE_HELPER_VERSION, helper_source_commit=update.BASE_HELPER_SHA,
                             documentation_source_commit=update.BASE_HELPER_SHA, firmware_source_commit=update.FIRMWARE_SHA,
                             helper={"version": update.BASE_HELPER_VERSION, "source_commit": update.BASE_HELPER_SHA,
                                     "html": entries["SmartUI_USB_Helper_2.8.html"], "zip": entries["SmartUI_USB_Helper_2.8.zip"]})
        (self.base / update.release.MANIFEST_NAME).write_text(json.dumps(self.manifest), encoding="utf-8")
        update.make_archive(self.base / update.release.ARCHIVE_NAME, list(self.base.iterdir()))
        self.pins = patch.multiple(update,
            BASE_MANIFEST_SHA256=update.release.digest(self.base / update.release.MANIFEST_NAME),
            BASE_ARCHIVE_SHA256=update.release.digest(self.base / update.release.ARCHIVE_NAME))
        self.pins.start()
        self.addCleanup(self.pins.stop)
        self.addCleanup(self.temporary.cleanup)

    def fake_helper(self, output):
        paths = (output / update.helper.HTML_NAME, output / update.helper.ZIP_NAME)
        for path in paths:
            path.write_bytes(("updated " + path.name).encode())
        return paths

    def fake_kit(self, output, commit, **kwargs):
        self.assertEqual(commit, HELPER_SHA)
        self.assertEqual(kwargs, {"firmware_commit": update.FIRMWARE_SHA})
        path = output / update.developer_kit.ZIP_NAME
        path.write_bytes(b"updated SDK fixture")
        return path

    def prepare(self, output):
        (self.root / update.release.NOTES_NAME).write_text("SmartUI 0.20 Helper 2.9 update\n", encoding="utf-8")
        with patch.object(update, "ROOT", self.root), \
             patch.object(update, "resolve_helper_commit", return_value=HELPER_SHA), \
             patch.object(update.helper, "package", side_effect=self.fake_helper), \
             patch.object(update.developer_kit, "package", side_effect=self.fake_kit):
            return update.prepare_update(self.base, output, HELPER_SHA)

    def test_six_replacements_preserve_fourteen_assets_and_distinct_commits(self):
        before = {path.name: path.read_bytes() for path in self.base.iterdir()}
        result = self.prepare(self.root / "new")
        output = Path(result["directory"])
        self.assertEqual({p.name for p in output.iterdir()}, update.NEW_ASSETS)
        self.assertEqual(len(update.NEW_ASSETS), 20)
        self.assertEqual({entry["name"] for entry in result["upload_only"]}, update.CHANGED)
        self.assertEqual(len(result["upload_only"]), 6)
        self.assertEqual(set(result["preserve_existing_asset_ids"]), update.UNCHANGED)
        self.assertEqual(len(update.UNCHANGED), 14)
        self.assertEqual(set(result["remove_only_after_replacements_verified"]), update.OLD_HELPER)
        self.assertFalse(result["firmware_rebuilt"])
        for name in update.UNCHANGED:
            self.assertEqual((output / name).read_bytes(), before[name])
        self.assertEqual({path.name: path.read_bytes() for path in self.base.iterdir()}, before)
        manifest = json.loads((output / update.release.MANIFEST_NAME).read_text(encoding="utf-8"))
        self.assertEqual(manifest["firmware"], self.manifest["firmware"])
        self.assertEqual(manifest["commit"], update.FIRMWARE_SHA)
        self.assertEqual(manifest["firmware_source_commit"], update.FIRMWARE_SHA)
        self.assertEqual(manifest["helper_source_commit"], HELPER_SHA)
        self.assertEqual(manifest["documentation_source_commit"], HELPER_SHA)
        self.assertEqual(manifest["helper"], {"version": "2.9", "source_commit": HELPER_SHA,
            "html": update.release.record(output / update.helper.HTML_NAME),
            "zip": update.release.record(output / update.helper.ZIP_NAME)})
        self.assertEqual(manifest["developer_kit"]["source_commit"], HELPER_SHA)
        self.assertEqual(manifest["developer_kit"]["firmware_source_commit"], update.FIRMWARE_SHA)
        self.assertEqual({entry["name"] for entry in manifest["files"]},
                         update.NEW_ASSETS - {update.release.MANIFEST_NAME, update.release.ARCHIVE_NAME})
        with zipfile.ZipFile(output / update.release.ARCHIVE_NAME) as archive:
            self.assertEqual(len(archive.namelist()), 19)
            for name in archive.namelist():
                self.assertEqual(archive.read(name), (output / name).read_bytes())

    def test_deterministic_output_and_no_overwrite(self):
        a = Path(self.prepare(self.root / "a")["directory"])
        b = Path(self.prepare(self.root / "b")["directory"])
        for path in a.iterdir():
            self.assertEqual(path.read_bytes(), (b / path.name).read_bytes())
        with self.assertRaisesRegex(ValueError, "overwrite"):
            self.prepare(a)

    def test_rejects_tampered_base_firmware_checksums_and_helper(self):
        for name in (next(iter(update.release.FIRMWARE_NAMES)), "SHA256SUMS.txt", "SmartUI_USB_Helper_2.8.html"):
            original = (self.base / name).read_bytes()
            (self.base / name).write_bytes(original + b"tampered")
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "Base asset mismatch"):
                self.prepare(self.root / "bad")
            self.assertFalse((self.root / "bad").exists())
            (self.base / name).write_bytes(original)

    def test_rejects_self_consistent_forged_manifest_and_archive(self):
        path = self.base / update.release.MANIFEST_NAME
        altered = deepcopy(self.manifest)
        altered["commit"] = HELPER_SHA
        path.write_text(json.dumps(altered), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "pinned public.*manifest"):
            update.validate_base(self.base)

    def test_rejects_modified_base_archive_and_extra_file(self):
        path = self.base / update.release.ARCHIVE_NAME
        original = path.read_bytes()
        path.write_bytes(original + b"trailer")
        with self.assertRaisesRegex(ValueError, "pinned public.*archive"):
            update.validate_base(self.base)
        path.write_bytes(original)
        (self.base / "unexpected.txt").write_bytes(b"x")
        with self.assertRaisesRegex(ValueError, "Asset set mismatch"):
            update.validate_base(self.base)

    def test_rejects_regressed_or_mixed_base_helper_provenance(self):
        for field, wrong in (("helper_version", "2.7"), ("helper_source_commit", HELPER_SHA),
                             ("firmware_source_commit", HELPER_SHA), ("documentation_source_commit", HELPER_SHA)):
            manifest = deepcopy(self.manifest)
            manifest[field] = wrong
            path = self.base / update.release.MANIFEST_NAME
            path.write_text(json.dumps(manifest), encoding="utf-8")
            # Even a newly trusted root must have a consistent prior Helper source.
            with patch.object(update, "BASE_MANIFEST_SHA256", update.release.digest(path)):
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, "base Helper identity"):
                    update.validate_base(self.base)

    def test_rejects_output_inside_immutable_base(self):
        with self.assertRaisesRegex(ValueError, "inside the immutable"):
            self.prepare(self.base / "new")

    def test_base_change_after_initial_verification_cannot_relabel_firmware(self):
        validate = update.validate_base
        def raced(folder):
            verified = validate(folder)
            path = folder / update.release.FIRMWARE_NAMES[0]
            path.write_bytes(path.read_bytes() + b"changed after verification")
            return verified
        with patch.object(update, "validate_base", side_effect=raced):
            with self.assertRaisesRegex(ValueError, "Immutable firmware/checksum changed"):
                self.prepare(self.root / "raced")
        self.assertFalse((self.root / "raced").exists())


class CurrentReleaseGuardTests(unittest.TestCase):
    def test_new_release_checkout_cannot_run_historical_helper_update(self):
        with patch.object(update, "resolve_helper_commit") as resolve, \
             patch.object(update, "validate_base") as validate:
            with self.assertRaisesRegex(ValueError, "Historical Helper updater.*0.20"):
                update.prepare_update(Path("unused-base"), Path("unused-output"))
            resolve.assert_not_called()
            validate.assert_not_called()


class ActualGitSourceGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="smartui-helper-git-guard-")
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "SmartUI guard test")
        (self.root / ".gitignore").write_text("platformio.local.ini\n", encoding="utf-8")
        (self.root / "README.md").write_text("base\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "firmware fixture")
        self.base = self.git("rev-parse", "HEAD").strip().decode()
        (self.root / "README.md").write_text("helper docs\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "helper fixture")
        self.head = self.git("rev-parse", "HEAD").strip().decode()
        self.pin = patch.multiple(update, FIRMWARE_SHA=self.base, BASE_HELPER_SHA=self.base)
        self.pin.start()
        self.addCleanup(self.pin.stop)

    def git(self, *arguments):
        return subprocess.check_output(["git", *arguments], cwd=self.root, stderr=subprocess.STDOUT)

    def test_clean_actual_head_and_explicit_identity(self):
        self.assertEqual(update.resolve_helper_commit(self.head, root=self.root), self.head)
        with self.assertRaisesRegex(ValueError, "differs from checkout"):
            update.resolve_helper_commit(HELPER_SHA, root=self.root)

    def test_rejects_tracked_dirty_untracked_and_ignored_override(self):
        path = self.root / "README.md"
        path.write_text("dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "dirty tracked"):
            update.resolve_helper_commit(root=self.root)
        path.write_text("helper docs\n", encoding="utf-8")
        extra = self.root / "extra.txt"
        extra.write_text("untracked\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "untracked"):
            update.resolve_helper_commit(root=self.root)
        extra.unlink()
        override = self.root / "platformio.local.ini"
        override.write_text("", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "platformio.local.ini"):
            update.resolve_helper_commit(root=self.root)
        override.unlink()
        self.assertEqual(update.resolve_helper_commit(root=self.root), self.head)

    def test_rejects_reusing_the_previous_helper_source(self):
        with patch.object(update, "BASE_HELPER_SHA", self.head):
            with self.assertRaisesRegex(ValueError, "new full source commit"):
                update.resolve_helper_commit(root=self.root)

    def test_requires_descending_from_the_published_helper(self):
        with patch.object(update, "BASE_HELPER_SHA", "f" * 40):
            with self.assertRaises(subprocess.CalledProcessError):
                update.resolve_helper_commit(root=self.root)

    def test_rejects_actual_firmware_source_change(self):
        source = self.root / "src/main.cpp"
        source.parent.mkdir()
        source.write_text("int changed;\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "unexpected firmware change")
        with self.assertRaisesRegex(ValueError, "changes firmware"):
            update.resolve_helper_commit(root=self.root)


if __name__ == "__main__":
    unittest.main()
