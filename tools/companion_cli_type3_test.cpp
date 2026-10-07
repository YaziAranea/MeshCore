// Template used by test_smartui_cli.py. Production methods are inserted, not
// reimplemented here. Spies replace encryption, RF, clocks, display and serial.
#include "CompanionFrameValidation.h"
#include <helpers/TxtDataHelpers.h>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

// EXTRACTED_CONSTANTS
#define MAX_FRAME_SIZE 176
#define EXPECTED_ACK_TABLE_SIZE 8
#define SMARTUI_CONNECTION_SELECTOR 1
#define DISPLAY_CLASS TestDisplay
#define MESH_DEBUG_PRINTLN(...) do {} while (0)

static unsigned command_executions;
bool executeSmartUiCliCommand(const char*, char*, size_t) { ++command_executions; return true; }
bool executeMeshCoreCliCommand(const char*, char*, size_t) { ++command_executions; return true; }

struct Identity { uint8_t pub_key[PUB_KEY_SIZE] = {1, 2, 3, 4, 5, 6}; };
struct ContactInfo {
  Identity id;
  char name[32] = "Peer";
  uint8_t out_path[MAX_PATH_SIZE] = {}, out_path_len = OUT_PATH_UNKNOWN, flags = 0;
  uint32_t lastmod = 0, sync_since = 0;
  uint8_t secret[PUB_KEY_SIZE] = {};
  const uint8_t* getSharedSecret(const Identity&) const { return secret; }
};
namespace mesh {
struct Packet {
  bool flood = false;
  uint8_t path[MAX_PATH_SIZE] = {}, path_len = 2;
  std::vector<uint8_t> payload;
  bool isRouteFlood() const { return flood; }
  float getSNR() const { return 2.5f; }
  size_t getRawLength() const { return payload.size(); }
};
struct Utils {
  static void sha256(uint8_t* dest, size_t len, const uint8_t*, size_t,
                     const uint8_t*, size_t) { memset(dest, 0xac, len); }
};
}
struct Clock {
  uint32_t now = 1000; unsigned unique_calls = 0;
  uint32_t getCurrentTime() const { return now; }
  uint32_t getCurrentTimeUnique() { ++unique_calls; return ++now; }
};
struct Millis { uint32_t getMillis() const { return 777; } };
struct Random { void random(uint8_t* dest, size_t n) { memset(dest, 1, n); } };
struct Radio { uint32_t getEstAirtimeFor(size_t) const { return 10; } };
struct BaseChatMesh {
  ContactInfo contacts[1]; int num_contacts = 1, matching_peer_indexes[1] = {0};
  Identity self_id; Clock clock; Random random; Radio radio; Radio* _radio = &radio;
  mesh::Packet outgoing, path_return;
  uint8_t temp_buf[MAX_PACKET_PAYLOAD] = {};
  unsigned datagrams = 0, flood_sends = 0, direct_sends = 0, path_returns = 0, rx_acks = 0;
  bool allocate_packet = true;
  uint32_t txt_send_timeout = 0;
  uint8_t last_extra_type = 0;
  Clock* getRTCClock() { return &clock; }
  Random* getRNG() { return &random; }
  uint32_t futureMillis(uint32_t value) { return 777 + value; }
  uint32_t calcFloodTimeoutMillisFor(uint32_t value) { return value + 100; }
  uint32_t calcDirectTimeoutMillisFor(uint32_t value, uint8_t) { return value + 50; }
  mesh::Packet* createDatagram(uint8_t type, const Identity&, const uint8_t*,
                               const uint8_t* data, size_t len) {
    assert(type == PAYLOAD_TYPE_TXT_MSG || type == PAYLOAD_TYPE_RESPONSE);
    if (!allocate_packet) return nullptr;
    ++datagrams; outgoing.payload.assign(data, data + len); return &outgoing;
  }
  mesh::Packet* createPathReturn(const Identity&, const uint8_t*, const uint8_t*,
                                 uint8_t, uint8_t type, const uint8_t*, size_t) {
    ++path_returns; last_extra_type = type; return &path_return;
  }
  void sendFloodScoped(const ContactInfo&, mesh::Packet*, uint32_t = 0) { ++flood_sends; }
  void sendDirect(mesh::Packet*, const uint8_t*, uint8_t, uint32_t = 0) { ++direct_sends; }
  void sendAckTo(const ContactInfo&, const uint8_t*, size_t = 4) { ++rx_acks; }
  uint8_t onContactRequest(const ContactInfo&, uint32_t, const uint8_t*, size_t, uint8_t*) { return 0; }
  void onContactResponse(const ContactInfo&, const uint8_t*, size_t) {}
  void handleReturnPathRetry(const ContactInfo&, const uint8_t*, uint8_t) {}
  virtual void onMessageRecv(const ContactInfo&, mesh::Packet*, uint32_t, const char*) = 0;
  virtual void onCommandDataRecv(const ContactInfo&, mesh::Packet*, uint32_t, const char*) = 0;
  virtual void onCliCommandMessage(const ContactInfo&, mesh::Packet*, uint32_t, const char*) = 0;
  virtual void onSignedMessageRecv(const ContactInfo&, mesh::Packet*, uint32_t, const uint8_t*, const char*) = 0;
  void onPeerDataRecv(mesh::Packet*, uint8_t, int, const uint8_t*, uint8_t*, size_t);
  mesh::Packet* composeMsgPacket(const ContactInfo&, uint32_t, uint8_t, const char*, uint32_t&);
  int sendMessage(const ContactInfo&, uint32_t, uint8_t, const char*, uint32_t&, uint32_t&);
  int sendCommandData(const ContactInfo&, uint32_t, uint8_t, uint8_t, const char*, uint32_t&);
};
enum class UIEventType { contactMessage };
struct UI {
  unsigned messages = 0, notifications = 0;
  template<typename... Args> void newMsg(Args...) { ++messages; }
  void notify(UIEventType) { ++notifications; }
};
struct Serial {
  bool connected = true;
  std::vector<std::vector<uint8_t>> frames;
  bool isConnected() const { return connected; }
  void writeFrame(const uint8_t* data, size_t len) { frames.emplace_back(data, data + len); }
};
struct MyMesh : BaseChatMesh {
  uint32_t before = 0x12345678;
  uint8_t cmd_frame[MAX_FRAME_SIZE + 1] = {}, out_frame[MAX_FRAME_SIZE + 1] = {};
  uint32_t after = 0x87654321;
  uint8_t app_target_ver = 3;
  UI ui; UI* _ui = &ui; Serial serial; Serial* _serial = &serial;
  Millis millis; Millis* _ms = &millis;
  int offline_queue_len = 0;
  bool queue_accepts = true, contact_exists = true;
  unsigned ui_generations = 0, marks = 0, status_notes = 0;
  std::vector<uint8_t> queued;
  uint8_t queued_flags = 255; uint32_t queued_generation = 0;
  struct AckTableEntry { uint32_t msg_sent = 0, ack = 0; uint8_t recipient_pub_key[PUB_KEY_SIZE] = {}; };
  AckTableEntry expected_ack_table[EXPECTED_ACK_TABLE_SIZE]; unsigned next_ack_idx = 0;
  void markConnectionActive(const ContactInfo&) { ++marks; }
  void noteNetworkStatus(const ContactInfo&, uint8_t) { ++status_notes; }
  void scheduleContactsSave() {}
  uint32_t nextUiMessageGeneration() { return ++ui_generations; }
  bool addToOfflineQueue(const uint8_t* data, int len, uint32_t generation, uint8_t flags) {
    assert(len > 0 && len <= MAX_FRAME_SIZE);
    queued.assign(data, data + len); queued_flags = flags; queued_generation = generation;
    if (queue_accepts) ++offline_queue_len;
    return queue_accepts;
  }
  ContactInfo* lookupContactByPubKey(const uint8_t* key, size_t len) {
    return contact_exists && !memcmp(key, contacts[0].id.pub_key, len) ? &contacts[0] : nullptr;
  }
  void writeErrFrame(uint8_t code) { uint8_t frame[] = {1, code}; _serial->writeFrame(frame, 2); }
  bool executeLocalCli(const char*, char*, size_t) { ++command_executions; return true; }
  bool handleCommand(const char*, uint32_t, char*) { ++command_executions; return true; }
  void recordExpectedAck(uint32_t, const uint8_t[PUB_KEY_SIZE]);
  void queueMessage(const ContactInfo&, uint8_t, mesh::Packet*, uint32_t, const uint8_t*, int, const char*);
  void onMessageRecv(const ContactInfo&, mesh::Packet*, uint32_t, const char*) override;
  void onCommandDataRecv(const ContactInfo&, mesh::Packet*, uint32_t, const char*) override;
  void onCliCommandMessage(const ContactInfo&, mesh::Packet*, uint32_t, const char*) override;
  void onSignedMessageRecv(const ContactInfo&, mesh::Packet*, uint32_t, const uint8_t*, const char*) override;
  void handleCmdFrame(size_t);
};

