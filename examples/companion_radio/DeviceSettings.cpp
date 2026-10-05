#include "DeviceSettings.h"
#include <helpers/AdcCalibration.h>
#include <stdio.h>
#include <string.h>

namespace smartui {
namespace {
constexpr uint8_t GPIO_MODE = 1;
constexpr uint8_t TONE_MODE = 2;
constexpr uint8_t VIBE_MODE = 4;

bool unsignedNumber(const char* text, uint32_t& number) {
  if (text == nullptr || *text == 0) return false;
  number = 0;
  for (; *text; ++text) {
    if (*text < '0' || *text > '9' || number > (UINT32_MAX - (*text - '0')) / 10U) return false;
    number = number * 10U + (*text - '0');
  }
  return true;
}

void response(char* reply, size_t capacity, const char* message) {
  if (reply != nullptr && capacity > 0) snprintf(reply, capacity, "%s", message);
}

void setNotifyBit(DeviceSettingsState& state, uint8_t bit, bool enabled) {
  if (enabled) {
    state.notify_mode |= bit;
    state.important_notify_mode |= bit;
  } else {
    state.notify_mode &= ~bit;
    state.important_notify_mode &= ~bit;
  }
}
}  // namespace

bool DeviceSettings::commit(const DeviceSettingsState& before,
                            const DeviceSettingsState& after, bool battery_changed) {
  // Persistence sees the candidate; hardware sees only committed preferences.
  // A rejected write restores RAM without resetting outputs or battery evidence.
  _hooks.write(after);
  if (!_hooks.save()) {
    _hooks.write(before);
    return false;
  }
  _preview_token = 0;
  _hooks.apply(battery_changed);
  return true;
}

bool DeviceSettings::handle(const char* command, char* reply, size_t capacity,
                            bool allow_mutation) {
  if (command == nullptr || strncmp(command, "settings", 8) != 0 ||
      (command[8] != 0 && command[8] != ' ')) return false;
  if (reply == nullptr || capacity < REPLY_CAPACITY) {
    response(reply, capacity, "ERR settings buffer");
    return true;
  }
  if (!_hooks.read || !_hooks.write || !_hooks.save || !_hooks.apply ||
      !_hooks.caps || !_hooks.batteryMilliVolts || !_hooks.adcMultiplier || !_hooks.millis) {
    response(reply, capacity, "ERR settings unavailable");
    return true;
  }
  const DeviceSettingsCaps caps = _hooks.caps();
  const DeviceSettingsState before = _hooks.read();
  if (strcmp(command, "settings caps") == 0) {
    snprintf(reply, capacity,
        "OK settings caps v=1 adc=%u sound=%u board_led=%u unread_led=%u vibration=%u gps=%u battery_protection=%u display=%u melody_max=%u adc_min=%.6f adc_max=%.6f",
        caps.adc, caps.sound, caps.board_led, caps.unread_led, caps.vibration, caps.gps,
        caps.battery_protection, caps.display, caps.melody_max,
        mesh::adcCalibrationMinimum(caps.adc_default), mesh::adcCalibrationMaximum(caps.adc_default));
    return true;
  }
  if (strcmp(command, "settings get") == 0) {
    snprintf(reply, capacity,
        "OK settings get battery_mv=%u adc_multiplier=%.6f adc_default=%.6f sound_quiet=%u volume=%u melody=%u board_led=%u unread_led=%u vibration=%u gps=%u battery_protection=%u shutdown_mv=%u muted=%u",
        _hooks.batteryMilliVolts(), _hooks.adcMultiplier(), caps.adc_default,
        (caps.effective_notify_mode & TONE_MODE) ? 0U : 1U, before.volume, before.melody_system,
        before.board_led, before.unread_led, (caps.effective_notify_mode & VIBE_MODE) ? 1U : 0U,
        before.gps_source == 0 ? before.gps : 0U, before.battery_protection,
        caps.battery_protection ? (before.battery_protection ? 3200U : 2700U) : 0U, before.muted);
    return true;
  }
  if (strncmp(command, "settings adc preview ", 21) == 0) {
    _preview_token = 0;
    uint32_t measured;
    if (!unsignedNumber(command + 21, measured)) {
      response(reply, capacity, "ERR settings invalid");
    } else if (!caps.adc) {
      response(reply, capacity, "ERR settings unsupported");
    } else if (measured < 2500 || measured > 4500) {
      response(reply, capacity, "ERR settings range");
    } else {
      const uint16_t sampled = _hooks.batteryMilliVolts();
      const float current = _hooks.adcMultiplier();
      float normalized;
      const float proposed = sampled ? current * (static_cast<float>(measured) / sampled) : 0;
      if (sampled == 0 || !isfinite(current) || current <= 0) {
        response(reply, capacity, "ERR settings measurement");
      } else if (!mesh::normalizeAdcMultiplier(proposed, caps.adc_default, normalized)) {
        response(reply, capacity, "ERR settings range");
      } else {
        if (++_token_counter == 0) ++_token_counter;
        _preview_token = _token_counter;
        _preview_started = _hooks.millis();
        _preview_multiplier = normalized;
        _preview_baseline = current;
        _preview_override = before.adc_override;
        snprintf(reply, capacity,
            "OK settings adc_preview token=%lu sampled_mv=%u measured_mv=%lu multiplier=%.6f",
            static_cast<unsigned long>(_preview_token), sampled,
            static_cast<unsigned long>(measured), normalized);
      }
    }
    return true;
  }
  if (!allow_mutation) {
    response(reply, capacity, "ERR settings readonly");
    return true;
  }
  DeviceSettingsState after = before;
  if (strncmp(command, "settings adc apply ", 19) == 0) {
    uint32_t token;
    if (!unsignedNumber(command + 19, token)) {
      response(reply, capacity, "ERR settings invalid");
    } else if (!caps.adc) {
      response(reply, capacity, "ERR settings unsupported");
    } else if (token == 0 || token != _preview_token ||
               static_cast<uint32_t>(_hooks.millis() - _preview_started) >= 60000U ||
               _hooks.adcMultiplier() != _preview_baseline || before.adc_override != _preview_override) {
      _preview_token = 0;
      response(reply, capacity, "ERR settings stale");
    } else {
      after.adc_override = _preview_multiplier;
      after.profile = 0;
      response(reply, capacity, commit(before, after, true) ?
          "OK settings adc_apply" : "ERR settings storage");
    }
    return true;
  }
  if (strcmp(command, "settings adc reset") == 0) {
    if (!caps.adc) response(reply, capacity, "ERR settings unsupported");
    else {
      after.adc_override = 0;
      after.profile = 0;
      response(reply, capacity, commit(before, after, true) ?
          "OK settings adc_reset" : "ERR settings storage");
    }
    return true;
  }
  if (strcmp(command, "settings test") == 0) {
    if (!(caps.sound || caps.unread_led || caps.vibration) || !_hooks.testNotification)
      response(reply, capacity, "ERR settings unsupported");
    else {
      _hooks.testNotification();
      response(reply, capacity, "OK settings test");
    }
    return true;
  }
  if (strncmp(command, "settings set ", 13) != 0) {
    response(reply, capacity, "ERR settings invalid");
    return true;
  }
  const char* key_start = command + 13;
  const char* separator = strchr(key_start, ' ');
  char key[24];
  uint32_t value;
  if (separator == nullptr || separator == key_start ||
      static_cast<size_t>(separator - key_start) >= sizeof(key) ||
      !unsignedNumber(separator + 1, value)) {
    response(reply, capacity, "ERR settings invalid");
    return true;
  }
  const size_t key_length = separator - key_start;
  memcpy(key, key_start, key_length);
  key[key_length] = 0;
  bool supported = true;
  uint32_t minimum = 0;
  uint32_t maximum = 1;
  bool battery_changed = false;
  if (strcmp(key, "sound_quiet") == 0) {
    supported = caps.sound;
    after.sound_quiet = value;
    setNotifyBit(after, TONE_MODE, value == 0);
  } else if (strcmp(key, "volume") == 0) {
    supported = caps.sound;
    minimum = 1;
    maximum = 10;
    after.volume = value;
  } else if (strcmp(key, "melody") == 0) {
    supported = caps.sound;
    maximum = caps.melody_max;
    after.melody = after.melody_dm = after.melody_mention = after.melody_system = value;
  } else if (strcmp(key, "board_led") == 0) {
    supported = caps.board_led;
    after.board_led = value;
  } else if (strcmp(key, "unread_led") == 0) {
    supported = caps.unread_led;
    after.unread_led = value;
    setNotifyBit(after, GPIO_MODE, value != 0);
  } else if (strcmp(key, "vibration") == 0) {
    supported = caps.vibration;
    after.vibe_quiet = value == 0;
    setNotifyBit(after, VIBE_MODE, value != 0);
  } else if (strcmp(key, "gps") == 0) {
    supported = caps.gps;
    after.gps = value;
    after.gps_source = 0;
  } else if (strcmp(key, "battery_protection") == 0) {
    supported = caps.battery_protection;
    after.battery_protection = value;
    battery_changed = true;
  } else if (strcmp(key, "muted") == 0) {
    after.muted = value;
    after.night_quiet = 0;
  } else {
    response(reply, capacity, "ERR settings invalid");
    return true;
  }
  if (!supported) response(reply, capacity, "ERR settings unsupported");
  else if (value < minimum || value > maximum) response(reply, capacity, "ERR settings range");
  else {
    after.profile = 0;
    if (!commit(before, after, battery_changed)) response(reply, capacity, "ERR settings storage");
    else snprintf(reply, capacity, "OK settings set key=%s value=%lu", key, static_cast<unsigned long>(value));
  }
  return true;
}
}  // namespace smartui
