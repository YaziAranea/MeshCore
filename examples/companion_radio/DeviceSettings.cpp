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

enum class Support : uint8_t {
  ALWAYS, SOUND, VIBE, LED, BOARD_LED, GPS, BATTERY, AGC, LNA, PA, BRIDGE,
  NOTIFY, PIN_LED, PIN_TONE, PIN_VIBE, TONE_8BIT, DRIVE, RESONANCE,
  MELODIES, DISPLAY, FONT, THEME, COLOR, GPS_SOURCE, PROFILE
};
struct ScalarSetting {
  const char* key;
  uint8_t offset;
  uint8_t width;
  int32_t minimum, maximum;
  uint16_t step;
  Support support;
  bool extended;
};
#define SCALAR(key, field, lo, hi, step, support, ext) \
  {key, static_cast<uint8_t>(offsetof(DeviceSettingsState, field)), \
   static_cast<uint8_t>(sizeof(DeviceSettingsState::field)), lo, hi, step, Support::support, ext}
const ScalarSetting SCALARS[] = {
  SCALAR("sound_quiet", sound_quiet, 0, 1, 1, SOUND, false),
  SCALAR("volume", volume, 1, 10, 1, SOUND, false),
  SCALAR("melody", melody_system, 0, 255, 1, SOUND, false),
  SCALAR("board_led", board_led, 0, 1, 1, BOARD_LED, false),
  SCALAR("unread_led", unread_led, 0, 1, 1, LED, false),
  SCALAR("vibration", vibe_quiet, 0, 1, 1, VIBE, false),
  SCALAR("gps", gps, 0, 1, 1, GPS, false),
  SCALAR("battery_protection", battery_protection, 0, 1, 1, BATTERY, false),
  SCALAR("muted", muted, 0, 1, 1, ALWAYS, false),
  SCALAR("agc_reset", agc_reset, 0, 1, 1, AGC, false),
  SCALAR("fem_lna", fem_lna, 0, 1, 1, LNA, false),
  SCALAR("fem_pa", fem_pa, 0, 1, 1, PA, false),
  SCALAR("bridge", bridge, 0, 1, 1, BRIDGE, false),
  SCALAR("notify_mode", notify_mode, 0, 7, 1, NOTIFY, true),
  SCALAR("important_notify_mode", important_notify_mode, 0, 7, 1, NOTIFY, true),
  SCALAR("led_pin", led_pin, 0, 127, 1, PIN_LED, true),
  SCALAR("tone_pin", tone_pin, 0, 127, 1, PIN_TONE, true),
  SCALAR("vibe_pin", vibe_pin, -1, 127, 1, PIN_VIBE, true),
  SCALAR("melody_dm", melody_dm, 0, 255, 1, MELODIES, true),
  SCALAR("melody_mention", melody_mention, 0, 255, 1, MELODIES, true),
  SCALAR("melody_system", melody_system, 0, 255, 1, SOUND, true),
  SCALAR("tone_8bit", tone_8bit, 0, 1, 1, TONE_8BIT, true),
  SCALAR("high_drive", high_drive, 0, 1, 1, DRIVE, true),
  SCALAR("resonance_hz", resonance_hz, 1800, 4200, 400, RESONANCE, true),
  SCALAR("offline_dm_led", offline_dm_led, 0, 1, 1, LED, true),
  SCALAR("ble_dm_led", ble_dm_led, 0, 1, 1, LED, true),
  SCALAR("msg_popup", msg_popup, 0, 1, 1, DISPLAY, true),
  SCALAR("ui_font", ui_font, 0, 255, 1, FONT, true),
  SCALAR("ui_theme", ui_theme, 0, 255, 1, THEME, true),
  SCALAR("ui_top_color", ui_top_color, 0, 5, 1, COLOR, true),
  SCALAR("ui_bottom_color", ui_bottom_color, 0, 5, 1, COLOR, true),
  SCALAR("backlight_timeout", backlight_timeout, 0, 2, 1, DISPLAY, true),
  SCALAR("gps_source", gps_source, 0, 1, 1, GPS_SOURCE, true),
  SCALAR("gps_interval", gps_interval, 0, 86400, 1, GPS, true),
  SCALAR("advert_location", advert_location, 0, 1, 1, ALWAYS, true),
  SCALAR("profile", profile, 0, 3, 1, PROFILE, true),
};
#undef SCALAR
static_assert(sizeof(DeviceSettingsState) <= 64, "Keep CLI transactions small on nRF52");

