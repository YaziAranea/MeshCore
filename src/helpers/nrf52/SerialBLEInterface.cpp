#include "SerialBLEInterface.h"
#include <stdio.h>
#include <string.h>
#include "ble_gap.h"
#include "ble_hci.h"

// Magic numbers came from actual testing
#define BLE_HEALTH_CHECK_INTERVAL  10000  // Advertising watchdog check every 10 seconds
#define BLE_RETRY_THROTTLE_MS      250    // Throttle retries to 250ms when queue buildup detected

// Connection parameters (units: interval=1.25ms, timeout=10ms)
#define BLE_MIN_CONN_INTERVAL      12     // 15ms
#define BLE_MAX_CONN_INTERVAL      24     // 30ms
#define BLE_SLAVE_LATENCY          4
#define BLE_CONN_SUP_TIMEOUT       200    // 2000ms

// Advertising parameters
#define BLE_ADV_INTERVAL_MIN       32     // 20ms (units: 0.625ms)
#define BLE_ADV_INTERVAL_MAX       244    // 152.5ms (units: 0.625ms)
#define BLE_ADV_FAST_TIMEOUT       30     // seconds

static SerialBLEInterface* instance = nullptr;

namespace {
// The pinned nRF52 core runs deferred Bluefruit callbacks at TASK_PRIO_NORMAL
// and loop() at TASK_PRIO_LOW. Its task critical section uses BASEPRI, leaving
// SoftDevice IRQs enabled while preventing task preemption. Guard only bounded
// memory operations: even BLEUart::read/flush take a FreeRTOS mutex internally.
class TransportLock {
public:
  TransportLock() { taskENTER_CRITICAL(); }
  ~TransportLock() { taskEXIT_CRITICAL(); }
  TransportLock(const TransportLock&) = delete;
  TransportLock& operator=(const TransportLock&) = delete;
};
}

void SerialBLEInterface::onConnect(uint16_t connection_handle) {
  BLE_DEBUG_PRINTLN("SerialBLEInterface: connected handle=0x%04X", connection_handle);
  if (instance) {
    TransportLock lock;
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
    if (instance->_isDeviceConnected) instance->advanceSessionGenerationLocked();
#endif
    instance->_conn_handle = connection_handle;
    instance->_isDeviceConnected = false;
    instance->clearBuffersLocked();
  }
}

void SerialBLEInterface::onDisconnect(uint16_t connection_handle, uint8_t reason) {
  BLE_DEBUG_PRINTLN("SerialBLEInterface: disconnected handle=0x%04X reason=%u", connection_handle, reason);
  if (instance) {
    TransportLock lock;
    if (instance->_conn_handle == connection_handle) {
      const bool had_session = instance->_isDeviceConnected;
      instance->_conn_handle = BLE_CONN_HANDLE_INVALID;
      instance->_isDeviceConnected = false;
      instance->clearBuffersLocked();
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
      if (had_session) instance->advanceSessionGenerationLocked();
#else
      (void)had_session;
#endif
    }
  }
}

void SerialBLEInterface::onSecured(uint16_t connection_handle) {
  BLE_DEBUG_PRINTLN("SerialBLEInterface: onSecured handle=0x%04X", connection_handle);
  if (instance) {
    bool accepted = false;
    if (instance->isValidConnection(connection_handle, true)) {
      TransportLock lock;
      if (instance->_isEnabled && !instance->_isDeviceConnected &&
          instance->_conn_handle == connection_handle) {
        instance->clearBuffersLocked();
        instance->_isDeviceConnected = true;
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
        instance->advanceSessionGenerationLocked();
#endif
        accepted = true;
      }
    }
    if (accepted) {
      
      // Connection interval units: 1.25ms, supervision timeout units: 10ms
      // Apple: "The product will not read or use the parameters in the Peripheral Preferred Connection Parameters characteristic."
      // So we explicitly set it here to make Android & Apple match
      ble_gap_conn_params_t conn_params;
      conn_params.min_conn_interval = BLE_MIN_CONN_INTERVAL;
      conn_params.max_conn_interval = BLE_MAX_CONN_INTERVAL;
      conn_params.slave_latency = BLE_SLAVE_LATENCY;
      conn_params.conn_sup_timeout = BLE_CONN_SUP_TIMEOUT;
      
      uint32_t err_code = sd_ble_gap_conn_param_update(connection_handle, &conn_params);
      if (err_code == NRF_SUCCESS) {
        BLE_DEBUG_PRINTLN("Connection parameter update requested: %u-%ums interval, latency=%u, %ums timeout",
                         conn_params.min_conn_interval * 5 / 4,  // convert to ms (1.25ms units)
                         conn_params.max_conn_interval * 5 / 4,
                         conn_params.slave_latency,
                         conn_params.conn_sup_timeout * 10);  // convert to ms (10ms units)
      } else {
        BLE_DEBUG_PRINTLN("Failed to request connection parameter update: %lu", err_code);
      }
    } else {
      BLE_DEBUG_PRINTLN("onSecured: ignoring stale/duplicate callback");
    }
  }
}

