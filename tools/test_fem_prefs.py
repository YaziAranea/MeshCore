"""Compile actual NodePrefs and verify durable FEM radio fields."""

from pathlib import Path
import shutil
import subprocess
import tempfile

from test_ui_sessions_v006 import function

ROOT = Path(__file__).resolve().parents[1]


def room_startup_code():
    source = (ROOT / "examples/simple_room_server/MyMesh.cpp").read_text(encoding="utf-8")
    begin = function(source, "void MyMesh::begin(")
    return r'''
namespace room_startup {
struct FILESYSTEM {};
namespace mesh { struct Mesh { void begin() {} }; }
struct RegionEntry {};
struct FakeRegionMap {
  void load(FILESYSTEM*) {}
  RegionEntry* getDefaultRegion() { return nullptr; }
  void getTransportKeysFor(const RegionEntry&, int*, int) {}
};
struct FakeACL { void load(FILESYSTEM*, int) {} };
static bool saved_lna, saved_pa, prefs_loaded;
struct FakeCLI {
  NodePrefs* prefs;
  void loadPrefs(FILESYSTEM*) {
    prefs->radio_fem_rxgain = saved_lna;
    prefs->radio_fem_txgain = saved_pa;
    prefs_loaded = true;
  }
};
struct FakeRadio {
  void setParams(float, float, uint8_t, uint8_t) { assert(prefs_loaded); }
  void setTxPower(int8_t) {}
  void setRxBoostedGainMode(bool) {}
} radio_driver;
struct FakeBoard {
  bool legacy_supported = true, lna = false, pa = false;
  unsigned lna_calls = 0, pa_calls = 0, attach_calls = 0;
  bool setLoRaFemLnaEnabled(bool enabled) {
    assert(prefs_loaded); ++lna_calls;
    if (legacy_supported) lna = enabled;
    return legacy_supported;
  }
  bool setLoRaFemPaGainEnabled(bool enabled) {
    assert(prefs_loaded); ++pa_calls;
    if (legacy_supported) pa = enabled;
    return legacy_supported;
  }
  void attachDynamicPrefs(KeyValueStore* custom) {
    assert(prefs_loaded); ++attach_calls;
    // Other upstream variants use their dynamic bridge instead of legacy FEM.
    if (!legacy_supported) {
      char value[8];
      assert(custom->getByKey("fem_rxgain", value, sizeof(value)));
      lna = atoi(value) != 0;
      assert(custom->getByKey("fem_txgain", value, sizeof(value)));
      pa = atoi(value) != 0;
    }
  }
  void setAdcMultiplier(float) {}
} board;
class MyMesh : public mesh::Mesh {
public:
  NodePrefs _prefs;
  FILESYSTEM* _fs = nullptr;
  FakeCLI _cli{&_prefs};
  FakeACL acl;
  FakeRegionMap region_map;
  int self_id = 0, default_scope = 0;
  void updateAdvertTimer() {}
  void updateFloodAdvertTimer() {}
  void begin(FILESYSTEM* fs);
};
''' + begin + r'''
void test() {
  for (int legacy = 1; legacy >= 0; --legacy) {
    for (int lna = 0; lna <= 1; ++lna) {
      for (int pa = 0; pa <= 1; ++pa) {
        FILESYSTEM fs;
        MyMesh instance;
        board = FakeBoard{};
        board.legacy_supported = legacy;
        // Opposite boot defaults prove the persisted settings are reapplied.
        board.lna = !lna; board.pa = !pa;
        instance._prefs.radio_fem_rxgain = !lna;
        instance._prefs.radio_fem_txgain = !pa;
        saved_lna = lna; saved_pa = pa; prefs_loaded = false;
        instance.begin(&fs);
        assert(board.lna == bool(lna) && board.pa == bool(pa));
        assert(board.lna_calls == 1 && board.pa_calls == 1);
        assert(board.attach_calls == 1);
      }
    }
  }
}
}
'''


