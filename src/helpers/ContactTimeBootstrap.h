#pragma once

#include <stdint.h>
#include "RTCClockQuality.h"

inline uint32_t selectContactTimeBootstrapCandidate(uint32_t latest,
                                                    uint32_t candidate) {
  // The strict upper bound leaves room for the +1 uniqueness step.
  if (!meshRtcTimestampPlausible(candidate) || candidate >= MESH_RTC_TRUST_MAX) {
    return latest;
  }
  return candidate > latest ? candidate : latest;
}

inline bool makeContactTimeEstimate(uint32_t latest, uint32_t& estimate) {
  if (!meshRtcTimestampPlausible(latest) || latest >= MESH_RTC_TRUST_MAX) return false;
  estimate = latest + 1U;
  return true;
}
