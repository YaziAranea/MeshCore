#pragma once

#include <stddef.h>
#include <stdint.h>

namespace smartui {

enum class SyncAction : uint8_t {
  Received = 1, Read = 2, Dismiss = 3, Snooze = 4,
  Resume = 5,  // Internal: a stored UI snooze has expired, not an app command.
};

enum SyncState : uint8_t {
  SYNC_RECEIVED = 1, SYNC_READ = 2, SYNC_DISMISSED = 4, SYNC_SNOOZED = 8,
};

enum class SyncResult : uint8_t { Applied, Unchanged, Unknown, Invalid, NotReady };
enum class SyncEventKind : uint8_t {
  Message = 1, Received = 2, Read = 3, Dismissed = 4, Snoozed = 5,
  Resumed = 6, Setting = 7, Connection = 8, Battery = 9, Notification = 10,
};
enum class SyncEventResult : uint8_t { Event, End, Gap, Invalid };

struct SyncRecord {
  uint32_t generation = 0;
  uint32_t revision = 0;
  uint32_t snooze_seconds = 0;
  uint8_t flags = 0;
  uint8_t state = 0;
};

struct SyncEvent {
  uint32_t seq = 0;
  uint32_t generation = 0;
  uint32_t value = 0;
  uint16_t key = 0;  // Stable caller-defined setting key; zero for messages.
  SyncEventKind kind = SyncEventKind::Message;
  uint8_t state = 0;
  uint8_t flags = 0;
};

// Volatile, bounded per-boot state. Transport session resets MUST NOT clear it.
// IDs are (boot(), generation), never a request ID, queue index, or timestamp.
// The caller verifies the boot ID before find/apply and validates UI actions
// before committing a state transition. This class never touches hardware.
class SmartUiSync {
public:
  static constexpr size_t RECORD_CAPACITY = 32;
  static constexpr size_t EVENT_CAPACITY = 32;
  static constexpr uint32_t MAX_SNOOZE_SECONDS = 86400;

  bool begin(uint64_t boot);
  uint64_t boot() const { return _boot; }
  uint32_t revision() const { return _revision; }
  size_t recordCount() const { return _record_count; }
  bool recordAt(size_t index, SyncRecord& record) const;
  bool find(uint32_t generation, SyncRecord& record) const;
  SyncResult noteMessage(uint32_t generation, uint8_t flags);
  SyncResult check(uint32_t generation, SyncAction action, uint32_t value = 0) const;
  SyncResult apply(uint32_t generation, SyncAction action, uint32_t value = 0);
  bool emitSetting(uint16_t key, uint32_t value);
  bool emitState(SyncEventKind kind, uint32_t value, uint16_t key = 0);

  uint32_t oldestEvent() const;
  uint32_t newestEvent() const { return _revision; }
  SyncEventResult eventAfter(uint32_t cursor, SyncEvent& event) const;

private:
  uint64_t _boot = 0;
  uint32_t _revision = 0;
  uint32_t _highest_generation = 0;
  size_t _record_count = 0;
  size_t _event_count = 0;
  size_t _event_head = 0;
  SyncRecord _records[RECORD_CAPACITY] = {};
  SyncEvent _events[EVENT_CAPACITY] = {};

  size_t recordIndex(uint32_t generation) const;
  bool canAppend() const { return _boot != 0 && _revision != UINT32_MAX; }
  void append(SyncEventKind kind, uint32_t generation, uint8_t flags,
              uint8_t state, uint32_t value, uint16_t key = 0);
};

}  // namespace smartui
