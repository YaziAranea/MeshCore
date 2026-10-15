#include "SerialWifiInterface.h"
#include <WiFi.h>
#include <errno.h>
#include <lwip/sockets.h>
#include <stdio.h>
#include <string.h>

#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR

#ifndef SMARTUI_WIFI_APPROVAL_TIMEOUT_MS
#define SMARTUI_WIFI_APPROVAL_TIMEOUT_MS 30000UL
#endif
#ifndef SMARTUI_WIFI_FRAME_TIMEOUT_MS
#define SMARTUI_WIFI_FRAME_TIMEOUT_MS 2000UL
#endif
#ifndef SMARTUI_WIFI_RX_BUDGET
#define SMARTUI_WIFI_RX_BUDGET 64
#endif
#ifndef SMARTUI_WIFI_TX_BUDGET
#define SMARTUI_WIFI_TX_BUDGET 64
#endif
#ifndef SMARTUI_WIFI_LISTENER_RETRY_MS
#define SMARTUI_WIFI_LISTENER_RETRY_MS 1000UL
#endif

#define WIFI_RX_IDLE 0
#define WIFI_RX_LEN_LOW 1
#define WIFI_RX_LEN_HIGH 2
#define WIFI_RX_PAYLOAD 3

bool SerialWifiInterface::deadlineReached(uint32_t now, uint32_t deadline) {
  return static_cast<int32_t>(now - deadline) >= 0;
}

void SerialWifiInterface::advanceSessionGeneration() const {
  ++_session_generation;
  if (_session_generation == 0) ++_session_generation;
}

void SerialWifiInterface::resetReceiveParser() {
  _rx_state = WIFI_RX_IDLE;
  _rx_frame_len = 0;
  _rx_len = 0;
  _rx_frame_started = 0;
}

void SerialWifiInterface::clearTransportBuffers() {
  _tx_queue_len = 0;
  resetReceiveParser();
}

void SerialWifiInterface::clearPendingClient(bool close_socket) {
  if (close_socket && pending_client) pending_client.stop();
  pending_client = WiFiClient();
  _pending_request_id = 0;
  _pending_deadline = 0;
  _pending_peer[0] = '\0';
}

void SerialWifiInterface::closeApprovedSession() {
  const bool had_session = _session_approved || deviceConnected;
  if (client) client.stop();
  client = WiFiClient();
  _session_approved = false;
  deviceConnected = false;
  clearTransportBuffers();
  if (had_session) advanceSessionGeneration();
}

void SerialWifiInterface::offerPendingClient(WiFiClient& candidate) {
  pending_client = candidate;
  ++_next_request_id;
  if (_next_request_id == 0) ++_next_request_id;
  _pending_request_id = _next_request_id;
  _pending_deadline = millis() + SMARTUI_WIFI_APPROVAL_TIMEOUT_MS;

  const IPAddress peer = pending_client.remoteIP();
  snprintf(_pending_peer, sizeof(_pending_peer), "%u.%u.%u.%u",
           static_cast<unsigned>(peer[0]), static_cast<unsigned>(peer[1]),
           static_cast<unsigned>(peer[2]), static_cast<unsigned>(peer[3]));
  WIFI_DEBUG_PRINTLN("Client %s waiting for local approval", _pending_peer);
}

void SerialWifiInterface::ensureServerListening() {
  if (!_isEnabled || _port == 0 || _server_running) return;
  // Selection can enable this transport before WiFi.mode() initializes lwIP.
  // Opening a socket then can assert instead of returning a retryable error.
  // Pinned core getMode() is safe before initialization; check it first.
  if ((WiFi.getMode() & WIFI_MODE_STA) == 0 || WiFi.status() != WL_CONNECTED) return;
  const uint32_t now = millis();
  if (_listener_retry_at != 0 &&
      !deadlineReached(now, _listener_retry_at)) {
    return;
  }

  // Pinned ESP32 core leaves its socket allocated when bind/listen fails.
  // Close before each bounded retry.
  server.end();
  server.begin(_port);
  _server_running = static_cast<bool>(server);
  if (_server_running) {
    server.setNoDelay(true);
    _listener_retry_at = 0;
  } else {
    _listener_retry_at = now + SMARTUI_WIFI_LISTENER_RETRY_MS;
  }
}

