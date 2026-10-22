#!/usr/bin/env python3
"""Exercise the production startup mount against pinned Adafruit/LittleFS code.

Flash is a RAM disk; FreeRTOS mutexes are checked host stubs. The production
Adafruit_LittleFS::begin/format and littlefs1.7 implementations are compiled
unchanged. Pinned InternalFS/CustomLFS callbacks create legacy images that the
guarded driver must read without writes. No board access, flash writes, or
installed package modifications.
"""

from pathlib import Path
import hashlib
import os
import re
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
FRAMEWORK_COMMIT = "d541301665b40959682252911e57b11df3ee651a"
HASHES = {
    "Adafruit_LittleFS.cpp": "a812a29bb42738e3f98bc5230a2c7c1ca0cdcb191b9a4a1b438c580ce8d37d32",
    "Adafruit_LittleFS.h": "4b3fb8db607393eb4f6a476e42c3f5017521d796c295d1e014a506d8ebf9807e",
    "Adafruit_LittleFS_File.h": "5d11f74d832d1776d5d453729bc02f33b8cbef9c448d68ecd3dc50672bf2f4b1",
    "littlefs/lfs.c": "21a07094466e132114c92654caea747335782465e17f11d677f2f0ae45415b2f",
    "littlefs/lfs.h": "4b5eac0ad8d72be2c8fe1e2b529d9ad4683ccf692acfbe7cea4b04e145751f26",
    "littlefs/lfs_util.c": "e8de372d8ee7ad90543a3165f74baa76d0abb9077c76099a80d2dbd0a6e04149",
    "littlefs/lfs_util.h": "52213bc2f11cb56d056aee9ac5cef189b0840683c62926af068e62ae0f6dfd73",
    "../../InternalFileSytem/src/InternalFileSystem.cpp": "bd024e7f106c48fa162d2df883159ea14a0e3a83945d0b4bdc52fabe9aa4d0e9",
    "../../InternalFileSytem/src/InternalFileSystem.h": "e5ab964c5a938a3edb2782d762f8a8b8eb2e918f6efaa4975da4c2a8bd133968",
    "../../InternalFileSytem/src/flash/flash_nrf5x.h": "87ad02039e0154e7ebe4e73c0450cc5ea839830e4d524b59fa8013840d3d2510",
}
CUSTOM_HASHES = {
    "CustomLFS.cpp": "5423457569861a5f26770cd1e1e180e2f67d8a0bac7945a84c07e83a28ffdf63",
    "CustomLFS.h": "65a2efcf699d6069dd68fd4f19b856a9e0573bda61fa3fc20568951b8d31f52d",
}


