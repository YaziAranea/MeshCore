#include "MeshCoreCli.h"

#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>

using namespace smartui;
static MeshCoreCliState state;
static MeshCoreCliResult next_result;
static unsigned checks, writes, reboots, power_offs, radio_calls;
static bool busy, wifi_built, wifi_associated, radio_allowed;
static std::string last_name, last_radio_command, radio_reply;
static uint32_t last_pin;
static int16_t last_tz;
static MeshCoreCli cli;
#define CHECK(x) do { ++checks; assert(x); } while (0)

static MeshCoreCliState read() { return state; }
static MeshCoreCliResult write_result() { ++writes; return next_result; }
static MeshCoreCliResult setName(const char* name) { last_name = name; return write_result(); }
static MeshCoreCliResult setPin(uint32_t pin) { last_pin = pin; return write_result(); }
static MeshCoreCliResult setTx(int8_t dbm) {
  if (next_result == MeshCoreCliResult::OK) state.tx_dbm = dbm;
  return write_result();
}
static MeshCoreCliResult setTuning(float rx, float af) {
  if (next_result == MeshCoreCliResult::OK) { state.rx_delay = rx; state.airtime_factor = af; }
  return write_result();
}
static MeshCoreCliResult setAcks(uint8_t count) { state.multi_acks = count; return write_result(); }
static MeshCoreCliResult setHash(uint8_t mode) { state.path_hash_mode = mode; return write_result(); }
static MeshCoreCliResult setGain(bool on) { state.rx_gain = on; return write_result(); }
static MeshCoreCliResult setTz(int16_t minutes) { last_tz = minutes; return write_result(); }
static bool radio(const char* command, char* reply, size_t capacity, bool allowed) {
  ++radio_calls;
  last_radio_command = command;
  radio_allowed = allowed;
  CHECK(capacity > 156);
  snprintf(reply, capacity, "%s", radio_reply.c_str());
  return true;
}
static MeshCoreCliResult reboot() { ++reboots; return next_result; }
static MeshCoreCliResult powerOff() { ++power_offs; return next_result; }
static bool wifi(bool& associated, char* ip, size_t capacity) {
  if (!wifi_built) return false;
  associated = wifi_associated;
  snprintf(ip, capacity, "%s", wifi_associated ? "192.168.1.37" : "");
  return true;
}
static bool isBusy() { return busy; }

static void fresh() {
  state = {};
  state.freq = 869.618f; state.bw = 62.5f; state.sf = 8; state.cr = 8;
  state.tx_dbm = 20; state.max_tx_dbm = 22; state.airtime_factor = 1.0f;
  state.rx_delay = 0; state.multi_acks = 0; state.path_hash_mode = 1;
  state.tz_minutes = 360;
  next_result = MeshCoreCliResult::OK;
  writes = reboots = power_offs = radio_calls = 0;
  busy = wifi_built = wifi_associated = radio_allowed = false;
  last_name.clear(); last_radio_command.clear();
  radio_reply = "OK ui radio freq_khz=869618 bw_hz=62500 sf=8 cr=8 path_bytes=2 tx_dbm=20 repeat=0";
  MeshCoreCliHooks hooks;
  hooks.read = read; hooks.setName = setName; hooks.setPin = setPin;
  hooks.setTxPower = setTx; hooks.setTuning = setTuning; hooks.setMultiAcks = setAcks;
  hooks.setPathHashMode = setHash; hooks.setRxGain = setGain;
  hooks.setTimezoneMinutes = setTz; hooks.radioCommand = radio;
  hooks.reboot = reboot; hooks.powerOff = powerOff; hooks.wifiStatus = wifi;
  hooks.busy = isBusy;
  cli.begin(hooks);
}

static std::string call(const std::string& command, bool writable = true, size_t capacity = 157) {
  char buffer[514];
  memset(buffer, 0x5a, sizeof(buffer));
  CHECK(cli.handle(command.c_str(), buffer + 1, capacity, writable));
  CHECK(buffer[0] == 0x5a && buffer[capacity + 1] == 0x5a);
  CHECK(memchr(buffer + 1, 0, capacity));
  CHECK(strlen(buffer + 1) <= 156);
  return buffer + 1;
}

static bool unknown(const std::string& command) {
  char buffer[157] = {};
  return !cli.handle(command.c_str(), buffer, sizeof(buffer), true) && buffer[0] == 0;
}

