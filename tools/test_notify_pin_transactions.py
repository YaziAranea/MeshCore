"""Execute production UI/CLI pin, bridge and appearance transactions on seven builds.

Actual profile macros, allowlists, UI picker/setters, DeviceSettings backend and
main.cpp effects run with recorded GPIO and flash. No hardware is accessed.
"""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile

from test_ble_pin_page import production_defines, resolved_profiles
from test_console_pin_runtime import scope
from test_notify_pins_v4 import board_defines
from test_smartui_api import setting_effects_source

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "examples/companion_radio/ui-new"


def integration(flags):
    source = (UI / "UITask.cpp").read_text(encoding="utf-8")
    main = (ROOT / "examples/companion_radio/main.cpp").read_text(encoding="utf-8")
    # Reuse the existing recording settings/board fixture, not its Ui mock or
    # assertions. Everything deciding pin validity and applying outputs below
    # is extracted independently from production.
    fixture = setting_effects_source().split("enum DeviceSettingEffect", 1)[0]
    fixture = fixture.replace("#define ENV_INCLUDE_GPS 1\n", "")
    ui_mock = scope(fixture, "struct Ui {") + " ui_task;"
    fixture = fixture.replace(ui_mock, "")
    fixture = fixture.replace("static unsigned ", "[[maybe_unused]] static unsigned ")
    fixture = fixture.replace("  NodePrefs* getNodePrefs()", """  bool quarantined=false, rescue=false;
  bool isStorageRecoveryRequired() const { return quarantined; }
  bool isCLIRescue() const { return rescue; }
  const char* getPrefsSaveErrorText() const { return "storage"; }
  NodePrefs* getNodePrefs()""")
    definitions = "#define HIGH 1\n#define LOW 0\n#define OUTPUT 1\n"
    definitions += "\n".join(f"#define {name} {value}" for name, value in flags.items()
                              if name.startswith(("DEFAULT_NOTIFY_", "P_LORA_")) or name == "LED_BUILTIN") + "\n"
    definitions += production_defines(source, flags)
    definitions += "#ifndef DEFAULT_NOTIFY_GPIO_PIN\n#define DEFAULT_NOTIFY_GPIO_PIN -1\n#endif\n"
    helpers = source[source.index("#ifndef UI_NOTIFY_ALLOW_RISKY_PINS"):
                     source.index("static uint8_t uiNextNotifyMode")]
    methods = (
        "bool UITask::isDeviceSettingsPinAllowed(", "void UITask::deviceSettingsPinOptions(",
        "int UITask::nextDeviceSettingsPin(",
        "int UITask::getNotifyLedPin(", "int UITask::getNotifyTonePin(", "int UITask::getNotifyVibePin(",
        "int UITask::getMsgAlertPin(", "int UITask::getMsgTonePin(", "int UITask::getMsgVibePin(",
        "bool UITask::isNotifyToneBridgeEnabled(", "bool UITask::isToneBridgePin(",
        "bool UITask::supportsNotifyToneBridge(",
        "void UITask::configureMsgAlertPin(", "void UITask::configureMsgTonePin(", "void UITask::configureMsgVibePin(",
        "void UITask::setNotifyLedPin(", "void UITask::setNotifyTonePin(", "void UITask::setNotifyVibePin(",
        "void UITask::cycleNotifyLedPin(", "void UITask::cycleNotifyTonePin(", "void UITask::cycleNotifyVibePin(",
        "smartui::ToneBridgeResult UITask::setNotifyToneBridgeEnabled(", "void UITask::toggleNotifyToneBridge(",
        "void UITask::stopNotifyOutputs(", "void UITask::stopMsgVibe(",
        "void UITask::applyDeviceSettingsAppearance(", "void UITask::applyDeviceSettingsPins(",
        "uint8_t UITask::getSupportedNotifyMode(",
    )
    if "PIN_MSG_ALERT" not in flags:
        methods = tuple(method for method in methods if method not in
                        ("int UITask::getMsgAlertPin(", "void UITask::configureMsgAlertPin("))
    code = definitions + fixture + r'''
#include <vector>
#include "OptionalTonePins.h"
#include "ConfirmedChoice.h"
#define NOTIFY_MODE_SILENT 0
#define NOTIFY_MODE_GPIO 1
#define NOTIFY_MODE_TONE 2
#define NOTIFY_MODE_VIBE 4
static unsigned gpio_calls;
static std::vector<int> touched;
static void pinMode(int pin,int) { CHECK(pin>=0 && pin<49); ++gpio_calls; touched.push_back(pin); }
static void digitalWrite(int pin,int) { CHECK(pin>=0 && pin<49); ++gpio_calls; touched.push_back(pin); }
static void noTone(int pin) { CHECK(pin>=0 && pin<49); ++gpio_calls; touched.push_back(pin); }
[[maybe_unused]] static void uiStopToneBridge(int,int) { ++gpio_calls; }
static constexpr int UI_OLED_FONT_M=1;
[[maybe_unused]] static int uiOledFontForRole(int font,int) { return font; }
[[maybe_unused]] static int uiOledTextSizeForRole(int) { return 1; }
struct Display { void setUiFont(int){} void setTextSize(int){} void setUiTheme(int){} };
'''
    code += '\n#pragma GCC diagnostic push\n#pragma GCC diagnostic ignored "-Wunused-function"\n'
    code += '#pragma GCC diagnostic ignored "-Wunused-parameter"\n' + helpers + '\n#pragma GCC diagnostic pop\n'
    code += r'''
struct UITask {
 NodePrefs* _node_prefs=&the_mesh.prefs;
 Display display; Display* _display=&display;
 int _msg_alert_pin=DEFAULT_NOTIFY_GPIO_PIN, _msg_tone_pin=DEFAULT_NOTIFY_TONE_PIN, _msg_vibe_pin=-1;
 uint32_t _msg_alert_until=0, _msg_tone_next=0, _msg_tone_off=0, _msg_vibe_until=0, _msg_vibe_next=0;
 uint8_t _msg_tone_step=0,_msg_tone_repeat_left=0,_msg_tone_fx_phase=0;
 uint16_t _msg_tone_fx_remaining=0,_msg_tone_test_frequency=0,_msg_tone_test_duration=700;
 uint32_t _next_refresh=0;
 bool _msg_tone_active=false,_msg_vibe_on=false;
 std::string alert;
 bool isNotifyGpioBlocked(int pin) const { return isNotifyGpioPinBlockedByBuild(pin); }
 bool commitUiPrefs(const NodePrefs& before) {
   if (!the_mesh.savePrefs()) { *_node_prefs=before; return false; } return true;
 }
 void showAlert(const char* text,int) { alert=text; }
 void startMsgTone(uint8_t=0xff) { _msg_tone_active=getMsgTonePin()>=0; }
 void triggerMsgAlert(){}
 void triggerMsgVibe(){}
 void silenceMsgTonePin(int pin) { if(pin>=0) noTone(pin); }
 void extendAutoOff(){}
 uint8_t getUiFontChoiceIndex() { return the_mesh.prefs.ui_font - 10; }
 uint8_t storedUiFontChoice(uint8_t choice) { return choice + 10; }
 uint8_t getNotifyToneVolume() const { return the_mesh.prefs.notify_tone_volume; }
 uint16_t getNotifyToneResonanceHz() const { return 3000; }
 void applyDeviceSettingsRuntime(bool battery_changed) {
   CHECK(save_ok && saves>0); ++notification_stops; battery_changes+=battery_changed;
 }
'''
    for method in methods:
        code += scope(source, method).split("{", 1)[0].strip().replace("UITask::", "") + ";\n"
    code += "} ui_task;\n" + "\n".join(scope(source, method) for method in methods)
    code += r'''
struct HomeScreen {
 enum HomePage { ALERT_LED, ALERT_TONE_PIN, ALERT_VIBE_PIN, ALERT_VOLUME, ALERT_TONE_RESONANCE, NOTIFY_PICKER };
 UITask* _task=&ui_task;
 smartui::ConfirmedChoice _notify_picker;
 uint8_t _notify_picker_page=0, _page=0;
 int notifyPickerActiveValue() const {
   return _notify_picker_page==ALERT_LED ? _task->getNotifyLedPin() :
       _notify_picker_page==ALERT_TONE_PIN ? _task->getNotifyTonePin() : _task->getNotifyVibePin();
 }
'''
    code += scope(source, "  void beginNotifyPicker(") + "\n};\n"
    code += main[main.index("enum DeviceSettingEffect"):main.index("static smartui::DeviceSettingsState readDeviceSettings(")]
    code += "\n".join(scope(main, signature) for signature in (
        "static smartui::DeviceSettingsState readDeviceSettings(", "static void writeDeviceSettings(",
        "static bool saveDeviceSettings(", "static void applyDeviceSettings(",
    ))
    code += ASSERTIONS
    return code


