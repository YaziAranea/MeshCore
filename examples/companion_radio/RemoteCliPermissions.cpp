#include "RemoteCliPermissions.h"

#include <stdio.h>
#include <string.h>

namespace smartui {
namespace {
int hex(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}
bool owns(const char* command, const char* prefix) {
  const size_t length = strlen(prefix);
  return strncmp(command, prefix, length) == 0 &&
      (command[length] == 0 || command[length] == ' ');
}
}

bool handleRemoteCliPermissionCommand(const char* command, char* reply, size_t capacity,
    bool writable, bool busy, ReadRemoteCliPermission read, WriteRemoteCliPermission write) {
  if (!command) return false;
  const bool set = owns(command, "set remote.cli");
  if (!set && !owns(command, "get remote.cli")) return false;
  if (!reply || !capacity) return true;
  auto respond = [&](const char* text) { snprintf(reply, capacity, "%s", text); };
  // Never change permission unless a complete reply can be returned.
  if (capacity < 157) { respond("Error: buffer"); return true; }
  size_t length = 0;
  while (length <= 156 && command[length]) ++length;
  if (length > 156 || command[14] != ' ' || length < 79) {
    respond("Error: invalid argument"); return true;
  }
  uint8_t key[32];
  for (size_t i = 0; i < sizeof(key); ++i) {
    const int high = hex(command[15 + 2 * i]), low = hex(command[16 + 2 * i]);
    if (high < 0 || low < 0) { respond("Error: invalid key"); return true; }
    key[i] = static_cast<uint8_t>((high << 4) | low);
  }
  const char* tail = command + 79;
  bool enabled = false;
  if (set) {
    if (strcmp(tail, " on") == 0) enabled = true;
    else if (strcmp(tail, " off") != 0) { respond("Error: invalid argument"); return true; }
  } else if (*tail) { respond("Error: invalid argument"); return true; }
  bool previous;
  if (!read || !read(key, previous)) { respond("Error: contact not found"); return true; }
  if (!set) { respond(previous ? "> on" : "> off"); return true; }
  if (!writable) { respond("Error: readonly"); return true; }
  if (busy) { respond("Error: busy"); return true; }
  if (previous == enabled) { respond("OK"); return true; }
  respond(write && write(key, enabled) ? "OK" : "Error: storage");
  return true;
}
}
