#pragma once

#include <MeshCore.h>
#include <helpers/ui/DisplayDriver.h>
#include <helpers/ui/UIScreen.h>
#include <helpers/SensorManager.h>
#include <helpers/MultiSerialInterface.h>
#include <helpers/BoardLedControl.h>
#include <Arduino.h>
#include <helpers/sensors/LPPDataHelpers.h>

#ifndef LED_STATE_ON
  #define LED_STATE_ON 1
#endif

#ifndef UI_STATS_WINDOW_MILLIS
  #define UI_STATS_WINDOW_MILLIS 3600000UL
#endif

#ifndef UI_STATS_BUCKET_MILLIS
  #define UI_STATS_BUCKET_MILLIS 60000UL
#endif

#ifndef UI_STATS_BUCKET_COUNT
  #define UI_STATS_BUCKET_COUNT 60
#endif

#ifndef UI_BATTERY_SAMPLE_MILLIS
  #define UI_BATTERY_SAMPLE_MILLIS 1000UL
#endif

#ifndef UI_BATTERY_SMOOTHING_SAMPLES
  #define UI_BATTERY_SMOOTHING_SAMPLES 4
#endif
#ifndef UI_BATTERY_DISPLAY_HYSTERESIS_MV
  #define UI_BATTERY_DISPLAY_HYSTERESIS_MV 0
#endif

#ifndef UI_PHONE_GPS
  #define UI_PHONE_GPS 0
#endif

struct UIHourlyStatsSnapshot {
  uint32_t elapsed_ms;
  uint32_t busy_ms;
  uint32_t tx_air_ms;
  uint32_t rx_air_ms;
  uint16_t msg_count;
};

#ifdef PIN_BUZZER
  #include <helpers/ui/buzzer.h>
#endif
#ifdef PIN_VIBRATION
  #include <helpers/ui/GenericVibration.h>
#endif

#ifndef UI_TONE_FALLBACK_TO_ALERT
  #define UI_TONE_FALLBACK_TO_ALERT 1
#endif

#ifndef UI_TONE_BRIDGE_PAGE
  #define UI_TONE_BRIDGE_PAGE 0
#endif

#ifndef UI_TONE_8BIT_PAGE
  #define UI_TONE_8BIT_PAGE 0
#endif

#ifndef UI_TONE_HIGH_DRIVE_PAGE
  #define UI_TONE_HIGH_DRIVE_PAGE 0
#endif

#ifndef UI_TONE_RESONANCE_PAGE
  #define UI_TONE_RESONANCE_PAGE 0
#endif

#ifndef UI_COMPACT_SETTINGS_MENU
  #define UI_COMPACT_SETTINGS_MENU 0
#endif

#ifndef UI_SMART_B11_EXTRAS
  #define UI_SMART_B11_EXTRAS 0
#endif
#ifndef UI_SMART_B12_TONE_LIST
  #define UI_SMART_B12_TONE_LIST 0
#endif

#ifndef PIN_MSG_TONE
  #ifdef PIN_BUZZER
    #define PIN_MSG_TONE PIN_BUZZER
  #elif defined(PIN_MSG_ALERT) && UI_TONE_FALLBACK_TO_ALERT
    #define PIN_MSG_TONE PIN_MSG_ALERT
  #endif
#endif

#include "../AbstractUITask.h"
#include "../NodePrefs.h"

