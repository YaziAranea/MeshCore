#!/usr/bin/env python3
"""Package the V3 addition without replacing the immutable five-board release.

Reads existing artifacts only. Does not build, flash, upload, change a Git tag,
or overwrite an output directory. Run from the checkout used to build V3.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

from validate_release_v3 import PAIR, validate_v3_pair


ROOT = Path(__file__).resolve().parents[1]
VERSION = "2.1.0-experimental.1"
V3_REVISION = "FS2"
TAG = "v" + VERSION
BASE_COMMIT = "00df4872c0ccad5530f5450132e743e1fb4f3d57"
BASE_ZIP = f"MeshCore_SmartUI_{VERSION}_all-five-boards.zip"
COMBINED_ZIP = f"MeshCore_SmartUI_{VERSION}_all-six-boards.zip"
NOTES = f"RELEASE_NOTES_{TAG}_RU.md"
ADDENDUM = f"V3_ADDENDUM_{TAG}_RU.md"
V3_MANIFEST = "RELEASE-MANIFEST-V3.json"
V3_SUMS = "SHA256SUMS-V3.txt"
ALL_MANIFEST = "RELEASE-MANIFEST-ALL-SIX.json"
ALL_SUMS = "SHA256SUMS-ALL-SIX.txt"
BASE_FIRMWARE = {
    f"T096_FEM_SmartUI_{VERSION}.uf2": "T096 FEM ON",
    f"T114_SmartUI_{VERSION}.uf2": "T114",
    f"ProMicro_RA62_SmartUI_{VERSION}.uf2": "ProMicro RA62",
    f"Heltec_V4.3_OLED_FEMON_SmartUI_{VERSION}-freshInstall-merged.bin": "Heltec V4.3 OLED FEM ON",
    f"Heltec_V4.3_OLED_FEMON_SmartUI_{VERSION}-update.bin": "Heltec V4.3 OLED FEM ON",
    f"Heltec_Wireless_Paper_FULL_SmartUI_{VERSION}-freshInstall-merged.bin": "Wireless Paper FULL",
    f"Heltec_Wireless_Paper_FULL_SmartUI_{VERSION}-update.bin": "Wireless Paper FULL",
}
BASE_PAYLOADS = set(BASE_FIRMWARE) | {NOTES, "SHA256SUMS.txt", "SHA256SUMS-ESP32.txt"}
BASE_ASSETS = BASE_PAYLOADS | {"RELEASE-MANIFEST.json", BASE_ZIP}
V3_FILES = (PAIR.stem + "-freshInstall-merged.bin", PAIR.stem + "-update.bin")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def record(name: str, raw: bytes, **metadata) -> dict:
    return {"name": name, "bytes": len(raw), "sha256": sha256(raw), **metadata}


def records(files: dict[str, bytes]) -> list[dict]:
    return [record(name, raw) for name, raw in sorted(files.items())]


def checksum_bytes(files: dict[str, bytes]) -> bytes:
    return "".join(f"{sha256(raw)}  {name}\n" for name, raw in sorted(files.items())).encode("utf-8")


def verify_checksums(raw: bytes, expected: dict[str, bytes], label: str) -> None:
    found = {}
    for line in raw.decode("utf-8-sig").splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r"([a-fA-F0-9]{64})  (.+)", line)
        require(match is not None, f"{label}: invalid checksum row {line!r}")
        digest, name = match.groups()
        require(name not in found, f"{label}: duplicate checksum for {name}")
        found[name] = digest.lower()
    require(set(found) == set(expected), f"{label}: checksum file set differs from expected payloads")
    for name, data in expected.items():
        require(found[name] == sha256(data), f"{label}: SHA256 mismatch for {name}")


def verify_zip(raw: bytes, expected: dict[str, bytes], label: str) -> None:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), f"{label}: duplicate ZIP entries")
        require(set(names) == set(expected), f"{label}: ZIP contents differ from expected payloads")
        require(archive.testzip() is None, f"{label}: ZIP CRC failure")
        for name, data in expected.items():
            actual = archive.read(name)
            require(len(actual) == len(data) and sha256(actual) == sha256(data),
                    f"{label}: ZIP payload mismatch for {name}")


def verify_base(directory: Path) -> dict[str, bytes]:
    require(directory.is_dir(), f"base directory not found: {directory}")
    entries = list(directory.iterdir())
    require(all(p.is_file() and not p.is_symlink() for p in entries),
            "base directory must contain only the 12 regular downloaded asset files")
    require({p.name for p in entries} == BASE_ASSETS, "base release must contain exactly the 12 original assets")
    files = {p.name: p.read_bytes() for p in entries}
    manifest = json.loads(files["RELEASE-MANIFEST.json"].decode("utf-8-sig"))
    require(manifest.get("tag") == TAG, "unexpected base release tag")
    require(manifest.get("commit") == BASE_COMMIT, "base release commit differs from the immutable tag")
    rows = manifest.get("files")
    require(isinstance(rows, list), "base manifest.files must be a list")
    seen = set()
    for row in rows:
        require(isinstance(row, dict), "invalid base manifest file record")
        name = row.get("name")
        require(isinstance(name, str) and name in BASE_PAYLOADS and name not in seen,
                f"unexpected or duplicate base manifest entry: {name!r}")
        seen.add(name)
        require(row.get("bytes") == len(files[name]), f"base byte count mismatch: {name}")
        require(isinstance(row.get("sha256"), str) and row["sha256"].lower() == sha256(files[name]),
                f"base SHA256 mismatch: {name}")
    require(seen == BASE_PAYLOADS, "base manifest does not cover every expected payload")
    for suffix, name in ((".uf2", "SHA256SUMS.txt"), (".bin", "SHA256SUMS-ESP32.txt")):
        verify_checksums(files[name], {n: files[n] for n in BASE_FIRMWARE if n.endswith(suffix)}, name)
    verify_zip(files[BASE_ZIP], {n: data for n, data in files.items() if n != BASE_ZIP}, BASE_ZIP)
    return files


def firmware_record(name: str, data: bytes, board: str, commit: str) -> dict:
    if name.endswith(".uf2"):
        kind, offset = "uf2-bootloader", None
    elif name.endswith("-freshInstall-merged.bin"):
        kind, offset = "esp32-fresh-install-merged", "0x00000"
    else:
        kind, offset = "esp32-application-update", "0x10000"
    metadata = {}
    if name in V3_FILES:
        fresh = name.endswith("-freshInstall-merged.bin")
        metadata = {
            "revision": V3_REVISION,
            "storage": {
                "contains_formatted_empty_spiffs": fresh,
                "overwrites_existing_identity_and_settings_even_without_erase": fresh,
                "clean_install_only": fresh,
                "preserves_existing_filesystem": not fresh,
                "initializes_erased_flash_storage": fresh,
                "boot_recovery": "exact-empty-factory-hash-only automatic native format; otherwise explicit two-step user confirmation",
                "hardware_validation": "FS1 still failed on user hardware; FS2 hardware success not yet confirmed",
            },
        }
    return record(name, data, board=board, kind=kind, flash_offset=offset,
                  source_commit=commit, **metadata)


def build_addon(base: dict[str, bytes], v3: dict[str, bytes], notes: bytes, commit: str) -> dict[str, bytes]:
    sources = {"original_five_boards": {"tag": TAG, "commit": BASE_COMMIT},
               "heltec_v3_addition": {"commit": commit, "revision": V3_REVISION,
                                     "updates_existing_release": TAG}}
    firmwares = {n: base[n] for n in BASE_FIRMWARE} | v3
    firmware_rows = [firmware_record(n, data, BASE_FIRMWARE.get(n, "Heltec V3 OLED"),
                                    BASE_COMMIT if n in BASE_FIRMWARE else commit)
                     for n, data in sorted(firmwares.items())]
    readme = f"""MeshCore SmartUI {VERSION} — шесть плат, экспериментальный интерфейс

