#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>

namespace smartui {

inline bool isUtf8Continuation(uint8_t c) {
  return (c & 0xC0) == 0x80;
}

inline const char* readUtf8Codepoint(const char* p, uint32_t& cp) {
  const uint8_t* s = (const uint8_t*)p;
  uint8_t b0 = s[0];
  if (b0 == 0 || b0 < 0x80) {
    cp = b0;
    return p + (b0 ? 1 : 0);
  }
  if ((b0 & 0xE0) == 0xC0 && isUtf8Continuation(s[1])) {
    cp = ((uint32_t)(b0 & 0x1F) << 6) | (s[1] & 0x3F);
    return p + 2;
  }
  if ((b0 & 0xF0) == 0xE0 && isUtf8Continuation(s[1]) && isUtf8Continuation(s[2])) {
    cp = ((uint32_t)(b0 & 0x0F) << 12) | ((uint32_t)(s[1] & 0x3F) << 6) | (s[2] & 0x3F);
    return p + 3;
  }
  if ((b0 & 0xF8) == 0xF0 && isUtf8Continuation(s[1]) &&
      isUtf8Continuation(s[2]) && isUtf8Continuation(s[3])) {
    cp = ((uint32_t)(b0 & 0x07) << 18) | ((uint32_t)(s[1] & 0x3F) << 12) |
         ((uint32_t)(s[2] & 0x3F) << 6) | (s[3] & 0x3F);
    return p + 4;
  }
  cp = b0;
  return p + 1;
}

inline uint32_t mentionLowerCodepoint(uint32_t cp) {
  if (cp >= 'A' && cp <= 'Z') return cp + ('a' - 'A');
  if (cp >= 0x0410 && cp <= 0x042F) return cp + 0x20;
  if (cp == 0x0401) return 0x0451;
  if (cp == 0x0404) return 0x0454;
  if (cp == 0x0406) return 0x0456;
  if (cp == 0x0407) return 0x0457;
  if (cp == 0x0490) return 0x0491;
  return cp;
}

inline bool mentionWordCodepoint(uint32_t cp) {
  if (cp >= '0' && cp <= '9') return true;
  if (cp >= 'A' && cp <= 'Z') return true;
  if (cp >= 'a' && cp <= 'z') return true;
  if (cp == '_' || cp == '-') return true;
  if (cp >= 0x0410 && cp <= 0x044F) return true;
  return cp == 0x0401 || cp == 0x0451 || cp == 0x0404 || cp == 0x0454 ||
         cp == 0x0406 || cp == 0x0456 || cp == 0x0407 || cp == 0x0457 ||
         cp == 0x0490 || cp == 0x0491;
}

inline bool mentionNameTokenCodepoint(uint32_t cp) {
  return mentionWordCodepoint(cp) && cp != '_' && cp != '-';
}

inline size_t utf8CodepointCount(const char* s) {
  size_t count = 0;
  while (s && *s) {
    uint32_t cp;
    s = readUtf8Codepoint(s, cp);
    count++;
  }
  return count;
}

inline size_t utf8NameFirstTokenCodepointCount(const char* node_name) {
  size_t count = 0;
  for (const char* n = node_name; n && *n;) {
    uint32_t cp;
    const char* next = readUtf8Codepoint(n, cp);
    if (!mentionNameTokenCodepoint(cp)) break;
    count++;
    n = next;
  }
  return count;
}

inline bool utf8NameMatchesAt(const char* text, const char* node_name, const char** after_text) {
  const char* t = text;
  const char* n = node_name;
  while (*n) {
    if (!*t) return false;
    uint32_t tc, nc;
    t = readUtf8Codepoint(t, tc);
    n = readUtf8Codepoint(n, nc);
    if (mentionLowerCodepoint(tc) != mentionLowerCodepoint(nc)) return false;
  }
  if (after_text) *after_text = t;
  return true;
}

inline bool utf8NameFirstTokenMatchesAt(const char* text, const char* node_name,
                                        const char** after_text) {
  const char* t = text;
  const char* n = node_name;
  size_t matched = 0;
  while (*n) {
    uint32_t nc;
    const char* next_n = readUtf8Codepoint(n, nc);
    if (!mentionNameTokenCodepoint(nc)) break;
    if (!*t) return false;
    uint32_t tc;
    t = readUtf8Codepoint(t, tc);
    if (mentionLowerCodepoint(tc) != mentionLowerCodepoint(nc)) return false;
    n = next_n;
    matched++;
  }
  if (matched < 2) return false;
  if (after_text) *after_text = t;
  return true;
}

inline const char* channelMentionBodyText(const char* text) {
  const char* sep = text ? strstr(text, ": ") : NULL;
  return (sep && sep > text) ? sep + 2 : text;
}

inline bool mentionMatchEndsAtBoundary(const char* after) {
  uint32_t after_cp = 0;
  if (after && *after) readUtf8Codepoint(after, after_cp);
  return !mentionWordCodepoint(after_cp);
}

struct MentionNameMetrics {
  size_t name_chars;
  size_t first_token_chars;
};

inline MentionNameMetrics mentionNameMetrics(const char* node_name) {
  return {utf8CodepointCount(node_name), utf8NameFirstTokenCodepointCount(node_name)};
}

inline uint16_t mentionMatchRankAt(const char* text, const char* node_name,
                                  bool allow_first_token, const MentionNameMetrics& metrics) {
  if (!text || !node_name || !*node_name) return 0;
  uint16_t best_rank = 0;
  const char* after = NULL;
  size_t name_chars = metrics.name_chars;
  if (name_chars >= 2 && utf8NameMatchesAt(text, node_name, &after) &&
      mentionMatchEndsAtBoundary(after)) {
    best_rank = (uint16_t)(name_chars * 2 + 1);
  }
  size_t first_token_chars = metrics.first_token_chars;
  if (allow_first_token && first_token_chars >= 2 &&
      utf8NameFirstTokenMatchesAt(text, node_name, &after) && mentionMatchEndsAtBoundary(after)) {
    uint16_t rank = (uint16_t)(first_token_chars * 2);
    if (rank > best_rank) best_rank = rank;
  }
  return best_rank;
}


inline uint16_t mentionMatchRankAt(const char* text, const char* node_name, bool allow_first_token) {
  return mentionMatchRankAt(text, node_name, allow_first_token, mentionNameMetrics(node_name));
}

struct MentionPolicy {
  bool require_at;
  size_t short_name_at_only_chars;
  bool allow_plain_node_name;
  bool allow_plain_first_token;
  size_t plain_first_token_min_chars;
};

// The expensive name-ownership check runs only after our own name matched.
template <typename AcceptCandidate>
bool textMentionsNodeName(const char* text, const char* node_name, const MentionPolicy& policy,
                          AcceptCandidate accept_candidate) {
  if (!text || !node_name || !*node_name) return false;
  const MentionNameMetrics metrics = mentionNameMetrics(node_name);
  if (metrics.name_chars < 2) return false;
  bool at_only = policy.require_at || metrics.name_chars <= policy.short_name_at_only_chars;
  bool plain_full_allowed = !at_only || policy.allow_plain_node_name;
  bool plain_first_allowed = policy.allow_plain_first_token &&
                            metrics.first_token_chars >= policy.plain_first_token_min_chars;
  auto matches = [&](const char* at, bool allow_first_token) {
    uint16_t own_rank = mentionMatchRankAt(at, node_name, allow_first_token, metrics);
    return own_rank != 0 && accept_candidate(at, allow_first_token, own_rank);
  };
  bool prev_boundary = true;
  for (const char* p = text; *p;) {
    uint32_t cp;
    const char* next = readUtf8Codepoint(p, cp);
    if (cp == '@' && matches(next, true)) return true;
    if (prev_boundary) {
      if (plain_full_allowed && matches(p, false)) return true;
      if (plain_first_allowed && matches(p, true)) return true;
    }
    prev_boundary = !mentionWordCodepoint(cp);
    p = next;
  }
  return false;
}

// Keep one per-message snapshot; avoid a copy on messages without a matching name.
template <typename Entry, size_t Capacity>
struct LazyMentionSnapshot {
  Entry entries[Capacity];
  int count = -1;

