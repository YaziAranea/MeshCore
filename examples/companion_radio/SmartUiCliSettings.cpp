#include "SmartUiCliSettings.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

namespace smartui {
namespace {

const char* const CAP_KEYS[] = {
    "v", "adc", "sound", "board_led", "unread_led", "vibration",
    "gps", "battery_protection", "display", "melody_max", "adc_min",
    "adc_max", "agc_reset", "fem_lna", "fem_pa", "bridge",
    "melody_names", "adc_service", "schema",
};

const char* const GET_KEYS[] = {
    "battery_mv", "adc_multiplier", "adc_default", "sound_quiet",
    "volume", "melody", "board_led", "unread_led", "vibration", "gps",
    "battery_protection", "shutdown_mv", "muted", "agc_reset", "fem_lna",
    "fem_pa", "bridge",
    "notify_mode", "important_notify_mode", "led_pin", "tone_pin", "vibe_pin",
    "melody_dm", "melody_mention", "melody_system", "tone_8bit", "high_drive",
    "resonance_hz", "offline_dm_led", "ble_dm_led", "msg_popup", "ui_font",
    "ui_theme", "ui_top_color", "ui_bottom_color", "backlight_timeout",
    "gps_source", "gps_interval", "advert_location", "profile",
};

const char* const SET_KEYS[] = {
    "sound_quiet", "volume", "melody", "board_led", "unread_led",
    "vibration", "gps", "battery_protection", "muted", "agc_reset",
    "fem_lna", "fem_pa", "bridge",
    "notify_mode", "important_notify_mode", "led_pin", "tone_pin", "vibe_pin",
    "melody_dm", "melody_mention", "melody_system", "tone_8bit", "high_drive",
    "resonance_hz", "offline_dm_led", "ble_dm_led", "msg_popup", "ui_font",
    "ui_theme", "ui_top_color", "ui_bottom_color", "backlight_timeout",
    "gps_source", "gps_interval", "advert_location", "profile",
};

void response(char* reply, size_t capacity, const char* message) {
  if (reply != nullptr && capacity > 0) snprintf(reply, capacity, "%s", message);
}

bool boundedAscii(const char* text, size_t& length) {
  if (text == nullptr) return false;
  for (length = 0; length <= SMARTUI_CLI_TEXT_MAX; ++length) {
    const unsigned char c = static_cast<unsigned char>(text[length]);
    if (c == 0) return true;
    if (c < 0x20 || c > 0x7e) return false;
  }
  return false;
}

bool isUnsigned(const char* text) {
  if (text == nullptr || *text == 0) return false;
  uint32_t value = 0;
  for (; *text; ++text) {
    if (*text < '0' || *text > '9' ||
        value > (UINT32_MAX - static_cast<uint32_t>(*text - '0')) / 10U)
      return false;
    value = value * 10U + static_cast<uint32_t>(*text - '0');
  }
  return true;
}

template <size_t N>
bool allowedKey(const char* key, const char* const (&keys)[N]) {
  for (size_t i = 0; i < N; ++i)
    if (strcmp(key, keys[i]) == 0) return true;
  return false;
}

bool oneWordAfter(const char* command, const char* prefix, char* value,
                  size_t value_capacity) {
  const size_t prefix_length = strlen(prefix);
  if (strncmp(command, prefix, prefix_length) != 0 ||
      command[prefix_length] == 0 || strchr(command + prefix_length, ' ') != nullptr)
    return false;
  const size_t length = strlen(command + prefix_length);
  if (length >= value_capacity) return false;
  memcpy(value, command + prefix_length, length + 1);
  return true;
}

bool keyAndUnsigned(const char* command, const char* prefix, char* key,
                    size_t key_capacity, const char*& value) {
  const size_t prefix_length = strlen(prefix);
  if (strncmp(command, prefix, prefix_length) != 0) return false;
  const char* key_start = command + prefix_length;
  const char* separator = strchr(key_start, ' ');
  if (separator == nullptr || separator == key_start || separator[1] == 0 ||
      strchr(separator + 1, ' ') != nullptr) return false;
  const size_t key_length = static_cast<size_t>(separator - key_start);
  if (key_length >= key_capacity) return false;
  memcpy(key, key_start, key_length);
  key[key_length] = 0;
  value = separator + 1;
  return isUnsigned(value) || (strcmp(key, "vibe_pin") == 0 && strcmp(value, "-1") == 0);
}

bool validBackendReply(const char* reply, size_t limit = SMARTUI_CLI_TEXT_MAX + 1) {
  if (reply == nullptr) return false;
  size_t length = 0;
  // Backend scratch is larger than the wire contract. Validate its own bound,
  // then apply the tighter wire bound only after response transformation.
  for (; length < limit; ++length) {
    const unsigned char c = static_cast<unsigned char>(reply[length]);
    if (c == 0)
      return strncmp(reply, "OK api ", 7) == 0 ||
             strncmp(reply, "ERR api ", 8) == 0;
    if (c < 0x20 || c > 0x7e) return false;
  }
  return false;
}

bool writeChecked(char* reply, size_t capacity, const char* format,
                  const char* first = nullptr, const char* second = nullptr) {
  if (reply == nullptr || capacity == 0) return false;
  int length;
  if (second != nullptr) length = snprintf(reply, capacity, format, first, second);
  else if (first != nullptr) length = snprintf(reply, capacity, format, first);
  else length = snprintf(reply, capacity, "%s", format);
  if (length < 0 || static_cast<size_t>(length) > SMARTUI_CLI_TEXT_MAX ||
      static_cast<size_t>(length) >= capacity) {
    response(reply, capacity, "ERR ui internal");
    return false;
  }
  return true;
}

bool renameBackendReply(const char* backend, char* reply, size_t capacity) {
  if (!validBackendReply(backend)) {
    response(reply, capacity, "ERR ui internal");
    return false;
  }
  if (strncmp(backend, "OK api ", 7) == 0)
    return writeChecked(reply, capacity, "OK ui %s", backend + 7);
  return writeChecked(reply, capacity, "ERR ui %s", backend + 8);
}

bool callBackend(DeviceSettings& settings, const char* command, char* backend,
                 bool allow_mutation, size_t size = SMARTUI_CLI_TEXT_MAX + 1) {
  memset(backend, 0, size);
  return settings.handle(command, backend, size,
                         allow_mutation) && validBackendReply(backend, size);
}

bool recordValue(const char* record, const char* key, char* value,
                 size_t value_capacity) {
  const size_t key_length = strlen(key);
  const char* cursor = record;
  while (*cursor) {
    while (*cursor == ' ') ++cursor;
    const char* end = strchr(cursor, ' ');
    if (end == nullptr) end = cursor + strlen(cursor);
    const size_t token_length = static_cast<size_t>(end - cursor);
    if (token_length > key_length + 1 &&
        memcmp(cursor, key, key_length) == 0 && cursor[key_length] == '=') {
      const size_t length = token_length - key_length - 1;
      if (length == 0 || length >= value_capacity) return false;
      memcpy(value, cursor + key_length + 1, length);
      value[length] = 0;
      return true;
    }
    cursor = end;
  }
  return false;
}

__attribute__((noinline)) bool singleValue(DeviceSettings& settings, const char* backend_command,
                 const char* kind, const char* key, char* reply,
                 size_t capacity) {
  char backend[DeviceSettings::REPLY_CAPACITY];
  if (!callBackend(settings, backend_command, backend, false, sizeof(backend))) {
    response(reply, capacity, "ERR ui internal");
    return true;
  }
  if (strncmp(backend, "ERR api ", 8) == 0) {
    renameBackendReply(backend, reply, capacity);
    return true;
  }
  char value[48];
  if (!recordValue(backend, key, value, sizeof(value))) {
    response(reply, capacity, "ERR ui unsupported");
    return true;
  }
  if (!writeChecked(reply, capacity, "OK ui %s key=%s value=", kind, key))
    return true;
  const size_t used = reply != nullptr ? strlen(reply) : 0;
  const size_t value_length = strlen(value);
  if (reply == nullptr || used + value_length > SMARTUI_CLI_TEXT_MAX ||
      used + value_length >= capacity) {
    response(reply, capacity, "ERR ui internal");
  } else {
    memcpy(reply + used, value, value_length + 1);
  }
  return true;
}

}  // namespace

bool handleSmartUiSettingsCli(DeviceSettings& settings, const char* command,
                              char* reply, size_t capacity,
                              bool allow_mutation) {
  if (command == nullptr || strncmp(command, "ui", 2) != 0 ||
      (command[2] != 0 && command[2] != ' ')) return false;

  size_t command_length = 0;
  if (!boundedAscii(command, command_length)) {
    response(reply, capacity, "ERR ui invalid");
    return true;
  }
  const bool settings_command =
      strncmp(command, "ui caps", 7) == 0 ||
      strncmp(command, "ui schema", 9) == 0 ||
      strncmp(command, "ui get", 6) == 0 ||
      strncmp(command, "ui set", 6) == 0 ||
      strncmp(command, "ui adc", 6) == 0 ||
      strncmp(command, "ui melody", 9) == 0 ||
      strncmp(command, "ui test", 7) == 0;
  if (!settings_command) return false;
  if (reply == nullptr || capacity == 0) return true;
  // Refuse before invoking a mutating backend when the caller cannot hold any
  // valid maximum-size reply. This mirrors DeviceSettings' no-ACK/no-write
  // rule instead of changing flash and then returning a truncated status.
  if (capacity <= SMARTUI_CLI_TEXT_MAX) {
    response(reply, capacity, "ERR ui buffer");
    return true;
  }

  char key[24];
  if (strncmp(command, "ui schema", 9) == 0 || strncmp(command, "ui get", 6) == 0 ||
      strcmp(command, "ui caps schema") == 0) {
    const bool schema = strncmp(command, "ui schema", 9) == 0;
    const bool caps_schema = strcmp(command, "ui caps schema") == 0;
    if (!caps_schema && (!oneWordAfter(command, schema ? "ui schema " : "ui get ", key, sizeof(key)) ||
        !allowedKey(key, GET_KEYS))) {
      response(reply, capacity, "ERR ui invalid"); return true;
    }
    char mapped[56];
    snprintf(mapped, sizeof(mapped), "api%s", command + 2);
    // Compact single-key records fit directly in the caller's wire buffer.
    // Avoid another 480-byte stack record just to read one scalar setting.
    if (!callBackend(settings, mapped, reply, false, capacity)) {
      response(reply, capacity, "ERR ui internal"); return true;
    }
    if (strncmp(reply, "OK api ", 7) == 0) {
      memmove(reply + 6, reply + 7, strlen(reply + 7) + 1); memcpy(reply, "OK ui ", 6);
    } else if (strncmp(reply, "ERR api ", 8) == 0) {
      memmove(reply + 7, reply + 8, strlen(reply + 8) + 1); memcpy(reply, "ERR ui ", 7);
    }
    return true;
  }
  if (strncmp(command, "ui caps", 7) == 0) {
    if (!oneWordAfter(command, "ui caps ", key, sizeof(key)) ||
        !allowedKey(key, CAP_KEYS)) {
      response(reply, capacity, "ERR ui invalid");
      return true;
    }
    return singleValue(settings, "api caps", "caps", key, reply, capacity);
  }
  if (strncmp(command, "ui get", 6) == 0) {
    if (!oneWordAfter(command, "ui get ", key, sizeof(key)) ||
        !allowedKey(key, GET_KEYS)) {
      response(reply, capacity, "ERR ui invalid");
      return true;
    }
    return singleValue(settings, "api get", "get", key, reply, capacity);
  }
  if (strncmp(command, "ui set", 6) == 0) {
    const char* value = nullptr;
    if (!keyAndUnsigned(command, "ui set ", key, sizeof(key), value) ||
        !allowedKey(key, SET_KEYS)) {
      response(reply, capacity, "ERR ui invalid");
      return true;
    }
    char backend_command[96];
    const int length = snprintf(backend_command, sizeof(backend_command),
                                "api set %s %s", key, value);
    if (length < 0 || static_cast<size_t>(length) >= sizeof(backend_command)) {
      response(reply, capacity, "ERR ui invalid");
      return true;
    }
    char backend[SMARTUI_CLI_TEXT_MAX + 1];
    if (!callBackend(settings, backend_command, backend, allow_mutation))
      response(reply, capacity, "ERR ui internal");
    else renameBackendReply(backend, reply, capacity);
    return true;
  }

  const char* backend_prefix = nullptr;
  const char* value = nullptr;
  bool decimal_value = false;
  if (strcmp(command, "ui adc manual") == 0) {
    backend_prefix = "api adc manual";
  } else if (strncmp(command, "ui adc set", 10) == 0) {
    backend_prefix = "api adc set ";
    value = command + 10;
    decimal_value = true;
  } else if (strcmp(command, "ui adc service") == 0) {
    backend_prefix = "api adc service";
  } else if (strcmp(command, "ui adc service start") == 0) {
    backend_prefix = "api adc service start";
  } else if (strcmp(command, "ui adc service stop") == 0) {
    backend_prefix = "api adc service stop";
  } else if (strncmp(command, "ui adc preview", 14) == 0) {
    backend_prefix = "api adc preview ";
    value = command + 14;
  } else if (strncmp(command, "ui adc apply", 12) == 0) {
    backend_prefix = "api adc apply ";
    value = command + 12;
  } else if (strcmp(command, "ui adc reset") == 0) {
    backend_prefix = "api adc reset";
  } else if (strncmp(command, "ui adc", 6) == 0) {
    response(reply, capacity, "ERR ui invalid");
    return true;
  }
  if (backend_prefix != nullptr) {
    char backend_command[64];
    if (value != nullptr) {
      if (*value != ' ' || value[1] == 0 ||
          (!decimal_value && !isUnsigned(value + 1))) {
        response(reply, capacity, "ERR ui invalid");
        return true;
      }
      const int length = snprintf(backend_command, sizeof(backend_command),
                                  "%s%s", backend_prefix, value + 1);
      if (length < 0 || static_cast<size_t>(length) >= sizeof(backend_command)) {
        response(reply, capacity, "ERR ui invalid");
        return true;
      }
    } else {
      snprintf(backend_command, sizeof(backend_command), "%s", backend_prefix);
    }
    char backend[SMARTUI_CLI_TEXT_MAX + 1];
    if (!callBackend(settings, backend_command, backend, allow_mutation))
      response(reply, capacity, "ERR ui internal");
    else renameBackendReply(backend, reply, capacity);
    return true;
  }

  if (strncmp(command, "ui melody", 9) == 0) {
    if (command[9] != ' ' || !isUnsigned(command + 10)) {
      response(reply, capacity, "ERR ui invalid");
      return true;
    }
    char backend_command[48];
    const int length = snprintf(backend_command, sizeof(backend_command),
                                "api melody %s", command + 10);
    if (length < 0 || static_cast<size_t>(length) >= sizeof(backend_command)) {
      response(reply, capacity, "ERR ui invalid");
      return true;
    }
    char backend[SMARTUI_CLI_TEXT_MAX + 1];
    if (!callBackend(settings, backend_command, backend, false))
      response(reply, capacity, "ERR ui internal");
    else renameBackendReply(backend, reply, capacity);
    return true;
  }

  if (strncmp(command, "ui test", 7) == 0) {
    if (strcmp(command, "ui test") != 0) {
      response(reply, capacity, "ERR ui invalid");
      return true;
    }
    char backend[SMARTUI_CLI_TEXT_MAX + 1];
    if (!callBackend(settings, "api test", backend, allow_mutation))
      response(reply, capacity, "ERR ui internal");
    else renameBackendReply(backend, reply, capacity);
    return true;
  }

  // `ui hello`, `ui connection`, `ui mode ...` and `ui wifi ...` are routed
  // by the caller. Unknown commands remain available to that dispatcher too.
  return false;
}

}  // namespace smartui
