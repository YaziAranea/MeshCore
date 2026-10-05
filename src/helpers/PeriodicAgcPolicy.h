#pragma once

#include <stdint.h>

namespace smartui {

// Scheduling only: never infer a fault from a quiet channel or an RSSI value.
// Future deadlines are not immediate work and must not keep the MCU awake.
class PeriodicAgcPolicy {
  bool _enabled = false;
  bool _reply_guard = false;
  uint32_t _last_attempt = 0;
  uint32_t _reply_until = 0;

public:
  static constexpr uint32_t INTERVAL_MS = 60000;

  void setEnabled(bool enabled, uint32_t now) {
    if (enabled && !_enabled) _last_attempt = now;
    _enabled = enabled;
  }

  void deferForReply(uint32_t now, uint32_t duration_ms) {
    // Bound signed deadline arithmetic even for an invalid external duration.
    if (duration_ms > 0x7fffffffU) duration_ms = 0x7fffffffU;
    if (duration_ms == 0) return;
    const uint32_t deadline = now + duration_ms;
    if (!_reply_guard || static_cast<int32_t>(now - _reply_until) >= 0 ||
        duration_ms > static_cast<uint32_t>(_reply_until - now)) {
      _reply_until = deadline;
    }
    _reply_guard = true;
  }

  bool ready(uint32_t now, bool traffic_pending) {
    if (_reply_guard && static_cast<int32_t>(now - _reply_until) >= 0) {
      _reply_guard = false;
    }
    return _enabled && !traffic_pending && !_reply_guard &&
           static_cast<uint32_t>(now - _last_attempt) >= INTERVAL_MS;
  }

  // Count accepted attempts, including failed hardware attempts, so a fault
  // cannot turn optional maintenance into an endless busy retry loop.
  void attempted(uint32_t now) { _last_attempt = now; }
};

}  // namespace smartui
