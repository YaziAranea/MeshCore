#!/usr/bin/env python3
"""Verify the R8 OLED profile and production board/storage/font code without hardware."""
from pathlib import Path
import configparser
import json
import os
import re
import shutil
import subprocess
import tempfile

import test_ssd1306_font_profiles as fonts
import test_v3_storage_recovery as storage

ROOT = Path(__file__).resolve().parents[1]
ENV = "env:heltec_v4_r8_companion_radio_ble_femon_smartui"


def configuration_checks():
    config = configparser.ConfigParser(interpolation=None, strict=False)
    config.read([ROOT / "platformio.ini", ROOT / "variants/heltec_v4/platformio.ini",
                 ROOT / "variants/heltec_v4_r8/platformio.ini",
                 ROOT / "platformio.smartui-headless.ini"], encoding="utf-8")

    def resolve(section, option):
        value = config[section].get(option, "")
        return re.sub(r"\$\{([^}]+)\}", lambda m: resolve(*m[1].rsplit(".", 1)), value)

    def flags(section):
        return dict(re.findall(r"-D\s*([A-Za-z_][A-Za-z_0-9]*)(?:=([^\s;]+))?", resolve(section, "build_flags")))

    r8 = flags(ENV)
    r2 = flags("env:heltec_v4_3_companion_radio_ble_femon_smartui")
    for key, value in r2.items():
        if key.startswith(("UI_", "SMARTUI_", "DEFAULT_NOTIFY_")):
            assert r8.get(key) == value, f"R8 lost SmartUI feature {key}={value}"
    expected = {
        "P_LORA_TX_LED": "46", "PIN_VEXT_EN": "40", "PIN_VEXT_EN_ACTIVE": "LOW",
        "PIN_GPS_RX": "38", "PIN_GPS_TX": "39", "PIN_GPS_EN": "42",
        "PIN_GPS_EN_ACTIVE": "LOW", "PIN_VBAT_READ": "1", "ADC_MULTIPLIER": "5.0715f",
        "P_LORA_PA_POWER": "7", "P_LORA_KCT8103L_PA_CSD": "2", "P_LORA_KCT8103L_PA_CTX": "5",
        "P_LORA_NSS": "8", "P_LORA_SCLK": "9", "P_LORA_MOSI": "10", "P_LORA_MISO": "11",
        "P_LORA_RESET": "12", "P_LORA_BUSY": "13", "P_LORA_DIO_1": "14",
        "PIN_USER_BTN": "0", "PIN_BOARD_SDA": "17", "PIN_BOARD_SCL": "18", "PIN_OLED_RESET": "21",
        "DISPLAY_CLASS": "SSD1306Display", "RADIO_FEM_RXGAIN": "1", "ARDUINO_USB_MODE": "1",
        "AUTO_SHUTDOWN_MILLIVOLTS": "3200", "LOW_BATTERY_SHUTDOWN_FLOOR_MILLIVOLTS": "2700",
    }
    for key, value in expected.items():
        assert r8.get(key) == value, (key, r8.get(key), value)
    assert "HELTEC_V4_R8_OLED" in r8 and "HELTEC_V4_R8" in r8
    assert "HELTEC_LORA_V4" not in r8 and "PIN_ADC_CTRL" not in r8 and "PIN_GPS_RESET" not in r8
    assert config[ENV]["custom_smartui_fresh_spiffs"] == "yes"
    assert "tool-mkspiffs @ 2.230.0" in config[ENV]["platform_packages"]
    assert "V4 R8 SmartUI 0.16" in resolve(ENV, "build_flags")
    assert "-DAUTO_SHUTDOWN_MILLIVOLTS=3400" in config[ENV]["build_unflags"]
    assert flags("env:SmartUI_V43_R8_headless")["SMARTUI_HEADLESS"] == "1"
    board = json.loads((ROOT / "boards/heltec_v4_r8.json").read_text())
    assert board["build"]["arduino"]["memory_type"] == "qio_opi"
    assert board["build"]["psram_type"] == "opi" and board["upload"]["flash_size"] == "16MB"
    assert board["build"]["arduino"]["partitions"] == "default_16MB.csv"
    ui = (ROOT / "examples/companion_radio/ui-new/UITask.cpp").read_text(encoding="utf-8")
    pins = re.search(r"#elif defined\(HELTEC_V4_R8_OLED\).*?notify_gpio_pins\[\] = \{([^}]+)\}", ui, re.S)[1]
    assert set(map(int, re.findall(r"\d+", pins))) == {46, 4, 6, 15, 16, 47, 48}
    base = (ROOT / "src/helpers/ESP32Board.cpp").read_text()
    assert base.index("display.turnOff()") < base.index("radio_driver.powerOff()") < base.index("->stop()")
    print("PASS R8 GPIO/OPI/16MB/SPIFFS/headless and complete SmartUI feature parity")


