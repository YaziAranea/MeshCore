#pragma once

#include <new>

namespace smartui {

// Full preferences include bounded text overrides. Nested UI handlers must
// not copy that object onto the small nRF loop stack. Allocate only for an
// actual mutation, and require the caller to abort before changing anything
// when allocation fails. A null source intentionally performs no allocation.
template <typename T> class CheckedUiSnapshot {
  T* _value;
public:
  explicit CheckedUiSnapshot(const T* source)
      : _value(source != nullptr ? new (std::nothrow) T(*source) : nullptr) {}
  ~CheckedUiSnapshot() { delete _value; }
  CheckedUiSnapshot(const CheckedUiSnapshot&) = delete;
  CheckedUiSnapshot& operator=(const CheckedUiSnapshot&) = delete;
  explicit operator bool() const { return _value != nullptr; }
  const T* get() const { return _value; }
  const T& operator*() const { return *_value; }
};

} // namespace smartui
