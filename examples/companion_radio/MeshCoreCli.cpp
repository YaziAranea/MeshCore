#include "MeshCoreCli.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

namespace smartui {
namespace {
constexpr size_t MAX_TEXT = 156;

// Upstream settings SmartUI has no backend for. `ui set agc_reset` is the
// SmartUI switch; its fixed 60-second policy is not upstream's interval.
const char* const UNSUPPORTED_KEYS[] = {
    "cad", "int.thresh", "agc.reset.interval", "txdelay", "direct.txdelay",
};

const char* after(const char* command, const char* prefix) {
  const size_t length = strlen(prefix);
  return strncmp(command, prefix, length) == 0 ? command + length : nullptr;
}

bool isNumberStart(char c) {
  return (c >= '0' && c <= '9') || c == '-' || c == '+' || c == '.';
}

// Plain decimals only ("-3", "5.5", ".5"): no blanks, exponent, NaN or
// infinity. The characters are checked before strtof because nRF52 builds
// use -Ofast, where isfinite() cannot be relied on.
bool parseFloat(const char* text, float& value) {
  if (text == nullptr || !isNumberStart(*text)) return false;
  const char* c = text;
  if (*c == '-' || *c == '+') ++c;
  bool digits = false, dot = false;
  for (; *c; ++c) {
    if (*c >= '0' && *c <= '9') digits = true;
    else if (*c == '.' && !dot) dot = true;
    else return false;
  }
  if (!digits || c - text > 16) return false;
  char* end = nullptr;
  value = strtof(text, &end);
  return *end == 0;
}

bool parseLong(const char* text, long& value) {
  if (text == nullptr || !isNumberStart(*text) || *text == '.') return false;
  char* end = nullptr;
  value = strtol(text, &end, 10);
  return end != text && *end == 0;
}

// Upstream prints floats without trailing zeros (StrHelper::ftoa/ftoa3).
void formatFloat(char* out, size_t capacity, float value) {
  snprintf(out, capacity, "%.3f", static_cast<double>(value));
  char* dot = strchr(out, '.');
  if (dot != nullptr) {
    char* end = out + strlen(out) - 1;
    while (end > dot && *end == '0') *end-- = 0;
    if (end == dot) *end = 0;
  }
  if (strcmp(out, "-0") == 0) snprintf(out, capacity, "0");
}

// Upstream AdvertDataParser::isValidName, plus a length that fits node_name
// without cutting a UTF-8 sequence (the frame layer already checked UTF-8).
bool validName(const char* name) {
  const size_t length = strlen(name);
  if (length == 0 || length > 31) return false;
  for (const char* c = name; *c; ++c) {
    if (*c == '[' || *c == ']' || *c == '\\' || *c == ':' || *c == ',' ||
        *c == '?' || *c == '*' || static_cast<unsigned char>(*c) < 0x20) return false;
  }
  return true;
}

void respond(char* reply, size_t capacity, const char* text) {
  snprintf(reply, capacity, "%s", text);
}

void respondResult(char* reply, size_t capacity, MeshCoreCliResult result,
                   const char* ok = "OK") {
  if (result == MeshCoreCliResult::OK) respond(reply, capacity, ok);
  else if (result == MeshCoreCliResult::UNSUPPORTED) respond(reply, capacity, "Error: unsupported");
  else if (result == MeshCoreCliResult::BUSY) respond(reply, capacity, "Error: busy");
  else respond(reply, capacity, "Error: storage");
}

void dutyCycleText(char* out, size_t capacity, float airtime_factor) {
  const float duty = 100.0f / (airtime_factor + 1.0f);
  const int whole = static_cast<int>(duty);
  const int tenth = static_cast<int>((duty - whole) * 10.0f + 0.5f);
  snprintf(out, capacity, "%d.%d%%", whole, tenth);
}
}  // namespace

bool MeshCoreCli::handle(const char* command, char* reply, size_t capacity,
                         bool allow_mutation) {
  if (command == nullptr || reply == nullptr || capacity == 0) return false;
  if (capacity <= MAX_TEXT) {
    respond(reply, capacity, "Error: buffer");
    return true;
  }
  if (_hooks.read == nullptr) return false;

  for (const char* key : UNSUPPORTED_KEYS) {
    const char* get = after(command, "get ");
    const char* set = after(command, "set ");
    const size_t length = strlen(key);
    if ((get != nullptr && strcmp(get, key) == 0) ||
        (set != nullptr && strncmp(set, key, length) == 0 && set[length] == ' ')) {
      respond(reply, capacity, "Error: unsupported");
      return true;
    }
  }

  if (strcmp(command, "reboot") == 0 || strcmp(command, "poweroff") == 0 ||
      strcmp(command, "shutdown") == 0) {
    auto action = command[0] == 'r' ? _hooks.reboot : _hooks.powerOff;
    if (action == nullptr) respond(reply, capacity, "Error: unsupported");
    else respondResult(reply, capacity, action());
    return true;
  }

  const MeshCoreCliState state = _hooks.read();
  char number[24];

  if (strcmp(command, "get freq") == 0) {
    formatFloat(number, sizeof(number), state.freq);
    snprintf(reply, capacity, "> %s", number);
    return true;
  }
  if (strcmp(command, "get tx") == 0) {
    snprintf(reply, capacity, "> %d", static_cast<int>(state.tx_dbm));
    return true;
  }
  if (strcmp(command, "get af") == 0) {
    formatFloat(number, sizeof(number), state.airtime_factor);
    snprintf(reply, capacity, "> %s", number);
    return true;
  }
  if (strcmp(command, "get dutycycle") == 0) {
    dutyCycleText(number, sizeof(number), state.airtime_factor);
    snprintf(reply, capacity, "> %s", number);
    return true;
  }
  if (strcmp(command, "get rxdelay") == 0) {
    formatFloat(number, sizeof(number), state.rx_delay);
    snprintf(reply, capacity, "> %s", number);
    return true;
  }
  if (strcmp(command, "get multi.acks") == 0) {
    snprintf(reply, capacity, "> %u", static_cast<unsigned>(state.multi_acks));
    return true;
  }
  if (strcmp(command, "get path.hash.mode") == 0) {
    snprintf(reply, capacity, "> %u", static_cast<unsigned>(state.path_hash_mode));
    return true;
  }
  if (strcmp(command, "get radio.rxgain") == 0) {
    snprintf(reply, capacity, "> %s", state.rx_gain ? "on" : "off");
    return true;
  }
  if (strcmp(command, "get tz.offset") == 0) {
    // Upstream keeps whole hours; SmartUI keeps half-hour steps in minutes.
    const int minutes = state.tz_minutes;
    if (minutes % 60 == 0) snprintf(reply, capacity, "> %d", minutes / 60);
    else snprintf(reply, capacity, "> %s%d.5", minutes < 0 ? "-" : "", abs(minutes) / 60);
    return true;
  }

  if (strcmp(command, "get wifi.status") == 0 || strcmp(command, "get wifi.ip") == 0) {
    bool associated = false;
    char ip[16] = {};
    if (_hooks.wifiStatus == nullptr || !_hooks.wifiStatus(associated, ip, sizeof(ip))) {
      respond(reply, capacity, "Error: unsupported");
    } else if (command[9] == 's') {
      respond(reply, capacity, associated ? "> connected" : "> disconnected");
    } else if (associated && ip[0]) {
      snprintf(reply, capacity, "> %s", ip);
    } else {
      respond(reply, capacity, "> (not connected)");
    }
    return true;
  }
  if (strcmp(command, "get wifi.pwd") == 0) {
    respond(reply, capacity, "Error: password is not readable");
    return true;
  }
  if (after(command, "get wifi.") != nullptr || after(command, "set wifi.") != nullptr) {
    // SmartUI changes Wi-Fi only through a tested draft that is saved last.
    respond(reply, capacity, "Error: use ui wifi");
    return true;
  }

  const char* value = after(command, "set ");
  if (value == nullptr) return false;

  const char* argument = nullptr;
  enum class Key : uint8_t { NONE, NAME, PIN, TX, AF, DUTY, RXDELAY, ACKS, HASH, RXGAIN, TZ, RADIO };
  Key key = Key::NONE;
  struct Prefix { const char* text; Key key; };
  static const Prefix prefixes[] = {
      {"name ", Key::NAME}, {"pin ", Key::PIN}, {"tx ", Key::TX}, {"af ", Key::AF},
      {"dutycycle ", Key::DUTY}, {"rxdelay ", Key::RXDELAY}, {"multi.acks ", Key::ACKS},
      {"path.hash.mode ", Key::HASH}, {"radio.rxgain ", Key::RXGAIN},
      {"tz.offset ", Key::TZ}, {"radio ", Key::RADIO},
  };
  for (const Prefix& prefix : prefixes) {
    argument = after(value, prefix.text);
    if (argument != nullptr) { key = prefix.key; break; }
  }
  if (key == Key::NONE) return false;

  // Every check of the argument comes before any permission or storage work.
  long whole = 0;
  float real = 0;
  switch (key) {
    case Key::NAME:
      if (!validName(argument)) { respond(reply, capacity, "Error, bad chars"); return true; }
      break;
    case Key::PIN:
      if (!parseLong(argument, whole) || !(whole == 0 || (whole >= 100000 && whole <= 999999))) {
        respond(reply, capacity, "Error, must be 0 or 6 digits");
        return true;
      }
      break;
    case Key::TX:
      if (!parseLong(argument, whole) || whole < -9 || whole > state.max_tx_dbm) {
        snprintf(reply, capacity, "Error, must be -9 to %d", static_cast<int>(state.max_tx_dbm));
        return true;
      }
      break;
    case Key::AF:
      if (!parseFloat(argument, real) || real < 0 || real > 9) {
        respond(reply, capacity, "ERROR: af must be 0-9");
        return true;
      }
      break;
    case Key::DUTY:
      if (!parseFloat(argument, real) || real < 1 || real > 100) {
        respond(reply, capacity, "ERROR: dutycycle must be 1-100");
        return true;
      }
      break;
    case Key::RXDELAY:
      if (!parseFloat(argument, real) || real < 0 || real > 20) {
        respond(reply, capacity, "Error, must be 0-20");
        return true;
      }
      break;
    case Key::ACKS:
      if (!parseLong(argument, whole) || whole < 0 || whole > 255) {
        respond(reply, capacity, "Error, must be 0-255");
        return true;
      }
      break;
    case Key::HASH:
      if (!parseLong(argument, whole) || whole < 0 || whole > 2) {
        respond(reply, capacity, "Error, must be 0,1, or 2");
        return true;
      }
      break;
    case Key::RXGAIN:
      if (strcmp(argument, "on") != 0 && strcmp(argument, "off") != 0) {
        respond(reply, capacity, "Error, must be on or off");
        return true;
      }
      break;
    case Key::TZ:
      if (!parseFloat(argument, real) || real < -12 || real > 14) {
        respond(reply, capacity, "Error, must be from -12 to +14");
        return true;
      }
      if (fabsf(real * 2.0f - roundf(real * 2.0f)) > 0.001f) {
        respond(reply, capacity, "Error, must be whole or half hours");
        return true;
      }
      break;
    case Key::RADIO:
    case Key::NONE:
      break;
  }

  if (key == Key::RADIO) {
    // Upstream form: freq,bw,sf,cr in MHz and kHz. SmartUI applies it at once
    // with rollback, where upstream answers "OK - reboot to apply".
    char text[48];
    const size_t length = strlen(argument);
    if (length >= sizeof(text) || _hooks.radioCommand == nullptr) {
      respond(reply, capacity, length >= sizeof(text) ? "Error, invalid radio params" : "Error: unsupported");
      return true;
    }
    memcpy(text, argument, length + 1);
    const char* parts[4] = {};
    size_t count = 0;
    for (char* cursor = text;;) {
      if (count == 4) { count = 5; break; }  // A fifth field is an error, not ignored.
      parts[count++] = cursor;
      char* comma = strchr(cursor, ',');
      if (comma == nullptr) break;
      *comma = 0;
      cursor = comma + 1;
    }
    float freq = 0, bw = 0;
    long sf = 0, cr = 0;
    if (count != 4 || !parseFloat(parts[0], freq) ||
        !parseFloat(parts[1], bw) || !parseLong(parts[2], sf) || !parseLong(parts[3], cr) ||
        freq < 150 || freq > 2500 || bw < 7 || bw > 500 || sf < 5 || sf > 12 || cr < 5 || cr > 8) {
      respond(reply, capacity, "Error, invalid radio params");
      return true;
    }
    char radio_command[64], radio_reply[MAX_TEXT + 4] = {};
    snprintf(radio_command, sizeof(radio_command), "ui radio set %lu %lu %ld %ld %u",
             static_cast<unsigned long>(lroundf(freq * 1000.0f)),
             static_cast<unsigned long>(lroundf(bw * 1000.0f)), sf, cr,
             static_cast<unsigned>(state.path_hash_mode + 1));
    if (!_hooks.radioCommand(radio_command, radio_reply, sizeof(radio_reply), allow_mutation)) {
      respond(reply, capacity, "Error: unsupported");
    } else if (strncmp(radio_reply, "OK ui radio", 11) == 0) {
      respond(reply, capacity, "OK");
    } else if (strcmp(radio_reply, "ERR ui invalid") == 0) {
      respond(reply, capacity, "Error, invalid radio params");
    } else if (strcmp(radio_reply, "ERR ui repeat") == 0) {
      respond(reply, capacity, "Error, frequency not allowed while repeat is on");
    } else if (strncmp(radio_reply, "ERR ui ", 7) == 0 && strlen(radio_reply + 7) < 32) {
      snprintf(reply, capacity, "Error: %s", radio_reply + 7);
    } else {
      respond(reply, capacity, "Error: internal");
    }
    return true;
  }

  if (!allow_mutation) { respond(reply, capacity, "Error: readonly"); return true; }
  if (_hooks.busy != nullptr && _hooks.busy()) { respond(reply, capacity, "Error: busy"); return true; }

  MeshCoreCliResult result = MeshCoreCliResult::UNSUPPORTED;
  switch (key) {
    case Key::NAME:
      if (_hooks.setName) result = _hooks.setName(argument);
      respondResult(reply, capacity, result);
      break;
    case Key::PIN:
      if (_hooks.setPin) result = _hooks.setPin(static_cast<uint32_t>(whole));
      if (result == MeshCoreCliResult::OK) snprintf(reply, capacity, "> pin is now %06ld", whole);
      else respondResult(reply, capacity, result);
      break;
    case Key::TX:
      if (_hooks.setTxPower) result = _hooks.setTxPower(static_cast<int8_t>(whole));
      respondResult(reply, capacity, result);
      break;
    case Key::AF:
      if (_hooks.setTuning) result = _hooks.setTuning(state.rx_delay, real);
      respondResult(reply, capacity, result);
      break;
    case Key::DUTY: {
      const float airtime_factor = 100.0f / real - 1.0f;
      if (_hooks.setTuning) result = _hooks.setTuning(state.rx_delay, airtime_factor);
      if (result == MeshCoreCliResult::OK) {
        dutyCycleText(number, sizeof(number), _hooks.read().airtime_factor);
        snprintf(reply, capacity, "OK - %s", number);
      } else {
        respondResult(reply, capacity, result);
      }
      break;
    }
    case Key::RXDELAY:
      if (_hooks.setTuning) result = _hooks.setTuning(real, state.airtime_factor);
      respondResult(reply, capacity, result);
      break;
    case Key::ACKS:
      if (_hooks.setMultiAcks) result = _hooks.setMultiAcks(static_cast<uint8_t>(whole));
      respondResult(reply, capacity, result);
      break;
    case Key::HASH:
      if (_hooks.setPathHashMode) result = _hooks.setPathHashMode(static_cast<uint8_t>(whole));
      respondResult(reply, capacity, result);
      break;
    case Key::RXGAIN:
      if (_hooks.setRxGain) result = _hooks.setRxGain(strcmp(argument, "on") == 0);
      respondResult(reply, capacity, result);
      break;
    case Key::TZ:
      if (_hooks.setTimezoneMinutes)
        result = _hooks.setTimezoneMinutes(static_cast<int16_t>(lroundf(real * 60.0f)));
      respondResult(reply, capacity, result);
      break;
    case Key::RADIO:
    case Key::NONE:
      break;
  }
  return true;
}

}  // namespace smartui
