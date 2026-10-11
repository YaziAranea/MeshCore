"""Run production optional ESP32 tone handlers with recorded GPIO/PWM calls.

Uses each board's actual OptionalTonePins allowlist. No electrical assumptions,
radio, display refresh timing or physical buzzer verification is simulated.
"""
from pathlib import Path
import tempfile

from test_console_pin_runtime import scope
from test_headless_runtime import integration as headless_integration
from test_ui_sessions_v006 import run_cpp

ROOT = Path(__file__).resolve().parents[1]
BOARDS = (
    ("v3", "HELTEC_LORA_V3", 35, 1),
    ("v43", "HELTEC_LORA_V4", 35, 1),
    ("r8", "HELTEC_V4_R8_OLED", 46, 1),
    ("paper", "HELTEC_WIRELESS_PAPER", 18, 0),
)


def integration(board, alert, selectable):
    source = (ROOT / "examples/companion_radio/ui-new/UITask.cpp").read_text(encoding="utf-8")
    helpers = source[source.index("#ifndef UI_NOTIFY_ALLOW_RISKY_PINS"):
                     source.index("static uint8_t uiNextNotifyMode")]
    tones = source[source.index("struct NotifyToneDef {"):
                   source.index("static uint16_t uiTone8BitArpeggioFrequency(")]
    methods = (
        "bool UITask::isDeviceSettingsPinAllowed(",
        "void UITask::deviceSettingsPinOptions(",
        "int UITask::getMsgTonePin(", "int UITask::getNotifyTonePin(",
        "int UITask::getNotifyLedPin(", "int UITask::getNotifyVibePin(",
        "int UITask::getMsgVibePin(", "void UITask::configureMsgVibePin(",
        "void UITask::configureMsgTonePin(", "void UITask::setNotifyTonePin(",
        "uint8_t UITask::getSupportedNotifyMode(", "uint8_t UITask::getNotifyMode(",
        "uint8_t UITask::getImportantNotifyMode(", "uint8_t UITask::getNotifyToneVolume(",
        "void UITask::silenceMsgTonePin(", "uint16_t UITask::getMsgToneOnMillis(",
        "void UITask::startMsgTone(", "void UITask::messageToneHandler(",
        "smartui::SoundPreviewResult UITask::previewSavedMelody(",
    )
    flags = f'''#define {board} 1
#define PIN_MSG_ALERT {alert}
#define DEFAULT_NOTIFY_GPIO_PIN {alert}
#define UI_NOTIFY_GPIO_SELECT {selectable}
'''
    if board == "HELTEC_LORA_V4":
        flags += "#define HELTEC_LORA_V4_OLED 1\n"
    return flags + r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#define UI_OPTIONAL_NOTIFY_TONE 1
