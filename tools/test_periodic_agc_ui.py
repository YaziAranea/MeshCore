"""Host-check actual AGC preference serialization, UI transaction and menu gates.

No radio, display or hardware behavior is simulated here. Those are separate
checks: this verifies the optional setting stays OFF for old preferences,
persists only on success, and is hidden when the runtime radio lacks support.
"""
from pathlib import Path
import argparse
import shutil
import subprocess

from test_compact_menu_cleanup import code as menu_code
from test_ui_sessions_v006 import function, run_cpp

ROOT = Path(__file__).resolve().parents[1]


def transaction_code(source):
    methods = '\n'.join(function(source, marker) for marker in (
        'bool UITask::supportsPeriodicAgcReset()',
        'bool UITask::isPeriodicAgcResetEnabled()',
        'bool UITask::togglePeriodicAgcReset()'))
    activation = function(source, '  void activateCompactSetting(uint8_t page)')
    fast_path = activation[activation.index('{')+1:activation.index('#if UI_SMART_B11_EXTRAS == 1')]
    assert 'HomePage::AGC_RESET' in fast_path
    assert 'NodePrefs' not in fast_path
    assert 'HomePage::AGC_RESET' not in activation[activation.index('#if UI_SMART_B11_EXTRAS == 1'):]
    return r'''
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
static int checks=0;
#define CHECK(x) do { ++checks; if(!(x)) { fprintf(stderr,"line %d: %s\n",__LINE__,#x); exit(1); } } while(0)
struct NodePrefs { uint8_t agc_reset_enabled=0; double node_lat=12.5, node_lon=64.5; };
// Intentionally exposes no radio-reset or RX/standby API. The setting may
// persist a flag, but must never synchronously manipulate hardware.
struct Mesh {
  NodePrefs* prefs=nullptr;
  bool supported=true, save_ok=true;
  uint8_t persisted=0;
  int saves=0;
  const char* save_error="Сбой записи";
  const char* getPrefsSaveErrorText() const { return save_error; }
  bool supportsPeriodicAgcReset() const { return supported; }
  bool savePrefs() {
    ++saves;
    prefs->node_lat=90;
    prefs->node_lon=180;
    if(save_ok) persisted=prefs->agc_reset_enabled;
    return save_ok;
  }
} the_mesh;
struct UITask {
  NodePrefs* _node_prefs=nullptr;
  unsigned _next_refresh=500, alerts=0;
  std::string message;
  void showAlert(const char* text, unsigned) { ++alerts; message=text; }
  bool supportsPeriodicAgcReset() const;
  bool isPeriodicAgcResetEnabled() const;
  bool togglePeriodicAgcReset();
};
''' + methods + r'''
#define UI_PERIODIC_AGC_RESET_PAGE 1
struct HomePage { enum : uint8_t { AGC_RESET, OTHER }; };
struct Menu {
  UITask* _task;
  unsigned generic_snapshot_attempts=0;
  void activateCompactSetting(uint8_t page) {
''' + fast_path + r'''
    ++generic_snapshot_attempts;
  }
};
int main() {
  NodePrefs prefs;
  UITask task;
  task._node_prefs=the_mesh.prefs=&prefs;
  CHECK(!task.isPeriodicAgcResetEnabled());
  CHECK(task.supportsPeriodicAgcReset());
  CHECK(task.togglePeriodicAgcReset());
  CHECK(prefs.agc_reset_enabled==1 && the_mesh.persisted==1);
  CHECK(task.isPeriodicAgcResetEnabled());
  CHECK(the_mesh.saves==1 && task._next_refresh==0);
  CHECK(task.message=="AGC: ВКЛ, 60 с");
  CHECK(task.togglePeriodicAgcReset());
  CHECK(prefs.agc_reset_enabled==0 && the_mesh.persisted==0);
  CHECK(the_mesh.saves==2 && task.message=="AGC: ВЫКЛ");
  for(uint8_t before: {uint8_t(0), uint8_t(1)}) {
    prefs.agc_reset_enabled=the_mesh.persisted=before;
    prefs.node_lat=12.5; prefs.node_lon=64.5;
    task._next_refresh=500;
    the_mesh.save_ok=false;
    CHECK(!task.togglePeriodicAgcReset());
    CHECK(prefs.agc_reset_enabled==before && the_mesh.persisted==before);
    CHECK(prefs.node_lat==12.5 && prefs.node_lon==64.5);
    CHECK(task._next_refresh==500);
    CHECK(task.message==the_mesh.save_error);
  }
  const int saves=the_mesh.saves;
  const unsigned alerts=task.alerts;
  the_mesh.supported=false;
  CHECK(!task.supportsPeriodicAgcReset());
  CHECK(!task.isPeriodicAgcResetEnabled());
  CHECK(!task.togglePeriodicAgcReset());
  CHECK(the_mesh.saves==saves && task.alerts==alerts);
  the_mesh.supported=true;
  task._node_prefs=nullptr;
  CHECK(!task.isPeriodicAgcResetEnabled());
  CHECK(!task.togglePeriodicAgcReset());
  CHECK(the_mesh.saves==saves && task.alerts==alerts);
  // Execute the production early dispatch: no full NodePrefs snapshot,
  // generic undo, or second persistence transaction for the AGC setting.
  task._node_prefs=&prefs;
  the_mesh.save_ok=true;
  prefs.agc_reset_enabled=0;
  Menu menu{&task};
  menu.activateCompactSetting(HomePage::AGC_RESET);
  CHECK(menu.generic_snapshot_attempts==0 && the_mesh.saves==saves+1);
  CHECK(prefs.agc_reset_enabled==1 && the_mesh.persisted==1);
  the_mesh.save_ok=false;
  the_mesh.save_error="Нет места";
  menu.activateCompactSetting(HomePage::AGC_RESET);
  CHECK(menu.generic_snapshot_attempts==0 && the_mesh.saves==saves+2);
  CHECK(prefs.agc_reset_enabled==1 && the_mesh.persisted==1);
  CHECK(task.message=="Нет места");
  menu.activateCompactSetting(HomePage::OTHER);
  CHECK(menu.generic_snapshot_attempts==1 && the_mesh.saves==saves+2);
  printf("PASS %d actual AGC UI transaction checks\n", checks);
}
'''