def custom_library_source():
    for source in (ROOT / ".pio/libdeps").glob("*/CustomLFS/src"):
        if all(hashlib.sha256((source / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
               == expected for name, expected in CUSTOM_HASHES.items()):
            return source
    raise RuntimeError("Install pinned CustomLFS before this test")


def library_source():
    platformio = (ROOT / "platformio.ini").read_text(encoding="utf-8")
    assert f"Adafruit_nRF52_Arduino#{FRAMEWORK_COMMIT}" in platformio
    assert "CustomLFS#b3928ea2d0f46c2533e901c43f471a081c503a3c" in platformio
    custom_library_source()
    core = Path(os.environ.get("PLATFORMIO_CORE_DIR", Path.home() / ".platformio"))
    for candidate in (core / "packages").glob(
        "framework-arduinoadafruitnrf52*/libraries/Adafruit_LittleFS/src"
    ):
        if all(hashlib.sha256((candidate / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
               == expected for name, expected in HASHES.items()):
            return candidate
    raise RuntimeError("Install the pinned Adafruit nRF52 framework before running this test")


RTOS = r'''#pragma once
#include <cassert>
#include <cstdint>
struct StaticSemaphore_t { bool held = false, shared = false; };
using SemaphoreHandle_t = StaticSemaphore_t*;
constexpr uint32_t portMAX_DELAY = UINT32_MAX;
constexpr int pdTRUE = 1;
extern unsigned lock_acquisitions;
extern bool filesystem_locked, cache_locked, creating_shared_mutex, fail_mutex_creation;
inline SemaphoreHandle_t xSemaphoreCreateMutexStatic(StaticSemaphore_t* s) {
  if (fail_mutex_creation) return nullptr;
  s->shared=creating_shared_mutex; return s;
}
inline int xSemaphoreTake(SemaphoreHandle_t s, uint32_t) {
  assert(!s->held);
  if (s->shared) {
    assert(filesystem_locked && !cache_locked); cache_locked=true;
  } else {
    assert(!filesystem_locked && !cache_locked); // Lock order: FS -> shared cache.
    filesystem_locked=true; ++lock_acquisitions;
  }
  s->held=true; return pdTRUE;
}
inline void xSemaphoreGive(SemaphoreHandle_t s) {
  assert(s->held && filesystem_locked);
  if (s->shared) { assert(cache_locked); cache_locked=false; }
  else { assert(!cache_locked); filesystem_locked=false; }
  s->held=false;
}
'''

HARNESS = (ROOT / "tools/nrf52_safe_mount_fixture.cpp").read_text(encoding="utf-8")


def main():
    library = library_source()
    custom = custom_library_source()
    use_wsl = not (shutil.which("gcc") and shutil.which("g++"))
    if use_wsl and not shutil.which("wsl"):
        raise RuntimeError("gcc/g++ required, natively or through WSL")

    def host(path):
        path = Path(path).resolve()
        if not use_wsl:
            return str(path)
        return subprocess.check_output(["wsl", "--exec", "wslpath", "-a", str(path)],
                                       text=True, encoding="utf-8").strip()

    def run(args):
        subprocess.run((["wsl", "--exec"] if use_wsl else []) + args,
                       check=True, timeout=60)

    with tempfile.TemporaryDirectory(prefix="nrf52-safe-mount-") as directory:
        directory = Path(directory)
        (directory / "rtos.h").write_text(RTOS, encoding="utf-8")
        (directory / "Stream.h").write_text(
            "#pragma once\n#include <cstdint>\n#include <cstddef>\n#include <cstring>\n"
            "class Stream { public: virtual ~Stream() = default; };\n", encoding="utf-8")
        (directory / "Arduino.h").write_text(
            '#pragma once\n#include "Stream.h"\n#define CFG_DEBUG 0\n'
            '#define varclr(p) std::memset((p),0,sizeof(*(p)))\n', encoding="utf-8")
        (directory / "Adafruit_TinyUSB.h").write_text("#pragma once\n", encoding="utf-8")
        (directory / "common_inc.h").write_text(
            "#pragma once\n#include <cstdint>\n#include <cstddef>\n"
            "#define VERIFY_1(c) do { if (!(c)) return false; } while (0);\n"
            "#define VERIFY_2(c,r) do { if (!(c)) return (r); } while (0);\n"
            "#define VERIFY_SELECT(_1,_2,name,...) name\n"
            "#define VERIFY(...) VERIFY_SELECT(__VA_ARGS__,VERIFY_2,VERIFY_1)(__VA_ARGS__)\n",
            encoding="utf-8")
        (directory / "test.cpp").write_text(HARNESS, encoding="utf-8")
        common = ["-O2", "-ffunction-sections", "-fdata-sections",
                  "-DLFS_NO_ASSERT=1", "-I", host(directory), "-I", host(library),
                  "-I", host(library.parents[1] / "InternalFileSytem/src"),
                  "-I", host(custom), "-I", host(ROOT / "src")]
        objects = []
        for name in ("littlefs/lfs.c", "littlefs/lfs_util.c", "Adafruit_LittleFS.cpp"):
            output = directory / (Path(name).stem + ".o")
            cpp = name.endswith(".cpp")
            run(["g++" if cpp else "gcc", "-std=c++17" if cpp else "-std=c99",
                 *common, "-c", host(library / name), "-o", host(output)])
            objects.append(host(output))
        for chip in ("NRF52840_XXAA", "NRF52832_XXAA"):
            binary = directory / chip
            legacy_objects = []
            for source in (library.parents[1] / "InternalFileSytem/src/InternalFileSystem.cpp",
                           custom / "CustomLFS.cpp"):
                output = directory / f"{source.stem}-{chip}.o"
                run(["g++", "-std=c++17", *common, "-D" + chip,
                     "-c", host(source), "-o", host(output)])
                legacy_objects.append(host(output))
            run(["g++", "-std=c++17", *common, "-D" + chip, "-Wall", "-Wextra", "-Werror",
                 host(directory / "test.cpp"), *objects, *legacy_objects,
                 "-Wl,--gc-sections", "-o", host(binary)])
            run([host(binary)])

        # Select the actual startup branches, preserving STM32 and QSPI behavior.
        main_source = (ROOT / "examples/companion_radio/main.cpp").read_text(encoding="utf-8")
        startup = main_source.split("  bool storage_ready = true;", 1)[1]
        startup = startup.split('    MESH_DEBUG_PRINTLN("STORAGE ERROR:', 1)[0]
        source = directory / "wiring.cpp"
        source.write_text(startup, encoding="utf-8")
        prefix = ["wsl", "--exec"] if use_wsl else []
        for platform in ("NRF52_PLATFORM", "STM32_PLATFORM"):
            for extension in (None, "EXTRAFS", "QSPIFLASH"):
                flags = ["-D" + platform] + (["-D" + extension] if extension else [])
                selected = subprocess.check_output(
                    [*prefix, "g++", "-E", "-P", "-x", "c++", *flags, host(source)],
                    text=True, encoding="utf-8", timeout=30)
                selected = re.sub(r"\s+", "", selected)
                calls = re.findall(r"storage_ready=([^;]+);", selected)
                primary = ("shared_flash_cache_lock.begin()&&smartui::mountAtStartupOrInitializeErased(InternalFS,internal_storage_region.config())"
                           if platform == "NRF52_PLATFORM" else "InternalFS.begin()")
                expected = [primary]
                if extension == "EXTRAFS":
                    expected.append("smartui::mountAtStartupOrInitializeErased(ExtraFS,extra_storage_region.config())"
                                    if platform == "NRF52_PLATFORM"
                                    else "ExtraFS.Adafruit_LittleFS::begin()")
                elif extension == "QSPIFLASH":
                    expected.append("QSPIFlash.begin()")
                assert calls == expected, (platform, extension, calls)
                assert selected.index(primary) < selected.index("the_mesh.begin(")
        print("PASS startup wiring: 6 NRF52/STM32 and InternalFS/ExtraFS/QSPI combinations")


if __name__ == "__main__":
    main()
