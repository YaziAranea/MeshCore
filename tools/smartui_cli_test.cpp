#include "SmartUiCli.h"
#include "CompanionFrameValidation.h"

#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

using smartui::SmartUiCli;
static unsigned calls;
static std::string last_command, reply_text = "OK";
static bool handled = true;
static bool unterminated;

static bool execute(void*, const char* command, char* reply, size_t capacity) {
  ++calls;
  last_command = command;
  assert(capacity == 157);
  if (unterminated) memset(reply, 'x', capacity);
  else {
    assert(reply_text.size() < capacity);
    memcpy(reply, reply_text.c_str(), reply_text.size() + 1);
  }
  return handled;
}

static std::vector<uint8_t> request(const std::string& command) {
  std::vector<uint8_t> frame {66};
  frame.insert(frame.end(), command.begin(), command.end());
  return frame;
}

static std::string run(SmartUiCli& cli, const std::vector<uint8_t>& frame,
                       bool* armed = nullptr) {
  std::array<uint8_t, SmartUiCli::MAX_FRAME + 2> output;
  output.fill(0xa5);
  bool arm = true;
  const size_t size = cli.handle(frame.data(), frame.size(), output.data() + 1,
      SmartUiCli::MAX_FRAME, execute, nullptr, arm);
  assert(size >= 2 && size <= SmartUiCli::MAX_FRAME);
  assert(output.front() == 0xa5 && output.back() == 0xa5);
  for (size_t i = 1 + size; i < output.size(); ++i) assert(output[i] == 0xa5);
  assert(output[1] == 29);
  if (armed) *armed = arm;
  else assert(!arm);
  return std::string(reinterpret_cast<char*>(output.data() + 2), size - 1);
}

