#include <Arduino.h>   // needed for PlatformIO
#include <Mesh.h>
#include "MyMesh.h"
#include <helpers/SmartUiBuildInfo.h>

#ifndef SMARTUI_HEADLESS
  #define SMARTUI_HEADLESS 0
#endif

#ifdef ESP32_PLATFORM
#include "esp_pm.h"
#include "esp_bt.h"
#include <helpers/SmartUiSleepPolicy.h>
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
static esp_pm_lock_handle_t companion_sleep_lock = nullptr;
static bool companion_sleep_lock_held = false;
static bool companion_wifi_awake = false;
#endif
#endif

// Believe it or not, this std C function is busted on some platforms!
static uint32_t _atoi(const char* sp) {
  uint32_t n = 0;
  while (*sp && *sp >= '0' && *sp <= '9') {
    n *= 10;
    n += (*sp++ - '0');
  }
  return n;
}

// interface manager
#include <helpers/MultiSerialInterface.h>
MultiSerialInterface interface_manager;

#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  #include "ConnectionController.h"
  #include "DeviceSettings.h"
  #include "SmartUiApi.h"
  #include "SmartUiSyncApi.h"
#endif

// include bluetooth interface
#if defined(BLE_PIN_CODE)
  #ifdef ESP32
    // include esp32 bluetooth interface
    #include <helpers/esp32/SerialBLEInterface.h>
    SerialBLEInterface bluetooth_interface;
  #elif defined(NRF52_PLATFORM)
    // include nrf52 bluetooth interface
    #include <helpers/nrf52/SerialBLEInterface.h>
    SerialBLEInterface bluetooth_interface;
  #else
    #error "SerialBLEInterface is not defined for this platform"
  #endif
#endif

// include wifi interface
#if defined(WIFI_SSID) || \
    (defined(ESP32) && defined(SMARTUI_CONNECTION_SELECTOR) && \
     SMARTUI_CONNECTION_SELECTOR)
  #ifndef TCP_PORT
    #define TCP_PORT 5000
  #endif
  #ifdef ESP32
    // include esp32 wifi interface
    #include <helpers/esp32/SerialWifiInterface.h>
    SerialWifiInterface wifi_interface;
  #else
    #error "SerialWifiInterface is not defined for this platform"
  #endif
#endif

// include usb interface
#if defined(ENABLE_USB_INTERFACE)
  #include <helpers/ArduinoSerialInterface.h>
  ArduinoSerialInterface usb_serial_interface;
#endif

// include ethernet interface
#if defined(ETHERNET_ENABLED)
  #include <helpers/ethernet/EthernetInterface.h>
  ETHERNET_CLASS ethernet_interface;
#endif

// include hardware serial interface
#if defined(SERIAL_RX)
  #include <helpers/ArduinoSerialInterface.h>
  ArduinoSerialInterface hardware_serial_interface;
  HardwareSerial companion_serial(1);
#endif

// platform file system
#if defined(NRF52_PLATFORM) || defined(STM32_PLATFORM)
  #include <InternalFileSystem.h>
  #if defined(QSPIFLASH)
    #include <CustomLFS_QSPIFlash.h>
    DataStore store(InternalFS, QSPIFlash, rtc_clock);
  #else
    #if defined(EXTRAFS)
      #include <CustomLFS.h>
      CustomLFS ExtraFS(0xD4000, 0x19000, 128);
      DataStore store(InternalFS, ExtraFS, rtc_clock);
    #else
      DataStore store(InternalFS, rtc_clock);
    #endif
  #endif
#elif defined(RP2040_PLATFORM)
  #include <LittleFS.h>
  DataStore store(LittleFS, rtc_clock);
#elif defined(ESP32)
  #include <SPIFFS.h>
  DataStore store(SPIFFS, rtc_clock);
#endif

/* GLOBAL OBJECTS */
#ifdef DISPLAY_CLASS
  #include "UITask.h"
  UITask ui_task(&board, &interface_manager);
  #if defined(HELTEC_WIRELESS_PAPER)
    static bool paper_display_attached = false;
  #endif
#endif

StdRNG fast_rng;
SimpleMeshTables tables;
MyMesh the_mesh(radio_driver, fast_rng, rtc_clock, tables, store
   #ifdef DISPLAY_CLASS
      , &ui_task
   #endif
);

#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
static smartui::DeviceSettings device_settings;
// Separate preview-token domain: USB console tokens are not API tokens.
static smartui::DeviceSettings api_device_settings;
static smartui::SmartUiApi smartui_api;
static smartui::SmartUiSync smartui_sync;
static smartui::SmartUiSyncApi smartui_sync_api;
static uint32_t sync_hint_cursor = 0;
static uint32_t sync_hint_at = 0;
enum DeviceSettingEffect : uint8_t {
  EFFECT_ADC = 1, EFFECT_GPS = 2, EFFECT_LED = 4,
  EFFECT_LNA = 8, EFFECT_PA = 16, EFFECT_NOTIFY = 32,
};
static uint8_t device_setting_effects = 0;

