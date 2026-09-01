#include "UITask.h"
#include "BatteryShutdownPolicy.h"
#include "UiTiming.h"
#include "ClockUptime.h"
#include "AdcCalibrationUi.h"
#include "ConfirmedChoice.h"
#include <math.h>
#include <helpers/TxtDataHelpers.h>
#include <helpers/RTCClockQuality.h>
#include <helpers/ui/Utf8Cyrillic5x7.h>
#include "../MyMesh.h"
#include "target.h"
#if UI_TONE_BRIDGE_PAGE == 1
  #include <HardwarePWM.h>
#endif
#if defined(PIN_NEOPIXEL) && defined(NEOPIXEL_NUM) && NEOPIXEL_NUM > 0
  #include <Adafruit_NeoPixel.h>
#endif
#ifdef WIFI_SSID
  #include <WiFi.h>
#endif

#if UI_TONE_BRIDGE_PAGE == 1
  #if !defined(NRF_PWM3) || !defined(DEFAULT_NOTIFY_TONE_BRIDGE_PIN) || !defined(DEFAULT_NOTIFY_TONE_PIN)
    #error "Tone bridge requires nRF PWM3 and fixed primary/secondary tone pins"
  #endif

static const uint32_t UI_TONE_BRIDGE_OWNER = 0x42525A54UL; // "BRZT"
static bool ui_tone_bridge_owned = false;

static void uiStopToneBridge(int primary_pin, int secondary_pin) {
  if (ui_tone_bridge_owned) {
    HwPWM3.stop();
    HwPWM3.removeAllPins();
    HwPWM3.releaseOwnership(UI_TONE_BRIDGE_OWNER);
    ui_tone_bridge_owned = false;
  }

  if (primary_pin >= 0) {
    pinMode(primary_pin, OUTPUT);
    digitalWrite(primary_pin, LOW);
  }
  if (secondary_pin >= 0 && secondary_pin != primary_pin) {
    pinMode(secondary_pin, OUTPUT);
    digitalWrite(secondary_pin, LOW);
  }
}

static bool uiStartToneBridge(int primary_pin, int secondary_pin, uint16_t frequency, bool high_drive) {
  uiStopToneBridge(primary_pin, secondary_pin);
  if (primary_pin < 0 || secondary_pin < 0 || primary_pin == secondary_pin) return false;
  if (frequency < 20 || frequency > 25000) return false;
  noTone(primary_pin); // PWM2 is used by Arduino tone(); release it before PWM3 takes over.
  if (!HwPWM3.takeOwnership(UI_TONE_BRIDGE_OWNER)) return false;
  ui_tone_bridge_owned = true;

  uint32_t pwm_clock = 1000000UL;
  uint8_t prescaler = PWM_PRESCALER_PRESCALER_DIV_16;
  uint32_t countertop = (pwm_clock + frequency / 2) / frequency;
  if (countertop > 32767UL) {
    pwm_clock = 500000UL;
    prescaler = PWM_PRESCALER_PRESCALER_DIV_32;
    countertop = (pwm_clock + frequency / 2) / frequency;
  }
  if (countertop < 3UL || countertop > 32767UL) {
    uiStopToneBridge(primary_pin, secondary_pin);
    return false;
  }

  HwPWM3.setClockDiv(prescaler);
  HwPWM3.setMaxValue((uint16_t)countertop);
  if (!HwPWM3.addPin(primary_pin) || !HwPWM3.addPin(secondary_pin)) {
    uiStopToneBridge(primary_pin, secondary_pin);
    return false;
  }
  if (high_drive) {
    pinMode(primary_pin, OUTPUT_H0H1);
    pinMode(secondary_pin, OUTPUT_H0H1);
  }

  uint16_t half_period = (uint16_t)(countertop / 2UL);
  if (!HwPWM3.writePin(primary_pin, half_period, false) ||
      !HwPWM3.writePin(secondary_pin, half_period, true)) {
    uiStopToneBridge(primary_pin, secondary_pin);
    return false;
  }
  return true;
}
#endif

#if UI_TONE_HIGH_DRIVE_PAGE == 1
static uint16_t uiToneNearestResonantOctave(uint16_t frequency, uint16_t resonance_hz) {
  if (frequency < 20 || resonance_hz < 1800 || resonance_hz > 4200) return frequency;

  uint16_t best = frequency;
  uint16_t best_delta = best > resonance_hz ? best - resonance_hz : resonance_hz - best;
  uint32_t candidate = frequency;
  while (candidate <= 6000UL) {
    uint16_t value = (uint16_t)candidate;
    uint16_t delta = value > resonance_hz ? value - resonance_hz : resonance_hz - value;
    if (delta < best_delta) {
      best = value;
      best_delta = delta;
    }
    candidate *= 2UL;
  }

  candidate = frequency / 2U;
  while (candidate >= 20UL) {
    uint16_t value = (uint16_t)candidate;
    uint16_t delta = value > resonance_hz ? value - resonance_hz : resonance_hz - value;
    if (delta < best_delta) {
      best = value;
      best_delta = delta;
    }
    candidate /= 2UL;
  }
  return best;
}
#endif

#ifndef AUTO_OFF_MILLIS
  #define AUTO_OFF_MILLIS     15000   // 15 seconds
#endif

#ifndef UI_MENU_AUTO_HOME_MILLIS
  #define UI_MENU_AUTO_HOME_MILLIS 0
#endif
#ifndef UI_AUTO_OFF_ALL_WINDOWS
  #define UI_AUTO_OFF_ALL_WINDOWS 0
#endif
#ifndef UI_SDVIG_NETWORK_LAYOUT
  #define UI_SDVIG_NETWORK_LAYOUT 0
#endif
#ifndef UI_TEXT_MARQUEE_ENABLE
  #define UI_TEXT_MARQUEE_ENABLE 1
#endif
#ifndef UI_TEXT_MARQUEE_STEP_MS
  #define UI_TEXT_MARQUEE_STEP_MS 420UL
#endif
#ifndef UI_TEXT_MARQUEE_EDGE_PAUSE_STEPS
  #define UI_TEXT_MARQUEE_EDGE_PAUSE_STEPS 4
#endif
#define BOOT_SCREEN_MILLIS   3000   // 3 seconds

#ifdef PIN_STATUS_LED
#define LED_ON_MILLIS     20
#define LED_ON_MSG_MILLIS 200
#define LED_CYCLE_MILLIS  4000
#endif

#ifndef LONG_PRESS_MILLIS
  #define LONG_PRESS_MILLIS   1200
#endif

#ifndef UI_RECENT_LIST_SIZE
  #define UI_RECENT_LIST_SIZE 4
#endif

#ifndef UI_NATIVE_TFT_PROFILE
  #if (defined(HELTEC_T114_WITH_DISPLAY) && defined(ST7789)) || defined(HELTEC_LORA_V4_TFT)
    #define UI_NATIVE_TFT_PROFILE 1
  #else
    #define UI_NATIVE_TFT_PROFILE 0
  #endif
#endif

#ifndef UI_V4_3_OLED_PROFILE
  #if defined(HELTEC_LORA_V4_3_OLED) || defined(PROMICRO) || defined(HELTEC_LORA_V3)
    #define UI_V4_3_OLED_PROFILE 1
  #else
    #define UI_V4_3_OLED_PROFILE 0
  #endif
#endif

#ifndef UI_CHAT_LIST_SIZE
  #if UI_NATIVE_TFT_PROFILE || UI_V4_3_OLED_PROFILE
    #define UI_CHAT_LIST_SIZE 20
  #else
    #define UI_CHAT_LIST_SIZE 12
  #endif
#endif

#ifndef UI_CHAT_RENDER_LINE_LIMIT
  #define UI_CHAT_RENDER_LINE_LIMIT 0
#endif

#ifndef MESHCORE_UI_VERSION
  #define MESHCORE_UI_VERSION "0.92"
#endif

#ifndef UI_RECENT_PAGE
  #define UI_RECENT_PAGE 0
#endif

#ifndef UI_LINK_TEST_PAGE
  #define UI_LINK_TEST_PAGE 0
#endif

#if UI_NATIVE_TFT_PROFILE
  #define UI_T114_APPEARANCE_MENU 1
#else
  #define UI_T114_APPEARANCE_MENU 0
#endif

#ifndef UI_APPEARANCE_MENU
  #define UI_APPEARANCE_MENU 1
#endif

#ifndef UI_COLOR_APPEARANCE_MENU
  #if UI_T096_PREMIUM_TFT || UI_NATIVE_TFT_PROFILE
    #define UI_COLOR_APPEARANCE_MENU 1
  #else
    #define UI_COLOR_APPEARANCE_MENU 0
  #endif
#endif

#ifndef UI_RICH_DYNAMIC_LINE_HEIGHT
  #if UI_T114_APPEARANCE_MENU || defined(HELTEC_WIRELESS_PAPER) || UI_V4_3_OLED_PROFILE
    #define UI_RICH_DYNAMIC_LINE_HEIGHT 1
  #else
    #define UI_RICH_DYNAMIC_LINE_HEIGHT 0
  #endif
#endif

#ifndef UI_UNREAD_USE_MONO_5X7
  #define UI_UNREAD_USE_MONO_5X7 0
#endif

#ifndef UI_CHAT_REFRESH_MILLIS
  #if UI_NATIVE_TFT_PROFILE || UI_V4_3_OLED_PROFILE
    #define UI_CHAT_REFRESH_MILLIS 220
  #else
    #define UI_CHAT_REFRESH_MILLIS 320
  #endif
#endif
#ifndef UI_LINK_TEST_REFRESH_MILLIS
  #define UI_LINK_TEST_REFRESH_MILLIS 540
#endif

#ifndef UI_CHAT_SCROLL_STEP_PX
  #if UI_NATIVE_TFT_PROFILE || UI_V4_3_OLED_PROFILE
    #define UI_CHAT_SCROLL_STEP_PX 6
  #else
    #define UI_CHAT_SCROLL_STEP_PX 3
  #endif
#endif

#ifndef UI_CHAT_EDGE_PAUSE_MILLIS
  #if UI_NATIVE_TFT_PROFILE || UI_V4_3_OLED_PROFILE
    #define UI_CHAT_EDGE_PAUSE_MILLIS 1200
  #else
    #define UI_CHAT_EDGE_PAUSE_MILLIS 1800
  #endif
#endif
#ifndef UI_EINK_SCROLL_REFRESH_MILLIS
  #define UI_EINK_SCROLL_REFRESH_MILLIS 2000UL
#endif

#ifndef UI_QUICK_REPLY_KEYBOARD
  #define UI_QUICK_REPLY_KEYBOARD 0
#endif

#ifndef UI_QUICK_REPLY_KEYBOARD_TEXT_MAX
  #define UI_QUICK_REPLY_KEYBOARD_TEXT_MAX 96
#endif

#ifndef UI_UNREAD_MSG_LIMIT
  #if UI_NATIVE_TFT_PROFILE || UI_V4_3_OLED_PROFILE
    #define UI_UNREAD_MSG_LIMIT 20
  #else
    #define UI_UNREAD_MSG_LIMIT 32
  #endif
#endif

#ifndef UI_UNREAD_DIRECT_ONLY
  #define UI_UNREAD_DIRECT_ONLY 0
#endif

#ifndef UI_UNREAD_TEXT_LEN
  #ifdef MAX_TEXT_LEN
    #define UI_UNREAD_TEXT_LEN (MAX_TEXT_LEN + 1)
  #else
    #define UI_UNREAD_TEXT_LEN 161
  #endif
#endif

#ifndef UI_UNREAD_RIGHT_GUARD_PX
  #if UI_NATIVE_TFT_PROFILE
    #define UI_UNREAD_RIGHT_GUARD_PX 4
  #else
    #define UI_UNREAD_RIGHT_GUARD_PX 1
  #endif
#endif

#ifndef UI_CLOCK_REFRESH_MILLIS
  #define UI_CLOCK_REFRESH_MILLIS 5000
#endif

#ifndef UI_DISPLAY_WAKE_RENDER_DELAY_MS
  #define UI_DISPLAY_WAKE_RENDER_DELAY_MS 250
#endif

#ifndef UI_DISPLAY_WAKE_LOCK_MS
  #define UI_DISPLAY_WAKE_LOCK_MS 2000
#endif

#ifndef UI_WAKE_SHOW_CLOCK
  #define UI_WAKE_SHOW_CLOCK 0
#endif

#ifndef UI_HOME_START_PAGE_FIRST
  #define UI_HOME_START_PAGE_FIRST 0
#endif

#ifndef UI_CLOCK_PAGE_VISIBLE
  #define UI_CLOCK_PAGE_VISIBLE 1
#endif

#ifndef UI_FIRST_PAGE_SAFE_CLOCK
  #define UI_FIRST_PAGE_SAFE_CLOCK 0
#endif

#ifndef UI_FIRST_PAGE_SHOW_MCU_TEMP
  #define UI_FIRST_PAGE_SHOW_MCU_TEMP 1
#endif

#ifndef UI_MCU_TEMP_DECIMALS
  #define UI_MCU_TEMP_DECIMALS 0
#endif

#ifndef UI_IMPORTANT_NOTIFY_ALL_MESSAGES
  #define UI_IMPORTANT_NOTIFY_ALL_MESSAGES 0
#endif

#ifndef UI_NOTIFY_ONLY_IMPORTANT_MESSAGES
  #define UI_NOTIFY_ONLY_IMPORTANT_MESSAGES 0
#endif

#ifndef UI_IMPORTANT_NOTIFY_REASON_ALERT
  #define UI_IMPORTANT_NOTIFY_REASON_ALERT 0
#endif

#ifndef UI_IMPORTANT_NOTIFY_SUPPRESS_STANDARD
  #define UI_IMPORTANT_NOTIFY_SUPPRESS_STANDARD 0
#endif

#ifndef UI_IMPORTANT_NOTIFY_WAKE_DISPLAY
  #define UI_IMPORTANT_NOTIFY_WAKE_DISPLAY 0
#endif

#ifndef UI_IMPORTANT_NOTIFY_LOCAL_ONLY_WHEN_DISCONNECTED
  #define UI_IMPORTANT_NOTIFY_LOCAL_ONLY_WHEN_DISCONNECTED 0
#endif

#ifndef UI_OFFLINE_DM_LED_PAGE
  #define UI_OFFLINE_DM_LED_PAGE 0
#endif

#ifndef UI_BOARD_LEDS_PAGE
  #define UI_BOARD_LEDS_PAGE 1
#endif

#ifndef UI_UNREAD_LED_PAGE
  #define UI_UNREAD_LED_PAGE 1
#endif

#ifndef UI_BLE_READ_FINISHES_IMPORTANT_NOTIFY
  #define UI_BLE_READ_FINISHES_IMPORTANT_NOTIFY UI_IMPORTANT_NOTIFY_LOCAL_ONLY_WHEN_DISCONNECTED
#endif

#ifndef UI_IMPORTANT_NOTIFY_BLE_SMART_DELAY_MS
  #define UI_IMPORTANT_NOTIFY_BLE_SMART_DELAY_MS 0
#endif

#ifndef UI_BLE_READ_SUPPRESSES_IMPORTANT_TONE_REPEAT
  #define UI_BLE_READ_SUPPRESSES_IMPORTANT_TONE_REPEAT 0
#endif

#ifndef UI_BLE_READ_SUPPRESSES_IMPORTANT_VISUAL_REPEAT
  #define UI_BLE_READ_SUPPRESSES_IMPORTANT_VISUAL_REPEAT 0
#endif

#ifndef UI_SMART_NOTIFY_WATCHER
  #define UI_SMART_NOTIFY_WATCHER 0
#endif

#ifndef UI_SMART_NOTIFY_WATCHER_CANCEL_PENDING_ON_BLE_READ
  #define UI_SMART_NOTIFY_WATCHER_CANCEL_PENDING_ON_BLE_READ UI_SMART_NOTIFY_WATCHER
#endif

#ifndef UI_SMART_NOTIFY_WATCHER_FINISH_ACTIVE_ON_BLE_READ
  #define UI_SMART_NOTIFY_WATCHER_FINISH_ACTIVE_ON_BLE_READ UI_SMART_NOTIFY_WATCHER
#endif

#ifndef UI_IMPORTANT_NOTIFY_VISUAL_BURST_MS
  #define UI_IMPORTANT_NOTIFY_VISUAL_BURST_MS 3500UL
#endif

#ifndef UI_OFFLINE_IMPORTANT_NOTIFY_BURST_COUNT
  #define UI_OFFLINE_IMPORTANT_NOTIFY_BURST_COUNT 1
#endif

#ifndef UI_OFFLINE_IMPORTANT_NOTIFY_BURST_GAP_MS
  #define UI_OFFLINE_IMPORTANT_NOTIFY_BURST_GAP_MS 3000UL
#endif

#ifndef UI_NOTIFY_LED_OVERRIDES_BOARD_LED_SETTING
  #define UI_NOTIFY_LED_OVERRIDES_BOARD_LED_SETTING 0
#endif

#ifndef UI_NOTIFY_TONE_PLAYS
  #define UI_NOTIFY_TONE_PLAYS 1
#endif

#ifndef UI_NOTIFY_TONE_REPEAT_GAP_MS
  #define UI_NOTIFY_TONE_REPEAT_GAP_MS 220UL
#endif

#ifndef UI_IMPORTANT_NOTIFY_TONE_PLAYS
  #define UI_IMPORTANT_NOTIFY_TONE_PLAYS 1
#endif

#ifndef UI_IMPORTANT_NOTIFY_TONE_REPEAT_GAP_MS
  #define UI_IMPORTANT_NOTIFY_TONE_REPEAT_GAP_MS UI_NOTIFY_TONE_REPEAT_GAP_MS
#endif

#ifndef UI_IMPORTANT_NOTIFY_TONE_SERIES_ONCE
  #define UI_IMPORTANT_NOTIFY_TONE_SERIES_ONCE 0
#endif

#ifndef UI_NIGHT_MODE_PROMPT
  #define UI_NIGHT_MODE_PROMPT 0
#endif

#ifndef UI_NIGHT_MODE_PROMPT_MINUTE
  #define UI_NIGHT_MODE_PROMPT_MINUTE (23 * 60 + 30)
#endif

#ifndef UI_NIGHT_MODE_END_MINUTE
  #define UI_NIGHT_MODE_END_MINUTE (7 * 60 + 30)
#endif

#ifndef UI_NIGHT_MODE_PROMPT_TIMEOUT_MS
  #define UI_NIGHT_MODE_PROMPT_TIMEOUT_MS 60000UL
#endif

#ifndef UI_TONE_8BIT_SLICE_MS
  #define UI_TONE_8BIT_SLICE_MS 40
#endif

#ifndef UI_TONE_8BIT_MIN_NOTE_MS
  #define UI_TONE_8BIT_MIN_NOTE_MS 100
#endif

#ifndef UI_IMPORTANT_NOTIFY_GPIO_DURING_TONE
  #define UI_IMPORTANT_NOTIFY_GPIO_DURING_TONE 1
#endif

#ifndef UI_IMPORTANT_NOTIFY_NEOPIXEL
  #define UI_IMPORTANT_NOTIFY_NEOPIXEL 0
#endif

#ifndef UI_IMPORTANT_NOTIFY_NEOPIXEL_STEP_MS
  #define UI_IMPORTANT_NOTIFY_NEOPIXEL_STEP_MS 220UL
#endif

#ifndef UI_IMPORTANT_NOTIFY_NEOPIXEL_BRIGHTNESS
  #define UI_IMPORTANT_NOTIFY_NEOPIXEL_BRIGHTNESS 24
#endif

#ifndef UI_IMPORTANT_NOTIFY_HOLD_SLEEP_LOCK
  #define UI_IMPORTANT_NOTIFY_HOLD_SLEEP_LOCK 1
#endif

#ifndef UI_HOME_ORDER_START_AT_FIRST
  #define UI_HOME_ORDER_START_AT_FIRST 0
#endif

#ifndef UI_HIDE_FIRST_PAGE
  #define UI_HIDE_FIRST_PAGE 0
#endif

#ifndef UI_BLE_PIN_PAGE
  #if defined(UI_T096_PREMIUM_TFT) && UI_T096_PREMIUM_TFT
    #define UI_BLE_PIN_PAGE 1
  #else
    #define UI_BLE_PIN_PAGE 0
  #endif
#endif

#ifndef UI_DISPLAY_VALIDATE_ON_INPUT
  #define UI_DISPLAY_VALIDATE_ON_INPUT 0
#endif

#ifndef UI_DISPLAY_RECOVER_ON_RENDER
  #define UI_DISPLAY_RECOVER_ON_RENDER 0
#endif

#ifndef UI_DISPLAY_RECOVER_RETRY_MS
  #define UI_DISPLAY_RECOVER_RETRY_MS 1000
#endif

#ifndef UI_DISPLAY_RECOVER_WINDOW_MS
  #define UI_DISPLAY_RECOVER_WINDOW_MS 0
#endif

#ifndef UI_LONG_PRESS_WAKES_DISPLAY
  #define UI_LONG_PRESS_WAKES_DISPLAY 0
#endif

#ifndef UI_CHAT_KEEP_DISPLAY_ON
  #define UI_CHAT_KEEP_DISPLAY_ON 1
#endif

#ifndef UI_BUTTON_WAKE_LATCH_MS
  #define UI_BUTTON_WAKE_LATCH_MS 0
#endif

#ifndef UI_BUTTON_WAKE_IRQ
  #define UI_BUTTON_WAKE_IRQ 0
#endif

#ifndef UI_BUTTON_WAKE_IMMEDIATE_CLICK_MS
  #define UI_BUTTON_WAKE_IMMEDIATE_CLICK_MS 0
#endif

#ifndef UI_RAW_BUTTON_WAKE_WHEN_DARK
  #define UI_RAW_BUTTON_WAKE_WHEN_DARK 0
#endif

#ifndef UI_WAKE_DEBUG_LOG
  #define UI_WAKE_DEBUG_LOG 0
#endif

#ifndef UI_WAKE_DEBUG_HEARTBEAT_MS
  #define UI_WAKE_DEBUG_HEARTBEAT_MS 0
#endif

#ifndef UI_BLE_TIME_SYNC_RESTART_DELAY_MS
  #define UI_BLE_TIME_SYNC_RESTART_DELAY_MS 800
#endif

#ifndef UI_POPUP_BLE_STATE_SETTLE_MS
  #define UI_POPUP_BLE_STATE_SETTLE_MS 1500
#endif

#ifndef UI_POPUP_WAKE_WHEN_BLE_CONNECTED
  #define UI_POPUP_WAKE_WHEN_BLE_CONNECTED 0
#endif

#ifndef UI_IMPORTANT_NOTIFY_LED_REPEAT_MS
  #define UI_IMPORTANT_NOTIFY_LED_REPEAT_MS 1200
#endif

#ifndef UI_IMPORTANT_NOTIFY_TONE_REPEAT_MS
  #define UI_IMPORTANT_NOTIFY_TONE_REPEAT_MS 1800
#endif

#ifndef UI_IDLE_REFRESH_MILLIS
  #define UI_IDLE_REFRESH_MILLIS 5000
#endif

#ifndef UI_EINK_IDLE_SCREENSAVER
  #define UI_EINK_IDLE_SCREENSAVER 0
#endif

#ifndef UI_EINK_IDLE_SCREENSAVER_MILLIS
  #define UI_EINK_IDLE_SCREENSAVER_MILLIS 60000UL
#endif

#ifndef UI_EINK_SAVER_REFRESH_MILLIS
  #define UI_EINK_SAVER_REFRESH_MILLIS 60000UL
#endif

#ifndef UI_WIRELESS_PAPER_BIG_CLOCK
  #define UI_WIRELESS_PAPER_BIG_CLOCK 0
#endif

#ifndef UI_STATS_WINDOW_MILLIS
  #define UI_STATS_WINDOW_MILLIS 3600000UL
#endif

#ifndef UI_TIMEZONE_OFFSET_SECONDS
  #define UI_TIMEZONE_OFFSET_SECONDS (6 * 60 * 60)
#endif

// Integration hook for a persisted preference.  A NodePrefs owner can define,
// for example, `UI_TIMEZONE_OFFSET_FROM_PREFS(p) ((p)->timezone_offset_minutes * 60)`
// without coupling this UI module to a particular prefs schema revision.
#ifndef UI_TIMEZONE_OFFSET_FROM_PREFS
  #define UI_TIMEZONE_OFFSET_FROM_PREFS(PREFS_PTR) \
      ((PREFS_PTR) != NULL ? (int32_t)(PREFS_PTR)->timezone_offset_minutes * 60L \
                           : (int32_t)UI_TIMEZONE_OFFSET_SECONDS)
#endif

#ifndef UI_RTC_VALID_MIN
  #define UI_RTC_VALID_MIN 1704067200UL
#endif

#ifndef DISABLE_LOW_BATTERY_SHUTDOWN
  #define DISABLE_LOW_BATTERY_SHUTDOWN 0
#endif

#if UI_BUTTON_WAKE_IRQ && defined(PIN_USER_BTN)
static volatile bool ui_button_wake_irq_pending = false;

static void uiButtonWakeIrqHandler() {
  ui_button_wake_irq_pending = true;
}
#endif

#ifndef LOW_BATTERY_SHUTDOWN_DEFAULT_ENABLED
  #define LOW_BATTERY_SHUTDOWN_DEFAULT_ENABLED (!DISABLE_LOW_BATTERY_SHUTDOWN)
#endif

// Non-SmartUI profiles retain the original meaning of disabled protection.
#ifndef LOW_BATTERY_SHUTDOWN_FLOOR_MILLIVOLTS
  #define LOW_BATTERY_SHUTDOWN_FLOOR_MILLIVOLTS 0
#endif

#ifndef UI_LOW_BATTERY_SHUTDOWN_PAGE
  #define UI_LOW_BATTERY_SHUTDOWN_PAGE 0
#endif

#ifndef LOW_BATTERY_SHUTDOWN_BOOT_GRACE_MILLIS
  #define LOW_BATTERY_SHUTDOWN_BOOT_GRACE_MILLIS 30000UL
#endif

#ifndef LOW_BATTERY_SHUTDOWN_CHECK_MILLIS
  #define LOW_BATTERY_SHUTDOWN_CHECK_MILLIS 8000UL
#endif

#ifndef LOW_BATTERY_SHUTDOWN_CONFIRM_COUNT
  #define LOW_BATTERY_SHUTDOWN_CONFIRM_COUNT 3
#endif

#ifndef USER_BUTTON_LONG_PRESS_POWEROFF
  #define USER_BUTTON_LONG_PRESS_POWEROFF 0
#endif

#ifndef USER_BUTTON_POWEROFF_AFTER_BOOT_MILLIS
  #define USER_BUTTON_POWEROFF_AFTER_BOOT_MILLIS 8000
#endif

#ifdef PIN_MSG_ALERT
#ifndef PIN_MSG_ALERT_ACTIVE
  #ifdef LED_STATE_ON
    #define PIN_MSG_ALERT_ACTIVE LED_STATE_ON
  #else
    #define PIN_MSG_ALERT_ACTIVE HIGH
  #endif
#endif
#ifndef MSG_ALERT_ON_MILLIS
  #define MSG_ALERT_ON_MILLIS 450
#endif
#define PIN_MSG_ALERT_INACTIVE (!PIN_MSG_ALERT_ACTIVE)
#endif

#ifndef MSG_VIBE_BURST_MILLIS
  #define MSG_VIBE_BURST_MILLIS 900
#endif
#ifndef MSG_VIBE_ON_MILLIS
  #define MSG_VIBE_ON_MILLIS 120
#endif
#ifndef MSG_VIBE_OFF_MILLIS
  #define MSG_VIBE_OFF_MILLIS 90
#endif

#ifndef BOARD_LED_INACTIVE_STATE
  #ifdef PIN_MSG_ALERT_ACTIVE
    #define BOARD_LED_INACTIVE_STATE (!PIN_MSG_ALERT_ACTIVE)
  #else
    #define BOARD_LED_INACTIVE_STATE (!LED_STATE_ON)
  #endif
#endif

#ifndef UI_NOTIFY_GPIO_SELECT
  #define UI_NOTIFY_GPIO_SELECT 0
#endif

#ifndef UI_NOTIFY_ALLOW_RISKY_PINS
  #define UI_NOTIFY_ALLOW_RISKY_PINS 0
#endif

#ifndef UI_BLOCK_BOARD_LED_NOTIFY
  #define UI_BLOCK_BOARD_LED_NOTIFY 0
#endif

#if UI_NOTIFY_GPIO_SELECT
#if defined(PROMICRO)
#if UI_NOTIFY_ALLOW_RISKY_PINS
static const int8_t notify_gpio_pins[] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 17, 18, 19, 20, 21, PIN_LED};
#else
static const int8_t notify_gpio_pins[] = {0, 1, 9, 18, 19, 20, PIN_LED};
#endif
#elif defined(HELTEC_LORA_V4_TFT)
static const int8_t notify_gpio_pins[] = {35, 40, 41, 47, 48};
#elif defined(HELTEC_LORA_V4)
static const int8_t notify_gpio_pins[] = {35, 3, 4, 40, 41, 47, 48};
#elif defined(HELTEC_LORA_V3)
static const int8_t notify_gpio_pins[] = {35, 40, 41, 3, 4};
#elif defined(HELTEC_WIRELESS_PAPER)
static const int8_t notify_gpio_pins[] = {18, 15, 16, 17, 21, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44};
#elif defined(HELTEC_T096)
static const int8_t notify_gpio_pins[] = {29, 31, 33, 34, 35, 36, 37, 39, 43, 45};
#elif defined(HELTEC_T114)
static const int8_t notify_gpio_pins[] = {35, 0, 1, 5, 7, 8, 9, 10, 13, 16, 18, 28, 29, 30, 31, 32, 33, 34, 36, 43, 44, 45, 46, 47};
#else
static const int8_t notify_gpio_pins[] = {
#ifdef DEFAULT_NOTIFY_GPIO_PIN
  DEFAULT_NOTIFY_GPIO_PIN
#elif defined(PIN_MSG_ALERT)
  PIN_MSG_ALERT
#elif defined(PIN_MSG_TONE)
  PIN_MSG_TONE
#elif defined(PIN_VIBRATION)
  PIN_VIBRATION
#else
  -1
#endif
};
#endif

static bool isNotifyGpioPinAllowed(int pin) {
  for (size_t i = 0; i < sizeof(notify_gpio_pins) / sizeof(notify_gpio_pins[0]); i++) {
    if (notify_gpio_pins[i] == pin) return true;
  }
  return false;
}

static bool isNotifyGpioPinBlockedByBuild(int pin) {
#if UI_BLOCK_BOARD_LED_NOTIFY
  if (pin < 0) return false;
#ifdef PIN_LED
  if (PIN_LED >= 0 && pin == PIN_LED) return true;
#endif
#ifdef LED_BUILTIN
  if (LED_BUILTIN >= 0 && pin == LED_BUILTIN) return true;
#endif
#ifdef PIN_STATUS_LED
  if (PIN_STATUS_LED >= 0 && pin == PIN_STATUS_LED) return true;
#endif
#ifdef P_LORA_TX_LED
  if (P_LORA_TX_LED >= 0 && pin == P_LORA_TX_LED) return true;
#endif
#endif
  return false;
}

static int getNextNotifyGpioPin(int pin) {
  const size_t count = sizeof(notify_gpio_pins) / sizeof(notify_gpio_pins[0]);
  if (count == 0) return pin;
  for (size_t i = 0; i < count; i++) {
    if (notify_gpio_pins[i] == pin) {
      for (size_t j = 1; j <= count; j++) {
        int candidate = notify_gpio_pins[(i + j) % count];
        if (!isNotifyGpioPinBlockedByBuild(candidate)) return candidate;
      }
      return pin;
    }
  }
  for (size_t i = 0; i < count; i++) {
    if (!isNotifyGpioPinBlockedByBuild(notify_gpio_pins[i])) return notify_gpio_pins[i];
  }
  return pin;
}

static int getNextNotifyGpioPinExcept(int pin, int skip_a, int skip_b) {
  int candidate = pin;
  const size_t count = sizeof(notify_gpio_pins) / sizeof(notify_gpio_pins[0]);
  for (size_t i = 0; i < count; i++) {
    candidate = getNextNotifyGpioPin(candidate);
    if (candidate != skip_a && candidate != skip_b) return candidate;
  }
  return pin;
}

static int getDefaultNotifyGpioPin() {
#ifdef DEFAULT_NOTIFY_GPIO_PIN
  if (isNotifyGpioPinAllowed(DEFAULT_NOTIFY_GPIO_PIN) && !isNotifyGpioPinBlockedByBuild(DEFAULT_NOTIFY_GPIO_PIN)) return DEFAULT_NOTIFY_GPIO_PIN;
#endif
#ifdef PIN_MSG_ALERT
  if (isNotifyGpioPinAllowed(PIN_MSG_ALERT) && !isNotifyGpioPinBlockedByBuild(PIN_MSG_ALERT)) return PIN_MSG_ALERT;
#endif
#ifdef PIN_MSG_TONE
  if (isNotifyGpioPinAllowed(PIN_MSG_TONE) && !isNotifyGpioPinBlockedByBuild(PIN_MSG_TONE)) return PIN_MSG_TONE;
#endif
#ifdef DEFAULT_NOTIFY_VIBE_PIN
  if (isNotifyGpioPinAllowed(DEFAULT_NOTIFY_VIBE_PIN) && !isNotifyGpioPinBlockedByBuild(DEFAULT_NOTIFY_VIBE_PIN)) return DEFAULT_NOTIFY_VIBE_PIN;
#endif
#ifdef PIN_VIBRATION
  if (isNotifyGpioPinAllowed(PIN_VIBRATION) && !isNotifyGpioPinBlockedByBuild(PIN_VIBRATION)) return PIN_VIBRATION;
#endif
  for (size_t i = 0; i < sizeof(notify_gpio_pins) / sizeof(notify_gpio_pins[0]); i++) {
    if (!isNotifyGpioPinBlockedByBuild(notify_gpio_pins[i])) return notify_gpio_pins[i];
  }
  return notify_gpio_pins[0];
}
#else
static bool isNotifyGpioPinBlockedByBuild(int) {
  return false;
}
#endif

static uint8_t uiNextNotifyMode(uint8_t mode, uint8_t supported) {
  supported &= NOTIFY_MODE_ALL;
  if (supported == NOTIFY_MODE_SILENT) return NOTIFY_MODE_SILENT;
  mode &= supported;

  static const uint8_t order[] = {
    NOTIFY_MODE_SILENT,
    NOTIFY_MODE_GPIO,
    NOTIFY_MODE_TONE,
    (uint8_t)(NOTIFY_MODE_GPIO | NOTIFY_MODE_TONE),
    NOTIFY_MODE_VIBE,
    (uint8_t)(NOTIFY_MODE_GPIO | NOTIFY_MODE_VIBE),
    (uint8_t)(NOTIFY_MODE_TONE | NOTIFY_MODE_VIBE),
    NOTIFY_MODE_ALL
  };
  const size_t count = sizeof(order) / sizeof(order[0]);
  size_t pos = 0;
  for (size_t i = 0; i < count; i++) {
    if (order[i] == mode) {
      pos = i;
      break;
    }
  }
  for (size_t i = 0; i < count; i++) {
    pos = (pos + 1) % count;
    uint8_t candidate = order[pos] & supported;
    if (candidate == order[pos]) return candidate;
  }
  return NOTIFY_MODE_SILENT;
}

#ifdef PIN_MSG_TONE
struct NotifyToneDef {
  const char* name;
  const uint16_t* freqs;
  const uint16_t* durations;
  uint8_t steps;
};

static const uint16_t msg_tone_pulse_freqs[] = {
  1, 0, 1, 0, 1
};
static const uint16_t msg_tone_pulse_durations[] = {
  90, 80, 90, 150, 160
};
static const uint16_t msg_tone_boomer_freqs[] = {
  988, 1175, 0, 1175, 988, 0, 1319, 1175, 1319, 1175, 1319, 1175, 1319, 1175, 1319, 1568,
  0, 1568, 1319, 1175, 988, 0, 988, 1175, 1319, 1568, 1319, 1175, 988, 0, 988
};
static const uint16_t msg_tone_boomer_durations[] = {
  120, 240, 240, 120, 240, 240, 120, 120, 120, 120, 120, 120, 120, 120, 120, 240,
  120, 120, 120, 120, 240, 120, 120, 120, 120, 180, 120, 120, 240, 120, 520
};
static const uint16_t msg_tone_swans_freqs[] = {
  880, 0, 880, 0, 880, 0, 880, 831, 880, 988, 0, 880, 0, 831, 0, 988, 0, 988, 0, 988, 0, 988,
  880, 988, 1109, 0, 988, 0, 880, 0, 1109, 0, 1480, 0, 1397, 0, 1109, 1109, 0, 1480, 0, 1397, 0, 1109
};
static const uint16_t msg_tone_swans_durations[] = {
  80, 80, 80, 80, 80, 80, 250, 40, 40, 80, 80, 80, 80, 80, 80, 80, 80, 80, 80, 80, 80, 250,
  40, 40, 80, 80, 80, 80, 80, 80, 80, 80, 80, 80, 80, 80, 825, 80, 80, 80, 80, 80, 80, 825
};
static const uint16_t msg_tone_fur_elise_freqs[] = {
  659, 0, 622, 0, 659, 0, 622, 0, 659, 0, 494, 0,
  587, 0, 523, 0, 440, 0, 262, 0, 330, 0, 440, 0,
  494, 0, 330, 0, 415, 0, 494, 0, 523, 0, 330, 0,
  659, 0, 622, 0, 659, 0, 622, 0, 659, 0, 494, 0,
  587, 0, 523, 0, 440, 0
};
static const uint16_t msg_tone_fur_elise_durations[] = {
  165, 25, 165, 25, 165, 25, 165, 25, 165, 25, 165, 25,
  165, 25, 165, 25, 495, 65, 165, 25, 165, 25, 165, 25,
  495, 65, 165, 25, 165, 25, 165, 25, 330, 235, 165, 25,
  165, 25, 165, 25, 165, 25, 165, 25, 165, 25, 165, 25,
  165, 25, 165, 25, 495, 65
};
static const uint16_t msg_tone_minuet_freqs[] = {
  587, 0, 392, 0, 440, 0, 494, 0, 523, 0, 587, 0,
  392, 0, 392, 0, 659, 0, 523, 0, 587, 0, 659, 0,
  740, 0, 784, 0, 392, 0, 392, 0
};
static const uint16_t msg_tone_minuet_durations[] = {
  380, 50, 190, 25, 190, 25, 190, 25, 190, 25, 380, 50,
  380, 50, 380, 50, 380, 50, 190, 25, 190, 25, 190, 25,
  190, 25, 380, 50, 380, 50, 380, 50
};
static const uint16_t msg_tone_canon_freqs[] = {
  294, 0, 370, 0, 392, 0, 440, 0, 370, 0, 392, 0,
  440, 0, 247, 0, 277, 0, 294, 0, 330, 0, 370, 0,
  392, 0, 370, 0, 294, 0, 330, 0, 370, 0
};
static const uint16_t msg_tone_canon_durations[] = {
  530, 70, 265, 35, 265, 35, 530, 70, 265, 35, 265, 35,
  530, 70, 265, 35, 265, 35, 265, 35, 265, 35, 265, 35,
  265, 35, 530, 70, 265, 35, 265, 35, 530, 70
};
static const uint16_t msg_tone_greensleeves_freqs[] = {
  392, 0, 466, 0, 523, 0, 587, 0, 622, 0, 587, 0,
  523, 0, 440, 0, 349, 0, 392, 0, 440, 0, 466, 0
};
static const uint16_t msg_tone_greensleeves_durations[] = {
  380, 50, 750, 105, 380, 50, 570, 75, 190, 25, 380, 50,
  750, 105, 380, 50, 570, 75, 190, 25, 380, 50, 750, 105
};
static const uint16_t msg_tone_beacon_freqs[] = {1568, 0, 1568, 0, 988};
static const uint16_t msg_tone_beacon_durations[] = {90, 55, 90, 160, 220};
static const uint16_t msg_tone_chime_freqs[] = {1047, 1319, 1568, 2093};
static const uint16_t msg_tone_chime_durations[] = {80, 80, 90, 180};
static const uint16_t msg_tone_bell_freqs[] = {784, 0, 1047, 0, 1319};
static const uint16_t msg_tone_bell_durations[] = {150, 55, 150, 55, 240};
static const uint16_t msg_tone_sos_freqs[] = {
  1568, 0, 1568, 0, 1568, 0, 1568, 0, 1568, 0, 1568, 0, 1568, 0, 1568, 0, 1568
};
static const uint16_t msg_tone_sos_durations[] = {
  80, 55, 80, 55, 80, 150, 240, 70, 240, 70, 240, 150, 80, 55, 80, 55, 80
};
static const uint16_t msg_tone_ode_long_freqs[] = {
  330, 0, 330, 0, 349, 0, 392, 0, 392, 0, 349, 0,
  330, 0, 294, 0, 262, 0, 262, 0, 294, 0, 330, 0,
  330, 0, 294, 0, 294, 0
};
static const uint16_t msg_tone_ode_long_durations[] = {
  460, 65, 460, 65, 460, 65, 460, 65, 460, 65, 460, 65,
  460, 65, 460, 65, 460, 65, 460, 65, 460, 65, 460, 65,
  695, 95, 235, 30, 930, 125
};
static const uint16_t msg_tone_korobeiniki_freqs[] = {
  659, 0, 494, 0, 523, 0, 587, 0, 523, 0, 494, 0,
  440, 0, 440, 0, 523, 0, 659, 0, 587, 0, 523, 0,
  494, 0, 523, 0, 587, 0, 659, 0, 523, 0, 440, 0,
  440, 0
};
static const uint16_t msg_tone_korobeiniki_durations[] = {
  365, 50, 185, 25, 185, 25, 365, 50, 185, 25, 185, 25,
  365, 50, 185, 25, 185, 25, 365, 50, 185, 25, 185, 25,
  550, 75, 185, 25, 365, 50, 365, 50, 365, 50, 365, 50,
  365, 50
};
static const uint16_t msg_tone_brahms_freqs[] = {
  392, 0, 392, 0, 466, 0, 392, 0, 392, 0, 466, 0,
  392, 0, 466, 0, 622, 0, 587, 0
};
static const uint16_t msg_tone_brahms_durations[] = {
  695, 95, 695, 95, 1045, 140, 350, 45, 695, 95, 695, 885,
  350, 45, 350, 45, 695, 95, 1045, 140
};
static const uint16_t msg_tone_badinerie_freqs[] = {
  988, 0, 1175, 0, 988, 0, 740, 0, 988, 0, 740, 0,
  587, 0, 740, 0, 587, 0, 494, 0, 349, 0, 494, 0,
  587, 0, 494, 0, 554, 0, 494, 0, 554, 0, 494, 0,
  466, 0, 554, 0, 659, 0, 554, 0, 587, 0, 494, 0,
  988, 0, 1175, 0, 988, 0, 740, 0, 988, 0, 740, 0,
  587, 0, 740, 0, 587, 0, 494, 0
};
static const uint16_t msg_tone_badinerie_durations[] = {
  330, 45, 110, 15, 110, 15, 330, 45, 110, 15, 110, 15,
  330, 45, 110, 15, 110, 15, 440, 60, 110, 15, 110, 15,
  110, 15, 110, 15, 110, 15, 110, 15, 110, 15, 110, 15,
  110, 15, 110, 15, 110, 15, 110, 15, 220, 30, 220, 30,
  330, 45, 110, 15, 110, 15, 330, 45, 110, 15, 110, 15,
  330, 45, 110, 15, 110, 15, 440, 60
};
static const uint16_t msg_tone_prince_igor_freqs[] = {
  392, 0, 392, 0, 587, 0, 523, 0, 587, 0, 466, 0,
  440, 0, 392, 0, 440, 0, 466, 0, 523, 0
};
static const uint16_t msg_tone_prince_igor_durations[] = {
  480, 65, 480, 65, 1440, 195, 240, 35, 240, 35, 480, 65,
  240, 35, 240, 35, 240, 35, 240, 35, 1920, 260
};
static const uint16_t msg_tone_silent_night_freqs[] = {
  392, 0, 440, 0, 392, 0, 330, 0, 392, 0, 440, 0,
  392, 0, 330, 0, 587, 0, 587, 0, 494, 0
};
static const uint16_t msg_tone_silent_night_durations[] = {
  570, 75, 190, 25, 380, 50, 1130, 155, 570, 75, 190, 25,
  380, 50, 1130, 155, 750, 105, 380, 50, 1130, 155
};
static const uint16_t msg_tone_birthday_freqs[] = {
  262, 0, 262, 0, 294, 0, 262, 0, 349, 0, 330, 0,
  262, 0, 262, 0, 294, 0, 262, 0, 392, 0, 349, 0
};
static const uint16_t msg_tone_birthday_durations[] = {
  380, 50, 190, 25, 570, 75, 570, 75, 570, 75, 1130, 155,
  380, 50, 190, 25, 570, 75, 570, 75, 570, 75, 1130, 155
};
static const uint16_t msg_tone_gran_vals_freqs[] = {
  659, 0, 587, 0, 370, 0, 415, 0, 554, 0, 494, 0,
  294, 0, 330, 0, 494, 0, 440, 0, 277, 0, 330, 0,
  440, 0,
  659, 0, 587, 0, 370, 0, 415, 0, 554, 0, 494, 0,
  294, 0, 330, 0, 494, 0, 440, 0, 277, 0, 330, 0,
  440, 0
};
static const uint16_t msg_tone_gran_vals_durations[] = {
  145, 20, 145, 20, 295, 40, 295, 40, 145, 20, 145, 20,
  295, 40, 295, 40, 145, 20, 145, 20, 295, 40, 295, 40,
  585, 200,
  145, 20, 145, 20, 295, 40, 295, 40, 145, 20, 145, 20,
  295, 40, 295, 40, 145, 20, 145, 20, 295, 40, 295, 40,
  585, 80
};
static const uint16_t msg_tone_ping_freqs[] = {1568};
static const uint16_t msg_tone_ping_durations[] = {120};
static const uint16_t msg_tone_double_freqs[] = {1568, 0, 1568};
static const uint16_t msg_tone_double_durations[] = {80, 60, 100};
static const uint16_t msg_tone_rise_freqs[] = {784, 988, 1175};
static const uint16_t msg_tone_rise_durations[] = {70, 70, 120};
static const uint16_t msg_tone_soft_freqs[] = {1047, 0, 784};
static const uint16_t msg_tone_soft_durations[] = {100, 45, 140};
static const uint16_t msg_tone_ode_short_freqs[] = {
  659, 659, 698, 784, 784, 698, 659, 587, 523, 523, 587, 659, 659, 587, 587
};
static const uint16_t msg_tone_ode_short_durations[] = {
  120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 160, 90, 220
};
static const uint16_t msg_tone_arcade_freqs[] = {784, 988, 1175, 1568, 1175, 1568};
static const uint16_t msg_tone_arcade_durations[] = {70, 70, 70, 120, 70, 150};
static const uint16_t msg_tone_lift_freqs[] = {659, 784, 988, 0, 988, 784};
static const uint16_t msg_tone_lift_durations[] = {75, 75, 150, 60, 75, 140};
static const uint16_t msg_tone_nova_freqs[] = {1319, 1568, 2093, 0, 1568};
static const uint16_t msg_tone_nova_durations[] = {70, 70, 160, 55, 120};
static const uint16_t msg_tone_radar_freqs[] = {1175, 0, 1175, 0, 1760};
static const uint16_t msg_tone_radar_durations[] = {95, 70, 95, 130, 190};
static const uint16_t msg_tone_echo_freqs[] = {988, 0, 988, 0, 784};
static const uint16_t msg_tone_echo_durations[] = {130, 80, 85, 65, 170};
static const uint16_t msg_tone_tiny_freqs[] = {2093, 0, 2349};
static const uint16_t msg_tone_tiny_durations[] = {55, 45, 75};
static const uint16_t msg_tone_alert_freqs[] = {1760, 0, 1568, 0, 1760, 2093};
static const uint16_t msg_tone_alert_durations[] = {80, 55, 80, 55, 80, 150};

#define UI_ASSERT_TONE_SHAPE(id) \
  static_assert(sizeof(msg_tone_##id##_freqs) == sizeof(msg_tone_##id##_durations), "Tone arrays differ: " #id)
UI_ASSERT_TONE_SHAPE(pulse);
UI_ASSERT_TONE_SHAPE(boomer);
UI_ASSERT_TONE_SHAPE(fur_elise);
UI_ASSERT_TONE_SHAPE(minuet);
UI_ASSERT_TONE_SHAPE(canon);
UI_ASSERT_TONE_SHAPE(greensleeves);
UI_ASSERT_TONE_SHAPE(beacon);
UI_ASSERT_TONE_SHAPE(chime);
UI_ASSERT_TONE_SHAPE(bell);
UI_ASSERT_TONE_SHAPE(sos);
UI_ASSERT_TONE_SHAPE(ode_long);
UI_ASSERT_TONE_SHAPE(korobeiniki);
UI_ASSERT_TONE_SHAPE(brahms);
UI_ASSERT_TONE_SHAPE(badinerie);
UI_ASSERT_TONE_SHAPE(prince_igor);
UI_ASSERT_TONE_SHAPE(silent_night);
UI_ASSERT_TONE_SHAPE(birthday);
UI_ASSERT_TONE_SHAPE(gran_vals);
UI_ASSERT_TONE_SHAPE(swans);
UI_ASSERT_TONE_SHAPE(ping);
UI_ASSERT_TONE_SHAPE(double);
UI_ASSERT_TONE_SHAPE(rise);
UI_ASSERT_TONE_SHAPE(soft);
UI_ASSERT_TONE_SHAPE(ode_short);
UI_ASSERT_TONE_SHAPE(arcade);
UI_ASSERT_TONE_SHAPE(lift);
UI_ASSERT_TONE_SHAPE(nova);
UI_ASSERT_TONE_SHAPE(radar);
UI_ASSERT_TONE_SHAPE(echo);
UI_ASSERT_TONE_SHAPE(tiny);
UI_ASSERT_TONE_SHAPE(alert);
#undef UI_ASSERT_TONE_SHAPE

static const NotifyToneDef notify_tones[] = {
  {"Пульс", msg_tone_pulse_freqs, msg_tone_pulse_durations, sizeof(msg_tone_pulse_freqs) / sizeof(msg_tone_pulse_freqs[0])},
  {"Бумер", msg_tone_boomer_freqs, msg_tone_boomer_durations, sizeof(msg_tone_boomer_freqs) / sizeof(msg_tone_boomer_freqs[0])},
  {"К Элизе", msg_tone_fur_elise_freqs, msg_tone_fur_elise_durations, sizeof(msg_tone_fur_elise_freqs) / sizeof(msg_tone_fur_elise_freqs[0])},
  {"Менуэт", msg_tone_minuet_freqs, msg_tone_minuet_durations, sizeof(msg_tone_minuet_freqs) / sizeof(msg_tone_minuet_freqs[0])},
  {"Канон", msg_tone_canon_freqs, msg_tone_canon_durations, sizeof(msg_tone_canon_freqs) / sizeof(msg_tone_canon_freqs[0])},
  {"Рукава", msg_tone_greensleeves_freqs, msg_tone_greensleeves_durations, sizeof(msg_tone_greensleeves_freqs) / sizeof(msg_tone_greensleeves_freqs[0])},
  {"Маяк", msg_tone_beacon_freqs, msg_tone_beacon_durations, sizeof(msg_tone_beacon_freqs) / sizeof(msg_tone_beacon_freqs[0])},
  {"Перезв", msg_tone_chime_freqs, msg_tone_chime_durations, sizeof(msg_tone_chime_freqs) / sizeof(msg_tone_chime_freqs[0])},
  {"Колокол", msg_tone_bell_freqs, msg_tone_bell_durations, sizeof(msg_tone_bell_freqs) / sizeof(msg_tone_bell_freqs[0])},
  {"SOS", msg_tone_sos_freqs, msg_tone_sos_durations, sizeof(msg_tone_sos_freqs) / sizeof(msg_tone_sos_freqs[0])},
  {"Ода", msg_tone_ode_long_freqs, msg_tone_ode_long_durations, sizeof(msg_tone_ode_long_freqs) / sizeof(msg_tone_ode_long_freqs[0])},
  {"Коробейники", msg_tone_korobeiniki_freqs, msg_tone_korobeiniki_durations, sizeof(msg_tone_korobeiniki_freqs) / sizeof(msg_tone_korobeiniki_freqs[0])},
  {"Колыбельная", msg_tone_brahms_freqs, msg_tone_brahms_durations, sizeof(msg_tone_brahms_freqs) / sizeof(msg_tone_brahms_freqs[0])},
  {"Бадинери", msg_tone_badinerie_freqs, msg_tone_badinerie_durations, sizeof(msg_tone_badinerie_freqs) / sizeof(msg_tone_badinerie_freqs[0])},
  {"Князь Игорь", msg_tone_prince_igor_freqs, msg_tone_prince_igor_durations, sizeof(msg_tone_prince_igor_freqs) / sizeof(msg_tone_prince_igor_freqs[0])},
  {"Тихая ночь", msg_tone_silent_night_freqs, msg_tone_silent_night_durations, sizeof(msg_tone_silent_night_freqs) / sizeof(msg_tone_silent_night_freqs[0])},
  {"День рожд.", msg_tone_birthday_freqs, msg_tone_birthday_durations, sizeof(msg_tone_birthday_freqs) / sizeof(msg_tone_birthday_freqs[0])},
  {"Гран-вальс", msg_tone_gran_vals_freqs, msg_tone_gran_vals_durations, sizeof(msg_tone_gran_vals_freqs) / sizeof(msg_tone_gran_vals_freqs[0])},
  {"Лебеди", msg_tone_swans_freqs, msg_tone_swans_durations, sizeof(msg_tone_swans_freqs) / sizeof(msg_tone_swans_freqs[0])},
  {"Пинг", msg_tone_ping_freqs, msg_tone_ping_durations, sizeof(msg_tone_ping_freqs) / sizeof(msg_tone_ping_freqs[0])},
  {"Дубль", msg_tone_double_freqs, msg_tone_double_durations, sizeof(msg_tone_double_freqs) / sizeof(msg_tone_double_freqs[0])},
  {"Рост", msg_tone_rise_freqs, msg_tone_rise_durations, sizeof(msg_tone_rise_freqs) / sizeof(msg_tone_rise_freqs[0])},
  {"Мягк", msg_tone_soft_freqs, msg_tone_soft_durations, sizeof(msg_tone_soft_freqs) / sizeof(msg_tone_soft_freqs[0])},
  {"Ода коротк.", msg_tone_ode_short_freqs, msg_tone_ode_short_durations, sizeof(msg_tone_ode_short_freqs) / sizeof(msg_tone_ode_short_freqs[0])},
  {"Аркада", msg_tone_arcade_freqs, msg_tone_arcade_durations, sizeof(msg_tone_arcade_freqs) / sizeof(msg_tone_arcade_freqs[0])},
  {"Лифт", msg_tone_lift_freqs, msg_tone_lift_durations, sizeof(msg_tone_lift_freqs) / sizeof(msg_tone_lift_freqs[0])},
  {"Nova", msg_tone_nova_freqs, msg_tone_nova_durations, sizeof(msg_tone_nova_freqs) / sizeof(msg_tone_nova_freqs[0])},
  {"Radar", msg_tone_radar_freqs, msg_tone_radar_durations, sizeof(msg_tone_radar_freqs) / sizeof(msg_tone_radar_freqs[0])},
  {"Echo", msg_tone_echo_freqs, msg_tone_echo_durations, sizeof(msg_tone_echo_freqs) / sizeof(msg_tone_echo_freqs[0])},
  {"Tiny", msg_tone_tiny_freqs, msg_tone_tiny_durations, sizeof(msg_tone_tiny_freqs) / sizeof(msg_tone_tiny_freqs[0])},
  {"Alert", msg_tone_alert_freqs, msg_tone_alert_durations, sizeof(msg_tone_alert_freqs) / sizeof(msg_tone_alert_freqs[0])},
};
enum { notify_tone_count = sizeof(notify_tones) / sizeof(notify_tones[0]) };
static_assert(notify_tone_count == NOTIFY_TONE_COUNT, "Update NOTIFY_TONE_COUNT when notify_tones changes");

static uint16_t uiTone8BitArpeggioFrequency(uint16_t base_frequency, uint8_t phase) {
  uint32_t shifted = base_frequency;
  switch (phase & 0x03) {
    case 1:
    case 3:
      shifted = (uint32_t)base_frequency * 3UL / 2UL;
      break;
    case 2:
      shifted = (uint32_t)base_frequency * 2UL;
      break;
    default:
      break;
  }
  return (uint16_t)(shifted > 6000UL ? 6000UL : shifted);
}
#endif

#if UI_IMPORTANT_NOTIFY_NEOPIXEL && defined(PIN_NEOPIXEL) && defined(NEOPIXEL_NUM) && NEOPIXEL_NUM > 0
static Adafruit_NeoPixel important_notify_pixels(NEOPIXEL_NUM, PIN_NEOPIXEL, NEO_GRB + NEO_KHZ800);
static bool important_notify_pixels_ready = false;
static unsigned long important_notify_pixels_next = 0;
static uint8_t important_notify_pixels_step = 0;

static void importantNotifyPixelsBegin() {
  if (important_notify_pixels_ready) return;
  important_notify_pixels.begin();
  important_notify_pixels.clear();
  important_notify_pixels.show();
  important_notify_pixels_ready = true;
}

static void importantNotifyPixelsOff() {
  importantNotifyPixelsBegin();
  important_notify_pixels.clear();
  important_notify_pixels.show();
  important_notify_pixels_next = 0;
}

static void importantNotifyPixelsHandler(bool allow_visual) {
  if (!allow_visual) {
    importantNotifyPixelsOff();
    return;
  }
  unsigned long now = millis();
  if (smartui::optionalDeadlinePending((uint32_t)now,
                                       (uint32_t)important_notify_pixels_next)) return;

  importantNotifyPixelsBegin();
  important_notify_pixels.clear();
  uint8_t brightness = UI_IMPORTANT_NOTIFY_NEOPIXEL_BRIGHTNESS;
  if ((important_notify_pixels_step & 0x03) == 0) {
    important_notify_pixels.setPixelColor(0, important_notify_pixels.Color(brightness, 0, 0));
    if (NEOPIXEL_NUM > 1) important_notify_pixels.setPixelColor(1, important_notify_pixels.Color(0, brightness, 0));
  } else if ((important_notify_pixels_step & 0x03) == 1) {
    important_notify_pixels.setPixelColor(0, important_notify_pixels.Color(0, brightness, 0));
    if (NEOPIXEL_NUM > 1) important_notify_pixels.setPixelColor(1, important_notify_pixels.Color(brightness, 0, 0));
  }
  important_notify_pixels.show();
  important_notify_pixels_step++;
  important_notify_pixels_next = now + UI_IMPORTANT_NOTIFY_NEOPIXEL_STEP_MS;
}
#endif

static const char* quick_reply_texts[] = {
  "Да",
  "Нет",
  "Потом",
  "Сейчас",
  "Завтра",
  "Сегодня",
  "Привет",
  "Пока",
  "Тест?"
};
static const uint8_t quick_reply_count = sizeof(quick_reply_texts) / sizeof(quick_reply_texts[0]);

#if UI_QUICK_REPLY_KEYBOARD
enum QuickReplyKeyboardAction {
  QR_KB_TEXT,
  QR_KB_SPACE,
  QR_KB_DELETE,
  QR_KB_SEND,
  QR_KB_BACK,
  QR_KB_PAGE
};

struct QuickReplyKeyboardKey {
  const char* label;
  uint8_t action;
  uint8_t page;
};

#define QR_KB_COLS 6
#define QR_KB_ROWS 4
#define QR_KB_KEYS (QR_KB_COLS * QR_KB_ROWS)
#define QR_KB_TEXT_KEY(s) { s, QR_KB_TEXT, 0 }
#define QR_KB_ACTION_KEY(label, action) { label, action, 0 }
#define QR_KB_PAGE_KEY(label, page_index) { label, QR_KB_PAGE, page_index }

static const QuickReplyKeyboardKey quick_reply_keyboard_pages[][QR_KB_KEYS] = {
  {
    QR_KB_TEXT_KEY("А"), QR_KB_TEXT_KEY("Б"), QR_KB_TEXT_KEY("В"), QR_KB_TEXT_KEY("Г"), QR_KB_TEXT_KEY("Д"), QR_KB_TEXT_KEY("Е"),
    QR_KB_TEXT_KEY("Ж"), QR_KB_TEXT_KEY("З"), QR_KB_TEXT_KEY("И"), QR_KB_TEXT_KEY("Й"), QR_KB_TEXT_KEY("К"), QR_KB_TEXT_KEY("Л"),
    QR_KB_TEXT_KEY("М"), QR_KB_TEXT_KEY("Н"), QR_KB_TEXT_KEY("О"), QR_KB_TEXT_KEY("П"), QR_KB_TEXT_KEY("Р"), QR_KB_TEXT_KEY("С"),
    QR_KB_PAGE_KEY("ТЯ", 1), QR_KB_ACTION_KEY("_", QR_KB_SPACE), QR_KB_ACTION_KEY("<-", QR_KB_DELETE),
    QR_KB_ACTION_KEY("OK", QR_KB_SEND), QR_KB_PAGE_KEY("123", 2), QR_KB_ACTION_KEY("X", QR_KB_BACK)
  },
  {
    QR_KB_TEXT_KEY("Т"), QR_KB_TEXT_KEY("У"), QR_KB_TEXT_KEY("Ф"), QR_KB_TEXT_KEY("Х"), QR_KB_TEXT_KEY("Ц"), QR_KB_TEXT_KEY("Ч"),
    QR_KB_TEXT_KEY("Ш"), QR_KB_TEXT_KEY("Щ"), QR_KB_TEXT_KEY("Ъ"), QR_KB_TEXT_KEY("Ы"), QR_KB_TEXT_KEY("Ь"), QR_KB_TEXT_KEY("Э"),
    QR_KB_TEXT_KEY("Ю"), QR_KB_TEXT_KEY("Я"), QR_KB_TEXT_KEY("."), QR_KB_TEXT_KEY(","), QR_KB_TEXT_KEY("?"), QR_KB_TEXT_KEY("!"),
    QR_KB_PAGE_KEY("АС", 0), QR_KB_ACTION_KEY("_", QR_KB_SPACE), QR_KB_ACTION_KEY("<-", QR_KB_DELETE),
    QR_KB_ACTION_KEY("OK", QR_KB_SEND), QR_KB_PAGE_KEY("123", 2), QR_KB_ACTION_KEY("X", QR_KB_BACK)
  },
  {
    QR_KB_TEXT_KEY("1"), QR_KB_TEXT_KEY("2"), QR_KB_TEXT_KEY("3"), QR_KB_TEXT_KEY("4"), QR_KB_TEXT_KEY("5"), QR_KB_TEXT_KEY("6"),
    QR_KB_TEXT_KEY("7"), QR_KB_TEXT_KEY("8"), QR_KB_TEXT_KEY("9"), QR_KB_TEXT_KEY("0"), QR_KB_TEXT_KEY("."), QR_KB_TEXT_KEY(","),
    QR_KB_TEXT_KEY("?"), QR_KB_TEXT_KEY("!"), QR_KB_TEXT_KEY(":"), QR_KB_TEXT_KEY(";"), QR_KB_TEXT_KEY("-"), QR_KB_TEXT_KEY("+"),
    QR_KB_PAGE_KEY("АС", 0), QR_KB_ACTION_KEY("_", QR_KB_SPACE), QR_KB_ACTION_KEY("<-", QR_KB_DELETE),
    QR_KB_ACTION_KEY("OK", QR_KB_SEND), QR_KB_PAGE_KEY("ТЯ", 1), QR_KB_ACTION_KEY("X", QR_KB_BACK)
  }
};

static const uint8_t quick_reply_keyboard_page_count = sizeof(quick_reply_keyboard_pages) / sizeof(quick_reply_keyboard_pages[0]);

enum QuickReplyTargetMode {
  QR_TARGET_CLOSED,
  QR_TARGET_KIND,
  QR_TARGET_CHANNEL,
  QR_TARGET_CONTACT
};
#endif

static ColorVal uiSemanticColor(uint8_t idx) {
  switch (idx) {
    case 1: return DisplayDriver::GREEN;
    case 2: return DisplayDriver::YELLOW;
    case 3: return DisplayDriver::BLUE;
    case 4: return DisplayDriver::ORANGE;
    case 5: return DisplayDriver::RED;
    case 0:
    default: return DisplayDriver::LIGHT;
  }
}

static const char* uiSemanticColorName(uint8_t idx) {
  switch (idx) {
    case 1: return "Зеленый";
    case 2: return "Желтый";
    case 3: return "Синий";
    case 4: return "Оранжевый";
    case 5: return "Красный";
    case 0:
    default: return "Белый";
  }
}

#ifndef UI_ADC_MULTIPLIER_PAGE
  #define UI_ADC_MULTIPLIER_PAGE 0
#endif

#ifndef UI_TIMEZONE_PAGE
  #define UI_TIMEZONE_PAGE UI_COMPACT_SETTINGS_MENU
#endif

#ifndef UI_CLIENT_REPEAT_PAGE
  #define UI_CLIENT_REPEAT_PAGE 0
#endif

#ifndef UI_AUTO_ADVERT_PAGE
  #define UI_AUTO_ADVERT_PAGE 0
#endif

#ifndef UI_BACKLIGHT_TIMEOUT_PAGE
  #define UI_BACKLIGHT_TIMEOUT_PAGE 1
#endif

#ifndef UI_COMPACT_SETTINGS_MAX_ROWS
  #define UI_COMPACT_SETTINGS_MAX_ROWS 4
#endif

#ifndef UI_SOUND_SETTINGS_GROUP
  #define UI_SOUND_SETTINGS_GROUP 1
#endif

#ifndef UI_NOTIFICATION_SETTINGS
  #define UI_NOTIFICATION_SETTINGS 1
#endif

#ifndef UI_CH2_RELAY_PAGE
  #define UI_CH2_RELAY_PAGE 0
#endif

#ifndef UI_ADC_MULTIPLIER_FINE_STEP
  #define UI_ADC_MULTIPLIER_FINE_STEP 0.005f
#endif

#ifndef UI_ADC_MULTIPLIER_MIN
  #ifdef ADC_MULTIPLIER
    #define UI_ADC_MULTIPLIER_MIN ((float)(ADC_MULTIPLIER) * 0.75f)
  #else
    #define UI_ADC_MULTIPLIER_MIN 0.1f
  #endif
#endif

#ifndef UI_ADC_MULTIPLIER_MAX
  #ifdef ADC_MULTIPLIER
    #define UI_ADC_MULTIPLIER_MAX ((float)(ADC_MULTIPLIER) * 1.25f)
  #else
    #define UI_ADC_MULTIPLIER_MAX 10.0f
  #endif
#endif

#if UI_HAS_JOYSTICK
  #define PRESS_LABEL "ввод"
#else
  #define PRESS_LABEL "удерж."
#endif

#include "icons.h"

static int uiBatteryPercentage(uint16_t milli_volts) {
#ifndef BATT_MIN_MILLIVOLTS
  #define BATT_MIN_MILLIVOLTS 3000
#endif
#ifndef BATT_MAX_MILLIVOLTS
  #define BATT_MAX_MILLIVOLTS 4200
#endif
  if (milli_volts == 0) return 0;
  int pct = ((int)milli_volts - BATT_MIN_MILLIVOLTS) * 100 / (BATT_MAX_MILLIVOLTS - BATT_MIN_MILLIVOLTS);
  if (pct < 0) pct = 0;
  if (pct > 100) pct = 100;
  return pct;
}

static ColorVal uiBatteryStatusColor(uint16_t milli_volts) {
  int pct = uiBatteryPercentage(milli_volts);
  if (pct <= 15) return DisplayDriver::RED;
  if (pct <= 35) return DisplayDriver::YELLOW;
  return DisplayDriver::GREEN;
}

static void drawUiBatteryIcon(DisplayDriver& display, int x, int y, int w, int h, uint16_t milli_volts) {
  display.setColor(uiBatteryStatusColor(milli_volts));
  display.drawRect(x, y, w, h);
  display.fillRect(x + w, y + 3, 2, h - 6);
  int fill_w = milli_volts > 0 ? ((w - 4) * uiBatteryPercentage(milli_volts) + 50) / 100 : 0;
  if (fill_w < 0) fill_w = 0;
  if (fill_w > w - 4) fill_w = w - 4;
  if (fill_w > 0) display.fillRect(x + 2, y + 2, fill_w, h - 4);
}

static void drawUiXbmScaled(DisplayDriver& display, int x, int y, const uint8_t* bits, int w, int h, int scale) {
  if (scale <= 1) {
    display.drawXbm(x, y, bits, w, h);
    return;
  }
  int byte_width = (w + 7) / 8;
  for (int row = 0; row < h; row++) {
    for (int col = 0; col < w; col++) {
      uint8_t byte = pgm_read_byte(bits + row * byte_width + col / 8);
      if (byte & (0x80 >> (col & 7))) {
        display.fillRect(x + col * scale, y + row * scale, scale, scale);
      }
    }
  }
}

static void drawUiXbmFitted(DisplayDriver& display, int x, int y, const uint8_t* bits, int w, int h, int target_w, int target_h) {
  if (target_w <= 0 || target_h <= 0) return;
  if (target_w == w && target_h == h) {
    display.drawXbm(x, y, bits, w, h);
    return;
  }
  int byte_width = (w + 7) / 8;
  for (int dy = 0; dy < target_h; dy++) {
    int src_y = ((dy * 2 + 1) * h) / (target_h * 2);
    if (src_y >= h) src_y = h - 1;
    int run_start = -1;
    for (int dx = 0; dx <= target_w; dx++) {
      bool set = false;
      if (dx < target_w) {
        int src_x = ((dx * 2 + 1) * w) / (target_w * 2);
        if (src_x >= w) src_x = w - 1;
        uint8_t byte = pgm_read_byte(bits + src_y * byte_width + src_x / 8);
        set = (byte & (0x80 >> (src_x & 7))) != 0;
      }
      if (set) {
        if (run_start < 0) run_start = dx;
      } else if (run_start >= 0) {
        display.fillRect(x + run_start, y + dy, dx - run_start, 1);
        run_start = -1;
      }
    }
  }
}

static void uiIconFill(DisplayDriver& display, int x, int y, int size, int gx, int gy, int gw, int gh) {
  const int grid = 12;
  int x1 = x + (gx * size) / grid;
  int y1 = y + (gy * size) / grid;
  int x2 = x + ((gx + gw) * size + grid - 1) / grid;
  int y2 = y + ((gy + gh) * size + grid - 1) / grid;
  if (x2 <= x1) x2 = x1 + 1;
  if (y2 <= y1) y2 = y1 + 1;
  display.fillRect(x1, y1, x2 - x1, y2 - y1);
}

static int uiIconStroke(int size) {
  return size >= 13 ? 2 : 1;
}

static void uiIconDiag(DisplayDriver& display, int x, int y, int size, bool rising) {
  int stroke = uiIconStroke(size);
  for (int i = 0; i < size; i += stroke) {
    int px = x + i;
    int py = rising ? y + size - 1 - i : y + i;
    display.fillRect(px, py, stroke, stroke);
  }
}

static void uiIconFaceOutline(DisplayDriver& display, int x, int y, int size) {
  uiIconFill(display, x, y, size, 3, 0, 6, 1);
  uiIconFill(display, x, y, size, 1, 1, 10, 1);
  uiIconFill(display, x, y, size, 0, 3, 1, 6);
  uiIconFill(display, x, y, size, 11, 3, 1, 6);
  uiIconFill(display, x, y, size, 1, 10, 10, 1);
  uiIconFill(display, x, y, size, 3, 11, 6, 1);
}

static bool uiIconIsFaceIcon(const uint8_t* icon) {
  return icon == emoji_smile_icon || icon == emoji_grin_icon || icon == emoji_laugh_icon ||
         icon == emoji_wink_icon || icon == emoji_love_face_icon || icon == emoji_cool_icon ||
         icon == emoji_think_icon || icon == emoji_neutral_icon || icon == emoji_surprise_icon ||
         icon == emoji_sleep_icon || icon == emoji_sad_icon || icon == emoji_cry_icon ||
         icon == emoji_angry_icon || icon == emoji_unknown_icon || icon == client_repeat_unknown_icon;
}

static void uiIconDrawEyes(DisplayDriver& display, int x, int y, int size, const uint8_t* icon) {
  if (icon == emoji_wink_icon) {
    uiIconFill(display, x, y, size, 3, 4, 2, 1);
    uiIconFill(display, x, y, size, 8, 4, 1, 2);
  } else if (icon == emoji_cool_icon) {
    uiIconFill(display, x, y, size, 2, 4, 3, 2);
    uiIconFill(display, x, y, size, 7, 4, 3, 2);
    uiIconFill(display, x, y, size, 5, 5, 2, 1);
  } else if (icon == emoji_love_face_icon) {
    uiIconFill(display, x, y, size, 2, 3, 2, 1);
    uiIconFill(display, x, y, size, 1, 4, 4, 1);
    uiIconFill(display, x, y, size, 2, 5, 2, 1);
    uiIconFill(display, x, y, size, 8, 3, 2, 1);
    uiIconFill(display, x, y, size, 7, 4, 4, 1);
    uiIconFill(display, x, y, size, 8, 5, 2, 1);
  } else if (icon == emoji_sleep_icon) {
    uiIconFill(display, x, y, size, 3, 4, 2, 1);
    uiIconFill(display, x, y, size, 8, 4, 2, 1);
    uiIconFill(display, x, y, size, 8, 1, 3, 1);
    uiIconFill(display, x, y, size, 9, 2, 1, 1);
    uiIconFill(display, x, y, size, 8, 3, 3, 1);
  } else if (icon == emoji_angry_icon) {
    uiIconFill(display, x, y, size, 2, 3, 3, 1);
    uiIconFill(display, x, y, size, 8, 3, 3, 1);
    uiIconFill(display, x, y, size, 3, 5, 1, 1);
    uiIconFill(display, x, y, size, 8, 5, 1, 1);
  } else {
    uiIconFill(display, x, y, size, 3, 4, 1, 2);
    uiIconFill(display, x, y, size, 8, 4, 1, 2);
  }
}

static bool uiIconDrawFace(DisplayDriver& display, int x, int y, const uint8_t* icon, int size) {
  if (!uiIconIsFaceIcon(icon)) return false;
  uiIconFaceOutline(display, x, y, size);
  uiIconDrawEyes(display, x, y, size, icon);

  if (icon == emoji_grin_icon) {
    uiIconFill(display, x, y, size, 3, 7, 6, 1);
    uiIconFill(display, x, y, size, 3, 9, 6, 1);
    uiIconFill(display, x, y, size, 3, 8, 1, 1);
    uiIconFill(display, x, y, size, 8, 8, 1, 1);
  } else if (icon == emoji_laugh_icon) {
    uiIconFill(display, x, y, size, 3, 7, 6, 3);
  } else if (icon == emoji_neutral_icon) {
    uiIconFill(display, x, y, size, 3, 8, 6, 1);
  } else if (icon == emoji_surprise_icon || icon == client_repeat_unknown_icon) {
    uiIconFill(display, x, y, size, 5, 7, 2, 1);
    uiIconFill(display, x, y, size, 4, 8, 4, 1);
    uiIconFill(display, x, y, size, 5, 9, 2, 1);
  } else if (icon == emoji_sad_icon || icon == emoji_cry_icon) {
    uiIconFill(display, x, y, size, 4, 7, 4, 1);
    uiIconFill(display, x, y, size, 3, 8, 1, 1);
    uiIconFill(display, x, y, size, 8, 8, 1, 1);
    if (icon == emoji_cry_icon) uiIconFill(display, x, y, size, 9, 6, 1, 3);
  } else if (icon == emoji_angry_icon) {
    uiIconFill(display, x, y, size, 3, 8, 6, 1);
  } else if (icon == emoji_think_icon || icon == emoji_unknown_icon) {
    uiIconFill(display, x, y, size, 5, 7, 4, 1);
    uiIconFill(display, x, y, size, 8, 8, 1, 1);
    uiIconFill(display, x, y, size, 7, 9, 2, 1);
  } else {
    uiIconFill(display, x, y, size, 4, 8, 4, 1);
    uiIconFill(display, x, y, size, 3, 7, 1, 1);
    uiIconFill(display, x, y, size, 8, 7, 1, 1);
  }
  return true;
}

static void uiIconDrawEnvelope(DisplayDriver& display, int x, int y, int size) {
  display.drawRect(x + 1, y + (size * 3) / 12, size - 2, (size * 7) / 12);
  uiIconFill(display, x, y, size, 2, 4, 1, 1);
  uiIconFill(display, x, y, size, 3, 5, 1, 1);
  uiIconFill(display, x, y, size, 4, 6, 1, 1);
  uiIconFill(display, x, y, size, 5, 7, 2, 1);
  uiIconFill(display, x, y, size, 8, 6, 1, 1);
  uiIconFill(display, x, y, size, 9, 5, 1, 1);
}

static void uiIconDrawTower(DisplayDriver& display, int x, int y, int size) {
  uiIconFill(display, x, y, size, 5, 2, 2, 8);
  uiIconFill(display, x, y, size, 3, 10, 6, 1);
  uiIconFill(display, x, y, size, 2, 6, 8, 1);
  uiIconFill(display, x, y, size, 1, 2, 2, 1);
  uiIconFill(display, x, y, size, 9, 2, 2, 1);
  uiIconFill(display, x, y, size, 0, 0, 3, 1);
  uiIconFill(display, x, y, size, 9, 0, 3, 1);
}

static void uiIconDrawPager(DisplayDriver& display, int x, int y, int size) {
  display.drawRect(x + 1, y + 2, size - 2, size - 4);
  uiIconFill(display, x, y, size, 3, 4, 6, 2);
  uiIconFill(display, x, y, size, 3, 8, 1, 1);
  uiIconFill(display, x, y, size, 5, 8, 1, 1);
  uiIconFill(display, x, y, size, 7, 8, 1, 1);
  uiIconFill(display, x, y, size, 9, 8, 1, 1);
}

static void uiIconDrawSatellite(DisplayDriver& display, int x, int y, int size) {
  uiIconFill(display, x, y, size, 5, 4, 3, 3);
  uiIconFill(display, x, y, size, 1, 4, 3, 2);
  uiIconFill(display, x, y, size, 9, 4, 3, 2);
  uiIconFill(display, x, y, size, 4, 5, 1, 1);
  uiIconFill(display, x, y, size, 8, 5, 1, 1);
  uiIconFill(display, x, y, size, 6, 2, 1, 2);
  uiIconFill(display, x, y, size, 7, 1, 1, 1);
  uiIconFill(display, x, y, size, 9, 0, 1, 1);
  uiIconFill(display, x, y, size, 10, 2, 1, 1);
  uiIconFill(display, x, y, size, 5, 8, 1, 2);
  uiIconFill(display, x, y, size, 7, 8, 1, 2);
}

static void uiIconDrawMute(DisplayDriver& display, int x, int y, int size) {
  uiIconFill(display, x, y, size, 1, 5, 3, 3);
  uiIconFill(display, x, y, size, 4, 4, 2, 5);
  uiIconDiag(display, x + 1, y + 1, size - 2, true);
}

static void uiIconDrawRelayPacket(DisplayDriver& display, int x, int y, int size) {
  uiIconFill(display, x, y, size, 1, 2, 3, 3);
  uiIconFill(display, x, y, size, 8, 2, 3, 3);
  uiIconFill(display, x, y, size, 5, 8, 3, 3);
  uiIconFill(display, x, y, size, 4, 4, 1, 1);
  uiIconFill(display, x, y, size, 7, 4, 1, 1);
  uiIconFill(display, x, y, size, 5, 6, 1, 1);
  uiIconFill(display, x, y, size, 7, 6, 1, 1);
}

static void uiIconDrawHome(DisplayDriver& display, int x, int y, int size) {
  uiIconFill(display, x, y, size, 5, 1, 2, 1);
  uiIconFill(display, x, y, size, 4, 2, 4, 1);
  uiIconFill(display, x, y, size, 3, 3, 6, 1);
  uiIconFill(display, x, y, size, 2, 4, 8, 1);
  display.drawRect(x + (size * 3) / 12, y + (size * 5) / 12, (size * 6) / 12, (size * 6) / 12);
  uiIconFill(display, x, y, size, 5, 8, 2, 3);
}

static void uiIconDrawSignal(DisplayDriver& display, int x, int y, int size) {
  uiIconFill(display, x, y, size, 2, 9, 2, 2);
  uiIconFill(display, x, y, size, 5, 7, 2, 4);
  uiIconFill(display, x, y, size, 8, 4, 2, 7);
}

static void uiIconDrawBattery(DisplayDriver& display, int x, int y, int size) {
  int w = size - 2;
  int h = (size * 7) / 12;
  int yy = y + (size - h) / 2;
  display.drawRect(x, yy, w, h);
  display.fillRect(x + w, yy + h / 3, 2, h / 3 + 1);
  display.fillRect(x + 2, yy + 2, w - 5, h - 4);
}

static void uiIconDrawHeart(DisplayDriver& display, int x, int y, int size) {
  uiIconFill(display, x, y, size, 2, 2, 3, 2);
  uiIconFill(display, x, y, size, 7, 2, 3, 2);
  uiIconFill(display, x, y, size, 1, 4, 10, 2);
  uiIconFill(display, x, y, size, 2, 6, 8, 2);
  uiIconFill(display, x, y, size, 4, 8, 4, 2);
  uiIconFill(display, x, y, size, 5, 10, 2, 1);
}

static void uiIconDrawWarn(DisplayDriver& display, int x, int y, int size) {
  uiIconFill(display, x, y, size, 5, 1, 2, 2);
  uiIconFill(display, x, y, size, 4, 3, 4, 2);
  uiIconFill(display, x, y, size, 3, 5, 6, 2);
  uiIconFill(display, x, y, size, 2, 7, 8, 2);
  uiIconFill(display, x, y, size, 1, 9, 10, 1);
  uiIconFill(display, x, y, size, 5, 4, 2, 3);
  uiIconFill(display, x, y, size, 5, 8, 2, 1);
}

static void uiIconDrawLock(DisplayDriver& display, int x, int y, int size) {
  uiIconFill(display, x, y, size, 4, 1, 4, 1);
  uiIconFill(display, x, y, size, 3, 2, 1, 3);
  uiIconFill(display, x, y, size, 8, 2, 1, 3);
  display.drawRect(x + (size * 2) / 12, y + (size * 5) / 12, (size * 8) / 12, (size * 6) / 12);
  uiIconFill(display, x, y, size, 5, 7, 2, 2);
}

static bool drawUiProceduralIcon(DisplayDriver& display, int x, int y, const uint8_t* icon, int size) {
  if (icon == NULL || size <= 0) return false;
  if (uiIconDrawFace(display, x, y, icon, size)) return true;
  if (icon == direct_packet_icon || icon == emoji_msg_icon || icon == emoji_mail_icon || icon == emoji_note_icon) {
    uiIconDrawEnvelope(display, x, y, size);
    return true;
  }
  if (icon == relay_packet_icon) {
    uiIconDrawRelayPacket(display, x, y, size);
    return true;
  }
  if (icon == tower_route_icon || icon == relay_status_icon || icon == emoji_antenna_icon || icon == emoji_radio_icon) {
    uiIconDrawTower(display, x, y, size);
    return true;
  }
  if (icon == pager_route_icon || icon == emoji_pager_icon) {
    uiIconDrawPager(display, x, y, size);
    return true;
  }
  if (icon == satellite_icon || icon == emoji_location_icon) {
    uiIconDrawSatellite(display, x, y, size);
    return true;
  }
  if (icon == muted_icon || icon == emoji_sound_icon) {
    uiIconDrawMute(display, x, y, size);
    return true;
  }
  if (icon == emoji_home_icon || icon == emoji_building_icon || icon == emoji_factory_icon) {
    uiIconDrawHome(display, x, y, size);
    return true;
  }
  if (icon == emoji_signal_icon || icon == mesh_traffic_icon) {
    uiIconDrawSignal(display, x, y, size);
    return true;
  }
  if (icon == emoji_battery_icon || icon == emoji_plug_icon) {
    uiIconDrawBattery(display, x, y, size);
    return true;
  }
  if (icon == emoji_heart_icon) {
    uiIconDrawHeart(display, x, y, size);
    return true;
  }
  if (icon == emoji_warn_icon) {
    uiIconDrawWarn(display, x, y, size);
    return true;
  }
  if (icon == emoji_lock_icon || icon == emoji_key_icon) {
    uiIconDrawLock(display, x, y, size);
    return true;
  }
  if (icon == emoji_check_icon) {
    uiIconDiag(display, x + 1, y + 1, size - 2, true);
    uiIconFill(display, x, y, size, 1, 7, 3, 2);
    return true;
  }
  if (icon == emoji_cross_icon) {
    uiIconDiag(display, x + 1, y + 1, size - 2, false);
    uiIconDiag(display, x + 1, y + 1, size - 2, true);
    return true;
  }
  return false;
}

#if UI_T096_PREMIUM_TFT || defined(HELTEC_T114_WITH_DISPLAY)
static bool drawUiIconpackV1(DisplayDriver& display, int x, int y, const uint16_t* rows, int size) {
  if (rows == NULL || size <= 0) return false;
  const int grid = 12;
  // Destination-driven nearest-neighbour sampling is intentional.  The old
  // source-driven ceil/floor rectangles overlapped adjacent cells, closing
  // one-pixel holes and turning small T114 icons into solid blocks.
  for (int dy = 0; dy < size; dy++) {
    int src_y = ((dy * 2 + 1) * grid) / (size * 2);
    if (src_y >= grid) src_y = grid - 1;
    uint16_t bits = pgm_read_word(rows + src_y);
    int run_start = -1;
    for (int dx = 0; dx <= size; dx++) {
      bool set = false;
      if (dx < size) {
        int src_x = ((dx * 2 + 1) * grid) / (size * 2);
        if (src_x >= grid) src_x = grid - 1;
        set = (bits & (1U << (grid - 1 - src_x))) != 0;
      }
      if (set) {
        if (run_start < 0) run_start = dx;
      } else if (run_start >= 0) {
        display.fillRect(x + run_start, y + dy, dx - run_start, 1);
        run_start = -1;
      }
    }
  }
  return true;
}
#endif

static int uiGpsBadgeScale(int size) {
  return size >= 14 ? 2 : 1;
}

static int uiGpsBadgeWidthForSize(int size) {
  return 25 * uiGpsBadgeScale(size);
}

static void drawUiGpsBadgeGlyph(DisplayDriver& display, int x, int y, int scale, const uint8_t rows[5]) {
  for (int row = 0; row < 5; row++) {
    for (int col = 0; col < 3; col++) {
      if (rows[row] & (1U << (2 - col))) {
        display.fillRect(x + col * scale, y + row * scale, scale, scale);
      }
    }
  }
}

static void drawUiGpsBadgeWaves(DisplayDriver& display, int x, int y, int scale, const uint8_t rows[5]) {
  for (int row = 0; row < 5; row++) {
    for (int col = 0; col < 6; col++) {
      if (rows[row] & (1U << (5 - col))) {
        display.fillRect(x + col * scale, y + row * scale, scale, scale);
      }
    }
  }
}

static void drawUiGpsBadge(DisplayDriver& display, int x, int y, int size) {
  static const uint8_t glyph_g[5] = {0x7, 0x4, 0x5, 0x5, 0x7};
  static const uint8_t glyph_p[5] = {0x6, 0x5, 0x6, 0x4, 0x4};
  static const uint8_t glyph_s[5] = {0x7, 0x4, 0x7, 0x1, 0x7};
  static const uint8_t waves_left[5] = {0x24, 0x12, 0x12, 0x12, 0x24};
  static const uint8_t waves_right[5] = {0x09, 0x12, 0x12, 0x12, 0x09};
  int scale = uiGpsBadgeScale(size);
  int glyph_h = 5 * scale;
  int yy = y + (size - glyph_h) / 2;
  if (yy < y) yy = y;

  // Two separated parenthesis-shaped waves on both sides of the GPS label.
  drawUiGpsBadgeWaves(display, x, yy, scale, waves_left);
  int text_x = x + 7 * scale;
  drawUiGpsBadgeGlyph(display, text_x, yy, scale, glyph_g);
  drawUiGpsBadgeGlyph(display, text_x + 4 * scale, yy, scale, glyph_p);
  drawUiGpsBadgeGlyph(display, text_x + 8 * scale, yy, scale, glyph_s);
  drawUiGpsBadgeWaves(display, x + 19 * scale, yy, scale, waves_right);
}

static void drawUiIcon(DisplayDriver& display, int x, int y, const uint8_t* icon, int size) {
  if (icon == satellite_icon) {
    drawUiGpsBadge(display, x, y, size);
    return;
  }
#if UI_T096_PREMIUM_TFT || defined(HELTEC_T114_WITH_DISPLAY)
  const MeshcoreIconpackV2Glyph* glyph = meshcoreIconpackV2Glyph(icon);
  // T114 status/chrome icons can be only 9-11 logical pixels high.  An
  // explicit 8x8 glyph survives that size better than downsampling 12x12.
  if (glyph != NULL && size < 12) {
    drawUiXbmFitted(display, x, y, glyph->small, 8, 8, size, size);
    return;
  }
  if (glyph != NULL && drawUiIconpackV1(display, x, y, glyph->large, size)) return;
#endif
  if (!drawUiProceduralIcon(display, x, y, icon, size)) {
    drawUiXbmFitted(display, x, y, icon, 8, 8, size, size);
  }
}

static ColorVal uiGpsStatusColor(bool enabled, bool valid) {
  if (!enabled) return DisplayDriver::RED;
  return valid ? DisplayDriver::GREEN : DisplayDriver::YELLOW;
}

static int uiStatusIconSize(DisplayDriver& display) {
#if UI_T096_PREMIUM_TFT
  (void)display;
  return 16;
#elif UI_NATIVE_TFT_PROFILE
  int line_h = display.getTextLineHeight();
  int size = line_h - 1;
  if (size < 9) return 9;
  if (size > 12) return 12;
  return size;
#else
  (void)display;
  return 8;
#endif
}

static int uiStatusIconAdvance(DisplayDriver& display) {
  int size = uiStatusIconSize(display);
  return size + (size > 8 ? 2 : 1);
}

static void drawUiStatusIcon(DisplayDriver& display, int x, int y, const uint8_t* icon) {
  int size = uiStatusIconSize(display);
  drawUiIcon(display, x, y, icon, size);
}

static int uiGpsStatusIconWidth(DisplayDriver& display) {
  return uiGpsBadgeWidthForSize(uiStatusIconSize(display));
}

static void drawUiGpsStatusIcon(DisplayDriver& display, int x, int y, bool enabled, bool valid) {
  int size = uiStatusIconSize(display);
  display.setColor(uiGpsStatusColor(enabled, valid));
  drawUiIcon(display, x, y, satellite_icon, size);
}

static void printOriginNameBold(DisplayDriver& display, const char* origin) {
  if (origin == NULL) return;

  const char* name = origin;
  const char* prefix_end = strstr(origin, ") ");
  if (origin[0] == '(' && prefix_end != NULL) {
    name = prefix_end + 2;
  }

  if (name > origin) {
    char prefix[16];
    size_t prefix_len = name - origin;
    if (prefix_len >= sizeof(prefix)) prefix_len = sizeof(prefix) - 1;
    memcpy(prefix, origin, prefix_len);
    prefix[prefix_len] = 0;
    display.setBold(false);
    display.print(prefix);
  }

  display.setBold(true);
  display.print(name);
  display.setBold(false);
}

static size_t richUtf8Len(const char* s) {
  uint8_t c = (uint8_t)s[0];
  if (c == 0) return 0;
  size_t expected = 1;
  if (c < 0x80) expected = 1;
  else if ((c & 0xE0) == 0xC0) expected = 2;
  else if ((c & 0xF0) == 0xE0) expected = 3;
  else if ((c & 0xF8) == 0xF0) expected = 4;
  for (size_t i = 1; i < expected; i++) {
    if (s[i] == 0) return i;
    if (((uint8_t)s[i] & 0xC0) != 0x80) return 1;
  }
  return expected;
}

static bool richIgnorableUtf8Mark(const char* src, size_t* consumed) {
  if (src == NULL || consumed == NULL || src[0] == 0) return false;
  const uint8_t* b = (const uint8_t*)src;
  if (src[1] != 0 && src[2] != 0 &&
      ((b[0] == 0xEF && b[1] == 0xB8 && (b[2] == 0x8F || b[2] == 0x8E)) ||
       (b[0] == 0xE2 && b[1] == 0x80 && b[2] == 0x8D))) {
    *consumed = 3;
    return true;
  }
  if (src[1] != 0 && src[2] != 0 && src[3] != 0 &&
      b[0] == 0xF0 && b[1] == 0x9F && b[2] == 0x8F &&
      b[3] >= 0xBB && b[3] <= 0xBF) {
    *consumed = 4;
    return true;
  }
  return false;
}

static const uint8_t* richAsciiEmojiIconAt(const char* src, size_t* consumed) {
  if (src == NULL || consumed == NULL || src[0] == 0) return NULL;

  static const char* const aliases[] = {
    ":'(", "T_T", ">:(", ":)", ":D", "xD", "^^", ";)", "B)", "<3"
  };
  for (size_t i = 0; i < sizeof(aliases) / sizeof(aliases[0]); i++) {
    size_t len = strlen(aliases[i]);
    if (strncmp(src, aliases[i], len) == 0) {
      const uint8_t* icon = meshcoreEmojiAliasIcon(aliases[i]);
      if (icon) {
        *consumed = len;
        return icon;
      }
    }
  }

  if (src[0] == '[') {
    const char* end = strchr(src, ']');
    if (end != NULL) {
      size_t len = end - src + 1;
      if (len > 2 && len < 16) {
        char alias[16];
        memcpy(alias, src, len);
        alias[len] = 0;
        const uint8_t* icon = meshcoreEmojiAliasIcon(alias);
        if (icon) {
          *consumed = len;
          return icon;
        }
      }
    }
  }

  return NULL;
}

static const uint8_t* richEmojiIconAt(const char* src, size_t* consumed) {
  size_t alias_consumed = 0;
  const char* alias = meshcoreEmojiAlias(src, &alias_consumed);
  if (alias) {
    const uint8_t* icon = meshcoreEmojiAliasIcon(alias);
    if (icon) {
      *consumed = alias_consumed;
      return icon;
    }
  }

  const uint8_t* ascii_icon = richAsciiEmojiIconAt(src, consumed);
  if (ascii_icon) return ascii_icon;

  size_t ignored = 0;
  if (richIgnorableUtf8Mark(src, &ignored)) return NULL;

  const uint8_t first = (uint8_t)src[0];
  if (first >= 0xE0) {
    const char* p = src;
    uint16_t cp = meshcoreReadUtf8Codepoint(p);
    size_t len = p - src;
    if (cp == '?' && len > 1) {
      *consumed = len;
      return emoji_unknown_icon;
    }
  }
  return NULL;
}

static int uiLineIconSize(DisplayDriver& display) {
  int line_h = display.getTextLineHeight();
#if UI_T096_PREMIUM_TFT
  if (line_h >= 23) return 24;
  if (line_h >= 14) return 16;
#elif UI_NATIVE_TFT_PROFILE
  if (line_h >= 18) return 14;
  if (line_h > 8) {
    int size = line_h - 1;
    if (size < 9) size = 9;
    if (size > 12) size = 12;
    return size;
  }
#else
  (void)display;
#endif
  return 8;
}

static int uiLineIconAdvance(DisplayDriver& display, const uint8_t* icon = NULL) {
  int size = uiLineIconSize(display);
  int width = icon == satellite_icon ? uiGpsBadgeWidthForSize(size) : size;
  return width + (size > 8 ? 2 : 1);
}

static int uiLineIconY(DisplayDriver& display, int y) {
  int line_h = display.getTextLineHeight();
  int icon_h = uiLineIconSize(display);
  int dy = (line_h - icon_h) / 2;
  if (dy < 0) dy = 0;
  return y + dy;
}

static void drawUiLineIcon(DisplayDriver& display, int x, int y, const uint8_t* icon) {
  int size = uiLineIconSize(display);
  drawUiIcon(display, x, uiLineIconY(display, y), icon, size);
}

static int uiRouteIconSize(DisplayDriver& display) {
#if UI_T096_PREMIUM_TFT
  (void)display;
  return 16;
#elif UI_NATIVE_TFT_PROFILE
  int line_h = display.getTextLineHeight();
  if (line_h >= 18) return 14;
  if (line_h > 8) {
    int size = line_h - 1;
    if (size < 9) size = 9;
    if (size > 12) size = 12;
    return size;
  }
#else
  (void)display;
#endif
  return 8;
}

static int uiRouteIconGap(DisplayDriver& display) {
  return uiRouteIconSize(display) > 8 ? 2 : 1;
}

static int uiRouteIconY(DisplayDriver& display, int y) {
  int line_h = display.getTextLineHeight();
  int icon_h = uiRouteIconSize(display);
  int dy = (line_h - icon_h) / 2;
  if (dy < 0) dy = 0;
  return y + dy;
}

static bool richSupportedCodepoint(uint16_t cp) {
  return (cp >= 32 && cp <= 126) || (cp >= 0x0400 && cp <= 0x04FF) ||
         cp == 0x00B0 || cp == 0x2116;
}

static int richCodepointWidth(DisplayDriver& display, uint16_t cp) {
  char tmp[5];
  size_t len = 0;
  if (!meshcoreAppendUtf8Codepoint(tmp, sizeof(tmp), len, cp)) return 0;
  tmp[len] = 0;
  return display.getTextWidth(tmp);
}

static bool richAppendFallbackByte(char* run, size_t run_size, size_t& run_len, uint8_t first, bool allow_cp1251) {
  uint16_t cp1251;
  if (allow_cp1251 && meshcoreCp1251Codepoint(first, &cp1251)) {
    return meshcoreAppendUtf8Codepoint(run, run_size, run_len, cp1251);
  }
  if (run_len + 1 >= run_size) return false;
  run[run_len++] = '*';
  return true;
}

static int richFallbackByteWidth(DisplayDriver& display, uint8_t first, bool allow_cp1251) {
  uint16_t cp1251;
  if (allow_cp1251 && meshcoreCp1251Codepoint(first, &cp1251)) {
    return richCodepointWidth(display, cp1251);
  }
  return display.getTextWidth("*");
}

static int richTokenWidth(DisplayDriver& display, const char* src) {
  size_t consumed = 0;
  const uint8_t* icon = richEmojiIconAt(src, &consumed);
  if (icon) return uiLineIconAdvance(display, icon);
  if (richIgnorableUtf8Mark(src, &consumed)) return 0;

  const char* p = src;
  uint8_t first = (uint8_t)*src;
  uint16_t cp = meshcoreReadUtf8Codepoint(p);
  if (cp == '\r' || cp == '\n') return 0;
  if (!richSupportedCodepoint(cp)) return richFallbackByteWidth(display, first, p - src == 1);

  char tmp[8];
  size_t len = p - src;
  if (len >= sizeof(tmp)) len = sizeof(tmp) - 1;
  memcpy(tmp, src, len);
  tmp[len] = 0;
  return display.getTextWidth(tmp);
}

static int richTextWidth(DisplayDriver& display, const char* text) {
  int width = 0;
  int max_width = 0;
  const char* p = text;
  while (p && *p) {
    size_t consumed = 0;
    const uint8_t* icon = richEmojiIconAt(p, &consumed);
    if (icon) {
      width += uiLineIconAdvance(display, icon);
      p += consumed;
      continue;
    }
    if (richIgnorableUtf8Mark(p, &consumed)) {
      p += consumed;
      continue;
    }

    const char* start = p;
    uint8_t first = (uint8_t)*start;
    uint16_t cp = meshcoreReadUtf8Codepoint(p);
    if (cp == '\n') {
      if (width > max_width) max_width = width;
      width = 0;
      continue;
    }
    if (cp == '\r') continue;
    if (!richSupportedCodepoint(cp)) {
      width += richFallbackByteWidth(display, first, p - start == 1);
      continue;
    }
    char tmp[8];
    size_t len = p - start;
    if (len >= sizeof(tmp)) len = sizeof(tmp) - 1;
    memcpy(tmp, start, len);
    tmp[len] = 0;
    width += display.getTextWidth(tmp);
  }
  return width > max_width ? width : max_width;
}

static void flushRichRun(DisplayDriver& display, int& x, int y, char* run, size_t& run_len) {
  if (run_len == 0) return;
  run[run_len] = 0;
  display.setCursor(x, y);
  display.print(run);
  x += display.getTextWidth(run);
  run_len = 0;
}

static void drawRichTextLine(DisplayDriver& display, int x, int y, const char* text) {
  char run[96];
  size_t run_len = 0;
  const char* p = text;

  while (p && *p) {
    size_t consumed = 0;
    const uint8_t* icon = richEmojiIconAt(p, &consumed);
    if (icon) {
      flushRichRun(display, x, y, run, run_len);
      drawUiLineIcon(display, x, y, icon);
      x += uiLineIconAdvance(display, icon);
      p += consumed;
      continue;
    }
    if (richIgnorableUtf8Mark(p, &consumed)) {
      p += consumed;
      continue;
    }

    const char* start = p;
    uint8_t first = (uint8_t)*start;
    uint16_t cp = meshcoreReadUtf8Codepoint(p);
    size_t len = p - start;
    if (cp == '\r') continue;
    if (cp == '\n') break;
    if (!richSupportedCodepoint(cp)) {
      if (run_len + 4 >= sizeof(run) - 1) {
        flushRichRun(display, x, y, run, run_len);
      }
      richAppendFallbackByte(run, sizeof(run), run_len, first, len == 1);
      continue;
    }

    if (run_len + len >= sizeof(run) - 1) {
      flushRichRun(display, x, y, run, run_len);
    }
    if (run_len + len < sizeof(run)) {
      memcpy(&run[run_len], start, len);
      run_len += len;
    }
  }

  flushRichRun(display, x, y, run, run_len);
}

static void copyRichTextWithoutIcons(char* out, size_t out_len, const char* text) {
  if (out_len == 0) return;
  size_t used = 0;
  const char* p = text;
  while (p && *p && used + 1 < out_len) {
    size_t consumed = 0;
    if (richEmojiIconAt(p, &consumed) || richIgnorableUtf8Mark(p, &consumed)) {
      p += consumed;
      continue;
    }

    const char* start = p;
    uint16_t cp = meshcoreReadUtf8Codepoint(p);
    size_t len = p - start;
    if (cp == '\r' || cp == '\n') break;
    if (!richSupportedCodepoint(cp)) continue;
    if (used + len >= out_len) break;
    memcpy(&out[used], start, len);
    used += len;
  }
  out[used] = 0;
}

#if UI_UNREAD_USE_MONO_5X7
static bool unreadIsAsciiWord(uint16_t cp) {
  return (cp >= '0' && cp <= '9') || (cp >= 'A' && cp <= 'Z') || (cp >= 'a' && cp <= 'z');
}

static bool unreadIsCyrillic(uint16_t cp) {
  return (cp >= 0x0400 && cp <= 0x04FF);
}

static const uint8_t* unreadMonoGlyph(uint16_t cp) {
  const uint8_t* glyph = meshcoreAsciiGlyph5x7(cp);
  if (glyph) return glyph;
  glyph = meshcoreCyrillicGlyph5x7(cp);
  if (glyph) return glyph;
  return meshcoreAsciiGlyph5x7('?');
}

static void drawUnreadMonoGlyph(DisplayDriver& display, int x, int y, const uint8_t* glyph, bool bold) {
  if (glyph == NULL) return;
  for (int col = 0; col < 5; col++) {
    uint8_t bits = glyph[col];
    for (int row = 0; row < 8; row++) {
      if (bits & (1 << row)) {
        display.fillRect(x + col, y + row, 1, 1);
        if (bold) {
          display.fillRect(x + col + 1, y + row, 1, 1);
        }
      }
    }
  }
}
#endif

static void drawUnreadTextLine(DisplayDriver& display, int x, int y, const char* text, bool bold = false) {
#if UI_UNREAD_USE_MONO_5X7
  const char* p = text;
  uint16_t prev_cp = 0;

  while (p && *p) {
    size_t consumed = 0;
    const uint8_t* icon = richEmojiIconAt(p, &consumed);
    if (icon) {
      drawUiLineIcon(display, x, y, icon);
      x += uiLineIconAdvance(display, icon);
      p += consumed;
      prev_cp = 0;
      continue;
    }
    if (richIgnorableUtf8Mark(p, &consumed)) {
      p += consumed;
      continue;
    }

    const char* start = p;
    uint8_t first = (uint8_t)*start;
    uint16_t cp = meshcoreReadUtf8Codepoint(p);
    size_t len = p - start;
    if (cp == '\r') continue;
    if (cp == '\n') break;
    if (!richSupportedCodepoint(cp) && len == 1) {
      uint16_t cp1251;
      if (meshcoreCp1251Codepoint(first, &cp1251)) {
        cp = cp1251;
      }
    }

    if (unreadIsAsciiWord(prev_cp) && unreadIsCyrillic(cp)) {
      x += 2;
    }
    drawUnreadMonoGlyph(display, x, y, unreadMonoGlyph(cp), bold);
    x += 6 + (bold ? 1 : 0);
    prev_cp = cp;
  }
#else
  drawRichTextLine(display, x, y, text);
#endif
}

static bool nextWrappedRichLine(DisplayDriver& display, const char*& src, char* out, size_t out_len, int max_width);

static int unreadTextWidth(DisplayDriver& display, const char* text, bool bold = false) {
#if UI_UNREAD_USE_MONO_5X7
  int width = 0;
  int max_width = 0;
  const char* p = text;
  uint16_t prev_cp = 0;

  while (p && *p) {
    size_t consumed = 0;
    const uint8_t* icon = richEmojiIconAt(p, &consumed);
    if (icon) {
      width += uiLineIconAdvance(display, icon);
      p += consumed;
      prev_cp = 0;
      continue;
    }
    if (richIgnorableUtf8Mark(p, &consumed)) {
      p += consumed;
      continue;
    }

    const char* start = p;
    uint8_t first = (uint8_t)*start;
    uint16_t cp = meshcoreReadUtf8Codepoint(p);
    size_t len = p - start;
    if (cp == '\n') {
      if (width > max_width) max_width = width;
      width = 0;
      prev_cp = 0;
      continue;
    }
    if (cp == '\r') continue;
    if (!richSupportedCodepoint(cp) && len == 1) {
      uint16_t cp1251;
      if (meshcoreCp1251Codepoint(first, &cp1251)) {
        cp = cp1251;
      }
    }
    if (unreadIsAsciiWord(prev_cp) && unreadIsCyrillic(cp)) {
      width += 2;
    }
    width += 6 + (bold ? 1 : 0);
    prev_cp = cp;
  }
  return width > max_width ? width : max_width;
#else
  return richTextWidth(display, text);
#endif
}

static bool nextWrappedUnreadLine(DisplayDriver& display, const char*& src, char* out, size_t out_len, int max_width) {
#if UI_UNREAD_USE_MONO_5X7
  while (*src == ' ') src++;
  if (*src == 0 || out_len == 0) return false;

  size_t used = 0;
  size_t last_space_out = 0;
  const char* last_space_src = NULL;
  const char* p = src;

  while (*p && used < out_len - 1) {
    size_t consumed = 0;
    if (richEmojiIconAt(p, &consumed) == NULL && !richIgnorableUtf8Mark(p, &consumed)) {
      consumed = richUtf8Len(p);
    }
    if (consumed == 0 || used + consumed >= out_len) break;

    if (*p == '\r') {
      p += consumed;
      continue;
    }
    if (*p == '\n') {
      p += consumed;
      break;
    }

    memcpy(&out[used], p, consumed);
    used += consumed;
    out[used] = 0;

    if (*p == ' ') {
      last_space_out = used - consumed;
      last_space_src = p + consumed;
    }

    if (unreadTextWidth(display, out) > max_width) {
      if (last_space_src && last_space_out > 0) {
        used = last_space_out;
        out[used] = 0;
        p = last_space_src;
      } else if (used > consumed) {
        used -= consumed;
        out[used] = 0;
      } else {
        p += consumed;
      }
      break;
    }

    p += consumed;
  }

  src = p;
  while (*src == ' ') src++;
  out[used] = 0;
  return used > 0;
#else
  return nextWrappedRichLine(display, src, out, out_len, max_width);
#endif
}

static void drawOriginNameRich(DisplayDriver& display, int x, int y, const char* origin) {
  if (origin == NULL) return;

  const char* name = origin;
  const char* prefix_end = strstr(origin, ") ");
  if (origin[0] == '(' && prefix_end != NULL) {
    name = prefix_end + 2;
  }

  if (name > origin) {
    char prefix[16];
    size_t prefix_len = name - origin;
    if (prefix_len >= sizeof(prefix)) prefix_len = sizeof(prefix) - 1;
    memcpy(prefix, origin, prefix_len);
    prefix[prefix_len] = 0;
    display.setBold(false);
    display.setCursor(x, y);
    display.print(prefix);
    x += display.getTextWidth(prefix);
  }

  display.setBold(true);
  drawRichTextLine(display, x, y, name);
  display.setBold(false);
}

static void drawUnreadOriginNameRich(DisplayDriver& display, int x, int y, const char* origin) {
  if (origin == NULL) return;

  const char* name = origin;
  const char* prefix_end = strstr(origin, ") ");
  if (origin[0] == '(' && prefix_end != NULL) {
    name = prefix_end + 2;
  }

  if (name > origin) {
    char prefix[16];
    size_t prefix_len = name - origin;
    if (prefix_len >= sizeof(prefix)) prefix_len = sizeof(prefix) - 1;
    memcpy(prefix, origin, prefix_len);
    prefix[prefix_len] = 0;
    display.setBold(false);
    drawUnreadTextLine(display, x, y, prefix);
    x += unreadTextWidth(display, prefix);
  }

  display.setBold(true);
  drawUnreadTextLine(display, x, y, name, true);
  display.setBold(false);
}

static bool nextWrappedRichLine(DisplayDriver& display, const char*& src, char* out, size_t out_len, int max_width) {
  while (*src == ' ') src++;
  if (*src == 0 || out_len == 0) return false;

  size_t used = 0;
  size_t last_space_out = 0;
  const char* last_space_src = NULL;
  const char* p = src;

  while (*p && used < out_len - 1) {
    size_t consumed = 0;
    if (richEmojiIconAt(p, &consumed) == NULL && !richIgnorableUtf8Mark(p, &consumed)) {
      consumed = richUtf8Len(p);
    }
    if (consumed == 0 || used + consumed >= out_len) break;

    if (*p == '\r') {
      p += consumed;
      continue;
    }
    if (*p == '\n') {
      p += consumed;
      break;
    }

    memcpy(&out[used], p, consumed);
    used += consumed;
    out[used] = 0;

    if (*p == ' ') {
      last_space_out = used - consumed;
      last_space_src = p + consumed;
    }

    if (richTextWidth(display, out) > max_width) {
      if (last_space_src && last_space_out > 0) {
        used = last_space_out;
        out[used] = 0;
        p = last_space_src;
      } else if (used > consumed) {
        used -= consumed;
        out[used] = 0;
      } else {
        p += consumed;
      }
      break;
    }

    p += consumed;
  }

  src = p;
  while (*src == ' ') src++;
  out[used] = 0;
  return used > 0;
}

static int uiRichLineHeight(DisplayDriver& display) {
#if UI_RICH_DYNAMIC_LINE_HEIGHT
  int line_h = display.getTextLineHeight();
  return line_h < 9 ? 9 : line_h;
#else
  (void)display;
  return 9;
#endif
}

static void drawRichTextWrapped(DisplayDriver& display, int x, int y, int max_width, const char* text) {
  char line[190];
  const char* p = text ? text : "";
  const int line_h = uiRichLineHeight(display);
  while (nextWrappedRichLine(display, p, line, sizeof(line), max_width)) {
    if (y > display.height() - line_h) break;
    drawRichTextLine(display, x, y, line);
    y += line_h;
  }
}

static int richTextWrappedLineCount(DisplayDriver& display, int max_width, const char* text) {
  char line[190];
  const char* p = text ? text : "";
  int count = 0;
  while (nextWrappedRichLine(display, p, line, sizeof(line), max_width)) {
    count++;
  }
  return count;
}

static void drawRichTextWrappedRange(DisplayDriver& display, int x, int y, int max_width, const char* text,
                                     int first_line, int max_lines) {
  if (max_lines <= 0) return;

  char line[190];
  const char* p = text ? text : "";
  const int line_h = uiRichLineHeight(display);
  int line_index = 0;
  int drawn = 0;

  while (nextWrappedRichLine(display, p, line, sizeof(line), max_width)) {
    if (line_index++ < first_line) continue;
    drawRichTextLine(display, x, y + drawn * line_h, line);
    if (++drawn >= max_lines) break;
  }
}

static size_t richMarqueeTokenLen(const char* src, bool* visible) {
  if (visible) *visible = false;
  if (src == NULL || src[0] == 0) return 0;

  size_t consumed = 0;
  if (richEmojiIconAt(src, &consumed)) {
    if (visible) *visible = true;
    return consumed;
  }
  if (richIgnorableUtf8Mark(src, &consumed)) return consumed;

  if (src[0] == '\r' || src[0] == '\n') return 1;
  consumed = richUtf8Len(src);
  if (consumed == 0) return 0;
  if (visible) *visible = true;
  return consumed;
}

static uint16_t richVisibleTokenCount(const char* text) {
  uint16_t count = 0;
  const char* p = text ? text : "";
  while (*p) {
    if (*p == '\r' || *p == '\n') break;
    bool visible = false;
    size_t consumed = richMarqueeTokenLen(p, &visible);
    if (consumed == 0) break;
    if (visible) count++;
    p += consumed;
  }
  return count;
}

static const char* richSkipVisibleTokens(const char* text, uint16_t skip) {
  const char* p = text ? text : "";
  while (*p && skip > 0) {
    if (*p == '\r' || *p == '\n') break;
    bool visible = false;
    size_t consumed = richMarqueeTokenLen(p, &visible);
    if (consumed == 0) break;
    if (visible) skip--;
    p += consumed;
  }
  while (*p == ' ') p++;
  return p;
}

static bool copyRichMarqueeWindow(DisplayDriver& display, const char* src, char* out, size_t out_len,
                                  int max_width, uint16_t* fit_tokens = NULL) {
  if (out_len == 0) return false;
  out[0] = 0;
  if (fit_tokens) *fit_tokens = 0;
  if (src == NULL || max_width <= 0) return false;

  size_t used = 0;
  uint16_t visible_count = 0;
  const char* p = src;
  while (*p && used < out_len - 1) {
    if (*p == '\r' || *p == '\n') break;
    bool visible = false;
    size_t consumed = richMarqueeTokenLen(p, &visible);
    if (consumed == 0) break;
    if (!visible) {
      p += consumed;
      continue;
    }
    if (used + consumed >= out_len) break;

    memcpy(&out[used], p, consumed);
    used += consumed;
    out[used] = 0;
    if (richTextWidth(display, out) > max_width) {
      if (used > consumed) {
        used -= consumed;
        out[used] = 0;
      }
      break;
    }

    visible_count++;
    p += consumed;
  }

  if (fit_tokens) *fit_tokens = visible_count;
  return used > 0;
}

static uint16_t uiMarqueeOffset(uint16_t total_tokens, uint16_t fit_tokens) {
  if (fit_tokens == 0 || total_tokens <= fit_tokens) return 0;
  uint16_t max_offset = total_tokens - fit_tokens;
  uint16_t pause = UI_TEXT_MARQUEE_EDGE_PAUSE_STEPS;
  uint32_t period = (uint32_t)pause + max_offset + pause;
  if (period == 0) return 0;

  uint32_t phase = (millis() / UI_TEXT_MARQUEE_STEP_MS) % period;
  if (phase < pause) return 0;
  phase -= pause;
  if (phase < max_offset) return (uint16_t)(phase + 1);
  return max_offset;
}

static void drawRichTextEllipsized(DisplayDriver& display, int x, int y, int max_width, const char* text) {
  if (text == NULL) return;
  if (max_width <= 0) return;

  if (richTextWidth(display, text) <= max_width) {
    drawRichTextLine(display, x, y, text);
    return;
  }

#if UI_TEXT_MARQUEE_ENABLE
  char line[160];
  uint16_t total_tokens = richVisibleTokenCount(text);
  uint16_t fit_tokens = 0;
  copyRichMarqueeWindow(display, text, line, sizeof(line), max_width, &fit_tokens);
  if (fit_tokens == 0) fit_tokens = 1;
  uint16_t offset = uiMarqueeOffset(total_tokens, fit_tokens);
  const char* start = richSkipVisibleTokens(text, offset);
  if (!copyRichMarqueeWindow(display, start, line, sizeof(line), max_width, NULL)) line[0] = 0;
  drawRichTextLine(display, x, y, line);
#else
  const char* ellipsis = "...";
  int ellipsis_width = display.getTextWidth(ellipsis);
  int line_width = max_width - ellipsis_width;
  if (line_width < 1) line_width = max_width;

  char line[160];
  const char* p = text;
  if (!nextWrappedRichLine(display, p, line, sizeof(line), line_width)) {
    line[0] = 0;
  }
  if (line_width != max_width) {
    size_t len = strlen(line);
    if (len < sizeof(line) - 4) {
      memcpy(&line[len], ellipsis, 4);
    }
  }
  drawRichTextLine(display, x, y, line);
#endif
}

// Menus must remain visually stable.  The general helper above deliberately
// scrolls long chat/status text, but several moving rows at once make a picker
// hard to scan.  Use a fixed UTF-8-safe prefix with an ellipsis in lists.
static void drawRichTextStaticEllipsized(DisplayDriver& display, int x, int y,
                                         int max_width, const char* text) {
  if (text == NULL || max_width <= 0) return;
  if (richTextWidth(display, text) <= max_width) {
    drawRichTextLine(display, x, y, text);
    return;
  }

  const char* ellipsis = "...";
  const int ellipsis_width = display.getTextWidth(ellipsis);
  int line_width = max_width - ellipsis_width;
  const bool can_append = line_width > 0;
  if (!can_append) line_width = max_width;

  char line[160];
  const char* p = text;
  if (!nextWrappedRichLine(display, p, line, sizeof(line), line_width)) line[0] = 0;
  if (can_append) {
    size_t len = strlen(line);
    if (len < sizeof(line) - 4) memcpy(&line[len], ellipsis, 4);
  }
  drawRichTextLine(display, x, y, line);
}

// Editor fields must keep the caret and the newest characters visible.  The
// regular rich-text helper intentionally scrolls/ellipsizes from the start,
// which is correct for labels but makes a long typed message look frozen.
static int drawRichTextTailEllipsized(DisplayDriver& display, int x, int y, int max_width,
                                      const char* text, bool show_caret = true) {
  if (text == NULL || max_width <= 0) return x;

  const int caret_gap = show_caret ? 3 : 0;
  int text_width = richTextWidth(display, text);
  const char* visible = text;
  bool clipped = false;
  const char* ellipsis = "...";
  int ellipsis_width = display.getTextWidth(ellipsis);
  int available = max_width - caret_gap;

  if (text_width > available) {
    clipped = true;
    int suffix_width = available - ellipsis_width;
    if (suffix_width < 1) suffix_width = available;
    while (*visible && richTextWidth(display, visible) > suffix_width) {
      const uint8_t lead = (uint8_t)*visible;
      int advance = 1;
      if ((lead & 0xE0) == 0xC0) advance = 2;
      else if ((lead & 0xF0) == 0xE0) advance = 3;
      else if ((lead & 0xF8) == 0xF0) advance = 4;
      for (int i = 1; i < advance && visible[i] != 0; i++) {
        if ((((uint8_t)visible[i]) & 0xC0) != 0x80) {
          advance = i;
          break;
        }
      }
      visible += advance;
    }
  }

  int cursor_x = x;
  if (clipped && available > ellipsis_width) {
    drawRichTextLine(display, cursor_x, y, ellipsis);
    cursor_x += ellipsis_width;
  }
  drawRichTextLine(display, cursor_x, y, visible);
  cursor_x += richTextWidth(display, visible);
  if (show_caret) {
    int caret_h = display.getTextLineHeight() - 2;
    if (caret_h < 5) caret_h = 5;
    if (cursor_x > x + max_width - 2) cursor_x = x + max_width - 2;
    display.fillRect(cursor_x + 1, y + 1, 1, caret_h);
  }
  return cursor_x;
}

static void drawRichTextCentered(DisplayDriver& display, int mid_x, int y, const char* text) {
  int w = richTextWidth(display, text);
  drawRichTextLine(display, mid_x - w / 2, y, text);
}

static void drawRichTextCenteredEllipsized(DisplayDriver& display, int mid_x, int y, int max_width, const char* text) {
  if (text == NULL) return;
  if (max_width <= 0) return;

  int w = richTextWidth(display, text);
  if (w <= max_width) {
    drawRichTextLine(display, mid_x - w / 2, y, text);
    return;
  }

  drawRichTextEllipsized(display, mid_x - max_width / 2, y, max_width, text);
}

static const uint8_t UI_OLED_FONT_M = 0;
static const uint8_t UI_OLED_FONT_S = 1;
static const uint8_t UI_OLED_FONT_L = 2;

#if UI_V4_3_OLED_PROFILE || UI_T096_PREMIUM_TFT
static const uint8_t UI_OLED_STYLE_COUNT = 5;
#if UI_T096_PREMIUM_TFT
static const uint8_t UI_T096_FONT_FAMILY_COUNT = 5;
static const uint8_t UI_T096_FONT_SIZE_GROUP_COUNT = 4;
static const uint8_t UI_T096_FONT_PROFILE_COUNT = UI_T096_FONT_FAMILY_COUNT * UI_T096_FONT_SIZE_GROUP_COUNT;
static const uint8_t UI_T096_FONT_VISIBLE_FIRST = UI_T096_FONT_FAMILY_COUNT;
static const uint8_t UI_T096_FONT_VISIBLE_COUNT = UI_T096_FONT_PROFILE_COUNT - UI_T096_FONT_VISIBLE_FIRST;
static const uint8_t UI_T096_FONT_DEFAULT = UI_T096_FONT_FAMILY_COUNT * 2;
#endif

static uint8_t uiT096NormalizeFontProfile(uint8_t profile) {
#if UI_T096_PREMIUM_TFT
  if (profile < UI_T096_FONT_VISIBLE_FIRST) profile += UI_T096_FONT_VISIBLE_FIRST;
  if (profile >= UI_T096_FONT_PROFILE_COUNT) profile = UI_T096_FONT_DEFAULT;
#endif
  return profile;
}

static uint8_t uiOledStyleFromFont(uint8_t font_id) {
#if UI_T096_PREMIUM_TFT
  font_id = uiT096NormalizeFontProfile(font_id);
  return font_id % UI_T096_FONT_FAMILY_COUNT;
#else
  if (font_id < 5) return font_id;
  if (font_id < 10) return font_id - 5;
  if (font_id < 15) return font_id - 10;
  return 0;
#endif
}

static uint8_t uiOledFontForRole(uint8_t style_id, uint8_t role) {
#if UI_T096_PREMIUM_TFT
  uint8_t profile = uiT096NormalizeFontProfile(style_id);
  uint8_t family = profile % UI_T096_FONT_FAMILY_COUNT;
  uint8_t group = profile / UI_T096_FONT_FAMILY_COUNT;
  uint8_t role_group = group;
  if (role == UI_OLED_FONT_S) {
    role_group = group > 1 ? group - 1 : 1;
  } else if (role == UI_OLED_FONT_L) {
    role_group = group + 1;
  }
  if (role_group >= UI_T096_FONT_SIZE_GROUP_COUNT) role_group = UI_T096_FONT_SIZE_GROUP_COUNT - 1;
  if (role_group == 0) role_group = 1;
  return role_group * UI_T096_FONT_FAMILY_COUNT + family;
#else
  if (style_id >= UI_OLED_STYLE_COUNT) style_id = uiOledStyleFromFont(style_id);
  (void)role;
  return style_id;
#endif
}

static uint8_t uiOledTextSizeForRole(uint8_t role) {
#if UI_T096_PREMIUM_TFT
  (void)role;
  return 1;
#else
  return role == UI_OLED_FONT_L ? 2 : 1;
#endif
}

static const char* uiOledStyleName(uint8_t style_id) {
  switch (uiOledStyleFromFont(style_id)) {
    case 0: return "Classic";
    case 1: return "Air";
    case 2: return "Strong";
    case 3: return "Narrow";
    case 4: return "Dense";
    default: return "Classic";
  }
}
#endif

static uint8_t uiPushOledRoleFont(DisplayDriver& display, uint8_t role) {
  uint8_t saved_font = display.getUiFont();
#if UI_T096_PREMIUM_TFT
  display.setUiFont(uiOledFontForRole(saved_font, role));
  display.setTextSize(uiOledTextSizeForRole(role));
#elif UI_V4_3_OLED_PROFILE
  uint8_t style = uiOledStyleFromFont(saved_font);
  display.setUiFont(uiOledFontForRole(style, role));
  display.setTextSize(uiOledTextSizeForRole(role));
#else
  (void)role;
  display.setTextSize(1);
#endif
  display.setBold(false);
  return saved_font;
}

static uint8_t uiPushCompactChromeFont(DisplayDriver& display) {
  return uiPushOledRoleFont(display, UI_OLED_FONT_S);
}

static uint8_t uiPushCompactSettingsFont(DisplayDriver& display) {
#if UI_T096_PREMIUM_TFT
  uint8_t saved_font = display.getUiFont();
  display.setUiFont(uiOledStyleFromFont(saved_font));
  display.setTextSize(1);
  display.setBold(false);
  return saved_font;
#elif UI_NATIVE_TFT_PROFILE
  // T114 offers large body fonts whose real logical line height is 12/13 px.
  // Dense lists and the 4-row keyboard need a stable L profile, otherwise the
  // last row is clipped after the driver's 128x64 -> 240x135 scaling.
  uint8_t saved_font = display.getUiFont();
  display.setUiFont(0);
  display.setTextSize(1);
  display.setBold(false);
  return saved_font;
#else
  return uiPushCompactChromeFont(display);
#endif
}

static void uiPopFont(DisplayDriver& display, uint8_t saved_font) {
  if (display.getUiFont() != saved_font && saved_font < display.getUiFontCount()) display.setUiFont(saved_font);
  display.setTextSize(1);
  display.setBold(false);
}

static void drawOledCompactMenuPage(DisplayDriver& display, const char* title,
                                    const char* line1, const char* line2, const char* line3) {
  uint8_t saved_font = uiPushCompactChromeFont(display);
  int line_h = display.getTextLineHeight();
  if (line_h < 12) line_h = 12;
  if (display.height() <= 64 && line_h > 12) line_h = 12;
  if (display.height() > 64 && line_h > 18) line_h = 18;

  int y = display.height() > 64 ? 14 : 16;
  int bottom_y = display.height() - line_h - 2;
  if (bottom_y < y + line_h * 3) bottom_y = display.height() - line_h - 1;
  display.setColor(DisplayDriver::GREEN);
  drawRichTextCentered(display, display.width() / 2, y, title);

  display.setColor(DisplayDriver::LIGHT);
  if (line1 != NULL && line1[0] != 0) drawRichTextEllipsized(display, 0, y + line_h, display.width(), line1);
  if (line2 != NULL && line2[0] != 0) drawRichTextEllipsized(display, 0, y + line_h * 2, display.width(), line2);
  if (line3 != NULL && line3[0] != 0) drawRichTextEllipsized(display, 0, bottom_y, display.width(), line3);
  uiPopFont(display, saved_font);
}

static void drawOledStyleSelectPage(DisplayDriver& display, const char* style_name, const char* count_line) {
  uint8_t small_font = uiPushCompactChromeFont(display);
  display.setColor(DisplayDriver::GREEN);
  drawRichTextCentered(display, display.width() / 2, 14, "Шрифт");
  uiPopFont(display, small_font);

  uint8_t body_font = uiPushOledRoleFont(display, UI_OLED_FONT_M);
  display.setColor(DisplayDriver::YELLOW);
  drawRichTextCentered(display, display.width() / 2, 29, style_name);
  uiPopFont(display, body_font);

  small_font = uiPushCompactChromeFont(display);
  display.setColor(DisplayDriver::LIGHT);
  drawRichTextCentered(display, display.width() / 2, 44, count_line);
  drawRichTextCentered(display, display.width() / 2, 52, "смена: " PRESS_LABEL);
  uiPopFont(display, small_font);
}

static const uint8_t ui_preview_ascii_5x7[][5] = {
  {0x00,0x00,0x00,0x00,0x00}, {0x00,0x00,0x5F,0x00,0x00},
  {0x00,0x07,0x00,0x07,0x00}, {0x14,0x7F,0x14,0x7F,0x14},
  {0x24,0x2A,0x7F,0x2A,0x12}, {0x23,0x13,0x08,0x64,0x62},
  {0x36,0x49,0x55,0x22,0x50}, {0x00,0x05,0x03,0x00,0x00},
  {0x00,0x1C,0x22,0x41,0x00}, {0x00,0x41,0x22,0x1C,0x00},
  {0x14,0x08,0x3E,0x08,0x14}, {0x08,0x08,0x3E,0x08,0x08},
  {0x00,0x50,0x30,0x00,0x00}, {0x08,0x08,0x08,0x08,0x08},
  {0x00,0x60,0x60,0x00,0x00}, {0x20,0x10,0x08,0x04,0x02},
  {0x3E,0x51,0x49,0x45,0x3E}, {0x00,0x42,0x7F,0x40,0x00},
  {0x42,0x61,0x51,0x49,0x46}, {0x21,0x41,0x45,0x4B,0x31},
  {0x18,0x14,0x12,0x7F,0x10}, {0x27,0x45,0x45,0x45,0x39},
  {0x3C,0x4A,0x49,0x49,0x30}, {0x01,0x71,0x09,0x05,0x03},
  {0x36,0x49,0x49,0x49,0x36}, {0x06,0x49,0x49,0x29,0x1E},
  {0x00,0x36,0x36,0x00,0x00}, {0x00,0x56,0x36,0x00,0x00},
  {0x08,0x14,0x22,0x41,0x00}, {0x14,0x14,0x14,0x14,0x14},
  {0x00,0x41,0x22,0x14,0x08}, {0x02,0x01,0x51,0x09,0x06},
  {0x32,0x49,0x79,0x41,0x3E}, {0x7E,0x11,0x11,0x11,0x7E},
  {0x7F,0x49,0x49,0x49,0x36}, {0x3E,0x41,0x41,0x41,0x22},
  {0x7F,0x41,0x41,0x22,0x1C}, {0x7F,0x49,0x49,0x49,0x41},
  {0x7F,0x09,0x09,0x09,0x01}, {0x3E,0x41,0x49,0x49,0x7A},
  {0x7F,0x08,0x08,0x08,0x7F}, {0x00,0x41,0x7F,0x41,0x00},
  {0x20,0x40,0x41,0x3F,0x01}, {0x7F,0x08,0x14,0x22,0x41},
  {0x7F,0x40,0x40,0x40,0x40}, {0x7F,0x02,0x0C,0x02,0x7F},
  {0x7F,0x04,0x08,0x10,0x7F}, {0x3E,0x41,0x41,0x41,0x3E},
  {0x7F,0x09,0x09,0x09,0x06}, {0x3E,0x41,0x51,0x21,0x5E},
  {0x7F,0x09,0x19,0x29,0x46}, {0x46,0x49,0x49,0x49,0x31},
  {0x01,0x01,0x7F,0x01,0x01}, {0x3F,0x40,0x40,0x40,0x3F},
  {0x1F,0x20,0x40,0x20,0x1F}, {0x3F,0x40,0x38,0x40,0x3F},
  {0x63,0x14,0x08,0x14,0x63}, {0x07,0x08,0x70,0x08,0x07},
  {0x61,0x51,0x49,0x45,0x43}, {0x00,0x7F,0x41,0x41,0x00},
  {0x02,0x04,0x08,0x10,0x20}, {0x00,0x41,0x41,0x7F,0x00},
  {0x04,0x02,0x01,0x02,0x04}, {0x40,0x40,0x40,0x40,0x40},
  {0x00,0x01,0x02,0x04,0x00}, {0x20,0x54,0x54,0x54,0x78},
  {0x7F,0x48,0x44,0x44,0x38}, {0x38,0x44,0x44,0x44,0x20},
  {0x38,0x44,0x44,0x48,0x7F}, {0x38,0x54,0x54,0x54,0x18},
  {0x08,0x7E,0x09,0x01,0x02}, {0x0C,0x52,0x52,0x52,0x3E},
  {0x7F,0x08,0x04,0x04,0x78}, {0x00,0x44,0x7D,0x40,0x00},
  {0x20,0x40,0x44,0x3D,0x00}, {0x7F,0x10,0x28,0x44,0x00},
  {0x00,0x41,0x7F,0x40,0x00}, {0x7C,0x04,0x18,0x04,0x78},
  {0x7C,0x08,0x04,0x04,0x78}, {0x38,0x44,0x44,0x44,0x38},
  {0x7C,0x14,0x14,0x14,0x08}, {0x08,0x14,0x14,0x18,0x7C},
  {0x7C,0x08,0x04,0x04,0x08}, {0x48,0x54,0x54,0x54,0x20},
  {0x04,0x3F,0x44,0x40,0x20}, {0x3C,0x40,0x40,0x20,0x7C},
  {0x1C,0x20,0x40,0x20,0x1C}, {0x3C,0x40,0x30,0x40,0x3C},
  {0x44,0x28,0x10,0x28,0x44}, {0x0C,0x50,0x50,0x50,0x3C},
  {0x44,0x64,0x54,0x4C,0x44}, {0x00,0x08,0x36,0x41,0x00},
  {0x00,0x00,0x7F,0x00,0x00}, {0x00,0x41,0x36,0x08,0x00},
  {0x10,0x08,0x08,0x10,0x08}
};

static const uint8_t* previewGlyph5x7(uint16_t cp) {
  if (cp >= 32 && cp <= 126) return ui_preview_ascii_5x7[cp - 32];
  return meshcoreCyrillicGlyph5x7(cp);
}

static int previewEmojiAdvance() {
#if UI_T096_PREMIUM_TFT
  return 18;
#else
  return 9;
#endif
}

static int previewTokenWidth(const char* src) {
  size_t consumed = 0;
  if (richEmojiIconAt(src, &consumed)) return previewEmojiAdvance();
  if (richIgnorableUtf8Mark(src, &consumed)) return 0;

  const char* p = src;
  uint8_t first = (uint8_t)*src;
  uint16_t cp = meshcoreReadUtf8Codepoint(p);
  if (cp == '\r' || cp == '\n') return 0;
  if (!previewGlyph5x7(cp) && p - src == 1) {
    uint16_t cp1251;
    if (meshcoreCp1251Codepoint(first, &cp1251)) cp = cp1251;
  }
  return previewGlyph5x7(cp) ? 6 : 6;
}

static int previewTextWidth(const char* text) {
  int width = 0;
  int max_width = 0;
  const char* p = text ? text : "";
  while (*p) {
    size_t consumed = 0;
    if (richEmojiIconAt(p, &consumed)) {
      width += previewEmojiAdvance();
      p += consumed;
      continue;
    }
    if (richIgnorableUtf8Mark(p, &consumed)) {
      p += consumed;
      continue;
    }

    const char* start = p;
    uint16_t cp = meshcoreReadUtf8Codepoint(p);
    if (cp == '\n') {
      if (width > max_width) max_width = width;
      width = 0;
      continue;
    }
    if (cp == '\r') continue;
    width += previewTokenWidth(start);
  }
  return width > max_width ? width : max_width;
}

static void drawPreviewGlyph(DisplayDriver& display, int x, int y, const uint8_t* glyph) {
  if (glyph == NULL) return;
  for (int col = 0; col < 5; col++) {
    uint8_t bits = glyph[col];
    for (int row = 0; row < 7; row++) {
      if (bits & (1 << row)) display.fillRect(x + col, y + row, 1, 1);
    }
  }
}

static void drawPreviewTextLine(DisplayDriver& display, int x, int y, const char* text) {
  const char* p = text ? text : "";
  while (*p) {
    size_t consumed = 0;
    const uint8_t* icon = richEmojiIconAt(p, &consumed);
    if (icon) {
      drawUiLineIcon(display, x, y, icon);
      x += uiLineIconAdvance(display, icon);
      p += consumed;
      continue;
    }
    if (richIgnorableUtf8Mark(p, &consumed)) {
      p += consumed;
      continue;
    }

    const char* start = p;
    uint8_t first = (uint8_t)*start;
    uint16_t cp = meshcoreReadUtf8Codepoint(p);
    if (cp == '\r') continue;
    if (cp == '\n') break;
    if (!previewGlyph5x7(cp) && p - start == 1) {
      uint16_t cp1251;
      if (meshcoreCp1251Codepoint(first, &cp1251)) cp = cp1251;
    }
    const uint8_t* glyph = previewGlyph5x7(cp);
    drawPreviewGlyph(display, x, y, glyph ? glyph : previewGlyph5x7('*'));
    x += 6;
  }
}

static bool nextPreviewWrappedLine(const char*& src, char* out, size_t out_len, int max_width) {
  while (*src == ' ') src++;
  if (*src == 0 || out_len == 0) return false;

  size_t used = 0;
  size_t last_space_out = 0;
  const char* last_space_src = NULL;
  const char* p = src;

  while (*p && used < out_len - 1) {
    size_t consumed = 0;
    if (richEmojiIconAt(p, &consumed) == NULL && !richIgnorableUtf8Mark(p, &consumed)) {
      consumed = richUtf8Len(p);
    }
    if (consumed == 0 || used + consumed >= out_len) break;

    if (*p == '\r') {
      p += consumed;
      continue;
    }
    if (*p == '\n') {
      p += consumed;
      break;
    }

    memcpy(&out[used], p, consumed);
    used += consumed;
    out[used] = 0;

    if (*p == ' ') {
      last_space_out = used - consumed;
      last_space_src = p + consumed;
    }

    if (previewTextWidth(out) > max_width) {
      if (last_space_src && last_space_out > 0) {
        used = last_space_out;
        out[used] = 0;
        p = last_space_src;
      } else if (used > consumed) {
        used -= consumed;
        out[used] = 0;
      } else {
        p += consumed;
      }
      break;
    }

    p += consumed;
  }

  src = p;
  while (*src == ' ') src++;
  out[used] = 0;
  return used > 0;
}

static int previewWrappedLineCount(int max_width, const char* text) {
  char line[190];
  const char* p = text ? text : "";
  int count = 0;
  while (nextPreviewWrappedLine(p, line, sizeof(line), max_width)) count++;
  return count;
}

static void drawPreviewWrappedRange(DisplayDriver& display, int x, int y, int max_width, const char* text,
                                    int first_line, int max_lines, int line_h) {
  if (max_lines <= 0) return;

  char line[190];
  const char* p = text ? text : "";
  int line_index = 0;
  int drawn = 0;
  while (nextPreviewWrappedLine(p, line, sizeof(line), max_width)) {
    if (line_index++ < first_line) continue;
    drawPreviewTextLine(display, x, y + drawn * line_h, line);
    if (++drawn >= max_lines) break;
  }
}

static bool copyPreviewMarqueeWindow(const char* src, char* out, size_t out_len, int max_width,
                                     uint16_t* fit_tokens = NULL) {
  if (out_len == 0) return false;
  out[0] = 0;
  if (fit_tokens) *fit_tokens = 0;
  if (src == NULL || max_width <= 0) return false;

  size_t used = 0;
  uint16_t visible_count = 0;
  const char* p = src;
  while (*p && used < out_len - 1) {
    if (*p == '\r' || *p == '\n') break;
    bool visible = false;
    size_t consumed = richMarqueeTokenLen(p, &visible);
    if (consumed == 0) break;
    if (!visible) {
      p += consumed;
      continue;
    }
    if (used + consumed >= out_len) break;

    memcpy(&out[used], p, consumed);
    used += consumed;
    out[used] = 0;
    if (previewTextWidth(out) > max_width) {
      if (used > consumed) {
        used -= consumed;
        out[used] = 0;
      }
      break;
    }

    visible_count++;
    p += consumed;
  }

  if (fit_tokens) *fit_tokens = visible_count;
  return used > 0;
}

static void drawPreviewTextEllipsized(DisplayDriver& display, int x, int y, int max_width, const char* text) {
  if (text == NULL || max_width <= 0) return;
  if (previewTextWidth(text) <= max_width) {
    drawPreviewTextLine(display, x, y, text);
    return;
  }

#if UI_TEXT_MARQUEE_ENABLE
  char line[160];
  uint16_t total_tokens = richVisibleTokenCount(text);
  uint16_t fit_tokens = 0;
  copyPreviewMarqueeWindow(text, line, sizeof(line), max_width, &fit_tokens);
  if (fit_tokens == 0) fit_tokens = 1;
  uint16_t offset = uiMarqueeOffset(total_tokens, fit_tokens);
  const char* start = richSkipVisibleTokens(text, offset);
  if (!copyPreviewMarqueeWindow(start, line, sizeof(line), max_width, NULL)) line[0] = 0;
  drawPreviewTextLine(display, x, y, line);
#else
  char line[160];
  const char* p = text;
  int line_width = max_width - previewTextWidth("...");
  if (line_width < 1) line_width = max_width;
  if (!nextPreviewWrappedLine(p, line, sizeof(line), line_width)) line[0] = 0;
  size_t len = strlen(line);
  if (len < sizeof(line) - 4 && line_width != max_width) {
    memcpy(&line[len], "...", 4);
  }
  drawPreviewTextLine(display, x, y, line);
#endif
}

static uint32_t uiApplyTimezoneOffset(uint32_t now, int32_t offset_seconds) {
  int64_t adjusted = (int64_t)now + offset_seconds;
  if (adjusted <= 0) return 0;
  if (adjusted >= UINT32_MAX) return UINT32_MAX;
  return (uint32_t)adjusted;
}

static bool drawClockUptimeBetween(DisplayDriver& display, const UITask* task,
                                   int left_used, int right_used, int y) {
  char text[12];
  smartui::formatClockUptime(text, sizeof(text), task->getUptimeSeconds());
  int text_width = display.getTextWidth(text);
  int right = smartui::clockUptimeRightEdge((int16_t)left_used,
                                             (int16_t)right_used,
                                             (int16_t)text_width);
  if (right < 0 && text[0] == 'U' && text[1] == ' ') {
    memmove(&text[1], &text[2], strlen(&text[2]) + 1);
    text_width = display.getTextWidth(text);
    right = smartui::clockUptimeRightEdge((int16_t)left_used,
                                           (int16_t)right_used,
                                           (int16_t)text_width,
                                           2);
  }
  if (right < 0) return false;
  display.drawTextRightAlign(right, y, text);
  return true;
}

#if UI_BLE_PIN_PAGE
static int renderBlePinPage(DisplayDriver& display, uint32_t ble_pin, bool connected) {
  char pin_text[12];
  if (ble_pin != 0) {
    snprintf(pin_text, sizeof(pin_text), "%06lu", (unsigned long)ble_pin);
  } else {
    strcpy(pin_text, "------");
  }

#if UI_WIRELESS_PAPER_BIG_CLOCK
  if (display.width() > 200 && display.height() > 80) {
    display.setColor(DisplayDriver::LIGHT);
    display.setBold(true);
    display.setTextSize(2);
    drawRichTextCentered(display, display.width() / 2, 20, "ПИНКОД BLE");

    display.setTextSize(4);
    drawRichTextCentered(display, display.width() / 2, 42, pin_text);

    display.setBold(false);
    display.setTextSize(1);
    drawRichTextCentered(display, display.width() / 2, 82,
                         connected ? "BLE ПОДКЛЮЧЕН" : "ОТКРОЙТЕ MESHCORE");
    if (!connected) {
      drawRichTextCentered(display, display.width() / 2, 96, "УСТРОЙСТВА > ДОБАВИТЬ");
      drawRichTextCentered(display, display.width() / 2, 110, "PIN / PASSKEY: ЭТИ 6 ЦИФР");
    }
    return UI_EINK_SAVER_REFRESH_MILLIS;
  }
#endif

  display.setColor(DisplayDriver::YELLOW);
#if UI_NATIVE_TFT_PROFILE
  // T114 exposes very large user-selectable fonts.  Keep the instruction
  // lines on the fixed dense-list font and reserve enough physical rows for
  // the 128x64 -> 240x135 scaling used by its display driver.
  const int title_y = 18;
  const int pin_y = 31;
  const int hint_y = 51;
  uint8_t title_font = uiPushCompactSettingsFont(display);
#else
  const int title_y = 21;
  const int pin_y = 38;
#if UI_T096_PREMIUM_TFT
  const int hint_y = 57;
#else
  // SSD1306 uses an 8-row cell; y=57 would clip its last row on 64 px.
  const int hint_y = 55;
#endif
  uint8_t title_font = uiPushOledRoleFont(display, UI_OLED_FONT_S);
#endif
  drawRichTextCentered(display, display.width() / 2, title_y, "ПИНКОД BLE");
  uiPopFont(display, title_font);

  display.setColor(DisplayDriver::GREEN);
  uint8_t hero_font = uiPushOledRoleFont(display, UI_OLED_FONT_L);
  drawRichTextCentered(display, display.width() / 2, pin_y, pin_text);
  uiPopFont(display, hero_font);

  display.setColor(DisplayDriver::LIGHT);
#if UI_NATIVE_TFT_PROFILE
  uint8_t small_font = uiPushCompactSettingsFont(display);
#else
  uint8_t small_font = uiPushCompactChromeFont(display);
#endif
  drawRichTextCentered(display, display.width() / 2, hint_y,
                       connected ? "BLE подключен" : "код в приложении");
  uiPopFont(display, small_font);
  return UI_IDLE_REFRESH_MILLIS;
}
#endif

#if UI_EINK_IDLE_SCREENSAVER || UI_WIRELESS_PAPER_BIG_CLOCK
static void drawUiPixel(DisplayDriver& display, int x, int y) {
  if (x < 0 || y < 0 || x >= display.width() || y >= display.height()) return;
  display.fillRect(x, y, 1, 1);
}

static void drawUiLine(DisplayDriver& display, int x0, int y0, int x1, int y1) {
  int dx = abs(x1 - x0);
  int sx = x0 < x1 ? 1 : -1;
  int dy = -abs(y1 - y0);
  int sy = y0 < y1 ? 1 : -1;
  int err = dx + dy;
  while (true) {
    drawUiPixel(display, x0, y0);
    if (x0 == x1 && y0 == y1) break;
    int e2 = 2 * err;
    if (e2 >= dy) {
      err += dy;
      x0 += sx;
    }
    if (e2 <= dx) {
      err += dx;
      y0 += sy;
    }
  }
}

static void drawUiPine(DisplayDriver& display, int x, int base_y, int h) {
  if (h < 8) h = 8;
  int top_y = base_y - h;
  drawUiLine(display, x, top_y, x, base_y);
  for (int y = top_y + 3; y < base_y; y += 4) {
    int span = (y - top_y) / 2 + 2;
    if (span > h / 3) span = h / 3;
    drawUiLine(display, x, y, x - span, y + 3);
    drawUiLine(display, x, y, x + span, y + 3);
  }
  display.fillRect(x - 1, base_y - 2, 3, 2);
}

static void drawUiMountainTexture(DisplayDriver& display, int x0, int y0, int x1, int y1, int seed) {
  for (int x = x0; x <= x1; x += 7) {
    int y = y0 + ((x + seed) % 11);
    drawUiLine(display, x, y, x + 10, y - 5);
  }
  for (int x = x0 + 4; x <= x1; x += 13) {
    int y = y1 - ((x + seed) % 9);
    drawUiLine(display, x, y, x + 8, y + 3);
  }
}

static void drawPaperForestBackdrop(DisplayDriver& display, uint8_t seed) {
  int w = display.width();
  int h = display.height();

  // A horizontal wood-case motif: ridge line, radio tower, and pine rhythm.
  int ridge_y = h - 22;
  int right_ridge = w - 70;
  drawUiLine(display, 0, ridge_y - 5, 26, ridge_y - 18);
  drawUiLine(display, 26, ridge_y - 18, 56, ridge_y - 6);
  drawUiLine(display, right_ridge, ridge_y - 7, right_ridge + 30, ridge_y - 25);
  drawUiLine(display, right_ridge + 30, ridge_y - 25, w - 1, ridge_y - 8);
  drawUiMountainTexture(display, 4, ridge_y - 30, 56, ridge_y - 5, seed);
  drawUiMountainTexture(display, right_ridge, ridge_y - 30, w - 10, ridge_y - 5, seed);

  int tower_x = 22 + (seed % 3);
  int tower_top = ridge_y - 40;
  drawUiLine(display, tower_x, tower_top, tower_x - 7, ridge_y - 14);
  drawUiLine(display, tower_x, tower_top, tower_x + 7, ridge_y - 14);
  drawUiLine(display, tower_x - 7, ridge_y - 14, tower_x + 7, ridge_y - 14);
  drawUiLine(display, tower_x, tower_top, tower_x, ridge_y - 8);
  display.drawRect(tower_x - 2, tower_top + 7, 5, 5);
  drawUiLine(display, tower_x - 12, tower_top + 4, tower_x - 4, tower_top + 8);
  drawUiLine(display, tower_x + 4, tower_top + 8, tower_x + 12, tower_top + 4);

  for (int x = 5; x < w; x += 18) {
    if (x > 58 && x < w - 58) continue;
    int ph = 17 + ((x + seed) % 11);
    drawUiPine(display, x, h - 2, ph);
  }
  for (int x = w - 68; x < w; x += 13) {
    int ph = 23 + ((x + seed * 3) % 15);
    drawUiPine(display, x, ridge_y + 10, ph);
  }

  // Top horizon, like the horizontal crop of the reference artwork.
  drawUiLine(display, 0, 18, 36, 14);
  drawUiLine(display, 36, 14, 70, 24);
  drawUiLine(display, 70, 24, 103, 11);
  drawUiLine(display, 103, 11, 143, 25);
  drawUiLine(display, 143, 25, 188, 14);
  drawUiLine(display, 188, 14, w - 1, 23);
  for (int x = w - 112; x < w; x += 15) {
    drawUiPine(display, x, 30, 20 + ((x + seed) % 8));
  }
}

static int paperBatteryLeftEdge(DisplayDriver& display, uint16_t milli_volts) {
  char tmp[12];
  snprintf(tmp, sizeof(tmp), "%u.%02uV", milli_volts / 1000, (milli_volts % 1000) / 10);
  display.setTextSize(1);
  return (display.width() - 26) - display.getTextWidth(tmp);
}

static void drawPaperBatteryIndicator(DisplayDriver& display, uint16_t milli_volts) {
  char tmp[12];
  snprintf(tmp, sizeof(tmp), "%u.%02uV", milli_volts / 1000, (milli_volts % 1000) / 10);
  display.setTextSize(1);
  display.drawTextRightAlign(display.width() - 26, 4, tmp);

  int x = display.width() - 24;
  int y = 3;
  display.drawRect(x, y, 21, 10);
  display.fillRect(x + 21, y + 3, 2, 4);
  int bars = 0;
  if (milli_volts >= 4100) bars = 5;
  else if (milli_volts >= 3950) bars = 4;
  else if (milli_volts >= 3800) bars = 3;
  else if (milli_volts >= 3650) bars = 2;
  else if (milli_volts >= 3450) bars = 1;
  for (int i = 0; i < bars; i++) {
    display.fillRect(x + 2 + i * 3, y + 2, 2, 6);
  }
}

static int renderPaperIdleClock(DisplayDriver& display, UITask* task, mesh::RTCClock* rtc, bool with_backdrop) {
  uint32_t rtc_now = rtc->getCurrentTime();
  bool time_valid = task->hasTrustedTime() && rtc_now >= UI_RTC_VALID_MIN;
  DateTime dt(time_valid ? task->getLocalClockTime(rtc_now) : 0);
  display.setTextSize(1);
  char uptime_text[12];
  smartui::formatClockUptime(uptime_text, sizeof(uptime_text), task->getUptimeSeconds());
  const uint16_t battery_mv = task->getBattMilliVolts();
  const int battery_left = paperBatteryLeftEdge(display, battery_mv);
  const int uptime_right = battery_left - 3;
  const int uptime_width = display.getTextWidth(uptime_text);
  const int uptime_left = uptime_right - uptime_width;

  if (with_backdrop) {
    // Keep the decorative pixels stable.  Only the clock/date/status should
    // change between minute refreshes on an e-paper panel.
    drawPaperForestBackdrop(display, 17);
    // The original Wood artwork crossed the clock, date and battery glyphs.
    // Reserve two clean paper-white islands while keeping the forest frame.
    if (display.width() >= 240 && display.height() >= 120) {
      display.setColor(DisplayDriver::DARK);
      display.fillRect(45, 34, 161, 64);
      display.fillRect(display.width() - 60, 0, 60, 15);
      display.fillRect(uptime_left - 2, 0, uptime_width + 4, 15);
    }
  }

  char tmp[32];
  display.setColor(DisplayDriver::LIGHT);
  display.setBold(false);
  display.setTextSize(1);
  int node_width = uptime_left - 8;
  if (node_width < 24) node_width = 24;
  drawRichTextEllipsized(display, 4, 4, node_width, task->getNodeName());
  display.drawTextRightAlign(uptime_right, 4, uptime_text);
  drawPaperBatteryIndicator(display, battery_mv);

  display.setBold(true);
  display.setTextSize(4);
  if (time_valid) {
    snprintf(tmp, sizeof(tmp), "%02u:%02u", dt.hour(), dt.minute());
  } else {
    strcpy(tmp, "--:--");
  }
  display.drawTextCentered(display.width() / 2, 39, tmp);

  display.setBold(false);
  display.setTextSize(2);
  if (time_valid) {
    snprintf(tmp, sizeof(tmp), "%02u.%02u.%04u", dt.day(), dt.month(), dt.year());
  } else {
    strcpy(tmp, "нет времени");
  }
  display.drawTextCentered(display.width() / 2, 78, tmp);

  display.setTextSize(1);
  snprintf(tmp, sizeof(tmp), "Непроч: %d", task->getMsgCount());
  display.drawTextCentered(display.width() / 2, 101, tmp);

  if (time_valid) {
    uint8_t sec = dt.second();
    unsigned long next_minute = (60UL - sec) * 1000UL;
    if (next_minute < 1000UL || next_minute > UI_EINK_SAVER_REFRESH_MILLIS) {
      next_minute = UI_EINK_SAVER_REFRESH_MILLIS;
    }
    return (int)next_minute;
  }
  return UI_EINK_SAVER_REFRESH_MILLIS;
}
#endif

class SplashScreen : public UIScreen {
  UITask* _task;
  unsigned long dismiss_after;
  char _version_info[12];

public:
  SplashScreen(UITask* task) : _task(task) {
    // strip off dash and commit hash by changing dash to null terminator
    // e.g: v1.2.3-abcdef -> v1.2.3
    const char *ver = FIRMWARE_VERSION;
    const char *dash = strchr(ver, '-');

    int len = dash ? dash - ver : strlen(ver);
    if (len >= sizeof(_version_info)) len = sizeof(_version_info) - 1;
    memcpy(_version_info, ver, len);
    _version_info[len] = 0;

    dismiss_after = millis() + BOOT_SCREEN_MILLIS;
  }

  int render(DisplayDriver& display) override {
#if UI_T096_PREMIUM_TFT
    uint8_t saved_font = display.getUiFont();
    display.setTextSize(1);
    display.setBold(false);

    display.setColor(DisplayDriver::GREEN);
    uint8_t hero_font = uiPushOledRoleFont(display, UI_OLED_FONT_L);
    display.setBold(true);
    drawRichTextCenteredEllipsized(display, display.width() / 2, 18, display.width() - 2, "Мешкор Омск");
    display.setBold(false);
    uiPopFont(display, hero_font);

    display.setColor(DisplayDriver::GREEN);
    uint8_t small_font = uiPushOledRoleFont(display, UI_OLED_FONT_S);
    drawRichTextCenteredEllipsized(display, display.width() / 2, 48, display.width() - 2, "UI " MESHCORE_UI_VERSION);
    uiPopFont(display, small_font);

    uiPopFont(display, saved_font);
#elif UI_V4_3_OLED_PROFILE
    uint8_t saved_font = display.getUiFont();
    display.setTextSize(1);
    display.setBold(false);

    display.setColor(DisplayDriver::BLUE);
    display.setTextSize(uiOledTextSizeForRole(UI_OLED_FONT_L));
    display.setUiFont(uiOledFontForRole(0, UI_OLED_FONT_L));
    drawRichTextCentered(display, display.width() / 2, 5, "Мешкор");
    drawRichTextCentered(display, display.width() / 2, 24, "Омск");

    display.setColor(DisplayDriver::LIGHT);
    display.setTextSize(uiOledTextSizeForRole(UI_OLED_FONT_S));
    display.setUiFont(uiOledFontForRole(0, UI_OLED_FONT_S));
    drawRichTextCenteredEllipsized(display, display.width() / 2, 42, display.width(), "UI " MESHCORE_UI_VERSION);
    drawRichTextCenteredEllipsized(display, display.width() / 2, 52, display.width(), _version_info);

    uiPopFont(display, saved_font);
#else
    display.setColor(DisplayDriver::BLUE);
    display.setTextSize(2);
    display.drawTextCentered(display.width()/2, 5, "Мешкор");
    display.drawTextCentered(display.width()/2, 24, "Омск");

    display.setColor(DisplayDriver::LIGHT);
    display.setTextSize(1);
    display.drawTextCentered(display.width()/2, 43, "UI " MESHCORE_UI_VERSION);
    display.drawTextCentered(display.width()/2, 55, _version_info);
#endif

    return 1000;
  }

  void poll() override {
    if (smartui::deadlineReached((uint32_t)millis(), (uint32_t)dismiss_after)) {
      _task->gotoHomeScreen();
    }
  }
};

#if UI_EINK_IDLE_SCREENSAVER
class PaperIdleClockScreen : public UIScreen {
  UITask* _task;
  mesh::RTCClock* _rtc;

public:
  PaperIdleClockScreen(UITask* task, mesh::RTCClock* rtc) : _task(task), _rtc(rtc) {}

  bool keepDisplayOn() const override {
    return true;
  }

  int render(DisplayDriver& display) override {
    return renderPaperIdleClock(display, _task, _rtc, true);
  }
};
#endif

class HomeScreen : public UIScreen {
  enum HomePage {
    CLOCK,
#if UI_BLE_PIN_PAGE
    BLE_PIN,
#endif
    RECENT,
    NETWORK,
    CHAT,
    ADVERT,
    RADIO,
#if UI_CLIENT_REPEAT_PAGE == 1
    CLIENT_REPEAT,
#endif
    LINK_TEST,
    BLUETOOTH,
    MSG_POPUP,
    IMPORTANT_NOTIFY,
#if UI_OFFLINE_DM_LED_PAGE == 1 && defined(PIN_MSG_ALERT)
    OFFLINE_DM_LED,
    BLE_DM_LED,
#endif
#if UI_BOARD_LEDS_PAGE == 1
    BOARD_LEDS,
#endif
#if UI_APPEARANCE_MENU
#if UI_UNREAD_LED_PAGE == 1
    UNREAD_LED,
#endif
    UI_THEME,
    UI_FONT,
#if UI_COMPACT_SETTINGS_MENU == 1
    THEME_PICKER,
    FONT_PICKER,
#endif
#if UI_COLOR_APPEARANCE_MENU
    UI_TOP_COLOR,
    UI_BOTTOM_COLOR,
#endif
#if UI_BACKLIGHT_TIMEOUT_PAGE == 1
    BACKLIGHT_TIMEOUT,
#endif
#endif
    ALERTS,
#ifdef PIN_MSG_ALERT
    ALERT_LED,
#endif
#ifdef PIN_MSG_TONE
    ALERT_TONE_PIN,
#if UI_TONE_BRIDGE_PAGE == 1
    ALERT_TONE_BRIDGE,
#endif
#endif
    ALERT_VIBE_PIN,
#ifdef PIN_MSG_TONE
    ALERT_SOUND,
#if UI_SMART_B12_TONE_LIST == 1
    TONE_PICKER,
#endif
#if UI_SMART_B11_EXTRAS == 1
    ALERT_SOUND_DM,
    ALERT_SOUND_MENTION,
#endif
#if UI_TONE_8BIT_PAGE == 1
    ALERT_TONE_STYLE,
#endif
    ALERT_VOLUME,
#if UI_TONE_RESONANCE_PAGE == 1
    ALERT_TONE_RESONANCE,
#endif
#endif
#if UI_AUTO_ADVERT_PAGE == 1
    ADVERT_TIMER,
#endif
#if UI_CH2_RELAY_PAGE == 1
    CH2_RELAY,
#endif
#if ENV_INCLUDE_GPS == 1 || UI_PHONE_GPS == 1
    GPS,
#endif
#if UI_SENSORS_PAGE == 1
    SENSORS,
#endif
#if UI_ADC_MULTIPLIER_PAGE == 1
    ADC,
#endif
#if UI_TIMEZONE_PAGE == 1
    TIMEZONE,
#endif
#if UI_LOW_BATTERY_SHUTDOWN_PAGE == 1 && defined(AUTO_SHUTDOWN_MILLIVOLTS)
    LOW_BATT_SHUTDOWN,
#endif
#if UI_SMART_B11_EXTRAS == 1
    SMART_PROFILE,
    FAVORITE_SLOT_1,
    FAVORITE_SLOT_2,
    FAVORITE_SLOT_3,
    UNDO_SETTING,
    DEVICE_STATUS,
    HARDWARE_TEST,
    SETTINGS_TRANSFER,
#endif
    FIRST,
    SETTINGS,
#if UI_COMPACT_SETTINGS_MENU == 1
    NOTIFY_PICKER,
#if UI_TIMEZONE_PAGE == 1
    TIMEZONE_PICKER,
#endif
#endif
    SHUTDOWN,
    Count    // keep as last
  };

  UITask* _task;
  mesh::RTCClock* _rtc;
  SensorManager* _sensors;
  NodePrefs* _node_prefs;
  uint8_t _page;
  bool _settings_open;
  bool _quick_reply_open;
  uint8_t _quick_reply_idx;
#if UI_QUICK_REPLY_KEYBOARD
  bool _quick_keyboard_open;
  uint8_t _quick_keyboard_page;
  uint8_t _quick_keyboard_cursor;
  uint8_t _quick_target_mode;
  uint16_t _quick_target_cursor;
  uint8_t _quick_last_target_mode = QR_TARGET_CLOSED;
  uint16_t _quick_last_target_cursor = 0;
  bool _quick_target_identity_valid;
  uint8_t _quick_target_identity_mode;
  uint16_t _quick_target_identity_cursor;
  uint8_t _quick_target_channel_id;
  uint8_t _quick_target_contact_pubkey[PUB_KEY_SIZE];
  char _quick_target_identity_label[32];
  char _quick_keyboard_text[UI_QUICK_REPLY_KEYBOARD_TEXT_MAX];
#endif
#if UI_COMPACT_SETTINGS_MENU == 1
  uint8_t _compact_settings_depth;
  uint8_t _compact_settings_group;
  uint8_t _compact_settings_cursor;
  smartui::ConfirmedChoice _notify_picker;
  uint8_t _notify_picker_page = SETTINGS;
#if UI_TIMEZONE_PAGE == 1
  uint8_t _timezone_picker_cursor;
#endif
#if UI_APPEARANCE_MENU
  uint8_t _font_picker_cursor;
  uint8_t _theme_picker_cursor;
#endif
#if UI_SMART_B12_TONE_LIST == 1 && defined(PIN_MSG_TONE)
  uint8_t _tone_picker_cursor;
#endif
#if UI_SMART_B11_EXTRAS == 1
  NodePrefs _compact_undo_prefs;
  bool _compact_undo_valid;
  uint8_t _hardware_test_step;
#endif
#endif
  int _chat_scroll_px;
  int _chat_scroll_dir;
  unsigned long _chat_pause_until;
  uint32_t _chat_latest_ts;
  uint32_t _chat_layout_ts;
  int _chat_layout_width;
  int _chat_layout_total_h;
  uint8_t _chat_layout_count;
  uint8_t _chat_layout_font;
  bool _chat_layout_valid;
  bool _shutdown_init;
#if UI_ADC_MULTIPLIER_PAGE == 1
  bool _adc_edit;
  float _adc_draft;
#endif
  AdvertPath recent[UI_RECENT_LIST_SIZE];
  NetworkStatusEntry network_status[UI_RECENT_LIST_SIZE];
  RecentChatEntry chat[UI_CHAT_LIST_SIZE];
  int _chat_item_h[UI_CHAT_LIST_SIZE];

  int roundSnrQ4(int8_t snr_q4) const {
    return snr_q4 >= 0 ? (snr_q4 + 2) / 4 : (snr_q4 - 2) / 4;
  }

  bool looksLikeIdName(const char* name) const {
    if (!name || !*name) return true;
    size_t len = strlen(name);
    if (name[0] == '!' || len < 6 || len > 12) return name[0] == '!';
    for (size_t i = 0; i < len; i++) {
      char c = name[i];
      if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F'))) {
        return false;
      }
    }
    return true;
  }

  void formatSignalMetrics(char* out, size_t out_len, const NetworkStatusEntry* n) const {
    snprintf(out, out_len, "S%+d R%d", roundSnrQ4(n->snr_q4), n->rssi);
  }

  void formatNetworkRoleLabel(char* out, size_t out_len, const NetworkStatusEntry* n) const {
    if (out_len == 0) return;
    bool is_relay = n && (n->flags & (NETWORK_STATUS_REPEATER | NETWORK_STATUS_CLIENT_REPEAT_UNKNOWN));
    bool is_direct = n && (n->flags & NETWORK_STATUS_DIRECT) && !(n->flags & NETWORK_STATUS_VIA_RELAY);
    snprintf(out, out_len, "%s%s", is_relay ? "Р" : "Н", is_direct ? "Д" : "");
  }

  ColorVal signalMetricsColor(const NetworkStatusEntry* n) const {
    if (n == NULL || (n->snr_q4 == 0 && n->rssi == 0)) return DisplayDriver::LIGHT;
    int snr = roundSnrQ4(n->snr_q4);
    if (snr >= 0 || n->rssi >= -105) return DisplayDriver::GREEN;
    if (snr >= -8 || n->rssi >= -118) return DisplayDriver::YELLOW;
    return DisplayDriver::RED;
  }

  uint32_t localClockTime(uint32_t now) const {
    return _task->getLocalClockTime(now);
  }

  void formatPercentTenths(char* out, size_t out_len, uint32_t pct10) const {
    if (pct10 > 999) pct10 = 999;
    snprintf(out, out_len, "%lu.%lu%%", (unsigned long)(pct10 / 10), (unsigned long)(pct10 % 10));
  }

  void formatPercentHundredths(char* out, size_t out_len, uint32_t pct100) const {
    if (pct100 > 9999) pct100 = 9999;
    if (pct100 < 1000) {
      snprintf(out, out_len, "%lu.%02lu%%", (unsigned long)(pct100 / 100), (unsigned long)(pct100 % 100));
      return;
    }

    uint32_t rounded10 = (pct100 + 5) / 10;
    if (rounded10 > 999) rounded10 = 999;
    snprintf(out, out_len, "%lu.%lu%%", (unsigned long)(rounded10 / 10), (unsigned long)(rounded10 % 10));
  }

  int routeIconsWidth(DisplayDriver& display, const NetworkStatusEntry* n) const {
    bool via_relay = (n->flags & NETWORK_STATUS_VIA_RELAY) != 0;
    bool has_relay_role = (n->flags & (NETWORK_STATUS_REPEATER | NETWORK_STATUS_CLIENT_REPEAT_UNKNOWN)) != 0;
    int icon_size = uiRouteIconSize(display);
    return (!via_relay && has_relay_role) ? (icon_size * 2 + uiRouteIconGap(display)) : icon_size;
  }

  int drawRouteIcons(DisplayDriver& display, int x, int y, const NetworkStatusEntry* n) {
    bool via_relay = (n->flags & NETWORK_STATUS_VIA_RELAY) != 0;
    bool has_relay_role = (n->flags & (NETWORK_STATUS_REPEATER | NETWORK_STATUS_CLIENT_REPEAT_UNKNOWN)) != 0;
    int used = 0;
    int icon_size = uiRouteIconSize(display);
    int icon_y = uiRouteIconY(display, y);

    if (via_relay) {
      display.setColor(DisplayDriver::YELLOW);
      drawUiIcon(display, x, icon_y, tower_route_icon, icon_size);
      return icon_size;
    }

    if (has_relay_role) {
      display.setColor(DisplayDriver::YELLOW);
      drawUiIcon(display, x, icon_y, tower_route_icon, icon_size);
      used += icon_size + uiRouteIconGap(display);
    }

    display.setColor(DisplayDriver::GREEN);
    drawUiIcon(display, x + used, icon_y, pager_route_icon, icon_size);
    return used + icon_size;
  }

  size_t nextUtf8Len(const char* s) const {
    uint8_t c = (uint8_t)s[0];
    if (c == 0) return 0;
    if (c < 0x80) return 1;
    if ((c & 0xE0) == 0xC0) return 2;
    if ((c & 0xF0) == 0xE0) return 3;
    if ((c & 0xF8) == 0xF0) return 4;
    return 1;
  }

  bool nextWrappedLine(DisplayDriver& display, const char*& src, char* out, size_t out_len, int max_width) {
    while (*src == ' ') src++;
    if (*src == 0) return false;

    size_t used = 0;
    size_t last_space_out = 0;
    const char* last_space_src = NULL;
    const char* p = src;

    while (*p && used < out_len - 1) {
      size_t clen = nextUtf8Len(p);
      if (clen == 0 || used + clen >= out_len) break;
      if (*p == '\r') {
        p += clen;
        continue;
      }
      if (*p == '\n') {
        p += clen;
        break;
      }

      memcpy(&out[used], p, clen);
      used += clen;
      out[used] = 0;

      if (*p == ' ') {
        last_space_out = used - clen;
        last_space_src = p + clen;
      }

      if (display.getTextWidth(out) > max_width) {
        if (last_space_src && last_space_out > 0) {
          used = last_space_out;
          out[used] = 0;
          p = last_space_src;
        } else if (used > clen) {
          used -= clen;
          out[used] = 0;
        } else {
          p += clen;
        }
        break;
      }
      p += clen;
    }

    src = p;
    while (*src == ' ') src++;
    out[used] = 0;
    return used > 0;
  }

  int measureChatEntryLines(DisplayDriver& display, int index) {
    char line[190];
#if UI_T096_PREMIUM_TFT
    const int text_x = 18;
#else
    const int text_x = UI_T114_APPEARANCE_MENU ? uiLineIconAdvance(display) : 10;
#endif
    const int text_w = display.width() - text_x;
#if UI_NATIVE_TFT_PROFILE && defined(HELTEC_T114)
    char combined[260];
    snprintf(combined, sizeof(combined), "%s %s", chat[index].origin, chat[index].text);
    int lines = 0;
    const char* p = combined;
    while (nextWrappedRichLine(display, p, line, sizeof(line), text_w)) {
      lines++;
#if UI_CHAT_RENDER_LINE_LIMIT > 0
      if (lines > UI_CHAT_RENDER_LINE_LIMIT) break;
#endif
    }
    return lines > 0 ? lines : 1;
#else
    int lines = 1;  // sender/source line
    const char* p = chat[index].text;
    while (nextWrappedRichLine(display, p, line, sizeof(line), text_w)) {
      lines++;
#if UI_CHAT_RENDER_LINE_LIMIT > 0
      if (lines > UI_CHAT_RENDER_LINE_LIMIT) break;
#endif
    }
    return lines;
#endif
  }

  int selectChatRenderCount(DisplayDriver& display, int count) {
#if UI_CHAT_RENDER_LINE_LIMIT > 0
    int used_lines = 0;
    int render_count = 0;
    for (int i = 0; i < count; i++) {
      int entry_lines = measureChatEntryLines(display, i);
      if (render_count > 0 && used_lines + entry_lines > UI_CHAT_RENDER_LINE_LIMIT) break;
      used_lines += entry_lines;
      render_count++;
      if (used_lines >= UI_CHAT_RENDER_LINE_LIMIT) break;
    }
    return render_count > 0 ? render_count : count;
#else
    (void)display;
    return count;
#endif
  }

  int renderChatFeed(DisplayDriver& display, int count, int y_start, int scroll_px, bool draw) {
    char line[190];
    int y = y_start - scroll_px;
    const int line_h = uiRichLineHeight(display);
    const int name_gap = UI_T114_APPEARANCE_MENU ? 4 : 1;
    const int msg_gap = UI_T114_APPEARANCE_MENU ? 3 : 2;
#if UI_T096_PREMIUM_TFT
    const int text_x = 18;
#else
    const int text_x = UI_T114_APPEARANCE_MENU ? uiLineIconAdvance(display) : 10;
#endif
    const int text_w = display.width() - text_x;
    int rendered_lines = 0;

    for (int i = count - 1; i >= 0; i--) {
#if UI_CHAT_RENDER_LINE_LIMIT > 0
      if (rendered_lines >= UI_CHAT_RENDER_LINE_LIMIT) break;
#endif
      int item_start = y;
      int cached_h = _chat_item_h[i];
      if (draw && cached_h > 0) {
        if (y + cached_h < 0) {
          y += cached_h;
          continue;
        }
        if (y > display.height() + line_h) break;
      }

      bool via_relay = (chat[i].flags & NETWORK_STATUS_VIA_RELAY) != 0;
#if UI_NATIVE_TFT_PROFILE && defined(HELTEC_T114)
      char combined[260];
      snprintf(combined, sizeof(combined), "%s %s", chat[i].origin, chat[i].text);
      const char* p = combined;
      bool first_line = true;
      while (nextWrappedRichLine(display, p, line, sizeof(line), text_w)) {
#if UI_CHAT_RENDER_LINE_LIMIT > 0
        if (rendered_lines >= UI_CHAT_RENDER_LINE_LIMIT) break;
#endif
        if (draw && y > -line_h && y < display.height()) {
          if (first_line) {
            display.setColor(via_relay ? DisplayDriver::YELLOW : DisplayDriver::GREEN);
            drawUiLineIcon(display, 0, y, via_relay ? relay_packet_icon : direct_packet_icon);
          }
          display.setColor(_task->getUiBottomColor());
          display.setBold(false);
          drawRichTextLine(display, text_x, y, line);
        }
        y += line_h;
        rendered_lines++;
        first_line = false;
      }
      y += msg_gap;
#else
      if (draw && y > -line_h && y < display.height()) {
        display.setColor(via_relay ? DisplayDriver::YELLOW : DisplayDriver::GREEN);
        drawUiLineIcon(display, 0, y, via_relay ? relay_packet_icon : direct_packet_icon);
          drawOriginNameRich(display, text_x, y, chat[i].origin);
      }
      y += line_h + name_gap;
      rendered_lines++;

      const char* p = chat[i].text;
      while (nextWrappedRichLine(display, p, line, sizeof(line), text_w)) {
#if UI_CHAT_RENDER_LINE_LIMIT > 0
        if (rendered_lines >= UI_CHAT_RENDER_LINE_LIMIT) break;
#endif
        if (draw && y > -line_h && y < display.height()) {
          display.setColor(_task->getUiBottomColor());
          display.setBold(false);
          drawRichTextLine(display, text_x, y, line);
        }
        y += line_h;
        rendered_lines++;
      }
      y += msg_gap;
#endif
      if (!draw) _chat_item_h[i] = y - item_start;
    }

    return y - y_start + scroll_px;
  }

  void formatChatAge(char* out, size_t out_len, const RecentChatEntry* entry) const {
    if (entry->recv_timestamp == 0) {
      snprintf(out, out_len, "--");
      return;
    }
    uint32_t now = _rtc->getCurrentTime();
    uint32_t age = entry->recv_timestamp > now ? 0 : now - entry->recv_timestamp;
    if (age < 60) {
      snprintf(out, out_len, "%lus", (unsigned long)age);
    } else if (age < 60UL * 60UL) {
      snprintf(out, out_len, "%lum", (unsigned long)(age / 60));
    } else if (age < 24UL * 60UL * 60UL) {
      snprintf(out, out_len, "%luh", (unsigned long)(age / (60UL * 60UL)));
    } else {
      snprintf(out, out_len, "%lud", (unsigned long)(age / (24UL * 60UL * 60UL)));
    }
  }

  void formatChatSignal(char* out, size_t out_len, const RecentChatEntry* entry) const {
    if (entry->snr_q4 == 0 && entry->rssi == 0) {
      out[0] = 0;
      return;
    }
    snprintf(out, out_len, "S%+d R%d", roundSnrQ4(entry->snr_q4), entry->rssi);
  }

  void renderChatList(DisplayDriver& display, int count) {
    if (count <= 0) return;
    count = selectChatRenderCount(display, count);
    if (count <= 0) return;
    uint32_t newest_ts = chat[0].recv_timestamp;
    uint32_t layout_sig = newest_ts ^ ((uint32_t)count << 24) ^ ((uint32_t)display.getUiFont() << 16);
    layout_sig ^= (uint8_t)chat[0].origin[0];
    layout_sig ^= ((uint32_t)(uint8_t)chat[0].text[0]) << 8;
    layout_sig ^= chat[count - 1].recv_timestamp;

    int total_h = _chat_layout_total_h;
    if (!_chat_layout_valid || _chat_layout_ts != layout_sig || _chat_layout_count != count ||
        _chat_layout_font != display.getUiFont() || _chat_layout_width != display.width()) {
      total_h = renderChatFeed(display, count, 0, 0, false);
      _chat_layout_total_h = total_h;
      _chat_layout_ts = layout_sig;
      _chat_layout_count = count;
      _chat_layout_font = display.getUiFont();
      _chat_layout_width = display.width();
      _chat_layout_valid = true;
    }
    int max_scroll = total_h > display.height() ? total_h - display.height() : 0;

    if (_chat_latest_ts != newest_ts) {
      _chat_latest_ts = newest_ts;
      _chat_scroll_px = max_scroll;
      _chat_scroll_dir = -1;
      _chat_pause_until = millis() + UI_CHAT_EDGE_PAUSE_MILLIS;
    }

    if (_chat_scroll_px > max_scroll) _chat_scroll_px = max_scroll;
    if (_chat_scroll_px < 0) _chat_scroll_px = 0;

    renderChatFeed(display, count, 0, _chat_scroll_px, true);

    if (max_scroll <= 0) return;
    unsigned long now = millis();
    if (smartui::deadlinePending((uint32_t)now, (uint32_t)_chat_pause_until)) return;

    _chat_scroll_px += _chat_scroll_dir * UI_CHAT_SCROLL_STEP_PX;
    if (_chat_scroll_px <= 0) {
      _chat_scroll_px = 0;
      _chat_scroll_dir = 1;
      _chat_pause_until = now + UI_CHAT_EDGE_PAUSE_MILLIS;
    } else if (_chat_scroll_px >= max_scroll) {
      _chat_scroll_px = max_scroll;
      _chat_scroll_dir = -1;
      _chat_pause_until = now + UI_CHAT_EDGE_PAUSE_MILLIS;
    }

  }

  int renderBatteryIndicator(DisplayDriver& display, uint16_t batteryMilliVolts, bool showMutedStatus = true) {
#if UI_T096_PREMIUM_TFT
    const int iconWidth = 22;
    const int iconHeight = 13;
    const int iconX = display.width() - iconWidth - 4;
    const int iconY = 1;
#else
    const int iconWidth = 18;
    const int iconHeight = 10;
    const int iconX = display.width() - iconWidth - 2;
    const int iconY = 2;
#endif
    ColorVal batteryColor = uiBatteryStatusColor(batteryMilliVolts);
    bool showMutedIcon = false;
#ifdef PIN_BUZZER
    showMutedIcon = showMutedStatus && _task->isBuzzerQuiet();
#endif
    int mutedIconReserve = 0;
#if UI_NATIVE_TFT_PROFILE && !UI_T096_PREMIUM_TFT
    if (showMutedIcon) mutedIconReserve = uiStatusIconSize(display) + 3;
#endif
    int leftmostX = iconX;

    if (batteryMilliVolts > 0) {
      char voltage[8];
      snprintf(voltage, sizeof(voltage), "%u.%02uV", batteryMilliVolts / 1000, (batteryMilliVolts % 1000) / 10);
      int voltageWidth = display.getTextWidth(voltage);
      int voltageX = iconX - mutedIconReserve - voltageWidth - 3;
      if (voltageX > 0) {
        if (voltageX < leftmostX) leftmostX = voltageX;
        display.setColor(batteryColor);
        display.setCursor(voltageX, 0);
        display.print(voltage);
      }
    }

    drawUiBatteryIcon(display, iconX, iconY, iconWidth, iconHeight, batteryMilliVolts);

    // show muted icon if buzzer is muted
#ifdef PIN_BUZZER
    if (showMutedIcon) {
      display.setColor(DisplayDriver::RED);
#if UI_T096_PREMIUM_TFT
      if (iconX - 18 < leftmostX) leftmostX = iconX - 18;
      drawUiIcon(display, iconX - 18, iconY, muted_icon, 16);
#elif UI_NATIVE_TFT_PROFILE
      int mutedSize = uiStatusIconSize(display);
      int mutedX = iconX - mutedSize - 3;
      int mutedY = iconY + (iconHeight - mutedSize) / 2;
      if (mutedY < 0) mutedY = 0;
      if (mutedX < leftmostX) leftmostX = mutedX;
      drawUiIcon(display, mutedX, mutedY, muted_icon, mutedSize);
#else
      if (iconX - 9 < leftmostX) leftmostX = iconX - 9;
      display.drawXbm(iconX - 9, iconY + 1, muted_icon, 8, 8);
#endif
    }
#endif
    return leftmostX;
  }

  CayenneLPP sensors_lpp;
  int sensors_nb = 0;
  bool sensors_scroll = false;
  int sensors_scroll_offset = 0;
  int next_sensors_refresh = 0;

#if UI_ADC_MULTIPLIER_PAGE == 1
  float getAdcStep(float value) const {
    if (value >= 1000.0f) return 25.0f;
    if (value >= 100.0f) return 1.0f;
    if (value >= 10.0f) return 0.05f;
    return UI_ADC_MULTIPLIER_FINE_STEP;
  }

  float clampAdcMultiplier(float value) const {
    if (value < UI_ADC_MULTIPLIER_MIN) return UI_ADC_MULTIPLIER_MIN;
    if (value > UI_ADC_MULTIPLIER_MAX) return UI_ADC_MULTIPLIER_MAX;
    return value;
  }

  void formatAdcMultiplier(char* out, size_t out_len, float value) const {
    if (value >= 100.0f) {
      snprintf(out, out_len, "%.0f", value);
    } else {
      snprintf(out, out_len, "%.3f", value);
    }
  }

  void adjustAdcMultiplier(float delta) {
    _adc_draft = clampAdcMultiplier(_adc_draft + delta);
    _task->setAdcMultiplier(_adc_draft, false);
  }

  void cancelAdcEdit() {
    if (_adc_edit) {
      if (!_task->setAdcMultiplier(_node_prefs->adc_multiplier, false)) {
        _task->setAdcMultiplier(0.0f, false);
      }
    }
    _adc_edit = false;
    _adc_draft = 0.0f;
  }
#endif

#if UI_COMPACT_SETTINGS_MENU == 1
  static const uint8_t COMPACT_SETTINGS_GROUP_COUNT =
#if UI_SMART_B11_EXTRAS == 1
    7
#else
    6
#endif
#if UI_SOUND_SETTINGS_GROUP == 0
    - 1
#endif
    ;

  const char* compactSettingsGroupName(uint8_t group) const {
#if UI_SMART_B11_EXTRAS == 1
    if (group == 0) return "Избранное";
    group--;
#endif
#if UI_SOUND_SETTINGS_GROUP == 0
    if (group >= 1) group++;
#endif
    switch (group) {
      case 0: return "Уведомления";
      case 1: return "Звук и вибро";
      case 2: return "Экран";
      case 3:
#if ENV_INCLUDE_GPS == 1 || UI_PHONE_GPS == 1
        return "Радио и GPS";
#else
        return "Радио";
#endif
      case 4: return "Система";
      case 5: return "Дополнительно";
      default: return "Настройки";
    }
  }

#if UI_SMART_B11_EXTRAS == 1
  uint8_t favoriteIdAt(uint8_t slot) const {
    if (_node_prefs == NULL) return SMART_FAVORITE_NOTIFY_MODE;
    if (slot == 0) return _node_prefs->favorite_setting_1;
    if (slot == 1) return _node_prefs->favorite_setting_2;
    return _node_prefs->favorite_setting_3;
  }

  uint8_t favoritePageFromId(uint8_t id) const {
    switch (id) {
#if UI_NOTIFICATION_SETTINGS == 1
      case SMART_FAVORITE_NOTIFY_MODE: return HomePage::ALERTS;
      case SMART_FAVORITE_IMPORTANT_NOTIFY: return HomePage::IMPORTANT_NOTIFY;
#endif
#ifdef PIN_MSG_TONE
#if UI_SMART_B12_TONE_LIST == 1
      case SMART_FAVORITE_SYSTEM_TONE:
      case SMART_FAVORITE_DM_TONE:
      case SMART_FAVORITE_MENTION_TONE:
        return HomePage::ALERT_SOUND;
#else
      case SMART_FAVORITE_SYSTEM_TONE: return HomePage::ALERT_SOUND;
      case SMART_FAVORITE_DM_TONE: return HomePage::ALERT_SOUND_DM;
      case SMART_FAVORITE_MENTION_TONE: return HomePage::ALERT_SOUND_MENTION;
#endif
#endif
#if UI_APPEARANCE_MENU
      case SMART_FAVORITE_UI_FONT: return HomePage::UI_FONT;
      case SMART_FAVORITE_UI_THEME: return HomePage::UI_THEME;
#endif
      case SMART_FAVORITE_BLUETOOTH: return HomePage::BLUETOOTH;
#if UI_AUTO_ADVERT_PAGE == 1
      case SMART_FAVORITE_AUTO_ADVERT: return HomePage::ADVERT_TIMER;
#endif
#if ENV_INCLUDE_GPS == 1 || UI_PHONE_GPS == 1
      case SMART_FAVORITE_GPS: return HomePage::GPS;
#endif
#if UI_BOARD_LEDS_PAGE == 1
      case SMART_FAVORITE_BOARD_LEDS: return HomePage::BOARD_LEDS;
#endif
#if UI_LOW_BATTERY_SHUTDOWN_PAGE == 1 && defined(AUTO_SHUTDOWN_MILLIVOLTS)
      case SMART_FAVORITE_LOW_BATTERY: return HomePage::LOW_BATT_SHUTDOWN;
#endif
#if UI_ADC_MULTIPLIER_PAGE == 1
      case SMART_FAVORITE_ADC: return HomePage::ADC;
#endif
#if UI_SMART_B12_TONE_LIST != 1
      case SMART_FAVORITE_PROFILE: return HomePage::SMART_PROFILE;
#endif
      default: return HomePage::SETTINGS;
    }
  }

  uint8_t defaultFavoritePageAt(uint8_t slot) const {
    static const uint8_t candidates[] = {
#if UI_NOTIFICATION_SETTINGS == 1
      HomePage::ALERTS,
#endif
#ifdef PIN_MSG_TONE
      HomePage::ALERT_SOUND,
#endif
#if UI_APPEARANCE_MENU
      HomePage::UI_FONT,
      HomePage::UI_THEME,
#endif
#if UI_AUTO_ADVERT_PAGE == 1
      HomePage::ADVERT_TIMER,
#endif
#if UI_ADC_MULTIPLIER_PAGE == 1
      HomePage::ADC,
#endif
      HomePage::BLUETOOTH,
      HomePage::RADIO,
      HomePage::MSG_POPUP,
    };
    uint8_t visible = 0;
    for (uint8_t i = 0; i < sizeof(candidates) / sizeof(candidates[0]); i++) {
      if (!isSettingsItem(candidates[i])) continue;
      if (visible == slot) return candidates[i];
      visible++;
    }
    return HomePage::SETTINGS;
  }

  uint8_t resolvedFavoritePageAt(uint8_t slot) const {
    uint8_t page = favoritePageFromId(favoriteIdAt(slot));
    if (page != HomePage::SETTINGS && isSettingsItem(page)) return page;
    return defaultFavoritePageAt(slot);
  }

  void setFavoriteId(uint8_t slot, uint8_t id) {
    if (_node_prefs == NULL) return;
    if (slot == 0) _node_prefs->favorite_setting_1 = id;
    else if (slot == 1) _node_prefs->favorite_setting_2 = id;
    else _node_prefs->favorite_setting_3 = id;
  }

  void cycleFavoriteSlot(uint8_t slot) {
    uint8_t next = favoriteIdAt(slot);
    for (uint8_t tries = 0; tries < SMART_FAVORITE_MAX; tries++) {
      next++;
      if (next > SMART_FAVORITE_MAX) next = 1;
#if UI_SMART_B12_TONE_LIST == 1
      if (next == SMART_FAVORITE_DM_TONE || next == SMART_FAVORITE_MENTION_TONE) continue;
      if (next == SMART_FAVORITE_PROFILE) continue;
#endif
      uint8_t page = favoritePageFromId(next);
      if (page != HomePage::SETTINGS && isSettingsItem(page)) {
        setFavoriteId(slot, next);
        the_mesh.savePrefs();
        char alert[64];
        snprintf(alert, sizeof(alert), "Избранное %u: %s", slot + 1, compactSettingsLabel(page));
        _task->showAlert(alert, 1000);
        return;
      }
    }
  }
#endif

  const uint8_t* compactSettingsRawPages(uint8_t group, uint8_t& count) const {
    static const uint8_t notification_pages[] = {
#if UI_NOTIFICATION_SETTINGS == 1
      HomePage::ALERTS,
      HomePage::IMPORTANT_NOTIFY,
#endif
      HomePage::MSG_POPUP,
#if UI_OFFLINE_DM_LED_PAGE == 1 && defined(PIN_MSG_ALERT)
      HomePage::OFFLINE_DM_LED,
      HomePage::BLE_DM_LED,
#endif
#if UI_APPEARANCE_MENU && UI_UNREAD_LED_PAGE == 1
      HomePage::UNREAD_LED,
#endif
    };
    static const uint8_t sound_pages[] = {
#ifdef PIN_MSG_TONE
#if UI_SMART_B11_EXTRAS == 1 && UI_SMART_B12_TONE_LIST != 1
      HomePage::ALERT_SOUND_DM,
      HomePage::ALERT_SOUND_MENTION,
#endif
      HomePage::ALERT_SOUND,
      HomePage::ALERT_VOLUME,
#endif
      HomePage::ALERT_VIBE_PIN,
    };
    static const uint8_t display_pages[] = {
#if UI_APPEARANCE_MENU
      HomePage::UI_FONT,
      HomePage::UI_THEME,
#if UI_COLOR_APPEARANCE_MENU
      HomePage::UI_TOP_COLOR,
      HomePage::UI_BOTTOM_COLOR,
#endif
#if UI_BACKLIGHT_TIMEOUT_PAGE == 1
      HomePage::BACKLIGHT_TIMEOUT,
#endif
#endif
    };
    static const uint8_t radio_pages[] = {
      HomePage::RADIO,
#if UI_AUTO_ADVERT_PAGE == 1
      HomePage::ADVERT_TIMER,
#endif
#if UI_CLIENT_REPEAT_PAGE == 1
      HomePage::CLIENT_REPEAT,
#endif
#if ENV_INCLUDE_GPS == 1 || UI_PHONE_GPS == 1
      HomePage::GPS,
#endif
#if UI_CH2_RELAY_PAGE == 1
      HomePage::CH2_RELAY,
#endif
#if UI_LINK_TEST_PAGE
      HomePage::LINK_TEST,
#endif
    };
    static const uint8_t system_pages[] = {
      HomePage::BLUETOOTH,
#if UI_TIMEZONE_PAGE == 1
      HomePage::TIMEZONE,
#endif
#if UI_BOARD_LEDS_PAGE == 1
      HomePage::BOARD_LEDS,
#endif
#if UI_LOW_BATTERY_SHUTDOWN_PAGE == 1 && defined(AUTO_SHUTDOWN_MILLIVOLTS)
      HomePage::LOW_BATT_SHUTDOWN,
#endif
#if UI_SMART_B11_EXTRAS == 1
#if UI_SMART_B12_TONE_LIST != 1
      HomePage::SMART_PROFILE,
#endif
      HomePage::FAVORITE_SLOT_1,
      HomePage::FAVORITE_SLOT_2,
      HomePage::FAVORITE_SLOT_3,
      HomePage::UNDO_SETTING,
      HomePage::DEVICE_STATUS,
#if UI_SMART_B12_TONE_LIST != 1
      HomePage::SETTINGS_TRANSFER,
#endif
#endif
    };
    static const uint8_t advanced_pages[] = {
#ifdef PIN_MSG_TONE
#if UI_TONE_8BIT_PAGE == 1
      HomePage::ALERT_TONE_STYLE,
#endif
#if UI_TONE_RESONANCE_PAGE == 1
      HomePage::ALERT_TONE_RESONANCE,
#endif
      HomePage::ALERT_TONE_PIN,
#if UI_TONE_BRIDGE_PAGE == 1
      HomePage::ALERT_TONE_BRIDGE,
#endif
#endif
#ifdef PIN_MSG_ALERT
      HomePage::ALERT_LED,
#endif
#if UI_ADC_MULTIPLIER_PAGE == 1
      HomePage::ADC,
#endif
#if UI_SMART_B11_EXTRAS == 1
      HomePage::HARDWARE_TEST,
#endif
    };

#if UI_SMART_B11_EXTRAS == 1
    if (group == 0) {
      count = 0;
      return NULL;
    }
    group--;
#endif
#if UI_SOUND_SETTINGS_GROUP == 0
    if (group >= 1) group++;
#endif
    switch (group) {
      case 0:
        count = sizeof(notification_pages) / sizeof(notification_pages[0]);
        return notification_pages;
      case 1:
        count = sizeof(sound_pages) / sizeof(sound_pages[0]);
        return sound_pages;
      case 2:
        count = sizeof(display_pages) / sizeof(display_pages[0]);
        return display_pages;
      case 3:
        count = sizeof(radio_pages) / sizeof(radio_pages[0]);
        return radio_pages;
      case 4:
        count = sizeof(system_pages) / sizeof(system_pages[0]);
        return system_pages;
      case 5:
        count = sizeof(advanced_pages) / sizeof(advanced_pages[0]);
        return advanced_pages;
      default:
        count = 0;
        return NULL;
    }
  }

  uint8_t compactSettingsItemCount(uint8_t group) const {
#if UI_SMART_B11_EXTRAS == 1
    if (group == 0) return 3;
#endif
    uint8_t raw_count = 0;
    const uint8_t* pages = compactSettingsRawPages(group, raw_count);
    uint8_t count = 0;
    for (uint8_t i = 0; pages != NULL && i < raw_count; i++) {
      if (isSettingsItem(pages[i])) count++;
    }
    return count;
  }

  uint8_t compactSettingsPageAt(uint8_t group, uint8_t index) const {
#if UI_SMART_B11_EXTRAS == 1
    if (group == 0) {
      if (index >= 3) return HomePage::SETTINGS;
      return resolvedFavoritePageAt(index);
    }
#endif
    uint8_t raw_count = 0;
    const uint8_t* pages = compactSettingsRawPages(group, raw_count);
    uint8_t visible = 0;
    for (uint8_t i = 0; pages != NULL && i < raw_count; i++) {
      if (!isSettingsItem(pages[i])) continue;
      if (visible == index) return pages[i];
      visible++;
    }
    return HomePage::SETTINGS;
  }

  const char* compactSettingsLabel(uint8_t page) const {
    switch (page) {
      case HomePage::ALERTS: return "Оповещения";
      case HomePage::IMPORTANT_NOTIFY: return "ЛС / упомин.";
      case HomePage::MSG_POPUP: return "Всплывающие";
#if UI_OFFLINE_DM_LED_PAGE == 1 && defined(PIN_MSG_ALERT)
      case HomePage::OFFLINE_DM_LED: return "LED без BLE";
      case HomePage::BLE_DM_LED: return "LED при BLE";
#endif
#if UI_APPEARANCE_MENU && UI_UNREAD_LED_PAGE == 1
      case HomePage::UNREAD_LED: return "LED непроч.";
#endif
#ifdef PIN_MSG_TONE
      case HomePage::ALERT_SOUND: return "Мелодия";
#if UI_SMART_B11_EXTRAS == 1
      case HomePage::ALERT_SOUND_DM: return "Мелодия ЛС";
      case HomePage::ALERT_SOUND_MENTION: return "Мелодия @";
#endif
#if UI_TONE_8BIT_PAGE == 1
      case HomePage::ALERT_TONE_STYLE: return "Стиль звука";
#endif
      case HomePage::ALERT_VOLUME: return "Громкость";
#if UI_TONE_RESONANCE_PAGE == 1
      case HomePage::ALERT_TONE_RESONANCE: return "Резонанс";
#endif
      case HomePage::ALERT_TONE_PIN: return "Выход звука";
#endif
      case HomePage::ALERT_VIBE_PIN: return "Вибрация";
#if UI_TONE_BRIDGE_PAGE == 1 && defined(PIN_MSG_TONE)
      case HomePage::ALERT_TONE_BRIDGE: return "Тип зуммера";
#endif
#ifdef PIN_MSG_ALERT
      case HomePage::ALERT_LED: return "Выход света";
#endif
#if UI_APPEARANCE_MENU
      case HomePage::UI_FONT: return "Шрифт";
      case HomePage::UI_THEME: return "Тема";
#if UI_COLOR_APPEARANCE_MENU
      case HomePage::UI_TOP_COLOR: return "Цвет верха";
      case HomePage::UI_BOTTOM_COLOR: return "Цвет низа";
#endif
#if UI_BACKLIGHT_TIMEOUT_PAGE == 1
      case HomePage::BACKLIGHT_TIMEOUT: return "Подсветка";
#endif
#endif
      case HomePage::RADIO: return "Радиоканал";
#if UI_AUTO_ADVERT_PAGE == 1
      case HomePage::ADVERT_TIMER: return "Авто-анонс";
#endif
#if UI_CLIENT_REPEAT_PAGE == 1
      case HomePage::CLIENT_REPEAT: return "Ретрансляция";
#endif
#if ENV_INCLUDE_GPS == 1 || UI_PHONE_GPS == 1
      case HomePage::GPS: return "GPS";
#endif
#if UI_CH2_RELAY_PAGE == 1
      case HomePage::CH2_RELAY: return "Канал 2";
#endif
#if UI_LINK_TEST_PAGE
      case HomePage::LINK_TEST: return "Опрос путей";
#endif
#if UI_ADC_MULTIPLIER_PAGE == 1
      case HomePage::ADC: return "Калибр. АКБ";
#endif
#if UI_TIMEZONE_PAGE == 1
      case HomePage::TIMEZONE: return "Часовой пояс";
#endif
      case HomePage::BLUETOOTH: return "Bluetooth";
#if UI_BOARD_LEDS_PAGE == 1
      case HomePage::BOARD_LEDS: return "LED платы";
#endif
#if UI_LOW_BATTERY_SHUTDOWN_PAGE == 1 && defined(AUTO_SHUTDOWN_MILLIVOLTS)
      case HomePage::LOW_BATT_SHUTDOWN: return "Защита АКБ";
#endif
#if UI_SMART_B11_EXTRAS == 1
#if UI_SMART_B12_TONE_LIST != 1
      case HomePage::SMART_PROFILE: return "Профиль";
#endif
      case HomePage::FAVORITE_SLOT_1: return "Избранное 1";
      case HomePage::FAVORITE_SLOT_2: return "Избранное 2";
      case HomePage::FAVORITE_SLOT_3: return "Избранное 3";
      case HomePage::UNDO_SETTING: return "Отменить изменение";
      case HomePage::DEVICE_STATUS: return "Состояние";
      case HomePage::HARDWARE_TEST: return "Тест оборудования";
#if UI_SMART_B12_TONE_LIST != 1
      case HomePage::SETTINGS_TRANSFER: return "Экспорт / импорт";
#endif
#endif
      default: return "Параметр";
    }
  }

  void compactSettingsValue(uint8_t page, char* out, size_t out_len) const {
    if (out_len == 0) return;
    out[0] = 0;
    switch (page) {
      case HomePage::ALERTS:
        snprintf(out, out_len, "%s", _task->getNotifyModeName());
        break;
      case HomePage::IMPORTANT_NOTIFY:
        snprintf(out, out_len, "%s", _task->getImportantNotifyModeName());
        break;
      case HomePage::MSG_POPUP:
        snprintf(out, out_len, "%s", _task->areMsgPopupsEnabled() ? "ВКЛ" : "ВЫКЛ");
        break;
#if UI_OFFLINE_DM_LED_PAGE == 1 && defined(PIN_MSG_ALERT)
      case HomePage::OFFLINE_DM_LED:
        snprintf(out, out_len, "%s", _task->isOfflineDmLedEnabled() ? "ВКЛ" : "ВЫКЛ");
        break;
      case HomePage::BLE_DM_LED:
        snprintf(out, out_len, "%s", _task->isBleDmLedEnabled() ? "ВКЛ" : "ВЫКЛ");
        break;
#endif
#if UI_APPEARANCE_MENU && UI_UNREAD_LED_PAGE == 1
      case HomePage::UNREAD_LED:
        snprintf(out, out_len, "%s", _task->isUnreadLedEnabled() ? "ВКЛ" : "ВЫКЛ");
        break;
#endif
#ifdef PIN_MSG_TONE
      case HomePage::ALERT_SOUND:
        snprintf(out, out_len, "%s", _task->getNotifySoundName());
        break;
#if UI_SMART_B11_EXTRAS == 1
      case HomePage::ALERT_SOUND_DM:
        snprintf(out, out_len, "%s", _task->getNotifyDmSoundName());
        break;
      case HomePage::ALERT_SOUND_MENTION:
        snprintf(out, out_len, "%s", _task->getNotifyMentionSoundName());
        break;
#endif
#if UI_TONE_8BIT_PAGE == 1
      case HomePage::ALERT_TONE_STYLE:
        snprintf(out, out_len, "%s", _task->getNotifyToneStyleName());
        break;
#endif
      case HomePage::ALERT_VOLUME:
#if UI_TONE_HIGH_DRIVE_PAGE == 1
        snprintf(out, out_len, "%s", _task->getNotifyToneDriveName());
#else
        snprintf(out, out_len, "%u/10", _task->getNotifyToneVolume());
#endif
        break;
#if UI_TONE_RESONANCE_PAGE == 1
      case HomePage::ALERT_TONE_RESONANCE:
        snprintf(out, out_len, "%u Гц", _task->getNotifyToneResonanceHz());
        break;
#endif
      case HomePage::ALERT_TONE_PIN:
      {
        int pin = _task->getNotifyTonePin();
        if (pin < 0) {
          snprintf(out, out_len, "ВЫКЛ");
#ifdef DEFAULT_NOTIFY_TONE_PIN
        } else if (pin == DEFAULT_NOTIFY_TONE_PIN) {
          snprintf(out, out_len, "ШТАТН.");
#endif
        } else {
          snprintf(out, out_len, "GPIO%d", pin);
        }
        break;
      }
#endif
      case HomePage::ALERT_VIBE_PIN: {
        int pin = _task->getNotifyVibePin();
        snprintf(out, out_len, "%s", pin >= 0 ? "ВКЛ" : "ВЫКЛ");
        break;
      }
#if UI_TONE_BRIDGE_PAGE == 1 && defined(PIN_MSG_TONE)
      case HomePage::ALERT_TONE_BRIDGE:
        snprintf(out, out_len, "%s", _task->isNotifyToneBridgeEnabled() ? "МОСТ" : "ОБЫЧН");
        break;
#endif
#ifdef PIN_MSG_ALERT
      case HomePage::ALERT_LED: {
        int pin = _task->getNotifyLedPin();
        if (pin < 0) {
          snprintf(out, out_len, "ВЫКЛ");
#ifdef DEFAULT_NOTIFY_GPIO_PIN
        } else if (pin == DEFAULT_NOTIFY_GPIO_PIN) {
          snprintf(out, out_len, "ШТАТН.");
#endif
        } else {
          snprintf(out, out_len, "GPIO%d", pin);
        }
        break;
      }
#endif
#if UI_APPEARANCE_MENU
      case HomePage::UI_FONT:
        snprintf(out, out_len, "%s", _task->getUiFontName());
        break;
      case HomePage::UI_THEME:
        snprintf(out, out_len, "%s", _task->getUiThemeName());
        break;
#if UI_COLOR_APPEARANCE_MENU
      case HomePage::UI_TOP_COLOR:
        snprintf(out, out_len, "%s", _task->getUiTopColorName());
        break;
      case HomePage::UI_BOTTOM_COLOR:
        snprintf(out, out_len, "%s", _task->getUiBottomColorName());
        break;
#endif
#if UI_BACKLIGHT_TIMEOUT_PAGE == 1
      case HomePage::BACKLIGHT_TIMEOUT:
        snprintf(out, out_len, "%s", _task->getBacklightTimeoutName());
        break;
#endif
#endif
      case HomePage::RADIO:
        snprintf(out, out_len, "%.3f", _node_prefs->freq);
        break;
#if UI_AUTO_ADVERT_PAGE == 1
      case HomePage::ADVERT_TIMER:
        snprintf(out, out_len, "%s", autoAdvertLabel());
        break;
#endif
#if UI_CLIENT_REPEAT_PAGE == 1
      case HomePage::CLIENT_REPEAT:
        snprintf(out, out_len, "%s", the_mesh.isClientRepeatEnabled() ? "ВКЛ" : "ВЫКЛ");
        break;
#endif
#if ENV_INCLUDE_GPS == 1 || UI_PHONE_GPS == 1
      case HomePage::GPS:
#if UI_PHONE_GPS == 1
        if (the_mesh.isPhoneGpsEnabled()) {
          snprintf(out, out_len, "%s", the_mesh.isPhoneGpsFresh() ? "ТЕЛ FIX" : "ТЕЛ ЖДЁТ");
        } else {
          snprintf(out, out_len, "%s", _task->getGPSState() ? "ВКЛ" : "ВЫКЛ");
        }
#else
        snprintf(out, out_len, "%s", _task->getGPSState() ? "ВКЛ" : "ВЫКЛ");
#endif
        break;
#endif
#if UI_CH2_RELAY_PAGE == 1
      case HomePage::CH2_RELAY:
        snprintf(out, out_len, "%s", the_mesh.getCh2ModeName());
        break;
#endif
#if UI_LINK_TEST_PAGE
      case HomePage::LINK_TEST:
        snprintf(out, out_len, "СТАРТ");
        break;
#endif
#if UI_ADC_MULTIPLIER_PAGE == 1
      case HomePage::ADC:
        formatAdcMultiplier(out, out_len, _task->getAdcMultiplier());
        break;
#endif
#if UI_TIMEZONE_PAGE == 1
      case HomePage::TIMEZONE: {
        int minutes = _task->getTimezoneOffsetMinutes();
        char sign = minutes < 0 ? '-' : '+';
        int magnitude = minutes < 0 ? -minutes : minutes;
        snprintf(out, out_len, "UTC%c%02d:%02d", sign, magnitude / 60, magnitude % 60);
        break;
      }
#endif
      case HomePage::BLUETOOTH:
        snprintf(out, out_len, "%s", _task->isBluetoothEnabled() ? "ВКЛ" : "ВЫКЛ");
        break;
#if UI_BOARD_LEDS_PAGE == 1
      case HomePage::BOARD_LEDS:
        snprintf(out, out_len, "%s", _task->areBoardLedsEnabled() ? "ВКЛ" : "ВЫКЛ");
        break;
#endif
#if UI_LOW_BATTERY_SHUTDOWN_PAGE == 1 && defined(AUTO_SHUTDOWN_MILLIVOLTS)
      case HomePage::LOW_BATT_SHUTDOWN:
        if (_task->getLowBatteryShutdownThreshold()) {
          uint16_t mv = _task->getLowBatteryShutdownThreshold();
          snprintf(out, out_len, "%s %u.%u", _task->isLowBatteryShutdownEnabled() ? "ВКЛ" : "ВЫК",
                   mv / 1000, (mv % 1000) / 100);
        } else {
          snprintf(out, out_len, "ВЫКЛ");
        }
        break;
#endif
#if UI_SMART_B11_EXTRAS == 1
#if UI_SMART_B12_TONE_LIST != 1
      case HomePage::SMART_PROFILE:
        snprintf(out, out_len, "%s", _task->getSmartProfileName());
        break;
#endif
      case HomePage::FAVORITE_SLOT_1:
      case HomePage::FAVORITE_SLOT_2:
      case HomePage::FAVORITE_SLOT_3: {
        uint8_t slot = page - HomePage::FAVORITE_SLOT_1;
        uint8_t favorite_page = resolvedFavoritePageAt(slot);
        snprintf(out, out_len, "%s", compactSettingsLabel(favorite_page));
        break;
      }
      case HomePage::UNDO_SETTING:
        snprintf(out, out_len, "%s", _compact_undo_valid ? "ГОТОВО" : "НЕТ");
        break;
      case HomePage::DEVICE_STATUS:
      case HomePage::HARDWARE_TEST:
        snprintf(out, out_len, "ОТКРЫТЬ");
        break;
#if UI_SMART_B12_TONE_LIST != 1
      case HomePage::SETTINGS_TRANSFER:
        snprintf(out, out_len, "BLE");
        break;
#endif
#endif
      default:
        break;
    }
  }

  void compactSettingsGroupSummary(uint8_t group, char* out, size_t out_len) const {
    if (out_len == 0) return;
#if UI_SMART_B11_EXTRAS == 1
    if (group == 0) {
      snprintf(out, out_len, "3 пункта");
      return;
    }
    group--;
#endif
#if UI_SOUND_SETTINGS_GROUP == 0
    if (group >= 1) group++;
#endif
    switch (group) {
      case 0:
#if UI_NOTIFICATION_SETTINGS == 1
        snprintf(out, out_len, "%s", _task->getNotifyModeName());
#else
        snprintf(out, out_len, "ЭКРАН");
#endif
        break;
      case 1:
        snprintf(out, out_len, "%s", _task->isNotifyToneHighDriveEnabled() ? "МАКС" : "ОБЫЧ");
        break;
      case 2:
        snprintf(out, out_len, "%s", _task->getUiFontName());
        break;
      case 3:
#if ENV_INCLUDE_GPS == 1 || UI_PHONE_GPS == 1
        snprintf(out, out_len, "GPS %s", _task->getGPSState() ? "ВКЛ" : "ВЫКЛ");
#else
        snprintf(out, out_len, "%.3f", _node_prefs->freq);
#endif
        break;
      case 4:
        snprintf(out, out_len, "BLE %s", _task->isBluetoothEnabled() ? "ВКЛ" : "ВЫКЛ");
        break;
      case 5:
        snprintf(out, out_len, "СЕРВИС");
        break;
      default:
        out[0] = 0;
        break;
    }
  }

  void renderCompactSettings(DisplayDriver& display) const {
    uint8_t saved_font = uiPushCompactSettingsFont(display);
    int line_h = display.getTextLineHeight();
    if (line_h < 8) line_h = 8;
    const char* title = _compact_settings_depth == 0
      ? "Настройки"
      : compactSettingsGroupName(_compact_settings_group);
    display.setColor(DisplayDriver::GREEN);
    drawRichTextStaticEllipsized(display, 2, 14, display.width() - 38, title);
    display.setColor(DisplayDriver::LIGHT);
    display.drawTextRightAlign(display.width() - 2, 14, "<>OK");

    uint8_t item_count = _compact_settings_depth == 0
      ? COMPACT_SETTINGS_GROUP_COUNT + 1
      : compactSettingsItemCount(_compact_settings_group) + 1;
    int row_y = 14 + line_h + 1;
    if (display.height() <= 64 && row_y < 28) row_y = 28;
    int row_h = line_h > 12 ? line_h : 12;
    uint8_t visible_rows = (display.height() - row_y) / row_h;
    if (visible_rows < 1) visible_rows = 1;
    if (visible_rows > UI_COMPACT_SETTINGS_MAX_ROWS) visible_rows = UI_COMPACT_SETTINGS_MAX_ROWS;
    uint8_t start = 0;
    if (_compact_settings_cursor >= visible_rows) {
      start = _compact_settings_cursor - visible_rows + 1;
    }
    if (item_count > visible_rows && start + visible_rows > item_count) {
      start = item_count - visible_rows;
    }

    int value_width = display.width() > 140 ? 66 : 50;
    for (uint8_t row = 0; row < visible_rows && start + row < item_count; row++) {
      uint8_t index = start + row;
      bool selected = index == _compact_settings_cursor;
      const char* label = "";
      char value[48] = {0};
      if (_compact_settings_depth == 0) {
        if (index < COMPACT_SETTINGS_GROUP_COUNT) {
          label = compactSettingsGroupName(index);
          compactSettingsGroupSummary(index, value, sizeof(value));
        } else {
          label = "Закрыть";
        }
      } else {
        uint8_t group_items = compactSettingsItemCount(_compact_settings_group);
        if (index < group_items) {
          uint8_t page = compactSettingsPageAt(_compact_settings_group, index);
          label = compactSettingsLabel(page);
          compactSettingsValue(page, value, sizeof(value));
        } else {
          label = "Назад";
        }
      }

      int y = row_y + row * row_h;
      if (selected) {
        display.setColor(DisplayDriver::YELLOW);
        display.fillRect(0, y, display.width() - (item_count > visible_rows ? 3 : 0), row_h);
        display.setColor(DisplayDriver::DARK);
        display.setBold(true);
      } else {
        display.setColor(DisplayDriver::LIGHT);
        display.setBold(false);
      }
      int label_x = 3;
      int value_x = display.width() - value_width;
      int label_width = value[0] ? value_x - label_x - 2 : display.width() - label_x - 2;
      drawRichTextStaticEllipsized(display, label_x, y, label_width, label);
      if (value[0]) {
        display.setColor(selected ? DisplayDriver::DARK : DisplayDriver::GREEN);
        drawRichTextStaticEllipsized(display, value_x, y, value_width - 1, value);
      }
      display.setBold(false);
    }
    if (item_count > visible_rows) {
      int track_y = row_y;
      int track_h = visible_rows * row_h - 2;
      int thumb_h = (track_h * visible_rows) / item_count;
      if (thumb_h < 4) thumb_h = 4;
      int max_start = item_count - visible_rows;
      int thumb_y = track_y;
      if (max_start > 0) thumb_y += ((track_h - thumb_h) * start) / max_start;
      display.setColor(DisplayDriver::LIGHT);
      display.drawRect(display.width() - 2, track_y, 2, track_h);
      display.setColor(DisplayDriver::YELLOW);
      display.fillRect(display.width() - 2, thumb_y, 2, thumb_h);
    }
    uiPopFont(display, saved_font);
  }

#if UI_APPEARANCE_MENU
  void renderAppearancePicker(DisplayDriver& display, bool font_picker) const {
    uint8_t saved_font = uiPushCompactSettingsFont(display);
    int line_h = display.getTextLineHeight();
    if (line_h < 8) line_h = 8;
    uint8_t choice_count = font_picker ? _task->getUiFontCount() : _task->getUiThemeCount();
    uint8_t item_count = choice_count + 1;  // final item is a non-destructive exit
    uint8_t cursor = font_picker ? _font_picker_cursor : _theme_picker_cursor;
    if (cursor >= item_count) cursor = item_count - 1;

    int row_y = 14 + line_h + 1;
    if (display.height() <= 64 && row_y < 28) row_y = 28;
    int row_h = line_h > 12 ? line_h : 12;
    uint8_t visible_rows = (display.height() - row_y) / row_h;
    if (visible_rows < 1) visible_rows = 1;
    if (visible_rows > UI_COMPACT_SETTINGS_MAX_ROWS) visible_rows = UI_COMPACT_SETTINGS_MAX_ROWS;
    uint8_t start = 0;
    if (cursor >= visible_rows) start = cursor - visible_rows + 1;
    if (item_count > visible_rows && start + visible_rows > item_count) {
      start = item_count - visible_rows;
    }

    display.setColor(DisplayDriver::GREEN);
    drawRichTextStaticEllipsized(display, 2, 14, display.width() - 38,
                                 font_picker ? "Шрифт" : "Тема");
    display.setColor(DisplayDriver::LIGHT);
    display.drawTextRightAlign(display.width() - 2, 14, "<>OK");

    uint8_t active = font_picker ? _task->getUiFontChoiceIndex() : _task->getUiThemeChoiceIndex();
    bool has_scrollbar = item_count > visible_rows;
    for (uint8_t row = 0; row < visible_rows && start + row < item_count; row++) {
      uint8_t index = start + row;
      bool selected = index == cursor;
      int y = row_y + row * row_h;
      if (selected) {
        display.setColor(DisplayDriver::YELLOW);
        display.fillRect(0, y, display.width() - (has_scrollbar ? 3 : 0), row_h);
        display.setColor(DisplayDriver::DARK);
        display.setBold(true);
      } else {
        display.setColor(DisplayDriver::LIGHT);
        display.setBold(false);
      }

      int label_x = 3;
      int right_guard = has_scrollbar ? 5 : 3;
      if (index < choice_count) {
        bool is_active = index == active;
        int marker_width = is_active ? display.getTextWidth("OK") + 4 : 0;
        int label_width = display.width() - label_x - right_guard - marker_width;
        const char* name = font_picker ? _task->getUiFontChoiceName(index)
                                       : _task->getUiThemeChoiceName(index);
        drawRichTextStaticEllipsized(display, label_x, y, label_width, name);
        if (is_active) {
          display.setColor(selected ? DisplayDriver::DARK : DisplayDriver::GREEN);
          display.drawTextRightAlign(display.width() - right_guard, y, "OK");
        }
      } else {
        drawRichTextStaticEllipsized(display, label_x, y,
                                     display.width() - label_x - right_guard, "Назад");
      }
      display.setBold(false);
    }

    if (has_scrollbar) {
      int track_y = row_y;
      int track_h = visible_rows * row_h - 2;
      int thumb_h = (track_h * visible_rows) / item_count;
      if (thumb_h < 4) thumb_h = 4;
      int max_start = item_count - visible_rows;
      int thumb_y = track_y;
      if (max_start > 0) thumb_y += ((track_h - thumb_h) * start) / max_start;
      display.setColor(DisplayDriver::LIGHT);
      display.drawRect(display.width() - 2, track_y, 2, track_h);
      display.setColor(DisplayDriver::YELLOW);
      display.fillRect(display.width() - 2, thumb_y, 2, thumb_h);
    }
    uiPopFont(display, saved_font);
  }
#endif

#if UI_SMART_B12_TONE_LIST == 1 && defined(PIN_MSG_TONE)
  void renderTonePicker(DisplayDriver& display) const {
    uint8_t saved_font = uiPushCompactSettingsFont(display);
    int line_h = display.getTextLineHeight();
    if (line_h < 8) line_h = 8;
    uint8_t tone_count = _task->getNotifyToneCount();
    uint8_t item_count = tone_count + 1;
    int row_y = 14 + line_h + 1;
    if (display.height() <= 64 && row_y < 28) row_y = 28;
    int row_h = line_h > 12 ? line_h : 12;
    uint8_t visible_rows = (display.height() - row_y) / row_h;
    if (visible_rows < 1) visible_rows = 1;
    if (visible_rows > UI_COMPACT_SETTINGS_MAX_ROWS) visible_rows = UI_COMPACT_SETTINGS_MAX_ROWS;
    uint8_t start = 0;
    if (_tone_picker_cursor >= visible_rows) {
      start = _tone_picker_cursor - visible_rows + 1;
    }
    if (item_count > visible_rows && start + visible_rows > item_count) {
      start = item_count - visible_rows;
    }

    display.setColor(DisplayDriver::GREEN);
    drawRichTextStaticEllipsized(display, 2, 14, display.width() - 38, "Мелодия");
    display.setColor(DisplayDriver::LIGHT);
    display.drawTextRightAlign(display.width() - 2, 14, "<>OK");

    uint8_t current = _task->getNotifyToneId();
    for (uint8_t row = 0; row < visible_rows && start + row < item_count; row++) {
      uint8_t index = start + row;
      bool selected = index == _tone_picker_cursor;
      int y = row_y + row * row_h;
      if (selected) {
        display.setColor(DisplayDriver::YELLOW);
        display.fillRect(0, y, display.width() - (item_count > visible_rows ? 3 : 0), row_h);
        display.setColor(DisplayDriver::DARK);
        display.setBold(true);
      } else {
        display.setColor(DisplayDriver::LIGHT);
        display.setBold(false);
      }
      int label_x = 3;
      if (index < tone_count) {
        bool active = index == current;
        int value_width = active ? display.getTextWidth("OK") + 4 : 0;
        int label_width = display.width() - label_x - value_width - 3;
        drawRichTextStaticEllipsized(display, label_x, y, label_width, _task->getNotifyToneName(index));
        if (active) {
          display.setColor(selected ? DisplayDriver::DARK : DisplayDriver::GREEN);
          display.drawTextRightAlign(display.width() - 3, y, "OK");
        }
      } else {
        drawRichTextStaticEllipsized(display, label_x, y, display.width() - label_x - 3, "Назад");
      }
      display.setBold(false);
    }

    if (item_count > visible_rows) {
      int track_y = row_y;
      int track_h = visible_rows * row_h - 2;
      int thumb_h = (track_h * visible_rows) / item_count;
      if (thumb_h < 4) thumb_h = 4;
      int max_start = item_count - visible_rows;
      int thumb_y = track_y;
      if (max_start > 0) thumb_y += ((track_h - thumb_h) * start) / max_start;
      display.setColor(DisplayDriver::LIGHT);
      display.drawRect(display.width() - 2, track_y, 2, track_h);
      display.setColor(DisplayDriver::YELLOW);
      display.fillRect(display.width() - 2, thumb_y, 2, thumb_h);
    }
    uiPopFont(display, saved_font);
  }
#endif

  int notifyPickerActiveValue() const {
    switch (_notify_picker_page) {
#ifdef PIN_MSG_ALERT
      case HomePage::ALERT_LED: return _task->getNotifyLedPin();
#endif
#ifdef PIN_MSG_TONE
      case HomePage::ALERT_TONE_PIN: return _task->getNotifyTonePin();
      case HomePage::ALERT_VOLUME: return _task->getNotifyToneVolume();
#if UI_TONE_RESONANCE_PAGE == 1
      case HomePage::ALERT_TONE_RESONANCE: return _task->getNotifyToneResonanceHz();
#endif
#endif
      case HomePage::ALERT_VIBE_PIN: return _task->getNotifyVibePin();
      default: return -1;
    }
  }

  void beginNotifyPicker(uint8_t page) {
    _notify_picker.reset();
    _notify_picker_page = page;
#ifdef PIN_MSG_TONE
#if UI_TONE_RESONANCE_PAGE == 1
    if (page == HomePage::ALERT_TONE_RESONANCE) {
      for (int hz = 1800; hz <= 4200; hz += 400) _notify_picker.add(hz);
    } else
#endif
    if (page == HomePage::ALERT_VOLUME) {
      for (int volume = 1; volume <= 10; volume++) _notify_picker.add(volume);
    } else
#endif
    {
#if UI_NOTIFY_GPIO_SELECT
#if defined(PIN_MSG_TONE) && UI_TONE_BRIDGE_PAGE == 1
      if (page == HomePage::ALERT_TONE_PIN && _task->isNotifyToneBridgeEnabled()) {
        _task->cycleNotifyTonePin();  // Fixed bridge pair: informational alert only.
        return;
      }
#endif
      for (size_t i = 0; i < sizeof(notify_gpio_pins) / sizeof(notify_gpio_pins[0]); i++) {
        int pin = notify_gpio_pins[i];
        if (isNotifyGpioPinBlockedByBuild(pin)) continue;
#if UI_TONE_BRIDGE_PAGE == 1
        if (_task->isNotifyToneBridgeEnabled() &&
            (pin == DEFAULT_NOTIFY_TONE_PIN || pin == DEFAULT_NOTIFY_TONE_BRIDGE_PIN)) continue;
#endif
        _notify_picker.add(pin);
      }
#else
      _task->showAlert("Вывод фиксирован", 900);
      return;
#endif
    }
    _notify_picker.begin(notifyPickerActiveValue());
    _page = HomePage::NOTIFY_PICKER;
  }

  void renderNotifyPicker(DisplayDriver& display) const {
    uint8_t saved_font = uiPushCompactSettingsFont(display);
    int line_h = display.getTextLineHeight();
    if (line_h < 8) line_h = 8;
    const uint8_t item_count = _notify_picker.count() + 1;
    const uint8_t cursor = _notify_picker.cursor();
    int row_y = 14 + line_h + 1;
    if (display.height() <= 64 && row_y < 28) row_y = 28;
    int row_h = line_h > 12 ? line_h : 12;
    int available_rows = (display.height() - row_y) / row_h;
    uint8_t visible_rows = available_rows < 1 ? 1 : available_rows;
    if (visible_rows > UI_COMPACT_SETTINGS_MAX_ROWS) visible_rows = UI_COMPACT_SETTINGS_MAX_ROWS;
    uint8_t start = cursor >= visible_rows ? cursor - visible_rows + 1 : 0;
    if (item_count > visible_rows && start + visible_rows > item_count) start = item_count - visible_rows;
    const bool has_scrollbar = item_count > visible_rows;

    display.setColor(DisplayDriver::GREEN);
    drawRichTextStaticEllipsized(display, 2, 14, display.width() - 38, compactSettingsLabel(_notify_picker_page));
    display.setColor(DisplayDriver::LIGHT);
    display.drawTextRightAlign(display.width() - 2, 14, "<>OK");
    const int active_value = notifyPickerActiveValue();
    for (uint8_t row = 0; row < visible_rows && start + row < item_count; row++) {
      uint8_t index = start + row;
      bool selected = index == cursor;
      int y = row_y + row * row_h;
      if (selected) {
        display.setColor(DisplayDriver::YELLOW);
        display.fillRect(0, y, display.width() - (has_scrollbar ? 3 : 0), row_h);
      }
      display.setColor(selected ? DisplayDriver::DARK : DisplayDriver::LIGHT);
      display.setBold(selected);
      char label[32];
      bool active = false;
      if (index < _notify_picker.count()) {
        int value = _notify_picker.value(index);
        active = value == active_value;
        const char* format = "D%d";
#ifdef PIN_MSG_TONE
        if (_notify_picker_page == HomePage::ALERT_VOLUME) format = "%d/10";
#if UI_TONE_RESONANCE_PAGE == 1
        if (_notify_picker_page == HomePage::ALERT_TONE_RESONANCE) format = "%d Гц";
#endif
#endif
        snprintf(label, sizeof(label), format, value);
      } else {
        snprintf(label, sizeof(label), "Отмена");
      }
      int right_guard = has_scrollbar ? 5 : 3;
      int marker_width = active ? display.getTextWidth("OK") + 4 : 0;
      drawRichTextStaticEllipsized(display, 3, y, display.width() - 3 - right_guard - marker_width, label);
      if (active) display.drawTextRightAlign(display.width() - right_guard, y, "OK");
      display.setBold(false);
    }
    if (has_scrollbar) {
      int track_h = visible_rows * row_h - 2;
      int thumb_h = (track_h * visible_rows) / item_count;
      if (thumb_h < 4) thumb_h = 4;
      int thumb_y = row_y + ((track_h - thumb_h) * start) / (item_count - visible_rows);
      display.setColor(DisplayDriver::LIGHT);
      display.drawRect(display.width() - 2, row_y, 2, track_h);
      display.setColor(DisplayDriver::YELLOW);
      display.fillRect(display.width() - 2, thumb_y, 2, thumb_h);
    }
    uiPopFont(display, saved_font);
  }

#if UI_TIMEZONE_PAGE == 1
  static const int16_t TIMEZONE_MINUTES_MIN = -720;
  static const int16_t TIMEZONE_MINUTES_MAX = 840;
  static const int16_t TIMEZONE_MINUTES_STEP = 30;
  static const uint8_t TIMEZONE_CHOICE_COUNT =
      (TIMEZONE_MINUTES_MAX - TIMEZONE_MINUTES_MIN) / TIMEZONE_MINUTES_STEP + 1;

  int16_t timezoneMinutesAt(uint8_t index) const {
    if (index >= TIMEZONE_CHOICE_COUNT) return _task->getTimezoneOffsetMinutes();
    return (int16_t)(TIMEZONE_MINUTES_MIN + index * TIMEZONE_MINUTES_STEP);
  }

  void formatTimezone(char* out, size_t out_len, int16_t minutes) const {
    char sign = minutes < 0 ? '-' : '+';
    int magnitude = minutes < 0 ? -(int)minutes : (int)minutes;
    snprintf(out, out_len, "UTC%c%02d:%02d", sign, magnitude / 60, magnitude % 60);
  }

  void renderTimezonePicker(DisplayDriver& display) const {
    uint8_t saved_font = uiPushCompactSettingsFont(display);
    int line_h = display.getTextLineHeight();
    if (line_h < 8) line_h = 8;
    const uint8_t item_count = TIMEZONE_CHOICE_COUNT + 1;  // final row is Cancel
    uint8_t cursor = _timezone_picker_cursor;
    if (cursor >= item_count) cursor = item_count - 1;
    int row_y = 14 + line_h + 1;
    if (display.height() <= 64 && row_y < 28) row_y = 28;
    int row_h = line_h > 12 ? line_h : 12;
    int available_rows = (display.height() - row_y) / row_h;
    uint8_t visible_rows = available_rows < 1 ? 1 : available_rows;
    if (visible_rows > UI_COMPACT_SETTINGS_MAX_ROWS) visible_rows = UI_COMPACT_SETTINGS_MAX_ROWS;
    uint8_t start = cursor >= visible_rows ? cursor - visible_rows + 1 : 0;
    if (item_count > visible_rows && start + visible_rows > item_count) start = item_count - visible_rows;
    const bool has_scrollbar = item_count > visible_rows;

    display.setColor(DisplayDriver::GREEN);
    drawRichTextStaticEllipsized(display, 2, 14, display.width() - 38, "Часовой пояс");
    display.setColor(DisplayDriver::LIGHT);
    display.drawTextRightAlign(display.width() - 2, 14, "<>OK");

    const int16_t active_minutes = _task->getTimezoneOffsetMinutes();
    for (uint8_t row = 0; row < visible_rows && start + row < item_count; row++) {
      uint8_t index = start + row;
      bool selected = index == cursor;
      int y = row_y + row * row_h;
      if (selected) {
        display.setColor(DisplayDriver::YELLOW);
        display.fillRect(0, y, display.width() - (has_scrollbar ? 3 : 0), row_h);
      }
      display.setColor(selected ? DisplayDriver::DARK : DisplayDriver::LIGHT);
      display.setBold(selected);
      char label[20];
      bool active = false;
      if (index < TIMEZONE_CHOICE_COUNT) {
        int16_t minutes = timezoneMinutesAt(index);
        formatTimezone(label, sizeof(label), minutes);
        active = minutes == active_minutes;
      } else {
        strcpy(label, "Отмена");
      }
      int right_guard = has_scrollbar ? 5 : 3;
      int marker_width = active ? display.getTextWidth("OK") + 4 : 0;
      drawRichTextStaticEllipsized(display, 3, y,
          display.width() - 3 - right_guard - marker_width, label);
      if (active) display.drawTextRightAlign(display.width() - right_guard, y, "OK");
      display.setBold(false);
    }

    if (has_scrollbar) {
      int track_h = visible_rows * row_h - 2;
      int thumb_h = (track_h * visible_rows) / item_count;
      if (thumb_h < 4) thumb_h = 4;
      int thumb_y = row_y + ((track_h - thumb_h) * start) / (item_count - visible_rows);
      display.setColor(DisplayDriver::LIGHT);
      display.drawRect(display.width() - 2, row_y, 2, track_h);
      display.setColor(DisplayDriver::YELLOW);
      display.fillRect(display.width() - 2, thumb_y, 2, thumb_h);
    }
    uiPopFont(display, saved_font);
  }
#endif

  void applyNotifyPickerChoice(int16_t value) {
    switch (_notify_picker_page) {
#ifdef PIN_MSG_ALERT
      case HomePage::ALERT_LED: _task->setNotifyLedPin(value); break;
#endif
#ifdef PIN_MSG_TONE
      case HomePage::ALERT_TONE_PIN: _task->setNotifyTonePin(value); break;
      case HomePage::ALERT_VOLUME: _task->setNotifyToneVolume(value); break;
#if UI_TONE_RESONANCE_PAGE == 1
      case HomePage::ALERT_TONE_RESONANCE: _task->setNotifyToneResonanceHz(value); break;
#endif
#endif
      case HomePage::ALERT_VIBE_PIN: _task->setNotifyVibePin(value); break;
      default: break;
    }
  }

  void activateCompactSetting(uint8_t page) {
#if UI_SMART_B11_EXTRAS == 1
    NodePrefs before = *_node_prefs;
    bool track_undo = page != HomePage::UNDO_SETTING &&
                      page != HomePage::DEVICE_STATUS &&
                      page != HomePage::HARDWARE_TEST &&
                      page != HomePage::SETTINGS_TRANSFER &&
                      page != HomePage::RADIO &&
                      page != HomePage::LINK_TEST;
#endif
    switch (page) {
      case HomePage::ALERTS:
        _task->cycleNotifyMode();
        break;
      case HomePage::IMPORTANT_NOTIFY:
        _task->cycleImportantNotifyMode();
        break;
      case HomePage::MSG_POPUP:
        _task->toggleMsgPopups();
        break;
#if UI_OFFLINE_DM_LED_PAGE == 1 && defined(PIN_MSG_ALERT)
      case HomePage::OFFLINE_DM_LED:
        _task->toggleOfflineDmLed();
        break;
      case HomePage::BLE_DM_LED:
        _task->toggleBleDmLed();
        break;
#endif
#if UI_APPEARANCE_MENU && UI_UNREAD_LED_PAGE == 1
      case HomePage::UNREAD_LED:
        _task->toggleUnreadLed();
        break;
#endif
#ifdef PIN_MSG_TONE
      case HomePage::ALERT_SOUND:
#if UI_SMART_B12_TONE_LIST == 1
        _tone_picker_cursor = _task->getNotifyToneId();
        _page = HomePage::TONE_PICKER;
#else
        _task->cycleNotifySystemSound();
#endif
        break;
#if UI_SMART_B11_EXTRAS == 1
      case HomePage::ALERT_SOUND_DM:
        _task->cycleNotifyDmSound();
        break;
      case HomePage::ALERT_SOUND_MENTION:
        _task->cycleNotifyMentionSound();
        break;
#endif
#if UI_TONE_8BIT_PAGE == 1
      case HomePage::ALERT_TONE_STYLE:
        _task->toggleNotifyTone8Bit();
        break;
#endif
      case HomePage::ALERT_VOLUME:
#if UI_TONE_HIGH_DRIVE_PAGE == 1
        _task->toggleNotifyToneHighDrive();
#else
        beginNotifyPicker(page);
#endif
        break;
#if UI_TONE_RESONANCE_PAGE == 1
      case HomePage::ALERT_TONE_RESONANCE:
        beginNotifyPicker(page);
        break;
#endif
      case HomePage::ALERT_TONE_PIN:
        beginNotifyPicker(page);
        break;
#endif
      case HomePage::ALERT_VIBE_PIN:
        beginNotifyPicker(page);
        break;
#if UI_TONE_BRIDGE_PAGE == 1 && defined(PIN_MSG_TONE)
      case HomePage::ALERT_TONE_BRIDGE:
        _task->toggleNotifyToneBridge();
        break;
#endif
#ifdef PIN_MSG_ALERT
      case HomePage::ALERT_LED:
        beginNotifyPicker(page);
        break;
#endif
#if UI_APPEARANCE_MENU
      case HomePage::UI_FONT:
        _font_picker_cursor = _task->getUiFontChoiceIndex();
        _page = HomePage::FONT_PICKER;
        break;
      case HomePage::UI_THEME:
        _theme_picker_cursor = _task->getUiThemeChoiceIndex();
        _page = HomePage::THEME_PICKER;
        break;
#if UI_COLOR_APPEARANCE_MENU
      case HomePage::UI_TOP_COLOR:
        _task->cycleUiTopColor();
        break;
      case HomePage::UI_BOTTOM_COLOR:
        _task->cycleUiBottomColor();
        break;
#endif
#if UI_BACKLIGHT_TIMEOUT_PAGE == 1
      case HomePage::BACKLIGHT_TIMEOUT:
        _task->cycleBacklightTimeout();
        break;
#endif
#endif
      case HomePage::RADIO:
        _page = HomePage::RADIO;
        break;
#if UI_AUTO_ADVERT_PAGE == 1
      case HomePage::ADVERT_TIMER:
        the_mesh.cycleAutoAdvertInterval();
        _task->showAlert(autoAdvertLabel(), 800);
        break;
#endif
#if UI_CLIENT_REPEAT_PAGE == 1
      case HomePage::CLIENT_REPEAT:
        the_mesh.toggleClientRepeat();
        _task->showAlert(the_mesh.isClientRepeatEnabled() ? "Ретранс: ВКЛ" : "Ретранс: ВЫКЛ", 800);
        break;
#endif
#if ENV_INCLUDE_GPS == 1 || UI_PHONE_GPS == 1
      case HomePage::GPS:
        _task->toggleGPS();
        break;
#endif
#if UI_CH2_RELAY_PAGE == 1
      case HomePage::CH2_RELAY:
        the_mesh.cycleCh2Mode();
        _task->showAlert(the_mesh.getCh2ModeName(), 800);
        break;
#endif
#if UI_LINK_TEST_PAGE
      case HomePage::LINK_TEST:
        _task->showAlert(the_mesh.startLinkTest() ? "Опрос путей старт" : "Нет узлов", 900);
        break;
#endif
#if UI_ADC_MULTIPLIER_PAGE == 1
      case HomePage::ADC:
        _adc_edit = false;
        _page = HomePage::ADC;
        break;
#endif
#if UI_TIMEZONE_PAGE == 1
      case HomePage::TIMEZONE: {
        int minutes = _task->getTimezoneOffsetMinutes();
        if (minutes < -720) minutes = -720;
        if (minutes > 840) minutes = 840;
        _timezone_picker_cursor = (uint8_t)((minutes + 720 + 15) / 30);
        _page = HomePage::TIMEZONE_PICKER;
        break;
      }
#endif
      case HomePage::BLUETOOTH:
        if (_task->isBluetoothEnabled()) _task->disableBluetooth();
        else _task->enableBluetooth();
        break;
#if UI_BOARD_LEDS_PAGE == 1
      case HomePage::BOARD_LEDS:
        _task->toggleBoardLeds();
        break;
#endif
#if UI_LOW_BATTERY_SHUTDOWN_PAGE == 1 && defined(AUTO_SHUTDOWN_MILLIVOLTS)
      case HomePage::LOW_BATT_SHUTDOWN:
        _task->toggleLowBatteryShutdown();
        break;
#endif
#if UI_SMART_B11_EXTRAS == 1
#if UI_SMART_B12_TONE_LIST != 1
      case HomePage::SMART_PROFILE:
        _task->cycleSmartProfile();
        break;
#endif
      case HomePage::FAVORITE_SLOT_1:
      case HomePage::FAVORITE_SLOT_2:
      case HomePage::FAVORITE_SLOT_3:
        cycleFavoriteSlot(page - HomePage::FAVORITE_SLOT_1);
        break;
      case HomePage::UNDO_SETTING:
        if (_compact_undo_valid) {
          NodePrefs redo = *_node_prefs;
          *_node_prefs = _compact_undo_prefs;
          _compact_undo_prefs = redo;
          _task->applyImportedPrefs();
          the_mesh.savePrefs();
          _task->showAlert("Изменение отменено", 1000);
        } else {
          _task->showAlert("Нет изменения", 900);
        }
        break;
      case HomePage::DEVICE_STATUS:
        _page = HomePage::DEVICE_STATUS;
        break;
      case HomePage::HARDWARE_TEST:
        _hardware_test_step = 0;
        _page = HomePage::HARDWARE_TEST;
        break;
#if UI_SMART_B12_TONE_LIST != 1
      case HomePage::SETTINGS_TRANSFER:
        _page = HomePage::SETTINGS_TRANSFER;
        break;
#endif
#endif
      default:
        break;
    }
#if UI_SMART_B11_EXTRAS == 1
    bool prefs_changed = memcmp(&before, _node_prefs, sizeof(NodePrefs)) != 0;
#if UI_SMART_B12_TONE_LIST != 1
    bool favorite_config = page == HomePage::FAVORITE_SLOT_1 ||
                           page == HomePage::FAVORITE_SLOT_2 ||
                           page == HomePage::FAVORITE_SLOT_3;
    if (prefs_changed && page != HomePage::SMART_PROFILE && !favorite_config) {
      _node_prefs->smart_profile_id = SMART_PROFILE_CUSTOM;
      the_mesh.savePrefs();
    }
#endif
    if (track_undo && prefs_changed) {
      _compact_undo_prefs = before;
      _compact_undo_valid = true;
    }
#if UI_ADC_MULTIPLIER_PAGE == 1
    else if (track_undo && page == HomePage::ADC) {
      _compact_undo_prefs = before;
      _compact_undo_valid = true;
    }
#endif
#endif
  }

  bool handleCompactSettingsInput(char c) {
    if (!_settings_open) return false;
    if (_page != HomePage::SETTINGS) {
      if (_page == HomePage::NOTIFY_PICKER) {
        if (c == KEY_LEFT || c == KEY_PREV) {
          _notify_picker.move(-1);
          return true;
        }
        if (c == KEY_NEXT || c == KEY_RIGHT) {
          _notify_picker.move(1);
          return true;
        }
        if (c != KEY_ENTER) return false;
        int16_t value;
        if (_notify_picker.selected(value)) {
#if UI_SMART_B11_EXTRAS == 1
          NodePrefs before = *_node_prefs;
#endif
          applyNotifyPickerChoice(value);
#if UI_SMART_B11_EXTRAS == 1
          if (memcmp(&before, _node_prefs, sizeof(NodePrefs)) != 0) {
            _compact_undo_prefs = before;
            _compact_undo_valid = true;
          }
#endif
        }
        _notify_picker.reset();
        _page = HomePage::SETTINGS;
        return true;
      }
#if UI_TIMEZONE_PAGE == 1
      if (_page == HomePage::TIMEZONE_PICKER) {
        const uint8_t item_count = TIMEZONE_CHOICE_COUNT + 1;
        if (c == KEY_LEFT || c == KEY_PREV) {
          _timezone_picker_cursor = (_timezone_picker_cursor + item_count - 1) % item_count;
          return true;
        }
        if (c == KEY_NEXT || c == KEY_RIGHT) {
          _timezone_picker_cursor = (_timezone_picker_cursor + 1) % item_count;
          return true;
        }
        if (c != KEY_ENTER) return false;
        if (_timezone_picker_cursor < TIMEZONE_CHOICE_COUNT) {
#if UI_SMART_B11_EXTRAS == 1
          NodePrefs before = *_node_prefs;
#endif
          int16_t selected = timezoneMinutesAt(_timezone_picker_cursor);
          bool changed = selected != _task->getTimezoneOffsetMinutes();
          if (changed) _task->setTimezoneOffsetMinutes(selected, true);
#if UI_SMART_B11_EXTRAS == 1
          if (changed) {
            _compact_undo_prefs = before;
            _compact_undo_valid = true;
          }
#else
          (void)changed;
#endif
        }
        _page = HomePage::SETTINGS;
        return true;
      }
#endif
#if UI_APPEARANCE_MENU
      if (_page == HomePage::FONT_PICKER || _page == HomePage::THEME_PICKER) {
        bool font_picker = _page == HomePage::FONT_PICKER;
        uint8_t choice_count = font_picker ? _task->getUiFontCount() : _task->getUiThemeCount();
        uint8_t item_count = choice_count + 1;
        uint8_t* cursor = font_picker ? &_font_picker_cursor : &_theme_picker_cursor;
        if (*cursor >= item_count) *cursor = item_count - 1;
        if (c == KEY_LEFT || c == KEY_PREV) {
          *cursor = (*cursor + item_count - 1) % item_count;
          return true;
        }
        if (c == KEY_NEXT || c == KEY_RIGHT) {
          *cursor = (*cursor + 1) % item_count;
          return true;
        }
        if (c != KEY_ENTER) return false;
        if (*cursor >= choice_count) {
          _page = HomePage::SETTINGS;
          return true;
        }

#if UI_SMART_B11_EXTRAS == 1
        NodePrefs before = *_node_prefs;
#endif
        bool changed = *cursor != (font_picker ? _task->getUiFontChoiceIndex()
                                                : _task->getUiThemeChoiceIndex());
        if (font_picker) _task->setUiFontChoice(*cursor);
        else _task->setUiThemeChoice(*cursor);
#if UI_SMART_B11_EXTRAS == 1
        if (changed) {
          _compact_undo_prefs = before;
          _compact_undo_valid = true;
        }
#else
        (void)changed;
#endif
        _page = HomePage::SETTINGS;
        return true;
      }
#endif
#if UI_SMART_B12_TONE_LIST == 1 && defined(PIN_MSG_TONE)
      if (_page == HomePage::TONE_PICKER) {
        uint8_t tone_count = _task->getNotifyToneCount();
        uint8_t item_count = tone_count + 1;
        if (c == KEY_LEFT || c == KEY_PREV) {
          _tone_picker_cursor = (_tone_picker_cursor + item_count - 1) % item_count;
          return true;
        }
        if (c == KEY_NEXT || c == KEY_RIGHT) {
          _tone_picker_cursor = (_tone_picker_cursor + 1) % item_count;
          return true;
        }
        if (c != KEY_ENTER) return false;
        if (_tone_picker_cursor >= tone_count) {
          _page = HomePage::SETTINGS;
          return true;
        }

#if UI_SMART_B11_EXTRAS == 1
        NodePrefs before = *_node_prefs;
#endif
        bool changed = _tone_picker_cursor != _task->getNotifyToneId();
        _task->setCommonNotifyTone(_tone_picker_cursor);
#if UI_SMART_B11_EXTRAS == 1
        if (changed) {
          _compact_undo_prefs = before;
          _compact_undo_valid = true;
        }
#else
        (void)changed;
#endif
        _page = HomePage::SETTINGS;
        return true;
      }
#endif
#if UI_SMART_B11_EXTRAS == 1
      if (_page == HomePage::HARDWARE_TEST && c == KEY_ENTER) {
        _hardware_test_step++;
        if (_hardware_test_step > 7) _hardware_test_step = 0;
        _task->runHardwareTestStep(_hardware_test_step);
        return true;
      }
#endif
#if UI_ADC_MULTIPLIER_PAGE == 1
      if (_page == HomePage::ADC) {
        if (_adc_edit) return false;
        if (c == KEY_ENTER) return false;
      }
#endif
      if (c == KEY_LEFT || c == KEY_PREV || c == KEY_NEXT || c == KEY_RIGHT || c == KEY_ENTER) {
        _page = HomePage::SETTINGS;
        return true;
      }
      return false;
    }

    uint8_t item_count = _compact_settings_depth == 0
      ? COMPACT_SETTINGS_GROUP_COUNT + 1
      : compactSettingsItemCount(_compact_settings_group) + 1;
    if (c == KEY_LEFT || c == KEY_PREV) {
      _compact_settings_cursor = (_compact_settings_cursor + item_count - 1) % item_count;
      return true;
    }
    if (c == KEY_NEXT || c == KEY_RIGHT) {
      _compact_settings_cursor = (_compact_settings_cursor + 1) % item_count;
      return true;
    }
    if (c != KEY_ENTER) return false;

    if (_compact_settings_depth == 0) {
      if (_compact_settings_cursor >= COMPACT_SETTINGS_GROUP_COUNT) {
#if UI_ADC_MULTIPLIER_PAGE == 1
        cancelAdcEdit();
#endif
        _settings_open = false;
        _compact_settings_cursor = 0;
      } else {
        _compact_settings_group = _compact_settings_cursor;
        _compact_settings_depth = 1;
        _compact_settings_cursor = 0;
      }
      return true;
    }

    uint8_t group_items = compactSettingsItemCount(_compact_settings_group);
    if (_compact_settings_cursor >= group_items) {
      _compact_settings_depth = 0;
      _compact_settings_cursor = _compact_settings_group;
      return true;
    }
    activateCompactSetting(compactSettingsPageAt(_compact_settings_group, _compact_settings_cursor));
    return true;
  }
#endif

  bool isSettingsItem(uint8_t page) const {
#if UI_COMPACT_SETTINGS_MENU == 1
    if (page == HomePage::NOTIFY_PICKER) return true;
#endif
#if UI_NOTIFICATION_SETTINGS == 1
    if (page == HomePage::ALERTS) return true;
#endif
#ifdef PIN_MSG_ALERT
    if (page == HomePage::ALERT_LED) return true;
#endif
#ifdef PIN_MSG_TONE
    if (page == HomePage::ALERT_TONE_PIN || page == HomePage::ALERT_SOUND || page == HomePage::ALERT_VOLUME
#if UI_SMART_B11_EXTRAS == 1
        || page == HomePage::ALERT_SOUND_DM || page == HomePage::ALERT_SOUND_MENTION
#endif
#if UI_TONE_BRIDGE_PAGE == 1
        || page == HomePage::ALERT_TONE_BRIDGE
#endif
#if UI_TONE_8BIT_PAGE == 1
        || page == HomePage::ALERT_TONE_STYLE
#endif
#if UI_TONE_RESONANCE_PAGE == 1
        || page == HomePage::ALERT_TONE_RESONANCE
#endif
       ) {
      return true;
    }
#endif
    if (page == HomePage::ALERT_VIBE_PIN) return true;
    if (page == HomePage::RADIO) return true;
#if UI_CLIENT_REPEAT_PAGE == 1
    if (page == HomePage::CLIENT_REPEAT) return true;
#endif
#if UI_LINK_TEST_PAGE
    if (page == HomePage::LINK_TEST) return true;
#endif
    if (page == HomePage::BLUETOOTH) return true;
    if (page == HomePage::MSG_POPUP) return true;
#if UI_NOTIFICATION_SETTINGS == 1
    if (page == HomePage::IMPORTANT_NOTIFY) return true;
#endif
#if UI_OFFLINE_DM_LED_PAGE == 1 && defined(PIN_MSG_ALERT)
    if (page == HomePage::OFFLINE_DM_LED) return true;
    if (page == HomePage::BLE_DM_LED) return true;
#endif
#if UI_BOARD_LEDS_PAGE == 1
    if (page == HomePage::BOARD_LEDS) return true;
#endif
#if UI_APPEARANCE_MENU
#if UI_UNREAD_LED_PAGE == 1
    if (page == HomePage::UNREAD_LED) return true;
#endif
    if (page == HomePage::UI_FONT) return _task->hasUiFontChoices();
    if (page == HomePage::UI_THEME) return _task->hasUiThemeChoices();
#if UI_COLOR_APPEARANCE_MENU
    if (page == HomePage::UI_TOP_COLOR) return true;
    if (page == HomePage::UI_BOTTOM_COLOR) return true;
#endif
#if UI_BACKLIGHT_TIMEOUT_PAGE == 1
    if (page == HomePage::BACKLIGHT_TIMEOUT) return true;
#endif
#endif
#if UI_AUTO_ADVERT_PAGE == 1
    if (page == HomePage::ADVERT_TIMER) return true;
#endif
#if UI_CH2_RELAY_PAGE == 1
    if (page == HomePage::CH2_RELAY) return true;
#endif
#if ENV_INCLUDE_GPS == 1 || UI_PHONE_GPS == 1
    if (page == HomePage::GPS) return true;
#endif
#if UI_ADC_MULTIPLIER_PAGE == 1
    if (page == HomePage::ADC) return true;
#endif
#if UI_TIMEZONE_PAGE == 1
    if (page == HomePage::TIMEZONE) return true;
#endif
#if UI_LOW_BATTERY_SHUTDOWN_PAGE == 1 && defined(AUTO_SHUTDOWN_MILLIVOLTS)
    if (page == HomePage::LOW_BATT_SHUTDOWN) return true;
#endif
#if UI_SMART_B11_EXTRAS == 1
    if (page == HomePage::FAVORITE_SLOT_1 ||
        page == HomePage::FAVORITE_SLOT_2 ||
        page == HomePage::FAVORITE_SLOT_3 ||
        page == HomePage::UNDO_SETTING ||
        page == HomePage::DEVICE_STATUS ||
        page == HomePage::HARDWARE_TEST
#if UI_SMART_B12_TONE_LIST == 1 && defined(PIN_MSG_TONE)
        || page == HomePage::TONE_PICKER
#else
        || page == HomePage::SMART_PROFILE ||
        page == HomePage::SETTINGS_TRANSFER
#endif
       ) return true;
#endif
    return false;
  }

  bool isPageVisibleInCurrentMenu(uint8_t page) const {
#if UI_COMPACT_SETTINGS_MENU == 1
    if (page == HomePage::NOTIFY_PICKER) return false;  // Only entered through a setting.
#if UI_TIMEZONE_PAGE == 1
    if (page == HomePage::TIMEZONE_PICKER) return false;
#endif
#endif
#if UI_NOTIFICATION_SETTINGS == 0
    if (page == HomePage::ALERTS || page == HomePage::IMPORTANT_NOTIFY) return false;
#endif
#if UI_COMPACT_SETTINGS_MENU == 1 && UI_APPEARANCE_MENU
    if (page == HomePage::FONT_PICKER || page == HomePage::THEME_PICKER) return false;
#endif
#if UI_SMART_B12_TONE_LIST == 1 && UI_SMART_B11_EXTRAS == 1
    if (page == HomePage::SMART_PROFILE || page == HomePage::SETTINGS_TRANSFER) return false;
#endif
#if !UI_CLOCK_PAGE_VISIBLE
    if (page == HomePage::CLOCK) return false;
#endif
#if UI_HIDE_FIRST_PAGE
    if (page == HomePage::FIRST) return false;
#endif
#if UI_BLE_PIN_PAGE
    if (page == HomePage::BLE_PIN) {
      return !_settings_open && !_task->hasConnection() && the_mesh.getBLEPin() != 0;
    }
#endif
    if (!UI_RECENT_PAGE && page == HomePage::RECENT) return false;
    if (!UI_LINK_TEST_PAGE && page == HomePage::LINK_TEST) return false;
#if UI_APPEARANCE_MENU
    if (page == HomePage::UI_FONT && !_task->hasUiFontChoices()) return false;
    if (page == HomePage::UI_THEME && !_task->hasUiThemeChoices()) return false;
#endif
    if (_settings_open) {
      return page == HomePage::SETTINGS || isSettingsItem(page);
    }
    return !isSettingsItem(page);
  }

  uint8_t nextVisiblePage(uint8_t page, int8_t direction) const {
#if UI_HOME_ORDER_START_AT_FIRST
    if (!_settings_open) {
      static const uint8_t order[] = {
        HomePage::FIRST,
        HomePage::RECENT,
        HomePage::NETWORK,
        HomePage::CHAT,
        HomePage::ADVERT,
        HomePage::SETTINGS,
        HomePage::SHUTDOWN,
        HomePage::CLOCK,
#if UI_BLE_PIN_PAGE
        HomePage::BLE_PIN
#endif
      };
      const uint8_t order_count = sizeof(order) / sizeof(order[0]);
      uint8_t pos = 0;
      for (uint8_t i = 0; i < order_count; i++) {
        if (order[i] == page) {
          pos = i;
          break;
        }
      }
      for (uint8_t i = 0; i < order_count; i++) {
        pos = direction > 0 ? (pos + 1) % order_count : (pos + order_count - 1) % order_count;
        if (isPageVisibleInCurrentMenu(order[pos])) return order[pos];
      }
      return defaultHomePage();
    }
#endif
    for (uint8_t i = 0; i < HomePage::Count; i++) {
      page = direction > 0 ? (page + 1) % HomePage::Count : (page + HomePage::Count - 1) % HomePage::Count;
      if (isPageVisibleInCurrentMenu(page)) return page;
    }
    return defaultHomePage();
  }

  static uint8_t defaultHomePage() {
#if UI_HOME_START_PAGE_FIRST
    return HomePage::FIRST;
#else
    return HomePage::CLOCK;
#endif
  }

  uint8_t firstSettingsPage() const {
    for (uint8_t i = 0, page = HomePage::SETTINGS; i < HomePage::Count; i++) {
      page = (page + 1) % HomePage::Count;
      if (isSettingsItem(page)) return page;
    }
    return HomePage::SETTINGS;
  }

  uint8_t visiblePageCount() const {
    uint8_t count = 0;
    for (uint8_t page = 0; page < HomePage::Count; page++) {
      if (isPageVisibleInCurrentMenu(page)) count++;
    }
    return count > 0 ? count : 1;
  }

  uint8_t visiblePageIndex() const {
    uint8_t index = 0;
#if UI_HOME_ORDER_START_AT_FIRST
    if (!_settings_open) {
      static const uint8_t order[] = {
        HomePage::FIRST,
        HomePage::RECENT,
        HomePage::NETWORK,
        HomePage::CHAT,
        HomePage::ADVERT,
        HomePage::SETTINGS,
        HomePage::SHUTDOWN,
        HomePage::CLOCK,
#if UI_BLE_PIN_PAGE
        HomePage::BLE_PIN
#endif
      };
      for (uint8_t i = 0; i < sizeof(order) / sizeof(order[0]); i++) {
        uint8_t page = order[i];
        if (!isPageVisibleInCurrentMenu(page)) continue;
        if (page == _page) return index;
        index++;
      }
      return 0;
    }
#endif
    for (uint8_t page = 0; page < HomePage::Count; page++) {
      if (!isPageVisibleInCurrentMenu(page)) continue;
      if (page == _page) return index;
      index++;
    }
    return 0;
  }

  void showPageAlert(uint8_t page) {
    if (page == HomePage::RECENT) {
      _task->showAlert("Недавние", 800);
    } else if (page == HomePage::CLOCK) {
      _task->showAlert("Часы", 800);
    } else if (page == HomePage::NETWORK) {
      _task->showAlert("Сеть", 800);
    } else if (page == HomePage::CHAT) {
      _task->showAlert("Чат", 800);
    } else if (page == HomePage::ALERTS) {
      _task->showAlert("Сигналы", 800);
    } else if (page == HomePage::SETTINGS) {
      _task->showAlert(_settings_open ? "Назад" : "Настройки", 800);
    } else if (page == HomePage::RADIO) {
      _task->showAlert("Радио", 800);
#if UI_CLIENT_REPEAT_PAGE == 1
    } else if (page == HomePage::CLIENT_REPEAT) {
      _task->showAlert("Ретрансляция", 800);
#endif
    } else if (page == HomePage::LINK_TEST) {
      _task->showAlert("Опрос путей", 800);
    } else if (page == HomePage::BLUETOOTH) {
      _task->showAlert("Bluetooth", 800);
#if UI_BLE_PIN_PAGE
    } else if (page == HomePage::BLE_PIN) {
      _task->showAlert("BLE PIN", 800);
#endif
    } else if (page == HomePage::MSG_POPUP) {
      _task->showAlert("Всплыв. сообщ.", 800);
    } else if (page == HomePage::IMPORTANT_NOTIFY) {
      _task->showAlert("ЛС/упомин.", 800);
#if UI_OFFLINE_DM_LED_PAGE == 1 && defined(PIN_MSG_ALERT)
    } else if (page == HomePage::OFFLINE_DM_LED) {
      _task->showAlert("LED ЛС без BLE", 800);
    } else if (page == HomePage::BLE_DM_LED) {
      _task->showAlert("LED ЛС при BLE", 800);
#endif
#if UI_BOARD_LEDS_PAGE == 1
    } else if (page == HomePage::BOARD_LEDS) {
      _task->showAlert("LED платы", 800);
#endif
#if UI_APPEARANCE_MENU
#if UI_UNREAD_LED_PAGE == 1
    } else if (page == HomePage::UNREAD_LED) {
      _task->showAlert("Непроч. LED", 800);
#endif
    } else if (page == HomePage::UI_FONT) {
      _task->showAlert("Шрифт", 800);
    } else if (page == HomePage::UI_THEME) {
      _task->showAlert("Цвет экрана", 800);
#if UI_COLOR_APPEARANCE_MENU
    } else if (page == HomePage::UI_TOP_COLOR) {
      _task->showAlert("Цвет верха", 800);
    } else if (page == HomePage::UI_BOTTOM_COLOR) {
      _task->showAlert("Цвет низа", 800);
#endif
#if UI_BACKLIGHT_TIMEOUT_PAGE == 1
    } else if (page == HomePage::BACKLIGHT_TIMEOUT) {
      _task->showAlert("Подсветка", 800);
#endif
#endif
#if UI_AUTO_ADVERT_PAGE == 1
    } else if (page == HomePage::ADVERT_TIMER) {
      _task->showAlert("Авто-анонс", 800);
#endif
#if UI_CH2_RELAY_PAGE == 1
    } else if (page == HomePage::CH2_RELAY) {
      _task->showAlert("Канал 2", 800);
#endif
#if ENV_INCLUDE_GPS == 1 || UI_PHONE_GPS == 1
    } else if (page == HomePage::GPS) {
      _task->showAlert("GPS", 800);
#endif
#ifdef PIN_MSG_ALERT
    } else if (page == HomePage::ALERT_LED) {
      _task->showAlert("Пин света", 800);
#endif
#ifdef PIN_MSG_TONE
    } else if (page == HomePage::ALERT_TONE_PIN) {
      _task->showAlert("Пин звука", 800);
#if UI_TONE_BRIDGE_PAGE == 1
    } else if (page == HomePage::ALERT_TONE_BRIDGE) {
      _task->showAlert("Схема зуммера", 800);
#endif
#endif
    } else if (page == HomePage::ALERT_VIBE_PIN) {
      _task->showAlert("Пин вибро", 800);
#ifdef PIN_MSG_TONE
    } else if (page == HomePage::ALERT_SOUND) {
      _task->showAlert("Мелодия", 800);
#if UI_TONE_8BIT_PAGE == 1
    } else if (page == HomePage::ALERT_TONE_STYLE) {
      _task->showAlert("Стиль звука", 800);
#endif
    } else if (page == HomePage::ALERT_VOLUME) {
#if UI_TONE_HIGH_DRIVE_PAGE == 1
      _task->showAlert("Громкость GPIO", 800);
#else
      _task->showAlert("Громкость", 800);
#endif
#if UI_TONE_RESONANCE_PAGE == 1
    } else if (page == HomePage::ALERT_TONE_RESONANCE) {
      _task->showAlert("Резонанс пьезо", 800);
#endif
#endif
#if UI_ADC_MULTIPLIER_PAGE == 1
    } else if (page == HomePage::ADC) {
      _task->showAlert("Калибровка АКБ", 800);
#endif
#if UI_LOW_BATTERY_SHUTDOWN_PAGE == 1 && defined(AUTO_SHUTDOWN_MILLIVOLTS)
    } else if (page == HomePage::LOW_BATT_SHUTDOWN) {
      _task->showAlert("Защита АКБ", 800);
#endif
    }
  }

#if UI_AUTO_ADVERT_PAGE == 1
  const char* autoAdvertLabel() const {
    uint16_t mins = the_mesh.getAutoAdvertIntervalMins();
    switch (mins) {
      case 15: return "15 мин";
      case 30: return "30 мин";
      case 60: return "1 час";
      case 120: return "2 часа";
      case 180: return "3 часа";
      case 0:
      default: return "выкл";
    }
  }
#endif

  uint8_t quickReplyMenuCount() const {
#if UI_QUICK_REPLY_KEYBOARD
    return quick_reply_count + 2; // canned replies + keyboard + back
#else
    return quick_reply_count + 1; // canned replies + back
#endif
  }

#if UI_QUICK_REPLY_KEYBOARD
  uint8_t quickReplyKeyboardIndex() const {
    return quick_reply_count;
  }
#endif

  uint8_t quickReplyBackIndex() const {
#if UI_QUICK_REPLY_KEYBOARD
    return quick_reply_count + 1;
#else
    return quick_reply_count;
#endif
  }

  const char* quickReplyLabel() const {
    if (_quick_reply_idx < quick_reply_count) return quick_reply_texts[_quick_reply_idx];
#if UI_QUICK_REPLY_KEYBOARD
    if (_quick_reply_idx == quickReplyKeyboardIndex()) return "Клавиатура";
#endif
    return "Назад";
  }

#if UI_QUICK_REPLY_KEYBOARD
  void clearQuickTargetIdentity() {
    _quick_target_identity_valid = false;
    _quick_target_identity_mode = QR_TARGET_CLOSED;
    _quick_target_identity_cursor = 0;
    _quick_target_channel_id = 0;
    memset(_quick_target_contact_pubkey, 0, sizeof(_quick_target_contact_pubkey));
    _quick_target_identity_label[0] = 0;
  }

  bool quickTargetIdentityMatchesCursor() const {
    return _quick_target_identity_valid &&
           _quick_target_identity_mode == _quick_target_mode &&
           _quick_target_identity_cursor == _quick_target_cursor;
  }

  bool captureQuickTargetIdentity() {
    clearQuickTargetIdentity();
    if (_quick_target_mode == QR_TARGET_CHANNEL) {
      uint8_t channel_id = 0;
      ChannelDetails channel;
      if (!the_mesh.getQuickReplyChannel(_quick_target_cursor, channel_id, channel)) return false;
      _quick_target_channel_id = channel_id;
      snprintf(_quick_target_identity_label, sizeof(_quick_target_identity_label), "%s", channel.name);
    } else if (_quick_target_mode == QR_TARGET_CONTACT) {
      ContactInfo contact;
      if (!the_mesh.getQuickReplyContact(_quick_target_cursor, contact)) return false;
      memcpy(_quick_target_contact_pubkey, contact.id.pub_key,
             sizeof(_quick_target_contact_pubkey));
      snprintf(_quick_target_identity_label, sizeof(_quick_target_identity_label), "%s", contact.name);
    } else {
      return false;
    }
    _quick_target_identity_mode = _quick_target_mode;
    _quick_target_identity_cursor = _quick_target_cursor;
    _quick_target_identity_valid = true;
    return true;
  }

  void resetQuickKeyboard() {
    _quick_keyboard_open = false;
    _quick_keyboard_page = 0;
    _quick_keyboard_cursor = 0;
    _quick_target_mode = QR_TARGET_CLOSED;
    _quick_target_cursor = 0;
    clearQuickTargetIdentity();
    _quick_keyboard_text[0] = 0;
  }

  void openQuickKeyboard() {
    _quick_keyboard_open = true;
    _quick_keyboard_page = 0;
    _quick_keyboard_cursor = 0;
    _quick_target_mode = QR_TARGET_CLOSED;
    _quick_target_cursor = 0;
    clearQuickTargetIdentity();
    _quick_keyboard_text[0] = 0;
  }

  bool appendQuickKeyboardText(const char* text) {
    if (text == NULL || text[0] == 0) return false;
    size_t len = strlen(_quick_keyboard_text);
    size_t add = strlen(text);
    if (len + add >= sizeof(_quick_keyboard_text)) return false;
    memcpy(&_quick_keyboard_text[len], text, add + 1);
    return true;
  }

  void deleteQuickKeyboardChar() {
    size_t len = strlen(_quick_keyboard_text);
    if (len == 0) return;
    size_t cut = len - 1;
    while (cut > 0 && (((uint8_t)_quick_keyboard_text[cut]) & 0xC0) == 0x80) {
      cut--;
    }
    _quick_keyboard_text[cut] = 0;
  }

  const QuickReplyKeyboardKey& currentQuickKeyboardKey() const {
    uint8_t page = _quick_keyboard_page;
    if (page >= quick_reply_keyboard_page_count) page = 0;
    uint8_t cursor = _quick_keyboard_cursor;
    if (cursor >= QR_KB_KEYS) cursor = 0;
    return quick_reply_keyboard_pages[page][cursor];
  }

  uint16_t quickTargetItemCount() const {
    switch (_quick_target_mode) {
      case QR_TARGET_KIND: return 3;
      case QR_TARGET_CHANNEL: return (uint16_t)the_mesh.getQuickReplyChannelCount();
      case QR_TARGET_CONTACT: return (uint16_t)the_mesh.getQuickReplyContactCount();
      default: return 0;
    }
  }

  uint16_t quickTargetTotalCount() const {
    uint16_t items = quickTargetItemCount();
    if (_quick_target_mode == QR_TARGET_CHANNEL || _quick_target_mode == QR_TARGET_CONTACT) return items + 1;
    return items;
  }

  const char* quickTargetTitle() const {
    switch (_quick_target_mode) {
      case QR_TARGET_CHANNEL: return "Чат";
      case QR_TARGET_CONTACT: return "Контакт";
      case QR_TARGET_KIND:
      default: return "Куда?";
    }
  }

  void quickTargetLabel(uint16_t idx, char* out, size_t out_len) const {
    if (out_len == 0) return;
    out[0] = 0;
    if (_quick_target_mode == QR_TARGET_KIND) {
      if (idx == 0) {
        int count = the_mesh.getQuickReplyChannelCount();
        if (count > 0) snprintf(out, out_len, "Чаты: %d", count);
        else snprintf(out, out_len, "Чаты: нет");
      } else if (idx == 1) {
        int count = the_mesh.getQuickReplyContactCount();
        if (count > 0) snprintf(out, out_len, "Контакты: %d", count);
        else snprintf(out, out_len, "Контакты: нет");
      } else {
        snprintf(out, out_len, "Назад");
      }
      return;
    }

    if (idx == _quick_target_cursor && quickTargetIdentityMatchesCursor()) {
      snprintf(out, out_len, "%s", _quick_target_identity_label);
      return;
    }
    uint16_t item_count = quickTargetItemCount();
    if (idx >= item_count) {
      snprintf(out, out_len, "%s", "Назад");
      return;
    }
    if (_quick_target_mode == QR_TARGET_CHANNEL) {
      uint8_t channel_idx = 0;
      ChannelDetails channel;
      if (the_mesh.getQuickReplyChannel(idx, channel_idx, channel)) snprintf(out, out_len, "%s", channel.name);
      return;
    }
    if (_quick_target_mode == QR_TARGET_CONTACT) {
      ContactInfo contact;
      if (the_mesh.getQuickReplyContact(idx, contact)) snprintf(out, out_len, "%s", contact.name);
    }
  }

  bool finishQuickKeyboardSend(bool sent) {
    if (sent) {
      _quick_last_target_mode = _quick_target_mode;
      _quick_last_target_cursor = _quick_target_cursor;
      _quick_target_mode = QR_TARGET_CLOSED;
      clearQuickTargetIdentity();
      _quick_keyboard_open = false;
      _quick_reply_open = false;
      _quick_keyboard_text[0] = 0;
      _task->notify(UIEventType::ack);
      _task->showAlert("Отправлено", 900);
    } else {
      _task->showAlert("Ошибка отправки", 1000);
    }
    return true;
  }

  bool selectQuickTarget() {
    if (_quick_target_mode == QR_TARGET_KIND) {
      if (_quick_target_cursor == 0) {
        if (the_mesh.getQuickReplyChannelCount() <= 0) {
          _task->showAlert("Нет чатов", 900);
        } else {
          _quick_target_mode = QR_TARGET_CHANNEL;
          uint16_t count = (uint16_t)the_mesh.getQuickReplyChannelCount();
          _quick_target_cursor = _quick_last_target_mode == QR_TARGET_CHANNEL && _quick_last_target_cursor < count
                                   ? _quick_last_target_cursor : 0;
          captureQuickTargetIdentity();
        }
        return true;
      }
      if (_quick_target_cursor == 1) {
        if (the_mesh.getQuickReplyContactCount() <= 0) {
          _task->showAlert("Нет контактов", 900);
        } else {
          _quick_target_mode = QR_TARGET_CONTACT;
          uint16_t count = (uint16_t)the_mesh.getQuickReplyContactCount();
          _quick_target_cursor = _quick_last_target_mode == QR_TARGET_CONTACT && _quick_last_target_cursor < count
                                   ? _quick_last_target_cursor : 0;
          captureQuickTargetIdentity();
        }
        return true;
      }
      _quick_target_mode = QR_TARGET_CLOSED;
      _quick_target_cursor = 0;
      clearQuickTargetIdentity();
      return true;
    }

    uint16_t item_count = quickTargetItemCount();
    if (_quick_target_cursor >= item_count && !quickTargetIdentityMatchesCursor()) {
      _quick_target_mode = QR_TARGET_KIND;
      _quick_target_cursor = 0;
      clearQuickTargetIdentity();
      return true;
    }

    // Do not resolve the mutable list ordinal again here: the visible choice
    // was snapshotted when the cursor entered this row.  If that target was
    // deleted meanwhile, the stable backend API rejects it safely.
    if ((_quick_target_mode == QR_TARGET_CHANNEL || _quick_target_mode == QR_TARGET_CONTACT) &&
        !quickTargetIdentityMatchesCursor()) {
      _task->showAlert("Цель изменилась", 1100);
      return true;
    }
    if (_quick_target_mode == QR_TARGET_CHANNEL) {
      return finishQuickKeyboardSend(
          the_mesh.sendQuickReplyToChannelId(_quick_target_channel_id, _quick_keyboard_text));
    }
    if (_quick_target_mode == QR_TARGET_CONTACT) {
      return finishQuickKeyboardSend(
          the_mesh.sendQuickReplyToContactPubKey(_quick_target_contact_pubkey, _quick_keyboard_text));
    }
    return true;
  }

  bool handleQuickTargetInput(char c) {
    uint16_t total = quickTargetTotalCount();
    if (total == 0) {
      _quick_target_mode = QR_TARGET_CLOSED;
      _quick_target_cursor = 0;
      clearQuickTargetIdentity();
      return true;
    }
    if (_quick_target_cursor >= total) _quick_target_cursor = 0;
    if (c == KEY_LEFT || c == KEY_PREV) {
      _quick_target_cursor = (_quick_target_cursor + total - 1) % total;
      if (_quick_target_cursor < quickTargetItemCount()) captureQuickTargetIdentity();
      else clearQuickTargetIdentity();
      return true;
    }
    if (c == KEY_NEXT || c == KEY_RIGHT) {
      _quick_target_cursor = (_quick_target_cursor + 1) % total;
      if (_quick_target_cursor < quickTargetItemCount()) captureQuickTargetIdentity();
      else clearQuickTargetIdentity();
      return true;
    }
    if (c == KEY_ENTER || c == KEY_SELECT) {
      return selectQuickTarget();
    }
    return true;
  }

  bool selectQuickKeyboardKey() {
    const QuickReplyKeyboardKey& key = currentQuickKeyboardKey();
    switch (key.action) {
      case QR_KB_TEXT:
        if (!appendQuickKeyboardText(key.label)) _task->showAlert("Текст заполнен", 800);
        return true;
      case QR_KB_SPACE:
        if (!appendQuickKeyboardText(" ")) _task->showAlert("Текст заполнен", 800);
        return true;
      case QR_KB_DELETE:
        deleteQuickKeyboardChar();
        return true;
      case QR_KB_PAGE:
        if (key.page < quick_reply_keyboard_page_count) {
          _quick_keyboard_page = key.page;
          _quick_keyboard_cursor = 0;
        }
        return true;
      case QR_KB_BACK:
        _quick_keyboard_open = false;
        _quick_reply_idx = quickReplyKeyboardIndex();
        _task->showAlert("К ответам", 800);
        return true;
      case QR_KB_SEND:
        if (_quick_keyboard_text[0] == 0) {
          _task->showAlert("Пустое сообщение", 800);
          return true;
        }
        _quick_target_mode = QR_TARGET_KIND;
        _quick_target_cursor = 0;
        clearQuickTargetIdentity();
        _task->showAlert("Куда?", 600);
        return true;
#if 0
        if (the_mesh.sendQuickReply(_quick_keyboard_text)) {
          _quick_keyboard_open = false;
          _quick_reply_open = false;
          _quick_keyboard_text[0] = 0;
          _task->notify(UIEventType::ack);
          _task->showAlert("Отправлено", 900);
        } else {
          _task->showAlert("Err", 1000);
        }
#endif
        return true;
      default:
        return true;
    }
  }

  bool handleQuickKeyboardInput(char c) {
    if (!_quick_keyboard_open) return false;
    if (_quick_target_mode != QR_TARGET_CLOSED) {
      return handleQuickTargetInput(c);
    }
    if (c == KEY_LEFT || c == KEY_PREV) {
      _quick_keyboard_cursor = (_quick_keyboard_cursor + QR_KB_KEYS - 1) % QR_KB_KEYS;
      return true;
    }
    if (c == KEY_NEXT || c == KEY_RIGHT) {
      _quick_keyboard_cursor = (_quick_keyboard_cursor + 1) % QR_KB_KEYS;
      return true;
    }
    if (c == KEY_ENTER || c == KEY_SELECT) {
      return selectQuickKeyboardKey();
    }
    return true;
  }

  void drawQuickKeyboardKey(DisplayDriver& display, const QuickReplyKeyboardKey& key,
                            int x, int y, int w, int h, int text_y) {
    int cx = x + w / 2;
    int cy = y + h / 2;
    if (key.action == QR_KB_SPACE) {
      int bar_w = w > 20 ? 10 : 7;
      display.fillRect(cx - bar_w / 2, cy + 2, bar_w, 1);
      return;
    }
    if (key.action == QR_KB_DELETE) {
      display.fillRect(cx - 4, cy, 9, 1);
      display.fillRect(cx - 4, cy - 1, 1, 3);
      display.fillRect(cx - 3, cy - 2, 1, 1);
      display.fillRect(cx - 3, cy + 2, 1, 1);
      return;
    }
    if (key.action == QR_KB_BACK) {
      for (int d = -3; d <= 3; d++) {
        display.fillRect(cx + d, cy + d, 1, 1);
        display.fillRect(cx + d, cy - d, 1, 1);
      }
      return;
    }
    drawRichTextCentered(display, cx, text_y, key.label);
  }

  void renderQuickTargetPicker(DisplayDriver& display) {
#if UI_T096_PREMIUM_TFT || UI_NATIVE_TFT_PROFILE
    uint8_t saved_font = uiPushCompactSettingsFont(display);
#else
    display.setTextSize(1);
    display.setBold(false);
#endif

    const int w = display.width();
    const int h = display.height();
#if UI_T096_PREMIUM_TFT
    const int line_h = display.getTextLineHeight();
    const int header_h = line_h + 2;
    const int list_y = header_h;
    const int row_h = line_h;
    const int title_y = (header_h - line_h) / 2;
    const int row_text_y = 0;
#elif UI_NATIVE_TFT_PROFILE
    const int line_h = display.getTextLineHeight();
    const int header_h = line_h + 2;
    const int list_y = header_h;
    const int row_h = (h - list_y) / 4;
    const int title_y = (header_h - line_h) / 2;
    const int row_text_y = row_h > line_h ? (row_h - line_h) / 2 : 0;
#else
    const int header_h = 14;
    const int list_y = header_h + 2;
    const int row_h = h <= 64 ? 12 : 14;
    const int title_y = 2;
    const int row_text_y = 2;
#endif
    int visible = (h - list_y) / row_h;
    if (visible < 1) visible = 1;

    uint16_t total = quickTargetTotalCount();
    if (quickTargetIdentityMatchesCursor()) {
      // Keep the snapshotted row visible even if the live list was compacted.
      // SEND will revalidate the immutable ID instead of silently retargeting.
      if (total <= _quick_target_cursor) total = _quick_target_cursor + 2;
    } else {
      if (_quick_target_cursor >= total && total > 0) _quick_target_cursor = 0;
      if ((_quick_target_mode == QR_TARGET_CHANNEL || _quick_target_mode == QR_TARGET_CONTACT) &&
          _quick_target_cursor < quickTargetItemCount()) {
        captureQuickTargetIdentity();
      }
    }
    uint16_t offset = 0;
    if (total > (uint16_t)visible && _quick_target_cursor >= (uint16_t)visible) {
      offset = _quick_target_cursor - visible + 1;
    }

    display.setColor(DisplayDriver::BLUE);
    display.drawRect(0, 0, w - 1, header_h);
    display.setColor(DisplayDriver::LIGHT);
    drawRichTextCenteredEllipsized(display, w / 2, title_y, w - 4, quickTargetTitle());

    for (int row = 0; row < visible; row++) {
      uint16_t idx = offset + row;
      if (idx >= total) break;
      int y = list_y + row * row_h;
      bool selected = idx == _quick_target_cursor;
      uint16_t item_count = quickTargetItemCount();
      bool back = (_quick_target_mode != QR_TARGET_KIND && idx >= item_count &&
                   !(selected && quickTargetIdentityMatchesCursor())) ||
                  (_quick_target_mode == QR_TARGET_KIND && idx == 2);
      char label[36];
      quickTargetLabel(idx, label, sizeof(label));

      if (selected) {
        display.setColor(back ? DisplayDriver::YELLOW : DisplayDriver::GREEN);
        display.fillRect(0, y, w, row_h);
        display.setColor(DisplayDriver::DARK);
        display.setBold(true);
      } else {
        display.setColor(back ? DisplayDriver::YELLOW : DisplayDriver::LIGHT);
        display.setBold(false);
      }
      int text_right_guard = total > (uint16_t)visible ? 7 : 3;
      drawRichTextStaticEllipsized(display, 3, y + row_text_y, w - 3 - text_right_guard,
                                   label[0] ? label : "?");
      display.setBold(false);
    }

    if (total > (uint16_t)visible) {
      int track_x = w - 2;
      int track_y = list_y;
      int track_h = visible * row_h;
      int thumb_h = (track_h * visible) / total;
      if (thumb_h < 4) thumb_h = 4;
      int max_offset = total - visible;
      int thumb_y = track_y;
      if (max_offset > 0) thumb_y += ((track_h - thumb_h) * offset) / max_offset;
      display.setColor(DisplayDriver::LIGHT);
      display.drawRect(track_x, track_y, 2, track_h);
      display.setColor(DisplayDriver::YELLOW);
      display.fillRect(track_x, thumb_y, 2, thumb_h);
    }
#if UI_T096_PREMIUM_TFT || UI_NATIVE_TFT_PROFILE
    uiPopFont(display, saved_font);
#endif
  }

  void renderQuickKeyboard(DisplayDriver& display) {
    if (_quick_target_mode != QR_TARGET_CLOSED) {
      renderQuickTargetPicker(display);
      return;
    }

#if UI_T096_PREMIUM_TFT || UI_NATIVE_TFT_PROFILE
    uint8_t saved_font = uiPushCompactSettingsFont(display);
#else
    display.setTextSize(1);
    display.setBold(false);
#endif

    const int w = display.width();
    const int h = display.height();
#if UI_T096_PREMIUM_TFT
    const int line_h = display.getTextLineHeight();
    const int preview_h = line_h + 2;
    const int grid_y = preview_h;
    const int preview_text_y = (preview_h - line_h) / 2;
#elif UI_NATIVE_TFT_PROFILE
    const int line_h = display.getTextLineHeight();
    const int preview_h = line_h + 2;
    const int grid_y = preview_h;
    const int preview_text_y = (preview_h - line_h) / 2;
#else
    const int line_h = 8;
    const int preview_h = 14;
    const int grid_y = preview_h + 2;
    const int preview_text_y = 2;
#endif
    const int cell_w = w / QR_KB_COLS;
    int cell_h = (h - grid_y) / QR_KB_ROWS;
    if (cell_h < 10) cell_h = 10;

    display.setColor(DisplayDriver::BLUE);
    display.drawRect(0, 0, w - 1, preview_h);
    display.setColor(DisplayDriver::LIGHT);
    drawRichTextTailEllipsized(display, 3, preview_text_y, w - 6, _quick_keyboard_text, true);

    for (uint8_t row = 0; row < QR_KB_ROWS; row++) {
      for (uint8_t col = 0; col < QR_KB_COLS; col++) {
        uint8_t index = row * QR_KB_COLS + col;
        const QuickReplyKeyboardKey& key = quick_reply_keyboard_pages[_quick_keyboard_page][index];
        int x = col * cell_w;
        int y = grid_y + row * cell_h;
        int key_w = (col == QR_KB_COLS - 1) ? (w - x) : cell_w;
        int key_h = row == QR_KB_ROWS - 1 ? (h - y) : cell_h;
        int text_y = y + (key_h > line_h ? (key_h - line_h) / 2 : 0);
        if (text_y + line_h > h) text_y = h - line_h;
        if (text_y < y) text_y = y;
        bool selected = index == _quick_keyboard_cursor;
        bool service = key.action != QR_KB_TEXT;

        if (selected) {
          display.setColor(key.action == QR_KB_SEND ? DisplayDriver::GREEN : DisplayDriver::YELLOW);
          display.fillRect(x, y, key_w, key_h);
          display.setColor(DisplayDriver::DARK);
          display.setBold(true);
        } else {
          display.setColor(service ? DisplayDriver::YELLOW : DisplayDriver::LIGHT);
          display.setBold(false);
        }

        drawQuickKeyboardKey(display, key, x, y, key_w, key_h, text_y);
        display.setBold(false);
      }
    }
#if UI_T096_PREMIUM_TFT || UI_NATIVE_TFT_PROFILE
    uiPopFont(display, saved_font);
#endif
  }
#endif

  void refresh_sensors() {
    if (smartui::deadlineDueOrImmediate((uint32_t)millis(),
                                        (uint32_t)next_sensors_refresh)) {
      sensors_lpp.reset();
      sensors_nb = 0;
      sensors_lpp.addVoltage(TELEM_CHANNEL_SELF, (float)_task->getBattMilliVolts() / 1000.0f);
      sensors.querySensors(0xFF, sensors_lpp);
      LPPReader reader (sensors_lpp.getBuffer(), sensors_lpp.getSize());
      uint8_t channel, type;
      while(reader.readHeader(channel, type)) {
        reader.skipData(type);
        sensors_nb ++;
      }
      sensors_scroll = sensors_nb > UI_RECENT_LIST_SIZE;
#if AUTO_OFF_MILLIS > 0
      next_sensors_refresh = millis() + 5000; // refresh sensor values every 5 sec
#else
      next_sensors_refresh = millis() + 60000; // refresh sensor values every 1 min
#endif
    }
  }

public:
  HomeScreen(UITask* task, mesh::RTCClock* rtc, SensorManager* sensors, NodePrefs* node_prefs)
     : _task(task), _rtc(rtc), _sensors(sensors), _node_prefs(node_prefs), _page(defaultHomePage()),
       _settings_open(false), _quick_reply_open(false), _quick_reply_idx(0),
       _chat_scroll_px(0), _chat_scroll_dir(-1), _chat_pause_until(0), _chat_latest_ts(0),
       _chat_layout_ts(0), _chat_layout_width(0), _chat_layout_total_h(0), _chat_layout_count(0),
       _chat_layout_font(0xFF), _chat_layout_valid(false), _shutdown_init(false),
#if UI_ADC_MULTIPLIER_PAGE == 1
       _adc_edit(false), _adc_draft(0.0f),
#endif
       sensors_lpp(200) {
        for (int i = 0; i < UI_CHAT_LIST_SIZE; i++) _chat_item_h[i] = 0;
#if UI_QUICK_REPLY_KEYBOARD
        resetQuickKeyboard();
#endif
#if UI_COMPACT_SETTINGS_MENU == 1
        _compact_settings_depth = 0;
        _compact_settings_group = 0;
        _compact_settings_cursor = 0;
#if UI_TIMEZONE_PAGE == 1
        _timezone_picker_cursor = 0;
#endif
#if UI_APPEARANCE_MENU
        _font_picker_cursor = 0;
        _theme_picker_cursor = 0;
#endif
#if UI_SMART_B12_TONE_LIST == 1 && defined(PIN_MSG_TONE)
        _tone_picker_cursor = 0;
#endif
#if UI_SMART_B11_EXTRAS == 1
        _compact_undo_valid = false;
        _hardware_test_step = 0;
        memset(&_compact_undo_prefs, 0, sizeof(_compact_undo_prefs));
#endif
#endif
       }

  void resetToFirstPage() {
#if UI_ADC_MULTIPLIER_PAGE == 1
    cancelAdcEdit();
#endif
    _page = defaultHomePage();
    _settings_open = false;
    _quick_reply_open = false;
    _quick_reply_idx = 0;
#if UI_QUICK_REPLY_KEYBOARD
    resetQuickKeyboard();
#endif
#if UI_COMPACT_SETTINGS_MENU == 1
    _compact_settings_depth = 0;
    _compact_settings_group = 0;
    _compact_settings_cursor = 0;
    _notify_picker.reset();
#if UI_TIMEZONE_PAGE == 1
    _timezone_picker_cursor = 0;
#endif
#if UI_APPEARANCE_MENU
    _font_picker_cursor = 0;
    _theme_picker_cursor = 0;
#endif
#if UI_SMART_B12_TONE_LIST == 1 && defined(PIN_MSG_TONE)
    _tone_picker_cursor = 0;
#endif
#if UI_SMART_B11_EXTRAS == 1
    _hardware_test_step = 0;
#endif
#endif
    _chat_scroll_px = 0;
    _chat_scroll_dir = -1;
    _chat_pause_until = 0;
    _chat_latest_ts = 0;
    _chat_layout_valid = false;
    _chat_layout_total_h = 0;
    for (int i = 0; i < UI_CHAT_LIST_SIZE; i++) _chat_item_h[i] = 0;
    _shutdown_init = false;
#if UI_ADC_MULTIPLIER_PAGE == 1
    _adc_edit = false;
    _adc_draft = 0.0f;
#endif
  }

  void readGpsUiState(bool& enabled, bool& valid, int& sats) const {
    enabled = false;
    valid = false;
    sats = -1;
#if ENV_INCLUDE_GPS == 1 || UI_PHONE_GPS == 1
#if UI_PHONE_GPS == 1
    if (the_mesh.isPhoneGpsEnabled()) {
      enabled = true;
      valid = the_mesh.isPhoneGpsFresh();
      return;
    }
#endif
    enabled = _task->getGPSState();
    if (enabled) {
      LocationProvider* nmea = sensors.getLocationProvider();
      if (nmea != NULL) {
        valid = nmea->isValid();
        sats = nmea->satellitesCount();
      }
    }
#endif
  }

  void renderGpsStatusPictogram(DisplayDriver& display, int x, int icon_y, bool enabled, bool valid, int sats,
                                bool show_count) {
    drawUiGpsStatusIcon(display, x, icon_y, enabled, valid);
    if (!show_count || !enabled) return;

    char sat_buf[5];
    if (sats >= 0) {
      if (sats > 99) sats = 99;
      snprintf(sat_buf, sizeof(sat_buf), "%d", sats);
    } else {
      strcpy(sat_buf, "?");
    }
    display.setColor(uiGpsStatusColor(enabled, valid));
    display.setCursor(x + uiGpsStatusIconWidth(display) + 3, icon_y - 2 < 0 ? 0 : icon_y - 2);
    display.print(sat_buf);
  }

  int renderGpsClockLabel(DisplayDriver& display, int x, int y, bool enabled, bool valid, int sats,
                          bool show_count) {
    char gps_buf[16];
#if UI_PHONE_GPS == 1
    if (the_mesh.isPhoneGpsEnabled()) {
      if (the_mesh.isPhoneGpsFresh()) {
        strcpy(gps_buf, "GPS TEL");
      } else if (the_mesh.getPhoneGpsAgeSeconds() == 0xFFFFFFFFUL) {
        strcpy(gps_buf, "GPS ...");
      } else {
        strcpy(gps_buf, "GPS OLD");
      }
    } else
#endif
    if (!enabled) {
      strcpy(gps_buf, "GPS OFF");
    } else if (show_count && sats >= 0) {
      if (sats > 99) sats = 99;
      snprintf(gps_buf, sizeof(gps_buf), "GPS ON %d", sats);
    } else {
      strcpy(gps_buf, "GPS ON");
    }
    display.setColor(uiGpsStatusColor(enabled, valid));
    display.setCursor(x, y);
    display.print(gps_buf);
    return x + display.getTextWidth(gps_buf);
  }

  bool isClockPage() const {
    return !_settings_open && _page == HomePage::CLOCK;
  }

#if UI_ADC_MULTIPLIER_PAGE == 1
  bool restoreAdcDefault(uint8_t click_count) {
    if (!smartui::adcFactoryResetGesture(_settings_open, _page == HomePage::ADC,
                                         _adc_edit, click_count)) return false;
    _adc_edit = false;
    _adc_draft = 0.0f;
    if (_task->setAdcMultiplier(0.0f, true)) {
      _task->showAlert("АЦП: заводской", 1000);
    } else {
      _task->showAlert("АЦП недоступен", 1000);
    }
    return true;
  }
#else
  bool restoreAdcDefault(uint8_t) { return false; }
#endif

  bool isBlePinPage() const {
#if UI_BLE_PIN_PAGE
    return !_settings_open && _page == HomePage::BLE_PIN;
#else
    return false;
#endif
  }

  void poll() override {
    if (_shutdown_init && !_task->isButtonPressed()) {  // must wait for USR button to be released
      _task->shutdown();
    }
  }

  bool keepDisplayOn() const override {
#if UI_CHAT_KEEP_DISPLAY_ON
    return _page == HomePage::CHAT;
#else
    return false;
#endif
  }

  int render(DisplayDriver& display) override {
    char tmp[80];
    bool skip_chrome = false;
#if UI_WIRELESS_PAPER_BIG_CLOCK
    skip_chrome = _page == HomePage::CLOCK;
#endif
#if UI_T096_PREMIUM_TFT
    skip_chrome = _page == HomePage::CLOCK;
#endif
    if (_page != HomePage::CHAT && !skip_chrome) {
      uint8_t chrome_font = uiPushCompactChromeFont(display);
      int name_x = 0;
      int name_right = display.width() - 1;

      // battery voltage and right-side status group
      name_right = renderBatteryIndicator(display, _task->getBattMilliVolts(), !isClockPage()) - 2;

#if UI_NATIVE_TFT_PROFILE && defined(HELTEC_T114)
      if (isClockPage()) {
        bool gps_enabled = false;
        bool gps_valid = false;
        int gps_count = -1;
        readGpsUiState(gps_enabled, gps_valid, gps_count);
        int gps_right = renderGpsClockLabel(display, name_x, 0, gps_enabled, gps_valid, gps_count, false);
        int status_right = gps_right;
        if (_task->areNotificationsMuted()) {
          int icon_size = uiStatusIconSize(display);
          int mute_x = gps_right + 3;
          if (mute_x + icon_size <= name_right) {
            display.setColor(DisplayDriver::RED);
            drawUiIcon(display, mute_x, 1, muted_icon, icon_size);
            status_right = mute_x + icon_size;
          }
        }
        display.setColor(_task->getUiBottomColor());
        drawClockUptimeBetween(display, _task, status_right, name_right, 0);
      } else
#endif
      {
#if UI_V4_3_OLED_PROFILE
        if (isClockPage()) {
#if ENV_INCLUDE_GPS == 1 || UI_PHONE_GPS == 1
          bool gps_enabled = false;
          bool gps_valid = false;
          int gps_count = -1;
          readGpsUiState(gps_enabled, gps_valid, gps_count);
          int gps_right = renderGpsClockLabel(display, name_x, 0, gps_enabled, gps_valid, gps_count, false);
          int status_right = gps_right;
          if (_task->areNotificationsMuted()) {
            int icon_size = uiStatusIconSize(display);
            int mute_x = gps_right + 3;
            if (mute_x + icon_size <= name_right) {
              display.setColor(DisplayDriver::RED);
              drawUiIcon(display, mute_x, 1, muted_icon, icon_size);
              status_right = mute_x + icon_size;
            }
          }
          display.setColor(_task->getUiBottomColor());
          drawClockUptimeBetween(display, _task, status_right, name_right, 0);
#else
          // A GPS-less board must not advertise a permanently disabled
          // module.  Keep only the useful mute state in the clock chrome.
          int status_right = -3;
          if (_task->areNotificationsMuted()) {
            int icon_size = uiStatusIconSize(display);
            if (name_x + icon_size <= name_right) {
              display.setColor(DisplayDriver::RED);
              drawUiIcon(display, name_x, 1, muted_icon, icon_size);
              status_right = name_x + icon_size;
            }
          }
          display.setColor(_task->getUiBottomColor());
          drawClockUptimeBetween(display, _task, status_right, name_right, 0);
#endif
        } else
#endif
        {
          if (isClockPage()) {
            display.setColor(_task->getUiBottomColor());
            drawClockUptimeBetween(display, _task, -3, name_right, 0);
          } else {
            // node name
            display.setColor(_task->getUiTopColor());
            int maxNameWidth = name_right - name_x;
            if (maxNameWidth < 18) maxNameWidth = 18;
            drawRichTextEllipsized(display, name_x, 0, maxNameWidth, _node_prefs->node_name);
          }
        }
      }

      // curr page indicator
      int y = 14;
      int indicator_step = 10;
      uint8_t page_count = visiblePageCount();
      uint8_t page_index = visiblePageIndex();
      display.setColor(_task->getUiBottomColor());
      if (page_count > 1) {
        int max_step = (display.width() - 4) / (page_count - 1);
        if (max_step < indicator_step) indicator_step = max_step;
      }
      if (indicator_step < 4) indicator_step = 4;
      int x = (display.width() - indicator_step * (page_count - 1)) / 2;
      for (uint8_t i = 0; i < page_count; i++, x += indicator_step) {
        if (i == page_index) {
          display.fillRect(x-1, y-1, 3, 3);
        } else {
          display.fillRect(x, y, 1, 1);
        }
      }
      uiPopFont(display, chrome_font);
    }

    if (_page == HomePage::FIRST) {
#if UI_FIRST_PAGE_SAFE_CLOCK
      uint32_t rtc_now = _rtc->getCurrentTime();
      bool time_valid = _task->hasTrustedTime() && rtc_now >= UI_RTC_VALID_MIN;
      bool compact_clock = display.width() <= 128 && display.height() <= 64;
      int time_y = compact_clock ? 18 : (display.height() / 2) - 24;
      if (time_y < 24) time_y = 24;
      int date_y = compact_clock ? 39 : time_y + 34;
      int footer_y = display.height() - (compact_clock ? 9 : 14);

      display.setColor(time_valid ? DisplayDriver::GREEN : DisplayDriver::YELLOW);
      display.setBold(true);
      display.setTextSize(compact_clock ? 2 : 3);
      if (time_valid) {
        DateTime dt(localClockTime(rtc_now));
        snprintf(tmp, sizeof(tmp), "%02u:%02u", dt.hour(), dt.minute());
        display.drawTextCentered(display.width() / 2, time_y, tmp);

        display.setBold(false);
        display.setTextSize(1);
        snprintf(tmp, sizeof(tmp), "%02u.%02u.%04u", dt.day(), dt.month(), dt.year());
        display.drawTextCentered(display.width() / 2, date_y, tmp);
      } else {
        display.drawTextCentered(display.width() / 2, time_y, "--:--");

        display.setBold(false);
        display.setTextSize(1);
        snprintf(tmp, sizeof(tmp), "синхр. время");
        display.drawTextCentered(display.width() / 2, date_y, tmp);
      }

      display.setBold(false);
      display.setTextSize(1);
      display.setColor(DisplayDriver::LIGHT);
#if UI_FIRST_PAGE_SHOW_MCU_TEMP
      float mcu_temp = _task->getMCUTemperature();
      if (!isnan(mcu_temp) && mcu_temp > -80.0f && mcu_temp < 180.0f) {
#if UI_MCU_TEMP_DECIMALS > 0
        snprintf(tmp, sizeof(tmp), "%.*fC", UI_MCU_TEMP_DECIMALS, mcu_temp);
#else
        snprintf(tmp, sizeof(tmp), "%.0fC", mcu_temp);
#endif
        display.drawTextRightAlign(display.width() - 1, footer_y, tmp);
      }
#endif
      snprintf(tmp, sizeof(tmp), "Msg %d", _task->getMsgCount());
      display.setCursor(0, footer_y);
      display.print(tmp);
      if (_task->hasConnection()) {
        display.setColor(DisplayDriver::GREEN);
        display.drawTextCentered(display.width() / 2, footer_y, "BLE");
      }
#else
#if UI_V4_3_OLED_PROFILE
#if UI_T096_PREMIUM_TFT
      if (false) {
#else
      if (!_task->hasConnection() && the_mesh.getBLEPin() != 0) {
#endif
        display.setColor(DisplayDriver::YELLOW);
        uint8_t small_font = uiPushCompactChromeFont(display);
        drawRichTextCentered(display, display.width() / 2, 21, "ПИНКОД BLE");
        uiPopFont(display, small_font);

        uint8_t hero_font = uiPushOledRoleFont(display, UI_OLED_FONT_L);
        sprintf(tmp, "%d", the_mesh.getBLEPin());
        drawRichTextCentered(display, display.width() / 2, 36, tmp);
        uiPopFont(display, hero_font);
      } else {
        display.setColor(DisplayDriver::YELLOW);
        uint8_t hero_font = uiPushOledRoleFont(display, UI_OLED_FONT_L);
        sprintf(tmp, "Сообщ: %d", _task->getMsgCount());
        drawRichTextCentered(display, display.width() / 2, 28, tmp);
        uiPopFont(display, hero_font);

        #ifdef WIFI_SSID
          IPAddress ip = WiFi.localIP();
          snprintf(tmp, sizeof(tmp), "IP: %d.%d.%d.%d", ip[0], ip[1], ip[2], ip[3]);
          uint8_t small_font = uiPushCompactChromeFont(display);
          display.setColor(DisplayDriver::LIGHT);
          drawRichTextCentered(display, display.width() / 2, 52, tmp);
          uiPopFont(display, small_font);
        #endif
      }
      if (_task->hasConnection()) {
        uint8_t small_font = uiPushCompactChromeFont(display);
        display.setColor(DisplayDriver::GREEN);
        drawRichTextCentered(display, display.width() / 2, 52, "< Связь есть >");
        uiPopFont(display, small_font);
      }
#else
      if (!_task->hasConnection() && the_mesh.getBLEPin() != 0) {
        display.setColor(DisplayDriver::YELLOW);
        display.setTextSize(1);
        display.drawTextCentered(display.width() / 2, 22, "ПИНКОД ОТ БЛЮТУС");
        display.setTextSize(2);
        sprintf(tmp, "%d", the_mesh.getBLEPin());
        display.drawTextCentered(display.width() / 2, 37, tmp);
      } else {
        display.setColor(DisplayDriver::YELLOW);
        display.setTextSize(2);
        sprintf(tmp, "Сообщ: %d", _task->getMsgCount());
        display.drawTextCentered(display.width() / 2, 20, tmp);

        #ifdef WIFI_SSID
          IPAddress ip = WiFi.localIP();
          snprintf(tmp, sizeof(tmp), "IP: %d.%d.%d.%d", ip[0], ip[1], ip[2], ip[3]);
          display.setTextSize(1);
          display.drawTextCentered(display.width() / 2, 54, tmp);
        #endif
      }
      if (_task->hasConnection()) {
        display.setColor(DisplayDriver::GREEN);
        display.setTextSize(1);
        display.drawTextCentered(display.width() / 2, 43, "< Связь есть >");
      }
#endif
#endif
    } else if (_page == HomePage::CLOCK) {
#if UI_T096_PREMIUM_TFT
      UIHourlyStatsSnapshot stats;
      _task->getHourlyStats(stats);

      uint32_t elapsed_ms = stats.elapsed_ms;
      if (elapsed_ms < 1000) elapsed_ms = 1000;
      uint32_t busy_ms = stats.busy_ms;
      uint64_t known_air_ms = (uint64_t)stats.tx_air_ms + stats.rx_air_ms;
      if ((uint64_t)busy_ms < known_air_ms) {
        busy_ms = known_air_ms > 0xFFFFFFFFULL ? 0xFFFFFFFFUL : (uint32_t)known_air_ms;
      }
      uint32_t util10 = (uint32_t)(((uint64_t)busy_ms * 1000ULL + elapsed_ms / 2) / elapsed_ms);
      if (util10 > 999) util10 = 999;
      uint32_t air100 = (uint32_t)(((uint64_t)stats.tx_air_ms * 10000ULL + elapsed_ms / 2) / elapsed_ms);
      if (air100 > 9999) air100 = 9999;

      char ch_pct[8];
      char air_pct[9];
      formatPercentTenths(ch_pct, sizeof(ch_pct), util10);
      formatPercentHundredths(air_pct, sizeof(air_pct), air100);

      ColorVal util_color = util10 >= 500 ? DisplayDriver::RED :
                                        util10 >= 200 ? DisplayDriver::YELLOW :
                                                        DisplayDriver::GREEN;
      ColorVal air_color = air100 >= 2000 ? DisplayDriver::RED :
                                       air100 >= 500 ? DisplayDriver::YELLOW :
                                                       DisplayDriver::GREEN;
      ColorVal load_color = (util_color == DisplayDriver::RED || air_color == DisplayDriver::RED) ? DisplayDriver::RED :
                                        (util_color == DisplayDriver::YELLOW || air_color == DisplayDriver::YELLOW) ? DisplayDriver::YELLOW :
                                                                                                                     DisplayDriver::GREEN;

      bool gps_enabled = false;
      bool gps_valid = false;
      int sats = -1;
      readGpsUiState(gps_enabled, gps_valid, sats);

      float mcu_temp = _task->getMCUTemperature();
      bool has_mcu_temp = !isnan(mcu_temp) && mcu_temp > -80.0f && mcu_temp < 180.0f;
      char temp_text[12];
      if (has_mcu_temp) {
#if UI_MCU_TEMP_DECIMALS > 0
        snprintf(temp_text, sizeof(temp_text), "%.*fC", UI_MCU_TEMP_DECIMALS, mcu_temp);
#else
        snprintf(temp_text, sizeof(temp_text), "%.0fC", mcu_temp);
#endif
      } else {
        strcpy(temp_text, "--C");
      }

      uint8_t small_font = uiPushCompactChromeFont(display);
      display.setBold(false);
      int battery_left = renderBatteryIndicator(display, _task->getBattMilliVolts());
      bool clock_muted = _task->areNotificationsMuted();
      // Satellite count is secondary.  On the widest T096 font it would leave
      // no safe room for the mute icon, so keep the explicit GPS ON state and
      // hide only the count while quiet mode is active.
      int gps_right = renderGpsClockLabel(display, 1, 1, gps_enabled, gps_valid, sats, !clock_muted);
      int status_right = gps_right;

      if (clock_muted) {
        const int mute_size = 16;
        int mute_x = gps_right + 4;
        if (mute_x + mute_size <= battery_left - 3) {
          display.setColor(DisplayDriver::RED);
          drawUiIcon(display, mute_x, 1, muted_icon, mute_size);
          status_right = mute_x + mute_size;
        }
      }
      display.setColor(_task->getUiBottomColor());
      drawClockUptimeBetween(display, _task, status_right, battery_left, 1);
      uiPopFont(display, small_font);

      uint32_t rtc_now = _rtc->getCurrentTime();
      bool time_valid = _task->hasTrustedTime() && rtc_now >= UI_RTC_VALID_MIN;
      DateTime dt(time_valid ? localClockTime(rtc_now) : 0);
      display.setColor(time_valid ? _task->getUiTopColor() : DisplayDriver::YELLOW);
      uint8_t clock_font = uiPushOledRoleFont(display, UI_OLED_FONT_L);
      display.setBold(true);
      if (time_valid) {
        snprintf(tmp, sizeof(tmp), "%02u:%02u", dt.hour(), dt.minute());
      } else {
        strcpy(tmp, "--:--");
      }
      drawRichTextCentered(display, display.width() / 2, 17, tmp);
      display.setBold(false);
      uiPopFont(display, clock_font);

      uint8_t detail_font = uiPushCompactChromeFont(display);
      display.setColor(_task->getUiBottomColor());
      if (time_valid) {
        snprintf(tmp, sizeof(tmp), "%02u.%02u.%04u", dt.day(), dt.month(), dt.year());
      } else {
        strcpy(tmp, "нет времени");
      }
      drawRichTextCenteredEllipsized(display, display.width() / 2, 43, display.width(), tmp);
#if UI_SMART_B11_EXTRAS == 1
      if (_task->getMsgCount() > 0) {
        display.setColor(DisplayDriver::RED);
        snprintf(tmp, sizeof(tmp), "Н:%d", _task->getMsgCount());
        drawRichTextEllipsized(display, 1, 43, 38, tmp);
      }
#endif

      const int block_y = 60;
      const int block_h = 19;
      const int load_block_w = 117;
      const int temp_block_x = 120;
      const int temp_block_w = 40;
      display.setColor(load_color);
      display.drawRect(0, block_y, load_block_w, block_h);
      display.fillRect(0, block_y, 3, block_h);
      display.setColor(_task->getUiBottomColor());
      snprintf(tmp, sizeof(tmp), "CH%s AIR%s", ch_pct, air_pct);
      drawRichTextEllipsized(display, 5, block_y + 2, load_block_w - 7, tmp);

      display.setColor(has_mcu_temp ? DisplayDriver::GREEN : DisplayDriver::YELLOW);
      display.drawRect(temp_block_x, block_y, temp_block_w, block_h);
      display.fillRect(temp_block_x, block_y, 3, block_h);
      display.setColor(_task->getUiBottomColor());
      drawRichTextCenteredEllipsized(display, temp_block_x + temp_block_w / 2, block_y + 2, temp_block_w - 5, temp_text);
      uiPopFont(display, detail_font);
#else
      UIHourlyStatsSnapshot stats;
      _task->getHourlyStats(stats);

      uint32_t elapsed_ms = stats.elapsed_ms;
      if (elapsed_ms < 1000) elapsed_ms = 1000;
      uint32_t busy_ms = stats.busy_ms;
      uint64_t known_air_ms = (uint64_t)stats.tx_air_ms + stats.rx_air_ms;
      if ((uint64_t)busy_ms < known_air_ms) {
        busy_ms = known_air_ms > 0xFFFFFFFFULL ? 0xFFFFFFFFUL : (uint32_t)known_air_ms;
      }
      uint32_t util10 = (uint32_t)(((uint64_t)busy_ms * 1000ULL + elapsed_ms / 2) / elapsed_ms);
      if (util10 > 999) util10 = 999;
      uint32_t air100 = (uint32_t)(((uint64_t)stats.tx_air_ms * 10000ULL + elapsed_ms / 2) / elapsed_ms);
      if (air100 > 9999) air100 = 9999;

      char ch_pct[8];
      char air_pct[9];
      char msg_hour[8];
      formatPercentTenths(ch_pct, sizeof(ch_pct), util10);
      formatPercentHundredths(air_pct, sizeof(air_pct), air100);
      if (stats.msg_count > 999) {
        snprintf(msg_hour, sizeof(msg_hour), "999+");
      } else {
        snprintf(msg_hour, sizeof(msg_hour), "%u", stats.msg_count);
      }
      float mcu_temp = _task->getMCUTemperature();
      bool has_mcu_temp = !isnan(mcu_temp) && mcu_temp > -80.0f && mcu_temp < 180.0f;
      char temp_text[12];
      temp_text[0] = 0;
      if (has_mcu_temp) {
#if UI_MCU_TEMP_DECIMALS > 0
        snprintf(temp_text, sizeof(temp_text), "%.*fC", UI_MCU_TEMP_DECIMALS, mcu_temp);
#else
        snprintf(temp_text, sizeof(temp_text), "%.0fC", mcu_temp);
#endif
      }

#if UI_WIRELESS_PAPER_BIG_CLOCK
      if (display.width() > 200) {
        uint32_t rtc_now = _rtc->getCurrentTime();
        bool time_valid = _task->hasTrustedTime() && rtc_now >= UI_RTC_VALID_MIN;
        DateTime dt(time_valid ? localClockTime(rtc_now) : 0);

        display.setTextSize(1);
        display.setBold(false);
        display.setColor(DisplayDriver::LIGHT);
        int battery_left = renderBatteryIndicator(display, _task->getBattMilliVolts());
        const int node_right = display.width() / 2;
        drawRichTextEllipsized(display, 4, 4, node_right - 8, _node_prefs->node_name);
        display.setColor(_task->getUiBottomColor());
        drawClockUptimeBetween(display, _task, node_right, battery_left, 4);

        display.setTextSize(4);
        display.setBold(true);
        display.setColor(time_valid ? DisplayDriver::GREEN : DisplayDriver::YELLOW);
        if (time_valid) {
          snprintf(tmp, sizeof(tmp), "%02u:%02u", dt.hour(), dt.minute());
        } else {
          strcpy(tmp, "--:--");
        }
        display.drawTextCentered(display.width() / 2, 25, tmp);

        display.setBold(false);
        display.setTextSize(2);
        if (time_valid) {
          snprintf(tmp, sizeof(tmp), "%02u.%02u.%04u", dt.day(), dt.month(), dt.year());
        } else {
          strcpy(tmp, "нет времени");
        }
        display.drawTextCentered(display.width() / 2, 61, tmp);

        display.setTextSize(1);
        display.setColor(DisplayDriver::LIGHT);
        snprintf(tmp, sizeof(tmp), "ChUtil %s  Air %s", ch_pct, air_pct);
        display.drawTextCentered(display.width() / 2, 86, tmp);

        int sats = -1;
#if ENV_INCLUDE_GPS == 1 || UI_PHONE_GPS == 1
        if (_task->getGPSState()) {
          LocationProvider* nmea = sensors.getLocationProvider();
          if (nmea != NULL) sats = nmea->satellitesCount();
        }
#endif
        snprintf(tmp, sizeof(tmp), "Msg/h %s", msg_hour);
        display.drawTextCentered(display.width() / 2, 101, tmp);
        if (has_mcu_temp) {
          display.drawTextRightAlign(display.width() - 4, 101, temp_text);
        }
        if (sats >= 0) {
          char sat_buf[5];
          if (sats > 99) sats = 99;
          snprintf(sat_buf, sizeof(sat_buf), "%d", sats);
          int sat_text_w = display.getTextWidth(sat_buf);
          int sat_right_x = has_mcu_temp ? display.width() - display.getTextWidth(temp_text) - 10 : display.width() - 4;
          int sat_icon_x = sat_right_x - sat_text_w - uiLineIconAdvance(display, satellite_icon);
          drawUiLineIcon(display, sat_icon_x, 101, satellite_icon);
          display.drawTextRightAlign(sat_right_x, 101, sat_buf);
        }
      } else {
#endif
      bool compact_clock = display.width() <= 128 && display.height() <= 64;
      int time_y = compact_clock ? 17 : 18;
      int date_y = compact_clock ? 34 : 38;
      int stats_y = compact_clock ? 45 : 48;
      int detail_y = compact_clock ? 54 : 58;
#if UI_V4_3_OLED_PROFILE
      if (compact_clock) {
        time_y = 18;
        date_y = 34;
        stats_y = 45;
        detail_y = 55;
      }
#endif
      bool show_clock_date = true;
#if UI_V4_3_OLED_PROFILE
      if (compact_clock) show_clock_date = false;
#elif UI_NATIVE_TFT_PROFILE
      if (compact_clock && display.getTextLineHeight() >= 13) show_clock_date = false;
#endif

      uint32_t rtc_now = _rtc->getCurrentTime();
      bool time_valid = _task->hasTrustedTime() && rtc_now >= UI_RTC_VALID_MIN;
      display.setColor(time_valid ? DisplayDriver::GREEN : DisplayDriver::YELLOW);
#if UI_V4_3_OLED_PROFILE
      uint8_t clock_hero_font = uiPushOledRoleFont(display, UI_OLED_FONT_L);
      if (compact_clock) display.setTextSize(3);
#else
      display.setTextSize(2);
#endif
#if UI_V4_3_OLED_PROFILE
      uint8_t clock_small_font = clock_hero_font;
#endif
      int clock_text_width = 0;
      if (time_valid) {
        DateTime dt(localClockTime(rtc_now));
        snprintf(tmp, sizeof(tmp), "%02u:%02u", dt.hour(), dt.minute());
        clock_text_width = display.getTextWidth(tmp);
        display.drawTextCentered(display.width() / 2, time_y, tmp);
#if UI_V4_3_OLED_PROFILE
        uiPopFont(display, clock_hero_font);
        clock_small_font = uiPushCompactChromeFont(display);
#endif
        if (show_clock_date) {
          display.setTextSize(1);
          snprintf(tmp, sizeof(tmp), "%02u.%02u.%04u", dt.day(), dt.month(), dt.year());
          display.drawTextCentered(display.width() / 2, date_y, tmp);
        }
      } else {
        clock_text_width = display.getTextWidth("--:--");
        display.drawTextCentered(display.width() / 2, time_y, "--:--");
#if UI_V4_3_OLED_PROFILE
        uiPopFont(display, clock_hero_font);
        clock_small_font = uiPushCompactChromeFont(display);
#endif
        if (show_clock_date) {
          display.setTextSize(1);
          display.drawTextCentered(display.width() / 2, date_y, "нет времени");
        }
      }
      display.setBold(false);
      display.setTextSize(1);

      int sats = -1;
#if ENV_INCLUDE_GPS == 1 || UI_PHONE_GPS == 1
      if (_task->getGPSState()) {
        LocationProvider* nmea = sensors.getLocationProvider();
        if (nmea != NULL) sats = nmea->satellitesCount();
      }
#endif
      display.setColor(DisplayDriver::LIGHT);
#if UI_V4_3_OLED_PROFILE
      if (compact_clock) {
        snprintf(tmp, sizeof(tmp), "CH%s A%s", ch_pct, air_pct);
        drawRichTextEllipsized(display, 0, stats_y, display.width(), tmp);
        int detail_right_x = display.width() - 1;
        if (has_mcu_temp) {
          display.drawTextRightAlign(detail_right_x, detail_y, temp_text);
          detail_right_x -= display.getTextWidth(temp_text) + 4;
        }
        if (sats >= 0) {
          char sat_buf[5];
          if (sats > 99) sats = 99;
          snprintf(sat_buf, sizeof(sat_buf), "%d", sats);
          int sat_text_w = display.getTextWidth(sat_buf);
          int sat_icon_x = detail_right_x - sat_text_w - uiLineIconAdvance(display, satellite_icon);
          if (sat_icon_x < 0) sat_icon_x = 0;
          drawUiLineIcon(display, sat_icon_x, detail_y, satellite_icon);
          display.drawTextRightAlign(detail_right_x, detail_y, sat_buf);
          detail_right_x = sat_icon_x - 2;
        }
        snprintf(tmp, sizeof(tmp), "MSG/h %s", msg_hour);
        if (detail_right_x >= 8) {
          drawRichTextEllipsized(display, 0, detail_y, detail_right_x + 1, tmp);
        }
      } else
#endif
      {
        if (compact_clock) {
#if UI_NATIVE_TFT_PROFILE && defined(HELTEC_T114)
          int right_x = display.width() - 1;
          int left_max_width = display.width();

          if (has_mcu_temp) {
            display.drawTextRightAlign(right_x, stats_y, temp_text);
            right_x -= display.getTextWidth(temp_text) + 4;
            left_max_width = right_x + 1;
          }
          snprintf(tmp, sizeof(tmp), "CH%s A%s", ch_pct, air_pct);
          if (left_max_width < 42) left_max_width = display.width();
          drawRichTextEllipsized(display, 0, stats_y, left_max_width, tmp);
#if UI_SMART_B11_EXTRAS == 1
          if (_task->getMsgCount() > 0) {
            display.setColor(DisplayDriver::LIGHT);
            snprintf(tmp, sizeof(tmp), "Н:%d  MSG/h %s", _task->getMsgCount(), msg_hour);
          } else {
            display.setColor(DisplayDriver::LIGHT);
            snprintf(tmp, sizeof(tmp), "MSG/h %s", msg_hour);
          }
          drawRichTextEllipsized(display, 0, detail_y, display.width(), tmp);
#endif
#else
          display.setCursor(0, stats_y);
          snprintf(tmp, sizeof(tmp), "CH%s A%s", ch_pct, air_pct);
          display.print(tmp);
          int detail_right_x = display.width() - 1;
          if (has_mcu_temp) {
            display.drawTextRightAlign(detail_right_x, detail_y, temp_text);
            detail_right_x -= display.getTextWidth(temp_text) + 4;
          }
          if (sats >= 0) {
            char sat_buf[5];
            if (sats > 99) sats = 99;
            snprintf(sat_buf, sizeof(sat_buf), "%d", sats);
            int sat_text_w = display.getTextWidth(sat_buf);
            int sat_icon_x = detail_right_x - sat_text_w - uiLineIconAdvance(display, satellite_icon);
            if (sat_icon_x < 0) sat_icon_x = 0;
            drawUiLineIcon(display, sat_icon_x, detail_y, satellite_icon);
            display.drawTextRightAlign(detail_right_x, detail_y, sat_buf);
            detail_right_x = sat_icon_x - 2;
          }
          snprintf(tmp, sizeof(tmp), "MSG/h %s", msg_hour);
          if (detail_right_x >= 8) {
            drawRichTextEllipsized(display, 0, detail_y, detail_right_x + 1, tmp);
          }
#endif
        } else {
          display.setCursor(0, stats_y);
          snprintf(tmp, sizeof(tmp), "ChUtil %s  Air %s", ch_pct, air_pct);
          display.print(tmp);
          snprintf(tmp, sizeof(tmp), "Msg/h %s", msg_hour);
          display.setCursor(0, detail_y);
          display.print(tmp);
          if (has_mcu_temp) {
            display.drawTextRightAlign(display.width() - 1, detail_y, temp_text);
          }
        }
      }
      if (sats >= 0 && !compact_clock) {
        char sat_buf[5];
        if (sats > 99) sats = 99;
        snprintf(sat_buf, sizeof(sat_buf), "%d", sats);
        int sat_text_w = display.getTextWidth(sat_buf);
        int sat_right_x = has_mcu_temp ? display.width() - display.getTextWidth(temp_text) - 8 : display.width() - 1;
        int sat_icon_x = sat_right_x - sat_text_w - uiLineIconAdvance(display, satellite_icon);
        if (sat_icon_x < 0) sat_icon_x = 0;
        int sat_y = detail_y;
        drawUiLineIcon(display, sat_icon_x, sat_y, satellite_icon);
        display.drawTextRightAlign(sat_right_x, sat_y, sat_buf);
      }
#if UI_V4_3_OLED_PROFILE
      uiPopFont(display, clock_small_font);
#endif
#if UI_WIRELESS_PAPER_BIG_CLOCK
      }
#endif
#endif
    } else if (_page == HomePage::RECENT) {
      the_mesh.getRecentlyHeard(recent, UI_RECENT_LIST_SIZE);
#if UI_V4_3_OLED_PROFILE
      uint8_t list_font = uiPushCompactChromeFont(display);
#endif
      display.setColor(DisplayDriver::GREEN);
      int y = 20;
      int row_h = 11;
#if UI_T096_PREMIUM_TFT
      y = 17;
      row_h = display.getTextLineHeight();
      if (row_h < 16) row_h = 16;
#elif UI_NATIVE_TFT_PROFILE
      y = 16;
      row_h = display.getTextLineHeight() + 3;
      if (row_h < 13) row_h = 13;
#elif UI_V4_3_OLED_PROFILE
      y = 16;
      row_h = 12;
#endif
      int recent_rows = UI_RECENT_LIST_SIZE;
      int recent_fit = (display.height() - y) / row_h;
      if (recent_fit < 1) recent_fit = 1;
      if (recent_rows > recent_fit) recent_rows = recent_fit;
      for (int i = 0; i < recent_rows; i++, y += row_h) {
        auto a = &recent[i];
        if (a->name[0] == 0) continue;  // empty slot
        int secs = _rtc->getCurrentTime() - a->recv_timestamp;
        if (secs < 60) {
          sprintf(tmp, "%dс", secs);
        } else if (secs < 60*60) {
          sprintf(tmp, "%dм", secs / 60);
        } else {
          sprintf(tmp, "%dч", secs / (60*60));
        }

        int timestamp_width = display.getTextWidth(tmp);
        int max_name_width = display.width() - timestamp_width - 1;

        drawRichTextEllipsized(display, 0, y, max_name_width, a->name);
        display.setCursor(display.width() - timestamp_width - 1, y);
        display.print(tmp);
      }
#if UI_V4_3_OLED_PROFILE
      uiPopFont(display, list_font);
#endif
    } else if (_page == HomePage::NETWORK) {
      int raw_count = the_mesh.getRecentNetworkStatus(network_status, UI_RECENT_LIST_SIZE);
      int count = 0;
      for (int i = 0; i < raw_count; i++) {
        if (network_status[i].flags & NETWORK_STATUS_CHANNEL_TRAFFIC) continue;
        if (count != i) network_status[count] = network_status[i];
        count++;
      }
#if UI_V4_3_OLED_PROFILE
      uint8_t list_font = uiPushCompactChromeFont(display);
#endif
      display.setTextSize(1);
      if (count == 0) {
        display.setColor(DisplayDriver::YELLOW);
        display.drawTextCentered(display.width() / 2, 25, "Нет данных");
        display.drawTextCentered(display.width() / 2, 38, "за 15 мин");
      } else {
        int y = 20;
        int row_h = 11;
#if UI_T096_PREMIUM_TFT
        y = 17;
        row_h = display.getTextLineHeight();
        if (row_h < 16) row_h = 16;
#elif UI_NATIVE_TFT_PROFILE
        y = 16;
        row_h = display.getTextLineHeight() + 3;
        if (row_h < 13) row_h = 13;
#elif UI_V4_3_OLED_PROFILE
        y = 16;
        row_h = 12;
#endif
        int network_fit = (display.height() - y) / row_h;
        if (network_fit < 1) network_fit = 1;
        if (count > network_fit) count = network_fit;
#if UI_SDVIG_NETWORK_LAYOUT
        const int left_margin = 0;
        const int right_margin = 0;
#elif UI_T096_PREMIUM_TFT
        const int left_margin = 0;
        const int right_margin = 1;
#else
        const int left_margin = 4;
        const int right_margin = 14;
#endif
        for (int i = 0; i < count; i++, y += row_h) {
          auto n = &network_status[i];
          bool via_relay = (n->flags & NETWORK_STATUS_VIA_RELAY) != 0;
          bool is_companion_relay = (n->flags & NETWORK_STATUS_CLIENT_REPEAT_UNKNOWN) != 0;
          display.setColor(via_relay ? DisplayDriver::YELLOW : DisplayDriver::GREEN);

          char metrics[16];
          formatSignalMetrics(metrics, sizeof(metrics), n);

#if UI_SDVIG_NETWORK_LAYOUT
          char role_label[8];
          formatNetworkRoleLabel(role_label, sizeof(role_label), n);
          int metrics_width = display.getTextWidth(metrics);
          int metrics_x = display.width() - right_margin - metrics_width;
          if (metrics_x < left_margin) metrics_x = left_margin;

          display.setColor(signalMetricsColor(n));
          display.setBold(false);
          display.setCursor(metrics_x, y);
          display.print(metrics);

          const char* status_name = n->name;
          if (is_companion_relay && looksLikeIdName(n->name)) {
            status_name = "через ретранслятор";
          }
          char plain_status_name[sizeof(n->name)];
          copyRichTextWithoutIcons(plain_status_name, sizeof(plain_status_name), status_name);
          if (plain_status_name[0] != 0) status_name = plain_status_name;

          int role_width = richTextWidth(display, role_label);
          display.setColor((n->flags & (NETWORK_STATUS_REPEATER | NETWORK_STATUS_CLIENT_REPEAT_UNKNOWN)) ? DisplayDriver::YELLOW : DisplayDriver::GREEN);
          drawRichTextLine(display, left_margin, y, role_label);

          int name_x = left_margin + role_width + 2;
          int max_name_width = metrics_x - name_x - 2;
          if (max_name_width < 10) max_name_width = 10;
          display.setColor(via_relay ? DisplayDriver::YELLOW : DisplayDriver::GREEN);
          display.setBold(false);
          drawRichTextEllipsized(display, name_x, y, max_name_width, status_name);
#else
          int route_width = routeIconsWidth(display, n);
          drawRouteIcons(display, left_margin, y, n);

          int metrics_width = display.getTextWidth(metrics);
          int metrics_x = display.width() - right_margin - metrics_width;
          if (metrics_x < left_margin) metrics_x = left_margin;
          display.setColor(signalMetricsColor(n));
          display.setBold(false);
          display.setCursor(metrics_x, y);
          display.print(metrics);

          const char* status_name = n->name;
          if (is_companion_relay && looksLikeIdName(n->name)) {
            status_name = "через ретранслятор";
          }

          int name_x = left_margin + route_width + 4;
          int max_name_width = metrics_x - name_x - 4;
          if (max_name_width < 10) max_name_width = 10;
          display.setColor(via_relay ? DisplayDriver::YELLOW : DisplayDriver::GREEN);
          display.setBold(false);
          drawRichTextEllipsized(display, name_x, y, max_name_width, status_name);
#endif
        }
      }
#if UI_V4_3_OLED_PROFILE
      uiPopFont(display, list_font);
#endif
    } else if (_page == HomePage::CHAT) {
      display.setTextSize(1);
      display.setColor(DisplayDriver::LIGHT);
      if (_quick_reply_open) {
#if UI_QUICK_REPLY_KEYBOARD
        if (_quick_keyboard_open) {
          renderQuickKeyboard(display);
        } else
#endif
        {
        display.setColor(DisplayDriver::GREEN);
#if UI_V4_3_OLED_PROFILE
        {
          uint8_t small_font = uiPushCompactChromeFont(display);
          drawRichTextCentered(display, display.width() / 2, 4, "Быстрый ответ");
          uiPopFont(display, small_font);
        }
        {
          uint8_t hero_font = uiPushOledRoleFont(display, UI_OLED_FONT_L);
          drawRichTextCenteredEllipsized(display, display.width() / 2, 22, display.width() - 2, quickReplyLabel());
          uiPopFont(display, hero_font);
        }
        {
          uint8_t small_font = uiPushCompactChromeFont(display);
          display.setColor(DisplayDriver::LIGHT);
          drawRichTextCenteredEllipsized(display, display.width() / 2, 52, display.width(), "клик далее / удерж OK");
          uiPopFont(display, small_font);
        }
#else
        display.drawTextCentered(display.width() / 2, 4, "Быстрый ответ");
        display.setTextSize(2);
        drawRichTextCentered(display, display.width() / 2, 22, quickReplyLabel());
        display.setTextSize(1);
        display.drawTextCentered(display.width() / 2, 47, "клик: далее");
        display.drawTextCentered(display.width() / 2, 56, "удерж: OK");
#endif
        }
      } else {
      int count = the_mesh.getRecentChannelMessages(chat, UI_CHAT_LIST_SIZE);
      if (count == 0) {
        display.setColor(DisplayDriver::YELLOW);
        display.drawTextCentered(display.width() / 2, 31, "Нет чата");
      } else {
        renderChatList(display, count);
      }
      }
    } else if (_page == HomePage::ALERTS) {
#if UI_V4_3_OLED_PROFILE
      uint8_t mode = _task->getNotifyMode();
      char mode_line[80];
      char led_line[80];
      char tone_line[80];
      snprintf(mode_line, sizeof(mode_line), "Режим: %s", _task->getNotifyModeName());
#ifdef PIN_MSG_ALERT
      snprintf(led_line, sizeof(led_line), "Свет: D%d %s", _task->getNotifyLedPin(), (mode & NOTIFY_MODE_GPIO) ? "ВКЛ" : "ВЫКЛ");
#else
      snprintf(led_line, sizeof(led_line), "Свет: нет");
#endif
#ifdef PIN_MSG_TONE
      snprintf(tone_line, sizeof(tone_line), "Звук: D%d %s", _task->getNotifyTonePin(), (mode & NOTIFY_MODE_TONE) ? "ВКЛ" : "ВЫКЛ");
#else
      snprintf(tone_line, sizeof(tone_line), "Звук: нет");
#endif
      drawOledCompactMenuPage(display, "Сигналы", mode_line, led_line, tone_line);
#else
      display.setColor(DisplayDriver::GREEN);
      display.setTextSize(1);
      display.drawTextCentered(display.width() / 2, 18, "Сигналы");

      uint8_t mode = _task->getNotifyMode();
      display.setCursor(0, 30);
      snprintf(tmp, sizeof(tmp), "Режим: %s", _task->getNotifyModeName());
      display.print(tmp);

      display.setCursor(0, 41);
#ifdef PIN_MSG_ALERT
      snprintf(tmp, sizeof(tmp), "Свет: D%d %s", _task->getNotifyLedPin(), (mode & NOTIFY_MODE_GPIO) ? "ВКЛ" : "ВЫКЛ");
#else
      snprintf(tmp, sizeof(tmp), "Свет: нет");
#endif
      display.print(tmp);

      display.setCursor(0, 52);
#ifdef PIN_MSG_TONE
      snprintf(tmp, sizeof(tmp), "Звук: D%d %s", _task->getNotifyTonePin(), (mode & NOTIFY_MODE_TONE) ? "ВКЛ" : "ВЫКЛ");
#else
      snprintf(tmp, sizeof(tmp), "Звук: нет");
#endif
      display.print(tmp);

      display.drawTextRightAlign(display.width() - 1, 52, PRESS_LABEL);
#endif
#ifdef PIN_MSG_ALERT
    } else if (_page == HomePage::ALERT_LED) {
#if UI_V4_3_OLED_PROFILE
      char pin_line[32];
      snprintf(pin_line, sizeof(pin_line), "Пин: D%d", _task->getNotifyLedPin());
#if UI_NOTIFY_GPIO_SELECT
      drawOledCompactMenuPage(display, "Пин света", pin_line, "мигнет здесь", PRESS_LABEL);
#else
      drawOledCompactMenuPage(display, "Пин света", pin_line, "задан в сборке", "нужна пересборка");
#endif
#else
      display.setColor(DisplayDriver::GREEN);
      display.setTextSize(1);
      display.drawTextCentered(display.width() / 2, 18, "Пин света");
      display.setCursor(0, 31);
      snprintf(tmp, sizeof(tmp), "Пин: D%d", _task->getNotifyLedPin());
      display.print(tmp);
      display.setCursor(0, 42);
#if UI_NOTIFY_GPIO_SELECT
      display.print("мигнет здесь");
      display.setCursor(0, 53);
      display.print(PRESS_LABEL);
#else
      display.print("задан в сборке");
      display.setCursor(0, 53);
      display.print("нужна пересборка");
#endif
#endif
#endif
#ifdef PIN_MSG_TONE
    } else if (_page == HomePage::ALERT_TONE_PIN) {
#if UI_V4_3_OLED_PROFILE
      char pin_line[32];
      snprintf(pin_line, sizeof(pin_line), "Пин: D%d", _task->getNotifyTonePin());
#if UI_NOTIFY_GPIO_SELECT
      drawOledCompactMenuPage(display, "Пин звука", pin_line, "зумер здесь", PRESS_LABEL);
#else
      drawOledCompactMenuPage(display, "Пин звука", pin_line, "задан в сборке", "нужна пересборка");
#endif
#else
      display.setColor(DisplayDriver::GREEN);
      display.setTextSize(1);
      display.drawTextCentered(display.width() / 2, 18, "Пин звука");
      display.setCursor(0, 31);
      snprintf(tmp, sizeof(tmp), "Пин: D%d", _task->getNotifyTonePin());
      display.print(tmp);
      display.setCursor(0, 42);
#if UI_NOTIFY_GPIO_SELECT
      display.print("зумер здесь");
      display.setCursor(0, 53);
      display.print(PRESS_LABEL);
#else
      display.print("задан в сборке");
      display.setCursor(0, 53);
      display.print("нужна пересборка");
#endif
#endif
#endif
#if UI_TONE_BRIDGE_PAGE == 1
    } else if (_page == HomePage::ALERT_TONE_BRIDGE) {
      const bool bridge = _task->isNotifyToneBridgeEnabled();
      char mode_line[32];
      char wiring_line[32];
      snprintf(mode_line, sizeof(mode_line), "Режим: %s", bridge ? "МОСТ" : "ОБЫЧНЫЙ");
      if (bridge) {
        snprintf(wiring_line, sizeof(wiring_line), "D%d <-> D%d",
                 _task->getNotifyTonePin(), _task->getNotifyToneBridgePin());
      } else {
        snprintf(wiring_line, sizeof(wiring_line), "D%d <-> GND", _task->getNotifyTonePin());
      }
#if UI_V4_3_OLED_PROFILE
      drawOledCompactMenuPage(display, "Схема зуммера", mode_line, wiring_line, PRESS_LABEL);
#else
      display.setColor(DisplayDriver::GREEN);
      display.setTextSize(1);
      display.drawTextCentered(display.width() / 2, 18, "Схема зуммера");
      display.setCursor(0, 34);
      display.print(mode_line);
      display.setCursor(0, 50);
      display.print(wiring_line);
#endif
#endif
    } else if (_page == HomePage::ALERT_VIBE_PIN) {
#if UI_V4_3_OLED_PROFILE
      char pin_line[32];
      int pin = _task->getNotifyVibePin();
      if (pin >= 0) {
        snprintf(pin_line, sizeof(pin_line), "Пин: D%d", pin);
      } else {
        snprintf(pin_line, sizeof(pin_line), "Пин: выкл");
      }
#if UI_NOTIFY_GPIO_SELECT
      drawOledCompactMenuPage(display, "Пин вибро", pin_line, "импульсы мотора", PRESS_LABEL);
#else
      drawOledCompactMenuPage(display, "Пин вибро", pin_line, "задан в сборке", "нужна пересборка");
#endif
#else
      display.setColor(DisplayDriver::GREEN);
      display.setTextSize(1);
      display.drawTextCentered(display.width() / 2, 18, "Пин вибро");
      display.setCursor(0, 31);
      int pin = _task->getNotifyVibePin();
      if (pin >= 0) {
        snprintf(tmp, sizeof(tmp), "Пин: D%d", pin);
      } else {
        snprintf(tmp, sizeof(tmp), "Пин: выкл");
      }
      display.print(tmp);
      display.setCursor(0, 42);
#if UI_NOTIFY_GPIO_SELECT
      display.print("импульсы мотора");
      display.setCursor(0, 53);
      display.print(PRESS_LABEL);
#else
      display.print("задан в сборке");
      display.setCursor(0, 53);
      display.print("нужна пересборка");
#endif
#endif
#ifdef PIN_MSG_TONE
    } else if (_page == HomePage::ALERT_SOUND) {
#if UI_V4_3_OLED_PROFILE
      char sound_line[48];
      snprintf(sound_line, sizeof(sound_line), "Звук: %s", _task->getNotifySoundName());
      drawOledCompactMenuPage(display, "Мелодия", sound_line, "выбор мелодии", PRESS_LABEL);
#else
      display.setColor(DisplayDriver::GREEN);
      display.setTextSize(1);
      display.drawTextCentered(display.width() / 2, 18, "Мелодия");
      display.setCursor(0, 31);
      snprintf(tmp, sizeof(tmp), "Звук: %s", _task->getNotifySoundName());
      display.print(tmp);
      display.setCursor(0, 42);
      display.print("выбор мелодии");
      display.setCursor(0, 53);
      display.print(PRESS_LABEL);
#endif
#if UI_TONE_8BIT_PAGE == 1
    } else if (_page == HomePage::ALERT_TONE_STYLE) {
#if UI_V4_3_OLED_PROFILE
      char style_line[32];
      snprintf(style_line, sizeof(style_line), "Режим: %s", _task->getNotifyToneStyleName());
      drawOledCompactMenuPage(display, "Стиль звука", style_line, "ретро-арпеджио", PRESS_LABEL);
#else
      display.setColor(DisplayDriver::GREEN);
      display.setTextSize(1);
      display.drawTextCentered(display.width() / 2, 18, "Стиль звука");
      display.setCursor(0, 31);
      snprintf(tmp, sizeof(tmp), "Режим: %s", _task->getNotifyToneStyleName());
      display.print(tmp);
      display.setCursor(0, 42);
      display.print("ретро-арпеджио");
      display.setCursor(0, 53);
      display.print(PRESS_LABEL);
#endif
#endif
    } else if (_page == HomePage::ALERT_VOLUME) {
#if UI_TONE_HIGH_DRIVE_PAGE == 1
#if UI_V4_3_OLED_PROFILE
      char drive_line[32];
      snprintf(drive_line, sizeof(drive_line), "Режим: %s", _task->getNotifyToneDriveName());
      drawOledCompactMenuPage(display, "Громкость GPIO", drive_line, "усиленный выход", PRESS_LABEL);
#else
      display.setColor(DisplayDriver::GREEN);
      display.setTextSize(1);
      display.drawTextCentered(display.width() / 2, 18, "Громкость GPIO");
      display.setCursor(0, 34);
      snprintf(tmp, sizeof(tmp), "Режим: %s", _task->getNotifyToneDriveName());
      display.print(tmp);
      display.setCursor(0, 50);
      display.print("усиленный выход");
#endif
#else
#if UI_V4_3_OLED_PROFILE
      char volume_line[32];
      snprintf(volume_line, sizeof(volume_line), "Громк: %u/10", _task->getNotifyToneVolume());
      drawOledCompactMenuPage(display, "Громкость", volume_line, "уровень зумера", PRESS_LABEL);
#else
      display.setColor(DisplayDriver::GREEN);
      display.setTextSize(1);
      display.drawTextCentered(display.width() / 2, 18, "Громкость");
      display.setCursor(0, 31);
      snprintf(tmp, sizeof(tmp), "Громк: %u/10", _task->getNotifyToneVolume());
      display.print(tmp);
      display.setCursor(0, 42);
      display.print("уровень зумера");
      display.setCursor(0, 53);
      display.print(PRESS_LABEL);
#endif
#endif
#if UI_TONE_RESONANCE_PAGE == 1
    } else if (_page == HomePage::ALERT_TONE_RESONANCE) {
      char resonance_line[32];
      snprintf(resonance_line, sizeof(resonance_line), "Частота: %u Гц", _task->getNotifyToneResonanceHz());
#if UI_V4_3_OLED_PROFILE
      drawOledCompactMenuPage(display, "Резонанс пьезо", resonance_line, "нажать и слушать", PRESS_LABEL);
#else
      display.setColor(DisplayDriver::GREEN);
      display.setTextSize(1);
      display.drawTextCentered(display.width() / 2, 18, "Резонанс пьезо");
      display.setCursor(0, 34);
      display.print(resonance_line);
      display.setCursor(0, 50);
      display.print("нажать и слушать");
#endif
#endif
#endif
    } else if (_page == HomePage::RADIO) {
#if UI_V4_3_OLED_PROFILE
      char freq_line[48];
      char bw_line[48];
      char tx_line[32];
      sprintf(freq_line, "Чст: %06.3f SF:%d", _node_prefs->freq, _node_prefs->sf);
      sprintf(bw_line, "Шир: %03.2f Код:%d", _node_prefs->bw, _node_prefs->cr);
      sprintf(tx_line, "Мощн: %ddBm  Шум:%d", _node_prefs->tx_power_dbm, radio_driver.getNoiseFloor());
      drawOledCompactMenuPage(display, "Радио", freq_line, bw_line, tx_line);
#else
      display.setColor(DisplayDriver::YELLOW);
      display.setTextSize(1);
      // freq / sf
      display.setCursor(0, 20);
      sprintf(tmp, "Чст: %06.3f SF:%d", _node_prefs->freq, _node_prefs->sf);
      display.print(tmp);

      display.setCursor(0, 31);
      sprintf(tmp, "Шир: %03.2f Код:%d", _node_prefs->bw, _node_prefs->cr);
      display.print(tmp);

      // tx power,  noise floor
      display.setCursor(0, 42);
      sprintf(tmp, "Мощн: %ddBm", _node_prefs->tx_power_dbm);
      display.print(tmp);
      display.setCursor(0, 53);
      sprintf(tmp, "Шум: %d", radio_driver.getNoiseFloor());
      display.print(tmp);
#endif
#if UI_CLIENT_REPEAT_PAGE == 1
    } else if (_page == HomePage::CLIENT_REPEAT) {
#if UI_V4_3_OLED_PROFILE
      char status_line[48];
      char freq_line[48];
      snprintf(status_line, sizeof(status_line), "Статус: %s", the_mesh.isClientRepeatEnabled() ? "ВКЛ" : "ВЫКЛ");
      snprintf(freq_line, sizeof(freq_line), "%06.3f MHz SF%d", _node_prefs->freq, _node_prefs->sf);
      drawOledCompactMenuPage(display, "Ретрансляция", status_line, freq_line, PRESS_LABEL);
#else
      display.setColor(DisplayDriver::GREEN);
      display.setTextSize(1);
      display.drawTextCentered(display.width() / 2, 18, "Ретрансляция");
      display.setCursor(0, 31);
      snprintf(tmp, sizeof(tmp), "Статус: %s", the_mesh.isClientRepeatEnabled() ? "ВКЛ" : "ВЫКЛ");
      display.print(tmp);
      display.setCursor(0, 42);
      snprintf(tmp, sizeof(tmp), "%06.3f MHz SF%d", _node_prefs->freq, _node_prefs->sf);
      display.print(tmp);
      display.setCursor(0, 53);
      display.print(PRESS_LABEL);
#endif
#endif
    } else if (_page == HomePage::LINK_TEST) {
#if UI_V4_3_OLED_PROFILE
      uint8_t link_font = uiPushCompactChromeFont(display);
#endif
      display.setColor(DisplayDriver::GREEN);
      display.setTextSize(1);
      display.drawTextCentered(display.width() / 2, 14, "Опрос путей");

      LinkTestStatus st;
      the_mesh.getLinkTestStatus(st);
      if (!st.has_target) {
        display.setColor(DisplayDriver::YELLOW);
        display.drawTextCentered(display.width() / 2, 29, st.done ? "Нет узлов" : "Все контакты");
        display.setColor(DisplayDriver::LIGHT);
        display.drawTextCentered(display.width() / 2, 43, "старт: " PRESS_LABEL);
        display.drawTextCentered(display.width() / 2, display.height() <= 64 ? 52 : 54, "поиск через flood");
      } else {
        const char* label = "Узел: ";
        int label_w = display.getTextWidth(label);
        display.setColor(DisplayDriver::LIGHT);
        display.setCursor(0, 27);
        display.print(label);
        drawRichTextEllipsized(display, label_w, 27, display.width() - label_w, st.target);

        display.setColor(st.active ? DisplayDriver::YELLOW : DisplayDriver::GREEN);
        snprintf(tmp, sizeof(tmp), "%s %u/%u П%u", st.active ? "Пути" : "Готово", st.ok, st.total, st.failed);
        display.drawTextCentered(display.width() / 2, 39, tmp);

        display.setColor(DisplayDriver::LIGHT);
        if (st.ok > 0) {
          snprintf(tmp, sizeof(tmp), "Ответ %ums S%+d R%d", st.avg_rtt_ms, roundSnrQ4(st.last_snr_q4), st.last_rssi);
        } else if (st.active) {
          snprintf(tmp, sizeof(tmp), "ждем ответы...");
        } else {
          snprintf(tmp, sizeof(tmp), "нет ответа");
        }
        display.drawTextCentered(display.width() / 2, 51, tmp);
      }
#if UI_V4_3_OLED_PROFILE
      uiPopFont(display, link_font);
#endif
    } else if (_page == HomePage::BLUETOOTH) {
      display.setColor(DisplayDriver::GREEN);
      display.drawXbm((display.width() - 32) / 2, 18,
          _task->isBluetoothEnabled() ? bluetooth_on : bluetooth_off,
          32, 32);
#if UI_V4_3_OLED_PROFILE
      uint8_t small_font = uiPushCompactChromeFont(display);
      drawRichTextCentered(display, display.width() / 2, 52, "перекл: " PRESS_LABEL);
      uiPopFont(display, small_font);
#else
      display.setTextSize(1);
      display.drawTextCentered(display.width() / 2, 64 - 11, "перекл: " PRESS_LABEL);
#endif
#if UI_BLE_PIN_PAGE
    } else if (_page == HomePage::BLE_PIN) {
      renderBlePinPage(display, the_mesh.getBLEPin(), _task->hasConnection());
#endif
    } else if (_page == HomePage::MSG_POPUP) {
#if UI_V4_3_OLED_PROFILE
      char status_line[48];
      snprintf(status_line, sizeof(status_line), "Окно: %s", _task->areMsgPopupsEnabled() ? "ВКЛ" : "ВЫКЛ");
      drawOledCompactMenuPage(display, "Всплыв. сообщ.", status_line, "авто-показ новых", PRESS_LABEL);
#else
      display.setColor(DisplayDriver::GREEN);
      display.setTextSize(1);
      display.drawTextCentered(display.width() / 2, 18, "Всплыв. сообщ.");
      display.setCursor(0, 31);
      snprintf(tmp, sizeof(tmp), "Окно: %s", _task->areMsgPopupsEnabled() ? "ВКЛ" : "ВЫКЛ");
      display.print(tmp);
      display.setCursor(0, 42);
      display.print("авто-показ новых");
      display.setCursor(0, 53);
      display.print(PRESS_LABEL);
#endif
    } else if (_page == HomePage::IMPORTANT_NOTIFY) {
#if UI_V4_3_OLED_PROFILE
      char mode_line[48];
      snprintf(mode_line, sizeof(mode_line), "Сигнал: %s", _task->getImportantNotifyModeName());
      drawOledCompactMenuPage(display, "ЛС/упомин.", mode_line, "ЛС + @имя", "сброс: кнопка");
#else
      display.setColor(DisplayDriver::GREEN);
      display.setTextSize(1);
      display.drawTextCentered(display.width() / 2, 18, "ЛС/упомин.");
      display.setCursor(0, 31);
      snprintf(tmp, sizeof(tmp), "Сигнал: %s", _task->getImportantNotifyModeName());
      display.print(tmp);
      display.setCursor(0, 42);
      display.print("ЛС + @имя");
      display.setCursor(0, 53);
      display.print("сброс: кнопка");
#endif
#if UI_OFFLINE_DM_LED_PAGE == 1 && defined(PIN_MSG_ALERT)
    } else if (_page == HomePage::OFFLINE_DM_LED) {
#if UI_V4_3_OLED_PROFILE
      char status_line[32];
      snprintf(status_line, sizeof(status_line), "LED: %s", _task->isOfflineDmLedEnabled() ? "ВКЛ" : "ВЫКЛ");
      drawOledCompactMenuPage(display, "LED ЛС без BLE", status_line, "только личные", PRESS_LABEL);
#else
      display.setColor(DisplayDriver::GREEN);
      display.setTextSize(1);
      display.drawTextCentered(display.width() / 2, 14, "LED ЛС без BLE");
      display.setCursor(0, 29);
      snprintf(tmp, sizeof(tmp), "LED: %s", _task->isOfflineDmLedEnabled() ? "ВКЛ" : "ВЫКЛ");
      display.print(tmp);
      display.setCursor(0, 42);
      display.print("только личные");
      display.setCursor(0, 53);
      display.print(PRESS_LABEL);
#endif
    } else if (_page == HomePage::BLE_DM_LED) {
#if UI_V4_3_OLED_PROFILE
      char status_line[32];
      snprintf(status_line, sizeof(status_line), "LED: %s", _task->isBleDmLedEnabled() ? "ВКЛ" : "ВЫКЛ");
      drawOledCompactMenuPage(display, "LED ЛС при BLE", status_line, "телефон подключен", PRESS_LABEL);
#else
      display.setColor(DisplayDriver::GREEN);
      display.setTextSize(1);
      display.drawTextCentered(display.width() / 2, 14, "LED ЛС при BLE");
      display.setCursor(0, 29);
      snprintf(tmp, sizeof(tmp), "LED: %s", _task->isBleDmLedEnabled() ? "ВКЛ" : "ВЫКЛ");
      display.print(tmp);
      display.setCursor(0, 42);
      display.print("телефон подключен");
      display.setCursor(0, 53);
      display.print(PRESS_LABEL);
#endif
#endif
#if UI_BOARD_LEDS_PAGE == 1
    } else if (_page == HomePage::BOARD_LEDS) {
#if UI_V4_3_OLED_PROFILE
      char status_line[48];
      snprintf(status_line, sizeof(status_line), "Статус: %s", _task->areBoardLedsEnabled() ? "ВКЛ" : "ВЫКЛ");
      drawOledCompactMenuPage(display, "LED платы", status_line, "штатные индик.", PRESS_LABEL);
#else
      display.setColor(DisplayDriver::GREEN);
      display.setTextSize(1);
      display.drawTextCentered(display.width() / 2, 18, "LED платы");
      display.setCursor(0, 31);
      snprintf(tmp, sizeof(tmp), "Статус: %s", _task->areBoardLedsEnabled() ? "ВКЛ" : "ВЫКЛ");
      display.print(tmp);
      display.setCursor(0, 42);
      display.print("штатные индик.");
      display.setCursor(0, 53);
      display.print(PRESS_LABEL);
#endif
#endif
#if UI_APPEARANCE_MENU
#if UI_UNREAD_LED_PAGE == 1
    } else if (_page == HomePage::UNREAD_LED) {
#if UI_V4_3_OLED_PROFILE
      char led_line[32];
      snprintf(led_line, sizeof(led_line), "LED: %s", _task->isUnreadLedEnabled() ? "ВКЛ" : "ВЫКЛ");
      drawOledCompactMenuPage(display, "Непрочитанные", led_line, "длинное мигание", PRESS_LABEL);
#else
      display.setColor(DisplayDriver::GREEN);
      display.setTextSize(1);
      display.drawTextCentered(display.width() / 2, 14, "Непрочитанные");
      display.setCursor(0, 29);
      snprintf(tmp, sizeof(tmp), "LED: %s", _task->isUnreadLedEnabled() ? "ВКЛ" : "ВЫКЛ");
      display.print(tmp);
      display.setCursor(0, 42);
      display.print("длинное мигание");
      display.setCursor(0, 53);
      display.print(PRESS_LABEL);
#endif
#endif
    } else if (_page == HomePage::UI_FONT) {
#if UI_V4_3_OLED_PROFILE
      char count_line[16];
#if UI_T096_PREMIUM_TFT
      snprintf(count_line, sizeof(count_line), "%u шрифтов", _task->getUiFontCount());
#else
      snprintf(count_line, sizeof(count_line), "%u стилей", _task->getUiFontCount());
#endif
      drawOledStyleSelectPage(display, _task->getUiFontName(), count_line);
#else
      display.setColor(DisplayDriver::GREEN);
      display.setTextSize(1);
      display.drawTextCentered(display.width() / 2, 14, "Шрифт");
      display.setColor(DisplayDriver::YELLOW);
      drawRichTextCentered(display, display.width() / 2, 29, _task->getUiFontName());
      display.setColor(DisplayDriver::LIGHT);
      snprintf(tmp, sizeof(tmp), "%u вар.", _task->getUiFontCount());
      display.drawTextCentered(display.width() / 2, 43, tmp);
      display.drawTextCentered(display.width() / 2, 64 - 11, "смена: " PRESS_LABEL);
#endif
    } else if (_page == HomePage::UI_THEME) {
#if UI_V4_3_OLED_PROFILE
      char count_line[16];
      snprintf(count_line, sizeof(count_line), "%u вар.", _task->getUiThemeCount());
      drawOledCompactMenuPage(display, "Цвет / фон", _task->getUiThemeName(), count_line, "смена: " PRESS_LABEL);
#else
      display.setColor(DisplayDriver::GREEN);
      display.setTextSize(1);
      display.drawTextCentered(display.width() / 2, 14, "Цвет / фон");
      display.setColor(DisplayDriver::YELLOW);
      drawRichTextCentered(display, display.width() / 2, 29, _task->getUiThemeName());
      display.setColor(DisplayDriver::LIGHT);
      snprintf(tmp, sizeof(tmp), "%u вар.", _task->getUiThemeCount());
      display.drawTextCentered(display.width() / 2, 43, tmp);
      display.drawTextCentered(display.width() / 2, 64 - 11, "смена: " PRESS_LABEL);
#endif
#if UI_COLOR_APPEARANCE_MENU
    } else if (_page == HomePage::UI_TOP_COLOR) {
      char color_line[48];
      snprintf(color_line, sizeof(color_line), "Верх: %s", _task->getUiTopColorName());
      drawOledCompactMenuPage(display, "Цвет верха", color_line, "часы / заголовки", "смена: " PRESS_LABEL);
    } else if (_page == HomePage::UI_BOTTOM_COLOR) {
      char color_line[48];
      snprintf(color_line, sizeof(color_line), "Низ: %s", _task->getUiBottomColorName());
      drawOledCompactMenuPage(display, "Цвет низа", color_line, "статусы / детали", "смена: " PRESS_LABEL);
#endif
#if UI_BACKLIGHT_TIMEOUT_PAGE == 1
    } else if (_page == HomePage::BACKLIGHT_TIMEOUT) {
      char light_line[48];
      snprintf(light_line, sizeof(light_line), "Экран: %s", _task->getBacklightTimeoutName());
      drawOledCompactMenuPage(display, "Подсветка", light_line, "15 / 30 / 1 мин", "смена: " PRESS_LABEL);
#endif
#endif
    } else if (_page == HomePage::ADVERT) {
      display.setColor(DisplayDriver::GREEN);
      display.drawXbm((display.width() - 32) / 2, 18, advert_icon, 32, 32);
#if UI_V4_3_OLED_PROFILE
      uint8_t small_font = uiPushCompactChromeFont(display);
      drawRichTextCentered(display, display.width() / 2, 52, "анонс: " PRESS_LABEL);
      uiPopFont(display, small_font);
#else
      display.drawTextCentered(display.width() / 2, 64 - 11, "анонс: " PRESS_LABEL);
#endif
#if UI_AUTO_ADVERT_PAGE == 1
    } else if (_page == HomePage::ADVERT_TIMER) {
#if UI_V4_3_OLED_PROFILE
      char interval_line[48];
      snprintf(interval_line, sizeof(interval_line), "Интервал: %s", autoAdvertLabel());
      drawOledCompactMenuPage(display, "Авто-анонс", interval_line, "передает себя", PRESS_LABEL);
#else
      display.setColor(DisplayDriver::GREEN);
      display.setTextSize(1);
      display.drawTextCentered(display.width() / 2, 18, "Авто-анонс");
      display.setCursor(0, 31);
      snprintf(tmp, sizeof(tmp), "Интервал: %s", autoAdvertLabel());
      display.print(tmp);
      display.setCursor(0, 42);
      display.print("передает себя");
      display.setCursor(0, 53);
      display.print(PRESS_LABEL);
#endif
#endif
#if UI_CH2_RELAY_PAGE == 1
    } else if (_page == HomePage::CH2_RELAY) {
#if UI_V4_3_OLED_PROFILE
      char mode_line[48];
      snprintf(mode_line, sizeof(mode_line), "Режим: %s", the_mesh.getCh2ModeName());
      drawOledCompactMenuPage(display, "Канал 2", mode_line,
          the_mesh.getCh2Mode() == CH2_MODE_BATCH ? "15 msg / repeat" : "869.650 / +5 dBm",
          PRESS_LABEL);
#else
      display.setColor(DisplayDriver::GREEN);
      display.setTextSize(1);
      display.drawTextCentered(display.width() / 2, 18, "Канал 2");
      display.setCursor(0, 31);
      snprintf(tmp, sizeof(tmp), "Режим: %s", the_mesh.getCh2ModeName());
      display.print(tmp);
      display.setCursor(0, 42);
      if (the_mesh.getCh2Mode() == CH2_MODE_BATCH) {
        display.print("15 msg / repeat");
      } else {
        display.print("869.650 / +5 dBm");
      }
      display.setCursor(0, 53);
      display.print(PRESS_LABEL);
#endif
#endif
#if ENV_INCLUDE_GPS == 1 || UI_PHONE_GPS == 1
    } else if (_page == HomePage::GPS) {
      uint8_t gps_saved_font = uiPushCompactSettingsFont(display);
      LocationProvider* nmea = sensors.getLocationProvider();
      char buf[50];
      int y = 18;
      int row_step = display.getTextLineHeight();
      if (row_step < 8) row_step = 8;
      // Four GPS rows must fit below the chrome. T114's real compact font
      // occupies 24 physical pixels (12 logical), not the old 22px mock-up.
      if (display.height() <= 64) {
        int gps_top = display.height() - 4 * row_step;
        if (gps_top >= 14 && y > gps_top) y = gps_top;
      }
      bool gps_state = false;
      bool gps_valid = false;
      int sats = -1;
      bool phone_source = false;
#if UI_PHONE_GPS == 1
      phone_source = the_mesh.isPhoneGpsEnabled();
#endif
      readGpsUiState(gps_state, gps_valid, sats);
      drawUiGpsStatusIcon(display, 0, y + 1, gps_state, gps_valid);
      display.drawTextLeftAlign(uiGpsStatusIconWidth(display) + 4, y,
                                phone_source ? "ТЕЛЕФОН" : "МОДУЛЬ");
      strcpy(buf, !gps_state ? "ВЫКЛ" : (gps_valid ? "FIX" : "ПОИСК"));
      display.drawTextRightAlign(display.width() - 1, y, buf);

      if (!phone_source && nmea == NULL) {
        y += row_step;
        drawRichTextEllipsized(display, 0, y, display.width(), "GPS-модуль не найден");
      } else if (!gps_state) {
        y += row_step;
        drawRichTextEllipsized(display, 0, y, display.width(), "Нажмите для включения");
      } else {
        y += row_step;
        display.drawTextLeftAlign(0, y, "СПУТН.");
        snprintf(buf, sizeof(buf), "%d", sats >= 0 ? sats : 0);
        display.drawTextRightAlign(display.width() - 1, y, buf);

        if (!gps_valid) {
          y += row_step;
          drawRichTextEllipsized(display, 0, y, display.width(), "Ожидание координат");
        } else {
          const double latitude = phone_source
            ? sensors.node_lat : nmea->getLatitude() / 1000000.0;
          const double longitude = phone_source
            ? sensors.node_lon : nmea->getLongitude() / 1000000.0;
          const double altitude = phone_source
            ? sensors.node_altitude : nmea->getAltitude() / 1000.0;
          y += row_step;
          display.drawTextLeftAlign(0, y, "ШИР");
          snprintf(buf, sizeof(buf), "%.4f", latitude);
          display.drawTextRightAlign(display.width() - 1, y, buf);
          y += row_step;
          display.drawTextLeftAlign(0, y, "ДОЛ");
          snprintf(buf, sizeof(buf), "%.4f", longitude);
          display.drawTextRightAlign(display.width() - 1, y, buf);
          if (display.height() > 64) {
            y += row_step;
            display.drawTextLeftAlign(0, y, "ВЫС");
            snprintf(buf, sizeof(buf), "%.0f м", altitude);
            display.drawTextRightAlign(display.width() - 1, y, buf);
          }
        }
      }
      uiPopFont(display, gps_saved_font);
#endif
#if UI_SENSORS_PAGE == 1
    } else if (_page == HomePage::SENSORS) {
      int y = 18;
      refresh_sensors();
      char buf[30];
      char name[30];
      LPPReader r(sensors_lpp.getBuffer(), sensors_lpp.getSize());

      for (int i = 0; i < sensors_scroll_offset; i++) {
        uint8_t channel, type;
        r.readHeader(channel, type);
        r.skipData(type);
      }

      for (int i = 0; i < (sensors_scroll?UI_RECENT_LIST_SIZE:sensors_nb); i++) {
        uint8_t channel, type;
        if (!r.readHeader(channel, type)) { // reached end, reset
          r.reset();
          r.readHeader(channel, type);
        }

        display.setCursor(0, y);
        float v;
        switch (type) {
          case LPP_GPS: // GPS
            float lat, lon, alt;
            r.readGPS(lat, lon, alt);
            strcpy(name, "GPS"); sprintf(buf, "%.4f %.4f", lat, lon);
            break;
          case LPP_VOLTAGE:
            r.readVoltage(v);
            strcpy(name, "напр"); sprintf(buf, "%6.2f", v);
            break;
          case LPP_CURRENT:
            r.readCurrent(v);
            strcpy(name, "ток"); sprintf(buf, "%.3f", v);
            break;
          case LPP_TEMPERATURE:
            r.readTemperature(v);
            strcpy(name, "темп"); sprintf(buf, "%.2f", v);
            break;
          case LPP_RELATIVE_HUMIDITY:
            r.readRelativeHumidity(v);
            strcpy(name, "влажн"); sprintf(buf, "%.2f", v);
            break;
          case LPP_BAROMETRIC_PRESSURE:
            r.readPressure(v);
            strcpy(name, "давл"); sprintf(buf, "%.2f", v);
            break;
          case LPP_ALTITUDE:
            r.readAltitude(v);
            strcpy(name, "выс"); sprintf(buf, "%.0f", v);
            break;
          case LPP_POWER:
            r.readPower(v);
            strcpy(name, "мощн"); sprintf(buf, "%6.2f", v);
            break;
          default:
            r.skipData(type);
            strcpy(name, "неизв"); sprintf(buf, "");
        }
        display.setCursor(0, y);
        display.print(name);
        display.setCursor(
          display.width()-display.getTextWidth(buf)-1, y
        );
        display.print(buf);
        y = y + 12;
      }
      if (sensors_scroll) sensors_scroll_offset = (sensors_scroll_offset+1)%sensors_nb;
      else sensors_scroll_offset = 0;
#endif
#if UI_ADC_MULTIPLIER_PAGE == 1
    } else if (_page == HomePage::ADC) {
      display.setColor(DisplayDriver::GREEN);
      display.setTextSize(1);
      uint16_t batteryMilliVolts = _task->getBattMilliVolts();
      float multiplier = _adc_edit ? _adc_draft : _task->getAdcMultiplier();
      char adc_buf[18];
      formatAdcMultiplier(adc_buf, sizeof(adc_buf), multiplier);

#if UI_V4_3_OLED_PROFILE
      char battery_line[32];
      char coef_line[32];
      sprintf(battery_line, "АКБ: %u.%02uВ", batteryMilliVolts / 1000, (batteryMilliVolts % 1000) / 10);
      snprintf(coef_line, sizeof(coef_line), "Коэф: %s", adc_buf);
      drawOledCompactMenuPage(display, _adc_edit ? "Калибр. АКБ +/-" : "Калибр. АКБ", battery_line, coef_line,
          _adc_edit ? "+/-; удерж: сохранить" : "удерж: правка; 2x: завод.");
#else
      display.drawTextCentered(display.width() / 2, 14, _adc_edit ? "Калибр. АКБ +/-" : "Калибр. АКБ");
      display.drawTextCentered(display.width() / 2, 24, "по мультиметру");
      display.drawTextCentered(display.width() / 2, 34,
          _adc_edit ? "удерж: сохранить" : "2x: заводской");
      display.setCursor(0, 44);
      sprintf(tmp, "АКБ: %u.%02uВ", batteryMilliVolts / 1000, (batteryMilliVolts % 1000) / 10);
      display.print(tmp);
      display.setCursor(0, 54);
      snprintf(tmp, sizeof(tmp), "Коэф: %s", adc_buf);
      display.print(tmp);
      if (_adc_edit) {
        display.drawTextRightAlign(display.width() - 1, 54, "+/-");
      } else {
        display.drawTextRightAlign(display.width() - 1, 54, PRESS_LABEL);
      }
#endif
#endif
#if UI_LOW_BATTERY_SHUTDOWN_PAGE == 1 && defined(AUTO_SHUTDOWN_MILLIVOLTS)
    } else if (_page == HomePage::LOW_BATT_SHUTDOWN) {
      uint16_t threshold = _task->getLowBatteryShutdownThreshold();
#if UI_V4_3_OLED_PROFILE
      char status_line[32];
      char threshold_line[32];
      snprintf(status_line, sizeof(status_line), "Статус: %s", _task->isLowBatteryShutdownEnabled() ? "ВКЛ" : "ВЫКЛ");
      snprintf(threshold_line, sizeof(threshold_line), "Порог: %u.%02uВ",
          threshold / 1000, (threshold % 1000) / 10);
      drawOledCompactMenuPage(display, "Защита АКБ", status_line, threshold_line, PRESS_LABEL);
#else
      display.setColor(DisplayDriver::GREEN);
      display.setTextSize(1);
      display.drawTextCentered(display.width() / 2, 18, "Защита АКБ");
      display.setCursor(0, 31);
      snprintf(tmp, sizeof(tmp), "Статус: %s", _task->isLowBatteryShutdownEnabled() ? "ВКЛ" : "ВЫКЛ");
      display.print(tmp);
      display.setCursor(0, 42);
      snprintf(tmp, sizeof(tmp), "Порог: %u.%02uВ",
          threshold / 1000, (threshold % 1000) / 10);
      display.print(tmp);
      display.setCursor(0, 53);
      display.print(PRESS_LABEL);
#endif
#endif
    }
#if UI_COMPACT_SETTINGS_MENU == 1
    else if (_page == HomePage::NOTIFY_PICKER) {
      renderNotifyPicker(display);
    }
#if UI_TIMEZONE_PAGE == 1
    else if (_page == HomePage::TIMEZONE_PICKER) {
      renderTimezonePicker(display);
    }
#endif
#endif
#if UI_COMPACT_SETTINGS_MENU == 1 && UI_APPEARANCE_MENU
    else if (_page == HomePage::FONT_PICKER) {
      renderAppearancePicker(display, true);
    } else if (_page == HomePage::THEME_PICKER) {
      renderAppearancePicker(display, false);
    }
#endif
#if UI_SMART_B12_TONE_LIST == 1 && defined(PIN_MSG_TONE)
    else if (_page == HomePage::TONE_PICKER) {
      renderTonePicker(display);
    }
#endif
#if UI_SMART_B11_EXTRAS == 1
    else if (_page == HomePage::DEVICE_STATUS) {
      uint8_t saved_font = uiPushCompactSettingsFont(display);
      display.setColor(DisplayDriver::GREEN);
      drawRichTextCenteredEllipsized(display, display.width() / 2, 14, display.width(), "Состояние");
      int y = display.height() > 64 ? 27 : 28;
      int row_h = display.height() > 64 ? 13 : 12;
      snprintf(tmp, sizeof(tmp), "АКБ %.3fВ  BLE %s",
               _task->getBattMilliVolts() / 1000.0f,
               _task->hasConnection() ? "СВЯЗЬ" : (_task->isBluetoothEnabled() ? "ЖДЁТ" : "ВЫКЛ"));
      display.setColor(DisplayDriver::LIGHT);
      drawRichTextEllipsized(display, 1, y, display.width() - 2, tmp);
      snprintf(tmp, sizeof(tmp), "RSSI %d  SNR %.1f",
               (int)radio_driver.getLastRSSI(), radio_driver.getLastSNR());
      drawRichTextEllipsized(display, 1, y + row_h, display.width() - 2, tmp);
#if ENV_INCLUDE_GPS == 1 || UI_PHONE_GPS == 1
      snprintf(tmp, sizeof(tmp), "GPS %s  FEM %s",
               _task->getGPSState() ? "ВКЛ" : "ВЫКЛ",
#ifdef RADIO_FEM_RXGAIN
               _node_prefs->radio_fem_rxgain ? "ВКЛ" : "ВЫКЛ");
#else
               "НЕТ");
#endif
#elif defined(RADIO_FEM_RXGAIN)
      snprintf(tmp, sizeof(tmp), "FEM %s",
               _node_prefs->radio_fem_rxgain ? "ВКЛ" : "ВЫКЛ");
#else
      snprintf(tmp, sizeof(tmp), "Радио SX1262");
#endif
      drawRichTextEllipsized(display, 1, y + row_h * 2, display.width() - 2, tmp);
      uiPopFont(display, saved_font);
    } else if (_page == HomePage::HARDWARE_TEST) {
      uint8_t saved_font = uiPushCompactSettingsFont(display);
      display.setColor(DisplayDriver::GREEN);
      drawRichTextCenteredEllipsized(display, display.width() / 2, 14, display.width(), "Тест оборудования");
      display.setColor(DisplayDriver::YELLOW);
      snprintf(tmp, sizeof(tmp), "Шаг %u/7: %s", _hardware_test_step,
               _task->getHardwareTestStepName(_hardware_test_step));
      drawRichTextCenteredEllipsized(display, display.width() / 2, 31, display.width() - 2, tmp);
      display.setColor(DisplayDriver::LIGHT);
      drawRichTextCenteredEllipsized(display, display.width() / 2, 45, display.width() - 2, "OK: следующий тест");
      drawRichTextCenteredEllipsized(display, display.width() / 2, 57, display.width() - 2, "< >: назад");
      uiPopFont(display, saved_font);
#if UI_SMART_B12_TONE_LIST != 1
    } else if (_page == HomePage::SETTINGS_TRANSFER) {
      uint8_t saved_font = uiPushCompactSettingsFont(display);
      display.setColor(DisplayDriver::GREEN);
      drawRichTextCenteredEllipsized(display, display.width() / 2, 14, display.width(), "Экспорт / импорт");
      display.setColor(DisplayDriver::LIGHT);
      drawRichTextCenteredEllipsized(display, display.width() / 2, 30, display.width() - 2, "BLE: custom vars");
      display.setColor(DisplayDriver::YELLOW);
      drawRichTextCenteredEllipsized(display, display.width() / 2, 43, display.width() - 2, "ключ smartui");
      display.setColor(DisplayDriver::LIGHT);
      drawRichTextCenteredEllipsized(display, display.width() / 2, 56, display.width() - 2, "копировать / вставить");
      uiPopFont(display, saved_font);
#endif
    }
#endif
    else if (_page == HomePage::SETTINGS) {
#if UI_COMPACT_SETTINGS_MENU == 1
      if (_settings_open) {
        renderCompactSettings(display);
      } else {
        snprintf(tmp, sizeof(tmp), "%u компактных разделов",
                 (unsigned)COMPACT_SETTINGS_GROUP_COUNT);
        drawOledCompactMenuPage(display, "Настройки", tmp,
                                "значения видны сразу", "вход: " PRESS_LABEL);
      }
#else
#if UI_V4_3_OLED_PROFILE
      if (_settings_open) {
        drawOledCompactMenuPage(display, "Настройки", "Назад", "в главное меню", PRESS_LABEL);
      } else {
        drawOledCompactMenuPage(display, "Настройки", "радио / BLE / экран", "сигналы / CH2 / АЦП", "вход: " PRESS_LABEL);
      }
#else
      display.setColor(DisplayDriver::GREEN);
      display.setTextSize(1);
      display.drawTextCentered(display.width() / 2, 18, "Настройки");
      if (_settings_open) {
        display.drawTextCentered(display.width() / 2, 32, "Назад");
        display.drawTextCentered(display.width() / 2, 44, "в главное меню");
        display.drawTextCentered(display.width() / 2, 64 - 11, PRESS_LABEL);
      } else {
        display.drawTextCentered(display.width() / 2, 32, "радио / BLE / экран");
        display.drawTextCentered(display.width() / 2, 44, "сигналы / CH2 / АЦП");
        display.drawTextCentered(display.width() / 2, 64 - 11, "вход: " PRESS_LABEL);
      }
#endif
#endif
    } else if (_page == HomePage::SHUTDOWN) {
      display.setColor(DisplayDriver::GREEN);
      display.setTextSize(1);
      if (_shutdown_init) {
        display.drawTextCentered(display.width() / 2, 34, "засыпаю...");
      } else {
        display.drawXbm((display.width() - 32) / 2, 18, power_icon, 32, 32);
#if UI_V4_3_OLED_PROFILE
        uint8_t small_font = uiPushCompactChromeFont(display);
        drawRichTextCentered(display, display.width() / 2, 52, "сон: " PRESS_LABEL);
        uiPopFont(display, small_font);
#else
        display.drawTextCentered(display.width() / 2, 64 - 11, "сон: " PRESS_LABEL);
#endif
      }
    }
    if (_page == HomePage::CHAT) return UI_CHAT_REFRESH_MILLIS;
    if (_page == HomePage::LINK_TEST) return UI_LINK_TEST_REFRESH_MILLIS;
    if (_page == HomePage::CLOCK) return UI_CLOCK_REFRESH_MILLIS;
    return UI_IDLE_REFRESH_MILLIS;
  }

  bool handleInput(char c) override {
    if (_quick_reply_open) {
#if UI_QUICK_REPLY_KEYBOARD
      if (_quick_keyboard_open) {
        return handleQuickKeyboardInput(c);
      }
#endif
      if (c == KEY_LEFT || c == KEY_PREV) {
        _quick_reply_idx = (_quick_reply_idx + quickReplyMenuCount() - 1) % quickReplyMenuCount();
        return true;
      }
      if (c == KEY_NEXT || c == KEY_RIGHT) {
        _quick_reply_idx = (_quick_reply_idx + 1) % quickReplyMenuCount();
        return true;
      }
      if (c == KEY_ENTER) {
#if UI_QUICK_REPLY_KEYBOARD
        if (_quick_reply_idx == quickReplyKeyboardIndex()) {
          openQuickKeyboard();
          _task->showAlert("Клавиатура", 700);
        } else
#endif
        if (_quick_reply_idx == quickReplyBackIndex()) {
          _quick_reply_open = false;
          _task->showAlert("Ответ закрыт", 800);
        } else if (the_mesh.sendQuickReply(quick_reply_texts[_quick_reply_idx])) {
          _quick_reply_open = false;
          _task->notify(UIEventType::ack);
          _task->showAlert("Ответ отправлен", 900);
        } else {
          _task->showAlert("Ошибка ответа", 1000);
        }
        return true;
      }
    }
#if UI_COMPACT_SETTINGS_MENU == 1
    if (handleCompactSettingsInput(c)) return true;
#endif
    if (c == KEY_LEFT || c == KEY_PREV) {
#if UI_ADC_MULTIPLIER_PAGE == 1
      if (_settings_open && _page == HomePage::ADC && _adc_edit) {
        adjustAdcMultiplier(-getAdcStep(_adc_draft));
        return true;
      }
#endif
      _page = nextVisiblePage(_page, -1);
      if (_settings_open) showPageAlert(_page);
      return true;
    }
    if (c == KEY_NEXT || c == KEY_RIGHT) {
#if UI_ADC_MULTIPLIER_PAGE == 1
      if (_settings_open && _page == HomePage::ADC && _adc_edit) {
        adjustAdcMultiplier(getAdcStep(_adc_draft));
        return true;
      }
#endif
      _page = nextVisiblePage(_page, 1);
      showPageAlert(_page);
      return true;
    }
    if (c == KEY_ENTER && _page == HomePage::SETTINGS) {
#if UI_COMPACT_SETTINGS_MENU == 1
      if (!_settings_open) {
        _settings_open = true;
        _compact_settings_depth = 0;
        _compact_settings_group = 0;
        _compact_settings_cursor = 0;
      }
#else
      if (_settings_open) {
        _settings_open = false;
#if UI_ADC_MULTIPLIER_PAGE == 1
        cancelAdcEdit();
#endif
        _task->showAlert("Настройки закрыты", 800);
      } else {
        _settings_open = true;
        _page = firstSettingsPage();
        showPageAlert(_page);
      }
#endif
      return true;
    }
    if (c == KEY_ENTER && _page == HomePage::CHAT) {
      _quick_reply_open = true;
      _quick_reply_idx = 0;
#if UI_QUICK_REPLY_KEYBOARD
      resetQuickKeyboard();
#endif
      _task->showAlert("Быстрый ответ", 800);
      return true;
    }
    if (c == KEY_ENTER && _settings_open && _page == HomePage::ALERTS) {
      _task->cycleNotifyMode();
      return true;
    }
#ifdef PIN_MSG_ALERT
    if (c == KEY_ENTER && _settings_open && _page == HomePage::ALERT_LED) {
      _task->cycleNotifyLedPin();
      return true;
    }
#endif
#ifdef PIN_MSG_TONE
    if (c == KEY_ENTER && _settings_open && _page == HomePage::ALERT_TONE_PIN) {
      _task->cycleNotifyTonePin();
      return true;
    }
#if UI_TONE_BRIDGE_PAGE == 1
    if (c == KEY_ENTER && _settings_open && _page == HomePage::ALERT_TONE_BRIDGE) {
      _task->toggleNotifyToneBridge();
      return true;
    }
#endif
#endif
    if (c == KEY_ENTER && _settings_open && _page == HomePage::ALERT_VIBE_PIN) {
      _task->cycleNotifyVibePin();
      return true;
    }
#ifdef PIN_MSG_TONE
    if (c == KEY_ENTER && _settings_open && _page == HomePage::ALERT_SOUND) {
      _task->cycleNotifySound();
      return true;
    }
#if UI_TONE_8BIT_PAGE == 1
    if (c == KEY_ENTER && _settings_open && _page == HomePage::ALERT_TONE_STYLE) {
      _task->toggleNotifyTone8Bit();
      return true;
    }
#endif
    if (c == KEY_ENTER && _settings_open && _page == HomePage::ALERT_VOLUME) {
#if UI_TONE_HIGH_DRIVE_PAGE == 1
      _task->toggleNotifyToneHighDrive();
#else
      _task->cycleNotifyToneVolume();
#endif
      return true;
    }
#if UI_TONE_RESONANCE_PAGE == 1
    if (c == KEY_ENTER && _settings_open && _page == HomePage::ALERT_TONE_RESONANCE) {
      _task->cycleNotifyToneResonance();
      return true;
    }
#endif
#endif
    if (c == KEY_ENTER && _page == HomePage::FIRST && the_mesh.getBLEPin() == 0 && _task->getMsgCount() > 0) {
      _task->msgRead(0);
      _task->showAlert("Непроч. очищ.", 800);
      return true;
    }
    if (c == KEY_ENTER && _settings_open && _page == HomePage::LINK_TEST) {
      if (the_mesh.startLinkTest()) {
        _task->showAlert("Опрос путей старт", 900);
      } else {
        _task->showAlert("Нет узлов", 1000);
      }
      return true;
    }
    if (c == KEY_ENTER && _settings_open && _page == HomePage::BLUETOOTH) {
      if (_task->isBluetoothEnabled()) {  // toggle Bluetooth on/off
        _task->disableBluetooth();
      } else {
        _task->enableBluetooth();
      }
      return true;
    }
    if (c == KEY_ENTER && _settings_open && _page == HomePage::MSG_POPUP) {
      _task->toggleMsgPopups();
      return true;
    }
    if (c == KEY_ENTER && _settings_open && _page == HomePage::IMPORTANT_NOTIFY) {
      _task->cycleImportantNotifyMode();
      return true;
    }
#if UI_OFFLINE_DM_LED_PAGE == 1 && defined(PIN_MSG_ALERT)
    if (c == KEY_ENTER && _settings_open && _page == HomePage::OFFLINE_DM_LED) {
      _task->toggleOfflineDmLed();
      return true;
    }
    if (c == KEY_ENTER && _settings_open && _page == HomePage::BLE_DM_LED) {
      _task->toggleBleDmLed();
      return true;
    }
#endif
#if UI_BOARD_LEDS_PAGE == 1
    if (c == KEY_ENTER && _settings_open && _page == HomePage::BOARD_LEDS) {
      _task->toggleBoardLeds();
      return true;
    }
#endif
#if UI_CLIENT_REPEAT_PAGE == 1
    if (c == KEY_ENTER && _settings_open && _page == HomePage::CLIENT_REPEAT) {
      the_mesh.toggleClientRepeat();
      _task->showAlert(the_mesh.isClientRepeatEnabled() ? "Ретранс: ВКЛ" : "Ретранс: ВЫКЛ", 900);
      return true;
    }
#endif
#if UI_APPEARANCE_MENU
#if UI_UNREAD_LED_PAGE == 1
    if (c == KEY_ENTER && _settings_open && _page == HomePage::UNREAD_LED) {
      _task->toggleUnreadLed();
      return true;
    }
#endif
    if (c == KEY_ENTER && _settings_open && _page == HomePage::UI_FONT) {
      _task->cycleUiFont();
      return true;
    }
    if (c == KEY_ENTER && _settings_open && _page == HomePage::UI_THEME) {
      _task->cycleUiTheme();
      return true;
    }
#if UI_COLOR_APPEARANCE_MENU
    if (c == KEY_ENTER && _settings_open && _page == HomePage::UI_TOP_COLOR) {
      _task->cycleUiTopColor();
      return true;
    }
    if (c == KEY_ENTER && _settings_open && _page == HomePage::UI_BOTTOM_COLOR) {
      _task->cycleUiBottomColor();
      return true;
    }
#endif
#if UI_BACKLIGHT_TIMEOUT_PAGE == 1
    if (c == KEY_ENTER && _settings_open && _page == HomePage::BACKLIGHT_TIMEOUT) {
      _task->cycleBacklightTimeout();
      return true;
    }
#endif
#endif
    if (c == KEY_ENTER && _page == HomePage::ADVERT) {
      _task->notify(UIEventType::ack);
      if (the_mesh.advert()) {
        _task->showAlert("Анонс отправлен", 1000);
      } else {
        _task->showAlert("Ошибка анонса", 1000);
      }
      return true;
    }
#if UI_AUTO_ADVERT_PAGE == 1
    if (c == KEY_ENTER && _settings_open && _page == HomePage::ADVERT_TIMER) {
      the_mesh.cycleAutoAdvertInterval();
      char alert[32];
      snprintf(alert, sizeof(alert), "Анонс: %s", autoAdvertLabel());
      _task->showAlert(alert, 900);
      return true;
    }
#endif
#if UI_CH2_RELAY_PAGE == 1
    if (c == KEY_ENTER && _settings_open && _page == HomePage::CH2_RELAY) {
      the_mesh.cycleCh2Mode();
      char alert[32];
      snprintf(alert, sizeof(alert), "CH2: %s", the_mesh.getCh2ModeName());
      _task->showAlert(alert, 900);
      return true;
    }
#endif
#if ENV_INCLUDE_GPS == 1 || UI_PHONE_GPS == 1
    if (c == KEY_ENTER && _settings_open && _page == HomePage::GPS) {
      _task->toggleGPS();
      return true;
    }
#endif
#if UI_SENSORS_PAGE == 1
    if (c == KEY_ENTER && _page == HomePage::SENSORS) {
      _task->toggleGPS();
      next_sensors_refresh=0;
      return true;
    }
#endif
#if UI_ADC_MULTIPLIER_PAGE == 1
    if (c == KEY_ENTER && _settings_open && _page == HomePage::ADC) {
      if (_adc_edit) {
        if (_task->setAdcMultiplier(_adc_draft, true)) {
#if UI_SMART_B11_EXTRAS == 1
          _node_prefs->smart_profile_id = SMART_PROFILE_CUSTOM;
          the_mesh.savePrefs();
#endif
          _task->showAlert("АЦП сохранен", 800);
        } else {
          _task->showAlert("АЦП недоступен", 1000);
        }
        _adc_edit = false;
      } else {
        _adc_draft = _task->getAdcMultiplier();
        if (_adc_draft <= 0.0f) {
          _task->showAlert("АЦП недоступен", 1000);
        } else {
          _adc_edit = true;
        }
      }
      return true;
    }
#endif
#if UI_LOW_BATTERY_SHUTDOWN_PAGE == 1 && defined(AUTO_SHUTDOWN_MILLIVOLTS)
    if (c == KEY_ENTER && _settings_open && _page == HomePage::LOW_BATT_SHUTDOWN) {
      _task->toggleLowBatteryShutdown();
      return true;
    }
#endif
    if (c == KEY_ENTER && _page == HomePage::SHUTDOWN) {
      _shutdown_init = true;  // need to wait for button to be released
      return true;
    }
    return false;
  }
};

class MsgPreviewScreen : public UIScreen {
  UITask* _task;
  mesh::RTCClock* _rtc;

  struct MsgEntry {
    uint32_t timestamp;
    uint32_t arrived_ms;
    uint8_t notify_flags;
    char sender[62];
    char msg[UI_UNREAD_TEXT_LEN];
  };
  #define MAX_UNREAD_MSGS   UI_UNREAD_MSG_LIMIT
  int num_unread;
  int head = MAX_UNREAD_MSGS - 1; // index of latest unread message
  MsgEntry unread[MAX_UNREAD_MSGS];
  int scroll_entry = -1;
  uint32_t scroll_arrived_ms = 0;
  int scroll_px = 0;
  int scroll_dir = 1;
  unsigned long scroll_pause_until = 0;
  int cached_total_h = 0;
  int cached_entry = -1;
  int cached_body_w = 0;
  uint8_t cached_font = 0xFF;
  uint32_t cached_arrived_ms = 0;
  int cached_unread_count = -1;
  // Direct frames dismissed locally still remain in MyMesh::offline_queue.
  // Count them so a later BLE sync acknowledges those frames without deleting
  // the next still-visible preview a second time.
  uint16_t direct_sync_debt = 0;
  char fitted_line[80];
  char count_label[12];
  char header_line[40];

  int unreadIndexFromNewest(int offset) const {
    return (head + MAX_UNREAD_MSGS - offset) % MAX_UNREAD_MSGS;
  }

  bool isDirectPreview(const MsgEntry& entry) const {
    return (entry.notify_flags & UI_MSG_FLAG_DIRECT) != 0;
  }

  bool senderWasShownFromNewer(int offset) const {
    const MsgEntry& entry = unread[unreadIndexFromNewest(offset)];
    for (int newer = 0; newer < offset; newer++) {
      const MsgEntry& candidate = unread[unreadIndexFromNewest(newer)];
      if (isDirectPreview(candidate) && strcmp(candidate.sender, entry.sender) == 0) return true;
    }
    return false;
  }

  int senderMessageCount(const char* sender) const {
    int count = 0;
    for (int offset = 0; offset < num_unread; offset++) {
      const MsgEntry& entry = unread[unreadIndexFromNewest(offset)];
      if (isDirectPreview(entry) && strcmp(entry.sender, sender) == 0) count++;
    }
    return count;
  }

  int uniqueDirectSenderCount() const {
    int count = 0;
    for (int offset = 0; offset < num_unread; offset++) {
      const MsgEntry& entry = unread[unreadIndexFromNewest(offset)];
      if (isDirectPreview(entry) && !senderWasShownFromNewer(offset)) count++;
    }
    return count;
  }

  void appendFittedEllipsis(DisplayDriver& display, int max_width) {
    const char* ellipsis = "...";
    const int ellipsis_w = unreadTextWidth(display, ellipsis);
    if (ellipsis_w > max_width) return;

    while (fitted_line[0] != 0 && unreadTextWidth(display, fitted_line) + ellipsis_w > max_width) {
      size_t cut = strlen(fitted_line) - 1;
      while (cut > 0 && (((uint8_t)fitted_line[cut] & 0xC0) == 0x80)) cut--;
      fitted_line[cut] = 0;
      size_t len = strlen(fitted_line);
      while (len > 0 && fitted_line[len - 1] == ' ') fitted_line[--len] = 0;
    }

    size_t len = strlen(fitted_line);
    if (len + 4 <= sizeof(fitted_line)) memcpy(&fitted_line[len], ellipsis, 4);
  }

  void drawFittedUnreadText(DisplayDriver& display, int x, int y, int max_width,
                            const char* text, bool bold = false) {
    fitted_line[0] = 0;
    if (text == NULL || text[0] == 0 || max_width <= 0) return;

    display.setBold(bold);
    const char* remainder = text;
    if (!nextWrappedUnreadLine(display, remainder, fitted_line, sizeof(fitted_line), max_width)) {
      display.setBold(false);
      return;
    }
    if (*remainder != 0) appendFittedEllipsis(display, max_width);

    drawUnreadTextLine(display, x, y, fitted_line, bold);
    display.setBold(false);
  }

  int renderUnreadSenders(DisplayDriver& display, int y_start, int scroll, bool draw) {
    int y = y_start - scroll;
    int line_h = display.getTextLineHeight();
    if (line_h < 1) line_h = 1;
    const int row_gap = display.height() > 64 ? 2 : 1;
    const int body_x = UI_T114_APPEARANCE_MENU ? 12 : 0;
    int body_w = display.width() - body_x - UI_UNREAD_RIGHT_GUARD_PX;
    if (body_w < 24) body_w = display.width() - body_x;
    const bool show_snippets = display.height() - y_start >= line_h * 2 + row_gap;

    for (int offset = 0; offset < num_unread; offset++) {
      const MsgEntry& entry = unread[unreadIndexFromNewest(offset)];
      if (!isDirectPreview(entry) || senderWasShownFromNewer(offset)) continue;

      snprintf(count_label, sizeof(count_label), "(%d)", senderMessageCount(entry.sender));
      const int count_w = unreadTextWidth(display, count_label);
      int name_w = body_w - count_w - 3;
      if (name_w < 1) name_w = body_w;
      if (draw && y >= y_start && y < display.height()) {
        display.setColor(DisplayDriver::YELLOW);
        drawFittedUnreadText(display, body_x, y, name_w, entry.sender);
        if (count_w < body_w) {
          display.setColor(DisplayDriver::GREEN);
          drawUnreadTextLine(display, body_x + body_w - count_w, y, count_label);
        }
      }
      y += line_h;

      if (show_snippets && entry.msg[0] != 0) {
        const int snippet_x = body_x + 6;
        const int snippet_w = body_w - 6;
        if (draw && y >= y_start && y < display.height()) {
          display.setColor(DisplayDriver::LIGHT);
          drawFittedUnreadText(display, snippet_x, y, snippet_w, entry.msg);
        }
        y += line_h;
      }

      y += row_gap;
    }

    return y - y_start + scroll;
  }

public:
  MsgPreviewScreen(UITask* task, mesh::RTCClock* rtc) : _task(task), _rtc(rtc) { num_unread = 0; }

  bool hasUnreadPreviews() const {
    return num_unread > 0;
  }

  int unreadPreviewCount() const {
    return num_unread;
  }

  void addDirectSyncDebt(uint16_t count) {
#if UI_UNREAD_DIRECT_ONLY
    uint32_t total = (uint32_t)direct_sync_debt + count;
    direct_sync_debt = total > 0xFFFFU ? 0xFFFFU : (uint16_t)total;
#else
    (void)count;
#endif
  }

  bool consumeDirectSyncDebt() {
#if UI_UNREAD_DIRECT_ONLY
    if (direct_sync_debt > 0) {
      direct_sync_debt--;
      return true;
    }
#endif
    return false;
  }

  bool removeOldestPreview(bool locally_dismissed = false) {
    if (num_unread <= 0) return false;
    if (locally_dismissed) addDirectSyncDebt(1);
    num_unread--;
    cached_entry = -1;
    cached_unread_count = -1;
    scroll_entry = -1;
    return true;
  }

  void clearPreviews(bool locally_dismissed = false) {
    if (locally_dismissed && num_unread > 0) addDirectSyncDebt((uint16_t)num_unread);
    num_unread = 0;
    cached_entry = -1;
    cached_unread_count = -1;
    scroll_entry = -1;
  }

  void addPreview(uint8_t path_len, const char* from_name, const char* msg, uint8_t notify_flags) {
    if (num_unread >= MAX_UNREAD_MSGS) {
      // The oldest direct frame is still queued for BLE, but no longer fits on
      // the node's small preview ring.  Treat the eviction like a local hide.
      addDirectSyncDebt(1);
    }
    head = (head + 1) % MAX_UNREAD_MSGS;
    if (num_unread < MAX_UNREAD_MSGS) num_unread++;

    auto p = &unread[head];
    p->timestamp = _rtc->getCurrentTime();
    p->arrived_ms = millis();
    p->notify_flags = notify_flags & (UI_MSG_FLAG_DIRECT | UI_MSG_FLAG_MENTION | UI_MSG_FLAG_IMPORTANT);
    StrHelper::strncpy(p->sender, from_name != NULL && from_name[0] != 0 ? from_name : "Без имени",
                       sizeof(p->sender));

    const char* preview_msg = msg != NULL ? msg : "";
    bool ch2_msg = msg != NULL && strncmp(msg, "ch2 ", 4) == 0;
    if (ch2_msg) {
      preview_msg = msg + 4;
    }
    (void)path_len;
    StrHelper::strncpy(p->msg, preview_msg, sizeof(p->msg));
    cached_entry = -1;
    cached_unread_count = -1;
  }

  int render(DisplayDriver& display) override {
    uint8_t saved_font = uiPushCompactSettingsFont(display);
    int line_h = display.getTextLineHeight();
    if (line_h < 1) line_h = 1;

    snprintf(header_line, sizeof(header_line), "ЛС: %d чел / %d", uniqueDirectSenderCount(), num_unread);
    display.setColor(DisplayDriver::GREEN);
    drawFittedUnreadText(display, 0, 0, display.width() - 1, header_line);

#if !UI_T096_PREMIUM_TFT
    display.drawRect(0, line_h + 1, display.width(), 1);  // horiz line
#endif
    const int content_y = line_h + 3;
    const int body_x = UI_T114_APPEARANCE_MENU ? 12 : 0;
    int body_w = display.width() - body_x - UI_UNREAD_RIGHT_GUARD_PX;
    if (body_w < 24) body_w = display.width() - body_x;
    const uint32_t latest_arrived_ms = num_unread > 0 ? unread[head].arrived_ms : 0;
    if (cached_entry != head || cached_arrived_ms != latest_arrived_ms ||
        cached_unread_count != num_unread ||
        cached_font != display.getUiFont() || cached_body_w != body_w) {
      cached_total_h = renderUnreadSenders(display, content_y, 0, false);
      cached_entry = head;
      cached_arrived_ms = latest_arrived_ms;
      cached_unread_count = num_unread;
      cached_font = display.getUiFont();
      cached_body_w = body_w;
    }
    int total_h = cached_total_h;
    int visible_h = display.height() - content_y - 1;
    if (visible_h < 1) visible_h = 1;
    int max_scroll = total_h > visible_h ? total_h - visible_h : 0;
    const bool needs_scroll = max_scroll > 0;

    if (scroll_entry != head || scroll_arrived_ms != latest_arrived_ms) {
      scroll_entry = head;
      scroll_arrived_ms = latest_arrived_ms;
      scroll_px = 0;
      scroll_dir = 1;
      scroll_pause_until = millis() + UI_CHAT_EDGE_PAUSE_MILLIS;
    }
    if (scroll_px > max_scroll) scroll_px = max_scroll;
    if (scroll_px < 0) scroll_px = 0;

    renderUnreadSenders(display, content_y, scroll_px, true);

    if (needs_scroll) {
      unsigned long now = millis();
      if (smartui::deadlineReached((uint32_t)now, (uint32_t)scroll_pause_until)) {
        scroll_px += scroll_dir * UI_CHAT_SCROLL_STEP_PX;
        if (scroll_px <= 0) {
          scroll_px = 0;
          scroll_dir = 1;
          scroll_pause_until = now + UI_CHAT_EDGE_PAUSE_MILLIS;
        } else if (scroll_px >= max_scroll) {
          scroll_px = max_scroll;
          scroll_dir = -1;
          scroll_pause_until = now + UI_CHAT_EDGE_PAUSE_MILLIS;
        }
      }
    }

    uiPopFont(display, saved_font);

#if AUTO_OFF_MILLIS==0 // probably e-ink
    return needs_scroll ? UI_EINK_SCROLL_REFRESH_MILLIS : 10000; // 10 s
#else
    return needs_scroll ? UI_CHAT_REFRESH_MILLIS : 1000;  // next render after 1000 ms
#endif
  }

  bool handleInput(char c) override {
    if (c == KEY_NEXT || c == KEY_RIGHT) {
      removeOldestPreview(true);
      if (num_unread == 0) {
        _task->msgRead(0);
      } else {
        _task->msgRead(num_unread);
      }
      return true;
    }
    if (c == KEY_ENTER) {
      clearPreviews(true);
      _task->msgRead(0);
      _task->showAlert("Непроч. очищ.", 800);
      return true;
    }
    return false;
  }
};

void UITask::begin(DisplayDriver* display, SensorManager* sensors, NodePrefs* node_prefs) {
  _display = display;
  _sensors = sensors;
  ui_started_at = millis();
  _uptime_accumulated_ms = 0;
  _uptime_last_millis = (uint32_t)ui_started_at;
  next_batt_chck = ui_started_at + LOW_BATTERY_SHUTDOWN_BOOT_GRACE_MILLIS;
  _low_batt_strikes = 0;
  _last_connection_state = hasConnection();
  _ble_state_changed_at = ui_started_at;
  _popup_pending = false;
  _display_recover_until = 0;
  _display_recover_next = 0;
  _display_recover_reset_to_clock = false;
  _button_wake_pending = false;
  _button_wake_pending_until = 0;
  _important_notify_active = false;
  _important_msg_flags = UI_MSG_FLAG_NONE;
  _important_notify_led_next = 0;
  _important_notify_tone_next = 0;
  _important_notify_vibe_next = 0;
  _important_notify_led_burst_step = 0;
  _important_notify_tone_burst_step = 0;
  _important_notify_vibe_burst_step = 0;
  _night_prompt_expires = 0;
  _night_prompt_active = false;
  _night_prompt_yes = true;
  invalidateBatteryCache();
  extendAutoOff();

#if defined(PIN_USER_BTN)
  user_btn.begin();
#if UI_BUTTON_WAKE_IRQ
  ui_button_wake_irq_pending = false;
  attachInterrupt(PIN_USER_BTN, uiButtonWakeIrqHandler, FALLING);
#endif
#endif
#if defined(PIN_USER_BTN_ANA)
  analog_btn.begin();
#endif

  _node_prefs = node_prefs;

  if (_display != NULL) {
    if (_node_prefs != NULL) {
#if UI_T096_PREMIUM_TFT
      if (_node_prefs->ui_font >= UI_T096_FONT_PROFILE_COUNT) _node_prefs->ui_font = 0;
      _display->setUiFont(uiOledFontForRole(_node_prefs->ui_font, UI_OLED_FONT_M));
      _display->setTextSize(uiOledTextSizeForRole(UI_OLED_FONT_M));
#elif UI_V4_3_OLED_PROFILE
      _node_prefs->ui_font = uiOledStyleFromFont(_node_prefs->ui_font);
      _display->setUiFont(uiOledFontForRole(_node_prefs->ui_font, UI_OLED_FONT_M));
      _display->setTextSize(uiOledTextSizeForRole(UI_OLED_FONT_M));
#else
      if (_node_prefs->ui_font >= _display->getUiFontCount()) _node_prefs->ui_font = 0;
      _display->setUiFont(_node_prefs->ui_font);
      _display->setTextSize(1);
#endif
      _display->setUiTheme(_node_prefs->ui_theme);
    }
    _display->turnOn();
  }

#ifdef PIN_BUZZER
  buzzer.begin();
  buzzer.quiet(_node_prefs->buzzer_quiet);
#endif

#ifdef PIN_VIBRATION
  vibration.begin();
#endif

#ifdef PIN_MSG_ALERT
  configureMsgAlertPin(_node_prefs ? _node_prefs->notify_gpio_pin : PIN_MSG_ALERT);
  _msg_alert_until = 0;
#endif
#ifdef PIN_MSG_TONE
  configureMsgTonePin(_node_prefs ? _node_prefs->notify_tone_pin : PIN_MSG_TONE);
  int tone_pin = getMsgTonePin();
  pinMode(tone_pin, OUTPUT);
  noTone(tone_pin);
#ifdef PIN_MSG_ALERT
  if (tone_pin == getMsgAlertPin()) {
    digitalWrite(getMsgAlertPin(), PIN_MSG_ALERT_INACTIVE);
  } else {
    digitalWrite(tone_pin, LOW);
  }
#else
  digitalWrite(tone_pin, LOW);
#endif
  _msg_tone_active = false;
  _msg_tone_step = 0;
  _msg_tone_fx_remaining = 0;
  _msg_tone_test_frequency = 0;
  _msg_tone_test_duration = 700;
  _msg_tone_fx_phase = 0;
  _msg_tone_next = 0;
#endif
  configureMsgVibePin(_node_prefs ? _node_prefs->notify_vibe_pin : -1);
  applyBoardLedsState();

  ui_started_at = millis();
  _last_activity_ms = ui_started_at;
  resetHourlyStats(ui_started_at);
  _alert_expiry = 0;

  splash = new SplashScreen(this);
  home = new HomeScreen(this, &rtc_clock, sensors, node_prefs);
#if UI_EINK_IDLE_SCREENSAVER
  idle_saver = new PaperIdleClockScreen(this, &rtc_clock);
#else
  idle_saver = NULL;
#endif
  msg_preview = new MsgPreviewScreen(this, &rtc_clock);
  setCurrScreen(splash);
}

void UITask::showAlert(const char* text, int duration_millis) {
  snprintf(_alert, sizeof(_alert), "%s", text ? text : "");
  _alert_expiry = millis() + duration_millis;
}

void UITask::invalidateBatteryCache() {
  _battery_milli_volts = 0;
  _battery_next_sample = 0;
  _battery_sample_valid = false;
}

uint16_t UITask::getBattMilliVolts() const {
  unsigned long now = millis();
  if (!_battery_sample_valid ||
      smartui::deadlineReached((uint32_t)now, (uint32_t)_battery_next_sample)) {
    uint16_t sample = _board->getBattMilliVolts();
    if (!_battery_sample_valid || _battery_milli_volts == 0 || sample == 0 || UI_BATTERY_SMOOTHING_SAMPLES <= 1) {
      _battery_milli_volts = sample;
    } else {
      uint32_t smoothed = ((uint32_t)_battery_milli_volts * (UI_BATTERY_SMOOTHING_SAMPLES - 1)) + sample;
      _battery_milli_volts = (uint16_t)((smoothed + (UI_BATTERY_SMOOTHING_SAMPLES / 2)) / UI_BATTERY_SMOOTHING_SAMPLES);
    }
    _battery_sample_valid = true;
    _battery_next_sample = now + UI_BATTERY_SAMPLE_MILLIS;
  }
  return _battery_milli_volts;
}

smartui::BatteryReading UITask::readSafetyBattery() const {
  if (_board == NULL) return smartui::BatteryReading();
  // This path is intentionally independent of the slow display EMA.  Three
  // immediate board-level readings suppress one-off ADC noise while retaining
  // a prompt response to a genuine voltage collapse.
  const uint16_t a = _board->getBattMilliVolts();
  const uint16_t b = _board->getBattMilliVolts();
  const uint16_t c = _board->getBattMilliVolts();
  return smartui::medianBatteryReading(a, b, c);
}

bool UITask::hasTrustedTime() const {
  return rtc_clock.isTimeTrusted() &&
         meshRtcTimestampPlausible(rtc_clock.getCurrentTime());
}

int16_t UITask::getTimezoneOffsetMinutes() const {
  int32_t minutes = getTimezoneOffsetSeconds() / 60L;
  if (minutes < -720) minutes = -720;
  if (minutes > 840) minutes = 840;
  return (int16_t)minutes;
}

bool UITask::setTimezoneOffsetMinutes(int16_t minutes, bool save) {
  if (_node_prefs == NULL || minutes < -720 || minutes > 840 ||
      (minutes % 30) != 0) return false;
  const int16_t previous_minutes = _node_prefs->timezone_offset_minutes;
  _node_prefs->timezone_offset_minutes = minutes;
  if (save) {
    if (!the_mesh.savePrefs()) {
      _node_prefs->timezone_offset_minutes = previous_minutes;
      _next_refresh = 0;
      return false;
    }
    notify(UIEventType::ack);
  }
  _next_refresh = 0;
  return true;
}

int32_t UITask::getTimezoneOffsetSeconds() const {
  int32_t seconds = (int32_t)UI_TIMEZONE_OFFSET_FROM_PREFS(_node_prefs);
  if (seconds < -12L * 60L * 60L) seconds = -12L * 60L * 60L;
  if (seconds > 14L * 60L * 60L) seconds = 14L * 60L * 60L;
  return seconds;
}

uint32_t UITask::getLocalClockTime(uint32_t utc_time) const {
  return uiApplyTimezoneOffset(utc_time, getTimezoneOffsetSeconds());
}

float UITask::getMCUTemperature() const {
  return _board != NULL ? _board->getMCUTemperature() : NAN;
}

void UITask::resetHourlyStats(unsigned long now) {
  memset(_hourly_stats, 0, sizeof(_hourly_stats));
  _hourly_stats_index = 0;
  _hourly_stats_used = 1;
  _hourly_stats_started = now;
  _hourly_bucket_started = now;
  _hourly_last_tx_air_ms = the_mesh.getTotalAirTime();
  _hourly_last_rx_air_ms = the_mesh.getReceiveAirTime();
  _hourly_last_busy_ms = the_mesh.getChannelBusyTime();
}

void UITask::updateHourlyStats() {
  unsigned long now = millis();
  if (_hourly_stats_used == 0 || _hourly_bucket_started == 0) {
    resetHourlyStats(now);
    return;
  }

  unsigned long bucket_age = now - _hourly_bucket_started;
  if (bucket_age >= UI_STATS_WINDOW_MILLIS) {
    resetHourlyStats(now);
    return;
  }

  while (bucket_age >= UI_STATS_BUCKET_MILLIS) {
    _hourly_stats_index = (_hourly_stats_index + 1) % UI_STATS_BUCKET_COUNT;
    memset(&_hourly_stats[_hourly_stats_index], 0, sizeof(_hourly_stats[_hourly_stats_index]));
    if (_hourly_stats_used < UI_STATS_BUCKET_COUNT) _hourly_stats_used++;
    _hourly_bucket_started += UI_STATS_BUCKET_MILLIS;
    bucket_age = now - _hourly_bucket_started;
  }

  unsigned long tx_now = the_mesh.getTotalAirTime();
  unsigned long rx_now = the_mesh.getReceiveAirTime();
  unsigned long busy_now = the_mesh.getChannelBusyTime();

  UIHourlyStatsBucket& bucket = _hourly_stats[_hourly_stats_index];
  bucket.tx_air_ms += (uint32_t)(tx_now - _hourly_last_tx_air_ms);
  bucket.rx_air_ms += (uint32_t)(rx_now - _hourly_last_rx_air_ms);
  bucket.busy_ms += (uint32_t)(busy_now - _hourly_last_busy_ms);

  _hourly_last_tx_air_ms = tx_now;
  _hourly_last_rx_air_ms = rx_now;
  _hourly_last_busy_ms = busy_now;
}

void UITask::addHourlyMessage() {
  updateHourlyStats();
  UIHourlyStatsBucket& bucket = _hourly_stats[_hourly_stats_index];
  if (bucket.msg_count < 65535) bucket.msg_count++;
}

void UITask::updateHourlyMessageWindow() {
  updateHourlyStats();
}

void UITask::updateUptime(uint32_t now) {
  // Unsigned subtraction deliberately carries across the 32-bit millis wrap.
  _uptime_accumulated_ms += (uint32_t)(now - _uptime_last_millis);
  _uptime_last_millis = now;
}

bool UITask::isNotifyGpioBlocked(int pin) const {
  return isNotifyGpioPinBlockedByBuild(pin);
}

bool UITask::isBoardLedPin(int pin) const {
  if (pin < 0) return false;
#ifdef PIN_LED
  if (PIN_LED >= 0 && pin == PIN_LED) return true;
#endif
#ifdef LED_BUILTIN
  if (LED_BUILTIN >= 0 && pin == LED_BUILTIN) return true;
#endif
#ifdef PIN_STATUS_LED
  if (PIN_STATUS_LED >= 0 && pin == PIN_STATUS_LED) return true;
#endif
#ifdef P_LORA_TX_LED
  if (P_LORA_TX_LED >= 0 && pin == P_LORA_TX_LED) return true;
#endif
  return false;
}

void UITask::setBoardLedPinOff(int pin) {
  if (pin < 0) return;
  pinMode(pin, OUTPUT);
  digitalWrite(pin, BOARD_LED_INACTIVE_STATE);
}

bool UITask::areBoardLedsEnabled() const {
  return _node_prefs == NULL || _node_prefs->board_leds_enabled != 0;
}

void UITask::applyBoardLedsState() {
  bool enabled = areBoardLedsEnabled();
  meshcoreSetBoardLedsEnabled(enabled);
  if (enabled) return;

#ifdef PIN_MSG_ALERT
  if (isBoardLedPin(getMsgAlertPin())) {
    digitalWrite(getMsgAlertPin(), PIN_MSG_ALERT_INACTIVE);
    _msg_alert_until = 0;
  }
#endif
#ifdef PIN_MSG_TONE
  if (isBoardLedPin(getMsgTonePin())) {
    noTone(getMsgTonePin());
    setBoardLedPinOff(getMsgTonePin());
    _msg_tone_active = false;
    _msg_tone_step = 0;
    _msg_tone_fx_remaining = 0;
    _msg_tone_fx_phase = 0;
    _msg_tone_next = 0;
    _msg_tone_off = 0;
  }
#endif
#ifdef PIN_STATUS_LED
  setBoardLedPinOff(PIN_STATUS_LED);
#endif
#ifdef P_LORA_TX_LED
  setBoardLedPinOff(P_LORA_TX_LED);
#endif
#ifdef PIN_LED
  setBoardLedPinOff(PIN_LED);
#endif
#ifdef LED_BUILTIN
  setBoardLedPinOff(LED_BUILTIN);
#endif
}

void UITask::toggleBoardLeds() {
  the_mesh.toggleBoardLeds();
  applyBoardLedsState();
  showAlert(areBoardLedsEnabled() ? "LED платы: ВКЛ" : "LED платы: ВЫКЛ", 900);
}

bool UITask::shouldHoldLightSleepLock() const {
#if !UI_IMPORTANT_NOTIFY_HOLD_SLEEP_LOCK
  if (false) {}
#else
  if (_important_notify_active) return true;
#endif
  if (_display != NULL && _display->isOn()) return true;
  const uint32_t now = (uint32_t)millis();
  if (smartui::optionalDeadlinePending(now, (uint32_t)_display_wake_lock_until)) return true;
#if UI_DISPLAY_RECOVER_WINDOW_MS > 0
  if (smartui::optionalDeadlinePending(now, (uint32_t)_display_recover_until)) return true;
#endif
#if UI_BUTTON_WAKE_LATCH_MS > 0
  if (smartui::optionalDeadlinePending(now, (uint32_t)_button_wake_pending_until)) return true;
#endif
  return smartui::optionalDeadlinePending(now, (uint32_t)_alert_expiry);
}

bool UITask::areMsgPopupsEnabled() const {
  return _node_prefs == NULL || _node_prefs->msg_popup_enabled != 0;
}

void UITask::toggleMsgPopups() {
  the_mesh.toggleMsgPopups();
  showAlert(areMsgPopupsEnabled() ? "Всплыв. сообщ.: ВКЛ" : "Всплыв. сообщ.: ВЫКЛ", 900);
  _next_refresh = 0;
}

bool UITask::isUnreadLedEnabled() const {
  return _node_prefs == NULL || _node_prefs->unread_led_enabled != 0;
}

void UITask::toggleUnreadLed() {
  the_mesh.toggleUnreadLed();
#ifdef PIN_MSG_ALERT
  if (!isUnreadLedEnabled()) {
    digitalWrite(getMsgAlertPin(), PIN_MSG_ALERT_INACTIVE);
    _msg_alert_until = 0;
  }
#endif
#if defined(PIN_MSG_ALERT) && defined(PIN_MSG_TONE)
  if (!isUnreadLedEnabled() && _msg_tone_active && getMsgTonePin() == getMsgAlertPin()) {
    silenceMsgTonePin(getMsgTonePin());
    _msg_tone_active = false;
    _msg_tone_step = 0;
    _msg_tone_fx_remaining = 0;
    _msg_tone_fx_phase = 0;
    _msg_tone_next = 0;
    _msg_tone_off = 0;
  }
#endif
  showAlert(isUnreadLedEnabled() ? "Непроч. LED: ВКЛ" : "Непроч. LED: ВЫКЛ", 900);
}

bool UITask::isOfflineDmLedEnabled() const {
  return _node_prefs == NULL || _node_prefs->offline_dm_led_enabled != 0;
}

void UITask::toggleOfflineDmLed() {
  if (_node_prefs == NULL) return;

  _node_prefs->offline_dm_led_enabled = _node_prefs->offline_dm_led_enabled ? 0 : 1;
  the_mesh.savePrefs();

#ifdef PIN_MSG_ALERT
  if (!isOfflineDmLedEnabled() && !hasConnection() && (_important_msg_flags & UI_MSG_FLAG_DIRECT)) {
    digitalWrite(getMsgAlertPin(), PIN_MSG_ALERT_INACTIVE);
    _msg_alert_until = 0;
    _important_notify_led_next = 0;
  }
#endif
  showAlert(isOfflineDmLedEnabled() ? "LED ЛС без BLE: ВКЛ" : "LED ЛС без BLE: ВЫКЛ", 900);
  _next_refresh = 0;
}

bool UITask::isBleDmLedEnabled() const {
  return _node_prefs == NULL || _node_prefs->ble_dm_led_enabled != 0;
}

void UITask::toggleBleDmLed() {
  if (_node_prefs == NULL) return;

  _node_prefs->ble_dm_led_enabled = _node_prefs->ble_dm_led_enabled ? 0 : 1;
  the_mesh.savePrefs();

#ifdef PIN_MSG_ALERT
  if (!isBleDmLedEnabled() && hasConnection() && (_important_msg_flags & UI_MSG_FLAG_DIRECT)) {
    digitalWrite(getMsgAlertPin(), PIN_MSG_ALERT_INACTIVE);
    _msg_alert_until = 0;
    _important_notify_led_next = 0;
  }
#endif
  showAlert(isBleDmLedEnabled() ? "LED ЛС при BLE: ВКЛ" : "LED ЛС при BLE: ВЫКЛ", 900);
  _next_refresh = 0;
}

bool UITask::isLowBatteryShutdownEnabled() const {
#if defined(AUTO_SHUTDOWN_MILLIVOLTS)
  if (_node_prefs == NULL) return LOW_BATTERY_SHUTDOWN_DEFAULT_ENABLED != 0;
  return _node_prefs->low_battery_shutdown_enabled != 0;
#else
  return false;
#endif
}

uint16_t UITask::getLowBatteryShutdownThreshold() const {
#if defined(AUTO_SHUTDOWN_MILLIVOLTS)
  return smartui::batteryShutdownThreshold(isLowBatteryShutdownEnabled(),
      AUTO_SHUTDOWN_MILLIVOLTS, LOW_BATTERY_SHUTDOWN_FLOOR_MILLIVOLTS);
#else
  return 0;
#endif
}

void UITask::toggleLowBatteryShutdown() {
#if defined(AUTO_SHUTDOWN_MILLIVOLTS)
  if (_node_prefs == NULL) return;

  _node_prefs->low_battery_shutdown_enabled = _node_prefs->low_battery_shutdown_enabled ? 0 : 1;
  _low_batt_strikes = 0;  // Start a fresh confirmation sequence for the new threshold.
  the_mesh.savePrefs();
  char alert[48];
  uint16_t threshold = getLowBatteryShutdownThreshold();
  if (threshold) {
    snprintf(alert, sizeof(alert), "%s: %u.%uВ",
             isLowBatteryShutdownEnabled() ? "Защита" : "Резерв",
             threshold / 1000, (threshold % 1000) / 100);
  } else {
    snprintf(alert, sizeof(alert), "Защита АКБ: ВЫКЛ");
  }
  showAlert(alert, 1100);
  _next_refresh = 0;
#endif
}

uint8_t UITask::getUiFontCount() const {
#if UI_T096_PREMIUM_TFT
  return UI_T096_FONT_VISIBLE_COUNT;
#elif UI_V4_3_OLED_PROFILE
  return UI_OLED_STYLE_COUNT;
#else
  return _display ? _display->getUiFontCount() : 1;
#endif
}

uint8_t UITask::getUiThemeCount() const {
  return _display ? _display->getUiThemeCount() : 1;
}

uint8_t UITask::getUiFontChoiceIndex() const {
  uint8_t count = getUiFontCount();
  if (count == 0) return 0;
  uint8_t font = _node_prefs ? _node_prefs->ui_font : (_display ? _display->getUiFont() : 0);
#if UI_T096_PREMIUM_TFT
  font = uiT096NormalizeFontProfile(font);
  if (font < UI_T096_FONT_VISIBLE_FIRST || font >= UI_T096_FONT_PROFILE_COUNT) return 0;
  return font - UI_T096_FONT_VISIBLE_FIRST;
#elif UI_V4_3_OLED_PROFILE
  font = uiOledStyleFromFont(font);
  return font < count ? font : 0;
#else
  return font < count ? font : 0;
#endif
}

uint8_t UITask::getUiThemeChoiceIndex() const {
  uint8_t count = getUiThemeCount();
  if (count == 0) return 0;
  uint8_t theme = _node_prefs ? _node_prefs->ui_theme : (_display ? _display->getUiTheme() : 0);
  return theme < count ? theme : 0;
}

bool UITask::hasUiFontChoices() const {
  return getUiFontCount() > 1;
}

bool UITask::hasUiThemeChoices() const {
  return getUiThemeCount() > 1;
}

const char* UITask::getUiFontName() const {
  if (_display == NULL) return "Стандарт";
  uint8_t font = _node_prefs ? _node_prefs->ui_font : _display->getUiFont();
#if UI_T096_PREMIUM_TFT
  font = uiT096NormalizeFontProfile(font);
  return _display->getUiFontName(font);
#elif UI_V4_3_OLED_PROFILE
  return uiOledStyleName(font);
#else
  return _display->getUiFontName(font);
#endif
}

const char* UITask::getUiFontChoiceName(uint8_t choice) const {
  if (_display == NULL) return "Стандарт";
  uint8_t count = getUiFontCount();
  if (count == 0) return "Стандарт";
  if (choice >= count) choice = 0;
#if UI_T096_PREMIUM_TFT
  return _display->getUiFontName(UI_T096_FONT_VISIBLE_FIRST + choice);
#elif UI_V4_3_OLED_PROFILE
  return uiOledStyleName(choice);
#else
  return _display->getUiFontName(choice);
#endif
}

const char* UITask::getUiThemeName() const {
  if (_display == NULL) return "Стандарт";
  uint8_t theme = _node_prefs ? _node_prefs->ui_theme : _display->getUiTheme();
  return _display->getUiThemeName(theme);
}

const char* UITask::getUiThemeChoiceName(uint8_t choice) const {
  if (_display == NULL) return "Стандарт";
  uint8_t count = getUiThemeCount();
  if (count == 0) return "Стандарт";
  if (choice >= count) choice = 0;
  return _display->getUiThemeName(choice);
}

const char* UITask::getUiTopColorName() const {
  return uiSemanticColorName(_node_prefs ? _node_prefs->ui_top_color : 1);
}

const char* UITask::getUiBottomColorName() const {
  return uiSemanticColorName(_node_prefs ? _node_prefs->ui_bottom_color : 0);
}

ColorVal UITask::getUiTopColor() const {
  return uiSemanticColor(_node_prefs ? _node_prefs->ui_top_color : 1);
}

ColorVal UITask::getUiBottomColor() const {
  return uiSemanticColor(_node_prefs ? _node_prefs->ui_bottom_color : 0);
}

void UITask::setUiFontChoice(uint8_t choice) {
  if (_display == NULL || _node_prefs == NULL) return;
  uint8_t count = getUiFontCount();
  if (count == 0) count = 1;
  if (choice >= count) choice = 0;
#if UI_T096_PREMIUM_TFT
  _node_prefs->ui_font = UI_T096_FONT_VISIBLE_FIRST + choice;
#else
  _node_prefs->ui_font = choice;
#endif
#if UI_T096_PREMIUM_TFT
  _display->setUiFont(uiOledFontForRole(_node_prefs->ui_font, UI_OLED_FONT_M));
  _display->setTextSize(uiOledTextSizeForRole(UI_OLED_FONT_M));
#elif UI_V4_3_OLED_PROFILE
  _display->setUiFont(uiOledFontForRole(_node_prefs->ui_font, UI_OLED_FONT_M));
  _display->setTextSize(uiOledTextSizeForRole(UI_OLED_FONT_M));
#else
  _display->setUiFont(_node_prefs->ui_font);
  _display->setTextSize(1);
#endif
  the_mesh.savePrefs();

  char alert[56];
  snprintf(alert, sizeof(alert), "Шрифт: %s", getUiFontName());
  showAlert(alert, 1000);
}

void UITask::setUiThemeChoice(uint8_t choice) {
  if (_display == NULL || _node_prefs == NULL) return;
  uint8_t count = getUiThemeCount();
  if (count == 0) count = 1;
  if (choice >= count) choice = 0;
  _node_prefs->ui_theme = choice;
  _display->setUiTheme(_node_prefs->ui_theme);
  the_mesh.savePrefs();

  char alert[56];
  snprintf(alert, sizeof(alert), "Цвет: %s", _display->getUiThemeName(_node_prefs->ui_theme));
  showAlert(alert, 1000);
}

void UITask::cycleUiFont() {
  uint8_t count = getUiFontCount();
  if (count == 0) count = 1;
  setUiFontChoice((getUiFontChoiceIndex() + 1) % count);
}

void UITask::cycleUiTheme() {
  uint8_t count = getUiThemeCount();
  if (count == 0) count = 1;
  setUiThemeChoice((getUiThemeChoiceIndex() + 1) % count);
}

void UITask::cycleUiTopColor() {
  if (_node_prefs == NULL) return;
  _node_prefs->ui_top_color = (_node_prefs->ui_top_color + 1) % 6;
  the_mesh.savePrefs();

  char alert[40];
  snprintf(alert, sizeof(alert), "Верх: %s", getUiTopColorName());
  showAlert(alert, 900);
}

void UITask::cycleUiBottomColor() {
  if (_node_prefs == NULL) return;
  _node_prefs->ui_bottom_color = (_node_prefs->ui_bottom_color + 1) % 6;
  the_mesh.savePrefs();

  char alert[40];
  snprintf(alert, sizeof(alert), "Низ: %s", getUiBottomColorName());
  showAlert(alert, 900);
}

const char* UITask::getBacklightTimeoutName() const {
  uint8_t idx = _node_prefs ? _node_prefs->backlight_timeout_idx : 0;
  switch (idx) {
    case 1: return "30 сек";
    case 2: return "1 мин";
    case 0:
    default: return "15 сек";
  }
}

uint32_t UITask::getBacklightTimeoutMillis() const {
  uint8_t idx = _node_prefs ? _node_prefs->backlight_timeout_idx : 0;
  switch (idx) {
    case 1: return 30000UL;
    case 2: return 60000UL;
    case 0:
    default: return 15000UL;
  }
}

void UITask::cycleBacklightTimeout() {
  if (_node_prefs == NULL) return;
  _node_prefs->backlight_timeout_idx = (_node_prefs->backlight_timeout_idx + 1) % 3;
  the_mesh.savePrefs();
  extendAutoOff();

  char alert[40];
  snprintf(alert, sizeof(alert), "Подсветка: %s", getBacklightTimeoutName());
  showAlert(alert, 900);
}

const char* UITask::getSmartProfileName() const {
  uint8_t profile = _node_prefs ? _node_prefs->smart_profile_id : SMART_PROFILE_CUSTOM;
  switch (profile) {
    case SMART_PROFILE_QUIET: return "Тихо";
    case SMART_PROFILE_OUTDOOR: return "Улица";
    case SMART_PROFILE_NIGHT: return "Ночь";
    default: return "Свой";
  }
}

void UITask::applyImportedPrefs() {
  if (_node_prefs == NULL) return;
  stopNotifyOutputs();

  if (_display != NULL) {
#if UI_T096_PREMIUM_TFT
    _node_prefs->ui_font = uiT096NormalizeFontProfile(_node_prefs->ui_font);
    _display->setUiFont(uiOledFontForRole(_node_prefs->ui_font, UI_OLED_FONT_M));
    _display->setTextSize(uiOledTextSizeForRole(UI_OLED_FONT_M));
#elif UI_V4_3_OLED_PROFILE
    _node_prefs->ui_font = uiOledStyleFromFont(_node_prefs->ui_font);
    _display->setUiFont(uiOledFontForRole(_node_prefs->ui_font, UI_OLED_FONT_M));
    _display->setTextSize(uiOledTextSizeForRole(UI_OLED_FONT_M));
#else
    if (_node_prefs->ui_font >= _display->getUiFontCount()) _node_prefs->ui_font = 0;
    _display->setUiFont(_node_prefs->ui_font);
    _display->setTextSize(1);
#endif
    uint8_t theme_count = _display->getUiThemeCount();
    if (theme_count == 0) theme_count = 1;
    _node_prefs->ui_theme %= theme_count;
    _display->setUiTheme(_node_prefs->ui_theme);
  }

#ifdef PIN_MSG_ALERT
  configureMsgAlertPin(_node_prefs->notify_gpio_pin);
#endif
#ifdef PIN_MSG_TONE
  configureMsgTonePin(_node_prefs->notify_tone_pin);
#endif
  configureMsgVibePin(_node_prefs->notify_vibe_pin);
  _board->setAdcMultiplier(_node_prefs->adc_multiplier);
#if ENV_INCLUDE_GPS == 1 || UI_PHONE_GPS == 1
  if (_sensors != NULL) {
    _sensors->setSettingValue("gps",
      (_node_prefs->gps_source == GPS_SOURCE_HW && _node_prefs->gps_enabled) ? "1" : "0");
  }
#endif
  the_mesh.applyUiPrefsRuntime();
  applyBoardLedsState();
  invalidateBatteryCache();
  extendAutoOff();
  _next_refresh = 0;
}

void UITask::cycleSmartProfile() {
#if UI_SMART_B11_EXTRAS == 1
  if (_node_prefs == NULL) return;
  uint8_t profile = _node_prefs->smart_profile_id;
  if (profile < SMART_PROFILE_QUIET || profile >= SMART_PROFILE_NIGHT) {
    profile = SMART_PROFILE_QUIET;
  } else {
    profile++;
  }
  _node_prefs->smart_profile_id = profile;

  uint8_t supported = getSupportedNotifyMode();
  if (profile == SMART_PROFILE_QUIET) {
    _node_prefs->notifications_muted = 0;
    _node_prefs->notify_mode = supported & NOTIFY_MODE_GPIO;
    _node_prefs->important_notify_mode = supported & NOTIFY_MODE_GPIO;
    _node_prefs->backlight_timeout_idx = 0;
  } else if (profile == SMART_PROFILE_OUTDOOR) {
    _node_prefs->notifications_muted = 0;
    _node_prefs->notify_mode = supported;
    _node_prefs->important_notify_mode = supported;
    _node_prefs->board_leds_enabled = 1;
    _node_prefs->backlight_timeout_idx = 2;
#if UI_TONE_HIGH_DRIVE_PAGE == 1
    _node_prefs->notify_tone_high_drive_enabled = 1;
#endif
  } else if (profile == SMART_PROFILE_NIGHT) {
    _node_prefs->notifications_muted = 1;
    _node_prefs->board_leds_enabled = 0;
    _node_prefs->backlight_timeout_idx = 0;
#if UI_T096_PREMIUM_TFT
    _node_prefs->ui_theme = 1;
#endif
  }

  applyImportedPrefs();
  the_mesh.savePrefs();
  char alert[40];
  snprintf(alert, sizeof(alert), "Профиль: %s", getSmartProfileName());
  showAlert(alert, 1000);
#endif
}

const char* UITask::getHardwareTestStepName(uint8_t step) const {
  switch (step) {
    case 1: return "Свет";
    case 2: return "Звук";
    case 3: return "Вибро";
    case 4: return "GPS";
    case 5: return "АКБ / АЦП";
    case 6: return "FEM / LNA";
    case 7: return "Готово";
    default: return "Старт";
  }
}

void UITask::runHardwareTestStep(uint8_t step) {
#if UI_SMART_B11_EXTRAS == 1
  char alert[48];
  switch (step) {
    case 1:
#ifdef PIN_MSG_ALERT
      triggerMsgAlert();
      showAlert("Тест света", 900);
#else
      showAlert("Свет недоступен", 900);
#endif
      break;
    case 2:
#ifdef PIN_MSG_TONE
      startNotifyToneTest(getNotifyToneResonanceHz());
      showAlert("Тест звука", 900);
#else
      showAlert("Звук недоступен", 900);
#endif
      break;
    case 3:
      if (getMsgVibePin() >= 0) {
        triggerMsgVibe();
        showAlert("Тест вибро", 900);
      } else {
        showAlert("Вибро не задано", 900);
      }
      break;
    case 4:
#if ENV_INCLUDE_GPS == 1 || UI_PHONE_GPS == 1
      showAlert(getGPSState() ? "GPS: ВКЛ" : "GPS: ВЫКЛ", 900);
#else
      showAlert("GPS недоступен", 900);
#endif
      break;
    case 5:
      snprintf(alert, sizeof(alert), "АКБ: %.3f В", getBattMilliVolts() / 1000.0f);
      showAlert(alert, 1000);
      break;
    case 6:
      if (_board->canControlLoRaFemLna()) {
        showAlert(_board->isLoRaFemLnaEnabled() ? "FEM LNA: ВКЛ" : "FEM LNA: ВЫКЛ", 1000);
      } else {
        showAlert("FEM: нет управления", 1000);
      }
      break;
    case 7:
      showAlert("Тест завершён", 900);
      break;
    default:
      showAlert("OK: следующий тест", 900);
      break;
  }
#else
  (void)step;
#endif
}

uint16_t UITask::getHourlyMsgCount() {
  UIHourlyStatsSnapshot stats;
  getHourlyStats(stats);
  return stats.msg_count;
}

uint8_t UITask::getHourlyMsgWindowMinutes() {
  UIHourlyStatsSnapshot stats;
  getHourlyStats(stats);
  uint8_t mins = stats.elapsed_ms / 60000UL;
  return mins > 60 ? 60 : mins;
}

void UITask::getHourlyStats(UIHourlyStatsSnapshot& out) {
  updateHourlyStats();
  memset(&out, 0, sizeof(out));

  uint32_t msg_sum = 0;
  for (uint8_t i = 0; i < UI_STATS_BUCKET_COUNT; i++) {
    out.busy_ms += _hourly_stats[i].busy_ms;
    out.tx_air_ms += _hourly_stats[i].tx_air_ms;
    out.rx_air_ms += _hourly_stats[i].rx_air_ms;
    msg_sum += _hourly_stats[i].msg_count;
  }

  unsigned long now = millis();
  uint32_t elapsed = _hourly_stats_started == 0 ? 0 : (uint32_t)(now - _hourly_stats_started);
  if (elapsed > UI_STATS_WINDOW_MILLIS) elapsed = UI_STATS_WINDOW_MILLIS;
  if (elapsed < 1000) elapsed = 1000;
  out.elapsed_ms = elapsed;
  out.msg_count = msg_sum > 65535 ? 65535 : (uint16_t)msg_sum;
}

uint8_t UITask::getSupportedNotifyMode() const {
  uint8_t mode = NOTIFY_MODE_SILENT;
#ifdef PIN_MSG_ALERT
  if (!isNotifyGpioBlocked(getMsgAlertPin())) {
    mode |= NOTIFY_MODE_GPIO;
  }
#endif
#ifdef PIN_MSG_TONE
  if (!isNotifyGpioBlocked(getMsgTonePin())) {
    mode |= NOTIFY_MODE_TONE;
  }
#endif
  int vibe_pin = getMsgVibePin();
  if (vibe_pin >= 0 && !isNotifyGpioBlocked(vibe_pin)) {
    mode |= NOTIFY_MODE_VIBE;
  }
  return mode;
}

uint8_t UITask::getNotifyMode() const {
  if (_node_prefs == NULL) return NOTIFY_MODE_SILENT;
  return _node_prefs->notify_mode & getSupportedNotifyMode();
}

const char* UITask::getNotifyModeName() const {
  switch (getNotifyMode()) {
    case NOTIFY_MODE_GPIO:
      return "Свет";
    case NOTIFY_MODE_TONE:
      return "Зумер";
    case NOTIFY_MODE_VIBE:
      return "Вибро";
    case NOTIFY_MODE_GPIO | NOTIFY_MODE_TONE:
      return "Оба";
    case NOTIFY_MODE_GPIO | NOTIFY_MODE_VIBE:
      return "Свет+вибро";
    case NOTIFY_MODE_TONE | NOTIFY_MODE_VIBE:
      return "Звук+вибро";
    case NOTIFY_MODE_GPIO | NOTIFY_MODE_TONE | NOTIFY_MODE_VIBE:
      return "Все";
    case NOTIFY_MODE_SILENT:
    default:
      return "Тихо";
  }
}

int UITask::getNotifyLedPin() const {
#ifdef PIN_MSG_ALERT
  int pin = getMsgAlertPin();
  return isNotifyGpioBlocked(pin) ? -1 : pin;
#else
  return -1;
#endif
}

int UITask::getNotifyTonePin() const {
#ifdef PIN_MSG_TONE
  int pin = getMsgTonePin();
  return isNotifyGpioBlocked(pin) ? -1 : pin;
#else
  return -1;
#endif
}

int UITask::getNotifyVibePin() const {
  int pin = getMsgVibePin();
  return isNotifyGpioBlocked(pin) ? -1 : pin;
}

const char* UITask::getNotifySoundName() const {
#ifdef PIN_MSG_TONE
  uint8_t tone_id = _node_prefs ? _node_prefs->notify_tone_system_id : 0;
  if (tone_id >= notify_tone_count) tone_id = 0;
  return notify_tones[tone_id].name;
#else
  return "нет";
#endif
}

const char* UITask::getNotifyDmSoundName() const {
#if UI_SMART_B12_TONE_LIST == 1
  return getNotifySoundName();
#else
#ifdef PIN_MSG_TONE
  uint8_t tone_id = _node_prefs ? _node_prefs->notify_tone_dm_id : 0;
  if (tone_id >= notify_tone_count) tone_id = 0;
  return notify_tones[tone_id].name;
#else
  return "нет";
#endif
#endif
}

const char* UITask::getNotifyMentionSoundName() const {
#if UI_SMART_B12_TONE_LIST == 1
  return getNotifySoundName();
#else
#ifdef PIN_MSG_TONE
  uint8_t tone_id = _node_prefs ? _node_prefs->notify_tone_mention_id : 0;
  if (tone_id >= notify_tone_count) tone_id = 0;
  return notify_tones[tone_id].name;
#else
  return "нет";
#endif
#endif
}

const char* UITask::getNotifySystemSoundName() const {
  return getNotifySoundName();
}

uint8_t UITask::getNotifyToneCount() const {
#ifdef PIN_MSG_TONE
  return notify_tone_count;
#else
  return 0;
#endif
}

uint8_t UITask::getNotifyToneId() const {
#ifdef PIN_MSG_TONE
  uint8_t tone_id = _node_prefs ? _node_prefs->notify_tone_system_id : 0;
  return tone_id < notify_tone_count ? tone_id : 0;
#else
  return 0;
#endif
}

const char* UITask::getNotifyToneName(uint8_t tone_id) const {
#ifdef PIN_MSG_TONE
  if (tone_id >= notify_tone_count) tone_id = 0;
  return notify_tones[tone_id].name;
#else
  (void)tone_id;
  return "нет";
#endif
}

void UITask::setCommonNotifyTone(uint8_t tone_id) {
#ifdef PIN_MSG_TONE
  if (_node_prefs == NULL || tone_id >= notify_tone_count) return;
  bool changed = _node_prefs->notify_tone_id != tone_id ||
                 _node_prefs->notify_tone_system_id != tone_id ||
                 _node_prefs->notify_tone_dm_id != tone_id ||
                 _node_prefs->notify_tone_mention_id != tone_id;
  _node_prefs->notify_tone_id = tone_id;
  _node_prefs->notify_tone_system_id = tone_id;
  _node_prefs->notify_tone_dm_id = tone_id;
  _node_prefs->notify_tone_mention_id = tone_id;
  if (changed) the_mesh.savePrefs();

  char alert[48];
  snprintf(alert, sizeof(alert), "Мелодия: %s", getNotifyToneName(tone_id));
  showAlert(alert, 900);
  startMsgTone(tone_id);
#else
  (void)tone_id;
#endif
}

uint8_t UITask::getNotifyToneVolume() const {
#ifdef PIN_MSG_TONE
#if UI_TONE_HIGH_DRIVE_PAGE == 1
  return 10;
#else
  uint8_t volume = _node_prefs ? _node_prefs->notify_tone_volume : 10;
  if (volume == 0 || volume > 10) volume = 10;
  return volume;
#endif
#else
  return 0;
#endif
}

bool UITask::isNotifyTone8BitEnabled() const {
#if UI_TONE_8BIT_PAGE == 1 && defined(PIN_MSG_TONE)
  return _node_prefs != NULL && _node_prefs->notify_tone_8bit_enabled != 0;
#else
  return false;
#endif
}

const char* UITask::getNotifyToneStyleName() const {
  return isNotifyTone8BitEnabled() ? "8-bit" : "Обычный";
}

bool UITask::isNotifyToneHighDriveEnabled() const {
#if UI_TONE_HIGH_DRIVE_PAGE == 1 && defined(PIN_MSG_TONE)
  return _node_prefs != NULL && _node_prefs->notify_tone_high_drive_enabled != 0;
#else
  return false;
#endif
}

const char* UITask::getNotifyToneDriveName() const {
  return isNotifyToneHighDriveEnabled() ? "МАКСИМУМ" : "ОБЫЧНАЯ";
}

uint16_t UITask::getNotifyToneResonanceHz() const {
#if UI_TONE_RESONANCE_PAGE == 1 && defined(PIN_MSG_TONE)
  uint16_t frequency = _node_prefs ? _node_prefs->notify_tone_resonance_hz : DEFAULT_NOTIFY_TONE_RESONANCE_HZ;
  if (frequency < 1800 || frequency > 4200) frequency = DEFAULT_NOTIFY_TONE_RESONANCE_HZ;
  return frequency;
#else
  return DEFAULT_NOTIFY_TONE_RESONANCE_HZ;
#endif
}

bool UITask::isNotifyToneBridgeEnabled() const {
#if UI_TONE_BRIDGE_PAGE == 1 && defined(PIN_MSG_TONE)
  return _node_prefs != NULL && _node_prefs->notify_tone_bridge_enabled != 0;
#else
  return false;
#endif
}

int UITask::getNotifyToneBridgePin() const {
#if UI_TONE_BRIDGE_PAGE == 1 && defined(DEFAULT_NOTIFY_TONE_BRIDGE_PIN)
  return DEFAULT_NOTIFY_TONE_BRIDGE_PIN;
#else
  return -1;
#endif
}

#ifdef PIN_MSG_TONE
bool UITask::isToneBridgePin(int pin) const {
#if UI_TONE_BRIDGE_PAGE == 1
  if (!isNotifyToneBridgeEnabled()) return false;
  return pin == DEFAULT_NOTIFY_TONE_PIN || pin == DEFAULT_NOTIFY_TONE_BRIDGE_PIN;
#else
  (void)pin;
  return false;
#endif
}
#endif

uint8_t UITask::getImportantNotifyMode() const {
  if (_node_prefs == NULL) return NOTIFY_MODE_SILENT;
  return _node_prefs->important_notify_mode & getSupportedNotifyMode();
}

const char* UITask::getImportantNotifyModeName() const {
  switch (getImportantNotifyMode()) {
    case NOTIFY_MODE_GPIO:
      return "Свет";
    case NOTIFY_MODE_TONE:
      return "Зумер";
    case NOTIFY_MODE_VIBE:
      return "Вибро";
    case NOTIFY_MODE_GPIO | NOTIFY_MODE_TONE:
      return "Оба";
    case NOTIFY_MODE_GPIO | NOTIFY_MODE_VIBE:
      return "Свет+вибро";
    case NOTIFY_MODE_TONE | NOTIFY_MODE_VIBE:
      return "Звук+вибро";
    case NOTIFY_MODE_GPIO | NOTIFY_MODE_TONE | NOTIFY_MODE_VIBE:
      return "Все";
    case NOTIFY_MODE_SILENT:
    default:
      return "Тихо";
  }
}

void UITask::cycleImportantNotifyMode() {
  if (_node_prefs == NULL) return;

  uint8_t supported = getSupportedNotifyMode();
  uint8_t mode = getImportantNotifyMode();
  uint8_t next = uiNextNotifyMode(mode, supported);

  _node_prefs->important_notify_mode = next;
  if (next == NOTIFY_MODE_SILENT) {
    clearImportantNotify();
  }
  the_mesh.savePrefs();

  char alert[48];
  snprintf(alert, sizeof(alert), "ЛС/упомин.: %s", getImportantNotifyModeName());
  showAlert(alert, 900);

#if defined(PIN_MSG_ALERT) && defined(PIN_MSG_TONE)
  if ((next & NOTIFY_MODE_GPIO) && !((next & NOTIFY_MODE_TONE) && getMsgTonePin() == getMsgAlertPin())) {
    triggerMsgAlert();
  }
#elif defined(PIN_MSG_ALERT)
  if (next & NOTIFY_MODE_GPIO) {
    triggerMsgAlert();
  }
#endif
#ifdef PIN_MSG_TONE
  if (next & NOTIFY_MODE_TONE) {
    startMsgTone();
  }
#endif
  if (next & NOTIFY_MODE_VIBE) {
    triggerMsgVibe();
  }
}

void UITask::cycleNotifyLedPin() {
#ifdef PIN_MSG_ALERT
#if UI_NOTIFY_GPIO_SELECT
  int next;
#if UI_TONE_BRIDGE_PAGE == 1
  next = isNotifyToneBridgeEnabled()
      ? getNextNotifyGpioPinExcept(getMsgAlertPin(), DEFAULT_NOTIFY_TONE_PIN, DEFAULT_NOTIFY_TONE_BRIDGE_PIN)
      : getNextNotifyGpioPin(getMsgAlertPin());
#else
  next = getNextNotifyGpioPin(getMsgAlertPin());
#endif
  setNotifyLedPin(next);
#else
  showAlert("Свет фикс", 900);
#endif
#endif
}

void UITask::cycleNotifyTonePin() {
#ifdef PIN_MSG_TONE
#if UI_NOTIFY_GPIO_SELECT
#if UI_TONE_BRIDGE_PAGE == 1
  if (isNotifyToneBridgeEnabled()) {
    char fixed_alert[40];
    snprintf(fixed_alert, sizeof(fixed_alert), "Мост фикс: D%d-D%d",
             DEFAULT_NOTIFY_TONE_PIN, DEFAULT_NOTIFY_TONE_BRIDGE_PIN);
    showAlert(fixed_alert, 1100);
    startMsgTone();
    return;
  }
#endif
  int next = getNextNotifyGpioPin(getMsgTonePin());
  setNotifyTonePin(next);
#else
  showAlert("Зумер фикс", 900);
#endif
#endif
}

void UITask::cycleNotifyVibePin() {
#if UI_NOTIFY_GPIO_SELECT
  int current = getMsgVibePin();
  int next;
#if UI_TONE_BRIDGE_PAGE == 1
  next = isNotifyToneBridgeEnabled()
      ? getNextNotifyGpioPinExcept(current, DEFAULT_NOTIFY_TONE_PIN, DEFAULT_NOTIFY_TONE_BRIDGE_PIN)
      : getNextNotifyGpioPin(current);
#else
  next = getNextNotifyGpioPin(current);
#endif
  setNotifyVibePin(next);
#else
  showAlert("Вибро фикс", 900);
#endif
}

void UITask::setNotifyLedPin(int pin) {
#if defined(PIN_MSG_ALERT) && UI_NOTIFY_GPIO_SELECT
  if (!_node_prefs || !isNotifyGpioPinAllowed(pin) || isNotifyGpioPinBlockedByBuild(pin)) return;
#if UI_TONE_BRIDGE_PAGE == 1
  if (isNotifyToneBridgeEnabled() &&
      (pin == DEFAULT_NOTIFY_TONE_PIN || pin == DEFAULT_NOTIFY_TONE_BRIDGE_PIN)) return;
#endif
  if (getMsgAlertPin() == pin) return;
  configureMsgAlertPin(pin);
  _node_prefs->notify_gpio_pin = pin;
#if UI_SMART_B11_EXTRAS == 1 && UI_SMART_B12_TONE_LIST != 1
  _node_prefs->smart_profile_id = SMART_PROFILE_CUSTOM;
#endif
  the_mesh.savePrefs();
  char alert[32];
  snprintf(alert, sizeof(alert), "Свет: D%d", pin);
  showAlert(alert, 900);
  triggerMsgAlert();
#else
  (void)pin;
#endif
}

void UITask::setNotifyTonePin(int pin) {
#if defined(PIN_MSG_TONE) && UI_NOTIFY_GPIO_SELECT
  if (!_node_prefs || !isNotifyGpioPinAllowed(pin) || isNotifyGpioPinBlockedByBuild(pin)) return;
  if (isNotifyToneBridgeEnabled() || getMsgTonePin() == pin) return;
  configureMsgTonePin(pin);
  _node_prefs->notify_tone_pin = pin;
#if UI_SMART_B11_EXTRAS == 1 && UI_SMART_B12_TONE_LIST != 1
  _node_prefs->smart_profile_id = SMART_PROFILE_CUSTOM;
#endif
  the_mesh.savePrefs();
  char alert[32];
  snprintf(alert, sizeof(alert), "Зумер: D%d", pin);
  showAlert(alert, 900);
  startMsgTone();
#else
  (void)pin;
#endif
}

void UITask::setNotifyVibePin(int pin) {
#if UI_NOTIFY_GPIO_SELECT
  if (!_node_prefs || !isNotifyGpioPinAllowed(pin) || isNotifyGpioPinBlockedByBuild(pin)) return;
#if UI_TONE_BRIDGE_PAGE == 1
  if (isNotifyToneBridgeEnabled() &&
      (pin == DEFAULT_NOTIFY_TONE_PIN || pin == DEFAULT_NOTIFY_TONE_BRIDGE_PIN)) return;
#endif
  if (getMsgVibePin() == pin) return;
  configureMsgVibePin(pin);
  _node_prefs->notify_vibe_pin = pin;
#if UI_SMART_B11_EXTRAS == 1 && UI_SMART_B12_TONE_LIST != 1
  _node_prefs->smart_profile_id = SMART_PROFILE_CUSTOM;
#endif
  the_mesh.savePrefs();
  char alert[32];
  snprintf(alert, sizeof(alert), "Вибро: D%d", pin);
  showAlert(alert, 900);
  triggerMsgVibe();
#else
  (void)pin;
#endif
}

void UITask::cycleNotifySound() {
  cycleNotifySystemSound();
}

void UITask::cycleNotifyDmSound() {
#ifdef PIN_MSG_TONE
  if (_node_prefs == NULL || notify_tone_count == 0) return;
#if UI_SMART_B12_TONE_LIST == 1
  setCommonNotifyTone((getNotifyToneId() + 1) % notify_tone_count);
#else
  _node_prefs->notify_tone_dm_id = (_node_prefs->notify_tone_dm_id + 1) % notify_tone_count;
  the_mesh.savePrefs();

  char alert[48];
  snprintf(alert, sizeof(alert), "ЛС: %s", getNotifyDmSoundName());
  showAlert(alert, 900);
  startMsgTone(_node_prefs->notify_tone_dm_id);
#endif
#endif
}

void UITask::cycleNotifyMentionSound() {
#ifdef PIN_MSG_TONE
  if (_node_prefs == NULL || notify_tone_count == 0) return;
#if UI_SMART_B12_TONE_LIST == 1
  setCommonNotifyTone((getNotifyToneId() + 1) % notify_tone_count);
#else
  _node_prefs->notify_tone_mention_id = (_node_prefs->notify_tone_mention_id + 1) % notify_tone_count;
  the_mesh.savePrefs();

  char alert[48];
  snprintf(alert, sizeof(alert), "Упомин.: %s", getNotifyMentionSoundName());
  showAlert(alert, 900);
  startMsgTone(_node_prefs->notify_tone_mention_id);
#endif
#endif
}

void UITask::cycleNotifySystemSound() {
#ifdef PIN_MSG_TONE
  if (_node_prefs == NULL || notify_tone_count == 0) return;
#if UI_SMART_B12_TONE_LIST == 1
  setCommonNotifyTone((getNotifyToneId() + 1) % notify_tone_count);
#else
  _node_prefs->notify_tone_system_id = (_node_prefs->notify_tone_system_id + 1) % notify_tone_count;
  _node_prefs->notify_tone_id = _node_prefs->notify_tone_system_id;
  the_mesh.savePrefs();

  char alert[48];
  snprintf(alert, sizeof(alert), "Система: %s", getNotifySystemSoundName());
  showAlert(alert, 900);
  startMsgTone(_node_prefs->notify_tone_system_id);
#endif
#endif
}

void UITask::cycleNotifyToneVolume() {
#ifdef PIN_MSG_TONE
  uint8_t volume = getNotifyToneVolume();
  volume = volume >= 10 ? 1 : volume + 1;
  setNotifyToneVolume(volume);
#endif
}

void UITask::setNotifyToneVolume(uint8_t volume) {
#if defined(PIN_MSG_TONE) && UI_TONE_HIGH_DRIVE_PAGE != 1
  if (!_node_prefs || volume < 1 || volume > 10 || getNotifyToneVolume() == volume) return;
  _node_prefs->notify_tone_volume = volume;
#if UI_SMART_B11_EXTRAS == 1 && UI_SMART_B12_TONE_LIST != 1
  _node_prefs->smart_profile_id = SMART_PROFILE_CUSTOM;
#endif
  the_mesh.savePrefs();

  char alert[32];
  snprintf(alert, sizeof(alert), "Громк: %u/10", volume);
  showAlert(alert, 900);
  startMsgTone();
#else
  (void)volume;
#endif
}

void UITask::toggleNotifyTone8Bit() {
#if UI_TONE_8BIT_PAGE == 1 && defined(PIN_MSG_TONE)
  if (_node_prefs == NULL) return;
  stopNotifyOutputs();
  _node_prefs->notify_tone_8bit_enabled = isNotifyTone8BitEnabled() ? 0 : 1;
  the_mesh.savePrefs();
  showAlert(isNotifyTone8BitEnabled() ? "Звук: 8-bit" : "Звук: обычный", 900);
  startMsgTone();
#endif
}

void UITask::toggleNotifyToneHighDrive() {
#if UI_TONE_HIGH_DRIVE_PAGE == 1 && defined(PIN_MSG_TONE)
  if (_node_prefs == NULL) return;
  stopNotifyOutputs();
  _node_prefs->notify_tone_high_drive_enabled = isNotifyToneHighDriveEnabled() ? 0 : 1;
  _node_prefs->notify_tone_volume = 10;
  the_mesh.savePrefs();
  showAlert(isNotifyToneHighDriveEnabled() ? "Громкость: максимум" : "Громкость: обычная", 1000);
  startMsgTone();
#endif
}

void UITask::cycleNotifyToneResonance() {
#if UI_TONE_RESONANCE_PAGE == 1 && defined(PIN_MSG_TONE)
  if (_node_prefs == NULL) return;
  static const uint16_t resonance_steps[] = {1800, 2200, 2600, 3000, 3400, 3800, 4200};
  const uint8_t step_count = sizeof(resonance_steps) / sizeof(resonance_steps[0]);
  uint16_t current = getNotifyToneResonanceHz();
  uint8_t next = 0;
  for (uint8_t i = 0; i < step_count; i++) {
    if (resonance_steps[i] == current) {
      next = (i + 1) % step_count;
      break;
    }
  }
  setNotifyToneResonanceHz(resonance_steps[next]);
#endif
}

void UITask::setNotifyToneResonanceHz(uint16_t frequency) {
#if UI_TONE_RESONANCE_PAGE == 1 && defined(PIN_MSG_TONE)
  if (!_node_prefs || frequency < 1800 || frequency > 4200 ||
      (frequency - 1800) % 400 != 0 || getNotifyToneResonanceHz() == frequency) return;
  _node_prefs->notify_tone_resonance_hz = frequency;
#if UI_SMART_B11_EXTRAS == 1 && UI_SMART_B12_TONE_LIST != 1
  _node_prefs->smart_profile_id = SMART_PROFILE_CUSTOM;
#endif
  the_mesh.savePrefs();

  char alert[40];
  snprintf(alert, sizeof(alert), "Тест: %u Гц", frequency);
  showAlert(alert, 900);
  startNotifyToneTest(frequency);
#else
  (void)frequency;
#endif
}

void UITask::toggleNotifyToneBridge() {
#if UI_TONE_BRIDGE_PAGE == 1 && defined(PIN_MSG_TONE)
  if (_node_prefs == NULL) return;

  stopNotifyOutputs();
  bool enable = !isNotifyToneBridgeEnabled();
  _node_prefs->notify_tone_bridge_enabled = enable ? 1 : 0;

  if (enable) {
    configureMsgTonePin(DEFAULT_NOTIFY_TONE_PIN);
#ifdef PIN_MSG_ALERT
    if (_msg_alert_pin == DEFAULT_NOTIFY_TONE_PIN || _msg_alert_pin == DEFAULT_NOTIFY_TONE_BRIDGE_PIN) {
      int safe_alert = getDefaultNotifyGpioPin();
      if (safe_alert == DEFAULT_NOTIFY_TONE_PIN || safe_alert == DEFAULT_NOTIFY_TONE_BRIDGE_PIN) {
        safe_alert = getNextNotifyGpioPinExcept(safe_alert, DEFAULT_NOTIFY_TONE_PIN, DEFAULT_NOTIFY_TONE_BRIDGE_PIN);
      }
      configureMsgAlertPin(safe_alert);
    }
#endif
    if (_msg_vibe_pin == DEFAULT_NOTIFY_TONE_PIN || _msg_vibe_pin == DEFAULT_NOTIFY_TONE_BRIDGE_PIN) {
      configureMsgVibePin(-1);
    }
    pinMode(DEFAULT_NOTIFY_TONE_BRIDGE_PIN, OUTPUT);
    digitalWrite(DEFAULT_NOTIFY_TONE_BRIDGE_PIN, LOW);
  } else {
    uiStopToneBridge(DEFAULT_NOTIFY_TONE_PIN, DEFAULT_NOTIFY_TONE_BRIDGE_PIN);
    configureMsgTonePin(DEFAULT_NOTIFY_TONE_PIN);
  }

  the_mesh.savePrefs();
  char alert[48];
  if (enable) {
    snprintf(alert, sizeof(alert), "МОСТ: D%d-D%d", DEFAULT_NOTIFY_TONE_PIN, DEFAULT_NOTIFY_TONE_BRIDGE_PIN);
  } else {
    snprintf(alert, sizeof(alert), "Обычный: D%d-GND", DEFAULT_NOTIFY_TONE_PIN);
  }
  showAlert(alert, 1200);
  startMsgTone();
#else
  showAlert("Мост недоступен", 1000);
#endif
}

bool UITask::hasToneAlert() const {
#ifdef PIN_MSG_TONE
  return true;
#else
  return false;
#endif
}

void UITask::cycleNotifyMode() {
  if (_node_prefs == NULL) return;

  uint8_t supported = getSupportedNotifyMode();
  uint8_t mode = getNotifyMode();
  uint8_t next = uiNextNotifyMode(mode, supported);

  _node_prefs->notify_mode = next;
#ifdef PIN_MSG_TONE
  if ((next & NOTIFY_MODE_TONE) == 0) {
    silenceMsgTonePin(getMsgTonePin());
    _msg_tone_active = false;
    _msg_tone_step = 0;
    _msg_tone_fx_remaining = 0;
    _msg_tone_fx_phase = 0;
    _msg_tone_next = 0;
    _msg_tone_off = 0;
  }
#endif
#ifdef PIN_MSG_ALERT
  if ((next & NOTIFY_MODE_GPIO) == 0) {
    digitalWrite(getMsgAlertPin(), PIN_MSG_ALERT_INACTIVE);
    _msg_alert_until = 0;
  }
#endif
  if ((next & NOTIFY_MODE_VIBE) == 0) {
    stopMsgVibe();
  }
#ifdef PIN_BUZZER
  _node_prefs->buzzer_quiet = (next & NOTIFY_MODE_TONE) ? 0 : 1;
  buzzer.quiet(_node_prefs->buzzer_quiet);
#endif
  the_mesh.savePrefs();

  char alert[48];
  snprintf(alert, sizeof(alert), "Сигналы: %s", getNotifyModeName());
  showAlert(alert, 900);
  previewNotifyMode();
}

#ifdef PIN_MSG_ALERT
int UITask::getMsgAlertPin() const {
  int pin = _msg_alert_pin;
#if UI_NOTIFY_GPIO_SELECT
  if (!isNotifyGpioPinAllowed(pin) || isNotifyGpioBlocked(pin)) pin = getDefaultNotifyGpioPin();
#if UI_TONE_BRIDGE_PAGE == 1
  if (isNotifyToneBridgeEnabled() &&
      (pin == DEFAULT_NOTIFY_TONE_PIN || pin == DEFAULT_NOTIFY_TONE_BRIDGE_PIN)) {
    pin = getDefaultNotifyGpioPin();
    if (pin == DEFAULT_NOTIFY_TONE_PIN || pin == DEFAULT_NOTIFY_TONE_BRIDGE_PIN) {
      pin = getNextNotifyGpioPinExcept(pin, DEFAULT_NOTIFY_TONE_PIN, DEFAULT_NOTIFY_TONE_BRIDGE_PIN);
    }
  }
#endif
#endif
  return pin;
}

void UITask::configureMsgAlertPin(int pin) {
#if UI_NOTIFY_GPIO_SELECT
  if (!isNotifyGpioPinAllowed(pin) || isNotifyGpioBlocked(pin)) pin = getDefaultNotifyGpioPin();
#if UI_TONE_BRIDGE_PAGE == 1
  if (isNotifyToneBridgeEnabled() &&
      (pin == DEFAULT_NOTIFY_TONE_PIN || pin == DEFAULT_NOTIFY_TONE_BRIDGE_PIN)) {
    pin = getDefaultNotifyGpioPin();
    if (pin == DEFAULT_NOTIFY_TONE_PIN || pin == DEFAULT_NOTIFY_TONE_BRIDGE_PIN) {
      pin = getNextNotifyGpioPinExcept(pin, DEFAULT_NOTIFY_TONE_PIN, DEFAULT_NOTIFY_TONE_BRIDGE_PIN);
    }
  }
#endif
#else
  pin = PIN_MSG_ALERT;
#endif

  if (_msg_alert_pin >= 0 && _msg_alert_pin != pin) {
    digitalWrite(_msg_alert_pin, PIN_MSG_ALERT_INACTIVE);
  }

  _msg_alert_pin = pin;
  pinMode(_msg_alert_pin, OUTPUT);
  digitalWrite(_msg_alert_pin, PIN_MSG_ALERT_INACTIVE);
  _msg_alert_until = 0;

  if (_node_prefs != NULL) {
    _node_prefs->notify_gpio_pin = _msg_alert_pin;
  }
}
#endif

#ifdef PIN_MSG_TONE
int UITask::getMsgTonePin() const {
  int pin = _msg_tone_pin;
#if UI_TONE_BRIDGE_PAGE == 1
  if (isNotifyToneBridgeEnabled()) pin = DEFAULT_NOTIFY_TONE_PIN;
#endif
#if UI_NOTIFY_GPIO_SELECT
  if (!isNotifyGpioPinAllowed(pin) || isNotifyGpioBlocked(pin)) pin = getDefaultNotifyGpioPin();
#endif
  return pin;
}

void UITask::configureMsgTonePin(int pin) {
#if UI_TONE_BRIDGE_PAGE == 1
  uiStopToneBridge(DEFAULT_NOTIFY_TONE_PIN, DEFAULT_NOTIFY_TONE_BRIDGE_PIN);
  if (isNotifyToneBridgeEnabled()) pin = DEFAULT_NOTIFY_TONE_PIN;
#endif
#if UI_NOTIFY_GPIO_SELECT
  if (!isNotifyGpioPinAllowed(pin) || isNotifyGpioBlocked(pin)) pin = getDefaultNotifyGpioPin();
#else
  pin = PIN_MSG_TONE;
#endif

  if (_msg_tone_pin >= 0 && _msg_tone_pin != pin) {
    noTone(_msg_tone_pin);
#ifdef PIN_MSG_ALERT
    if (_msg_tone_pin != getMsgAlertPin()) {
      digitalWrite(_msg_tone_pin, LOW);
    }
#else
    digitalWrite(_msg_tone_pin, LOW);
#endif
  }

  _msg_tone_pin = pin;
  pinMode(_msg_tone_pin, OUTPUT);
  noTone(_msg_tone_pin);
#ifdef PIN_MSG_ALERT
  if (_msg_tone_pin == getMsgAlertPin()) {
    digitalWrite(getMsgAlertPin(), PIN_MSG_ALERT_INACTIVE);
  } else {
    digitalWrite(_msg_tone_pin, LOW);
  }
#else
  digitalWrite(_msg_tone_pin, LOW);
#endif
  _msg_tone_active = false;
  _msg_tone_step = 0;
  _msg_tone_fx_remaining = 0;
  _msg_tone_fx_phase = 0;
  _msg_tone_next = 0;

  if (_node_prefs != NULL) {
    _node_prefs->notify_tone_pin = _msg_tone_pin;
  }
}
#endif

int UITask::getMsgVibePin() const {
  int pin = _msg_vibe_pin;
#if UI_NOTIFY_GPIO_SELECT
  if (pin < 0) return -1;
  if (!isNotifyGpioPinAllowed(pin) || isNotifyGpioBlocked(pin)) return -1;
#if UI_TONE_BRIDGE_PAGE == 1
  if (isToneBridgePin(pin)) return -1;
#endif
  return pin;
#elif defined(PIN_VIBRATION)
  return PIN_VIBRATION;
#else
  return pin >= 0 ? pin : -1;
#endif
}

void UITask::configureMsgVibePin(int pin) {
#if UI_NOTIFY_GPIO_SELECT
  if (pin >= 0 && (!isNotifyGpioPinAllowed(pin) || isNotifyGpioBlocked(pin))) {
    pin = -1;
  }
#if UI_TONE_BRIDGE_PAGE == 1
  if (isToneBridgePin(pin)) pin = -1;
#endif
#elif defined(PIN_VIBRATION)
  pin = PIN_VIBRATION;
#else
  pin = -1;
#endif

  if (_msg_vibe_pin >= 0 && _msg_vibe_pin != pin) {
    digitalWrite(_msg_vibe_pin, LOW);
  }

  _msg_vibe_pin = pin;
  _msg_vibe_until = 0;
  _msg_vibe_next = 0;
  _msg_vibe_on = false;

  if (_msg_vibe_pin >= 0) {
    pinMode(_msg_vibe_pin, OUTPUT);
    digitalWrite(_msg_vibe_pin, LOW);
  }

  if (_node_prefs != NULL) {
    _node_prefs->notify_vibe_pin = _msg_vibe_pin;
  }
}

void UITask::stopMsgVibe() {
  int pin = getMsgVibePin();
  if (pin >= 0) {
    digitalWrite(pin, LOW);
  }
  _msg_vibe_until = 0;
  _msg_vibe_next = 0;
  _msg_vibe_on = false;
}

void UITask::triggerMsgVibe() {
  int pin = getMsgVibePin();
  if (areNotificationsMuted() || pin < 0) {
    stopMsgVibe();
    return;
  }
  pinMode(pin, OUTPUT);
  _msg_vibe_until = millis() + MSG_VIBE_BURST_MILLIS;
  _msg_vibe_next = 0;
  _msg_vibe_on = false;
  messageVibeHandler();
}

void UITask::messageVibeHandler() {
  int pin = getMsgVibePin();
  if (pin < 0 || areNotificationsMuted()) {
    stopMsgVibe();
    return;
  }
  if (_msg_vibe_until == 0) return;

  unsigned long now = millis();
  if (smartui::deadlineReached((uint32_t)now, (uint32_t)_msg_vibe_until)) {
    stopMsgVibe();
    return;
  }
  if (smartui::optionalDeadlinePending((uint32_t)now, (uint32_t)_msg_vibe_next)) return;

  _msg_vibe_on = !_msg_vibe_on;
  digitalWrite(pin, _msg_vibe_on ? HIGH : LOW);
  _msg_vibe_next = now + (_msg_vibe_on ? MSG_VIBE_ON_MILLIS : MSG_VIBE_OFF_MILLIS);
}

void UITask::previewNotifyMode() {
  uint8_t mode = getNotifyMode();
#if defined(PIN_MSG_ALERT) && defined(PIN_MSG_TONE)
  if ((mode & NOTIFY_MODE_GPIO) && !((mode & NOTIFY_MODE_TONE) && getMsgTonePin() == getMsgAlertPin())) {
    triggerMsgAlert();
  }
#elif defined(PIN_MSG_ALERT)
  if (mode & NOTIFY_MODE_GPIO) {
    triggerMsgAlert();
  }
#endif
#ifdef PIN_MSG_TONE
  if (mode & NOTIFY_MODE_TONE) {
    startMsgTone();
  }
#endif
  if (mode & NOTIFY_MODE_VIBE) {
    triggerMsgVibe();
  }
}

void UITask::notify(UIEventType t) {
#if defined(PIN_BUZZER)
switch(t){
  case UIEventType::contactMessage:
  case UIEventType::channelMessage:
    break;
  case UIEventType::ack:
    buzzer.play("ack:d=32,o=8,b=120:c");
    break;
  case UIEventType::roomMessage:
  case UIEventType::newContactMessage:
  case UIEventType::none:
  default:
    break;
}
#endif

#ifdef PIN_VIBRATION
  // Trigger vibration for all UI events except none
  if (t != UIEventType::none) {
    vibration.trigger();
  }
#endif
}

void UITask::stopNotifyOutputs() {
#ifdef PIN_MSG_ALERT
  digitalWrite(getMsgAlertPin(), PIN_MSG_ALERT_INACTIVE);
  _msg_alert_until = 0;
#endif
#ifdef PIN_MSG_TONE
  silenceMsgTonePin(getMsgTonePin());
  _msg_tone_active = false;
  _msg_tone_step = 0;
  _msg_tone_repeat_left = 0;
  _msg_tone_fx_remaining = 0;
  _msg_tone_test_frequency = 0;
  _msg_tone_test_duration = 700;
  _msg_tone_fx_phase = 0;
  _msg_tone_next = 0;
  _msg_tone_off = 0;
#endif
  stopMsgVibe();
#if UI_IMPORTANT_NOTIFY_NEOPIXEL && defined(PIN_NEOPIXEL) && defined(NEOPIXEL_NUM) && NEOPIXEL_NUM > 0
  importantNotifyPixelsOff();
#endif
}

void UITask::finishImportantNotify(bool stop_tone) {
  if (!_important_notify_active &&
      _important_msg_flags == UI_MSG_FLAG_NONE &&
      _ble_smart_notify_flags == UI_MSG_FLAG_NONE) return;

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
  _important_notify_led_burst_step = 0;
  _important_notify_tone_burst_step = 0;
  _important_notify_vibe_burst_step = 0;
  _ble_smart_notify_due = 0;

  if (stop_tone) {
    stopNotifyOutputs();
  } else {
#ifdef PIN_MSG_ALERT
    digitalWrite(getMsgAlertPin(), PIN_MSG_ALERT_INACTIVE);
    _msg_alert_until = 0;
#endif
    stopMsgVibe();
#if UI_IMPORTANT_NOTIFY_NEOPIXEL && defined(PIN_NEOPIXEL) && defined(NEOPIXEL_NUM) && NEOPIXEL_NUM > 0
    importantNotifyPixelsOff();
#endif
  }

  _next_refresh = 0;
}

unsigned long UITask::nextImportantNotifyDelay(uint8_t& burst_step, unsigned long repeat_ms) const {
  if (!hasConnection() && UI_OFFLINE_IMPORTANT_NOTIFY_BURST_COUNT > 1) {
    burst_step++;
    if (burst_step < UI_OFFLINE_IMPORTANT_NOTIFY_BURST_COUNT) {
      return UI_OFFLINE_IMPORTANT_NOTIFY_BURST_GAP_MS;
    }
    burst_step = 0;
  } else {
    burst_step = 0;
  }
  return repeat_ms;
}

void UITask::toggleNotificationsMuted() {
  if (_node_prefs == NULL) return;

  // A manual change owns the mute state from this point on.  Morning auto-unmute
  // must never undo a mute that the user selected manually.
  _node_prefs->night_quiet_active = 0;
  _node_prefs->notifications_muted = _node_prefs->notifications_muted ? 0 : 1;
  if (_node_prefs->notifications_muted) {
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
    _important_notify_led_burst_step = 0;
    _important_notify_tone_burst_step = 0;
    _important_notify_vibe_burst_step = 0;
    _ble_smart_notify_due = 0;
    stopNotifyOutputs();
  }
  the_mesh.savePrefs();
  showAlert(_node_prefs->notifications_muted ? "Тишина: ВКЛ" : "Тишина: ВЫКЛ", 900);
  _next_refresh = 0;
}

void UITask::closeNightPrompt(bool enable_quiet, bool timed_out) {
#if UI_NIGHT_MODE_PROMPT
  if (!_night_prompt_active || _node_prefs == NULL) return;

  _night_prompt_active = false;
  _night_prompt_expires = 0;
  _night_prompt_yes = true;

  if (enable_quiet) {
    _node_prefs->night_quiet_active = 1;
    _node_prefs->notifications_muted = 1;
    stopNotifyOutputs();
  } else {
    _node_prefs->night_quiet_active = 0;
  }
  the_mesh.savePrefs();

  if (!timed_out) {
    showAlert(enable_quiet ? "Ночной режим: ВКЛ" : "Ночной режим: НЕТ", 1200);
  }
  _last_activity_ms = millis();
  extendAutoOff();
  _next_refresh = 0;
#else
  (void)enable_quiet;
  (void)timed_out;
#endif
}

bool UITask::handleNightPromptInput(char c) {
#if UI_NIGHT_MODE_PROMPT
  if (!_night_prompt_active) return false;

  if (c == KEY_NEXT || c == KEY_PREV || c == KEY_LEFT || c == KEY_RIGHT) {
    _night_prompt_yes = !_night_prompt_yes;
    _night_prompt_expires = millis() + UI_NIGHT_MODE_PROMPT_TIMEOUT_MS;
    _next_refresh = 0;
    return true;
  }
  if (c == KEY_ENTER || c == KEY_SELECT) {
    closeNightPrompt(_night_prompt_yes);
    return true;
  }
  return true;
#else
  (void)c;
  return false;
#endif
}

void UITask::renderNightPrompt(DisplayDriver& display) {
#if UI_NIGHT_MODE_PROMPT
  uint8_t saved_font = uiPushCompactSettingsFont(display);
  int line_h = display.getTextLineHeight();
  if (line_h < 8) line_h = 8;
  int margin = display.width() >= 200 ? 10 : 3;
  int box_h = line_h * 4 + 10;
  if (box_h > display.height() - 4) box_h = display.height() - 4;
  int box_y = (display.height() - box_h) / 2;
  int text_y = box_y + 4;

  display.setColor(DisplayDriver::DARK);
  display.fillRect(margin, box_y, display.width() - margin * 2, box_h);
  display.setColor(getUiTopColor());
  display.drawRect(margin, box_y, display.width() - margin * 2, box_h);
  display.setTextSize(1);
  display.setBold(true);
  drawRichTextCenteredEllipsized(display, display.width() / 2, text_y,
                                 display.width() - margin * 2 - 8, "НОЧНОЙ РЕЖИМ");
  display.setBold(false);
  display.setColor(DisplayDriver::LIGHT);
  drawRichTextCenteredEllipsized(display, display.width() / 2, text_y + line_h,
                                 display.width() - margin * 2 - 8, "Тишина до 07:30?");

  display.setColor(_night_prompt_yes ? DisplayDriver::GREEN : DisplayDriver::LIGHT);
  drawRichTextCenteredEllipsized(display, display.width() / 2, text_y + line_h * 2,
                                 display.width() - margin * 2 - 8,
                                 _night_prompt_yes ? "> ДА <    нет" : "да    > НЕТ <");

  display.setColor(DisplayDriver::LIGHT);
  drawRichTextCenteredEllipsized(display, display.width() / 2, text_y + line_h * 3,
                                 display.width() - margin * 2 - 8, "клик: смена / удерж: OK");
  uiPopFont(display, saved_font);
#else
  (void)display;
#endif
}

void UITask::nightModeHandler() {
#if UI_NIGHT_MODE_PROMPT
  if (_node_prefs == NULL || _display == NULL) return;

  if (_night_prompt_active) {
    if (_night_prompt_expires != 0 &&
        smartui::deadlineReached((uint32_t)millis(), (uint32_t)_night_prompt_expires)) {
      closeNightPrompt(false, true);
    }
    return;
  }

  uint32_t rtc_now = rtc_clock.getCurrentTime();
  if (!hasTrustedTime() || rtc_now < UI_RTC_VALID_MIN) return;

  uint32_t local_now = getLocalClockTime(rtc_now);
  DateTime dt(local_now);
  uint16_t minute_of_day = (uint16_t)dt.hour() * 60U + dt.minute();
  uint32_t local_day = local_now / 86400UL;

  if (_node_prefs->night_quiet_active) {
    bool morning = minute_of_day >= UI_NIGHT_MODE_END_MINUTE &&
                   minute_of_day < UI_NIGHT_MODE_PROMPT_MINUTE;
    bool missed_morning = local_day != _node_prefs->night_prompt_day &&
                          minute_of_day >= UI_NIGHT_MODE_PROMPT_MINUTE;
    if (morning || missed_morning) {
      _node_prefs->night_quiet_active = 0;
      _node_prefs->notifications_muted = 0;
      the_mesh.savePrefs();
      _next_refresh = 0;
    } else {
      return;
    }
  }

  if (minute_of_day < UI_NIGHT_MODE_PROMPT_MINUTE ||
      _node_prefs->night_prompt_day == local_day) return;

  // A night-mode suggestion must never cover or steal input from a message.
  // Keep the offer eligible until every pending notification/output is idle.
  if (_important_notify_active || _important_msg_flags != UI_MSG_FLAG_NONE ||
      _ble_smart_notify_flags != UI_MSG_FLAG_NONE || _popup_pending) return;
#ifdef PIN_MSG_TONE
  if (_msg_tone_active) return;
#endif
#ifdef PIN_MSG_ALERT
  if (smartui::optionalDeadlinePending((uint32_t)millis(), (uint32_t)_msg_alert_until)) return;
#endif
  if (smartui::optionalDeadlinePending((uint32_t)millis(), (uint32_t)_msg_vibe_until)) return;

  // Remember the offer before showing it, so a reset cannot make the node
  // repeatedly chirp during the same night.
  _node_prefs->night_prompt_day = local_day;
  the_mesh.savePrefs();
  if (areNotificationsMuted()) return;

  _night_prompt_active = true;
  _night_prompt_yes = true;
  _night_prompt_expires = millis() + UI_NIGHT_MODE_PROMPT_TIMEOUT_MS;
  gotoHomeFirstScreen();
  _display->turnOn();
  markDisplayWake(false);
#if AUTO_OFF_MILLIS > 0
  _auto_off = _night_prompt_expires;
#endif
#ifdef PIN_MSG_TONE
  if (hasToneAlert()) startNotifyToneTest(2300, 120);
#endif
  _next_refresh = 0;
#endif
}

void UITask::beginImportantNotify(uint8_t flags, bool suppress_tone_repeats) {
  flags &= (UI_MSG_FLAG_DIRECT | UI_MSG_FLAG_MENTION | UI_MSG_FLAG_IMPORTANT);
  if (flags == UI_MSG_FLAG_NONE || areNotificationsMuted() || getImportantNotifyMode() == NOTIFY_MODE_SILENT) return;

  // One active notification owns exactly one tone series.  BLE watchers and
  // duplicate delivery callbacks may report the same unread event again while
  // that series is playing; merge their flags without rearming the melody.
  if (_important_notify_active) {
    _important_msg_flags |= flags;
    if (suppress_tone_repeats) {
      _important_notify_tone_repeat_suppressed = true;
    }
    return;
  }

  _important_notify_active = true;
  _important_msg_flags |= flags;
  _important_notify_tone_started = false;
  _important_notify_tone_repeat_suppressed = suppress_tone_repeats;
  _important_notify_visual_repeat_suppressed = false;
  _important_notify_visual_until = 0;
#if UI_BLE_READ_SUPPRESSES_IMPORTANT_VISUAL_REPEAT
  if (suppress_tone_repeats) {
    _important_notify_visual_repeat_suppressed = true;
    _important_notify_visual_until = millis() + UI_IMPORTANT_NOTIFY_VISUAL_BURST_MS;
  }
#endif
  _important_notify_led_next = 0;
  _important_notify_tone_next = 0;
  _important_notify_vibe_next = 0;
  _important_notify_led_burst_step = 0;
  _important_notify_tone_burst_step = 0;
  _important_notify_vibe_burst_step = 0;
  importantNotifyHandler();
}

void UITask::clearBleSmartNotify() {
  _ble_smart_notify_flags = UI_MSG_FLAG_NONE;
  _ble_smart_notify_read_zero_seen = false;
  _ble_smart_notify_due = 0;
}

void UITask::scheduleBleSmartNotify(uint8_t flags) {
#if UI_IMPORTANT_NOTIFY_BLE_SMART_DELAY_MS > 0
  flags &= (UI_MSG_FLAG_DIRECT | UI_MSG_FLAG_MENTION | UI_MSG_FLAG_IMPORTANT);
  if (flags == UI_MSG_FLAG_NONE) return;

  if (_ble_smart_notify_flags == UI_MSG_FLAG_NONE) {
    _ble_smart_notify_read_zero_seen = false;
  }
  _ble_smart_notify_flags |= flags;
  unsigned long due = millis() + UI_IMPORTANT_NOTIFY_BLE_SMART_DELAY_MS;
  if (_ble_smart_notify_due == 0 ||
      smartui::deadlinePending((uint32_t)due, (uint32_t)_ble_smart_notify_due)) {
    _ble_smart_notify_due = due;
  }
  _next_refresh = 0;
#else
  (void)flags;
#endif
}

void UITask::bleSmartNotifyHandler() {
#if UI_IMPORTANT_NOTIFY_BLE_SMART_DELAY_MS > 0
  if (_ble_smart_notify_flags == UI_MSG_FLAG_NONE) return;

  if (areNotificationsMuted() || getImportantNotifyMode() == NOTIFY_MODE_SILENT) {
    clearBleSmartNotify();
    return;
  }

  unsigned long now = millis();
  bool due = smartui::deadlineDueOrImmediate((uint32_t)now,
                                             (uint32_t)_ble_smart_notify_due);
  if (!hasConnection()) {
    uint8_t flags = _ble_smart_notify_flags;
    clearBleSmartNotify();
    beginImportantNotify(flags, false);
    return;
  }

  if (!due) return;

  uint8_t flags = _ble_smart_notify_flags;
#if UI_SMART_NOTIFY_WATCHER_CANCEL_PENDING_ON_BLE_READ
  if (_ble_smart_notify_read_zero_seen) {
    clearBleSmartNotify();
    _next_refresh = 0;
    return;
  }
#endif
  bool suppress_tone_repeats = _ble_smart_notify_read_zero_seen;
  clearBleSmartNotify();
  beginImportantNotify(flags, suppress_tone_repeats);
#endif
}

void UITask::startImportantNotify(uint8_t flags) {
  flags &= (UI_MSG_FLAG_DIRECT | UI_MSG_FLAG_MENTION | UI_MSG_FLAG_IMPORTANT);
  if (flags == UI_MSG_FLAG_NONE || areNotificationsMuted() || getImportantNotifyMode() == NOTIFY_MODE_SILENT) return;
#if UI_IMPORTANT_NOTIFY_BLE_SMART_DELAY_MS > 0
  if (hasConnection()) {
    scheduleBleSmartNotify(flags);
    return;
  }
#elif UI_IMPORTANT_NOTIFY_LOCAL_ONLY_WHEN_DISCONNECTED
  if (hasConnection()) {
    _next_refresh = 0;
    return;
  }
#endif

  beginImportantNotify(flags, false);
}

void UITask::clearImportantNotify() {
  finishImportantNotify(true);
}

void UITask::importantNotifyHandler() {
  if (!_important_notify_active) return;

  uint8_t mode = getImportantNotifyMode();
  if (areNotificationsMuted() || mode == NOTIFY_MODE_SILENT) {
    clearImportantNotify();
    return;
  }

  unsigned long now = millis();
  bool allow_visual = (mode & NOTIFY_MODE_GPIO) != 0;
#if UI_OFFLINE_DM_LED_PAGE == 1 && defined(PIN_MSG_ALERT)
  if (allow_visual && !isOfflineDmLedEnabled() && !hasConnection() && (_important_msg_flags & UI_MSG_FLAG_DIRECT)) {
    allow_visual = false;
  }
  if (allow_visual && !isBleDmLedEnabled() && hasConnection() && (_important_msg_flags & UI_MSG_FLAG_DIRECT)) {
    allow_visual = false;
  }
#endif
#if UI_BLE_READ_SUPPRESSES_IMPORTANT_VISUAL_REPEAT
  if (allow_visual && _important_notify_visual_repeat_suppressed) {
    if (_important_notify_visual_until == 0) {
      _important_notify_visual_until = now + UI_IMPORTANT_NOTIFY_VISUAL_BURST_MS;
    }
    allow_visual = smartui::deadlinePending((uint32_t)now,
                                            (uint32_t)_important_notify_visual_until);
  }
#endif

#if UI_IMPORTANT_NOTIFY_NEOPIXEL && defined(PIN_NEOPIXEL) && defined(NEOPIXEL_NUM) && NEOPIXEL_NUM > 0
  importantNotifyPixelsHandler(allow_visual);
#endif

#if defined(PIN_MSG_ALERT) && defined(PIN_MSG_TONE)
  bool tone_uses_led_pin = (mode & NOTIFY_MODE_TONE) && getMsgTonePin() == getMsgAlertPin();
  bool defer_gpio_while_tone = false;
#if !UI_IMPORTANT_NOTIFY_GPIO_DURING_TONE
  defer_gpio_while_tone = (mode & NOTIFY_MODE_TONE) && !tone_uses_led_pin && _msg_tone_active;
#endif
  if (!allow_visual && getMsgTonePin() != getMsgAlertPin()) {
    digitalWrite(getMsgAlertPin(), PIN_MSG_ALERT_INACTIVE);
    _msg_alert_until = 0;
  }
  if (allow_visual &&
      !defer_gpio_while_tone &&
      smartui::deadlineDueOrImmediate((uint32_t)now,
                                      (uint32_t)_important_notify_led_next)) {
    triggerMsgAlert();
    _important_notify_led_next = now + nextImportantNotifyDelay(_important_notify_led_burst_step, UI_IMPORTANT_NOTIFY_LED_REPEAT_MS);
  }
#elif defined(PIN_MSG_ALERT)
  if (!allow_visual) {
    digitalWrite(getMsgAlertPin(), PIN_MSG_ALERT_INACTIVE);
    _msg_alert_until = 0;
  }
  if (allow_visual &&
      smartui::deadlineDueOrImmediate((uint32_t)now,
                                      (uint32_t)_important_notify_led_next)) {
    triggerMsgAlert();
    _important_notify_led_next = now + nextImportantNotifyDelay(_important_notify_led_burst_step, UI_IMPORTANT_NOTIFY_LED_REPEAT_MS);
  }
#endif

#ifdef PIN_MSG_TONE
  bool allow_first_tone = !_important_notify_tone_started;
  bool allow_tone_repeat = !UI_IMPORTANT_NOTIFY_TONE_SERIES_ONCE &&
                           !_important_notify_tone_repeat_suppressed && !hasConnection();
#if defined(PIN_MSG_ALERT) && defined(PIN_MSG_TONE)
  if ((mode & NOTIFY_MODE_TONE) && !tone_uses_led_pin && (allow_first_tone || allow_tone_repeat)) {
    if (allow_first_tone && !_msg_tone_active) {
      startMsgTone();
      _important_notify_tone_started = true;
      _important_notify_tone_next = allow_tone_repeat ? now + nextImportantNotifyDelay(_important_notify_tone_burst_step, UI_IMPORTANT_NOTIFY_TONE_REPEAT_MS) : 0;
    } else if (allow_tone_repeat && !_msg_tone_active) {
      if (_important_notify_tone_next == 0) {
        _important_notify_tone_next = now + nextImportantNotifyDelay(_important_notify_tone_burst_step, UI_IMPORTANT_NOTIFY_TONE_REPEAT_MS);
      } else if (smartui::deadlineReached((uint32_t)now,
                                          (uint32_t)_important_notify_tone_next)) {
        startMsgTone();
        _important_notify_tone_next = now + nextImportantNotifyDelay(_important_notify_tone_burst_step, UI_IMPORTANT_NOTIFY_TONE_REPEAT_MS);
      }
    }
  } else if (!allow_tone_repeat) {
    _important_notify_tone_next = 0;
  }
#else
  if ((mode & NOTIFY_MODE_TONE) && (allow_first_tone || allow_tone_repeat)) {
    if (allow_first_tone && !_msg_tone_active) {
      startMsgTone();
      _important_notify_tone_started = true;
      _important_notify_tone_next = allow_tone_repeat ? now + nextImportantNotifyDelay(_important_notify_tone_burst_step, UI_IMPORTANT_NOTIFY_TONE_REPEAT_MS) : 0;
    } else if (allow_tone_repeat && !_msg_tone_active) {
      if (_important_notify_tone_next == 0) {
        _important_notify_tone_next = now + nextImportantNotifyDelay(_important_notify_tone_burst_step, UI_IMPORTANT_NOTIFY_TONE_REPEAT_MS);
      } else if (smartui::deadlineReached((uint32_t)now,
                                          (uint32_t)_important_notify_tone_next)) {
        startMsgTone();
        _important_notify_tone_next = now + nextImportantNotifyDelay(_important_notify_tone_burst_step, UI_IMPORTANT_NOTIFY_TONE_REPEAT_MS);
      }
    }
  } else if (!allow_tone_repeat) {
    _important_notify_tone_next = 0;
  }
#endif
#endif
  if ((mode & NOTIFY_MODE_VIBE) &&
      smartui::deadlineDueOrImmediate((uint32_t)now,
                                      (uint32_t)_important_notify_vibe_next)) {
    triggerMsgVibe();
    _important_notify_vibe_next = now + nextImportantNotifyDelay(_important_notify_vibe_burst_step, UI_IMPORTANT_NOTIFY_TONE_REPEAT_MS);
  }
}

#ifdef PIN_MSG_ALERT
void UITask::triggerMsgAlert() {
  int alert_pin = getMsgAlertPin();
  if (areNotificationsMuted() ||
      isNotifyGpioBlocked(alert_pin)
#if !UI_NOTIFY_LED_OVERRIDES_BOARD_LED_SETTING
      || (!areBoardLedsEnabled() && isBoardLedPin(alert_pin))
#endif
  ) {
    setBoardLedPinOff(alert_pin);
    _msg_alert_until = 0;
    return;
  }
  digitalWrite(alert_pin, PIN_MSG_ALERT_ACTIVE);
  _msg_alert_until = millis() + MSG_ALERT_ON_MILLIS;
}

void UITask::messageAlertHandler() {
  int alert_pin = getMsgAlertPin();
  if (areNotificationsMuted() ||
      isNotifyGpioBlocked(alert_pin)
#if !UI_NOTIFY_LED_OVERRIDES_BOARD_LED_SETTING
      || (!areBoardLedsEnabled() && isBoardLedPin(alert_pin))
#endif
  ) {
    setBoardLedPinOff(alert_pin);
    _msg_alert_until = 0;
    return;
  }
#ifdef PIN_MSG_TONE
  if (_msg_tone_active && getMsgTonePin() == getMsgAlertPin()) {
    return;
  }
#endif
  if (_msg_alert_until &&
      smartui::deadlineReached((uint32_t)millis(), (uint32_t)_msg_alert_until)) {
    digitalWrite(getMsgAlertPin(), PIN_MSG_ALERT_INACTIVE);
    _msg_alert_until = 0;
  }
}
#endif

#ifdef PIN_MSG_TONE
void UITask::silenceMsgTonePin(int tone_pin) {
#if UI_TONE_BRIDGE_PAGE == 1
  uiStopToneBridge(DEFAULT_NOTIFY_TONE_PIN, DEFAULT_NOTIFY_TONE_BRIDGE_PIN);
#endif
  noTone(tone_pin);
  if (!areBoardLedsEnabled() && isBoardLedPin(tone_pin)) {
    setBoardLedPinOff(tone_pin);
  } else {
    digitalWrite(tone_pin, LOW);
  }
#ifdef PIN_MSG_ALERT
  if (tone_pin == getMsgAlertPin()) {
    digitalWrite(getMsgAlertPin(), PIN_MSG_ALERT_INACTIVE);
    _msg_alert_until = 0;
  }
#endif
}

uint16_t UITask::getMsgToneOnMillis(uint16_t duration, uint16_t freq) const {
  if (freq == 0) return duration;
  uint8_t volume = getNotifyToneVolume();
  if (volume >= 10) return duration;

  uint16_t on_millis = (duration * volume + 9) / 10;
  if (on_millis < 12) on_millis = 12;
  if (on_millis + 8 >= duration) return duration;
  return on_millis;
}

void UITask::startMsgTone(uint8_t tone_id) {
  if (areNotificationsMuted()) return;
  if (notify_tone_count == 0) return;
  if (tone_id == 0xFF) {
    tone_id = _node_prefs ? _node_prefs->notify_tone_system_id : 0;
#if UI_SMART_B12_TONE_LIST != 1
    if (_important_notify_active && _node_prefs != NULL) {
      if (_important_msg_flags & UI_MSG_FLAG_DIRECT) {
        tone_id = _node_prefs->notify_tone_dm_id;
      } else if (_important_msg_flags & UI_MSG_FLAG_MENTION) {
        tone_id = _node_prefs->notify_tone_mention_id;
      }
    }
#endif
  }
  if (tone_id >= notify_tone_count) tone_id = 0;
  _msg_tone_id_active = tone_id;
  uint16_t plays = _important_notify_active ? UI_IMPORTANT_NOTIFY_TONE_PLAYS : UI_NOTIFY_TONE_PLAYS;
  if (plays == 0) plays = 1;
  if (plays > 10) plays = 10;
  _msg_tone_step = 0;
  _msg_tone_repeat_left = plays > 1 ? plays - 1 : 0;
  _msg_tone_fx_remaining = 0;
  _msg_tone_test_frequency = 0;
  _msg_tone_test_duration = 700;
  _msg_tone_fx_phase = 0;
  _msg_tone_active = true;
  _msg_tone_next = 0;
  _msg_tone_off = 0;
  messageToneHandler();
}

void UITask::startNotifyToneTest(uint16_t frequency, uint16_t duration) {
  if (areNotificationsMuted() || frequency < 20 || frequency > 6000) return;
  stopNotifyOutputs();
  _msg_tone_test_frequency = frequency;
  _msg_tone_test_duration = constrain(duration, 40, 2000);
  _msg_tone_step = 0;
  _msg_tone_repeat_left = 0;
  _msg_tone_fx_remaining = 0;
  _msg_tone_fx_phase = 0;
  _msg_tone_active = true;
  _msg_tone_next = 0;
  _msg_tone_off = 0;
  messageToneHandler();
}

void UITask::messageToneHandler() {
  if (!_msg_tone_active) return;
  int tone_pin = getMsgTonePin();
  if (areNotificationsMuted() || (!areBoardLedsEnabled() && isBoardLedPin(tone_pin))) {
    silenceMsgTonePin(tone_pin);
    _msg_tone_active = false;
    _msg_tone_step = 0;
    _msg_tone_repeat_left = 0;
    _msg_tone_fx_remaining = 0;
    _msg_tone_test_frequency = 0;
    _msg_tone_test_duration = 700;
    _msg_tone_fx_phase = 0;
    _msg_tone_next = 0;
    _msg_tone_off = 0;
    return;
  }

  if (_msg_tone_off &&
      smartui::deadlineReached((uint32_t)millis(), (uint32_t)_msg_tone_off)) {
    silenceMsgTonePin(tone_pin);
    _msg_tone_off = 0;
  }

  if (smartui::optionalDeadlinePending((uint32_t)millis(),
                                       (uint32_t)_msg_tone_next)) return;
  _msg_tone_off = 0;

  uint16_t test_duration = _msg_tone_test_duration;
  NotifyToneDef test_tone = {"", &_msg_tone_test_frequency, &test_duration, 1};
  const NotifyToneDef* tone_def = &test_tone;
  if (_msg_tone_test_frequency == 0) {
    uint8_t tone_id = _msg_tone_id_active;
    if (tone_id >= notify_tone_count) tone_id = 0;
    tone_def = &notify_tones[tone_id];
  }

  if (_msg_tone_step >= tone_def->steps) {
    silenceMsgTonePin(tone_pin);
    if (_msg_tone_repeat_left > 0) {
      _msg_tone_repeat_left--;
      _msg_tone_step = 0;
      _msg_tone_fx_remaining = 0;
      _msg_tone_fx_phase = 0;
      _msg_tone_next = millis() +
        (_important_notify_active ? UI_IMPORTANT_NOTIFY_TONE_REPEAT_GAP_MS : UI_NOTIFY_TONE_REPEAT_GAP_MS);
      _msg_tone_off = 0;
      return;
    }
    _msg_tone_active = false;
    _msg_tone_repeat_left = 0;
    _msg_tone_test_frequency = 0;
    _msg_tone_test_duration = 700;
    return;
  }

  uint16_t freq = tone_def->freqs[_msg_tone_step];
  uint16_t duration = tone_def->durations[_msg_tone_step];
  bool advance_step = true;
#if UI_TONE_8BIT_PAGE == 1
  if (_msg_tone_test_frequency == 0 &&
      isNotifyTone8BitEnabled() && freq > 1 && duration >= UI_TONE_8BIT_MIN_NOTE_MS) {
    if (_msg_tone_fx_remaining == 0) {
      _msg_tone_fx_remaining = duration;
      _msg_tone_fx_phase = 0;
    }
    duration = _msg_tone_fx_remaining > UI_TONE_8BIT_SLICE_MS
      ? UI_TONE_8BIT_SLICE_MS
      : _msg_tone_fx_remaining;
    freq = uiTone8BitArpeggioFrequency(freq, _msg_tone_fx_phase);
    _msg_tone_fx_remaining -= duration;
    advance_step = _msg_tone_fx_remaining == 0;
    _msg_tone_fx_phase++;
  }
#endif
#if UI_TONE_HIGH_DRIVE_PAGE == 1
  if (isNotifyToneHighDriveEnabled() && freq > 1) {
    freq = uiToneNearestResonantOctave(freq, getNotifyToneResonanceHz());
  }
#endif
  if (freq == 0) {
    silenceMsgTonePin(tone_pin);
  } else if (freq == 1) {
#if UI_TONE_BRIDGE_PAGE == 1
    if (isNotifyToneBridgeEnabled()) {
      if (!uiStartToneBridge(DEFAULT_NOTIFY_TONE_PIN, DEFAULT_NOTIFY_TONE_BRIDGE_PIN, 2000,
                             isNotifyToneHighDriveEnabled())) {
        tone(tone_pin, 2000);
#if UI_TONE_HIGH_DRIVE_PAGE == 1
        if (isNotifyToneHighDriveEnabled()) pinMode(tone_pin, OUTPUT_H0H1);
#endif
      }
    } else
#endif
    {
      noTone(tone_pin);
      pinMode(tone_pin, OUTPUT);
      digitalWrite(tone_pin, HIGH);
    }
  } else {
#if UI_TONE_BRIDGE_PAGE == 1
    if (isNotifyToneBridgeEnabled()) {
      if (!uiStartToneBridge(DEFAULT_NOTIFY_TONE_PIN, DEFAULT_NOTIFY_TONE_BRIDGE_PIN, freq,
                             isNotifyToneHighDriveEnabled())) {
        tone(tone_pin, freq);
#if UI_TONE_HIGH_DRIVE_PAGE == 1
        if (isNotifyToneHighDriveEnabled()) pinMode(tone_pin, OUTPUT_H0H1);
#endif
      }
    } else
#endif
    {
      tone(tone_pin, freq);
#if UI_TONE_HIGH_DRIVE_PAGE == 1
      if (isNotifyToneHighDriveEnabled()) pinMode(tone_pin, OUTPUT_H0H1);
#endif
    }
  }

  uint16_t on_millis = getMsgToneOnMillis(duration, freq);
  if (freq != 0 && on_millis < duration) {
    _msg_tone_off = millis() + on_millis;
  }
  if (advance_step) {
    _msg_tone_step++;
    _msg_tone_fx_remaining = 0;
    _msg_tone_fx_phase = 0;
  }
  _msg_tone_next = millis() + duration;
}
#endif

void UITask::msgRead(int msgcount) {
  msgRead(msgcount, true);
}

void UITask::msgRead(int msgcount, bool dismiss_notification) {
#if UI_IMPORTANT_NOTIFY_BLE_SMART_DELAY_MS > 0
  if (!dismiss_notification && msgcount == 0 && hasConnection() &&
      (_ble_smart_notify_flags != UI_MSG_FLAG_NONE ||
       _important_notify_active ||
       _important_msg_flags != UI_MSG_FLAG_NONE)) {
#if UI_BLE_READ_SUPPRESSES_IMPORTANT_TONE_REPEAT
    if (_ble_smart_notify_flags != UI_MSG_FLAG_NONE) {
      _ble_smart_notify_read_zero_seen = true;
    }
    if (_important_notify_active || _important_msg_flags != UI_MSG_FLAG_NONE) {
      _important_notify_tone_repeat_suppressed = true;
    }
#endif
#if UI_BLE_READ_SUPPRESSES_IMPORTANT_VISUAL_REPEAT
    if (_ble_smart_notify_flags != UI_MSG_FLAG_NONE) {
      _ble_smart_notify_read_zero_seen = true;
    }
    if (_important_notify_active || _important_msg_flags != UI_MSG_FLAG_NONE) {
      _important_notify_visual_repeat_suppressed = true;
      if (_important_notify_visual_until == 0) {
        _important_notify_visual_until = millis() + UI_IMPORTANT_NOTIFY_VISUAL_BURST_MS;
      }
    }
#endif
#if UI_SMART_NOTIFY_WATCHER_CANCEL_PENDING_ON_BLE_READ
    if (_ble_smart_notify_flags != UI_MSG_FLAG_NONE && !_important_notify_active) {
      clearBleSmartNotify();
      _next_refresh = 0;
      return;
    }
#endif
#if UI_SMART_NOTIFY_WATCHER_FINISH_ACTIVE_ON_BLE_READ
    if (_important_notify_active || _important_msg_flags != UI_MSG_FLAG_NONE) {
      finishImportantNotify(false);
      _next_refresh = 0;
      return;
    }
#endif
    _next_refresh = 0;
    return;
  }
#endif

#if UI_UNREAD_DIRECT_ONLY
  if (dismiss_notification && msg_preview != NULL) {
    MsgPreviewScreen* preview = (MsgPreviewScreen *)msg_preview;
    if (msgcount == 0) preview->clearPreviews(true);
    _msgcount = preview->unreadPreviewCount();
  }
#else
  _msgcount = msgcount;
#endif
  if (msgcount == 0) {
    if (dismiss_notification) {
      clearImportantNotify();
    } else {
#if UI_BLE_READ_FINISHES_IMPORTANT_NOTIFY
      if (hasConnection()) {
        finishImportantNotify(false);
      }
#endif
      _next_refresh = 0;
      return;
    }
    if (curr == msg_preview && msg_preview != NULL && ((MsgPreviewScreen *) msg_preview)->hasUnreadPreviews()) {
      _next_refresh = 100;
      return;
    }
    gotoHomeScreen();
  }
}

void UITask::directMsgRead(bool dismiss_notification) {
#if UI_UNREAD_DIRECT_ONLY
  if (msg_preview == NULL) return;
  MsgPreviewScreen* preview = (MsgPreviewScreen *)msg_preview;
  if (!preview->consumeDirectSyncDebt()) preview->removeOldestPreview(false);
  _msgcount = preview->unreadPreviewCount();
  if (_msgcount == 0) {
    _popup_pending = false;
    if (dismiss_notification) clearImportantNotify();
    if (curr == msg_preview) gotoHomeScreen();
  }
  _next_refresh = 0;
#else
  (void)dismiss_notification;
#endif
}

void UITask::newMsg(uint8_t path_len, const char* from_name, const char* text, int msgcount, uint8_t flags) {
#if UI_UNREAD_DIRECT_ONLY
  (void)msgcount;
#else
  _msgcount = msgcount;
#endif
  addHourlyMessage();
#if UI_IMPORTANT_NOTIFY_ALL_MESSAGES
  flags |= UI_MSG_FLAG_IMPORTANT;
#endif
  uint8_t important_flags = flags & (UI_MSG_FLAG_DIRECT | UI_MSG_FLAG_MENTION | UI_MSG_FLAG_IMPORTANT);
  bool direct_preview = (important_flags & UI_MSG_FLAG_DIRECT) != 0;
  if (_night_prompt_active && important_flags != UI_MSG_FLAG_NONE) {
    // The message wins.  Close silently so the same button press cannot act on
    // a stale modal while the fresh DM is already visible underneath it.
    closeNightPrompt(false, true);
  }
  bool allow_standard_notify = true;
#if UI_NOTIFY_ONLY_IMPORTANT_MESSAGES
  allow_standard_notify = important_flags != UI_MSG_FLAG_NONE;
#endif
#if UI_IMPORTANT_NOTIFY_SUPPRESS_STANDARD
  if (important_flags != UI_MSG_FLAG_NONE) {
    allow_standard_notify = false;
  }
#endif
#if UI_IMPORTANT_NOTIFY_REASON_ALERT
  if (important_flags != UI_MSG_FLAG_NONE) {
    const char* reason = "Notify";
    if (important_flags & UI_MSG_FLAG_DIRECT) {
      reason = "Notify: DM";
    } else if (important_flags & UI_MSG_FLAG_MENTION) {
      reason = "Notify: @";
    }
    showAlert(reason, 1600);
  }
#endif
  uint8_t notify_mode = getNotifyMode();
  bool unread_led_enabled = isUnreadLedEnabled();
  if (areNotificationsMuted()) {
    allow_standard_notify = false;
  }
#if UI_IMPORTANT_NOTIFY_LOCAL_ONLY_WHEN_DISCONNECTED
  if (hasConnection()) {
    allow_standard_notify = false;
  }
#elif UI_IMPORTANT_NOTIFY_BLE_SMART_DELAY_MS > 0
  if (hasConnection() && important_flags != UI_MSG_FLAG_NONE) {
    allow_standard_notify = false;
  }
#endif
#if defined(PIN_MSG_ALERT) && defined(PIN_MSG_TONE)
  if (allow_standard_notify && unread_led_enabled && (notify_mode & NOTIFY_MODE_GPIO) && !((notify_mode & NOTIFY_MODE_TONE) && getMsgTonePin() == getMsgAlertPin())) {
    triggerMsgAlert();
  }
#elif defined(PIN_MSG_ALERT)
  if (allow_standard_notify && unread_led_enabled && (notify_mode & NOTIFY_MODE_GPIO)) {
    triggerMsgAlert();
  }
#endif
#ifdef PIN_MSG_TONE
  bool tone_uses_unread_led = false;
#ifdef PIN_MSG_ALERT
  tone_uses_unread_led = getMsgTonePin() == getMsgAlertPin();
#endif
  if (allow_standard_notify && (notify_mode & NOTIFY_MODE_TONE) && (unread_led_enabled || !tone_uses_unread_led)) {
    startMsgTone();
  }
#endif
  if (allow_standard_notify && (notify_mode & NOTIFY_MODE_VIBE)) {
    triggerMsgVibe();
  }

  startImportantNotify(important_flags);

  MsgPreviewScreen* preview = (MsgPreviewScreen *)msg_preview;
#if UI_UNREAD_DIRECT_ONLY
  if (direct_preview) {
    preview->addPreview(path_len, from_name, text, important_flags);
  }
  _msgcount = preview->unreadPreviewCount();
#else
  preview->addPreview(path_len, from_name, text, important_flags);
#endif
  bool should_show_preview = areMsgPopupsEnabled();
#if UI_UNREAD_DIRECT_ONLY
  should_show_preview = should_show_preview && direct_preview;
#endif
#if UI_NOTIFY_ONLY_IMPORTANT_MESSAGES
  if (important_flags == UI_MSG_FLAG_NONE) {
    should_show_preview = false;
  }
#endif
  if (should_show_preview) {
    _popup_pending = true;
    _popup_pending_important = important_flags != UI_MSG_FLAG_NONE;
    _next_refresh = 0;
  } else if (_display != NULL && _display->isOn()) {
    _next_refresh = 0;
  }
}

void UITask::userLedHandler() {
#ifdef PIN_STATUS_LED
  if (!areBoardLedsEnabled()) {
    setBoardLedPinOff(PIN_STATUS_LED);
    led_state = 0;
    return;
  }
  if (_msgcount > 0 && !isUnreadLedEnabled()) {
    setBoardLedPinOff(PIN_STATUS_LED);
    led_state = 0;
    next_led_change = millis() + LED_CYCLE_MILLIS;
    return;
  }
  uint32_t cur_time = (uint32_t)millis();
  if (smartui::deadlineDueOrImmediate(cur_time, (uint32_t)next_led_change)) {
    if (led_state == 0) {
      led_state = 1;
      if (_msgcount > 0 && isUnreadLedEnabled()) {
        last_led_increment = LED_ON_MSG_MILLIS;
      } else {
        last_led_increment = LED_ON_MILLIS;
      }
      next_led_change = cur_time + last_led_increment;
    } else {
      led_state = 0;
      next_led_change = cur_time + LED_CYCLE_MILLIS - last_led_increment;
    }
    digitalWrite(PIN_STATUS_LED, led_state == LED_STATE_ON);
  }
#endif
}

void UITask::setCurrScreen(UIScreen* c) {
  curr = c;
  _next_refresh = 100;
}

void UITask::gotoHomeFirstScreen() {
  if (home != NULL) {
    ((HomeScreen*)home)->resetToFirstPage();
    setCurrScreen(home);
  }
}

void UITask::extendAutoOff(unsigned long now) {
  if (now == 0) now = millis();
#if AUTO_OFF_MILLIS > 0
  uint32_t timeout = getBacklightTimeoutMillis();
  if (timeout == 0) timeout = AUTO_OFF_MILLIS;
  _auto_off = now + timeout;
#else
  (void)now;
#endif
}

void UITask::markDisplayWake(bool reset_to_clock) {
  unsigned long now = millis();
#if UI_WAKE_DEBUG_LOG
  Serial.printf("[DBG UI] markDisplayWake now=%lu reset=%d display_on=%d\r\n",
                now, reset_to_clock ? 1 : 0,
                (_display != NULL && _display->isOn()) ? 1 : 0);
#endif
  _display_recover_until = 0;
  _display_recover_next = 0;
  _display_recover_reset_to_clock = false;
  _button_wake_pending = false;
  _button_wake_pending_until = 0;
  _display_wake_lock_until = now + UI_DISPLAY_WAKE_LOCK_MS;
  if (reset_to_clock) {
    gotoHomeFirstScreen();
  }
  _last_activity_ms = now;
  extendAutoOff(now);
  _next_refresh = now + UI_DISPLAY_WAKE_RENDER_DELAY_MS;
}

void UITask::resetButtonStateAfterWake() {
#if defined(PIN_USER_BTN)
#if UI_WAKE_DEBUG_LOG
  bool pressed_before_reset = user_btn.isPressed();
#endif
  user_btn.reconfigure();
  user_btn.resetState(true);
#if UI_BUTTON_WAKE_IMMEDIATE_CLICK_MS > 0
  user_btn.preferImmediateClickUntil(millis() + UI_BUTTON_WAKE_IMMEDIATE_CLICK_MS);
#endif
#if UI_WAKE_DEBUG_LOG
  Serial.printf("[DBG UI] resetButtonStateAfterWake now=%lu pressed_before=%d immediate_until=%lu\r\n",
                millis(), pressed_before_reset ? 1 : 0,
                (unsigned long)(millis() + UI_BUTTON_WAKE_IMMEDIATE_CLICK_MS));
#endif
#endif
#if defined(PIN_USER_BTN_ANA)
  analog_btn.resetState(true);
#if UI_BUTTON_WAKE_IMMEDIATE_CLICK_MS > 0
  analog_btn.preferImmediateClickUntil(millis() + UI_BUTTON_WAKE_IMMEDIATE_CLICK_MS);
#endif
#endif
}

bool UITask::handleRawButtonWakeWhenDark() {
#if UI_RAW_BUTTON_WAKE_WHEN_DARK && defined(PIN_USER_BTN)
  if (_display == NULL || _display->isOn()) return false;

  user_btn.reconfigure();
  if (!user_btn.isPressed()) return false;

  unsigned long now = millis();
  clearImportantNotify();
  _display->turnOn();
  bool reset_to_clock =
#if UI_WAKE_SHOW_CLOCK
      true;
#else
      false;
#endif
  if (_display->isOn()) {
    markDisplayWake(reset_to_clock);
  } else {
    scheduleDisplayRecover(reset_to_clock, now);
  }
  resetButtonStateAfterWake();
  return true;
#else
  return false;
#endif
}

void UITask::scheduleDisplayRecover(bool reset_to_clock, unsigned long now) {
#if UI_DISPLAY_RECOVER_WINDOW_MS > 0
  _display_recover_until = now + UI_DISPLAY_RECOVER_WINDOW_MS;
  _display_recover_next = now + UI_DISPLAY_RECOVER_RETRY_MS;
  _display_recover_reset_to_clock = reset_to_clock;
  _display_wake_lock_until = now + UI_DISPLAY_RECOVER_WINDOW_MS;
#else
  (void)reset_to_clock;
  (void)now;
#endif
}

void UITask::noteButtonWakeFromSleep(unsigned long now) {
#if UI_BUTTON_WAKE_LATCH_MS > 0
#if UI_WAKE_DEBUG_LOG
  Serial.printf("[DBG UI] noteButtonWakeFromSleep now=%lu display_on=%d\r\n",
                now, (_display != NULL && _display->isOn()) ? 1 : 0);
#endif
  _button_wake_pending = true;
  _button_wake_pending_until = now + UI_BUTTON_WAKE_LATCH_MS;
  _display_wake_lock_until = now + UI_BUTTON_WAKE_LATCH_MS;
#else
  (void)now;
#endif
}

void UITask::handleButtonWakeLatch() {
#if UI_BUTTON_WAKE_LATCH_MS > 0
  if (!_button_wake_pending) return;
  unsigned long now = millis();
  if (smartui::deadlineReached((uint32_t)now,
                               (uint32_t)_button_wake_pending_until)) {
#if UI_WAKE_DEBUG_LOG
    Serial.printf("[DBG UI] buttonWakeLatch expired now=%lu\r\n", now);
#endif
    _button_wake_pending = false;
    _button_wake_pending_until = 0;
    resetButtonStateAfterWake();
    return;
  }

  if (_display != NULL && !_display->isOn()) {
#if UI_WAKE_DEBUG_LOG
    Serial.printf("[DBG UI] buttonWakeLatch turnOn begin now=%lu\r\n", now);
#endif
    _display->turnOn();
    if (_display->isOn()) {
#if UI_WAKE_DEBUG_LOG
      Serial.printf("[DBG UI] buttonWakeLatch turnOn ok now=%lu\r\n", millis());
#endif
      clearImportantNotify();
      markDisplayWake(
#if UI_WAKE_SHOW_CLOCK
          true
#else
          false
#endif
      );
      resetButtonStateAfterWake();
    } else {
#if UI_WAKE_DEBUG_LOG
      Serial.printf("[DBG UI] buttonWakeLatch turnOn failed now=%lu\r\n", millis());
#endif
      scheduleDisplayRecover(
#if UI_WAKE_SHOW_CLOCK
          true,
#else
          false,
#endif
          now);
    }
  } else {
#if UI_WAKE_DEBUG_LOG
    Serial.printf("[DBG UI] buttonWakeLatch display already on/null now=%lu display_on=%d\r\n",
                  now, (_display != NULL && _display->isOn()) ? 1 : 0);
#endif
    _button_wake_pending = false;
    _button_wake_pending_until = 0;
    resetButtonStateAfterWake();
  }
#endif
}

void UITask::displayRecoverHandler() {
#if UI_DISPLAY_RECOVER_WINDOW_MS > 0
  if (_display == NULL || _display->isOn() || _display_recover_until == 0) return;
  unsigned long now = millis();
  if (smartui::deadlineReached((uint32_t)now, (uint32_t)_display_recover_until)) {
    _display_recover_until = 0;
    _display_recover_next = 0;
    _display_recover_reset_to_clock = false;
    return;
  }
  if (smartui::deadlinePending((uint32_t)now, (uint32_t)_display_recover_next)) return;

  _display->turnOn();
  if (_display->isOn()) {
    bool reset_to_clock = _display_recover_reset_to_clock;
    _display_recover_until = 0;
    _display_recover_next = 0;
    _display_recover_reset_to_clock = false;
    markDisplayWake(reset_to_clock);
  } else {
    _display_recover_next = now + UI_DISPLAY_RECOVER_RETRY_MS;
  }
#endif
}

void UITask::updateConnectionState() {
  bool connected = hasConnection();
  if (connected != _last_connection_state) {
    _last_connection_state = connected;
    _ble_state_changed_at = millis();
#if UI_BLE_PIN_PAGE
    if (connected && home != NULL && ((HomeScreen*)home)->isBlePinPage()) {
      ((HomeScreen*)home)->resetToFirstPage();
      if (curr == home) _next_refresh = 0;
    }
#endif
  }
}

void UITask::handlePendingPopupWake() {
  if (!_popup_pending) return;
  if (!areMsgPopupsEnabled()) {
    _popup_pending = false;
    return;
  }
  if (_display == NULL || msg_preview == NULL) {
    _popup_pending = false;
    return;
  }

  setCurrScreen(msg_preview);

  if (_display->isOn()) {
    extendAutoOff();
    _next_refresh = 0;
    _popup_pending = false;
    return;
  }

#if !UI_POPUP_WAKE_WHEN_BLE_CONNECTED
  if (hasConnection()) {
    _popup_pending = false;
    return;
  }
#endif

  unsigned long now = millis();
  if ((unsigned long)(now - _ble_state_changed_at) < UI_POPUP_BLE_STATE_SETTLE_MS) {
    _next_refresh = now + UI_POPUP_BLE_STATE_SETTLE_MS;
    return;
  }
  if (smartui::optionalDeadlinePending((uint32_t)now, (uint32_t)_next_refresh)) return;

  _display->turnOn();
  if (_display->isOn()) {
    markDisplayWake(false);
    _next_refresh = 0;
    _popup_pending = false;
  } else {
    scheduleDisplayRecover(false, now);
    _next_refresh = now + UI_DISPLAY_RECOVER_RETRY_MS;
    _popup_pending = false;
  }
}

/*
  hardware-agnostic pre-shutdown activity should be done here
*/
void UITask::shutdown(bool restart, bool preserve_eink_frame) {

  #ifdef PIN_BUZZER
  /* note: we have a choice here -
     we can do a blocking buzzer.loop() with non-deterministic consequences
     or we can set a flag and delay the shutdown for a couple of seconds
     while a non-blocking buzzer.loop() plays out in UITask::loop()
  */
  buzzer.shutdown();
  uint32_t buzzer_timer = millis(); // fail-safe shutdown
  while (buzzer.isPlaying() &&
         !smartui::elapsedAtLeast((uint32_t)millis(), buzzer_timer, 2500U))
    buzzer.loop();

  #endif // PIN_BUZZER

  if (restart) {
    _board->reboot();
  } else {
#if UI_EINK_IDLE_SCREENSAVER
    if (!preserve_eink_frame && _display != NULL && idle_saver != NULL) {
      if (!_display->isOn()) {
        _display->turnOn();
      }
      _display->startFrame();
      idle_saver->render(*_display);
      _display->endFrame();
      delay(150);
    }
#endif
    (void)preserve_eink_frame;
    // PowerSaving-v17 centralises the radio/display/GPS shutdown sequence in
    // MainBoard.  Do not power peripherals down twice from the UI layer.
    _board->powerOff();
  }
}

bool UITask::isButtonPressed() const {
#ifdef PIN_USER_BTN
  return user_btn.isPressed();
#else
  return false;
#endif
}

void UITask::debugHeartbeat() {
#if UI_WAKE_DEBUG_LOG && UI_WAKE_DEBUG_HEARTBEAT_MS > 0
  static unsigned long next_debug_heartbeat = 0;
  unsigned long now = millis();
  if (smartui::optionalDeadlinePending((uint32_t)now,
                                       (uint32_t)next_debug_heartbeat)) return;
  next_debug_heartbeat = now + UI_WAKE_DEBUG_HEARTBEAT_MS;

  int btn_raw = -1;
  int btn_pressed = -1;
  int btn_prev = -1;
  int btn_cancel = -1;
  unsigned long btn_down = 0;
  uint8_t btn_clicks = 0;
  int btn_pending = 0;
  unsigned long btn_immediate_until = 0;

#ifdef PIN_USER_BTN
  btn_raw = user_btn.rawLevel();
  btn_pressed = user_btn.isPressed() ? 1 : 0;
  btn_prev = user_btn.debugPrev();
  btn_cancel = user_btn.debugCancel();
  btn_down = user_btn.debugDownAt();
  btn_clicks = user_btn.debugClickCount();
  btn_pending = user_btn.debugPendingClick() ? 1 : 0;
  btn_immediate_until = user_btn.debugImmediateClickUntil();
#endif

  Serial.printf("[DBG HB] now=%lu disp=%d conn=%d curr=%p auto_off=%lu next=%lu wake_left=%ld latch=%d latch_left=%ld recover_left=%ld btn_raw=%d btn_pressed=%d btn_prev=%d btn_cancel=%d btn_down=%lu btn_clicks=%u btn_pending=%d btn_immediate_until=%lu\r\n",
                now,
                (_display != NULL && _display->isOn()) ? 1 : 0,
                hasConnection() ? 1 : 0,
                curr,
                _auto_off,
                _next_refresh,
                _display_wake_lock_until == 0 ? 0 : (long)(_display_wake_lock_until - now),
                _button_wake_pending ? 1 : 0,
                _button_wake_pending_until == 0 ? 0 : (long)(_button_wake_pending_until - now),
                _display_recover_until == 0 ? 0 : (long)(_display_recover_until - now),
                btn_raw,
                btn_pressed,
                btn_prev,
                btn_cancel,
                btn_down,
                btn_clicks,
                btn_pending,
                btn_immediate_until);
  Serial.flush();
#endif
}

void UITask::loop() {
  updateUptime((uint32_t)millis());
  debugHeartbeat();
  updateConnectionState();
  nightModeHandler();
#if UI_BUTTON_WAKE_IRQ && defined(PIN_USER_BTN)
  noInterrupts();
  bool button_wake_irq = ui_button_wake_irq_pending;
  ui_button_wake_irq_pending = false;
  interrupts();
  if (button_wake_irq && _display != NULL && !_display->isOn()) {
    noteButtonWakeFromSleep(millis());
  }
#endif
  handleButtonWakeLatch();
  bool raw_wake_consumed = handleRawButtonWakeWhenDark();

  if (_ble_reenable_at != 0 &&
      smartui::deadlineReached((uint32_t)millis(), (uint32_t)_ble_reenable_at)) {
    enableBluetooth();
    _ble_reenable_at = 0;
    showAlert("BLE connect app", 1000);
    _next_refresh = 0;
  }

  char c = 0;
#if UI_HAS_JOYSTICK
  int ev = raw_wake_consumed ? BUTTON_EVENT_NONE : user_btn.check();
  if (ev == BUTTON_EVENT_CLICK) {
    c = checkDisplayOn(KEY_ENTER);
  } else if (ev == BUTTON_EVENT_LONG_PRESS) {
    c = handleLongPress(KEY_ENTER);  // REVISIT: could be mapped to different key code
  }
  ev = joystick_left.check();
  if (ev == BUTTON_EVENT_CLICK) {
    c = checkDisplayOn(KEY_LEFT);
  } else if (ev == BUTTON_EVENT_LONG_PRESS) {
    c = handleLongPress(KEY_LEFT);
  }
  ev = joystick_right.check();
  if (ev == BUTTON_EVENT_CLICK) {
    c = checkDisplayOn(KEY_RIGHT);
  } else if (ev == BUTTON_EVENT_LONG_PRESS) {
    c = handleLongPress(KEY_RIGHT);
  }
  ev = back_btn.check();
  if (ev == BUTTON_EVENT_TRIPLE_CLICK) {
    c = handleTripleClick(KEY_SELECT);
  }
#elif defined(PIN_USER_BTN)
  int ev = raw_wake_consumed ? BUTTON_EVENT_NONE : user_btn.check();
#if UI_WAKE_DEBUG_LOG
  if (ev != BUTTON_EVENT_NONE) {
    Serial.printf("[DBG UI] user_btn ev=%d now=%lu display_on=%d raw=%d\r\n",
                  ev, millis(), (_display != NULL && _display->isOn()) ? 1 : 0,
                  raw_wake_consumed ? 1 : 0);
  }
#endif
  if (ev == BUTTON_EVENT_CLICK) {
    c = checkDisplayOn(KEY_NEXT);
  } else if (ev == BUTTON_EVENT_LONG_PRESS) {
    c = handleLongPress(KEY_ENTER);
  } else if (ev == BUTTON_EVENT_DOUBLE_CLICK) {
    c = handleDoubleClick(KEY_PREV);
  } else if (ev == BUTTON_EVENT_TRIPLE_CLICK) {
    c = handleTripleClick(KEY_SELECT);
  }
#endif
#if defined(UI_HAS_ROTARY_INPUT)
  // Keep the PowerSaving-v17 contract: rotary movement navigates only while
  // the display is already awake, so an encoder tick cannot wake the panel.
  RotaryInputEvent rotaryEv = rotary_input.poll();
  if (c == 0 && _display != NULL && _display->isOn()) {
    if (rotaryEv == RotaryInputEvent::Next) {
      c = KEY_NEXT;
    } else if (rotaryEv == RotaryInputEvent::Prev) {
      c = KEY_PREV;
    }
  }
#endif
#if defined(PIN_USER_BTN_ANA)
  if (smartui::elapsedAtLeast((uint32_t)millis(),
                              (uint32_t)_analogue_pin_read_millis, 11U)) {
    ev = analog_btn.check();
    if (ev == BUTTON_EVENT_CLICK) {
      c = checkDisplayOn(KEY_NEXT);
    } else if (ev == BUTTON_EVENT_LONG_PRESS) {
      c = handleLongPress(KEY_ENTER);
    } else if (ev == BUTTON_EVENT_DOUBLE_CLICK) {
      c = handleDoubleClick(KEY_PREV);
    } else if (ev == BUTTON_EVENT_TRIPLE_CLICK) {
      c = handleTripleClick(KEY_SELECT);
    }
    _analogue_pin_read_millis = millis();
  }
#endif
#if defined(BACKLIGHT_BTN)
  if (smartui::deadlineDueOrImmediate((uint32_t)millis(), next_backlight_btn_check)) {
    bool touch_state = digitalRead(PIN_BUTTON2);
#if defined(DISP_BACKLIGHT)
    digitalWrite(DISP_BACKLIGHT, !touch_state);
#elif defined(EXP_PIN_BACKLIGHT)
    expander.digitalWrite(EXP_PIN_BACKLIGHT, !touch_state);
#endif
    next_backlight_btn_check = millis() + 300;
  }
#endif

  if (c != 0 && _night_prompt_active) {
    handleNightPromptInput(c);
    c = 0;
  }

  if (c != 0 && curr) {
    clearImportantNotify();
    _last_activity_ms = millis();
#if UI_EINK_IDLE_SCREENSAVER
    if (curr == idle_saver) {
      setCurrScreen(home);
      c = 0;
    }
#endif
    if (c != 0) {
      curr->handleInput(c);
    }
    extendAutoOff();
    _next_refresh = 100;  // trigger refresh
  }

  userLedHandler();
  updateHourlyMessageWindow();
#ifdef PIN_MSG_ALERT
  messageAlertHandler();
#endif
#ifdef PIN_MSG_TONE
  messageToneHandler();
#endif
  messageVibeHandler();
  bleSmartNotifyHandler();
  importantNotifyHandler();

#ifdef PIN_BUZZER
  if (buzzer.isPlaying())  buzzer.loop();
#endif

  if (curr) curr->poll();
  handlePendingPopupWake();
  displayRecoverHandler();

#if UI_EINK_IDLE_SCREENSAVER
  if (idle_saver != NULL && curr == home &&
      (unsigned long)(millis() - _last_activity_ms) >= UI_EINK_IDLE_SCREENSAVER_MILLIS &&
      smartui::deadlineDueOrImmediate((uint32_t)millis(), (uint32_t)_alert_expiry)) {
    setCurrScreen(idle_saver);
  }
#endif

#if UI_MENU_AUTO_HOME_MILLIS > 0
  if (home != NULL && curr != NULL && curr != splash &&
      smartui::deadlineDueOrImmediate((uint32_t)millis(), (uint32_t)_alert_expiry) &&
#if UI_EINK_IDLE_SCREENSAVER
      curr != idle_saver &&
#endif
      (unsigned long)(millis() - _last_activity_ms) >= UI_MENU_AUTO_HOME_MILLIS) {
    bool needs_home = curr != home || !((HomeScreen*)home)->isClockPage();
    if (needs_home) {
      ((HomeScreen*)home)->resetToFirstPage();
      if (curr != home) setCurrScreen(home);
      _last_activity_ms = millis();
      _next_refresh = 0;
    }
  }
#endif

  if (_display != NULL && _display->isOn()) {
#if UI_DISPLAY_RECOVER_ON_RENDER
    if (smartui::deadlineDueOrImmediate((uint32_t)millis(),
                                        (uint32_t)_next_refresh) && curr) {
      _display->turnOn();
      if (!_display->isOn()) {
        _next_refresh = millis() + UI_DISPLAY_RECOVER_RETRY_MS;
      }
    }
#endif
    if (_display->isOn() &&
        smartui::deadlineDueOrImmediate((uint32_t)millis(),
                                        (uint32_t)_next_refresh) && curr) {
      _display->startFrame();
      int delay_millis = curr->render(*_display);
      if (_night_prompt_active) {
        renderNightPrompt(*_display);
        _next_refresh = _night_prompt_expires != 0 ? _night_prompt_expires : millis() + 1000;
      } else if (smartui::optionalDeadlinePending((uint32_t)millis(),
                                                  (uint32_t)_alert_expiry)) {
        _display->setTextSize(1);
        int line_h = _display->getTextLineHeight();
        int pad_x = _display->width() >= 150 ? 8 : 5;
        int pad_y = _display->height() >= 80 ? 4 : 3;
        int max_w = _display->width() - 4;
        int text_w = _display->getTextWidth(_alert);
        int box_w = text_w + pad_x * 2;
        if (box_w > max_w) box_w = max_w;
        int box_h = line_h + pad_y * 2;
        if (box_h > _display->height() - 4) box_h = _display->height() - 4;
        int x = (_display->width() - box_w) / 2;
        int y = (_display->height() - box_h) / 2;
        _display->setColor(DisplayDriver::DARK);
        _display->fillRect(x, y, box_w, box_h);
        _display->setColor(getUiTopColor());
        _display->drawRect(x, y, box_w, box_h);
        drawRichTextCenteredEllipsized(*_display, _display->width() / 2, y + pad_y, box_w - pad_x * 2, _alert);
        _next_refresh = _alert_expiry;   // will need refresh when alert is dismissed
      } else {
        _next_refresh = millis() + delay_millis;
      }
      _display->endFrame();
    }
#if AUTO_OFF_MILLIS > 0
    if (_display->isOn() && (UI_AUTO_OFF_ALL_WINDOWS || !curr->keepDisplayOn()) &&
        smartui::deadlineReached((uint32_t)millis(), (uint32_t)_auto_off)) {
#if UI_WAKE_DEBUG_LOG
      Serial.printf("[DBG UI] autoOff turnOff now=%lu auto_off=%lu curr_keep=%d\r\n",
                    millis(), _auto_off, curr->keepDisplayOn() ? 1 : 0);
#endif
      _display->turnOff();
    }
#endif
  }

#ifdef PIN_VIBRATION
  vibration.loop();
#endif

#if defined(AUTO_SHUTDOWN_MILLIVOLTS)
  const uint16_t shutdownThreshold = getLowBatteryShutdownThreshold();
  if (shutdownThreshold == 0) {
    _low_batt_strikes = 0;
  } else if (smartui::deadlineDueOrImmediate((uint32_t)millis(), (uint32_t)next_batt_chck)) {
    const smartui::BatteryReading reading = readSafetyBattery();
    _low_batt_strikes = smartui::nextLowBatteryStrikeCount(_low_batt_strikes,
        reading, shutdownThreshold, LOW_BATTERY_SHUTDOWN_CONFIRM_COUNT);

    if (_low_batt_strikes >= LOW_BATTERY_SHUTDOWN_CONFIRM_COUNT) {

      // show low battery shutdown alert
      // we should only do this for eink displays, which will persist after power loss
      #if defined(THINKNODE_M1) || defined(LILYGO_TECHO) || defined(HELTEC_WIRELESS_PAPER)
      if (_display != NULL) {
        if (!_display->isOn()) _display->turnOn();
        _display->startFrame();
        _display->setTextSize(2);
        _display->setColor(DisplayDriver::RED);
        const int line_h = _display->getTextLineHeight();
        const int top = (_display->height() - line_h * 2 - 4) / 2;
        _display->drawTextCentered(_display->width() / 2, top, "АКБ села");
        _display->drawTextCentered(_display->width() / 2, top + line_h + 4, "Выключаюсь");
        _display->endFrame();
        delay(150);
      }
      #endif

      // E-paper retains this safety message without consuming standby power.
      shutdown(false, true);

    }
    next_batt_chck = (uint32_t)millis() + LOW_BATTERY_SHUTDOWN_CHECK_MILLIS;
  }
#endif
}

char UITask::checkDisplayOn(char c) {
  if (_display != NULL) {
    bool checked_display = false;
#if UI_DISPLAY_VALIDATE_ON_INPUT
    if (_display->isOn()) {
      _display->turnOn();
      checked_display = true;
    }
#endif
    if (!_display->isOn()) {
      unsigned long now = millis();
#if UI_WAKE_DEBUG_LOG
      Serial.printf("[DBG UI] checkDisplayOn turnOn begin now=%lu c=%d checked=%d\r\n",
                    now, (int)c, checked_display ? 1 : 0);
#endif
      if (!checked_display) {
        _display->turnOn();   // turn display on and consume event
      }
      clearImportantNotify();
      bool reset_to_clock =
#if UI_WAKE_SHOW_CLOCK
          true;
#else
          false;
#endif
      if (_display->isOn()) {
#if UI_WAKE_DEBUG_LOG
        Serial.printf("[DBG UI] checkDisplayOn turnOn ok now=%lu\r\n", millis());
#endif
        markDisplayWake(reset_to_clock);
        resetButtonStateAfterWake();
      } else {
#if UI_WAKE_DEBUG_LOG
        Serial.printf("[DBG UI] checkDisplayOn turnOn failed now=%lu\r\n", millis());
#endif
        scheduleDisplayRecover(reset_to_clock, now);
      }
      c = 0;
      return c;
    }
    _last_activity_ms = millis();
    extendAutoOff();
    _next_refresh = 0;  // trigger refresh
  }
  return c;
}

char UITask::handleLongPress(char c) {
  if (_night_prompt_active) {
    return KEY_ENTER;
  }
#if USER_BUTTON_LONG_PRESS_POWEROFF
  if (millis() - ui_started_at >= USER_BUTTON_POWEROFF_AFTER_BOOT_MILLIS) {
    shutdown();
    return 0;
  }
#endif
  #if UI_LONG_PRESS_WAKES_DISPLAY
  if (_display != NULL && !_display->isOn()) {
    checkDisplayOn(c);
    return 0;
  }
  #endif
  if (millis() - ui_started_at < 8000) {   // long press in first 8 seconds since startup -> CLI/rescue
    the_mesh.enterCLIRescue();
    c = 0;   // consume event
  }
  if (c != 0 && curr == home && home != NULL && ((HomeScreen*)home)->isClockPage()) {
    toggleNotificationsMuted();
    return 0;
  }
  return c;
}

char UITask::handleDoubleClick(char c) {
  MESH_DEBUG_PRINTLN("UITask: double click triggered");
  c = checkDisplayOn(c);
  if (c != 0 && curr == home && home != NULL &&
      ((HomeScreen*)home)->restoreAdcDefault(2)) {
    return 0;
  }
  return c;
}

char UITask::handleTripleClick(char c) {
  MESH_DEBUG_PRINTLN("UITask: triple click triggered");
  checkDisplayOn(c);
  gotoHomeFirstScreen();
  c = 0;
  return c;
}

bool UITask::getGPSState() {
#if UI_PHONE_GPS == 1
  if (the_mesh.isPhoneGpsEnabled()) return true;
#endif
  if (_sensors != NULL) {
    int num = _sensors->getNumSettings();
    for (int i = 0; i < num; i++) {
      if (strcmp(_sensors->getSettingName(i), "gps") == 0) {
        return !strcmp(_sensors->getSettingValue(i), "1");
      }
    }
  }
  return false;
}

void UITask::toggleGPS() {
  bool has_hardware = false;
  bool hardware_on = false;
  if (_sensors != NULL) {
    int num = _sensors->getNumSettings();
    for (int i = 0; i < num; i++) {
      if (strcmp(_sensors->getSettingName(i), "gps") == 0) {
        has_hardware = true;
        hardware_on = strcmp(_sensors->getSettingValue(i), "1") == 0;
        break;
      }
    }
  }

  const char* state = "ВЫКЛ";
#if UI_PHONE_GPS == 1
  if (the_mesh.isPhoneGpsEnabled()) {
    the_mesh.setGpsSource(GPS_SOURCE_HW, false);
    if (has_hardware) _sensors->setSettingValue("gps", "0");
    _node_prefs->gps_enabled = 0;
  } else if (has_hardware && !hardware_on) {
    the_mesh.setGpsSource(GPS_SOURCE_HW, false);
    _sensors->setSettingValue("gps", "1");
    _node_prefs->gps_enabled = 1;
    state = "МОДУЛЬ";
  } else {
    if (has_hardware) _sensors->setSettingValue("gps", "0");
    _node_prefs->gps_enabled = 0;
    the_mesh.setGpsSource(GPS_SOURCE_PHONE, false);
    state = "ТЕЛЕФОН";
  }
#else
  // EXP45 stable path: only a real onboard GPS can be toggled.  Do not offer
  // the former Phone GPS state, because the stock companion app cannot feed it.
  the_mesh.setGpsSource(GPS_SOURCE_HW, false);
  if (!has_hardware) {
    _node_prefs->gps_enabled = 0;
    the_mesh.savePrefs();
    showAlert("GPS-модуль не найден", 1100);
    _next_refresh = 0;
    return;
  }
  hardware_on = !hardware_on;
  _sensors->setSettingValue("gps", hardware_on ? "1" : "0");
  _node_prefs->gps_enabled = hardware_on ? 1 : 0;
  state = hardware_on ? "ВКЛ" : "ВЫКЛ";
#endif

  the_mesh.savePrefs();
  notify(UIEventType::ack);
  char alert[20];
  snprintf(alert, sizeof(alert), "GPS: %s", state);
  showAlert(alert, 800);
  _next_refresh = 0;
}

float UITask::getAdcMultiplier() const {
  return _board->getAdcMultiplier();
}

bool UITask::setAdcMultiplier(float multiplier, bool save) {
  if (!isfinite(multiplier) || multiplier < 0.0f) {
    return false;
  }
  const float previous_multiplier = _board->getAdcMultiplier();
  const float previous_pref = _node_prefs ? _node_prefs->adc_multiplier : 0.0f;
  if (!_board->setAdcMultiplier(multiplier)) {
    return false;
  }
  invalidateBatteryCache();
  if (save) {
    if (_node_prefs == NULL) {
      _board->setAdcMultiplier(previous_multiplier);
      invalidateBatteryCache();
      return false;
    }
    _node_prefs->adc_multiplier = multiplier;
    if (!the_mesh.savePrefs()) {
      _node_prefs->adc_multiplier = previous_pref;
      // During edit the board already carries the draft value, so the only
      // durable rollback source is the last committed preference.
      if (!_board->setAdcMultiplier(previous_pref)) {
        _board->setAdcMultiplier(0.0f);
      }
      invalidateBatteryCache();
      _next_refresh = 0;
      return false;
    }
    notify(UIEventType::ack);
  }
  _next_refresh = 0;
  return true;
}

void UITask::toggleBuzzer() {
    // Toggle buzzer quiet mode
  #ifdef PIN_BUZZER
    if (buzzer.isQuiet()) {
      buzzer.quiet(false);
      notify(UIEventType::ack);
    } else {
      buzzer.quiet(true);
    }
    _node_prefs->buzzer_quiet = buzzer.isQuiet();
    the_mesh.savePrefs();
    showAlert(buzzer.isQuiet() ? "Зумер: ВЫКЛ" : "Зумер: ВКЛ", 800);
    _next_refresh = 0;  // trigger refresh
  #endif
}
