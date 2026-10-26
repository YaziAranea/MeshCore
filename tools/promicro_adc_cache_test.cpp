#include <cassert>
#include <cmath>
#include <cstdint>
#include <initializer_list>
#include <cstdio>
#include <string>
#include <Arduino.h>
#include "DeviceSettings.h"
#include "SmartUiCliSettings.h"

static uint32_t fake_now;
static uint32_t fake_raw;
static int fake_resolution;
static unsigned fake_reads;
static bool power_states[8];
static unsigned power_count;
static unsigned power_index;

static void power(std::initializer_list<bool> states) {
  assert(states.size() <= 8);
  power_count = static_cast<unsigned>(states.size());
  power_index = 0;
  unsigned i = 0;
  for (bool state : states) power_states[i++] = state;
}

bool promicroTestExternalPower() {
  assert(power_index < power_count);
  return power_states[power_index++];
}

void analogReadResolution(int resolution) { fake_resolution = resolution; }
uint32_t analogRead(uint32_t pin) {
  assert(pin == 17);
  ++fake_reads;
  return fake_raw;
}
uint32_t millis() { return fake_now; }
int digitalRead(uint32_t) { return HIGH; }

#include "../variants/promicro/PromicroBoard.h"
#include "adc_ui_bounds.h"

void PromicroBoard::begin() {}

static uint32_t rawFor(uint16_t millivolts, float multiplier) {
  return static_cast<uint32_t>(std::lround(millivolts / multiplier));
}

static PromicroBoard settings_board;
static smartui::DeviceSettings settings;
static smartui::DeviceSettingsState state, persisted;
static bool save_ok = true;
static unsigned saves, applies;
static smartui::DeviceSettingsState readState() { return state; }
static void writeState(const smartui::DeviceSettingsState& value) { state = value; }
static bool saveState() {
  ++saves;
  if (!save_ok) return false;
  persisted = state;
  return true;
}
static void applyState(bool battery_changed) {
  assert(battery_changed);
  ++applies;
  assert(settings_board.setAdcMultiplier(state.adc_override));
}
static smartui::DeviceSettingsCaps readCaps() {
  smartui::DeviceSettingsCaps caps;
  caps.adc = true;
  caps.adc_default = ADC_MULTIPLIER;
  return caps;
}
static uint16_t readBattery() {
  power({false, false});
  return settings_board.getBattMilliVolts();
}
static float readMultiplier() { return settings_board.getAdcMultiplier(); }
static std::string command(const std::string& text, bool cli = false) {
  char reply[smartui::DeviceSettings::REPLY_CAPACITY] = {};
  assert(cli ? smartui::handleSmartUiSettingsCli(settings, text.c_str(), reply, sizeof(reply), true)
             : settings.handle(text.c_str(), reply, sizeof(reply), true));
  return reply;
}

