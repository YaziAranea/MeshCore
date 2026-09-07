#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>

namespace smartui {

// Compact, deterministic A-Z / А-Я / # index. Ё belongs to Е. No allocation,
// no locale dependency, and unsupported/invalid initials stay reachable in #.
static constexpr uint8_t CONTACT_INITIAL_GROUPS = 59;
inline uint8_t contactInitialGroup(const char* name) {
  if (name == nullptr) return 58;
  while (*name == ' ' || *name == '\t') ++name;
  const uint8_t a = static_cast<uint8_t>(name[0]);
  if (a >= 'A' && a <= 'Z') return a - 'A';
  if (a >= 'a' && a <= 'z') return a - 'a';
  if ((a == 0xD0 || a == 0xD1) && name[1] != 0) {
    const uint8_t b = static_cast<uint8_t>(name[1]);
    if (b >= 0x80 && b <= 0xBF) {
      uint16_t cp = ((a & 0x1F) << 6) | (b & 0x3F);
      if (cp == 0x401 || cp == 0x451) cp = 0x415;
      if (cp >= 0x430 && cp <= 0x44F) cp -= 0x20;
      if (cp >= 0x410 && cp <= 0x42F) return 26 + cp - 0x410;
    }
  }
  return 58;
}

inline void contactInitialLabel(uint8_t group, char out[3]) {
  if (group < 26) {
    out[0] = 'A' + group;
    out[1] = 0;
  } else if (group < 58) {
    uint16_t cp = 0x410 + group - 26;
    out[0] = static_cast<char>(0xC0 | (cp >> 6));
    out[1] = static_cast<char>(0x80 | (cp & 0x3F));
    out[2] = 0;
  } else {
    out[0] = '#';
    out[1] = 0;
  }
}

// Session-only recipient shortcuts, not message drafts. A key is remembered
// only after a successful enqueue; live contact type/existence is revalidated.
template <size_t KeySize, size_t Capacity = 3>
class RecentRecipientKeys {
  uint8_t keys_[Capacity][KeySize] = {};
  uint8_t count_ = 0;
public:
  uint8_t count() const { return count_; }
  const uint8_t* at(size_t index) const { return index < count_ ? keys_[index] : nullptr; }
  void remember(const uint8_t* key) {
    if (key == nullptr) return;
    size_t found = 0;
    while (found < count_ && memcmp(keys_[found], key, KeySize) != 0) ++found;
    if (found == count_ && count_ < Capacity) ++count_;
    size_t last = found < Capacity ? found : Capacity - 1;
    for (size_t i = last; i > 0; --i) memcpy(keys_[i], keys_[i - 1], KeySize);
    memcpy(keys_[0], key, KeySize);
  }
};

inline const char* gpsClockStateWord(bool enabled, bool valid) {
  return !enabled ? "OFF" : valid ? "FIX" : "...";
}

}  // namespace smartui
