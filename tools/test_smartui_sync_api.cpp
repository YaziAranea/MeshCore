// Host tests use the production journal, command service and framed router.
#include "SmartUiApi.h"
#include "SmartUiSyncApi.h"
#include <algorithm>
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

using namespace smartui;
static unsigned checks = 0;
#define CHECK(x) do { ++checks; if (!(x)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); std::abort(); } } while (0)
static constexpr uint64_t BOOT = UINT64_C(0x0123456789abcdef);
static const char* BOOT_TEXT = "0123456789abcdef";
static SmartUiSync state;
static SmartUiSyncApi api;
static SmartUiApi router;
struct Frame { uint32_t generation; uint8_t flags; std::vector<uint8_t> bytes; };
static std::vector<Frame> queue;
static unsigned receive_calls, action_calls, policy_calls, peek_calls;
static uint32_t action_generation, action_value, now, snooze_deadline;
static SyncAction action_kind;
static bool policy_enabled, action_allowed, snooze_allowed;
static int peek_mode;

static int peek(uint8_t* out, uint32_t& generation, uint8_t& flags) {
  ++peek_calls;
  if (peek_mode) {
    generation = peek_mode == 3 ? 0 : 1;
    flags = 255;
    return peek_mode == 1 ? -1 : peek_mode == 2 ? 177 : 176;
  }
  if (queue.empty()) return 0;
  const auto& frame = queue.front();
  generation = frame.generation; flags = frame.flags;
  std::memcpy(out, frame.bytes.data(), frame.bytes.size());
  return static_cast<int>(frame.bytes.size());
}
static bool receive(uint32_t generation) {
  ++receive_calls;
  auto found = std::find_if(queue.begin(), queue.end(), [=](const Frame& frame) { return frame.generation == generation; });
  if (found == queue.end()) return false;
  queue.erase(found);
  return true;
}
static bool action(uint32_t generation, SyncAction kind, uint32_t value) {
  ++action_calls;
  action_generation = generation; action_kind = kind; action_value = value;
  if (!action_allowed || (kind == SyncAction::Snooze && !snooze_allowed)) return false;
  if (kind == SyncAction::Snooze) snooze_deadline = now + value * 1000;
  if (kind == SyncAction::Read || kind == SyncAction::Dismiss) snooze_deadline = 0;
  return true;
}
static void policy(bool enabled) { ++policy_calls; policy_enabled = enabled; }
static bool canSnooze(uint32_t) { return snooze_allowed; }
static bool execute(const char* command, char* reply, size_t capacity, bool writable) {
  return api.handle(command, reply, capacity, writable);
}
static SyncApiHooks hooks() {
  SyncApiHooks result;
  result.peek = peek; result.receive = receive; result.action = action;
  result.policy = policy; result.canSnooze = canSnooze;
  return result;
}
static void reset() {
  CHECK(state.begin(BOOT));
  queue.clear(); receive_calls = action_calls = policy_calls = peek_calls = 0;
  action_generation = action_value = snooze_deadline = 0; now = 100;
  policy_enabled = false; action_allowed = snooze_allowed = true; peek_mode = 0;
  api.begin(state, hooks()); router.begin(execute);
  CHECK(!api.enabled() && api.subscriptions() == 0 && !policy_enabled && policy_calls == 1);
}
static std::string call(const std::string& command, bool writable = true) {
  std::array<unsigned char, 514> bytes;
  bytes.fill(0xa7);
  char* reply = reinterpret_cast<char*>(bytes.data() + 17);
  CHECK(api.handle(command.c_str(), reply, 480, writable));
  for (size_t i = 0; i < 17; ++i) CHECK(bytes[i] == 0xa7);
  for (size_t i = 497; i < bytes.size(); ++i) CHECK(bytes[i] == 0xa7);
  CHECK(std::memchr(reply, 0, 480));
  CHECK(std::strlen(reply) < 480);
  return reply;
}
static std::string id(uint32_t value) {
  char text[9]; std::snprintf(text, sizeof(text), "%08lx", static_cast<unsigned long>(value)); return text;
}
static std::string mutation(const char* verb, uint32_t generation, const char* tail = "") {
  return std::string("api inbox ") + verb + " " + BOOT_TEXT + " " + id(generation) + tail;
}
static std::string event(uint32_t cursor) {
  return std::string("api events next ") + BOOT_TEXT + " " + std::to_string(cursor);
}
static std::string item(uint32_t revision, uint32_t index) {
  return std::string("api inbox item ") + BOOT_TEXT + " " + std::to_string(revision) + " " + std::to_string(index);
}
static void note(uint32_t generation, uint8_t flags = 1, size_t length = 3) {
  CHECK(state.noteMessage(generation, flags) == SyncResult::Applied);
  Frame frame {generation, flags, {}};
  for (size_t i = 0; i < length; ++i) frame.bytes.push_back(static_cast<uint8_t>(i));
  queue.push_back(frame);
}
static void enable() { CHECK(call("api sync enable").find("explicit=1") != std::string::npos); }

