#include "SmartUiApi.h"
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

using smartui::SmartUiApi;
static unsigned checks, executions, mutations;
static std::string last_command, next_reply;
static bool last_permission;
static int reply_mode;
static SmartUiApi api;
#define CHECK(x) do { ++checks; assert(x); } while (0)

static bool execute(const char* command, char* reply, size_t capacity, bool allowed) {
  ++executions;
  CHECK(command != nullptr && reply != nullptr && capacity == SmartUiApi::MAX_REPLY);
  CHECK(strlen(command) <= SmartUiApi::MAX_COMMAND);
  last_command = command;
  last_permission = allowed;
  if (allowed && last_command.find("api set ") == 0) ++mutations;
  if (reply_mode == 1) return false;
  if (reply_mode == 2) {
    memset(reply, 'x', capacity);
    memcpy(reply, "OK api ", 7);
    return true;
  }
  if (reply_mode == 3) return true;  // A handled request without a response.
  CHECK(next_reply.size() < capacity);
  memcpy(reply, next_reply.c_str(), next_reply.size() + 1);
  return true;
}

static void fresh(const std::string& reply = "OK api test") {
  executions = mutations = 0;
  last_command.clear();
  last_permission = false;
  next_reply = reply;
  reply_mode = 0;
  api.begin(execute);
}

static uint16_t u16(const uint8_t* p) { return p[0] | (uint16_t(p[1]) << 8); }
static std::vector<uint8_t> request(uint16_t id = 1, uint8_t operation = 1,
                                    const std::string& command = "api test") {
  std::vector<uint8_t> result = {SmartUiApi::COMMAND, 'S', 'U', 'I', SmartUiApi::VERSION,
                                uint8_t(id), uint8_t(id >> 8), operation};
  if (operation == 1) result.insert(result.end(), command.begin(), command.end());
  return result;
}
static std::vector<uint8_t> fetch(uint16_t id, uint16_t offset) {
  auto result = request(id, 2);
  result.push_back(uint8_t(offset));
  result.push_back(uint8_t(offset >> 8));
  return result;
}

struct Result {
  std::vector<uint8_t> bytes;
  uint16_t id() const { CHECK(bytes.size() >= SmartUiApi::RESPONSE_HEADER); return u16(bytes.data() + 5); }
  uint8_t operation() const { CHECK(bytes.size() >= SmartUiApi::RESPONSE_HEADER); return bytes[7]; }
  uint8_t status() const { CHECK(bytes.size() >= SmartUiApi::RESPONSE_HEADER); return bytes[8]; }
  uint16_t offset() const { CHECK(bytes.size() >= SmartUiApi::RESPONSE_HEADER); return u16(bytes.data() + 9); }
  uint16_t total() const { CHECK(bytes.size() >= SmartUiApi::RESPONSE_HEADER); return u16(bytes.data() + 11); }
  std::string body() const { return std::string(bytes.begin() + SmartUiApi::RESPONSE_HEADER, bytes.end()); }
};

