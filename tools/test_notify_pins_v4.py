"""Bounded production-C++ notification output regression tests.

Extracts real pin selection and notification/tone handlers. GPIO/tone calls are
recorded; single-ended modes use the three nRF52 boards' actual pin definitions.
Does not emulate PWM electronics, optional bridge/8-bit/high-drive effects, BLE
delivery or the complete UITask. Reminder policy has its own separate tests.
"""
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "examples/companion_radio/ui-new/UITask.cpp"
OUT = ROOT / "qa_outputs/notify-pins-v4"
BOARDS = {
    "promicro": "ProMicro_ra62_companion_radio_ble",
    "heltec_t096": "Heltec_t096_companion_radio_ble_femon",
    "heltec_t114": "Heltec_t114_companion_radio_ble",
}


def function(source, signature):
    start = source.index(signature)
    end = source.index("\n}", start) + 2
    return source[start:end]


def board_defines(board, env):
    text = (ROOT / "variants" / board / "platformio.ini").read_text(encoding="utf-8")
    matches = list(re.finditer(r"(?m)^\[([^]]+)\]\s*$", text))
    sections = {m[1]: text[m.end():matches[i + 1].start() if i + 1 < len(matches) else len(text)]
                for i, m in enumerate(matches)}
    seen = set()

    def collect(name):
        if name in seen:
            return ""
        seen.add(name)
        body = sections.get(name, "")
        parent = re.search(r"(?m)^extends\s*=\s*([^\r\n]+)", body)
        inherited = "" if not parent else "".join(collect(p.strip()) for p in parent[1].split(","))
        return inherited + "\n" + body

    flags = {}
    for line in collect("env:" + env).splitlines():
        if line.lstrip().startswith(";"):
            continue
        match = re.search(r"-D\s+([A-Z_][A-Z_0-9]*)(?:=([^;\s]+))?", line)
        if match:
            flags[match[1]] = match[2] or "1"
    variant = (ROOT / "variants" / board / "variant.h").read_text(encoding="utf-8")
    for name in ("LED_BUILTIN", "PIN_LED", "LED_STATE_ON"):
        match = re.search(r"(?m)^#define\s+" + name + r"\s+([^\r\n/]+)", variant)
        if match:
            flags[name] = match[1].strip()
    return flags