static void contract() {
  reset();
  char untouched[8] = "same";
  CHECK(!api.handle(nullptr, untouched, sizeof(untouched), true));
  CHECK(!api.handle("api get", untouched, sizeof(untouched), true));
  CHECK(!std::strcmp(untouched, "same"));
  CHECK(call("api sync status") == "OK api sync boot=0123456789abcdef explicit=0 subscribed=0 cursor=0 oldest=0 revision=0 count=0 capacity=32");
  CHECK(call("api inbox snapshot", false) == "OK api inbox snapshot boot=0123456789abcdef revision=0 count=0 cursor=0 capacity=32");
  CHECK(call(event(0), false) == "OK api events end=1 boot=0123456789abcdef cursor=0");
  CHECK(call("api inbox next") == "ERR api negotiate");
  CHECK(call(mutation("read", 1)) == "ERR api negotiate");
  CHECK(call("api sync enable", false) == "ERR api readonly");
  CHECK(!api.enabled() && !policy_enabled && policy_calls == 1);
  CHECK(call("api events subscribe 15", false) == "OK api events subscribed=15 boot=0123456789abcdef cursor=0");
  CHECK(api.subscriptions() == 15 && !api.enabled());
  enable();
  CHECK(policy_enabled && policy_calls == 2);
  CHECK(call("api sync disable", false) == "ERR api readonly");
  CHECK(api.enabled() && api.subscriptions() == 15);
  CHECK(call("api inbox next", false) == "OK api inbox empty=1 boot=0123456789abcdef");
  note(1, 3);
  CHECK(call("api inbox snapshot") == "OK api inbox snapshot boot=0123456789abcdef revision=1 count=1 cursor=1 capacity=32");
  CHECK(call(item(1, 0)) == "OK api inbox item boot=0123456789abcdef revision=1 index=0 id=00000001 flags=3 state=0 snooze=0 snoozable=1");
  snooze_allowed = false;
  CHECK(call(item(1, 0)).find("snoozable=0") != std::string::npos);
  CHECK(call(event(0)) == "OK api event boot=0123456789abcdef seq=1 id=00000001 kind=1 state=0 flags=3 value=0 key=0");
  CHECK(call(event(1)) == "OK api events end=1 boot=0123456789abcdef cursor=1");
  CHECK(call(event(2)) == "ERR api range");
  CHECK(call(item(1, 1)) == "ERR api range");
  CHECK(call(item(0, 0)) == "ERR api changed");
  CHECK(call("api inbox next") == "OK api inbox next boot=0123456789abcdef id=00000001 flags=3 frame_hex=000102");
  CHECK(queue.size() == 1 && receive_calls == 0 && action_calls == 0 && state.revision() == 1);
  CHECK(call("api sync disable").find("explicit=0 subscribed=0") != std::string::npos);
  CHECK(!policy_enabled && !api.subscriptions() && state.recordCount() == 1);
}

