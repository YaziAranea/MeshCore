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

public:
  DeferredSavePolicy() : _pending(false), _first_dirty(0), _deadline(0) {}

  bool pending() const { return _pending; }

  void schedule(uint32_t now, uint32_t delay_ms) {
    if (!_pending) {
      _pending = true;
      _first_dirty = now;
    }
    _deadline = now + delay_ms;
  }

  bool due(uint32_t now, uint32_t max_dirty_age_ms) const {
    if (!_pending) return false;
    const bool deadline_reached = static_cast<int32_t>(now - _deadline) >= 0;
    const bool maximum_age_reached =
        static_cast<uint32_t>(now - _first_dirty) >= max_dirty_age_ms;
    return deadline_reached || maximum_age_reached;
  }

  void retryFrom(uint32_t now, uint32_t delay_ms) {
    _pending = true;
    _first_dirty = now;
    _deadline = now + delay_ms;
  }

  void clear() {
    _pending = false;
    _first_dirty = 0;
    _deadline = 0;
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
