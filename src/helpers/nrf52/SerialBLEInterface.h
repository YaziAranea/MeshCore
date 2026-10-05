#pragma once

#include "../BaseSerialInterface.h"
#include <bluefruit.h>
#include "BoundedFrameQueue.h"

#ifndef BLE_TX_POWER
#define BLE_TX_POWER 4
#endif

class SerialBLEInterface : public BaseSerialInterface {
  BLEDfu bledfu;
  BLEUart bleuart;
  bool _isEnabled;
  bool _isDeviceConnected;
  uint16_t _conn_handle;
  unsigned long _last_health_check;
  unsigned long _last_retry_attempt;
  uint32_t _buffer_generation;
  bool _rx_active;
  bool _rx_overlap;
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  mutable uint32_t _session_generation;
#endif

  struct Frame {
    uint8_t len;
    uint8_t buf[MAX_FRAME_SIZE];
  };

  #define FRAME_QUEUE_SIZE  12
  
  BoundedFrameQueue<Frame, FRAME_QUEUE_SIZE> send_queue;
  BoundedFrameQueue<Frame, FRAME_QUEUE_SIZE> recv_queue;

  // These helpers require the transport's task critical section.
  void clearBuffersLocked();
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  void advanceSessionGenerationLocked() const;
#endif
  bool isValidConnection(uint16_t handle, bool requireWaitingForSecurity = false) const;
  bool isAdvertising() const;
  static void onConnect(uint16_t connection_handle);
  static void onDisconnect(uint16_t connection_handle, uint8_t reason);
  static void onSecured(uint16_t connection_handle);
  static bool onPairingPasskey(uint16_t connection_handle, uint8_t const passkey[6], bool match_request);
  static void onPairingComplete(uint16_t connection_handle, uint8_t auth_status);
  static void onBLEEvent(ble_evt_t* evt);
  static void onBleUartRX(uint16_t conn_handle);

public:
  SerialBLEInterface() {
    _isEnabled = false;
    _isDeviceConnected = false;
    _conn_handle = BLE_CONN_HANDLE_INVALID;
    _last_health_check = 0;
    _last_retry_attempt = 0;
    _buffer_generation = 0;
    _rx_active = false;
    _rx_overlap = false;
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
    _session_generation = 0;
#endif
  }

  /**
   * init the BLE interface.
   * @param prefix   a prefix for the device name
   * @param name  IN/OUT - a name for the device (combined with prefix). If "@@MAC", is modified and returned
   * @param pin_code   the BLE security pin
   */
  void begin(const char* prefix, char* name, uint32_t pin_code);

  void disconnect();
  void enable() override;
  void disable() override;
  bool isEnabled() const override;
  bool isConnected() const override;
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  uint32_t sessionGeneration() const override;
#endif
  bool isReadBusy() const override;
  bool isWriteBusy() const override;
  bool hasPendingTx() const override;
  size_t writeFrame(const uint8_t src[], size_t len) override;
  size_t checkRecvFrame(uint8_t dest[]) override;
};

#if BLE_DEBUG_LOGGING && ARDUINO
  #include <Arduino.h>
  #define BLE_DEBUG_PRINT(F, ...) Serial.printf("BLE: " F, ##__VA_ARGS__)
  #define BLE_DEBUG_PRINTLN(F, ...) Serial.printf("BLE: " F "\n", ##__VA_ARGS__)
#else
  #define BLE_DEBUG_PRINT(...) {}
  #define BLE_DEBUG_PRINTLN(...) {}
#endif