// EXTRACTED_METHODS

static uint32_t u32(const uint8_t* p) { uint32_t value; memcpy(&value, p, 4); return value; }
static void guards(const MyMesh& mesh) {
  assert(mesh.before == 0x12345678 && mesh.after == 0x87654321);
  assert(mesh.out_frame[MAX_FRAME_SIZE] == 0);
  assert(command_executions == 0);
}
static void send(MyMesh& mesh, uint8_t type, const std::string& text, uint8_t attempt = 2) {
  assert(text.size() + 13 <= MAX_FRAME_SIZE);
  memset(mesh.cmd_frame, 0xa5, sizeof(mesh.cmd_frame));
  mesh.cmd_frame[0] = CMD_SEND_TXT_MSG; mesh.cmd_frame[1] = type; mesh.cmd_frame[2] = attempt;
  const uint32_t app_timestamp = 42; memcpy(mesh.cmd_frame + 3, &app_timestamp, 4);
  memcpy(mesh.cmd_frame + 7, mesh.contacts[0].id.pub_key, 6);
  memcpy(mesh.cmd_frame + 13, text.data(), text.size());
  mesh.handleCmdFrame(13 + text.size()); guards(mesh);
}
static void receive(MyMesh& mesh, uint8_t type, bool flood, const std::string& text) {
  assert(text.size() <= MAX_TEXT_LEN);
  // Mesh supplies spare termination/padding bytes to onPeerDataRecv.
  uint8_t data[MAX_PACKET_PAYLOAD + 2] = {};
  const uint32_t timestamp = 123; memcpy(data, &timestamp, 4); data[4] = (type << 2) | 2;
  memcpy(data + 5, text.data(), text.size());
  mesh::Packet packet; packet.flood = flood;
  mesh.onPeerDataRecv(&packet, PAYLOAD_TYPE_TXT_MSG, 0, mesh.contacts[0].secret,
                      data, 5 + text.size());
  assert(data[5 + text.size()] == 0); guards(mesh);
}
int main() {
  static_assert(TXT_TYPE_CLI_COMMAND == 3, "Protocol14 text command wire value");
  unsigned cases = 0;
  for (uint8_t type : {TXT_TYPE_PLAIN, TXT_TYPE_CLI_DATA, TXT_TYPE_CLI_COMMAND}) {
    for (bool flood : {false, true}) {
      MyMesh mesh; mesh.contacts[0].out_path_len = flood ? OUT_PATH_UNKNOWN : 2;
      send(mesh, type, "get name");
      const auto& packet = mesh.outgoing.payload;
      assert(mesh.datagrams == 1 && packet.size() == 13 && packet[4] == ((type << 2) | 2));
      assert(std::string(packet.begin() + 5, packet.end()) == "get name");
      assert(mesh.flood_sends == unsigned(flood) && mesh.direct_sends == unsigned(!flood));
      const bool plain = type == TXT_TYPE_PLAIN;
      assert(u32(packet.data()) == (plain ? 42u : 1001u));
      assert(mesh.clock.unique_calls == unsigned(!plain));
      assert(mesh.serial.frames.size() == 1);
      const auto& response = mesh.serial.frames[0];
      assert(response.size() == 10 && response[0] == RESP_CODE_SENT && response[1] == unsigned(flood));
      assert(u32(response.data() + 2) == (plain ? 0xacacacacu : 0u));
      assert(mesh.next_ack_idx == unsigned(plain));
      assert(u32(response.data() + 6) == (flood ? 110u : 60u));
      assert(mesh.txt_send_timeout == 777 + u32(response.data() + 6)); ++cases;
    }
    for (size_t n : {size_t(1), size_t(MAX_TEXT_LEN), size_t(MAX_TEXT_LEN + 1), size_t(MAX_FRAME_SIZE - 13)}) {
      MyMesh mesh; send(mesh, type, std::string(n, 'x'));
      assert(mesh.datagrams == unsigned(n <= MAX_TEXT_LEN));
      assert(mesh.serial.frames.back()[0] == (n <= MAX_TEXT_LEN ? RESP_CODE_SENT : 1));
      if (n > MAX_TEXT_LEN) assert(mesh.serial.frames.back()[1] == ERR_CODE_TABLE_FULL);
      ++cases;
    }
    for (bool flood : {false, true}) for (uint8_t app : {uint8_t(2), uint8_t(3)}) {
      MyMesh mesh; mesh.app_target_ver = app; mesh.serial.connected = false;
      receive(mesh, type, flood, "reboot");
      const size_t prefix = app >= 3 ? 3 : 0;
      assert(mesh.queued[0] == (app >= 3 ? RESP_CODE_CONTACT_MSG_RECV_V3 : RESP_CODE_CONTACT_MSG_RECV));
      assert(!memcmp(mesh.queued.data() + 1 + prefix, mesh.contacts[0].id.pub_key, 6));
      assert(mesh.queued[7 + prefix] == (flood ? 2 : 255) && mesh.queued[8 + prefix] == type);
      assert(u32(mesh.queued.data() + 9 + prefix) == 123);
      assert(std::string(mesh.queued.begin() + 13 + prefix, mesh.queued.end()) == "reboot");
      const bool plain = type == TXT_TYPE_PLAIN;
      assert(mesh.ui.messages == unsigned(plain) && mesh.ui.notifications == unsigned(plain));
      assert(mesh.ui_generations == unsigned(plain));
      assert(mesh.queued_flags == (plain ? UI_MSG_FLAG_DIRECT : UI_MSG_FLAG_NONE));
      assert(mesh.queued_generation == unsigned(plain));
      assert(mesh.rx_acks == unsigned(plain && !flood));
      assert(mesh.path_returns == unsigned(flood && type != TXT_TYPE_CLI_COMMAND));
      assert(mesh.datagrams == 0 && mesh.serial.frames.empty());
      assert(mesh.marks == 1 && mesh.status_notes == 1); ++cases;
    }
  }
  for (const char* command : {"reboot", "set pin 123456", "ui set volume 1"}) {
    for (uint8_t flags : {uint8_t(0), uint8_t(0x10)}) {
      MyMesh mesh; mesh.contacts[0].flags = flags;
      receive(mesh, TXT_TYPE_CLI_COMMAND, true, command);
      assert(mesh.serial.frames == std::vector<std::vector<uint8_t>>{{PUSH_CODE_MSG_WAITING}});
      assert(mesh.datagrams == 0 && mesh.path_returns == 0 && mesh.rx_acks == 0);
      assert(mesh.ui.messages == 0 && mesh.ui.notifications == 0); ++cases;
    }
  }
  for (uint8_t type : {TXT_TYPE_CLI_DATA, TXT_TYPE_CLI_COMMAND}) {
    MyMesh mesh;
    for (uint8_t attempt : {uint8_t(0), uint8_t(3), uint8_t(255)}) {
      const uint32_t before = mesh.clock.now;
      send(mesh, type, "get name", attempt);
      assert(mesh.outgoing.payload[4] == ((type << 2) | (attempt & 3)));
      assert(u32(mesh.outgoing.payload.data()) == before + 1);
      assert(mesh.next_ack_idx == 0 && u32(mesh.serial.frames.back().data() + 2) == 0);
      ++cases;
    }
  }
  for (size_t len = 0; len < 14; ++len) {
    MyMesh mesh; mesh.cmd_frame[0] = CMD_SEND_TXT_MSG; mesh.cmd_frame[1] = TXT_TYPE_CLI_COMMAND;
    mesh.handleCmdFrame(len);
    assert(mesh.serial.frames == std::vector<std::vector<uint8_t>>({{1, ERR_CODE_ILLEGAL_ARG}}));
    assert(mesh.datagrams == 0 && mesh.clock.unique_calls == 0); guards(mesh); ++cases;
  }
  {
    MyMesh mesh; mesh.cmd_frame[0] = CMD_SEND_TXT_MSG;
    mesh.handleCmdFrame(MAX_FRAME_SIZE + 1);
    assert(mesh.serial.frames == std::vector<std::vector<uint8_t>>({{1, ERR_CODE_ILLEGAL_ARG}}));
    assert(mesh.datagrams == 0); guards(mesh); ++cases;
  }
  for (size_t len = 0; len <= 5; ++len) {
    MyMesh mesh; uint8_t data[8] = {}; data[4] = TXT_TYPE_CLI_COMMAND << 2; mesh::Packet packet;
    mesh.onPeerDataRecv(&packet, PAYLOAD_TYPE_TXT_MSG, 0, mesh.contacts[0].secret, data, len);
    assert(mesh.queued.empty() && mesh.serial.frames.empty() && mesh.datagrams == 0);
    guards(mesh); ++cases;
  }
  {
    MyMesh mesh; receive(mesh, TXT_TYPE_CLI_COMMAND, false, std::string(MAX_TEXT_LEN, 'x'));
    assert(mesh.queued.size() == 16 + MAX_TEXT_LEN && mesh.queued.size() == MAX_FRAME_SIZE);
    guards(mesh); ++cases;
  }
  {
    MyMesh mesh; mesh.queue_accepts = false;
    receive(mesh, TXT_TYPE_CLI_COMMAND, false, "poweroff");
    assert(mesh.serial.frames.empty() && mesh.ui.messages == 0 && mesh.ui.notifications == 0);
    guards(mesh); ++cases;
  }
  for (int mode = 0; mode < 4; ++mode) {
    MyMesh mesh;
    if (mode == 0) mesh.contact_exists = false;
    if (mode == 1) mesh.allocate_packet = false;
    send(mesh, mode == 2 ? 2 : mode == 3 ? 63 : TXT_TYPE_CLI_COMMAND, "get name");
    assert(mesh.serial.frames[0][0] == 1 && mesh.datagrams == 0 && mesh.next_ack_idx == 0);
    assert(mesh.serial.frames[0][1] == (mode == 0 ? ERR_CODE_NOT_FOUND :
      mode == 1 ? ERR_CODE_TABLE_FULL : ERR_CODE_UNSUPPORTED_CMD)); ++cases;
  }
  {
    MyMesh mesh; mesh.matching_peer_indexes[0] = -1;
    receive(mesh, TXT_TYPE_CLI_COMMAND, false, "get name");
    assert(mesh.queued.empty() && mesh.serial.frames.empty()); ++cases;
  }
  assert(command_executions == 0);
  printf("PASS production companion type3 RX/TX: %u cases; no execution/ACK/UI alert, bounded frames, types0/1 retained\n", cases);
}
