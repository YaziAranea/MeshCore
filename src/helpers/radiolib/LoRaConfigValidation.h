#pragma once

#include <stdint.h>

// Use positive comparisons so NaN, infinity and unsupported radio settings
// are rejected before any hardware or persistent configuration is changed.
inline bool validCompanionLoRaParams(float freq, float bw, uint8_t sf, uint8_t cr) {
  return freq >= 150.0f && freq <= 2500.0f && bw >= 7.0f && bw <= 500.0f &&
         sf >= 5 && sf <= 12 && cr >= 5 && cr <= 8;
}

inline bool validSX1262LoRaParams(float freq, float bw, uint8_t sf, uint8_t cr) {
  if (!validCompanionLoRaParams(freq, bw, sf, cr) || freq > 960.0f) return false;
  // RadioLib's integer switch accepts intervals around these values. Only
  // accept the actual bandwidths, so its time-on-air cache and RXPS geometry
  // cannot disagree with the modulation register (for example BW=126).
  static const float bandwidths[] = {
      7.8f, 10.4f, 15.6f, 20.8f, 31.25f, 41.7f, 62.5f, 125.0f, 250.0f, 500.0f};
  for (float supported : bandwidths) {
    if (bw == supported) return true;
  }
  return false;
}