void SerialWifiInterface::serviceClientState() {
  if (!_isEnabled) return;

  ensureServerListening();

  const uint32_t now = millis();
  if (_pending_request_id != 0 &&
      (!pending_client.connected() ||
       deadlineReached(now, _pending_deadline))) {
    WIFI_DEBUG_PRINTLN("Pending client rejected or timed out");
    clearPendingClient(true);
  }

  if (_session_approved && !client.connected()) {
    WIFI_DEBUG_PRINTLN("Approved client disconnected");
    closeApprovedSession();
  }

  if (!_server_running) return;
  WiFiClient candidate = server.available();
  if (!candidate) return;

  if (_session_approved || _pending_request_id != 0) {
    // Never let a new TCP connection evict an approved or pending peer.
    candidate.stop();
    return;
  }
  offerPendingClient(candidate);
}

void SerialWifiInterface::pumpTx() {
  serviceClientState();
  if (!_session_approved || !deviceConnected || !client.connected() ||
      _tx_queue_len == 0) {
    return;
  }

  TxFrame& frame = _tx_queue[0];
  const uint16_t remaining = frame.len - frame.offset;
  const size_t chunk = remaining < SMARTUI_WIFI_TX_BUDGET
                           ? remaining
                           : SMARTUI_WIFI_TX_BUDGET;
  const int socket_fd = client.fd();
  if (socket_fd < 0) return;
  const int sent = send(socket_fd, &frame.buf[frame.offset], chunk,
                        MSG_DONTWAIT);
  size_t written = sent > 0 ? static_cast<size_t>(sent) : 0;
  if (written > chunk) written = chunk;
  if (sent < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
    closeApprovedSession();
    return;
  }
  if (written > 0) _last_write = millis();
  frame.offset += static_cast<uint16_t>(written);
  if (frame.offset < frame.len) return;

  --_tx_queue_len;
  for (uint8_t i = 0; i < _tx_queue_len; ++i) {
    _tx_queue[i] = _tx_queue[i + 1];
  }
}

void SerialWifiInterface::begin(int port) {
  _port = port > 0 ? static_cast<uint16_t>(port) : 0;
  _listener_retry_at = 0;
  if (_isEnabled) {
    closeApprovedSession();
    clearPendingClient(true);
    server.end();
    _server_running = false;
    ensureServerListening();
  }
}

void SerialWifiInterface::enable() {
  if (_isEnabled) return;
  _isEnabled = true;
  clearTransportBuffers();
  clearPendingClient(true);
  closeApprovedSession();
  _listener_retry_at = 0;
  ensureServerListening();
}

void SerialWifiInterface::disable() {
  if (!_isEnabled && !_server_running && !_session_approved &&
      _pending_request_id == 0) {
    return;
  }
  _isEnabled = false;
  clearPendingClient(true);
  closeApprovedSession();
  server.end();
  _server_running = false;
  _listener_retry_at = 0;
}

bool SerialWifiInterface::hasPendingClientApproval() const {
  SerialWifiInterface* self = const_cast<SerialWifiInterface*>(this);
  self->serviceClientState();
  return _pending_request_id != 0;
}

uint32_t SerialWifiInterface::getPendingClientRequestId() const {
  SerialWifiInterface* self = const_cast<SerialWifiInterface*>(this);
  self->serviceClientState();
  return _pending_request_id;
}

uint32_t SerialWifiInterface::getPendingClientDeadline() const {
  SerialWifiInterface* self = const_cast<SerialWifiInterface*>(this);
  self->serviceClientState();
  return _pending_deadline;
}

bool SerialWifiInterface::copyPendingClientPeer(char* out, size_t out_len) const {
  if (!out || out_len == 0) return false;
  SerialWifiInterface* self = const_cast<SerialWifiInterface*>(this);
  self->serviceClientState();
  if (_pending_request_id == 0) {
    out[0] = '\0';
    return false;
  }
  strncpy(out, _pending_peer, out_len - 1);
  out[out_len - 1] = '\0';
  return true;
}

