#pragma once
#include <stdint.h>
#include "BatteryShutdownPolicy.h"

namespace smartui {
// Used before preferences/UI exist. Failures must not bypass battery safety.
// Unavailable ADC (zero) preserves previous evidence. Confirmed USB relaxes
// the normal cutoff, but never disables the emergency undervoltage floor.
class RecoveryBatteryGuard {
  uint32_t _last = 0;
  uint8_t _low = 0;
  uint16_t _threshold = 0;
  bool _sampled = false;
public:
  bool sampleDue(uint32_t now) const {
    return !_sampled || static_cast<uint32_t>(now - _last) >= 1000;
  }
  bool update(uint32_t now, uint16_t mv, bool external, uint16_t threshold,
              uint16_t floor = 2700) {
    if (!sampleDue(now)) return false;
    _last = now;
    _sampled = true;
    const uint16_t effective = effectiveBatteryShutdownThreshold(threshold, floor, external);
    if (_threshold != effective) { _threshold = effective; _low = 0; }
    _low = nextLowBatteryStrikeCount(_low, mv, effective, 3);
    return _low >= 3;
  }
};
} // namespace smartui
