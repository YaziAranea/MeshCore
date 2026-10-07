"""Run bounded ADC calibration policy and check its production safety wiring."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def scope(source, signature):
    start = source.index(signature)
    brace = source.index("{", start)
    depth, end = 1, brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def integration():
    main = (ROOT / "examples/companion_radio/main.cpp").read_text(encoding="utf-8")
    ui = (ROOT / "examples/companion_radio/ui-new/UITask.cpp").read_text(encoding="utf-8")
    nrf = (ROOT / "src/helpers/NRF52Board.cpp").read_text(encoding="utf-8")
    board = (ROOT / "src/MeshCore.h").read_text(encoding="utf-8")
    poll = scope(main, "static void serviceAdcCalibrationWindow()")
    assert "board.isUsbPowerConfirmed()" in poll
    assert "deviceApiWritesAllowed()" in poll
    assert "adcServiceOwnerConnected(owner)" in poll
    assert "adcServiceSession(owner)" in poll
    link = scope(main, "static bool adcServiceUsbLinkPresent()")
    assert "return Serial.dtr();" in link and "return false;" in link
    owner = scope(main, "static bool adcServiceOwnerConnected(")
    assert "usbConsoleEnabled" in owner and "InterfaceType::USB" in owner
    assert "isInterfaceConnected(InterfaceType::USB)" in owner
    cli = scope(main, "static void companionAdcService(")
    assert "getSelectedInterface() == InterfaceType::USB" in cli
    assert "Owner::NONE" in cli
    loop = scope(main, "void loop()")
    assert loop.index("serviceAdcCalibrationWindow();") < loop.index("ui_task.loop();")
    transition = scope(ui, "void UITask::setAdcCalibrationServiceActive(")
    assert "_low_batt_strikes = 0;" in transition and "next_batt_chck = 0;" in transition
    assert "BOOT_GRACE" not in transition
    assert "!_storage_recovery_active && _board != NULL && _board->isUsbPowerConfirmed()" in ui
    adc_save = scope(ui, "bool UITask::setAdcMultiplier(")
    assert adc_save.index("commitUiPrefs(before)") < adc_save.index("stopSmartUiAdcCalibrationService();")
    fatal = scope(main, "static void serviceFatalBatterySafety()")
    assert "adc_calibration_service" not in fatal and "guard.update" in fatal
    assert "supportsConfirmedUsbPower() const { return false; }" in board
    assert "isUsbPowerConfirmed() { return false; }" in board
    confirmed = scope(nrf, "bool NRF52Board::isUsbPowerConfirmed()")
    assert "sd_softdevice_is_enabled(&sd_enabled) != NRF_SUCCESS" in confirmed
    assert "sd_power_usbregstatus_get(&usb_status) != NRF_SUCCESS" in confirmed
    # Execute the production hardware detection body, including both error paths.
    return r'''
#include <cassert>
#include <cstdint>
constexpr int NRF_SUCCESS = 0;
constexpr uint32_t POWER_USBREGSTATUS_VBUSDETECT_Msk = 1;
static int sd_query_result = 0, usb_result = 0;
static uint8_t sd_on = 1;
static uint32_t usb_value = 1;
static int sd_softdevice_is_enabled(uint8_t* value) { *value = sd_on; return sd_query_result; }
static int sd_power_usbregstatus_get(uint32_t* value) { *value = usb_value; return usb_result; }
struct Power { uint32_t USBREGSTATUS = 0; } power_registers;
static Power* NRF_POWER = &power_registers;
struct NRF52Board { bool isUsbPowerConfirmed(); };
''' + confirmed + r'''
int main() {
  NRF52Board board;
  assert(board.isUsbPowerConfirmed());
  usb_result = 1; assert(!board.isUsbPowerConfirmed());
  usb_result = 0; sd_query_result = 1; assert(!board.isUsbPowerConfirmed());
  sd_query_result = 0; usb_value = 0; assert(!board.isUsbPowerConfirmed());
  sd_on = 0; power_registers.USBREGSTATUS = 1; assert(board.isUsbPowerConfirmed());
  power_registers.USBREGSTATUS = 0; assert(!board.isUsbPowerConfirmed());
}
'''


def owner_integration():
    source = (ROOT / "examples/companion_radio/main.cpp").read_text(encoding="utf-8")
    body = "\n".join(scope(source, signature) for signature in (
        "static bool adcServiceUsbLinkPresent(", "static bool adcServiceOwnerConnected(",
        "static uint32_t adcServiceSession(", "static void serviceAdcCalibrationWindow(",
        "void stopSmartUiAdcCalibrationService(", "static void handleAdcService(",
        "static void consoleAdcService(", "static void companionAdcService("))
    return r'''
#include "AdcCalibrationService.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#define NRF52_PLATFORM 1
#define ENABLE_USB_INTERFACE 1
#define DISPLAY_CLASS 1
static uint32_t now = 100;
uint32_t millis() { return now; }
static smartui::AdcCalibrationService adc_calibration_service;
struct Board { bool external = true; bool isUsbPowerConfirmed() { return external; } } board;
struct Port { bool open = true; bool dtr() { return open; } } Serial;
struct Caps { bool adc_service = true; } caps;
static Caps deviceSettingsCapabilities() { return caps; }
enum class InterfaceType { Bluetooth, USB, WiFi };
struct Interfaces {
  InterfaceType selected = InterfaceType::Bluetooth;
  uint32_t generation = 1;
  bool connected = true;
  InterfaceType getSelectedInterface() const { return selected; }
  bool isInterfaceConnected(InterfaceType type) const { return type == selected && connected; }
  uint32_t getSessionGeneration() const { return generation; }
} interface_manager;
struct Status { bool usbConsoleEnabled = true; };
struct Controller {
  bool writable = true;
  Status value;
  Status status() const { return value; }
  bool deviceApiWritesAllowed() const { return writable; }
} connection_controller;
struct UI { bool active = false; void setAdcCalibrationServiceActive(bool value) { active = value; } } ui_task;
''' + body + r'''
static std::string command(const char* action, bool console = true) {
  char reply[480];
  if (console) consoleAdcService(action, reply, sizeof(reply), connection_controller.writable);
  else companionAdcService(action, reply, sizeof(reply), connection_controller.writable);
  return reply;
}
static void fresh() {
  adc_calibration_service = smartui::AdcCalibrationService{};
  board = Board{}; Serial = Port{}; caps = Caps{};
  interface_manager = Interfaces{}; connection_controller = Controller{};
  ui_task = UI{}; now = 100;
}
int main() {
  fresh();
  assert(command("start", false) == "ERR settings usb_required");
  interface_manager.selected = InterfaceType::WiFi;
  assert(command("start", false) == "ERR settings usb_required");
  interface_manager.selected = InterfaceType::Bluetooth;
  assert(command("start").find("active=1 remaining_ms=120000") != std::string::npos);
  now += 30000;
  assert(command("start").find("remaining_ms=90000") != std::string::npos);
  assert(ui_task.active);
  Serial.open = false; serviceAdcCalibrationWindow(); assert(!ui_task.active);
  Serial.open = true; serviceAdcCalibrationWindow(); assert(!ui_task.active);
  assert(command("").find("active=0 remaining_ms=0") != std::string::npos);
  assert(command("start").find("active=1") != std::string::npos);
  board.external = false; serviceAdcCalibrationWindow(); assert(!ui_task.active);
  assert(command("start") == "ERR settings usb_required");
  board.external = true;
  assert(command("start").find("active=1") != std::string::npos);
  now += 120000; serviceAdcCalibrationWindow(); assert(!ui_task.active);
  assert(command("").find("remaining_ms=0") != std::string::npos);
  assert(command("start").find("remaining_ms=120000") != std::string::npos);
  connection_controller.writable = false; serviceAdcCalibrationWindow(); assert(!ui_task.active);
  assert(command("start") == "ERR settings readonly");
  assert(command("stop").find("active=0") != std::string::npos);
  connection_controller.writable = true; caps.adc_service = false;
  assert(command("start") == "ERR settings unsupported");
  caps.adc_service = true;
  assert(command("start").find("active=1") != std::string::npos);
  connection_controller.value.usbConsoleEnabled = false;
  interface_manager.selected = InterfaceType::USB;
  serviceAdcCalibrationWindow(); assert(!ui_task.active);
  assert(command("start", false).find("active=1") != std::string::npos);
  interface_manager.generation++; serviceAdcCalibrationWindow(); assert(!ui_task.active);
  assert(command("start", false).find("active=1") != std::string::npos);
  interface_manager.connected = false; serviceAdcCalibrationWindow(); assert(!ui_task.active);
  interface_manager.connected = true; serviceAdcCalibrationWindow(); assert(!ui_task.active);
  assert(command("start", false).find("active=1") != std::string::npos);
  stopSmartUiAdcCalibrationService(); assert(!ui_task.active);
  puts("PASS production ADC service owner/USB/CLI hooks, deadline, reconnect and readonly cancellation");
}
'''


def main():
    hardware_test = integration()
    with tempfile.TemporaryDirectory(prefix="smartui-adc-service-") as directory:
        directory = Path(directory)
        hardware = directory / "confirmed_usb_test.cpp"
        hardware.write_text(hardware_test, encoding="utf-8")
        owners = directory / "adc_service_owner_test.cpp"
        owners.write_text(owner_integration(), encoding="utf-8")
        compiler = shutil.which("g++") or shutil.which("clang++")
        use_wsl = not compiler and os.name == "nt"
        if not compiler and not use_wsl:
            raise RuntimeError("Host C++ compiler required; cannot skip safety checks")

        def path(value):
            if not use_wsl:
                return str(value)
            return subprocess.check_output(["wsl", "--exec", "wslpath", "-a", str(value)], text=True).strip()

        prefix = ["wsl", "--exec", "g++"] if use_wsl else [compiler]
        for source in [ROOT / "tools/adc_calibration_service_test.cpp", hardware, owners]:
            output = directory / source.stem
            subprocess.run([*prefix, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O2",
                            "-I" + path(ROOT / "examples/companion_radio"),
                            path(source), "-o", path(output)], check=True)
            subprocess.run((["wsl", "--exec"] if use_wsl else []) + [path(output)], check=True)
        print("PASS production ADC service wiring and confirmed-USB hardware error paths")


if __name__ == "__main__":
    main()