static void malformed() {
  reset(); note(1); enable();
  const std::vector<std::string> invalid {
    "api sync", "api sync status ", "api sync  status", "api sync status extra",
    "api sync nope", "api sync\tstatus", "api syncx status", "api inboxx next",
    "api inbox next extra", "api inbox read", "api inbox snapshot x", "api events next",
    "api inbox read 0123456789abcdef 1", "api inbox read 0123456789abcdef 000000001",
    "api inbox read 0123456789abcdef 00000000", "api inbox read 0123456789abcdef 0000000g",
    "api inbox read 0123456789abcde 00000001", "api inbox read 00123456789abcdef 00000001",
    "api inbox read 0123456789abcdeg 00000001", "api inbox read 0123456789abcdef 00000001 x",
    "api inbox resume 0123456789abcdef 00000001", "api inbox snooze 0123456789abcdef 00000001",
    "api inbox snooze 0123456789abcdef 00000001 0", "api inbox snooze 0123456789abcdef 00000001 -1",
    "api inbox snooze 0123456789abcdef 00000001 +1", "api inbox snooze 0123456789abcdef 00000001 1.0",
    "api inbox snooze 0123456789abcdef 00000001 86401", "api inbox snooze 0123456789abcdef 00000001 4294967296",
    "api inbox snooze 0123456789abcdef 00000001 4294967295", "api inbox snooze 0123456789abcdef 00000001 1 extra",
    "api inbox read 0123456789abcdef 00000001 a b c d", "api events next 0123456789abcdef -1",
    "api events next 0123456789abcdef +1", "api events next 0123456789abcdef 4294967296",
    "api inbox item 0123456789abcdef 1 -1", "api inbox item 0123456789abcdef 4294967296 0",
    "api inbox item 0123456789abcdef 1 4294967296", "api inbox item 0123456789abcdef 1 0 extra",
    std::string("api sync ") + std::string(144, 'x'),
  };
  for (const auto& command : invalid) {
    CHECK(call(command) == "ERR api invalid");
    CHECK(state.revision() == 1 && queue.size() == 1 && receive_calls == 0 && action_calls == 0);
  }
  for (const char* value : {"16", "-1", "+1", "4294967295", "4294967296", "x"})
    CHECK(call(std::string("api events subscribe ") + value) == "ERR api range");
  CHECK(call("api inbox read 0123456789abcdee 00000001") == "ERR api boot boot=0123456789abcdef");
  CHECK(call("api inbox read 0000000000000000 00000001") == "ERR api boot boot=0123456789abcdef");
  CHECK(call("api inbox read 0123456789ABCDEF 00000002") == "ERR api gone");
  CHECK(call(event(UINT32_MAX)) == "ERR api range");
  CHECK(call(item(1, UINT32_MAX)) == "ERR api range");
  CHECK(state.revision() == 1 && queue.size() == 1 && action_calls == 0 && receive_calls == 0);
  CHECK(call("api inbox read 0123456789ABCDEF 00000001") == "OK api inbox read id=00000001 state=2 changed=1");
}

static void mutations() {
  reset(); note(1); note(2); enable();
  for (const char* verb : {"received", "read", "dismiss", "snooze"}) {
    CHECK(call(mutation(verb, 1, !std::strcmp(verb, "snooze") ? " 900" : ""), false) == "ERR api readonly");
    CHECK(state.revision() == 2 && queue.size() == 2 && !receive_calls && !action_calls);
  }
  CHECK(call(mutation("received", 2)) == "OK api inbox received id=00000002 state=1 changed=1");
  CHECK(queue.size() == 1 && queue[0].generation == 1 && receive_calls == 1 && action_calls == 0);
  CHECK(call(mutation("received", 2)) == "OK api inbox received id=00000002 state=1 changed=0");
  CHECK(state.revision() == 3 && queue[0].generation == 1);
  CHECK(call(mutation("read", 1)) == "OK api inbox read id=00000001 state=2 changed=1");
  CHECK(queue.size() == 1 && action_calls == 1 && action_generation == 1 && action_kind == SyncAction::Read);
  CHECK(call(mutation("read", 1)) == "OK api inbox read id=00000001 state=2 changed=0");
  CHECK(action_calls == 1 && state.revision() == 4);
  CHECK(call(mutation("snooze", 1, " 900")) == "ERR api invalid");
  CHECK(call(mutation("dismiss", 2)) == "OK api inbox dismiss id=00000002 state=5 changed=1");
  CHECK(call(mutation("dismiss", 2)) == "OK api inbox dismiss id=00000002 state=5 changed=0");
  CHECK(call(mutation("snooze", 2, " 86400")) == "OK api inbox snooze id=00000002 state=9 changed=1");
  CHECK(action_value == 86400 && snooze_deadline == now + 86400000);
  CHECK(call(mutation("received", 1)) == "OK api inbox received id=00000001 state=3 changed=1");
  CHECK(queue.empty());
  CHECK(call(mutation("read", 999)) == "ERR api gone");
  CHECK(call(mutation("received", 999)) == "ERR api gone");
  SyncRecord record;
  CHECK(state.find(2, record) && record.state == (SYNC_RECEIVED | SYNC_SNOOZED));
  const auto revision = state.revision();
  action_allowed = false;
  CHECK(call(mutation("read", 2)) == "ERR api unsupported");
  CHECK(state.revision() == revision && state.find(2, record) && record.state == 9);
  auto missing = hooks(); missing.action = nullptr; missing.receive = nullptr; missing.canSnooze = nullptr;
  api.begin(state, missing); enable();
  CHECK(call(mutation("read", 2)) == "ERR api unsupported");
  CHECK(call(mutation("received", 2)) == "ERR api unsupported");
  CHECK(call(item(revision, 1)).find("snoozable=0") != std::string::npos);
  CHECK(state.revision() == revision);
}

