#pragma once

#include "../BaseSerialInterface.h"
#include <WiFi.h>

class SerialWifiInterface : public BaseSerialInterface {
  bool deviceConnected;
  bool _isEnabled;
  unsigned long _last_write;
  unsigned long adv_restart_time;

  WiFiServer server;
  WiFiClient client;

#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  struct TxFrame {
    uint16_t len;
    uint16_t offset;
    uint8_t buf[MAX_FRAME_SIZE + 3];
  };

  static const uint8_t WIFI_TX_QUEUE_CAPACITY = 4;
  static const size_t PENDING_PEER_SIZE = 16;

  WiFiClient pending_client;
  bool _server_running;
  bool _session_approved;
  uint16_t _port;
  uint32_t _listener_retry_at;
  mutable uint32_t _session_generation;
  uint32_t _next_request_id;
  uint32_t _pending_request_id;
  uint32_t _pending_deadline;
  char _pending_peer[PENDING_PEER_SIZE];

  uint8_t _rx_state;
  uint16_t _rx_frame_len;
  uint16_t _rx_len;
  uint32_t _rx_frame_started;
  uint8_t _rx_buf[MAX_FRAME_SIZE];

  uint8_t _tx_queue_len;
  TxFrame _tx_queue[WIFI_TX_QUEUE_CAPACITY];

  void advanceSessionGeneration() const;
  void resetReceiveParser();
  void clearTransportBuffers();
  void clearPendingClient(bool close_socket);
  void closeApprovedSession();
  void serviceClientState();
  void ensureServerListening();
  void offerPendingClient(WiFiClient& candidate);
  void pumpTx();
  static bool deadlineReached(uint32_t now, uint32_t deadline);
#else
  struct FrameHeader {
    uint8_t type;
    uint16_t length;
  };

  struct Frame {
    uint8_t len;
    uint8_t buf[MAX_FRAME_SIZE];
  };

  FrameHeader received_frame_header;

  #define FRAME_QUEUE_SIZE  4
  int recv_queue_len;
  Frame recv_queue[FRAME_QUEUE_SIZE];
  int send_queue_len;
  Frame send_queue[FRAME_QUEUE_SIZE];

  void clearBuffers() { recv_queue_len = 0; send_queue_len = 0; }
#endif

public:
  SerialWifiInterface()
      : deviceConnected(false), _isEnabled(false), _last_write(0),
        adv_restart_time(0), server(), client()
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
        , pending_client(), _server_running(false), _session_approved(false),
        _port(0), _listener_retry_at(0), _session_generation(0),
        _next_request_id(0), _pending_request_id(0), _pending_deadline(0),
        _pending_peer{},
        _rx_state(0), _rx_frame_len(0), _rx_len(0), _rx_frame_started(0),
        _rx_buf{}, _tx_queue_len(0), _tx_queue{}
#else
        , received_frame_header{}, recv_queue_len(0), recv_queue{},
        send_queue_len(0), send_queue{}
#endif
  {}

  void begin(int port);

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

#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  bool hasPendingClientApproval() const;
  uint32_t getPendingClientRequestId() const;
  uint32_t getPendingClientDeadline() const;
  bool copyPendingClientPeer(char* out, size_t out_len) const;
  bool resolvePendingClient(uint32_t request_id, bool approve);
  bool isSessionApproved() const;
#else
  bool hasReceivedFrameHeader();
  void resetReceivedFrameHeader();
#endif
};

#if WIFI_DEBUG_LOGGING && ARDUINO
  #include <Arduino.h>
  #define WIFI_DEBUG_PRINT(F, ...) Serial.printf("WiFi: " F, ##__VA_ARGS__)
  #define WIFI_DEBUG_PRINTLN(F, ...) Serial.printf("WiFi: " F "\n", ##__VA_ARGS__)
#else
  #define WIFI_DEBUG_PRINT(...) {}
  #define WIFI_DEBUG_PRINTLN(...) {}
#endif
