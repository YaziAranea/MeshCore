"""Compile the production compact-menu input body with recording host stubs.

Bounded navigation/confirmation tests only: no display or hardware simulation.
"""
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "qa_outputs/experimental-settings-flow"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source = (ROOT / "examples/companion_radio/ui-new/UITask.cpp").read_text(encoding="utf-8")
    start = source.index("  bool handleCompactSettingsInput(char c)")
    end = source.index("\n  }\n#endif", start) + len("\n  }")
    body = source[start:end]
    helper = (ROOT / "examples/companion_radio/ui-new/ConfirmedChoice.h").as_posix()
    code = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define UI_SMART_B11_EXTRAS 1
#define UI_ADC_MULTIPLIER_PAGE 1
#define KEY_PREV 'p'
#define KEY_LEFT 'l'
#define KEY_NEXT 'n'
#define KEY_RIGHT 'r'
#define KEY_ENTER 'e'
struct NodePrefs { uint8_t favorite_setting_1=1, favorite_setting_2=2, favorite_setting_3=3; };
struct Mesh { bool ok=true; int saves=0; bool savePrefs() { ++saves; return ok; } } the_mesh;
struct Task { void showAlert(const char*,int) {} void runHardwareTestStep(int) {} } task;
struct HomeScreen {
 enum HomePage { SETTINGS, ADC, ADC_RESET, FAVORITE_PICKER, FAVORITE_SLOT_1,
  FAVORITE_SLOT_2,FAVORITE_SLOT_3,CONTROLS_HELP,NOTIFY_PICKER,HARDWARE_TEST };
 static constexpr uint8_t COMPACT_SETTINGS_GROUP_COUNT=7;
 bool _settings_open=true, _adc_edit=false, _adc_reset_confirm=false;
 uint8_t _page=SETTINGS, _compact_settings_depth=0,_compact_settings_cursor=0;
 uint8_t _compact_root_cursor=0,_compact_settings_group=0,_compact_group_cursors[8]={};
 uint8_t _favorite_picker_slot=0,_controls_help_page=0,_notify_picker_page=0,_hardware_test_step=0;
 smartui::ConfirmedChoice _favorite_picker,_notify_picker;
 NodePrefs prefs; NodePrefs* _node_prefs=&prefs; Task* _task=&task;
 int resets=0, undos=0, activations=0;
 uint8_t favoriteIdAt(uint8_t slot) { return slot==0?prefs.favorite_setting_1:slot==1?prefs.favorite_setting_2:prefs.favorite_setting_3; }
 void setFavoriteId(uint8_t slot,uint8_t value) { if(slot==0)prefs.favorite_setting_1=value;else if(slot==1)prefs.favorite_setting_2=value;else prefs.favorite_setting_3=value; }
 void rememberSettingUndo(const NodePrefs&,uint8_t) { ++undos; }
 void restoreAdcDefaultConfirmed() { ++resets; }
 void applyNotifyPickerChoice(int16_t) {}
 void cancelAdcEdit() { _adc_edit=false; }
 uint8_t compactSettingsItemCount(uint8_t) { return 6; }
 uint8_t compactSettingsPageAt(uint8_t,uint8_t) { return SETTINGS; }
 void activateCompactSetting(uint8_t) { ++activations; }
'''
    code = '#include "' + helper + '"\n' + code + body + "\n};\n"
    code += r'''
static int checks=0;
#define CHECK(expr) do { ++checks; if(!(expr)) { fprintf(stderr,"failed line %d: %s\n",__LINE__,#expr); exit(1); } } while(0)
int main() {
 HomeScreen h;
 h._compact_settings_cursor=2; h._compact_root_cursor=2; h._compact_group_cursors[2]=3;
 h.handleCompactSettingsInput(KEY_ENTER);
 CHECK(h._compact_settings_group==2 && h._compact_settings_cursor==3 && h._compact_settings_depth==1);
 h.handleCompactSettingsInput(KEY_NEXT); CHECK(h._compact_group_cursors[2]==4);
 h._compact_settings_cursor=6; h.handleCompactSettingsInput(KEY_ENTER);
 CHECK(h._compact_settings_depth==0 && h._compact_settings_cursor==2 && h._compact_root_cursor==2);
 h.handleCompactSettingsInput(KEY_ENTER); CHECK(h._compact_settings_cursor==4);
 h._page=HomeScreen::ADC;
 CHECK(h.handleCompactSettingsInput(KEY_PREV)); CHECK(h._page==HomeScreen::SETTINGS && h.resets==0);
 h._page=HomeScreen::ADC; CHECK(!h.handleCompactSettingsInput(KEY_ENTER));
 h._adc_edit=true; CHECK(!h.handleCompactSettingsInput(KEY_PREV)); CHECK(h.resets==0 && h._adc_edit);
 h._adc_edit=false; h._page=HomeScreen::ADC_RESET; h._adc_reset_confirm=false;
 h.handleCompactSettingsInput(KEY_ENTER); CHECK(h.resets==0 && h._page==HomeScreen::SETTINGS);
 h._page=HomeScreen::ADC_RESET; h.handleCompactSettingsInput(KEY_PREV);
 CHECK(h._adc_reset_confirm && h.resets==0);
 h.handleCompactSettingsInput(KEY_ENTER); CHECK(h.resets==1 && !h._adc_reset_confirm && h._page==HomeScreen::SETTINGS);
 for(int slot=0;slot<3;++slot) {
   h._favorite_picker_slot=slot; uint8_t before=h.favoriteIdAt(slot);
   h._page=HomeScreen::FAVORITE_PICKER; h._favorite_picker.add(before); h._favorite_picker.add(8); h._favorite_picker.begin(before);
   h.handleCompactSettingsInput(KEY_PREV); CHECK(h._favorite_picker.cursor()==h._favorite_picker.count());
   h.handleCompactSettingsInput(KEY_ENTER); CHECK(h.favoriteIdAt(slot)==before && h._page==HomeScreen::SETTINGS);
   h._page=HomeScreen::FAVORITE_PICKER; h._favorite_picker.add(before); h._favorite_picker.add(8); h._favorite_picker.begin(before);
   h.handleCompactSettingsInput(KEY_NEXT); CHECK(h.favoriteIdAt(slot)==before);
   h.handleCompactSettingsInput(KEY_ENTER); CHECK(h.favoriteIdAt(slot)==8 && h._page==HomeScreen::SETTINGS);
 }
 CHECK(h.undos==3 && the_mesh.saves==3);
 h._favorite_picker_slot=0; h._page=HomeScreen::FAVORITE_PICKER;
 h._favorite_picker.add(8); h._favorite_picker.add(10); h._favorite_picker.begin(8);
 h.handleCompactSettingsInput(KEY_NEXT); the_mesh.ok=false; h.handleCompactSettingsInput(KEY_ENTER);
 CHECK(h.prefs.favorite_setting_1==8 && h.undos==3 && the_mesh.saves==4);
 h._page=HomeScreen::CONTROLS_HELP; h.handleCompactSettingsInput(KEY_PREV); CHECK(h._controls_help_page==7);
 h.handleCompactSettingsInput(KEY_NEXT); CHECK(h._controls_help_page==0);
 h.handleCompactSettingsInput(KEY_ENTER); CHECK(h._page==HomeScreen::SETTINGS);
 h._compact_settings_depth=0; h._compact_settings_cursor=7;
 h.handleCompactSettingsInput(KEY_ENTER); CHECK(!h._settings_open && h._compact_settings_cursor==2);
 CHECK(!h.handleCompactSettingsInput(KEY_NEXT));
 printf("PASS %d actual compact-menu C++ flow checks\n", checks);
}
'''
    cpp = OUT / "settings_flow.cpp"
    cpp.write_text(code, encoding="utf-8")
    if shutil.which("g++"):
        binary = OUT / "settings_flow"
        subprocess.run(["g++", "-std=c++17", "-Os", str(cpp), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
    else:
        linux_root = subprocess.check_output(["wsl", "--exec", "wslpath", "-a", ROOT.as_posix()]).decode().strip()
        # Translate the absolute helper include for WSL compilation.
        cpp.write_text(code.replace(ROOT.as_posix(), linux_root), encoding="utf-8")
        linux_out = linux_root + "/qa_outputs/experimental-settings-flow"
        subprocess.run(["wsl", "--exec", "g++", "-std=c++17", "-Os", linux_out+"/settings_flow.cpp", "-o", linux_out+"/settings_flow"], check=True)
        subprocess.run(["wsl", "--exec", linux_out+"/settings_flow"], check=True)


if __name__ == "__main__":
    main()
