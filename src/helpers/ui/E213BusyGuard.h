#pragma once

#include <stdint.h>

// Small, Arduino-independent deadline guard used by the pinned e-paper
// driver's virtual wait() methods. Unsigned subtraction keeps elapsed-time
// checks correct across millis() wrap.
class E213BusyGuard {
  bool _active = false;
  bool _timed_out = false;
  uint32_t _operation_started = 0;
  uint32_t _operation_budget = 0;
  uint32_t _wait_budget = 0;
  uint32_t _last_elapsed = 0;

  static bool elapsed(uint32_t now, uint32_t started, uint32_t budget) {
    return budget > 0 && (uint32_t)(now - started) >= budget;
  }

public:
  void begin(uint32_t now, uint32_t operation_budget, uint32_t wait_budget) {
    _active = true;
    _timed_out = false;
    _operation_started = now;
    _operation_budget = operation_budget;
    _wait_budget = wait_budget;
    _last_elapsed = 0;
  }

  bool keepWaiting(uint32_t now, uint32_t wait_started) {
    if (!_active || _timed_out) return false;
    if (elapsed(now, _operation_started, _operation_budget) ||
        elapsed(now, wait_started, _wait_budget)) {
      _timed_out = true;
      return false;
    }
    return true;
  }

  bool finish(uint32_t now) {
    if (!_active) return !_timed_out;
    _last_elapsed = (uint32_t)(now - _operation_started);
    if (elapsed(now, _operation_started, _operation_budget)) _timed_out = true;
    _active = false;
    return !_timed_out;
  }

  bool timedOut() const { return _timed_out; }
  uint32_t lastElapsed() const { return _last_elapsed; }
};