  template <typename Loader>
  int load(Loader loader) {
    if (count < 0) {
      count = loader(entries, Capacity);
      if (count < 0) count = 0;
      if (count > static_cast<int>(Capacity)) count = static_cast<int>(Capacity);
    }
    return count;
  }
};

// Complete key:value entries only; never truncate a field or exceed the frame.
class CustomVarsWriter {
  char* _buffer;
  size_t _capacity;
  size_t _size = 0;

public:
  CustomVarsWriter(char* buffer, size_t capacity) : _buffer(buffer), _capacity(capacity) {
    if (_capacity) _buffer[0] = 0;
  }

  size_t size() const { return _size; }

  bool append(const char* name, const char* value) {
    if (!name || !value || _capacity == 0) return false;
    size_t room = _capacity - _size - 1; // reserve the trailing NUL
    const size_t separator = _size ? 1 : 0;
    if (room < separator + 1) return false;
    room -= separator + 1; // comma, when needed, plus colon
    const size_t name_length = strlen(name);
    if (name_length > room) return false;
    room -= name_length;
    const size_t value_length = strlen(value);
    if (value_length > room) return false;
    if (separator) _buffer[_size++] = ',';
    memcpy(_buffer + _size, name, name_length);
    _size += name_length;
    _buffer[_size++] = ':';
    memcpy(_buffer + _size, value, value_length);
    _size += value_length;
    _buffer[_size] = 0;
    return true;
  }
};

} // namespace smartui
