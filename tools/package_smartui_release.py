#!/usr/bin/env python3
"""Validate and package one exact-source, six-board SmartUI experimental release.

Reads PlatformIO outputs or the release-named CI firmware directory. Does not
build, flash, upload, move a tag, or overwrite an existing output directory.
V3 retains its narrowly guarded FS2 recovery and prepared clean-install SPIFFS;
V4.3/Paper storage behavior is deliberately unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

import validate_release_esp32 as esp32
import validate_release_uf2 as uf2
import validate_release_v3 as v3


ROOT = Path(__file__).resolve().parents[1]
VERSION = "2.1.0-experimental.2"
TAG = "v" + VERSION
NOTES_NAME = f"RELEASE_NOTES_{TAG}_RU.md"
ARCHIVE_NAME = f"MeshCore_SmartUI_{VERSION}_all-six-boards.zip"
MANIFEST_NAME = "RELEASE-MANIFEST.json"
NRF_ENVS = (
    "Heltec_t096_companion_radio_ble_femon",
    "Heltec_t114_companion_radio_ble",
    "ProMicro_ra62_companion_radio_ble",
)
ESP_ENVS = (
    "Heltec_v3_companion_radio_ble_smartui",
    "heltec_v4_3_companion_radio_ble_femon_smartui",
    "Heltec_Wireless_Paper_companion_radio_ble_smartui_full",
)
ESP_PAIRS = (v3.PAIR, *esp32.EXPECTED)
BOARD_NAMES = ("T096 FEM ON", "T114", "ProMicro RA62",
               "Heltec V3 OLED", "Heltec V4.3 OLED FEM ON", "Wireless Paper FULL")
FIRMWARE_NAMES = tuple(uf2.EXPECTED) + tuple(
    pair.stem + suffix for pair in ESP_PAIRS
    for suffix in ("-freshInstall-merged.bin", "-update.bin")
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def require_clean_checkout(root: Path = ROOT) -> None:
    # Some inherited blobs still contain CRLF despite the newer eol=lf
    # attributes. A pristine Linux checkout consequently reports them dirty:
    # the clean filter normalizes the worktree before comparing it to HEAD.
    # Accept that false positive only when the ORIGINAL bytes and mode match
    # HEAD exactly. Do not ignore whitespace, normalize contents, or waive
    # real source changes merely because a build artifact already exists.
    result = subprocess.run(
        ["git", "diff", "--raw", "--no-renames", "--no-abbrev", "-z", "HEAD", "--"],
        cwd=root, capture_output=True, check=True,
    )
    entries = result.stdout.split(b"\0")
    require(entries[-1] == b"" and (len(entries) - 1) % 2 == 0,
            "unexpected Git raw diff format")
    for index in range(0, len(entries) - 1, 2):
        fields = entries[index].split()
        relative = entries[index + 1].decode("utf-8")
        error = f"refusing exact-source packaging from a dirty tracked checkout: {relative}"
        require(len(fields) == 5 and fields[0].startswith(b":"), error)
        old_mode, new_mode = fields[0][1:], fields[1]
        path = root / relative
        require(old_mode == new_mode and old_mode in {b"100644", b"100755"}
                and path.is_file() and not path.is_symlink(), error)
        original = subprocess.run(["git", "show", "HEAD:" + relative], cwd=root,
                                  capture_output=True, check=True).stdout
        require(path.read_bytes() == original, error)


def resolve_commit(explicit: str | None = None) -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                            capture_output=True, text=True, check=True)
    commit = result.stdout.strip()
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "invalid checkout commit")
    require(explicit is None or explicit == commit,
            "requested source commit differs from the checked-out HEAD")
    require_clean_checkout()
    return commit


def input_files(build_dir: Path, firmware_dir: Path | None = None) -> list[tuple[Path, str]]:
    if firmware_dir is not None:
        require(firmware_dir.is_dir(), f"firmware directory missing: {firmware_dir}")
        actual = {p.name for p in firmware_dir.iterdir() if p.suffix in {".uf2", ".bin"}}
        require(actual == set(FIRMWARE_NAMES), "firmware directory must contain exactly the nine release images")
        files = [(firmware_dir / name, name) for name in FIRMWARE_NAMES]
    else:
        files = [(build_dir / env / "firmware.uf2", name)
                 for env, name in zip(NRF_ENVS, uf2.EXPECTED)]
        for env, pair in zip(ESP_ENVS, ESP_PAIRS):
            files.extend((
                (build_dir / env / "firmware-merged.bin", pair.stem + "-freshInstall-merged.bin"),
                (build_dir / env / "firmware.bin", pair.stem + "-update.bin"),
            ))
    require(len(files) == 9 and {name for _, name in files} == set(FIRMWARE_NAMES),
            "six-board release contract must contain exactly nine firmware images")
    for source, _ in files:
        require(source.is_file() and not source.is_symlink() and source.stat().st_size > 0,
                f"regular nonempty build artifact missing: {source}")
    return files


def firmware_metadata(name: str, commit: str) -> dict:
    if name.endswith(".uf2"):
        index = tuple(uf2.EXPECTED).index(name)
        return {"board": BOARD_NAMES[index], "environment": NRF_ENVS[index],
                "source_commit": commit, "image_kind": "nrf52840-uf2-bootloader",
                "flash_offset": None}
    index = next(i for i, pair in enumerate(ESP_PAIRS) if name.startswith(pair.stem + "-"))
    fresh = name.endswith("-freshInstall-merged.bin")
    storage = {
        "contains_formatted_empty_spiffs": index == 0 and fresh,
        "prepared_clean_install_storage": index == 0 and fresh,
        "preserves_existing_filesystem": not fresh,
        "v3_fs2_recovery": index == 0,
        "hardware_storage_success_confirmed": False,
    }
    if index == 0:
        storage["warning"] = (
            "Fresh merged overwrites identity/settings even without Erase; clean installation only."
            if fresh else
            "App-only update preserves FS; FS2 may initialize exact-known-empty FS or run a confirmed user reset."
        )
    else:
        storage["warning"] = (
            "Storage unchanged: merged has no prepared SPIFFS; fresh erased installation may show STORAGE ERROR."
            if fresh else "App-only update; no new storage recovery or formatting policy."
        )
    return {"board": BOARD_NAMES[index + 3], "environment": ESP_ENVS[index],
            "source_commit": commit,
            "image_kind": "esp32-fresh-install-merged" if fresh else "esp32-application-update",
            "flash_offset": "0x00000" if fresh else "0x10000", "storage": storage}


def record(path: Path, **metadata) -> dict:
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": digest(path), **metadata}


def validate_stage(stage: Path, *, mkspiffs: Path | None = None,
                   sdkconfig: Path | None = None) -> None:
    for name, marker in uf2.EXPECTED.items():
        uf2.validate(stage / name, marker)
    for pair in esp32.EXPECTED:
        esp32.validate_pair(stage, pair)
    v3.validate_v3_pair(stage, mkspiffs=mkspiffs, sdkconfig=sdkconfig)


def verify_archive(archive: Path, paths: list[Path]) -> None:
    expected = {p.name: p for p in paths}
    with zipfile.ZipFile(archive) as zipped:
        names = zipped.namelist()
        require(len(names) == len(set(names)) and set(names) == set(expected),
                "ZIP entries differ from the exact six-board release payloads")
        require(zipped.testzip() is None, "ZIP CRC failure")
        for name, path in expected.items():
            raw = zipped.read(name)
            require(len(raw) == path.stat().st_size and hashlib.sha256(raw).hexdigest() == digest(path),
                    f"ZIP payload mismatch: {name}")


def package_release(output: Path, files: list[tuple[Path, str]], notes: Path, commit: str,
                    *, mkspiffs: Path | None = None, sdkconfig: Path | None = None) -> dict:
    output = output.resolve()
    require(not output.exists(), f"refusing to overwrite existing release directory: {output}")
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "source commit must be a full lowercase SHA")
    require(notes.is_file() and not notes.is_symlink(), f"release notes missing: {notes}")
    text = notes.read_text(encoding="utf-8-sig")
    require(text.strip() and "RELEASE_FINALIZATION" not in text, "release notes are unfinished")
    require(VERSION in text, "release notes must identify this exact experimental version")
    require(len(files) == 9 and {name for _, name in files} == set(FIRMWARE_NAMES),
            "packaging requires the exact nine-image six-board set")
    with tempfile.TemporaryDirectory(prefix="smartui-six-board-release-") as folder:
        stage = Path(folder)
        for source, name in files:
            require(source.is_file() and not source.is_symlink(), f"regular artifact missing: {source}")
            shutil.copy2(source, stage / name)
        validate_stage(stage, mkspiffs=mkspiffs, sdkconfig=sdkconfig)
        shutil.copy2(notes, stage / NOTES_NAME)
        for suffix, name in ((".uf2", "SHA256SUMS.txt"), (".bin", "SHA256SUMS-ESP32.txt")):
            rows = [f"{digest(path)}  {path.name}" for path in sorted(stage.glob("*" + suffix))]
            (stage / name).write_text("\n".join(rows) + "\n", encoding="ascii", newline="\n")
        payloads = sorted(stage.iterdir())
        manifest = {
            "schema_version": 2, "version": VERSION, "tag": TAG, "commit": commit,
            "experimental": True, "board_count": 6, "firmware_count": 9,
            "publication": {"draft": False, "prerelease": False, "make_latest": False},
            "firmware": [record(stage / name, **firmware_metadata(name, commit))
                         for name in sorted(FIRMWARE_NAMES)],
            "files": [record(path) for path in payloads],
        }
        manifest_path = stage / MANIFEST_NAME
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8", newline="\n")
        archive_payloads = sorted(payloads + [manifest_path])
        archive = stage / ARCHIVE_NAME
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
            for path in archive_payloads:
                info = zipfile.ZipInfo(path.name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                zipped.writestr(info, path.read_bytes(), compresslevel=9)
        verify_archive(archive, archive_payloads)
        require(len(list(stage.iterdir())) == 14, "release must contain exactly fourteen assets")
        shutil.copytree(stage, output)
    return {"directory": str(output), "tag": TAG, "commit": commit,
            "assets": [record(path) for path in sorted(output.iterdir())]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new release directory (must not exist)")
    parser.add_argument("--build-dir", type=Path, default=ROOT / ".pio/build")
    parser.add_argument("--firmware-dir", type=Path, help="CI directory with exactly nine release-named images")
    parser.add_argument("--commit", help="must equal the clean checkout's full HEAD SHA")
    parser.add_argument("--mkspiffs", type=Path, help="pinned PlatformIO mkspiffs used by the V3 build")
    parser.add_argument("--sdkconfig", type=Path, help="ESP32-S3 Arduino SDK configuration from the V3 build")
    args = parser.parse_args()
    try:
        commit = resolve_commit(args.commit)
        files = input_files(args.build_dir, args.firmware_dir)
        result = package_release(args.output, files, ROOT / NOTES_NAME, commit,
                                 mkspiffs=args.mkspiffs, sdkconfig=args.sdkconfig)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"[FAIL] {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