ВНИМАНИЕ: это эксперимент, не стабильная версия. Компиляция и симуляции
не заменяют проверку на реальной плате. Выбирайте файл строго для своей платы.

Пять исходных плат: {BASE_COMMIT}
Heltec V3 OLED, исправление {V3_REVISION}: {commit}
Старый тег {TAG} и его 12 файлов НЕ заменены.
Этот общий ZIP дополнен V3; старый all-five-boards.zip оставлен без изменений.

V3 FS2: ВАЖНО ПЕРЕД ПРОШИВКОЙ
- Работающая нода: update.bin по адресу 0x10000, БЕЗ Erase Flash.
  Этот файл содержит только приложение и не записывает раздел SPIFFS.
- После уже выполненной очистки или STORAGE ERROR именно после Erase:
  freshInstall-merged.bin FS2 по адресу 0x00000. Он содержит заранее
  отформатированное пустое SPIFFS; повторять Erase Flash не требуется.
- ВНИМАНИЕ: V3 freshInstall-merged.bin FS2 заменяет SPIFFS пустым хранилищем
  и удаляет сохранённые identity/настройки ДАЖЕ БЕЗ галочки Erase Flash.
  Это файл только для осознанной чистой установки, не обычного обновления.
  Сохраните identity и нужные данные приватно до такой установки.
