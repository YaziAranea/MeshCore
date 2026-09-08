#!/usr/bin/env python3
"""Validate V3 FS2: exact application pair and mountable, pristine empty SPIFFS.

Requires PlatformIO's pinned tool-mkspiffs 2.230.0 and the installed ESP32-S3
Arduino SDK configuration. No downloads, formatting of devices or hardware
access. mkspiffs -l executes its real SPIFFS_mount; it does not auto-format.
"""

import argparse
import hashlib
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile

from validate_release_esp32 import ImagePair, validate_pair


PAIR = ImagePair(
    "Heltec_V3_OLED_SmartUI_2.1.0-experimental.1",
    b"V3 OLED SmartUI 2.1.0-experimental.1 FS2",
)

PARTITION_OFFSET = 0x8000
PARTITION_SECTOR = 0x1000
BLOCK_SIZE = 4096
PAGE_SIZE = 256
FORMAT_CONFIG = {
    "SPIFFS_OBJ_NAME_LEN": 32, "SPIFFS_OBJ_META_LEN": 4,
    "SPIFFS_USE_MAGIC": 1, "SPIFFS_USE_MAGIC_LENGTH": 1,
    "SPIFFS_ALIGNED_OBJECT_INDEX_TABLES": 0,
}


def factory_spiffs_sha256() -> str:
    header = Path(__file__).resolve().parents[1] / "examples/companion_radio/ui-new/V3StorageRecovery.h"
    source = header.read_text(encoding="utf-8")
    match = re.search(r'kV3FactorySpiffsSha256Hex\[\]\s*=\s*"([0-9a-f]{64})"\s*;', source)
    if not match:
        raise ValueError("missing exact factory SPIFFS SHA256 in V3StorageRecovery.h")
    return match[1]


def validate_exact_application(image: bytes) -> None:
    """Check actual ESP segment/checksum/hash extent, rejecting appended FS/padding."""
    pos, checksum = 24, 0xEF
    for _ in range(image[1]):
        if pos + 8 > len(image):
            raise ValueError("truncated ESP application segment header")
        _, size = struct.unpack_from("<II", image, pos)
        pos += 8
        if pos + size > len(image):
            raise ValueError("truncated ESP application segment")
        for value in image[pos:pos + size]:
            checksum ^= value
        pos += size
    end = (pos + 16) & ~15
    if end > len(image) or image[end - 1] != checksum:
        raise ValueError("ESP application checksum mismatch")
    if image[pos:end - 1] != b"\0" * (end - pos - 1):
        raise ValueError("unexpected ESP application alignment padding")
    if image[23] not in (0, 1):
        raise ValueError("unsupported ESP application hash flag")
    expected_end = end + (32 if image[23] else 0)
    if len(image) != expected_end:
        raise ValueError("update has trailing bytes outside the ESP application (FS/padding is forbidden)")
    if image[23] and hashlib.sha256(image[:end]).digest() != image[end:]:
        raise ValueError("ESP application appended SHA256 mismatch")


def parse_partitions(merged: bytes) -> list[dict]:
    """Parse the actual ESP-IDF partition table, including its mandatory MD5."""
    table = merged[PARTITION_OFFSET:PARTITION_OFFSET + PARTITION_SECTOR]
    if len(table) != PARTITION_SECTOR:
        raise ValueError("merged does not contain a complete partition-table sector")
    entries = []
    digest_seen = False
    for pos in range(0, 0xC00, 32):
        row = table[pos:pos + 32]
        if row[:2] == b"\xeb\xeb":
            if row[2:16] != b"\xff" * 14 or row[16:] != hashlib.md5(table[:pos]).digest():
                raise ValueError("partition-table MD5 mismatch")
            if table[pos + 32:] != b"\xff" * (len(table) - pos - 32):
                raise ValueError("unexpected data after partition-table MD5")
            digest_seen = True
            break
        if row[:2] != b"\xaa\x50":
            raise ValueError("partition table is malformed or missing its MD5")
        _, kind, subtype, offset, size, raw_name, flags = struct.unpack("<HBBII16sI", row)
        if not size or offset < PARTITION_OFFSET + PARTITION_SECTOR:
            raise ValueError("invalid partition offset/size")
        if offset % BLOCK_SIZE or size % BLOCK_SIZE:
            raise ValueError("partition is not flash-sector aligned")
        if kind == 0 and offset % 0x10000:
            raise ValueError("application partition is not 64-KiB aligned")
        entries.append(dict(type=kind, subtype=subtype, offset=offset, size=size,
                            name=raw_name.split(b"\0", 1)[0].decode("ascii"), flags=flags))
    if not digest_seen or not entries:
        raise ValueError("partition table has no entries or MD5")
    flash_code = merged[3] >> 4
    if flash_code > 7:
        raise ValueError("unsupported ESP image flash-size field")
    flash_size = (1 << 20) << flash_code
    ordered = sorted(entries, key=lambda entry: entry["offset"])
    end = PARTITION_OFFSET + PARTITION_SECTOR
    for entry in ordered:
        if entry["offset"] < end:
            raise ValueError("overlapping partitions")
        end = entry["offset"] + entry["size"]
        if end > flash_size:
            raise ValueError("partition exceeds declared flash capacity")
    return entries


