#include "DeviceSettings.h"
#include "SmartUiCliSettings.h"
#include <helpers/AdcCalibration.h>
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <limits>
#include <string>
#include <vector>

using namespace smartui;
static DeviceSettingsState state, persisted;
static DeviceSettingsCaps caps;
static float multiplier;
static uint16_t battery;
static uint32_t now;
static bool calibration_source_enabled, calibration_source_valid;
static uint16_t calibration_battery;
static float calibration_multiplier;
static uint32_t calibration_age_ms;
static bool save_ok;
static unsigned writes, saves, applies, tests, battery_changes, checks, melody_reads;
static const char* melody_name;
static unsigned bridge_calls;
static bool bridge_ok;
static unsigned adc_commits, adc_service_calls;
static bool adc_service_active;
static DeviceSettings service;
#define CHECK(x) do { ++checks; assert(x); } while (0)

static DeviceSettingsState read() { return state; }
static void write(const DeviceSettingsState& value) { ++writes; state = value; }
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
static bool readCalibrationBattery(uint16_t& millivolts, float& sample_multiplier,
                                   uint32_t& age_ms) {
  if (!calibration_source_valid) return false;
  millivolts = calibration_battery;
  sample_multiplier = calibration_multiplier;
  age_ms = calibration_age_ms;
  return true;
}
static float readAdc() { return multiplier; }
static uint32_t readMillis() { return now; }
static void testNotification() { ++tests; }
static const char* melodyName(uint8_t id) { ++melody_reads; CHECK(id <= caps.melody_max); return melody_name; }
static bool setToneBridge(bool enabled) {
  ++bridge_calls;
  if (!bridge_ok) return false;
  state.bridge = enabled ? 1 : 0;
  persisted = state;
  return true;
}
static bool pinAllowed(const char* key, int pin) {
  return pin == 35 || pin == 36 || (strcmp(key, "vibe_pin") == 0 && pin == -1);
}
static void pinOptions(const char* key, char* out, size_t capacity) {
  snprintf(out, capacity, "%s", strcmp(key, "vibe_pin") == 0 ? "-1,35,36" : "35,36");
}
static void adcCommitted() { ++adc_commits; adc_service_active = false; }
static void adcService(const char* action, char* reply, size_t capacity, bool writable) {
  ++adc_service_calls;
  if (strcmp(action, "start") == 0) { CHECK(writable); adc_service_active = true; }
  if (strcmp(action, "stop") == 0) adc_service_active = false;
  snprintf(reply, capacity,
      "OK settings adc_service supported=1 active=%u remaining_ms=%u external=1",
      adc_service_active ? 1U : 0U, adc_service_active ? 120000U : 0U);
}
static void fresh(float factory = 4.9f, bool names = true, bool bridge_hook = true) {
  state = DeviceSettingsState{};
  state.notify_mode = state.important_notify_mode = 7;
  caps = DeviceSettingsCaps{};
  caps.adc = caps.sound = caps.board_led = caps.unread_led = true;
  caps.vibration = caps.gps = caps.battery_protection = true;
  caps.agc_reset = caps.fem_lna = caps.fem_pa = true;
  caps.adc_default = multiplier = factory;
  caps.melody_max = 30;
  battery = 4000;
  now = 100;
  calibration_source_enabled = calibration_source_valid = false;
  calibration_battery = battery;
  calibration_multiplier = multiplier;
  calibration_age_ms = 0;
  save_ok = true;
  writes = saves = applies = tests = battery_changes = melody_reads = 0;
  melody_name = "Test tone";
  bridge_calls = 0; bridge_ok = true;
  adc_commits = adc_service_calls = 0; adc_service_active = false;
  persisted = state;
  DeviceSettingsHooks hooks;
  hooks.read = read; hooks.write = write; hooks.save = save; hooks.apply = apply;
  hooks.caps = capabilities; hooks.batteryMilliVolts = readBattery;
  hooks.batteryCalibrationSample = calibration_source_enabled ? readCalibrationBattery : nullptr;
  hooks.adcMultiplier = readAdc; hooks.millis = readMillis;
  hooks.testNotification = testNotification;
  hooks.melodyName = names ? melodyName : nullptr;
  hooks.setToneBridge = bridge_hook ? setToneBridge : nullptr;
  hooks.adcCommitted = adcCommitted;
  hooks.pinAllowed = pinAllowed;
  hooks.pinOptions = pinOptions;
  service = DeviceSettings{};
  service.begin(hooks);
}
static std::string command(const char* text, bool allowed = true) {
  struct {
    char reply[DeviceSettings::REPLY_CAPACITY];
    char guard[8];
  } output;
  memset(&output, '!', sizeof(output));
  CHECK(service.handle(text, output.reply, sizeof(output.reply), allowed));
  CHECK(memchr(output.reply, 0, sizeof(output.reply)) != nullptr);
  CHECK(memcmp(output.guard, "!!!!!!!!", sizeof(output.guard)) == 0);
  for (const unsigned char* p = reinterpret_cast<const unsigned char*>(output.reply); *p; ++p)
    CHECK(*p >= 0x20 && *p <= 0x7e);
  return output.reply;
}
static std::string cliCommand(const char* text, bool allowed = true) {
  struct {
    char reply[SMARTUI_CLI_TEXT_MAX + 1];
    char guard[8];
  } output;
  memset(&output, '!', sizeof(output));
  CHECK(handleSmartUiSettingsCli(service, text, output.reply,
                                 sizeof(output.reply), allowed));
  const char* end = static_cast<const char*>(
      memchr(output.reply, 0, sizeof(output.reply)));
  CHECK(end != nullptr);
  CHECK(static_cast<size_t>(end - output.reply) <= SMARTUI_CLI_TEXT_MAX);
  CHECK(memcmp(output.guard, "!!!!!!!!", sizeof(output.guard)) == 0);
  for (const unsigned char* p =
           reinterpret_cast<const unsigned char*>(output.reply); *p; ++p)
    CHECK(*p >= 0x20 && *p <= 0x7e);
  return output.reply;
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
  static_assert(sizeof(DeviceSettingsState) <= 64, "Keep nRF52 stack snapshot bounded");
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

  CHECK(command("settings adc service", false) ==
        "OK settings adc_service supported=0 active=0 remaining_ms=0 external=0");
  CHECK(command("settings adc service stop", false).find("active=0") != std::string::npos);
  CHECK(command("settings adc service start") == "ERR settings unsupported");
  CHECK(command("settings adc service start", false) == "ERR settings readonly");
  CHECK(cliCommand("ui caps adc_service") == "OK ui caps key=adc_service value=0");
  CHECK(cliCommand("ui adc service", false).find("OK ui adc_service") == 0);
  CHECK(cliCommand("ui adc service stop", false).find("active=0") != std::string::npos);
  CHECK(cliCommand("ui adc service start") == "ERR ui unsupported");
  CHECK(cliCommand("ui adc service unknown") == "ERR ui invalid");
  CHECK(command("settings adc service unknown") == "ERR settings invalid");

  {
    DeviceSettingsHooks hooks;
    hooks.read = read; hooks.write = write; hooks.save = save; hooks.apply = apply;
    hooks.caps = capabilities; hooks.batteryMilliVolts = readBattery;
    hooks.adcMultiplier = readAdc; hooks.millis = readMillis;
    hooks.adcService = adcService; hooks.adcCommitted = adcCommitted;
    caps.adc_service = true;
    service.begin(hooks);
    CHECK(command("settings adc service start", false) == "ERR settings readonly");
    CHECK(adc_service_calls == 0);
    CHECK(command("settings adc service start").find("active=1") != std::string::npos);
    CHECK(cliCommand("ui adc service", false).find("active=1") != std::string::npos);
    CHECK(cliCommand("ui caps adc_service") == "OK ui caps key=adc_service value=1");
    CHECK(adc_service_active && saves == 0);
    auto token = preview();
    save_ok = false;
    CHECK(applyToken(token) == "ERR settings storage");
    CHECK(adc_service_active && adc_commits == 0);
    save_ok = true;
    CHECK(applyToken(token) == "OK settings adc_apply");
    CHECK(!adc_service_active && adc_commits == 1);
    CHECK(cliCommand("ui adc service start").find("active=1") != std::string::npos);
    save_ok = false;
    CHECK(cliCommand("ui adc reset") == "ERR ui storage");
    CHECK(adc_service_active && adc_commits == 1);
    save_ok = true;
    CHECK(cliCommand("ui adc reset") == "OK ui adc_reset");
    CHECK(!adc_service_active && adc_commits == 2);
    CHECK(cliCommand("ui adc service start").find("active=1") != std::string::npos);
    CHECK(cliCommand("ui adc service stop", false).find("active=0") != std::string::npos);
    CHECK(!adc_service_active && adc_commits == 2);
  }

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

  // A transport-disturbed board uses only a recent battery-only sample made
  // with the same multiplier. It never falls back to the live USB reading.
  fresh(1.815f); calibration_source_enabled = calibration_source_valid = true;
  multiplier = state.adc_override = 1.97f;
  calibration_battery = 3100; calibration_multiplier = multiplier;
  calibration_age_ms = 0; battery = 4400;
  {
    DeviceSettingsHooks hooks;
    hooks.read = read; hooks.write = write; hooks.save = save; hooks.apply = apply;
    hooks.caps = capabilities; hooks.batteryMilliVolts = readBattery;
    hooks.batteryCalibrationSample = readCalibrationBattery;
    hooks.adcMultiplier = readAdc; hooks.millis = readMillis;
    service = DeviceSettings{}; service.begin(hooks);
  }
  const auto cached_reply = command("settings adc preview 3320");
  unsigned long cached_token = 0;
  CHECK(sscanf(cached_reply.c_str(),
               "OK settings adc_preview token=%lu sampled_mv=3100 measured_mv=3320 multiplier=2.109806",
               &cached_token) == 1);
  CHECK(cached_token != 0);
  calibration_age_ms = 120000U;
  CHECK(command("settings adc preview 3320").find("sampled_mv=3100") != std::string::npos);
  calibration_source_valid = false;
  CHECK(command("settings adc preview 3320") == "ERR settings source");
  CHECK(command("api adc preview 3320") == "ERR api source");
  CHECK(applyToken(static_cast<uint32_t>(cached_token)) == "ERR settings stale");
  calibration_source_valid = true; calibration_age_ms = 120001U;
  CHECK(command("settings adc preview 3320") == "ERR settings source");
  calibration_age_ms = 0; calibration_multiplier = multiplier + 0.01f;
  CHECK(command("settings adc preview 3320") == "ERR settings source");

  // The real ProMicro cache ignores USB-disturbed samples, invalidates after a
  // multiplier change and reports wrap-safe age. This path needs no display.
  mesh::BatteryCalibrationSampleCache promicro_cache;
  uint16_t cached_mv = 0; float cached_multiplier = 0.0f; uint32_t cached_age = 0;
  promicro_cache.capture(3100, 1.815f, UINT32_MAX - 49U, false);
  promicro_cache.capture(4400, 1.815f, UINT32_MAX - 20U, true);
  CHECK(promicro_cache.read(50U, cached_mv, cached_multiplier, cached_age));
  CHECK(cached_mv == 3100 && cached_multiplier == 1.815f && cached_age == 100U);
  promicro_cache.invalidate();
  CHECK(!promicro_cache.read(51U, cached_mv, cached_multiplier, cached_age));

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

  // Legacy keys remain stable; 0.14 adds one optional service capability.
  fresh(4.0f);
  const std::string legacy_caps = "OK settings caps v=1 adc=1 sound=1 board_led=1 unread_led=1 vibration=1 gps=1 battery_protection=1 display=0 melody_max=30 adc_min=3.000000 adc_max=5.000000 adc_service=0";
  const std::string legacy_get = "OK settings get battery_mv=4000 adc_multiplier=4.000000 adc_default=4.000000 sound_quiet=0 volume=10 melody=0 board_led=1 unread_led=1 vibration=1 gps=0 battery_protection=1 shutdown_mv=3200 muted=0";
  CHECK(command("settings caps") == legacy_caps);
  CHECK(command("settings get") == legacy_get);
  CHECK(command("api caps", false) == "OK api " + legacy_caps.substr(12) +
        " agc_reset=1 fem_lna=1 fem_pa=1 bridge=0 melody_names=1");
  CHECK(command("api get", false) == "OK api " + legacy_get.substr(12) +
        " agc_reset=0 fem_lna=0 fem_pa=0 bridge=0");
  CHECK(command("settings set agc_reset 1") == "OK settings set key=agc_reset value=1");
  CHECK(command("settings set fem_lna 1") == "OK settings set key=fem_lna value=1");
  CHECK(command("settings set fem_pa 1") == "OK settings set key=fem_pa value=1");
  CHECK(writes == 3 && saves == 3 && applies == 3);
  fresh();
  CHECK(!service.handle("apix get", reply, sizeof(reply), true));
  CHECK(!service.handle("ap", reply, sizeof(reply), true));
  CHECK(command("api") == "ERR api invalid");
  CHECK(command("api what") == "ERR api invalid");
  CHECK(command(("api set " + std::string(120, 'a')).c_str()) == "ERR api invalid");
  CHECK(service.handle("api set gps 1", tiny, sizeof(tiny), true));
  CHECK(tiny[3] == 0 && saves == 0);
  CHECK(service.handle("api test", nullptr, 0, true));
  CHECK(tests == 0);
  CHECK(unavailable.handle("api get", reply, sizeof(reply), true));
  CHECK(strcmp(reply, "ERR api unavailable") == 0);

  // Existing API aliases preserve validation, mutation, and side effects.
  for (const auto& setting : valid) {
    fresh();
    const auto legacy = command(("settings set " + setting).c_str());
    const auto expected = state;
    fresh();
    CHECK(command(("api set " + setting).c_str()) == "OK api " + legacy.substr(12));
    CHECK(memcmp(&state, &expected, sizeof(state)) == 0);
    CHECK(saves == 1 && applies == 1);
  }
  for (const char* key : {"agc_reset", "fem_lna", "fem_pa"}) {
    fresh();
    state.profile = 7;
    const auto initial = state;
    const auto request = std::string("api set ") + key + " 1";
    CHECK(command(request.c_str(), false) == "ERR api readonly");
    CHECK(writes == 0 && saves == 0 && applies == 0);
    save_ok = false;
    CHECK(command(request.c_str()) == "ERR api storage");
    CHECK(memcmp(&state, &initial, sizeof(state)) == 0);
    CHECK(writes == 2 && saves == 1 && applies == 0 && battery_changes == 0);
    save_ok = true;
    CHECK(command(request.c_str()) == std::string("OK api set key=") + key + " value=1");
    CHECK(state.profile == 0 && saves == 2 && applies == 1 && battery_changes == 0);
    CHECK(memcmp(&state, &persisted, sizeof(state)) == 0);
    CHECK(state.agc_reset == (strcmp(key, "agc_reset") == 0));
    CHECK(state.fem_lna == (strcmp(key, "fem_lna") == 0));
    CHECK(state.fem_pa == (strcmp(key, "fem_pa") == 0));
    CHECK(command("api get").find(std::string(key) + "=1") != std::string::npos);
    CHECK(command((std::string("api set ") + key + " 0").c_str()) ==
          std::string("OK api set key=") + key + " value=0");
  }
  for (const char* key : {"agc_reset", "fem_lna", "fem_pa", "gps", "melody", "volume"}) {
    for (const char* value : {"256", "257", "4294967295", "4294967296", "-1", "+1", "1x", "1 0", "1.0", "", " 1"}) {
      fresh();
      const auto initial = state;
      CHECK(command((std::string("api set ") + key + " " + value).c_str()).find("ERR api ") == 0);
      CHECK(writes == 0 && saves == 0 && applies == 0);
      CHECK(memcmp(&state, &initial, sizeof(state)) == 0);
    }
  }
  fresh();
  caps.agc_reset = caps.fem_lna = caps.fem_pa = false;
  for (const char* key : {"agc_reset", "fem_lna", "fem_pa", "bridge"}) {
    CHECK(command((std::string("api set ") + key + " 1").c_str()) == "ERR api unsupported");
  }
  CHECK(writes == 0 && saves == 0 && applies == 0);

  // Melody labels are bounded byte strings represented as ASCII-safe hex.
  fresh();
  CHECK(command("api melody 0", false) == "OK api melody id=0 name_hex=5465737420746f6e65");
  melody_name = "\xd0\x97\xd0\xb2\xd1\x83\xd0\xba";
  CHECK(command("api melody 30") == "OK api melody id=30 name_hex=d097d0b2d183d0ba");
  CHECK(saves == 0 && applies == 0 && melody_reads == 2);
  CHECK(command("api melody 31") == "ERR api range");
  CHECK(command("api melody 256") == "ERR api range");
  CHECK(command("api melody 4294967296") == "ERR api invalid");
  CHECK(command("api melody -1") == "ERR api invalid");
  CHECK(command("api melody 0 1") == "ERR api invalid");
  CHECK(melody_reads == 2);
  const std::string maximum_name(DeviceSettings::MELODY_NAME_MAX, 'A');
  melody_name = maximum_name.c_str();
  CHECK(command("api melody 1").size() == strlen("OK api melody id=1 name_hex=") + 2 * maximum_name.size());
  const std::string oversized_name(DeviceSettings::MELODY_NAME_MAX + 1, 'A');
  melody_name = oversized_name.c_str();
  CHECK(command("api melody 0") == "ERR api internal");
  melody_name = "";
  CHECK(command("api melody 0") == "ERR api internal");
  melody_name = nullptr;
  CHECK(command("api melody 0") == "ERR api internal");
  caps.sound = false;
  CHECK(command("api melody 0") == "ERR api unsupported");
  CHECK(command("api caps").find("melody_names=0") != std::string::npos);
  fresh(4.9f, false);
  CHECK(command("api melody 0") == "ERR api unsupported");
  CHECK(command("api caps").find("sound=1") != std::string::npos);
  CHECK(command("api caps").find("melody_names=0") != std::string::npos);
  CHECK(melody_reads == 0);

  // The bridge owns a separate checked pin transaction, never the generic
  // preferences writer/apply hooks. Invalid or idempotent calls do no work.
  fresh(); caps.bridge = true;
  CHECK(command("api caps").find("bridge=1") != std::string::npos);
  CHECK(command("settings set bridge 1", false) == "ERR settings readonly");
  CHECK(command("api set bridge 1", false) == "ERR api readonly");
  CHECK(bridge_calls == 0);
  for (const char* value : {"2", "256", "4294967295", "4294967296", "-1", "+1", "1x", "1 0", "", " 1"}) {
    CHECK(command((std::string("api set bridge ") + value).c_str()).find("ERR api ") == 0);
  }
  CHECK(bridge_calls == 0 && writes == 0 && saves == 0 && applies == 0);
  CHECK(command("api set bridge 0") == "OK api set key=bridge value=0" && bridge_calls == 0);
  token = preview();
  bridge_ok = false;
  CHECK(command("api set bridge 1") == "ERR api storage");
  CHECK(state.bridge == 0 && bridge_calls == 1 && applies == 0 && saves == 0);
  CHECK(applyToken(token) == "OK settings adc_apply");
  token = preview(); bridge_ok = true;
  const auto writes_before_bridge = writes, saves_before_bridge = saves, applies_before_bridge = applies;
  CHECK(command("api set bridge 1") == "OK api set key=bridge value=1");
  CHECK(state.bridge == 1 && persisted.bridge == 1 && bridge_calls == 2);
  CHECK(writes == writes_before_bridge && saves == saves_before_bridge && applies == applies_before_bridge);
  CHECK(command("api get").find("bridge=1") != std::string::npos);
  CHECK(applyToken(token) == "ERR settings stale");
  token = preview();
  CHECK(command("api set bridge 1") == "OK api set key=bridge value=1" && bridge_calls == 2);
  CHECK(applyToken(token) == "OK settings adc_apply");
  CHECK(command("api set bridge 0") == "OK api set key=bridge value=0");
  CHECK(state.bridge == 0 && bridge_calls == 3);
  fresh(4.9f, true, false); caps.bridge = true;
  CHECK(command("api caps").find("bridge=0") != std::string::npos);
  CHECK(command("api set bridge 1") == "ERR api unsupported" && bridge_calls == 0);

  // Reset invalidates both entry points, but does not recycle the next token.
  fresh();
  token = preview();
  service.resetSession();
  CHECK(applyToken(token) == "ERR settings stale");
  const auto next_token = preview();
  CHECK(next_token != token && next_token > token);
  service.resetSession();
  CHECK(command((std::string("api adc apply ") + std::to_string(next_token)).c_str()) == "ERR api stale");
  unsigned long api_token = 0;
  CHECK(sscanf(command("api adc preview 4120").c_str(), "OK api adc_preview token=%lu", &api_token) == 1);
  CHECK(api_token > next_token);
  save_ok = false;
  CHECK(command((std::string("api adc apply ") + std::to_string(api_token)).c_str()) == "ERR api storage");
  CHECK(state.adc_override == 0 && applies == 0);
  save_ok = true;
  CHECK(command((std::string("api adc apply ") + std::to_string(api_token)).c_str()) == "OK api adc_apply");
  CHECK(command("api adc reset") == "OK api adc_reset");
  CHECK(command("api test", false) == "ERR api readonly");
  CHECK(command("api test") == "OK api test");
  CHECK(tests == 1);
  token = preview();
  CHECK(command("api set fem_lna 1") == "OK api set key=fem_lna value=1");
  CHECK(applyToken(token) == "ERR settings stale");

  // CMD66-facing UI facade exposes one bounded field at a time while keeping
  // the existing transaction, capability and ADC-source guarantees.
  fresh(4.9f);
  CHECK(cliCommand("ui caps v") == "OK ui caps key=v value=1");
  CHECK(cliCommand("ui caps fem_lna") == "OK ui caps key=fem_lna value=1");
  CHECK(cliCommand("ui caps adc_min") == "OK ui caps key=adc_min value=3.675000");
  CHECK(cliCommand("ui get battery_mv") == "OK ui get key=battery_mv value=4000");
  CHECK(cliCommand("ui get fem_lna") == "OK ui get key=fem_lna value=0");
  CHECK(saves == 0 && applies == 0);
  CHECK(cliCommand("ui caps") == "ERR ui invalid");
  CHECK(cliCommand("ui caps unknown") == "ERR ui invalid");
  CHECK(cliCommand("ui get unknown") == "ERR ui invalid");
  CHECK(cliCommand("ui get battery_mv extra") == "ERR ui invalid");
  CHECK(cliCommand("ui set unknown 1") == "ERR ui invalid");
  CHECK(cliCommand("ui set fem_lna -1") == "ERR ui invalid");
  CHECK(cliCommand("ui set fem_lna 1 extra") == "ERR ui invalid");
  CHECK(saves == 0 && applies == 0);

  save_ok = false;
  CHECK(cliCommand("ui set fem_lna 1") == "ERR ui storage");
  CHECK(state.fem_lna == 0 && persisted.fem_lna == 0 && applies == 0);
  save_ok = true;
  CHECK(cliCommand("ui set fem_lna 1", false) == "ERR ui readonly");
  CHECK(state.fem_lna == 0 && saves == 1 && applies == 0);
  CHECK(cliCommand("ui set fem_lna 1") == "OK ui set key=fem_lna value=1");
  CHECK(state.fem_lna == 1 && persisted.fem_lna == 1 && applies == 1);
  caps.fem_lna = false;
  CHECK(cliCommand("ui set fem_lna 0") == "ERR ui unsupported");
  CHECK(state.fem_lna == 1);
  CHECK(cliCommand("ui test", false) == "ERR ui readonly");
  CHECK(tests == 0);
  CHECK(cliCommand("ui test") == "OK ui test");
  CHECK(tests == 1);
  CHECK(cliCommand("ui test now") == "ERR ui invalid");

  fresh(1.815f); calibration_source_enabled = calibration_source_valid = true;
  multiplier = state.adc_override = 1.97f;
  calibration_battery = 3100; calibration_multiplier = multiplier;
  calibration_age_ms = 0; battery = 4400;
  {
    DeviceSettingsHooks hooks;
    hooks.read = read; hooks.write = write; hooks.save = save; hooks.apply = apply;
    hooks.caps = capabilities; hooks.batteryMilliVolts = readBattery;
    hooks.batteryCalibrationSample = readCalibrationBattery;
    hooks.adcMultiplier = readAdc; hooks.millis = readMillis;
    hooks.melodyName = melodyName;
    service = DeviceSettings{}; service.begin(hooks);
  }
  const std::string cli_preview = cliCommand("ui adc preview 3320");
  unsigned long cli_token = 0;
  CHECK(sscanf(cli_preview.c_str(),
      "OK ui adc_preview token=%lu sampled_mv=3100 measured_mv=3320 multiplier=2.109806",
      &cli_token) == 1);
  CHECK(cli_token != 0 && saves == 0 && applies == 0);
  CHECK(cliCommand(("ui adc apply " + std::to_string(cli_token)).c_str(), false) ==
        "ERR ui readonly");
  CHECK(cliCommand(("ui adc apply " + std::to_string(cli_token)).c_str()) ==
        "OK ui adc_apply");
  CHECK(saves == 1 && applies == 1);
  CHECK(cliCommand("ui adc reset") == "OK ui adc_reset");
  calibration_source_valid = false;
  CHECK(cliCommand("ui adc preview 3320") == "ERR ui source");
  for (const char* invalid : {"ui adc preview", "ui adc preview -1",
                              "ui adc apply 1 2", "ui adc reset 1",
                              "ui melody -1", "ui melody 0 1"})
    CHECK(cliCommand(invalid) == "ERR ui invalid");

  fresh();
  CHECK(cliCommand("ui melody 0") ==
        "OK ui melody id=0 name_hex=5465737420746f6e65");
  const std::string maximum_cli_name(DeviceSettings::MELODY_NAME_MAX, 'A');
  melody_name = maximum_cli_name.c_str();
  CHECK(cliCommand("ui melody 1").size() == 155);
  caps.melody_max = 255;
  CHECK(cliCommand("ui melody 255") == "ERR ui internal");
  char short_reply[32];
  const auto before_short = state;
  CHECK(handleSmartUiSettingsCli(service, "ui set fem_lna 1", short_reply,
                                 sizeof(short_reply), true));
  CHECK(strcmp(short_reply, "ERR ui buffer") == 0);
  CHECK(memcmp(&state, &before_short, sizeof(state)) == 0 && saves == 0);
  CHECK(!handleSmartUiSettingsCli(service, "ui hello", short_reply,
                                  sizeof(short_reply), true));
  CHECK(!handleSmartUiSettingsCli(service, "api get", short_reply,
                                  sizeof(short_reply), true));
  CHECK(cliCommand(("ui get " + std::string(150, 'a')).c_str()) ==
        "ERR ui invalid");
  std::string non_ascii = "ui get battery_mv";
  non_ascii.push_back(static_cast<char>(0x80));
  CHECK(cliCommand(non_ascii.c_str()) == "ERR ui invalid");

  // Extended per-key records keep both transports bounded instead of growing
  // the legacy aggregate snapshot. Hardware ownership is checked before save.
  fresh();
  caps.notify_pins = caps.tone_8bit = caps.high_drive = caps.resonance = true;
  caps.separate_melodies = caps.display = caps.colors = caps.phone_gps = caps.profiles = true;
  caps.font_count = 5; caps.theme_count = 3; caps.notify_mask = 7;
  CHECK(command("settings caps schema") == "OK settings caps key=schema value=1");
  CHECK(cliCommand("ui caps schema") == "OK ui caps key=schema value=1");
  CHECK(cliCommand("ui get led_pin") == "OK ui get key=led_pin value=-1");
  CHECK(cliCommand("ui get tone_pin") == "OK ui get key=tone_pin value=-1");
  CHECK(cliCommand("ui schema tone_pin") ==
      "OK ui schema key=tone_pin supported=1 min=0 max=127 step=1 options=35,36");
  CHECK(cliCommand("ui schema resonance_hz") ==
      "OK ui schema key=resonance_hz supported=1 min=1800 max=4200 step=400 options=-");
  CHECK(cliCommand("ui schema notify_mode").find("options=0,1,2,3,4,5,6,7") != std::string::npos);
  for (const char* entry : {"notify_mode 3", "important_notify_mode 7", "led_pin 35",
       "tone_pin 36", "vibe_pin -1", "melody_dm 3", "melody_mention 4", "melody_system 5",
       "tone_8bit 1", "high_drive 1", "resonance_hz 4200", "offline_dm_led 0", "ble_dm_led 0",
       "msg_popup 0", "ui_font 4", "ui_theme 2", "ui_top_color 5", "ui_bottom_color 0",
       "backlight_timeout 2", "gps_source 1", "gps_interval 86400", "advert_location 1"}) {
    std::string text(entry);
    const auto split = text.find(' ');
    const std::string key = text.substr(0, split), value = text.substr(split + 1);
    CHECK(cliCommand(("ui set " + text).c_str()) == "OK ui set key=" + key + " value=" + value);
    CHECK(cliCommand(("ui get " + key).c_str()) == "OK ui get key=" + key + " value=" + value);
    CHECK(command(("settings get " + key).c_str()) == "OK settings get key=" + key + " value=" + value);
  }
  unsigned before_saves = saves;
  const DeviceSettingsState before_extended = state;
  for (const char* entry : {"led_pin 9", "tone_pin 9", "vibe_pin 9"})
    CHECK(cliCommand((std::string("ui set ") + entry).c_str()) == "ERR ui pin_conflict");
  for (const char* entry : {"resonance_hz 1801", "resonance_hz 4400", "ui_font 5", "ui_theme 3",
       "ui_top_color 6", "backlight_timeout 3", "gps_interval 86401", "profile 4", "notify_mode 8"})
    CHECK(cliCommand((std::string("ui set ") + entry).c_str()) == "ERR ui range");
  CHECK(saves == before_saves && memcmp(&state, &before_extended, sizeof(state)) == 0);
  CHECK(cliCommand("ui set led_pin 35", false) == "ERR ui readonly");
  save_ok = false;
  CHECK(cliCommand("ui set ui_theme 1") == "ERR ui storage");
  CHECK(memcmp(&state, &before_extended, sizeof(state)) == 0);
  save_ok = true;
  CHECK(cliCommand("ui set profile 3") == "OK ui set key=profile value=3");
  CHECK(state.profile == 3 && state.muted == 1 && state.board_led == 0 && state.backlight_timeout == 0);
  CHECK(cliCommand("ui set profile 2") == "OK ui set key=profile value=2");
  CHECK(state.profile == 2 && state.muted == 0 && state.notify_mode == 7 && state.board_led == 1);
  caps.notify_mask = 3;
  CHECK(cliCommand("ui get notify_mode") == "OK ui get key=notify_mode value=3");
  CHECK(state.notify_mode == 7);  // Read is effective, never a persistence mutation.
  CHECK(cliCommand("ui set notify_mode 4") == "ERR ui range");
  caps.phone_gps = false;
  CHECK(cliCommand("ui set gps_source 1") == "ERR ui range");
  caps.separate_melodies = false;
  CHECK(cliCommand("ui set melody_dm 2") == "ERR ui unsupported");
  CHECK(cliCommand("ui set melody_system 2") == "OK ui set key=melody_system value=2");
  CHECK(state.melody == 2 && state.melody_dm == 2 && state.melody_mention == 2 && state.melody_system == 2);
  caps.display = false;
  CHECK(cliCommand("ui set ui_font 1") == "ERR ui unsupported");
  CHECK(cliCommand("ui schema ui_font").find("supported=0") != std::string::npos);

  // Worst-case numeric widths remain complete and within the 480-byte reply.
  fresh();
  battery = UINT16_MAX;
  caps.adc_default = multiplier = std::numeric_limits<float>::max() / 2;
  caps.melody_max = UINT8_MAX;
  state.volume = state.melody_system = state.board_led = state.unread_led = UINT8_MAX;
  state.gps = state.battery_protection = state.muted = UINT8_MAX;
  state.agc_reset = state.fem_lna = state.fem_pa = UINT8_MAX;
  CHECK(command("api caps").find("melody_names=1") != std::string::npos);
  CHECK(command("api get").find("agc_reset=255 fem_lna=255 fem_pa=255") != std::string::npos);
  printf("PASS %u production DeviceSettings transaction/protocol checks\n", checks);
}