static Result callRaw(const uint8_t* input, size_t length, size_t capacity = SmartUiApi::MAX_FRAME,
                      bool allowed = true, bool null_output = false) {
  constexpr size_t GUARD = 16;
  CHECK(capacity <= 256);
  std::array<uint8_t, 256 + 2 * GUARD> output;
  output.fill(0xa5);
  const auto size = api.handle(input, length, null_output ? nullptr : output.data() + GUARD,
                               capacity, allowed);
  CHECK(size <= capacity && size <= SmartUiApi::MAX_FRAME);
  for (size_t i = 0; i < GUARD; ++i) CHECK(output[i] == 0xa5);
  // No bytes may be touched beyond the returned complete frame, even inside
  // a larger transport buffer. This also covers the no-ACK/no-execution gate.
  for (size_t i = GUARD + size; i < output.size(); ++i) CHECK(output[i] == 0xa5);
  Result result{{output.begin() + GUARD, output.begin() + GUARD + size}};
  if (size) {
    CHECK(size >= SmartUiApi::RESPONSE_HEADER);
    const uint8_t expected[] = {SmartUiApi::COMMAND, 'S', 'U', 'I', SmartUiApi::VERSION};
    CHECK(memcmp(result.bytes.data(), expected, sizeof(expected)) == 0);
    CHECK(result.total() < SmartUiApi::MAX_REPLY);
    CHECK(result.offset() <= result.total());
    CHECK(result.body().size() <= static_cast<size_t>(result.total() - result.offset()));
  }
  return result;
}
static Result call(const std::vector<uint8_t>& input, size_t capacity = SmartUiApi::MAX_FRAME,
                   bool allowed = true) {
  const auto before = input;
  const auto result = callRaw(input.data(), input.size(), capacity, allowed);
  CHECK(before == input);
  return result;
}
static void expectError(const std::vector<uint8_t>& input, uint8_t status) {
  const auto count = executions;
  const auto result = call(input);
  CHECK(result.status() == status && result.total() == 0 && result.offset() == 0);
  CHECK(result.bytes.size() == SmartUiApi::RESPONSE_HEADER && result.body().empty());
  CHECK(executions == count);
}

