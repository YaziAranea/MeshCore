"""Run production notification/melody handlers against a deterministic clock.

Uses real profile flags and melody tables, not a Python copy of the scheduler.
GPIO, BLE connection state and display navigation are host stubs. This does
not claim hardware PWM, radio delivery, sleep-current or full-device testing.
"""
from pathlib import Path
import re

from test_notify_pins_v4 import UI, ROOT, BOARDS, board_defines, build_harness, function, run_cpp

OUT = ROOT / "qa_outputs/important-notify-v4"


def harness(source, flags):
    code = build_harness(source, flags)
    names = (
        "UI_IMPORTANT_NOTIFY_BLE_SMART_DELAY_MS", "UI_IMPORTANT_NOTIFY_LOCAL_ONLY_WHEN_DISCONNECTED",
        "UI_BLE_READ_SUPPRESSES_IMPORTANT_TONE_REPEAT", "UI_BLE_READ_SUPPRESSES_IMPORTANT_VISUAL_REPEAT",
        "UI_SMART_NOTIFY_WATCHER_CANCEL_PENDING_ON_BLE_READ", "UI_SMART_NOTIFY_WATCHER_FINISH_ACTIVE_ON_BLE_READ",
        "UI_BLE_READ_FINISHES_IMPORTANT_NOTIFY",
    )
    # These are explicit in every tested public profile; fail if a flag vanishes.
    code = "\n".join(f"#define {n} {flags[n]}" for n in names) + "\n" + code
    code = code.replace("class UITask {", "struct MsgPreviewScreen { bool hasUnreadPreviews() { return false; } };\nclass UITask {")
    code = code.replace("  void clearImportantNotify() { _important_notify_active=false; }", r'''
  void clearImportantNotify();
  void stopNotifyOutputs();
  void finishImportantNotify(bool);
  void clearBleSmartNotify();
  void scheduleBleSmartNotify(uint8_t);
  void bleSmartNotifyHandler();
  void startImportantNotify(uint8_t);
  void msgRead(int,bool);
  void stopMsgVibe() {}
  void gotoHomeScreen() {}
  void* curr=nullptr; void* msg_preview=nullptr;
  int _msgcount=0;
  uint8_t _ble_smart_notify_flags=0;
  bool _ble_smart_notify_read_zero_seen=false;
  unsigned long _ble_smart_notify_due=0, _next_refresh=0;
''')
    code = code.replace("messageToneHandler(); importantNotifyHandler();", "messageToneHandler(); bleSmartNotifyHandler(); importantNotifyHandler();")
    methods = (
        "void UITask::clearImportantNotify()", "void UITask::stopNotifyOutputs()",
        "void UITask::finishImportantNotify(", "void UITask::clearBleSmartNotify()",
        "void UITask::scheduleBleSmartNotify(", "void UITask::bleSmartNotifyHandler()",
        "void UITask::startImportantNotify(", "void UITask::msgRead(int msgcount, bool",
    )
    code += "\n" + "\n".join(function(source, m) for m in methods)
    return code


