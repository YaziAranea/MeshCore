#!/usr/bin/env python3
"""Compile the production optional-buzzer pin policy against audited board wiring."""
from pathlib import Path
import configparser
import os
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "examples/companion_radio/ui-new"

# These are hardware expectations, not values parsed from the policy header.
# Sources are the Heltec schematic URLs documented in OptionalTonePins.h.
PROFILES = (
    ("V3", "env:Heltec_v3_companion_radio_ble_smartui", "SmartUI_V3_headless",
     {4, 40, 41}, {1, 15, 16, 17, 18, 21, 35, 36, 37, 47, 48}),
    ("V43", "env:heltec_v4_3_companion_radio_ble_femon_smartui", "SmartUI_V43_headless",
     {4, 47, 48}, {1, 2, 5, 7, 17, 18, 21, 34, 35, 36, 37, 38, 39, 40, 41, 42}),
    ("R8", "env:heltec_v4_r8_companion_radio_ble_femon_smartui", "SmartUI_V43_R8_headless",
     {4, 6, 15, 16, 47, 48}, {1, 2, 5, 7, 17, 18, 21, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42}),
    ("Paper", "env:Heltec_Wireless_Paper_companion_radio_ble_smartui_full", "SmartUI_Paper_headless",
     {17, 21}, {2, 4, 5, 6, 7, 15, 16, 18, 19, 20, 45}),
)
# Strap pins, radio bus, USB, flash/PSRAM bus, and console UART are never options.
COMMON_RESERVED = {0, 3, 8, 9, 10, 11, 12, 13, 14, 19, 20, 26, 27, 28, 29, 30, 31, 32, 43, 44, 45, 46}
PIN_MACROS = (
    "P_LORA_DIO_1", "P_LORA_NSS", "P_LORA_RESET", "P_LORA_BUSY", "P_LORA_SCLK",
    "P_LORA_MISO", "P_LORA_MOSI", "P_LORA_TX_LED", "P_LORA_PA_POWER",
    "P_LORA_KCT8103L_PA_CSD", "P_LORA_KCT8103L_PA_CTX", "P_LORA_GC1109_PA_EN",
    "P_LORA_GC1109_PA_TX_EN", "PIN_USER_BTN", "PIN_VEXT_EN", "PIN_VBAT_READ",
    "PIN_ADC_CTRL", "PIN_BOARD_SDA", "PIN_BOARD_SCL", "PIN_OLED_RESET",
    "PIN_GPS_RX", "PIN_GPS_TX", "PIN_GPS_EN", "PIN_GPS_RESET",
    "DISP_CS", "DISP_BUSY", "DISP_DC", "DISP_RST", "DISP_SCLK", "DISP_MOSI",
)


def configuration():
    config = configparser.ConfigParser(interpolation=None, strict=False, inline_comment_prefixes=(";",))
    config.read([ROOT / "platformio.ini", ROOT / "platformio.smartui-headless.ini", *[
        ROOT / "variants" / board / "platformio.ini" for board in
        ("heltec_v3", "heltec_v4", "heltec_v4_r8", "heltec_wireless_paper")]], encoding="utf-8")

    def resolve(section, option, stack=()):
        key = (section, option)
        assert key not in stack, f"recursive configuration: {key}"
        if not config.has_option(section, option):
            parent = config[section].get("extends", "").strip()
            return resolve(parent, option, (*stack, key)) if parent else ""
        return re.sub(r"\$\{([^}]+)\}", lambda match:
                      resolve(*match[1].rsplit(".", 1), (*stack, key)), config[section][option])

    def macros(section):
        pattern = r"-([DU])\s*([A-Za-z_][A-Za-z_0-9]*)(?:=([^\s;]+))?"
        removed = set(re.findall(pattern, resolve(section, "build_unflags")))
        result = {}
        for operation, name, value in re.findall(pattern, resolve(section, "build_flags")):
            if (operation, name, value) in removed:
                continue
            if operation == "U":
                result.pop(name, None)
            else:
                result[name] = value or "1"
        return result

    cases = []
    for name, section, headless, allowed, hardware_reserved in PROFILES:
        flags = macros(section)
        for current in (flags, macros("env:" + headless)):
            for key, value in (("UI_OPTIONAL_NOTIFY_TONE", "1"), ("PIN_MSG_TONE", "-1"),
                               ("DEFAULT_NOTIFY_TONE_PIN", "-1"), ("UI_TONE_FALLBACK_TO_ALERT", "0"),
                               ("UI_SOUND_SETTINGS_GROUP", "1")):
                assert current.get(key) == value, (name, key, current.get(key))
        assert macros("env:" + headless)["SMARTUI_HEADLESS"] == "1"
        assert flags["SMARTUI_RELEASE_LABEL"].strip("'\"") == "0.18"
        assert "PIN_BUZZER" not in flags and "PIN_VIBRATION" not in flags
        if name == "Paper":
            assert flags["UI_NOTIFY_GPIO_SELECT"] == "0", "Tone must not enable Paper vibration GPIO"
            assert flags["UI_NOTIFICATION_SETTINGS"] == "1"
        else:
            assert flags["UI_NOTIFY_GPIO_SELECT"] == "1"
        resolved_reserved = set()
        for key in PIN_MACROS:
            value = flags.get(key, "")
            if value in flags:
                value = flags[value]
            if re.fullmatch(r"[0-9]+", value):
                resolved_reserved.add(int(value))
        reserved = COMMON_RESERVED | hardware_reserved | resolved_reserved
        assert not allowed & reserved, (name, "allowed GPIO conflicts with hardware", allowed & reserved)
        board_defines = [key + "=" + value for key, value in flags.items() if key.startswith("HELTEC_")]
        cases.append((name, board_defines, allowed, reserved))

    # Feature belongs to public SmartUI profiles; upstream and TFT keep their wiring.
    for section in ("env:Heltec_v3_companion_radio_ble", "env:heltec_v4_companion_radio_ble_femon",
                    "env:heltec_v4_r8_companion_radio_ble", "env:Heltec_Wireless_Paper_companion_radio_ble"):
        assert "UI_OPTIONAL_NOTIFY_TONE" not in macros(section), section
    print("PASS four public/headless optional-off defaults, menu gates, inherited peripheral conflicts, upstream isolation")
    return cases


