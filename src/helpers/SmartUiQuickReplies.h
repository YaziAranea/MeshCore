#pragma once
#include <stddef.h>
#include <stdint.h>

#define SMARTUI_QUICK_REPLY_COUNT 9
#define SMARTUI_QUICK_REPLY_MAX_BYTES 64

namespace smartui {
// Empty override restores the built-in phrase. Reject malformed UTF-8 and
// control characters rather than silently truncating a user message.
inline bool validQuickReply(const char* text) {
  if (!text) return false;
  size_t length = 0;
  while (length <= SMARTUI_QUICK_REPLY_MAX_BYTES && text[length]) ++length;
  if (length > SMARTUI_QUICK_REPLY_MAX_BYTES) return false;
  for (size_t i = 0; i < length;) {
    const uint8_t first = static_cast<uint8_t>(text[i++]);
    uint32_t point = first;
    unsigned extra = 0;
    uint32_t minimum = 0;
    if (first >= 0xc2 && first <= 0xdf) { point = first & 31; extra = 1; minimum = 0x80; }
    else if (first >= 0xe0 && first <= 0xef) { point = first & 15; extra = 2; minimum = 0x800; }
    else if (first >= 0xf0 && first <= 0xf4) { point = first & 7; extra = 3; minimum = 0x10000; }
    else if (first >= 0x80) return false;
    if (i + extra > length) return false;
    while (extra--) {
      const uint8_t next = static_cast<uint8_t>(text[i++]);
      if ((next & 0xc0) != 0x80) return false;
      point = (point << 6) | (next & 63);
    }
    if (point < minimum || point > 0x10ffff || (point >= 0xd800 && point <= 0xdfff) ||
        point < 0x20 || (point >= 0x7f && point <= 0x9f) || point == 0x2028 || point == 0x2029) return false;
  }
  return true;
}
}  // namespace smartui