def source_code():
    stream_tests = (ROOT / "test/test_companion_node_prefs/test_companion_node_prefs.cpp").read_text(
        encoding="utf-8"
    )
    streams = stream_tests[stream_tests.index("class ReplayStream"):stream_tests.index("TEST(")]
    utils = (ROOT / "src/Utils.cpp").read_text(encoding="utf-8")
    hex_methods = "\n".join(
        function(utils, marker)
        for marker in ("static uint8_t hexVal(", "bool Utils::fromHex(")
    )
    radio = (ROOT / "src/helpers/CommonRadioPrefsKeys.cpp").read_text(encoding="utf-8")
    radio_keys = "\n".join(function(radio, marker) for marker in (
        "bool CommonRadioPrefs::getByKey(", "bool CommonRadioPrefs::setByKey("))
    return r'''
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include "examples/companion_radio/NodePrefs.h"
#include "Utils.h"
#include "helpers/ConfigSerializer.cpp"
#include "helpers/DynamicConfigSerializer.cpp"
namespace mesh {
''' + hex_methods + "\n}\n" + radio_keys + "\n" + streams + room_startup_code() + r'''
int main() {
  room_startup::test();
  NodePrefs saved;
  saved.radio_fem_rxgain = 1;
  saved.radio_fem_txgain = 1;
  NodePrefs copied(saved), assigned;
  assigned = copied;
  assert(copied.radio_fem_rxgain == 1 && copied.radio_fem_txgain == 1);
  assert(assigned.radio_fem_rxgain == 1 && assigned.radio_fem_txgain == 1);

  CaptureStream output;
  assert(assigned.saveSerial(output));
  assert(output.text().find("fem_rxgain:1") != std::string::npos);
  assert(output.text().find("fem_txgain:1") != std::string::npos);
  assert(output.text().find("smart_ui:{fem_") == std::string::npos);

  NodePrefs loaded;
  ReplayStream input(output.text().c_str());
  assert(loaded.loadSerial(input));
  assert(loaded.radio_fem_rxgain == 1 && loaded.radio_fem_txgain == 1);

  // Older prefs.json generations have no FEM keys. Loading them must retain
  // the board/startup defaults instead of manufacturing a migration value.
  NodePrefs missing;
  missing.radio_fem_rxgain = 1;
  missing.radio_fem_txgain = 0;
  ReplayStream old("{name:\"old\",radio:{rxgain:0,tx:20},smart_ui:{font:1}}");
  assert(missing.loadSerial(old));
  assert(missing.radio_fem_rxgain == 1 && missing.radio_fem_txgain == 0);
  assert(missing.rx_boosted_gain == 0 && missing.tx_power_dbm == 20);

  loaded.radio_fem_rxgain = 0;
  loaded.radio_fem_txgain = 0;
  CaptureStream disabled;
  assert(loaded.saveSerial(disabled));
  assert(disabled.text().find("fem_rxgain:0") != std::string::npos);
  assert(disabled.text().find("fem_txgain:0") != std::string::npos);
  NodePrefs reloaded;
  reloaded.radio_fem_rxgain = reloaded.radio_fem_txgain = 1;
  ReplayStream disabled_input(disabled.text().c_str());
  assert(reloaded.loadSerial(disabled_input));
  assert(reloaded.radio_fem_rxgain == 0 && reloaded.radio_fem_txgain == 0);

  puts("PASS actual NodePrefs FEM fields: copy, old-key defaults, ON/OFF JSON roundtrip; room server startup legacy/dynamic FEM restore");
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix="smartui-fem-prefs-") as directory:
        folder = Path(directory)
        source = folder / "test.cpp"
        output = folder / "test_fem_prefs"
        source.write_text(source_code(), encoding="utf-8")
        includes = [ROOT, ROOT / "src", ROOT / "test/mocks"]
        compiler = shutil.which("g++") or shutil.which("clang++")
        if compiler:
            build = [compiler]
            convert = str
            execute = [str(output)]
        elif shutil.which("wsl"):
            build = ["wsl", "--exec", "g++"]

            def convert(path):
                return subprocess.check_output(
                    ["wsl", "--exec", "wslpath", "-a", str(path)], text=True
                ).strip()

            execute = ["wsl", "--exec", convert(output)]
        else:
            raise RuntimeError("Host C++ compiler required; no skipped test success")
        args = build + ["-std=c++17", "-O1", "-Wall", "-Wextra", "-Werror",
                        "-Wno-unused-parameter", "-Wno-sign-compare",
                        "-Wno-implicit-fallthrough"]
        for include in includes:
            args += ["-I", convert(include)]
        args += [convert(source), "-o", convert(output)]
        subprocess.run(args, check=True)
        subprocess.run(execute, check=True)


if __name__ == "__main__":
    main()
