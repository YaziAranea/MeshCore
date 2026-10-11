#pragma once

#include <stdint.h>

namespace smartui {

// Optional external buzzer outputs for the public OLED/e-paper profiles only.
// Keep this separate from the legacy LED/vibration pool: that pool includes
// onboard LEDs, strapping pins, and pins used by board peripherals.
// Wiring references (Heltec schematics, checked 2026-10-11):
// https://resource.heltec.cn/download/WiFi_LoRa_32_V3/WiFi_LoRa_32_V3.2_Schematic_Diagram.pdf
// https://resource.heltec.cn/download/WiFi_LoRa_32_V4/Schematic/HTIT-WB32LAF_V4.3.pdf
// https://resource.heltec.cn/download/WiFi_LoRa_32_V4-R8/Schematic/HTIT-WBR8H_V4.3.2.pdf
// https://resource.heltec.cn/download/Wireless_Paper/Wireless_Paper_V0.4_Schematic_Diagram.pdf
#if defined(HELTEC_LORA_V3)
// GPIO40/41 are available only when no external JTAG probe is connected.
constexpr int8_t optional_tone_gpio_pins[] = {4, 40, 41};
#elif defined(HELTEC_V4_R8_OLED)
// GPIO33..37 are octal PSRAM, 40 is VEXT, and 41 is GNSS PPS.
constexpr int8_t optional_tone_gpio_pins[] = {4, 6, 15, 16, 47, 48};
#elif defined(HELTEC_LORA_V4_OLED)
// GPIO40/41 also reach the GNSS connector (WAKE_UP/PPS).
constexpr int8_t optional_tone_gpio_pins[] = {4, 47, 48};
#elif defined(HELTEC_WIRELESS_PAPER)
// GPIO15/16 belong to the 32.768 kHz crystal; 18 is the onboard TX LED.
constexpr int8_t optional_tone_gpio_pins[] = {17, 21};
#else
constexpr int8_t optional_tone_gpio_pins[] = {-1};
#endif

inline bool isOptionalTonePinAllowed(int pin) {
  if (pin == -1) return true;
  for (int8_t candidate : optional_tone_gpio_pins) {
    if (pin == candidate) return true;
  }
  return false;
}

}  // namespace smartui
