#pragma once

#include <stdint.h>

namespace smartui {

// Turning off the normal cutoff retains the board's emergency floor.
inline uint16_t batteryShutdownThreshold(bool enabled, uint16_t normal, uint16_t floor) {
  return enabled ? normal : floor;
}

inline uint8_t nextLowBatteryStrikeCount(uint8_t strikes, uint16_t mv, uint16_t threshold,
                                         uint16_t validMin, uint8_t confirmCount) {
  if (threshold == 0 || mv < validMin || mv >= threshold) return 0;
  if (strikes >= confirmCount) return confirmCount;
  return static_cast<uint8_t>(strikes + 1);
}

} // namespace smartui
