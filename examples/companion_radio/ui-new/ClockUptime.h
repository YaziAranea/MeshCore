#pragma once

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

namespace smartui {

// Compact, deliberately low-churn text for small and e-paper clock screens.
// The value changes once a minute/hour/day instead of every second.
inline void formatClockUptime(char* out, size_t out_len, uint64_t uptime_seconds) {
  if (out == NULL || out_len == 0) return;
  if (uptime_seconds < 3600ULL) {
    snprintf(out, out_len, "U %lum", (unsigned long)(uptime_seconds / 60ULL));
  } else if (uptime_seconds < 86400ULL) {
    snprintf(out, out_len, "U %luh", (unsigned long)(uptime_seconds / 3600ULL));
  } else {
    uint64_t days = uptime_seconds / 86400ULL;
    if (days > 999ULL) {
      snprintf(out, out_len, "U 999+d");
    } else {
      snprintf(out, out_len, "U %lud", (unsigned long)days);
    }
  }
}

// Returns the x coordinate for drawTextRightAlign(), or -1 if the real font
// metrics do not leave enough room between the neighbouring status groups.
inline int16_t clockUptimeRightEdge(int16_t left_used, int16_t right_used,
                                    int16_t text_width, int16_t gap = 3) {
  if (text_width <= 0 || right_used <= left_used) return -1;
  int32_t right = (int32_t)right_used - gap;
  int32_t left = right - text_width;
  if (left < (int32_t)left_used + gap) return -1;
  if (right > INT16_MAX) return -1;
  return (int16_t)right;
}

}  // namespace smartui