bool SerialBLEInterface::onPairingPasskey(uint16_t connection_handle, uint8_t const passkey[6], bool match_request) {
  (void)connection_handle;
  (void)passkey;
  BLE_DEBUG_PRINTLN("SerialBLEInterface: pairing passkey request match=%d", match_request);
  return true;
}

void SerialBLEInterface::onPairingComplete(uint16_t connection_handle, uint8_t auth_status) {
  BLE_DEBUG_PRINTLN("SerialBLEInterface: pairing complete handle=0x%04X status=%u", connection_handle, auth_status);
  if (instance) {
    if (instance->isValidConnection(connection_handle)) {
      if (auth_status == BLE_GAP_SEC_STATUS_SUCCESS) {
        BLE_DEBUG_PRINTLN("SerialBLEInterface: pairing successful");
      } else {
        BLE_DEBUG_PRINTLN("SerialBLEInterface: pairing failed, disconnecting");
        instance->disconnect();
      }
    } else {
      BLE_DEBUG_PRINTLN("onPairingComplete: ignoring stale callback");
    }
  }
}

void SerialBLEInterface::onBLEEvent(ble_evt_t* evt) {
  if (!instance) return;
  
  if (evt->header.evt_id == BLE_GAP_EVT_CONN_PARAM_UPDATE_REQUEST) {
    uint16_t conn_handle = evt->evt.gap_evt.conn_handle;
    if (instance->isValidConnection(conn_handle)) {
      BLE_DEBUG_PRINTLN("CONN_PARAM_UPDATE_REQUEST: handle=0x%04X, min_interval=%u, max_interval=%u, latency=%u, timeout=%u",
                       conn_handle,
                       evt->evt.gap_evt.params.conn_param_update_request.conn_params.min_conn_interval,
                       evt->evt.gap_evt.params.conn_param_update_request.conn_params.max_conn_interval,
                       evt->evt.gap_evt.params.conn_param_update_request.conn_params.slave_latency,
                       evt->evt.gap_evt.params.conn_param_update_request.conn_params.conn_sup_timeout);
      
      uint32_t err_code = sd_ble_gap_conn_param_update(conn_handle, NULL);
      if (err_code == NRF_SUCCESS) {
        BLE_DEBUG_PRINTLN("Accepted CONN_PARAM_UPDATE_REQUEST (using PPCP)");
      } else {
        BLE_DEBUG_PRINTLN("ERROR: Failed to accept CONN_PARAM_UPDATE_REQUEST: 0x%08X", err_code);
      }
    } else {
      BLE_DEBUG_PRINTLN("CONN_PARAM_UPDATE_REQUEST: ignoring stale callback for handle=0x%04X", conn_handle);
    }
  }
}

