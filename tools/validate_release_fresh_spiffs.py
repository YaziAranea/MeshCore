#!/usr/bin/env python3
"""Validate prepared clean-install SPIFFS for V4.3 and Wireless Paper.

The merged image must contain one exact-layout, canonical, formatted, empty
SPIFFS image. The update image remains the exact application only and therefore
preserves existing storage when flashed at 0x10000.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from validate_release_esp32 import EXPECTED, ImagePair, validate_pair
from validate_release_v3 import inspect_prepared_spiffs, parse_partitions


LAYOUTS = {
    "Heltec_V4.3_UI_0.05": (0xC90000, 0x360000),
    "Paper_UI_0.05": (0x670000, 0x180000),
}
FACTORY_SPIFFS_SHA256 = {
    "Heltec_V4.3_UI_0.05": "ec202a958aea323b1e5f8388ab92814695b85d5ac9c77227fdf47ed850fff7fe",
    "Paper_UI_0.05": "debe417f42a5bdda6c6e81539f9a3519b4653ab70cefeba01885ecc4b2d3cf5b",
}


def validate_prepared_pair(directory: Path, pair: ImagePair, *,
                           mkspiffs: Path | None = None,
                           sdkconfig: Path | None = None) -> tuple[int, int, str, str, dict]:
    if pair.stem not in LAYOUTS:
        raise ValueError(f"no approved SPIFFS layout for {pair.stem}")
    result = validate_pair(directory, pair)
    merged = (directory / f"{pair.stem}-merged.bin").read_bytes()
    update = (directory / f"{pair.stem}-update.bin").read_bytes()
    apps = [entry for entry in parse_partitions(merged)
            if entry["type"] == 0 and entry["offset"] == 0x10000]
    if len(apps) != 1 or len(update) > apps[0]["size"]:
        raise ValueError("update image does not fit the actual app partition at 0x10000")
    storage = inspect_prepared_spiffs(
        merged, LAYOUTS[pair.stem], mkspiffs=mkspiffs, sdkconfig=sdkconfig,
        expected_sha256=FACTORY_SPIFFS_SHA256[pair.stem])
    expected_hash = FACTORY_SPIFFS_SHA256[pair.stem].encode("ascii")
    if expected_hash not in update:
        raise ValueError(
            "update does not contain its exact factory-empty SPIFFS hash; "
            "safe native recovery is not bound to this release image"
        )
    return (*result, storage)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware_dir", type=Path)
    parser.add_argument("--mkspiffs", type=Path)
    parser.add_argument("--sdkconfig", type=Path)
    args = parser.parse_args()
    failures = 0
    for pair in EXPECTED:
        try:
            merged_size, update_size, merged_hash, update_hash, storage = validate_prepared_pair(
                args.firmware_dir, pair, mkspiffs=args.mkspiffs, sdkconfig=args.sdkconfig)
            print(
                f"[PASS] {pair.stem}: merged {merged_size} bytes SHA256 {merged_hash}; "
                f"update {update_size} bytes SHA256 {update_hash}; canonical empty SPIFFS "
                f"0x{storage['offset']:X}+0x{storage['size']:X}"
            )
        except (OSError, ValueError) as error:
            failures += 1
            print(f"[FAIL] {pair.stem}: {error}")
    print(f"Prepared SPIFFS validation: {len(EXPECTED) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
