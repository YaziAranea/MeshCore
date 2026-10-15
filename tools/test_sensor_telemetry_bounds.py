"""Exercise production sensor telemetry parsing and subscription state transitions."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile

from test_ui_sessions_v006 import function

ROOT = Path(__file__).resolve().parents[1]


def source_code():
    source = (ROOT / "examples/simple_sensor/SensorMesh.cpp").read_text(encoding="utf-8")
    capacity = re.search(r"telemetry\((MAX_PACKET_PAYLOAD[^\n]+)\)\s*$", source, re.M)[1]
    core = (ROOT / "src/MeshCore.h").read_text(encoding="utf-8")
    constants = "\n".join(re.findall(r"^#define (?:MAX_PACKET_PAYLOAD|CIPHER_MAC_SIZE|CIPHER_BLOCK_SIZE)\s+\d+.*$", core, re.M))
    mesh_source = (ROOT / "src/Mesh.cpp").read_text(encoding="utf-8")
    datagram = function(mesh_source, "Packet* Mesh::createDatagram")
    datagram_guard = datagram[datagram.index("{") + 1:datagram.index("  Packet* packet")]
    definitions = "\n".join(re.findall(r"^#define REQ_TYPE_.*$", source, re.M))
    helpers = source[source.index("static bool isScalarTelemType"):source.index("/* ------------------ end Cayenne")]
    methods = "\n".join(function(source, signature) for signature in (
        "bool SensorMesh::telemHasChanged", "void SensorMesh::snapshotTelemetry", "uint8_t SensorMesh::handleRequest"))
    return r'''
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <vector>
#include "helpers/sensors/LPPDataHelpers.h"
using std::abs;
using std::isnan;
''' + constants + r'''
constexpr int PAYLOAD_TYPE_TXT_MSG = 2, PAYLOAD_TYPE_REQ = 0, PAYLOAD_TYPE_RESPONSE = 1;
bool acceptsDatagram(uint8_t type, size_t data_len) {
''' + datagram_guard + r'''
  return true;
}
constexpr int TELEM_CHANNEL_SELF = 1;
constexpr int PERM_ACL_ROLE_MASK = 3, PERM_ACL_READ_ONLY = 1, PERM_ACL_ADMIN = 3;
struct ClientInfo {
  struct { uint8_t pub_key[32]{}; } id;
  uint8_t permissions = 3;
  struct { struct {
    uint32_t push_tag = 55, expiry_timestamp = 0;
    uint16_t scope_region_id = 0;
    uint8_t min_deltas_len = 0, min_deltas[14]{}, prev_telem[14]{};
  } sensor; } extra;
  bool isAdmin() const { return permissions == 3; }
};
struct Telemetry {
  size_t capacity;
  std::vector<uint8_t> bytes;
  explicit Telemetry(size_t n) : capacity(n) {}
  uint8_t* getBuffer() { return bytes.data(); }
  uint8_t getSize() { return bytes.size(); }
  void reset() { bytes.clear(); }
  void addVoltage(int, float) {}
  void addTemperature(int, float) {}
};
struct RegionEntry { uint16_t id = 7; char name[16] = "region"; bool isWildcard() const { return false; } } region;
struct { RegionEntry* getDefaultRegion() { return &region; } } region_map;
struct { int getNumClients() const { return 0; } ClientInfo* getClientByIdx(int) { return nullptr; } } acl;
struct { int getBattMilliVolts() { return 4100; } float getMCUTemperature() { return 20; } } board;
struct Location { bool isPowerSavingEnabled() { return false; } void syncTime() {} } location;
struct { Location* getLocationProvider() { return &location; } void querySensors(int, Telemetry&) {} } sensors;
struct Clock { uint32_t getCurrentTime() const { return 100; } } clock_source;
struct Random { void random(uint8_t* p, size_t n) { memset(p, 0x42, n); } } random_source;
struct MinMaxAvg { uint8_t _channel, _lpp_type; float _min, _max, _avg; };
struct SensorMesh {
  Telemetry telemetry{''' + capacity + r'''};
  uint8_t reply_data[MAX_PACKET_PAYLOAD]{};
  RegionEntry* recv_pkt_region = nullptr;
  Clock* getRTCClock() { return &clock_source; }
  Random* getRNG() { return &random_source; }
  int querySeriesData(uint32_t, uint32_t, MinMaxAvg*, int) { return 0; }
  bool telemHasChanged(ClientInfo*);
  void snapshotTelemetry(ClientInfo*);
  uint8_t handleRequest(ClientInfo*, uint32_t, uint8_t, uint8_t*, size_t);
};
''' + definitions + "\n" + helpers + "\n" + methods + r'''
int main() {
  SensorMesh mesh;
  ClientInfo client;
  assert(mesh.telemetry.capacity + 8 <= sizeof(mesh.reply_data));
  assert(acceptsDatagram(PAYLOAD_TYPE_RESPONSE, mesh.telemetry.capacity + 8));
  assert(!acceptsDatagram(PAYLOAD_TYPE_RESPONSE, mesh.telemetry.capacity + 9));
  assert(LPPData::getDataSize(LPP_RELATIVE_HUMIDITY) == 1);
  assert(LPPData::getMultiplier(LPP_RELATIVE_HUMIDITY) == 2);
  const uint8_t delta[] = {1, LPP_TEMPERATURE, 0, 10, 2, LPP_RELATIVE_HUMIDITY, 4};
  assert(validTelemDeltas(delta, sizeof(delta)));
  const uint8_t unknown[] = {1, 255, 0};
  const uint8_t negative[] = {1, LPP_TEMPERATURE, 255, 255};
  const uint8_t vector[] = {1, LPP_GPS, 0,0,0,0,0,0,0,0,0};
  assert(!validTelemDeltas(unknown, sizeof(unknown)));
  assert(!validTelemDeltas(negative, sizeof(negative)));
  assert(!validTelemDeltas(vector, sizeof(vector)));
  for (size_t size = 0; size < sizeof(delta); ++size) {
    std::vector<uint8_t> short_data(delta, delta + size);
    bool valid = validTelemDeltas(short_data.data(), short_data.size());
    assert(valid == (size == 4)); // Only a complete first scalar is valid.
  }
  for (uint8_t command : {REQ_TYPE_GET_TELEMETRY_DATA, REQ_TYPE_GET_AVG_MIN_MAX, REQ_TYPE_GET_ACCESS_LIST}) {
    const size_t required = command == REQ_TYPE_GET_TELEMETRY_DATA ? 1 : command == REQ_TYPE_GET_AVG_MIN_MAX ? 10 : 2;
    for (size_t size = 0; size < required; ++size) {
      std::vector<uint8_t> payload(size, 0);
      assert(mesh.handleRequest(&client, 1, command, payload.data(), size) == 0);
    }
  }
  std::vector<uint8_t> subscribe = {77,0,0,0,60,0,0,sizeof(delta)};
  subscribe.insert(subscribe.end(), delta, delta + sizeof(delta));
  for (size_t size = 0; size < subscribe.size(); ++size) {
    std::vector<uint8_t> payload(subscribe.begin(), subscribe.begin() + size);
    ClientInfo before = client;
    mesh.handleRequest(&client, 1, REQ_TYPE_SUBSCRIBE, payload.data(), size);
    assert(client.extra.sensor.push_tag == before.extra.sensor.push_tag);
    assert(client.extra.sensor.min_deltas_len == 0);
    assert(client.extra.sensor.scope_region_id == 0);
  }
  assert(mesh.handleRequest(&client, 1, REQ_TYPE_SUBSCRIBE, subscribe.data(), subscribe.size()) > 8);
  assert(client.extra.sensor.push_tag == 77 && client.extra.sensor.scope_region_id == 7);
  assert(client.extra.sensor.expiry_timestamp == 160 && client.extra.sensor.min_deltas_len == sizeof(delta));
  mesh.telemetry.bytes = {1,LPP_TEMPERATURE,0,210,2,LPP_RELATIVE_HUMIDITY,100};
  assert(mesh.telemHasChanged(&client));
  assert(mesh.telemHasChanged(&client)); // An unsent update remains pending.
  assert(client.extra.sensor.prev_telem[3] == 0);
  mesh.snapshotTelemetry(&client);
  assert(!memcmp(client.extra.sensor.prev_telem, mesh.telemetry.bytes.data(), sizeof(delta)));
  assert(!mesh.telemHasChanged(&client));
  mesh.telemetry.bytes[6] = 106;
  assert(mesh.telemHasChanged(&client));
  const uint8_t truncated[] = {1,LPP_TEMPERATURE,0};
  assert(findTelemValue(truncated, sizeof(truncated), 1, LPP_TEMPERATURE, -1) == -1);
  client.extra.sensor.min_deltas_len = 15;
  assert(!mesh.telemHasChanged(&client));
  client.extra.sensor.min_deltas_len = 3;
  memcpy(client.extra.sensor.min_deltas, truncated, 3);
  assert(!mesh.telemHasChanged(&client));
  mesh.handleRequest(&client, 1, REQ_TYPE_UNSUBSCRIBE, nullptr, 0);
  assert(client.extra.sensor.min_deltas_len == 0 && client.extra.sensor.scope_region_id == 0);
  puts("PASS production sensor telemetry: short requests, atomic subscriptions, scalar bounds, humidity, snapshots and push capacity");
}
'''


def main():
    compiler = shutil.which("g++") or shutil.which("clang++")
    with tempfile.TemporaryDirectory(prefix="sensor-telemetry-") as directory:
        def path(p):
            if compiler or os.name != "nt":
                return str(p)
            return subprocess.check_output(["wsl", "--exec", "wslpath", "-a", str(p)], text=True).strip()
        source = Path(directory) / "test.cpp"
        source.write_text(source_code(), encoding="utf-8")
        for optimization in ("-O1", "-Ofast"):
            output = Path(directory) / ("test" + optimization)
            flags = ["-std=c++17", optimization, "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                     "-Wno-sign-compare", "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie"]
            prefix = [compiler] if compiler else ["wsl", "--exec", "g++"]
            subprocess.run(prefix + flags + ["-I", path(ROOT / "src"), path(source), "-o", path(output)], check=True)
            subprocess.run([str(output)] if compiler else ["wsl", "--exec", path(output)], check=True)


if __name__ == "__main__":
    main()