def build_code(source, flags, during_tone):
    defaults = dict(re.findall(r"#ifndef (UI_[A-Z_0-9]+)\s+#define \1\s+([^\r\n]+)", source))
    names = {
        "PROMICRO", "HELTEC_T096", "HELTEC_T114", "PIN_LED", "LED_BUILTIN", "LED_STATE_ON",
        "P_LORA_TX_LED", "PIN_MSG_ALERT", "PIN_MSG_ALERT_ACTIVE", "PIN_MSG_TONE",
        "DEFAULT_NOTIFY_GPIO_PIN", "DEFAULT_NOTIFY_TONE_PIN", "UI_NOTIFY_GPIO_SELECT",
        "UI_BLOCK_BOARD_LED_NOTIFY", "UI_NOTIFY_ALLOW_RISKY_PINS", "UI_OFFLINE_DM_LED_PAGE",
        "UI_BLE_READ_SUPPRESSES_IMPORTANT_VISUAL_REPEAT", "UI_IMPORTANT_NOTIFY_VISUAL_BURST_MS",
        "UI_IMPORTANT_NOTIFY_TONE_SERIES_ONCE", "UI_IMPORTANT_NOTIFY_LED_REPEAT_MS",
        "UI_IMPORTANT_NOTIFY_TONE_REPEAT_MS", "UI_OFFLINE_IMPORTANT_NOTIFY_BURST_COUNT",
        "UI_OFFLINE_IMPORTANT_NOTIFY_BURST_GAP_MS", "UI_IMPORTANT_NOTIFY_TONE_PLAYS",
        "UI_IMPORTANT_NOTIFY_TONE_REPEAT_GAP_MS", "UI_NOTIFY_TONE_PLAYS", "UI_NOTIFY_TONE_REPEAT_GAP_MS",
        "UI_NOTIFY_LED_OVERRIDES_BOARD_LED_SETTING", "UI_SMART_B12_TONE_LIST",
    }
    definitions = "#define HIGH 1\n#define LOW 0\n#define OUTPUT 1\n"
    definitions += "\n".join(f"#define {name} {flags.get(name, defaults.get(name, '0'))}"
                             for name in sorted(names) if name in flags or name.startswith("UI_")) + "\n"
    definitions += f"#define UI_IMPORTANT_NOTIFY_GPIO_DURING_TONE {during_tone}\n"
    definitions += "#define UI_TONE_BRIDGE_PAGE 0\n#define UI_TONE_8BIT_PAGE 0\n#define UI_TONE_HIGH_DRIVE_PAGE 0\n"
    definitions += "#define MSG_ALERT_ON_MILLIS 450\n#define PIN_MSG_ALERT_INACTIVE (!PIN_MSG_ALERT_ACTIVE)\n"
    node = (ROOT / "examples/companion_radio/NodePrefs.h").read_text(encoding="utf-8")
    for line in node.splitlines():
        if line.startswith("#define NOTIFY_MODE_") or line.startswith("#define NOTIFY_TONE_COUNT"):
            definitions += line + "\n"
    methods = [
        "int UITask::getMsgAlertPin() const", "int UITask::getMsgTonePin() const",
        "void UITask::configureMsgTonePin(int pin)", "uint8_t UITask::getSupportedNotifyMode() const",
        "uint8_t UITask::getNotifyMode() const", "uint8_t UITask::getImportantNotifyMode() const",
        "unsigned long UITask::nextImportantNotifyDelay(", "void UITask::beginImportantNotify(",
        "void UITask::importantNotifyHandler()", "void UITask::triggerMsgAlert()",
        "void UITask::messageAlertHandler()", "void UITask::silenceMsgTonePin(",
        "uint16_t UITask::getMsgToneOnMillis(", "void UITask::startMsgTone(",
        "void UITask::messageToneHandler()",
    ]
    # Compile the same GPIO allow/block lists and role defaults as production.
    helpers = source[source.index("#ifndef UI_NOTIFY_ALLOW_RISKY_PINS"):
                     source.index("static uint8_t uiNextNotifyMode")]
    tones = source[source.index("struct NotifyToneDef"):
                   source.index("static uint16_t uiTone8BitArpeggioFrequency")]
    code = r'''
#include <cassert>
#include <cstdio>
#include <cstdint>
#include <vector>
#include <initializer_list>
'''+ definitions + r'''
struct Io { int pin, value; bool pwm; };
static std::vector<Io> io;
static uint32_t now=100;
static unsigned long millis() { return now; }
static void pinMode(int,int) {}
static void digitalWrite(int pin,int value) { io.push_back({pin,value,false}); }
static void noTone(int pin) { io.push_back({pin,0,true}); }
static void tone(int pin,int freq) { io.push_back({pin,freq,true}); }
struct NodePrefs {
  int8_t notify_tone_pin=DEFAULT_NOTIFY_TONE_PIN;
  uint8_t notify_mode=3, important_notify_mode=3, notify_tone_system_id=24;
  uint8_t notify_tone_dm_id=24, notify_tone_mention_id=24, notify_tone_volume=10;
};
enum { UI_MSG_FLAG_NONE=0, UI_MSG_FLAG_DIRECT=1, UI_MSG_FLAG_MENTION=2, UI_MSG_FLAG_IMPORTANT=4 };
'''+ (ROOT / "examples/companion_radio/ui-new/UiTiming.h").read_text(encoding="utf-8").replace("#pragma once", "") + helpers + tones + r'''
class UITask {
public:
  NodePrefs prefs;
  NodePrefs* _node_prefs=&prefs;
  int _msg_alert_pin=DEFAULT_NOTIFY_GPIO_PIN, _msg_tone_pin=DEFAULT_NOTIFY_TONE_PIN;
  bool muted=false, connected=false, board_leds=true, offline_led=true, ble_led=true;
  bool _important_notify_active=false, _important_notify_tone_started=false;
  bool _important_notify_tone_repeat_suppressed=false, _important_notify_visual_repeat_suppressed=false;
  uint32_t _important_notify_generation=0;
  bool _msg_tone_active=false;
  unsigned long _msg_alert_until=0, _msg_tone_next=0, _msg_tone_off=0;
  unsigned long _important_notify_led_next=0, _important_notify_tone_next=0;
  unsigned long _important_notify_vibe_next=0, _important_notify_visual_until=0;
  uint8_t _important_msg_flags=0, _important_notify_led_burst_step=0;
  uint8_t _important_notify_tone_burst_step=0, _important_notify_vibe_burst_step=0;
  uint8_t _msg_tone_step=0, _msg_tone_fx_phase=0, _msg_tone_repeat_left=0, _msg_tone_id_active=0;
  uint16_t _msg_tone_fx_remaining=0, _msg_tone_test_frequency=0, _msg_tone_test_duration=700;
  bool hasConnection() const { return connected; }
  bool areNotificationsMuted() const { return muted; }
  bool areBoardLedsEnabled() const { return board_leds; }
  bool isBoardLedPin(int pin) const { return pin==PIN_LED; }
  bool isNotifyGpioBlocked(int pin) const { return isNotifyGpioPinBlockedByBuild(pin); }
  bool isOfflineDmLedEnabled() const { return offline_led; }
  bool isBleDmLedEnabled() const { return ble_led; }
  int getMsgVibePin() const { return -1; }
  uint8_t getNotifyToneVolume() const { return prefs.notify_tone_volume; }
  void setBoardLedPinOff(int pin) { digitalWrite(pin,!LED_STATE_ON); }
  void clearImportantNotify() { _important_notify_active=false; }
  void triggerMsgVibe() { assert(false); }
  int getMsgAlertPin() const;
  int getMsgTonePin() const;
  void configureMsgTonePin(int);
  uint8_t getSupportedNotifyMode() const;
  uint8_t getNotifyMode() const;
  uint8_t getImportantNotifyMode() const;
  unsigned long nextImportantNotifyDelay(uint8_t&,unsigned long) const;
  void beginImportantNotify(uint8_t,uint32_t,bool);
  void importantNotifyHandler();
  void triggerMsgAlert();
  void messageAlertHandler();
  void silenceMsgTonePin(int);
  uint16_t getMsgToneOnMillis(uint16_t,uint16_t) const;
  void startMsgTone(uint8_t id=0xff);
  void messageToneHandler();
  // Assert the production loop's output-handler ordering separately in Python.
  void outputLoop() { messageAlertHandler(); messageToneHandler(); importantNotifyHandler(); }
};
'''+ "\n".join(function(source, method) for method in methods) + r'''
static int sounds() { int n=0; for(const auto& e:io) n+=e.pwm && e.value>1; return n; }
static int lights(int pin) { int n=0; for(const auto& e:io) n+=!e.pwm && e.pin==pin && e.value==PIN_MSG_ALERT_ACTIVE; return n; }
int main() {
  unsigned checks=0;
  assert(DEFAULT_NOTIFY_TONE_PIN!=DEFAULT_NOTIFY_GPIO_PIN);
  for(int pin : {-128,-1,100,127,PIN_LED,DEFAULT_NOTIFY_GPIO_PIN,DEFAULT_NOTIFY_TONE_PIN}) {
    now=100; UITask t; t._msg_tone_pin=pin;
    const int expected=isNotifyGpioPinAllowed(pin) && !isNotifyGpioPinBlockedByBuild(pin) ? pin : DEFAULT_NOTIFY_TONE_PIN;
    assert(t.getMsgTonePin()==expected);
    t.configureMsgTonePin(pin);
    assert(t.getMsgTonePin()==expected && t.prefs.notify_tone_pin==expected);
    assert(t.prefs.notify_mode==3 && t.prefs.important_notify_mode==3);
    ++checks;
  }
  // Every allowed, unblocked user pin survives; no blanket pin migration.
  for(int pin : notify_gpio_pins) if(!isNotifyGpioPinBlockedByBuild(pin)) {
    UITask t; t.configureMsgTonePin(pin);
    assert(t.getMsgTonePin()==pin && t.prefs.notify_tone_pin==pin); ++checks;
  }
  for(bool shared : {false,true}) for(uint8_t mode : {0,1,2,3}) {
    now=100; UITask t; t.prefs.important_notify_mode=mode;
    if(shared) t.configureMsgTonePin(DEFAULT_NOTIFY_GPIO_PIN);
    io.clear(); t.beginImportantNotify(UI_MSG_FLAG_DIRECT,1,false);
    assert((sounds()>0)==bool(mode&NOTIFY_MODE_TONE));
    assert((lights(t.getMsgAlertPin())>0)==bool(mode&NOTIFY_MODE_GPIO));
    assert(t.getImportantNotifyMode()==mode); ++checks;
    if(mode&NOTIFY_MODE_TONE) {
      assert(t._msg_tone_active);
      // An already-active melody and its inter-play gap retain the shared pin.
      for(int stage : {0,1}) {
        if(stage) { t._msg_tone_next=now+UI_IMPORTANT_NOTIFY_TONE_REPEAT_GAP_MS; t._msg_tone_off=0; }
        t._important_notify_led_next=0; io.clear(); t.outputLoop();
        if(shared) assert(io.empty());
        else if((mode&NOTIFY_MODE_GPIO) && UI_IMPORTANT_NOTIFY_GPIO_DURING_TONE) assert(lights(t.getMsgAlertPin())==1);
        else assert(!lights(t.getMsgAlertPin()));
        ++checks;
      }
      if(mode&NOTIFY_MODE_GPIO) {
        t._msg_tone_active=false; t._important_notify_led_next=0;
        t._important_notify_tone_next=now+UI_IMPORTANT_NOTIFY_TONE_REPEAT_MS;
        io.clear(); t.importantNotifyHandler();
        assert(lights(t.getMsgAlertPin())==1); ++checks;
      }
    }
  }
  for(bool muted : {false,true}) for(bool offline_led : {false,true}) {
    now=100; UITask t; t.muted=muted; t.offline_led=offline_led;
    io.clear(); t.beginImportantNotify(UI_MSG_FLAG_DIRECT,1,false);
    assert((sounds()>0)==!muted);
    assert((lights(t.getMsgAlertPin())>0)==(!muted && offline_led)); ++checks;
  }
  // Reach an actual inter-play gap through the production melody state machine.
  // A due visual reminder must not steal a shared pin during that silent gap.
  now=100; UITask shared; shared.configureMsgTonePin(DEFAULT_NOTIFY_GPIO_PIN);
  shared.beginImportantNotify(UI_MSG_FLAG_DIRECT,1,false);
  bool real_gap_seen=false;
  for(unsigned elapsed=0; shared._msg_tone_active && elapsed<100000; ++elapsed) {
    ++now; shared._important_notify_led_next=0; io.clear(); shared.outputLoop();
    if(shared._msg_tone_active && shared._msg_tone_step==0 &&
       shared._msg_tone_repeat_left==0 && smartui::deadlinePending(now,(uint32_t)shared._msg_tone_next)) {
      real_gap_seen=true;
      ++now; io.clear(); shared.outputLoop(); assert(io.empty()); ++checks;
    }
  }
  assert(real_gap_seen && !shared._msg_tone_active);
  io.clear(); shared._important_notify_led_next=0; shared.importantNotifyHandler();
  assert(lights(shared.getMsgAlertPin())==1); ++checks;
  printf("PASS %u actual C++ notification pin/collision cases\n",checks);
}
'''
    return code