static smartui::DeviceSettingsState readDeviceSettings() {
  const NodePrefs& p = *the_mesh.getNodePrefs();
  smartui::DeviceSettingsState s;
  s.adc_override = p.adc_multiplier;
  s.notify_mode = p.notify_mode;
  s.important_notify_mode = p.important_notify_mode;
  s.sound_quiet = p.buzzer_quiet;
  s.vibe_quiet = p.vibe_quiet;
  s.volume = p.notify_tone_volume;
  s.melody = p.notify_tone_id;
  s.melody_dm = p.notify_tone_dm_id;
  s.melody_mention = p.notify_tone_mention_id;
  s.melody_system = p.notify_tone_system_id;
  s.board_led = p.board_leds_enabled;
  s.unread_led = p.unread_led_enabled;
  s.gps = p.gps_enabled;
  s.gps_source = p.gps_source;
  s.battery_protection = p.low_battery_shutdown_enabled;
  s.muted = p.notifications_muted;
  s.night_quiet = p.night_quiet_active;
  s.profile = p.smart_profile_id;
  s.agc_reset = p.agc_reset_enabled;
  s.fem_lna = p.radio_fem_rxgain;
  s.fem_pa = p.radio_fem_txgain;
  s.bridge = p.notify_tone_bridge_enabled;
  return s;
}

static void writeDeviceSettings(const smartui::DeviceSettingsState& s) {
  NodePrefs& p = *the_mesh.getNodePrefs();
  // Recomputed on each candidate/rollback. Persistence failure never applies
  // these effects. Unrelated changes must not restart radio RX or AGC work.
  device_setting_effects = 0;
  if (p.adc_multiplier != s.adc_override) device_setting_effects |= EFFECT_ADC;
  if (p.gps_enabled != s.gps || p.gps_source != s.gps_source) device_setting_effects |= EFFECT_GPS;
  if (p.board_leds_enabled != s.board_led) device_setting_effects |= EFFECT_LED;
  if (p.radio_fem_rxgain != s.fem_lna) device_setting_effects |= EFFECT_LNA;
  if (p.radio_fem_txgain != s.fem_pa) device_setting_effects |= EFFECT_PA;
  if (p.notify_mode != s.notify_mode || p.important_notify_mode != s.important_notify_mode ||
      p.buzzer_quiet != s.sound_quiet || p.vibe_quiet != s.vibe_quiet ||
      p.notify_tone_volume != s.volume || p.notify_tone_id != s.melody ||
      p.notify_tone_dm_id != s.melody_dm || p.notify_tone_mention_id != s.melody_mention ||
      p.notify_tone_system_id != s.melody_system || p.unread_led_enabled != s.unread_led ||
      p.notifications_muted != s.muted || p.night_quiet_active != s.night_quiet)
    device_setting_effects |= EFFECT_NOTIFY;
  p.adc_multiplier = s.adc_override;
  p.notify_mode = s.notify_mode;
  p.important_notify_mode = s.important_notify_mode;
  p.buzzer_quiet = s.sound_quiet;
  p.vibe_quiet = s.vibe_quiet;
  p.notify_tone_volume = s.volume;
  p.notify_tone_id = s.melody;
  p.notify_tone_dm_id = s.melody_dm;
  p.notify_tone_mention_id = s.melody_mention;
  p.notify_tone_system_id = s.melody_system;
  p.board_leds_enabled = s.board_led;
  p.unread_led_enabled = s.unread_led;
  p.gps_enabled = s.gps;
  p.gps_source = s.gps_source;
  p.low_battery_shutdown_enabled = s.battery_protection;
  p.notifications_muted = s.muted;
  p.night_quiet_active = s.night_quiet;
  p.smart_profile_id = s.profile;
  p.agc_reset_enabled = s.agc_reset;
  p.radio_fem_rxgain = s.fem_lna;
  p.radio_fem_txgain = s.fem_pa;
}

static smartui::DeviceSettingsCaps deviceSettingsCapabilities() {
  smartui::DeviceSettingsCaps c;
  c.agc_reset = the_mesh.supportsPeriodicAgcReset();
  c.fem_lna = board.canControlLoRaFemLna();
  c.fem_pa = board.canControlLoRaFemPaGain();
#ifdef ADC_MULTIPLIER
  c.adc_default = ADC_MULTIPLIER;
  c.adc = c.adc_default > 0 && board.getAdcMultiplier() > 0;
#endif
#ifdef DISPLAY_CLASS
  c.display = ui_task.hasDisplay();
  c.bridge = ui_task.supportsNotifyToneBridge();
  c.sound = ui_task.getNotifyTonePin() >= 0;
  c.unread_led = ui_task.getNotifyLedPin() >= 0;
  c.vibration = ui_task.getNotifyVibePin() >= 0;
#if UI_NOTIFY_ONLY_IMPORTANT_MESSAGES == 1
  c.effective_notify_mode = ui_task.getImportantNotifyMode();
#else
  c.effective_notify_mode = ui_task.getNotifyMode();
#endif
  c.melody_max = ui_task.getNotifyToneCount() ? ui_task.getNotifyToneCount() - 1 : 0;
#if defined(PIN_STATUS_LED) && PIN_STATUS_LED >= 0
  c.unread_led = true;
#endif
#if defined(AUTO_SHUTDOWN_MILLIVOLTS) && AUTO_SHUTDOWN_MILLIVOLTS > 0
  c.battery_protection = true;
#endif
#endif
#if (defined(PIN_LED) && PIN_LED >= 0) || (defined(LED_BUILTIN) && LED_BUILTIN >= 0) || \
    (defined(PIN_STATUS_LED) && PIN_STATUS_LED >= 0) || (defined(P_LORA_TX_LED) && P_LORA_TX_LED >= 0)
  c.board_led = true;
#endif
#if ENV_INCLUDE_GPS == 1
  c.gps = sensors.getLocationProvider() != nullptr;
#endif
  return c;
}

