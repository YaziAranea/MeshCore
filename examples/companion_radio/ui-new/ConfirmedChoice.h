#pragma once

#include <stddef.h>
#include <stdint.h>

namespace smartui {

// A draft selection only: browsing never changes preferences or hardware.
// The final row (index == count()) is always Cancel, not a sentinel value.
class ConfirmedChoice {
public:
  static constexpr uint8_t CAPACITY = 32;

private:
  int16_t _values[CAPACITY] = {};
  uint8_t _count = 0;
  uint8_t _cursor = 0;

public:
  uint8_t count() const { return _count; }
  uint8_t cursor() const { return _cursor; }

  // Callers should iterate only [0, count()); invalid indices are harmless.
  int16_t value(size_t index) const { return index < _count ? _values[index] : 0; }

  void reset() {
    _count = 0;
    _cursor = 0;
  }

  bool add(int16_t value) {
    if (_count == CAPACITY) return false;
    const bool was_cancel = _cursor == _count;
    _values[_count++] = value;
    if (was_cancel) _cursor = _count;
    return true;
  }

  void begin(int16_t active_value) {
    _cursor = _count;
    for (uint8_t index = 0; index < _count; ++index) {
      if (_values[index] == active_value) {
        _cursor = index;
        break;
      }
    }
  }

  void move(int direction) {
    const int rows = _count + 1;
    // Reduce first so even INT_MIN/INT_MAX cannot overflow the addition.
    const int next = _cursor + direction % rows;
    _cursor = static_cast<uint8_t>((next + rows) % rows);
  }

  bool selected(int16_t& out) const {
    if (_cursor >= _count) return false;
    out = _values[_cursor];
    return true;
  }
};

} // namespace smartui