- FS1 не устранила STORAGE ERROR на пользовательской плате.
- FS2 при ошибке mount автоматически готовит штатное SPIFFS только при точном
  SHA256 известного пустого заводского образа и правильной разметке. Другие данные,
  стертый FF-раздел или ошибки чтения не разрешают автоматическое форматирование.
- Иначе восстановление требует двух отдельных подтверждений PRG/BOOT с отпусканием
  между ними; это удаляет identity/контакты/настройки. Отказ и таймаут не стирают данные.
- Успешная аппаратная проверка FS2 пока не подтверждена.
Имена V3-файлов прежние: скачайте их заново и проверьте свежий SHA256SUMS-V3.txt.

ФАЙЛЫ ПРОШИВОК
"""
    for row in firmware_rows:
        mode = "UF2 для USB-bootloader" if row["flash_offset"] is None else (
            "полный merged BIN, адрес 0x00000" if row["flash_offset"] == "0x00000" else
            "обновление приложения BIN, адрес 0x10000")
        if row["name"] in V3_FILES:
            mode += ("; FS2, ЧИСТАЯ УСТАНОВКА СО СБРОСОМ ДАННЫХ" if row["flash_offset"] == "0x00000"
                     else "; FS2, без записи файлового хранилища")
        readme += f"\n{row['board']} — {mode}\n  {row['name']}\n"
    readme += f"""
UF2 нельзя использовать как BIN и наоборот. Модели V3, V4.3 и Wireless Paper
не взаимозаменяемы. Merged предназначен для полной первоначальной установки;
update содержит только приложение. Перед очисткой флеш-памяти сохраните настройки.
Файлы V4.3/Wireless Paper оставлены прежними, без этого FS2-исправления:
после Erase их пустое хранилище также может дать STORAGE ERROR. Для работающих
нод используйте совместимый update без Erase. Не устанавливайте на них V3 BIN.

