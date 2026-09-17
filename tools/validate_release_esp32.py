#!/usr/bin/env python3
"""Validate paired ESP32-S3 fresh-install and update images.

The merged image is flashed at 0x00000.  The update image is the application
payload flashed at 0x10000.  This deliberately does not treat BIN files as UF2.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path


ESP_IMAGE_MAGIC = 0xE9
APP_OFFSET = 0x10000


@dataclass(frozen=True)
class ImagePair:
    stem: str
    marker: bytes


EXPECTED = (
    ImagePair(
        "Heltec_V4.3_OLED_FEMON_SmartUI_2.1.0-experimental.2",
        b"V4.3 OLED SmartUI 2.1.0-experimental.2",
    ),
    ImagePair(
        "Heltec_Wireless_Paper_FULL_SmartUI_2.1.0-experimental.2",
        b"Wireless Paper SmartUI 2.1.0-experimental.2 FULL",
    ),
)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def validate_esp_image(raw: bytes, label: str) -> None:
    if len(raw) < 24:
        raise ValueError(f"{label}: image is too short")
    if raw[0] != ESP_IMAGE_MAGIC:
        raise ValueError(f"{label}: ESP image magic is 0x{raw[0]:02X}, expected 0xE9")
    segment_count = raw[1]
    if segment_count < 1 or segment_count > 16:
        raise ValueError(f"{label}: implausible segment count {segment_count}")


def validate_exact_application(image: bytes) -> None:
    """Check every ESP segment, checksum and appended hash; forbid FS/padding."""
    validate_esp_image(image, "application")
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


def validate_pair(directory: Path, pair: ImagePair) -> tuple[int, int, str, str]:
    merged_path = directory / f"{pair.stem}-freshInstall-merged.bin"
    update_path = directory / f"{pair.stem}-update.bin"
    merged = merged_path.read_bytes()
    update = update_path.read_bytes()

    validate_esp_image(merged, merged_path.name)
    validate_esp_image(update, update_path.name)
    if len(merged) < APP_OFFSET + len(update):
        raise ValueError(
            f"{merged_path.name}: {len(merged)} bytes cannot contain the "
            f"{len(update)}-byte app at 0x{APP_OFFSET:X}"
        )
    if merged[APP_OFFSET:APP_OFFSET + len(update)] != update:
        raise ValueError("merged application slice differs from the update image")
    validate_exact_application(update)
    if pair.marker not in update:
        raise ValueError(f"version marker {pair.marker.decode()!r} was not found")

    return len(merged), len(update), sha256(merged), sha256(update)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "firmware_dir",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "firmware",
        help="directory containing the two ESP32-S3 BIN pairs",
    )
    args = parser.parse_args()

    failures = 0
    for pair in EXPECTED:
        try:
            merged_size, update_size, merged_hash, update_hash = validate_pair(
                args.firmware_dir, pair
            )
            print(
                f"[PASS] {pair.stem}: merged {merged_size} bytes "
                f"SHA256 {merged_hash}; update {update_size} bytes SHA256 {update_hash}"
            )
        except (OSError, ValueError) as error:
            failures += 1
            print(f"[FAIL] {pair.stem}: {error}")

    print(f"ESP32 BIN validation: {len(EXPECTED) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