def build_harness(source, flags, during_tone=1):
    """Reusable production handlers and recording fixture, without a test main."""
    return build_code(source, flags, during_tone).split("\nint main() {", 1)[0]


def run_cpp(code, stem, out_dir=OUT):
    """Compile/run a caller's bounded C++ main on native g++ or Windows WSL."""
    assert re.fullmatch(r"[a-zA-Z0-9_-]+", stem), "test artifact stem must be a simple name"
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cpp = out_dir / (stem + ".cpp")
    cpp.write_text(code, encoding="utf-8")
    native = shutil.which("g++")
    linux = None if native else subprocess.check_output(
        ["wsl", "--exec", "wslpath", "-a", out_dir.resolve().as_posix()], text=True).strip()
    compiler = [native] if native else ["wsl", "--exec", "g++"]
    path = str(cpp) if native else linux + "/" + cpp.name
    binary = str(out_dir / stem) if native else linux + "/" + stem
    result = subprocess.run(compiler + ["-std=c++17", "-O2", "-Wall", "-Wextra", "-Wno-unused-function", "-Wno-unused-parameter", path, "-o", binary],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError(result.stderr)
    return subprocess.check_output([binary] if native else ["wsl", "--exec", binary],
                                   text=True, encoding="utf-8", errors="replace")


def main():
    source = UI.read_text(encoding="utf-8")
    loop = source[source.index("void UITask::loop()") :]
    assert loop.index("messageAlertHandler();") < loop.index("messageToneHandler();") < loop.index("importantNotifyHandler();")
    for board, env in BOARDS.items():
        flags = board_defines(board, env)
        for during_tone in (0,1):
            stem = f"{board}_{during_tone}"
            print(run_cpp(build_code(source, flags, during_tone), stem), end="")
    print("PASS three real board pin profiles, both GPIO-during-tone policies")


if __name__ == "__main__":
    main()
