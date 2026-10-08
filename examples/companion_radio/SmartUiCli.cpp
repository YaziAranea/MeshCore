#include "SmartUiCli.h"

#include <stdio.h>
#include <string.h>

namespace smartui {
namespace {
bool asciiAlnum(uint8_t c) {
  return (c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z') ||
         (c >= 'a' && c <= 'z');
}

size_t boundedLength(const char* text, size_t capacity) {
  size_t length = 0;
  while (length < capacity && text[length]) ++length;
  return length;
}

bool validReplyText(const char* text, size_t length) {
  for (size_t i = 0; i < length;) {
    const uint8_t first = static_cast<uint8_t>(text[i++]);
    if (first < 0x20 || first == 0x7f) return false;
    if (first < 0x80) continue;
    unsigned extra;
    uint32_t code, minimum;
    if (first >= 0xc2 && first <= 0xdf) { extra = 1; code = first & 0x1f; minimum = 0x80; }
    else if (first >= 0xe0 && first <= 0xef) { extra = 2; code = first & 0x0f; minimum = 0x800; }
    else if (first >= 0xf0 && first <= 0xf4) { extra = 3; code = first & 0x07; minimum = 0x10000; }
    else return false;
    if (length - i < extra) return false;
    while (extra--) {
      const uint8_t c = static_cast<uint8_t>(text[i++]);
      if ((c & 0xc0) != 0x80) return false;
      code = (code << 6) | (c & 0x3f);
    }
    if (code < minimum || code > 0x10ffff || (code >= 0xd800 && code <= 0xdfff)) return false;
  }
  return true;
}

void erase(char* buffer, size_t size) {
  volatile char* p = buffer;
  while (size--) *p++ = 0;
}
}  // namespace

void SmartUiCli::resetSession() {
  erase(_command, sizeof(_command));
  erase(_reply, sizeof(_reply));
}

size_t SmartUiCli::handle(const uint8_t* request, size_t length,
                         uint8_t* response, size_t capacity, Execute execute,
                         void* context, bool& arm_mode) {
  arm_mode = false;
  resetSession();
  if (!response || capacity < MAX_FRAME) return 0;
  char prefix[3] = {};
  size_t prefix_length = 0;
  const char* error = nullptr;
  if (!request || !length || request[0] != COMMAND) return 0;
  if (length > MAX_FRAME) error = "Error: command too long";
  else if (length < 2) error = "Error: invalid command";
  else {
    // Preserve a syntactically valid correlation prefix even when the body
    // is rejected. Never echo invalid/control bytes from the prefix itself.
    if (length >= 4 && request[3] == '|') {
      if (!asciiAlnum(request[1]) || !asciiAlnum(request[2])) {
        error = "Error: invalid prefix";
      } else {
        memcpy(prefix, request + 1, sizeof(prefix));
        prefix_length = sizeof(prefix);
      }
    }
    // Upstream commands carry UTF-8 text (`set name Дача`). Control bytes,
    // DEL and malformed sequences stay rejected; `ui ...` keeps its own ASCII
    // checks in each handler.
    if (!error && !validReplyText(reinterpret_cast<const char*>(request + 1), length - 1))
      error = "Error: invalid command";
    if (!error) {
      const size_t command_length = length - 1 - prefix_length;
      if (!command_length) error = "Error: invalid command";
      else if (command_length > MAX_COMMAND) error = "Error: command too long";
      else {
        memcpy(_command, request + 1 + prefix_length, command_length);
        _command[command_length] = 0;
        if (strchr(_command, '|')) error = "Error: invalid prefix";
      }
    }
  }
  if (error) {
    snprintf(_reply, sizeof(_reply), "%s", error);
  } else if (!execute || !execute(context, _command, _reply, sizeof(_reply))) {
    snprintf(_reply, sizeof(_reply), "Unknown command");
  }
  size_t reply_length = boundedLength(_reply, sizeof(_reply));
  const bool valid_reply = reply_length > 0 && reply_length <= MAX_REPLY &&
      validReplyText(_reply, reply_length);
  // UTF-8 names are allowed in replies, but never line/control injection.
  if (!valid_reply) {
    snprintf(_reply, sizeof(_reply), "Error: invalid response");
    reply_length = strlen(_reply);
  }
  if (!error && valid_reply) {
    const char* modes[] = {"ble", "usb", "wifi"};
    for (const char* mode : modes) {
      char command[20], reply[48];
      snprintf(command, sizeof(command), "ui mode %s", mode);
      snprintf(reply, sizeof(reply), "OK ui mode target=%s state=pending", mode);
      if (strcmp(_command, command) == 0 && strcmp(_reply, reply) == 0) {
        arm_mode = true;
        break;
      }
      // The compact console uses the same delayed mode transaction. Arm it
      // only for this exact request/target/reply pair, after the outer owner
      // has queued the complete response; unrelated or stale replies cannot
      // close the connection.
      snprintf(command, sizeof(command), "set connection %s", mode);
      snprintf(reply, sizeof(reply), "OK mode target=%s state=pending", mode);
      if (strcmp(_command, command) == 0 && strcmp(_reply, reply) == 0) {
        arm_mode = true;
        break;
      }
    }
  }
  response[0] = RESPONSE;
  if (prefix_length) memcpy(response + 1, prefix, prefix_length);
  memcpy(response + 1 + prefix_length, _reply, reply_length);
  const size_t result = 1 + prefix_length + reply_length;
  resetSession();  // Never retain Wi-Fi command credentials between calls.
  return result;
}

}  // namespace smartui
