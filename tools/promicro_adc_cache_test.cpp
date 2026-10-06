#include <cassert>
#include <cmath>
#include <cstdint>
#include <initializer_list>
#include <Arduino.h>

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

void PromicroBoard::begin() {}

static uint32_t rawFor(uint16_t millivolts, float multiplier) {
  return static_cast<uint32_t>(std::lround(millivolts / multiplier));
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
}