int main() {
  static_assert(SmartUiApi::HEADER + SmartUiApi::MAX_COMMAND == 160, "Request wire limit changed");
  static_assert(SmartUiApi::MAX_FRAME == 160, "Response wire limit changed");
  static_assert(SmartUiApi::MAX_REPLY == 480, "Reply allocation changed");
  fresh("OK api hello v=1 request_max=160 frame_max=160 reply_max=479");
  auto result = call(request(1, 0));
  CHECK(result.status() == SmartUiApi::OK && result.id() == 1 && result.operation() == 0);
  CHECK(result.offset() == 0 && result.total() == next_reply.size() && result.body() == next_reply);
  CHECK(last_command == "api hello" && executions == 1);

  // Every short output buffer (including zero) must refuse execution and
  // leave the request ID usable once enough room for the ACK is supplied.
  const auto write = request(1, 1, "api set fem_lna 1");
  for (size_t capacity = 0; capacity < SmartUiApi::MAX_FRAME; ++capacity) {
    fresh();
    CHECK(call(write, capacity).bytes.empty());
    CHECK(executions == 0 && mutations == 0);
    CHECK(call(write).status() == SmartUiApi::OK);
    CHECK(executions == 1 && mutations == 1);
  }
  fresh();
  CHECK(callRaw(write.data(), write.size(), 256, true, true).bytes.empty());
  CHECK(executions == 0 && mutations == 0);
  CHECK(call(write, 256).status() == SmartUiApi::OK);
  CHECK(executions == 1 && mutations == 1);

  // Structural rejection must happen before execution or cache consumption.
  fresh();
  for (size_t length = 0; length < SmartUiApi::HEADER; ++length) {
    const auto input = request();
    std::vector<uint8_t> truncated(input.begin(), input.begin() + length);
    expectError(truncated, SmartUiApi::MALFORMED);
  }
  result = callRaw(nullptr, 0);
  CHECK(result.status() == SmartUiApi::MALFORMED && result.id() == 0);
  result = callRaw(nullptr, SmartUiApi::HEADER + SmartUiApi::MAX_COMMAND + 1);
  CHECK(result.status() == SmartUiApi::MALFORMED && result.id() == 0);
  for (size_t byte = 0; byte < 4; ++byte) {
    auto input = request(); input[byte] ^= 0xff;
    expectError(input, SmartUiApi::MALFORMED);
  }
  expectError(request(0), SmartUiApi::MALFORMED);
  auto input = request(); input[4] = 0;
  expectError(input, SmartUiApi::BAD_VERSION);
  input[4] = 255;
  expectError(input, SmartUiApi::BAD_VERSION);
  for (uint16_t operation = 3; operation <= 255; ++operation)
    expectError(request(1, uint8_t(operation)), SmartUiApi::UNKNOWN_OPERATION);
  input = request(1, 0); input.push_back('x');
  expectError(input, SmartUiApi::MALFORMED);
  expectError(request(1, 1, ""), SmartUiApi::MALFORMED);
  expectError(request(1, 1, std::string(SmartUiApi::MAX_COMMAND + 1, 'x')), SmartUiApi::MALFORMED);
  input = request(); input.resize(2000, 'x');
  expectError(input, SmartUiApi::MALFORMED);
  CHECK(executions == 0);
  CHECK(call(request()).status() == SmartUiApi::OK && executions == 1);

  // All 256 byte values are checked at the command boundary; printable ASCII
  // only. Maximum-length input is NUL-terminated safely for the execute hook.
  for (uint16_t value = 0; value <= 255; ++value) {
    fresh();
    input = request(1, 1, std::string(1, char(value)));
    if (value < 0x20 || value > 0x7e) expectError(input, SmartUiApi::MALFORMED);
    else {
      CHECK(call(input).status() == SmartUiApi::OK);
      CHECK(executions == 1 && last_command == std::string(1, char(value)));
    }
  }
  fresh();
  CHECK(call(request(65535, 1, std::string(SmartUiApi::MAX_COMMAND, '~'))).status() == SmartUiApi::OK);
  CHECK(last_command.size() == SmartUiApi::MAX_COMMAND);

  // Replay is exact-byte and does not re-run reads, previews, or mutations.
  fresh("OK api set key=fem_lna value=1");
  auto first = call(write);
  next_reply = "ERR api storage";
  CHECK(call(write).bytes == first.bytes);
  CHECK(call(write, SmartUiApi::MAX_FRAME, false).bytes == first.bytes);
  CHECK(executions == 1 && mutations == 1);
  expectError(request(1, 1, "api set fem_lna 0"), SmartUiApi::STALE);
  expectError(request(1, 0), SmartUiApi::STALE);
  CHECK(call(write).bytes == first.bytes && executions == 1);
  CHECK(call(request(2)).status() == SmartUiApi::COMMAND_FAILED && executions == 2);
  expectError(write, SmartUiApi::STALE);
  CHECK(call(request(65535)).status() == SmartUiApi::COMMAND_FAILED);
  expectError(request(65534), SmartUiApi::STALE);
  expectError(request(1), SmartUiApi::STALE);
  api.resetSession();
  expectError(fetch(65535, 0), SmartUiApi::STALE);
  CHECK(call(request(1)).status() == SmartUiApi::COMMAND_FAILED);

  // Full 479-byte snapshots paginate in 147-byte chunks, with arbitrary valid
  // offsets supported. Invalid fetches never execute or destroy the cache.
  fresh("OK api get " + std::string(SmartUiApi::MAX_REPLY - 1 - strlen("OK api get "), 'x'));
  first = call(request(12));
  CHECK(first.bytes.size() == SmartUiApi::MAX_FRAME && first.total() == 479);
  std::string assembled = first.body();
  while (assembled.size() < first.total()) {
    result = call(fetch(12, uint16_t(assembled.size())));
    CHECK(result.id() == 12 && result.operation() == 2 && result.offset() == assembled.size());
    CHECK(result.status() == SmartUiApi::OK && result.total() == 479);
    assembled += result.body();
  }
  CHECK(assembled == next_reply && executions == 1);
  for (uint16_t offset : {0, 1, 146, 147, 148, 293, 294, 440, 441, 478}) {
    result = call(fetch(12, offset));
    CHECK(result.body() == next_reply.substr(offset, SmartUiApi::MAX_FRAME - SmartUiApi::RESPONSE_HEADER));
  }
  expectError(fetch(12, 479), SmartUiApi::MALFORMED);
  expectError(fetch(12, 480), SmartUiApi::MALFORMED);
  expectError(fetch(12, 65535), SmartUiApi::MALFORMED);
  expectError(fetch(11, 0), SmartUiApi::STALE);
  expectError(fetch(13, 0), SmartUiApi::STALE);
  expectError(request(12, 2), SmartUiApi::MALFORMED);
  input = fetch(12, 0); input.push_back(0);
  expectError(input, SmartUiApi::MALFORMED);
  CHECK(call(request(12)).bytes == first.bytes && executions == 1);
  CHECK(call(request(12), 256).bytes == first.bytes);
  api.resetSession();
  expectError(fetch(12, 0), SmartUiApi::STALE);
  CHECK(call(request(12)).body() == first.body() && executions == 2);

  // Denial and busy responses are cached too; the hook receives the actual
  // authorization gate. A new request ID is required after conditions change.
  fresh("ERR api readonly");
  result = call(write, SmartUiApi::MAX_FRAME, false);
  CHECK(result.status() == SmartUiApi::DENIED && !last_permission && mutations == 0);
  next_reply = "OK api set key=fem_lna value=1";
  CHECK(call(write).bytes == result.bytes && executions == 1 && mutations == 0);
  CHECK(call(request(2, 1, "api set fem_lna 1")).status() == SmartUiApi::OK);
  CHECK(last_permission && mutations == 1);
  fresh("ERR api busy");
  CHECK(call(request()).status() == SmartUiApi::BUSY);
  CHECK(call(fetch(1, 0)).status() == SmartUiApi::BUSY && executions == 1);
  fresh("OK api adc_preview token=17 sampled_mv=4000 measured_mv=4120 multiplier=5.047000");
  input = request(9, 1, "api adc preview 4120");
  first = call(input);
  next_reply = "OK api adc_preview token=18 sampled_mv=3999 measured_mv=4120 multiplier=5.048262";
  CHECK(call(input).bytes == first.bytes && executions == 1);
  api.resetSession();
  expectError(fetch(9, 0), SmartUiApi::STALE);
  CHECK(call(input).body() == next_reply && executions == 2);

  // Broken hooks must never publish unterminated, multiline, binary, or empty
  // protocol records, and their normalized failure must itself be replayable.
  for (int mode : {1, 2, 3}) {
    fresh(); reply_mode = mode;
    result = call(request());
    CHECK(result.status() == SmartUiApi::COMMAND_FAILED && result.body() == "ERR api unsupported");
    CHECK(call(request()).bytes == result.bytes && executions == 1);
  }
  for (const std::string& body : {std::string("nonsense"), std::string("OK api "), std::string("ERR api "),
       std::string("OK api get value=1\nforged"), std::string("OK api get value=1\rforged"),
       std::string("ERR api bad\tvalue"), std::string("OK api get value=\x7f"),
       std::string("OK api get value=\x80")}) {
    fresh(body);
    result = call(request());
    CHECK(result.status() == SmartUiApi::COMMAND_FAILED && result.body() == "ERR api unsupported");
    CHECK(call(fetch(1, 0)).body() == "ERR api unsupported" && executions == 1);
  }
  fresh(); api.begin(nullptr);
  CHECK(call(request()).body() == "ERR api unsupported" && executions == 0);

  // Deterministic structural fuzzing supplements the specific boundary cases.
  uint32_t random = 0x12345678;
  for (unsigned iteration = 0; iteration < 1500; ++iteration) {
    fresh();
    random = random * 1664525U + 1013904223U;
    input.resize(random % 201);
    for (auto& byte : input) { random = random * 1664525U + 1013904223U; byte = uint8_t(random >> 24); }
    result = call(input);
    CHECK(result.status() != SmartUiApi::OK && executions == 0 && mutations == 0);
  }
  printf("PASS %u production SmartUiApi framing/session/bounds assertions\n", checks);
}
