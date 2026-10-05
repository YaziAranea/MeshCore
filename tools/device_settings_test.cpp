#include "DeviceSettings.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

using namespace smartui;
static DeviceSettingsState state, persisted;
static DeviceSettingsCaps caps;
static float multiplier;
static uint16_t battery;
static uint32_t now;
static bool save_ok;
static unsigned saves, applies, tests, battery_changes, checks;
static DeviceSettings service;
#define CHECK(x) do { ++checks; assert(x); } while (0)

static DeviceSettingsState read() { return state; }
static void write(const DeviceSettingsState& value) { state = value; }
static bool save() {
  ++saves;
  if (!save_ok) return false;
  persisted = state;
  return true;
}
static void apply(bool battery_changed) {
  ++applies;
  battery_changes += battery_changed;
  multiplier = state.adc_override ? state.adc_override : caps.adc_default;
}
static DeviceSettingsCaps capabilities() {
  DeviceSettingsCaps resolved = caps;
  resolved.effective_notify_mode = state.important_notify_mode;
  return resolved;
}
static uint16_t readBattery() { return battery; }
static float readAdc() { return multiplier; }
static uint32_t readMillis() { return now; }
static void testNotification() { ++tests; }
static void fresh(float factory = 4.9f) {
  state = DeviceSettingsState{};
  state.notify_mode = state.important_notify_mode = 7;
  caps = DeviceSettingsCaps{};
  caps.adc = caps.sound = caps.board_led = caps.unread_led = true;
  caps.vibration = caps.gps = caps.battery_protection = true;
  caps.adc_default = multiplier = factory;
  caps.melody_max = 30;
  battery = 4000;
  now = 100;
  save_ok = true;
  saves = applies = tests = battery_changes = 0;
  persisted = state;
  DeviceSettingsHooks hooks;
  hooks.read = read; hooks.write = write; hooks.save = save; hooks.apply = apply;
  hooks.caps = capabilities; hooks.batteryMilliVolts = readBattery;
  hooks.adcMultiplier = readAdc; hooks.millis = readMillis;
  hooks.testNotification = testNotification;
  service = DeviceSettings{};
  service.begin(hooks);
}
static std::string command(const char* text, bool allowed = true) {
  char reply[DeviceSettings::REPLY_CAPACITY];
  CHECK(service.handle(text, reply, sizeof(reply), allowed));
  CHECK(strlen(reply) < sizeof(reply));
  CHECK(strchr(reply, '\r') == nullptr && strchr(reply, '\n') == nullptr);
  return reply;
}
static uint32_t preview(const char* measured = "4120") {
  const auto reply = command((std::string("settings adc preview ") + measured).c_str());
  unsigned long token = 0;
  CHECK(sscanf(reply.c_str(), "OK settings adc_preview token=%lu", &token) == 1);
  CHECK(token != 0);
  return token;
}
static std::string applyToken(uint32_t token, bool allowed = true) {
  return command((std::string("settings adc apply ") + std::to_string(token)).c_str(), allowed);
}

