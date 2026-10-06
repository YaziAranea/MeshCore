#include "DeviceSettings.h"
#include <helpers/AdcCalibration.h>
#include <stdio.h>
#include <string.h>

namespace smartui {
namespace {
constexpr uint8_t GPIO_MODE = 1;
constexpr uint8_t TONE_MODE = 2;
constexpr uint8_t VIBE_MODE = 4;
constexpr uint32_t ADC_CALIBRATION_SAMPLE_MAX_AGE_MS = 120000U;

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
  if (command != nullptr && strncmp(command, "api", 3) == 0 &&
      (command[3] == 0 || command[3] == ' ')) {
    return handleApi(command, reply, capacity, allow_mutation);
  }
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
      const float current = _hooks.adcMultiplier();
      const uint32_t preview_now = _hooks.millis();
      uint16_t sampled = 0;
      bool source_valid = true;
      if (_hooks.batteryCalibrationSample) {
        float sample_multiplier = 0.0f;
        uint32_t sample_age_ms = 0;
        source_valid = _hooks.batteryCalibrationSample(
            sampled, sample_multiplier, sample_age_ms) && sampled != 0 &&
            isfinite(sample_multiplier) && isfinite(current) && current > 0.0f &&
            fabsf(sample_multiplier - current) <= current * 0.000001f &&
            sample_age_ms <= ADC_CALIBRATION_SAMPLE_MAX_AGE_MS;
      } else {
        sampled = _hooks.batteryMilliVolts();
      }
      float normalized;
      const float proposed = sampled ? current * (static_cast<float>(measured) / sampled) : 0;
      if (!source_valid) {
        response(reply, capacity, "ERR settings source");
      } else if (sampled == 0 || !isfinite(current) || current <= 0) {
        response(reply, capacity, "ERR settings measurement");
      } else if (!mesh::normalizeAdcMultiplier(proposed, caps.adc_default, normalized)) {
        response(reply, capacity, "ERR settings range");
      } else {
        if (++_token_counter == 0) ++_token_counter;
        _preview_token = _token_counter;
        _preview_started = preview_now;
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
  enum class Setting {
    SOUND_QUIET, VOLUME, MELODY, BOARD_LED, UNREAD_LED, VIBRATION, GPS,
    BATTERY_PROTECTION, MUTED
  } setting;
  if (strcmp(key, "sound_quiet") == 0) {
    supported = caps.sound;
    setting = Setting::SOUND_QUIET;
  } else if (strcmp(key, "volume") == 0) {
    supported = caps.sound;
    minimum = 1;
    maximum = 10;
    setting = Setting::VOLUME;
  } else if (strcmp(key, "melody") == 0) {
    supported = caps.sound;
    maximum = caps.melody_max;
    setting = Setting::MELODY;
  } else if (strcmp(key, "board_led") == 0) {
    supported = caps.board_led;
    setting = Setting::BOARD_LED;
  } else if (strcmp(key, "unread_led") == 0) {
    supported = caps.unread_led;
    setting = Setting::UNREAD_LED;
  } else if (strcmp(key, "vibration") == 0) {
    supported = caps.vibration;
    setting = Setting::VIBRATION;
  } else if (strcmp(key, "gps") == 0) {
    supported = caps.gps;
    setting = Setting::GPS;
  } else if (strcmp(key, "battery_protection") == 0) {
    supported = caps.battery_protection;
    setting = Setting::BATTERY_PROTECTION;
    battery_changed = true;
  } else if (strcmp(key, "muted") == 0) {
    setting = Setting::MUTED;
  } else {
    response(reply, capacity, "ERR settings invalid");
    return true;
  }
  if (!supported) response(reply, capacity, "ERR settings unsupported");
  else if (value < minimum || value > maximum) response(reply, capacity, "ERR settings range");
  else {
    // Validate the full-width input before narrowing it to a stored byte.
    const uint8_t checked = static_cast<uint8_t>(value);
    switch (setting) {
      case Setting::SOUND_QUIET:
        after.sound_quiet = checked;
        setNotifyBit(after, TONE_MODE, checked == 0);
        break;
      case Setting::VOLUME: after.volume = checked; break;
      case Setting::MELODY:
        after.melody = after.melody_dm = after.melody_mention = after.melody_system = checked;
        break;
      case Setting::BOARD_LED: after.board_led = checked; break;
      case Setting::UNREAD_LED:
        after.unread_led = checked;
        setNotifyBit(after, GPIO_MODE, checked != 0);
        break;
      case Setting::VIBRATION:
        after.vibe_quiet = checked == 0;
        setNotifyBit(after, VIBE_MODE, checked != 0);
        break;
      case Setting::GPS: after.gps = checked; after.gps_source = 0; break;
      case Setting::BATTERY_PROTECTION: after.battery_protection = checked; break;
      case Setting::MUTED: after.muted = checked; after.night_quiet = 0; break;
    }
    after.profile = 0;
    if (!commit(before, after, battery_changed)) response(reply, capacity, "ERR settings storage");
    else snprintf(reply, capacity, "OK settings set key=%s value=%lu", key, static_cast<unsigned long>(value));
  }
  return true;
}

bool DeviceSettings::handleApi(const char* command, char* reply, size_t capacity,
                               bool allow_mutation) {
  static_assert(48 + 2 * MELODY_NAME_MAX < REPLY_CAPACITY, "Melody record must fit the response");
  if (reply == nullptr || capacity < REPLY_CAPACITY) {
    response(reply, capacity, "ERR api buffer");
    return true;
  }
  if (!_hooks.read || !_hooks.write || !_hooks.save || !_hooks.apply ||
      !_hooks.caps || !_hooks.batteryMilliVolts || !_hooks.adcMultiplier || !_hooks.millis) {
    response(reply, capacity, "ERR api unavailable");
    return true;
  }
  if (strncmp(command, "api melody ", 11) == 0) {
    uint32_t id;
    const DeviceSettingsCaps caps = _hooks.caps();
    if (!unsignedNumber(command + 11, id)) response(reply, capacity, "ERR api invalid");
    else if (!caps.sound || !_hooks.melodyName) response(reply, capacity, "ERR api unsupported");
    else if (id > caps.melody_max) response(reply, capacity, "ERR api range");
    else {
      const char* name = _hooks.melodyName(static_cast<uint8_t>(id));
      size_t length = 0;
      if (name) while (length <= MELODY_NAME_MAX && name[length]) ++length;
      if (length == 0 || length > MELODY_NAME_MAX) {
        response(reply, capacity, "ERR api internal");
      } else {
        // Hex keeps arbitrary UTF-8 labels out of the ASCII record grammar.
        static const char hex[] = "0123456789abcdef";
        const int prefix = snprintf(reply, capacity, "OK api melody id=%lu name_hex=",
                                    static_cast<unsigned long>(id));
        size_t position = static_cast<size_t>(prefix);
        for (size_t i = 0; i < length; ++i) {
          const uint8_t byte = static_cast<uint8_t>(name[i]);
          reply[position++] = hex[byte >> 4];
          reply[position++] = hex[byte & 15];
        }
        reply[position] = 0;
      }
    }
    return true;
  }

  if (strncmp(command, "api set ", 8) == 0) {
    const char* key_start = command + 8;
    const char* separator = strchr(key_start, ' ');
    const size_t length = separator ? static_cast<size_t>(separator - key_start) : 0;
    const bool agc = length == 9 && strncmp(key_start, "agc_reset", length) == 0;
    const bool lna = length == 7 && strncmp(key_start, "fem_lna", length) == 0;
    const bool pa = length == 6 && strncmp(key_start, "fem_pa", length) == 0;
    const bool bridge = length == 6 && strncmp(key_start, "bridge", length) == 0;
    if (agc || lna || pa || bridge) {
      uint32_t value;
      const DeviceSettingsCaps caps = _hooks.caps();
      const bool supported = agc ? caps.agc_reset : lna ? caps.fem_lna : pa ? caps.fem_pa :
                             caps.bridge && _hooks.setToneBridge;
      if (!allow_mutation) response(reply, capacity, "ERR api readonly");
      else if (!unsignedNumber(separator + 1, value)) response(reply, capacity, "ERR api invalid");
      else if (!supported) response(reply, capacity, "ERR api unsupported");
      else if (value > 1) response(reply, capacity, "ERR api range");
      else if (bridge) {
        const bool changed = (_hooks.read().bridge != 0) != (value != 0);
        if (changed && !_hooks.setToneBridge(value != 0)) {
          response(reply, capacity, "ERR api storage");
        } else {
          if (changed) _preview_token = 0;
          snprintf(reply, capacity, "OK api set key=bridge value=%lu", static_cast<unsigned long>(value));
        }
      }
      else {
        const DeviceSettingsState before = _hooks.read();
        DeviceSettingsState after = before;
        const uint8_t checked = static_cast<uint8_t>(value);
        if (agc) after.agc_reset = checked;
        else if (lna) after.fem_lna = checked;
        else after.fem_pa = checked;
        after.profile = 0;
        if (!commit(before, after, false)) response(reply, capacity, "ERR api storage");
        else snprintf(reply, capacity, "OK api set key=%.*s value=%lu",
                      static_cast<int>(length), key_start, static_cast<unsigned long>(value));
      }
      return true;
    }
  }

  // Keep the v1 USB grammar and its side effects in one implementation. The
  // separate namespace permits additive API metadata without changing legacy
  // caps/get records, whose older clients deliberately reject extra fields.
  char legacy_command[96];
  const int command_length = snprintf(legacy_command, sizeof(legacy_command), "settings%s", command + 3);
  if (command_length < 0 || static_cast<size_t>(command_length) >= sizeof(legacy_command)) {
    response(reply, capacity, "ERR api invalid");
    return true;
  }
  handle(legacy_command, reply, capacity, allow_mutation);
  if (strncmp(reply, "OK settings ", 12) == 0) {
    memmove(reply + 7, reply + 12, strlen(reply + 12) + 1);
    memcpy(reply, "OK api ", 7);
  } else if (strncmp(reply, "ERR settings ", 13) == 0) {
    memmove(reply + 8, reply + 13, strlen(reply + 13) + 1);
    memcpy(reply, "ERR api ", 8);
  } else {
    response(reply, capacity, "ERR api internal");
    return true;
  }
  const size_t used = strlen(reply);
  int added = 0;
  if (strcmp(command, "api caps") == 0 && strncmp(reply, "OK ", 3) == 0) {
    const DeviceSettingsCaps caps = _hooks.caps();
    added = snprintf(reply + used, capacity - used,
                     " agc_reset=%u fem_lna=%u fem_pa=%u bridge=%u melody_names=%u",
                     caps.agc_reset, caps.fem_lna, caps.fem_pa,
                     caps.bridge && _hooks.setToneBridge ? 1U : 0U,
                     caps.sound && _hooks.melodyName ? 1U : 0U);
  } else if (strcmp(command, "api get") == 0 && strncmp(reply, "OK ", 3) == 0) {
    const DeviceSettingsState state = _hooks.read();
    added = snprintf(reply + used, capacity - used, " agc_reset=%u fem_lna=%u fem_pa=%u bridge=%u",
                     state.agc_reset, state.fem_lna, state.fem_pa, state.bridge);
  }
  if (added < 0 || static_cast<size_t>(added) >= capacity - used) {
    response(reply, capacity, "ERR api internal");
  }
  return true;
}
}  // namespace smartui
