#include "SmartUiConsoleCommands.h"

#include <cassert>
#include <cstdio>
#include <cstring>
#include <map>
#include <string>
#include <vector>

static unsigned checks = 0, calls = 0;
static std::vector<std::string> commands;
static std::string forced;
static bool accepted = true, unterminated = false;
static std::map<std::string, std::string> records;

static void check(bool result) { ++checks; assert(result); }

static bool execute(const char* command, char* reply, size_t capacity) {
  ++calls;
  commands.emplace_back(command);
  check(capacity == 157);
  check(strlen(command) <= 156);
  check(strncmp(command, "ui ", 3) == 0);
  if (unterminated) { memset(reply, 'A', capacity); return true; }
  const auto record = records.find(command);
  std::string value = !forced.empty() ? forced : record != records.end() ? record->second : "";
  if (value.empty()) {
    if (strncmp(command, "ui get ", 7) == 0)
      value = std::string("OK ui get key=") + (command + 7) + " value=7";
    else if (strncmp(command, "ui caps ", 8) == 0)
      value = std::string("OK ui caps key=") + (command + 8) + " value=1";
    else value = "OK ui set";
  }
  snprintf(reply, capacity, "%s", value.c_str());
  return accepted;
}

static std::string run(const std::string& command, bool handled = true, size_t capacity = 157) {
  char reply[180];
  memset(reply, 0x55, sizeof(reply));
  const bool result = smartui::handleSmartUiConsoleCommand(command.c_str(), reply, capacity, execute);
  check(result == handled);
  if (!result) return "";
  if (capacity == 0) return "";
  check(memchr(reply, 0, capacity) != nullptr);
  check(strlen(reply) <= 156);
  for (size_t i = capacity; i < sizeof(reply); ++i) check(reply[i] == 0x55);
  return reply;
}

static void maps(const char* command, const char* expected, const char* reply) {
  const unsigned before = calls;
  check(run(command) == reply);
  check(calls == before + 1);
  check(commands.back() == expected);
}

static std::string hex(const std::string& text) {
  static const char digits[] = "0123456789abcdef";
  std::string encoded;
  for (unsigned char c : text) { encoded += digits[c >> 4]; encoded += digits[c & 15]; }
  return encoded;
}

