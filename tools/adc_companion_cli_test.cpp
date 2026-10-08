#include "DeviceSettings.h"
#include "SmartUiCli.h"
#include "SmartUiCliSettings.h"
#include "SmartUiConsoleCommands.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>

// Exercise the real phone transport and all ADC command adapters together.
// Persistence and board hooks are simulated; no connected hardware is touched.
using namespace smartui;
static DeviceSettings settings;
static DeviceSettingsState state, persisted;
static DeviceSettingsCaps caps;
static SmartUiCli transport;
static bool writable = true, save_ok = true;
static float multiplier = 4.9f;
static unsigned saves, applies, samples, writes, checks;
#define CHECK(condition) do { ++checks; assert(condition); } while (0)

static DeviceSettingsState readState() { return state; }
static void writeState(const DeviceSettingsState& value) { ++writes; state = value; }
static bool saveState() { ++saves; if (!save_ok) return false; persisted = state; return true; }
static void applyState(bool battery_changed) {
  CHECK(battery_changed);
  ++applies;
  multiplier = state.adc_override ? state.adc_override : caps.adc_default;
}
static DeviceSettingsCaps readCaps() { return caps; }
static uint16_t readBattery() { ++samples; return 4100; }
static float readMultiplier() { return multiplier; }
static uint32_t now() { return 100; }
static bool uiCommand(const char* command, char* reply, size_t capacity) {
  return handleSmartUiSettingsCli(settings, command, reply, capacity, writable);
}
static bool execute(void*, const char* command, char* reply, size_t capacity) {
  if (strncmp(command, "ui ", 3) == 0) return uiCommand(command, reply, capacity);
  return handleSmartUiConsoleCommand(command, reply, capacity, uiCommand);
}
static void fresh() {
  settings = DeviceSettings{};
  state = DeviceSettingsState{};
  persisted = state;
  caps = DeviceSettingsCaps{};
  caps.adc = true;
  caps.adc_default = 4.9f;  // T114 factory coefficient, not a voltage.
  multiplier = caps.adc_default;
  saves = applies = samples = writes = 0;
  writable = save_ok = true;
  DeviceSettingsHooks hooks;
  hooks.read = readState; hooks.write = writeState; hooks.save = saveState;
  hooks.apply = applyState; hooks.caps = readCaps;
  hooks.batteryMilliVolts = readBattery; hooks.adcMultiplier = readMultiplier;
  hooks.millis = now;
  settings.begin(hooks);
  transport.resetSession();
}
static std::string call(const std::string& command) {
  uint8_t request[SmartUiCli::MAX_FRAME + 1] = {}, response[SmartUiCli::MAX_FRAME + 1] = {};
  const std::string prefixed = "a1|" + command;
  CHECK(prefixed.size() + 1 <= SmartUiCli::MAX_FRAME);
  request[0] = SmartUiCli::COMMAND;
  memcpy(request + 1, prefixed.data(), prefixed.size());
  response[SmartUiCli::MAX_FRAME] = 0xa5;
  bool arm_mode = true;
  const auto count = transport.handle(request, prefixed.size() + 1, response,
      SmartUiCli::MAX_FRAME, execute, nullptr, arm_mode);
  CHECK(count >= 4 && count <= SmartUiCli::MAX_FRAME);
  CHECK(response[0] == SmartUiCli::RESPONSE && memcmp(response + 1, "a1|", 3) == 0);
  CHECK(response[SmartUiCli::MAX_FRAME] == 0xa5 && !arm_mode);
  return std::string(reinterpret_cast<char*>(response + 4), count - 4);
}

int main() {
  for (const char* prefix : {"set adc ", "set adc.multiplier ", "ui adc set "}) {
    const bool native = prefix[0] == 'u';
    for (const char* value : {"3.675", "4", "4.11", "4.9", "5.000000", "6.125"}) {
      fresh();
      CHECK(call(std::string(prefix) + value) == (native ? "OK ui adc_set" : "OK adc_set"));
      CHECK(saves == 1 && applies == 1 && samples == 0);
      CHECK(persisted.adc_override == state.adc_override && multiplier == state.adc_override);
      // A second phone command still succeeds and uses the same committed data.
      CHECK(call("get adc.multiplier").find("> ") == 0);
      const unsigned writes_before_help = writes;
      CHECK(call("help adc") == "Unknown command");
      CHECK(writes == writes_before_help && saves == 1 && applies == 1 && samples == 0);
    }
    for (const char* value : {"0", "1", "3.2", "6.126", "999", "4294.967295"}) {
      fresh();
      CHECK(call(std::string(prefix) + value) == (native ? "ERR ui range" : "Error: range"));
      CHECK(saves == 0 && applies == 0 && samples == 0 && state.adc_override == 0);
      CHECK(call("get adc.multiplier") == "> 4.900000");
    }
    for (const char* value : {"NaN", "inf", "1e0", "4,9", "-4.9", "4.9foo"}) {
      fresh();
      CHECK(call(std::string(prefix) + value) == (native ? "ERR ui invalid" : "Error: invalid"));
      CHECK(saves == 0 && applies == 0 && state.adc_override == 0);
    }
    fresh(); save_ok = false;
    CHECK(call(std::string(prefix) + "5") == (native ? "ERR ui storage" : "Error: storage"));
    CHECK(saves == 1 && applies == 0 && state.adc_override == 0 && multiplier == 4.9f);
    save_ok = true;
    CHECK(call(std::string(prefix) + "5") == (native ? "OK ui adc_set" : "OK adc_set"));
    CHECK(saves == 2 && applies == 1 && persisted.adc_override == 5);
    fresh(); writable = false;
    CHECK(call(std::string(prefix) + "5") == (native ? "ERR ui readonly" : "Error: readonly"));
    CHECK(saves == 0 && applies == 0);
  }
  fresh();
  CHECK(call("set adc 5") == "OK adc_set");
  CHECK(call("adc reset") == "OK adc_reset");
  CHECK(multiplier == 4.9f && persisted.adc_override == 0 && saves == 2);
  std::printf("PASS %u full companion ADC transport/backend checks (T114 coefficient)\n", checks);
}
