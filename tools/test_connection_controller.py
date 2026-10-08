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

static const uint8_t FILE_O_READ = 0;
static const uint8_t FILE_O_WRITE = 1;

#if defined(NRF52_PLATFORM)
#include <cassert>
using lfs_block_t = uint32_t;
static constexpr int LFS_ERR_CORRUPT = -52;
struct lfs_config { uint32_t block_count = 224; uint32_t block_size = 128; };
struct lfs_info { uint32_t size = 0; };
struct lfs_t {
  const lfs_config* cfg = nullptr;
  std::map<std::string, std::vector<uint8_t>>* files = nullptr;
  std::vector<std::string>* inspected_paths = nullptr;
  std::map<std::string, int> stat_errors;
  std::vector<lfs_block_t> blocks = {0, 1, 2};
  bool locked = false;
  int error = 0;
  unsigned calls = 0, locks = 0, unlocks = 0;
};
inline int lfs_traverse(lfs_t* fs, int (*callback)(void*, lfs_block_t), void* context) {
  assert(fs->locked);
  ++fs->calls;
  for (auto block : fs->blocks) { const int error = callback(context, block); if (error) return error; }
  return fs->error;
}
inline int lfs_stat(lfs_t* fs, const char* path, lfs_info* info) {
  assert(fs->locked);
  fs->inspected_paths->push_back(path);
  if (fs->stat_errors.count(path)) return fs->stat_errors[path];
  auto found = fs->files->find(path);
  if (found == fs->files->end()) return -2;
  info->size = static_cast<uint32_t>(found->second.size());
  return 0;
}
#endif

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
  std::string fail_read_open_path;
  std::string drop_flush_path;
  std::string corrupt_primary_on_remove;
  mutable std::vector<std::string> inspected_paths;
  unsigned write_open_count = 0;
  unsigned remove_attempt_count = 0;
  unsigned rename_attempt_count = 0;
  unsigned file_read_count = 0;
#if defined(NRF52_PLATFORM)
  lfs_config config;
  lfs_t lfs;
  FakeFS() { lfs.cfg = &config; lfs.files = &files; lfs.inspected_paths = &inspected_paths; }
  void _lockFS() { assert(!lfs.locked); lfs.locked = true; ++lfs.locks; }
  void _unlockFS() { assert(lfs.locked); lfs.locked = false; ++lfs.unlocks; }
  lfs_t* _getFS() { assert(lfs.locked); return &lfs; }
#endif

  void checkpoint() { if (record_snapshots) snapshots.push_back(files); }

  bool exists(const char* path) const {
#if defined(NRF52_PLATFORM)
    assert(!lfs.locked);  // File/exists methods must never recursively lock.
#endif
    inspected_paths.push_back(path);
    return files.count(path) != 0;
  }
  bool remove(const char* path) {
    ++remove_attempt_count;
    if (permanent_remove_path == path) return false;
    if (fail_remove_path == path) {
      fail_remove_path.clear();
      return false;
    }
    const bool removed = files.erase(path) != 0;
    if (corrupt_primary_on_remove == path) {
      corrupt_primary_on_remove.clear();
      if (!files["/connection.cfg"].empty()) files["/connection.cfg"][0] ^= 0xff;
    }
    if (removed) checkpoint();
    return removed;
  }
  bool rename(const char* from, const char* to) {
    ++rename_attempt_count;
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
  File open(const char* path, uint8_t mode);
};