bool SerialWifiInterface::resolvePendingClient(uint32_t request_id,
                                               bool approve) {
  serviceClientState();
  if (request_id == 0 || request_id != _pending_request_id ||
      !pending_client.connected()) {
    return false;
  }

  if (!approve) {
    clearPendingClient(true);
    return true;
  }

  client = pending_client;
  clearPendingClient(false);
  clearTransportBuffers();
  _session_approved = true;
  deviceConnected = true;
  advanceSessionGeneration();
  WIFI_DEBUG_PRINTLN("Client approved");
  return true;
}

bool SerialWifiInterface::isSessionApproved() const {
  SerialWifiInterface* self = const_cast<SerialWifiInterface*>(this);
  self->serviceClientState();
  return _isEnabled && _session_approved && deviceConnected &&
         self->client.connected();
}

bool SerialWifiInterface::isConnected() const {
  return isSessionApproved();
}

uint32_t SerialWifiInterface::sessionGeneration() const {
  SerialWifiInterface* self = const_cast<SerialWifiInterface*>(this);
  self->serviceClientState();
  return _session_generation;
}

void SerialWifiInterface::loop() {
  serviceClientState();
  pumpTx();
}

bool SerialWifiInterface::isReadBusy() const {
  SerialWifiInterface* self = const_cast<SerialWifiInterface*>(this);
  self->serviceClientState();
  return _rx_state != WIFI_RX_IDLE ||
         (_session_approved && self->client.connected() &&
          self->client.available() > 0);
}

bool SerialWifiInterface::isWriteBusy() const {
  return _tx_queue_len >= (WIFI_TX_QUEUE_CAPACITY * 2 / 3);
}

size_t SerialWifiInterface::writeFrame(const uint8_t src[], size_t len) {
  serviceClientState();
  if (!src || len == 0 || len > MAX_FRAME_SIZE || !_session_approved ||
      !deviceConnected || !client.connected() ||
      _tx_queue_len >= WIFI_TX_QUEUE_CAPACITY) {
    return 0;
  }

  TxFrame& frame = _tx_queue[_tx_queue_len++];
  frame.len = static_cast<uint16_t>(len + 3);
  frame.offset = 0;
  frame.buf[0] = '>';
  frame.buf[1] = static_cast<uint8_t>(len & 0xFF);
  frame.buf[2] = static_cast<uint8_t>((len >> 8) & 0xFF);
  memcpy(&frame.buf[3], src, len);
  pumpTx();
  return len;
}

size_t SerialWifiInterface::checkRecvFrame(uint8_t dest[]) {
  serviceClientState();
  pumpTx();
  if (!dest || !_session_approved || !deviceConnected ||
      !client.connected()) {
    return 0;
  }

  const uint32_t now = millis();
  if (_rx_state != WIFI_RX_IDLE &&
      static_cast<uint32_t>(now - _rx_frame_started) >=
          static_cast<uint32_t>(SMARTUI_WIFI_FRAME_TIMEOUT_MS)) {
    resetReceiveParser();
  }

  unsigned budget = SMARTUI_WIFI_RX_BUDGET;
  while (budget-- > 0 && client.available() > 0) {
    const int value = client.read();
    if (value < 0) break;
    const uint8_t byte = static_cast<uint8_t>(value);

    switch (_rx_state) {
      case WIFI_RX_IDLE:
        if (byte == '<') {
          _rx_state = WIFI_RX_LEN_LOW;
          _rx_frame_started = now;
        }
        break;
      case WIFI_RX_LEN_LOW:
        _rx_frame_len = byte;
        _rx_state = WIFI_RX_LEN_HIGH;
        break;
      case WIFI_RX_LEN_HIGH:
        _rx_frame_len |= static_cast<uint16_t>(byte) << 8;
        _rx_len = 0;
        if (_rx_frame_len == 0) resetReceiveParser();
        else _rx_state = WIFI_RX_PAYLOAD;
        break;
      default:
        if (_rx_len < MAX_FRAME_SIZE) _rx_buf[_rx_len] = byte;
        ++_rx_len;
        if (_rx_len >= _rx_frame_len) {
          const uint16_t completed_len = _rx_frame_len;
          resetReceiveParser();
          if (completed_len > MAX_FRAME_SIZE) return 0;
          memcpy(dest, _rx_buf, completed_len);
          return completed_len;
        }
        break;
    }
  }
  return 0;
}

#else

