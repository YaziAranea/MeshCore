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

int main() {
  const char* booleans[] = {"vibration", "sound_quiet", "muted", "board_led", "unread_led",
      "gps", "battery_protection", "agc_reset", "fem.lna", "fem.pa", "sound.bridge"};
  const char* backend[] = {"vibration", "sound_quiet", "muted", "board_led", "unread_led",
      "gps", "battery_protection", "agc_reset", "fem_lna", "fem_pa", "bridge"};
  for (size_t i = 0; i < sizeof(booleans) / sizeof(*booleans); ++i) {
    maps((std::string("get ") + booleans[i]).c_str(), (std::string("ui get ") + backend[i]).c_str(), "> 7");
    for (const char* value : {"on", "off", "1", "0"}) {
      const char* normalized = strcmp(value, "on") == 0 ? "1" : strcmp(value, "off") == 0 ? "0" : value;
      maps((std::string("set ") + booleans[i] + " " + value).c_str(),
           (std::string("ui set ") + backend[i] + " " + normalized).c_str(), "OK");
    }
  }
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
  for (const char* value : {"v", "adc", "sound", "board_led", "unread_led", "vibration", "gps",
      "battery_protection", "display", "melody_max", "adc_min", "adc_max", "agc_reset",
      "fem_lna", "fem_pa", "bridge", "melody_names", "adc_service"}) {
    maps((std::string("caps ") + value).c_str(), (std::string("ui caps ") + value).c_str(), "> 1");
    maps((std::string("get caps ") + value).c_str(), (std::string("ui caps ") + value).c_str(), "> 1");
  }
  maps("caps fem.lna", "ui caps fem_lna", "> 1");
  maps("get caps fem.pa", "ui caps fem_pa", "> 1");
  maps("caps sound.bridge", "ui caps bridge", "> 1");

  const unsigned before_unknown = calls;
  for (const char* command : {"get tx", "set tx 22", "get radio", "set radio 869.161,62.5,7,7",
      "board", "ver", "get name", "set name Hello mesh node", "ui get volume", "erase",
      "get wifi.pwd", "helpful", "reboot", "set fem_lna 1", "", "set name \xd0\xa2\xd0\xb5\xd1\x81\xd1\x82"}) run(command, false);
  check(calls == before_unknown);

  const unsigned before_invalid = calls;
  for (const char* command : {"set volume", "get volume 1", "set volume on", "set volume -1",
      "set volume 4294967296", "set volume 1 trailing", "set volume 1\n", "set volume 1\t",
      "set volume  1", "set volume 1 ", "set volume \xff", "set vibration ON", "set vibration 2",
      "set vibration 00", "set battery 5", "set adc.default 1", "set adc nan", "set adc inf",
      "set adc 1e2", "set adc -1", "set adc +1", "set adc 1,5", "set adc 1..5", "set adc .",
      "adc", "adc preview", "adc preview -1", "adc apply x", "adc service start now",
      "adc service maybe", "adc erase", "melody", "melody -1", "melody 4294967296",
      "melodies 1", "test", "test notification 1", "caps unknown", "caps", "get caps",
      "get caps volume", "help sound 0", "help sound 3", "help sound 1 now", "help fake",
      "set advert", "get advert 1", "set advert -1"}) check(run(command).find("Error:") == 0);
  check(run(std::string("set volume ") + std::string(160, '1')) == "Error: invalid");
  check(run(std::string("set adc ") + std::string(58, '1')) == "Error: invalid");
  run(std::string("ui wifi ssid ") + std::string(64, 'a'), false);
  run(std::string("set name ") + std::string(65, 'a'), false);
  check(calls == before_invalid);

  for (const char* command : {"set volume 7", "set fem.pa on", "adc apply 42", "adc service start",
      "set adc 1.815000", "test notification", "get volume", "help"}) {
    for (size_t capacity = 0; capacity <= 156; ++capacity) run(command, true, capacity);
  }
  check(calls == before_invalid);
  check(!smartui::handleSmartUiConsoleCommand(nullptr, nullptr, 0, execute));
  check(smartui::handleSmartUiConsoleCommand("set volume 7", nullptr, 157, execute));
  check(calls == before_invalid);

  for (const char* error : {"readonly", "busy", "storage", "source", "range", "unsupported",
      "adc_source sample=battery_required", "invalid", "token"}) {
    forced = std::string("ERR ui ") + error;
    for (const char* command : {"set volume 11", "set fem.pa on", "set adc 99.0",
        "adc preview 3320", "adc apply 42", "adc reset", "adc service start", "test notification"}) {
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
  check(run("melodies") == "> current=3 max=18; melody N: name; set melody N: select; test notification: play");

  const unsigned before_help = calls;
  for (const char* command : {"help", "help sound", "help sound 1", "help sound 2", "help fem",
      "help adc", "help adc 1", "help adc 2", "help adc 3", "help radio", "help radio 2",
      "help connection", "help connection 2", "help system", "help advert", "help led", "help gps"}) {
    check(run(command).find("Error:") != 0);
  }
  check(calls == before_help);
  check(run("help radio").find("get/set tx") != std::string::npos);
  check(run("help connection 2").find("ui wifi password HEX") != std::string::npos);

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
  printf("PASS SmartUI friendly console: %u checks (aliases, guards, ADC, UTF-8, help, bounds)\n", checks);
}
