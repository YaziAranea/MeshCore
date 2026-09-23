#pragma once

#include <stdint.h>

namespace smartui {

// Reset is a separate confirmation screen; navigation gestures never reset.
inline bool adcFactoryResetConfirmed(bool settings_open, bool reset_page,
                                     bool editing, bool confirmed) {
  return settings_open && reset_page && !editing && confirmed;
}

// Preview a draft calibration without applying it to MainBoard.  The board
// stays on the committed multiplier, so battery safety and telemetry cannot
// inherit an uncommitted UI value.
inline uint16_t adcPreviewMilliVolts(uint16_t committed_mv,
                                     float committed_multiplier,
                                     float draft_multiplier) {
  if (!(committed_multiplier > 0.0f) || !(draft_multiplier > 0.0f)) {
    return committed_mv;
  }
  const float preview = (float)committed_mv * draft_multiplier / committed_multiplier;
  if (!(preview > 0.0f)) return 0;
  if (preview >= 65535.0f) return 65535U;
  return (uint16_t)(preview + 0.5f);
}

} // namespace smartui
