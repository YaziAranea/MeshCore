#pragma once

#include <stdint.h>

namespace mesh {
namespace storage {

// Give a queued command response a bounded chance to leave the application TX
// queue before starting an already-due filesystem transaction. A dirty batch
// gets one grant only: more commands or a stuck client cannot extend the wait.
// Queue drain is not proof of physical delivery or a peer acknowledgement.
class DeferredSaveResponseGate {
  enum State : uint8_t { UNUSED, REQUESTED, WAITING, RELEASED };
  State _state = UNUSED;
  uint32_t _session = 0;
  uint32_t _started = 0;

public:
  void clear() {
    _state = UNUSED;
    _session = 0;
    _started = 0;
  }

  void request(uint32_t session) {
    if (_state != UNUSED) return;
    _state = REQUESTED;
    _session = session;
  }

  bool waiting(uint32_t now, bool pending_tx, uint32_t session,
               uint32_t max_wait_ms) const {
    return _state == WAITING && pending_tx && session == _session &&
           static_cast<uint32_t>(now - _started) < max_wait_ms;
  }

  // Call only when the deferred save itself is due. Starting the budget here
  // covers a reset arriving when the old batch has reached its maximum age.
  bool allowsSave(uint32_t now, bool pending_tx, uint32_t session,
                  uint32_t max_wait_ms) {
    if (_state == UNUSED || _state == RELEASED) return true;
    if (_state == REQUESTED) {
      _state = WAITING;
      _started = now;
    }
    if (waiting(now, pending_tx, session, max_wait_ms)) return false;
    _state = RELEASED;
    return true;
  }
};

}  // namespace storage
}  // namespace mesh