static bool saveDeviceSettings() {
  // savePrefs refreshes location fields too. Restore those incidental RAM
  // changes if persistence fails, in addition to the service's small snapshot.
  NodePrefs& prefs = *the_mesh.getNodePrefs();
  const double latitude = prefs.node_lat;
  const double longitude = prefs.node_lon;
  if (the_mesh.savePrefs()) return true;
  prefs.node_lat = latitude;
  prefs.node_lon = longitude;
  return false;
}
static uint16_t deviceBatteryMilliVolts() { return board.getBattMilliVolts(); }
static bool deviceBatteryCalibrationSample(uint16_t& millivolts, float& multiplier,
                                           uint32_t& age_ms) {
  return board.getBatteryCalibrationSample(millivolts, multiplier, age_ms);
}
static float deviceAdcMultiplier() { return board.getAdcMultiplier(); }
static uint32_t deviceSettingsMillis() { return static_cast<uint32_t>(millis()); }
static void applyDeviceSettings(bool battery_changed) {
  const NodePrefs& p = *the_mesh.getNodePrefs();
  const uint8_t effects = device_setting_effects;
  device_setting_effects = 0;
  if (effects & EFFECT_ADC) board.setAdcMultiplier(p.adc_multiplier);
  if (effects & EFFECT_LED) meshcoreSetBoardLedsEnabled(p.board_leds_enabled != 0);
  if (effects & EFFECT_LNA) board.setLoRaFemLnaEnabled(p.radio_fem_rxgain != 0);
  if (effects & EFFECT_PA) board.setLoRaFemPaGainEnabled(p.radio_fem_txgain != 0);
#if ENV_INCLUDE_GPS == 1
  if (effects & EFFECT_GPS) the_mesh.applyGpsPrefs();
#endif
#ifdef DISPLAY_CLASS
  if (battery_changed || (effects & (EFFECT_NOTIFY | EFFECT_LED)))
    ui_task.applyDeviceSettingsRuntime(battery_changed);
#else
  (void)battery_changed;
#endif
}
static void testDeviceNotification() {
#ifdef DISPLAY_CLASS
  ui_task.previewNotifyMode();
#endif
}
static bool handleCompanionDeviceSettings(const char* command, char* reply,
                                          size_t capacity, bool allow_mutation) {
  return device_settings.handle(command, reply, capacity, allow_mutation);
}

static const char* apiMelodyName(uint8_t id) {
#ifdef DISPLAY_CLASS
  return ui_task.getNotifyToneName(id);
#else
  (void)id;
  return nullptr;
#endif
}

static bool apiSetToneBridge(bool enabled) {
#ifdef DISPLAY_CLASS
  return ui_task.setNotifyToneBridgeEnabled(enabled);
#else
  (void)enabled;
  return false;
#endif
}

static const char* apiTransportName(CompanionMode mode) {
  return mode == CompanionMode::WiFi ? "wifi" : mode == CompanionMode::USB ? "usb" : "ble";
}

void noteSmartUiMessage(uint32_t generation, uint8_t flags) {
  smartui_sync.noteMessage(generation, flags);
}

static void localSyncAction(uint32_t generation, smartui::SyncAction action, uint32_t value) {
  smartui_sync.apply(generation, action, value);
}

static int syncPeekFrame(uint8_t* frame, uint32_t& generation, uint8_t& flags) {
  return the_mesh.apiPeekOfflineFrame(frame, generation, flags);
}

static bool syncReceiveFrame(uint32_t generation) { return the_mesh.apiReceiveOfflineFrame(generation); }

static bool syncMessageAction(uint32_t generation, smartui::SyncAction action, uint32_t value) {
#ifdef DISPLAY_CLASS
  return ui_task.applyMessageAction(generation, action, value);
#else
  (void)generation; (void)value;
  return action == smartui::SyncAction::Read || action == smartui::SyncAction::Dismiss;
#endif
}

static void syncReadPolicy(bool enabled) {
#ifdef DISPLAY_CLASS
  ui_task.setExplicitReadPolicy(enabled);
#else
  (void)enabled;
#endif
}

static bool syncCanSnooze(uint32_t generation) {
#ifdef DISPLAY_CLASS
  return ui_task.canSnoozeMessage(generation);
#else
  (void)generation;
  return false;
#endif
}

static uint32_t syncNotificationGeneration() {
#ifdef DISPLAY_CLASS
  return ui_task.notificationGeneration();
#else
  return 0;
#endif
}

