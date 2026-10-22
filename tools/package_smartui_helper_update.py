#!/usr/bin/env python3
"""Prepare Helper 2.9 for the existing SmartUI 0.20 release, without publishing.

The original twelve firmware files, their checksum files and their source SHA
remain unchanged. Only six assets are replaced. This deliberately does not use
the firmware publication workflow, move a tag, build firmware or call GitHub.
The base bundle must be the exact current public Helper 2.8 / SmartUI 0.20 bundle, already downloaded
and verified by the release operator. Output is a new complete twenty-file
bundle; the JSON result identifies the six files eligible for upload.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

import package_smartui_release as release
import package_smartui_developer_kit as developer_kit
import package_usb_helper as helper

ROOT = Path(__file__).resolve().parents[1]
FIRMWARE_SHA = "b3be1cc01d229cb75d48fe206fadde48a0e25b3f"
BASE_MANIFEST_SHA256 = "c096363d660c8dabe2855f005dbc24b97b78a4c53e7019e4f64a931823bec7f1"
BASE_ARCHIVE_SHA256 = "f96f93340f9d70567a850f6290c413c8f68e5f17cd4b1a443c846467c686862e"
BASE_HELPER_SHA = "93a7bca300e57343e1871df3b573538561ce67da"
BASE_HELPER_VERSION = "2.8"
HELPER_VERSION = "2.9"
RELEASE_ID = 414030602
OLD_HELPER = {"SmartUI_USB_Helper_2.8.html", "SmartUI_USB_Helper_2.8.zip"}
NEW_HELPER = {"SmartUI_USB_Helper_2.9.html", "SmartUI_USB_Helper_2.9.zip"}
CHECKSUMS = {"SHA256SUMS.txt", "SHA256SUMS-ESP32.txt"}
UNCHANGED = set(release.FIRMWARE_NAMES) | CHECKSUMS
CHANGED = NEW_HELPER | {developer_kit.ZIP_NAME, release.ARCHIVE_NAME,
                        release.NOTES_NAME, release.MANIFEST_NAME}
OLD_ASSETS = UNCHANGED | (CHANGED - NEW_HELPER) | OLD_HELPER
NEW_ASSETS = UNCHANGED | CHANGED


def records(items, description):
    result = {item["name"]: item for item in items}
    release.require(len(result) == len(items), "Duplicate names: " + description)
    return result


def regular_files(folder: Path, names: set[str]) -> dict[str, Path]:
    release.require(folder.is_dir() and not folder.is_symlink(), f"Regular directory required: {folder}")
    children = list(folder.iterdir())
    release.require(all(p.is_file() and not p.is_symlink() for p in children),
                    f"Only regular asset files are allowed: {folder}")
    result = {p.name: p for p in children}
    release.require(set(result) == names, f"Asset set mismatch: {sorted(set(result) ^ names)}")
    return result


def validate_base(folder: Path) -> dict:
    """Verify immutable roots of trust before trusting any supplied metadata."""
    files = regular_files(folder, OLD_ASSETS)
    release.require(release.digest(files[release.MANIFEST_NAME]) == BASE_MANIFEST_SHA256,
                    "Base manifest is not the pinned public Helper 2.8 / SmartUI 0.20 manifest")
    release.require(release.digest(files[release.ARCHIVE_NAME]) == BASE_ARCHIVE_SHA256,
                    "Base all-boards archive is not the pinned public Helper 2.8 / SmartUI 0.20 archive")
    manifest = json.loads(files[release.MANIFEST_NAME].read_text(encoding="utf-8"))
    release.require((manifest["schema_version"], manifest["version"], manifest["tag"], manifest["commit"])
                    == (2, "0.20", "smartui-0.20", FIRMWARE_SHA), "Unexpected base firmware identity")
    release.require((manifest["board_count"], manifest["profile_count"],
                     manifest["firmware_count"], manifest["asset_count"]) == (7, 8, 12, 20),
                    "Unexpected base release counts")
    entries = records(manifest["files"], "base manifest")
    release.require(set(entries) == OLD_ASSETS - {release.MANIFEST_NAME, release.ARCHIVE_NAME},
                    "Base manifest must cover all eighteen non-recursive payloads")
    release.require(manifest["helper_version"] == BASE_HELPER_VERSION and
                    manifest["helper_source_commit"] == manifest["documentation_source_commit"] == BASE_HELPER_SHA and
                    manifest["firmware_source_commit"] == FIRMWARE_SHA, "Unexpected base Helper identity")
    release.require(manifest["helper"] == {"version": BASE_HELPER_VERSION, "source_commit": BASE_HELPER_SHA,
                    "html": entries["SmartUI_USB_Helper_2.8.html"],
                    "zip": entries["SmartUI_USB_Helper_2.8.zip"]}, "Base Helper provenance mismatch")
    release.require(manifest["developer_kit"]["source_commit"] == BASE_HELPER_SHA and
                    manifest["developer_kit"]["firmware_source_commit"] == FIRMWARE_SHA,
                    "Base SDK provenance mismatch")
    for name, entry in entries.items():
        release.require(entry["bytes"] == files[name].stat().st_size and
                        entry["sha256"] == release.digest(files[name]), "Base asset mismatch: " + name)
    firmware = records(manifest["firmware"], "base firmware")
    release.require(set(firmware) == set(release.FIRMWARE_NAMES), "Base firmware inventory differs")
    for name, entry in firmware.items():
        release.require(entry["source_commit"] == FIRMWARE_SHA and
                        all(entry[key] == entries[name][key] for key in ("name", "bytes", "sha256")),
                        "Base firmware provenance mismatch: " + name)
        release.validate_source_identity(files[name], FIRMWARE_SHA)
    release.verify_archive(files[release.ARCHIVE_NAME],
                           [files[name] for name in sorted(OLD_ASSETS - {release.ARCHIVE_NAME})])
    return manifest


def resolve_helper_commit(explicit: str | None = None, *, root: Path = ROOT) -> str:
    root = Path(root)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root).decode("ascii").strip()
    release.require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None and commit not in {FIRMWARE_SHA, BASE_HELPER_SHA},
                    "Helper update requires a new full source commit")
    release.require(explicit is None or explicit == commit, "Helper commit differs from checkout HEAD")
    release.require_clean_checkout(root)
    subprocess.run(["git", "merge-base", "--is-ancestor", FIRMWARE_SHA, commit], cwd=root, check=True)
    subprocess.run(["git", "merge-base", "--is-ancestor", BASE_HELPER_SHA, commit], cwd=root, check=True)
    # A helper-only update must not silently include firmware changes. The
    # actual images are additionally pinned and compared byte for byte below.
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", "--no-renames", FIRMWARE_SHA, commit, "--"], cwd=root,
    ).decode("utf-8").splitlines()
    allowed_roots = ("tools/", "docs/", ".github/")
    allowed_docs = {"README.md", "README_RU.md", release.NOTES_NAME}
    release.require(changed and all(path in allowed_docs or path.startswith(allowed_roots) for path in changed),
                    "Helper-only source commit changes firmware or another unexpected path")
    return commit


def make_archive(path: Path, payloads: list[Path]) -> None:
    with zipfile.ZipFile(path, "x", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for payload in sorted(payloads):
            info = zipfile.ZipInfo(payload.name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload.read_bytes(), compresslevel=9)
    release.verify_archive(path, payloads)


def prepare_update(base: Path, output: Path, explicit_commit: str | None = None) -> dict:
    """Create a new complete local bundle; return the restricted upload plan."""
    # This historical operation is pinned to the old release and source SHA.
    # Refuse newer checkouts before inspecting files or resolving their HEAD.
    release.require(developer_kit.VERSION == release.VERSION == "0.20" and release.TAG == "smartui-0.20",
                    "Historical Helper updater requires the SmartUI 0.20 checkout")
    base, output = Path(base).resolve(), Path(output).resolve()
    release.require(not output.exists(), f"Refusing to overwrite an existing output: {output}")
    release.require(base not in output.parents, "Output must not be inside the immutable base bundle")
    commit = resolve_helper_commit(explicit_commit)
    original = validate_base(base)
    release.require({helper.HTML_NAME, helper.ZIP_NAME} == NEW_HELPER,
                    "This updater requires exactly Helper 2.9")
    notes = ROOT / release.NOTES_NAME
    release.validate_release_notes(notes.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="smartui-helper29-update-") as temporary:
        stage = Path(temporary)
        for name in sorted(UNCHANGED):
            shutil.copy2(base / name, stage / name)
        shutil.copy2(notes, stage / release.NOTES_NAME)
        html, helper_zip = helper.package(stage)
        kit = developer_kit.package(stage, commit, firmware_commit=FIRMWARE_SHA)
        manifest = deepcopy(original)
        manifest.update(firmware_source_commit=FIRMWARE_SHA, helper_source_commit=commit,
                        documentation_source_commit=commit, helper_version=HELPER_VERSION)
        manifest["helper"] = {"version": HELPER_VERSION, "source_commit": commit,
                              "html": release.record(html), "zip": release.record(helper_zip)}
        manifest["developer_kit"] = release.record(
            kit, source_commit=commit, firmware_source_commit=FIRMWARE_SHA,
            cli_version=1, transport="companion-cli", companion_protocol_version=14, local_only=True)
        manifest["files"] = [release.record(path) for path in sorted(stage.iterdir())]
        manifest_path = stage / release.MANIFEST_NAME
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8", newline="\n")
        payloads = sorted(stage.iterdir())
        make_archive(stage / release.ARCHIVE_NAME, payloads)
        regular_files(stage, NEW_ASSETS)
        original_files = records(original["files"], "original manifest")
        for name in sorted(UNCHANGED):
            expected = original_files[name]
            release.require((stage / name).stat().st_size == expected["bytes"] and
                            release.digest(stage / name) == expected["sha256"] and
                            (stage / name).read_bytes() == (base / name).read_bytes(),
                            "Immutable firmware/checksum changed: " + name)
        release.require(manifest["firmware"] == original["firmware"] and
                        manifest["commit"] == FIRMWARE_SHA, "Firmware metadata changed")
        # Refuse a race with source edits during packaging. Rechecking HEAD
        # also prevents assigning artifacts to a commit created concurrently.
        release.require(resolve_helper_commit(commit) == commit, "Helper source changed during packaging")
        shutil.copytree(stage, output)
    return {
        "directory": str(output), "tag": release.TAG, "release_id": RELEASE_ID,
        "firmware_source_commit": FIRMWARE_SHA, "helper_source_commit": commit,
        "helper_version": HELPER_VERSION, "tag_and_target_commitish_must_remain": FIRMWARE_SHA,
        "upload_only": [release.record(output / name) for name in sorted(CHANGED)],
        "preserve_existing_asset_ids": sorted(UNCHANGED),
        "remove_only_after_replacements_verified": sorted(OLD_HELPER),
        "expected_final_asset_count": 20, "firmware_rebuilt": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path, help="verified current public twenty-asset Helper 2.8 / SmartUI 0.20 bundle")
    parser.add_argument("output", type=Path, help="new output directory; never overwrite existing assets")
    parser.add_argument("--commit", help="must equal the clean Helper checkout HEAD")
    args = parser.parse_args(argv)
    try:
        result = prepare_update(args.base, args.output, args.commit)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        parser.exit(1, f"[FAIL] {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    main()
