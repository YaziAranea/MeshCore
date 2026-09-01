#pragma once

#include <stdint.h>

namespace smartui {

struct BatteryReading {
  uint16_t millivolts;
  bool valid;

  BatteryReading(uint16_t mv = 0, bool is_valid = false)
      : millivolts(mv), valid(is_valid) { }
};

// Turning off the normal cutoff retains the board's emergency floor.
inline uint16_t batteryShutdownThreshold(bool enabled, uint16_t normal, uint16_t floor) {
  return enabled ? normal : floor;
}

// A zero value is the MainBoard convention for "battery ADC unavailable".
// Every non-zero reading is real data, including severe undervoltage below
// 2.5 V.  Invalid samples neither count nor erase earlier valid evidence.
inline BatteryReading batteryReading(uint16_t millivolts) {
  return BatteryReading(millivolts, millivolts != 0);
}

inline uint8_t nextLowBatteryStrikeCount(uint8_t strikes, BatteryReading reading,
                                         uint16_t threshold, uint8_t confirmCount) {
  if (threshold == 0 || confirmCount == 0) return 0;
  if (!reading.valid) return strikes > confirmCount ? confirmCount : strikes;
  if (reading.millivolts >= threshold) return 0;
  if (strikes >= confirmCount) return confirmCount;
  return static_cast<uint8_t>(strikes + 1);
}

inline uint8_t nextLowBatteryStrikeCount(uint8_t strikes, uint16_t millivolts,
                                         uint16_t threshold, uint8_t confirmCount) {
  return nextLowBatteryStrikeCount(strikes, batteryReading(millivolts), threshold,
                                   confirmCount);
}

// Median of the available raw samples.  Missing (zero) ADC samples are
// excluded, so they cannot turn a genuine sub-2.5 V reading into "invalid".
inline BatteryReading medianBatteryReading(uint16_t a, uint16_t b, uint16_t c) {
  uint16_t samples[3];
  uint8_t count = 0;
  if (a != 0) samples[count++] = a;
  if (b != 0) samples[count++] = b;
  if (c != 0) samples[count++] = c;
  if (count == 0) return BatteryReading();

  for (uint8_t i = 1; i < count; i++) {
    uint16_t value = samples[i];
    uint8_t j = i;
    while (j > 0 && samples[j - 1] > value) {
      samples[j] = samples[j - 1];
      j--;
    }
    samples[j] = value;
  }

  // For two available readings choose the lower one.  A protection path must
  // not mask a real voltage collapse merely because one ADC sample was high.
  return BatteryReading(samples[(count - 1) / 2], true);
}

} // namespace smartui
