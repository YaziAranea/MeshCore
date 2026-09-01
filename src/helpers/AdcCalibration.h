#pragma once

#include <math.h>
#include <stdint.h>

namespace mesh {

// User calibration is intended to compensate resistor/ADC tolerance, not to
// redefine the board circuit.  A 25% window is deliberately generous while
// preventing values that can disable low-battery protection or overflow.
inline float adcCalibrationMinimum(float board_default) {
  return board_default * 0.75f;
}

inline float adcCalibrationMaximum(float board_default) {
  return board_default * 1.25f;
}

inline bool normalizeAdcMultiplier(float requested, float board_default, float& applied) {
  if (!isfinite(requested) || !isfinite(board_default) || board_default <= 0.0f) return false;
  if (requested == 0.0f) {
    applied = board_default;
    return true;
  }
  // Decimal values persisted by the UI can land a few ULPs either side of an
  // inclusive 75/125% boundary (for example 4.9f * 0.75f vs 3.675f).
  const float tolerance = board_default * 0.000001f;
  if (requested < adcCalibrationMinimum(board_default) - tolerance ||
      requested > adcCalibrationMaximum(board_default) + tolerance) return false;
  applied = requested;
  return true;
}

inline uint16_t saturatingBatteryMilliVolts(float millivolts) {
  if (!isfinite(millivolts) || millivolts <= 0.0f) return 0;
  if (millivolts >= 65535.0f) return UINT16_MAX;
  return static_cast<uint16_t>(millivolts + 0.5f);
}

} // namespace mesh
