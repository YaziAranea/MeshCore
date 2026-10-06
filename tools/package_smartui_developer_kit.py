#!/usr/bin/env python3
"""Package the explicit, offline-readable developer source kit; never flash/upload."""
from pathlib import Path
import hashlib
import json
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.10"
ZIP_NAME = f"SmartUI_Developer_Kit_{VERSION}.zip"
SOURCES = (
    "LICENSE",
    "docs/SMARTUI_API_EN.md",
    "docs/SMARTUI_API_RU.md",
    "tools/smartui-api/README.md",
    "tools/smartui-api/inspect_device.py",
    "tools/smartui-api/smartui_api.py",
    "tools/smartui-api/transports.py",
    "tools/smartui-api/tests/test_smartui_api.py",
)
MANIFEST_NAME = "DEVELOPER-KIT-MANIFEST.json"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def package(output, commit, *, root=ROOT):
    """Preserve repo-relative links, with no recursive/glob inclusion of local files."""
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Developer kit requires the full exact-source commit")
    output, root = Path(output), Path(root)
    path = output / ZIP_NAME
    if path.exists():
        raise ValueError("Refusing to overwrite an existing developer kit")
    payloads = {}
    for name in SOURCES:
        source = root / name
        if not source.is_file() or source.is_symlink() or not source.stat().st_size:
            raise ValueError(f"Developer kit source must be a regular nonempty file: {name}")
        payloads[name] = source.read_bytes()
    payloads["README.md"] = (
        f"# SmartUI {VERSION} — Developer Kit\n\n"
        "[Русская инструкция](docs/SMARTUI_API_RU.md) · "
        "[English protocol guide](docs/SMARTUI_API_EN.md) · "
        "[Python SDK](tools/smartui-api/README.md)\n\n"
        "Это исходники SDK, документация и тесты, не прошивка устройства. "
        "Для обычной настройки используйте USB Helper 1.3. "
        "Поддержку API проверяйте через discovery, не только по номеру прошивки.\n\n"
        "The source kit does not install dependencies or connect to a device automatically. "
        "Read the transport/security limits before connecting. "
        "Tests use simulated transports, not physical-device acceptance.\n\n"
        "Run from this extracted directory:\n\n"
        "```sh\npython -B -m unittest discover -s tools/smartui-api/tests -v\n```\n"
    ).encode("utf-8")
    manifest = {
        "schema_version": 1, "firmware_version": VERSION, "api_version": 1,
        "source_commit": commit, "distribution": "public",
        "files": [{"name": name, "bytes": len(raw), "sha256": digest(raw)}
                  for name, raw in sorted(payloads.items())],
    }
    payloads[MANIFEST_NAME] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    payloads["SHA256SUMS.txt"] = "".join(
        f"{digest(raw)}  {name}\n" for name, raw in sorted(payloads.items())
    ).encode("ascii")
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, raw in sorted(payloads.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, raw, compresslevel=9)
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != set(payloads) or archive.testzip() is not None:
            raise ValueError("Developer kit archive entries/CRC differ from expected sources")
        for name, raw in payloads.items():
            if archive.read(name) != raw:
                raise ValueError(f"Developer kit source mismatch: {name}")
    return path