int main() {
  SmartUiCli cli;
  assert(run(cli, request("ui caps")) == "OK");
  assert(last_command == "ui caps");
  assert(run(cli, request("a9|ui caps")) == "a9|OK");
  assert(last_command == "ui caps");
  handled = false;
  assert(run(cli, request("AB|unknown")) == "AB|Unknown command");
  handled = true;
  const unsigned before = calls;
  for (const auto& command : {std::string(), std::string("AA|"), std::string("A|ver"),
      std::string("!A|ver"), std::string("AA||ver"), std::string("ui\nget"),
      std::string("ui\rget"), std::string("ui\tget"), std::string("ui\x7f"),
      std::string("ui\xc3"), std::string("ui\xc0\xaf"), std::string("ui\xed\xa0\x80"),
      std::string("ui\xff"), std::string("ui\0set", 6)}) {
    assert(run(cli, request(command)).find("Error:") != std::string::npos);
  }
  assert(calls == before);
  assert(run(cli, request("AA|ui\nget")) == "AA|Error: invalid command");
  assert(run(cli, request(std::string("a9|ui\0get", 9))) == "a9|Error: invalid command");
  assert(run(cli, request("Z1|ui\xc3")) == "Z1|Error: invalid command");
  assert(calls == before);
  // Upstream commands carry UTF-8 text; it reaches the dispatcher unchanged.
  assert(run(cli, request("Z1|set name \xd0\x94\xd0\xb0\xd1\x87\xd0\xb0")) == "Z1|OK");
  assert(last_command == "set name \xd0\x94\xd0\xb0\xd1\x87\xd0\xb0");
  assert(run(cli, request("set name \xf0\x9f\x93\xa1")) == "OK");
  assert(last_command == "set name \xf0\x9f\x93\xa1");
  assert(calls == before + 2);
  assert(run(cli, request(std::string(157, 'x'))) == "Error: command too long");
  assert(run(cli, request("AA|" + std::string(157, 'x'))) == "Error: command too long");
  assert(calls == before + 2);
  reply_text = std::string(156, 'r');
  assert(run(cli, request(std::string(156, 'x'))).size() == 156);
  assert(run(cli, request("AA|" + std::string(156, 'x'))).size() == 159);
  assert(last_command.size() == 156);
  for (const std::string& valid : {std::string("\xd0\xa2\xd0\xb5\xd1\x81\xd1\x82"),
      std::string("\xf0\x9f\x93\xa1"), std::string(154, 'x') + "\xc3\xa9"}) {
    reply_text = valid;
    assert(run(cli, request("get name")) == valid);
  }
  for (const std::string& invalid : {std::string(), std::string("\n"), std::string("\r"),
      std::string("\x01"), std::string("\x7f"), std::string("\xc0\xaf"),
      std::string("\xed\xa0\x80"), std::string("\xf4\x90\x80\x80"),
      std::string("\x80"), std::string("\xf0\x9f\x93"), std::string(155, 'x') + "\xc3"}) {
    reply_text = invalid;
    assert(run(cli, request("AA|get name")) == "AA|Error: invalid response");
  }
  unterminated = true;
  assert(run(cli, request("ui get")) == "Error: invalid response");
  unterminated = false;
  for (const char* mode : {"ble", "usb", "wifi"}) {
    reply_text = std::string("OK ui mode target=") + mode + " state=pending";
    bool armed = false;
    assert(run(cli, request(std::string("AA|ui mode ") + mode), &armed) == "AA|" + reply_text);
    assert(armed);
    run(cli, request("ui wifi status"));  // Stale callback text cannot arm anything else.
    reply_text += " extra";
    run(cli, request(std::string("ui mode ") + mode));
    reply_text = std::string("OK mode target=") + mode + " state=pending";
    assert(run(cli, request(std::string("set connection ") + mode), &armed) == reply_text);
    assert(armed);
    assert(run(cli, request(std::string("B2|set connection ") + mode), &armed) == "B2|" + reply_text);
    assert(armed);
    run(cli, request("connection status"));
    run(cli, request(std::string("ui mode ") + mode)); // Wrong response namespace.
    reply_text += " extra";
    run(cli, request(std::string("set connection ") + mode));
    reply_text = std::string("OK mode target=") + mode + " state=active";
    run(cli, request(std::string("set connection ") + mode));
  }
  reply_text = "OK ui mode target=ble state=pending";
  run(cli, request("ui mode wifi"));
  reply_text = "ERR ui readonly";
  run(cli, request("ui mode ble"));
  reply_text = "OK mode target=ble state=pending";
  run(cli, request("set connection wifi"));
  reply_text = "Error: readonly";
  run(cli, request("set connection ble"));
  reply_text = "OK";
  const unsigned repeated = calls;
  run(cli, request("AA|ui caps"));
  run(cli, request("AA|ui caps"));
  cli.resetSession();
  run(cli, request("AA|ui caps"));
  assert(calls == repeated + 3);  // Prefix is not an at-most-once token.

  std::array<uint8_t, 162> output;
  output.fill(0xa5);
  bool arm = true;
  auto cmd = request("ui mode ble");
  const unsigned untouched = calls;
  assert(!cli.handle(cmd.data(), cmd.size(), output.data(), 159, execute, nullptr, arm));
  assert(!arm && calls == untouched);
  for (auto c : output) assert(c == 0xa5);
  arm = true;
  assert(!cli.handle(nullptr, 0, output.data(), 160, execute, nullptr, arm) && !arm);
  const uint8_t archived[] = {201, 'S', 'U', 'I'};
  assert(!cli.handle(archived, sizeof(archived), output.data(), 160, execute, nullptr, arm));
  assert(calls == untouched);

  using namespace companion;
  const auto validate = [](const std::vector<uint8_t>& frame) {
    return validateCommandFrame(frame.data(), frame.size(), 176, 32, 64, 172);
  };
  assert(validate({66}) == kFrameTooShort);
  assert(validate(request("v")) == kFrameValid);
  assert(validate(request("AA|" + std::string(156, 'x'))) == kFrameValid);
  assert(validate(request("AA|" + std::string(157, 'x'))) == kFrameTooLarge);

  // Random bytes/lengths cannot escape fixed frame buffers. Callback output
  // remains bounded; malformed requests must not accidentally arm a mode.
  uint32_t random = 0x51f2e33d;
  for (unsigned iteration = 0; iteration < 10000; ++iteration) {
    random = random * 1664525U + 1013904223U;
    std::vector<uint8_t> frame(1 + random % 180);
    frame[0] = 66;
    for (size_t i = 1; i < frame.size(); ++i) {
      random = random * 1664525U + 1013904223U;
      frame[i] = static_cast<uint8_t>(random >> 24);
    }
    run(cli, frame);
  }
  puts("PASS production local CLI bounds, prefixes, UTF-8, malformed hooks, mode intent, session and fuzz");
}
