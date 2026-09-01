#pragma once

#include <stdint.h>

namespace smartui {

// Wrap-safe comparison for 32-bit millis() deadlines.  Correct as long as an
// individual deadline is less than 2^31 ms in the future (about 24.8 days).
inline bool deadlineReached(uint32_t now, uint32_t deadline) {
  return static_cast<int32_t>(now - deadline) >= 0;
}

inline bool deadlinePending(uint32_t now, uint32_t deadline) {
  return static_cast<int32_t>(now - deadline) < 0;
}

// Optional deadlines use zero as "not scheduled".
inline bool optionalDeadlinePending(uint32_t now, uint32_t deadline) {
  return deadline != 0 && deadlinePending(now, deadline);
}

// Some UI timers use zero as "refresh immediately".
inline bool deadlineDueOrImmediate(uint32_t now, uint32_t deadline) {
  return deadline == 0 || deadlineReached(now, deadline);
}

inline bool elapsedAtLeast(uint32_t now, uint32_t since, uint32_t duration) {
  return static_cast<uint32_t>(now - since) >= duration;
}

} // namespace smartui
