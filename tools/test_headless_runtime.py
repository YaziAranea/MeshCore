"""Execute the complete production UITask::loop with null-display host stubs.

The scheduler, output devices, ADC and storage are deterministic stubs. This
checks software call ordering and null-display guards, not real hardware timing.
"""
from pathlib import Path
import re
import tempfile
from test_ui_sessions_v006 import function, run_cpp

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = (ROOT / "examples/companion_radio/ui-new/UITask.cpp").read_text(encoding="utf-8")
    code = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <initializer_list>
#include "BatteryShutdownPolicy.h"
#include "UiTiming.h"
#define PIN_MSG_ALERT 1
#define PIN_MSG_TONE 9
#define PIN_BUZZER 9
#define PIN_VIBRATION 10
#define PIN_USER_BTN 11
#define SMARTUI_CONNECTION_SELECTOR 1
#define UI_NOTIFY_ONLY_IMPORTANT_MESSAGES 1
#define UI_NIGHT_MODE_PROMPT 1
#define UI_RTC_VALID_MIN 1356998400UL
#define UI_NIGHT_MODE_END_MINUTE 480
#define UI_NIGHT_MODE_PROMPT_MINUTE 1380
#define UI_NIGHT_MODE_PROMPT_TIMEOUT_MS 30000
#define UI_MSG_FLAG_NONE 0
#define BUTTON_EVENT_NONE 0
#define BUTTON_EVENT_CLICK 1
#define BUTTON_EVENT_LONG_PRESS 2
#define BUTTON_EVENT_DOUBLE_CLICK 3
#define BUTTON_EVENT_TRIPLE_CLICK 4
#define KEY_ENTER 10
#define KEY_NEXT 11
#define KEY_PREV 12
#define KEY_SELECT 13
#define UI_TONE_HIGH_DRIVE_PAGE 1
#define NOTIFY_MODE_GPIO 1
#define NOTIFY_MODE_TONE 2
#define NOTIFY_MODE_VIBE 4
#define AUTO_SHUTDOWN_MILLIVOLTS 3200
#define LOW_BATTERY_SHUTDOWN_FLOOR_MILLIVOLTS 2700
#define LOW_BATTERY_SHUTDOWN_CONFIRM_COUNT 3
#define LOW_BATTERY_SHUTDOWN_CHECK_MILLIS 1000
#define HELTEC_WIRELESS_PAPER 1
uint32_t now = 0;
uint32_t millis() { return now; }
uint32_t rtc_now = 0;
struct Clock { uint32_t getCurrentTime() { return rtc_now; } } rtc_clock;
struct DateTime {
  uint32_t value;
  DateTime(uint32_t time):value(time) {}
  uint8_t hour() { return value / 3600 % 24; }
  uint8_t minute() { return value / 60 % 60; }
};
void delay(unsigned) {}
struct Button { int event=0; int check() { int result=event; event=0; return result; } } user_btn;
struct Prefs;
struct Mesh {
  int rescues=0;
  int saves=0;
  bool save_ok=true;
  Prefs* prefs=nullptr;
  void enterCLIRescue() { ++rescues; }
  bool isCLIRescue() const { return false; }
  bool savePrefs();
} the_mesh;
struct Controller {
  struct Status { bool usbConsoleEnabled=true; };
  Status status() const { return Status{}; }
} connection_controller;
struct DisplayDriver {
  enum { RED, DARK };
  static int calls;
  bool isOn() { ++calls; return true; }
  void turnOn() { ++calls; }
  void turnOff() { ++calls; }
  void startFrame() { ++calls; }
  void endFrame() { ++calls; }
  void setTextSize(int) { ++calls; }
  void setColor(int) { ++calls; }
  int getTextLineHeight() { ++calls; return 10; }
  int getTextWidth(const char*) { ++calls; return 50; }
  int height() { ++calls; return 64; }
  int width() { ++calls; return 128; }
  void drawTextCentered(int,int,const char*) { ++calls; }
  void fillRect(int,int,int,int) { ++calls; }
  void drawRect(int,int,int,int) { ++calls; }
};
int DisplayDriver::calls = 0;
void drawRichTextCenteredEllipsized(DisplayDriver&,int,int,int,const char*) {}
struct Screen {
  int polls = 0, renders = 0;
  void handleInput(char) {}
  void poll() { ++polls; }
  int render(DisplayDriver&) { ++renders; return 100; }
  bool isClockPage() const { return false; }
  bool isIdleForNightPrompt() const { return true; }
};
using HomeScreen = Screen;
struct Board {
  bool external = false, confirmed_usb = false;
  bool isExternalPowered() { return external; }
  bool isUsbPowerConfirmed() { return confirmed_usb; }
};
struct Prefs {
  uint8_t buzzer_quiet=0, notifications_muted=0, vibe_quiet=0, notify_tone_volume=10;
  uint8_t night_quiet_active=0;
  uint32_t night_prompt_day=0;
  double node_lat=1.5, node_lon=2.5;
};
bool Mesh::savePrefs() {
  ++saves;
  if (prefs) { prefs->node_lat=3.5; prefs->node_lon=4.5; }
  return save_ok;
}
struct Buzzer {
  int loops=0, plays=0;
  bool quiet_state=false;
  bool isPlaying() { return true; }
  void loop() { ++loops; }
  void quiet(bool value) { quiet_state=value; }
  void play(const char*) { ++plays; }
};
struct Vibration {
  int loops=0, stops=0, triggers=0;
  void loop() { ++loops; }
  void stop() { ++stops; }
  void trigger() { ++triggers; }
};
enum class UIEventType { none, contactMessage, channelMessage, ack, roomMessage, newContactMessage };
class UITask {
public:
  DisplayDriver* _display=nullptr;
  Screen screen; Screen* curr=&screen; Screen* msg_preview=nullptr; Screen* home=nullptr;
  Board board; Board* _board=&board;
  Prefs prefs; Prefs* _node_prefs=&prefs;
  Buzzer buzzer; Vibration vibration;
  bool _night_prompt_active=false, _storage_recovery_active=false;
  bool _adc_calibration_service_active=false;
  bool _night_prompt_yes=false, trusted=true;
  bool _important_notify_active=false, _popup_pending=false, _msg_tone_active=false;
  uint8_t _important_msg_flags=0, _ble_smart_notify_flags=0;
  uint32_t _msg_alert_until=0, _msg_vibe_until=0;
  uint32_t ui_started_at=0;
  uint32_t _ble_reenable_at=0, _next_refresh=0, _last_activity_ms=0;
  uint32_t _night_prompt_expires=0, _alert_expiry=0, next_batt_chck=0;
  uint32_t _night_save_retry_at=0;
  const char* _alert="";
  uint16_t _low_batt_threshold=0, threshold=3200, mv=4000;
  uint8_t _low_batt_strikes=0, mode=7, important_mode=7;
  bool unread=true;
  int leds=0, alerts=0, tones=0, vibes=0, smart=0, important=0;
  int shutdowns=0, cache_invalidations=0, stopped=0, board_applies=0;
  int alert_tests=0, tone_tests=0, vibe_tests=0;
  void updateUptime(uint32_t) {}
  void debugHeartbeat() {}
  void updateConnectionState() {}
  void nightModeHandler();
  bool persistNightPrefs(uint8_t,uint8_t,uint32_t);
  bool hasTrustedTime() const { return trusted; }
  uint32_t getLocalClockTime(uint32_t value) const { return value; }
  void closeNightPrompt(bool,bool) { _night_prompt_active=false; }
  void markDisplayWake(bool) {}
  bool hasToneAlert() const { return true; }
  void startNotifyToneTest(unsigned,unsigned) { ++tone_tests; }
  void connectionApprovalHandler() {}
  void handleButtonWakeLatch() {}
  bool handleRawButtonWakeWhenDark() { return false; }
  void enableBluetooth() {}
  void showAlert(const char*,int) {}
  void handleNightPromptInput(char) {}
  char checkDisplayOn(char c) { return c; }
  char handleLongPress(char c);
  char handleDoubleClick(char c) { return c; }
  char handleTripleClick(char c) { return c; }
  void toggleNotificationsMuted() {}
  void clearImportantNotify() {}
  void dismissCurrentMessageNotifications() {}
  void extendAutoOff() {}
  void userLedHandler() { ++leds; }
  void updateHourlyMessageWindow() {}
  void messageAlertHandler() { ++alerts; }
  void messageToneHandler() { ++tones; }
  void messageVibeHandler() { ++vibes; }
  void bleSmartNotifyHandler() { ++smart; }
  void importantNotifyHandler() { ++important; }
  void snoozedMessageHandler() {}
  void handlePendingPopupWake() {}
  void displayRecoverHandler() {}
  void renderNightPrompt(DisplayDriver&) {}
  int getUiTopColor() { return 1; }
  uint16_t getLowBatteryShutdownThreshold() { return threshold; }
  smartui::BatteryReading readSafetyBattery() { return smartui::batteryReading(mv); }
  void shutdown(bool=false,bool=false,bool emergency=true) { assert(emergency); ++shutdowns; }
  void stopNotifyOutputs() { ++stopped; }
  void applyBoardLedsState() { ++board_applies; }
  void invalidateBatteryCache() { ++cache_invalidations; }
  bool areNotificationsMuted() const { return prefs.notifications_muted; }
  bool isUnreadLedEnabled() const { return unread; }
  uint8_t getNotifyMode() const { return mode; }
  uint8_t getImportantNotifyMode() const { return important_mode; }
  int getMsgTonePin() const { return PIN_MSG_TONE; }
  int getMsgAlertPin() const { return PIN_MSG_ALERT; }
  void triggerMsgAlert() { ++alert_tests; }
  void startMsgTone() { ++tone_tests; }
  void triggerMsgVibe() { ++vibe_tests; }
  void loop();
  void applyDeviceSettingsRuntime(bool);
  void setAdcCalibrationServiceActive(bool);
  void previewNotifyMode();
  void notify(UIEventType);
  uint8_t getNotifyToneVolume() const;
};
'''
    for name in ("UI_RTC_VALID_MIN", "UI_NIGHT_MODE_END_MINUTE",
                 "UI_NIGHT_MODE_PROMPT_MINUTE", "UI_NIGHT_MODE_PROMPT_TIMEOUT_MS"):
        value = re.search(r"#define\s+" + name + r"\s+([^\r\n]+)", source).group(1)
        code = re.sub(r"(?m)^#define " + name + r" .+$", "#define " + name + " " + value, code)
    for signature in ("void UITask::loop()", "void UITask::applyDeviceSettingsRuntime(",
                      "void UITask::setAdcCalibrationServiceActive(",
                      "void UITask::previewNotifyMode()", "void UITask::notify(UIEventType",
                      "uint8_t UITask::getNotifyToneVolume() const", "char UITask::handleLongPress(char c)",
                      "bool UITask::persistNightPrefs(", "void UITask::nightModeHandler()"):
        code += function(source, signature) + "\n"
    code += r'''