#include "../DeviceSettings.h"
#include "UiTiming.h"
#include "OptionalTonePins.h"
#define PIN_MSG_TONE -1
#define DEFAULT_NOTIFY_TONE_PIN -1
#define PIN_MSG_ALERT_INACTIVE 0
#define UI_TONE_BRIDGE_PAGE 0
#define UI_TONE_HIGH_DRIVE_PAGE 0
#define UI_TONE_8BIT_PAGE 0
#define UI_SMART_B12_TONE_LIST 1
#define NOTIFY_TONE_COUNT 31
#define NOTIFY_MODE_SILENT 0
#define NOTIFY_MODE_GPIO 1
#define NOTIFY_MODE_TONE 2
#define NOTIFY_MODE_VIBE 4
#define UI_IMPORTANT_NOTIFY_TONE_PLAYS 2
#define UI_NOTIFY_TONE_PLAYS 1
#define UI_IMPORTANT_NOTIFY_TONE_REPEAT_GAP_MS 200
#define UI_NOTIFY_TONE_REPEAT_GAP_MS 200
#define LOW 0
#define HIGH 1
#define OUTPUT 1
struct Io { int pin, value; char kind; };
static std::vector<Io> io;
static unsigned checks;
#define CHECK(x) do { ++checks; assert(x); } while (0)
static uint32_t clock_ms = 100;
static uint32_t millis() { return clock_ms; }
static void record(int pin, int value, char kind) {
  CHECK(pin >= 0 && pin <= 48);
  io.push_back({pin, value, kind});
}
static void tone(int pin, unsigned frequency) { record(pin, frequency, 'T'); }
static void noTone(int pin) { record(pin, 0, 'N'); }
static void pinMode(int pin, int value) { record(pin, value, 'M'); }
static void digitalWrite(int pin, int value) { record(pin, value, 'D'); }
struct NodePrefs {
  int8_t notify_tone_pin = -1, notify_vibe_pin = -1;
  uint8_t notify_tone_id = 0, notify_tone_system_id = 0, notify_tone_volume = 10;
  uint8_t notify_mode = 3, important_notify_mode = 3;
};
''' + '\n#pragma GCC diagnostic push\n#pragma GCC diagnostic ignored "-Wunused-function"\n#pragma GCC diagnostic ignored "-Wunused-parameter"\n' + helpers + '\n#pragma GCC diagnostic pop\n' + tones + r'''
struct UITask {
  NodePrefs prefs, persisted;
  NodePrefs* _node_prefs = &prefs;
  uint32_t _msg_tone_next = 0, _msg_tone_off = 0, _msg_vibe_until = 0;
  uint32_t _msg_vibe_next = 0, _msg_alert_until = 0;
  uint8_t _msg_tone_step = 0, _msg_tone_repeat_left = 0, _msg_tone_fx_phase = 0, _msg_tone_id_active = 0;
  uint16_t _msg_tone_fx_remaining = 0, _msg_tone_test_frequency = 0, _msg_tone_test_duration = 700;
  int _msg_tone_pin = -1, _msg_vibe_pin = -1, alert_pin = PIN_MSG_ALERT;
  bool _msg_tone_active = false, _important_notify_active = false, _msg_vibe_on = false;
  bool muted = false, board_led = true, save_ok = true;
  unsigned saves = 0;
  bool areNotificationsMuted() const { return muted; }
  bool areBoardLedsEnabled() const { return board_led; }
  bool isNotifyGpioBlocked(int pin) const { return isNotifyGpioPinBlockedByBuild(pin); }
  bool isBoardLedPin(int pin) const { return pin == PIN_MSG_ALERT; }
  void setBoardLedPinOff(int pin) { digitalWrite(pin, LOW); }
  bool isNotifyToneBridgeEnabled() const { return false; }
  int getMsgAlertPin() const { return alert_pin; }
  void showAlert(const char*, int) {}
  bool commitUiPrefs(const NodePrefs& before) {
    ++saves;
    if (!save_ok) { prefs = before; return false; }
    persisted = prefs; return true;
  }
  bool isDeviceSettingsPinAllowed(const char*, int) const;
  void deviceSettingsPinOptions(const char*, char*, size_t) const;
  int getMsgTonePin() const;
  int getNotifyTonePin() const;
  int getNotifyLedPin() const;
  int getNotifyVibePin() const;
  int getMsgVibePin() const;
  void configureMsgVibePin(int);
  void configureMsgTonePin(int);
  void setNotifyTonePin(int);
  uint8_t getSupportedNotifyMode() const;
  uint8_t getNotifyMode() const;
  uint8_t getImportantNotifyMode() const;
  uint8_t getNotifyToneVolume() const;
  void silenceMsgTonePin(int);
  uint16_t getMsgToneOnMillis(uint16_t, uint16_t) const;
  void startMsgTone(uint8_t = 0xff);
  void messageToneHandler();
  smartui::SoundPreviewResult previewSavedMelody();
};
''' + "\n".join(scope(source, method) for method in methods) + r'''
static unsigned countIo(int pin, char kind, int value) {
  unsigned count = 0;
  for (const auto& event : io)
    if (event.pin == pin && event.kind == kind && event.value == value) ++count;
  return count;
}
int main() {
  UITask task;
  task.configureMsgTonePin(-1);
  task.silenceMsgTonePin(-1);
  task.startMsgTone(); task.messageToneHandler();
  CHECK(io.empty() && task.getMsgTonePin() == -1 && task.getNotifyTonePin() == -1);
  CHECK(task.getSupportedNotifyMode() == NOTIFY_MODE_GPIO);
  CHECK(task.getNotifyMode() == 1 && task.getImportantNotifyMode() == 1);
  CHECK(task.prefs.notify_mode == 3 && task.prefs.important_notify_mode == 3);
  CHECK(task.isDeviceSettingsPinAllowed("tone_pin", -1));
  CHECK(!task.isDeviceSettingsPinAllowed("tone_pin", PIN_MSG_ALERT));
  CHECK(!task.isDeviceSettingsPinAllowed("tone_pin", -2));
  CHECK(!task.isDeviceSettingsPinAllowed("tone_pin", 127));
  char options[88]; task.deviceSettingsPinOptions("tone_pin", options, sizeof(options));
  CHECK(std::string(options).find("-1,") == 0);
  std::vector<int> choices;
  for (int pin : smartui::optional_tone_gpio_pins) {
    if (pin < 0) continue;
    CHECK(task.isDeviceSettingsPinAllowed("tone_pin", pin));
    task.configureMsgTonePin(pin);
    CHECK(task.getNotifyTonePin() == pin && task.prefs.notify_tone_pin == pin);
    choices.push_back(pin);
  }
  CHECK(choices.size() >= 2);
  const int first = choices.front(), second = choices.back();

  // Active buzzer pattern drives level pulses; passive melody uses tone PWM.
  task.configureMsgTonePin(first); io.clear();
  task.startMsgTone(0);
  CHECK(countIo(first, 'D', HIGH) == 1 && countIo(first, 'T', 1) == 0);
  CHECK(task._msg_tone_active);
  clock_ms += 90; task.messageToneHandler();
  CHECK(countIo(first, 'D', LOW) >= 1);
  task.configureMsgTonePin(first); io.clear(); task.startMsgTone(19);
  CHECK(countIo(first, 'T', 1568) == 1);
  task.configureMsgTonePin(second);
  CHECK(countIo(first, 'N', 0) >= 1 && countIo(first, 'D', LOW) >= 1);
  CHECK(task.getNotifyTonePin() == second && !task._msg_tone_active);
  CHECK(task._msg_tone_repeat_left == 0 && task._msg_tone_off == 0);
  io.clear(); task.startMsgTone(19); task.configureMsgTonePin(-1);
  CHECK(countIo(second, 'N', 0) >= 1 && countIo(second, 'D', LOW) >= 1);
  CHECK(task.getNotifyTonePin() == -1 && !task._msg_tone_active);
  io.clear(); task.startMsgTone(19); task.messageToneHandler(); CHECK(io.empty());

  // Bad stored pins fail closed; they must never select the board LED.
  for (int invalid : {-128, 127, PIN_MSG_ALERT}) {
    task._msg_tone_pin = -1; io.clear(); task.configureMsgTonePin(invalid);
    CHECK(task.getNotifyTonePin() == -1 && task.prefs.notify_tone_pin == -1 && io.empty());
  }
  task.alert_pin = first;
  CHECK(!task.isDeviceSettingsPinAllowed("tone_pin", first));
  task.configureMsgTonePin(first); CHECK(task.getNotifyTonePin() == -1);
  task.alert_pin = PIN_MSG_ALERT;
  task._msg_vibe_pin = first;
  CHECK(!task.isDeviceSettingsPinAllowed("tone_pin", first));
  task.configureMsgTonePin(first); CHECK(task.getNotifyTonePin() == -1);
  task._msg_vibe_pin = -1;
#if UI_NOTIFY_GPIO_SELECT
  // Boot/apply configures tone before vibration; saved conflicts must be safe.
  task.prefs.notify_tone_pin = task.prefs.notify_vibe_pin = first;
  task.configureMsgTonePin(task.prefs.notify_tone_pin);
  task.configureMsgVibePin(task.prefs.notify_vibe_pin);
  CHECK(task.getNotifyTonePin() < 0 || task.getNotifyTonePin() != task.getNotifyVibePin());
  task.configureMsgVibePin(-1);
#else
  CHECK(!task.isDeviceSettingsPinAllowed("vibe_pin", first));
  CHECK(!task.isDeviceSettingsPinAllowed("led_pin", first));
#endif

  task.configureMsgTonePin(first); io.clear(); task.muted = true;
  task.startMsgTone(19); CHECK(io.empty());
  task.muted = false; task.startMsgTone(19); task.muted = true; task.messageToneHandler();
  CHECK(!task._msg_tone_active && countIo(first, 'D', LOW) >= 1);
  task.muted = false; task.prefs.notify_tone_volume = 1;
  CHECK(task.getMsgToneOnMillis(120, 1568) == 12);
  task.startMsgTone(19); clock_ms += 12; task.messageToneHandler();
  CHECK(countIo(first, 'D', LOW) >= 2);
  task.configureMsgTonePin(-1); task.setNotifyTonePin(first);
  CHECK(task.persisted.notify_tone_pin == first && task.getNotifyTonePin() == first);
  task.save_ok = false; task.setNotifyTonePin(-1);
  CHECK(task.prefs.notify_tone_pin == first && task.persisted.notify_tone_pin == first);
  CHECK(task.getNotifyTonePin() == first);
  task.save_ok = true; task.setNotifyTonePin(-1);
  CHECK(task.persisted.notify_tone_pin == -1 && task.getNotifyTonePin() == -1);
  printf("PASS %u optional tone runtime checks: off, pulses/PWM, pins, masks, mute, rollback\n", checks);
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix="smartui-optional-tone-") as directory:
        for name, macro, alert, selectable in BOARDS:
            print(name + ": " + run_cpp(integration(macro, alert, selectable),
                                       Path(directory), name), end="", flush=True)
        for paper in (True, False):
            name = "paper_timing" if paper else "oled_timing"
            print(run_cpp(scheduling_policy(paper), Path(directory), name), end="", flush=True)
    verify_display_wiring()


