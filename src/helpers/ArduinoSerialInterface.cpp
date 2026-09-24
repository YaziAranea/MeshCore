#include "ArduinoSerialInterface.h"

#define RECV_STATE_IDLE        0
#define RECV_STATE_HDR_FOUND   1
#define RECV_STATE_LEN1_FOUND  2
#define RECV_STATE_LEN2_FOUND  3

#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
#ifndef SMARTUI_SERIAL_RX_BUDGET
#define SMARTUI_SERIAL_RX_BUDGET 64
#endif
#ifndef SMARTUI_SERIAL_TX_BUDGET
#define SMARTUI_SERIAL_TX_BUDGET 32
#endif
#ifndef SMARTUI_SERIAL_FRAME_TIMEOUT_MS
#define SMARTUI_SERIAL_FRAME_TIMEOUT_MS 2000UL
#endif
#ifndef SMARTUI_SERIAL_SESSION_LEASE_MS
#define SMARTUI_SERIAL_SESSION_LEASE_MS 300000UL
#endif

void ArduinoSerialInterface::advanceSessionGeneration() const {
  ++_session_generation;
  if (_session_generation == 0) ++_session_generation;
}

void ArduinoSerialInterface::resetReceiveParser() {
  _state = RECV_STATE_IDLE;
  _frame_len = 0;
  rx_len = 0;
  _rx_frame_started = 0;
}

void ArduinoSerialInterface::clearTransportBuffers() {
  _tx_queue_len = 0;
  resetReceiveParser();
}

void ArduinoSerialInterface::clearSession() {
  const bool had_session = _session_established;
  _session_established = false;
  _last_session_activity = 0;
  clearTransportBuffers();
  if (had_session) advanceSessionGeneration();
}

void ArduinoSerialInterface::serviceSessionState() {
  if (!_isEnabled) {
    if (_session_established) clearSession();
    return;
  }
  if (_link_state_probe && !_link_state_probe(_link_state_context)) {
    clearSession();
  }
}

bool ArduinoSerialInterface::sessionLeaseFresh() const {
  if (!_session_established) return false;
  if (_link_state_probe) return _link_state_probe(_link_state_context);
  if (SMARTUI_SERIAL_SESSION_LEASE_MS == 0) return true;
  return static_cast<uint32_t>(millis() - _last_session_activity) <
         static_cast<uint32_t>(SMARTUI_SERIAL_SESSION_LEASE_MS);
}

bool ArduinoSerialInterface::sessionActive() const {
  return _isEnabled && _serial && sessionLeaseFresh();
}

void ArduinoSerialInterface::noteAcceptedFrame(const uint8_t* frame, size_t len) {
  if (!frame || len == 0) return;
  const bool handshake = (frame[0] == 1 && len >= 8) ||
                         (frame[0] == 22 && len >= 2);
  const bool expired_fallback_session =
      _session_established && !_link_state_probe && !sessionLeaseFresh();
  if (!_session_established && handshake) {
    _session_established = true;
    advanceSessionGeneration();
  } else if (expired_fallback_session && handshake) {
    // A new handshake after a quiet UART lease is a new app session.  Drop
    // stale replies, but keep ordinary post-lease commands compatible with
    // apps which leave UART open and do not repeat negotiation.
    _tx_queue_len = 0;
    advanceSessionGeneration();
  }
  if (_session_established) _last_session_activity = millis();
}

void ArduinoSerialInterface::pumpTx() {
  serviceSessionState();
  if (!sessionActive() || _tx_queue_len == 0) return;

  TxFrame& frame = _tx_queue[0];
  const uint16_t remaining = frame.len - frame.offset;
  const int available = _serial->availableForWrite();
  if (available <= 0) return;
  size_t chunk = remaining < SMARTUI_SERIAL_TX_BUDGET
                     ? remaining
                     : SMARTUI_SERIAL_TX_BUDGET;
  if (chunk > static_cast<size_t>(available)) chunk = available;
  size_t written = _serial->write(&frame.buf[frame.offset], chunk);
  if (written > chunk) written = chunk;
  frame.offset += static_cast<uint16_t>(written);
  if (frame.offset < frame.len) return;

  --_tx_queue_len;
  for (uint8_t i = 0; i < _tx_queue_len; ++i) {
    _tx_queue[i] = _tx_queue[i + 1];
  }
}
#endif

void ArduinoSerialInterface::enable() { 
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  clearSession();
#endif
  _isEnabled = true;
  _state = RECV_STATE_IDLE;
  _frame_len = 0;
  rx_len = 0;
}
void ArduinoSerialInterface::disable() {
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  clearSession();
#endif
  _isEnabled = false;
}

bool ArduinoSerialInterface::isConnected() const { 
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  ArduinoSerialInterface* self = const_cast<ArduinoSerialInterface*>(this);
  self->serviceSessionState();
  return self->sessionActive();
#else
  return true;   // no way of knowing, so assume yes
#endif
}

uint32_t ArduinoSerialInterface::sessionGeneration() const {
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  ArduinoSerialInterface* self = const_cast<ArduinoSerialInterface*>(this);
  self->serviceSessionState();
  return _session_generation;
#else
  return 0;
#endif
}

