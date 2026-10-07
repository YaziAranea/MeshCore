#!/usr/bin/env python3
"""Run production local CMD66 framing and MyMesh routing on the host."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def scope(source, signature):
    start = source.index(signature)
    brace = source.index("{", start)
    depth, end = 1, brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def integration():
    source = (ROOT / "examples/companion_radio/MyMesh.cpp").read_text(encoding="utf-8")
    header = (ROOT / "examples/companion_radio/MyMesh.h").read_text(encoding="utf-8")
    main_source = (ROOT / "examples/companion_radio/main.cpp").read_text(encoding="utf-8")
    assert "#define FIRMWARE_VER_CODE 14" in header
    assert 'vars.append("smartui_cli", "1")' in source
    assert 'vars.append("smartui_api"' not in source
    assert "handleSmartUiApiFrame(" not in source
    assert "onCLICommandRecv(" not in source  # Remote execution was not backported.
    remote = scope(source, "void MyMesh::onCliCommandMessage(")
    assert "queueMessage(from, TXT_TYPE_CLI_COMMAND" in remote
    for runner in ("executeLocalCli", "executeMeshCoreCliCommand", "executeSmartUiCliCommand", "handleCommand"):
        assert runner not in remote, runner  # A type-3 command from the mesh is only handed to the app.
    # The archived command-201 implementation may remain as inactive source,
    # but it must never regain a router, runtime ledger or UI callback in the
    # production entry point. Local unread/reminder state belongs to UITask.
    for archived_runtime in (
        '#include "SmartUiApi.h"', '#include "SmartUiSyncApi.h"',
        "static smartui::SmartUiApi", "static smartui::SmartUiSyncApi",
        "static smartui::SmartUiSync smartui_sync", "executeSmartUiApi(",
        "handleSmartUiApiFrame(", "noteSmartUiMessage(",
        "serviceSmartUiSync(", "setSyncActionCallback(",
    ):
        assert archived_runtime not in main_source, archived_runtime
    dispatch = scope(source, "void MyMesh::handleCmdFrame(")
    dispatch = dispatch[:dispatch.index("\n  if (cmd_frame[0] == CMD_DEVICE_QUERY")]
    dispatch += "\n  writeErrFrame(ERR_CODE_UNSUPPORTED_CMD);\n}\n"
    return r'''
#include "SmartUiCli.h"
#include "CompanionFrameValidation.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#define SMARTUI_CONNECTION_SELECTOR 1
#define SMARTUI_VERSION "0.13"
#define FIRMWARE_VERSION "v1.17.1"
#define MAX_FRAME_SIZE 176
#define PUB_KEY_SIZE 32
#define MAX_PATH_SIZE 64
#define MAX_PACKET_PAYLOAD 172
#define ERR_CODE_ILLEGAL_ARG 6
#define ERR_CODE_UNSUPPORTED_CMD 1
#define MESH_DEBUG_PRINTLN(...) do {} while (0)
static unsigned backend_calls;
static std::string backend_reply = "OK", last_command;
static bool backend_handled = true;
bool executeSmartUiCliCommand(const char* command, char* reply, size_t capacity) {
  ++backend_calls; last_command = command;
  snprintf(reply, capacity, "%s", backend_reply.c_str()); return backend_handled;
}
static unsigned meshcore_calls;
static std::string meshcore_reply = "OK", meshcore_command;
static bool meshcore_handled;
bool executeMeshCoreCliCommand(const char* command, char* reply, size_t capacity) {
  ++meshcore_calls; meshcore_command = command;
  if (meshcore_handled) snprintf(reply, capacity, "%s", meshcore_reply.c_str());
  return meshcore_handled;
}
struct Board {
  std::string name = "Test board";
  const char* getManufacturerName() { return name.c_str(); }
} board;
struct Connection { unsigned arms = 0; void apiReplyQueued() { ++arms; } } connection_controller;
struct Serial {
  size_t accepted = static_cast<size_t>(-1);
  std::vector<uint8_t> output;
  size_t writeFrame(const uint8_t* bytes, size_t length) {
    output.assign(bytes, bytes + length);
    return accepted == static_cast<size_t>(-1) ? length : accepted;
  }
};
struct MyMesh {
  struct Prefs { char node_name[32] = "Node"; float freq = 869.161f, bw = 62.5f; uint8_t sf = 7, cr = 7; } _prefs;
  uint8_t cmd_frame[177] = {}, out_frame[177] = {};
  smartui::SmartUiCli _local_cli;
  Serial* _serial;
  explicit MyMesh(Serial* serial) : _serial(serial) {}
  static bool executeLocalCli(void*, const char*, char*, size_t);
  void handleLocalCliFrame(size_t);
  void handleCmdFrame(size_t);
  void writeErrFrame(uint8_t code) { const uint8_t frame[] = {1, code}; _serial->writeFrame(frame, 2); }
};
''' + "\n".join((scope(source, "bool MyMesh::executeLocalCli("),
                    scope(source, "void MyMesh::handleLocalCliFrame("), dispatch)) + r'''
static std::string send(MyMesh& mesh, Serial& serial, const std::string& command) {
  assert(command.size() <= 175);
  mesh.cmd_frame[0] = 66;
  memcpy(mesh.cmd_frame + 1, command.data(), command.size());
  mesh.handleCmdFrame(command.size() + 1);
  assert(!serial.output.empty());
  return std::string(serial.output.begin() + 1, serial.output.end());
}
int main() {
  Serial serial; MyMesh mesh(&serial);
  assert(send(mesh, serial, "board") == "Test board");
  assert(send(mesh, serial, "AB|ver") == "AB|SmartUI 0.13; firmware=v1.17.1");
  assert(send(mesh, serial, "get radio") == "> 869.161,62.500,7,7");
  strcpy(mesh._prefs.node_name, "\xd0\xa2\xd0\xb5\xd1\x81\xd1\x82");
  assert(send(mesh, serial, "get name") == "> \xd0\xa2\xd0\xb5\xd1\x81\xd1\x82");
  board.name = std::string(170, 'b');
  assert(send(mesh, serial, "board") == "Error: response too long");
  // Everything outside `ui` goes to the upstream-name dispatcher, which knows
  // no rescue, filesystem or raw commands; the ui backend never sees them.
  for (const char* command : {"erase", "rebuild", "rm /prefs.json", "ui-extra", "ls"}) {
    assert(send(mesh, serial, command) == "Unknown command");
    assert(serial.output[0] == 29 && meshcore_command == command);
  }
  assert(meshcore_calls == 5 && backend_calls == 0);
  meshcore_handled = true;
  assert(send(mesh, serial, "AA|set radio 869.161,62.5,7,7") == "AA|OK");
  assert(meshcore_command == "set radio 869.161,62.5,7,7");
  assert(send(mesh, serial, "set name \xd0\x94\xd0\xb0\xd1\x87\xd0\xb0") == "OK");
  assert(meshcore_command == "set name \xd0\x94\xd0\xb0\xd1\x87\xd0\xb0");
  meshcore_handled = false;
  assert(meshcore_calls == 7 && backend_calls == 0);
  assert(send(mesh, serial, "AA|ui caps") == "AA|OK");
  assert(backend_calls == 1 && last_command == "ui caps");
  backend_reply = "OK ui mode target=usb state=pending";
  serial.accepted = 0;
  send(mesh, serial, "AA|ui mode usb");
  assert(connection_controller.arms == 0);
  serial.accepted = 1;
  send(mesh, serial, "AA|ui mode usb");
  assert(connection_controller.arms == 0);
  serial.accepted = static_cast<size_t>(-1);
  send(mesh, serial, "ui wifi status");
  assert(connection_controller.arms == 0);
  send(mesh, serial, "AA|ui mode usb");
  assert(connection_controller.arms == 1);
  backend_reply = "ERR ui readonly";
  send(mesh, serial, "ui mode usb");
  assert(connection_controller.arms == 1);
  const auto calls = backend_calls;
  send(mesh, serial, std::string(160, 'x'));
  assert((serial.output == std::vector<uint8_t>{1, 6}) && backend_calls == calls);
  send(mesh, serial, std::string("ui\0caps", 7));
  assert(serial.output[0] == 29 && backend_calls == calls);
  mesh.cmd_frame[0] = 201; mesh.cmd_frame[1] = 'S';
  mesh.handleCmdFrame(2);
  assert((serial.output == std::vector<uint8_t>{1, 1}) && backend_calls == calls);
  assert(connection_controller.arms == 1);
  puts("PASS production MyMesh CLI read-only standards, namespace isolation, archive rejection and exact response-queue mode gate");
}
'''


def main_dispatch_integration():
    source = (ROOT / "examples/companion_radio/main.cpp").read_text(encoding="utf-8")
    body = "\n".join(scope(source, signature) for signature in (
        "bool executeSmartUiCliCommand(", "void resetSmartUiCliSession("))
    return r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#define SMARTUI_VERSION "0.13"
static unsigned controller_calls, controller_resets, backend_calls, backend_resets;
static bool backend_allowed, backend_handled = true;
static std::string last_command;
struct Controller {
  bool writable = true, busy = false;
  bool deviceApiWritesAllowed() const { return writable; }
  bool deviceApiBusy() const { return busy; }
  bool handleCliCommand(const char* command, char* reply, size_t capacity, bool allowed) {
    ++controller_calls;
    if (strcmp(command, "ui connection") != 0) return false;
    snprintf(reply, capacity, "OK ui connection write=%u", allowed ? 1U : 0U);
    return true;
  }
  void resetApiSession() { ++controller_resets; }
} connection_controller;
struct Mesh {
  bool pending = false;
  bool hasPendingWork() const { return pending; }
} the_mesh;
struct Radio {
  bool receiving = false, recv = true;
  bool isReceiving() const { return receiving; }
  bool isInRecvMode() const { return recv; }
} radio_driver;
namespace smartui {
struct DeviceSettings { void resetSession() { ++backend_resets; } };
bool handleSmartUiSettingsCli(DeviceSettings&, const char* command, char* reply,
                              size_t capacity, bool allowed) {
  ++backend_calls; backend_allowed = allowed; last_command = command;
  if (backend_handled) snprintf(reply, capacity, "OK ui backend");
  return backend_handled;
}
}
static smartui::DeviceSettings cli_device_settings;
struct RadioSettings {
  bool handle(const char* command, char* reply, size_t capacity, bool allowed) {
    if (strcmp(command, "ui radio") != 0 && strcmp(command, "ui advert") != 0 &&
        strncmp(command, "ui radio set ", 13) != 0) return false;
    snprintf(reply, capacity, "OK ui radio-backend write=%u", allowed ? 1U : 0U);
    return true;
  }
} radio_settings;
''' + body + r'''
static std::string call(const char* command, bool expected_handled = true) {
  char reply[157] = {};
  const bool handled = executeSmartUiCliCommand(command, reply, sizeof(reply));
  assert(handled == expected_handled);
  return reply;
}
static void fresh() {
  connection_controller = Controller{}; the_mesh = Mesh{}; radio_driver = Radio{};
  controller_calls = backend_calls = 0; backend_allowed = false;
  backend_handled = true; last_command.clear();
}
int main() {
  fresh(); connection_controller.writable = false;
  assert(call("ui hello").find("write=0 sync=0 events=0 meshcore=1") != std::string::npos);
  assert(controller_calls == 0 && backend_calls == 0);
  assert(call("ui connection") == "OK ui connection write=0");
  assert(controller_calls == 1 && backend_calls == 0);
  assert(call("ui radio") == "OK ui radio-backend write=0");
  assert(call("ui advert") == "OK ui radio-backend write=0");
  assert(call("ui radio set 869161 62500 7 7 2") == "OK ui radio-backend write=0");
  assert(backend_calls == 0);

  connection_controller.busy = true;
  for (const char* command : {"ui caps v", "ui get battery_mv", "ui melody 0"}) {
    assert(call(command) == "OK ui backend");
    assert(last_command == command && !backend_allowed);
  }
  const unsigned reads = backend_calls;
  assert(call("ui set volume 2") == "ERR ui busy" && backend_calls == reads);
  assert(call("ui adc preview 3320") == "ERR ui busy" && backend_calls == reads);
  assert(call("ui test") == "ERR ui busy" && backend_calls == reads);
  connection_controller.busy = false;
  assert(call("ui set volume 2") == "ERR ui readonly" && backend_calls == reads);

  connection_controller.writable = true;
  assert(call("ui test") == "OK ui backend" && backend_allowed);
  const unsigned before_fem = backend_calls;
  the_mesh.pending = true;
  assert(call("ui set fem_lna 1") == "ERR ui busy" && backend_calls == before_fem);
  the_mesh.pending = false; radio_driver.receiving = true;
  assert(call("ui set fem_pa 1") == "ERR ui busy" && backend_calls == before_fem);
  radio_driver.receiving = false; radio_driver.recv = false;
  assert(call("ui set fem_lna 0") == "ERR ui busy" && backend_calls == before_fem);
  radio_driver.recv = true;
  assert(call("ui set fem_lna 1") == "OK ui backend" && backend_calls == before_fem + 1);

  backend_handled = false;
  call("ui unknown", false);
  const unsigned old_backend_resets = backend_resets, old_controller_resets = controller_resets;
  resetSmartUiCliSession();
  assert(backend_resets == old_backend_resets + 1 &&
         controller_resets == old_controller_resets + 1);
  puts("PASS production main CMD66 dispatcher permissions, busy/FEM gates and session reset");
}
'''


def radio_hooks_integration():
    source = (ROOT / "examples/companion_radio/main.cpp").read_text(encoding="utf-8")
    mesh = (ROOT / "examples/companion_radio/MyMesh.cpp").read_text(encoding="utf-8")
    controller = (ROOT / "examples/companion_radio/ConnectionController.cpp").read_text(encoding="utf-8")
    assert "radio_settings.handle(command, reply, capacity, allow_mutation)" in scope(source, "static bool handleCompanionDeviceSettings(")
    assert "handleDeviceSettingsCommand(line);" in scope(controller, "void ConnectionController::handleConsoleLine(")
    assert "smartui::validAutoAdvertInterval(mins)" in scope(mesh, "static bool isValidAutoAdvertIntervalMins(")
    assert "sendZeroHop(pkt);" in scope(mesh, "bool MyMesh::advert()")
    body = "\n".join(scope(source, signature) for signature in (
        "static bool saveDeviceSettings(", "static smartui::RadioSettingsState readRadioSettings(",
        "static void writeRadioSettings(", "static bool validateRadioSettings(",
        "static bool applyRadioSettings(", "static bool repeatFrequencyAllowed(",
        "static void applyAdvertSettings(", "static bool radioSettingsBusy(",
        "static bool radioSettingsHealthy("))
    start = source.index("  smartui::RadioSettingsHooks radio_hooks;")
    stop = source.index("  radio_settings.begin(radio_hooks);", start) + len("  radio_settings.begin(radio_hooks);")
    return r'''
#include "RadioSettings.h"
#include <helpers/radiolib/LoRaConfigValidation.h>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
struct NodePrefs {
  float freq=869.161f,bw=62.5f; uint8_t sf=7,cr=7,path_hash_mode=0;
  int8_t tx_power_dbm=20; uint16_t auto_advert_interval_mins=30;
  bool repeat=false; double node_lat=12.0,node_lon=34.0;
  char identity[16]="leave-alone";
  bool isRepeatEn() const { return repeat; }
};
struct Mesh {
  NodePrefs prefs, disk;
  bool save_ok=true, busy=false, healthy=true;
  unsigned applies=0, timers=0;
  NodePrefs* getNodePrefs() { return &prefs; }
  bool savePrefs() { prefs.node_lat=56; prefs.node_lon=78; if(save_ok) disk=prefs; return save_ok; }
  bool validateLocalRadioSettings(float f,float b,uint8_t s,uint8_t c) { return validSX1262LoRaParams(f,b,s,c); }
  bool applyLocalRadioSettings(float f,float b,uint8_t s,uint8_t c) { ++applies;return validSX1262LoRaParams(f,b,s,c); }
  bool localRepeatFrequencyAllowed(uint32_t khz) const { return khz == 869495; }
  void applyLocalAdvertInterval() { ++timers; }
  bool localRadioSettingsBusy() const { return busy; }
  bool localRadioSettingsHealthy() const { return healthy; }
} the_mesh;
struct Controller { bool busy=false; bool deviceApiBusy() const {return busy;} } connection_controller;
static smartui::RadioSettings radio_settings;
''' + body + r'''
static std::string call(const char* command,bool writable=true) {
  char reply[157]={}; assert(radio_settings.handle(command,reply,sizeof(reply),writable)); return reply;
}
int main() {
''' + source[start:stop] + r'''
  assert(call("ui radio").find("path_bytes=1")!=std::string::npos);
  assert(call("settings radio set 868731 125000 9 8 3").find("path_bytes=3")!=std::string::npos);
  assert(the_mesh.prefs.path_hash_mode==2 && the_mesh.disk.path_hash_mode==2);
  assert(the_mesh.prefs.tx_power_dbm==20 && !the_mesh.prefs.repeat);
  assert(strcmp(the_mesh.prefs.identity,"leave-alone")==0 && the_mesh.timers==0);
  assert(call("ui advert set 120")=="OK ui advert interval_min=120");
  assert(the_mesh.prefs.auto_advert_interval_mins==120 && the_mesh.timers==1);
  assert(call("settings advert")=="OK settings advert interval_min=120");
  assert(call("settings advert set 120")=="OK settings advert interval_min=120" && the_mesh.timers==1);
  connection_controller.busy=true;
  assert(call("ui radio set 869161 62500 7 7 1")=="ERR ui busy");
  connection_controller.busy=false; the_mesh.busy=true;
  assert(call("settings radio set 869161 62500 7 7 1")=="ERR settings busy");
  the_mesh.busy=false; the_mesh.save_ok=false;
  the_mesh.prefs.node_lat=12;the_mesh.prefs.node_lon=34;
  assert(call("settings radio set 869161 62500 7 7 1")=="ERR settings storage");
  assert(the_mesh.prefs.node_lat==12 && the_mesh.prefs.node_lon==34);
  assert(the_mesh.prefs.path_hash_mode==2 && the_mesh.prefs.freq==868.731f);
  assert(call("settings advert set 30")=="ERR settings storage");
  assert(the_mesh.prefs.auto_advert_interval_mins==120 && the_mesh.timers==1);
  assert(the_mesh.prefs.node_lat==12 && the_mesh.prefs.node_lon==34);
  puts("PASS production RadioSettings hooks, USB/CLI routing, persisted path bytes, scheduler, location rollback");
}
'''


def meshcore_hooks_integration():
    source = (ROOT / "examples/companion_radio/main.cpp").read_text(encoding="utf-8")
    mesh = (ROOT / "examples/companion_radio/MyMesh.cpp").read_text(encoding="utf-8")
    local = scope(mesh, "bool MyMesh::executeLocalCli(")
    assert "return executeMeshCoreCliCommand(command, reply, capacity);" in local
    assert local.index("executeSmartUiCliCommand") < local.index("executeMeshCoreCliCommand")
    # Each upstream setter persists through the same rollback as its binary twin.
    for setter in ("bool MyMesh::setLocalNodeName(", "bool MyMesh::setLocalBlePin(",
                   "bool MyMesh::setLocalTuning(", "bool MyMesh::setLocalMultiAcks(",
                   "bool MyMesh::setLocalPathHashMode(", "bool MyMesh::setLocalRxBoostedGain(",
                   "bool MyMesh::setLocalTimezoneMinutes("):
        assert "commitPrefsOrRollback(before)" in scope(mesh, setter), setter
    assert "flushPendingStorage()" in scope(mesh, "void MyMesh::rebootLocal(")
    body = "\n".join(scope(source, signature) for signature in (
        "static smartui::MeshCoreCliResult cliResult(",
        "static smartui::MeshCoreCliState readMeshCoreCliState(",
        "static smartui::MeshCoreCliResult cliSetName(",
        "static smartui::MeshCoreCliResult cliSetPin(",
        "static smartui::MeshCoreCliResult cliSetTxPower(",
        "static smartui::MeshCoreCliResult cliSetTuning(",
        "static smartui::MeshCoreCliResult cliSetMultiAcks(",
        "static smartui::MeshCoreCliResult cliSetPathHashMode(",
        "static smartui::MeshCoreCliResult cliSetRxGain(",
        "static smartui::MeshCoreCliResult cliSetTimezoneMinutes(",
        "static bool cliRadioCommand(", "static smartui::MeshCoreCliResult cliReboot(",
        "static smartui::MeshCoreCliResult cliPowerOff(", "static bool cliWifiStatus(",
        "static bool cliBusy(", "bool executeMeshCoreCliCommand("))
    start = source.index("  smartui::MeshCoreCliHooks meshcore_hooks;")
    stop = source.index("  meshcore_cli.begin(meshcore_hooks);", start) + len("  meshcore_cli.begin(meshcore_hooks);")
    return r'''
#include "MeshCoreCli.h"
#include "ConnectionTypes.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#define MAX_LORA_TX_POWER 22
struct NodePrefs {
  float freq=869.618f,bw=62.5f; uint8_t sf=8,cr=8; int8_t tx_power_dbm=20;
  float airtime_factor=1.0f,rx_delay_base=0; uint8_t multi_acks=0,path_hash_mode=1,rx_boosted_gain=0;
  int16_t timezone_offset_minutes=330;
};
struct Mesh {
  NodePrefs prefs; bool save_ok=true,radio_busy=false,gain_supported=true,flush_ok=true;
  unsigned reboots=0; std::string name; uint32_t pin=1;
  NodePrefs* getNodePrefs() { return &prefs; }
  bool setLocalNodeName(const char* n) { if(save_ok) name=n; return save_ok; }
  bool setLocalBlePin(uint32_t p) { if(save_ok) pin=p; return save_ok; }
  bool setLocalTxPower(int8_t d) { if(save_ok) prefs.tx_power_dbm=d; return save_ok; }
  bool setLocalTuning(float r,float a) { if(save_ok){prefs.rx_delay_base=r;prefs.airtime_factor=a;} return save_ok; }
  bool setLocalMultiAcks(uint8_t c) { if(save_ok) prefs.multi_acks=c; return save_ok; }
  bool setLocalPathHashMode(uint8_t m) { if(save_ok) prefs.path_hash_mode=m; return save_ok; }
  bool setLocalRxBoostedGain(bool b,bool& s) { s=gain_supported; if(s&&save_ok) prefs.rx_boosted_gain=b; return s&&save_ok; }
  bool setLocalTimezoneMinutes(int16_t m) { if(save_ok) prefs.timezone_offset_minutes=m; return save_ok; }
  bool localRadioSettingsBusy() { return radio_busy; }
  void rebootLocal() { ++reboots; }  // Returning stands for a failed flush.
  bool flushPendingStorage() { return flush_ok; }
} the_mesh;
struct Board { unsigned power_offs=0; void powerOff() { ++power_offs; } } board;
struct Controller {
  bool writable=true,busy=false; CompanionStatus current;
  CompanionStatus status() const { return current; }
  bool deviceApiBusy() const { return busy; }
  bool deviceApiWritesAllowed() const { return writable; }
} connection_controller;
struct RadioStub {
  std::string last; bool allowed=false;
  bool handle(const char* c,char* r,size_t cap,bool a) { last=c; allowed=a; snprintf(r,cap,"OK ui radio freq_khz=869618"); return true; }
} radio_settings;
static smartui::MeshCoreCli meshcore_cli;
''' + body + r'''
static std::string call(const char* command) {
  char reply[157]={}; assert(executeMeshCoreCliCommand(command,reply,sizeof(reply))); return reply;
}
int main() {
''' + source[start:stop] + r'''
  assert(call("get tz.offset")=="> 5.5" && call("get tx")=="> 20" && call("get freq")=="> 869.618");
  assert(call("set tx 21")=="OK" && the_mesh.prefs.tx_power_dbm==21);
  assert(call("set tx 23")=="Error, must be -9 to 22" && the_mesh.prefs.tx_power_dbm==21);
  assert(call("set name \xd0\x94\xd0\xb0\xd1\x87\xd0\xb0")=="OK" && the_mesh.name=="\xd0\x94\xd0\xb0\xd1\x87\xd0\xb0");
  assert(call("set pin 654321")=="> pin is now 654321" && the_mesh.pin==654321);
  assert(call("set af 2")=="OK" && the_mesh.prefs.airtime_factor==2 && the_mesh.prefs.rx_delay_base==0);
  assert(call("set rxdelay 4")=="OK" && the_mesh.prefs.rx_delay_base==4 && the_mesh.prefs.airtime_factor==2);
  assert(call("set multi.acks 1")=="OK" && the_mesh.prefs.multi_acks==1);
  assert(call("set path.hash.mode 2")=="OK" && the_mesh.prefs.path_hash_mode==2);
  assert(call("set tz.offset -3.5")=="OK" && the_mesh.prefs.timezone_offset_minutes==-210);
  assert(call("set radio 869.618,62.5,8,8")=="OK");
  assert(radio_settings.last=="ui radio set 869618 62500 8 8 3" && radio_settings.allowed);
  the_mesh.radio_busy=true;
  assert(call("set radio.rxgain on")=="Error: busy" && !the_mesh.prefs.rx_boosted_gain);
  the_mesh.radio_busy=false; the_mesh.gain_supported=false;
  assert(call("set radio.rxgain on")=="Error: unsupported" && !the_mesh.prefs.rx_boosted_gain);
  the_mesh.gain_supported=true;
  assert(call("set radio.rxgain on")=="OK" && the_mesh.prefs.rx_boosted_gain==1);
  the_mesh.save_ok=false;
  assert(call("set tx 10")=="Error: storage" && the_mesh.prefs.tx_power_dbm==21);
  the_mesh.save_ok=true; connection_controller.writable=false;
  assert(call("set tx 10")=="Error: readonly" && the_mesh.prefs.tx_power_dbm==21);
  assert(call("set radio 869.618,62.5,8,8")=="OK" && !radio_settings.allowed);
  connection_controller.writable=true; connection_controller.busy=true;
  assert(call("set tx 10")=="Error: busy" && the_mesh.prefs.tx_power_dbm==21);
  connection_controller.busy=false;
  assert(call("get wifi.status")=="Error: unsupported");
  connection_controller.current.capabilities=COMPANION_CAP_WIFI;
  connection_controller.current.wifiAssociated=true;
  strcpy(connection_controller.current.wifiLocalIp,"10.0.0.7");
  assert(call("get wifi.status")=="> connected" && call("get wifi.ip")=="> 10.0.0.7");
  assert(call("reboot")=="Error: storage" && the_mesh.reboots==1);
  the_mesh.flush_ok=false;
  assert(call("poweroff")=="Error: storage" && board.power_offs==0);
  the_mesh.flush_ok=true;
  assert(call("shutdown")=="Error: unsupported" && board.power_offs==1);
  char reply[157]={};
  assert(!executeMeshCoreCliCommand("erase",reply,sizeof(reply)) && reply[0]==0);
  puts("PASS production MeshCore CLI hooks: binary-command setters, radio transaction, gates, Wi-Fi status, reboot/power-off");
}
'''


def queue_integration():
    source = (ROOT / "examples/companion_radio/MyMesh.cpp").read_text(encoding="utf-8")
    queue = scope(source, "bool MyMesh::addToOfflineQueue(")
    assert "noteSmartUiMessage" not in queue
    return r'''
#include <helpers/OfflineQueueSync.h>
#include <cassert>
#include <cstdio>
#include <cstring>
#define SMARTUI_CONNECTION_SELECTOR 1
#define MAX_FRAME_SIZE 176
#define OFFLINE_QUEUE_SIZE 8
#define MESH_DEBUG_PRINTLN(...) do {} while (0)
struct MyMesh {
  struct Frame {
    uint8_t len=0, buf[176]={}; uint32_t ui_generation=0; uint8_t ui_flags=0;
    bool isChannelMsg() const { return buf[0] == 8; }
  };
  uint32_t before=0xfeedface;
  Frame offline_queue[8];
  uint32_t after=0xaabbccdd;
  int offline_queue_len=0;
  uint32_t next_ui_message_generation=0;
  bool addToOfflineQueue(const uint8_t[], int, uint32_t=0, uint8_t=0);
  int peekOfflineQueue(uint8_t[], uint32_t&, uint8_t&) const;
  void commitOfflineQueue();
  uint32_t nextUiMessageGeneration();
};
''' + "\n".join((queue, *(scope(source, signature) for signature in (
        "int MyMesh::peekOfflineQueue(", "void MyMesh::commitOfflineQueue(",
        "uint32_t MyMesh::nextUiMessageGeneration(")))) + r'''
int main() {
  MyMesh mesh; uint8_t frame[176]={7, 1, 2};
  assert(!mesh.addToOfflineQueue(nullptr, 3));
  assert(!mesh.addToOfflineQueue(frame, 0) && !mesh.addToOfflineQueue(frame, 177));
  assert(mesh.next_ui_message_generation == 0);
  auto id = mesh.nextUiMessageGeneration();
  assert(mesh.addToOfflineQueue(frame, 176, id, 1));
  assert(mesh.addToOfflineQueue(frame, 3));
  assert(mesh.offline_queue[0].ui_generation == 1 && mesh.offline_queue[1].ui_generation == 2);
  uint8_t output[178]; memset(output, 0xa5, sizeof(output)); uint32_t generation=0; uint8_t flags=0;
  assert(mesh.peekOfflineQueue(output+1, generation, flags)==176 && generation==1 && flags==1);
  assert(output[0]==0xa5 && output[177]==0xa5 && !memcmp(output+1, frame, 176));
  assert(mesh.offline_queue_len==2);
  mesh.commitOfflineQueue();
  assert(mesh.peekOfflineQueue(output+1, generation, flags)==3 && generation==2 && flags==0);
  mesh.commitOfflineQueue();
  assert(mesh.peekOfflineQueue(output+1, generation, flags)==0 && generation==0 && flags==0);
  for (unsigned i=0; i<8; ++i) assert(mesh.addToOfflineQueue(frame, 3));
  assert(!mesh.addToOfflineQueue(frame, 3) && mesh.offline_queue_len==8);
  const auto oldest=mesh.offline_queue[0].ui_generation;
  mesh.offline_queue[3].buf[0]=8;
  assert(mesh.addToOfflineQueue(frame, 3));
  assert(mesh.offline_queue_len==8 && mesh.offline_queue[0].ui_generation==oldest);
  assert(mesh.offline_queue[7].ui_generation==mesh.next_ui_message_generation);
  mesh.next_ui_message_generation=UINT32_MAX;
  assert(!mesh.addToOfflineQueue(frame, 3) && mesh.offline_queue_len==8);
  assert(mesh.before==0xfeedface && mesh.after==0xaabbccdd);
  puts("PASS production local UI/offline queue generations without archived API side effects");
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix="smartui-cli-") as directory:
        adapter = Path(directory) / "cli_integration.cpp"
        adapter.write_text(integration(), encoding="utf-8")
        main_adapter = Path(directory) / "cli_main_dispatch.cpp"
        main_adapter.write_text(main_dispatch_integration(), encoding="utf-8")
        queue = Path(directory) / "cli_queue.cpp"
        queue.write_text(queue_integration(), encoding="utf-8")
        radio_hooks = Path(directory) / "radio_hooks.cpp"
        radio_hooks.write_text(radio_hooks_integration(), encoding="utf-8")
        meshcore_hooks = Path(directory) / "meshcore_hooks.cpp"
        meshcore_hooks.write_text(meshcore_hooks_integration(), encoding="utf-8")
        compiler = shutil.which("g++") or shutil.which("clang++")
        flags = ["-std=c++17", "-Wall", "-Wextra", "-Werror"]
        if os.environ.get("SMARTUI_TEST_SANITIZE") == "1":
            flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie"]
        include = ROOT / "examples/companion_radio"
        for suite in (ROOT / "tools/smartui_cli_test.cpp", adapter, main_adapter, queue,
                      ROOT / "tools/radio_settings_test.cpp", radio_hooks,
                      ROOT / "tools/meshcore_cli_test.cpp", meshcore_hooks):
            paths = [suite, include / "SmartUiCli.cpp"]
            radio_suite = suite.name in ("radio_settings_test.cpp", "radio_hooks.cpp")
            meshcore_suite = suite.name in ("meshcore_cli_test.cpp", "meshcore_hooks.cpp")
            if radio_suite:
                paths += [include / "RadioSettings.cpp"]
            if meshcore_suite:
                paths += [include / "MeshCoreCli.cpp"]
            # nRF52 builds use -Ofast; normal optimization alone misses the
            # reciprocal-conversion rounding that rejected valid presets, and
            # the upstream-name parser must reject NaN/infinity without isfinite().
            for optimization in (("-O1", "-Ofast") if radio_suite or meshcore_suite else ("-O1",)):
                output = Path(directory) / (suite.stem + optimization)
                if compiler:
                    build = [compiler, *flags, optimization, "-I" + str(include), "-I" + str(ROOT / "src"), *map(str, paths), "-o", str(output)]
                    execute = [str(output)]
                elif os.name == "nt":
                    def linux(path):
                        return subprocess.check_output(["wsl", "--exec", "wslpath", "-a", str(path)], text=True).strip()
                    build = ["wsl", "--exec", "g++", *flags, optimization, "-I" + linux(include), "-I" + linux(ROOT / "src"), *map(linux, paths), "-o", linux(output)]
                    execute = ["wsl", "--exec", linux(output)]
                else:
                    raise RuntimeError("Host C++ compiler required; no skipped test success")
                print(f"{suite.name} {optimization}", flush=True)
                subprocess.run(build, check=True)
                subprocess.run(execute, check=True)


if __name__ == "__main__":
    main()