// Observe RAM state, not flash bytes or credentials. This adds no ADC reads,
// persistent writes, wake deadlines or power-management locks.
static void serviceSmartUiSync() {
  const uint32_t now = (uint32_t)millis();
  static bool observed = false;
  static uint32_t observed_at = 0, settings_hash = 0, connection_bits = 0, notification = 0;
  static uint16_t battery_mv = 0;
  static uint8_t battery_state = 0;
  if (!observed || (uint32_t)(now - observed_at) >= 1000U) {
    observed_at = now;
    const auto s = readDeviceSettings();
    uint32_t hash = 2166136261UL;
    auto mix = [&](uint32_t n) { for (unsigned i = 0; i < 4; ++i) { hash ^= n & 255U; hash *= 16777619UL; n >>= 8; } };
    uint32_t adc_bits = 0;
    static_assert(sizeof(adc_bits) == sizeof(s.adc_override), "ADC fingerprint width");
    memcpy(&adc_bits, &s.adc_override, sizeof(adc_bits));
    mix(adc_bits);
    mix(s.notify_mode); mix(s.important_notify_mode); mix(s.sound_quiet); mix(s.vibe_quiet);
    mix(s.volume); mix(s.melody); mix(s.board_led); mix(s.unread_led); mix(s.gps); mix(s.gps_source);
    mix(s.battery_protection); mix(s.muted); mix(s.night_quiet); mix(s.agc_reset); mix(s.fem_lna); mix(s.fem_pa); mix(s.bridge);
    const CompanionStatus connection = connection_controller.status();
    const uint32_t bits = (uint32_t)connection.selected | (connection.clientConnected ? 4U : 0U) |
        (connection.wifiAssociated ? 8U : 0U) | (connection.wifiConfigured ? 16U : 0U);
    const uint32_t active = syncNotificationGeneration();
    if (observed && hash != settings_hash) smartui_sync.emitState(smartui::SyncEventKind::Setting, hash);
    if (observed && bits != connection_bits) smartui_sync.emitState(smartui::SyncEventKind::Connection, bits);
    if (observed && active != notification) smartui_sync.emitState(smartui::SyncEventKind::Notification, active ? 1U : 0U);
    settings_hash = hash; connection_bits = bits; notification = active;
#ifdef DISPLAY_CLASS
    uint16_t mv = 0; uint32_t sampled_at = 0;
    const bool valid = ui_task.peekBatterySample(mv, sampled_at) && mv && (uint32_t)(now - sampled_at) <= 120000U;
    // Informational low-voltage state, not a shutdown prediction. Hysteresis
    // avoids event storms near 3.3 V; the existing safety policy is unchanged.
    const uint8_t state = !valid ? 3 : (mv <= 3300 || (battery_state == 2 && mv < 3400)) ? 2 : 1;
    const unsigned delta = mv > battery_mv ? mv - battery_mv : battery_mv - mv;
    if (state != battery_state || (valid && delta >= 50)) {
      smartui_sync.emitState(smartui::SyncEventKind::Battery, valid ? mv : 0, state);
      // Compare with the last emitted voltage, not the previous sample: slow
      // discharge must eventually cross the 50 mV reporting threshold too.
      battery_mv = mv;
    }
    battery_state = state;
#endif
    observed = true;
  }
  const uint8_t subscriptions = smartui_sync_api.subscriptions();
  if (!subscriptions || !interface_manager.isConnected()) { sync_hint_cursor = smartui_sync.newestEvent(); return; }
  if (sync_hint_cursor == smartui_sync.newestEvent() || interface_manager.hasPendingTx() ||
      (uint32_t)(now - sync_hint_at) < 250U) return;
  uint32_t cursor = sync_hint_cursor;
  uint8_t changed = 0;
  smartui::SyncEvent event;
  for (unsigned i = 0; i < smartui::SmartUiSync::EVENT_CAPACITY; ++i) {
    const auto result = smartui_sync.eventAfter(cursor, event);
    if (result == smartui::SyncEventResult::Gap) { changed = 15; break; }
    if (result != smartui::SyncEventResult::Event) break;
    cursor = event.seq;
    changed |= event.kind == smartui::SyncEventKind::Setting ? 2 :
        event.kind == smartui::SyncEventKind::Connection ? 4 :
        event.kind == smartui::SyncEventKind::Battery ? 8 : 1;
  }
  changed &= subscriptions;
  if (!changed) { sync_hint_cursor = smartui_sync.newestEvent(); return; }
  uint8_t frame[smartui::SmartUiApi::MAX_FRAME] = {201, 'S', 'U', 'I', 1, 0, 0, 3, 0, 0, 0, 0, 0};
  const uint64_t boot = smartui_sync.boot();
  const int length = snprintf((char*)frame + 13, sizeof(frame) - 13,
      "EV api events boot=%08lx%08lx cursor=%lu mask=%u", (unsigned long)(uint32_t)(boot >> 32),
      (unsigned long)(uint32_t)boot, (unsigned long)smartui_sync.newestEvent(), changed);
  if (length <= 0 || size_t(length) >= sizeof(frame) - 13) return;
  frame[11] = uint8_t(length); frame[12] = uint8_t(length >> 8);
  sync_hint_at = now;
  if (interface_manager.writeFrame(frame, size_t(length) + 13) == size_t(length) + 13)
    sync_hint_cursor = smartui_sync.newestEvent();
}

static bool executeSmartUiApi(const char* command, char* reply, size_t capacity,
                              bool allow_mutation) {
  // The reusable service also speaks the USB legacy grammar. Never expose
  // that grammar through this wire namespace (including commands with effects).
  if (strncmp(command, "api ", 4) != 0) {
    snprintf(reply, capacity, "ERR api unsupported");
    return true;
  }
  const CompanionStatus status = connection_controller.status();
  if (strcmp(command, "api hello") == 0) {
    snprintf(reply, capacity,
        "OK api hello v=1 firmware=%s stage=release max_command=152 max_reply=479 max_frame=160 transport=%s write=%u events=1 sync=1 wifi_setup=%u",
        SMARTUI_VERSION, apiTransportName(status.selected), allow_mutation ? 1U : 0U,
        (status.capabilities & COMPANION_CAP_WIFI) && status.selected != CompanionMode::WiFi ? 1U : 0U);
    return true;
  }
  if (strcmp(command, "api connection") == 0) {
    snprintf(reply, capacity,
        "OK api connection selected=%s via=%s caps=%u wifi_configured=%u wifi_associated=%u ip=%s readonly=%u",
        apiTransportName(status.selected), status.clientConnected ? apiTransportName(status.connectedVia) : "none",
        status.capabilities, status.wifiConfigured, status.wifiAssociated,
        status.wifiLocalIp[0] ? status.wifiLocalIp : "none", allow_mutation ? 0U : 1U);
    return true;
  }
  // This controller owns the staged Wi-Fi workflow and deferred mode switch.
  // It must run before the ordinary settings busy guard, or its own pending
  // transaction would block status/save/cancel forever.
  if (connection_controller.handleApiCommand(command, reply, capacity, allow_mutation)) return true;
  if (smartui_sync_api.handle(command, reply, capacity, allow_mutation)) return true;
  if (strcmp(command, "api notify status") == 0) {
    const uint32_t generation = syncNotificationGeneration();
    snprintf(reply, capacity, "OK api notify active=%u id=%08lx muted=%u", generation ? 1U : 0U,
             (unsigned long)generation, readDeviceSettings().muted ? 1U : 0U);
    return true;
  }
  // No arbitrary CLI passthrough or raw GPIO writes. TCP retains the existing
  // companion trust model: no extra authentication or TLS; trusted LAN only.
  const bool read = strcmp(command, "api caps") == 0 || strcmp(command, "api get") == 0 ||
                    strncmp(command, "api melody ", 11) == 0;
  if (!read && connection_controller.deviceApiBusy()) {
    snprintf(reply, capacity, "ERR api busy");
    return true;
  }
  if (!read && !allow_mutation) {
    snprintf(reply, capacity, "ERR api readonly");
    return true;
  }
  // Do not change FEM gain during a packet, queued TX, or radio maintenance.
  if (strncmp(command, "api set fem_", 12) == 0 &&
      (the_mesh.hasPendingWork() || radio_driver.isReceiving() || !radio_driver.isInRecvMode())) {
    snprintf(reply, capacity, "ERR api busy");
    return true;
  }
  return api_device_settings.handle(command, reply, capacity, allow_mutation);
}

