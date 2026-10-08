#!/usr/bin/env python3
"""Package the explicit, offline-readable developer source kit; never flash/upload."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.16"
ZIP_NAME = f"SmartUI_Developer_Kit_{VERSION}.zip"
DEVELOPMENT_ZIP_NAME = f"SmartUI_Developer_Kit_{VERSION}-development.zip"
SOURCES = (
    "LICENSE",
    "docs/SMARTUI_CLI_RU.md",
    "docs/CONSOLE_COMMANDS_RU.md",
    "tools/smartui-cli/README.md",
    "tools/smartui-cli/inspect_device.py",
    "tools/smartui-cli/smartui_cli.py",
    "tools/smartui-cli/transports.py",
    "tools/smartui-cli/tests/test_smartui_cli.py",
    "tools/usb-helper/api.js",
    "tools/usb-helper/core.js",
    "tools/usb-helper/test_api.js",
    "tools/usb-helper/test_api_fixture.js",
    "tools/usb-helper/presets.js",
    "tools/usb-helper/test_presets.js",
    "tools/usb-helper/PRESETS_SOURCE_RU.md",
    "tools/update_meshcoretel_presets.js",
)
MANIFEST_NAME = "DEVELOPER-KIT-MANIFEST.json"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def package(output, commit, *, root=ROOT, development=False):
    """Package only explicit sources, preserving repo-relative offline links.

    The default retains the release contract: commit identifies exact sources,
    whose checkout/build validation belongs to the release caller. Development
    mode instead labels it only as a base commit; hashes identify the actual
    working-tree snapshot, which can contain uncommitted/untracked source files.
    Neither mode uploads, commits, flashes, or rewrites a published artifact.
    """
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        label = "base commit" if development else "exact-source commit"
        raise ValueError(f"Developer kit requires the full {label}")
    output, root = Path(output), Path(root)
    path = output / (DEVELOPMENT_ZIP_NAME if development else ZIP_NAME)
    if path.exists():
        raise ValueError("Refusing to overwrite an existing developer kit")
    payloads = {}
    for name in SOURCES:
        source = root / name
        if not source.is_file() or source.is_symlink() or not source.stat().st_size:
            raise ValueError(f"Developer kit source must be a regular nonempty file: {name}")
        payloads[name] = source.read_bytes()
    title = (f"# SmartUI Developer Kit — LOCAL DEVELOPMENT (base {VERSION})\n\n"
             if development else f"# SmartUI {VERSION} — Developer Kit\n\n")
    notice = (
        "Локальный development-снимок SDK и документации поверх базы " + VERSION + ". "
        "Это не опубликованный Developer Kit " + VERSION + " и не exact-source содержимое base commit. "
        "Изменённые и новые allowlisted-файлы включены в их текущем виде; "
        "фактические байты определяются manifest и SHA256SUMS.txt.\n\n"
        "Local development snapshot, not a published release. The manifest base commit "
        "is provenance only, NOT the exact commit of these working-tree files. "
        "Packaging does not change the firmware version. No hardware verification is claimed.\n\n"
        if development else ""
    )
    helper = "USB Helper 2.0"
    payloads["README.md"] = (
        title + notice +
        "[Локальный CLI: инструкция](docs/SMARTUI_CLI_RU.md) · "
        "[Справочник команд](docs/CONSOLE_COMMANDS_RU.md) · "
        "[Python и JavaScript SDK](tools/smartui-cli/README.md)\n\n"
        "Это исходники SDK, документация и тесты, не прошивка устройства. "
        f"Для обычной настройки используйте {helper}. "
        "Проверяйте smartui_cli:1 и ui hello. CMD66/RESP29; старый API201 и sync/events не поддерживаются.\n\n"
        "The source kit does not install dependencies or connect to a device automatically. "
        "Read the transport/security limits before connecting. "
        "Tests use simulated transports, not physical-device acceptance.\n\n"
        "Run from this extracted directory:\n\n"
        "```sh\npython -B -m unittest discover -s tools/smartui-cli/tests -v\n```\n"
    ).encode("utf-8")
    if development:
        manifest = {
            "schema_version": 2, "stage": "development", "distribution": "local",
            "cli_version": 1, "base_firmware_version": VERSION, "base_source_commit": commit,
            "source_snapshot": "working-tree", "exact_source_commit": False,
        }
    else:
        manifest = {
            "schema_version": 1, "firmware_version": VERSION, "cli_version": 1,
            "source_commit": commit, "distribution": "public", "stage": "release",
        }
    manifest.update(transport="companion-cli", command=66, response=29,
                    companion_protocol_version=14, local_only=True, sync=False, events=False)
    manifest["files"] = [{"name": name, "bytes": len(raw), "sha256": digest(raw)}
                         for name, raw in sorted(payloads.items())]
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="output folder; existing kit files are never overwritten")
    parser.add_argument("--development", action="store_true", help="package a distinctly named local working-tree snapshot")
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument("--commit", help="full exact-source commit, release mode only")
    identity.add_argument("--base-commit", help="full provenance base commit, development mode only")
    args = parser.parse_args(argv)
    if args.development and args.base_commit is None:
        parser.error("--development requires --base-commit, not --commit")
    if not args.development and args.commit is None:
        parser.error("--base-commit requires --development")
    try:
        path = package(args.output, args.base_commit if args.development else args.commit,
                       development=args.development)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"{path.name}: {path.stat().st_size} bytes; SHA256 {digest(path.read_bytes())}")
    return path


if __name__ == "__main__":
    main()
