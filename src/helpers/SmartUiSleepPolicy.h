#pragma once
#include <stdint.h>

namespace smartui {
// UART bridges cannot reliably tell firmware that a PC opened its COM port.
// A button wake opens a service window; received bytes renew that window.
inline bool serialServiceWindow(bool seen, uint32_t now, uint32_t last_input) {
  return seen && static_cast<uint32_t>(now - last_input) < 120000u;
}
inline bool holdCompanionLightSleep(bool usb_mode, bool wifi_active,
                                    bool console_active, bool ui_active,
                                    bool rescue) {
  return usb_mode || wifi_active || console_active || ui_active || rescue;
}
}
