#pragma once

#include <stddef.h>
#include <stdint.h>

namespace smartui {

// Local CMD66/RESP29 backport, discovered through smartui_cli:1. This does
// not advertise protocol v14 or grant remote mesh CLI permission. Prefixes
// correlate responses only: commands are not cached or deduplicated.
class SmartUiCli {
public:
  static constexpr uint8_t COMMAND = 66;
  static constexpr uint8_t RESPONSE = 29;
  static constexpr size_t MAX_FRAME = 160;
  static constexpr size_t MAX_COMMAND = 156;
  static constexpr size_t MAX_REPLY = 156;
  using Execute = bool (*)(void*, const char*, char*, size_t);

  void resetSession();
  // No writes or dynamic allocation here. A full response-sized destination
  // is required before executing anything. arm_mode belongs to this call only.
  size_t handle(const uint8_t* request, size_t length, uint8_t* response,
                size_t capacity, Execute execute, void* context, bool& arm_mode);

private:
  char _command[MAX_COMMAND + 1] = {};
  char _reply[MAX_REPLY + 1] = {};
};

}  // namespace smartui

#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
bool executeSmartUiCliCommand(const char* command, char* reply, size_t capacity);
void resetSmartUiCliSession();
#endif
