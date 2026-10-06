#!/usr/bin/env python3
"""Execute production ConnectionController against deterministic host stubs."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "examples/companion_radio"


ARDUINO = r'''#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <map>
#include <string>
#include <vector>

extern uint32_t fake_now;
inline unsigned long millis() { return fake_now; }

class String {
  std::string value_;
public:
  String() = default;
  String(const char* value) : value_(value ? value : "") {}
  const char* c_str() const { return value_.c_str(); }
};

class Stream {
public:
  virtual ~Stream() = default;
  virtual int available() = 0;
  virtual int read() = 0;
  virtual int availableForWrite() = 0;
  virtual size_t write(const uint8_t* data, size_t len) = 0;
};

class File;
class FakeFS {
public:
  using State = std::map<std::string, std::vector<uint8_t>>;
  State files;
  bool record_snapshots = false;
  std::vector<State> snapshots;
  bool fail_next_rename = false;
  std::string fail_remove_path;
  std::string fail_write_open_path;
  std::string short_write_path;
  std::string corrupt_flush_path;
  std::string fail_rename_from;
  std::string corrupt_rename_to;
  std::string permanent_remove_path;
  std::string permanent_write_open_path;

  void checkpoint() { if (record_snapshots) snapshots.push_back(files); }

  bool exists(const char* path) const { return files.count(path) != 0; }
  bool remove(const char* path) {
    if (permanent_remove_path == path) return false;
    if (fail_remove_path == path) {
      fail_remove_path.clear();
      return false;
    }
    const bool removed = files.erase(path) != 0;
    if (removed) checkpoint();
    return removed;
  }
  bool rename(const char* from, const char* to) {
    if (fail_next_rename || fail_rename_from == from) {
      fail_next_rename = false;
      fail_rename_from.clear();
      return false;
    }
    auto found = files.find(from);
    if (found == files.end()) return false;
    files[to] = found->second;
    files.erase(found);
    if (corrupt_rename_to == to) {
      corrupt_rename_to.clear();
      if (!files[to].empty()) files[to][0] ^= 0xff;
    }
    checkpoint();
    return true;
  }
  File open(const char* path, const char* mode, bool create = false);
};

class File {
  FakeFS* fs_ = nullptr;
  std::string path_;
  size_t offset_ = 0;
  bool open_ = false;
public:
  File() = default;
  File(FakeFS* fs, const char* path, bool write)
      : fs_(fs), path_(path), open_(fs != nullptr) {
    if (open_ && write) {
      fs_->files[path_].clear();
      fs_->checkpoint();
    }
  }
  explicit operator bool() const { return open_; }
  size_t size() const {
    auto found = fs_->files.find(path_);
    return found == fs_->files.end() ? 0 : found->second.size();
  }
  int read(uint8_t* out, size_t len) {
    if (!open_) return 0;
    auto& bytes = fs_->files[path_];
    const size_t count = std::min(len, bytes.size() - std::min(offset_, bytes.size()));
    if (count) std::memcpy(out, bytes.data() + offset_, count);
    offset_ += count;
    return static_cast<int>(count);
  }
  size_t write(const uint8_t* data, size_t len) {
    if (!open_) return 0;
    if (fs_->short_write_path == path_) {
      fs_->short_write_path.clear();
      if (len) --len;
    }
    auto& bytes = fs_->files[path_];
    if (bytes.size() < offset_ + len) bytes.resize(offset_ + len);
    std::memcpy(bytes.data() + offset_, data, len);
    offset_ += len;
    fs_->checkpoint();
    return len;
  }
  void flush() {
    if (open_ && fs_->corrupt_flush_path == path_) {
      fs_->corrupt_flush_path.clear();
      auto& bytes = fs_->files[path_];
      if (!bytes.empty()) bytes.back() ^= 0xff;
      fs_->checkpoint();
    }
  }
  void close() { open_ = false; }
};

inline File FakeFS::open(const char* path, const char* mode, bool) {
  const bool write = mode && mode[0] == 'w';
  if (write && permanent_write_open_path == path) return File();
  if (write && fail_write_open_path == path) {
    fail_write_open_path.clear();
    return File();
  }
  if (!write && !exists(path)) return File();
  return File(this, path, write);
}

#define FILESYSTEM FakeFS
'''


MULTI = r'''#pragma once
#include <Arduino.h>

enum class InterfaceType : uint8_t {
  NONE, Bluetooth, USB, WiFi, Ethernet, HardwareSerial
};

class BaseSerialInterface {
public:
  virtual ~BaseSerialInterface() = default;
  virtual void enable() = 0;
  virtual void disable() = 0;
  virtual bool isEnabled() const = 0;
  virtual bool isConnected() const = 0;
};

class MultiSerialInterface {
  struct Item { InterfaceType type; BaseSerialInterface* interface; };
  Item items_[4] = {};
  bool enabled_ = false;
  InterfaceType selected_ = InterfaceType::Bluetooth;
  BaseSerialInterface* find(InterfaceType type) const {
    for (const auto& item : items_) if (item.interface && item.type == type) return item.interface;
    return nullptr;
  }
public:
  bool fail_next_select = false;
  bool pending_tx = false;
  bool hasPendingTx() const { return pending_tx; }
  uint32_t session_generation = 1;
  uint32_t sessionGeneration() const { return session_generation; }
  bool addInterface(InterfaceType type, BaseSerialInterface* interface) {
    for (auto& item : items_) if (!item.interface) { item = {type, interface}; return true; }
    return false;
  }
  bool hasInterface(InterfaceType type) const { return find(type) != nullptr; }
  bool selectExclusive(InterfaceType type) {
    if (fail_next_select) {
      fail_next_select = false;
      return false;
    }
    BaseSerialInterface* next = find(type);
    if (!next) return false;
    for (auto& item : items_) if (item.interface) item.interface->disable();
    selected_ = type;
    if (enabled_) next->enable();
    return true;
  }
  void enable() { enabled_ = true; selectExclusive(selected_); }
  void disable() {
    enabled_ = false;
    for (auto& item : items_) if (item.interface) item.interface->disable();
  }
  bool isInterfaceConnected(InterfaceType type) const {
    BaseSerialInterface* interface = find(type);
    return enabled_ && interface && interface->isEnabled() && interface->isConnected();
  }
  InterfaceType getSelectedInterface() const { return selected_; }
  bool isEnabled() const { return enabled_; }
};
'''


WIFI = r'''#pragma once
#include <Arduino.h>

static const int WIFI_OFF = 0;
static const int WIFI_STA = 1;
static const int WL_CONNECTED = 3;
static const int WL_DISCONNECTED = 6;

class IPAddress {
  const char* value_;
public:
  explicit IPAddress(const char* value) : value_(value) {}
  String toString() const { return String(value_); }
};

class FakeWiFiClass {
public:
  int status_code = WL_DISCONNECTED;
  int begin_count = 0;
  int off_count = 0;
  bool erased = false;
  std::string last_ssid;
  std::string last_password;
  void persistent(bool) {}
  void setAutoReconnect(bool) {}
  void mode(int value) { if (value == WIFI_OFF) ++off_count; }
  void disconnect(bool off = false, bool erase = false) {
    if (off) status_code = WL_DISCONNECTED;
    erased = erased || erase;
  }
  void begin(const char* ssid, const char* password) {
    ++begin_count;
    last_ssid = ssid ? ssid : "";
    last_password = password ? password : "";
  }
  int status() const { return status_code; }
  IPAddress localIP() const { return IPAddress("192.0.2.7"); }
};

extern FakeWiFiClass WiFi;
'''


SERIAL_WIFI = r'''#pragma once
#include <helpers/MultiSerialInterface.h>

class SerialWifiInterface : public BaseSerialInterface {
public:
  bool enabled = false;
  bool connected = false;
  bool pending = false;
  bool approved = false;
  uint32_t request_id = 0;
  uint32_t deadline = 0;
  char peer[16] = {};
  void enable() override { enabled = true; }
  void disable() override { enabled = false; connected = false; pending = false; }
  bool isEnabled() const override { return enabled; }
  bool isConnected() const override { return enabled && connected; }
  bool hasPendingClientApproval() const { return pending; }
  uint32_t getPendingClientRequestId() const { return request_id; }
  uint32_t getPendingClientDeadline() const { return deadline; }
  bool copyPendingClientPeer(char* out, size_t out_len) const {
    if (!out || !out_len) return false;
    std::strncpy(out, peer, out_len - 1); out[out_len - 1] = 0; return pending;
  }
  bool resolvePendingClient(uint32_t id, bool allow) {
    if (!pending || id != request_id || static_cast<int32_t>(fake_now - deadline) >= 0) return false;
    pending = false; approved = allow; connected = allow; return true;
  }
};
'''


DATA_STORE = r'''#pragma once
#include <Arduino.h>
class DataStore {
  FILESYSTEM* fs_;
public:
  bool available = true;
  explicit DataStore(FILESYSTEM& fs) : fs_(&fs) {}
  FILESYSTEM* getPrimaryFS() const { return available ? fs_ : nullptr; }
};
'''


HARNESS = r'''#include <cassert>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>
#include "ConnectionController.h"
#include "DataStore.h"
#include <helpers/MultiSerialInterface.h>
#include <helpers/StorageTransaction.h>
#include <helpers/SmartUiBuildInfo.h>
#if defined(ESP32)
#include <helpers/esp32/SerialWifiInterface.h>
#include <WiFi.h>
#endif

uint32_t fake_now = 100;
#if defined(ESP32)
FakeWiFiClass WiFi;
#endif

class FakeTransport : public BaseSerialInterface {
public:
  bool enabled = false;
  bool connected = false;
  void enable() override { enabled = true; }
  void disable() override { enabled = false; connected = false; }
  bool isEnabled() const override { return enabled; }
  bool isConnected() const override { return enabled && connected; }
};

class FakeStream : public Stream {
public:
  std::string input;
  std::string output;
  size_t read_offset = 0;
  int write_room = 4096;
  size_t max_write = 0;
  int available() override { return static_cast<int>(input.size() - read_offset); }
  int read() override { return available() ? static_cast<uint8_t>(input[read_offset++]) : -1; }
  int availableForWrite() override { return write_room; }
  size_t write(const uint8_t* data, size_t len) override {
    const size_t count = std::min(len, static_cast<size_t>(std::max(0, write_room)));
    output.append(reinterpret_cast<const char*>(data), count);
    max_write = std::max(max_write, count);
    return count;
  }
  void add(const char* text) { input += text; }
  size_t unread() const { return input.size() - read_offset; }
};

static int reset_count = 0;
static bool sleep_inhibited = false;
static bool cli_rescue = false;
static bool quarantined = false;
static void resetSession() { ++reset_count; }
static void setSleep(bool value) { sleep_inhibited = value; }
static bool isCli() { return cli_rescue; }
static bool isQuarantined() { return quarantined; }
static const char* boardName() { return "Test Board"; }
static std::string quick_replies[9];
static bool reply_save_fail = false;
static const char* getReply(uint8_t slot) { return slot < 9 ? quick_replies[slot].c_str() : ""; }
static bool setReply(uint8_t slot, const char* text) {
  if (slot >= 9 || reply_save_fail) return false;
  quick_replies[slot] = text;
  return true;
}

static unsigned settings_calls = 0;
static bool settings_writable = false;
static unsigned settings_reply_fault = 0;
static std::string settings_command;
static bool settingsHook(const char* command, char* reply, size_t capacity, bool writable) {
  ++settings_calls;
  settings_command = command;
  settings_writable = writable;
  assert(capacity >= 480);
  if (settings_reply_fault == 1) {
    std::memset(reply, 'x', capacity);  // Missing terminator must fail closed.
    return true;
  }
  if (settings_reply_fault == 2) {
    std::strcpy(reply, "OK settings get\r\nprivate-password");
    return true;
  }
  if (settings_reply_fault == 3) return false;
  if (settings_reply_fault == 4) {
    const std::string maximum = "OK settings get " + std::string(463, 'x');
    assert(maximum.size() == 479);
    std::memcpy(reply, maximum.c_str(), maximum.size() + 1);
    return true;
  }
  const bool read = std::strcmp(command, "settings caps") == 0 ||
      std::strcmp(command, "settings get") == 0 ||
      std::strncmp(command, "settings adc preview ", 21) == 0;
  std::strcpy(reply, !writable && !read ? "ERR settings readonly" :
      read ? "OK settings get value=1" : "OK settings saved");
  return true;
}

static ConnectionControllerHooks hooks() {
  ConnectionControllerHooks value;
  value.resetLocalSession = resetSession;
  value.setWifiSleepInhibit = setSleep;
  value.isCliRescue = isCli;
  value.isStorageQuarantined = isQuarantined;
  value.getBoardName = boardName;
  value.getQuickReply = getReply;
  value.setQuickReply = setReply;
  value.handleDeviceSettings = settingsHook;
  return value;
}

static void pump(ConnectionController& controller, unsigned count = 24) {
  while (count--) controller.loop();
}

static void send(ConnectionController& controller, FakeStream& stream, const char* text) {
  stream.add(text);
  for (unsigned i = 0; i < 80 && stream.unread(); ++i) controller.loop();
  pump(controller);
  assert(stream.unread() == 0);
}

struct ModeChangeFixture {
  FakeFS fs;
  DataStore store;
  FakeTransport ble, usb;
  MultiSerialInterface manager;
  FakeStream console;
  ConnectionController controller;

  ModeChangeFixture() : store(fs) {
    manager.addInterface(InterfaceType::Bluetooth, &ble);
    manager.addInterface(InterfaceType::USB, &usb);
    manager.enable();
    controller.begin(store, manager, console, nullptr, hooks());
    assert(controller.status().selected == CompanionMode::BLE);
    assert(controller.lastChangeError() == ConnectionChangeError::None);
    assert(fs.exists("/connection.cfg"));
  }

  void expectFailure(ConnectionChangeError error) {
    const int before_reset = reset_count;
    assert(!controller.setMode(CompanionMode::USB));
    assert(controller.lastChangeError() == error);
    assert(controller.status().selected == CompanionMode::BLE);
    assert(manager.getSelectedInterface() == InterfaceType::Bluetooth);
    if (error != ConnectionChangeError::Apply) assert(reset_count == before_reset);
    controller.loop();
    assert(controller.lastChangeError() == error);
  }
};

static void testModeChangeErrors() {
  {
    ConnectionController not_started;
    assert(not_started.lastChangeError() == ConnectionChangeError::None);
    assert(!not_started.setMode(CompanionMode::USB));
    assert(not_started.lastChangeError() == ConnectionChangeError::NotStarted);
  }
  {
    ModeChangeFixture fixture;
    const auto before = fixture.fs.files;
    cli_rescue = true;
    fixture.expectFailure(ConnectionChangeError::CliRescue);
    assert(fixture.fs.files == before);
    // Rescue must also reject an otherwise no-op request, without bypassing it.
    assert(!fixture.controller.setMode(CompanionMode::BLE));
    assert(fixture.controller.lastChangeError() == ConnectionChangeError::CliRescue);
    cli_rescue = false;
    assert(fixture.controller.setMode(CompanionMode::USB));
    assert(fixture.controller.lastChangeError() == ConnectionChangeError::None);
  }
  {
    ModeChangeFixture fixture;
    const auto before = fixture.fs.files;
    quarantined = true;
    fixture.expectFailure(ConnectionChangeError::StorageReadOnly);
    assert(fixture.fs.files == before);
    quarantined = false;
  }
  {
    ModeChangeFixture fixture;
    assert(!fixture.controller.setMode(CompanionMode::WiFi));
    assert(fixture.controller.lastChangeError() == ConnectionChangeError::Unavailable);
    // A valid no-op clears an earlier error just like a successful change.
    assert(fixture.controller.setMode(CompanionMode::BLE));
    assert(fixture.controller.lastChangeError() == ConnectionChangeError::None);
  }
  {
    ModeChangeFixture fixture;
    fixture.store.available = false;
    fixture.expectFailure(ConnectionChangeError::StorageUnavailable);
  }
  {
    ModeChangeFixture fixture;
    fixture.fs.files["/connection.cfg.tmp"] = {1};
    fixture.fs.fail_remove_path = "/connection.cfg.tmp";
    fixture.expectFailure(ConnectionChangeError::TempCleanup);
  }
  {
    ModeChangeFixture fixture;
    fixture.fs.fail_write_open_path = "/connection.cfg.tmp";
    fixture.expectFailure(ConnectionChangeError::Write);
  }
  {
    ModeChangeFixture fixture;
    fixture.fs.short_write_path = "/connection.cfg.tmp";
    fixture.expectFailure(ConnectionChangeError::Write);
  }
  {
    ModeChangeFixture fixture;
    fixture.fs.corrupt_flush_path = "/connection.cfg.tmp";
    fixture.expectFailure(ConnectionChangeError::VerifyTemp);
    assert(!fixture.fs.exists("/connection.cfg.tmp"));
  }
  {
    ModeChangeFixture fixture;
    fixture.fs.files["/connection.cfg.bak"] = fixture.fs.files["/connection.cfg"];
    fixture.fs.fail_remove_path = "/connection.cfg.bak";
    fixture.expectFailure(ConnectionChangeError::Rotate);
  }
  {
    ModeChangeFixture fixture;
    fixture.fs.fail_next_rename = true;
    fixture.expectFailure(ConnectionChangeError::Rotate);
  }
  {
    ModeChangeFixture fixture;
    fixture.fs.files["/connection.cfg"] = {1};
    fixture.fs.fail_remove_path = "/connection.cfg";
    fixture.expectFailure(ConnectionChangeError::Rotate);
  }
  {
    ModeChangeFixture fixture;
    const auto primary = fixture.fs.files["/connection.cfg"];
    fixture.fs.fail_rename_from = "/connection.cfg.tmp";
    fixture.expectFailure(ConnectionChangeError::Publish);
    // Rollback restores the old primary but must preserve the publish error.
    assert(fixture.fs.files["/connection.cfg"] == primary);
    assert(fixture.controller.setMode(CompanionMode::USB));
    assert(fixture.controller.lastChangeError() == ConnectionChangeError::None);
  }
  {
    ModeChangeFixture fixture;
    fixture.fs.corrupt_rename_to = "/connection.cfg";
    fixture.expectFailure(ConnectionChangeError::VerifyFinal);
  }
  {
    ModeChangeFixture fixture;
    fixture.manager.fail_next_select = true;
    fixture.expectFailure(ConnectionChangeError::Apply);
  }
}

static bool containsBytes(const std::vector<uint8_t>& bytes, const char* text) {
  const std::string haystack(bytes.begin(), bytes.end());
  return haystack.find(text) != std::string::npos;
}

static std::vector<uint8_t> configRecord(CompanionMode mode, bool credentials = false) {
  // Keep the established 109-byte v1 ABI: header9 + SSID32 + password64 + CRC4.
  std::vector<uint8_t> record(109, 0);
  std::memcpy(record.data(), "MCC1", 4);
  record[4] = 1;
  record[5] = static_cast<uint8_t>(mode);
  if (credentials) {
    const char* ssid = "private-network";
    const char* password = "private-password";
    record[6] = 1;
    record[7] = std::strlen(ssid);
    record[8] = std::strlen(password);
    std::memcpy(record.data() + 9, ssid, record[7]);
    std::memcpy(record.data() + 41, password, record[8]);
  }
  mesh::storage::Crc32 crc;
  crc.update(record.data(), 105);
  const uint32_t checksum = crc.value();
  for (unsigned i = 0; i < 4; ++i) record[105 + i] = checksum >> (8 * i);
  return record;
}

struct RecoveryFixture {
  FakeFS fs;
  DataStore store;
  FakeTransport ble, usb;
  MultiSerialInterface manager;
  FakeStream console;
  ConnectionController controller;
#if defined(ESP32)
  SerialWifiInterface wifi;
#endif

  RecoveryFixture() : store(fs) {
    manager.addInterface(InterfaceType::Bluetooth, &ble);
    manager.addInterface(InterfaceType::USB, &usb);
#if defined(ESP32)
    manager.addInterface(InterfaceType::WiFi, &wifi);
#endif
    manager.enable();
  }
  void boot() {
    controller.begin(store, manager, console,
#if defined(ESP32)
                     &wifi,
#else
                     nullptr,
#endif
                     hooks());
  }
};

static void assertNoCredentials(const FakeFS::State& files) {
  for (const auto& item : files) {
    assert(!containsBytes(item.second, "private-network"));
    assert(!containsBytes(item.second, "private-password"));
  }
}

static void testCredentialBearingRecovery() {
  for (const char* path : {"/connection.cfg.tmp", "/connection.cfg.bak"}) {
    for (unsigned fault = 0; fault < 4; ++fault) {
      RecoveryFixture first;
      const auto record = configRecord(CompanionMode::USB, true);
      first.fs.files[path] = record;
      first.fs.files["/connection.cfg"] = {1, 2};
      if (fault == 1) first.fs.fail_write_open_path = "/connection.cfg";
      if (fault == 2) first.fs.short_write_path = "/connection.cfg";
      if (fault == 3) first.fs.corrupt_flush_path = "/connection.cfg";
      first.fs.record_snapshots = true;
      first.boot();
      assert(first.controller.status().wifiConfigured);
      assert(first.controller.status().selected == CompanionMode::USB);
      assert(first.controller.status().storageRecoveryRequired == (fault != 0));
      if (fault) {
        assert(first.controller.status().usbConsoleEnabled);
        assert(!first.manager.isEnabled());
      }
      first.fs.snapshots.push_back(first.fs.files);
      for (const auto& files : first.fs.snapshots) {
        RecoveryFixture second;
        second.fs.files = files;
        second.boot();
        assert(second.controller.status().wifiConfigured);
        assert(second.controller.status().selected == CompanionMode::USB);
        assert(!second.controller.status().storageRecoveryRequired);
        assert(second.fs.files["/connection.cfg"] == record);
      }
    }
  }
}

static void testRecoveryConsoleAndReplies() {
  RecoveryFixture recovery;
  recovery.fs.files["/connection.cfg"] = configRecord(CompanionMode::USB);
  recovery.fs.fail_remove_path = "/connection.forgot";
  recovery.boot();
  assert(recovery.controller.status().storageRecoveryRequired);
  assert(recovery.controller.status().usbConsoleEnabled);
  assert(!recovery.manager.isEnabled());
  send(recovery.controller, recovery.console, "wifi forget\n");
  assert(!recovery.controller.status().storageRecoveryRequired);
  assert(recovery.manager.isEnabled());
  assert(recovery.controller.status().selected == CompanionMode::BLE);

  send(recovery.controller, recovery.console, "reply set 1 d094d0b0\nreply get 1\n");
  assert(quick_replies[0] == "\xd0\x94\xd0\xb0");
  assert(recovery.console.output.find("Reply=1 hex=d094d0b0") != std::string::npos);
  const std::string max_command = "reply set 9 " + std::string(128, '6') + "\n";
  send(recovery.controller, recovery.console, max_command.c_str());
  assert(quick_replies[8] == std::string(64, 'f'));
  for (const char* invalid : {"reply set 1 00\n", "reply set 1 c080\n", "reply set 1 f4908080\n", "reply set 1 eda080\n", "reply set 1 0a\n", "reply set 1 zz\n", "reply set 0 61\n"}) {
    send(recovery.controller, recovery.console, invalid);
    assert(quick_replies[0] == "\xd0\x94\xd0\xb0");
  }
  reply_save_fail = true;
  send(recovery.controller, recovery.console, "reply set 1 61\n");
  assert(quick_replies[0] == "\xd0\x94\xd0\xb0");
  reply_save_fail = false;
  quarantined = true;
  send(recovery.controller, recovery.console, "reply set 1 61\nreply get 1\n");
  assert(quick_replies[0] == "\xd0\x94\xd0\xb0");
  quarantined = false;
  send(recovery.controller, recovery.console, "reply set 1 -\nreply get 1\n");
  assert(quick_replies[0].empty());
  assert(recovery.console.output.find("Reply=1 hex=-") != std::string::npos);
#if defined(ESP32)
  RecoveryFixture online;
  online.fs.files["/connection.cfg"] = configRecord(CompanionMode::WiFi, true);
  online.boot();
  WiFi.status_code = WL_CONNECTED;
  online.wifi.connected = true;
  online.controller.loop();
  const int begins = WiFi.begin_count;
  send(online.controller, online.console, "wifi cancel\n");
  assert(WiFi.begin_count == begins);
  assert(online.controller.status().clientConnected);
#endif
}

static void assertCleanReboot(const FakeFS::State& files, CompanionMode mode) {
  RecoveryFixture next;
  next.fs.files = files;
  next.boot();
  assert(next.controller.status().selected == mode);
  assert(!next.controller.status().wifiConfigured);
  assert(!next.controller.status().storageRecoveryRequired);
  assert(next.fs.files["/connection.cfg"] == configRecord(mode));
  assertNoCredentials(next.fs.files);
}

static void testCredentialFreeRecovery() {
  for (CompanionMode mode : {CompanionMode::BLE, CompanionMode::USB
#if defined(ESP32)
                            , CompanionMode::WiFi
#endif
                            }) {
    for (const char* source : {"/connection.cfg.tmp", "/connection.cfg.bak"}) {
      for (bool corrupt_primary : {false, true}) {
        for (unsigned fault = 0; fault < 10; ++fault) {
          RecoveryFixture first;
          const auto record = configRecord(mode);
          first.fs.files[source] = record;
          if (corrupt_primary) first.fs.files["/connection.cfg"] = {1, 2, 3};
          switch (fault) {
            case 1: first.fs.fail_write_open_path = "/connection.forgot"; break;
            case 2: first.fs.short_write_path = "/connection.forgot"; break;
            case 3: first.fs.fail_write_open_path = "/connection.cfg"; break;
            case 4: first.fs.short_write_path = "/connection.cfg"; break;
            case 5: first.fs.corrupt_flush_path = "/connection.cfg"; break;
            case 6: first.fs.fail_remove_path = source; break;
            case 7: first.fs.permanent_remove_path = source;
                    first.fs.fail_write_open_path = source; break;
            case 8: first.fs.fail_remove_path = "/connection.forgot"; break;
            // Recovery no longer needs rename and cannot consume its sole .tmp.
            case 9: first.fs.fail_next_rename = true; break;
          }
          first.fs.record_snapshots = true;
          first.boot();
          assert(first.controller.status().selected == mode);
          assert(!first.controller.status().wifiConfigured);
          if (first.controller.status().storageRecoveryRequired) {
            assert(!first.manager.isEnabled());
            assert(!first.controller.setMode(CompanionMode::BLE));
            assert(first.controller.lastChangeError() == ConnectionChangeError::StorageReadOnly);
          }
          // A healthy next boot recovers both clean mode and durable primary.
          assertCleanReboot(first.fs.files, mode);
          // Every simulated power-cut keeps at least one complete clean record.
          for (const auto& snapshot : first.fs.snapshots) assertCleanReboot(snapshot, mode);
        }
      }
    }
  }

  // Read-only external modes never even create the recovery marker.
  for (bool cli : {false, true}) {
    RecoveryFixture readonly;
    readonly.fs.files["/connection.cfg.tmp"] = configRecord(CompanionMode::USB);
    const auto before = readonly.fs.files;
    cli_rescue = cli;
    quarantined = !cli;
    readonly.boot();
    assert(readonly.fs.files == before);
    assert(readonly.controller.status().selected == CompanionMode::USB);
    assert(!readonly.manager.isEnabled());
    cli_rescue = quarantined = false;
  }
}

static void testForgetFailurePrivacy() {
  const char* paths[] = {"/connection.cfg", "/connection.cfg.tmp", "/connection.cfg.bak"};
  for (const char* blocked : paths) {
    for (unsigned fault = 0; fault < 5; ++fault) {
      RecoveryFixture first;
      const auto secret = configRecord(CompanionMode::BLE, true);
      first.fs.files["/connection.cfg"] = secret;
      first.boot();
      for (const char* path : paths) first.fs.files[path] = secret;
      first.fs.record_snapshots = true;
      first.fs.permanent_remove_path = blocked;
      switch (fault) {
        case 0: first.fs.permanent_write_open_path = blocked; break;
        case 1: first.fs.short_write_path = blocked; break;
        case 2: first.fs.corrupt_flush_path = blocked; break;
        case 3: break;  // Failed unlink can be neutralized by verified overwrite.
        case 4: first.fs.fail_remove_path = "/connection.forgot"; break;
      }
      send(first.controller, first.console, "wifi forget\n");
      assert(!first.controller.status().wifiConfigured);
      if (first.controller.status().storageRecoveryRequired) {
        assert(first.fs.exists("/connection.forgot"));
        assert(!first.manager.isEnabled());
        assert(first.console.output.find("Do not assume credentials were erased") != std::string::npos);
      } else {
        assert(!first.fs.exists("/connection.forgot"));
        assertNoCredentials(first.fs.files);
      }
      for (const auto& snapshot : first.fs.snapshots) {
        assertCleanReboot(snapshot, CompanionMode::BLE);
      }
      // Permanent write+unlink failure must stay fail-closed on every boot,
      // including loss of the clean primary after a failed backup cleanup.
      if (fault == 0) {
        for (bool corrupt_clean_primary : {false, true}) {
          FakeFS::State state = first.fs.files;
          if (corrupt_clean_primary && std::strcmp(blocked, "/connection.cfg") != 0) {
            state["/connection.cfg"] = {1, 2, 3};
          }
          for (unsigned boot = 0; boot < 2; ++boot) {
            RecoveryFixture next;
            next.fs.files = state;
            next.fs.permanent_remove_path = blocked;
            next.fs.permanent_write_open_path = blocked;
            next.boot();
            assert(!next.controller.status().wifiConfigured);
            assert(next.controller.status().storageRecoveryRequired);
            assert(!next.manager.isEnabled());
            assert(next.fs.exists("/connection.forgot"));
#if defined(ESP32)
            assert(!next.wifi.enabled && !sleep_inhibited);
#endif
            state = next.fs.files;
          }
        }
      }
      // Retry is available without reboot once the storage fault is gone.
      first.fs.permanent_remove_path.clear();
      first.fs.permanent_write_open_path.clear();
      send(first.controller, first.console, "wifi forget\n");
      assert(!first.controller.status().storageRecoveryRequired);
      assert(first.manager.isEnabled());
      assertNoCredentials(first.fs.files);
      assertCleanReboot(first.fs.files, CompanionMode::BLE);
    }
  }

  // A storage device that cannot create the barrier cannot claim Forget.
  // Existing data must remain intact and the failure must be explicit.
  RecoveryFixture unavailable;
  unavailable.fs.files["/connection.cfg"] = configRecord(CompanionMode::BLE, true);
  unavailable.boot();
  const auto before = unavailable.fs.files;
  unavailable.fs.permanent_write_open_path = "/connection.forgot";
  send(unavailable.controller, unavailable.console, "wifi forget\n");
  assert(unavailable.fs.files == before);
  assert(unavailable.controller.status().storageRecoveryRequired);
  assert(!unavailable.controller.status().wifiConfigured && !unavailable.manager.isEnabled());
  assert(unavailable.console.output.find("Do not assume credentials were erased") != std::string::npos);
}

static void testInfoReadOnly() {
  RecoveryFixture fixture;
  fixture.fs.files["/connection.cfg"] = configRecord(CompanionMode::BLE, true);
  fixture.boot();
  pump(fixture.controller);
  fixture.console.output.clear();
  const auto before = fixture.fs.files;
  for (bool quarantine : {false, true}) {
    quarantined = quarantine;
    send(fixture.controller, fixture.console, "info\n");
    assert(fixture.console.output.find("SmartUI=" SMARTUI_VERSION " core=" SMARTUI_CORE_VERSION
        " build=" SMARTUI_BUILD_SHA " upstream=" SMARTUI_UPSTREAM_SHA " capabilities=BLE,USB") != std::string::npos);
    assert(fixture.console.output.find(" board=Test Board\r\n") != std::string::npos);
    assert(fixture.console.output.find("private-network") == std::string::npos);
    assert(fixture.console.output.find("private-password") == std::string::npos);
    assert(fixture.fs.files == before);
    fixture.console.output.clear();
  }
  quarantined = false;
}

static void testDeviceSettingsConsole() {
  RecoveryFixture fixture;
  fixture.boot();
  send(fixture.controller, fixture.console, "help\n");
  assert(fixture.console.output.find("Settings protocol: 1\r\nCredential input") != std::string::npos);
  fixture.console.output.clear();
  send(fixture.controller, fixture.console, "  SETTINGS GET  \r\n");
  assert(settings_command == "settings get" && settings_writable);
  assert(fixture.console.output == "OK settings get value=1\r\n");

  quarantined = true;
  fixture.console.output.clear();
  send(fixture.controller, fixture.console, "settings get\nsettings set volume 1\nsettings adc preview 4120\nsettings test\n");
  assert(!settings_writable);
  assert(fixture.console.output == "OK settings get value=1\r\nERR settings readonly\r\nOK settings get value=1\r\nERR settings readonly\r\n");
  quarantined = false;

  for (unsigned fault : {1U, 2U, 3U}) {
    settings_reply_fault = fault;
    fixture.console.output.clear();
    send(fixture.controller, fixture.console, "settings get\n");
    assert(fixture.console.output == (fault == 3 ? "ERR settings unsupported\r\n" : "ERR settings internal\r\n"));
    assert(fixture.console.output.find("private-password") == std::string::npos);
  }
  settings_reply_fault = 4;
  fixture.console.output.clear();
  // Pipelined full-size replies must not overflow the 512-byte TX queue.
  send(fixture.controller, fixture.console, "settings get\nsettings get\n");
  const std::string maximum = "OK settings get " + std::string(463, 'x') + "\r\n";
  assert(fixture.console.output == maximum + maximum);
  settings_reply_fault = 0;

  // A stalled host must not consume another command or lose its response.
  fixture.console.output.clear();
  fixture.console.write_room = 0;
  const unsigned before_blocked = settings_calls;
  fixture.console.add("settings get\nsettings set volume 2\n");
  pump(fixture.controller, 100);
  assert(settings_calls == before_blocked + 1);
  assert(fixture.console.unread() > 0 && fixture.console.output.empty());
  fixture.console.write_room = 3;
  pump(fixture.controller, 100);
  assert(settings_calls == before_blocked + 2 && fixture.console.unread() == 0);
  assert(fixture.console.output == "OK settings get value=1\r\nOK settings saved\r\n");
  fixture.console.write_room = 4096;

  const unsigned before_invalid = settings_calls;
  const std::string overlong = "settings " + std::string(160, 'x') + "\n";
  send(fixture.controller, fixture.console, overlong.c_str());
  send(fixture.controller, fixture.console, "settingsx get\n");
  assert(settings_calls == before_invalid);

  RecoveryFixture local_recovery;
  local_recovery.fs.files["/connection.cfg"] = configRecord(CompanionMode::USB);
  local_recovery.fs.fail_remove_path = "/connection.forgot";
  local_recovery.boot();
  assert(local_recovery.controller.status().storageRecoveryRequired);
  send(local_recovery.controller, local_recovery.console, "settings get\nsettings adc reset\n");
  assert(!settings_writable);
  assert(local_recovery.console.output.find("OK settings get value=1\r\nERR settings readonly\r\n") != std::string::npos);

  RecoveryFixture no_hook;
  auto legacy_hooks = hooks();
  legacy_hooks.handleDeviceSettings = nullptr;
  no_hook.controller.begin(no_hook.store, no_hook.manager, no_hook.console, nullptr, legacy_hooks);
  send(no_hook.controller, no_hook.console, "help\nsettings get\n");
  assert(no_hook.console.output.find("Settings protocol:") == std::string::npos);
  assert(no_hook.console.output.find("ERR settings unsupported") != std::string::npos);

#if defined(ESP32)
  RecoveryFixture wifi_fixture;
  wifi_fixture.boot();
  send(wifi_fixture.controller, wifi_fixture.console, "wifi setup\n");
  const unsigned before_credentials = settings_calls;
  send(wifi_fixture.controller, wifi_fixture.console, "settings get\nsettings caps\n");
  assert(settings_calls == before_credentials);
  assert(WiFi.last_ssid == "settings get" && WiFi.last_password == "settings caps");
  assert(wifi_fixture.console.output.find("settings get") == std::string::npos);
  send(wifi_fixture.controller, wifi_fixture.console, "settings get\nsettings set gps 1\n");
  assert(settings_calls == before_credentials);
  assert(wifi_fixture.console.output.find("ERR settings busy") != std::string::npos);
  send(wifi_fixture.controller, wifi_fixture.console, "wifi cancel\n");
#endif
}

class MyMesh {
public:
  bool _cli_rescue = false;
  char cli_command[160] = {};
  void enterCLIRescue();
};
struct RescueSerial {
  void println(const char*) {}
} Serial;

// Injected from MyMesh.cpp so physical entry tests execute production code.
@@USB_SERVICE_ENTRY@@

static void testPhysicalUsbServiceEntry() {
  FakeFS fs;
  DataStore store(fs);
  FakeTransport ble, usb;
  MultiSerialInterface manager;
  manager.addInterface(InterfaceType::Bluetooth, &ble);
  manager.addInterface(InterfaceType::USB, &usb);
  manager.enable();
  FakeStream console;
  connection_controller.begin(store, manager, console, nullptr, hooks());
  assert(connection_controller.setMode(CompanionMode::USB));
  MyMesh mesh;
  fs.fail_write_open_path = "/connection.cfg.tmp";
  mesh.enterCLIRescue();
  assert(!mesh._cli_rescue);
  assert(connection_controller.status().selected == CompanionMode::USB);
  assert(!connection_controller.status().usbConsoleEnabled);
  mesh.enterCLIRescue();
  assert(!mesh._cli_rescue);
  assert(connection_controller.status().selected == CompanionMode::BLE);
  assert(connection_controller.status().usbConsoleEnabled);
  send(connection_controller, console, "settings get\n");
  assert(console.output.find("OK settings get value=1") != std::string::npos);
  // Ordinary BLE startup rescue remains available, unchanged.
  mesh.enterCLIRescue();
  assert(mesh._cli_rescue);
}

static std::string api(ConnectionController& controller, const char* command, bool writable = true) {
  char reply[480] = {};
  assert(controller.handleApiCommand(command, reply, sizeof(reply), writable));
  assert(std::strchr(reply, '\n') == nullptr && std::strchr(reply, '\r') == nullptr);
  return reply;
}

static void testApiConnectionControl() {
  FakeFS fs;
  DataStore store(fs);
  FakeTransport ble, usb;
  MultiSerialInterface manager;
  FakeStream console;
  ConnectionController controller;
  manager.addInterface(InterfaceType::Bluetooth, &ble);
  manager.addInterface(InterfaceType::USB, &usb);
#if defined(ESP32)
  WiFi = FakeWiFiClass();
  SerialWifiInterface wifi;
  manager.addInterface(InterfaceType::WiFi, &wifi);
#endif
  manager.enable();
  controller.begin(store, manager, console,
#if defined(ESP32)
                   &wifi,
#else
                   nullptr,
#endif
                   hooks());
  pump(controller);
  ble.connected = true;
  console.output.clear();
  const auto initial = fs.files;
  assert(api(controller, "api mode usb", false) == "ERR api readonly");
  assert(api(controller, "api mode invalid") == "ERR api invalid");
  assert(api(controller, "api mode usb").find("state=pending") != std::string::npos);
  fake_now += 150;
  api(controller, "api wifi status"); // Unrelated read must not arm a switch.
  pump(controller);
  assert(controller.status().selected == CompanionMode::BLE); // No queued ACK.
  fake_now += 2000;
  pump(controller);
  assert(fs.files == initial);
  assert(api(controller, "api wifi status").find("last_mode_error=timeout") != std::string::npos);
  api(controller, "api mode usb");
  controller.apiReplyQueued();
  manager.pending_tx = true;
  fake_now += 150;
  pump(controller);
  assert(controller.status().selected == CompanionMode::BLE);
  manager.pending_tx = false;
  pump(controller);
  assert(controller.status().selected == CompanionMode::USB);
  usb.connected = true;
  api(controller, "api mode ble");
  controller.apiReplyQueued();
  controller.resetApiSession();
  fake_now += 200;
  pump(controller);
  assert(controller.status().selected == CompanionMode::USB);
  assert(controller.setMode(CompanionMode::BLE));
  ble.connected = true;
  // Physical disconnect before the router's session-reset callback also cancels.
  api(controller, "api mode usb");
  controller.apiReplyQueued();
  ble.connected = false;
  fake_now += 150;
  pump(controller);
  assert(controller.status().selected == CompanionMode::BLE);
  assert(api(controller, "api wifi status").find("last_mode_error=cancelled") != std::string::npos);
  ble.connected = true;
  // Disconnect/reconnect between router polls: connected stays true but the
  // replacement session must not inherit the old session's queued mode write.
  const auto before_reconnect = fs.files;
  api(controller, "api mode usb");
  controller.apiReplyQueued();
  ++manager.session_generation;
  assert(manager.isInterfaceConnected(InterfaceType::Bluetooth));
  fake_now += 150;
  pump(controller);
  assert(controller.status().selected == CompanionMode::BLE);
  assert(fs.files == before_reconnect);
  assert(!controller.deviceApiBusy());
  assert(api(controller, "api wifi status").find("mode_pending=none last_mode_error=cancelled") != std::string::npos);
#if defined(ESP32)
  assert(api(controller, "api mode wifi") == "ERR api unconfigured");
  assert(api(controller, "api wifi begin", false) == "ERR api readonly");
  assert(api(controller, "api wifi begin").find("state=ssid") != std::string::npos);
  assert(controller.deviceApiWritesAllowed() && controller.deviceApiBusy());
  assert(api(controller, "api wifi begin") == "ERR api busy");
  assert(api(controller, "api wifi save") == "ERR api stale");
  assert(api(controller, "api wifi ssid 0a") == "ERR api invalid");
  assert(api(controller, "api wifi ssid 746573746e6574").find("state=password") != std::string::npos);
  assert(api(controller, "api wifi password 00") == "ERR api invalid");
  const std::string invalid_psk = "api wifi password " + std::string(128, '7'); // Decodes non-hex 'w'.
  assert(api(controller, invalid_psk.c_str()) == "ERR api invalid");
  assert(api(controller, "api wifi password 7465737470617373").find("state=ready") != std::string::npos);
  assert(api(controller, "api wifi status").find("testpass") == std::string::npos);
  assert(api(controller, "api wifi status").find("testnet") == std::string::npos);
  const auto before_test = fs.files;
  console.output.clear();
  assert(api(controller, "api wifi test").find("state=testing") != std::string::npos);
  assert(WiFi.last_ssid == "testnet" && WiFi.last_password == "testpass");
  WiFi.status_code = WL_CONNECTED;
  pump(controller);
  assert(api(controller, "api wifi status").find("state=test_ok") != std::string::npos);
  assert(fs.files == before_test); // Testing never persists candidate.
  assert(console.output.find("WiFi test") == std::string::npos);
  fs.short_write_path = "/connection.cfg.tmp";
  assert(api(controller, "api wifi save") == "ERR api storage");
  assert(!controller.status().wifiConfigured);
  assert(api(controller, "api wifi save") == "OK api wifi save");
  assert(controller.status().wifiConfigured && controller.status().selected == CompanionMode::BLE);
  assert(!controller.deviceApiBusy());
  assert(api(controller, "api wifi status").find("state=saved") != std::string::npos);
  const auto saved = fs.files;
  // USB API uses the same staged backend without writing console bytes.
  assert(controller.setMode(CompanionMode::USB));
  api(controller, "api wifi begin");
  api(controller, "api wifi ssid 746573746e6574");
  assert(api(controller, "api wifi password -").find("state=ready") != std::string::npos);
  api(controller, "api wifi test");
  controller.resetApiSession();
  assert(!controller.deviceApiBusy() && !sleep_inhibited);
  assert(api(controller, "api wifi save") == "ERR api stale");
  assert(api(controller, "api wifi status").find("ssid_set=0") != std::string::npos);
  // Test timeout restores saved configuration; no candidate survives.
  api(controller, "api wifi begin");
  api(controller, "api wifi ssid 746573746e6574");
  api(controller, "api wifi password -");
  api(controller, "api wifi test");
  WiFi.status_code = WL_DISCONNECTED;
  fake_now += 15001;
  pump(controller);
  assert(api(controller, "api wifi status").find("state=failed") != std::string::npos);
  assert(!controller.deviceApiBusy());
  api(controller, "api wifi begin");
  fake_now += 120001;
  pump(controller);
  assert(api(controller, "api wifi status").find("state=timeout") != std::string::npos);
  // A local text wizard cannot consume/overwrite an API candidate.
  assert(controller.setMode(CompanionMode::BLE));
  api(controller, "api wifi begin");
  send(controller, console, "wifi setup\n");
  assert(api(controller, "api wifi status").find("owner=api") != std::string::npos);
  api(controller, "api wifi cancel");
  assert(api(controller, "api wifi status").find("state=cancelled") != std::string::npos);
  assert(controller.setMode(CompanionMode::WiFi));
  assert(api(controller, "api wifi begin") == "ERR api transport");
  assert(controller.status().wifiConfigured);
  // A maximum-size PSK fits the command and is never echoed.
  assert(controller.setMode(CompanionMode::BLE));
  api(controller, "api wifi begin");
  api(controller, "api wifi ssid 61");
  const std::string full_psk = "api wifi password " + std::string(128, '6'); // 64 hexadecimal 'f' bytes.
  assert(api(controller, full_psk.c_str()).find("state=ready") != std::string::npos);
  api(controller, "api wifi cancel");
  quarantined = true;
  assert(api(controller, "api wifi begin") == "ERR api readonly");
  quarantined = false;
  (void)saved;
#else
  assert(api(controller, "api wifi begin") == "ERR api unsupported");
  assert(api(controller, "api wifi status").find("supported=0") != std::string::npos);
#endif
}

int main() {
  FakeFS fs;
  DataStore store(fs);
  FakeTransport ble, usb;
  MultiSerialInterface manager;
  manager.addInterface(InterfaceType::Bluetooth, &ble);
  manager.addInterface(InterfaceType::USB, &usb);
#if defined(ESP32)
  SerialWifiInterface wifi;
  manager.addInterface(InterfaceType::WiFi, &wifi);
#endif
  manager.enable();
  FakeStream console;
  ConnectionController controller;
  controller.begin(store, manager, console,
#if defined(ESP32)
                   &wifi,
#else
                   nullptr,
#endif
                   hooks());
  assert(fs.exists("/connection.cfg"));
  CompanionStatus status = controller.status();
  assert(status.selected == CompanionMode::BLE);
  assert(status.usbConsoleEnabled && (status.capabilities & COMPANION_CAP_BLE));
  assert(manager.getSelectedInterface() == InterfaceType::Bluetooth);

#if defined(ESP32)
  // Selection precedes provisioning: transport remains exclusive but inactive,
  // WiFi radio/server stay off, and USB remains service console.
  assert(controller.setMode(CompanionMode::WiFi));
  assert(controller.lastChangeError() == ConnectionChangeError::None);
  assert(reset_count == 1);
  status = controller.status();
  assert(status.selected == CompanionMode::WiFi && !status.wifiConfigured);
  assert(status.usbConsoleEnabled && !status.wifiAssociated && !wifi.enabled);
  assert(manager.getSelectedInterface() == InterfaceType::WiFi);
  assert(!sleep_inhibited && WiFi.begin_count == 0);

  // CRLF may split across loop calls.  Its LF must not become an unintended
  // blank password after CR advances the wizard stage.
  send(controller, console, "wifi setup\r");
  console.add("\n"); controller.loop();
  send(controller, console, " My SSID \r");
  assert(WiFi.begin_count == 0);
  console.add("\n"); controller.loop();
  assert(WiFi.begin_count == 0);
  send(controller, console, " pass word \r\n");
  assert(WiFi.begin_count == 1);
  assert(WiFi.last_ssid == " My SSID ");
  assert(WiFi.last_password == " pass word ");
  assert(console.output.find("My SSID") == std::string::npos);
  assert(console.output.find("pass word") == std::string::npos);
  WiFi.status_code = WL_CONNECTED;
  pump(controller);
  send(controller, console, "wifi save\n");
  status = controller.status();
  assert(status.wifiConfigured && status.wifiAssociated);
  assert(std::string(status.wifiLocalIp) == "192.0.2.7");
  assert(wifi.enabled && sleep_inhibited);

  // A passed candidate can lose its association while waiting for Save.
  // Do not reconnect the old network, and Save must start the stored candidate.
  send(controller, console, "wifi setup\n");
  send(controller, console, "Candidate New\n");
  send(controller, console, "candidate pass\n");
  WiFi.status_code = WL_CONNECTED;
  pump(controller);
  const int candidate_attempts = WiFi.begin_count;
  WiFi.status_code = WL_DISCONNECTED;
  controller.loop();
  fake_now += 5001;
  pump(controller);
  assert(WiFi.begin_count == candidate_attempts);
  assert(WiFi.last_ssid == "Candidate New");
  assert(!controller.status().wifiAssociated);
  assert(containsBytes(fs.files["/connection.cfg"], " My SSID "));
  send(controller, console, "wifi save\n");
  assert(WiFi.begin_count == candidate_attempts + 1);
  assert(WiFi.last_ssid == "Candidate New" &&
         WiFi.last_password == "candidate pass");
  assert(containsBytes(fs.files["/connection.cfg"], "Candidate New"));
  WiFi.status_code = WL_CONNECTED;
  pump(controller);
  assert(controller.status().wifiAssociated && wifi.enabled);

  // Cancel after a different passed candidate drops still restores saved data.
  send(controller, console, "wifi setup\n");
  send(controller, console, "Cancel Candidate\n");
  send(controller, console, "cancelled pass\n");
  WiFi.status_code = WL_CONNECTED;
  pump(controller);
  WiFi.status_code = WL_DISCONNECTED;
  const int before_cancel_restore = WiFi.begin_count;
  fake_now += 5001;
  pump(controller);
  assert(WiFi.begin_count == before_cancel_restore);
  send(controller, console, "wifi cancel\n");
  assert(WiFi.begin_count == before_cancel_restore + 1);
  assert(WiFi.last_ssid == "Candidate New" &&
         WiFi.last_password == "candidate pass");
  assert(containsBytes(fs.files["/connection.cfg"], "Candidate New"));

  // Restore the original fixture for the existing timeout/retry coverage.
  send(controller, console, "wifi setup\n");
  send(controller, console, " My SSID \n");
  send(controller, console, " pass word \n");
  WiFi.status_code = WL_CONNECTED;
  pump(controller);
  send(controller, console, "wifi save\n");

  // A deliberate empty password Enter still starts an open-network test.
  send(controller, console, "wifi setup\r\n");
  send(controller, console, "Open Network\r\n");
  const int before_open_test = WiFi.begin_count;
  send(controller, console, "\r\n");
  assert(WiFi.begin_count == before_open_test + 1 && WiFi.last_password.empty());
  send(controller, console, "wifi cancel\r\n");

  // TEST_OK cannot keep candidate radio/credentials alive forever.
  send(controller, console, "wifi setup\r\n");
  send(controller, console, "Timeout Net\r\n");
  send(controller, console, "timeout pass\r\n");
  WiFi.status_code = WL_CONNECTED;
  pump(controller);
  const int before_timeout_restore = WiFi.begin_count;
  fake_now += 120001;
  controller.loop();
  assert(WiFi.begin_count == before_timeout_restore + 1);
  assert(WiFi.last_ssid == " My SSID " && sleep_inhibited);
  assert(console.output.find("Timeout Net") == std::string::npos);

  // Restarting from TEST_OK drops candidate association before new input.
  send(controller, console, "wifi setup\r\n");
  send(controller, console, "Restart Net\r\n");
  send(controller, console, "restart pass\r\n");
  WiFi.status_code = WL_CONNECTED;
  pump(controller);
  send(controller, console, "wifi setup\r\n");
  assert(!sleep_inhibited && WiFi.off_count > 0);
  fake_now += 120001;
  controller.loop();
  assert(WiFi.last_ssid == " My SSID " && sleep_inhibited);
  WiFi.status_code = WL_CONNECTED;
  controller.loop();  // observe restored association before loss/retry test

  wifi.pending = true;
  wifi.request_id = 71;
  wifi.deadline = fake_now + 30000;
  std::strcpy(wifi.peer, "198.51.100.4");
  status = controller.status();
  assert(status.wifiApprovalPending && status.wifiRequestId == 71);
  assert(std::string(status.wifiClientIp) == "198.51.100.4");
  assert(status.wifiApprovalRemainingMs == 30000);
  assert(!controller.resolveWifiClient(70, true));
  const int before_approval_reset = reset_count;
  controller.loop();
  assert(!wifi.pending && wifi.approved && wifi.connected);
  assert(reset_count == before_approval_reset);  // MyMesh alone observes epochs.

  // New automatic sessions are blocked in rescue, quarantine and setup. A
  // currently approved connection is left to the transport/session lifecycle.
  cli_rescue = true;
  wifi.pending = true; wifi.request_id = 72; wifi.deadline = fake_now + 30000;
  controller.loop();
  assert(!wifi.pending && !wifi.approved);
  cli_rescue = false;
  send(controller, console, "wifi setup\n");
  wifi.pending = true; wifi.request_id = 73; wifi.deadline = fake_now + 30000;
  assert(!controller.resolveWifiClient(73, true));
  controller.loop();
  assert(!wifi.pending && !wifi.approved);
  send(controller, console, "cancel\n");
  WiFi.status_code = WL_CONNECTED;

  controller.loop();  // Record the restored link before testing a new loss.

  const int attempts = WiFi.begin_count;
  WiFi.status_code = WL_DISCONNECTED;
  controller.loop();
  fake_now += 5001;
  controller.loop();
  assert(WiFi.begin_count == attempts + 1);

  const char* switch_and_binary = "mode usb\r\n<binary";
  console.add(switch_and_binary);
  controller.loop();
  assert(!controller.status().usbConsoleEnabled);
  assert(manager.getSelectedInterface() == InterfaceType::USB);
  assert(!sleep_inhibited);
  assert(console.unread() == std::strlen("\n<binary"));
  console.read_offset = console.input.size();
  const size_t old_output = console.output.size();
  console.add("status\n");
  controller.loop();
  assert(console.unread() == 7 && console.output.size() == old_output);
  console.read_offset = console.input.size();
  assert(controller.setMode(CompanionMode::BLE));

  // Interrupted mode transaction never changes live mode or resets session.
  const int before_failed_reset = reset_count;
  fs.fail_next_rename = true;
  assert(!controller.setMode(CompanionMode::USB));
  assert(controller.status().selected == CompanionMode::BLE);
  assert(reset_count == before_failed_reset);

  // Recovery consumes a verified temporary generation when primary is bad.
  assert(controller.setMode(CompanionMode::USB));
  fs.files["/connection.cfg.tmp"] = fs.files["/connection.cfg"];
  fs.files["/connection.cfg.bak"] = fs.files["/connection.cfg"];
  fs.files["/connection.cfg"][0] ^= 0xff;
  FakeTransport ble2, usb2;
  SerialWifiInterface wifi2;
  MultiSerialInterface manager2;
  manager2.addInterface(InterfaceType::Bluetooth, &ble2);
  manager2.addInterface(InterfaceType::USB, &usb2);
  manager2.addInterface(InterfaceType::WiFi, &wifi2);
  manager2.enable();
  FakeStream console2;
  ConnectionController recovered;
  recovered.begin(store, manager2, console2, &wifi2, hooks());
  assert(recovered.status().selected == CompanionMode::USB);
  assert(recovered.setMode(CompanionMode::BLE));

  // Forget leaves no eligible credential-bearing generation.
  send(recovered, console2, "wifi forget\n");
  assert(!recovered.status().wifiConfigured);
  assert(recovered.status().selected == CompanionMode::BLE);
  assert(fs.exists("/connection.cfg"));
  assert(!fs.exists("/connection.cfg.tmp") && !fs.exists("/connection.cfg.bak"));
  for (const auto& item : fs.files) {
    assert(!containsBytes(item.second, "My SSID"));
    assert(!containsBytes(item.second, "pass word"));
  }
#else
  assert(!(status.capabilities & COMPANION_CAP_WIFI));
  assert(!controller.setMode(CompanionMode::WiFi));
#endif

  // Runtime quarantine preserves active transport for MyMesh's terminal error,
  // rejects a new WiFi peer, and freezes persistent/live selection.
  const auto clean_snapshot = fs.files;
  quarantined = true;
#if defined(ESP32)
  wifi2.pending = true; wifi2.request_id = 99; wifi2.deadline = fake_now + 30000;
  recovered.loop();
  assert(manager2.isEnabled());
  assert(manager2.getSelectedInterface() == InterfaceType::Bluetooth);
  assert(!recovered.setMode(CompanionMode::USB));
  assert(!wifi2.pending && !wifi2.approved);
#else
  controller.loop();
  assert(manager.isEnabled());
  assert(manager.getSelectedInterface() == InterfaceType::Bluetooth);
  assert(!controller.setMode(CompanionMode::USB));
#endif
  assert(fs.files == clean_snapshot);

  // Boot-time quarantine leaves manager disabled; console remains status-only.
  FakeTransport ble3, usb3;
  MultiSerialInterface manager3;
  manager3.addInterface(InterfaceType::Bluetooth, &ble3);
  manager3.addInterface(InterfaceType::USB, &usb3);
#if defined(ESP32)
  SerialWifiInterface wifi3;
  manager3.addInterface(InterfaceType::WiFi, &wifi3);
#endif
  manager3.enable();
  FakeStream console3;
  ConnectionController read_only;
  read_only.begin(store, manager3, console3,
#if defined(ESP32)
                  &wifi3,
#else
                  nullptr,
#endif
                  hooks());
  assert(!manager3.isEnabled());
  assert(!read_only.setMode(CompanionMode::USB));
  send(read_only, console3, "status\nmode usb\n");
  assert(fs.files == clean_snapshot);
  assert(console3.output.find("read-only") != std::string::npos);
  quarantined = false;

  // CLI rescue owns USB, so service console neither reads nor writes it.
  cli_rescue = true;
  FakeTransport ble4, usb4;
  MultiSerialInterface manager4;
  manager4.addInterface(InterfaceType::Bluetooth, &ble4);
  manager4.addInterface(InterfaceType::USB, &usb4);
  manager4.enable();
  FakeStream rescue_console;
  rescue_console.add("status\n");
  ConnectionController rescue;
  rescue.begin(store, manager4, rescue_console, nullptr, hooks());
  rescue.loop();
  assert(rescue_console.unread() == 7 && rescue_console.output.empty());
  cli_rescue = false;

  // Invalid config resets only connection settings; TX stays queued when USB
  // cannot accept bytes, then drains in bounded chunks.
  FakeFS bad_fs;
  bad_fs.files["/connection.cfg"] = {1, 2, 3};
  DataStore bad_store(bad_fs);
  FakeTransport bad_ble, bad_usb;
  MultiSerialInterface bad_manager;
  bad_manager.addInterface(InterfaceType::Bluetooth, &bad_ble);
  bad_manager.addInterface(InterfaceType::USB, &bad_usb);
  bad_manager.enable();
  FakeStream blocked_console;
  blocked_console.write_room = 0;
  ConnectionController repaired;
  repaired.begin(bad_store, bad_manager, blocked_console, nullptr, hooks());
  repaired.loop();
  assert(blocked_console.output.empty());
  blocked_console.write_room = 7;
  pump(repaired, 100);
  assert(blocked_console.output.find("identity was not changed") != std::string::npos);
  assert(blocked_console.max_write <= 7 && blocked_console.max_write <= 64);

  testModeChangeErrors();
  testCredentialFreeRecovery();
  testCredentialBearingRecovery();
  testRecoveryConsoleAndReplies();
  testForgetFailurePrivacy();
  testInfoReadOnly();
  testDeviceSettingsConsole();
  testPhysicalUsbServiceEntry();
  testApiConnectionControl();
  return 0;
}
'''


def linux_path(path: Path) -> str:
    resolved = path.resolve()
    if os.name != "nt":
        return str(resolved)
    return "/mnt/" + resolved.drive[0].lower() + resolved.as_posix()[2:]


def run_build(root: Path, esp32: bool) -> None:
    binary = root / ("controller-esp32" if esp32 else "controller-generic")
    sources = [
        root / "controller_test.cpp",
        root / "examples/companion_radio/ConnectionController.cpp",
    ]
    definitions = ["SMARTUI_CONNECTION_SELECTOR=1"]
    if esp32:
        definitions.append("ESP32=1")
    arguments = [
        "-std=c++17", "-O1", "-Wall", "-Wextra", "-Werror",
        *[f"-D{definition}" for definition in definitions],
        "-I", linux_path(root / "stubs"),
        "-I", linux_path(root / "examples/companion_radio"),
        "-I", linux_path(root / "src"),
        *[linux_path(source) for source in sources],
        "-o", linux_path(binary),
    ]
    if os.name == "nt":
        build = ["wsl", "--exec", "g++", *arguments]
        run = ["wsl", "--exec", linux_path(binary)]
    else:
        compiler = shutil.which("g++") or shutil.which("clang++")
        if not compiler:
            if os.environ.get("CI"):
                raise SystemExit("[FAIL] CI host C++ compiler missing")
            print("[SKIP] host C++ compiler missing")
            return
        build = [compiler, *arguments]
        run = [str(binary)]
    compiled = subprocess.run(
        build, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60)
    if compiled.returncode:
        raise SystemExit("[FAIL] ConnectionController compile:\n" + compiled.stdout + compiled.stderr)
    executed = subprocess.run(
        run, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=20)
    if executed.returncode:
        raise SystemExit("[FAIL] ConnectionController flow:\n" + executed.stdout + executed.stderr)


def main() -> None:
    source = (CONTROLLER / "ConnectionController.cpp").read_text(encoding="utf-8")
    assert "getSessionGeneration" not in source
    assert "_interfaces->sessionGeneration() != _api_mode_session" in source
    assert "_api_mode_session = _interfaces->sessionGeneration();" in source
    assert "noteSessionBoundary" not in source
    assert "while (_console" not in source
    main_source = (CONTROLLER / "main.cpp").read_text(encoding="utf-8")
    assert "usb_serial_interface.begin(Serial, isUsbCompanionLinkPresent)" in main_source
    assert "return Serial.dtr();" in main_source
    assert "if (connection_controller.status().usbConsoleEnabled)" in main_source
    assert main_source.index("connection_controller.loop();") < main_source.index("the_mesh.loop();")
    mesh_source = (CONTROLLER / "MyMesh.cpp").read_text(encoding="utf-8")
    arm = mesh_source.index("connection_controller.apiReplyQueued();")
    guard = mesh_source[max(0, arm - 500):arm]
    assert "queued == reply_length" in guard
    assert "cmd_frame[7] == 1" in guard
    assert "out_frame[8] == smartui::SmartUiApi::OK" in guard
    assert '"api mode ", 9' in guard
    with tempfile.TemporaryDirectory(prefix="smartui-connection-controller-") as raw:
        root = Path(raw)
        example = root / "examples/companion_radio"
        helpers = root / "stubs/helpers"
        esp_helpers = helpers / "esp32"
        source_helpers = root / "src/helpers"
        example.mkdir(parents=True)
        esp_helpers.mkdir(parents=True)
        source_helpers.mkdir(parents=True)
        for name in ("ConnectionController.cpp", "ConnectionController.h", "ConnectionTypes.h"):
            shutil.copy2(CONTROLLER / name, example / name)
        shutil.copy2(ROOT / "src/helpers/StorageTransaction.h", source_helpers / "StorageTransaction.h")
        shutil.copy2(ROOT / "src/helpers/SmartUiBuildInfo.h", source_helpers / "SmartUiBuildInfo.h")
        shutil.copy2(ROOT / "src/helpers/SmartUiSleepPolicy.h", source_helpers / "SmartUiSleepPolicy.h")
        shutil.copy2(ROOT / "src/helpers/SmartUiQuickReplies.h", source_helpers / "SmartUiQuickReplies.h")
        # Angle-bracket helper includes resolve through stubs first.
        shutil.copy2(source_helpers / "StorageTransaction.h", helpers / "StorageTransaction.h")
        (root / "stubs/Arduino.h").write_text(ARDUINO, encoding="utf-8")
        (helpers / "MultiSerialInterface.h").write_text(MULTI, encoding="utf-8")
        (root / "stubs/WiFi.h").write_text(WIFI, encoding="utf-8")
        (esp_helpers / "SerialWifiInterface.h").write_text(SERIAL_WIFI, encoding="utf-8")
        (example / "DataStore.h").write_text(DATA_STORE, encoding="utf-8")
        mesh_source = (CONTROLLER / "MyMesh.cpp").read_text(encoding="utf-8")
        entry_start = mesh_source.index("void MyMesh::enterCLIRescue() {")
        entry_end = mesh_source.index("void MyMesh::checkCLIRescueCmd()", entry_start)
        harness = HARNESS.replace("@@USB_SERVICE_ENTRY@@", mesh_source[entry_start:entry_end])
        (root / "controller_test.cpp").write_text(harness, encoding="utf-8")
        run_build(root, esp32=True)
        run_build(root, esp32=False)
    print("[PASS] ConnectionController persistence, recovery, privacy, console compatibility, staged API Wi-Fi, transactional save, secrets, session/timeout cleanup, ACK/drain-gated mode changes, settings guards")


if __name__ == "__main__":
    main()
