"""Exercise actual UI LED gating and tone handlers with recorded GPIO writes.

Host stubs cover hardware and preferences; this does not emulate flash storage,
BLE or physical LED polarity. The V4 reminder suite covers all melodies/read paths.
"""
from test_notify_pins_v4 import UI, ROOT, BOARDS, board_defines, build_harness, function, run_cpp

OUT = ROOT / "qa_outputs/board-led-ui-v5"


def harness(source, flags):
    code = build_harness(source, flags)
    code = "#define BOARD_LED_INACTIVE_STATE (!PIN_MSG_ALERT_ACTIVE)\n" + code
    code = code.replace("struct NodePrefs {", "struct NodePrefs {\n  uint8_t board_leds_enabled=1;")
    replacements = {
        "bool areBoardLedsEnabled() const { return board_leds; }": "bool areBoardLedsEnabled() const;",
        "bool isBoardLedPin(int pin) const { return pin==PIN_LED; }": "bool isBoardLedPin(int pin) const;",
        "void setBoardLedPinOff(int pin) { digitalWrite(pin,!LED_STATE_ON); }":
            "void setBoardLedPinOff(int pin);\n  void applyBoardLedsState();",
    }
    for old, new in replacements.items():
        assert old in code, old
        code = code.replace(old, new)
    code += "\nstatic bool hardware_leds=true;\nstatic void meshcoreSetBoardLedsEnabled(bool on) { hardware_leds=on; }\n"
    for signature in ("bool UITask::isBoardLedPin(int pin) const", "void UITask::setBoardLedPinOff(int pin)",
                      "bool UITask::areBoardLedsEnabled() const", "void UITask::applyBoardLedsState()"):
        code += function(source, signature) + "\n"
    return code


MAIN = r'''
static unsigned checks=0;
#define CHECK(x) do { ++checks; assert(x); } while(0)
static int activeWrites(int pin) {
  int result=0;
  for(const auto& e:io) result+=e.pin==pin && !e.pwm && e.value==PIN_MSG_ALERT_ACTIVE;
  return result;
}
static void tick(UITask& t,unsigned ms) { while(ms--) { ++now; t.outputLoop(); } }
int main() {
  static_assert(DEFAULT_NOTIFY_TONE_PIN!=PIN_LED);
  UITask t;
  CHECK(t.isBoardLedPin(PIN_LED)); CHECK(!t.isBoardLedPin(-1));
  t._msg_alert_pin=PIN_LED;
  const bool selectable=isNotifyGpioPinAllowed(PIN_LED) && !t.isNotifyGpioBlocked(PIN_LED);
  CHECK((t.getMsgAlertPin()==PIN_LED)==selectable);
  io.clear(); t.triggerMsgAlert(); CHECK(activeWrites(PIN_LED)==int(selectable));
  CHECK(t._msg_alert_until!=0);
  t.prefs.board_leds_enabled=0;
  io.clear(); t.applyBoardLedsState();
  CHECK(!hardware_leds && !t.areBoardLedsEnabled());
  CHECK((!selectable || t._msg_alert_until==0) && activeWrites(PIN_LED)==0);
  CHECK(t.prefs.notify_mode==3 && t.prefs.important_notify_mode==3);
  for(int i=0;i<20;++i) { ++now; t.triggerMsgAlert(); t.messageAlertHandler(); }
  CHECK(activeWrites(PIN_LED)==0 && (!selectable || t._msg_alert_until==0));
  t.prefs.board_leds_enabled=1; t.applyBoardLedsState();
  CHECK(hardware_leds); io.clear(); t.triggerMsgAlert(); CHECK(activeWrites(PIN_LED)==int(selectable));
  now+=MSG_ALERT_ON_MILLIS; t.messageAlertHandler(); CHECK(!t._msg_alert_until);

  // External notification GPIOs are not silenced by the board-LED master.
  t.prefs.board_leds_enabled=0; t.applyBoardLedsState();
  for(int pin:notify_gpio_pins) if(!t.isBoardLedPin(pin) && !t.isNotifyGpioBlocked(pin)) {
    t._msg_alert_pin=pin; CHECK(t.getMsgAlertPin()==pin);
    io.clear(); t.triggerMsgAlert(); CHECK(activeWrites(pin)==1);
    now+=MSG_ALERT_ON_MILLIS; t.messageAlertHandler(); CHECK(!t._msg_alert_until);
  }

  // Switching off a shared LED/PWM pin stops that output immediately.
  if(selectable) {
    t.prefs.board_leds_enabled=1; t.applyBoardLedsState();
    t.configureMsgTonePin(PIN_LED); io.clear(); t.startMsgTone(19);
    CHECK(t._msg_tone_active);
    t.prefs.board_leds_enabled=0; t.applyBoardLedsState();
    CHECK(!t._msg_tone_active && !t._msg_tone_next && !t._msg_tone_off);
    io.clear(); t.messageToneHandler(); CHECK(!sounds() && !activeWrites(PIN_LED));
  } else {
    // T096 intentionally disallows using the TX LED as an alert/buzzer GPIO.
    t.configureMsgTonePin(PIN_LED); CHECK(t.getMsgTonePin()!=PIN_LED);
  }

  // Normal external buzzer remains active; still two plays and a 120 s reminder.
  now=100; UITask n; n._msg_alert_pin=PIN_LED;
  n.prefs.notify_tone_system_id=n.prefs.notify_tone_dm_id=n.prefs.notify_tone_mention_id=19;
  io.clear(); n.beginImportantNotify(UI_MSG_FLAG_DIRECT,1,false);
  CHECK(n._msg_tone_active && sounds()>0);
  unsigned long reminder=n._important_notify_tone_next;
  n.prefs.board_leds_enabled=0; n.applyBoardLedsState();
  CHECK(n._msg_tone_active && n._important_notify_active);
  CHECK(n._important_notify_tone_next==reminder && reminder==100+120000UL);
  io.clear(); tick(n,30000); CHECK(!n._msg_tone_active && sounds()>0);
  CHECK(!activeWrites(PIN_LED));
  io.clear(); tick(n,89999); CHECK(!sounds());
  tick(n,1); CHECK(n._msg_tone_active && sounds()>0 && !activeWrites(PIN_LED));
  CHECK(n.prefs.notify_mode==3 && n.prefs.important_notify_mode==3 && !n.prefs.board_leds_enabled);
  printf("PASS %u production UI board LED checks\n",checks);
}
'''


def main():
    source = UI.read_text(encoding="utf-8")
    assert "#if !UI_NOTIFY_LED_OVERRIDES_BOARD_LED_SETTING" not in source
    for board, env in BOARDS.items():
        flags = board_defines(board, env)
        # Even a stale user build flag must not override the explicit master OFF.
        flags["UI_NOTIFY_LED_OVERRIDES_BOARD_LED_SETTING"] = "1"
        print(run_cpp(harness(source, flags) + MAIN, board, OUT), end="")
    print("PASS T114/T096/ProMicro: master OFF, immediate apply, independent buzzer and external LEDs")


if __name__ == "__main__":
    main()
