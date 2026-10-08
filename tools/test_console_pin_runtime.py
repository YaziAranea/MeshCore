#!/usr/bin/env python3
"""Run production notification-pin/bridge ownership methods with GPIO stubs."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def verify_variant_maps():
    """Validate the real production nRF allowlists against their Arduino maps."""
    source = (ROOT / "examples/companion_radio/ui-new/UITask.cpp").read_text(encoding="utf-8")
    checked = 0
    for macro, variant in (("HELTEC_T114", "heltec_t114"),
                           ("HELTEC_T096", "heltec_t096"),
                           ("PROMICRO", "promicro")):
        board = ROOT / "variants" / variant
        variant_source = (board / "variant.cpp").read_text(encoding="utf-8")
        initializer = scope(variant_source, "const uint32_t g_ADigitalPinMap[]")
        initializer = re.sub(r"//[^\n]*|/\*.*?\*/", "", initializer, flags=re.S)
        mapping = [int(value.strip(), 0) for value in initializer.split("{", 1)[1][:-1].split(",")
                   if value.strip()]
        branch = source.split(f"defined({macro})\n", 1)[1].split("\n#elif", 1)[0]
        branch = branch.split("\n#else\nstatic const int8_t notify_gpio_pins[] = {\n", 1)[0]
        lists = re.findall(r"static const int8_t notify_gpio_pins\[\] = \{([^}]+)\}", branch)
        assert lists, f"{macro}: production allowlist missing"
        for choices in lists:
            for value in choices.split(","):
                value = value.strip()
                if value == "PIN_LED":
                    header = (board / "variant.h").read_text(encoding="utf-8")
                    value = re.search(r"#define\s+PIN_LED\s+\(?\s*(\d+)", header)[1]
                pin = int(value, 0)
                assert 0 <= pin < len(mapping), f"{macro}: Arduino pin {pin} outside map"
                assert 0 <= mapping[pin] < 48, f"{macro}: pin {pin} maps to invalid {mapping[pin]:#x}"
                checked += 1
        if macro == "HELTEC_T114":
            assert mapping[0] == mapping[1] == 0xff
    print(f"PASS {checked} production nRF notification choices match real Arduino variant GPIO maps", flush=True)


def scope(source, signature):
    start = source.index(signature)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def integration():
    source = (ROOT / "examples/companion_radio/ui-new/UITask.cpp").read_text(encoding="utf-8")
    pin_list = source.split("#elif defined(HELTEC_T114)\n", 1)[1].split("\n#else", 1)[0]
    return r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#define UI_NOTIFY_GPIO_SELECT 1
#define UI_TONE_BRIDGE_PAGE 1
#define PIN_MSG_ALERT 35
#define PIN_MSG_TONE 13
#define DEFAULT_NOTIFY_TONE_PIN 13
#define DEFAULT_NOTIFY_TONE_BRIDGE_PIN 16
#define OUTPUT 1
#define LOW 0
static const uint32_t UI_TONE_BRIDGE_OWNER = 0x42525A54UL;
static bool ui_tone_bridge_owned = false;
static unsigned pin_writes, pin_modes;
static int levels[64];
static void pinMode(int pin, int) { assert(pin >= 0 && pin < 64); ++pin_modes; }
static void digitalWrite(int pin, int value) { assert(pin >= 0 && pin < 64); levels[pin] = value; ++pin_writes; }
struct PWM {
  unsigned stops = 0, clears = 0, releases = 0;
  void stop() { ++stops; }
  void removeAllPins() { ++clears; }
  void releaseOwnership(uint32_t owner) { assert(owner == UI_TONE_BRIDGE_OWNER); ++releases; }
} HwPWM3;
static bool block_board_led = false;
static bool isNotifyGpioPinBlockedByBuild(int pin) { return block_board_led && pin == 35; }
struct UITask {
  int led = 35, tone = 13, vibe = -1;
  bool bridge = false;
  int getNotifyLedPin() const { return led; }
  int getNotifyTonePin() const { return tone; }
  int getNotifyVibePin() const { return vibe; }
  bool isNotifyToneBridgeEnabled() const { return bridge; }
  bool isDeviceSettingsPinAllowed(const char*, int) const;
  void deviceSettingsPinOptions(const char*, char*, size_t) const;
};
''' + pin_list + "\n" + "\n".join(scope(source, signature) for signature in (
        "static bool isNotifyGpioPinAllowed(", "static void uiStopToneBridge(",
        "bool UITask::isDeviceSettingsPinAllowed(", "void UITask::deviceSettingsPinOptions(")) + r'''
int main() {
  // Unowned bridge cleanup must not pull an independently configured LED low.
  levels[13] = levels[16] = 1;
  uiStopToneBridge(13, 16);
  assert(levels[13] == 1 && levels[16] == 1 && pin_writes == 0 && pin_modes == 0);
  assert(HwPWM3.stops == 0 && HwPWM3.clears == 0 && HwPWM3.releases == 0);
  ui_tone_bridge_owned = true;
  uiStopToneBridge(13, 16);
  assert(!ui_tone_bridge_owned && levels[13] == 0 && levels[16] == 0);
  assert(HwPWM3.stops == 1 && HwPWM3.clears == 1 && HwPWM3.releases == 1);
  levels[16] = 1; const auto before = pin_writes;
  uiStopToneBridge(13, 16);
  assert(levels[16] == 1 && pin_writes == before);

  UITask ui;
  assert(ui.isDeviceSettingsPinAllowed("led_pin", 35));
  assert(ui.isDeviceSettingsPinAllowed("led_pin", 16));
  assert(!ui.isDeviceSettingsPinAllowed("led_pin", 13));
  assert(!ui.isDeviceSettingsPinAllowed("tone_pin", 35));
  assert(ui.isDeviceSettingsPinAllowed("vibe_pin", -1));
  assert(!ui.isDeviceSettingsPinAllowed("tone_pin", -1));
  assert(!ui.isDeviceSettingsPinAllowed("led_pin", 21));
  assert(!ui.isDeviceSettingsPinAllowed("not_a_pin", 16));
  // T114's Arduino 0/1 entries are 0xff sentinels, not usable physical pins.
  for (const char* role : {"led_pin", "tone_pin", "vibe_pin"}) {
    assert(!ui.isDeviceSettingsPinAllowed(role, 0));
    assert(!ui.isDeviceSettingsPinAllowed(role, 1));
  }
  ui.tone = 0; // A stale saved choice must not bypass the hardware allowlist.
  assert(!ui.isDeviceSettingsPinAllowed("tone_pin", 0));
  ui.tone = 13;
  ui.bridge = true;
  assert(!ui.isDeviceSettingsPinAllowed("led_pin", 16));
  assert(!ui.isDeviceSettingsPinAllowed("vibe_pin", 16));
  assert(!ui.isDeviceSettingsPinAllowed("tone_pin", 18));
  assert(ui.isDeviceSettingsPinAllowed("tone_pin", 13));
  block_board_led = true;
  assert(!ui.isDeviceSettingsPinAllowed("led_pin", 35));
  block_board_led = false;
  for (bool bridge : {false, true}) {
    ui.bridge = bridge;
    for (const char* role : {"led_pin", "tone_pin", "vibe_pin", "not_a_pin"}) {
      for (size_t capacity = 0; capacity <= 100; ++capacity) {
        unsigned char guarded[128]; memset(guarded, 0xa5, sizeof(guarded));
        char* out = reinterpret_cast<char*>(guarded + 8);
        ui.deviceSettingsPinOptions(role, out, capacity);
        for (size_t i = 0; i < 8; ++i) assert(guarded[i] == 0xa5);
        for (size_t i = 8 + capacity; i < sizeof(guarded); ++i) assert(guarded[i] == 0xa5);
        if (capacity) assert(memchr(out, 0, capacity));
      }
      ui.deviceSettingsPinOptions(role, nullptr, 100);
    }
  }
  char options[88];
  for (const char* role : {"led_pin", "tone_pin", "vibe_pin"}) {
    ui.bridge = false; ui.deviceSettingsPinOptions(role, options, sizeof(options));
    const std::string choices = std::string(",") + options + ",";
    assert(choices.find(",0,") == std::string::npos);
    assert(choices.find(",1,") == std::string::npos);
  }
  ui.bridge = false; ui.deviceSettingsPinOptions("vibe_pin", options, sizeof(options));
  assert(std::string(options).find("-1,") == 0);
  ui.bridge = true; ui.deviceSettingsPinOptions("tone_pin", options, sizeof(options));
  assert(std::string(options) == "13");
  puts("PASS production T114 pin ownership, bridge cleanup, runtime options and bounded buffers");
}
'''


def main():
    verify_variant_maps()
    compiler = shutil.which("g++") or shutil.which("clang++")
    flags = ["-std=c++17", "-Wall", "-Wextra", "-Werror"]
    if os.environ.get("SMARTUI_TEST_SANITIZE") == "1":
        flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie"]
    with tempfile.TemporaryDirectory(prefix="smartui-pin-runtime-") as directory:
        source = Path(directory) / "pins.cpp"
        source.write_text(integration(), encoding="utf-8")
        for optimization in ("-O1", "-Os", "-Ofast"):
            output = Path(directory) / ("pins" + optimization)
            if compiler:
                build = [compiler, *flags, optimization, str(source), "-o", str(output)]
                execute = [str(output)]
            elif os.name == "nt":
                def linux(path):
                    return subprocess.check_output(["wsl", "--exec", "wslpath", "-a", str(path)], text=True).strip()
                build = ["wsl", "--exec", "g++", *flags, optimization, linux(source), "-o", linux(output)]
                execute = ["wsl", "--exec", linux(output)]
            else:
                raise RuntimeError("Host C++ compiler required; tests were not run")
            print(f"Notification pin runtime {optimization}", flush=True)
            subprocess.run(build, check=True)
            subprocess.run(execute, check=True)


if __name__ == "__main__":
    main()
