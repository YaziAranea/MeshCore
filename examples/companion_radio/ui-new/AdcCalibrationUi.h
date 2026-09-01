#pragma once

#include <stdint.h>

namespace smartui {

// Factory reset deliberately uses a double click while merely viewing the
// ADC page.  Long ENTER remains the normal edit/confirm gesture, and a double
// click while editing cannot discard an in-progress calibration by accident.
inline bool adcFactoryResetGesture(bool settings_open, bool adc_page,
                                   bool editing, uint8_t click_count) {
  return settings_open && adc_page && !editing && click_count == 2;
}

} // namespace smartui
