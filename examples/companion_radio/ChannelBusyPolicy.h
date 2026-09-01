#pragma once

#include <stdint.h>

namespace companion {

// Sampling radio state can perform an SPI transaction. Keep it out of the hot
// loop and use unsigned elapsed-time arithmetic so millis() rollover is safe.
inline bool channelBusySampleDue(uint32_t now, uint32_t previous,
                                 uint32_t interval_ms) {
  return interval_ms != 0 && static_cast<uint32_t>(now - previous) >= interval_ms;
}

inline uint32_t channelBusyElapsedToAccount(uint32_t now, uint32_t previous,
                                            uint32_t interval_ms,
                                            bool receiving) {
  if (!receiving || previous == 0 || interval_ms == 0) return 0;
  const uint32_t elapsed = static_cast<uint32_t>(now - previous);
  // A long gap normally means deep sleep or a blocked task. The instantaneous
  // radio state cannot describe that whole interval, so only rebase it.
  if (elapsed > interval_ms * 2U) return 0;
  return elapsed;
}

}  // namespace companion
