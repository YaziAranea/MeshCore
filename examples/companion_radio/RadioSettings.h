#pragma once

#include <stddef.h>
#include <stdint.h>

namespace smartui {

// Shared by the node menu, service console and local Companion CLI.
inline bool validAutoAdvertInterval(uint32_t minutes) {
  return minutes == 0 || minutes == 15 || minutes == 30 || minutes == 60 ||
         minutes == 120 || minutes == 180;
}

struct RadioSettingsState {
  float frequency_mhz = 0;
  float bandwidth_khz = 0;
  uint8_t sf = 0, cr = 0, path_bytes = 1;
  int8_t tx_dbm = 0;
  bool repeat = false;
  uint16_t advert_minutes = 0;
};

struct RadioSettingsHooks {
  RadioSettingsState (*read)() = nullptr;
  void (*write)(const RadioSettingsState&) = nullptr;
  bool (*save)() = nullptr;
  bool (*validate)(const RadioSettingsState&) = nullptr;
  bool (*repeatAllowed)(uint32_t frequency_khz) = nullptr;
  bool (*applyRadio)(const RadioSettingsState&) = nullptr;
  void (*applyAdvert)() = nullptr;
  bool (*busy)() = nullptr;
  bool (*healthy)() = nullptr;
};

// A small transaction image, never a full NodePrefs on the 4 KiB nRF52 stack.
// No automatic retries, radio transmission, secrets or arbitrary command parser.
class RadioSettings {
public:
  void begin(const RadioSettingsHooks& hooks) { _hooks = hooks; }
  bool handle(const char* command, char* reply, size_t capacity, bool allow_mutation);
private:
  RadioSettingsHooks _hooks;
};

}  // namespace smartui