static void rangeAndPersistence() {
  smartui::DeviceSettingsHooks hooks;
  hooks.read = readState; hooks.write = writeState; hooks.save = saveState;
  hooks.apply = applyState; hooks.caps = readCaps; hooks.batteryMilliVolts = readBattery;
  hooks.adcMultiplier = readMultiplier; hooks.millis = millis;
  settings.begin(hooks);
  const AdcMenu menu;
  assert(std::fabs(menu.clampAdcMultiplier(0) - 1.36125f) < 0.000001f);
  assert(menu.clampAdcMultiplier(2.905f) == 2.905f);
  assert(menu.clampAdcMultiplier(4.005f) == 4.0f);
  assert(command("settings caps").find("adc_min=1.361250 adc_max=4.000000") != std::string::npos);
  assert(command("ui caps adc_max", true) == "OK ui caps key=adc_max value=4.000000");

  for (const char* value : {"1.361250", "2.268750", "2.905", "4.000000"}) {
    assert(command(std::string("ui adc set ") + value, true) == "OK ui adc_set");
    assert(readMultiplier() == state.adc_override && persisted.adc_override == state.adc_override);
    PromicroBoard reloaded;
    assert(reloaded.setAdcMultiplier(persisted.adc_override));
    assert(reloaded.getAdcMultiplier() == readMultiplier());
  }
  assert(command("ui get adc_multiplier", true) == "OK ui get key=adc_multiplier value=4.000000");
  fake_raw = 1050;
  assert(readBattery() == 4200);
  const unsigned saved = saves, applied = applies;
  for (const char* value : {"1.361", "4.00001", "4.005", "9"}) {
    assert(command(std::string("settings adc set ") + value) == "ERR settings range");
    assert(saves == saved && applies == applied && readMultiplier() == 4.0f);
  }
  for (float value : {1.361f, 4.00001f, 4.005f, 9.0f}) {
    assert(!settings_board.setAdcMultiplier(value));
    assert(readMultiplier() == 4.0f);
  }
  save_ok = false;
  assert(command("settings adc set 2.905") == "ERR settings storage");
  assert(state.adc_override == 4.0f && persisted.adc_override == 4.0f);
  assert(readMultiplier() == 4.0f && applies == applied);
  save_ok = true;

  // A multimeter correction beyond the former 125% ceiling can preview and commit.
  assert(command("settings adc set 2.268750") == "OK settings adc_set");
  fake_raw = rawFor(3280, readMultiplier());
  const float corrected = readMultiplier() * 4200.0f / readBattery();
  const auto preview = command("settings adc preview 4200");
  unsigned long token = 0;
  assert(std::sscanf(preview.c_str(), "OK settings adc_preview token=%lu", &token) == 1 && token != 0);
  assert(readMultiplier() == 2.26875f);
  assert(command("settings adc apply " + std::to_string(token)) == "OK settings adc_apply");
  assert(std::fabs(readMultiplier() - corrected) < 0.000001f);
  assert(persisted.adc_override == readMultiplier());
  assert(command("settings adc reset") == "OK settings adc_reset");
  assert(persisted.adc_override == 0 && readMultiplier() == 1.815f);
}

int main() {
  PromicroBoard board;
  uint16_t sampled = 0;
  float sample_multiplier = 0.0f;
  uint32_t age = 0;

  // A plain board read is enough to populate the cache: headless builds do not
  // depend on display code. Both power checks must say battery.
  fake_now = 1000;
  fake_raw = rawFor(3100, 1.815f);
  fake_reads = 0;
  power({false, false});
  assert(board.getBattMilliVolts() == 3100);
  assert(fake_resolution == 12 && fake_reads == 8 && power_index == 2);

  // A USB reading is still returned for ordinary status, but cannot replace
  // the calibration source captured on battery.
  fake_now = 1050;
  fake_raw = rawFor(4400, 1.815f);
  power({true, true});
  assert(board.getBattMilliVolts() == 4400);
  power({true});
  assert(board.getBatteryCalibrationSample(sampled, sample_multiplier, age));
  assert(sampled == 3100 && sample_multiplier == 1.815f && age == 50);

  // Connecting USB during the ADC burst is rejected by the second check.
  PromicroBoard transitioning;
  power({false, true});
  transitioning.getBattMilliVolts();
  power({true});
  assert(!transitioning.getBatteryCalibrationSample(sampled, sample_multiplier, age));

  // A changed multiplier invalidates evidence made with the old scale. A
  // rejected request does not destroy a valid same-scale sample; reset does.
  assert(board.setAdcMultiplier(1.97f));
  power({true});
  assert(!board.getBatteryCalibrationSample(sampled, sample_multiplier, age));
  fake_now = 1100;
  fake_raw = rawFor(3100, 1.97f);
  power({false, false});
  board.getBattMilliVolts();
  assert(!board.setAdcMultiplier(9.0f));
  power({true});
  assert(board.getBatteryCalibrationSample(sampled, sample_multiplier, age));
  assert(sample_multiplier == 1.97f);
  assert(board.setAdcMultiplier(0.0f));
  power({true});
  assert(!board.getBatteryCalibrationSample(sampled, sample_multiplier, age));

  // Age remains correct across the uint32_t millis() wrap.
  PromicroBoard wrapping;
  fake_now = UINT32_MAX - 49U;
  fake_raw = rawFor(3100, 1.815f);
  power({false, false});
  wrapping.getBattMilliVolts();
  fake_now = 50;
  power({true});
  assert(wrapping.getBatteryCalibrationSample(sampled, sample_multiplier, age));
  assert(age == 100U);
  rangeAndPersistence();
}