ПРОИСХОЖДЕНИЕ И ПРОВЕРКА
{ALL_MANIFEST}: source_commit и SHA256 для каждой из девяти прошивок,
а также хеши документов. {ALL_SUMS}: хеши всех остальных файлов ZIP,
включая общий манифест; файл контрольных сумм не хеширует сам себя.
base-release/ содержит неизменённые исходные заметки, манифест и контрольные суммы
пяти плат. Новый список V3: {ADDENDUM}.
Отдельный внешний {V3_SUMS} проверяет пять остальных новых release assets,
в том числе этот ZIP. Его не включают внутрь ZIP, чтобы избежать циклических хешей.
"""
    payloads = firmwares | {"README_ALL_SIX_RU.txt": readme.encode("utf-8"), ADDENDUM: notes}
    for name in (NOTES, "RELEASE-MANIFEST.json", "SHA256SUMS.txt", "SHA256SUMS-ESP32.txt"):
        payloads["base-release/" + name] = base[name]
    common = {"schema_version": 1, "tag": TAG, "kind": "six-board-combined-bundle",
              "v3_revision": V3_REVISION,
              "sources": sources, "original_release_assets": records(base),
              "files": firmware_rows + records({n: b for n, b in payloads.items() if n not in firmwares}),
              "checksums_file": ALL_SUMS,
              "checksums_scope": "Every ZIP entry except the checksum file itself."}
    payloads[ALL_MANIFEST] = json_bytes(common)
    payloads[ALL_SUMS] = checksum_bytes(payloads)
    verify_checksums(payloads[ALL_SUMS], {n: b for n, b in payloads.items() if n != ALL_SUMS}, ALL_SUMS)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(payloads.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    zip_raw = output.getvalue()
    verify_zip(zip_raw, payloads, COMBINED_ZIP)
    assets = v3 | {ADDENDUM: notes, COMBINED_ZIP: zip_raw}
    manifest = {"schema_version": 1, "tag": TAG, "kind": "heltec-v3-release-addition",
                "revision": V3_REVISION,
                "sources": sources, "original_release_assets_unchanged": records(base),
                "firmware_files": [row for row in firmware_rows if row["source_commit"] == commit],
                "files": records(assets), "checksums_file": V3_SUMS,
                "checksums_scope": "All five other new assets, including this manifest and the combined ZIP."}
    assets[V3_MANIFEST] = json_bytes(manifest)
    assets[V3_SUMS] = checksum_bytes(assets)
    require(len(assets) == 6, "internal error: addition must contain exactly six assets")
    require(not (set(assets) & BASE_ASSETS), "internal error: addition would replace an existing release asset")
    verify_checksums(assets[V3_SUMS], {n: b for n, b in assets.items() if n != V3_SUMS}, V3_SUMS)
    return assets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--v3-dir", type=Path, required=True)
    parser.add_argument("--commit", required=True, help="full 40-hex source commit used to build V3")
    parser.add_argument("--output", type=Path, required=True, help="new, non-existing output directory")
    args = parser.parse_args()
    try:
        commit = args.commit.lower()
        require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None and commit != BASE_COMMIT,
                "--commit must be the full new V3 source commit, not the original five-board commit")
        base_dir, v3_dir, output = args.base_dir.resolve(), args.v3_dir.resolve(), args.output.resolve()
        require(not output.exists(), f"refusing to overwrite an existing output directory: {output}")
        for source_dir in (base_dir, v3_dir):
            require(not output.is_relative_to(source_dir) and not source_dir.is_relative_to(output),
                    "output must not overlap either input directory")
        base = verify_base(base_dir)
        require(PAIR.stem == f"Heltec_V3_OLED_SmartUI_{VERSION}" and
                PAIR.marker == f"V3 OLED SmartUI {VERSION} {V3_REVISION}".encode("ascii"),
                "unexpected V3 FS2 validation configuration")
        sizes_and_hashes = validate_v3_pair(v3_dir)
        v3 = {name: (v3_dir / name).read_bytes() for name in V3_FILES}
        for index, name in enumerate(V3_FILES):
            require(len(v3[name]) == sizes_and_hashes[index] and
                    sha256(v3[name]) == sizes_and_hashes[index + 2].lower(),
                    f"V3 input changed during validation: {name}")
        notes = (ROOT / ADDENDUM).read_bytes()
        require(bool(notes.decode("utf-8-sig").strip()), "V3 addendum must not be empty")
        assets = build_addon(base, v3, notes, commit)
        # All format/CRC/hash checks finish before touching the output directory.
        output.mkdir(parents=True)
        for name, data in sorted(assets.items()):
            with (output / name).open("xb") as file:
                file.write(data)
        require({p.name for p in output.iterdir()} == set(assets), "output asset inventory mismatch")
        for name, data in assets.items():
            require(sha256((output / name).read_bytes()) == sha256(data), f"written asset hash mismatch: {name}")
        for directory, original in ((base_dir, base), (v3_dir, v3)):
            for name, data in original.items():
                require(sha256((directory / name).read_bytes()) == sha256(data), f"input changed: {directory / name}")
        print(json.dumps({"directory": str(output), "tag_unchanged": TAG,
                          "v3_revision": V3_REVISION,
                          "base_commit": BASE_COMMIT, "v3_source_commit": commit,
                          "original_assets_unchanged": 12, "assets": records(assets)}, indent=2))
        return 0
    except (OSError, ValueError, zipfile.BadZipFile, KeyError, TypeError) as error:
        parser.exit(1, f"V3 add-on packaging failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