int main() {
  const char* booleans[] = {"vibration", "sound_quiet", "muted", "mute", "night_quiet", "board_led", "unread_led",
      "gps", "battery_protection", "agc_reset", "fem.lna", "fem.pa", "sound.bridge"};
  const char* backend[] = {"vibration", "sound_quiet", "muted", "muted", "night_quiet", "board_led", "unread_led",
      "gps", "battery_protection", "agc_reset", "fem_lna", "fem_pa", "bridge"};
  for (size_t i = 0; i < sizeof(booleans) / sizeof(*booleans); ++i) {
    maps((std::string("get ") + booleans[i]).c_str(), (std::string("ui get ") + backend[i]).c_str(), "> 7");
    for (const char* value : {"on", "off", "1", "0"}) {
      const char* normalized = strcmp(value, "on") == 0 ? "1" : strcmp(value, "off") == 0 ? "0" : value;
      maps((std::string("set ") + booleans[i] + " " + value).c_str(),
           (std::string("ui set ") + backend[i] + " " + normalized).c_str(), "OK");
    }
  }
  records["ui get sound_quiet"] = "OK ui get key=sound_quiet value=1";
  maps("get sound", "ui get sound_quiet", "> 0");
  records["ui get sound_quiet"] = "OK ui get key=sound_quiet value=0";
  maps("get sound", "ui get sound_quiet", "> 1");
  for (const char* value : {"on", "1"})
    maps((std::string("set sound ") + value).c_str(), "ui set sound_quiet 0", "OK");
  for (const char* value : {"off", "0"})
    maps((std::string("set sound ") + value).c_str(), "ui set sound_quiet 1", "OK");
  records["ui schema sound_quiet"] = "OK ui schema key=sound_quiet supported=1 min=0 max=1 step=1 options=-";
  records["ui schema muted"] = "OK ui schema key=muted supported=1 min=0 max=1 step=1 options=0,1";
  maps("schema sound", "ui schema sound_quiet", "OK schema key=sound supported=1 min=0 max=1 step=1 options=-");
  maps("schema mute", "ui schema muted", "OK schema key=mute supported=1 min=0 max=1 step=1 options=0,1");
  maps("schema sound_quiet", "ui schema sound_quiet", "OK schema key=sound_quiet supported=1 min=0 max=1 step=1 options=-");
  maps("schema muted", "ui schema muted", "OK schema key=muted supported=1 min=0 max=1 step=1 options=0,1");
  maps("schema night_quiet", "ui schema night_quiet", "OK set");
  records.erase("ui get sound_quiet");
  maps("get volume", "ui get volume", "> 7");
  maps("set volume 10", "ui set volume 10", "OK");
  maps("get melody", "ui get melody", "> 7");
  maps("set melody 12", "ui set melody 12", "OK");
  maps("get adc.multiplier", "ui get adc_multiplier", "> 7");
  maps("get adc", "ui get adc_multiplier", "> 7");
  maps("get adc.default", "ui get adc_default", "> 7");
  maps("get battery", "ui get battery_mv", "> 7");
  maps("get battery_mv", "ui get battery_mv", "> 7");
  maps("get shutdown_mv", "ui get shutdown_mv", "> 7");
  records["ui adc set 1.815000"] = "OK ui adc_set";
  maps("set adc.multiplier 1.815000", "ui adc set 1.815000", "OK adc_set");
  maps("set adc 1.815000", "ui adc set 1.815000", "OK adc_set");
  records["ui adc preview 3320"] = "OK ui adc_preview token=42 sampled_mv=4100 measured_mv=3320 multiplier=1.469707";
  maps("adc preview 3320", "ui adc preview 3320", "OK adc_preview token=42 sampled_mv=4100 measured_mv=3320 multiplier=1.469707");
  for (const char* value : {"apply 42", "manual", "reset", "service", "service start", "service stop"}) {
    maps((std::string("adc ") + value).c_str(), (std::string("ui adc ") + value).c_str(), "OK set");
  }
  records["ui advert"] = "OK ui advert interval_min=60";
  records["ui advert set 120"] = "OK ui advert interval_min=120";
  maps("get advert", "ui advert", "> interval_min=60");
  maps("set advert 120", "ui advert set 120", "> interval_min=120");
  maps("test notification", "ui test", "OK");
  maps("test", "ui test", "OK");
  records["ui sound preview"] = "OK ui sound_preview";
  maps("sound preview", "ui sound preview", "OK sound_preview");
  records["ui connection"] = "OK ui connection mode=ble client=ble caps=7 write=1";
  maps("get connection", "ui connection", "OK connection mode=ble client=ble caps=7 write=1");
  records["ui mode status"] = "OK ui mode pending=none error=none";
  maps("connection status", "ui mode status", "OK mode pending=none error=none");
  for (const char* mode : {"ble", "usb", "wifi"}) {
    const std::string wire = std::string("ui mode ") + mode;
    for (const char* state : {"pending", "active"}) {
      records[wire] = std::string("OK ui mode target=") + mode + " state=" + state;
      maps((std::string("set connection ") + mode).c_str(), wire.c_str(),
           (std::string("OK mode target=") + mode + " state=" + state).c_str());
    }
  }
  for (const char* value : {"v", "adc", "sound", "board_led", "unread_led", "vibration", "gps",
      "battery_protection", "display", "melody_max", "adc_min", "adc_max", "agc_reset",
      "fem_lna", "fem_pa", "bridge", "melody_names", "adc_service", "sound_preview", "night_quiet"}) {
    maps((std::string("caps ") + value).c_str(), (std::string("ui caps ") + value).c_str(), "> 1");
    maps((std::string("get caps ") + value).c_str(), (std::string("ui caps ") + value).c_str(), "> 1");
  }
  maps("caps fem.lna", "ui caps fem_lna", "> 1");
  maps("get caps fem.pa", "ui caps fem_pa", "> 1");
  maps("caps sound.bridge", "ui caps bridge", "> 1");

  const unsigned before_unknown = calls;
  for (const char* command : {"get tx", "set tx 22", "get radio", "set radio 869.161,62.5,7,7",
      "board", "ver", "get name", "set name Hello mesh node", "ui get volume", "erase",
      "get wifi.pwd", "helpful", "help", "help sound", "help sound 1", "help sound 0",
      "help fake", "help sound 1 now", "reboot", "set fem_lna 1", "", "replying get 1",
      "set name \xd0\xa2\xd0\xb5\xd1\x81\xd1\x82"}) run(command, false);
  check(calls == before_unknown);

  const unsigned before_invalid = calls;
  for (const char* command : {"set volume", "get volume 1", "set volume on", "set volume -1",
      "set volume 4294967296", "set volume 1 trailing", "set volume 1\n", "set volume 1\t",
      "set volume  1", "set volume 1 ", "set volume \xff", "set vibration ON", "set vibration 2",
      "set vibration 00", "set battery 5", "set adc.default 1", "set adc nan", "set adc inf",
      "set adc 1e2", "set adc -1", "set adc +1", "set adc 1,5", "set adc 1..5", "set adc .",
      "adc", "adc preview", "adc preview -1", "adc apply x", "adc service start now",
      "adc service maybe", "adc erase", "melody", "melody -1", "melody 4294967296",
      "melodies 1", "test notification 1", "test other", "caps unknown", "caps", "get caps",
      "get caps volume", "sound", "sound preview 1", "sound preview ", "sound stop",
      "set sound 2", "set sound ON", "set sound 00", "set mute maybe", "get sound 1",
      "get connection ble", "set connection", "set connection wifi extra", "set connection WIFI",
      "set connection usb|reboot", "set connection 1", "connection", "connection other",
      "connection status now", "get connection ",
      "set advert", "get advert 1", "set advert -1"}) check(run(command).find("Error:") == 0);
  check(run(std::string("set volume ") + std::string(160, '1')) == "Error: invalid");
  check(run(std::string("set adc ") + std::string(58, '1')) == "Error: invalid");
  run(std::string("ui wifi ssid ") + std::string(64, 'a'), false);
  run(std::string("set name ") + std::string(65, 'a'), false);
  check(calls == before_invalid);

  for (const char* command : {"set volume 7", "set fem.pa on", "adc apply 42", "adc service start",
      "set adc 1.815000", "test notification", "get volume", "set sound on", "get sound",
      "set mute off", "test", "sound preview", "set connection usb", "get connection",
      "connection status", "reply get 1", "reply set 1 Hello", "reply reset 1"}) {
    for (size_t capacity = 0; capacity <= 156; ++capacity) run(command, true, capacity);
  }
  check(calls == before_invalid);
  check(!smartui::handleSmartUiConsoleCommand(nullptr, nullptr, 0, execute));
  check(smartui::handleSmartUiConsoleCommand("set volume 7", nullptr, 157, execute));
  check(calls == before_invalid);

  for (const char* error : {"readonly", "busy", "storage", "source", "range", "unsupported",
      "adc_source sample=battery_required", "invalid", "token", "muted", "pin_conflict", "unconfigured"}) {
    forced = std::string("ERR ui ") + error;
    for (const char* command : {"set volume 11", "set fem.pa on", "set adc 99.0",
        "adc preview 3320", "adc apply 42", "adc reset", "adc service start", "test notification",
        "get sound", "set sound on", "set mute off", "schema sound", "schema mute", "test", "sound preview",
        "get connection", "set connection usb", "connection status",
        "reply get 1", "reply set 1 Hello", "reply reset 1"}) {
      const unsigned before = calls;
      check(run(command) == std::string("Error: ") + error);
      check(calls == before + 1);
    }
  }
  forced.clear();
  accepted = false;
  check(run("get volume") == "Error: unsupported");
  accepted = true;
  unterminated = true;
  check(run("get volume") == "Error: internal");
  unterminated = false;
  for (const char* text : {"OK", "OK api get key=volume value=1", "OK ui get value=1\n",
      "OK ui get value=\xff", "OK ui get key=volume", "garbage"}) {
    forced = text;
    check(run("get volume") == "Error: internal");
  }
  forced.clear();

  // Reply formatting now reuses the backend reply in place. Exercise each
  // maximal record/prefix conversion; no overlapping snprintf or lost fields.
  forced = "ERR ui " + std::string(149, 'e');
  check(run("set volume 7") == "Error: " + std::string(149, 'e'));
  forced = "OK ui adc_preview " + std::string(138, 'x');
  check(run("adc preview 3320") == "OK adc_preview " + std::string(138, 'x'));
  forced = "OK ui advert " + std::string(143, 'a');
  check(run("get advert") == "> " + std::string(143, 'a'));
  forced = "OK ui get key=adc_multiplier value=" + std::string(63, '9');
  check(run("get adc") == "> " + std::string(63, '9'));
  forced = "OK ui get key=adc_multiplier value=" + std::string(64, '9');
  check(run("get adc") == "Error: internal");
  forced.clear();

  records["ui melody 1"] = "OK ui melody id=1 name_hex=d09fd180d0b8d0b2d0b5d182";
  check(run("melody 1") == "> 1: \xd0\x9f\xd1\x80\xd0\xb8\xd0\xb2\xd0\xb5\xd1\x82");
  for (const char* bad : {"", "0", "zz", "00", "01", "7f", "c080", "c2", "80", "eda080", "f4908080", "e280a8", "e280ae", "e281a6"}) {
    records["ui melody 1"] = std::string("OK ui melody id=1 name_hex=") + bad;
    check(run("melody 1") == "Error: internal");
  }
  records["ui melody 1"] = "OK ui melody id=1 name_hex=";
  // Long valid UTF-8 is not cut mid-codepoint. Its encoded record still fits.
  for (unsigned i = 0; i < 21; ++i) records["ui melody 1"] += "e29883";
  check(run("melody 1").size() == 5 + 21 * 3);
  records["ui get melody"] = "OK ui get key=melody value=3";
  records["ui caps melody_max"] = "OK ui caps key=melody_max value=18";
  check(run("melodies") == "> current=3 max=18");
  for (const char* key : {"notify_mode", "important_notify_mode", "led_pin", "tone_pin", "vibe_pin",
      "melody_dm", "melody_mention", "melody_system", "tone_8bit", "high_drive", "resonance_hz",
      "offline_dm_led", "ble_dm_led", "msg_popup", "ui_font", "ui_theme", "ui_top_color",
      "ui_bottom_color", "backlight_timeout", "gps_source", "gps_interval", "advert_location", "profile"}) {
    maps((std::string("get ") + key).c_str(), (std::string("ui get ") + key).c_str(), "> 7");
    maps((std::string("set ") + key + " 1").c_str(), (std::string("ui set ") + key + " 1").c_str(), "OK");
    maps((std::string("schema ") + key).c_str(), (std::string("ui schema ") + key).c_str(), "OK set");
  }
  maps("set vibe_pin -1", "ui set vibe_pin -1", "OK");
  maps("set tone_8bit on", "ui set tone_8bit 1", "OK");
  maps("set high_drive off", "ui set high_drive 0", "OK");

  // Text replies preserve the complete payload, not a whitespace-tokenized
  // approximation. '-' is text here; only reset maps to the built-in marker.
  const std::string russian = "\xd0\x94\xd0\xb0";
  const std::string emoji = "\xf0\x9f\x98\x80";
  for (unsigned slot = 1; slot <= 9; ++slot) {
    const std::string id = std::to_string(slot);
    const std::string saved = "OK reply_saved slot=" + id;
    for (const std::string& text : {std::string("Hello"), russian, emoji,
         std::string(" one  two "), std::string("-"), std::string(64, ' ')}) {
      const std::string mapped = "ui reply set " + id + " " + hex(text);
      records[mapped] = "OK ui reply_saved slot=" + id;
      maps(("reply set " + id + " " + text).c_str(), mapped.c_str(), saved.c_str());
      records["ui reply get " + id] = "OK ui reply slot=" + id + " hex=" + hex(text);
      maps(("reply get " + id).c_str(), ("ui reply get " + id).c_str(), ("> " + text).c_str());
    }
    records["ui reply set " + id + " -"] = "OK ui reply_saved slot=" + id;
    maps(("reply reset " + id).c_str(), ("ui reply set " + id + " -").c_str(), saved.c_str());
    records["ui reply get " + id] = "OK ui reply slot=" + id + " hex=-";
    maps(("reply get " + id).c_str(), ("ui reply get " + id).c_str(),
         ("OK reply slot=" + id + " default=1").c_str());
  }
  // Both byte limits matter: 64 UTF-8 bytes become 128 hex bytes, still below
  // the 156-byte wire limit. Do not split the last code point to make it fit.
  for (const std::string& text : {std::string(64, 'a'), std::string(60, 'a') + emoji}) {
    const std::string mapped = "ui reply set 1 " + hex(text);
    records[mapped] = "OK ui reply_saved slot=1";
    maps(("reply set 1 " + text).c_str(), mapped.c_str(), "OK reply_saved slot=1");
    records["ui reply get 1"] = "OK ui reply slot=1 hex=" + hex(text);
    check(run("reply get 1") == "> " + text);
  }
  unsigned before_reply_invalid = calls;
  for (const char* command : {"reply", "reply get", "reply get ", "reply get 0", "reply get 10",
      "reply get 01", "reply get 1 ", "reply get 1 x", "reply get 1\n", "reply get -1",
      "reply set", "reply set 1", "reply set 1 ", "reply set 0 text", "reply set 10 text",
      "reply set 01 text", "reply set 1\ttext", "reply set  1 text", "reply set 1 one|two",
      "reply set 1 one\ntwo", "reply set 1 one\rtwo", "reply set 1 one\ttwo", "reply set 1 \x7f",
      "reply reset", "reply reset 0", "reply reset 10", "reply reset 01", "reply reset 1 ",
      "reply reset 1 text", "reply delete 1", "reply Set 1 text"}) {
    check(run(command) == "Error: invalid");
  }
  for (const char* text : {"\xc0\x80", "\xc2", "\x80", "\xed\xa0\x80", "\xf4\x90\x80\x80",
      "\xc2\x80", "\xe2\x80\xa8", "\xe2\x80\xae", "\xe2\x81\xa6"}) {
    check(run(std::string("reply set 1 ") + text) == "Error: invalid");
  }
  check(run("reply set 1 " + std::string(65, 'a')) == "Error: invalid");
  check(run("reply set 1 " + std::string(61, 'a') + emoji) == "Error: invalid");
  check(run("reply set 1 " + std::string(64, 'a') + "\xc2") == "Error: invalid");
  check(run("reply set 1 " + std::string(145, 'a')) == "Error: invalid");
  check(calls == before_reply_invalid);
  for (const char* bad : {"", "0", "zz", "00", "01", "7f", "7c", "c080", "c2", "80",
      "eda080", "f4908080", "c280", "e280a8", "e280ae", "e281a6"}) {
    records["ui reply get 1"] = std::string("OK ui reply slot=1 hex=") + bad;
    check(run("reply get 1") == "Error: internal");
  }
  records["ui reply get 1"] = "OK ui reply slot=1 hex=" + std::string(130, 'a');
  check(run("reply get 1") == "Error: internal");
  for (const char* bad : {"OK ui reply hex=61", "OK ui reply slot=2 hex=61",
      "OK ui reply slot=01 hex=61", "OK ui reply_saved slot=1 hex=61", "OK ui reply slot=1"}) {
    records["ui reply get 1"] = bad;
    check(run("reply get 1") == "Error: internal");
  }
  for (const char* bad : {"7", "00", "-1", "true"}) {
    records["ui get sound_quiet"] = std::string("OK ui get key=sound_quiet value=") + bad;
    check(run("get sound") == "Error: internal");
  }
  records.erase("ui get sound_quiet");
  for (const char* alias : {"sound", "mute"}) {
    const std::string source = strcmp(alias, "sound") == 0 ? "sound_quiet" : "muted";
    for (const char* bad : {"OK ui set", "OK ui schema supported=1", "OK ui schema key=other supported=1",
        "OK ui schema key=muted_extra supported=1", "OK ui schema key=sound_quiet_extra supported=1"}) {
      records["ui schema " + source] = bad;
      check(run(std::string("schema ") + alias) == "Error: internal");
    }
    records["ui schema " + source] = "OK ui schema key=" + source + " supported=0 min=0 max=1 step=1 options=-";
    check(run(std::string("schema ") + alias) == std::string("OK schema key=") + alias + " supported=0 min=0 max=1 step=1 options=-");
    // A full wire-sized schema must keep every suffix byte while shortening
    // only the key. No truncation and no backend compatibility-key rewrite.
    const std::string prefix = "OK ui schema key=" + source + " supported=1 options=";
    const std::string suffix(156 - prefix.size(), '1');
    records["ui schema " + source] = prefix + suffix;
    check(run(std::string("schema ") + alias) == std::string("OK schema key=") + alias + " supported=1 options=" + suffix);
  }

  // Every proper prefix of a mutation must remain inert unless it is itself a
  // complete command (e.g. adc service). This catches accidental prefix writes.
  for (const std::string command : {"set volume 7", "set fem.pa on", "adc service start"}) {
    for (size_t end = 0; end < command.size(); ++end) {
      const unsigned before = calls;
      char out[157];
      smartui::handleSmartUiConsoleCommand(command.substr(0, end).c_str(), out, sizeof(out), execute);
      if (command.substr(0, end) != "adc service") check(calls == before);
    }
  }
  printf("PASS SmartUI compact console: %u checks (aliases, guards, ADC, replies, UTF-8, bounds)\n", checks);
}
