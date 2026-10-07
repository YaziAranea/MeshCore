#include "DeviceSettings.h"
#include "SmartUiCliSettings.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>

using namespace smartui;
static DeviceSettings settings;
static DeviceSettingsState state, persisted;
static DeviceSettingsCaps caps;
static float multiplier;
static bool save_ok, source_ok, service_active;
static unsigned writes, saves, applies, adc_commits, samples, checks;
#define CHECK(x) do { ++checks; assert(x); } while (0)

static DeviceSettingsState read() { return state; }
static void write(const DeviceSettingsState& value) { state = value; ++writes; }
static bool save() { ++saves; if (!save_ok) return false; persisted = state; return true; }
static void apply(bool battery_changed) {
  CHECK(battery_changed);
  ++applies;
  multiplier = state.adc_override ? state.adc_override : caps.adc_default;
}
static DeviceSettingsCaps capabilities() { return caps; }
static float adc() { return multiplier; }
static uint16_t battery() { ++samples; return 4000; }
static bool sample(uint16_t& mv, float& factor, uint32_t& age) {
  ++samples;
  mv = 4000; factor = multiplier; age = 0;
  return source_ok;
}
static uint32_t clockMillis() { return 100; }
static void committed() { ++adc_commits; service_active = false; }
static void fresh(float factory = 1.815f) {
  state = DeviceSettingsState{}; state.profile = 3;
  persisted = state;
  caps = DeviceSettingsCaps{}; caps.adc = true; caps.adc_default = factory;
  multiplier = factory; save_ok = true; source_ok = false; service_active = true;
  writes = saves = applies = adc_commits = samples = 0;
  DeviceSettingsHooks hooks;
  hooks.read = read; hooks.write = write; hooks.save = save; hooks.apply = apply;
  hooks.caps = capabilities; hooks.adcMultiplier = adc; hooks.batteryMilliVolts = battery;
  hooks.batteryCalibrationSample = sample; hooks.millis = clockMillis;
  hooks.adcCommitted = committed;
  settings = DeviceSettings{}; settings.begin(hooks);
}
static std::string command(const std::string& text, bool writable = true, bool cli = false) {
  char reply[DeviceSettings::REPLY_CAPACITY] = {};
  CHECK(cli ? handleSmartUiSettingsCli(settings, text.c_str(), reply, sizeof(reply), writable) :
              settings.handle(text.c_str(), reply, sizeof(reply), writable));
  CHECK(std::strlen(reply) < (cli ? SMARTUI_CLI_TEXT_MAX + 1U : sizeof(reply)));
  return reply;
}
static std::string set(const char* value, bool cli = false, bool writable = true) {
  return command(std::string(cli ? "ui adc set " : "settings adc set ") + value, writable, cli);
}
static uint32_t preview() {
  source_ok = true;
  const auto response = command("settings adc preview 4000");
  unsigned long token = 0;
  CHECK(std::sscanf(response.c_str(), "OK settings adc_preview token=%lu", &token) == 1);
  CHECK(token != 0);
  return token;
}

