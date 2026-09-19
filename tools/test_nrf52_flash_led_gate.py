"""Host integration test for the nRF52 flash-cache onboard-LED gate.

The test compiles the exact pinned Adafruit ``flash_cache.c`` from PlatformIO's
package cache.  Hardware callbacks are host stubs; the LED policy and linker
interposition are the production C++ implementations and genuine GNU
``--wrap=ledOn`` behavior.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "qa_outputs/nrf52-flash-led-gate"
PINNED_FRAMEWORK_COMMIT = "d541301665b40959682252911e57b11df3ee651a"
PINNED_FLASH_CACHE_SHA256 = "758f3b9f5628f718572736174e079af13a91b811ec82b103bfaec50dce5674f9"
LED_BUILTIN = 35


def normalized_sha256(path: Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def find_pinned_flash_cache() -> Path:
    platformio = (ROOT / "platformio.ini").read_text(encoding="utf-8")
    pin = re.search(
        r"framework-arduinoadafruitnrf52\s*@\s*"
        r"https://github\.com/meshcore-dev/Adafruit_nRF52_Arduino#([0-9a-f]{40})",
        platformio,
    )
    assert pin and pin.group(1) == PINNED_FRAMEWORK_COMMIT, "unexpected nRF52 framework pin"

    core = Path(os.environ.get("PLATFORMIO_CORE_DIR", Path.home() / ".platformio"))
    candidates = sorted(
        (core / "packages").glob(
            "framework-arduinoadafruitnrf52*/libraries/"
            "InternalFileSytem/src/flash/flash_cache.c"
        )
    )
    for candidate in candidates:
        if normalized_sha256(candidate) == PINNED_FLASH_CACHE_SHA256:
            return candidate

    details = ", ".join(
        f"{candidate} ({normalized_sha256(candidate)})" for candidate in candidates
    ) or "no cached framework candidates"
    raise RuntimeError(
        "Pinned Adafruit flash_cache.c is not installed in PlatformIO's package cache: "
        + details
    )


def ini_section(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    match = re.search(
        rf"(?ms)^\[{re.escape(name)}\]\s*$\n(.*?)(?=^\[|\Z)",
        source,
    )
    assert match, f"missing [{name}] in {path.relative_to(ROOT)}"
    return match.group(1)


def assert_gate_flags(section: str, profile: str) -> None:
    assert re.search(r"(?m)^\s*-D\s+SMARTUI_NRF52_LED_GATE=1\s*$", section), profile
    assert re.search(r"(?m)^\s*-Wl,--wrap=ledOn\s*$", section), profile


def assert_release_profiles() -> None:
    assert_gate_flags(
        ini_section(
            ROOT / "variants/heltec_t096/platformio.ini",
            "env:Heltec_t096_companion_radio_ble_femon",
        ),
        "T096 FEM release profile",
    )
    assert_gate_flags(
        ini_section(
            ROOT / "variants/heltec_t114/platformio.ini",
            "env:Heltec_t114_companion_radio_ble",
        ),
        "T114 release profile",
    )

    promicro_path = ROOT / "variants/promicro/platformio.ini"
    promicro_base = ini_section(promicro_path, "env:ProMicro_companion_radio_ble")
    assert_gate_flags(promicro_base, "ProMicro BLE base profile")
    promicro_release = ini_section(promicro_path, "env:ProMicro_ra62_companion_radio_ble")
    assert re.search(
        r"(?m)^\s*extends\s*=\s*env:ProMicro_companion_radio_ble\s*$",
        promicro_release,
    ), "ProMicro RA62 release must inherit the gated BLE profile"
    assert "${env:ProMicro_companion_radio_ble.build_flags}" in promicro_release


class HostToolchain:
    def __init__(self) -> None:
        self.use_wsl = not (shutil.which("gcc") and shutil.which("g++"))
        if self.use_wsl and not shutil.which("wsl"):
            raise RuntimeError("gcc and g++ are required (native or through WSL)")

    def path(self, path: Path) -> str:
        resolved = path.resolve()
        if not self.use_wsl:
            return str(resolved)
        return subprocess.check_output(
            ["wsl", "--exec", "wslpath", "-a", str(resolved)],
            text=True,
            encoding="utf-8",
            errors="replace",
        ).strip()

    def run(self, tool: str, args: list[str]) -> None:
        command = (["wsl", "--exec", tool] if self.use_wsl else [tool]) + args
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode:
            raise RuntimeError(
                f"{' '.join(command)} failed ({result.returncode})\n"
                f"{result.stdout}{result.stderr}"
            )

    def output(self, executable: Path) -> str:
        command = (
            ["wsl", "--exec", self.path(executable)]
            if self.use_wsl
            else [str(executable.resolve())]
        )
        return subprocess.check_output(
            command,
            text=True,
            encoding="utf-8",
            errors="replace",
        )


COMMON_FUNC_H = r"""#pragma once
#include <stdint.h>
#define minof(a, b) ((a) < (b) ? (a) : (b))
static inline uint32_t min32(uint32_t a, uint32_t b) { return a < b ? a : b; }
"""

VARIANT_H = r"""#pragma once
#ifndef LED_BUILTIN
#error LED_BUILTIN must be supplied by the test profile
#endif
"""

WIRING_DIGITAL_H = r"""#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
void ledOn(uint32_t pin);
void ledOff(uint32_t pin);
#ifdef __cplusplus
}
#endif
"""

ARDUINO_H = r"""#pragma once
#include <stdint.h>
"""

LED_CALLSITE_C = r"""#include <stdint.h>
#include "wiring_digital.h"
void invoke_led_on(uint32_t pin) { ledOn(pin); }
"""

HARNESS_CPP = r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

#include "BoardLedControl.h"
#include "flash_cache.h"

extern "C" void invoke_led_on(uint32_t pin);

namespace {
constexpr uint32_t kPageAddress = 0x10000;
constexpr uint32_t kOffset = 117;
constexpr uint32_t kOtherPin = LED_BUILTIN + 7;

std::array<uint8_t, FLASH_CACHE_SIZE> flash_image;
std::array<uint8_t, FLASH_CACHE_SIZE> cache_buffer;
std::vector<uint32_t> led_on_pins;
std::vector<uint32_t> led_off_pins;
unsigned read_count;
unsigned verify_count;
unsigned erase_count;
unsigned program_count;
uint32_t program_address;
uint32_t program_length;

void reset_observations() {
  led_on_pins.clear();
  led_off_pins.clear();
  read_count = verify_count = erase_count = program_count = 0;
  program_address = program_length = 0;
}

bool erase_flash(uint32_t address) {
  assert(address == kPageAddress);
  ++erase_count;
  flash_image.fill(0xff);
  return true;
}

uint32_t program_flash(uint32_t address, const void* source, uint32_t length) {
  assert(address == kPageAddress);
  assert(length == FLASH_CACHE_SIZE);
  ++program_count;
  program_address = address;
  program_length = length;
  std::memcpy(flash_image.data(), source, length);
  return length;
}

uint32_t read_flash(void* destination, uint32_t address, uint32_t length) {
  assert(address == kPageAddress);
  assert(length == FLASH_CACHE_SIZE);
  ++read_count;
  std::memcpy(destination, flash_image.data(), length);
  return length;
}

bool verify_flash(uint32_t address, const void* source, uint32_t length) {
  assert(address == kPageAddress);
  assert(length == FLASH_CACHE_SIZE);
  ++verify_count;
  return std::memcmp(flash_image.data(), source, length) == 0;
}

flash_cache_t new_cache() {
  cache_buffer.fill(0);
  return {
      erase_flash,
      program_flash,
      read_flash,
      verify_flash,
      FLASH_CACHE_INVALID_ADDR,
      cache_buffer.data(),
  };
}

struct WriteResult {
  std::array<uint8_t, FLASH_CACHE_SIZE> image;
  std::vector<uint32_t> on_pins;
  std::vector<uint32_t> off_pins;
  unsigned reads;
  unsigned verifies;
  unsigned erases;
  unsigned programs;
  uint32_t programmed_at;
  uint32_t programmed_bytes;
};

WriteResult changed_write(bool leds_enabled) {
  flash_image.fill(0xa5);
  const std::array<uint8_t, 9> payload = {0x01, 0x23, 0x45, 0x67, 0x89,
                                          0xab, 0xcd, 0xef, 0x5a};
  auto expected = flash_image;
  std::copy(payload.begin(), payload.end(), expected.begin() + kOffset);
  reset_observations();
  meshcoreSetBoardLedsEnabled(leds_enabled);
  auto cache = new_cache();

  assert(flash_cache_write(&cache, kPageAddress + kOffset, payload.data(), payload.size()) ==
         static_cast<int>(payload.size()));
  assert(cache.cache_addr == kPageAddress);
  flash_cache_flush(&cache);

  assert(cache.cache_addr == FLASH_CACHE_INVALID_ADDR);
  assert(flash_image == expected);
  return {flash_image, led_on_pins, led_off_pins, read_count, verify_count,
          erase_count, program_count, program_address, program_length};
}

void verify_equal_write_is_a_noop() {
  flash_image.fill(0x3c);
  const std::array<uint8_t, 5> identical = {0x3c, 0x3c, 0x3c, 0x3c, 0x3c};
  const auto before = flash_image;
  reset_observations();
  meshcoreSetBoardLedsEnabled(true);
  auto cache = new_cache();

  assert(flash_cache_write(&cache, kPageAddress + kOffset, identical.data(), identical.size()) ==
         static_cast<int>(identical.size()));
  flash_cache_flush(&cache);

  assert(read_count == 1);
  assert(verify_count == 1);
  assert(erase_count == 0 && program_count == 0);
  assert(led_on_pins.empty() && led_off_pins.empty());
  assert(flash_image == before);
  assert(cache.cache_addr == FLASH_CACHE_INVALID_ADDR);
}
}  // namespace

extern "C" void ledOn(uint32_t pin) { led_on_pins.push_back(pin); }
extern "C" void ledOff(uint32_t pin) { led_off_pins.push_back(pin); }

int main() {
  assert(meshcoreBoardLedsEnabled());

  const WriteResult disabled = changed_write(false);
  const WriteResult enabled = changed_write(true);

  // The policy changes only activation of the builtin LED. Flash work and
  // the full programmed page are byte-for-byte identical.
  assert(disabled.reads == 1 && enabled.reads == 1);
  assert(disabled.verifies == 1 && enabled.verifies == 1);
  assert(disabled.erases == 1 && enabled.erases == 1);
  assert(disabled.programs == 1 && enabled.programs == 1);
  assert(disabled.programmed_at == kPageAddress && enabled.programmed_at == kPageAddress);
  assert(disabled.programmed_bytes == FLASH_CACHE_SIZE);
  assert(enabled.programmed_bytes == FLASH_CACHE_SIZE);
  assert(disabled.image == enabled.image);
  assert(disabled.on_pins.empty());
  assert(enabled.on_pins == std::vector<uint32_t>{LED_BUILTIN});
  // OFF edges remain unconditional and therefore safe in either policy state.
  assert(disabled.off_pins == std::vector<uint32_t>{LED_BUILTIN});
  assert(enabled.off_pins == std::vector<uint32_t>{LED_BUILTIN});

  // The same genuine linker wrapper must pass non-builtin LEDs through even
  // while the onboard LED master is disabled.
  reset_observations();
  meshcoreSetBoardLedsEnabled(false);
  invoke_led_on(kOtherPin);
  assert(led_on_pins == std::vector<uint32_t>{kOtherPin});
  assert(erase_count == 0 && program_count == 0);

  verify_equal_write_is_a_noop();
  std::printf("PASS actual pinned flash_cache.c honors nRF52 onboard LED gate; flash data path preserved\n");
}
"""