const ScalarSetting* scalar(const char* key) {
  for (const auto& item : SCALARS) if (strcmp(key, item.key) == 0) return &item;
  return nullptr;
}
bool supported(const ScalarSetting& item, const DeviceSettingsCaps& c) {
  switch (item.support) {
    case Support::ALWAYS: return true;
    case Support::SOUND: return c.sound;
    case Support::VIBE: return c.vibration;
    case Support::LED: return c.unread_led;
    case Support::BOARD_LED: return c.board_led;
    case Support::GPS: return c.gps;
    case Support::BATTERY: return c.battery_protection;
    case Support::AGC: return c.agc_reset;
    case Support::LNA: return c.fem_lna;
    case Support::PA: return c.fem_pa;
    case Support::BRIDGE: return c.bridge;
    case Support::NOTIFY: return c.notify_mask != 0;
    case Support::PIN_LED: return c.notify_pins && c.unread_led;
    case Support::PIN_TONE: return c.notify_pins && c.sound;
    case Support::PIN_VIBE: return c.notify_pins;
    case Support::TONE_8BIT: return c.tone_8bit && c.sound;
    case Support::DRIVE: return c.high_drive && c.sound;
    case Support::RESONANCE: return c.resonance && c.sound;
    case Support::MELODIES: return c.separate_melodies && c.sound;
    case Support::DISPLAY: return c.display;
    case Support::FONT: return c.display && c.font_count > 1;
    case Support::THEME: return c.display && c.theme_count > 1;
    case Support::COLOR: return c.display && c.colors;
    case Support::GPS_SOURCE: return c.phone_gps || c.gps;
    case Support::PROFILE: return c.profiles;
  }
  return false;
}
int32_t maximum(const ScalarSetting& item, const DeviceSettingsCaps& c) {
  if (strncmp(item.key, "melody", 6) == 0) return c.melody_max;
  if (item.support == Support::FONT) return c.font_count ? c.font_count - 1 : 0;
  if (item.support == Support::THEME) return c.theme_count ? c.theme_count - 1 : 0;
  return item.maximum;
}
int32_t scalarValue(const ScalarSetting& item, const DeviceSettingsState& state) {
  const uint8_t* data = reinterpret_cast<const uint8_t*>(&state) + item.offset;
  if (item.support == Support::PIN_LED || item.support == Support::PIN_TONE ||
      item.support == Support::PIN_VIBE) return *reinterpret_cast<const int8_t*>(data);
  if (item.width == 1) return *data;
  if (item.width == 2) { uint16_t value; memcpy(&value, data, 2); return value; }
  uint32_t value; memcpy(&value, data, 4); return static_cast<int32_t>(value);
}
void scalarWrite(const ScalarSetting& item, DeviceSettingsState& state, int32_t value) {
  uint8_t* data = reinterpret_cast<uint8_t*>(&state) + item.offset;
  if (item.width == 1) *data = static_cast<uint8_t>(value);
  else if (item.width == 2) { const uint16_t v = value; memcpy(data, &v, 2); }
  else { const uint32_t v = value; memcpy(data, &v, 4); }
}

bool unsignedNumber(const char* text, uint32_t& number) {
  if (text == nullptr || *text == 0) return false;
  number = 0;
  for (; *text; ++text) {
    if (*text < '0' || *text > '9' || number > (UINT32_MAX - (*text - '0')) / 10U) return false;
    number = number * 10U + (*text - '0');
  }
  return true;
}

bool adcDecimal(const char* text, float& number) {
  // Decimal ASCII only. Parse bounded integer micro-units before touching
  // floats, so -Ofast cannot turn NaN/Inf/exponent input into an accepted ADC.
  if (text == nullptr || *text < '0' || *text > '9') return false;
  uint32_t whole = 0, fraction = 0, scale = 1;
  unsigned length = 0, digits = 0;
  while (*text >= '0' && *text <= '9') {
    const uint32_t digit = static_cast<uint32_t>(*text++ - '0');
    if (++length > 17 || whole > (UINT32_MAX - digit) / 10U) return false;
    whole = whole * 10U + digit;
  }
  if (*text == '.') {
    ++text;
    if (++length > 17) return false;
    while (*text >= '0' && *text <= '9') {
      if (++digits > 6 || ++length > 17) return false;
      fraction = fraction * 10U + static_cast<uint32_t>(*text++ - '0');
      scale *= 10U;
    }
    if (digits == 0) return false;
  }
  if (*text != 0) return false;
  const uint64_t micro_units = static_cast<uint64_t>(whole) * 1000000U +
      static_cast<uint64_t>(fraction) * (1000000U / scale);
  if (micro_units > UINT32_MAX) return false;
  number = static_cast<float>(static_cast<double>(micro_units) / 1000000.0);
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
  return handleSettings(command, reply, capacity, allow_mutation);
}

