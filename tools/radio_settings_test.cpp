#include "RadioSettings.h"
#include <helpers/radiolib/LoRaConfigValidation.h>
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

using namespace smartui;
static RadioSettingsState state, persisted, hardware;
static unsigned saves, writes, applies, advert_updates, checks;
static bool save_ok, busy, healthy, fail_after_save;
static unsigned radio_failures;
static RadioSettings service;
#define CHECK(x) do { ++checks; assert(x); } while (0)
static RadioSettingsState read() { return state; }
static void write(const RadioSettingsState& s) { state = s; ++writes; }
static bool save() {
  ++saves;
  if (fail_after_save) { healthy = false; radio_failures = 1; }
  if (save_ok) persisted = state;
  return save_ok;
}
static bool validate(const RadioSettingsState& s) {
  return validSX1262LoRaParams(s.frequency_mhz, s.bandwidth_khz, s.sf, s.cr);
}
static bool repeatAllowed(uint32_t khz) { return khz == 869495; }
static bool apply(const RadioSettingsState& s) {
  ++applies;
  // Simulate partial SPI mutation, including a failed rollback.
  hardware.frequency_mhz = s.frequency_mhz;
  if (radio_failures) { --radio_failures; healthy = false; return false; }
  hardware = s; healthy = true; return true;
}
static void applyAdvert() { ++advert_updates; }
static bool isBusy() { return busy; }
static bool isHealthy() { return healthy; }
static void fresh() {
  state = {};
  state.frequency_mhz = 869.161f; state.bandwidth_khz = 62.5f;
  state.sf = state.cr = 7; state.path_bytes = 1; state.tx_dbm = 20;
  state.advert_minutes = 30;
  persisted = hardware = state;
  saves = writes = applies = advert_updates = radio_failures = 0;
  save_ok = healthy = true; busy = fail_after_save = false;
  RadioSettingsHooks hooks;
  hooks.read = read; hooks.write = write; hooks.save = save; hooks.validate = validate;
  hooks.repeatAllowed = repeatAllowed; hooks.applyRadio = apply;
  hooks.applyAdvert = applyAdvert; hooks.busy = isBusy; hooks.healthy = isHealthy;
  service.begin(hooks);
}
static std::string call(const std::string& command, bool writable = true, size_t capacity = 157) {
  char buffer[514]; memset(buffer, 0x5a, sizeof(buffer));
  CHECK(service.handle(command.c_str(), buffer + 1, capacity, writable));
  CHECK(buffer[0] == 0x5a && buffer[capacity + 1] == 0x5a);
  CHECK(memchr(buffer + 1, 0, capacity));
  CHECK(strlen(buffer + 1) <= 156);
  return buffer + 1;
}
static void expectUnchanged() {
  CHECK(state.frequency_mhz == persisted.frequency_mhz);
  CHECK(state.bandwidth_khz == persisted.bandwidth_khz);
  CHECK(state.sf == persisted.sf && state.cr == persisted.cr);
  CHECK(state.path_bytes == persisted.path_bytes && state.advert_minutes == persisted.advert_minutes);
  CHECK(state.tx_dbm == 20 && state.repeat == persisted.repeat);
}
static uint32_t floatBits(float value) {
  uint32_t bits; memcpy(&bits, &value, sizeof(bits)); return bits;
}
static float drift(float value, int ulps) {
  uint32_t bits = floatBits(value) + ulps;
  memcpy(&value, &bits, sizeof(value)); return value;
}