class UITask : public AbstractUITask {
  DisplayDriver* _display;
  SensorManager* _sensors;
#ifdef PIN_BUZZER
  genericBuzzer buzzer;
#endif
#ifdef PIN_VIBRATION
  GenericVibration vibration;
#endif
  unsigned long _next_refresh, _auto_off;
  NodePrefs* _node_prefs;
  char _alert[80];
  unsigned long _alert_expiry;
  int _msgcount;
  struct UIHourlyStatsBucket {
    uint32_t busy_ms;
    uint32_t tx_air_ms;
    uint32_t rx_air_ms;
    uint16_t msg_count;
  };
  UIHourlyStatsBucket _hourly_stats[UI_STATS_BUCKET_COUNT];
  uint8_t _hourly_stats_index;
  uint8_t _hourly_stats_used;
  unsigned long _hourly_stats_started;
  unsigned long _hourly_bucket_started;
  unsigned long _hourly_last_tx_air_ms;
  unsigned long _hourly_last_rx_air_ms;
  unsigned long _hourly_last_busy_ms;
  unsigned long ui_started_at, next_batt_chck;
  uint8_t _low_batt_strikes;
  mutable uint16_t _battery_milli_volts;
  mutable uint16_t _battery_display_milli_volts;
  mutable unsigned long _battery_next_sample;
  mutable bool _battery_sample_valid;
  int next_backlight_btn_check = 0;
#ifdef PIN_STATUS_LED
  int led_state = 0;
  int next_led_change = 0;
  int last_led_increment = 0;
#endif
#ifdef PIN_MSG_ALERT
  unsigned long _msg_alert_until = 0;
  int8_t _msg_alert_pin = PIN_MSG_ALERT;
#endif
#ifdef PIN_MSG_TONE
  unsigned long _msg_tone_next = 0;
  unsigned long _msg_tone_off = 0;
  uint8_t _msg_tone_step = 0;
  uint8_t _msg_tone_repeat_left = 0;
  uint16_t _msg_tone_fx_remaining = 0;
  uint16_t _msg_tone_test_frequency = 0;
  uint16_t _msg_tone_test_duration = 700;
  uint8_t _msg_tone_fx_phase = 0;
  uint8_t _msg_tone_id_active = 0;
  int8_t _msg_tone_pin = PIN_MSG_TONE;
  bool _msg_tone_active = false;
#endif
  unsigned long _msg_vibe_until = 0;
  unsigned long _msg_vibe_next = 0;
  int8_t _msg_vibe_pin = -1;
  bool _msg_vibe_on = false;

#ifdef PIN_USER_BTN_ANA
  unsigned long _analogue_pin_read_millis = millis();
#endif

  UIScreen* splash;
  UIScreen* home;
  UIScreen* idle_saver;
  UIScreen* msg_preview;
  UIScreen* curr;
  unsigned long _last_activity_ms;
  unsigned long _display_wake_lock_until;
  unsigned long _display_recover_until;
  unsigned long _display_recover_next;
  unsigned long _button_wake_pending_until;
  unsigned long _ble_reenable_at;
  unsigned long _ble_state_changed_at;
  bool _last_connection_state;
  bool _popup_pending;
  bool _popup_pending_important;
  bool _display_recover_reset_to_clock;
  bool _button_wake_pending;
  bool _important_notify_active;
  uint8_t _important_msg_flags;
  uint8_t _ble_smart_notify_flags;
  bool _important_notify_tone_started;
  bool _important_notify_tone_repeat_suppressed;
  bool _important_notify_visual_repeat_suppressed;
  bool _ble_smart_notify_read_zero_seen;
  unsigned long _important_notify_visual_until;
  unsigned long _important_notify_led_next;
  unsigned long _important_notify_tone_next;
  unsigned long _important_notify_vibe_next;
  unsigned long _ble_smart_notify_due;
  uint8_t _important_notify_led_burst_step;
  uint8_t _important_notify_tone_burst_step;
  uint8_t _important_notify_vibe_burst_step;
  unsigned long _night_prompt_expires;
  bool _night_prompt_active;
  bool _night_prompt_yes;

  void userLedHandler();
  void updateHourlyMessageWindow();
  void resetHourlyStats(unsigned long now);
  void updateHourlyStats();
  void addHourlyMessage();
  void invalidateBatteryCache();
  void markDisplayWake(bool reset_to_clock);
  void scheduleDisplayRecover(bool reset_to_clock, unsigned long now);
  void displayRecoverHandler();
  void resetButtonStateAfterWake();
  bool handleRawButtonWakeWhenDark();
  void handleButtonWakeLatch();
  void updateConnectionState();
  void handlePendingPopupWake();
  void extendAutoOff(unsigned long now = 0);
  void stopNotifyOutputs();
  void finishImportantNotify(bool stop_tone);
  unsigned long nextImportantNotifyDelay(uint8_t& burst_step, unsigned long repeat_ms) const;
  void beginImportantNotify(uint8_t flags, bool suppress_tone_repeats = false);
  void scheduleBleSmartNotify(uint8_t flags);
  void clearBleSmartNotify();
  void bleSmartNotifyHandler();
  void startImportantNotify(uint8_t flags);
  void clearImportantNotify();
  void importantNotifyHandler();
  void nightModeHandler();
  bool handleNightPromptInput(char c);
  void renderNightPrompt(DisplayDriver& display);
  void closeNightPrompt(bool enable_quiet, bool timed_out = false);
  void debugHeartbeat();