static void boundedJournal() {
  reset(); note(1); note(2); enable();
  for (uint32_t generation = 3; generation <= 34; ++generation)
    CHECK(state.noteMessage(generation, 1) == SyncResult::Applied);
  CHECK(state.recordCount() == 32 && state.oldestEvent() == 3 && state.newestEvent() == 34);
  CHECK(call(event(0)) == "ERR api gap boot=0123456789abcdef oldest=3 cursor=34");
  CHECK(call(event(1)) == "ERR api gap boot=0123456789abcdef oldest=3 cursor=34");
  CHECK(call(event(2)) == "OK api event boot=0123456789abcdef seq=3 id=00000003 kind=1 state=0 flags=1 value=0 key=0");
  CHECK(call(item(34, 0)).find("id=00000003") != std::string::npos);
  CHECK(call(mutation("read", 1)) == "ERR api gone");
  CHECK(queue.size() == 2 && !receive_calls && !action_calls);
  CHECK(call(mutation("received", 1)) == "OK api inbox received id=00000001 state=1 changed=1 tracked=0");
  CHECK(queue.size() == 1 && queue[0].generation == 2 && state.revision() == 34);
  CHECK(call(mutation("received", 1)) == "ERR api gone");
  CHECK(queue.size() == 1 && queue[0].generation == 2 && state.recordCount() == 32);
  CHECK(state.noteMessage(1, 1) == SyncResult::Unknown);
  CHECK(state.emitSetting(65535, UINT32_MAX));
  CHECK(call(item(34, 0)) == "ERR api changed");
  CHECK(call(event(34)) == "OK api event boot=0123456789abcdef seq=35 id=00000000 kind=7 state=0 flags=0 value=4294967295 key=65535");
  CHECK(call(item(35, 31)).find("id=00000022") != std::string::npos);
  CHECK(call(item(35, 32)) == "ERR api range");
  for (const auto kind : {SyncEventKind::Connection, SyncEventKind::Battery, SyncEventKind::Notification}) {
    const auto before = state.newestEvent();
    CHECK(state.emitState(kind, UINT32_MAX));
    CHECK(call(event(before)).find("id=00000000 kind=" + std::to_string(static_cast<unsigned>(kind))) != std::string::npos);
  }
}