int main() {
  fresh();
  // Reads use upstream's "> value" text.
  CHECK(call("get freq") == "> 869.618");
  CHECK(call("get tx") == "> 20");
  CHECK(call("get af") == "> 1");
  CHECK(call("get dutycycle") == "> 50.0%");
  CHECK(call("get rxdelay") == "> 0");
  CHECK(call("get multi.acks") == "> 0");
  CHECK(call("get path.hash.mode") == "> 1");
  CHECK(call("get radio.rxgain") == "> off");
  CHECK(call("get tz.offset") == "> 6");
  state.tz_minutes = 330; CHECK(call("get tz.offset") == "> 5.5");
  state.tz_minutes = -30; CHECK(call("get tz.offset") == "> -0.5");
  state.tz_minutes = -570; CHECK(call("get tz.offset") == "> -9.5");
  CHECK(writes == 0);

  // Commands upstream has, but SmartUI has no backend for.
  for (const char* command : {"get cad", "set cad on", "get int.thresh", "set int.thresh 14",
      "get agc.reset.interval", "set agc.reset.interval 60", "get txdelay", "set txdelay 0.5",
      "get direct.txdelay", "set direct.txdelay 0.2"}) {
    CHECK(call(command) == "Error: unsupported");
  }
  CHECK(writes == 0);

  // Commands neither firmware has stay unknown to the caller.
  for (const char* command : {"erase", "rebuild", "ls", "rm /prefs.json", "set", "get",
      "set name", "get nothing", "set nothing 1", "setname x", "get tx ", "get txx",
      "set prv.key 00", "password x", "start ota", "clkreboot", "Reboot", "reboot now"}) {
    CHECK(unknown(command));
  }

  // Names: upstream's character rule, 31 bytes, UTF-8 kept whole.
  CHECK(call("set name \xd0\x94\xd0\xb0\xd1\x87\xd0\xb0") == "OK");
  CHECK(last_name == "\xd0\x94\xd0\xb0\xd1\x87\xd0\xb0");
  for (const char* bad : {"set name a,b", "set name [x]", "set name a:b", "set name a?",
      "set name *", "set name a\\b"}) {
    CHECK(call(bad) == "Error, bad chars");
  }
  CHECK(call("set name " + std::string(31, 'n')) == "OK");
  CHECK(call("set name " + std::string(32, 'n')) == "Error, bad chars");
  const unsigned name_writes = writes;
  CHECK(call("set name x", false) == "Error: readonly" && writes == name_writes);
  busy = true;
  CHECK(call("set name x") == "Error: busy" && writes == name_writes);
  busy = false;
  next_result = MeshCoreCliResult::STORAGE;
  CHECK(call("set name x") == "Error: storage");
  next_result = MeshCoreCliResult::OK;

  // PIN: binary command's rule, upstream's reply.
  CHECK(call("set pin 123456") == "> pin is now 123456" && last_pin == 123456);
  CHECK(call("set pin 0") == "> pin is now 000000" && last_pin == 0);
  for (const char* bad : {"set pin 12345", "set pin 1234567", "set pin -1", "set pin abc",
      "set pin 12 34", "set pin 1e5", "set pin "}) {
    CHECK(call(bad) == "Error, must be 0 or 6 digits");
  }

  // TX power within this board's limit.
  CHECK(call("set tx 22") == "OK" && state.tx_dbm == 22);
  CHECK(call("set tx -9") == "OK" && state.tx_dbm == -9);
  CHECK(call("set tx 23") == "Error, must be -9 to 22");
  CHECK(call("set tx -10") == "Error, must be -9 to 22");
  CHECK(call("set tx 2.5") == "Error, must be -9 to 22");

  // Airtime factor, duty cycle and RX delay share one tuning write.
  CHECK(call("set af 2.5") == "OK" && state.airtime_factor == 2.5f && state.rx_delay == 0);
  CHECK(call("set af 10") == "ERROR: af must be 0-9");
  for (const char* bad : {"set af nan", "set af +nan", "set af -nan", "set af inf", "set af +inf",
      "set af 1e0", "set af 0x1", "set af 1 ", "set af 1..2", "set af .", "set af -",
      "set af 0.0000000000000001"}) {
    CHECK(call(bad) == "ERROR: af must be 0-9");
  }
  CHECK(call("set af .5") == "OK" && state.airtime_factor == 0.5f);
  CHECK(call("set tz.offset +nan") == "Error, must be from -12 to +14");
  CHECK(call("set dutycycle 10") == "OK - 10.0%" && fabsf(state.airtime_factor - 9.0f) < 0.001f);
  const unsigned before_bad_duty = writes;
  for (const char* bad : {"0", "1", "9", "9.99", "9.99999999999999", "-10", "101",
      "100.000000000001", "nan", "inf", "1e1", ".5", "+", "10..0"}) {
    CHECK(call(std::string("set dutycycle ") + bad) == "ERROR: dutycycle must be 10-100");
    CHECK(writes == before_bad_duty && state.airtime_factor == 9.0f);
  }
  CHECK(call("set dutycycle 100") == "OK - 100.0%" && state.airtime_factor == 0.0f);
  CHECK(call("set dutycycle +100.000") == "OK - 100.0%" && state.airtime_factor == 0.0f);
  CHECK(call("set dutycycle 49.96") == "OK - 50.0%");
  CHECK(call("get dutycycle") == "> 50.0%");
  CHECK(call("set dutycycle 99.96") == "OK - 100.0%");
  CHECK(call("get dutycycle") == "> 100.0%");
  CHECK(call("set dutycycle 10.000") == "OK - 10.0%" && state.airtime_factor == 9.0f);
  const unsigned before_blocked_duty = writes;
  CHECK(call("set dutycycle 50", false) == "Error: readonly" && writes == before_blocked_duty);
  busy = true;
  CHECK(call("set dutycycle 50") == "Error: busy" && writes == before_blocked_duty);
  busy = false;
  next_result = MeshCoreCliResult::STORAGE;
  CHECK(call("set dutycycle 50") == "Error: storage" && writes == before_blocked_duty + 1);
  CHECK(state.airtime_factor == 9.0f && call("get dutycycle") == "> 10.0%");
  next_result = MeshCoreCliResult::OK;
  CHECK(call("set rxdelay 3") == "OK" && state.rx_delay == 3.0f &&
        fabsf(state.airtime_factor - 9.0f) < 0.001f);
  CHECK(call("set rxdelay 21") == "Error, must be 0-20");

  CHECK(call("set multi.acks 1") == "OK" && state.multi_acks == 1);
  CHECK(call("set multi.acks 256") == "Error, must be 0-255");
  CHECK(call("set path.hash.mode 2") == "OK" && state.path_hash_mode == 2);
  CHECK(call("set path.hash.mode 3") == "Error, must be 0,1, or 2");
  CHECK(call("set radio.rxgain on") == "OK" && state.rx_gain);
  CHECK(call("get radio.rxgain") == "> on");
  CHECK(call("set radio.rxgain yes") == "Error, must be on or off");
  next_result = MeshCoreCliResult::UNSUPPORTED;
  CHECK(call("set radio.rxgain off") == "Error: unsupported");
  next_result = MeshCoreCliResult::BUSY;
  CHECK(call("set radio.rxgain off") == "Error: busy");
  next_result = MeshCoreCliResult::OK;

  // Time zone: whole or half hours, kept in minutes.
  CHECK(call("set tz.offset 5.5") == "OK" && last_tz == 330);
  CHECK(call("set tz.offset -3") == "OK" && last_tz == -180);
  CHECK(call("set tz.offset 14") == "OK" && last_tz == 840);
  CHECK(call("set tz.offset 15") == "Error, must be from -12 to +14");
  CHECK(call("set tz.offset 5.25") == "Error, must be whole or half hours");

  // set radio goes through the ui radio transaction with the current path bytes.
  fresh();
  CHECK(call("set radio 869.618,62.5,8,8") == "OK");
  CHECK(last_radio_command == "ui radio set 869618 62500 8 8 2" && radio_allowed);
  CHECK(call("set radio 433.175,125,9,5", false) == "OK" && !radio_allowed);
  CHECK(last_radio_command == "ui radio set 433175 125000 9 5 2");
  radio_reply = "ERR ui invalid";
  CHECK(call("set radio 869.618,62.5,8,8") == "Error, invalid radio params");
  radio_reply = "ERR ui repeat";
  CHECK(call("set radio 869.618,62.5,8,8") == "Error, frequency not allowed while repeat is on");
  radio_reply = "ERR ui readonly";
  CHECK(call("set radio 869.618,62.5,8,8") == "Error: readonly");
  radio_reply = "garbage";
  CHECK(call("set radio 869.618,62.5,8,8") == "Error: internal");
  const unsigned before_bad = radio_calls;
  for (const char* bad : {"set radio 869.618,62.5,8", "set radio 869.618,62.5,8,8,1",
      "set radio 869.618;62.5;8;8", "set radio 100,62.5,8,8", "set radio 869.618,600,8,8",
      "set radio 869.618,62.5,4,8", "set radio 869.618,62.5,8,9", "set radio 869.618,62.5,8.5,8",
      "set radio ,62.5,8,8", "set radio 869.618, 62.5,8,8"}) {
    CHECK(call(bad) == "Error, invalid radio params");
  }
  CHECK(radio_calls == before_bad);

  // Wi-Fi: status and address only. The password is never read back and
  // changes go through the tested ui wifi draft.
  CHECK(call("get wifi.status") == "Error: unsupported");
  wifi_built = true;
  CHECK(call("get wifi.status") == "> disconnected");
  CHECK(call("get wifi.ip") == "> (not connected)");
  wifi_associated = true;
  CHECK(call("get wifi.status") == "> connected");
  CHECK(call("get wifi.ip") == "> 192.168.1.37");
  CHECK(call("get wifi.pwd") == "Error: password is not readable");
  for (const char* command : {"get wifi.ssid", "set wifi.ssid Home", "set wifi.pwd secret",
      "set wifi.enabled 1", "set wifi.clear", "get wifi.enabled"}) {
    CHECK(call(command) == "Error: use ui wifi");
  }
  CHECK(writes == 0);

  // Disruptive actions must not call hardware while readonly or busy.
  for (const char* command : {"reboot", "poweroff", "shutdown"}) {
    const unsigned before_actions = reboots + power_offs;
    CHECK(call(command, false) == "Error: readonly");
    busy = true;
    CHECK(call(command, false) == "Error: readonly");
    CHECK(call(command) == "Error: busy");
    CHECK(reboots + power_offs == before_actions);
    busy = false;
    next_result = MeshCoreCliResult::OK;
    CHECK(call(command) == "OK" && reboots + power_offs == before_actions + 1);
    next_result = MeshCoreCliResult::STORAGE;
    CHECK(call(command) == "Error: storage" && reboots + power_offs == before_actions + 2);
    next_result = MeshCoreCliResult::UNSUPPORTED;
    CHECK(call(command) == "Error: unsupported" && reboots + power_offs == before_actions + 3);
  }
  CHECK(reboots == 3 && power_offs == 6);
  next_result = MeshCoreCliResult::OK;

  // Missing action hooks remain unsupported, without any hardware calls.
  MeshCoreCliHooks no_action_hooks;
  no_action_hooks.read = read;
  no_action_hooks.busy = isBusy;
  cli.begin(no_action_hooks);
  for (const char* command : {"reboot", "poweroff", "shutdown"}) {
    CHECK(call(command) == "Error: unsupported");
    CHECK(call(command, false) == "Error: readonly");
  }
  CHECK(reboots == 3 && power_offs == 6);
  fresh();

  // A caller buffer too small for a full reply changes nothing.
  CHECK(call("set tx 10", true, 156) == "Error: buffer" && writes == 0);

  // Arbitrary text never escapes the reply bound or reaches a setter unchecked.
  uint32_t random = 0x2545f491;
  for (unsigned iteration = 0; iteration < 20000; ++iteration) {
    static const char* const stems[] = {"set name ", "set pin ", "set tx ", "set af ",
        "set dutycycle ", "set rxdelay ", "set multi.acks ", "set path.hash.mode ",
        "set radio ", "set tz.offset ", "set radio.rxgain ", "get "};
    random = random * 1664525U + 1013904223U;
    std::string command = stems[random % (sizeof(stems) / sizeof(stems[0]))];
    const unsigned length = (random >> 8) % 40;
    for (unsigned i = 0; i < length; ++i) {
      random = random * 1664525U + 1013904223U;
      command += "0123456789.,-+ eaxon:"[(random >> 16) % 21];
    }
    char buffer[159];
    memset(buffer, 0x5a, sizeof(buffer));
    if (cli.handle(command.c_str(), buffer + 1, 157, true)) {
      CHECK(buffer[0] == 0x5a && buffer[158] == 0x5a && strlen(buffer + 1) <= 156);
    }
  }
  printf("PASS upstream MeshCore companion CLI names, replies, limits, permissions and fuzz (%u checks)\n", checks);
}