size_t handleSmartUiApiFrame(const uint8_t* request, size_t length,
                            uint8_t* response, size_t capacity) {
  const bool writable = connection_controller.deviceApiWritesAllowed();
  return smartui_api.handle(request, length, response, capacity, writable);
}

void resetSmartUiApiSession() {
  smartui_api.resetSession();
  smartui_sync_api.resetSession();
  sync_hint_cursor = smartui_sync.newestEvent();
  api_device_settings.resetSession();
  connection_controller.resetApiSession();
}

static void resetCompanionSession() {
  the_mesh.resetLocalAppSession();
}

static void setWifiSleepInhibit(bool inhibit) {
#if defined(ESP32)
  board.setInhibitSleep(inhibit);
  companion_wifi_awake = inhibit;
  // This firmware uses automatic IDF sleep, not ESP32Board::sleep().
  // Acquire before WiFi setup can yield; release is reconciled in loop().
  if (inhibit && companion_sleep_lock && !companion_sleep_lock_held) {
    companion_sleep_lock_held = esp_pm_lock_acquire(companion_sleep_lock) == ESP_OK;
  }
#else
  (void)inhibit;
#endif
}

static bool isCompanionCliRescue() {
  return the_mesh.isCLIRescue();
}

static const char* companionBoardName() {
  return board.getManufacturerName();
}

static const char* companionQuickReply(uint8_t slot) {
  return the_mesh.getQuickReplyOverride(slot);
}

static bool setCompanionQuickReply(uint8_t slot, const char* text) {
  return the_mesh.setQuickReplyOverride(slot, text);
}

static bool isCompanionStorageQuarantined() {
  return the_mesh.isStorageRecoveryRequired();
}

#if defined(ENABLE_USB_INTERFACE) && \
    (defined(NRF52_PLATFORM) || \
     (defined(ESP32) && defined(ARDUINO_USB_CDC_ON_BOOT) && \
      ARDUINO_USB_CDC_ON_BOOT))
static bool isUsbCompanionLinkPresent(void*) {
#if defined(NRF52_PLATFORM)
  return Serial.dtr();
#else
  return static_cast<bool>(Serial);
#endif
}
#endif
#endif

/* END GLOBAL OBJECTS */

static bool radio_initialized = false;

#include "ui-new/RecoveryBatteryGuard.h"

static void serviceFatalBatterySafety() {
#if defined(AUTO_SHUTDOWN_MILLIVOLTS) && AUTO_SHUTDOWN_MILLIVOLTS > 0
  static smartui::RecoveryBatteryGuard guard;
  const uint32_t now = millis();
  if (guard.sampleDue(now) && guard.update(now, board.getBattMilliVolts(),
      board.isExternalPowered(), AUTO_SHUTDOWN_MILLIVOLTS)) {
    // No preferences or usable filesystem are assumed here. Never attempt a
    // lazy write/format while the battery is already below the safe threshold.
    board.powerOff();
  }
#endif
#ifdef HAS_EXTERNAL_WATCHDOG
  external_watchdog.loop();
#endif
}

#if defined(ESP32) && defined(DISPLAY_CLASS) && (UI_V3_STORAGE_RECOVERY || UI_SAFE_STORAGE_RECOVERY)
  #include "ui-new/V3StorageRecovery.h"
#endif

void halt() {
  if (radio_initialized) radio_driver.powerOff();
  const uint32_t started = millis();
  bool display_off = false;
  for (;;) {
    serviceFatalBatterySafety();
#ifdef DISPLAY_CLASS
    if (!display_off && static_cast<uint32_t>(millis() - started) >= 30000) {
      display.turnOff();
      display_off = true;
    }
#endif
    delay(20); // yield to RTOS/watchdog instead of spinning at full CPU load
  }
}

#ifdef DISPLAY_CLASS
static void showFatalStorageError(DisplayDriver* disp, const char* title,
                                  const char* action) {
  if (!disp) return;
  disp->startFrame();
  disp->setTextSize(1);
  disp->setColor(UIColor::warning_txt);
  const int first_line = max(0, disp->height() / 2 - 10);
  disp->drawTextCentered(disp->width() / 2, first_line, title);
  disp->drawTextCentered(disp->width() / 2, first_line + 14, action);
  disp->endFrame();
}
#endif

