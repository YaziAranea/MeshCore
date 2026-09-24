#include <cassert>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <deque>
#include <iostream>
#include <memory>
#include <unordered_map>
#include <vector>

#include "helpers/ArduinoSerialInterface.h"
#include "helpers/MultiSerialInterface.h"
#include "helpers/esp32/SerialWifiInterface.h"

std::unordered_map<int, std::weak_ptr<MockWiFiClientState>>
    g_mock_wifi_clients;
bool g_mock_wifi_server_begin_succeeds = true;
unsigned g_mock_wifi_server_begin_calls = 0;
std::deque<WiFiClient> g_mock_wifi_accept_queue;
static bool g_mock_send_would_block = false;
static int g_mock_send_limit = 0x7fffffff;

int mock_socket_send(int fd, const void* data, size_t len, int) {
  if (g_mock_send_would_block) {
    errno = EAGAIN;
    return -1;
  }
  const auto found = g_mock_wifi_clients.find(fd);
  if (found == g_mock_wifi_clients.end()) {
    errno = EBADF;
    return -1;
  }
  const auto state = found->second.lock();
  if (!state || !state->connected) {
    errno = ENOTCONN;
    return -1;
  }
  const size_t count = std::min(len, static_cast<size_t>(g_mock_send_limit));
  const uint8_t* bytes = static_cast<const uint8_t*>(data);
  state->tx.insert(state->tx.end(), bytes, bytes + count);
  return static_cast<int>(count);
}

namespace {

std::vector<uint8_t> framed(const std::vector<uint8_t>& payload) {
  std::vector<uint8_t> result = {
      '<', static_cast<uint8_t>(payload.size() & 0xff),
      static_cast<uint8_t>((payload.size() >> 8) & 0xff)};
  result.insert(result.end(), payload.begin(), payload.end());
  return result;
}

class FakeStream : public Stream {
public:
  std::deque<uint8_t> input;
  std::vector<uint8_t> output;
  int write_capacity = 64;
  size_t write_limit = 64;

  void append(const std::vector<uint8_t>& bytes) {
    input.insert(input.end(), bytes.begin(), bytes.end());
  }
  int available() override { return static_cast<int>(input.size()); }
  int availableForWrite() override { return write_capacity; }
  int read() override {
    if (input.empty()) return -1;
    const uint8_t value = input.front();
    input.pop_front();
    return value;
  }
  size_t write(const uint8_t* bytes, size_t len) override {
    const size_t count = std::min(len, write_limit);
    output.insert(output.end(), bytes, bytes + count);
    return count;
  }
};

class FakeTransport : public BaseSerialInterface {
public:
  bool enabled = false;
  bool connected = false;
  uint32_t generation = 0;
  unsigned writes = 0;