def scheduling_policy(paper):
    """Exercise the actual whole UI loop, with deterministic output stubs."""
    source = (ROOT / "examples/companion_radio/ui-new/UITask.cpp").read_text(encoding="utf-8")
    code = headless_integration().split("\nint main() {", 1)[0]
    if not paper:
        code = code.replace("#define HELTEC_WIRELESS_PAPER 1", "")
    code = "#define UI_OPTIONAL_NOTIFY_TONE 1\n#define UI_WIRELESS_PAPER_BIG_CLOCK 1\n" + code
    code = code.replace("bool shouldDeferPaperDisplay() const;", """
  bool shouldDeferPaperDisplay() const;
  bool shouldHoldLightSleepLock() const;
  bool hasActiveComposeSession() const { return false; }
  uint32_t _display_wake_lock_until=0;
""")
    code += "\n" + scope(source, "bool UITask::shouldHoldLightSleepLock() const") + "\n"
    return code + r'''
int main() {
  now=130000;
  DisplayDriver display;
  UITask task; task._display=&display; task._msg_tone_active=true;
  CHECK(task.shouldHoldLightSleepLock());
#ifdef HELTEC_WIRELESS_PAPER
  CHECK(task.shouldDeferPaperDisplay());
  for (int tick=0; tick<10; ++tick) { now+=1000; task.loop(); }
  CHECK(display.frames_started==0 && display.frames_ended==0);
  CHECK(task._next_refresh==0); // Due frame stays pending, never starts halfway.
  CHECK(task.tones==10 && task.vibes==10 && task.important==10 && task.smart==10);
  CHECK(task.screen.polls==10 && task.next_batt_chck>now);
  CHECK(task.shutdowns==0);
  task._msg_tone_active=false;
  CHECK(!task.shouldDeferPaperDisplay() && !task.shouldHoldLightSleepLock());
  task.loop();
  CHECK(display.frames_started==1 && display.frames_ended==1 && task.screen.renders==1);
  CHECK(task._next_refresh>now);
  task._msg_tone_active=true; task.mv=3100;
  for (int tick=0; tick<3; ++tick) { now+=1000; task.loop(); }
  CHECK(task.shutdowns==1 && task.stopped==1 && !task._msg_tone_active);
  CHECK(display.frames_started==2 && display.frames_ended==2); // Safety frame still completes.
  puts("PASS production Paper loop: deferred complete frames, notification/battery service, sleep lock, safety stop");
#else
  CHECK(!task.shouldDeferPaperDisplay());
  task.loop();
  CHECK(display.frames_started==1 && display.frames_ended==1 && task.screen.renders==1);
  task._msg_tone_active=false;
  CHECK(!task.shouldHoldLightSleepLock());
  puts("PASS production non-Paper loop: render during tone retained, active tone holds sleep lock");
#endif
}
'''