void SerialWifiInterface::begin(int port) {
  // wifi setup is handled outside of this class, only starts the server
  server.begin(port);
}

void SerialWifiInterface::enable() {
  if (_isEnabled) return;

  _isEnabled = true;
  clearBuffers();
}

void SerialWifiInterface::disable() {
  _isEnabled = false;
}

size_t SerialWifiInterface::writeFrame(const uint8_t src[], size_t len) {
  if (len > MAX_FRAME_SIZE) {
    WIFI_DEBUG_PRINTLN("writeFrame(), frame too big, len=%d\n", len);
    return 0;
  }

  if (deviceConnected && len > 0) {
    if (send_queue_len >= FRAME_QUEUE_SIZE) {
      WIFI_DEBUG_PRINTLN("writeFrame(), send_queue is full!");
      return 0;
    }

    send_queue[send_queue_len].len = len;
    memcpy(send_queue[send_queue_len].buf, src, len);
    send_queue_len++;

    return len;
  }
  return 0;
}

bool SerialWifiInterface::isReadBusy() const {
  return false;
}

bool SerialWifiInterface::isWriteBusy() const {
  return false;
}

uint32_t SerialWifiInterface::sessionGeneration() const {
  return 0;
}

void SerialWifiInterface::loop() {}

bool SerialWifiInterface::hasReceivedFrameHeader() {
  return received_frame_header.type != 0 && received_frame_header.length != 0;
}

void SerialWifiInterface::resetReceivedFrameHeader() {
  received_frame_header.type = 0;
  received_frame_header.length = 0;
}

size_t SerialWifiInterface::checkRecvFrame(uint8_t dest[]) {
  auto newClient = server.available();
  if (newClient) {
    deviceConnected = false;
    client.stop();
    client = newClient;
    resetReceivedFrameHeader();
  }

  if (client.connected()) {
    if (!deviceConnected) {
      WIFI_DEBUG_PRINTLN("Got connection");
      deviceConnected = true;
    }
  } else if (deviceConnected) {
    deviceConnected = false;
    WIFI_DEBUG_PRINTLN("Disconnected");
  }

  if (deviceConnected) {
    if (send_queue_len > 0) {
      _last_write = millis();
      int len = send_queue[0].len;

      uint8_t pkt[3 + len];
      pkt[0] = '>';
      pkt[1] = (len & 0xFF);
      pkt[2] = (len >> 8);
      memcpy(&pkt[3], send_queue[0].buf, send_queue[0].len);
      client.write(pkt, 3 + len);
      send_queue_len--;
      for (int i = 0; i < send_queue_len; i++) {
        send_queue[i] = send_queue[i + 1];
      }
    } else {
      if (!hasReceivedFrameHeader()) {
        int frame_header_length = 3;
        if (client.available() >= frame_header_length) {
          client.readBytes(&received_frame_header.type, 1);
          client.readBytes((uint8_t*)&received_frame_header.length, 2);
        }
      }

      if (hasReceivedFrameHeader()) {
        int available = client.available();
        int frame_type = received_frame_header.type;
        int frame_length = received_frame_header.length;
        if (frame_length > available) {
          WIFI_DEBUG_PRINTLN("Waiting for %d more bytes", frame_length - available);
          return 0;
        }

        if (frame_length > MAX_FRAME_SIZE) {
          WIFI_DEBUG_PRINTLN("Skipping frame: length=%d is larger than MAX_FRAME_SIZE=%d", frame_length, MAX_FRAME_SIZE);
          while (frame_length > 0) {
            uint8_t skip[1];
            int skipped = client.read(skip, 1);
            frame_length -= skipped;
          }
          resetReceivedFrameHeader();
          return 0;
        }

        if (frame_type != '<') {
          WIFI_DEBUG_PRINTLN("Skipping frame: type=0x%x is unexpected", frame_type);
          while (frame_length > 0) {
            uint8_t skip[1];
            int skipped = client.read(skip, 1);
            frame_length -= skipped;
          }
          resetReceivedFrameHeader();
          return 0;
        }

        client.readBytes(dest, frame_length);
        resetReceivedFrameHeader();
        return frame_length;
      }
    }
  }

  return 0;
}

bool SerialWifiInterface::isConnected() const {
  return deviceConnected;
}

#endif