void ArduinoSerialInterface::loop() {
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  pumpTx();
#endif
}

bool ArduinoSerialInterface::isReadBusy() const {
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  return _state != RECV_STATE_IDLE;
#else
  return false;
#endif
}

bool ArduinoSerialInterface::isWriteBusy() const {
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  return _tx_queue_len >= (TX_QUEUE_SIZE * 2 / 3);
#else
  return false;
#endif
}

size_t ArduinoSerialInterface::writeFrame(const uint8_t src[], size_t len) {
  if (len > MAX_FRAME_SIZE) {
    // frame is too big!
    return 0;
  }

#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  serviceSessionState();
  if (!sessionActive() || len == 0 ||
      _tx_queue_len >= TX_QUEUE_SIZE) {
    return 0;
  }

  TxFrame& frame = _tx_queue[_tx_queue_len++];
  frame.len = static_cast<uint16_t>(len + 3);
  frame.offset = 0;
  frame.buf[0] = '>';
  frame.buf[1] = len & 0xFF;
  frame.buf[2] = (len >> 8) & 0xFF;
  memcpy(&frame.buf[3], src, len);
  pumpTx();
  return len;
#else

  uint8_t hdr[3];
  hdr[0] = '>';
  hdr[1] = (len & 0xFF);  // LSB
  hdr[2] = (len >> 8);    // MSB

  _serial->write(hdr, 3);
  return _serial->write(src, len);
#endif
}

size_t ArduinoSerialInterface::checkRecvFrame(uint8_t dest[]) {
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  serviceSessionState();
  if (!_isEnabled || !_serial || !dest) return 0;
  if (_link_state_probe && !_link_state_probe(_link_state_context)) return 0;
  pumpTx();

  const uint32_t now = millis();
  if (_state != RECV_STATE_IDLE &&
      static_cast<uint32_t>(now - _rx_frame_started) >=
          static_cast<uint32_t>(SMARTUI_SERIAL_FRAME_TIMEOUT_MS)) {
    resetReceiveParser();
  }

  unsigned budget = SMARTUI_SERIAL_RX_BUDGET;
  while (budget-- > 0 && _serial->available()) {
    int c = _serial->read();
    if (c < 0) break;

    switch (_state) {
      case RECV_STATE_IDLE:
        if (c == '<') {
          _state = RECV_STATE_HDR_FOUND;
          _rx_frame_started = now;
        }
        break;
      case RECV_STATE_HDR_FOUND:
        _frame_len = static_cast<uint8_t>(c);
        _state = RECV_STATE_LEN1_FOUND;
        break;
      case RECV_STATE_LEN1_FOUND:
        _frame_len |= static_cast<uint16_t>(c) << 8;
        rx_len = 0;
        if (_frame_len > 0) _state = RECV_STATE_LEN2_FOUND;
        else resetReceiveParser();
        break;
      default:
        if (rx_len < MAX_FRAME_SIZE) rx_buf[rx_len] = static_cast<uint8_t>(c);
        ++rx_len;
        if (rx_len >= _frame_len) {
          const uint16_t completed_len = _frame_len;
          resetReceiveParser();
          if (completed_len > MAX_FRAME_SIZE) return 0;

          const bool handshake =
              (rx_buf[0] == 1 && completed_len >= 8) ||
              (rx_buf[0] == 22 && completed_len >= 2);
          if (!_session_established && !handshake) return 0;
          memcpy(dest, rx_buf, completed_len);
          noteAcceptedFrame(dest, completed_len);
          return completed_len;
        }
    }
  }
  return 0;
#else
  while (_serial->available()) {
    int c = _serial->read();
    if (c < 0) break;

    switch (_state) {
      case RECV_STATE_IDLE:
        if (c == '<') {
          _state = RECV_STATE_HDR_FOUND;
        }
        break;
      case RECV_STATE_HDR_FOUND:
        _frame_len = (uint8_t)c;   // LSB
        _state = RECV_STATE_LEN1_FOUND;
        break;
      case RECV_STATE_LEN1_FOUND:
        _frame_len |= ((uint16_t)c) << 8;   // MSB
        rx_len = 0;
        _state = _frame_len > 0 ? RECV_STATE_LEN2_FOUND : RECV_STATE_IDLE;
        break;
      default:
        if (rx_len < MAX_FRAME_SIZE) {
          rx_buf[rx_len] = (uint8_t)c;   // rest of frame will be discarded if > MAX
        }
        rx_len++;
        if (rx_len >= _frame_len) {  // received a complete frame?
          const uint16_t completed_len = _frame_len;
          _state = RECV_STATE_IDLE;  // reset state, for next frame
          _frame_len = 0;
          rx_len = 0;
          // Never turn an oversized wire frame into a valid command by
          // dispatching its truncated prefix (which could itself be a reboot
          // or factory-reset command). The payload has already been drained.
          if (completed_len > MAX_FRAME_SIZE) return 0;
          memcpy(dest, rx_buf, completed_len);
          return completed_len;
        }
    }
  }
  return 0;
#endif
}