  // Button action handlers
  char checkDisplayOn(char c);
  char handleLongPress(char c);
  char handleDoubleClick(char c);
  char handleTripleClick(char c);

  void setCurrScreen(UIScreen* c);
#ifdef PIN_MSG_ALERT
  int getMsgAlertPin() const;
  void configureMsgAlertPin(int pin);
  void triggerMsgAlert();
  void messageAlertHandler();
#endif
#ifdef PIN_MSG_TONE
  int getMsgTonePin() const;
  void configureMsgTonePin(int pin);
  void startMsgTone(uint8_t tone_id = 0xFF);
  void startNotifyToneTest(uint16_t frequency, uint16_t duration = 700);
  void messageToneHandler();
  void silenceMsgTonePin(int tone_pin);
  uint16_t getMsgToneOnMillis(uint16_t duration, uint16_t freq) const;
  bool isToneBridgePin(int pin) const;
#endif
  int getMsgVibePin() const;
  void configureMsgVibePin(int pin);
  void triggerMsgVibe();
  void stopMsgVibe();
  void messageVibeHandler();
  bool isNotifyGpioBlocked(int pin) const;
  bool isBoardLedPin(int pin) const;
  void setBoardLedPinOff(int pin);

public:

  UITask(mesh::MainBoard* board, MultiSerialInterface* serial) : AbstractUITask(board, serial), _display(NULL), _sensors(NULL) {
    next_batt_chck = _next_refresh = 0;
    memset(_hourly_stats, 0, sizeof(_hourly_stats));
    _hourly_stats_index = 0;
    _hourly_stats_used = 0;
    _hourly_stats_started = 0;
    _hourly_bucket_started = 0;
    _hourly_last_tx_air_ms = 0;
    _hourly_last_rx_air_ms = 0;
    _hourly_last_busy_ms = 0;
    ui_started_at = 0;
    _low_batt_strikes = 0;
    _battery_milli_volts = 0;
    _battery_display_milli_volts = 0;
    _battery_next_sample = 0;
    _battery_sample_valid = false;
    _last_activity_ms = 0;
    _display_wake_lock_until = 0;
    _display_recover_until = 0;
    _display_recover_next = 0;
    _button_wake_pending_until = 0;
    _ble_reenable_at = 0;
    _ble_state_changed_at = 0;
    _last_connection_state = false;
    _popup_pending = false;
    _popup_pending_important = false;
    _display_recover_reset_to_clock = false;
    _button_wake_pending = false;
    _important_notify_active = false;
    _important_msg_flags = UI_MSG_FLAG_NONE;
    _ble_smart_notify_flags = UI_MSG_FLAG_NONE;
    _important_notify_tone_started = false;
    _important_notify_tone_repeat_suppressed = false;
    _important_notify_visual_repeat_suppressed = false;
    _ble_smart_notify_read_zero_seen = false;
    _important_notify_visual_until = 0;
    _important_notify_led_next = 0;
    _important_notify_tone_next = 0;
    _important_notify_vibe_next = 0;
    _ble_smart_notify_due = 0;
    _important_notify_led_burst_step = 0;
    _important_notify_tone_burst_step = 0;
    _important_notify_vibe_burst_step = 0;
    _night_prompt_expires = 0;
    _night_prompt_active = false;
    _night_prompt_yes = true;
    idle_saver = NULL;
    curr = NULL;
  }
  void begin(DisplayDriver* display, SensorManager* sensors, NodePrefs* node_prefs);

