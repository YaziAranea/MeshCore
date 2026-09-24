#!/usr/bin/env python3
"""Host regression for V4.3/Paper clean-install and update storage policy."""

from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import tempfile

from validate_release_esp32 import EXPECTED, validate_exact_application
from validate_release_fresh_spiffs import (
    FACTORY_SPIFFS_SHA256, LAYOUTS, validate_prepared_pair,
)
from validate_release_v3 import (
    BLOCK_SIZE, PAGE_SIZE, PARTITION_OFFSET, PARTITION_SECTOR,
    find_mkspiffs, inspect_prepared_spiffs, run_tool,
)
from package_smartui_release import TAG, VERSION, firmware_metadata


ROOT = Path(__file__).resolve().parents[1]


def partition_table(entries: list[tuple]) -> bytes:
    rows = b"".join(struct.pack("<HBBII16sI", 0x50AA, *entry) for entry in entries)
    rows += b"\xeb\xeb" + b"\xff" * 14 + hashlib.md5(rows).digest()
    return rows.ljust(PARTITION_SECTOR, b"\xff")


def application(marker: bytes, flash_code: int, factory_hash: str | None) -> bytes:
    payload = marker + b"\0synthetic storage-policy fixture\0"
    if factory_hash is not None:
        payload += factory_hash.encode("ascii") + b"\0"
    header = bytearray(24)
    header[0] = 0xE9
    header[1] = 1
    header[3] = flash_code << 4
    image = bytes(header) + struct.pack("<II", 0x3C000020, len(payload)) + payload
    checksum = 0xEF
    for value in payload:
        checksum ^= value
    image += b"\0" * (((len(image) + 16) & ~15) - len(image) - 1) + bytes([checksum])
    validate_exact_application(image)
    return image


def build_fixture(folder: Path, pair, tool: Path, *, include_hash: bool = True
                  ) -> tuple[Path, bytes, tuple[int, int]]:
    fixture = folder / f"fixture-{pair.stem}-{'bound' if include_hash else 'unbound'}"
    fixture.mkdir()
    offset, size = LAYOUTS[pair.stem]
    is_v4 = offset == 0xC90000
    app_size = 0x640000 if is_v4 else 0x330000
    app1_offset = 0x650000 if is_v4 else 0x340000
    flash_code = 4 if is_v4 else 3
    entries = [
        (1, 2, 0x9000, 0x5000, b"nvs", 0),
        (1, 0, 0xE000, 0x2000, b"otadata", 0),
        (0, 0x10, 0x10000, app_size, b"app0", 0),
        (0, 0x11, app1_offset, app_size, b"app1", 0),
        (1, 0x82, offset, size, b"spiffs", 0),
        (1, 3, offset + size, 0x10000, b"coredump", 0),
    ]
    update = application(
        pair.marker, flash_code,
        FACTORY_SPIFFS_SHA256[pair.stem] if include_hash else None)
    empty = fixture / "empty"
    empty.mkdir()
    fs_path = fixture / "fs.bin"
    run_tool(tool, "-c", empty, "-s", size, "-p", PAGE_SIZE, "-b", BLOCK_SIZE, fs_path)
    fs = fs_path.read_bytes()
    merged = bytearray(b"\xff" * (offset + size))
    merged[:24] = update[:24]
    merged[PARTITION_OFFSET:PARTITION_OFFSET + PARTITION_SECTOR] = partition_table(entries)
    merged[0x10000:0x10000 + len(update)] = update
    merged[offset:offset + size] = fs
    output = fixture / "pair"
    output.mkdir()
    (output / f"{pair.stem}-merged.bin").write_bytes(merged)
    (output / f"{pair.stem}-update.bin").write_bytes(update)
    return output, bytes(merged), (offset, size)


def section(text: str, name: str) -> str:
    marker = f"[{name}]"
    start = text.index(marker)
    end = text.find("\n[", start + len(marker))
    return text[start:] if end < 0 else text[start:end]


