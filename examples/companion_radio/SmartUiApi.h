#pragma once

#include <stddef.h>
#include <stdint.h>

namespace smartui {

// Fork-local, opt-in extension. Discover smartui_api:1 using CUSTOM_VARS
// before sending this opcode; it is not an upstream-reserved command number.
class SmartUiApi {
public:
  static constexpr uint8_t COMMAND = 201;
  static constexpr uint8_t VERSION = 1;
  static constexpr size_t HEADER = 8;
  static constexpr size_t RESPONSE_HEADER = 13;
  static constexpr size_t MAX_COMMAND = 152;
  static constexpr size_t MAX_REPLY = 480;
  // Fits both a 176-byte companion frame and ATT MTU 176 (3 bytes overhead).
  // BLE clients must negotiate ATT MTU >= 163 before using this extension.
  static constexpr size_t MAX_FRAME = 160;
  enum Status : uint8_t {
    OK = 0, MALFORMED = 1, BAD_VERSION = 2, UNKNOWN_OPERATION = 3,
    BUSY = 4, DENIED = 5, STALE = 6, COMMAND_FAILED = 7,
  };
  using Execute = bool (*)(const char*, char*, size_t, bool);

  void begin(Execute execute) { _execute = execute; resetSession(); }
  void resetSession();
  // Produces exactly one complete companion frame. No transport writes here.
  // Reads are cached too, making pagination and retransmission one snapshot.
  size_t handle(const uint8_t* request, size_t length, uint8_t* response,
                size_t capacity, bool allow_mutation);

private:
  Execute _execute = nullptr;
  uint8_t _request[HEADER + MAX_COMMAND] = {};
  char _reply[MAX_REPLY] = {};
  uint16_t _last_id = 0;
  uint16_t _request_length = 0;
  uint16_t _reply_length = 0;
  uint8_t _status = OK;
  size_t page(uint8_t* response, size_t capacity, uint16_t id, uint8_t operation,
              uint8_t status, uint16_t offset, const char* body, uint16_t total);
};

}  // namespace smartui

#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
size_t handleSmartUiApiFrame(const uint8_t* request, size_t length,
                            uint8_t* response, size_t capacity);
void resetSmartUiApiSession();
#endif
