#pragma once

#include "SmartUiCli.h"

namespace smartui {

// Native LoRa TXT_TYPE_CLI_COMMAND adapter. Own framing buffers keep a remote
// request independent of the local companion client's CMD66/session state.
class RemoteCli {
public:
  static constexpr size_t REPLY_CAPACITY = 161;  // 160 text bytes and NUL.
  void handle(const char* text, size_t length, bool allowed,
              uint32_t timestamp, uint32_t& high_water, char* reply,
              size_t capacity, SmartUiCli::Execute execute, void* context);
  static bool localOnly(const char* command);

private:
  struct Context;
  static bool dispatch(void*, const char*, char*, size_t);
  SmartUiCli _cli;
  uint8_t _request[SmartUiCli::MAX_FRAME] = {};
  // One extra character exposes snprintf truncation at the wire limit.
  char _result[SmartUiCli::MAX_REPLY + 2] = {};
};

}  // namespace smartui
