#pragma once

#include "BaseSerialInterface.h"
#include <Arduino.h>

class ArduinoSerialInterface : public BaseSerialInterface {
  bool _isEnabled;
  uint8_t _state;
  uint16_t _frame_len;
  uint16_t rx_len;
  Stream* _serial;
  uint8_t rx_buf[MAX_FRAME_SIZE];

#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
public:
  using LinkStateProbe = bool (*)(void* context);

private:
  struct TxFrame {
    uint16_t len;
    uint16_t offset;
    uint8_t buf[MAX_FRAME_SIZE + 3];
  };

  static const uint8_t TX_QUEUE_SIZE = 4;
  TxFrame _tx_queue[TX_QUEUE_SIZE];
  uint8_t _tx_queue_len;
  mutable bool _session_established;
  mutable uint32_t _session_generation;
  mutable uint32_t _last_session_activity;
  uint32_t _rx_frame_started;
  LinkStateProbe _link_state_probe;
  void* _link_state_context;

  void advanceSessionGeneration() const;
  void resetReceiveParser();
  void clearTransportBuffers();
  void serviceSessionState();
  bool sessionLeaseFresh() const;
  bool sessionActive() const;
  void noteAcceptedFrame(const uint8_t* frame, size_t len);
  void pumpTx();
#endif

public:
  ArduinoSerialInterface()
      : _isEnabled(false), _state(0), _frame_len(0), rx_len(0),
        _serial(nullptr)
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
        , _tx_queue_len(0), _session_established(false),
        _session_generation(0), _last_session_activity(0),
        _rx_frame_started(0), _link_state_probe(nullptr),
        _link_state_context(nullptr)
#endif
  {}

  void begin(Stream& serial) { 
    _serial = &serial; 
  #ifdef RAK_4631
    pinMode(WB_IO2, OUTPUT);
  #endif  
  }

#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  void begin(Stream& serial, LinkStateProbe probe, void* context = nullptr) {
    begin(serial);
    _link_state_probe = probe;
    _link_state_context = context;
  }

  void setLinkStateProbe(LinkStateProbe probe, void* context = nullptr) {
    _link_state_probe = probe;
    _link_state_context = context;
  }

  void clearSession();
  bool hasEstablishedSession() const { return _session_established; }
#endif

  // BaseSerialInterface methods
  void enable() override;
  void disable() override;
  bool isEnabled() const override { return _isEnabled; }

  bool isConnected() const override;
  uint32_t sessionGeneration() const override;
  void loop() override;

  bool isReadBusy() const override;
  bool isWriteBusy() const override;
  size_t writeFrame(const uint8_t src[], size_t len) override;
  size_t checkRecvFrame(uint8_t dest[]) override;
};