/* WIFI RECONNECT TRACKERS */
#if defined(ESP32) && defined(WIFI_SSID) && \
    !(defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR)
  bool wifi_needs_reconnect = false;
  unsigned long last_wifi_reconnect_attempt = 0;
#endif

void setup() {
  // Keep an exact-source marker in the linked image for release validation.
  // The volatile reads prevent link-time removal of this non-display metadata.
  const volatile char* build_identity = "SmartUI-source:" SMARTUI_BUILD_SHA;
  for (size_t i = 0; i < sizeof("SmartUI-source:" SMARTUI_BUILD_SHA); ++i)
    (void)build_identity[i];
  Serial.begin(115200);
  board.begin();

#ifdef HAS_EXTERNAL_WATCHDOG
  external_watchdog.begin();
#endif

#ifdef DISPLAY_CLASS
  DisplayDriver* disp = NULL;
#if !SMARTUI_HEADLESS
  if (display.begin()) {
    disp = &display;
    disp->startFrame();
  #ifdef ST7789
    disp->setTextSize(2);
  #endif
    disp->drawTextCentered(disp->width() / 2, 28, "Loading...");
    disp->endFrame();
  }
#endif
#endif

  if (!radio_init()) { halt(); }
  radio_initialized = true;

  fast_rng.begin(radio_driver.getRngSeed());

  bool storage_ready = true;
  bool mesh_started = false;
#if defined(NRF52_PLATFORM) || defined(STM32_PLATFORM)
  storage_ready = InternalFS.begin();
  if (storage_ready) {
  #if defined(QSPIFLASH)
    storage_ready = QSPIFlash.begin();
    if (!storage_ready) {
      // debug output might not be available at this point, might be too early. maybe should fall back to InternalFS here?
      MESH_DEBUG_PRINTLN("CustomLFS_QSPIFlash: failed to initialize");
    } else {
      MESH_DEBUG_PRINTLN("CustomLFS_QSPIFlash: initialized successfully");
    }
  #else
  #if defined(EXTRAFS)
      // Call the non-formatting base mount directly. CustomLFS::begin() erases
      // and formats this region after any mount failure, which can turn a
      // transient error into loss of contacts/channels.
      storage_ready = ExtraFS.Adafruit_LittleFS::begin();
      if (!storage_ready) {
        MESH_DEBUG_PRINTLN("CustomLFS: mount failed; refusing to auto-format persistent data");
      }
  #endif
  #endif
  if (storage_ready) {
    store.begin();
    mesh_started = the_mesh.begin(
    #ifdef DISPLAY_CLASS
        disp != NULL
    #else
        false
    #endif
    );
  }
  }
#elif defined(RP2040_PLATFORM)
  storage_ready = LittleFS.begin();
  if (storage_ready) {
    store.begin();
    mesh_started = the_mesh.begin(
    #ifdef DISPLAY_CLASS
        disp != NULL
    #else
        false
    #endif
    );
  }
#elif defined(ESP32)
  // Never turn a transient mount failure into an implicit factory reset.
  // Release boards may initialize only a hash-verified factory-empty image;
  // other data requires explicit recovery confirmation, never a mount-failure wipe.
#if (UI_V3_STORAGE_RECOVERY || UI_SAFE_STORAGE_RECOVERY) && defined(DISPLAY_CLASS)
  storage_ready = smartui::v3MountStorage(disp);
#else
  storage_ready = SPIFFS.begin(false);
#endif
  if (!storage_ready) {
    MESH_DEBUG_PRINTLN("SPIFFS mount failed; refusing to auto-format persistent data");
  } else {
    store.begin();
    mesh_started = the_mesh.begin(
      #ifdef DISPLAY_CLASS
          disp != NULL
      #else
          false
      #endif
    );
  }
#else
  #error "need to define filesystem"
#endif

  if (!storage_ready) {
    MESH_DEBUG_PRINTLN("STORAGE ERROR: persistent filesystem is unavailable; refusing to continue");
#ifdef DISPLAY_CLASS
    showFatalStorageError(disp, "STORAGE ERROR", "RESTART / REFLASH");
#endif
    halt();
  }

  if (!mesh_started) {
    // A failed radio profile is not identity corruption. Never offer a
    // destructive identity reset as the remedy for an SPI/configuration error.
    if (the_mesh.isRadioStartupError()) {
      MESH_DEBUG_PRINTLN("RADIO ERROR: cannot apply a supported radio profile");
#ifdef DISPLAY_CLASS
      showFatalStorageError(disp, "RADIO ERROR", "CHECK MODULE");
#endif
      halt();
    }
    MESH_DEBUG_PRINTLN("IDENTITY ERROR: restore a valid identity backup or perform an explicit factory reset");
#ifdef DISPLAY_CLASS
    showFatalStorageError(disp, "IDENTITY ERROR", "RESTORE / RESET");
#endif
#if defined(ESP32) && defined(DISPLAY_CLASS) && (UI_V3_STORAGE_RECOVERY || UI_SAFE_STORAGE_RECOVERY)
    smartui::v3StorageRecoveryMenu(disp, true);
#endif
    halt();
  }

// add bluetooth interface
#if defined(BLE_PIN_CODE)
  bluetooth_interface.begin(BLE_NAME_PREFIX, the_mesh.getNodePrefs()->node_name, the_mesh.getBLEPin());
  interface_manager.addInterface(InterfaceType::Bluetooth, &bluetooth_interface);
#endif

// add wifi interface
#if defined(ESP32) && defined(SMARTUI_CONNECTION_SELECTOR) && \
    SMARTUI_CONNECTION_SELECTOR
  // Credentials and association are owned by ConnectionController.  Starting
  // the transport here only records its TCP port; exclusive selection decides
  // when the listener becomes available.
  wifi_interface.begin(TCP_PORT);
  interface_manager.addInterface(InterfaceType::WiFi, &wifi_interface);
#elif defined(WIFI_SSID)
  board.setInhibitSleep(true);   // prevent sleep when WiFi is active
  WiFi.setAutoReconnect(true);

  WiFi.onEvent([](WiFiEvent_t event, WiFiEventInfo_t info){
      if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED) {
          WIFI_DEBUG_PRINTLN("WiFi disconnected. Flagging for reconnect...");
          wifi_needs_reconnect = true;
      } else if (event == ARDUINO_EVENT_WIFI_STA_GOT_IP) {
          WIFI_DEBUG_PRINTLN("WiFi connected successfully!");
          wifi_needs_reconnect = false;
      }
  });

  WiFi.begin(WIFI_SSID, WIFI_PWD);
  wifi_interface.begin(TCP_PORT);
  interface_manager.addInterface(InterfaceType::WiFi, &wifi_interface);