MAIN = r'''
static unsigned checks=0;
static void tick(UITask& t, uint32_t duration) {
  while(duration--) { ++now; t.outputLoop(); }
}
static int notes(int id) {
  int result=0; for(int i=0;i<notify_tones[id].steps;++i) result+=notify_tones[id].freqs[i]>0;
  return result;
}
static int playedNotes() {
  int result=0;
  for(const auto& event:io)
    result += (event.pwm && event.value>1) ||
      (!event.pwm && event.pin==DEFAULT_NOTIFY_TONE_PIN && event.value==HIGH);
  return result;
}
static void fresh(UITask& t,int id=19) {
  t.prefs.important_notify_mode=NOTIFY_MODE_TONE;
  t.prefs.notify_tone_system_id=id;
  t.prefs.notify_tone_dm_id=id;
  t.prefs.notify_tone_mention_id=id;
  io.clear();
}
int main() {
  static_assert(UI_IMPORTANT_NOTIFY_TONE_SERIES_ONCE==0);
  static_assert(UI_IMPORTANT_NOTIFY_TONE_REPEAT_MS==120000UL);
  static_assert(UI_IMPORTANT_NOTIFY_TONE_PLAYS==2);
  // All actual melodies: exactly two complete plays per series, none at the
  // old 3-second burst gap, then another series at 2 and 4 minutes.
  for(int id=0;id<notify_tone_count;++id) {
    now=100; UITask t; fresh(t,id); t.startImportantNotify(UI_MSG_FLAG_DIRECT);
    assert(t._important_notify_active && t._msg_tone_active);
    auto due=t._important_notify_tone_next;
    tick(t,500);
    t.beginImportantNotify(UI_MSG_FLAG_DIRECT,false); // duplicate delivery
    t.beginImportantNotify(UI_MSG_FLAG_MENTION,false); // merged active notification
    assert(t._important_notify_tone_next==due);
    tick(t,119499);
    assert(!t._msg_tone_active && playedNotes()==notes(id)*2);
    tick(t,1); assert(t._msg_tone_active && t._important_notify_tone_next==240100);
    tick(t,119999); assert(!t._msg_tone_active && playedNotes()==notes(id)*4);
    tick(t,1); assert(t._msg_tone_active && t._important_notify_tone_next==360100);
    tick(t,60000); assert(!t._msg_tone_active && playedNotes()==notes(id)*6);
    ++checks;
  }
  // Local acknowledgement interrupts an active series and cancels its timer.
  now=100; UITask local; fresh(local); local.startImportantNotify(UI_MSG_FLAG_DIRECT);
  local.msgRead(0,true); int before=sounds();
  assert(!local._important_notify_active && !local._msg_tone_active);
  tick(local,250000); assert(sounds()==before); ++checks;

  // Global mute (also used by night quiet) cancels, never silently re-arms.
  now=100; UITask mute; fresh(mute); mute.startImportantNotify(UI_MSG_FLAG_DIRECT);
  mute.muted=true; tick(mute,1); before=sounds();
  assert(!mute._important_notify_active && !mute._msg_tone_active);
  tick(mute,240000); mute.muted=false; tick(mute,240000);
  assert(sounds()==before); ++checks;
  now=100; UITask disabled; fresh(disabled); disabled.prefs.important_notify_mode=0;
  disabled.startImportantNotify(UI_MSG_FLAG_DIRECT); tick(disabled,240000);
  assert(sounds()==0 && !disabled._important_notify_active); ++checks;

  // Connecting BLE pauses reminders. Unread state survives the connection;
  // on disconnect the next reminder is scheduled two minutes later.
  now=100; UITask ble; fresh(ble); ble.startImportantNotify(UI_MSG_FLAG_DIRECT);
  tick(ble,10000); assert(sounds()==2*notes(19)); ble.connected=true;
  tick(ble,240000); assert(sounds()==2*notes(19) && ble._important_notify_tone_next==0);
  ble.connected=false; tick(ble,1); auto disconnected=now;
  tick(ble,119999); assert(sounds()==2*notes(19));
  tick(ble,1); assert(ble._msg_tone_active && now-disconnected==120000); ++checks;

  // Real BLE read callback ends an active unread event. No reminder after
  // disconnect; this is distinct from a mere BLE connection.
  ble.connected=true; ble.msgRead(0,false);
  assert(!ble._important_notify_active); tick(ble,10000); before=sounds();
  ble.connected=false; tick(ble,240000); assert(sounds()==before); ++checks;

  // Arrives while BLE connected: delayed first series, no periodic series.
  now=100; UITask incoming; fresh(incoming); incoming.connected=true;
  incoming.startImportantNotify(UI_MSG_FLAG_DIRECT);
  assert(!incoming._important_notify_active && incoming._ble_smart_notify_flags);
  tick(incoming,7999); assert(sounds()==0);
  tick(incoming,1); assert(incoming._msg_tone_active);
  tick(incoming,250000); assert(sounds()==2*notes(19)); ++checks;
  // Disconnect before BLE delay expires starts the offline notification.
  now=100; UITask queued; fresh(queued); queued.connected=true;
  queued.startImportantNotify(UI_MSG_FLAG_DIRECT); tick(queued,1000);
  queued.connected=false; tick(queued,1); assert(queued._msg_tone_active);
  tick(queued,119999); assert(sounds()==2*notes(19));
  tick(queued,1); assert(queued._msg_tone_active); ++checks;

  // millis wrap, including a next deadline that would equal the zero sentinel.
  for(uint32_t start : {uint32_t(0xffff0000),uint32_t(0U-120000U)}) {
    now=start; UITask wrap; fresh(wrap); wrap.startImportantNotify(UI_MSG_FLAG_DIRECT);
    tick(wrap,119999); assert(sounds()==2*notes(19));
    tick(wrap,2); assert(wrap._msg_tone_active && sounds()>2*notes(19)); ++checks;
  }
  printf("PASS %u production-C++ reminder/melody scenarios\n",checks);
}
'''


def main():
    source = UI.read_text(encoding="utf-8")
    loop = source[source.index("void UITask::loop()") :]
    assert loop.index("importantNotifyHandler();") < loop.index("if (_display != NULL && _display->isOn())")
    assert "clearImportantNotify();" in loop[loop.index("if (c != 0 && curr)") : loop.index("userLedHandler();")]
    handler = function(source, "void UITask::importantNotifyHandler()")
    assert "_display" not in handler
    for board, env in BOARDS.items():
        print(run_cpp(harness(source, board_defines(board, env)) + MAIN, board, OUT), end="")
    print("PASS notification output loop runs independently of display rendering")


if __name__ == "__main__":
    main()
