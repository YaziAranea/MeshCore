#include "DynamicConfigSerializer.h"

namespace {
bool validKey(const char* key) {
  if (!key || !*key) return false;
  for (size_t len = 0; key[len]; ++len) {
    const char c = key[len];
    if (len >= CONFIG_MAX_KEYLEN - 1 ||
        !((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
          (c >= '0' && c <= '9') || c == '_')) return false;
  }
  return true;
}

bool matchesKey(const char* item, size_t item_len, const char* key, size_t key_len) {
  return item_len > key_len && item[key_len] == ':' &&
         memcmp(item, key, key_len) == 0;
}
}

bool DynamicConfigSerializer::setByKeyPrv(const char* key, const char* value) {
  // Reject unrepresentable delimiters before modifying the fallback or store.
  if (!validKey(key) || !value || strchr(value, '|') || strchr(value, ':')) return false;
  const size_t key_len = strlen(key);
  const size_t value_len = strlen(value);
  if (key_len + value_len + 2 > sizeof(_config)) return false;
  if (_fallback && _fallback->setByKey(key, value)) return true;

  char next[MAX_DYNAMIC_CONFG];
  size_t used = 0;
  for (const char* item = _config; *item;) {
    const char* end = strchr(item, '|');
    const size_t item_len = end ? static_cast<size_t>(end - item) : strlen(item);
    if (!matchesKey(item, item_len, key, key_len)) {
      const size_t need = item_len + (used ? 1 : 0);
      if (used + need >= sizeof(next)) return false;
      if (used) next[used++] = '|';
      memcpy(next + used, item, item_len);
      used += item_len;
    }
    if (!end) break;
    item = end + 1;
  }
  const size_t need = (used ? 1 : 0) + key_len + 1 + value_len;
  if (used + need >= sizeof(next)) return false;
  if (used) next[used++] = '|';
  memcpy(next + used, key, key_len);
  used += key_len;
  next[used++] = ':';
  memcpy(next + used, value, value_len);
  used += value_len;
  next[used] = 0;
  memcpy(_config, next, used + 1);
  return true;
}

bool DynamicConfigSerializer::setByKey(const char* key, const char* value) {
  if (!setByKeyPrv(key, value)) return false;
  markDirty();
  return true;
}

bool DynamicConfigSerializer::getByKey(const char* key, char* value, size_t max_len) {
  if (!validKey(key) || !value || max_len == 0) return false;
  if (_fallback && _fallback->getByKey(key, value, max_len)) return true;
  const size_t key_len = strlen(key);
  for (const char* item = _config; *item;) {
    const char* end = strchr(item, '|');
    const size_t item_len = end ? static_cast<size_t>(end - item) : strlen(item);
    if (matchesKey(item, item_len, key, key_len)) {
      size_t len = item_len - key_len - 1;
      if (len >= max_len) len = max_len - 1;
      memcpy(value, item + key_len + 1, len);
      value[len] = 0;
      return true;
    }
    if (!end) break;
    item = end + 1;
  }
  return false;
}

void DynamicConfigSerializer::structure() {
  if (_context->op() == OP::WRITE) {
    char tmp[MAX_DYNAMIC_CONFG];
    memcpy(tmp, _config, sizeof(tmp));
    for (char* item = tmp; *item;) {
      char* end = strchr(item, '|');
      if (end) *end = 0;
      char* separator = strchr(item, ':');
      if (separator) {
        *separator = 0;
        def(item, separator + 1, strlen(separator + 1) + 1);
      }
      if (!end) break;
      item = end + 1;
    }
  } else if (_context->objectToken() || _context->tokenDepth() != getDepth() ||
             !setByKeyPrv(_context->getKey(getDepth()), _context->getToken())) {
    _context->success = false;
  }
}
