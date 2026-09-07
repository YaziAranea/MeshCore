#pragma once

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

namespace smartui {

// Hours never wrap at midnight or turn into days. Minute precision avoids
// unnecessary second-by-second e-paper updates.
inline void formatClockUptime(char* out, size_t out_len, uint64_t uptime_seconds) {
  if (out == NULL || out_len == 0) return;
  // nRF builds link newlib-nano without printf long-long support. Convert
  // the hours ourselves instead of relying on a host-only working %llu.
  char hours[21];
  unsigned pos = sizeof(hours) - 1;
  hours[pos] = '\0';
  uint64_t value = uptime_seconds / 3600ULL;
  do {
    hours[--pos] = char('0' + value % 10ULL);
    value /= 10ULL;
  } while (value != 0);
  snprintf(out, out_len, "U %sh%02um", hours + pos,
           (unsigned)((uptime_seconds / 60ULL) % 60ULL));
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
