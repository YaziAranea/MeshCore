#pragma once

#include <stddef.h>
#include <stdint.h>

namespace smartui {

// Small, display-independent transaction image. Never copy NodePrefs (including
// quick replies and serializers) onto the nRF52's 4 KiB loop stack.
struct DeviceSettingsState {
  float adc_override = 0;
  uint8_t notify_mode = 0;
  uint8_t important_notify_mode = 0;
  uint8_t sound_quiet = 0;
  uint8_t vibe_quiet = 0;
  uint8_t volume = 10;
  uint8_t melody = 0;
  uint8_t melody_dm = 0;
  uint8_t melody_mention = 0;
  uint8_t melody_system = 0;
  uint8_t board_led = 1;
  uint8_t unread_led = 1;
  uint8_t gps = 0;
  uint8_t gps_source = 0;
  uint8_t battery_protection = 1;
  uint8_t muted = 0;
  uint8_t night_quiet = 0;
  uint8_t profile = 0;
};

struct DeviceSettingsCaps {
  bool adc = false;
  bool sound = false;
  bool board_led = false;
  bool unread_led = false;
  bool vibration = false;
  bool gps = false;
  bool battery_protection = false;
  bool display = false;
  uint8_t melody_max = 0;
  // Runtime-resolved mode for messages this profile actually notifies about.
  // Internal only; raw preference modes remain in the transaction snapshot.
  uint8_t effective_notify_mode = 0;
  float adc_default = 0;
};

struct DeviceSettingsHooks {
  DeviceSettingsState (*read)() = nullptr;
  void (*write)(const DeviceSettingsState&) = nullptr;
  bool (*save)() = nullptr;
  void (*apply)(bool battery_changed) = nullptr;
  DeviceSettingsCaps (*caps)() = nullptr;
  uint16_t (*batteryMilliVolts)() = nullptr;
  float (*adcMultiplier)() = nullptr;
  uint32_t (*millis)() = nullptr;
  void (*testNotification)() = nullptr;
};

class DeviceSettings {
public:
  static constexpr size_t REPLY_CAPACITY = 480;
  void begin(const DeviceSettingsHooks& hooks) { _hooks = hooks; _preview_token = 0; }
  // Returns false only when the command is outside this protocol's namespace.
  // Replies have no newline; the serial console owns framing and backpressure.
  bool handle(const char* command, char* reply, size_t capacity, bool allow_mutation);

private:
  DeviceSettingsHooks _hooks;
  uint32_t _token_counter = 0;
  uint32_t _preview_token = 0;
  uint32_t _preview_started = 0;
  float _preview_multiplier = 0;
  float _preview_baseline = 0;
  float _preview_override = 0;

  bool commit(const DeviceSettingsState& before, const DeviceSettingsState& after,
              bool battery_changed);
};

}  // namespace smartui
