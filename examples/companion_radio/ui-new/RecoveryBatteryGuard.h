#pragma once
#include <stdint.h>
#include "BatteryShutdownPolicy.h"

namespace smartui {
// Used before preferences/UI exist. Failures must not bypass battery safety.
// Unavailable ADC (zero) preserves previous evidence; USB resets it.
class RecoveryBatteryGuard {
  uint32_t _last = 0;
  uint8_t _low = 0;
  bool _sampled = false;
public:
  bool sampleDue(uint32_t now) const {
    return !_sampled || static_cast<uint32_t>(now - _last) >= 1000;
  }
  bool update(uint32_t now, uint16_t mv, bool external, uint16_t threshold) {
    if (!sampleDue(now)) return false;
    _last = now;
    _sampled = true;
    if (external) _low = 0;
    else _low = nextLowBatteryStrikeCount(_low, mv, threshold, 3);
    return _low >= 3;
  }
};
} // namespace smartui