ARDUINO = r'''
#pragma once
#include <stdint.h>
#include <cassert>
#define HIGH 1
#define LOW 0
#define OUTPUT 1
#define BD_STARTUP_RX_PACKET 2
using gpio_num_t=int;
using esp_reset_reason_t=int;
constexpr int ESP_RST_DEEPSLEEP=5;
extern int pins[49];
extern bool held[49], board_leds, deep_hold, peripherals_stopped;
extern uint32_t adc_raw;
extern int adc_resolution, reset_reason;
inline void pinMode(int,int) {}
inline void digitalWrite(int pin,int value) { assert(pin>=0 && pin<49);if(!held[pin])pins[pin]=value; }
inline void delay(unsigned) {}
inline void analogReadResolution(int bits) { adc_resolution=bits; }
inline uint32_t analogReadMilliVolts(int pin) { assert(pin==1);return adc_raw; }
inline int esp_reset_reason() { return reset_reason; }
inline uint64_t esp_sleep_get_ext1_wakeup_status() { return 0; }
inline void rtc_gpio_hold_dis(int pin) { assert(pin<=21);held[pin]=false; }
inline void rtc_gpio_hold_en(int pin) { assert(pin<=21);held[pin]=true; }
inline void rtc_gpio_deinit(int pin) { assert(pin<=21); }
inline void gpio_hold_dis(int pin) { assert(pin==40);held[pin]=false; }
inline void gpio_hold_en(int pin) { assert(pin==40);assert(peripherals_stopped);held[pin]=true; }
inline void gpio_deep_sleep_hold_dis() { deep_hold=false; }
inline void gpio_deep_sleep_hold_en() { deep_hold=true; }
void stopPeripherals();
'''

BASE = r'''
#pragma once
#include <Arduino.h>
class ESP32Board {
protected:
  uint8_t startup_reason=0;
public:
  virtual ~ESP32Board()=default;
  void begin() { digitalWrite(46,LOW); }
  virtual void onBeforeTransmit() {}
  virtual void onAfterTransmit() {}
  virtual void shutdownPeripherals() { stopPeripherals(); }
  virtual uint16_t getBattMilliVolts() { return 0; }
  virtual bool setAdcMultiplier(float) { return false; }
  virtual float getAdcMultiplier() const { return 0; }
  virtual bool setLoRaFemLnaEnabled(bool) { return false; }
  virtual bool canControlLoRaFemLna() const { return false; }
  virtual bool isLoRaFemLnaEnabled() const { return false; }
  virtual const char* getManufacturerName() const { return "stub"; }
};
'''

HARNESS = r'''
#include "HeltecV4R8Board.h"
#include <cmath>
#include <cstring>
#include <cstdio>
int pins[49]={};bool held[49]={},board_leds=false,deep_hold=false,peripherals_stopped=false;
uint32_t adc_raw=800;int adc_resolution=0,reset_reason=0;
HeltecV4R8Board* current=nullptr;
bool meshcoreBoardLedsEnabled() { return board_leds; }
void meshcoreSetBoardLedsEnabled(bool enabled) { board_leds=enabled; }
void stopPeripherals() {
  // Model the base class contract: display and GPS each release their claim;
  // radio is powered off before the derived board disables the shared rail.
  assert(pins[40]==LOW && pins[7]==HIGH);
  current->periph_power.release();
  assert(pins[40]==LOW);
  current->periph_power.release();
  assert(pins[40]==LOW);
  peripherals_stopped=true;
}
int main() {
  HeltecV4R8Board board;current=&board;board.begin();
  assert(pins[40]==LOW && pins[7]==HIGH && pins[2]==HIGH && pins[5]==HIGH);
  assert(strcmp(board.getManufacturerName(),"Heltec V4 R8 OLED")==0);
  assert(board.canControlLoRaFemLna() && !board.isLoRaFemLnaEnabled());
  assert(board.setLoRaFemLnaEnabled(true));
#if RADIO_FEM_RXGAIN == 0
  assert(!board.isLoRaFemLnaEnabled() && pins[5]==HIGH);
#else
  assert(board.isLoRaFemLnaEnabled() && pins[5]==LOW);
#endif
  assert(board.setLoRaFemLnaEnabled(false) && !board.isLoRaFemLnaEnabled() && pins[5]==HIGH);
  board.onBeforeTransmit();assert(pins[46]==LOW && pins[5]==HIGH);
  board_leds=true;board.onBeforeTransmit();assert(pins[46]==HIGH);
  board.onAfterTransmit();assert(pins[46]==LOW);
  const float nominal=board.getAdcMultiplier();
  assert(nominal==5.0715f && board.setAdcMultiplier(nominal*0.75f));
  assert(board.setAdcMultiplier(nominal*1.25f));
  assert(!board.setAdcMultiplier(nominal*0.7f) && !board.setAdcMultiplier(nominal*1.3f));
  assert(!board.setAdcMultiplier(NAN) && !board.setAdcMultiplier(INFINITY));
  assert(board.setAdcMultiplier(0) && board.getAdcMultiplier()==nominal);
  assert(board.getBattMilliVolts()==static_cast<uint16_t>(800*nominal+0.5f));
  assert(adc_resolution==12);adc_raw=20000;assert(board.getBattMilliVolts()==65535);
  // Turning off OLED cannot disable the FEM rail: permanent board claim stays.
  board.periph_power.claim();board.periph_power.release();
  assert(pins[40]==LOW && pins[7]==HIGH && !held[40] && !deep_hold);
  board.periph_power.claim(); // active display
  board.periph_power.claim(); // active GPS
  board.shutdownPeripherals();
  assert(peripherals_stopped && pins[40]==HIGH && pins[7]==LOW && pins[2]==LOW);
  assert(held[40] && held[7] && held[2] && deep_hold);
  // Simulate reset from deep sleep. GPIO writes must follow hold release.
  reset_reason=ESP_RST_DEEPSLEEP;
  HeltecV4R8Board rebooted;current=&rebooted;rebooted.begin();
  assert(pins[40]==LOW && pins[7]==HIGH && pins[2]==HIGH);
  assert(!held[40] && !held[7] && !held[2] && !deep_hold);
  puts("PASS actual R8 board: LED gate, LNA, ADC, awake/display-off rail, shutdown, held-pin wake");
}
'''


