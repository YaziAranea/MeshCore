#!/usr/bin/env python3
"""Package already-built SmartUI files; validate before producing checksums/ZIP.

Does not build, flash, upload, or overwrite an existing output directory.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

import validate_release_esp32 as esp32
import validate_release_uf2 as uf2


ROOT = Path(__file__).resolve().parents[1]
NRF_ENVS = (
    "Heltec_t096_companion_radio_ble_femon",
    "Heltec_t114_companion_radio_ble",
    "ProMicro_ra62_companion_radio_ble",
)
ESP_ENVS = (
    "heltec_v4_3_companion_radio_ble_femon_smartui",
    "Heltec_Wireless_Paper_companion_radio_ble_smartui_wood",
    "Heltec_Wireless_Paper_companion_radio_ble_smartui_full",
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new, empty release directory")
    parser.add_argument("--build-dir", type=Path, default=ROOT / ".pio/build")
    args = parser.parse_args()
    files = []
    for env, name in zip(NRF_ENVS, uf2.EXPECTED):
        files.append((args.build_dir / env / "firmware.uf2", name))
    for env, pair in zip(ESP_ENVS, esp32.EXPECTED):
        files.extend((
            (args.build_dir / env / "firmware-merged.bin", pair.stem + "-freshInstall-merged.bin"),
            (args.build_dir / env / "firmware.bin", pair.stem + "-update.bin"),
        ))
    for source, _ in files:
        if not source.is_file():
            parser.error(f"build artifact missing: {source}")
    output = args.output.resolve()
    if output.exists():
        parser.error(f"refusing to overwrite existing release directory: {output}")
    output.mkdir(parents=True)
    for source, name in files:
        shutil.copy2(source, output / name)
    for name, marker in uf2.EXPECTED.items():
        uf2.validate(output / name, marker)
    for pair in esp32.EXPECTED:
        esp32.validate_pair(output, pair)

    for suffix, manifest in ((".uf2", "SHA256SUMS.txt"), (".bin", "SHA256SUMS-ESP32.txt")):
        rows = [f"{digest(path)}  {path.name}" for path in sorted(output.glob("*" + suffix))]
        (output / manifest).write_text("\n".join(rows) + "\n", encoding="ascii", newline="\n")

    first_name = next(iter(uf2.EXPECTED))
    version = first_name.split("_SmartUI_", 1)[1].removesuffix(".uf2")
    notes_source = ROOT / f"RELEASE_NOTES_v{version}_RU.md"
    if notes_source.is_file():
        shutil.copy2(notes_source, output / notes_source.name)

    manifest_payloads = sorted(output.iterdir())
    manifest = {
        "version": version,
        "files": [
            {"name": path.name, "bytes": path.stat().st_size, "sha256": digest(path)}
            for path in manifest_payloads
        ],
    }
    manifest_path = output / "RELEASE-MANIFEST.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    names = sorted(path.name for path in output.iterdir())
    archive = output / f"MeshCore_SmartUI_{version}_all-five-boards.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name in names:
            z.write(output / name, name)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert sorted(z.namelist()) == names
        for name in names:
            assert hashlib.sha256(z.read(name)).hexdigest() == digest(output / name)
    print(json.dumps({
        "directory": str(output),
        "assets": [{"name": p.name, "bytes": p.stat().st_size, "sha256": digest(p)}
                   for p in sorted(output.iterdir())],
    }, indent=2))


if __name__ == "__main__":
    main()
