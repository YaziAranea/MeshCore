#include "SmartUiSyncApi.h"
#include <stdio.h>
#include <string.h>

namespace smartui {
namespace {
bool decimal(const char* text, uint32_t& value) {
  if (!text || !*text) return false;
  value = 0;
  for (; *text; ++text) {
    if (*text < '0' || *text > '9' || value > (UINT32_MAX - uint32_t(*text - '0')) / 10) return false;
    value = value * 10 + uint32_t(*text - '0');
  }
  return true;
}
bool hexadecimal(const char* text, size_t digits, uint64_t& value) {
  if (!text || strlen(text) != digits) return false;
  value = 0;
  for (size_t i = 0; i < digits; ++i) {
    char c = text[i];
    const unsigned n = c >= '0' && c <= '9' ? unsigned(c - '0') :
        c >= 'a' && c <= 'f' ? unsigned(c - 'a' + 10) :
        c >= 'A' && c <= 'F' ? unsigned(c - 'A' + 10) : 16;
    if (n > 15) return false;
    value = (value << 4) | n;
  }
  return true;
}
void bootText(uint64_t value, char (&out)[17]) {
  snprintf(out, sizeof(out), "%08lx%08lx", (unsigned long)(uint32_t)(value >> 32),
           (unsigned long)(uint32_t)value);
}
}

void SmartUiSyncApi::resetSession() {
  _enabled = false;
  _subscriptions = 0;
  if (_hooks.policy) _hooks.policy(false);
}

bool SmartUiSyncApi::handle(const char* command, char* reply, size_t capacity, bool writable) {
  if (!command || (strncmp(command, "api sync", 8) != 0 &&
      strncmp(command, "api inbox", 9) != 0 && strncmp(command, "api events", 10) != 0)) return false;
  if (!reply || !capacity) return true;
  auto error = [&](const char* text) { snprintf(reply, capacity, "ERR api %s", text); };
  if (capacity < 480) { error("buffer"); return true; }
  if (!_state || !_state->boot()) { error("unavailable"); return true; }
  if (strlen(command) > 152) { error("invalid"); return true; }
  char input[153]; strcpy(input, command);
  char* tokens[7] = {};
  size_t count = 0;
  char* start = input;
  for (char* p = input;; ++p) {
    if (*p != ' ' && *p != 0) continue;
    const bool last = *p == 0;
    if (p == start || count == 7) { error("invalid"); return true; }
    tokens[count++] = start;
    *p = 0;
    start = p + 1;
    if (last) break;
  }
  if (count < 3 || strcmp(tokens[0], "api")) { error("invalid"); return true; }
  char boot[17]; bootText(_state->boot(), boot);
  const char* family = tokens[1];
  const char* verb = tokens[2];
  if (!strcmp(family, "sync") && count == 3) {
    if (!strcmp(verb, "enable") || !strcmp(verb, "disable")) {
      if (!writable) { error("readonly"); return true; }
      _enabled = !strcmp(verb, "enable");
      if (!_enabled) _subscriptions = 0;
      if (_hooks.policy) _hooks.policy(_enabled);
    } else if (strcmp(verb, "status")) { error("invalid"); return true; }
    snprintf(reply, capacity, "OK api sync boot=%s explicit=%u subscribed=%u cursor=%lu oldest=%lu revision=%lu count=%u capacity=32",
        boot, _enabled, _subscriptions, (unsigned long)_state->newestEvent(),
        (unsigned long)_state->oldestEvent(), (unsigned long)_state->revision(), (unsigned)_state->recordCount());
    return true;
  }
  if (!strcmp(family, "events") && !strcmp(verb, "subscribe") && count == 4) {
    uint32_t mask;
    if (!decimal(tokens[3], mask) || mask > 15) { error("range"); return true; }
    _subscriptions = (uint8_t)mask;
    snprintf(reply, capacity, "OK api events subscribed=%u boot=%s cursor=%lu", _subscriptions, boot,
             (unsigned long)_state->newestEvent());
    return true;
  }
  if (!strcmp(family, "inbox") && !strcmp(verb, "snapshot") && count == 3) {
    snprintf(reply, capacity, "OK api inbox snapshot boot=%s revision=%lu count=%u cursor=%lu capacity=32",
        boot, (unsigned long)_state->revision(), (unsigned)_state->recordCount(), (unsigned long)_state->newestEvent());
    return true;
  }
  if (!strcmp(family, "inbox") && !strcmp(verb, "next") && count == 3) {
    if (!_enabled) { error("negotiate"); return true; }
    uint8_t frame[176] = {}, flags = 0;
    uint32_t generation = 0;
    const int length = _hooks.peek ? _hooks.peek(frame, generation, flags) : 0;
    if (length == 0) { snprintf(reply, capacity, "OK api inbox empty=1 boot=%s", boot); return true; }
    if (length < 0 || length > 176 || !generation) { error("unavailable"); return true; }
    size_t position = snprintf(reply, capacity, "OK api inbox next boot=%s id=%08lx flags=%u frame_hex=",
                               boot, (unsigned long)generation, flags);
    static const char hex[] = "0123456789abcdef";
    if (position + 2 * size_t(length) >= capacity) { error("buffer"); return true; }
    for (int i = 0; i < length; ++i) {
      reply[position++] = hex[frame[i] >> 4]; reply[position++] = hex[frame[i] & 15];
    }
    reply[position] = 0;
    return true;
  }
  uint64_t requested_boot = 0;
  if (count < 5 || !hexadecimal(tokens[3], 16, requested_boot)) { error("invalid"); return true; }
  if (requested_boot != _state->boot()) {
    snprintf(reply, capacity, "ERR api boot boot=%s", boot); return true;
  }
  if (!strcmp(family, "events") && !strcmp(verb, "next") && count == 5) {
    uint32_t cursor;
    if (!decimal(tokens[4], cursor)) { error("invalid"); return true; }
    SyncEvent event;
    switch (_state->eventAfter(cursor, event)) {
      case SyncEventResult::Gap:
        snprintf(reply, capacity, "ERR api gap boot=%s oldest=%lu cursor=%lu", boot,
                 (unsigned long)_state->oldestEvent(), (unsigned long)_state->newestEvent()); break;
      case SyncEventResult::Invalid: error("range"); break;
      case SyncEventResult::End:
        snprintf(reply, capacity, "OK api events end=1 boot=%s cursor=%lu", boot, (unsigned long)_state->newestEvent()); break;
      case SyncEventResult::Event:
        snprintf(reply, capacity, "OK api event boot=%s seq=%lu id=%08lx kind=%u state=%u flags=%u value=%lu key=%u",
            boot, (unsigned long)event.seq, (unsigned long)event.generation, (unsigned)event.kind,
            event.state, event.flags, (unsigned long)event.value, event.key); break;
    }
    return true;
  }
  if (!strcmp(family, "inbox") && !strcmp(verb, "item") && count == 6) {
    uint32_t revision, index;
    if (!decimal(tokens[4], revision) || !decimal(tokens[5], index)) { error("invalid"); return true; }
    if (revision != _state->revision()) { error("changed"); return true; }
    SyncRecord record;
    if (!_state->recordAt(index, record)) { error("range"); return true; }
    snprintf(reply, capacity, "OK api inbox item boot=%s revision=%lu index=%lu id=%08lx flags=%u state=%u snooze=%lu snoozable=%u",
        boot, (unsigned long)revision, (unsigned long)index, (unsigned long)record.generation,
        record.flags, record.state, (unsigned long)record.snooze_seconds,
        _hooks.canSnooze && _hooks.canSnooze(record.generation) ? 1U : 0U);
    return true;
  }
  SyncAction action;
  if (strcmp(family, "inbox")) { error("invalid"); return true; }
  if (!strcmp(verb, "received")) action = SyncAction::Received;
  else if (!strcmp(verb, "read")) action = SyncAction::Read;
  else if (!strcmp(verb, "dismiss")) action = SyncAction::Dismiss;
  else if (!strcmp(verb, "snooze")) action = SyncAction::Snooze;
  else { error("invalid"); return true; }
  uint64_t id;
  uint32_t seconds = 0;
  if (count != (action == SyncAction::Snooze ? 6U : 5U) || !hexadecimal(tokens[4], 8, id) || !id ||
      (action == SyncAction::Snooze && (!decimal(tokens[5], seconds) || !seconds || seconds > 86400))) {
    error("invalid"); return true;
  }
  if (!_enabled) { error("negotiate"); return true; }
  if (!writable) { error("readonly"); return true; }
  const uint32_t generation = (uint32_t)id;
  SyncResult result = _state->check(generation, action, seconds);
  bool queue_removed = false;
  if (action == SyncAction::Received) {
    // A queued frame can outlive the bounded metadata journal. Accept its
    // exact receipt without recreating unread state or removing another ID.
    if (result == SyncResult::NotReady) { error("unavailable"); return true; }
    if (!_hooks.receive) { error("unsupported"); return true; }
    queue_removed = _hooks.receive(generation);
    if (result == SyncResult::Unknown && queue_removed) {
      snprintf(reply, capacity, "OK api inbox received id=%08lx state=1 changed=1 tracked=0", (unsigned long)generation);
      return true;
    }
  }
  if (result == SyncResult::Unknown) { error("gone"); return true; }
  if (result == SyncResult::Invalid) { error("invalid"); return true; }
  if (result == SyncResult::NotReady) { error("unavailable"); return true; }
  if (result == SyncResult::Applied) {
    if (action != SyncAction::Received &&
        (!_hooks.action || !_hooks.action(generation, action, seconds))) { error("unsupported"); return true; }
    result = _state->apply(generation, action, seconds);
  }
  SyncRecord record;
  if (!_state->find(generation, record)) { error("gone"); return true; }
  snprintf(reply, capacity, "OK api inbox %s id=%08lx state=%u changed=%u", verb,
           (unsigned long)generation, record.state, result == SyncResult::Applied || queue_removed ? 1U : 0U);
  return true;
}
}  // namespace smartui