static int checks=0;
#define CHECK(x) do { ++checks; assert(x); } while(0)
int main() {
  UITask rescue; now=100; user_btn.event=BUTTON_EVENT_LONG_PRESS;
  rescue.loop();
  CHECK(the_mesh.rescues==1 && rescue.screen.polls==0 && DisplayDriver::calls==0);
  UITask task;
  for (int i=0;i<20;++i) { now+=1000; task.loop(); }
  CHECK(task.leds==20 && task.alerts==20 && task.tones==20 && task.vibes==20);
  CHECK(task.smart==20 && task.important==20 && task.buzzer.loops==20 && task.vibration.loops==20);
  CHECK(task.screen.polls==0 && task.screen.renders==0 && DisplayDriver::calls==0);
  CHECK(task.shutdowns==0);
  task.mv=3100;
  for(int i=0;i<3;++i) { now+=1000; task.loop(); }
  CHECK(task.shutdowns==1 && DisplayDriver::calls==0);
  UITask floor; floor.threshold=2700; floor.mv=3100;
  for(int i=0;i<3;++i) { now+=1000; floor.loop(); }
  CHECK(floor.shutdowns==0);
  floor.mv=2600;
  for(int i=0;i<3;++i) { now+=1000; floor.loop(); }
  CHECK(floor.shutdowns==1 && DisplayDriver::calls==0);
  UITask usb; usb.board.external=true; usb.mv=3100;
  for(int i=0;i<5;++i) { now+=1000; usb.loop(); }
  CHECK(usb.shutdowns==0);
  usb.mv=2600;
  for(int i=0;i<3;++i) { now+=1000; usb.loop(); }
  CHECK(usb.shutdowns==1);
  // Headless service uses the same real transition and cutoff code as OLED.
  UITask calibration; calibration.mv=2600;
  calibration.board.external=calibration.board.confirmed_usb=true;
  calibration._low_batt_strikes=2; calibration.next_batt_chck=now+100000;
  calibration.setAdcCalibrationServiceActive(true);
  CHECK(calibration._low_batt_strikes==0 && calibration.next_batt_chck==0);
  for(int i=0;i<10;++i) { now+=1000; calibration.loop(); }
  CHECK(calibration.shutdowns==0 && calibration._low_batt_strikes==0);
  CHECK(calibration.important==10 && calibration.buzzer.loops==10);
  CHECK(DisplayDriver::calls==0);
  calibration.setAdcCalibrationServiceActive(false);
  CHECK(calibration._low_batt_strikes==0 && calibration.next_batt_chck==0);
  calibration.loop(); CHECK(calibration._low_batt_strikes==1);
  for(int i=0;i<2;++i) { now+=1000; calibration.loop(); }
  CHECK(calibration.shutdowns==1 && DisplayDriver::calls==0);
  UITask unconfirmed; unconfirmed.mv=2600; unconfirmed.board.external=true;
  unconfirmed.setAdcCalibrationServiceActive(true);
  for(int i=0;i<3;++i) { now+=1000; unconfirmed.loop(); }
  CHECK(unconfirmed.shutdowns==1 && DisplayDriver::calls==0);
  UITask recovery_cal; recovery_cal.mv=2600;
  recovery_cal.board.external=recovery_cal.board.confirmed_usb=true;
  recovery_cal._storage_recovery_active=true;
  recovery_cal.setAdcCalibrationServiceActive(true);
  for(int i=0;i<3;++i) { now+=1000; recovery_cal.loop(); }
  CHECK(recovery_cal.shutdowns==1 && DisplayDriver::calls==0);
  UITask unavailable; unavailable.mv=0;
  for(int i=0;i<5;++i) { now+=1000; unavailable.loop(); }
  CHECK(unavailable.shutdowns==0);
  UITask notify;
  notify.previewNotifyMode();
  CHECK(notify.alert_tests==1 && notify.tone_tests==1 && notify.vibe_tests==1);
  notify.prefs.notifications_muted=1; notify.previewNotifyMode();
  CHECK(notify.alert_tests==1 && notify.tone_tests==1 && notify.vibe_tests==1);
  notify.notify(UIEventType::ack);
  CHECK(notify.buzzer.plays==0 && notify.vibration.triggers==0);
  notify.prefs.notifications_muted=0; notify.important_mode=NOTIFY_MODE_GPIO; notify.unread=false;
  notify.previewNotifyMode();
  CHECK(notify.alert_tests==1 && notify.tone_tests==1 && notify.vibe_tests==1);
  notify.prefs.buzzer_quiet=1; notify.prefs.vibe_quiet=1;
  notify.notify(UIEventType::ack);
  CHECK(notify.buzzer.plays==0 && notify.vibration.triggers==0);
  notify.prefs.buzzer_quiet=0; notify.prefs.vibe_quiet=0;
  notify.notify(UIEventType::ack);
  CHECK(notify.buzzer.plays==1 && notify.vibration.triggers==1);
  notify._low_batt_strikes=2; notify._low_batt_threshold=3200; notify.next_batt_chck=100000;
  notify.applyDeviceSettingsRuntime(false);
  CHECK(notify._low_batt_strikes==2 && notify.cache_invalidations==0);
  notify.applyDeviceSettingsRuntime(true);
  CHECK(notify._low_batt_strikes==0 && notify._low_batt_threshold==0 && notify.next_batt_chck==0);
  CHECK(notify.cache_invalidations==1 && notify.stopped==2 && DisplayDriver::calls==0);
  for(int volume=1;volume<=10;++volume) {
    notify.prefs.notify_tone_volume=volume;
    CHECK(notify.getNotifyToneVolume()==volume);
  }
  // A saved display-era night mute must expire normally after a headless boot.
  UITask night; the_mesh.prefs=&night.prefs;
  night.prefs.night_quiet_active=night.prefs.notifications_muted=1;
  night.prefs.night_prompt_day=20000;
  rtc_now=20001U*86400+UI_NIGHT_MODE_END_MINUTE*60-60;
  night.nightModeHandler();
  CHECK(night.prefs.notifications_muted==1 && the_mesh.saves==0);
  rtc_now+=60;
  night.nightModeHandler();
  CHECK(night.prefs.night_quiet_active==0 && night.prefs.notifications_muted==0 && the_mesh.saves==1);
  CHECK(!night._night_prompt_active && night.tone_tests==0 && DisplayDriver::calls==0);
  // A failed save restores all touched preferences and incidental coordinates.
  night.prefs.night_quiet_active=night.prefs.notifications_muted=1;
  night.prefs.node_lat=1.5; night.prefs.node_lon=2.5;
  the_mesh.save_ok=false; night.nightModeHandler();
  CHECK(night.prefs.night_quiet_active==1 && night.prefs.notifications_muted==1);
  CHECK(night.prefs.node_lat==1.5 && night.prefs.node_lon==2.5 && night.prefs.night_prompt_day==20000);
  CHECK(!night._night_prompt_active && DisplayDriver::calls==0);
  const int failed_writes=the_mesh.saves;
  night.nightModeHandler();
  CHECK(the_mesh.saves==failed_writes);
  now+=4999; night.nightModeHandler();
  CHECK(the_mesh.saves==failed_writes);
  ++now; night.nightModeHandler();
  CHECK(the_mesh.saves==failed_writes+1 && night.prefs.notifications_muted==1);
  now+=5000;
  // Trusted time and storage safety gates still apply; no speculative unmute.
  the_mesh.saves=0; night.trusted=false; night.nightModeHandler();
  CHECK(the_mesh.saves==0 && night.prefs.notifications_muted==1);
  night.trusted=true; night._storage_recovery_active=true; night.nightModeHandler();
  CHECK(the_mesh.saves==0 && night.prefs.notifications_muted==1);
  night._storage_recovery_active=false; the_mesh.save_ok=true;
  rtc_now=20002U*86400+UI_NIGHT_MODE_PROMPT_MINUTE*60; night.nightModeHandler();
  CHECK(night.prefs.night_quiet_active==0 && night.prefs.notifications_muted==0);
  CHECK(the_mesh.saves==1 && !night._night_prompt_active && night.tone_tests==0);
  // No new headless prompt and no rewrite on the following night.
  rtc_now+=86400; night.nightModeHandler();
  CHECK(the_mesh.saves==1 && !night._night_prompt_active && DisplayDriver::calls==0);
  // An explicit permanent mute is not a scheduled night mute.
  night.prefs.notifications_muted=1; rtc_now+=9*3600; night.nightModeHandler();
  CHECK(night.prefs.notifications_muted==1 && the_mesh.saves==1);
  // The existing visible night prompt still requires a committed day marker.
  UITask visible; DisplayDriver panel; visible._display=&panel;
  visible.home=&visible.screen; visible.curr=visible.home; the_mesh.prefs=&visible.prefs;
  rtc_now=20005U*86400+UI_NIGHT_MODE_PROMPT_MINUTE*60; the_mesh.save_ok=false;
  visible.nightModeHandler();
  CHECK(!visible._night_prompt_active && visible.prefs.night_prompt_day==0 && DisplayDriver::calls==0);
  CHECK(visible.prefs.node_lat==1.5 && visible.prefs.node_lon==2.5);
  the_mesh.save_ok=true; now+=5000; visible.nightModeHandler();
  CHECK(visible._night_prompt_active && visible.prefs.night_prompt_day==20005);
  CHECK(DisplayDriver::calls==1 && visible.tone_tests==1);
  // The five-second retry is preserved across millis wrap, including zero.
  for(uint32_t start : {UINT32_MAX-1999U, uint32_t(0U-5000U)}) {
    UITask wrap; the_mesh.prefs=&wrap.prefs;
    wrap.prefs.night_quiet_active=wrap.prefs.notifications_muted=1;
    wrap.prefs.night_prompt_day=20000;
    rtc_now=20001U*86400+UI_NIGHT_MODE_END_MINUTE*60;
    now=start; the_mesh.save_ok=false; the_mesh.saves=0;
    wrap.nightModeHandler();
    CHECK(the_mesh.saves==1 && wrap._night_save_retry_at!=0);
    now+=4999; wrap.nightModeHandler();
    CHECK(the_mesh.saves==1 && wrap.prefs.notifications_muted==1);
    the_mesh.save_ok=true;
    now=wrap._night_save_retry_at; wrap.nightModeHandler();
    CHECK(the_mesh.saves==2 && wrap.prefs.notifications_muted==0 && wrap._night_save_retry_at==0);
  }
  printf("PASS %d actual UITask null-display loop, notification and protection checks\n",checks);
}
'''
    with tempfile.TemporaryDirectory(prefix="smartui-headless-") as directory:
        print(run_cpp(code, Path(directory), "headless_runtime"), end="")
    main_source = (ROOT / "examples/companion_radio/main.cpp").read_text(encoding="utf-8")
    assert "#if !SMARTUI_HEADLESS\n  if (display.begin())" in main_source
    assert "defined(DISPLAY_CLASS) && !SMARTUI_HEADLESS" in main_source
    assert "paper_attach_attempts < 2" in main_source
    assert "setCurrScreen(_display != NULL ? splash : NULL);" in source
    night = function(source, "void UITask::nightModeHandler()")
    assert night.index("if (_display == NULL) return;") > night.index("if (morning || missed_morning)")
    assert "NodePrefs before" not in night
    print("PASS headless initialization and bounded display retry source contracts")


if __name__ == "__main__":
    main()