#endif

// add usb interface
#if defined(ENABLE_USB_INTERFACE)
  #if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR && \
      (defined(NRF52_PLATFORM) || \
       (defined(ESP32) && defined(ARDUINO_USB_CDC_ON_BOOT) && \
        ARDUINO_USB_CDC_ON_BOOT))
  usb_serial_interface.begin(Serial, isUsbCompanionLinkPresent);
  #else
  usb_serial_interface.begin(Serial);
  #endif
  interface_manager.addInterface(InterfaceType::USB, &usb_serial_interface);
#endif

// add ethernet interface
#if defined(ETHERNET_ENABLED)
  ethernet_interface.begin();
  interface_manager.addInterface(InterfaceType::Ethernet, &ethernet_interface);
#endif

// add hardware serial interface
#if defined(SERIAL_RX)
  companion_serial.setPins(SERIAL_RX, SERIAL_TX);
  companion_serial.begin(115200);
  hardware_serial_interface.begin(companion_serial);
  interface_manager.addInterface(InterfaceType::HardwareSerial, &hardware_serial_interface);
#endif

  the_mesh.startInterface(interface_manager);
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  ConnectionControllerHooks connection_hooks;
  connection_hooks.resetLocalSession = resetCompanionSession;
  connection_hooks.setWifiSleepInhibit = setWifiSleepInhibit;
  connection_hooks.isCliRescue = isCompanionCliRescue;
  connection_hooks.isStorageQuarantined = isCompanionStorageQuarantined;
  connection_hooks.getBoardName = companionBoardName;
  connection_hooks.getQuickReply = companionQuickReply;
  connection_hooks.setQuickReply = setCompanionQuickReply;
  connection_hooks.handleDeviceSettings = handleCompanionDeviceSettings;
  connection_controller.begin(
      store, interface_manager, Serial,
    #if defined(ESP32)
      &wifi_interface,
    #else
      nullptr,
    #endif
      connection_hooks);
#endif

#if ENV_INCLUDE_GPS == 1
  // Apply PowerSaving profile for GPS
  if (sensors.getLocationProvider() != NULL) {
    // GPS on and off duration in seconds
    sensors.getLocationProvider()->setPowerSavingProfile(the_mesh.getNodePrefs()->powersaving_enabled, 600,
                                                         1800); // Max 10 minutes, 30 minutes
  }
#endif

  sensors.begin();

#if ENV_INCLUDE_GPS == 1
  the_mesh.applyGpsPrefs();
#endif

#ifdef DISPLAY_CLASS
  ui_task.begin(disp, &sensors, the_mesh.getNodePrefs());  // still want to pass this in as dependency, as prefs might be moved
  #if defined(HELTEC_WIRELESS_PAPER)
    paper_display_attached = (disp != nullptr);
  #endif
#endif

#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  smartui::DeviceSettingsHooks settings_hooks;
  settings_hooks.read = readDeviceSettings;
  settings_hooks.write = writeDeviceSettings;
  settings_hooks.save = saveDeviceSettings;
  settings_hooks.apply = applyDeviceSettings;
  settings_hooks.caps = deviceSettingsCapabilities;
  settings_hooks.batteryMilliVolts = deviceBatteryMilliVolts;
  settings_hooks.batteryCalibrationSample = deviceBatteryCalibrationSample;
  settings_hooks.adcMultiplier = deviceAdcMultiplier;
  settings_hooks.millis = deviceSettingsMillis;
  settings_hooks.testNotification = testDeviceNotification;
  device_settings.begin(settings_hooks);
  settings_hooks.melodyName = apiMelodyName;
  settings_hooks.setToneBridge = apiSetToneBridge;
  api_device_settings.begin(settings_hooks);
  uint64_t sync_boot = 0;
  fast_rng.random((uint8_t*)&sync_boot, sizeof(sync_boot));
  // Nonzero boot nonce prevents stale IDs crossing ordinary resets. No flash
  // counter is written; nonce uniqueness is probabilistic, not authentication.
  if (!sync_boot) sync_boot = 1;
  smartui_sync.begin(sync_boot);
  smartui::SyncApiHooks sync_hooks;
  sync_hooks.peek = syncPeekFrame;
  sync_hooks.receive = syncReceiveFrame;
  sync_hooks.action = syncMessageAction;
  sync_hooks.policy = syncReadPolicy;
  sync_hooks.canSnooze = syncCanSnooze;
  smartui_sync_api.begin(smartui_sync, sync_hooks);