def main():
    cases = configuration()
    cases += [("unrecognized", [], set(), set()),
              ("V4-TFT", ["HELTEC_LORA_V4=1", "HELTEC_LORA_V4_TFT=1"], set(), set()),
              ("R8-TFT", ["HELTEC_V4_R8=1", "HELTEC_V4_R8_TFT=1"], set(), set())]
    compiler = shutil.which("g++") or shutil.which("clang++")
    via_wsl = not compiler and os.name == "nt"
    if not compiler and not via_wsl:
        raise RuntimeError("Host C++ compiler required; no skipped test success")

    def path(value):
        return (subprocess.check_output(["wsl", "--exec", "wslpath", "-a", str(value)], text=True).strip()
                if via_wsl else str(value))

    with tempfile.TemporaryDirectory(prefix="smartui-optional-tone-") as directory:
        folder = Path(directory)
        for name, defines, allowed, reserved in cases:
            source = folder / (name + ".cpp")
            source.write_text('''#include "OptionalTonePins.h"
#include <cassert>
#include <climits>
#include <cstdio>
#include <set>
int main() {
  const std::set<int> allowed = { ALLOWED };
  const std::set<int> reserved = { RESERVED };
  assert(smartui::isOptionalTonePinAllowed(-1));
  assert(!smartui::isOptionalTonePinAllowed(INT_MIN));
  assert(!smartui::isOptionalTonePinAllowed(INT_MAX));
  for (int pin = -256; pin <= 512; ++pin)
    assert(smartui::isOptionalTonePinAllowed(pin) == (pin == -1 || allowed.count(pin) != 0));
  for (int pin : reserved) assert(!smartui::isOptionalTonePinAllowed(pin));
  std::set<int> offered;
  for (int pin : smartui::optional_tone_gpio_pins) {
    assert(smartui::isOptionalTonePinAllowed(pin));
    assert(offered.insert(pin).second);
  }
  if (allowed.empty()) assert(offered == std::set<int>{-1});
  else assert(offered == allowed);
  puts("PASS NAME: production pin predicate/list, reserved GPIO, off sentinel, invalid boundaries");
}
'''.replace("ALLOWED", ", ".join(map(str, sorted(allowed))))
                .replace("RESERVED", ", ".join(map(str, sorted(reserved))))
                .replace("NAME", name), encoding="utf-8")
            output = folder / (name + (".exe" if os.name == "nt" and not via_wsl else ""))
            command = (["wsl", "--exec", "g++"] if via_wsl else [compiler])
            command += ["-std=c++11", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
                        "-I" + path(UI), *["-D" + flag for flag in defines], path(source), "-o", path(output)]
            subprocess.run(command, check=True)
            subprocess.run(["wsl", "--exec", path(output)] if via_wsl else [str(output)], check=True)


if __name__ == "__main__":
    main()
