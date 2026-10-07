#pragma once

#include <stdint.h>
#include <string.h>

inline uint32_t loRaFloatBits(float value) {
  static_assert(sizeof(float) == sizeof(uint32_t), "LoRa settings require binary32 floats");
  uint32_t bits;
  memcpy(&bits, &value, sizeof(bits));
  return bits;
}

inline bool finiteLoRaFloat(float value) {
  // isfinite/NaN comparisons may be optimized away by the nRF52 -Ofast build.
  return (loRaFloatBits(value) & 0x7f800000U) != 0x7f800000U;
}

inline float companionFrequencyMHz(uint32_t khz) {
  // Keep reciprocal rounding below binary32 precision. A float intermediate
  // under -Ofast can turn the valid 960000 kHz endpoint into 960.000061 MHz.
  return static_cast<float>(static_cast<double>(khz) / 1000.0);
}

inline float companionBandwidthKHz(uint32_t hz) {
  // -Ofast can turn /1000.0f into multiplication by an approximate reciprocal:
  // 62500 Hz then becomes 62.5000038 kHz. Use the actual modulation constants.
  switch (hz) {
    case 7800: return 7.8f;
    case 10400: return 10.4f;
    case 15600: return 15.6f;
    case 20800: return 20.8f;
    case 31250: return 31.25f;
    case 41700: return 41.7f;
    case 62500: return 62.5f;
    case 125000: return 125.0f;
    case 250000: return 250.0f;
    case 500000: return 500.0f;
    default: return static_cast<float>(hz) / 1000.0f;
  }
}

inline bool canonicalSX1262Bandwidth(float bw, float& canonical) {
  const uint32_t bits = loRaFloatBits(bw);
  if ((bits & 0x80000000U) || !finiteLoRaFloat(bw)) return false;
  static const float bandwidths[] = {
      7.8f, 10.4f, 15.6f, 20.8f, 31.25f, 41.7f, 62.5f, 125.0f, 250.0f, 500.0f};
  for (float supported : bandwidths) {
    const uint32_t expected = loRaFloatBits(supported);
    const uint32_t distance = bits > expected ? bits - expected : expected - bits;
    // Accept only binary rounding residue from older saved profiles, not
    // arbitrary nearby bandwidths. At 500 kHz two ULP are less than 0.062 Hz.
    if (distance <= 2U) { canonical = supported; return true; }
  }
  return false;
}

// Use positive comparisons so NaN, infinity and unsupported radio settings
// are rejected before any hardware or persistent configuration is changed.
inline bool validCompanionLoRaParams(float freq, float bw, uint8_t sf, uint8_t cr) {
  return finiteLoRaFloat(freq) && finiteLoRaFloat(bw) &&
         freq >= 150.0f && freq <= 2500.0f && bw >= 7.0f && bw <= 500.0f &&
         sf >= 5 && sf <= 12 && cr >= 5 && cr <= 8;
}

inline bool validSX1262LoRaParams(float freq, float bw, uint8_t sf, uint8_t cr) {
  float canonical;
  if (!canonicalSX1262Bandwidth(bw, canonical) ||
      !validCompanionLoRaParams(freq, canonical, sf, cr) || freq > 960.0f) return false;
  // RadioLib's integer switch accepts intervals around these values. Only
  // accept the actual bandwidths, so its time-on-air cache and RXPS geometry
  // cannot disagree with the modulation register (for example BW=126).
  return true;
}
