#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

// Boundary injection only; production code is compiled separately unchanged.
#define private public
#include "SmartUiSync.h"
#undef private

using namespace smartui;
static unsigned checks = 0;
#define CHECK(value) do { ++checks; assert(value); } while (0)

struct Guarded {
  uint64_t before = UINT64_C(0x38164e92c701abcd);
  SmartUiSync sync;
  uint64_t after = UINT64_C(0x8943af21b630efcd);
  void check() const {
    CHECK(before == UINT64_C(0x38164e92c701abcd));
    CHECK(after == UINT64_C(0x8943af21b630efcd));
  }
};

static void transitions() {
  Guarded guarded;
  auto& sync = guarded.sync;
  SyncEvent event;
  SyncRecord record;
  CHECK(sync.noteMessage(1, 1) == SyncResult::NotReady);
  CHECK(sync.apply(1, SyncAction::Read) == SyncResult::NotReady);
  CHECK(!sync.begin(0));
  CHECK(sync.eventAfter(0, event) == SyncEventResult::Invalid);
  CHECK(sync.begin(UINT64_C(0x3141592653589793)));
  CHECK(sync.boot() == UINT64_C(0x3141592653589793));
  CHECK(sync.recordCount() == 0 && sync.revision() == 0);
  CHECK(sync.eventAfter(0, event) == SyncEventResult::End);
  CHECK(sync.eventAfter(1, event) == SyncEventResult::Invalid);
  CHECK(sync.noteMessage(0, 1) == SyncResult::Invalid);
  CHECK(sync.noteMessage(1, 128) == SyncResult::Invalid);
  CHECK(sync.noteMessage(1, 1) == SyncResult::Applied);
  CHECK(sync.noteMessage(1, 1) == SyncResult::Unchanged);
  CHECK(sync.noteMessage(1, 2) == SyncResult::Invalid);
  CHECK(sync.revision() == 1 && sync.recordCount() == 1);
  CHECK(sync.find(1, record) && record.state == 0 && record.flags == 1 && record.revision == 1);
  CHECK(sync.eventAfter(0, event) == SyncEventResult::Event);
  CHECK(event.seq == 1 && event.generation == 1 && event.kind == SyncEventKind::Message);
  CHECK(sync.apply(1, SyncAction::Received) == SyncResult::Applied);
  CHECK(sync.find(1, record) && record.state == SYNC_RECEIVED);
  CHECK(sync.apply(1, SyncAction::Received) == SyncResult::Unchanged);
  CHECK(sync.apply(1, SyncAction::Read, 1) == SyncResult::Invalid);
  CHECK(sync.apply(1, SyncAction::Snooze, 0) == SyncResult::Invalid);
  CHECK(sync.apply(1, SyncAction::Snooze, 86401) == SyncResult::Invalid);
  CHECK(sync.apply(1, SyncAction::Snooze, UINT32_MAX) == SyncResult::Invalid);
  CHECK(sync.apply(1, static_cast<SyncAction>(99)) == SyncResult::Invalid);
  CHECK(sync.apply(7, SyncAction::Read) == SyncResult::Unknown);
  CHECK(sync.apply(0, SyncAction::Read) == SyncResult::Invalid);
  CHECK(sync.revision() == 2);
  CHECK(sync.apply(1, SyncAction::Snooze, 900) == SyncResult::Applied);
  CHECK(sync.find(1, record) && record.state == (SYNC_RECEIVED | SYNC_SNOOZED));
  CHECK(record.snooze_seconds == 900);
  const uint32_t snoozed_revision = sync.revision();
  CHECK(sync.check(1, SyncAction::Snooze, 900) == SyncResult::Unchanged);
  CHECK(sync.apply(1, SyncAction::Snooze, 900) == SyncResult::Unchanged);
  CHECK(sync.revision() == snoozed_revision);
  CHECK(sync.apply(1, SyncAction::Snooze, 600) == SyncResult::Applied);
  CHECK(sync.apply(1, SyncAction::Dismiss) == SyncResult::Applied);
  CHECK(sync.find(1, record) && record.state == (SYNC_RECEIVED | SYNC_DISMISSED));
  CHECK(record.snooze_seconds == 0);
  CHECK(sync.apply(1, SyncAction::Dismiss) == SyncResult::Unchanged);
  CHECK(sync.apply(1, SyncAction::Snooze, 900) == SyncResult::Applied);
  CHECK(sync.find(1, record) && record.state == (SYNC_RECEIVED | SYNC_SNOOZED));
  CHECK(sync.apply(1, SyncAction::Resume) == SyncResult::Applied);
  CHECK(sync.find(1, record) && record.state == SYNC_RECEIVED && record.snooze_seconds == 0);
  CHECK(sync.apply(1, SyncAction::Resume) == SyncResult::Unchanged);
  CHECK(sync.apply(1, SyncAction::Snooze, 1) == SyncResult::Applied);
  CHECK(sync.apply(1, SyncAction::Read) == SyncResult::Applied);
  CHECK(sync.find(1, record) && record.state == (SYNC_RECEIVED | SYNC_READ));
  CHECK(record.snooze_seconds == 0);
  CHECK(sync.apply(1, SyncAction::Snooze, 900) == SyncResult::Invalid);
  CHECK(sync.apply(1, SyncAction::Read) == SyncResult::Unchanged);
  CHECK(sync.apply(1, SyncAction::Received) == SyncResult::Unchanged);
  CHECK(sync.noteMessage(2, 2) == SyncResult::Applied);
  CHECK(sync.apply(1, SyncAction::Read) == SyncResult::Unchanged);
  CHECK(sync.find(2, record) && record.state == 0);  // Old read never acknowledges B.
  CHECK(sync.noteMessage(3, 0) == SyncResult::Applied);  // Non-important records retain identity.
  CHECK(!sync.emitSetting(0, 123));
  CHECK(sync.emitSetting(5, 123));
  CHECK(sync.eventAfter(sync.revision() - 1, event) == SyncEventResult::Event);
  CHECK(event.kind == SyncEventKind::Setting && event.key == 5 && event.value == 123 && event.generation == 0);
  CHECK(sync.emitState(SyncEventKind::Connection, 2));
  CHECK(sync.emitState(SyncEventKind::Battery, 4000));
  CHECK(sync.emitState(SyncEventKind::Notification, 1));
  const uint32_t revision = sync.revision();
  CHECK(!sync.emitState(SyncEventKind::Read, 1));
  CHECK(!sync.emitState(static_cast<SyncEventKind>(99), 1));
  CHECK(sync.revision() == revision);
  guarded.check();
}