def pio_packages() -> Path:
    return Path(os.environ.get("PLATFORMIO_PACKAGES_DIR",
                str(Path(os.environ.get("PLATFORMIO_CORE_DIR", str(Path.home() / ".platformio"))) / "packages")))


def find_mkspiffs(explicit: Path | None = None) -> Path:
    if explicit:
        return Path(explicit).resolve(strict=True)
    if os.environ.get("SMARTUI_MKSPIFFS"):
        return Path(os.environ["SMARTUI_MKSPIFFS"]).resolve(strict=True)
    folder = pio_packages() / "tool-mkspiffs"
    for name in ("mkspiffs_espressif32_arduino", "mkspiffs_espressif32_arduino.exe"):
        if (folder / name).is_file():
            return folder / name
    raise ValueError("missing PlatformIO tool-mkspiffs 2.230.0; set SMARTUI_MKSPIFFS or --mkspiffs")


def run_tool(tool: Path, *args: str) -> str:
    result = subprocess.run([str(tool), *map(str, args)], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=30)
    if result.returncode:
        raise ValueError(f"mkspiffs failed ({result.returncode}): {(result.stdout + result.stderr).strip()}")
    if result.stderr.strip():
        raise ValueError(f"mkspiffs reported an error: {result.stderr.strip()}")
    return result.stdout


def check_host_configuration(tool: Path, sdkconfig: Path | None = None) -> dict:
    version = run_tool(tool, "--version")
    for key, value in FORMAT_CONFIG.items():
        if not re.search(rf"^\s*{key}:\s*{value}\s*$", version, re.M):
            raise ValueError(f"mkspiffs on-disk configuration mismatch: {key}={value}")
    if "mkspiffs ver. 0.2.3" not in version or "SPIFFS ver. 0.3.7-5-gf5e26c4" not in version:
        raise ValueError("unexpected mkspiffs/SPIFFS version; review before changing the FS2 contract")
    if sdkconfig is None and os.environ.get("SMARTUI_SPIFFS_SDKCONFIG"):
        sdkconfig = Path(os.environ["SMARTUI_SPIFFS_SDKCONFIG"])
    configs = [Path(sdkconfig)] if sdkconfig else sorted(pio_packages().glob(
        "framework-arduinoespressif32*/tools/sdk/esp32s3/*/include/sdkconfig.h"))
    if not configs:
        raise ValueError("missing ESP32-S3 SDK configuration; set SMARTUI_SPIFFS_SDKCONFIG or --sdkconfig")
    expected = {"CONFIG_SPIFFS_PAGE_SIZE": PAGE_SIZE, "CONFIG_SPIFFS_OBJ_NAME_LEN": 32,
                "CONFIG_SPIFFS_META_LENGTH": 4, "CONFIG_SPIFFS_USE_MAGIC": 1,
                "CONFIG_SPIFFS_USE_MAGIC_LENGTH": 1}
    # All installed candidate S3 memory variants must agree; never silently
    # pick whichever SDK happens to match when another candidate conflicts.
    for config in configs:
        text = config.read_text(encoding="utf-8")
        for key, value in expected.items():
            if not re.search(rf"^#define\s+{key}\s+{value}\s*$", text, re.M):
                raise ValueError(f"{config}: incompatible {key}")
        header = config.parents[2] / "include/spiffs/include/spiffs_config.h"
        source = header.read_text(encoding="utf-8")
        if not re.search(r"^#define\s+SPIFFS_ALIGNED_OBJECT_INDEX_TABLES\s+0\s*$", source, re.M):
            raise ValueError(f"{header}: incompatible SPIFFS alignment")
    return {"tool": str(tool), "tool_version": version.strip(),
            "sdk_configs_checked": [str(config) for config in configs]}


