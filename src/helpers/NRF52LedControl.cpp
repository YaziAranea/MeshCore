#include <Arduino.h>

#include "BoardLedControl.h"

#if defined(NRF52_PLATFORM) && defined(SMARTUI_NRF52_LED_GATE) && SMARTUI_NRF52_LED_GATE

extern "C" void __real_ledOn(uint32_t pin);

// Adafruit InternalFileSystem uses ledOn(LED_BUILTIN) as an unconditional
// flash-write indicator.  Keep that framework behavior for every other pin,
// but make the onboard LED obey SmartUI's persisted board-LED master switch.
extern "C" void __wrap_ledOn(uint32_t pin) {
#if defined(LED_BUILTIN)
  if (pin == static_cast<uint32_t>(LED_BUILTIN) && !meshcoreBoardLedsEnabled()) return;
#endif
  __real_ledOn(pin);
}

#endif
