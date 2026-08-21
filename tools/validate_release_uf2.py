#!/usr/bin/env python3
"""Validate the three UF2 artifacts published with SmartUI v2.0.0-rc1."""

from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


MAGIC_START0 = 0x0A324655
MAGIC_START1 = 0x9E5D5157
MAGIC_END = 0x0AB16F30
NRF52840_FAMILY = 0xADA52840
APP_START = 0x26000

EXPECTED = {
    "T096_FEM_SmartUI_v2.0.0-rc1.uf2": b"T096 SmartUI 2.0.0-rc1",
    "T114_SmartUI_v2.0.0-rc1.uf2": b"T114 SmartUI 2.0.0-rc1",
    "ProMicro_RA62_SmartUI_v2.0.0-rc1.uf2": b"ProMicro SmartUI 2.0.0-rc1",
}


def validate(path: Path, marker: bytes) -> tuple[str, int, int]:
    raw = path.read_bytes()
    if not raw or len(raw) % 512:
        raise ValueError("size is not a non-zero multiple of 512 bytes")

    blocks = len(raw) // 512
    payloads: dict[int, bytes] = {}
    declared_count: int | None = None

    for index in range(blocks):
        block = raw[index * 512:(index + 1) * 512]
        header = struct.unpack_from("<8I", block)
        magic0, magic1, flags, address, size, number, count, family = header
        end_magic = struct.unpack_from("<I", block, 508)[0]

        if (magic0, magic1, end_magic) != (MAGIC_START0, MAGIC_START1, MAGIC_END):
            raise ValueError(f"block {index}: invalid UF2 magic")
        if number != index:
            raise ValueError(f"block {index}: declares block number {number}")
        if declared_count is None:
            declared_count = count
        if count != declared_count or count != blocks:
            raise ValueError(f"block {index}: inconsistent block count {count}")
        if size <= 0 or size > 476:
            raise ValueError(f"block {index}: invalid payload size {size}")
        if not flags & 0x2000 or family != NRF52840_FAMILY:
            raise ValueError(f"block {index}: wrong or missing nRF52840 family ID")
        if address in payloads:
            raise ValueError(f"block {index}: duplicate target address 0x{address:08X}")
        payloads[address] = block[32:32 + size]

    first_address = min(payloads)
    if first_address != APP_START:
        raise ValueError(f"application starts at 0x{first_address:08X}, expected 0x{APP_START:08X}")

    last_address = max(address + len(payload) for address, payload in payloads.items())
    image = bytearray(b"\xFF" * (last_address - first_address))
    for address, payload in payloads.items():
        offset = address - first_address
        image[offset:offset + len(payload)] = payload
    if marker not in image:
        raise ValueError(f"version marker {marker.decode()!r} was not found")

    return hashlib.sha256(raw).hexdigest().upper(), len(raw), blocks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "firmware_dir",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "firmware",
        help="directory containing the three release UF2 files",
    )
    args = parser.parse_args()

    failures = 0
    for filename, marker in EXPECTED.items():
        path = args.firmware_dir / filename
        try:
            digest, size, blocks = validate(path, marker)
            print(f"[PASS] {filename}: {size} bytes, {blocks} blocks, SHA256 {digest}")
        except (OSError, ValueError) as error:
            failures += 1
            print(f"[FAIL] {filename}: {error}")

    print(f"UF2 validation: {len(EXPECTED) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
