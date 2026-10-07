#include "SmartUiConsoleCommands.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

namespace smartui {
namespace {
constexpr size_t MAX_TEXT = 156;
// Every valid friendly command fits comfortably: the longest setting name is
// 18 bytes and the production ADC parser permits at most 17 decimal bytes.
// This limit applies only after ownership is established; upstream UTF-8
// names and existing ui commands retain their full transport allowance.
constexpr size_t MAX_FRIENDLY = 64;

enum class Kind : uint8_t { NUMBER, BOOLEAN, ADC, READONLY };
struct Key { const char* name; const char* backend; Kind kind; };
const Key KEYS[] = {
    {"volume", "volume", Kind::NUMBER},
    {"vibration", "vibration", Kind::BOOLEAN},
    {"melody", "melody", Kind::NUMBER},
    {"sound_quiet", "sound_quiet", Kind::BOOLEAN},
    {"muted", "muted", Kind::BOOLEAN},
    {"board_led", "board_led", Kind::BOOLEAN},
    {"unread_led", "unread_led", Kind::BOOLEAN},
    {"gps", "gps", Kind::BOOLEAN},
    {"battery_protection", "battery_protection", Kind::BOOLEAN},
    {"agc_reset", "agc_reset", Kind::BOOLEAN},
    {"fem.lna", "fem_lna", Kind::BOOLEAN},
    {"fem.pa", "fem_pa", Kind::BOOLEAN},
    {"sound.bridge", "bridge", Kind::BOOLEAN},
    {"adc.multiplier", "adc_multiplier", Kind::ADC},
    {"adc", "adc_multiplier", Kind::ADC},
    {"adc.default", "adc_default", Kind::READONLY},
    {"battery", "battery_mv", Kind::READONLY},
    {"battery_mv", "battery_mv", Kind::READONLY},
    {"shutdown_mv", "shutdown_mv", Kind::READONLY},
};
const char* const CAPS[] = {
    "v", "adc", "sound", "board_led", "unread_led", "vibration", "gps",
    "battery_protection", "display", "melody_max", "adc_min", "adc_max",
    "agc_reset", "fem_lna", "fem_pa", "bridge", "melody_names", "adc_service",
};

struct Help { const char* topic; unsigned page; const char* text; };
const Help HELP[] = {
    {"", 1, "help TOPIC [PAGE]; sound 1-2; fem; adc 1-3; radio 1-2; connection 1-2; system; advert; led; gps. Commands lowercase; get reads, set saves."},
    {"sound", 1, "get/set volume 1..10; get/set vibration on|off; get/set melody N; melodies; melody N (name); test notification (play selected)."},
    {"sound", 2, "get/set sound_quiet on|off; get/set muted on|off; get/set sound.bridge on|off (supported piezo wiring only). caps sound; caps vibration."},
    {"fem", 1, "get/set fem.lna on|off; get/set fem.pa on|off; caps fem.lna; caps fem.pa. Only supported boards. Does not change TX power; get tx."},
    {"adc", 1, "get battery (mV); get adc.multiplier; get adc.default; set adc.multiplier DECIMAL; caps adc_min; caps adc_max. adc reset: factory value."},
    {"adc", 2, "adc preview MV (multimeter); adc apply TOKEN (save preview); adc manual (support). ProMicro preview needs a battery-only sample before USB."},
    {"adc", 3, "adc service [start|stop]: 120s calibration window, confirmed USB power only. No erase. ADC save, timeout or USB loss ends window."},
    {"radio", 1, "get radio; get freq; get/set tx DBM (board limits); set radio MHz,kHz,SF,CR; CR=5..8 means 4/5..4/8. Changes must match your mesh."},
    {"radio", 2, "get/set af; get/set dutycycle 10..100; get/set rxdelay; get/set multi.acks; get/set path.hash.mode; get/set radio.rxgain on|off."},
    {"connection", 1, "ui connection; ui mode ble|usb|wifi; ui mode status; get wifi.status; get wifi.ip. Mode switch disconnects current client."},
    {"connection", 2, "ui wifi begin; ui wifi ssid HEX; ui wifi password HEX; ui wifi test; ui wifi status; ui wifi save (test_ok only); ui wifi cancel."},
    {"system", 1, "board; ver; get/set name; set pin; get/set tz.offset; get/set battery_protection on|off; get shutdown_mv; get/set agc_reset on|off."},
    {"advert", 1, "get advert; set advert MIN: 0=off, 15,30,60,120,180. Saved schedule; not an immediate advert. Radio parameters stay unchanged."},
    {"led", 1, "get/set board_led on|off (board activity); get/set unread_led on|off (unread reminders); caps board_led; caps unread_led. Separate controls."},
    {"gps", 1, "get/set gps on|off; caps gps. Requires supported external/built-in GPS and correct wiring. Enabling GPS does not guarantee a position fix."},
};

void respond(char* reply, size_t capacity, const char* value) {
  if (reply != nullptr && capacity != 0) snprintf(reply, capacity, "%s", value);
}

bool textLength(const char* text, size_t& length) {
  if (text == nullptr) return false;
  for (length = 0; length <= MAX_TEXT; ++length) if (!text[length]) return true;
  return false;
}

bool ascii(const char* text) {
  for (; *text; ++text) {
    const unsigned char c = static_cast<unsigned char>(*text);
    if (c < 32 || c > 126) return false;
  }
  return true;
}

bool word(const char* command, const char* name) {
  const size_t length = strlen(name);
  return strncmp(command, name, length) == 0 &&
         (command[length] == 0 || command[length] == ' ');
}

const Key* findKey(const char* name) {
  for (const Key& key : KEYS) if (strcmp(name, key.name) == 0) return &key;
  return nullptr;
}

bool unsignedNumber(const char* text, uint32_t* result = nullptr) {
  if (text == nullptr || !*text) return false;
  uint32_t value = 0;
  for (; *text; ++text) {
    if (*text < '0' || *text > '9' ||
        value > (UINT32_MAX - static_cast<unsigned>(*text - '0')) / 10U) return false;
    value = value * 10U + static_cast<unsigned>(*text - '0');
  }
  if (result) *result = value;
  return true;
}

// The backend performs numeric bounds/precision checks, but malformed syntax
// never reaches a mutating callback. No permissive atof, exponent or NaN.
bool decimal(const char* text) {
  if (text == nullptr || !*text) return false;
  bool digit = false, dot = false;
  for (; *text; ++text) {
    if (*text >= '0' && *text <= '9') digit = true;
    else if (*text == '.' && !dot) dot = true;
    else return false;
  }
  return digit;
}

const char* capKey(const char* name) {
  if (strcmp(name, "fem.lna") == 0) return "fem_lna";
  if (strcmp(name, "fem.pa") == 0) return "fem_pa";
  if (strcmp(name, "sound.bridge") == 0) return "bridge";
  for (const char* key : CAPS) if (strcmp(name, key) == 0) return key;
  return nullptr;
}

bool fieldView(const char* record, const char* key, const char*& value, size_t& value_length) {
  const size_t key_length = strlen(key);
  for (const char* p = record; *p;) {
    const char* end = strchr(p, ' ');
    if (end == nullptr) end = p + strlen(p);
    const size_t length = static_cast<size_t>(end - p);
    if (length > key_length + 1 && memcmp(p, key, key_length) == 0 && p[key_length] == '=') {
      value_length = length - key_length - 1;
      value = p + key_length + 1;
      return true;
    }
    p = *end ? end + 1 : end;
  }
  return false;
}

bool field(const char* record, const char* key, char* out, size_t capacity) {
  const char* value = nullptr;
  size_t length = 0;
  if (!fieldView(record, key, value, length) || length >= capacity) return false;
  memcpy(out, value, length);
  out[length] = 0;
  return true;
}

bool backendCall(SmartUiConsoleExecute execute, const char* command, char* backend,
                 char* reply, size_t capacity) {
  memset(backend, 0, MAX_TEXT + 1);
  if (!execute || !execute(command, backend, MAX_TEXT + 1)) {
    respond(reply, capacity, "Error: unsupported");
    return false;
  }
  size_t length = 0;
  if (!textLength(backend, length) || !ascii(backend)) {
    respond(reply, capacity, "Error: internal");
    return false;
  }
  if (strncmp(backend, "ERR ui ", 7) == 0) {
    // The caller may use its reply buffer as backend scratch. Equal-size
    // prefixes allow an in-place rename without overlapping snprintf input.
    if (reply != backend) memcpy(reply, backend, length + 1);
    memcpy(reply, "Error: ", 7);
    return false;
  }
  if (strncmp(backend, "OK ui ", 6) != 0) {
    respond(reply, capacity, "Error: internal");
    return false;
  }
  return true;
}

bool invoke(SmartUiConsoleExecute execute, const char* command, char* reply,
            size_t capacity, bool value_only = false, bool plain_ok = false) {
  if (reply == nullptr || capacity <= MAX_TEXT) {
    respond(reply, capacity, "Error: buffer");
    return true;
  }
  // Reuse the wire reply instead of nesting another 157-byte scratch buffer
  // above DeviceSettings' existing transaction buffers on the nRF52 stack.
  if (!backendCall(execute, command, reply, reply, capacity)) return true;
  if (plain_ok) respond(reply, capacity, "OK");
  else if (value_only) {
    const char* value = nullptr;
    size_t length = 0;
    if (!fieldView(reply, "value", value, length) || length >= 64)
      respond(reply, capacity, "Error: internal");
    else {
      memmove(reply + 2, value, length);
      reply[length + 2] = 0;
      memcpy(reply, "> ", 2);
    }
  } else if (strncmp(reply, "OK ui advert ", 13) == 0) {
    memmove(reply + 2, reply + 13, strlen(reply + 13) + 1);
    memcpy(reply, "> ", 2);
  } else {
    memmove(reply + 3, reply + 6, strlen(reply + 6) + 1);
    memcpy(reply, "OK ", 3);
  }
  return true;
}

int hexDigit(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

bool utf8Printable(const char* text, size_t length) {
  for (size_t i = 0; i < length;) {
    const uint8_t first = static_cast<uint8_t>(text[i++]);
    if (first < 0x80) {
      if (first < 0x20 || first == 0x7f) return false;
      continue;
    }
    unsigned following;
    uint32_t code, minimum;
    if (first >= 0xc2 && first <= 0xdf) { following = 1; code = first & 0x1f; minimum = 0x80; }
    else if (first >= 0xe0 && first <= 0xef) { following = 2; code = first & 0x0f; minimum = 0x800; }
    else if (first >= 0xf0 && first <= 0xf4) { following = 3; code = first & 7; minimum = 0x10000; }
    else return false;
    if (following > length - i) return false;
    while (following--) {
      const uint8_t c = static_cast<uint8_t>(text[i++]);
      if ((c & 0xc0) != 0x80) return false;
      code = (code << 6) | (c & 0x3f);
    }
    if (code < minimum || code > 0x10ffff || (code >= 0xd800 && code <= 0xdfff) ||
        (code >= 0x80 && code <= 0x9f) || code == 0x2028 || code == 0x2029 ||
        (code >= 0x202a && code <= 0x202e) || (code >= 0x2066 && code <= 0x2069)) return false;
  }
  return true;
}

bool melody(SmartUiConsoleExecute execute, const char* id, char* reply, size_t capacity) {
  char command[24];
  snprintf(command, sizeof(command), "ui melody %s", id);
  if (!backendCall(execute, command, reply, reply, capacity)) return true;
  char returned_id[16];
  const char* hex = nullptr;
  size_t length = 0;
  if (!field(reply, "id", returned_id, sizeof(returned_id)) ||
      !unsignedNumber(returned_id) || !fieldView(reply, "name_hex", hex, length)) {
    respond(reply, capacity, "Error: internal"); return true;
  }
  const size_t prefix = strlen(returned_id) + 4;  // "> ID: "
  // Decode toward the beginning of the same buffer. The entire encoded name
  // must start after the new prefix, so no unread hex is overwritten.
  if (!length || (length & 1) != 0 || prefix >= static_cast<size_t>(hex - reply) ||
      prefix + length / 2 > MAX_TEXT) {
    respond(reply, capacity, "Error: internal"); return true;
  }
  for (size_t i = 0; i < length; i += 2) {
    const int hi = hexDigit(hex[i]), lo = hexDigit(hex[i + 1]);
    if (hi < 0 || lo < 0) { respond(reply, capacity, "Error: internal"); return true; }
    reply[prefix + i / 2] = static_cast<char>((hi << 4) | lo);
  }
  reply[prefix + length / 2] = 0;
  if (!utf8Printable(reply + prefix, length / 2)) { respond(reply, capacity, "Error: internal"); return true; }
  memcpy(reply, "> ", 2);
  memcpy(reply + 2, returned_id, prefix - 4);
  memcpy(reply + prefix - 2, ": ", 2);
  return true;
}
}  // namespace

bool handleSmartUiConsoleCommand(const char* command, char* reply, size_t capacity,
                                 SmartUiConsoleExecute execute) {
  if (command == nullptr) return false;
  size_t length;
  if (!textLength(command, length)) { respond(reply, capacity, "Error: invalid"); return true; }
  // First identify ownership without swallowing upstream UTF-8 node names or
  // commands such as get tx, set radio and all existing ui commands.
  const bool getter = word(command, "get"), setter = word(command, "set");
  char key_name[24] = {};
  const Key* key = nullptr;
  if ((getter || setter) && length > 4) {
    const char* end = strchr(command + 4, ' ');
    const size_t count = end ? static_cast<size_t>(end - command - 4) : length - 4;
    if (count < sizeof(key_name)) { memcpy(key_name, command + 4, count); key = findKey(key_name); }
  }
  const bool owned = key || (getter && strcmp(key_name, "caps") == 0) ||
      ((getter || setter) && strcmp(key_name, "advert") == 0) ||
      word(command, "help") || word(command, "caps") || word(command, "adc") ||
      word(command, "melody") || word(command, "melodies") || word(command, "test");
  if (!owned) return false;
  if (reply == nullptr || capacity <= MAX_TEXT) { respond(reply, capacity, "Error: buffer"); return true; }
  if (length > MAX_FRIENDLY || !ascii(command) || !length ||
      command[length - 1] == ' ' || strstr(command, "  ")) {
    respond(reply, capacity, "Error: invalid"); return true;
  }
  char copy[MAX_FRIENDLY + 1];
  memcpy(copy, command, length + 1);
  char* tokens[3] = {copy};
  size_t count = 1;
  for (char* c = copy; *c; ++c) {
    if (*c != ' ') continue;
    *c = 0;
    if (count == 3) { respond(reply, capacity, "Error: invalid"); return true; }
    tokens[count++] = c + 1;
  }
  char mapped[MAX_FRIENDLY + 1];
  if (key != nullptr) {
    if (getter && count == 2) {
      snprintf(mapped, sizeof(mapped), "ui get %s", key->backend);
      return invoke(execute, mapped, reply, capacity, true);
    }
    if (!setter || count != 3) { respond(reply, capacity, "Error: invalid"); return true; }
    if (key->kind == Kind::READONLY) { respond(reply, capacity, "Error: readonly"); return true; }
    const char* value = tokens[2];
    if (key->kind == Kind::BOOLEAN) {
      if (strcmp(value, "on") == 0) value = "1";
      else if (strcmp(value, "off") == 0) value = "0";
      else if (strcmp(value, "0") != 0 && strcmp(value, "1") != 0) {
        respond(reply, capacity, "Error: range"); return true;
      }
    } else if (key->kind == Kind::ADC ? !decimal(value) : !unsignedNumber(value)) {
      respond(reply, capacity, "Error: invalid"); return true;
    }
    const int written = key->kind == Kind::ADC
        ? snprintf(mapped, sizeof(mapped), "ui adc set %s", value)
        : snprintf(mapped, sizeof(mapped), "ui set %s %s", key->backend, value);
    if (written < 0 || static_cast<size_t>(written) >= sizeof(mapped)) {
      respond(reply, capacity, "Error: invalid"); return true;
    }
    return invoke(execute, mapped, reply, capacity, false, key->kind != Kind::ADC);
  }
  if (strcmp(tokens[0], "help") == 0) {
    uint32_t page = 1;
    if (count > 3 || (count == 3 && !unsignedNumber(tokens[2], &page))) {
      respond(reply, capacity, "Error: invalid"); return true;
    }
    const char* topic = count > 1 ? tokens[1] : "";
    for (const Help& help : HELP) {
      if (strcmp(help.topic, topic) != 0 || help.page != page) continue;
      if (strlen(help.text) > MAX_TEXT) respond(reply, capacity, "Error: internal");
      else respond(reply, capacity, help.text);
      return true;
    }
    respond(reply, capacity, "Error: unknown help page; use help"); return true;
  }
  if (strcmp(tokens[0], "caps") == 0 || (getter && strcmp(key_name, "caps") == 0)) {
    const size_t index = getter ? 2 : 1;
    const char* backend_key = count == index + 1 ? capKey(tokens[index]) : nullptr;
    if (!backend_key) { respond(reply, capacity, "Error: invalid; use caps KEY"); return true; }
    snprintf(mapped, sizeof(mapped), "ui caps %s", backend_key);
    return invoke(execute, mapped, reply, capacity, true);
  }
  if (strcmp(key_name, "advert") == 0) {
    if (getter && count == 2) return invoke(execute, "ui advert", reply, capacity);
    if (setter && count == 3 && unsignedNumber(tokens[2])) {
      snprintf(mapped, sizeof(mapped), "ui advert set %s", tokens[2]);
      return invoke(execute, mapped, reply, capacity);
    }
  } else if (strcmp(tokens[0], "adc") == 0) {
    const bool simple = count == 2 && (strcmp(tokens[1], "manual") == 0 ||
        strcmp(tokens[1], "reset") == 0 || strcmp(tokens[1], "service") == 0);
    const bool number = count == 3 && (strcmp(tokens[1], "preview") == 0 ||
        strcmp(tokens[1], "apply") == 0) && unsignedNumber(tokens[2]);
    const bool service = count == 3 && strcmp(tokens[1], "service") == 0 &&
        (strcmp(tokens[2], "start") == 0 || strcmp(tokens[2], "stop") == 0);
    if (simple || number || service) {
      snprintf(mapped, sizeof(mapped), "ui %s", command);
      return invoke(execute, mapped, reply, capacity);
    }
  } else if (strcmp(tokens[0], "melody") == 0 && count == 2 && unsignedNumber(tokens[1])) {
    return melody(execute, tokens[1], reply, capacity);
  } else if (strcmp(tokens[0], "melodies") == 0 && count == 1) {
    char current[16], maximum[16];
    if (!backendCall(execute, "ui get melody", reply, reply, capacity)) return true;
    if (!field(reply, "value", current, sizeof(current)) || !unsignedNumber(current)) {
      respond(reply, capacity, "Error: internal"); return true;
    }
    if (!backendCall(execute, "ui caps melody_max", reply, reply, capacity)) return true;
    if (!field(reply, "value", maximum, sizeof(maximum)) || !unsignedNumber(maximum)) {
      respond(reply, capacity, "Error: internal"); return true;
    }
    snprintf(reply, capacity, "> current=%s max=%s; melody N: name; set melody N: select; test notification: play", current, maximum);
    return true;
  } else if (strcmp(command, "test notification") == 0) {
    return invoke(execute, "ui test", reply, capacity, false, true);
  }
  respond(reply, capacity, "Error: invalid");
  return true;
}

}  // namespace smartui
