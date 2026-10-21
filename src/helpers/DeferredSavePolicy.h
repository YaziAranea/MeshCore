#pragma once

#include <stdint.h>

namespace mesh {
namespace storage {

// Tracks delayed persistence separately from work which must run immediately.
// All arithmetic is wrap-safe for delays shorter than 2^31 milliseconds.
class DeferredSavePolicy {
  bool _pending;
  uint32_t _first_dirty;
  uint32_t _deadline;
  uint32_t _retry_delay;

public:
  DeferredSavePolicy()
      : _pending(false), _first_dirty(0), _deadline(0), _retry_delay(0) {}

  bool pending() const { return _pending; }

  void schedule(uint32_t now, uint32_t delay_ms) {
    // New changes join the pending batch without shortening its recovery
    // delay or postponing the next retry indefinitely under steady traffic.
    if (_retry_delay != 0) return;
    if (!_pending) {
      _pending = true;
      _first_dirty = now;
    }
    _deadline = now + delay_ms;
  }

  bool due(uint32_t now, uint32_t max_dirty_age_ms) const {
    if (!_pending) return false;
    const bool deadline_reached = static_cast<int32_t>(now - _deadline) >= 0;
    // The normal coalescing limit must not bypass a longer failure backoff.
    if (_retry_delay != 0) return deadline_reached;
    const bool maximum_age_reached =
        static_cast<uint32_t>(now - _first_dirty) >= max_dirty_age_ms;
    return deadline_reached || maximum_age_reached;
  }

  void retryFrom(uint32_t now, uint32_t initial_delay_ms,
                 uint32_t max_delay_ms) {
    if (_retry_delay == 0) {
      _retry_delay = initial_delay_ms < max_delay_ms
                         ? initial_delay_ms : max_delay_ms;
    } else if (_retry_delay > max_delay_ms / 2) {
      _retry_delay = max_delay_ms;
    } else {
      _retry_delay *= 2;
    }
    _pending = true;
    _deadline = now + _retry_delay;
  }

  void clear() {
    _pending = false;
    _first_dirty = 0;
    _deadline = 0;
    _retry_delay = 0;
  }
};

// A failed destructive storage operation quarantines the filesystem.  Do not
// replay deferred RAM state into a filesystem whose contents are now partial.
template <typename Save>
bool flushDeferredSave(DeferredSavePolicy& policy, bool storage_quarantined,
                       Save save) {
  if (!policy.pending()) return true;
  if (storage_quarantined) return false;
  if (!save()) return false;
  policy.clear();
  return true;
}

}  // namespace storage
}  // namespace mesh
