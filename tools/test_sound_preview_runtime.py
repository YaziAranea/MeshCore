"""Exercise production melody audition and scheduler without hardware writes."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
from test_console_pin_runtime import scope

ROOT = Path(__file__).resolve().parents[1]


def integration():
    source = (ROOT / "examples/companion_radio/ui-new/UITask.cpp").read_text(encoding="utf-8")
    tones = source[source.index("struct NotifyToneDef {"):source.index("static uint16_t uiTone8BitArpeggioFrequency(")]
    signatures = (
        "smartui::SoundPreviewResult UITask::previewSavedMelody(",
        "void UITask::silenceMsgTonePin(",
        "uint16_t UITask::getMsgToneOnMillis(",
        "void UITask::startMsgTone(",
        "void UITask::messageToneHandler(",
    )
    return r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
#include "DeviceSettings.h"
#include "ui-new/UiTiming.h"
#define PIN_MSG_TONE 13
#define PIN_MSG_ALERT 35
#define PIN_MSG_ALERT_INACTIVE 0
#define UI_NOTIFY_GPIO_SELECT 1
#define UI_TONE_BRIDGE_PAGE 0
#define UI_TONE_HIGH_DRIVE_PAGE 0
#define UI_TONE_8BIT_PAGE 0
#define UI_SMART_B12_TONE_LIST 1
#define NOTIFY_TONE_COUNT 31
#define UI_IMPORTANT_NOTIFY_TONE_PLAYS 2
#define UI_NOTIFY_TONE_PLAYS 2
#define UI_IMPORTANT_NOTIFY_TONE_REPEAT_GAP_MS 200
#define UI_NOTIFY_TONE_REPEAT_GAP_MS 200
#define LOW 0
#define HIGH 1
#define OUTPUT 1
static uint32_t clock_ms = 1;
static uint32_t millis() { return clock_ms; }
static std::vector<unsigned> tones_played;
static unsigned pin_writes;
static void tone(int pin, unsigned frequency) { assert(pin == 13); tones_played.push_back(frequency); }
static void noTone(int) {}
static void pinMode(int, int) {}
static void digitalWrite(int, int) { ++pin_writes; }
static bool isNotifyGpioPinAllowed(int pin) { return pin == 13; }
static bool isBoardLedPin(int pin) { return pin == 35; }
static void setBoardLedPinOff(int) {}
struct NodePrefs {
  uint8_t notify_tone_id = 18, notify_tone_system_id = 18;
  uint8_t sound_quiet = 1, notify_mode = 1, volume = 10;
  bool muted = false;
};
struct UITask {
  NodePrefs prefs;
  NodePrefs* _node_prefs = &prefs;
  uint32_t _msg_tone_next = 0, _msg_tone_off = 0, _msg_vibe_until = 0, _msg_alert_until = 0;
  uint8_t _msg_tone_step = 0, _msg_tone_repeat_left = 0, _msg_tone_fx_phase = 0, _msg_tone_id_active = 0;
  uint16_t _msg_tone_fx_remaining = 0, _msg_tone_test_frequency = 0, _msg_tone_test_duration = 700;
  int _msg_tone_pin = 13, resolved_pin = 13, vibe_pin = -1;
  bool _msg_tone_active = false, _important_notify_active = false, blocked = false;
  bool areNotificationsMuted() const { return prefs.muted; }
  bool areBoardLedsEnabled() const { return true; }
  bool isNotifyGpioBlocked(int) const { return blocked; }
  int getMsgTonePin() const { return resolved_pin; }
  int getMsgAlertPin() const { return 35; }
  int getMsgVibePin() const { return vibe_pin; }
  uint8_t getNotifyToneVolume() const { return prefs.volume; }
  smartui::SoundPreviewResult previewSavedMelody();
  void silenceMsgTonePin(int);
  uint16_t getMsgToneOnMillis(uint16_t, uint16_t) const;
  void startMsgTone(uint8_t tone_id = 0xff);
  void messageToneHandler();
};
''' + tones + "\n" + "\n".join(scope(source, signature) for signature in signatures) + r'''
int main() {
  using Result = smartui::SoundPreviewResult;
  UITask task;
  const NodePrefs before = task.prefs;
  assert(task.previewSavedMelody() == Result::STARTED);
  assert(task._msg_tone_active && task._msg_tone_repeat_left == 0);
  assert(tones_played.size() == 1 && tones_played.front() == 880);
  assert(task.previewSavedMelody() == Result::BUSY);
  for (unsigned elapsed = 0; task._msg_tone_active && elapsed < 20000; ++elapsed) {
    ++clock_ms; task.messageToneHandler();
  }
  assert(!task._msg_tone_active);
  unsigned expected = 0;
  for (const auto frequency : msg_tone_swans_freqs) if (frequency > 1) ++expected;
  assert(tones_played.size() == expected); // One full saved melody, no repeat.
  assert(memcmp(&before, &task.prefs, sizeof(before)) == 0);
  const unsigned sounds_before = tones_played.size(), writes_before = pin_writes;
  task.prefs.muted = true;
  assert(task.previewSavedMelody() == Result::MUTED);
  task.prefs.muted = false; task._important_notify_active = true;
  assert(task.previewSavedMelody() == Result::BUSY);
  task._important_notify_active = false; task._msg_vibe_until = clock_ms + 100;
  assert(task.previewSavedMelody() == Result::BUSY);
  task._msg_vibe_until = 0; task.blocked = true;
  assert(task.previewSavedMelody() == Result::PIN_CONFLICT);
  task.blocked = false; task.resolved_pin = 35;
  assert(task.previewSavedMelody() == Result::PIN_CONFLICT);
  task.resolved_pin = 13; task.vibe_pin = 13;
  assert(task.previewSavedMelody() == Result::PIN_CONFLICT);
  assert(tones_played.size() == sounds_before && pin_writes == writes_before);
  task.vibe_pin = -1;
  assert(task.previewSavedMelody() == Result::STARTED);
  task.prefs.muted = true;
  task.messageToneHandler();
  assert(!task._msg_tone_active); // Muting during audition still stops sound.
  puts("PASS production melody preview: quiet mask, one full melody, no preference changes, mute/busy/pins");
}
'''


def main():
    compiler = shutil.which("g++") or shutil.which("clang++")
    with tempfile.TemporaryDirectory(prefix="smartui-sound-preview-") as directory:
        source = Path(directory) / "preview.cpp"
        source.write_text(integration(), encoding="utf-8")
        includes = ROOT / "examples/companion_radio"
        for optimization in ("-O1", "-Os", "-Ofast"):
            output = Path(directory) / ("preview" + optimization)
            flags = ["-std=c++17", "-Wall", "-Wextra", "-Werror", optimization]
            if os.environ.get("SMARTUI_TEST_SANITIZE") == "1":
                flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie"]
            if compiler:
                build = [compiler, *flags, "-I" + str(includes), str(source), "-o", str(output)]
                execute = [str(output)]
            elif os.name == "nt":
                def linux(path):
                    return subprocess.check_output(["wsl", "--exec", "wslpath", "-a", str(path)], text=True).strip()
                build = ["wsl", "--exec", "g++", *flags, "-I" + linux(includes), linux(source), "-o", linux(output)]
                execute = ["wsl", "--exec", linux(output)]
            else:
                raise RuntimeError("Host C++ compiler required; no skipped test success")
            subprocess.run(build, check=True)
            subprocess.run(execute, check=True)


if __name__ == "__main__":
    main()
