#!/usr/bin/python3

# Adds PlatformIO post-processing to merge all the ESP flash images into a single image.

import os
import hashlib
import json
import re
import struct
import subprocess
import tempfile
from pathlib import Path

Import("env", "projenv")

board_config = env.BoardConfig()
firmware_bin = "${BUILD_DIR}/${PROGNAME}.bin"
merged_bin = os.environ.get("MERGED_BIN_PATH", "${BUILD_DIR}/${PROGNAME}-merged.bin")


def read_partition_table(path, flash_size):
    """Read the exact table being flashed, including its generated MD5 footer."""
    raw = path.read_bytes()
    if len(raw) < 64 or len(raw) % 32:
        raise ValueError("Invalid partitions.bin length")
    partitions = []
    checked_md5 = False
    for pos in range(0, len(raw), 32):
        record = raw[pos:pos + 32]
        if record[:2] == b"\xeb\xeb":
            if record[2:16] != b"\xff" * 14 or record[16:] != hashlib.md5(raw[:pos]).digest():
                raise ValueError("Partition-table MD5 is invalid")
            if any(byte != 0xFF for byte in raw[pos + 32:]):
                raise ValueError("Unexpected data after partition-table MD5")
            checked_md5 = True
            break
        magic, kind, subtype, offset, size, label, flags = struct.unpack("<HBBII16sI", record)
        if magic != 0x50AA or size == 0 or offset % 4096 or size % 4096:
            raise ValueError("Invalid partition entry")
        if offset + size > flash_size:
            raise ValueError("Partition exceeds configured flash capacity")
        partitions.append(dict(kind=kind, subtype=subtype, offset=offset, size=size,
                               label=label.split(b"\0", 1)[0].decode("ascii"), flags=flags))
    if not checked_md5 or not partitions:
        raise ValueError("Expected a nonempty partition table with MD5")
    ordered = sorted(partitions, key=lambda entry: entry["offset"])
    for left, right in zip(ordered, ordered[1:]):
        if left["offset"] + left["size"] > right["offset"]:
            raise ValueError("Overlapping flash partitions")
    return partitions


def spiffs_geometry(env):
    """Match mkspiffs' Arduino variant to the SDK actually on the include path."""
    sdk_paths = {Path(env.subst(str(include))) / "sdkconfig.h"
                 for include in env.get("CPPPATH", [])}
    sdk_paths = {path.resolve() for path in sdk_paths if path.is_file()}
    if len(sdk_paths) != 1:
        raise ValueError("Cannot uniquely resolve the active SDK sdkconfig.h")
    sdk = next(iter(sdk_paths)).read_text(encoding="utf-8")
    names = ("PAGE_SIZE", "OBJ_NAME_LEN", "META_LENGTH", "USE_MAGIC", "USE_MAGIC_LENGTH")
    config = {}
    for name in names:
        match = re.search(r"^#define\s+CONFIG_SPIFFS_" + name + r"\s+(\d+)\s*$", sdk, re.M)
        if match is None:
            raise ValueError("Missing SPIFFS SDK setting " + name)
        config[name] = int(match.group(1))
    # The pinned espressif32 builder uses one 4 KiB physical erase sector per
    # logical SPIFFS block. Page size and on-disk fields come from sdkconfig.
    block = 4096
    page = config["PAGE_SIZE"]
    if page <= 0 or page > block or block % page:
        raise ValueError("Unsupported SPIFFS page/block geometry")
    return config, page, block


def create_fresh_spiffs(env, partition, work):
    package = env.PioPlatform().get_package_dir("tool-mkspiffs")
    if not package:
        raise ValueError("Pinned PlatformIO tool-mkspiffs is not installed")
    package = Path(package)
    metadata = json.loads((package / "package.json").read_text(encoding="utf-8"))
    if metadata.get("version") != "2.230.0":
        raise ValueError("Fresh SPIFFS requires pinned tool-mkspiffs 2.230.0")
    tool = package / ("mkspiffs_espressif32_arduino" + (".exe" if os.name == "nt" else ""))
    if not tool.is_file():
        raise ValueError("PlatformIO Arduino ESP32 mkspiffs executable is missing")
    config, page, block = spiffs_geometry(env)
    version = subprocess.check_output([str(tool), "--version"], text=True)
    for tool_name, sdk_name in (("OBJ_NAME_LEN", "OBJ_NAME_LEN"), ("OBJ_META_LEN", "META_LENGTH"),
                               ("USE_MAGIC", "USE_MAGIC"), ("USE_MAGIC_LENGTH", "USE_MAGIC_LENGTH")):
        match = re.search(r"^\s*SPIFFS_" + tool_name + r":\s*(\d+)\s*$", version, re.M)
        if match is None or int(match.group(1)) != config[sdk_name]:
            raise ValueError("mkspiffs/firmware mismatch: " + tool_name)
    if not re.search(r"SPIFFS_ALIGNED_OBJECT_INDEX_TABLES:\s*0\s*$", version, re.M):
        raise ValueError("Unsupported mkspiffs object-index alignment")
    if partition["flags"] != 0 or partition["size"] % block:
        raise ValueError("Encrypted/unaligned SPIFFS partitions are not supported")
    empty = work / "empty-data"
    empty.mkdir()  # A new private directory, never the project's data/ or user files.
    image = Path(env.subst("$BUILD_DIR")) / "smartui-fresh-spiffs.bin"
    geometry = ["-s", str(partition["size"]), "-p", str(page), "-b", str(block)]
    subprocess.run([str(tool), "-c", str(empty), *geometry, str(image)], check=True)
    if any(empty.iterdir()):
        raise ValueError("Fresh SPIFFS staging directory is not empty")
    raw = image.read_bytes()
    if len(raw) != partition["size"] or all(byte == 0xFF for byte in raw):
        raise ValueError("Fresh SPIFFS image is erased or has an incorrect size")
    listing = subprocess.check_output([str(tool), "-l", *geometry, str(image)], text=True)
    if listing.strip():
        raise ValueError("Fresh SPIFFS image contains unexpected files")
    print("SmartUI fresh SPIFFS: offset=0x%x size=0x%x page=%d block=%d; EMPTY filesystem" %
          (partition["offset"], partition["size"], page, block))
    return image, raw