void SerialBLEInterface::begin(const char* prefix, char* name, uint32_t pin_code) {
  instance = this;

  char charpin[20];
  snprintf(charpin, sizeof(charpin), "%lu", (unsigned long)pin_code);
  
#if defined(PROMICRO) && defined(SMARTUI_RELEASE_LABEL)
  // SmartUI owns the ProMicro builtin LED. Disable Bluefruit's independent
  // advertising timer before it is created; notification/UI policy may still
  // use PIN_LED explicitly.
  Bluefruit.autoConnLed(false);
#endif
  Bluefruit.configPrphBandwidth(BANDWIDTH_MAX);
  Bluefruit.begin();
 
  char dev_name[32+16];
  if (strcmp(name, "@@MAC") == 0) {
    ble_gap_addr_t addr;
    if (sd_ble_gap_addr_get(&addr) == NRF_SUCCESS) {
      sprintf(name, "%02X%02X%02X%02X%02X%02X",    // modify (IN-OUT param)
          addr.addr[5], addr.addr[4], addr.addr[3], addr.addr[2], addr.addr[1], addr.addr[0]);
    }
  }
  sprintf(dev_name, "%s%s", prefix, name);

  // Connection interval units: 1.25ms, supervision timeout units: 10ms
  ble_gap_conn_params_t ppcp_params;
  ppcp_params.min_conn_interval = BLE_MIN_CONN_INTERVAL;
  ppcp_params.max_conn_interval = BLE_MAX_CONN_INTERVAL;
  ppcp_params.slave_latency = BLE_SLAVE_LATENCY;
  ppcp_params.conn_sup_timeout = BLE_CONN_SUP_TIMEOUT;
  
  uint32_t err_code = sd_ble_gap_ppcp_set(&ppcp_params);
  if (err_code == NRF_SUCCESS) {
    BLE_DEBUG_PRINTLN("PPCP set: %u-%ums interval, latency=%u, %ums timeout",
                     ppcp_params.min_conn_interval * 5 / 4,  // convert to ms (1.25ms units)
                     ppcp_params.max_conn_interval * 5 / 4,
                     ppcp_params.slave_latency,
                     ppcp_params.conn_sup_timeout * 10);  // convert to ms (10ms units)
  } else {
    BLE_DEBUG_PRINTLN("Failed to set PPCP: %lu", err_code);
  }
  
  Bluefruit.setTxPower(BLE_TX_POWER);
  Bluefruit.setName(dev_name);

  Bluefruit.Security.setMITM(true);
  Bluefruit.Security.setPIN(charpin);
  Bluefruit.Security.setIOCaps(true, false, false);
  Bluefruit.Security.setPairPasskeyCallback(onPairingPasskey);
  Bluefruit.Security.setPairCompleteCallback(onPairingComplete);

  Bluefruit.Periph.setConnectCallback(onConnect);
  Bluefruit.Periph.setDisconnectCallback(onDisconnect);
  Bluefruit.Security.setSecuredCallback(onSecured);

  Bluefruit.setEventCallback(onBLEEvent);

  bleuart.setPermission(SECMODE_ENC_WITH_MITM, SECMODE_ENC_WITH_MITM);
  bleuart.begin();
  bleuart.setRxCallback(onBleUartRX);



  // Register DFU on the main BLE stack so paired clients can discover it
  // without switching the device into a separate OTA-only BLE mode first.
  bledfu.setPermission(SECMODE_ENC_WITH_MITM, SECMODE_ENC_WITH_MITM);
  bledfu.begin();

  Bluefruit.Advertising.addFlags(BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE);
  Bluefruit.Advertising.addTxPower();
  Bluefruit.Advertising.addService(bleuart);

  Bluefruit.ScanResponse.addName();

  Bluefruit.Advertising.setInterval(BLE_ADV_INTERVAL_MIN, BLE_ADV_INTERVAL_MAX);
  Bluefruit.Advertising.setFastTimeout(BLE_ADV_FAST_TIMEOUT);

  Bluefruit.Advertising.restartOnDisconnect(true);

}

void SerialBLEInterface::clearBuffersLocked() {
  send_queue.clear();
  recv_queue.clear();
  _last_retry_attempt = 0;
  ++_buffer_generation;
  if (_buffer_generation == 0) ++_buffer_generation;
  // Do not flush BLEUart here. Only the RX callback consumes its FIFO; a reset
  // invalidates any local callback/TX snapshot through this buffer generation.
}

#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
void SerialBLEInterface::advanceSessionGenerationLocked() const {
  ++_session_generation;
  if (_session_generation == 0) ++_session_generation;
}

uint32_t SerialBLEInterface::sessionGeneration() const {
  TransportLock lock;
  return _session_generation;
}
#endif