def agc_menu_code(source, sound, extras, flat):
    generated = menu_code(source, sound, extras)
    generated = '#include <initializer_list>\n#define UI_PERIODIC_AGC_RESET_PAGE 1\n' + generated
    if flat:
        generated = generated.replace('#define UI_COMPACT_SETTINGS_MENU 1',
                                      '#define UI_COMPACT_SETTINGS_MENU 0')
    generated = generated.replace('struct Task {', '''struct Task {
  bool agc_supported=true;
  bool supportsPeriodicAgcReset() const { return agc_supported; }''')
    # Reuse actual navigation methods without coupling this test to the old
    # cleanup test's assertions about pages that flat menus intentionally hide.
    generated = generated[:generated.index('int main()')]
    return generated + r'''
int main() {
  Menu menu;
  const uint8_t system_group=UI_SOUND_SETTINGS_GROUP ? 4 : 3;
  assert(!strcmp(menu.compactSettingsGroupName(system_group), "Система"));
  assert(menu.compactSettingsPageAt(system_group,0)==HomePage::BLUETOOTH);
  assert(menu.compactSettingsPageAt(system_group,1)==HomePage::AGC_RESET);
  int seen=0;
  for(uint8_t group=0;group<menu.COMPACT_SETTINGS_GROUP_COUNT;++group) {
    for(uint8_t row=0;row<menu.compactSettingsItemCount(group);++row) {
      if(menu.compactSettingsPageAt(group,row)==HomePage::AGC_RESET) {
        assert(group==system_group);
        ++seen;
      }
    }
  }
  assert(seen==1 && menu.isSettingsItem(HomePage::AGC_RESET));
  menu._settings_open=false;
  assert(!menu.isPageVisibleInCurrentMenu(HomePage::AGC_RESET));
  menu._settings_open=true;
  assert(menu.isPageVisibleInCurrentMenu(HomePage::AGC_RESET));
  const uint8_t supported_count=menu.compactSettingsItemCount(system_group);
  menu.task.agc_supported=false;
  assert(!menu.isSettingsItem(HomePage::AGC_RESET));
  assert(menu.compactSettingsItemCount(system_group)+1==supported_count);
  for(uint8_t group=0;group<menu.COMPACT_SETTINGS_GROUP_COUNT;++group)
    for(uint8_t row=0;row<menu.compactSettingsItemCount(group);++row)
      assert(menu.compactSettingsPageAt(group,row)!=HomePage::AGC_RESET);
  assert(!menu.isPageVisibleInCurrentMenu(HomePage::AGC_RESET));
  menu._settings_open=false;
  assert(!menu.isPageVisibleInCurrentMenu(HomePage::AGC_RESET));
  puts("PASS actual AGC compact/flat menu: System only, supported once, unsupported hidden");
}
'''


