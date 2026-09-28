#pragma once

#include <stddef.h>

// Fixed-storage FIFO. The owner must serialize every operation, including
// size()/clear(), with the same lock that protects its session state. Payload
// copies are part of that operation; an atomic length alone is insufficient.
template <typename Frame, size_t Capacity>
class BoundedFrameQueue {
  static_assert(Capacity > 0, "A frame queue needs storage");
  Frame _frames[Capacity];
  size_t _head = 0;
  size_t _size = 0;

public:
  size_t size() const { return _size; }
  void clear() { _head = 0; _size = 0; }

  bool push(const Frame& frame) {
    if (_size == Capacity) return false;
    _frames[(_head + _size) % Capacity] = frame;
    ++_size;
    return true;
  }

  bool peek(Frame& frame) const {
    if (_size == 0) return false;
    frame = _frames[_head];
    return true;
  }

  bool discard() {
    if (_size == 0) return false;
    _head = (_head + 1) % Capacity;
    --_size;
    return true;
  }

  bool pop(Frame& frame) {
    if (!peek(frame)) return false;
    return discard();
  }
};