int main() {
  static_assert(sizeof(DeviceSettingsState) <= 32, "Keep nRF52 stack snapshot bounded");
  fresh();
  CHECK(command("settings caps").find("display=0") != std::string::npos);
  CHECK(command("settings get").find("shutdown_mv=3200") != std::string::npos);
  CHECK(saves == 0 && applies == 0);
  char tiny[4] = {'x', 'x', 'x', 'x'};
  CHECK(service.handle("settings set gps 1", tiny, sizeof(tiny), true));
  CHECK(tiny[3] == 0 && saves == 0);
  CHECK(service.handle("settings test", nullptr, 0, true));
  CHECK(tests == 0);
  CHECK(!service.handle("settingsx get", tiny, sizeof(tiny), true));
  CHECK(!service.handle(nullptr, tiny, sizeof(tiny), true));

  for (float factory : {4.9f, 8.4f, 1.815f, 1.73f}) {
    fresh(factory);
    const auto token = preview();
    CHECK(multiplier == factory && state.adc_override == 0 && saves == 0 && applies == 0);
    CHECK(applyToken(token, false) == "ERR settings readonly");
    CHECK(multiplier == factory && saves == 0);
    CHECK(applyToken(token) == "OK settings adc_apply");
    CHECK(fabs(multiplier - factory * 1.03f) < 0.00001f && saves == 1 && applies == 1);
    CHECK(persisted.adc_override == multiplier && battery_changes == 1);
    CHECK(applyToken(token) == "ERR settings stale");
    CHECK(command("settings adc reset") == "OK settings adc_reset");
    CHECK(multiplier == factory && persisted.adc_override == 0);
  }
  fresh();
  auto token = preview();
  save_ok = false;
  CHECK(applyToken(token) == "ERR settings storage");
  CHECK(state.adc_override == 0 && multiplier == caps.adc_default && applies == 0);
  save_ok = true;
  CHECK(applyToken(token) == "OK settings adc_apply");
  token = preview();
  now += 60000;
  CHECK(applyToken(token) == "ERR settings stale");
  token = preview();
  state.adc_override = 4.8f;
  CHECK(applyToken(token) == "ERR settings stale");
  fresh(); token = preview(); multiplier = 4.8f;
  CHECK(applyToken(token) == "ERR settings stale");
  fresh(); now = UINT32_MAX - 999; token = preview(); now += 2000;
  CHECK(applyToken(token) == "OK settings adc_apply");
  fresh(); now = UINT32_MAX - 999; token = preview(); now += 60000;
  CHECK(applyToken(token) == "ERR settings stale");
  fresh(); token = preview(); command("settings set board_led 0");
  CHECK(applyToken(token) == "ERR settings stale");

  for (const char* text : {"0", "2499", "4501", "4294967296", "-1", "+4000", "4000x", "4000 1", "4000.0", "NaN", "Inf", ""}) {
    fresh();
    CHECK(command((std::string("settings adc preview ") + text).c_str()).find("ERR settings ") == 0);
    CHECK(saves == 0 && applies == 0 && state.adc_override == 0);
  }
  fresh(); battery = 0;
  CHECK(command("settings adc preview 4120") == "ERR settings measurement");
  fresh(); battery = 2000;
  CHECK(command("settings adc preview 4120") == "ERR settings range");
  fresh(); battery = 4000;
  CHECK(command("settings adc preview 3000").find("OK settings adc_preview") == 0);
  fresh(); battery = 3600;
  CHECK(command("settings adc preview 4500").find("OK settings adc_preview") == 0);

  const std::vector<std::string> valid = {
    "sound_quiet 1", "volume 1", "volume 10", "melody 0", "melody 30",
    "board_led 0", "unread_led 0", "vibration 0", "gps 1", "battery_protection 0", "muted 1"
  };
  for (const auto& setting : valid) {
    fresh(); save_ok = false;
    const auto initial = state;
    const auto request = "settings set " + setting;
    CHECK(command(request.c_str()) == "ERR settings storage");
    CHECK(memcmp(&state, &initial, sizeof(state)) == 0);
    CHECK(applies == 0 && battery_changes == 0);
    save_ok = true;
    CHECK(command(request.c_str()).find("OK settings set key=") == 0);
    CHECK(applies == 1 && saves == 2);
    CHECK(memcmp(&state, &persisted, sizeof(state)) == 0);
  }
  for (const char* setting : {"volume 0", "volume 11", "melody 31", "gps 2", "board_led 256", "unread_led -1", "muted 999999999999999", "bad 1", "gps 1 x", "gps ", " gps 1"}) {
    fresh();
    CHECK(command((std::string("settings set ") + setting).c_str()).find("ERR settings ") == 0);
    CHECK(saves == 0 && applies == 0);
  }
  fresh();
  command("settings set sound_quiet 1");
  CHECK((state.notify_mode & 2) == 0 && (state.important_notify_mode & 2) == 0 && state.sound_quiet == 1);
  command("settings set sound_quiet 0");
  CHECK((state.notify_mode & 2) && (state.important_notify_mode & 2) && !state.sound_quiet);
  command("settings set melody 12");
  CHECK(state.melody == 12 && state.melody_dm == 12 && state.melody_mention == 12 && state.melody_system == 12);
  command("settings set battery_protection 0");
  CHECK(command("settings get").find("shutdown_mv=2700") != std::string::npos);
  state.gps_source = 1; command("settings set gps 1");
  CHECK(state.gps == 1 && state.gps_source == 0);
  state.night_quiet = 1; command("settings set muted 0");
  CHECK(state.muted == 0 && state.night_quiet == 0);
  fresh();
  caps = DeviceSettingsCaps{};
  for (const char* setting : {"sound_quiet 0", "volume 5", "melody 3", "board_led 1", "unread_led 1", "vibration 1", "gps 1", "battery_protection 0"}) {
    CHECK(command((std::string("settings set ") + setting).c_str()) == "ERR settings unsupported");
  }
  CHECK(command("settings adc preview 4000") == "ERR settings unsupported");
  CHECK(command("settings adc reset") == "ERR settings unsupported");
  CHECK(command("settings test") == "ERR settings unsupported");
  CHECK(saves == 0 && applies == 0 && tests == 0);
  fresh();
  state.notify_mode = 7;
  state.important_notify_mode = 1;
  CHECK(command("settings get").find("sound_quiet=1") != std::string::npos);
  CHECK(command("settings get").find("vibration=0") != std::string::npos);
  command("settings set sound_quiet 0");
  CHECK(command("settings get").find("sound_quiet=0") != std::string::npos);
  fresh();
  CHECK(command("settings test", false) == "ERR settings readonly");
  CHECK(tests == 0);
  CHECK(command("settings test") == "OK settings test");
  CHECK(tests == 1 && saves == 0 && applies == 0);
  DeviceSettings unavailable;
  char reply[DeviceSettings::REPLY_CAPACITY];
  CHECK(unavailable.handle("settings get", reply, sizeof(reply), true));
  CHECK(strcmp(reply, "ERR settings unavailable") == 0);
  printf("PASS %u production DeviceSettings transaction/protocol checks\n", checks);
}
