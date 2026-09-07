#pragma once

#include <stdint.h>
#include <string.h>

namespace smartui {

// One UI operation may update several coupled scalar fields (one common
// melody has four IDs). Never retain or restore a whole preferences object.
class SettingUndo {
public:
  enum Result { Empty, Conflict, SaveFailed, Applied };
  static const uint8_t CAPACITY = 24;
private:
  struct Field {
    void* target;
    uint8_t size;
    uint8_t before[4];
    uint8_t after[4];
  } _fields[CAPACITY];
  uint8_t _count = 0;
  bool _overflow = false;
  // Some preferences are intentionally exposed through getters/setters only.
  void* _bool_context = nullptr;
  bool (*_read_bool)(void*) = nullptr;
  void (*_write_bool)(void*, bool) = nullptr;
  bool _bool_before = false, _bool_after = false;
public:
  void clear() { _count = 0; _overflow = false; _read_bool = nullptr; _write_bool = nullptr; }
  bool available() const { return (_count != 0 || _read_bool != nullptr) && !_overflow; }
  bool overflowed() const { return _overflow; }
  uint8_t count() const { return _count; }

  template <typename T> void capture(T& current, const T& previous) {
    static_assert(sizeof(T) <= 4, "UI undo supports scalar fields up to 32 bits");
    if (memcmp(&current, &previous, sizeof(T)) == 0) return;
    if (_count == CAPACITY) { _overflow = true; return; }
    Field& field = _fields[_count++];
    field.target = &current;
    field.size = sizeof(T);
    memcpy(field.before, &previous, sizeof(T));
    memcpy(field.after, &current, sizeof(T));
  }

  void captureBool(void* context, bool previous, bool current,
                   bool (*read)(void*), void (*write)(void*, bool)) {
    if (previous == current) return;
    _bool_context = context;
    _read_bool = read;
    _write_bool = write;
    _bool_before = previous;
    _bool_after = current;
  }

  template <typename Save> Result apply(Save save) {
    if (!available()) return Empty;
    // Validate every affected field before writing any of them. A newer BLE
    // or local change must not be overwritten by an old UI undo operation.
    if (_read_bool != nullptr && _read_bool(_bool_context) != _bool_after) {
      clear();
      return Conflict;
    }
    for (uint8_t i = 0; i < _count; ++i) {
      if (memcmp(_fields[i].target, _fields[i].after, _fields[i].size) != 0) {
        clear();
        return Conflict;
      }
    }
    for (uint8_t i = 0; i < _count; ++i)
      memcpy(_fields[i].target, _fields[i].before, _fields[i].size);
    if (_write_bool != nullptr) _write_bool(_bool_context, _bool_before);
    if (!save()) {
      for (uint8_t i = 0; i < _count; ++i)
        memcpy(_fields[i].target, _fields[i].after, _fields[i].size);
      if (_write_bool != nullptr) _write_bool(_bool_context, _bool_after);
      return SaveFailed;
    }
    clear();  // A second press cannot silently redo the operation.
    return Applied;
  }
};

} // namespace smartui
