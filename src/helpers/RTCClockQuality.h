#pragma once

#include <stdint.h>

// Plausibility is not trust by itself.  It only validates timestamps already
// associated with a trusted source or retained-clock marker.
#define MESH_RTC_TRUST_MIN 1704067200UL  // 2024-01-01 00:00:00 UTC
#define MESH_RTC_TRUST_MAX 4102444800UL  // 2100-01-01 00:00:00 UTC

inline bool meshRtcTimestampPlausible(uint32_t timestamp) {
  return timestamp >= MESH_RTC_TRUST_MIN && timestamp <= MESH_RTC_TRUST_MAX;
}
