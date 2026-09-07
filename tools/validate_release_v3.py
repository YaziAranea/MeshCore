#!/usr/bin/env python3
"""Validate the Heltec V3 OLED add-on without requiring other board images."""

import argparse
from pathlib import Path

from validate_release_esp32 import ImagePair, validate_pair


PAIR = ImagePair(
    "Heltec_V3_OLED_SmartUI_2.1.0-experimental.1",
    b"V3 OLED SmartUI 2.1.0-experimental.1",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware_dir", type=Path)
    args = parser.parse_args()
    try:
        merged_size, update_size, merged_hash, update_hash = validate_pair(args.firmware_dir, PAIR)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"[FAIL] {PAIR.stem}: {exc}\n")
    print(f"[PASS] {PAIR.stem}: merged {merged_size} bytes SHA256 {merged_hash}; "
          f"update {update_size} bytes SHA256 {update_hash}")


if __name__ == "__main__":
    main()