def merge_with_fresh_spiffs(source, env, flash_images):
    flash_name = board_config.get("upload.flash_size", "4MB")
    match = re.fullmatch(r"(\d+)(KB|MB)", flash_name.upper())
    if match is None:
        raise ValueError("Fresh-install merge requires a known flash capacity")
    flash_size = int(match.group(1)) * (1024 if match.group(2) == "KB" else 1024 * 1024)
    build = Path(env.subst("$BUILD_DIR")).resolve()
    table = build / "partitions.bin"
    partitions = read_partition_table(table, flash_size)
    candidates = [p for p in partitions if p["kind"] == 1 and p["subtype"] == 0x82]
    if len(candidates) != 1:
        raise ValueError("Fresh-install merge requires exactly one SPIFFS partition")
    spiffs = candidates[0]
    if len(flash_images) % 2:
        raise ValueError("Invalid merge image/offset pairs")
    images = [(int(env.subst(str(flash_images[i])), 0),
               Path(env.subst(str(flash_images[i + 1]))).resolve())
              for i in range(0, len(flash_images), 2)]
    if sum(path == table for _, path in images) != 1:
        raise ValueError("Merged partition table differs from the inspected table")
    app = Path(source[0].get_abspath()).resolve()
    app_offset = int(env.subst("$ESP32_APP_OFFSET"), 0)
    app_before = app.read_bytes()
    app_parts = [p for p in partitions if p["kind"] == 0 and p["offset"] == app_offset]
    if len(app_parts) != 1 or len(app_before) > app_parts[0]["size"]:
        raise ValueError("Application does not fit its partition")
    extents = []
    for offset, path in images:
        length = path.stat().st_size
        if length <= 0 or offset < 0 or offset + length > flash_size:
            raise ValueError("Invalid merge image bounds: " + str(path))
        extents.append((offset, offset + length))
    extents.append((spiffs["offset"], spiffs["offset"] + spiffs["size"]))
    extents.sort()
    if any(left[1] > right[0] for left, right in zip(extents, extents[1:])):
        raise ValueError("Fresh filesystem overlaps an application/boot image")
    destination = Path(env.subst(merged_bin)).resolve()
    with tempfile.TemporaryDirectory(prefix="smartui-fresh-", dir=build) as temporary:
        work = Path(temporary)
        fs_image, fs_raw = create_fresh_spiffs(env, spiffs, work)
        merged = work / "firmware-merged.bin"
        command = [env.subst("$PYTHONEXE"), env.subst("$OBJCOPY"), "--chip",
                   board_config.get("build.mcu", "esp32"), "merge_bin", "-o", str(merged),
                   "--flash_mode", board_config.get("build.flash_mode", "dio"),
                   "--flash_freq", env.subst("${__get_board_f_flash(__env__)}"),
                   "--flash_size", flash_name]
        for offset, path in [*images, (spiffs["offset"], fs_image)]:
            command.extend([hex(offset), str(path)])
        subprocess.run(command, check=True)
        result = merged.read_bytes()
        if app.read_bytes() != app_before or result[app_offset:app_offset + len(app_before)] != app_before:
            raise ValueError("Fresh merge changed the update/application bytes")
        if result[spiffs["offset"]:spiffs["offset"] + spiffs["size"]] != fs_raw:
            raise ValueError("Merged SPIFFS slice differs from the checked empty image")
        os.replace(merged, destination)
    print("WARNING: freshInstall-merged replaces SPIFFS identity/settings; update.bin does not.")
    return 0


def merge_bin_action(source, target, env):
    flash_images = [
        *env.Flatten(env.get("FLASH_EXTRA_IMAGES", [])),
        "$ESP32_APP_OFFSET",
        source[0].get_abspath(),
    ]
    option = env.GetProjectOption("custom_smartui_fresh_spiffs", "no").strip().lower()
    if option == "yes":
        try:
            return merge_with_fresh_spiffs(source, env, flash_images)
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            print("ERROR: refusing fresh-install merge: %s" % error)
            return 1
    if option not in ("no", "false", "0", ""):
        print("ERROR: custom_smartui_fresh_spiffs must be yes or no")
        return 1
    merge_cmd = " ".join(
        [
            '"$PYTHONEXE"',
            '"$OBJCOPY"',
            "--chip",
            board_config.get("build.mcu", "esp32"),
            "merge_bin",
            "-o",
            merged_bin,
            "--flash_mode",
            board_config.get("build.flash_mode", "dio"),
            "--flash_freq",
            "${__get_board_f_flash(__env__)}",
            "--flash_size",
            board_config.get("upload.flash_size", "4MB"),
            *flash_images,
        ]
    )
    return env.Execute(merge_cmd)


env.AddCustomTarget(
    name="mergebin",
    dependencies=firmware_bin,
    actions=merge_bin_action,
    title="Merge binary",
    description="Build combined image",
    always_build=True,
)