int main() {
  for (bool cli : {false, true}) {
    const std::string ns = cli ? "ui" : "settings";
    fresh();
    CHECK(command(ns + " adc manual", false, cli) == "OK " + ns + " adc_manual supported=1");
    CHECK(saves == 0 && writes == 0 && applies == 0 && samples == 0 && service_active);
    CHECK(command("settings caps").find("adc_manual") == std::string::npos);
    CHECK(set("1.815000", cli, false) == "ERR " + ns + " readonly");
    CHECK(saves == 0 && state.adc_override == 0 && service_active);
    CHECK(set("1.900000", cli) == "OK " + ns + " adc_set");
    CHECK(std::fabs(multiplier - 1.9f) < 0.000001f && persisted.adc_override == multiplier);
    CHECK(state.profile == 0 && applies == 1 && saves == 1 && writes == 1);
    CHECK(samples == 0 && adc_commits == 1 && !service_active);

    fresh(); caps.adc = false;
    CHECK(command(ns + " adc manual", false, cli) == "OK " + ns + " adc_manual supported=0");
    CHECK(set("1.815", cli) == "ERR " + ns + " unsupported");
    CHECK(saves == 0 && samples == 0 && adc_commits == 0);

    for (const char* invalid : {"", "-1.815", "+1.815", "nan", "NaN", "inf", "Infinity",
          "1e0", "1E0", "0x1.0p0", "1,815", ".815", "1.", "1..8", "1.8150000",
          "1.815 ", " 1.815", "1.815\t", "1.8 15", "1.8\n", "1.8abc",
          "4294967296", "4294967295.999999", "4294.967296", "999999999999999999",
          "000000000000000001.815", "\xd9\xa1.815"}) {
      fresh();
      CHECK(set(invalid, cli) == "ERR " + ns + " invalid");
      CHECK(writes == 0 && saves == 0 && applies == 0 && samples == 0 && service_active);
    }
    for (const char* outside : {"0", "0.000000", "0.000001", "1.000000", "2.500000", "4294.967295"}) {
      fresh();
      CHECK(set(outside, cli) == "ERR " + ns + " range");
      CHECK(writes == 0 && saves == 0 && applies == 0 && service_active);
    }
    for (const char* valid : {"1.815", "1.8150", "1.815000", "01.815000", "00001.815000"}) {
      fresh(); CHECK(set(valid, cli) == "OK " + ns + " adc_set");
      CHECK(multiplier == caps.adc_default && samples == 0);
    }
    fresh(1.2f); CHECK(set("1", cli) == "OK " + ns + " adc_set");
    CHECK(multiplier == 1.0f);

    for (float factory : {1.815f, 1.73f, 4.9f, 5.0715f, 8.4f}) {
      for (float ratio : {0.75f, 1.0f, 1.25f}) {
        fresh(factory);
        char value[32]; std::snprintf(value, sizeof(value), "%.6f", factory * ratio);
        CHECK(set(value, cli) == "OK " + ns + " adc_set");
        CHECK(std::fabs(multiplier - factory * ratio) < 0.000002f && saves == 1 && samples == 0);
      }
      for (float ratio : {0.749f, 1.251f}) {
        fresh(factory);
        char value[32]; std::snprintf(value, sizeof(value), "%.6f", factory * ratio);
        CHECK(set(value, cli) == "ERR " + ns + " range");
        CHECK(saves == 0 && applies == 0 && multiplier == factory);
      }
    }
    fresh();
    const auto before = state;
    save_ok = false;
    CHECK(set("1.9", cli) == "ERR " + ns + " storage");
    CHECK(state.adc_override == before.adc_override && state.profile == before.profile);
    CHECK(persisted.adc_override == 0 && multiplier == caps.adc_default);
    CHECK(writes == 2 && saves == 1 && applies == 0 && adc_commits == 0 && service_active);
    save_ok = true;
    CHECK(set("1.9", cli) == "OK " + ns + " adc_set");
    CHECK(saves == 2 && applies == 1 && !service_active);
  }

  fresh();
  auto token = preview();
  CHECK(set("1.9") == "OK settings adc_set");
  CHECK(command("settings adc apply " + std::to_string(token)) == "ERR settings stale");
  CHECK(saves == 1);
  fresh(); token = preview(); save_ok = false;
  CHECK(set("1.9") == "ERR settings storage");
  save_ok = true;
  CHECK(command("settings adc apply " + std::to_string(token)) == "OK settings adc_apply");
  fresh();
  CHECK(command("settings adc preview 3320") == "ERR settings source");
  samples = 0;
  CHECK(set("1.815000") == "OK settings adc_set" && samples == 0);
  fresh();
  char short_reply[4];
  CHECK(settings.handle("settings adc set 1.9", short_reply, sizeof(short_reply), true));
  CHECK(saves == 0);
  CHECK(handleSmartUiSettingsCli(settings, "ui adc set 1.9", short_reply, sizeof(short_reply), true));
  CHECK(saves == 0);
  std::printf("PASS %u manual ADC production backend/CLI checks\n", checks);
}