def main():
    configuration_checks()
    compiler = shutil.which("g++")
    via_wsl = not compiler and os.name == "nt"
    if not compiler and not via_wsl:
        raise RuntimeError("Host g++ required; no skipped test success")

    def path(value):
        if via_wsl:
            return subprocess.check_output(["wsl", "--exec", "wslpath", "-a", str(value)], text=True).strip()
        return str(value)

    def build_run(folder, name, sources, includes, defines=()):
        binary = folder / name
        command = (["wsl", "--exec", "g++"] if via_wsl else [compiler])
        command += ["-std=c++17", "-O2", "-Wall", "-Wextra", "-Wno-unused-parameter"]
        command += ["-D" + flag for flag in defines]
        command += ["-I" + path(include) for include in includes]
        command += [path(source) for source in sources] + ["-o", path(binary)]
        subprocess.run(command, check=True)
        run = ["wsl", "--exec", path(binary)] if via_wsl else [str(binary)]
        return subprocess.check_output(run, text=True)

    with tempfile.TemporaryDirectory(prefix="smartui-r8-profile-") as directory:
        folder = Path(directory)
        board = folder / "board"
        (board / "driver").mkdir(parents=True)
        (board / "helpers").mkdir()
        (board / "Arduino.h").write_text(ARDUINO)
        (board / "helpers/ESP32Board.h").write_text(BASE)
        for filename in ("driver/gpio.h", "driver/rtc_io.h", "esp_sleep.h"):
            (board / filename).write_text('#include "Arduino.h"\n')
        (board / "main.cpp").write_text(HARNESS)
        variant = ROOT / "variants/heltec_v4_r8"
        defines = ("HELTEC_V4_R8_OLED=1", "PIN_VEXT_EN=40", "PIN_VEXT_EN_ACTIVE=LOW",
                   "P_LORA_TX_LED=46", "P_LORA_PA_POWER=7", "P_LORA_KCT8103L_PA_CSD=2",
                   "P_LORA_KCT8103L_PA_CTX=5", "P_LORA_DIO_1=14", "P_LORA_NSS=8",
                   "PIN_VBAT_READ=1", "ADC_MULTIPLIER=5.0715f")
        for lna in (0, 1):
            print(build_run(folder, f"board-{lna}", [board / "main.cpp", variant / "HeltecV4R8Board.cpp",
                  variant / "LoRaFEMControl.cpp"], [board, variant, ROOT / "src"],
                  (*defines, f"RADIO_FEM_RXGAIN={lna}")), end="")

        safe = folder / "storage"
        safe.mkdir()
        (safe / "stub.h").write_text(storage.STUB)
        for filename in ("SHA256.h", "esp_partition.h", "esp_spiffs.h", "SPIFFS.h"):
            (safe / filename).write_text('#include "stub.h"\n')
        (safe / "main.cpp").write_text(storage.SOURCE.replace('int main() {',
            'int main() { expect(strcmp(smartui::kStorageRecoveryBoard,"V4 R8")==0);'))
        print(build_run(folder, "storage-r8", [safe / "main.cpp"], [safe, storage.HEADERS],
              ("TEST_PROFILE=2", "UI_V3_STORAGE_RECOVERY=0", "UI_SAFE_STORAGE_RECOVERY=1", "HELTEC_V4_R8=1")), end="")

        render = folder / "font"
        render.mkdir()
        for filename, source in fonts.STUBS.items():
            (render / filename).write_text(source, encoding="utf-8")
        (render / "main.cpp").write_text(fonts.HARNESS, encoding="utf-8")
        cases = {}
        for profile in ("HELTEC_LORA_V4_3_OLED", "HELTEC_V4_R8_OLED"):
            cases[profile] = build_run(folder, profile, [render / "main.cpp",
                ROOT / "src/helpers/ui/SSD1306Display.cpp"], [render, ROOT / "src"], (profile + "=1",))
        assert cases["HELTEC_LORA_V4_3_OLED"] == cases["HELTEC_V4_R8_OLED"], "R8 OLED pixel/metric mismatch"
        print("PASS R8/R2 OLED renderer: all five fonts, UTF-8, wrapping and framebuffer pixels identical")


if __name__ == "__main__":
    main()