#ifdef DISPLAY_CLASS
  ui_task.setSyncActionCallback(localSyncAction);
#endif
  smartui_api.begin(executeSmartUiApi);
#endif

  board.onBootComplete();

#if defined(ESP32_PLATFORM)
  #if defined(BLE_PIN_CODE) && !CONFIG_IDF_TARGET_ESP32C6
    // Enable BLE sleep
    esp_bt_sleep_enable();
  #endif

#if CONFIG_IDF_TARGET_ESP32C3
  esp_pm_config_esp32c3_t pm_config;
#elif CONFIG_IDF_TARGET_ESP32S3
  esp_pm_config_esp32s3_t pm_config;
#elif CONFIG_IDF_TARGET_ESP32
  esp_pm_config_esp32_t pm_config;
#elif CONFIG_IDF_TARGET_ESP32C6
  esp_pm_config_t pm_config;
#endif

  // Configure Power Management
#if (defined(ARDUINO_USB_CDC_ON_BOOT) && ARDUINO_USB_CDC_ON_BOOT) || \
    (defined(ENABLE_USB_INTERFACE) && \
     !(defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR))
  // Disable automatic light sleep for USB CDC Serial and USB Companion
  pm_config = { .max_freq_mhz = 80, .min_freq_mhz = 40, .light_sleep_enable = false };
#else
  pm_config = { .max_freq_mhz = 80, .min_freq_mhz = 40, .light_sleep_enable = true };
#endif

#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  if (pm_config.light_sleep_enable) {
    const esp_err_t lock_result = esp_pm_lock_create(
        ESP_PM_NO_LIGHT_SLEEP, 0, "smartui_io", &companion_sleep_lock);
    if (lock_result != ESP_OK ||
        esp_pm_lock_acquire(companion_sleep_lock) != ESP_OK) {
      // Prefer stable USB over sleeping without a working transport guard.
      pm_config.light_sleep_enable = false;
    } else {
      companion_sleep_lock_held = true;
    }
  }
#endif
  esp_err_t errPM = esp_pm_configure(&pm_config);
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  // Selected USB carries framed companion traffic only.  Never inject text
  // diagnostics into that byte stream.
  if (connection_controller.status().usbConsoleEnabled) {
#endif
  if (errPM == ESP_OK) {
    Serial.println("Power Management configured successfully");
  } else {
    Serial.printf("Power Management failed to configure: %d\r\n", errPM);
  }
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  }
#endif
#endif
}

void loop() {
#if defined(HELTEC_WIRELESS_PAPER) && defined(DISPLAY_CLASS) && !SMARTUI_HEADLESS
  // A bounded boot-time display failure must not make the node permanently
  // headless. E213 owns the exponential backoff and bounds each retry.
  // Retry only twice after the initial attempt. A physically absent display
  // must not consume SPI time and power forever on a functioning headless node.
  static uint8_t paper_attach_attempts = 0;
  if (!paper_display_attached && paper_attach_attempts < 2 && display.retryAfterMillis() == 0) {
    ++paper_attach_attempts;
    if (display.begin()) paper_display_attached = ui_task.attachDisplay(&display);
  }
#endif
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  connection_controller.loop();
#endif
  the_mesh.loop();
  interface_manager.loop();
  sensors.loop();
#ifdef DISPLAY_CLASS
  ui_task.loop();
#endif
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  serviceSmartUiSync();
#endif
  rtc_clock.tick();
#ifdef HAS_EXTERNAL_WATCHDOG
  external_watchdog.loop();
#endif

#if defined(ESP32_PLATFORM) && defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  if (companion_sleep_lock) {
    bool ui_active = false;
#ifdef DISPLAY_CLASS
    ui_active = ui_task.shouldHoldLightSleepLock();
#endif
    const bool hold = smartui::holdCompanionLightSleep(
        connection_controller.status().selected == CompanionMode::USB,
        companion_wifi_awake, connection_controller.consoleActive(millis()),
        ui_active, the_mesh.isCLIRescue());
    if (hold && !companion_sleep_lock_held) {
      companion_sleep_lock_held = esp_pm_lock_acquire(companion_sleep_lock) == ESP_OK;
    } else if (!hold && companion_sleep_lock_held) {
      if (esp_pm_lock_release(companion_sleep_lock) == ESP_OK)
        companion_sleep_lock_held = false;
    }
  }
#endif

  if (!the_mesh.hasPendingWork()) {
#if defined(NRF52_PLATFORM)
    board.sleep(0); // nrf ignores seconds param, sleeps whenever possible
#elif defined(ESP32_PLATFORM)
  #if defined(BLE_PIN_CODE)
    if (!bluetooth_interface.isReadBusy() && !bluetooth_interface.isWriteBusy()) { // BLE is not busy
      vTaskDelay(pdMS_TO_TICKS(10)); // attempt to sleep
    }
  #elif defined(ENABLE_USB_INTERFACE)
    vTaskDelay(pdMS_TO_TICKS(10)); // attempt to sleep
  #endif
#endif
  }

#if defined(ESP32) && defined(WIFI_SSID) && \
    !(defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR)
  // Safely attempt to reconnect every 10 seconds if flagged
  if (wifi_needs_reconnect && (millis() - last_wifi_reconnect_attempt > 10000)) {
    WIFI_DEBUG_PRINTLN("Attempting manual WiFi reconnect...");
    WiFi.disconnect();
    WiFi.reconnect();
    last_wifi_reconnect_attempt = millis();
  }
#endif
}