static void replyBounds() {
  reset(); note(UINT32_MAX, 7, 176); enable();
  std::string expected = "OK api inbox next boot=0123456789abcdef id=ffffffff flags=7 frame_hex=";
  for (unsigned i = 0; i < 176; ++i) { char hex[3]; std::snprintf(hex, sizeof(hex), "%02x", i); expected += hex; }
  CHECK(call("api inbox next") == expected && expected.size() < 480);
  CHECK(call("api inbox next") == expected && queue.size() == 1 && !receive_calls);
  for (int mode = 1; mode <= 3; ++mode) {
    peek_mode = mode; CHECK(call("api inbox next") == "ERR api unavailable");
  }
  peek_mode = 4;
  CHECK(call("api inbox next") == "OK api inbox next boot=0123456789abcdef id=00000001 flags=255 frame_hex=" + std::string(352, '0'));
  peek_mode = 0;
  const auto revision = state.revision();
  for (size_t capacity = 0; capacity <= 520; ++capacity) {
    std::array<unsigned char, 554> buffer; buffer.fill(0xd3);
    char* reply = reinterpret_cast<char*>(buffer.data() + 17);
    const auto command = capacity < 480 ? mutation("received", UINT32_MAX) : std::string("api inbox next");
    CHECK(api.handle(command.c_str(), reply, capacity, true));
    for (size_t i = 0; i < 17; ++i) CHECK(buffer[i] == 0xd3);
    for (size_t i = 17 + capacity; i < buffer.size(); ++i) CHECK(buffer[i] == 0xd3);
    if (capacity) CHECK(std::memchr(reply, 0, capacity));
    if (capacity >= 480) CHECK(reply == expected);
    CHECK(state.revision() == revision && queue.size() == 1 && !receive_calls && !action_calls);
  }
  CHECK(api.handle(mutation("received", UINT32_MAX).c_str(), nullptr, 480, true));
  CHECK(state.revision() == revision && queue.size() == 1 && !receive_calls);
  SmartUiSyncApi absent;
  char reply[480];
  CHECK(absent.handle("api sync status", reply, sizeof(reply), true));
  CHECK(!std::strcmp(reply, "ERR api unavailable"));
  CHECK(!state.begin(0));
  CHECK(call("api sync status") == "ERR api unavailable");
}

static uint16_t u16(const uint8_t* p) { return p[0] | uint16_t(p[1]) << 8; }
static std::vector<uint8_t> request(uint16_t sequence, const std::string& command) {
  std::vector<uint8_t> result {201, 'S', 'U', 'I', 1, static_cast<uint8_t>(sequence), static_cast<uint8_t>(sequence >> 8), 1};
  result.insert(result.end(), command.begin(), command.end()); return result;
}
struct WireReply { uint8_t status; std::string body; };
static WireReply wire(uint16_t sequence, const std::string& command, bool writable = true) {
  auto input = request(sequence, command);
  std::array<uint8_t, SmartUiApi::MAX_FRAME + 34> buffer; buffer.fill(0xc5);
  auto* out = buffer.data() + 17;
  size_t length = router.handle(input.data(), input.size(), out, SmartUiApi::MAX_FRAME, writable);
  CHECK(length >= 13 && length <= SmartUiApi::MAX_FRAME);
  CHECK(out[0] == 201 && !std::memcmp(out + 1, "SUI", 3) && out[4] == 1 && u16(out + 5) == sequence);
  const uint16_t total = u16(out + 11);
  CHECK(total < SmartUiApi::MAX_REPLY && u16(out + 9) == 0);
  WireReply result {out[8], std::string(reinterpret_cast<char*>(out + 13), length - 13)};
  while (result.body.size() < total) {
    const uint16_t offset = static_cast<uint16_t>(result.body.size());
    uint8_t fetch[] {201, 'S', 'U', 'I', 1, static_cast<uint8_t>(sequence), static_cast<uint8_t>(sequence >> 8), 2,
                     static_cast<uint8_t>(offset), static_cast<uint8_t>(offset >> 8)};
    length = router.handle(fetch, sizeof(fetch), out, SmartUiApi::MAX_FRAME, writable);
    CHECK(length > 13 && length <= SmartUiApi::MAX_FRAME && out[8] == result.status);
    CHECK(u16(out + 9) == offset && u16(out + 11) == total);
    result.body.append(reinterpret_cast<char*>(out + 13), length - 13);
  }
  CHECK(result.body.size() == total);
  for (size_t i = 0; i < 17; ++i) CHECK(buffer[i] == 0xc5 && buffer[17 + SmartUiApi::MAX_FRAME + i] == 0xc5);
  return result;
}

