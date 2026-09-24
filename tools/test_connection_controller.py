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
  std::map<std::string, std::vector<uint8_t>> files;
  bool fail_next_rename = false;
  std::string fail_remove_path;

  bool exists(const char* path) const { return files.count(path) != 0; }
  bool remove(const char* path) {
    if (fail_remove_path == path) {
      fail_remove_path.clear();
      return false;
    }
    return files.erase(path) != 0;
  }
  bool rename(const char* from, const char* to) {
    if (fail_next_rename) {
      fail_next_rename = false;
      return false;
    }
    auto found = files.find(from);
    if (found == files.end()) return false;
    files[to] = found->second;
    files.erase(found);
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
    if (open_ && write) fs_->files[path_].clear();
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
    auto& bytes = fs_->files[path_];
    if (bytes.size() < offset_ + len) bytes.resize(offset_ + len);
    std::memcpy(bytes.data() + offset_, data, len);
    offset_ += len;
    return len;
  }
  void flush() {}
  void close() { open_ = false; }
};

inline File FakeFS::open(const char* path, const char* mode, bool) {
  const bool write = mode && mode[0] == 'w';
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
  bool addInterface(InterfaceType type, BaseSerialInterface* interface) {
    for (auto& item : items_) if (!item.interface) { item = {type, interface}; return true; }
    return false;
  }
  bool hasInterface(InterfaceType type) const { return find(type) != nullptr; }
  bool selectExclusive(InterfaceType type) {
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
  explicit DataStore(FILESYSTEM& fs) : fs_(&fs) {}
  FILESYSTEM* getPrimaryFS() const { return fs_; }
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

static ConnectionControllerHooks hooks() {
  ConnectionControllerHooks value;
  value.resetLocalSession = resetSession;
  value.setWifiSleepInhibit = setSleep;
  value.isCliRescue = isCli;
  value.isStorageQuarantined = isQuarantined;
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

#if defined(ESP32)
static bool containsBytes(const std::vector<uint8_t>& bytes, const char* text) {
  const std::string haystack(bytes.begin(), bytes.end());
  return haystack.find(text) != std::string::npos;
}
#endif

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
  assert(controller.resolveWifiClient(71, true));
  assert(reset_count == before_approval_reset);  // MyMesh alone observes epochs.

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
    assert "sessionGeneration()" not in source
    assert "noteSessionBoundary" not in source
    assert "while (_console" not in source
    main_source = (CONTROLLER / "main.cpp").read_text(encoding="utf-8")
    assert "usb_serial_interface.begin(Serial, isUsbCompanionLinkPresent)" in main_source
    assert "return Serial.dtr();" in main_source
    assert "if (connection_controller.status().usbConsoleEnabled)" in main_source
    assert main_source.index("connection_controller.loop();") < main_source.index("the_mesh.loop();")
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
        # Angle-bracket helper includes resolve through stubs first.
        shutil.copy2(source_helpers / "StorageTransaction.h", helpers / "StorageTransaction.h")
        (root / "stubs/Arduino.h").write_text(ARDUINO, encoding="utf-8")
        (helpers / "MultiSerialInterface.h").write_text(MULTI, encoding="utf-8")
        (root / "stubs/WiFi.h").write_text(WIFI, encoding="utf-8")
        (esp_helpers / "SerialWifiInterface.h").write_text(SERIAL_WIFI, encoding="utf-8")
        (example / "DataStore.h").write_text(DATA_STORE, encoding="utf-8")
        (root / "controller_test.cpp").write_text(HARNESS, encoding="utf-8")
        run_build(root, esp32=True)
        run_build(root, esp32=False)
    print("[PASS] ConnectionController persistence, recovery, hidden setup, bounded console, retry, approval, quarantine")


if __name__ == "__main__":
    main()