  void enable() override { enabled = true; }
  void disable() override { enabled = false; connected = false; }
  bool isEnabled() const override { return enabled; }
  bool isConnected() const override { return connected; }
  uint32_t sessionGeneration() const override { return generation; }
  bool isReadBusy() const override { return false; }
  bool isWriteBusy() const override { return false; }
  size_t writeFrame(const uint8_t*, size_t len) override {
    ++writes;
    return connected ? len : 0;
  }
  size_t checkRecvFrame(uint8_t*) override { return 0; }
};

std::shared_ptr<MockWiFiClientState> wifiPeer(
    int fd, IPAddress ip, const std::vector<uint8_t>& input = {}) {
  auto state = std::make_shared<MockWiFiClientState>();
  state->fd = fd;
  state->remote_ip = ip;
  state->rx.insert(state->rx.end(), input.begin(), input.end());
  return state;
}

void testExclusiveManagerEpochs() {
  FakeTransport ble;
  FakeTransport usb;
  ble.connected = true;
  usb.connected = true;
  MultiSerialInterface manager;
  assert(manager.addInterface(InterfaceType::Bluetooth, &ble));
  assert(manager.addInterface(InterfaceType::USB, &usb));
  manager.enable();
  assert(ble.enabled && !usb.enabled);

  const uint8_t payload[] = {7};
  assert(manager.writeFrame(payload, sizeof(payload)) == sizeof(payload));
  assert(ble.writes == 1 && usb.writes == 0);

  const uint32_t before_switch = manager.sessionGeneration();
  assert(manager.selectExclusive(InterfaceType::USB));
  assert(!ble.enabled && usb.enabled);
  assert(manager.sessionGeneration() != before_switch);

  const uint32_t before_epoch = manager.sessionGeneration();
  usb.generation += 2;  // disconnect+reconnect between manager polls
  usb.connected = true;
  assert(manager.sessionGeneration() != before_epoch);

  const uint32_t before_soft_state = manager.sessionGeneration();
  usb.connected = false;
  assert(!manager.isConnected());
  assert(manager.sessionGeneration() == before_soft_state);
}

void testUsbLeaseAndBackpressure() {
  g_mock_millis = 0;
  FakeStream stream;
  stream.write_limit = 2;
  ArduinoSerialInterface usb;
  usb.begin(stream);
  MultiSerialInterface manager;
  assert(manager.addInterface(InterfaceType::USB, &usb));
  manager.enable();
  assert(!manager.isConnected());

  uint8_t out[MAX_FRAME_SIZE] = {};
  stream.append(framed({9}));
  assert(manager.checkRecvFrame(out) == 0);  // no pre-handshake commands
  const uint32_t initial_generation = manager.sessionGeneration();

  stream.append(framed({22, 3}));
  assert(manager.checkRecvFrame(out) == 2);
  assert(out[0] == 22 && out[1] == 3);
  const uint32_t established_generation = manager.sessionGeneration();
  assert(established_generation != initial_generation);
  assert(manager.isConnected());

  stream.append(framed({1, 0, 0, 0, 0, 0, 0, 0}));
  assert(manager.checkRecvFrame(out) == 8);
  assert(manager.sessionGeneration() == established_generation);

  const uint8_t reply[] = {42, 43, 44, 45};
  assert(manager.writeFrame(reply, sizeof(reply)) == sizeof(reply));
  for (int i = 0; i < 8; ++i) manager.loop();
  const std::vector<uint8_t> expected = {'>', 4, 0, 42, 43, 44, 45};
  assert(stream.output == expected);

  g_mock_millis = SMARTUI_SERIAL_SESSION_LEASE_MS;
  assert(!manager.isConnected());
  assert(manager.sessionGeneration() == established_generation);

  stream.append(framed({7}));
  assert(manager.checkRecvFrame(out) == 1);
  assert(out[0] == 7);
  assert(manager.isConnected());
  assert(manager.sessionGeneration() == established_generation);

  g_mock_millis += SMARTUI_SERIAL_SESSION_LEASE_MS;
  stream.append(framed({22, 4}));
  assert(manager.checkRecvFrame(out) == 2);
  const uint32_t renewed_generation = manager.sessionGeneration();
  assert(renewed_generation != established_generation);
  stream.append(framed({1, 0, 0, 0, 0, 0, 0, 0}));
  assert(manager.checkRecvFrame(out) == 8);
  assert(manager.sessionGeneration() == renewed_generation);

  // Unsigned subtraction remains valid across millis() wrap.
  g_mock_millis = UINT32_MAX - 50;
  stream.append(framed({7}));
  assert(manager.checkRecvFrame(out) == 1);
  g_mock_millis = 25;
  assert(manager.isConnected());
}

bool linkProbe(void* context) {
  return *static_cast<bool*>(context);
}

void testUsbHardDisconnectAndParserTimeout() {
  g_mock_millis = 10;
  bool link_up = true;
  FakeStream stream;
  ArduinoSerialInterface usb;
  usb.begin(stream, linkProbe, &link_up);
  usb.enable();
  uint8_t out[MAX_FRAME_SIZE] = {};
  stream.append(framed({22, 1}));
  assert(usb.checkRecvFrame(out) == 2);
  const uint32_t connected_generation = usb.sessionGeneration();
  link_up = false;
  assert(!usb.isConnected());
  assert(usb.sessionGeneration() != connected_generation);
  assert(!usb.hasEstablishedSession());

  link_up = true;
  stream.append({'<', 2});
  assert(usb.checkRecvFrame(out) == 0);
  g_mock_millis += SMARTUI_SERIAL_FRAME_TIMEOUT_MS;
  stream.append(framed({22, 2}));
  assert(usb.checkRecvFrame(out) == 2);  // stale partial discarded first
}

void testWifiApprovalIsolationAndNonblockingTx() {
  g_mock_millis = 0;
  g_mock_wifi_server_begin_calls = 0;
  g_mock_wifi_server_begin_succeeds = false;
  SerialWifiInterface wifi;
  wifi.begin(5000);
  wifi.enable();
  assert(g_mock_wifi_server_begin_calls == 1);
  wifi.loop();
  assert(g_mock_wifi_server_begin_calls == 1);
  g_mock_millis = SMARTUI_WIFI_LISTENER_RETRY_MS;
  g_mock_wifi_server_begin_succeeds = true;
  wifi.loop();
  assert(g_mock_wifi_server_begin_calls == 2);

  const auto first = wifiPeer(11, IPAddress(192, 168, 4, 2), framed({22, 5}));
  const auto rejected = wifiPeer(12, IPAddress(192, 168, 4, 3));
  g_mock_wifi_accept_queue.emplace_back(first);
  wifi.loop();
  assert(wifi.hasPendingClientApproval());
  assert(!wifi.isConnected());
  const uint32_t request = wifi.getPendingClientRequestId();
  char peer[16] = {};
  assert(wifi.copyPendingClientPeer(peer, sizeof(peer)));
  assert(std::strcmp(peer, "192.168.4.2") == 0);

  g_mock_wifi_accept_queue.emplace_back(rejected);
  wifi.loop();
  assert(!rejected->connected);
  assert(wifi.getPendingClientRequestId() == request);
  assert(!wifi.resolvePendingClient(request + 1, true));

  const uint32_t before_approval = wifi.sessionGeneration();
  assert(wifi.resolvePendingClient(request, true));
  assert(wifi.isConnected());
  assert(wifi.sessionGeneration() != before_approval);
  uint8_t out[MAX_FRAME_SIZE] = {};
  assert(wifi.checkRecvFrame(out) == 2);  // queued app handshake survives approval
  assert(out[0] == 22 && out[1] == 5);

  g_mock_send_would_block = true;
  const uint8_t response[] = {8, 9, 10, 11};
  assert(wifi.writeFrame(response, sizeof(response)) == sizeof(response));
  for (int i = 0; i < 4; ++i) wifi.loop();
  assert(first->tx.empty());

  g_mock_send_would_block = false;
  g_mock_send_limit = 2;
  for (int i = 0; i < 8; ++i) wifi.loop();
  const std::vector<uint8_t> expected = {'>', 4, 0, 8, 9, 10, 11};
  assert(first->tx == expected);

  const auto takeover = wifiPeer(13, IPAddress(192, 168, 4, 4));
  g_mock_wifi_accept_queue.emplace_back(takeover);
  wifi.loop();
  assert(!takeover->connected);
  assert(wifi.isConnected());

  const uint32_t active_generation = wifi.sessionGeneration();
  first->connected = false;
  wifi.loop();
  assert(!wifi.isConnected());
  assert(wifi.sessionGeneration() != active_generation);

  const auto timeout = wifiPeer(14, IPAddress(10, 0, 0, 7));
  g_mock_wifi_accept_queue.emplace_back(timeout);
  wifi.loop();
  const uint32_t timeout_request = wifi.getPendingClientRequestId();
  assert(timeout_request != 0);
  g_mock_millis = wifi.getPendingClientDeadline();
  wifi.loop();
  assert(!wifi.hasPendingClientApproval());
  assert(!timeout->connected);
  assert(!wifi.resolvePendingClient(timeout_request, true));
  wifi.disable();
}

}  // namespace

int main() {
  testExclusiveManagerEpochs();
  testUsbLeaseAndBackpressure();
  testUsbHardDisconnectAndParserTimeout();
  testWifiApprovalIsolationAndNonblockingTx();
  std::cout << "PASS transport selector: exclusive routing, USB epochs/lease/backpressure, WiFi approval/timeout/nonblocking TX\n";
  return 0;
}