static void sessionsAndReplay() {
  reset(); note(1, 1, 176); note(2);
  CHECK(wire(1, "api sync enable").status == SmartUiApi::OK);
  CHECK(wire(2, "api events subscribe 15").status == SmartUiApi::OK);
  const auto next = wire(3, "api inbox next");
  CHECK(next.status == SmartUiApi::OK && next.body.size() > SmartUiApi::MAX_FRAME && queue.size() == 2 && peek_calls == 1);
  CHECK(wire(3, "api inbox next").body == next.body && peek_calls == 1);
  auto read = wire(4, mutation("snooze", 1, " 900"));
  CHECK(read.status == SmartUiApi::OK && read.body == "OK api inbox snooze id=00000001 state=8 changed=1");
  const auto deadline = snooze_deadline;
  now += 1000;
  CHECK(wire(4, mutation("snooze", 1, " 900")).body == read.body && action_calls == 1 && snooze_deadline == deadline);
  CHECK(wire(4, mutation("read", 2)).status == SmartUiApi::STALE && action_calls == 1);
  CHECK(wire(3, mutation("read", 2)).status == SmartUiApi::STALE && action_calls == 1);
  CHECK(wire(5, mutation("read", 2), false).status == SmartUiApi::DENIED && action_calls == 1);
  CHECK(wire(6, mutation("received", 1)).body == "OK api inbox received id=00000001 state=9 changed=1");
  CHECK(wire(6, mutation("received", 1)).body == "OK api inbox received id=00000001 state=9 changed=1" && receive_calls == 1);
  CHECK(queue.size() == 1 && queue[0].generation == 2);
  const auto revision = state.revision();
  api.resetSession(); router.resetSession();
  CHECK(!policy_enabled && !api.enabled() && api.subscriptions() == 0 && state.revision() == revision);
  CHECK(wire(1, mutation("read", 1)).body == "ERR api negotiate");
  CHECK(wire(2, "api sync enable").status == SmartUiApi::OK);
  CHECK(wire(3, mutation("snooze", 1, " 900")).body == "OK api inbox snooze id=00000001 state=9 changed=0");
  CHECK(action_calls == 1 && snooze_deadline == deadline && state.revision() == revision);
  CHECK(wire(4, mutation("snooze", 1, " 901")).body == "OK api inbox snooze id=00000001 state=9 changed=1");
  CHECK(action_calls == 2 && snooze_deadline == now + 901000);
  CHECK(wire(5, mutation("dismiss", 1)).status == SmartUiApi::OK && snooze_deadline == 0);
  CHECK(wire(6, mutation("snooze", 1, " 901")).body == "OK api inbox snooze id=00000001 state=9 changed=1");
  CHECK(action_calls == 4);
  CHECK(state.begin(BOOT + 1)); note(1);
  api.resetSession(); router.resetSession();
  CHECK(wire(1, "api sync enable").status == SmartUiApi::OK);
  CHECK(wire(2, mutation("read", 1)).body == "ERR api boot boot=0123456789abcdf0");
  CHECK(action_calls == 4 && state.revision() == 1);
}

static void immutablePage() {
  reset(); note(1, 7, 176); enable();
  auto input = request(1, "api inbox next");
  uint8_t out[SmartUiApi::MAX_FRAME];
  size_t length = router.handle(input.data(), input.size(), out, sizeof(out), true);
  CHECK(length == sizeof(out) && out[8] == SmartUiApi::OK);
  const auto total = u16(out + 11);
  std::string first(reinterpret_cast<char*>(out + 13), length - 13);
  const auto expected = call("api inbox next");
  CHECK(receive(1)); note(2, 1, 3); // Change live queue between FETCH pages.
  while (first.size() < total) {
    const auto offset = static_cast<uint16_t>(first.size());
    uint8_t fetch[] {201, 'S', 'U', 'I', 1, 1, 0, 2, static_cast<uint8_t>(offset), static_cast<uint8_t>(offset >> 8)};
    length = router.handle(fetch, sizeof(fetch), out, sizeof(out), true);
    CHECK(out[8] == SmartUiApi::OK && u16(out + 11) == total && u16(out + 9) == offset);
    first.append(reinterpret_cast<char*>(out + 13), length - 13);
  }
  CHECK(first == expected && queue.size() == 1 && queue[0].generation == 2);
  CHECK(wire(1, "api inbox next").body == expected);
  CHECK(wire(2, "api inbox next").body.find("id=00000002") != std::string::npos);
}

int main() {
  contract(); malformed(); mutations(); boundedJournal(); replyBounds(); sessionsAndReplay(); immutablePage();
  std::printf("PASS %u production sync API/router wire, bounds, replay, boot and exact-receipt assertions (selector=%d)\n",
              checks, SMARTUI_CONNECTION_SELECTOR);
}
