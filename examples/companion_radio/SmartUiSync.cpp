#include "SmartUiSync.h"

namespace smartui {

bool SmartUiSync::begin(uint64_t boot) {
  _boot = boot;
  _revision = _highest_generation = 0;
  _record_count = _event_count = _event_head = 0;
  for (auto& record : _records) record = SyncRecord{};
  for (auto& event : _events) event = SyncEvent{};
  return boot != 0;
}

size_t SmartUiSync::recordIndex(uint32_t generation) const {
  if (generation != 0)
    for (size_t i = 0; i < _record_count; ++i)
      if (_records[i].generation == generation) return i;
  return _record_count;
}

bool SmartUiSync::recordAt(size_t index, SyncRecord& record) const {
  if (index >= _record_count) return false;
  record = _records[index];
  return true;
}

bool SmartUiSync::find(uint32_t generation, SyncRecord& record) const {
  return recordAt(recordIndex(generation), record);
}

void SmartUiSync::append(SyncEventKind kind, uint32_t generation, uint8_t flags,
                          uint8_t state, uint32_t value, uint16_t key) {
  // Every caller checks capacity/sequence exhaustion before changing state.
  SyncEvent& event = _events[_event_head];
  event.seq = ++_revision;
  event.generation = generation;
  event.kind = kind;
  event.flags = flags;
  event.state = state;
  event.value = value;
  event.key = key;
  _event_head = (_event_head + 1) % EVENT_CAPACITY;
  if (_event_count < EVENT_CAPACITY) ++_event_count;
}

SyncResult SmartUiSync::noteMessage(uint32_t generation, uint8_t flags) {
  if (_boot == 0) return SyncResult::NotReady;
  if (generation == 0 || (flags & ~uint8_t(7)) != 0) return SyncResult::Invalid;
  const size_t existing = recordIndex(generation);
  if (existing != _record_count)
    return _records[existing].flags == flags ? SyncResult::Unchanged : SyncResult::Invalid;
  // An evicted generation cannot resurrect an already-read notification.
  if (generation <= _highest_generation) return SyncResult::Unknown;
  if (!canAppend()) return SyncResult::NotReady;
  if (_record_count == RECORD_CAPACITY) {
    for (size_t i = 1; i < _record_count; ++i) _records[i - 1] = _records[i];
    --_record_count;
  }
  SyncRecord& record = _records[_record_count++];
  record = SyncRecord{};
  record.generation = generation;
  record.flags = flags;
  _highest_generation = generation;
  append(SyncEventKind::Message, generation, flags, 0, 0);
  record.revision = _revision;
  return SyncResult::Applied;
}

SyncResult SmartUiSync::check(uint32_t generation, SyncAction action, uint32_t value) const {
  if (_boot == 0) return SyncResult::NotReady;
  if (generation == 0) return SyncResult::Invalid;
  if (action != SyncAction::Received && action != SyncAction::Read &&
      action != SyncAction::Dismiss && action != SyncAction::Snooze &&
      action != SyncAction::Resume) return SyncResult::Invalid;
  if (action == SyncAction::Snooze) {
    if (value == 0 || value > MAX_SNOOZE_SECONDS) return SyncResult::Invalid;
  } else if (value != 0) return SyncResult::Invalid;
  const size_t index = recordIndex(generation);
  if (index == _record_count) return SyncResult::Unknown;
  const uint8_t state = _records[index].state;
  if ((action == SyncAction::Received && (state & SYNC_RECEIVED)) ||
      (action == SyncAction::Read && (state & SYNC_READ)) ||
      (action == SyncAction::Dismiss && (state & SYNC_DISMISSED)) ||
      (action == SyncAction::Snooze && (state & SYNC_SNOOZED) &&
       _records[index].snooze_seconds == value) ||
      (action == SyncAction::Resume && !(state & SYNC_SNOOZED))) return SyncResult::Unchanged;
  if (action == SyncAction::Snooze && (state & SYNC_READ))
    return SyncResult::Invalid;
  return canAppend() ? SyncResult::Applied : SyncResult::NotReady;
}

SyncResult SmartUiSync::apply(uint32_t generation, SyncAction action, uint32_t value) {
  const SyncResult result = check(generation, action, value);
  if (result != SyncResult::Applied) return result;
  SyncRecord& record = _records[recordIndex(generation)];
  SyncEventKind kind;
  switch (action) {
    case SyncAction::Received:
      record.state |= SYNC_RECEIVED;
      kind = SyncEventKind::Received;
      break;
    case SyncAction::Read:
      record.state = (record.state | SYNC_READ) & ~SYNC_SNOOZED;
      record.snooze_seconds = 0;
      kind = SyncEventKind::Read;
      break;
    case SyncAction::Dismiss:
      record.state = (record.state | SYNC_DISMISSED) & ~SYNC_SNOOZED;
      record.snooze_seconds = 0;
      kind = SyncEventKind::Dismissed;
      break;
    case SyncAction::Snooze:
      record.state = (record.state | SYNC_SNOOZED) & ~SYNC_DISMISSED;
      record.snooze_seconds = value;
      kind = SyncEventKind::Snoozed;
      break;
    case SyncAction::Resume:
      record.state &= ~SYNC_SNOOZED;
      record.snooze_seconds = 0;
      kind = SyncEventKind::Resumed;
      break;
    default: return SyncResult::Invalid;
  }
  append(kind, generation, record.flags, record.state, value);
  record.revision = _revision;
  return SyncResult::Applied;
}

bool SmartUiSync::emitSetting(uint16_t key, uint32_t value) {
  if (key == 0) return false;
  return emitState(SyncEventKind::Setting, value, key);
}

bool SmartUiSync::emitState(SyncEventKind kind, uint32_t value, uint16_t key) {
  if (!canAppend() || (kind != SyncEventKind::Setting && kind != SyncEventKind::Connection &&
      kind != SyncEventKind::Battery && kind != SyncEventKind::Notification)) return false;
  append(kind, 0, 0, 0, value, key);
  return true;
}

uint32_t SmartUiSync::oldestEvent() const {
  if (_event_count == 0) return 0;
  return _events[(_event_head + EVENT_CAPACITY - _event_count) % EVENT_CAPACITY].seq;
}

SyncEventResult SmartUiSync::eventAfter(uint32_t cursor, SyncEvent& event) const {
  if (_boot == 0 || cursor > _revision) return SyncEventResult::Invalid;
  if (cursor == _revision) return SyncEventResult::End;
  const uint32_t oldest = oldestEvent();
  if (oldest != 0 && cursor < oldest - 1) return SyncEventResult::Gap;
  const size_t first = (_event_head + EVENT_CAPACITY - _event_count) % EVENT_CAPACITY;
  const size_t offset = static_cast<size_t>(cursor + 1 - oldest);
  if (offset >= _event_count) return SyncEventResult::Invalid;
  event = _events[(first + offset) % EVENT_CAPACITY];
  return SyncEventResult::Event;
}

}  // namespace smartui