bool SerialBLEInterface::isValidConnection(uint16_t handle, bool requireWaitingForSecurity) const {
  uint32_t generation;
  {
    TransportLock lock;
    if (_conn_handle != handle || (requireWaitingForSecurity && _isDeviceConnected)) return false;
    generation = _buffer_generation;
  }
  // Query the SoftDevice without retaining a BLEConnection*, which the stack
  // may delete in its higher-priority task while a callback is running.
  ble_gap_conn_sec_t security;
  if (sd_ble_gap_conn_sec_get(handle, &security) != NRF_SUCCESS) return false;
  TransportLock lock;
  return generation == _buffer_generation && _conn_handle == handle &&
         (!requireWaitingForSecurity || !_isDeviceConnected);
}

bool SerialBLEInterface::isAdvertising() const {
  ble_gap_addr_t adv_addr;
  uint32_t err_code = sd_ble_gap_adv_addr_get(0, &adv_addr);
  return (err_code == NRF_SUCCESS);
}

void SerialBLEInterface::enable() {
  const unsigned long now = millis();
  {
    TransportLock lock;
    if (_isEnabled) return;
    _isEnabled = true;
    clearBuffersLocked();
    _last_health_check = now;
  }

  Bluefruit.Advertising.restartOnDisconnect(true);
  Bluefruit.Advertising.start(0);
}

void SerialBLEInterface::disconnect() {
  uint16_t handle;
  {
    TransportLock lock;
    handle = _conn_handle;
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
    if (_isDeviceConnected) advanceSessionGenerationLocked();
#endif
    _isDeviceConnected = false;
    clearBuffersLocked();
  }
  if (handle != BLE_CONN_HANDLE_INVALID) {
    sd_ble_gap_disconnect(handle, BLE_HCI_REMOTE_USER_TERMINATED_CONNECTION);
  }
}

void SerialBLEInterface::disable() {
  BLE_DEBUG_PRINTLN("SerialBLEInterface: disable");
  uint16_t handle;
  {
    TransportLock lock;
    _isEnabled = false;
    handle = _conn_handle;
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
    if (_isDeviceConnected) advanceSessionGenerationLocked();
#endif
    _isDeviceConnected = false;
    clearBuffersLocked();
    _last_health_check = 0;
  }
  Bluefruit.Advertising.restartOnDisconnect(false);
  Bluefruit.Advertising.stop();
  if (handle != BLE_CONN_HANDLE_INVALID) {
    sd_ble_gap_disconnect(handle, BLE_HCI_REMOTE_USER_TERMINATED_CONNECTION);
  }
}

size_t SerialBLEInterface::writeFrame(const uint8_t src[], size_t len) {
  if (len == 0 || len > MAX_FRAME_SIZE) {
    BLE_DEBUG_PRINTLN("writeFrame(), frame too big, len=%u", (unsigned)len);
    return 0;
  }

  TransportLock lock;
  if (!_isEnabled || !_isDeviceConnected) return 0;
  Frame frame = {};
  frame.len = len;
  memcpy(frame.buf, src, len);
  return send_queue.push(frame) ? len : 0;
}

