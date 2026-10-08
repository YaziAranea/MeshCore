#include "CoreSettingsCommands.h"
#include "MeshCoreCli.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>

static smartui::MeshCoreCli cli;
static smartui::MeshCoreCliState state;
static char name[32] = "Node";
static bool busy, fail;
static unsigned writes;
static smartui::MeshCoreCliState read() { return state; }
static smartui::MeshCoreCliResult setTx(int8_t value) {
  ++writes;
  if (fail) return smartui::MeshCoreCliResult::STORAGE;
  state.tx_dbm = value; return smartui::MeshCoreCliResult::OK;
}
static smartui::MeshCoreCliResult setName(const char* value) {
  ++writes;
  if (fail) return smartui::MeshCoreCliResult::STORAGE;
  snprintf(name, sizeof(name), "%s", value); return smartui::MeshCoreCliResult::OK;
}
static bool isBusy() { return busy; }
static std::string call(const std::string& command, bool writable = true) {
  char guard[159]; memset(guard, 0x5a, sizeof(guard));
  assert(smartui::handleCoreSettingsCommand(command.c_str(), guard + 1, 157, writable, cli, name, 22));
  assert(guard[0] == 0x5a && guard[158] == 0x5a && strlen(guard + 1) <= 156);
  return guard + 1;
}
int main() {
  smartui::MeshCoreCliHooks hooks;
  hooks.read = read; hooks.setName = setName; hooks.setTxPower = setTx; hooks.busy = isBusy;
  cli.begin(hooks); state.tx_dbm = 20; state.max_tx_dbm = 22;
  for (const std::string ns : {"settings", "ui"}) {
    const std::string ok = "OK " + ns, err = "ERR " + ns;
    assert(call(ns + " tx") == ok + " tx value=20 min=-9 max=22");
    assert(call(ns + " tx set -9") == ok + " tx value=-9 min=-9 max=22");
    assert(call(ns + " tx set 22") == ok + " tx value=22 min=-9 max=22");
    const unsigned before = writes;
    for (const char* value : {"", "23", "-10", "999999999999999999999", "nan", "inf", "1.2", "1 2", "1\n", "+1"}) {
      assert(call(ns + " tx set " + value) == err + " invalid");
      assert(writes == before && state.tx_dbm == 22);
    }
    assert(call(ns + " tx set 1", false) == err + " readonly");
    busy = true; assert(call(ns + " tx set 1") == err + " busy"); busy = false;
    assert(writes == before);
    fail = true; assert(call(ns + " tx set 1") == err + " storage"); fail = false;
    assert(state.tx_dbm == 22);
    assert(call(ns + " name d094d0b0") == ok + " name name_hex=d094d0b0");
    assert(call(ns + " identity", false) == ok + " identity name_hex=d094d0b0 max_name_bytes=31");
    const unsigned named = writes;
    for (const char* hex : {"", "00", "0a", "7f", "c080", "eda080", "f4908080", "zz", "6", "5b", "61 62"}) {
      assert(call(ns + " name " + hex) == err + " invalid"); assert(writes == named);
    }
    assert(call(ns + " name 61", false) == err + " readonly");
    busy = true; assert(call(ns + " name 61") == err + " busy"); busy = false;
    fail = true; assert(call(ns + " name 61") == err + " storage"); fail = false;
    assert(call(ns + " identity") == ok + " identity name_hex=d094d0b0 max_name_bytes=31");
    const std::string max_name(62, '6');
    assert(call(ns + " name " + max_name) == ok + " name name_hex=" + max_name);
    assert(call(ns + " name " + max_name + "66") == err + " invalid");
    assert(call(ns + " name 4e6f6465") == ok + " name name_hex=4e6f6465");
    assert(call(ns + " tx set 20") == ok + " tx value=20 min=-9 max=22");
  }
  for (size_t capacity = 0; capacity < 157; ++capacity) {
    char guard[159]; memset(guard, 0x5a, sizeof(guard));
    const unsigned before = writes;
    assert(smartui::handleCoreSettingsCommand("ui tx set 1", guard + 1, capacity, true, cli, name, 22));
    assert(writes == before && guard[0] == 0x5a && guard[158] == 0x5a);
    for (size_t i = capacity + 1; i < sizeof(guard); ++i) assert(guard[i] == 0x5a);
  }
  char reply[157];
  for (const char* command : {"ui get volume", "ui tx_extra", "settings adc set 1.815", "get tx", "ui name_extra", "ui identity x"})
    assert(!smartui::handleCoreSettingsCommand(command, reply, sizeof(reply), true, cli, name, 22));
  puts("PASS CoreSettings: service/companion name and TX, UTF-8, limits, readonly, busy, storage, bounded buffers");
}