def main() -> None:
    tool = find_mkspiffs()
    passed = 0
    with tempfile.TemporaryDirectory(prefix="smartui-all-spiffs-") as raw_folder:
        folder = Path(raw_folder)
        fixtures = {}
        for pair in EXPECTED:
            directory, merged, layout = build_fixture(folder, pair, tool)
            result = validate_prepared_pair(directory, pair)
            assert result[4]["empty"] is True
            assert (result[4]["offset"], result[4]["size"]) == layout
            validate_exact_application((directory / f"{pair.stem}-update.bin").read_bytes())
            fixtures[pair.stem] = (merged, layout)
            passed += 1
            print(f"[PASS] {pair.stem}: exact-layout canonical empty SPIFFS; pure update")

        paper, paper_layout = fixtures["Paper_UI_0.05"]
        try:
            inspect_prepared_spiffs(paper, LAYOUTS["Heltec_V4.3_UI_0.05"])
        except ValueError as error:
            assert "layout mismatch" in str(error)
        else:
            raise AssertionError("Paper image accepted as V4.3 layout")
        passed += 1
        print("[PASS] rejects cross-board SPIFFS layout")

        offset, size = paper_layout
        erased = paper[:offset] + b"\xff" * size
        try:
            inspect_prepared_spiffs(erased, paper_layout)
        except ValueError as error:
            assert "erased" in str(error)
        else:
            raise AssertionError("erased SPIFFS accepted as formatted")
        passed += 1
        print("[PASS] rejects erased unformatted SPIFFS")

        pair = EXPECTED[1]
        missing_hash_dir, _, _ = build_fixture(folder, pair, tool, include_hash=False)
        try:
            validate_prepared_pair(missing_hash_dir, pair)
        except ValueError as error:
            assert "safe native recovery is not bound" in str(error)
        else:
            raise AssertionError("prepared image without runtime factory hash was accepted")
        passed += 1
        print("[PASS] rejects prepared merged not bound to safe native recovery hash")

    v4 = (ROOT / "variants/heltec_v4/platformio.ini").read_text(encoding="utf-8")
    paper = (ROOT / "variants/heltec_wireless_paper/platformio.ini").read_text(encoding="utf-8")
    for config, name in (
        (v4, "env:heltec_v4_3_companion_radio_ble_femon_smartui"),
        (paper, "Heltec_Wireless_Paper_companion_smartui_common"),
    ):
        body = section(config, name)
        assert "custom_smartui_fresh_spiffs = yes" in body
        assert "platformio/tool-mkspiffs @ 2.230.0" in body
        assert "UI_SAFE_STORAGE_RECOVERY=1" in body
        passed += 1
        print(f"[PASS] {name}: prepared-storage and safe-recovery gates enabled")

    assert (VERSION, TAG) == ("0.05", "smartui-0.05")
    for pair in EXPECTED:
        fresh = firmware_metadata(f"{pair.stem}-merged.bin", "0" * 40)["storage"]
        update = firmware_metadata(f"{pair.stem}-update.bin", "0" * 40)["storage"]
        assert fresh["contains_formatted_empty_spiffs"] is True
        assert fresh["prepared_clean_install_storage"] is True
        assert fresh["preserves_existing_filesystem"] is False
        assert update["contains_formatted_empty_spiffs"] is False
        assert update["preserves_existing_filesystem"] is True
        assert fresh["safe_factory_empty_native_recovery"] is True
        assert update["safe_factory_empty_native_recovery"] is True
        assert fresh["factory_spiffs_layout"] == update["factory_spiffs_layout"]
        assert fresh["factory_spiffs_sha256"] == FACTORY_SPIFFS_SHA256[pair.stem]
    passed += 1
    print("[PASS] 0.05 manifest marks merged clean-only and update state-preserving")

    print(f"Fresh-install storage regression: {passed} passed.")
    print("Real pinned mkspiffs host mount; synthetic ESP containers, not hardware boot tests.")


if __name__ == "__main__":
    main()
