#pragma once
#include "SmartUiSync.h"
#include <stddef.h>
#include <stdint.h>

namespace smartui {
struct SyncApiHooks {
  int (*peek)(uint8_t*, uint32_t&, uint8_t&) = nullptr;
  bool (*receive)(uint32_t) = nullptr;
  bool (*action)(uint32_t, SyncAction, uint32_t) = nullptr;
  void (*policy)(bool) = nullptr;
  bool (*canSnooze)(uint32_t) = nullptr;
};

// Text namespace behind the existing bounded/paged SUI v1 envelope.
// Session reset drops only negotiation, never the boot-scoped journal.
class SmartUiSyncApi {
public:
  void begin(SmartUiSync& state, SyncApiHooks hooks) { _state = &state; _hooks = hooks; resetSession(); }
  void resetSession();
  bool enabled() const { return _enabled; }
  uint8_t subscriptions() const { return _subscriptions; }
  bool handle(const char* command, char* reply, size_t capacity, bool writable);
private:
  SmartUiSync* _state = nullptr;
  SyncApiHooks _hooks;
  bool _enabled = false;
  uint8_t _subscriptions = 0;
};
}  // namespace smartui