def write_support_files() -> dict[str, Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "common_func.h": COMMON_FUNC_H,
        "variant.h": VARIANT_H,
        "wiring_digital.h": WIRING_DIGITAL_H,
        "Arduino.h": ARDUINO_H,
        "led_callsite.c": LED_CALLSITE_C,
        "harness.cpp": HARNESS_CPP,
    }
    result = {}
    for name, source in files.items():
        path = OUT / name
        path.write_text(source, encoding="utf-8")
        result[name] = path
    return result


def compile_and_run(flash_cache: Path) -> str:
    files = write_support_files()
    toolchain = HostToolchain()
    helpers = ROOT / "src/helpers"
    flash_dir = flash_cache.parent
    defines = [
        "-DNRF52_PLATFORM",
        "-DSMARTUI_NRF52_LED_GATE=1",
        f"-DLED_BUILTIN={LED_BUILTIN}",
    ]
    warnings = ["-O2", "-Wall", "-Wextra", "-Werror"]
    stub_include = ["-I", toolchain.path(OUT)]
    helper_include = ["-I", toolchain.path(helpers)]
    flash_include = ["-I", toolchain.path(flash_dir)]

    objects = {
        "flash": OUT / "flash_cache.o",
        "callsite": OUT / "led_callsite.o",
        "wrapper": OUT / "NRF52LedControl.o",
        "policy": OUT / "BoardLedControl.o",
        "harness": OUT / "harness.o",
    }
    toolchain.run(
        "gcc",
        ["-std=gnu11", *warnings, *defines, *stub_include, "-c", toolchain.path(flash_cache),
         "-o", toolchain.path(objects["flash"])],
    )
    toolchain.run(
        "gcc",
        ["-std=gnu11", *warnings, *stub_include, "-c", toolchain.path(files["led_callsite.c"]),
         "-o", toolchain.path(objects["callsite"])],
    )
    toolchain.run(
        "g++",
        ["-std=c++17", *warnings, *defines, *stub_include, *helper_include, "-c",
         toolchain.path(helpers / "NRF52LedControl.cpp"), "-o", toolchain.path(objects["wrapper"])],
    )
    toolchain.run(
        "g++",
        ["-std=c++17", *warnings, *defines, *helper_include, "-c",
         toolchain.path(helpers / "BoardLedControl.cpp"), "-o", toolchain.path(objects["policy"])],
    )
    toolchain.run(
        "g++",
        ["-std=c++17", *warnings, *defines, *helper_include, *flash_include, "-c",
         toolchain.path(files["harness.cpp"]), "-o", toolchain.path(objects["harness"])],
    )

    executable = OUT / ("nrf52-flash-led-gate.exe" if os.name == "nt" and not toolchain.use_wsl
                        else "nrf52-flash-led-gate")
    toolchain.run(
        "g++",
        [*(toolchain.path(path) for path in objects.values()), "-Wl,--wrap=ledOn",
         "-o", toolchain.path(executable)],
    )
    return toolchain.output(executable)


def main() -> None:
    assert_release_profiles()
    flash_cache = find_pinned_flash_cache()
    print(compile_and_run(flash_cache), end="")
    print(f"PASS compiled cached pinned framework source: {flash_cache}")
    print("PASS T096, T114 and ProMicro RA62 release profiles enable --wrap=ledOn")


if __name__ == "__main__":
    main()
