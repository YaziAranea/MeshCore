#pragma once

#include <stddef.h>
#include <stdint.h>

namespace smartui {

enum class SoundPreviewResult : uint8_t {
  STARTED, MUTED, BUSY, PIN_CONFLICT, UNSUPPORTED
};

enum class NightQuietResult : uint8_t {
  OK, UNSUPPORTED, TIME, MUTED, STORAGE
};

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
  uint8_t agc_reset = 0;
  uint8_t fem_lna = 0;
  uint8_t fem_pa = 0;
  uint8_t bridge = 0;
  int8_t led_pin = -1;
  int8_t tone_pin = -1;
  int8_t vibe_pin = -1;
  uint8_t tone_8bit = 0;
  uint8_t high_drive = 0;
  uint16_t resonance_hz = 3000;
  uint8_t offline_dm_led = 1;
  uint8_t ble_dm_led = 1;
  uint8_t msg_popup = 1;
  uint8_t ui_font = 0;
  uint8_t ui_theme = 0;
  uint8_t ui_top_color = 1;
  uint8_t ui_bottom_color = 0;
  uint8_t backlight_timeout = 0;
  uint8_t advert_location = 0;
  uint32_t gps_interval = 0;
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
  bool agc_reset = false;
  bool fem_lna = false;
  bool fem_pa = false;
  bool bridge = false;
  bool adc_service = false;
  bool notify_pins = false;
  bool tone_8bit = false;
  bool high_drive = false;
  bool resonance = false;
  bool separate_melodies = false;
  bool phone_gps = false;
  bool colors = false;
  bool profiles = false;
  bool night_quiet = false;
  bool night_theme = false;
  uint8_t font_count = 0;
  uint8_t theme_count = 0;
  uint8_t notify_mask = 0;
};

struct DeviceSettingsHooks {
  DeviceSettingsState (*read)() = nullptr;
  void (*write)(const DeviceSettingsState&) = nullptr;
  bool (*save)() = nullptr;
  void (*apply)(bool battery_changed) = nullptr;
  DeviceSettingsCaps (*caps)() = nullptr;
  uint16_t (*batteryMilliVolts)() = nullptr;
  // Optional battery-only calibration source. Boards whose USB power path
  // disturbs the live ADC return a cached sample, its multiplier and age.
  bool (*batteryCalibrationSample)(uint16_t& millivolts, float& multiplier,
                                   uint32_t& age_ms) = nullptr;
  float (*adcMultiplier)() = nullptr;
  uint32_t (*millis)() = nullptr;
  void (*testNotification)() = nullptr;
  // Explicit local audition: one saved melody, without changing preferences.
  SoundPreviewResult (*previewSound)() = nullptr;
  // UTF-8 label for a build-local melody ID. At most MELODY_NAME_MAX bytes.
  const char* (*melodyName)(uint8_t id) = nullptr;
  // Dedicated checked transaction: fixed bridge pins and peripheral ownership
  // cannot be safely represented by changing the preferences byte alone.
  bool (*setToneBridge)(bool enabled) = nullptr;
  // Timed quiet owns its prompt day and morning-release policy in UITask.
  NightQuietResult (*setNightQuiet)(bool enabled) = nullptr;
  void (*adcService)(const char* action, char* reply, size_t capacity,
                     bool allow_mutation) = nullptr;
  void (*adcCommitted)() = nullptr;
  // Board-owned allowlist; options are actual Arduino pin numbers, not GPIO
  // arithmetic. Current peripheral/bridge ownership is checked on every write.
  bool (*pinAllowed)(const char* key, int pin) = nullptr;
  void (*pinOptions)(const char* key, char* out, size_t capacity) = nullptr;
  int (*pinValue)(const char* key) = nullptr;
};

class DeviceSettings {
public:
  static constexpr size_t REPLY_CAPACITY = 480;
  static constexpr size_t MELODY_NAME_MAX = 64;
  void begin(const DeviceSettingsHooks& hooks) { _hooks = hooks; resetSession(); }
  // The transport owner must call this when a client disconnects or changes.
  // Do not recycle tokens between sessions within the same device boot.
  void resetSession() { _preview_token = 0; }
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
  bool handleApi(const char* command, char* reply, size_t capacity, bool allow_mutation);
  bool handleSettings(const char* command, char* reply, size_t capacity, bool allow_mutation);
  bool handleExtended(const char* command, char* reply, size_t capacity, bool allow_mutation);
  bool handleMelody(const char* argument, const char* prefix, char* reply, size_t capacity);
};

}  // namespace smartui
