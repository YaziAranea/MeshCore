#include "CoreSettingsCommands.h"
#include "MeshCoreCli.h"
#include <helpers/SmartUiQuickReplies.h>
#include <stdio.h>
#include <string.h>

namespace smartui {
namespace {
int hexDigit(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  return -1;
}
}

bool handleCoreSettingsCommand(const char* command, char* reply, size_t capacity,
                               bool writable, MeshCoreCli& cli,
                               const char* node_name, int8_t max_tx) {
  if (!command) return false;
  const char* ns;
  const char* body;
  if (strncmp(command, "ui ", 3) == 0) { ns = "ui"; body = command + 3; }
  else if (strncmp(command, "settings ", 9) == 0) { ns = "settings"; body = command + 9; }
  else return false;
  const bool identity = strcmp(body, "identity") == 0;
  const bool name = strcmp(body, "name") == 0 || strncmp(body, "name ", 5) == 0;
  const bool tx = strcmp(body, "tx") == 0 || strncmp(body, "tx ", 3) == 0;
  if (!identity && !name && !tx) return false;
  if (!reply || !capacity) return true;
  auto error = [&](const char* why) { snprintf(reply, capacity, "ERR %s %s", ns, why); };
  if (capacity < 157) { error("buffer"); return true; }
  size_t length = 0;
  while (length <= 156 && command[length]) {
    const unsigned char c = static_cast<unsigned char>(command[length++]);
    if (c < 32 || c > 126) { error("invalid"); return true; }
  }
  if (length > 156) { error("invalid"); return true; }
  char operation[48] = {};
  const bool write = name || (tx && strcmp(body, "tx") != 0);
  if (name) {
    if (strncmp(body, "name ", 5) != 0) { error("invalid"); return true; }
    const char* hex = body + 5;
    const size_t size = strlen(hex);
    if (!size || size > 62 || size % 2) { error("invalid"); return true; }
    memcpy(operation, "set name ", 9);
    for (size_t i = 0; i < size; i += 2) {
      const int hi = hexDigit(hex[i]), lo = hexDigit(hex[i + 1]);
      if (hi < 0 || lo < 0 || (hi == 0 && lo == 0)) { error("invalid"); return true; }
      operation[9 + i / 2] = static_cast<char>((hi << 4) | lo);
    }
    if (!validQuickReply(operation + 9)) { error("invalid"); return true; }
  } else if (tx) {
    if (write) {
      if (strncmp(body, "tx set ", 7) != 0 || strlen(body + 7) >= 16) {
        error("invalid"); return true;
      }
      const char* digits = body + 7;
      if (*digits == '-') ++digits;
      if (!*digits) { error("invalid"); return true; }
      for (const char* p = digits; *p; ++p)
        if (*p < '0' || *p > '9') { error("invalid"); return true; }
      snprintf(operation, sizeof(operation), "set tx %s", body + 7);
    } else memcpy(operation, "get tx", 7);
  }
  if (!identity) {
    if (!cli.handle(operation, reply, capacity, writable)) { error("unsupported"); return true; }
    if (write) {
      if (strcmp(reply, "OK") != 0) {
        const char* why = strstr(reply, "readonly") ? "readonly" :
            strstr(reply, "busy") ? "busy" : strstr(reply, "storage") ? "storage" :
            strstr(reply, "unsupported") ? "unsupported" : "invalid";
        error(why); return true;
      }
      if (tx && !cli.handle("get tx", reply, capacity, false)) { error("internal"); return true; }
    }
    if (tx) {
      // Output comes from the known production get-tx formatter; still validate
      // before embedding it in a machine-readable record.
      if (strncmp(reply, "> ", 2) != 0) { error("internal"); return true; }
      const char* number = reply + 2;
      bool negative = *number == '-';
      if (negative) ++number;
      if (!*number || strlen(number) > 3) { error("internal"); return true; }
      int value = 0;
      for (; *number; ++number) {
        if (*number < '0' || *number > '9') { error("internal"); return true; }
        value = value * 10 + *number - '0';
      }
      if (negative) value = -value;
      snprintf(reply, capacity, "OK %s tx value=%d min=-9 max=%d", ns, value, static_cast<int>(max_tx));
      return true;
    }
  }
  size_t size = 0;
  if (!node_name) { error("unsupported"); return true; }
  while (size <= 31 && node_name[size]) ++size;
  if (size > 31) { error("internal"); return true; }
  const size_t used = static_cast<size_t>(snprintf(reply, capacity, "OK %s %s name_hex=", ns, identity ? "identity" : "name"));
  static const char digits[] = "0123456789abcdef";
  for (size_t i = 0; i < size; ++i) {
    const uint8_t c = static_cast<uint8_t>(node_name[i]);
    reply[used + 2 * i] = digits[c >> 4];
    reply[used + 2 * i + 1] = digits[c & 15];
  }
  snprintf(reply + used + 2 * size, capacity - used - 2 * size, "%s", identity ? " max_name_bytes=31" : "");
  return true;
}
}