int main() {
  for (const std::string ns : {"ui", "settings"}) {
    const std::string ok = "OK " + ns, err = "ERR " + ns;
    struct Bandwidth { uint32_t hz; float khz; };
    const Bandwidth bandwidths[] = {
      {7800,7.8f}, {10400,10.4f}, {15600,15.6f}, {20800,20.8f}, {31250,31.25f},
      {41700,41.7f}, {62500,62.5f}, {125000,125.0f}, {250000,250.0f}, {500000,500.0f}
    };
    for (const auto& bw : bandwidths) {
      fresh();
      const auto hz = std::to_string(bw.hz);
      CHECK(call(ns + " radio set 868731 " + hz + " 7 7 1") ==
          ok + " radio freq_khz=868731 bw_hz=" + hz + " sf=7 cr=7 path_bytes=1 tx_dbm=20 repeat=0");
      CHECK(floatBits(state.bandwidth_khz) == floatBits(bw.khz));
      CHECK(floatBits(persisted.bandwidth_khz) == floatBits(bw.khz));
      CHECK(floatBits(hardware.bandwidth_khz) == floatBits(bw.khz));
      CHECK(saves == 1 && applies == 1);
      for (int delta : {-1, 1}) {
        fresh();
        CHECK(call(ns + " radio set 868731 " + std::to_string(bw.hz + delta) + " 7 7 1") == err + " invalid");
        CHECK(saves == 0 && applies == 0 && writes == 0);
        expectUnchanged();
      }
      // Profiles written before the fix can contain harmless binary32 drift,
      // including a BW slightly above the nominal 500 kHz upper boundary.
      for (int ulps : {-2, -1, 1, 2}) {
        fresh();
        state.bandwidth_khz = drift(bw.khz, ulps);
        persisted = hardware = state;
        CHECK(call(ns + " radio").find("bw_hz=" + hz + " ") != std::string::npos);
        CHECK(call(ns + " radio set 868731 62500 7 7 1").find(ok + " radio ") == 0);
        CHECK(floatBits(state.bandwidth_khz) == floatBits(62.5f));
        CHECK(saves == 1 && applies == 1);
      }
    }
    // Exact user report: ProMicro 869.618 / BW62.5 / SF8 / CR4/5 / 22 dBm
    // to OMS 868.731 / BW62.5 / SF7 / CR4/7. Power must remain unchanged.
    fresh();
    state.frequency_mhz = 869.618f; state.sf = 8; state.cr = 5; state.tx_dbm = 22;
    persisted = hardware = state;
    CHECK(call(ns + " radio set 868731 62500 7 7 1") ==
        ok + " radio freq_khz=868731 bw_hz=62500 sf=7 cr=7 path_bytes=1 tx_dbm=22 repeat=0");
    CHECK(floatBits(state.bandwidth_khz) == floatBits(62.5f));
    CHECK(state.tx_dbm == 22 && persisted.tx_dbm == 22 && hardware.tx_dbm == 22);
    for (uint32_t frequency : {150000U, 960000U}) {
      fresh();
      const auto khz = std::to_string(frequency);
      CHECK(call(ns + " radio set " + khz + " 62500 7 7 1") ==
          ok + " radio freq_khz=" + khz + " bw_hz=62500 sf=7 cr=7 path_bytes=1 tx_dbm=20 repeat=0");
      CHECK(saves == 1 && applies == 1);
    }
    fresh();
    CHECK(call(ns + " radio", false) == ok + " radio freq_khz=869161 bw_hz=62500 sf=7 cr=7 path_bytes=1 tx_dbm=20 repeat=0");
    CHECK(call(ns + " advert", false) == ok + " advert interval_min=30");
    CHECK(saves == 0 && applies == 0);
    CHECK(call(ns + " radio set 868731 125000 9 8 2") ==
        ok + " radio freq_khz=868731 bw_hz=125000 sf=9 cr=8 path_bytes=2 tx_dbm=20 repeat=0");
    CHECK(applies == 1 && saves == 1 && writes == 1);
    CHECK(hardware.sf == 9 && persisted.path_bytes == 2 && state.tx_dbm == 20 && !state.repeat);
    CHECK(advert_updates == 0 && state.advert_minutes == 30);
    for (unsigned minutes : {0U, 15U, 30U, 60U, 120U, 180U}) {
      const auto target = std::to_string(minutes);
      const unsigned old_saves = saves;
      CHECK(call(ns + " advert set " + target) == ok + " advert interval_min=" + target);
      CHECK(state.advert_minutes == minutes && persisted.advert_minutes == minutes);
      CHECK(saves == old_saves + 1);
      const unsigned updates = advert_updates;
      CHECK(call(ns + " advert set " + target) == ok + " advert interval_min=" + target);
      CHECK(saves == old_saves + 1 && advert_updates == updates); // no postponement
    }
    const unsigned baseline_saves = saves;
    for (unsigned i = 0; i < 1000; ++i) {
      if (validAutoAdvertInterval(i)) continue;
      CHECK(call(ns + " advert set " + std::to_string(i)) == err + " invalid");
    }
    CHECK(saves == baseline_saves);
    const std::vector<std::string> invalid = {
      "radio set", "radio set ", "radio set 869161 62500 7 7", "radio get",
      "radio set 869161 62500 7 7 2 1", "radio set 869161 62500 7 7 2 ",
      "radio set 869161  62500 7 7 2", "radio set +869161 62500 7 7 2",
      "radio set -1 62500 7 7 2", "radio set 869.161 62500 7 7 2",
      "radio set 4294967296 62500 7 7 2", "radio set 869161 4294967296 7 7 2",
      "radio set 149999 62500 7 7 2", "radio set 960001 62500 7 7 2", "radio set 2500001 62500 7 7 2",
      "radio set 869161 500001 7 7 2", "radio set 869161 6999 7 7 2",
      "radio set 869161 62500 263 7 2", "radio set 869161 62500 7 263 2",
      "radio set 869161 62500 7 7 258", "radio set 869161 62500 7 7 0",
      "radio set 869161 62500 7 7 4", "radio set 869161 126000 7 7 2",
      "radio set 2400000 125000 7 7 2", "radio set 869161 62500 4 7 2",
      "radio set 869161 62500 13 7 2", "radio set 869161 62500 7 4 2",
      "radio set 869161 62500 7 9 2", "advert set 65566", "advert set 4294967296",
      "advert set -1", "advert set 30\n", "advert set 30 0", "advert set 30 ",
      "radio " + std::string(160, 'x'), "advert " + std::string(160, 'x'),
    };
    for (const auto& command : invalid) {
      fresh();
      CHECK(call(ns + " " + command) == err + " invalid");
      CHECK(applies == 0 && writes == 0 && saves == 0);
      expectUnchanged();
    }
    for (const auto& command : {"radio set 868731 62500 7 7 2", "advert set 60"}) {
      fresh();
      CHECK(call(ns + " " + command, false) == err + " readonly");
      CHECK(saves == 0 && applies == 0 && writes == 0);
      busy = true;
      CHECK(call(ns + " " + command) == err + " busy");
      CHECK(saves == 0 && applies == 0 && writes == 0);
      CHECK(call(ns + " advert", false) == ok + " advert interval_min=30");
      CHECK(call(ns + " radio", false).find(ok + " radio ") == 0);
      busy = false;
      CHECK(call(ns + " " + command, true, 156) == err + " buffer");
      CHECK(saves == 0 && applies == 0 && writes == 0);
    }
    fresh(); state.repeat = persisted.repeat = hardware.repeat = true;
    CHECK(call(ns + " radio set 868731 62500 7 7 2") == err + " repeat");
    CHECK(saves == 0 && applies == 0 && writes == 0);
    CHECK(call(ns + " radio set 869495 62500 7 7 2").find("repeat=1") != std::string::npos);
    CHECK(state.repeat && state.tx_dbm == 20);
    fresh(); radio_failures = 1;
    CHECK(call(ns + " radio set 868731 125000 9 8 2") == err + " radio");
    CHECK(applies == 2 && saves == 0 && writes == 0 && healthy);
    CHECK(hardware.frequency_mhz == state.frequency_mhz && hardware.sf == state.sf);
    expectUnchanged();
    fresh(); radio_failures = 2;
    CHECK(call(ns + " radio set 868731 125000 9 8 2") == err + " restore");
    CHECK(call(ns + " radio") == err + " restore");
    CHECK(applies == 2 && saves == 0 && writes == 0 && !healthy);
    expectUnchanged();
    fresh(); save_ok = false;
    CHECK(call(ns + " radio set 868731 125000 9 8 2") == err + " storage");
    CHECK(applies == 2 && saves == 1 && writes == 2 && healthy);
    CHECK(hardware.frequency_mhz == state.frequency_mhz && hardware.sf == state.sf);
    expectUnchanged();
    fresh(); save_ok = false; fail_after_save = true;
    CHECK(call(ns + " radio set 868731 125000 9 8 2") == err + " restore");
    CHECK(call(ns + " radio") == err + " restore");
    expectUnchanged();
    fresh(); save_ok = false;
    CHECK(call(ns + " advert set 60") == err + " storage");
    CHECK(advert_updates == 0 && applies == 0 && writes == 2 && saves == 1);
    expectUnchanged();
    fresh(); state.frequency_mhz = NAN;
    CHECK(call(ns + " radio") == err + " restore");
    CHECK(call(ns + " radio set 868731 125000 9 8 2") == err + " restore");
    CHECK(applies == 0 && saves == 0);
  }
  fresh(); char reply[157] = {};
  CHECK(!service.handle("ui hello", reply, sizeof(reply), true));
  CHECK(!service.handle("settings get", reply, sizeof(reply), true));
  CHECK(!service.handle(nullptr, reply, sizeof(reply), true));
  CHECK(service.handle("ui radio set 868731 62500 7 7 2", nullptr, 157, true));
  CHECK(service.handle("ui advert set 60", reply, 0, true));
  CHECK(saves == 0 && applies == 0);
  printf("PASS RadioSettings %u checks: both transports, range/overflow, rollback, repeat, intervals\n", checks);
}
