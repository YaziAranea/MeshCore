#include "SmartUiApi.h"
#include <string.h>

namespace smartui {
namespace {
uint16_t u16(const uint8_t* p) { return p[0] | (uint16_t(p[1]) << 8); }
void put16(uint8_t* p, uint16_t value) { p[0] = value; p[1] = value >> 8; }
}

void SmartUiApi::resetSession() {
  // No requests or ADC-operation results may leak to the next local client.
  memset(_request, 0, sizeof(_request));
  memset(_reply, 0, sizeof(_reply));
  _last_id = _request_length = _reply_length = 0;
  _status = OK;
}

size_t SmartUiApi::page(uint8_t* response, size_t capacity, uint16_t id,
                       uint8_t operation, uint8_t status, uint16_t offset,
                       const char* body, uint16_t total) {
  if (!response || capacity < RESPONSE_HEADER || offset > total) return 0;
  const uint8_t header[] = {COMMAND, 'S', 'U', 'I', VERSION};
  memcpy(response, header, sizeof(header));
  put16(response + 5, id);
  response[7] = operation;
  response[8] = status;
  put16(response + 9, offset);
  put16(response + 11, total);
  if (capacity > MAX_FRAME) capacity = MAX_FRAME;
  size_t count = total - offset;
  if (count > capacity - RESPONSE_HEADER) count = capacity - RESPONSE_HEADER;
  if (count) memcpy(response + RESPONSE_HEADER, body + offset, count);
  return RESPONSE_HEADER + count;
}

size_t SmartUiApi::handle(const uint8_t* request, size_t length,
                         uint8_t* response, size_t capacity, bool allow_mutation) {
  if (!response || capacity < MAX_FRAME) return 0;  // never mutate without room for ACK
  const uint16_t id = request && length >= HEADER ? u16(request + 5) : 0;
  const uint8_t op = request && length >= HEADER ? request[7] : 0;
  auto error = [&](uint8_t code) {
    return page(response, capacity, id, op, code, 0, nullptr, 0);
  };
  if (!request || length < HEADER || length > HEADER + MAX_COMMAND ||
      request[0] != COMMAND || memcmp(request + 1, "SUI", 3) != 0 || !id)
    return error(MALFORMED);
  if (request[4] != VERSION) return error(BAD_VERSION);
  if (op > 2) return error(UNKNOWN_OPERATION);
  if (op == 2) {
    if (length != HEADER + 2) return error(MALFORMED);
    const uint16_t offset = u16(request + HEADER);
    if (!_last_id || id != _last_id) return error(STALE);
    if (offset > _reply_length || (offset == _reply_length && offset != 0))
      return error(MALFORMED);
    return page(response, capacity, id, op, _status, offset, _reply, _reply_length);
  }
  if ((op == 0 && length != HEADER) || (op == 1 && length == HEADER))
    return error(MALFORMED);
  if (op == 1) {
    for (size_t i = HEADER; i < length; ++i)
      if (request[i] < 0x20 || request[i] > 0x7e) return error(MALFORMED);
  }
  if (id == _last_id) {
    if (length != _request_length || memcmp(request, _request, length) != 0)
      return error(STALE);
    return page(response, capacity, id, op, _status, 0, _reply, _reply_length);
  }
  // Strictly increasing IDs stop a late retry from replaying an old write.
  // Reconnect before the 16-bit counter wraps; no modulo comparisons.
  if (id < _last_id) return error(STALE);
  memcpy(_request, request, length);
  _request_length = length;
  _last_id = id;
  memset(_reply, 0, sizeof(_reply));
  char command[MAX_COMMAND + 1];
  if (op == 0) strcpy(command, "api hello");
  else {
    memcpy(command, request + HEADER, length - HEADER);
    command[length - HEADER] = 0;
  }
  bool handled = _execute && _execute(command, _reply, sizeof(_reply), allow_mutation);
  const char* end = static_cast<const char*>(memchr(_reply, 0, sizeof(_reply)));
  bool valid = handled && end &&
      ((strncmp(_reply, "OK api ", 7) == 0 && end > _reply + 7) ||
       (strncmp(_reply, "ERR api ", 8) == 0 && end > _reply + 8));
  if (valid) {
    for (const char* p = _reply; p != end; ++p)
      if (*p < 0x20 || *p > 0x7e) { valid = false; break; }
  }
  if (!valid) {
    strcpy(_reply, "ERR api unsupported");
  }
  _reply_length = strlen(_reply);
  _status = strncmp(_reply, "OK api ", 7) == 0 ? OK : COMMAND_FAILED;
  if (strcmp(_reply, "ERR api readonly") == 0) _status = DENIED;
  if (strcmp(_reply, "ERR api busy") == 0) _status = BUSY;
  return page(response, capacity, id, op, _status, 0, _reply, _reply_length);
}
}  // namespace smartui