def verify_display_wiring():
    source = (ROOT / "examples/companion_radio/ui-new/UITask.cpp").read_text(encoding="utf-8")
    loop = scope(source, "void UITask::loop()")
    guard = "if (_display != NULL && _display->isOn() && !shouldDeferPaperDisplay())"
    frame = scope(loop, guard)
    assert frame.index("startFrame();") < frame.index("endFrame();")
    assert "return;" not in frame
    assert loop.index("messageToneHandler();") < loop.index(guard)
    assert loop.index(guard) < loop.index("const uint16_t shutdownThreshold")
    for signature in ("void UITask::displayRecoverHandler()",
                      "void UITask::handlePendingPopupWake()",
                      "bool UITask::attachDisplay("):
        method = scope(source, signature)
        assert method.index("shouldDeferPaperDisplay()") < method.index("turnOn();")
    for signature in ("bool UITask::handleRawButtonWakeWhenDark()",
                      "void UITask::handleButtonWakeLatch()", "char UITask::checkDisplayOn("):
        method = scope(source, signature)
        assert method.index("shouldDeferPaperDisplay()") < method.index("stopNotifyOutputs();") < method.index("turnOn();")
    shutdown = scope(source, "void UITask::shutdown(")
    assert shutdown.index("stopNotifyOutputs();") < shutdown.index("_display->turnOn();")
    main = (ROOT / "examples/companion_radio/main.cpp").read_text(encoding="utf-8")
    retry = scope(main, "void loop()")
    assert retry.index("!ui_task.shouldDeferPaperDisplay()") < retry.index("++paper_attach_attempts;") < retry.index("display.begin()")
    print("PASS Paper display retry/wake/shutdown guards are wired before blocking I/O")


if __name__ == "__main__":
    main()