size_t SerialBLEInterface::checkRecvFrame(uint8_t dest[]) {
  const unsigned long now = millis();
  Frame tx = {};
  uint16_t handle = BLE_CONN_HANDLE_INVALID;
  uint32_t generation = 0;
  bool have_tx = false;
  {
    TransportLock lock;
    if (!_isEnabled) return 0;
    if (!_isDeviceConnected) {
      send_queue.clear();
    } else if (!(_last_retry_attempt > 0 &&
                 (now - _last_retry_attempt) < BLE_RETRY_THROTTLE_MS)) {
      have_tx = send_queue.peek(tx);
      handle = _conn_handle;
      generation = _buffer_generation;
    }
  }

  if (have_tx) {
    // BLEUart::write can wait for notification credits. Never hold the memory
    // lock here; a disconnect/reset may run while this local copy is in flight.
    bool valid = isValidConnection(handle);
    {
      TransportLock lock;
      valid = valid && generation == _buffer_generation &&
              handle == _conn_handle && _isEnabled && _isDeviceConnected;
    }
    // The epoch below protects our queue, not cancellation/lifetime inside the
    // pinned framework's blocking notify(). Bytes already handed to that API
    // cannot be recalled here; the captured handle avoids its default-handle
    // routing, but does not make handle reuse inside the framework atomic.
    const size_t written = valid ? bleuart.write(handle, tx.buf, tx.len) : 0;
    const bool connected = isValidConnection(handle);
    TransportLock lock;
    if (generation == _buffer_generation && handle == _conn_handle) {
      if (written > 0 || !connected || !_isDeviceConnected || !_isEnabled) {
        // Partial writes retain the existing drop policy, not a duplicate retry.
        send_queue.discard();
        _last_retry_attempt = 0;
      } else {
        _last_retry_attempt = now;
      }
    }
  }

  bool check_advertising = false;
  {
    TransportLock lock;
    Frame rx;
    // Copy and dequeue are one operation. Callback preemption cannot overwrite
    // a copied slot or observe a half-published payload/queue index.
    if (_isEnabled && _isDeviceConnected && recv_queue.pop(rx)) {
      memcpy(dest, rx.buf, rx.len);
      return rx.len;
    }
    if (_isEnabled && _conn_handle == BLE_CONN_HANDLE_INVALID &&
        now - _last_health_check >= BLE_HEALTH_CHECK_INTERVAL) {
      _last_health_check = now;
      check_advertising = true;
    }
  }

  // Advertising watchdog: periodically check if advertising is running, restart if not
  // Only run when truly disconnected (no connection handle), not during connection establishment
  if (check_advertising && !isAdvertising()) {
    BLE_DEBUG_PRINTLN("SerialBLEInterface: advertising watchdog - advertising stopped, restarting");
    Bluefruit.Advertising.start(0);
  }
  
  return 0;
}

void SerialBLEInterface::onBleUartRX(uint16_t conn_handle) {
  if (!instance) return;
  uint32_t generation;
  bool discard;
  {
    TransportLock lock;
    // Normally all RX callbacks share the deferred callback task. The pinned
    // framework can fall back to its BLE task if callback allocation fails.
    // An overlapping callback must not become a second FIFO reader. Drop this
    // ambiguous batch, including any bytes it appended, rather than merge it.
    if (instance->_rx_active) {
      instance->_rx_overlap = true;
      return;
    }
    instance->_rx_active = true;
    generation = instance->_buffer_generation;
    discard = !instance->_isEnabled || !instance->_isDeviceConnected ||
              instance->_conn_handle != conn_handle;
  }

  for (;;) {
    const int available = instance->bleuart.available();
    if (available == 0) {
      TransportLock lock;
      // A fallback RX can arrive after available() but before this lock. Its
      // overlap flag requires another drain before releasing FIFO ownership.
      if (instance->_rx_overlap) {
        instance->_rx_overlap = false;
        discard = true;
        continue;
      }
      instance->_rx_active = false;
      return;
    }
    if (available > MAX_FRAME_SIZE) discard = true;
    Frame frame = {};
    const int requested = available > MAX_FRAME_SIZE ? MAX_FRAME_SIZE : available;
    // Bulk FIFO read never waits for additional bytes (unlike readBytes()).
    const int received = instance->bleuart.read(frame.buf, requested);
    if (received <= 0) {
      discard = true;
      continue;
    }
    frame.len = received;
    {
      TransportLock lock;
      discard = discard || instance->_rx_overlap ||
                generation != instance->_buffer_generation ||
                !instance->_isEnabled || !instance->_isDeviceConnected ||
                instance->_conn_handle != conn_handle;
      if (!discard) instance->recv_queue.push(frame);  // bounded, drop newest
    }
    // One BLE write is one frame. Further bytes can only be an overlapping
    // fallback write; preserve framing by draining them, not publishing a tail.
    discard = true;
  }
}

bool SerialBLEInterface::isEnabled() const {
  TransportLock lock;
  return _isEnabled;
}

bool SerialBLEInterface::isConnected() const {
  uint16_t handle;
  {
    TransportLock lock;
    if (!_isEnabled || !_isDeviceConnected) return false;
    handle = _conn_handle;
  }
  return isValidConnection(handle);
}

bool SerialBLEInterface::isReadBusy() const {
  TransportLock lock;
  return recv_queue.size() > 0;
}

bool SerialBLEInterface::isWriteBusy() const {
  TransportLock lock;
  return send_queue.size() >= (FRAME_QUEUE_SIZE * 2 / 3);
}

bool SerialBLEInterface::hasPendingTx() const {
  TransportLock lock;
  return send_queue.size() > 0;
}