class File {
  FakeFS* fs_ = nullptr;
  std::string path_;
  size_t offset_ = 0;
  bool open_ = false;
public:
  File() = default;
  File(FakeFS* fs, const char* path, bool write, bool append = false)
      : fs_(fs), path_(path), open_(fs != nullptr) {
    if (open_ && write) {
      const bool existed = fs_->files.count(path_) != 0;
      auto& bytes = fs_->files[path_];
      if (append) {
        offset_ = bytes.size();
        if (!existed) fs_->checkpoint();
      } else {
        bytes.clear();
        fs_->checkpoint();
      }
    }
  }
  explicit operator bool() const { return open_; }
  size_t size() const {
    auto found = fs_->files.find(path_);
    return found == fs_->files.end() ? 0 : found->second.size();
  }
  int read(uint8_t* out, size_t len) {
    if (!open_) return 0;
    ++fs_->file_read_count;
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
    if (open_ && fs_->drop_flush_path == path_) {
      fs_->drop_flush_path.clear();
      fs_->files.erase(path_);
      fs_->checkpoint();
    }
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
  if (!write) inspected_paths.push_back(path);
  if (!write && fail_read_open_path == path) return File();
  if (write) ++write_open_count;
  if (write && permanent_write_open_path == path) return File();
  if (write && fail_write_open_path == path) {
    fail_write_open_path.clear();
    return File();
  }
  if (!write && !exists(path)) return File();
  return File(this, path, write);
}

inline File FakeFS::open(const char* path, uint8_t mode) {
  const bool write = mode == FILE_O_WRITE;
  if (!write) inspected_paths.push_back(path);
  if (!write && fail_read_open_path == path) return File();
  if (write) ++write_open_count;
  if (write && permanent_write_open_path == path) return File();
  if (write && fail_write_open_path == path) {
    fail_write_open_path.clear();
    return File();
  }
  if (!write && !exists(path)) return File();
  // Match Adafruit_LittleFS: FILE_O_WRITE opens read/write, creates when
  // absent, then seeks to EOF.  It does not truncate an existing file.
  return File(this, path, write, write);
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

template <typename Fixture>
static std::string storageDiagnostic(Fixture& fixture, const char* phase) {
  pump(fixture.controller);  // Drain the unrelated initial console banner.
  fixture.console.output.clear();
  fixture.fs.inspected_paths.clear();
  const auto before = fixture.fs.files;
  const auto writes = fixture.fs.write_open_count;
  const auto removes = fixture.fs.remove_attempt_count;
  const auto renames = fixture.fs.rename_attempt_count;
  const auto resets = reset_count;
  const auto setting_calls = settings_calls;
  send(fixture.controller, fixture.console, "storage status\n");
  assert(fixture.fs.files == before);
  assert(fixture.fs.write_open_count == writes);
  assert(fixture.fs.remove_attempt_count == removes);
  assert(fixture.fs.rename_attempt_count == renames);
  assert(reset_count == resets && settings_calls == setting_calls);
  for (const auto& path : fixture.fs.inspected_paths) {
    assert(path == "/connection.cfg" || path == "/connection.cfg.tmp" ||
           path == "/connection.cfg.bak" || path == "/connection.forgot");
  }
  const auto& line = fixture.console.output;
  assert(line.find("Storage v=1 phase=" + std::string(phase) + " ") == 0);
  assert(line.size() < 320 && line.substr(line.size() - 2) == "\r\n");
  assert(line.find('\n') == line.size() - 1);
  assert(line.find("private-network") == std::string::npos);
  assert(line.find("private-password") == std::string::npos);
  assert(line.find("unrelated-secret") == std::string::npos);
  return line;
}

static void testStorageDiagnostics() {
  const char* phases[] = {
      "marker-open", "marker-verify", "clean-primary-remove", "clean-primary-open",
      "clean-primary-write", "clean-primary-verify", "clean-temp", "clean-backup",
      "clean-final-verify", "marker-remove", "recover-primary-remove",
      "recover-primary-open", "recover-primary-write", "recover-primary-verify",
      "recovery-blocked", "unavailable"};
  for (unsigned fault = 0; fault < sizeof(phases) / sizeof(phases[0]); ++fault) {
    RecoveryFixture f;
    f.fs.files["/prefs.json"] = {'u', 'n', 'r', 'e', 'l', 'a', 't', 'e', 'd', '-', 's', 'e', 'c', 'r', 'e', 't'};
    switch (fault) {
      case 0: f.fs.fail_write_open_path = "/connection.forgot"; break;
      case 1: f.fs.drop_flush_path = "/connection.forgot"; break;
      case 2: f.fs.files["/connection.cfg"] = {1}; f.fs.permanent_remove_path = "/connection.cfg"; break;
      case 3: f.fs.fail_write_open_path = "/connection.cfg"; break;
      case 4: f.fs.short_write_path = "/connection.cfg"; break;
      case 5: f.fs.corrupt_flush_path = "/connection.cfg"; break;
      case 6: case 7: {
        const char* path = fault == 6 ? "/connection.cfg.tmp" : "/connection.cfg.bak";
        f.fs.files["/connection.cfg"] = configRecord(CompanionMode::BLE);
        f.fs.files[path] = configRecord(CompanionMode::BLE, true);
        f.fs.permanent_remove_path = path;
        break;
      }
      case 8:
        f.fs.files["/connection.cfg"] = configRecord(CompanionMode::BLE);
        f.fs.files["/connection.cfg.tmp"] = configRecord(CompanionMode::BLE);
        f.fs.corrupt_primary_on_remove = "/connection.cfg.tmp";
        break;
      case 9:
        f.fs.files["/connection.cfg"] = configRecord(CompanionMode::BLE);
        f.fs.files["/connection.forgot"] = {};
        f.fs.permanent_remove_path = "/connection.forgot";
        break;
      case 10: case 11: case 12: case 13:
        f.fs.files["/connection.cfg"] = {1};
        f.fs.files["/connection.cfg.tmp"] = configRecord(CompanionMode::BLE, true);
        if (fault == 10) f.fs.permanent_remove_path = "/connection.cfg";
        if (fault == 11) f.fs.fail_write_open_path = "/connection.cfg";
        if (fault == 12) f.fs.short_write_path = "/connection.cfg";
        if (fault == 13) f.fs.corrupt_flush_path = "/connection.cfg";
        break;
      case 14: quarantined = true; break;
      case 15: f.store.available = false; break;
    }
    f.boot();
    assert(f.controller.status().storageRecoveryRequired);
    const auto first = storageDiagnostic(f, phases[fault]);
    assert(first.find(fault == 14 ? " local=1 global=1 " : " local=1 global=0 ") != std::string::npos);
    if (fault == 9) assert(first.find("marker=1:0:1") != std::string::npos);
    if (fault == 15) assert(first.find(" fs=0 ") != std::string::npos);
    // A refused mutation or repeated diagnostic must not replace the root cause.
    assert(!f.controller.setMode(CompanionMode::USB));
    assert(storageDiagnostic(f, phases[fault]) == first);
    quarantined = false;
  }

  // Present-but-unreadable and malformed records are metadata, never echoed.
  RecoveryFixture f;
  f.fs.files["/connection.cfg"] = configRecord(CompanionMode::BLE);
  f.boot();
  f.fs.files["/connection.cfg.tmp"] = configRecord(CompanionMode::BLE, true);
  f.fs.files["/connection.cfg.bak"] = {1, 2, 3};
  f.fs.files["/connection.forgot"] = {};
  f.fs.fail_read_open_path = "/connection.cfg.tmp";
  auto line = storageDiagnostic(f, "none");
  assert(line == "Storage v=1 phase=none local=0 global=0 fs=1 primary=1:109:1 temp=1:-1:0 backup=1:3:0 marker=1:0:1\r\n");
  f.fs.fail_read_open_path.clear();
  line = storageDiagnostic(f, "none");
  assert(line.find("temp=1:109:1") != std::string::npos);
  f.fs.inspected_paths.clear();
  send(f.controller, f.console, "storage status /prefs.json\n");
  assert(f.fs.inspected_paths.empty());  // No caller-supplied path is accepted.
  f.console.output.clear();
  send(f.controller, f.console, "help\n");
  assert(f.console.output.find("Commands: info | status | mode ble | mode usb | mode wifi | wifi setup | wifi status | wifi save | wifi cancel | wifi forget | reply get N | reply set N HEX | help\r\n") == 0);
  assert(f.console.output.find("E:S:V=exists:size:valid") != std::string::npos);
  assert(f.console.output.find("marker valid means readable presence, even empty.\r\n") != std::string::npos);
  assert(f.console.output.find("storage usage | storage legacy: rc:size; -2=absent; -1=unknown.\r\n") != std::string::npos);

  // Global quarantine can exist independently of a local config failure.
  RecoveryFixture global;
  global.fs.files["/connection.cfg"] = configRecord(CompanionMode::BLE, true);
  quarantined = true;
  global.boot();
  assert(storageDiagnostic(global, "none").find(" local=0 global=1 ") != std::string::npos);
  quarantined = false;

  // Existing nonfatal cleanup behavior is unchanged, but its failure is visible.
  RecoveryFixture leftover;
  leftover.fs.files["/connection.cfg"] = configRecord(CompanionMode::BLE, true);
  leftover.fs.files["/connection.cfg.tmp"] = configRecord(CompanionMode::BLE, true);
  leftover.fs.permanent_remove_path = "/connection.cfg.tmp";
  leftover.boot();
  assert(!leftover.controller.status().storageRecoveryRequired);
  storageDiagnostic(leftover, "recover-temp-cleanup");

  // A successful explicit retry clears the live flag, not historical evidence.
  RecoveryFixture retry;
  retry.fs.files["/connection.cfg"] = configRecord(CompanionMode::BLE);
  retry.fs.files["/connection.forgot"] = {1};
  retry.fs.permanent_remove_path = "/connection.forgot";
  retry.boot();
  storageDiagnostic(retry, "marker-remove");
  retry.fs.permanent_remove_path.clear();
  send(retry.controller, retry.console, "wifi forget\n");
  assert(!retry.controller.status().storageRecoveryRequired);
  assert(storageDiagnostic(retry, "marker-remove").find(" local=0 global=0 ") != std::string::npos);

  const char* save_phases[] = {"save-temp-remove", "save-temp-open", "save-temp-write",
      "save-temp-verify", "save-rotate", "save-publish", "save-final-verify"};
  for (unsigned fault = 0; fault < sizeof(save_phases) / sizeof(save_phases[0]); ++fault) {
    ModeChangeFixture save;
    switch (fault) {
      case 0: save.fs.files["/connection.cfg.tmp"] = {1}; save.fs.fail_remove_path = "/connection.cfg.tmp"; break;
      case 1: save.fs.fail_write_open_path = "/connection.cfg.tmp"; break;
      case 2: save.fs.short_write_path = "/connection.cfg.tmp"; break;
      case 3: save.fs.corrupt_flush_path = "/connection.cfg.tmp"; break;
      case 4: save.fs.fail_next_rename = true; break;
      case 5: save.fs.fail_rename_from = "/connection.cfg.tmp"; break;
      case 6: save.fs.corrupt_rename_to = "/connection.cfg"; break;
    }
    assert(!save.controller.setMode(CompanionMode::USB));
    storageDiagnostic(save, save_phases[fault]);
  }
}

static std::string storageUsage(RecoveryFixture& f) {
  pump(f.controller);
  f.console.output.clear();
  f.fs.inspected_paths.clear();
  const auto before = f.fs.files;
  const auto writes = f.fs.write_open_count, removes = f.fs.remove_attempt_count;
  const auto renames = f.fs.rename_attempt_count, reads = f.fs.file_read_count;
  const auto resets = reset_count;
  send(f.controller, f.console, "storage usage\n");
  assert(f.fs.files == before && f.fs.write_open_count == writes);
  assert(f.fs.remove_attempt_count == removes && f.fs.rename_attempt_count == renames);
  assert(f.fs.file_read_count == reads && reset_count == resets);
  for (const auto& path : f.fs.inspected_paths)
    assert(path == "/prefs.json" || path == "/prefs.json.tmp" || path == "/prefs.json.bak" ||
           path == "/new_prefs" || path == "/_main.id" || path == "/connection.forgot" ||
           path == "/contacts3");
  const auto& line = f.console.output;
  assert(line.find("StorageUsage v=1 source=primary ") == 0);
  assert(line.size() < 512 && line.substr(line.size() - 2) == "\r\n");
  assert(line.find('\n') == line.size() - 1);
  assert(line.find("private-password") == std::string::npos);
#if defined(NRF52_PLATFORM)
  assert(!f.fs.lfs.locked && f.fs.lfs.locks == f.fs.lfs.unlocks);
#endif
  return line;
}

static void testStorageUsage() {
  RecoveryFixture f;
  f.fs.fail_write_open_path = "/connection.forgot";
  f.fs.files["/prefs.json"] = std::vector<uint8_t>(2200, 'P');
  f.fs.files["/prefs.json.bak"] = std::vector<uint8_t>(2100, 'B');
  f.fs.files["/new_prefs"] = std::vector<uint8_t>(872, 'L');
  f.fs.files["/_main.id"] = std::vector<uint8_t>(152, 'I');
  f.fs.files["/contacts3"] = std::vector<uint8_t>(7200, 'C');
  f.boot();
  assert(f.controller.status().storageRecoveryRequired);
  std::string line = storageUsage(f);
#if defined(NRF52_PLATFORM)
  assert(line.find("mounted=1 result=ok block_size=128 total_blocks=224 used_blocks=3 error=0") != std::string::npos);
  assert(line.find("heap_free=8000 heap_min=-1 marker=-2:-1 prefs=0:2200 prefs_tmp=-2:-1") != std::string::npos);
  assert(f.fs.lfs.calls == 1 && f.fs.lfs.locks == 1);
#else
  assert(line.find("mounted=1 result=unsupported block_size=0 total_blocks=0 used_blocks=-1 error=0") != std::string::npos);
  assert(line.find("heap_free=-1 heap_min=-1 marker=-1:-1 prefs=0:2200 prefs_tmp=-1:-1") != std::string::npos);
#endif
  assert(line.find("prefs_bak=0:2100 legacy=0:872 identity=0:152 contacts=0:7200") != std::string::npos);
  storageDiagnostic(f, "marker-open");  // Usage cannot replace the recovery phase.
#if defined(NRF52_PLATFORM)
  f.fs.lfs.stat_errors["/prefs.json"] = -5;
  f.fs.lfs.stat_errors["/connection.forgot"] = -52;
  assert(storageUsage(f).find("marker=-52:-1 prefs=-5:-1 ") != std::string::npos);
  f.fs.lfs.stat_errors.clear();
  f.fs.files["/connection.forgot"] = {};
  assert(storageUsage(f).find("marker=0:0 ") != std::string::npos);
  f.fs.files.erase("/connection.forgot");
#else
  f.fs.fail_read_open_path = "/prefs.json";
  assert(storageUsage(f).find("prefs=-1:-1 ") != std::string::npos);
  f.fs.fail_read_open_path.clear();
#endif
  f.store.available = false;
  assert(storageUsage(f).find("mounted=0 result=unavailable") != std::string::npos);
  assert(f.fs.inspected_paths.empty());
  f.store.available = true;

#if defined(NRF52_PLATFORM)
  f.fs.lfs.blocks = {0, 1, 1, 2, 2};
  assert(storageUsage(f).find("used_blocks=3 error=0") != std::string::npos);
  f.fs.lfs.error = -5;
  assert(storageUsage(f).find("result=traverse-error block_size=128 total_blocks=224 used_blocks=-1 error=-5") != std::string::npos);
  f.fs.lfs.error = 0;
  f.fs.lfs.blocks = {224};  // Equal to block_count is already out of bounds.
  assert(storageUsage(f).find("used_blocks=-1 error=-52") != std::string::npos);
  f.fs.lfs.blocks = std::vector<lfs_block_t>(1000, 0);  // Corrupt cycle/visit limit.
  assert(storageUsage(f).find("used_blocks=-1 error=-52") != std::string::npos);
  const auto calls = f.fs.lfs.calls;
  f.fs.config.block_count = 1025;
  assert(storageUsage(f).find("result=geometry") != std::string::npos);
  assert(f.fs.lfs.calls == calls && f.fs.inspected_paths.empty());
  f.fs.lfs.cfg = nullptr;
  assert(storageUsage(f).find("result=unavailable") != std::string::npos);
  assert(f.fs.lfs.calls == calls && f.fs.inspected_paths.empty());
  f.fs.lfs.cfg = &f.fs.config;
  f.fs.config.block_count = 224;
  f.fs.lfs.blocks.clear();
  for (unsigned i = 0; i < 224; ++i) f.fs.lfs.blocks.push_back(i);
  assert(storageUsage(f).find("total_blocks=224 used_blocks=224 error=0") != std::string::npos);
#endif
  // Global quarantine grants diagnostics, not write access.
  RecoveryFixture global;
  global.fs.files["/connection.cfg"] = configRecord(CompanionMode::BLE);
  quarantined = true;
  global.boot();
  storageUsage(global);
  assert(!global.controller.deviceApiWritesAllowed());
  quarantined = false;
  f.fs.inspected_paths.clear();
  send(f.controller, f.console, "storage usage /anything\n");
  assert(f.fs.inspected_paths.empty());
}

static std::string storageLegacy(RecoveryFixture& f) {
  pump(f.controller);
  f.console.output.clear();
  f.fs.inspected_paths.clear();
  const auto before = f.fs.files;
  const auto writes = f.fs.write_open_count, removes = f.fs.remove_attempt_count;
  const auto renames = f.fs.rename_attempt_count, reads = f.fs.file_read_count;
  const auto resets = reset_count;
  send(f.controller, f.console, "storage legacy\n");
  assert(f.fs.files == before && f.fs.write_open_count == writes);
  assert(f.fs.remove_attempt_count == removes && f.fs.rename_attempt_count == renames);
  assert(f.fs.file_read_count == reads && reset_count == resets);
  for (const auto& path : f.fs.inspected_paths)
    assert(path == "/contacts3" || path == "/contacts3.tmp" || path == "/contacts3.bak" ||
           path == "/channels2" || path == "/channels2.tmp" || path == "/channels2.bak" ||
           path == "/_main.id.tmp" || path == "/_main.id.bak" || path == "/adv_blobs");
  const auto& line = f.console.output;
  assert(line.find("StorageLegacy v=1 source=primary ") == 0);
  assert(line.size() < 448 && line.substr(line.size() - 2) == "\r\n");
  assert(line.find('\n') == line.size() - 1);
  assert(line.find("private-password") == std::string::npos);
#if defined(NRF52_PLATFORM)
  assert(!f.fs.lfs.locked && f.fs.lfs.locks == f.fs.lfs.unlocks);
  assert(f.fs.lfs.calls == 0);  // No traversal or attempt to repair/mount.
#endif
  return line;
}

static void testStorageLegacy() {
  RecoveryFixture f;
  f.fs.fail_write_open_path = "/connection.forgot";
  const char* paths[] = {"/contacts3", "/contacts3.tmp", "/contacts3.bak",
      "/channels2", "/channels2.tmp", "/channels2.bak",
      "/_main.id.tmp", "/_main.id.bak", "/adv_blobs"};
  for (unsigned i = 0; i < 9; ++i) f.fs.files[paths[i]] = std::vector<uint8_t>(100 + i, 'P');
  f.boot();
  assert(f.controller.status().storageRecoveryRequired);
  std::string line = storageLegacy(f);
  assert(line.find("contacts=0:100 contacts_tmp=0:101 contacts_bak=0:102 channels=0:103 channels_tmp=0:104 channels_bak=0:105 identity_tmp=0:106 identity_bak=0:107 blobs=0:108") != std::string::npos);
  storageDiagnostic(f, "marker-open");
#if defined(NRF52_PLATFORM)
  assert(line.find("mounted=1 result=ok ") != std::string::npos);
  f.fs.lfs.stat_errors["/contacts3.tmp"] = -5;
  f.fs.files.erase("/channels2.bak");
  line = storageLegacy(f);
  assert(line.find("contacts_tmp=-5:-1 ") != std::string::npos);
  assert(line.find("channels_bak=-2:-1 ") != std::string::npos);
  f.fs.config.block_count = 0;
  assert(storageLegacy(f).find("result=geometry contacts=-1:-1 ") != std::string::npos);
  assert(f.fs.inspected_paths.empty());
  f.fs.config.block_count = 224;
  f.fs.lfs.cfg = nullptr;
  assert(storageLegacy(f).find("result=unavailable contacts=-1:-1 ") != std::string::npos);
  assert(f.fs.inspected_paths.empty());
  f.fs.lfs.cfg = &f.fs.config;
#else
  assert(line.find("mounted=1 result=unsupported ") != std::string::npos);
  f.fs.fail_read_open_path = "/contacts3.tmp";
  assert(storageLegacy(f).find("contacts_tmp=-1:-1 ") != std::string::npos);
#endif
  f.store.available = false;
  assert(storageLegacy(f).find("mounted=0 result=unavailable ") != std::string::npos);
  assert(f.fs.inspected_paths.empty());
  f.store.available = true;
  quarantined = true;
  storageLegacy(f);
  assert(!f.controller.deviceApiWritesAllowed());
  quarantined = false;
  f.fs.inspected_paths.clear();
  send(f.controller, f.console, "storage legacy /private\n");
  assert(f.fs.inspected_paths.empty());
}

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
  recovery.fs.files["/connection.forgot"] = {1};
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

static void testCleanBootDoesNotWrite() {
  RecoveryFixture clean;
  clean.fs.files["/connection.cfg"] = configRecord(CompanionMode::BLE);
  const auto before = clean.fs.files;
  // A healthy boot must not touch the recovery marker or any config record.
  clean.fs.fail_write_open_path = "/connection.forgot";
  clean.fs.fail_remove_path = "/connection.forgot";
  clean.boot();
  assert(!clean.controller.status().storageRecoveryRequired);
  assert(clean.manager.isEnabled());
  assert(clean.fs.files == before);
  assert(clean.fs.write_open_count == 0);
  assert(clean.fs.remove_attempt_count == 0);
  assert(clean.fs.rename_attempt_count == 0);
}

static void testNrfAppendSafeRecovery() {
#if defined(NRF52_PLATFORM)
  const auto clean = configRecord(CompanionMode::BLE);
  std::vector<std::vector<uint8_t>> malformed = {
      {}, {1, 2, 3}, std::vector<uint8_t>(108, 0x41),
      std::vector<uint8_t>(110, 0x42)};
  auto bad_crc = clean;
  bad_crc[105] ^= 0x80;
  malformed.push_back(bad_crc);
  auto oversized_secret = configRecord(CompanionMode::BLE, true);
  oversized_secret.push_back(0x43);
  malformed.push_back(oversized_secret);

  for (const auto& damaged : malformed) {
    RecoveryFixture repaired;
    repaired.fs.files["/connection.cfg"] = damaged;
    repaired.fs.record_snapshots = true;
    repaired.boot();
    assert(!repaired.controller.status().storageRecoveryRequired);
    assert(repaired.manager.isEnabled());
    assert(repaired.fs.files["/connection.cfg"] == clean);
    assert(!repaired.fs.exists("/connection.forgot"));
    assertNoCredentials(repaired.fs.files);
    // Every observable power-cut state remains recoverable on the next boot.
    for (const auto& snapshot : repaired.fs.snapshots) {
      assertCleanReboot(snapshot, CompanionMode::BLE);
    }
  }

  // A blocked invalid primary stays byte-for-byte unchanged: no append retry.
  // Once unlink works again, the same non-destructive WiFi cleanup command
  // replaces only connection metadata and releases recovery without reboot.
  RecoveryFixture blocked;
  auto malformed_primary = clean;
  malformed_primary[105] ^= 0x40;
  blocked.fs.files["/connection.cfg"] = malformed_primary;
  blocked.fs.permanent_remove_path = "/connection.cfg";
  blocked.boot();
  assert(blocked.controller.status().storageRecoveryRequired);
  assert(blocked.fs.files["/connection.cfg"] == malformed_primary);
  const unsigned writes_before_retry = blocked.fs.write_open_count;
  send(blocked.controller, blocked.console, "wifi forget\n");
  assert(blocked.controller.status().storageRecoveryRequired);
  assert(blocked.fs.files["/connection.cfg"] == malformed_primary);
  assert(blocked.fs.write_open_count == writes_before_retry);
  blocked.fs.permanent_remove_path.clear();
  send(blocked.controller, blocked.console, "wifi forget\n");
  assert(!blocked.controller.status().storageRecoveryRequired);
  assert(blocked.manager.isEnabled());
  assert(blocked.fs.files["/connection.cfg"] == clean);
  assert(!blocked.fs.exists("/connection.forgot"));

  // Interrupted cleanup marker: first unlink failure is explicit recovery;
  // retry removes the marker without rewriting an already-clean primary.
  RecoveryFixture marker;
  marker.fs.files["/connection.cfg"] = clean;
  marker.fs.files["/connection.forgot"] = {1};
  marker.fs.fail_remove_path = "/connection.forgot";
  marker.boot();
  assert(marker.controller.status().storageRecoveryRequired);
  assert(marker.fs.write_open_count == 0);
  send(marker.controller, marker.console, "wifi forget\n");
  assert(!marker.controller.status().storageRecoveryRequired);
  assert(marker.fs.write_open_count == 0);
  assert(!marker.fs.exists("/connection.forgot"));

  // Failed unlink is idempotent when the leftover is already exact and clean.
  RecoveryFixture clean_leftover;
  clean_leftover.fs.files["/connection.cfg"] = clean;
  clean_leftover.fs.files["/connection.cfg.tmp"] = clean;
  clean_leftover.fs.permanent_remove_path = "/connection.cfg.tmp";
  clean_leftover.boot();
  assert(!clean_leftover.controller.status().storageRecoveryRequired);
  assert(clean_leftover.fs.files["/connection.cfg.tmp"] == clean);
  assert(clean_leftover.fs.write_open_count == 1);  // marker only
  assert(!clean_leftover.fs.exists("/connection.forgot"));

  // A credential-bearing leftover that cannot be unlinked is never appended
  // to or claimed clean.  Recovery remains fail-closed until unlink succeeds.
  RecoveryFixture secret_leftover;
  const auto secret = configRecord(CompanionMode::BLE, true);
  secret_leftover.fs.files["/connection.cfg"] = clean;
  secret_leftover.fs.files["/connection.cfg.tmp"] = secret;
  secret_leftover.fs.permanent_remove_path = "/connection.cfg.tmp";
  secret_leftover.boot();
  assert(secret_leftover.controller.status().storageRecoveryRequired);
  assert(secret_leftover.fs.files["/connection.cfg.tmp"] == secret);
  assert(secret_leftover.fs.write_open_count == 1);  // marker only
  assert(secret_leftover.fs.exists("/connection.forgot"));
  secret_leftover.fs.permanent_remove_path.clear();
  send(secret_leftover.controller, secret_leftover.console, "wifi forget\n");
  assert(!secret_leftover.controller.status().storageRecoveryRequired);
  assertNoCredentials(secret_leftover.fs.files);
#endif
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
      first.fs.fail_remove_path.clear();
      first.fs.short_write_path.clear();
      first.fs.corrupt_flush_path.clear();
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
  local_recovery.fs.files["/connection.forgot"] = {1};
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

static std::string cli(ConnectionController& controller, const char* command, bool writable = true) {
  char guarded[159];
  memset(guarded, 0x5a, sizeof(guarded));
  assert(controller.handleCliCommand(command, guarded + 1, 157, writable));
  assert(guarded[0] == 0x5a && guarded[158] == 0x5a);
  assert(std::strlen(guarded + 1) <= 156);
  assert(!std::strchr(guarded + 1, '\r') && !std::strchr(guarded + 1, '\n'));
  const std::string reply = guarded + 1;
  assert(reply.find("api ") == std::string::npos);
  assert(reply.find("testpass") == std::string::npos && reply.find("testnet") == std::string::npos);
  return reply;
}

static void testCliQuickReplies() {
  quarantined = cli_rescue = reply_save_fail = false;
  RecoveryFixture f;
  f.boot();
  quick_replies[0].clear();
  assert(cli(f.controller, "ui reply get 1", false) == "OK ui reply slot=1 hex=-");
  assert(cli(f.controller, "ui reply set 1 d094d0b0") == "OK ui reply_saved slot=1");
  assert(cli(f.controller, "ui reply get 1") == "OK ui reply slot=1 hex=d094d0b0");
  const std::string before = quick_replies[0];
  for (const char* command : {"ui reply", "ui reply get", "ui reply set", "ui reply set 1", "ui reply set 1 ",
      "ui reply get 0", "ui reply get 10", "ui reply get 1 junk", "ui reply set 1 00", "ui reply set 1 0a",
      "ui reply set 1 c080", "ui reply set 1 eda080", "ui reply set 1 f4908080", "ui reply set 1 zz", "ui reply set 1 6"}) {
    assert(cli(f.controller, command) == "ERR ui invalid");
    assert(quick_replies[0] == before);
  }
  assert(cli(f.controller, "ui reply set 1 61", false) == "ERR ui readonly");
  quarantined = true;
  assert(cli(f.controller, "ui reply set 1 61") == "ERR ui readonly");
  assert(cli(f.controller, "ui reply get 1", false) == "OK ui reply slot=1 hex=d094d0b0");
  quarantined = false;
  reply_save_fail = true;
  assert(cli(f.controller, "ui reply set 1 61") == "ERR ui storage");
  reply_save_fail = false;
  assert(quick_replies[0] == before);
  for (size_t capacity = 0; capacity < 157; ++capacity) {
    char guarded[159]; memset(guarded, 0x5a, sizeof(guarded));
    assert(f.controller.handleCliCommand("ui reply set 1 61", guarded + 1, capacity, true));
    assert(guarded[0] == 0x5a && guarded[158] == 0x5a && quick_replies[0] == before);
  }
  const std::string max = "ui reply set 9 " + std::string(128, '6');
  assert(cli(f.controller, max.c_str()) == "OK ui reply_saved slot=9");
  assert(cli(f.controller, "ui reply get 9") == "OK ui reply slot=9 hex=" + std::string(128, '6'));
  assert(cli(f.controller, (max + "66").c_str()) == "ERR ui invalid");
  assert(cli(f.controller, "ui reply set 1 -") == "OK ui reply_saved slot=1");
  assert(quick_replies[0].empty());
  assert(cli(f.controller, "ui mode usb") == "OK ui mode target=usb state=pending");
  assert(cli(f.controller, "ui reply set 1 61") == "ERR ui busy");
  assert(quick_replies[0].empty());
}

static void testCliConnectionControl() {
  quarantined = cli_rescue = false;
#if defined(ESP32)
  WiFi = FakeWiFiClass();
#endif
  RecoveryFixture f;
  f.boot();
  auto& controller = f.controller;
  f.ble.connected = true;
  pump(controller);
  const auto initial = f.fs.files;
  assert(cli(controller, "ui connection") == "OK ui connection mode=ble client=ble caps=" +
      std::to_string(controller.status().capabilities) + " write=1");
  assert(cli(controller, "ui mode status", false) == "OK ui mode pending=none error=none");
  assert(cli(controller, "ui wifi status", false).find("OK ui wifi state=idle supported=") == 0);
  assert(cli(controller, "ui connection", false).find("write=0") != std::string::npos);
  assert(f.fs.files == initial);
  f.ble.connected = false;
  assert(cli(controller, "ui connection").find("client=none") != std::string::npos);
  f.ble.connected = true;

  char reply[157] = {};
  assert(!controller.handleCliCommand("ui caps", reply, sizeof(reply), true));
  assert(!controller.handleCliCommand("ui mode_extra usb", reply, sizeof(reply), true));
  assert(!controller.handleCliCommand(nullptr, reply, sizeof(reply), true));
  assert(controller.handleCliCommand("ui mode usb", nullptr, 157, true));
  for (size_t capacity : {size_t(0), size_t(1), size_t(15), size_t(156)}) {
    assert(controller.handleCliCommand("ui mode usb", reply, capacity, true));
    if (capacity >= 14) assert(strcmp(reply, "ERR ui buffer") == 0);
    assert(!controller.deviceApiBusy() && f.fs.files == initial);
  }
  assert(cli(controller, "ui mode usb", false) == "ERR ui readonly");
  assert(cli(controller, "ui mode") == "ERR ui invalid");
  assert(cli(controller, "ui mode invalid") == "ERR ui invalid");
  assert(cli(controller, ("ui wifi ssid " + std::string(160, '6')).c_str()) == "ERR ui invalid");
  assert(cli(controller, "ui mode usb\n") == "ERR ui invalid");
  assert(!controller.deviceApiBusy() && f.fs.files == initial);
  quarantined = true;
  assert(cli(controller, "ui connection").find("write=0") != std::string::npos);
  assert(cli(controller, "ui mode usb") == "ERR ui readonly");
  assert(cli(controller, "ui mode status") == "OK ui mode pending=none error=none");
  quarantined = false;

  assert(cli(controller, "ui mode usb") == "OK ui mode target=usb state=pending");
  assert(cli(controller, "ui mode status") == "OK ui mode pending=usb error=none");
  cli(controller, "ui wifi status");
  fake_now += 150;
  pump(controller);
  assert(controller.status().selected == CompanionMode::BLE && f.fs.files == initial);
  fake_now += 2000;
  pump(controller);
  assert(cli(controller, "ui mode status") == "OK ui mode pending=none error=timeout");
  cli(controller, "ui mode usb");
  controller.apiReplyQueued();
  f.manager.pending_tx = true;
  fake_now += 150;
  pump(controller);
  assert(controller.status().selected == CompanionMode::BLE);
  f.manager.pending_tx = false;
  pump(controller);
  assert(controller.status().selected == CompanionMode::USB);
  f.usb.connected = true;
  assert(cli(controller, "ui mode usb") == "OK ui mode target=usb state=active");
  cli(controller, "ui mode ble");
  controller.apiReplyQueued();
  controller.resetApiSession();
  fake_now += 200;
  pump(controller);
  assert(controller.status().selected == CompanionMode::USB);
  assert(cli(controller, "ui mode status") == "OK ui mode pending=none error=cancelled");
  assert(controller.setMode(CompanionMode::BLE));
  f.ble.connected = true;
  cli(controller, "ui mode usb");
  controller.apiReplyQueued();
  ++f.manager.session_generation;
  fake_now += 150;
  pump(controller);
  assert(controller.status().selected == CompanionMode::BLE);
  assert(cli(controller, "ui mode status") == "OK ui mode pending=none error=cancelled");
  cli(controller, "ui mode usb");
  controller.apiReplyQueued();
  f.fs.fail_write_open_path = "/connection.cfg.tmp";
  fake_now += 150;
  pump(controller);
  assert(controller.status().selected == CompanionMode::BLE);
  assert(cli(controller, "ui mode status") == "OK ui mode pending=none error=storage");

#if defined(ESP32)
  assert(cli(controller, "ui wifi begin", false) == "ERR ui readonly");
  assert(cli(controller, "ui mode wifi") == "ERR ui unconfigured");
  assert(cli(controller, "ui wifi begin") == "OK ui wifi begin state=ssid");
  assert(cli(controller, "ui wifi begin") == "ERR ui busy");
  assert(cli(controller, "ui mode usb") == "ERR ui busy");
  assert(cli(controller, "ui wifi status", false) == "OK ui wifi state=ssid supported=1 configured=0 associated=0 ip=none");
  assert(cli(controller, "ui wifi ssid 00") == "ERR ui invalid");
  assert(cli(controller, "ui wifi ssid 746573746e6574") == "OK ui wifi ssid state=password");
  assert(cli(controller, "ui wifi password 7465737470617373") == "OK ui wifi password state=ready");
  const auto before_test = f.fs.files;
  assert(cli(controller, "ui wifi test") == "OK ui wifi test state=testing");
  assert(WiFi.last_ssid == "testnet" && WiFi.last_password == "testpass");
  WiFi.status_code = WL_CONNECTED;
  pump(controller);
  assert(cli(controller, "ui wifi status") == "OK ui wifi state=test_ok supported=1 configured=0 associated=1 ip=192.0.2.7");
  assert(f.fs.files == before_test);
  f.fs.short_write_path = "/connection.cfg.tmp";
  assert(cli(controller, "ui wifi save") == "ERR ui storage");
  assert(!controller.status().wifiConfigured);
  assert(cli(controller, "ui wifi save") == "OK ui wifi save");
  assert(controller.status().wifiConfigured);
  assert(cli(controller, "ui wifi status").find("state=saved") != std::string::npos);
  cli(controller, "ui wifi begin");
  cli(controller, "ui wifi ssid 61");
  const std::string psk = "ui wifi password " + std::string(128, '6');
  assert(cli(controller, psk.c_str()) == "OK ui wifi password state=ready");
  controller.resetApiSession();
  assert(cli(controller, "ui wifi save") == "ERR ui stale");
  assert(!controller.deviceApiBusy());
  cli(controller, "ui wifi begin");
  cli(controller, "ui wifi ssid 61");
  assert(cli(controller, "ui wifi password -") == "OK ui wifi password state=ready");
  assert(cli(controller, "ui wifi cancel") == "OK ui wifi cancel");
  assert(cli(controller, "ui wifi status").find("state=cancelled") != std::string::npos);
  cli(controller, "ui wifi begin");
  fake_now += 120001;
  pump(controller);
  assert(cli(controller, "ui wifi status").find("state=timeout") != std::string::npos);
  assert(controller.setMode(CompanionMode::WiFi));
  assert(cli(controller, "ui wifi begin") == "ERR ui transport");
#else
  assert(cli(controller, "ui wifi begin") == "ERR ui unsupported");
  assert(cli(controller, "ui wifi status") == "OK ui wifi state=idle supported=0 configured=0 associated=0 ip=none");
#endif
  // Local recovery, independently of global quarantine, remains a write gate.
  RecoveryFixture blocked;
  blocked.fs.fail_write_open_path = "/connection.forgot";
  blocked.boot();
  assert(cli(blocked.controller, "ui connection").find("write=0") != std::string::npos);
  assert(cli(blocked.controller, "ui mode usb") == "ERR ui readonly");
  assert(cli(blocked.controller, "ui mode status") == "OK ui mode pending=none error=none");
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
  testStorageDiagnostics();
  testStorageUsage();
  testStorageLegacy();
  testCleanBootDoesNotWrite();
  testNrfAppendSafeRecovery();
  testCredentialFreeRecovery();
  testCredentialBearingRecovery();
  testRecoveryConsoleAndReplies();
  testForgetFailurePrivacy();
  testInfoReadOnly();
  testDeviceSettingsConsole();
  testPhysicalUsbServiceEntry();
  testApiConnectionControl();
  testCliQuickReplies();
  testCliConnectionControl();
  return 0;
}
'''


def linux_path(path: Path) -> str:
    resolved = path.resolve()
    if os.name != "nt":
        return str(resolved)
    return "/mnt/" + resolved.drive[0].lower() + resolved.as_posix()[2:]


def run_build(root: Path, platform: str) -> None:
    binary = root / ("controller-" + platform)
    sources = [
        root / "controller_test.cpp",
        root / "examples/companion_radio/ConnectionController.cpp",
    ]
    definitions = ["SMARTUI_CONNECTION_SELECTOR=1"]
    if platform == "esp32":
        definitions.append("ESP32=1")
    elif platform == "nrf52":
        definitions.append("NRF52_PLATFORM=1")
    arguments = [
        "-std=c++17", "-O1", "-Wall", "-Wextra", "-Werror",
        *[f"-D{definition}" for definition in definitions],
        "-I", linux_path(root / "stubs"),
        "-I", linux_path(root / "examples/companion_radio"),
        "-I", linux_path(root / "src"),
        *[linux_path(source) for source in sources],
        "-o", linux_path(binary),
    ]
    if os.environ.get("SMARTUI_TEST_SANITIZE") == "1":
        arguments += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie"]
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
    assert "if (arm_mode && queued == reply_length)" in guard
    cli_source = (CONTROLLER / "SmartUiCli.cpp").read_text(encoding="utf-8")
    assert '"ui mode %s"' in cli_source
    assert '"OK ui mode target=%s state=pending"' in cli_source
    assert "strcmp(_command, command) == 0 && strcmp(_reply, reply) == 0" in cli_source
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
        (root / "stubs/Adafruit_LittleFS.h").write_text('#pragma once\n#include <Arduino.h>\n', encoding="utf-8")
        (root / "stubs/utility").mkdir()
        (root / "stubs/utility/debug.h").write_text('#pragma once\ninline int dbgHeapFree() { return 8000; }\n', encoding="utf-8")
        (helpers / "MultiSerialInterface.h").write_text(MULTI, encoding="utf-8")
        (root / "stubs/WiFi.h").write_text(WIFI, encoding="utf-8")
        (esp_helpers / "SerialWifiInterface.h").write_text(SERIAL_WIFI, encoding="utf-8")
        (example / "DataStore.h").write_text(DATA_STORE, encoding="utf-8")
        mesh_source = (CONTROLLER / "MyMesh.cpp").read_text(encoding="utf-8")
        entry_start = mesh_source.index("void MyMesh::enterCLIRescue() {")
        entry_end = mesh_source.index("void MyMesh::checkCLIRescueCmd()", entry_start)
        harness = HARNESS.replace("@@USB_SERVICE_ENTRY@@", mesh_source[entry_start:entry_end])
        (root / "controller_test.cpp").write_text(harness, encoding="utf-8")
        run_build(root, "esp32")
        run_build(root, "generic")
        run_build(root, "nrf52")
    print("[PASS] ConnectionController generic/ESP32/nRF52 persistence, append-safe recovery, zero-write clean boot, bounded read-only storage diagnostics, exact failure phases, privacy, console compatibility, staged API Wi-Fi, transactional save, secrets, session/timeout cleanup, ACK/drain-gated mode changes, settings guards")


if __name__ == "__main__":
    main()