static void bounds() {
  Guarded guarded;
  auto& sync = guarded.sync;
  CHECK(sync.begin(1));
  SyncRecord record;
  SyncEvent event;
  for (uint32_t generation = 1; generation <= 10000; ++generation) {
    CHECK(sync.noteMessage(generation, generation % 8) == SyncResult::Applied);
    CHECK(sync.apply(generation, SyncAction::Received) == SyncResult::Applied);
    CHECK(sync.apply(generation, SyncAction::Snooze, 86400) == SyncResult::Applied);
    CHECK(sync.apply(generation, SyncAction::Read) == SyncResult::Applied);
    CHECK(sync.recordCount() <= SmartUiSync::RECORD_CAPACITY);
    CHECK(sync.newestEvent() == generation * 4);
    uint32_t last_generation = 0;
    for (size_t i = 0; i < sync.recordCount(); ++i) {
      CHECK(sync.recordAt(i, record));
      CHECK(record.generation > last_generation);
      CHECK(record.state == (SYNC_RECEIVED | SYNC_READ));
      CHECK(record.snooze_seconds == 0 && record.revision <= sync.revision());
      last_generation = record.generation;
    }
    CHECK(!sync.recordAt(sync.recordCount(), record));
    CHECK(!sync.recordAt(SIZE_MAX, record));
    CHECK(!sync.find(0, record));
    CHECK(sync.eventAfter(sync.newestEvent(), event) == SyncEventResult::End);
    CHECK(sync.eventAfter(sync.newestEvent() + 1, event) == SyncEventResult::Invalid);
    const uint32_t oldest = sync.oldestEvent();
    CHECK(sync.eventAfter(oldest - 1, event) == SyncEventResult::Event && event.seq == oldest);
    if (oldest > 1) CHECK(sync.eventAfter(oldest - 2, event) == SyncEventResult::Gap);
    for (uint32_t cursor = oldest - 1; cursor < sync.newestEvent(); ++cursor) {
      CHECK(sync.eventAfter(cursor, event) == SyncEventResult::Event);
      CHECK(event.seq == cursor + 1 && event.generation != 0);
    }
    if (generation > SmartUiSync::RECORD_CAPACITY) {
      const uint32_t gone = generation - SmartUiSync::RECORD_CAPACITY;
      CHECK(!sync.find(gone, record));
      CHECK(sync.apply(gone, SyncAction::Read) == SyncResult::Unknown);
      CHECK(sync.noteMessage(gone, 1) == SyncResult::Unknown);
    }
    guarded.check();
  }
  CHECK(sync.recordAt(0, record) && record.generation == 9969);
  CHECK(sync.begin(2));
  CHECK(sync.recordCount() == 0 && sync.revision() == 0 && sync.boot() == 2);
  CHECK(!sync.find(10000, record));
  CHECK(sync.apply(10000, SyncAction::Read) == SyncResult::Unknown);
  CHECK(sync.noteMessage(1, 1) == SyncResult::Applied);
  CHECK(sync.find(1, record) && record.state == 0);  // Reboot gets a new namespace.
  guarded.check();
}

static void exhaustion() {
  SmartUiSync sync;
  CHECK(sync.begin(3));
  CHECK(sync.noteMessage(UINT32_MAX, 1) == SyncResult::Applied);
  CHECK(sync.noteMessage(1, 1) == SyncResult::Unknown);
  CHECK(sync.apply(UINT32_MAX, SyncAction::Read) == SyncResult::Applied);
  sync._revision = UINT32_MAX - 1;  // Simulate multi-year event exhaustion.
  CHECK(sync.emitState(SyncEventKind::Battery, 3900));
  CHECK(sync.revision() == UINT32_MAX);
  CHECK(sync.apply(UINT32_MAX, SyncAction::Read) == SyncResult::Unchanged);
  CHECK(sync.apply(UINT32_MAX, SyncAction::Received) == SyncResult::NotReady);
  CHECK(!sync.emitState(SyncEventKind::Battery, 3899));
  CHECK(sync.revision() == UINT32_MAX);
  SyncEvent event;
  CHECK(sync.eventAfter(UINT32_MAX, event) == SyncEventResult::End);
}

int main() {
  static_assert(sizeof(SmartUiSync) <= 2048, "Sync journal exceeded the fixed RAM budget");
  transitions();
  bounds();
  exhaustion();
  printf("PASS %u production SmartUiSync state/event/bounds assertions (%zu bytes state)\n",
         checks, sizeof(SmartUiSync));
}
