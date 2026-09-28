#!/usr/bin/env python3
"""Exercise production nRF52 BLE queue/session methods under a task scheduler model.

Compile the real class declaration, ring queue and transport method bodies with
Bluefruit/FreeRTOS stubs. Instrument every ring payload/index mutation to request
callback preemption; the FreeRTOS model defers it until taskEXIT_CRITICAL. This
is a host interleaving regression, not a SoftDevice or on-device BLE stack test.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NRF = ROOT / "src/helpers/nrf52"


def function(source, signature):
    start = source.index(signature)
    begin = source.index("{", start)
    depth, end = 1, begin + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


STUBS = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <deque>
#include <functional>
#include <vector>
static unsigned critical_depth = 0;
static unsigned point_count = 0, target_point = 0;
static bool pending = false;
static std::function<void()> preempt;
static void schedulePoint() {
  ++point_count;
  if (target_point && point_count == target_point) pending = true;
  if (!critical_depth && pending) {
    pending = false; auto callback = preempt; preempt = {}; callback();
  }
}
static void enterCritical() { ++critical_depth; }
static void exitCritical() {
  assert(critical_depth); --critical_depth;
  if (!critical_depth && pending) {
    pending = false; auto callback = preempt; preempt = {}; callback();
  }
}
#define taskENTER_CRITICAL() enterCritical()
#define taskEXIT_CRITICAL() exitCritical()
static unsigned long tick = 1000;
static unsigned long millis() { assert(!critical_depth); return tick; }
static bool physical_connected = false;
static uint16_t physical_handle = 1;
static std::function<void()> read_hook, available_hook, write_hook;
static size_t write_result = SIZE_MAX;
static std::vector<std::vector<uint8_t>> writes;
static std::vector<uint16_t> written_handles;
#define BLE_CONN_HANDLE_INVALID 0xffff
#define NRF_SUCCESS 0
#define BLE_HCI_REMOTE_USER_TERMINATED_CONNECTION 0x13
struct ble_evt_t {};
struct ble_gap_addr_t {};
struct ble_gap_conn_sec_t {};
struct ble_gap_conn_params_t {
  uint16_t min_conn_interval, max_conn_interval, slave_latency, conn_sup_timeout;
};
static unsigned sd_ble_gap_conn_sec_get(uint16_t handle, ble_gap_conn_sec_t*) {
  assert(!critical_depth);
  return physical_connected && handle == physical_handle ? NRF_SUCCESS : 1;
}
static unsigned sd_ble_gap_disconnect(uint16_t, uint8_t) {
  assert(!critical_depth); physical_connected = false; return NRF_SUCCESS;
}
static unsigned sd_ble_gap_conn_param_update(uint16_t, ble_gap_conn_params_t*) {
  assert(!critical_depth); return NRF_SUCCESS;
}
static unsigned sd_ble_gap_adv_addr_get(uint16_t, ble_gap_addr_t*) {
  assert(!critical_depth); return NRF_SUCCESS;
}
struct BLEDfu {};
struct BLEUart {
  std::deque<uint8_t> bytes;
  int available() {
    assert(!critical_depth); const int n = int(bytes.size());
    if (available_hook) { auto h = available_hook; available_hook = {}; h(); }
    return n;
  }
  int read(uint8_t* out, size_t n) {
    assert(!critical_depth);
    const size_t count = std::min(n, bytes.size());
    for (size_t i = 0; i < count; ++i) {out[i] = bytes.front(); bytes.pop_front();}
    if (read_hook) {auto h = read_hook; read_hook = {}; h();}
    return int(count);
  }
  size_t write(uint16_t handle, const uint8_t* data, size_t n) {
    assert(!critical_depth);
    writes.emplace_back(data, data + n); written_handles.push_back(handle);
    if (write_hook) {auto h = write_hook; write_hook = {}; h();}
    return write_result == SIZE_MAX ? n : write_result;
  }
};
struct {
  struct {
    void restartOnDisconnect(bool) { assert(!critical_depth); }
    void start(int) { assert(!critical_depth); }
    void stop() { assert(!critical_depth); }
  } Advertising;
} Bluefruit;
'''

TESTS = r'''
static void resetHarness() {
  assert(!critical_depth);
  target_point = point_count = 0; pending = false; preempt = {};
  available_hook = read_hook = write_hook = {};
  write_result = SIZE_MAX; writes.clear(); written_handles.clear(); tick = 1000;
  physical_connected = false; physical_handle = 1;
}
static void connect(SerialBLEInterface& s, uint16_t handle = 1) {
  instance = &s; s.enable(); physical_handle = handle; physical_connected = true;
  SerialBLEInterface::onConnect(handle); SerialBLEInterface::onSecured(handle);
  assert(s.isConnected());
}
static void receive(SerialBLEInterface& s, uint8_t b, size_t n = 1) {
  for(size_t i = 0; i < n; ++i) s.bleuart.bytes.push_back(b);
  SerialBLEInterface::onBleUartRX(physical_handle);
}
static void reconnect(SerialBLEInterface& s, uint16_t handle = 1) {
  physical_connected = false; SerialBLEInterface::onDisconnect(physical_handle, 0);
  connect(s, handle);
}
static void arm(unsigned point, std::function<void()> callback) {
  point_count = 0; target_point = point; preempt = callback;
}
static void disarm() {target_point = 0; preempt = {}; assert(!pending);}

int main() {
  uint8_t out[MAX_FRAME_SIZE] = {};
  // Every real pop mutation: payload copy, head advance and length decrement.
  // Old A/B slots remain in storage; arriving C must never become stale B.
  for(unsigned point = 1; point <= 3; ++point) {
    resetHarness(); SerialBLEInterface s; connect(s);
    receive(s, 0xA1); receive(s, 0xB2);
    assert(s.checkRecvFrame(out) == 1 && out[0] == 0xA1);
    assert(s.checkRecvFrame(out) == 1 && out[0] == 0xB2);
    receive(s, 0xA1);
    arm(point, [&] {receive(s, 0xC3);});
    assert(s.checkRecvFrame(out) == 1 && out[0] == 0xA1);
    assert(!preempt); disarm();
    assert(s.checkRecvFrame(out) == 1 && out[0] == 0xC3);
    assert(s.checkRecvFrame(out) == 0);
  }
  // Preemption at both enqueue mutations: session reset cannot publish stale
  // bytes after reset, and cannot observe partially initialized frame storage.
  for(unsigned point = 1; point <= 2; ++point) {
    resetHarness(); SerialBLEInterface s; connect(s);
    arm(point, [&] {reconnect(s);});
    receive(s, 0xA1); assert(!preempt); disarm();
    assert(!s.isReadBusy()); receive(s, 0xC3);
    assert(s.checkRecvFrame(out) == 1 && out[0] == 0xC3);
  }
  // Capacity, drop-newest, payload integrity, repeated ring wrapping.
  resetHarness(); SerialBLEInterface s; connect(s);
  for(unsigned round = 0; round < 20; ++round) {
    for(unsigned i = 0; i < FRAME_QUEUE_SIZE + 5; ++i) receive(s, i, MAX_FRAME_SIZE);
    assert(s.recv_queue.size() == FRAME_QUEUE_SIZE);
    for(unsigned i = 0; i < FRAME_QUEUE_SIZE; ++i) {
      assert(s.checkRecvFrame(out) == MAX_FRAME_SIZE);
      for(auto b : out) assert(b == i);
    }
    assert(!s.isReadBusy());
  }
  receive(s, 0xee, MAX_FRAME_SIZE + 1);
  assert(s.bleuart.bytes.empty() && !s.isReadBusy());

  // Reset/disconnect during a FIFO read: local old-generation payload rejected.
  read_hook = [&] {reconnect(s);}; receive(s, 0xA1);
  assert(!s.isReadBusy() && !s._rx_active);
  receive(s, 0xC3); assert(s.checkRecvFrame(out) == 1 && out[0] == 0xC3);
  read_hook = [&] {s.disable();}; receive(s, 0xA1);
  assert(!s.isEnabled() && !s.isConnected() && !s.isReadBusy());
  receive(s, 0xB2); assert(s.bleuart.bytes.empty() && !s.isReadBusy());
  connect(s);

  // Framework allocation-failure inline RX fallback: no second FIFO reader,
  // and no combined/tail frame from overlapping writes.
  read_hook = [&] {receive(s, 0xB2);}; receive(s, 0xA1);
  assert(!s.isReadBusy() && s.bleuart.bytes.empty() && !s._rx_active);
  // Specifically arrive after available() observed empty, before ownership exit.
  read_hook = [&] {available_hook = [&] {receive(s, 0xB2);};};
  receive(s, 0xA1);
  assert(s.checkRecvFrame(out) == 1 && out[0] == 0xA1);
  assert(!s.isReadBusy() && s.bleuart.bytes.empty() && !s._rx_active);

  // Queue clear head/count cuts are atomic relative to callback enqueue.
  for(unsigned point = 1; point <= 4; ++point) {
    receive(s, 0xA1);
    arm(point, [&] {receive(s, 0xB2);});
    s.disconnect(); assert(!preempt); disarm();
    assert(!s.isReadBusy() && !s.isWriteBusy()); connect(s);
  }

  // In-flight TX completion, success and failure, never consumes a newly
  // connected session's head or updates its retry timestamp (including reuse
  // of the same numeric connection handle).
  for(unsigned result : {0u, 1u}) {
    for(uint16_t next_handle : {uint16_t(1), uint16_t(2)}) {
      resetHarness(); SerialBLEInterface t; connect(t);
      const uint8_t old_frame = 0xA1, new_frame = 0xC3;
      assert(t.writeFrame(&old_frame, 1) == 1);
      write_result = result;
      write_hook = [&] {reconnect(t, next_handle); assert(t.writeFrame(&new_frame, 1) == 1);};
      t.checkRecvFrame(out);
      assert(t.send_queue.size() == 1 && t._last_retry_attempt == 0);
      write_result = SIZE_MAX; t.checkRecvFrame(out);
      assert(t.send_queue.size() == 0 && writes.size() == 2);
      assert(writes[1][0] == new_frame && written_handles[1] == next_handle);
    }
  }
  resetHarness(); SerialBLEInterface t; connect(t);
  uint8_t frame[2] = {0xA1, 0xB2};
  assert(!t.writeFrame(frame, 0) && !t.writeFrame(frame, MAX_FRAME_SIZE + 1));
  for(unsigned i = 0; i < FRAME_QUEUE_SIZE; ++i) assert(t.writeFrame(frame, 2) == 2);
  assert(t.isWriteBusy() && !t.writeFrame(frame, 2));
  write_result = 0; t.checkRecvFrame(out);
  assert(t.send_queue.size() == FRAME_QUEUE_SIZE && t._last_retry_attempt == tick);
  tick += BLE_RETRY_THROTTLE_MS - 1; t.checkRecvFrame(out); assert(writes.size() == 1);
  ++tick; write_result = 1; t.checkRecvFrame(out); // explicit partial write drops head
  assert(writes.size() == 2 && t.send_queue.size() == FRAME_QUEUE_SIZE - 1);
  assert(t._last_retry_attempt == 0);
  t.disable(); assert(!t.writeFrame(frame, 2) && !t.isWriteBusy());
  assert(t.checkRecvFrame(out) == 0);
  connect(t);
#if SMARTUI_CONNECTION_SELECTOR
  const uint32_t epoch = t.sessionGeneration();
  SerialBLEInterface::onSecured(physical_handle);
  SerialBLEInterface::onDisconnect(99, 0);
  assert(t.sessionGeneration() == epoch && t.isConnected());
  t.disconnect(); assert(t.sessionGeneration() != epoch && !t.isConnected());
  const uint32_t ended = t.sessionGeneration();
  SerialBLEInterface::onDisconnect(physical_handle, 0);
  assert(t.sessionGeneration() == ended); // no double end
#endif
  assert(!critical_depth);
  puts("PASS nRF BLE production queue: preemption, bursts, wrap, reset, disconnect/reconnect, RX overlap, TX epoch/retry");
}
'''


def main():
    source = (NRF / "SerialBLEInterface.cpp").read_text(encoding="utf-8")
    assert "bleuart.flush(" not in source
    assert "bleuart.readBytes(" not in source
    assert "bleuart.setRxCallback(onBleUartRX)" in source
    # Extract all relevant production bodies, not simplified replacements.
    names = [
        ("void", "onConnect"), ("void", "onDisconnect"), ("void", "onSecured"),
        ("void", "clearBuffersLocked"), ("bool", "isValidConnection"),
        ("bool", "isAdvertising"), ("void", "enable"), ("void", "disconnect"),
        ("void", "disable"), ("size_t", "writeFrame"), ("size_t", "checkRecvFrame"),
        ("void", "onBleUartRX"), ("bool", "isEnabled"), ("bool", "isConnected"),
        ("bool", "isReadBusy"), ("bool", "isWriteBusy"),
    ]
    methods = "\n".join(function(source, f"{kind} SerialBLEInterface::{name}(") for kind, name in names)
    methods += "\n#if SMARTUI_CONNECTION_SELECTOR\n"
    methods += function(source, "void SerialBLEInterface::advanceSessionGenerationLocked(") + "\n"
    methods += function(source, "uint32_t SerialBLEInterface::sessionGeneration(") + "\n#endif\n"
    prefix = source[source.index("// Magic numbers"):source.index("void SerialBLEInterface::onConnect(")]
    header = (NRF / "SerialBLEInterface.h").read_text(encoding="utf-8")
    # Expose state only in the test copy; no production friend/test API required.
    header = header.replace("class SerialBLEInterface :", "struct SerialBLEInterface :")
    header = header.replace('#include "../BaseSerialInterface.h"', '#include "BaseSerialInterface.h"')
    queue = (NRF / "BoundedFrameQueue.h").read_text(encoding="utf-8")
    for statement in ["_head = 0;", "_size = 0;", "_frames[(_head + _size) % Capacity] = frame;",
                      "++_size;", "frame = _frames[_head];", "_head = (_head + 1) % Capacity;", "--_size;"]:
        # Initial field declarations are not scheduling points.
        queue = queue.replace(statement, statement + " schedulePoint();")
    queue = queue.replace("size_t _head = 0; schedulePoint();", "size_t _head = 0;")
    queue = queue.replace("size_t _size = 0; schedulePoint();", "size_t _size = 0;")
    with tempfile.TemporaryDirectory(prefix="smartui-nrf-queue-") as raw:
        out = Path(raw)
        (out / "Arduino.h").write_text("#pragma once\n", encoding="utf-8")
        (out / "bluefruit.h").write_text("#pragma once\n", encoding="utf-8")
        (out / "BaseSerialInterface.h").write_text((ROOT / "src/helpers/BaseSerialInterface.h").read_text(), encoding="utf-8")
        (out / "SerialBLEInterface.h").write_text(header, encoding="utf-8")
        (out / "BoundedFrameQueue.h").write_text(queue, encoding="utf-8")
        cpp = out / "test.cpp"
        cpp.write_text(STUBS + '\n#include "SerialBLEInterface.h"\n' + prefix + methods + TESTS, encoding="utf-8")
        for selector in (0, 1):
            binary = out / f"test-{selector}"
            flags = ["-std=c++17", "-O1", "-Wall", "-Wextra", f"-DSMARTUI_CONNECTION_SELECTOR={selector}"]
            if os.name == "nt":
                def linux(p):
                    return "/mnt/" + p.drive[0].lower() + p.as_posix()[2:]
                build = ["wsl", "--exec", "g++", *flags, "-I" + linux(out), linux(cpp), "-o", linux(binary)]
                run = ["wsl", "--exec", linux(binary)]
            else:
                cxx = shutil.which("g++") or shutil.which("clang++")
                if not cxx:
                    raise RuntimeError("A C++ compiler is required")
                build = [cxx, *flags, "-I" + str(out), str(cpp), "-o", str(binary)]
                run = [str(binary)]
            subprocess.run(build, check=True, timeout=60)
            subprocess.run(run, check=True, timeout=30)
            print(f"PASS selector={selector}; all stubbed BLE I/O asserted outside critical sections")


if __name__ == "__main__":
    main()
