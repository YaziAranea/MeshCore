#include "RemoteCli.h"

#include <stdio.h>
#include <string.h>

namespace smartui {
namespace {
bool word(const char* command, const char* prefix) {
  const size_t n = strlen(prefix);
  return strncmp(command, prefix, n) == 0 && (command[n] == 0 || command[n] == ' ');
}
bool alnum(char c) {
  return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z');
}
}  // namespace

struct RemoteCli::Context {
  bool allowed;
  uint32_t timestamp;
  uint32_t& high_water;
  SmartUiCli::Execute execute;
  void* owner;
  char* result;
};

bool RemoteCli::localOnly(const char* command) {
  // These operations own a local transport, Wi-Fi wizard, calibration preview,
  // or permission session. Reject before any shared local dispatcher runs.
  if (word(command, "set connection") || word(command, "get remote.cli") ||
      word(command, "set remote.cli")) return true;
  if (word(command, "ui mode") && strcmp(command, "ui mode status") != 0) return true;
  if (word(command, "ui wifi") && strcmp(command, "ui wifi status") != 0) return true;
  if (word(command, "ui adc") || word(command, "adc") ||
      word(command, "set adc") || word(command, "set adc.multiplier")) return true;
  // Private/legacy entry points never become a remotely reachable escape hatch.
  return word(command, "api") || word(command, "settings") || word(command, "wifi");
}

bool RemoteCli::dispatch(void* opaque, const char* command, char* reply, size_t capacity) {
  Context& context = *static_cast<Context*>(opaque);
  const char* error = nullptr;
  if (!context.allowed) error = "Error: denied";
  else if (context.timestamp <= context.high_water) error = "Error: replay";
  else {
    // RAM only, tied to the complete authenticated ContactInfo identity.
    // A new timestamp is a new request, even if command text is identical.
    context.high_water = context.timestamp;
    if (localOnly(command)) error = "Error: local only";
  }
  if (error) { snprintf(reply, capacity, "%s", error); return true; }
  if (!context.execute || !context.execute(context.owner, command, context.result,
                                            SmartUiCli::MAX_REPLY + 2)) return false;
  size_t length = 0;
  while (length <= SmartUiCli::MAX_REPLY && context.result[length]) ++length;
  if (length > SmartUiCli::MAX_REPLY) snprintf(reply, capacity, "Error: response too long");
  else memcpy(reply, context.result, length + 1);
  return true;
}

void RemoteCli::handle(const char* text, size_t length, bool allowed,
                       uint32_t timestamp, uint32_t& high_water, char* reply,
                       size_t capacity, SmartUiCli::Execute execute, void* owner) {
  if (!reply || capacity < REPLY_CAPACITY) return;
  reply[0] = 0;
  // Encryption pads the plaintext with NULs. Strip only trailing padding;
  // embedded NUL/control bytes remain in the request and fail SmartUiCli checks.
  while (text && length && text[length - 1] == 0) --length;
  if (!text || length >= sizeof(_request)) {
    const bool prefix = text && length >= 3 && text[2] == '|' && alnum(text[0]) && alnum(text[1]);
    snprintf(reply, capacity, "%.*s%s", prefix ? 3 : 0, prefix ? text : "",
             text ? "Error: command too long" : "Error: invalid command");
    return;
  }
  _request[0] = SmartUiCli::COMMAND;
  if (length) memcpy(_request + 1, text, length);
  memset(_result, 0, sizeof(_result));
  Context context{allowed, timestamp, high_water, execute, owner, _result};
  bool arm_mode = false;
  const size_t size = _cli.handle(_request, length + 1, reinterpret_cast<uint8_t*>(reply),
                                  capacity, dispatch, &context, arm_mode);
  if (size) {
    // Native CLI replies contain text only; CMD66/RESP29 never goes over LoRa.
    memmove(reply, reply + 1, size - 1);
    reply[size - 1] = 0;
  }
  volatile uint8_t* erase = _request;
  for (size_t i = 0; i < sizeof(_request); ++i) erase[i] = 0;
  volatile char* erase_result = _result;
  for (size_t i = 0; i < sizeof(_result); ++i) erase_result[i] = 0;
}

}  // namespace smartui
