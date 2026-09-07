#pragma once

#include <stdint.h>

namespace smartui {

// Reset is a separate confirmation screen; navigation gestures never reset.
inline bool adcFactoryResetConfirmed(bool settings_open, bool reset_page,
                                     bool editing, bool confirmed) {
  return settings_open && reset_page && !editing && confirmed;
}

} // namespace smartui