ASSERTIONS = r'''
static smartui::DeviceSettings service;
static smartui::DeviceSettingsCaps capabilities() {
 smartui::DeviceSettingsCaps c;
 c.sound=ui_task.getNotifyTonePin()>=0; c.unread_led=ui_task.getNotifyLedPin()>=0;
 c.notify_pins=UI_NOTIFY_GPIO_SELECT; c.tone_pin_selectable=UI_OPTIONAL_NOTIFY_TONE;
 c.bridge=ui_task.supportsNotifyToneBridge();
 c.display=true;c.colors=true;c.font_count=6;c.theme_count=6;
 c.notify_mask=ui_task.getSupportedNotifyMode();return c;
}
static void fresh() {
 the_mesh=Mesh{};ui_task=UITask{};board=Board{};
 the_mesh.prefs.notify_gpio_pin=DEFAULT_NOTIFY_GPIO_PIN;
 the_mesh.prefs.notify_tone_pin=DEFAULT_NOTIFY_TONE_PIN;
#ifdef PIN_MSG_ALERT
 ui_task.configureMsgAlertPin(DEFAULT_NOTIFY_GPIO_PIN);
#endif
 ui_task.configureMsgTonePin(DEFAULT_NOTIFY_TONE_PIN);ui_task.configureMsgVibePin(-1);
 the_mesh.persisted=the_mesh.prefs;
 saves=gpio_calls=0;touched.clear();save_ok=true;device_setting_effects=0;
 smartui::DeviceSettingsHooks hooks;
 hooks.read=readDeviceSettings;hooks.write=writeDeviceSettings;hooks.save=saveDeviceSettings;
 hooks.apply=applyDeviceSettings;hooks.caps=capabilities;
 hooks.batteryMilliVolts=[]()->uint16_t{return 3900;};hooks.adcMultiplier=[](){return 4.9f;};
 hooks.millis=[]()->uint32_t{return 100;};
 hooks.pinAllowed=[](const char* key,int pin){return ui_task.isDeviceSettingsPinAllowed(key,pin);};
 hooks.setToneBridge=[](bool on){return ui_task.setNotifyToneBridgeEnabled(on);};
 service.begin(hooks);
}
static std::string command(const std::string& text,bool writable=true) {
 char reply[480];CHECK(service.handle(text.c_str(),reply,sizeof(reply),writable));return reply;
}
static int value(const char* role) {
 return strcmp(role,"led_pin")==0 ? ui_task.getNotifyLedPin() :
     strcmp(role,"tone_pin")==0 ? ui_task.getNotifyTonePin() : ui_task.getNotifyVibePin();
}
static int savedValue(const char* role) {
 return strcmp(role,"led_pin")==0 ? the_mesh.persisted.notify_gpio_pin :
     strcmp(role,"tone_pin")==0 ? the_mesh.persisted.notify_tone_pin : the_mesh.persisted.notify_vibe_pin;
}
static void setUi(const char* role,int pin) {
 if(strcmp(role,"led_pin")==0)ui_task.setNotifyLedPin(pin);
 else if(strcmp(role,"tone_pin")==0)ui_task.setNotifyTonePin(pin);
 else ui_task.setNotifyVibePin(pin);
}
static void activeTone() {
 ui_task._msg_tone_active=true;ui_task._msg_tone_repeat_left=2;
 ui_task._msg_tone_step=3;ui_task._msg_tone_next=600;ui_task._msg_tone_off=500;
 ui_task._msg_vibe_until=400;ui_task._msg_alert_until=300;
}
static void unchangedTone() {
 CHECK(ui_task._msg_tone_active && ui_task._msg_tone_repeat_left==2);
 CHECK(ui_task._msg_tone_step==3 && ui_task._msg_tone_next==600 && ui_task._msg_tone_off==500);
 CHECK(ui_task._msg_vibe_until==400 && ui_task._msg_alert_until==300 && gpio_calls==0);
}
int main() {
 using Result=smartui::ToneBridgeResult;
 for(const char* role : {"led_pin","tone_pin","vibe_pin"}) {
   for(int pin=-1;pin<=49;++pin) {
     fresh(); const int before=value(role);
     const bool allowed=ui_task.isDeviceSettingsPinAllowed(role,pin);
     const bool capable=strcmp(role,"tone_pin")==0 ? UI_NOTIFY_GPIO_SELECT || UI_OPTIONAL_NOTIFY_TONE : UI_NOTIFY_GPIO_SELECT;
     const auto response=command(std::string("settings set ")+role+" "+std::to_string(pin));
     CHECK((response.find("OK settings set ")==0)==(capable && allowed));
     if(!allowed || !capable)CHECK(saves==0 && gpio_calls==0 && value(role)==before);
     else CHECK(value(role)==pin && savedValue(role)==pin);
     fresh();setUi(role,pin);
     if(!allowed || !capable)CHECK(saves==0 && gpio_calls==0 && value(role)==before);
     else CHECK(value(role)==pin && (pin==before || savedValue(role)==pin));
     if(allowed && capable && before!=pin) {
       fresh();save_ok=false;setUi(role,pin);
       CHECK(value(role)==before && savedValue(role)==before && saves==1);
     }
   }
   fresh();
   if(UI_NOTIFY_GPIO_SELECT || (UI_OPTIONAL_NOTIFY_TONE && strcmp(role,"tone_pin")==0)) {
     HomeScreen home;
     home.beginNotifyPicker(strcmp(role,"led_pin")==0 ? HomeScreen::ALERT_LED :
         strcmp(role,"tone_pin")==0 ? HomeScreen::ALERT_TONE_PIN : HomeScreen::ALERT_VIBE_PIN);
     CHECK(saves==0 && gpio_calls==0);
     bool off=false;
     for(unsigned i=0;i<home._notify_picker.count();++i) {
       const int choice=home._notify_picker.value(i);
       CHECK(ui_task.isDeviceSettingsPinAllowed(role,choice));off|=choice==-1;
     }
     CHECK(off==(strcmp(role,"vibe_pin")==0 || (UI_OPTIONAL_NOTIFY_TONE && strcmp(role,"tone_pin")==0)));
     int next=value(role);
     for(unsigned i=0;i<home._notify_picker.count()+1U;++i) {
       next=ui_task.nextDeviceSettingsPin(role,next);
       CHECK(ui_task.isDeviceSettingsPinAllowed(role,next));
     }
   }
 }
 // Old nRF UI repro: another role cannot acquire the active sound output.
#if !UI_OPTIONAL_NOTIFY_TONE
 fresh();const int tone=ui_task.getNotifyTonePin();
 CHECK(command(std::string("settings set vibe_pin ")+std::to_string(tone))=="ERR settings pin_conflict");
 ui_task.setNotifyVibePin(tone);CHECK(ui_task.getNotifyVibePin()==-1 && saves==0 && gpio_calls==0);
 // Existing shared normal-mode LED/tone stays intact; no blanket migration.
 ui_task.configureMsgTonePin(ui_task.getNotifyLedPin());gpio_calls=0;
 CHECK(ui_task.isDeviceSettingsPinAllowed("tone_pin",ui_task.getNotifyLedPin()));
 ui_task.setNotifyTonePin(ui_task.getNotifyLedPin());CHECK(gpio_calls==0 && saves==0);
#endif
 // UI off releases the old vibration GPIO, preserving saved notification masks.
#if UI_NOTIFY_GPIO_SELECT
 fresh(); const int vibration=ui_task.nextDeviceSettingsPin("vibe_pin",-1);
 CHECK(vibration>=0);ui_task.setNotifyVibePin(vibration);
 ui_task.setNotifyVibePin(-1);
 CHECK(ui_task.getNotifyVibePin()==-1 && the_mesh.persisted.notify_vibe_pin==-1);
 CHECK(the_mesh.prefs.notify_mode==7 && the_mesh.prefs.important_notify_mode==7);
#endif
 fresh();
#if UI_TONE_BRIDGE_PAGE == 1
 CHECK(command("settings set bridge 1")=="OK settings set key=bridge value=1");
 CHECK(ui_task.getNotifyTonePin()==DEFAULT_NOTIFY_TONE_PIN);
 CHECK(ui_task.getNotifyLedPin()==DEFAULT_NOTIFY_GPIO_PIN && ui_task.getNotifyVibePin()==-1);
 const auto count=gpio_calls, stored=saves;
 CHECK(command("api set bridge 1")=="OK api set key=bridge value=1");
 CHECK(gpio_calls==count && saves==stored);
 CHECK(command("api set bridge 0")=="OK api set key=bridge value=0");
 for(bool initial : {false,true}) {
   fresh();if(initial)CHECK(ui_task.setNotifyToneBridgeEnabled(true)==Result::OK);
   gpio_calls=saves=0;activeTone();save_ok=false;
   const double latitude=the_mesh.prefs.node_lat, longitude=the_mesh.prefs.node_lon;
   CHECK(ui_task.setNotifyToneBridgeEnabled(!initial)==Result::STORAGE);
   CHECK(ui_task.isNotifyToneBridgeEnabled()==initial && saves==1);
   CHECK(the_mesh.prefs.node_lat==latitude && the_mesh.prefs.node_lon==longitude);
   unchangedTone();
 }
 // Every owner of either fixed bridge output must be explicitly reassigned.
 for(bool led : {false,true}) for(int pin : {DEFAULT_NOTIFY_TONE_PIN,DEFAULT_NOTIFY_TONE_BRIDGE_PIN}) {
   fresh();if(led)ui_task.configureMsgAlertPin(pin);else ui_task.configureMsgVibePin(pin);
   gpio_calls=saves=0;activeTone();
   CHECK(command("api set bridge 1")=="ERR api pin_conflict");
   CHECK(command("settings set bridge 1")=="ERR settings pin_conflict");
   CHECK(!ui_task.isNotifyToneBridgeEnabled() && saves==0);unchangedTone();
   ui_task.toggleNotifyToneBridge();CHECK(ui_task.alert.find("LED/")!=std::string::npos);unchangedTone();
 }
#else
 CHECK(command("settings set bridge 1")=="ERR settings unsupported");
 CHECK(ui_task.setNotifyToneBridgeEnabled(true)==Result::UNSUPPORTED && saves==0 && gpio_calls==0);
#endif
#ifdef HELTEC_T114
 fresh();
 for(const char* change : {"settings set tone_pin 18","settings set led_pin 13","settings set vibe_pin 35"})
   CHECK(command(change).find("OK settings set ")==0);
 gpio_calls=saves=0;activeTone();
 CHECK(command("settings set bridge 1")=="ERR settings pin_conflict");
 CHECK(ui_task.getNotifyLedPin()==13 && ui_task.getNotifyTonePin()==18 && ui_task.getNotifyVibePin()==35);
 CHECK(the_mesh.persisted.notify_gpio_pin==13 && the_mesh.persisted.notify_vibe_pin==35 && saves==0);unchangedTone();
#endif
 // Actual main.cpp hooks dispatch appearance-only changes without GPIO/audio.
 for(const char* change : {"settings set ui_font 2","settings set ui_theme 2","settings set ui_top_color 2",
     "settings set ui_bottom_color 2","settings set backlight_timeout 2","settings set msg_popup 0"}) {
   fresh();activeTone();CHECK(command(change).find("OK settings set ")==0);
   CHECK(saves==1);unchangedTone();
   fresh();activeTone();save_ok=false;CHECK(command(change)=="ERR settings storage");unchangedTone();
   fresh();activeTone();CHECK(command(change,false)=="ERR settings readonly");CHECK(saves==0);unchangedTone();
 }
 printf("PASS %u UI/CLI pin, picker/off, bridge ownership/rollback and appearance isolation checks\n",checks);
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix="smartui-pin-transactions-") as directory:
        out = Path(directory)
        compiler = shutil.which("g++") or shutil.which("clang++")
        options = ["-std=c++17", "-O1", "-Wall", "-Wextra"]
        if os.environ.get("SMARTUI_TEST_SANITIZE") == "1":
            options += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie"]
        for env, flags in resolved_profiles(include_headless=True):
            flags = dict(flags)
            for macro, variant in (("HELTEC_T096", "heltec_t096"), ("HELTEC_T114", "heltec_t114"),
                                   ("PROMICRO", "promicro")):
                if macro in flags:
                    flags.update({key: value for key, value in board_defines(variant, env).items()
                                  if key in ("PIN_LED", "LED_BUILTIN", "LED_STATE_ON")})
            cpp = out / (env + ".cpp")
            cpp.write_text(integration(flags), encoding="utf-8")
            exe = out / env
            paths = [cpp, ROOT / "examples/companion_radio/DeviceSettings.cpp"]
            includes = [UI, ROOT / "examples/companion_radio", ROOT / "src"]
            if compiler:
                build = [compiler, *options, *["-I" + str(p) for p in includes], *map(str, paths), "-o", str(exe)]
                execute = [str(exe)]
            elif os.name == "nt":
                def linux(path):
                    return subprocess.check_output(["wsl", "--exec", "wslpath", "-a", str(path)], text=True).strip()
                build = ["wsl", "--exec", "g++", *options, *["-I" + linux(p) for p in includes],
                         *map(linux, paths), "-o", linux(exe)]
                execute = ["wsl", "--exec", linux(exe)]
            else:
                raise RuntimeError("Host C++ compiler required; no skipped test success")
            print(env, flush=True)
            subprocess.run(build, check=True)
            subprocess.run(execute, check=True)


if __name__ == "__main__":
    main()
