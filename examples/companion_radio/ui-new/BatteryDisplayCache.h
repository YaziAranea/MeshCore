#pragma once

#include <stdint.h>
#include "BatteryShutdownPolicy.h"

namespace smartui {

// One voltage for every UI page, without averaging old screen frames into a
// new reading.  A short median rejects an ADC spike; no multi-minute EMA tail
// survives a voltage change, a slow e-paper refresh, or a sleeping display.
class BatteryDisplayCache {
  uint16_t _millivolts = 0;
  uint32_t _sampled_at = 0;
  bool _sampled = false;

public:
  void invalidate() {
    _millivolts = 0;
    _sampled_at = 0;
    _sampled = false;
  }

  template <typename ReadMilliVolts>
  uint16_t read(uint32_t now, uint32_t interval_ms, ReadMilliVolts read_mv) {
    if (!_sampled || static_cast<uint32_t>(now - _sampled_at) >= interval_ms) {
      const uint16_t a = read_mv();
      const uint16_t b = read_mv();
      const uint16_t c = read_mv();
      _millivolts = medianBatteryReading(a, b, c).millivolts;
      _sampled_at = now;
      _sampled = true;
    }
    return _millivolts;
  }
};

} // namespace smartui