def inspect_fresh_spiffs(merged: bytes, *, mkspiffs: Path | None = None,
                         sdkconfig: Path | None = None) -> dict:
    partitions = parse_partitions(merged)
    matches = [entry for entry in partitions if (entry["type"], entry["subtype"]) == (1, 0x82)]
    if len(matches) != 1:
        raise ValueError("expected exactly one data/SPIFFS partition")
    part = matches[0]
    if part["flags"] != 0 or part["size"] < 3 * BLOCK_SIZE:
        raise ValueError("SPIFFS must be unencrypted and contain at least three logical blocks")
    image = merged[part["offset"]:part["offset"] + part["size"]]
    if len(image) != part["size"]:
        raise ValueError("freshInstall merged is missing the complete SPIFFS partition")
    if image == b"\xff" * len(image):
        raise ValueError("SPIFFS partition is erased, not formatted")
    tool = find_mkspiffs(mkspiffs)
    configuration = check_host_configuration(tool, sdkconfig)
    with tempfile.TemporaryDirectory(prefix="smartui-v3-fs1-check-") as folder:
        temp = Path(folder)
        snapshot = temp / "merged-spiffs.bin"
        snapshot.write_bytes(image)
        args = ("-p", PAGE_SIZE, "-b", BLOCK_SIZE, "-s", part["size"])
        listing = run_tool(tool, "-l", *args, snapshot)
        if listing.strip():
            raise ValueError("freshInstall SPIFFS contains files; refusing embedded user data")
        if snapshot.read_bytes() != image:
            raise ValueError("host mount unexpectedly modified the supplied image")
        empty = temp / "empty"
        empty.mkdir()
        canonical = temp / "canonical-empty.bin"
        run_tool(tool, "-c", empty, *args, canonical)
        if canonical.read_bytes() != image:
            raise ValueError("SPIFFS is not a pristine canonical empty image (stale data or geometry mismatch)")
    if part["offset"] != 0x670000 or part["size"] != 0x180000:
        raise ValueError("SPIFFS layout does not match the narrowly scoped V3 recovery guard")
    if hashlib.sha256(image).hexdigest() != factory_spiffs_sha256():
        raise ValueError("factory SPIFFS SHA256 differs from V3StorageRecovery.h")
    return {**part, "page_size": PAGE_SIZE, "block_size": BLOCK_SIZE,
            "sha256": hashlib.sha256(image).hexdigest().upper(), "empty": True,
            "host_mount": "SPIFFS_mount via pinned mkspiffs -l; no auto-format",
            "configuration": configuration,
            "proof_limits": "Host on-disk compatibility and empty-image proof, not ESP32 execution or physical flash testing."}


def validate_v3_pair(directory: Path, *, mkspiffs: Path | None = None,
                     sdkconfig: Path | None = None) -> tuple[int, int, str, str]:
    result = validate_pair(directory, PAIR)
    update = (directory / f"{PAIR.stem}-update.bin").read_bytes()
    validate_exact_application(update)
    if factory_spiffs_sha256().encode("ascii") not in update:
        raise ValueError("update does not contain the exact factory-empty recovery hash")
    merged = (directory / f"{PAIR.stem}-freshInstall-merged.bin").read_bytes()
    apps = [entry for entry in parse_partitions(merged) if entry["type"] == 0 and entry["offset"] == 0x10000]
    if len(apps) != 1 or result[1] > apps[0]["size"]:
        raise ValueError("update image does not fit the actual app partition at 0x10000")
    inspect_fresh_spiffs(merged, mkspiffs=mkspiffs, sdkconfig=sdkconfig)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware_dir", type=Path)
    parser.add_argument("--mkspiffs", type=Path, help="installed PlatformIO ESP32 Arduino mkspiffs binary")
    parser.add_argument("--sdkconfig", type=Path, help="actual ESP32-S3 Arduino SDK sdkconfig.h")
    args = parser.parse_args()
    try:
        merged_size, update_size, merged_hash, update_hash = validate_v3_pair(
            args.firmware_dir, mkspiffs=args.mkspiffs, sdkconfig=args.sdkconfig)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"[FAIL] {PAIR.stem}: {exc}\n")
    print(f"[PASS] {PAIR.stem}: merged {merged_size} bytes SHA256 {merged_hash}; "
          f"update {update_size} bytes SHA256 {update_hash}; FS2 empty SPIFFS host mount verified")


if __name__ == "__main__":
    main()
