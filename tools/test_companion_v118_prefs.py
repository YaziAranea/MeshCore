"""Exercise real v1.18 serializers, snapshot ownership and local PIN reads."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile

from test_fem_prefs import source_code
from test_ui_sessions_v006 import function

ROOT = Path(__file__).resolve().parents[1]


def prefs_code():
    mesh = (ROOT / "examples/companion_radio/MyMesh.cpp").read_text(encoding="utf-8")
    start = mesh.index("  // sanitise bad pref values")
    normalization = mesh[start:mesh.index("  _prefs.airtime_factor = constrain", start)]
    header = (ROOT / "examples/companion_radio/MyMesh.h").read_text(encoding="utf-8")
    save = function(header, "bool savePrefs()").replace("bool savePrefs()", "bool MyMesh::savePrefs()", 1)
    return source_code().split("int main()", 1)[0] + r'''
#include "helpers/radiolib/LoRaConfigValidation.h"
template <typename T, typename L, typename H> T constrain(T value, L low, H high) {
  return value < low ? low : value > high ? high : value;
}
void normalize(NodePrefs& _prefs) {
''' + normalization + r'''
}
struct Sensors { double node_lat = 10, node_lon = 20; } sensors;
struct Store { bool result = false; bool savePrefs(NodePrefs&) { return result; } } store;
struct MyMesh {
  NodePrefs _prefs; Store* _store = &store;
  bool isPhoneGpsEnabled() const { return false; }
  bool savePrefs();
};
''' + save + r'''
int main() {
  MyMesh mesh;
  mesh._prefs.getCustom()->setByKey("custom1", "1");
  assert(mesh._prefs.isDirty() && !mesh.savePrefs() && mesh._prefs.isDirty());
  store.result = true;
  assert(mesh.savePrefs() && !mesh._prefs.isDirty());
  for (uint32_t bits : {0x7fc00000U, 0x7f800000U, 0xff800000U}) {
    memcpy(&mesh._prefs.tx_delay_factor, &bits, sizeof(bits));
    memcpy(&mesh._prefs.direct_tx_delay_factor, &bits, sizeof(bits));
    normalize(mesh._prefs);
    assert(mesh._prefs.tx_delay_factor == 0.5f && mesh._prefs.direct_tx_delay_factor == 0.2f);
  }
  mesh._prefs.tx_delay_factor = -1; mesh._prefs.direct_tx_delay_factor = 3;
  normalize(mesh._prefs);
  assert(mesh._prefs.tx_delay_factor == 0 && mesh._prefs.direct_tx_delay_factor == 2);
  NodePrefs live;
  live.tx_delay_factor = 0.5f; live.direct_tx_delay_factor = 0.2f;
  live.cad_enabled = 1; live.interference_threshold = 90;
  live.agc_reset_interval = 15; live.tz_offset = -4;
  live.timezone_offset_minutes = 390; live.notify_tone_pin = -1;
  strcpy(live.quick_replies[0], "reply");
#ifdef ENABLE_WIFI_INTERFACE
  strcpy(live.wifi_ssid, "test network"); strcpy(live.wifi_pwd, "test password");
  live.wifi_enabled = 0;
#endif
  assert(live.getCustom()->setByKey("sensor_1", "25"));
  assert(live.getCustom()->setByKey("fem_rxgain", "1"));
  NodePrefs before(live), assigned;
  assigned = before;
  assert(assigned.isDirty());
  assert(assigned.tx_delay_factor == 0.5f && assigned.direct_tx_delay_factor == 0.2f);
  assert(assigned.cad_enabled == 1 && assigned.interference_threshold == 90);
  assert(assigned.agc_reset_interval == 15 && assigned.tz_offset == -4);
  assert(assigned.timezone_offset_minutes == 390 && assigned.notify_tone_pin == -1);
  assert(!strcmp(assigned.quick_replies[0], "reply"));
  // Changing a copied object's fallback must never target live or the snapshot.
  assert(assigned.getCustom()->setByKey("fem_rxgain", "0"));
  assert(assigned.radio_fem_rxgain == 0);
  assert(live.radio_fem_rxgain == 1 && before.radio_fem_rxgain == 1);
  assert(assigned.getCustom()->setByKey("sensor_1", "30"));
  assigned = before;
  char value[32];
  assert(assigned.getCustom()->getByKey("sensor_1", value, sizeof(value)));
  assert(!strcmp(value, "25"));
  assert(assigned.radio_fem_rxgain == 1);
  CaptureStream saved;
  assert(assigned.saveSerial(saved));
  NodePrefs reboot;
  ReplayStream input(saved.text().c_str());
  assert(reboot.loadSerial(input));
  assert(reboot.tx_delay_factor == 0.5f && reboot.direct_tx_delay_factor == 0.2f);
  assert(reboot.cad_enabled == 1 && reboot.interference_threshold == 90);
  assert(reboot.agc_reset_interval == 15 && reboot.tz_offset == -4);
  assert(reboot.timezone_offset_minutes == 390 && reboot.notify_tone_pin == -1);
  assert(reboot.radio_fem_rxgain == 1 && !strcmp(reboot.quick_replies[0], "reply"));
  assert(reboot.getCustom()->getByKey("sensor_1", value, sizeof(value)));
  assert(!strcmp(value, "25"));
#ifdef ENABLE_WIFI_INTERFACE
  assert(!strcmp(reboot.wifi_ssid, "test network"));
  assert(!strcmp(reboot.wifi_pwd, "test password") && reboot.wifi_enabled == 0);
#endif
  // Dirty state clears only on the owner, with every snapshot independently bound.
  assigned.clearDirty(); assert(!assigned.isDirty() && live.isDirty());
  assigned.getRadioPrefs()->setFloodTxDelay(0.75f);
  assert(assigned.isDirty() && live.tx_delay_factor == 0.5f);
  assigned.getRadioPrefs()->setTxPower(-9);
  assert(assigned.getRadioPrefs()->getTxPower() == -9);

  DynamicConfigSerializer custom;
  for (int i = 0; i < 12; ++i) {
    char key[16]; snprintf(key, sizeof(key), "k%d", i);
    assert(custom.setByKey(key, "x"));
  }
  CaptureStream many; assert(custom.saveSerial(many));
  DynamicConfigSerializer restored;
  ReplayStream many_input(many.text().c_str()); assert(restored.loadSerial(many_input));
  for (int i = 0; i < 12; ++i) {
    char key[16]; snprintf(key, sizeof(key), "k%d", i);
    assert(restored.getByKey(key, value, sizeof(value)) && !strcmp(value, "x"));
  }
  struct Guard { char before = 'A'; char output[2] = {}; char after = 'Z'; } guard;
  assert(restored.setByKey("k0", "1234"));
  assert(restored.getByKey("k0", guard.output, sizeof(guard.output)));
  assert(!strcmp(guard.output, "1") && guard.before == 'A' && guard.after == 'Z');
  guard.output[0] = '!';
  assert(!restored.getByKey("k0", guard.output, 0) && guard.output[0] == '!');
  assert(restored.getByKey("k0", guard.output, 1) && guard.output[0] == 0);
  assert(!restored.getByKey("way_too_long_a_key", value, sizeof(value)));
  assert(!restored.setByKey("bad:key", "x"));
  assert(!restored.setByKey("bad", "x|injected:y"));
  assert(!restored.setByKey("", "x"));
  assert(!restored.setByKey("k1", std::string(128, 'x').c_str()));
  assert(restored.getByKey("k1", value, sizeof(value)) && !strcmp(value, "x"));
  DynamicConfigSerializer invalid;
  ReplayStream malformed("{custom_key:\"value|injected:1\"}");
  assert(!invalid.loadSerial(malformed));
  // Empty upstream custom:{} stays a valid generation; old files keep defaults.
  ReplayStream empty("{custom:{},radio:{tx:10},smart_ui:{tone_8bit:1}}");
  assert(reboot.loadSerial(empty) && reboot.tx_power_dbm == 10 && reboot.notify_tone_8bit_enabled == 1);
  for (const char* malformed : {
      "{custom:{fem_txgain:0},custom:1}",
      "{radio:{fem_txgain:1},}", "{radio:{fem_txgain:1,}}",
      "{custom:{x:{}}}", "{custom:{x:{value:1}}}",
      "{name:{}}", "{name:{nested:1}}", "{radio:1}",
      "{,name:\"bad\"}", "{custom:{} radio:{tx:1}}"}) {
    NodePrefs candidate(live);
    ReplayStream bad(malformed);
    assert(!candidate.loadSerial(bad));
    // DataStore only commits a successfully parsed candidate generation.
    assert(live.radio_fem_txgain == 0 && live.radio_fem_rxgain == 1);
  }
  ReplayStream unknown("{unknown:{future:1},custom:{},radio:{tx:-9}}");
  assert(reboot.loadSerial(unknown) && reboot.tx_power_dbm == -9);
  puts("PASS v1.18 prefs: roundtrip, snapshot/fallback ownership, rollback, WiFi, custom bounds");
}
'''


def pin_code():
    mesh = (ROOT / "examples/companion_radio/MyMesh.cpp").read_text(encoding="utf-8")
    code = function(mesh, "bool MyMesh::executeLocalCli(")
    remote = function(mesh, "void MyMesh::onCliCommandMessage(")
    assert "getBLEPin" not in remote and "execute" not in remote
    return r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <cstdint>
#include <initializer_list>
#define SMARTUI_VERSION "test"
#define FIRMWARE_VERSION "v1.18.0"
struct Board { const char* getManufacturerName() { return "test"; } } board;
bool executeSmartUiCliCommand(const char*, char*, size_t) { return false; }
bool executeMeshCoreCliCommand(const char*, char*, size_t) { return false; }
struct MyMesh {
  struct Prefs { char node_name[32] = {}; float freq=0, bw=0; unsigned sf=0, cr=0; } _prefs;
  uint32_t active_pin = 42;
  uint32_t getBLEPin() { return active_pin; }
  static bool executeLocalCli(void*, const char*, char*, size_t);
};
''' + code + r'''
int main() {
  MyMesh mesh; char reply[80];
  for (const char* command : {"get pin", "get ble.pin"}) {
    assert(MyMesh::executeLocalCli(&mesh, command, reply, sizeof(reply)));
#if defined(BLE_PIN_CODE) && !defined(SMARTUI_DISABLE_BLE)
    assert(!strcmp(reply, "> 000042"));
    mesh.active_pin = 0;
    assert(MyMesh::executeLocalCli(&mesh, command, reply, sizeof(reply)) && !strcmp(reply, "> 0"));
    mesh.active_pin = 42;
#else
    assert(!strcmp(reply, "Error: unsupported"));
#endif
  }
  puts("PASS local active BLE PIN read; no remote command execution");
}
'''


def response_code():
    mesh = (ROOT / "examples/companion_radio/MyMesh.cpp").read_text(encoding="utf-8")
    constants = ("PUSH_CODE_LOGIN_SUCCESS", "PUSH_CODE_LOGIN_FAIL", "PUSH_CODE_STATUS_RESPONSE",
                 "PUSH_CODE_TELEMETRY_RESPONSE", "PUSH_CODE_BINARY_RESPONSE")
    defines = "\n".join(re.search(r"^#define " + name + r"\s+[^\n]+", mesh, re.M)[0]
                        for name in constants)
    return r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <cstdint>
#include <vector>
#define MAX_FRAME_SIZE 176
#define MAX_PACKET_PAYLOAD 172
#define RESP_SERVER_LOGIN_OK 0
struct ContactInfo { struct { uint8_t pub_key[32] = {1,2,3,4,5,6}; } id; };
struct Serial {
  std::vector<uint8_t> output;
  void writeFrame(const uint8_t* data, size_t len) {
    assert(len <= MAX_FRAME_SIZE); output.assign(data, data + len);
  }
};
struct MyMesh {
  struct Listener {
    bool handled = false; unsigned calls = 0;
    bool onUnhandledResponse(const ContactInfo&, uint32_t, const uint8_t*, uint8_t) {
      ++calls; return handled;
    }
  };
  Listener* _listener = nullptr;
  uint32_t pending_login = 0, pending_status = 0, pending_telemetry = 0, pending_req = 0;
  uint8_t out_frame[MAX_FRAME_SIZE + 1] = {};
  Serial serial; Serial* _serial = &serial;
  unsigned connections = 0;
  void startConnection(const ContactInfo&, uint16_t) { ++connections; }
  void onContactResponse(const ContactInfo&, const uint8_t*, uint8_t);
};
''' + defines + "\n" + function(mesh, "void MyMesh::onContactResponse(") + r'''
int main() {
  ContactInfo contact; unsigned cases = 0;
  for (unsigned mode = 0; mode < 5; ++mode) for (unsigned len = 0; len < 256; ++len) {
    MyMesh mesh;
    std::vector<uint8_t> data(len, 0);
    if (len >= 4) { const uint32_t tag = 123; memcpy(data.data(), &tag, 4); }
    uint32_t peer; memcpy(&peer, contact.id.pub_key, 4);
    if (mode == 1) mesh.pending_login = peer;
    if (mode == 2) mesh.pending_status = peer;
    if (mode == 3) mesh.pending_telemetry = 123;
    if (mode == 4) mesh.pending_req = 123;
    mesh.onContactResponse(contact, data.data(), static_cast<uint8_t>(len));
    if (len < 4 || len > MAX_PACKET_PAYLOAD || (mode == 1 && len < 13))
      assert(mesh.serial.output.empty());
    assert(mesh.out_frame[MAX_FRAME_SIZE] == 0);
    ++cases;
  }
  MyMesh mesh;
  uint32_t peer; memcpy(&peer, contact.id.pub_key, 4);
  const uint8_t legacy[] = {1,2,3,4,'O','K'};
  mesh.pending_login = peer;
  mesh.onContactResponse(contact, legacy, sizeof(legacy));
  assert(mesh.serial.output.size() == 8 && mesh.serial.output[0] == PUSH_CODE_LOGIN_SUCCESS);
  const uint8_t denied[] = {1,2,3,4,1};
  mesh.pending_login = peer;
  mesh.onContactResponse(contact, denied, sizeof(denied));
  assert(mesh.serial.output[0] == PUSH_CODE_LOGIN_FAIL);
  MyMesh::Listener listener; mesh._listener = &listener; listener.handled = true;
  mesh.serial.output.clear();
  mesh.onContactResponse(contact, denied, sizeof(denied));
  assert(listener.calls == 1 && mesh.serial.output.empty());
  listener.handled = false;
  mesh.onContactResponse(contact, denied, sizeof(denied));
  assert(listener.calls == 2 && mesh.serial.output.size() == 7);
  assert(mesh.serial.output[0] == PUSH_CODE_BINARY_RESPONSE);
  assert(!memcmp(mesh.serial.output.data() + 2, denied, sizeof(denied)));
  printf("PASS production contact response bounds: %u cases, legacy/modern login, unsolicited/listener paths\n", cases);
}
'''


def main():
    compiler = shutil.which("g++") or shutil.which("clang++")
    with tempfile.TemporaryDirectory(prefix="smartui-v118-prefs-") as directory:
        def path(p):
            if compiler or os.name != "nt":
                return str(p)
            return subprocess.check_output(["wsl", "--exec", "wslpath", "-a", str(p)], text=True).strip()
        prefix = [compiler] if compiler else ["wsl", "--exec", "g++"]
        for name, code, extra in (
            ("prefs", prefs_code(), []), ("wifi", prefs_code(), ["-DENABLE_WIFI_INTERFACE"]),
            ("prefs_fast", prefs_code(), ["-Ofast"]),
            ("pin", pin_code(), ["-DBLE_PIN_CODE=123456"]),
            ("no_ble", pin_code(), []),
            ("disabled_ble", pin_code(), ["-DBLE_PIN_CODE=123456", "-DSMARTUI_DISABLE_BLE=1"]),
            ("responses", response_code(), []),
        ):
            source = Path(directory) / (name + ".cpp")
            output = Path(directory) / name
            source.write_text(code, encoding="utf-8")
            flags = ["-std=c++17", "-O1", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter", "-Wno-sign-compare", "-Wno-implicit-fallthrough"] + extra
            if os.environ.get("SMARTUI_TEST_SANITIZE") == "1":
                flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie"]
            for include in (ROOT, ROOT / "src", ROOT / "test/mocks"):
                flags += ["-I", path(include)]
            subprocess.run(prefix + flags + [path(source), "-o", path(output)], check=True)
            subprocess.run([str(output)] if compiler else ["wsl", "--exec", path(output)], check=True)


if __name__ == "__main__":
    main()
