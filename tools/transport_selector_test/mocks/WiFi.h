#pragma once

#include <Arduino.h>
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <deque>
#include <memory>
#include <unordered_map>
#include <vector>

enum wifi_mode_t {
  WIFI_MODE_NULL = 0,
  WIFI_MODE_STA = 1,
  WIFI_MODE_AP = 2,
  WIFI_MODE_APSTA = 3,
};
static const int WL_CONNECTED = 3;
static const int WL_DISCONNECTED = 6;
extern bool g_mock_wifi_initialized;
extern wifi_mode_t g_mock_wifi_mode;
extern int g_mock_wifi_status;
extern unsigned g_mock_wifi_status_calls;

class MockWiFiClass {
public:
  // Pinned core getMode() is safe before WiFi initialization.
  wifi_mode_t getMode() const {
    return g_mock_wifi_initialized ? g_mock_wifi_mode : WIFI_MODE_NULL;
  }
  int status() const {
    assert(g_mock_wifi_initialized && "WiFi status queried before initialization");
    ++g_mock_wifi_status_calls;
    return g_mock_wifi_status;
  }
};
extern MockWiFiClass WiFi;

class IPAddress {
  uint8_t _bytes[4];

public:
  IPAddress(uint8_t a = 0, uint8_t b = 0, uint8_t c = 0, uint8_t d = 0)
      : _bytes{a, b, c, d} {}
  uint8_t operator[](size_t index) const { return _bytes[index]; }
};

struct MockWiFiClientState {
  bool connected = true;
  int fd = -1;
  IPAddress remote_ip;
  std::deque<uint8_t> rx;
  std::vector<uint8_t> tx;
};

extern std::unordered_map<int, std::weak_ptr<MockWiFiClientState>>
    g_mock_wifi_clients;

class WiFiClient : public Stream {
  std::shared_ptr<MockWiFiClientState> _state;

public:
  WiFiClient() = default;
  explicit WiFiClient(const std::shared_ptr<MockWiFiClientState>& state)
      : _state(state) {
    if (_state) g_mock_wifi_clients[_state->fd] = _state;
  }

  std::shared_ptr<MockWiFiClientState> state() const { return _state; }
  uint8_t connected() {
    return _state && _state->connected;
  }
  operator bool() { return connected(); }
  void stop() {
    if (_state) _state->connected = false;
  }
  int available() override {
    return connected() ? static_cast<int>(_state->rx.size()) : 0;
  }
  int read() override {
    if (available() <= 0) return -1;
    const uint8_t value = _state->rx.front();
    _state->rx.pop_front();
    return value;
  }
  int peek() override {
    return available() > 0 ? _state->rx.front() : -1;
  }
  size_t read(uint8_t* out, size_t len) {
    size_t count = 0;
    while (count < len && available() > 0) out[count++] = read();
    return count;
  }
  size_t readBytes(uint8_t* out, size_t len) override {
    return read(out, len);
  }
  size_t write(const uint8_t* data, size_t len) override {
    if (!connected()) return 0;
    _state->tx.insert(_state->tx.end(), data, data + len);
    return len;
  }
  size_t write(uint8_t value) override { return write(&value, 1); }
  int fd() const { return _state ? _state->fd : -1; }
  IPAddress remoteIP() const {
    return _state ? _state->remote_ip : IPAddress();
  }
};

extern bool g_mock_wifi_server_begin_succeeds;
extern unsigned g_mock_wifi_server_begin_calls;
extern std::deque<WiFiClient> g_mock_wifi_accept_queue;

class WiFiServer {
  bool _listening = false;

public:
  WiFiServer(uint16_t = 80, uint8_t = 4) {}
  void begin(uint16_t = 0) {
    // Real lwIP may assert in tcpip_send_msg_wait_sem instead of returning
    // a recoverable bind/listen error when its mailbox does not exist yet.
    assert(g_mock_wifi_initialized && "TCP socket opened before netstack initialization");
    ++g_mock_wifi_server_begin_calls;
    _listening = g_mock_wifi_server_begin_succeeds;
  }
  void setNoDelay(bool) {}
  void end() { _listening = false; }
  void stop() { end(); }
  operator bool() { return _listening; }
  WiFiClient available() {
    if (!_listening || g_mock_wifi_accept_queue.empty()) return WiFiClient();
    WiFiClient next = g_mock_wifi_accept_queue.front();
    g_mock_wifi_accept_queue.pop_front();
    return next;
  }
};