  void gotoHomeScreen() { setCurrScreen(home); }
  void gotoHomeFirstScreen();
  void showAlert(const char* text, int duration_millis);
  int  getMsgCount() const { return _msgcount; }
  const char* getNodeName() const {
    return (_node_prefs != NULL && _node_prefs->node_name[0] != 0)
        ? _node_prefs->node_name
        : "MeshCore";
  }
  uint16_t getHourlyMsgCount();
  uint8_t getHourlyMsgWindowMinutes();
  void getHourlyStats(UIHourlyStatsSnapshot& out);
  bool hasDisplay() const { return _display != NULL; }
  bool isButtonPressed() const;
  void noteButtonWakeFromSleep(unsigned long now);
  uint8_t getNotifyMode() const;
  uint8_t getSupportedNotifyMode() const;
  const char* getNotifyModeName() const;
  int getNotifyLedPin() const;
  int getNotifyTonePin() const;
  int getNotifyVibePin() const;
  const char* getNotifySoundName() const;
  const char* getNotifyDmSoundName() const;
  const char* getNotifyMentionSoundName() const;
  const char* getNotifySystemSoundName() const;
  uint8_t getNotifyToneCount() const;
  uint8_t getNotifyToneId() const;
  const char* getNotifyToneName(uint8_t tone_id) const;
  void setCommonNotifyTone(uint8_t tone_id);
  uint8_t getNotifyToneVolume() const;
  bool isNotifyTone8BitEnabled() const;
  const char* getNotifyToneStyleName() const;
  bool isNotifyToneHighDriveEnabled() const;
  const char* getNotifyToneDriveName() const;
  uint16_t getNotifyToneResonanceHz() const;
  bool isNotifyToneBridgeEnabled() const;
  int getNotifyToneBridgePin() const;
  uint8_t getImportantNotifyMode() const;
  const char* getImportantNotifyModeName() const;
  bool hasImportantNotifyActive() const { return _important_notify_active; }
  bool areNotificationsMuted() const { return _node_prefs != NULL && _node_prefs->notifications_muted != 0; }
  void toggleNotificationsMuted();
  void cycleImportantNotifyMode();
  void cycleNotifyLedPin();
  void cycleNotifyTonePin();
  void cycleNotifyVibePin();
  void cycleNotifySound();
  void cycleNotifyDmSound();
  void cycleNotifyMentionSound();
  void cycleNotifySystemSound();
  void cycleNotifyToneVolume();
  void toggleNotifyTone8Bit();
  void toggleNotifyToneHighDrive();
  void cycleNotifyToneResonance();
  void toggleNotifyToneBridge();
  bool hasToneAlert() const;
  void cycleNotifyMode();
  void previewNotifyMode();
  bool areBoardLedsEnabled() const;
  void toggleBoardLeds();
  void applyBoardLedsState();
  bool shouldHoldLightSleepLock() const;
  bool areMsgPopupsEnabled() const;
  void toggleMsgPopups();
  bool isUnreadLedEnabled() const;
  void toggleUnreadLed();
  bool isOfflineDmLedEnabled() const;
  void toggleOfflineDmLed();
  bool isBleDmLedEnabled() const;
  void toggleBleDmLed();
  bool isLowBatteryShutdownEnabled() const;
  void toggleLowBatteryShutdown();
  const char* getUiFontName() const;
  const char* getUiThemeName() const;
  const char* getUiFontChoiceName(uint8_t choice) const;
  const char* getUiThemeChoiceName(uint8_t choice) const;
  const char* getUiTopColorName() const;
  const char* getUiBottomColorName() const;
  uint8_t getUiFontCount() const;
  uint8_t getUiThemeCount() const;
  uint8_t getUiFontChoiceIndex() const;
  uint8_t getUiThemeChoiceIndex() const;
  bool hasUiFontChoices() const;
  bool hasUiThemeChoices() const;
  void setUiFontChoice(uint8_t choice);
  void setUiThemeChoice(uint8_t choice);
  void cycleUiFont();
  void cycleUiTheme();
  ColorVal getUiTopColor() const;
  ColorVal getUiBottomColor() const;
  void cycleUiTopColor();
  void cycleUiBottomColor();
  const char* getBacklightTimeoutName() const;
  uint32_t getBacklightTimeoutMillis() const;
  void cycleBacklightTimeout();
  const char* getSmartProfileName() const;
  void cycleSmartProfile();
  void applyImportedPrefs() override;
  const char* getHardwareTestStepName(uint8_t step) const;
  void runHardwareTestStep(uint8_t step);

  bool isBuzzerQuiet() { 
#ifdef PIN_BUZZER
    return buzzer.isQuiet();
#else
    return true;
#endif
  }

  void toggleBuzzer();
  bool getGPSState();
  void toggleGPS();
  float getMCUTemperature() const;
  float getAdcMultiplier() const;
  bool setAdcMultiplier(float multiplier, bool save);
  uint16_t getBattMilliVolts() const override;


  // from AbstractUITask
  void msgRead(int msgcount) override;
  void msgRead(int msgcount, bool dismiss_notification) override;
  void directMsgRead(bool dismiss_notification) override;
  void newMsg(uint8_t path_len, const char* from_name, const char* text, int msgcount, uint8_t flags = UI_MSG_FLAG_NONE) override;
  void notify(UIEventType t = UIEventType::none) override;
  void loop() override;

  void shutdown(bool restart = false);
};