bool DeviceSettings::handleSettings(const char* command, char* reply, size_t capacity,
                                    bool allow_mutation) {
  const bool bulk = strcmp(command, "settings caps") == 0 || strcmp(command, "settings get") == 0;
  if (reply == nullptr || capacity < (bulk ? REPLY_CAPACITY : 157)) {
    response(reply, capacity, "ERR settings buffer");
    return true;
  }
  if (!_hooks.read || !_hooks.write || !_hooks.save || !_hooks.apply ||
      !_hooks.caps || !_hooks.batteryMilliVolts || !_hooks.adcMultiplier || !_hooks.millis) {
    response(reply, capacity, "ERR settings unavailable");
    return true;
  }
  if (handleExtended(command, reply, capacity, allow_mutation)) return true;
  const DeviceSettingsCaps caps = _hooks.caps();
  const DeviceSettingsState before = _hooks.read();
  if (strcmp(command, "settings caps") == 0) {
    snprintf(reply, capacity,
        "OK settings caps v=1 adc=%u sound=%u board_led=%u unread_led=%u vibration=%u gps=%u battery_protection=%u display=%u melody_max=%u adc_min=%.6f adc_max=%.6f adc_service=%u",
        caps.adc, caps.sound, caps.board_led, caps.unread_led, caps.vibration, caps.gps,
        caps.battery_protection, caps.display, caps.melody_max,
        mesh::adcCalibrationMinimum(caps.adc_default), mesh::adcCalibrationMaximum(caps.adc_default),
        caps.adc_service ? 1U : 0U);
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
  if (strcmp(command, "settings adc manual") == 0) {
    snprintf(reply, capacity, "OK settings adc_manual supported=%u", caps.adc ? 1U : 0U);
    return true;
  }
  if (strcmp(command, "settings adc service") == 0 ||
      strncmp(command, "settings adc service ", 21) == 0) {
    const char* action = command[20] ? command + 21 : "";
    if (action[0] && strcmp(action, "start") != 0 && strcmp(action, "stop") != 0)
      response(reply, capacity, "ERR settings invalid");
    else if (strcmp(action, "start") == 0 && !allow_mutation)
      response(reply, capacity, "ERR settings readonly");
    else if (_hooks.adcService) _hooks.adcService(action, reply, capacity, allow_mutation);
    else if (strcmp(action, "start") == 0) response(reply, capacity, "ERR settings unsupported");
    else response(reply, capacity,
        "OK settings adc_service supported=0 active=0 remaining_ms=0 external=0");
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
  if (strncmp(command, "settings adc set ", 17) == 0) {
    float requested, normalized;
    if (!adcDecimal(command + 17, requested))
      response(reply, capacity, "ERR settings invalid");
    else if (!caps.adc)
      response(reply, capacity, "ERR settings unsupported");
    // Zero is reserved for the explicit reset command, not a manual override.
    else if (requested <= 0.0f ||
             !mesh::normalizeAdcMultiplier(requested, caps.adc_default, normalized))
      response(reply, capacity, "ERR settings range");
    else {
      after.adc_override = normalized;
      after.profile = 0;
      const bool saved = commit(before, after, true);
      if (saved && _hooks.adcCommitted) _hooks.adcCommitted();
      response(reply, capacity, saved ? "OK settings adc_set" : "ERR settings storage");
    }
    return true;
  }
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
      const bool saved = commit(before, after, true);
      if (saved && _hooks.adcCommitted) _hooks.adcCommitted();
      response(reply, capacity, saved ?
          "OK settings adc_apply" : "ERR settings storage");
    }
    return true;
  }
  if (strcmp(command, "settings adc reset") == 0) {
    if (!caps.adc) response(reply, capacity, "ERR settings unsupported");
    else {
      after.adc_override = 0;
      after.profile = 0;
      const bool saved = commit(before, after, true);
      if (saved && _hooks.adcCommitted) _hooks.adcCommitted();
      response(reply, capacity, saved ?
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

bool DeviceSettings::handleExtended(const char* command, char* reply, size_t capacity,
                                    bool allow_mutation) {
  if (strcmp(command, "settings caps schema") == 0) {
    response(reply, capacity, "OK settings caps key=schema value=1");
    return true;
  }
  const bool schema = strncmp(command, "settings schema ", 16) == 0;
  const bool get = strncmp(command, "settings get ", 13) == 0;
  const bool set = strncmp(command, "settings set ", 13) == 0;
  if (!schema && !get && !set) return false;
  const char* start = command + (schema ? 16 : 13);
  const char* space = strchr(start, ' ');
  const size_t length = space ? static_cast<size_t>(space - start) : strlen(start);
  char key[24];
  if (!length || length >= sizeof(key) || ((schema || get) && space)) {
    response(reply, capacity, "ERR settings invalid"); return true;
  }
  memcpy(key, start, length); key[length] = 0;
  const ScalarSetting* item = scalar(key);
  const bool api_extra = item && (item->support == Support::AGC || item->support == Support::LNA ||
      item->support == Support::PA || item->support == Support::BRIDGE);
  if (set && (!item || (!item->extended && !api_extra))) return false;
  const DeviceSettingsCaps caps = _hooks.caps();
  if (schema) {
    if (!item) { response(reply, capacity, "ERR settings unsupported"); return true; }
    char options[88] = "-";
    if (supported(*item, caps)) {
      if (item->support == Support::PIN_LED || item->support == Support::PIN_TONE ||
          item->support == Support::PIN_VIBE) {
        if (_hooks.pinOptions) _hooks.pinOptions(key, options, sizeof(options));
      } else if (item->support == Support::NOTIFY) {
        size_t used = 0;
        for (unsigned value = 0; value < 8; ++value) {
          if (value & ~caps.notify_mask) continue;
          used += snprintf(options + used, sizeof(options) - used, "%s%u", used ? "," : "", value);
        }
      } else if (item->support == Support::GPS_SOURCE) {
        snprintf(options, sizeof(options), "%s", caps.gps ? (caps.phone_gps ? "0,1" : "0") : "1");
      }
    }
    const int count = snprintf(reply, capacity,
        "OK settings schema key=%s supported=%u min=%ld max=%ld step=%u options=%s",
        key, supported(*item, caps) ? 1U : 0U, static_cast<long>(item->minimum),
        static_cast<long>(maximum(*item, caps)), item->step, options);
    if (count < 0 || static_cast<size_t>(count) >= capacity || count > 156)
      response(reply, capacity, "ERR settings internal");
    return true;
  }
  if (get) {
    if (strcmp(key, "adc_multiplier") == 0 || strcmp(key, "adc_default") == 0) {
      snprintf(reply, capacity, "OK settings get key=%s value=%.6f", key,
          strcmp(key, "adc_multiplier") == 0 ? _hooks.adcMultiplier() : caps.adc_default);
      return true;
    }
    const DeviceSettingsState state = _hooks.read();
    int32_t value;
    if (strcmp(key, "battery_mv") == 0) value = _hooks.batteryMilliVolts();
    else if (strcmp(key, "shutdown_mv") == 0)
      value = caps.battery_protection ? (state.battery_protection ? 3200 : 2700) : 0;
    else if (!item) { response(reply, capacity, "ERR settings unsupported"); return true; }
    else if (strcmp(key, "sound_quiet") == 0) value = (caps.effective_notify_mode & TONE_MODE) ? 0 : 1;
    else if (strcmp(key, "vibration") == 0) value = (caps.effective_notify_mode & VIBE_MODE) ? 1 : 0;
    else if (strcmp(key, "gps") == 0) value = state.gps_source == 0 ? state.gps : 0;
    else if (item->support == Support::NOTIFY) value = scalarValue(*item, state) & caps.notify_mask;
    else if ((item->support == Support::PIN_LED || item->support == Support::PIN_TONE ||
              item->support == Support::PIN_VIBE) && _hooks.pinValue) value = _hooks.pinValue(key);
    else value = scalarValue(*item, state);
    snprintf(reply, capacity, "OK settings get key=%s value=%ld", key, static_cast<long>(value));
    return true;
  }
  if (!allow_mutation) { response(reply, capacity, "ERR settings readonly"); return true; }
  if (!supported(*item, caps)) { response(reply, capacity, "ERR settings unsupported"); return true; }
  int32_t value = 0;
  uint32_t number = 0;
  if (space && strcmp(space + 1, "-1") == 0 && item->minimum == -1) value = -1;
  else if (!space || !unsignedNumber(space + 1, number) || number > INT32_MAX) {
    response(reply, capacity, "ERR settings invalid"); return true;
  } else value = number;
  if (value < item->minimum || value > maximum(*item, caps) ||
      (value - item->minimum) % item->step != 0 ||
      (item->support == Support::NOTIFY && (value & ~caps.notify_mask)) ||
      (item->support == Support::GPS_SOURCE && ((value == 0 && !caps.gps) || (value == 1 && !caps.phone_gps)))) {
    response(reply, capacity, "ERR settings range"); return true;
  }
  if ((item->support == Support::PIN_LED || item->support == Support::PIN_TONE ||
       item->support == Support::PIN_VIBE) &&
      (!_hooks.pinAllowed || !_hooks.pinAllowed(key, value))) {
    response(reply, capacity, "ERR settings pin_conflict"); return true;
  }
  if (item->support == Support::BRIDGE) {
    if (!_hooks.setToneBridge) { response(reply, capacity, "ERR settings unsupported"); return true; }
    if (!_hooks.setToneBridge(value != 0)) response(reply, capacity, "ERR settings storage");
    else { _preview_token = 0; snprintf(reply, capacity, "OK settings set key=bridge value=%ld", static_cast<long>(value)); }
    return true;
  }
  const DeviceSettingsState before = _hooks.read();
  DeviceSettingsState after = before;
  scalarWrite(*item, after, value);
  if (item->support == Support::PROFILE) {
    if (value == 1) {
      after.muted = 0; after.notify_mode = after.important_notify_mode = caps.notify_mask & GPIO_MODE;
      after.backlight_timeout = 0;
    } else if (value == 2) {
      after.muted = 0; after.notify_mode = after.important_notify_mode = caps.notify_mask;
      after.board_led = 1; after.backlight_timeout = 2;
      if (caps.high_drive) after.high_drive = 1;
    } else if (value == 3) {
      after.muted = 1; after.board_led = 0; after.backlight_timeout = 0;
      if (caps.night_theme) after.ui_theme = 1;
    }
    after.sound_quiet = (after.important_notify_mode & TONE_MODE) ? 0 : 1;
    after.vibe_quiet = (after.important_notify_mode & VIBE_MODE) ? 0 : 1;
    after.night_quiet = 0;
  } else after.profile = 0;
  if (strcmp(key, "melody_system") == 0) {
    after.melody = after.melody_system;
    if (!caps.separate_melodies) after.melody_dm = after.melody_mention = after.melody_system;
  }
  if (strcmp(key, "high_drive") == 0) after.volume = 10;
  if (item->support == Support::NOTIFY) {
    after.sound_quiet = ((after.notify_mode | after.important_notify_mode) & TONE_MODE) ? 0 : 1;
    after.vibe_quiet = ((after.notify_mode | after.important_notify_mode) & VIBE_MODE) ? 0 : 1;
  }
  if (!commit(before, after, false)) response(reply, capacity, "ERR settings storage");
  else snprintf(reply, capacity, "OK settings set key=%s value=%ld", key, static_cast<long>(value));
  return true;
}

bool DeviceSettings::handleApi(const char* command, char* reply, size_t capacity,
                               bool allow_mutation) {
  static_assert(48 + 2 * MELODY_NAME_MAX < REPLY_CAPACITY, "Melody record must fit the response");
  const bool bulk = strcmp(command, "api caps") == 0 || strcmp(command, "api get") == 0;
  if (reply == nullptr || capacity < (bulk ? REPLY_CAPACITY : 157)) {
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
        if (prefix < 0 || static_cast<size_t>(prefix) + 2 * length >= capacity) {
          response(reply, capacity, "ERR api internal");
          return true;
        }
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
  handleSettings(legacy_command, reply, capacity, allow_mutation);
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