def prefs_code():
    stream_tests = (ROOT/'test/test_companion_node_prefs/test_companion_node_prefs.cpp').read_text(encoding='utf-8')
    streams = stream_tests[stream_tests.index('class ReplayStream'):stream_tests.index('TEST(')]
    utils = (ROOT/'src/Utils.cpp').read_text(encoding='utf-8')
    hex_methods = '\n'.join(function(utils, marker) for marker in (
        'static uint8_t hexVal(', 'bool Utils::fromHex('))
    return r'''
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include "examples/companion_radio/NodePrefs.h"
#include "Utils.h"
#include "helpers/ConfigSerializer.cpp"
namespace mesh {
''' + hex_methods + '\n}\n' + streams + r'''
int main() {
  NodePrefs saved;
  assert(saved.agc_reset_enabled==0);
  strcpy(saved.node_name,"AGC prefs check");
  saved.agc_reset_enabled=1;
  NodePrefs copied(saved), assigned;
  assigned=copied;
  assert(copied.agc_reset_enabled==1 && assigned.agc_reset_enabled==1);
  copied.agc_reset_enabled=0;
  saved.agc_reset_enabled=0;
  CaptureStream output;
  assert(assigned.saveSerial(output));
  assert(output.text().find("agc_reset:1")!=std::string::npos);
  NodePrefs loaded;
  ReplayStream input(output.text().c_str());
  assert(loaded.loadSerial(input));
  assert(loaded.agc_reset_enabled==1);
  NodePrefs legacy;
  ReplayStream old("{name:\"old\",smart_ui:{font:1}}");
  assert(legacy.loadSerial(old));
  assert(legacy.agc_reset_enabled==0 && legacy.ui_font==1);
  loaded.agc_reset_enabled=0;
  CaptureStream disabled;
  assert(loaded.saveSerial(disabled));
  assert(disabled.text().find("agc_reset:0")!=std::string::npos);
  NodePrefs reloaded;
  reloaded.agc_reset_enabled=1;
  ReplayStream disabled_input(disabled.text().c_str());
  assert(reloaded.loadSerial(disabled_input));
  assert(reloaded.agc_reset_enabled==0);
  puts("PASS actual NodePrefs + ConfigSerializer: default OFF, legacy OFF, copy, ON/OFF roundtrip");
}
'''


def run_prefs(code, out):
    out.mkdir(parents=True, exist_ok=True)
    cpp = out/'agc_prefs.cpp'
    cpp.write_text(code, encoding='utf-8')
    includes = [ROOT, ROOT/'src', ROOT/'test/mocks']
    if shutil.which('g++'):
        prefix = ['g++']
        convert = str
        execute = []
    else:
        prefix = ['wsl', '--exec', 'g++']
        def convert(path):
            return subprocess.check_output(['wsl', '--exec', 'wslpath', '-a', str(path)], text=True).strip()
        execute = ['wsl', '--exec']
    exe = convert(out/'agc_prefs')
    args = prefix + ['-std=c++17', '-O1', '-Wall', '-Wextra', '-Wno-unused-parameter',
                     '-Wno-sign-compare', '-Wno-implicit-fallthrough']
    for include in includes:
        args += ['-I', convert(include)]
    subprocess.run(args + [convert(cpp), '-o', exe], check=True)
    return subprocess.check_output(execute + [exe], text=True, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT/'qa_outputs/periodic-agc-ui')
    args = parser.parse_args()
    out = args.out.resolve()
    source = (ROOT/'examples/companion_radio/ui-new/UITask.cpp').read_text(encoding='utf-8')
    print(run_cpp(transaction_code(source), out, 'agc_transaction'), end='')
    print(run_prefs(prefs_code(), out), end='')
    for sound in (False, True):
        for extras in (False, True):
            for flat in (False, True):
                name = f'agc_menu_sound{int(sound)}_extras{int(extras)}_flat{int(flat)}'
                print(run_cpp(agc_menu_code(source, sound, extras, flat), out, name), end='')


if __name__ == '__main__':
    main()
