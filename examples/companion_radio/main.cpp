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
  #include "AdcCalibrationService.h"
  #include "SmartUiCliSettings.h"
  #include "RadioSettings.h"
  #include "SmartUiSync.h"
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
// Separate preview-token domains for the service console and Companion CLI.
static smartui::DeviceSettings cli_device_settings;
static smartui::RadioSettings radio_settings;
static smartui::AdcCalibrationService adc_calibration_service;
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
  c.adc_service = c.adc && board.supportsConfirmedUsbPower();
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

static bool adcServiceUsbLinkPresent() {
#if defined(NRF52_PLATFORM) && defined(ENABLE_USB_INTERFACE)
  return Serial.dtr();
#else
  return false;  // No reliable VBUS/session contract on these targets yet.
#endif
}

static bool adcServiceOwnerConnected(smartui::AdcCalibrationService::Owner owner) {
  if (!adcServiceUsbLinkPresent()) return false;
  if (owner == smartui::AdcCalibrationService::Owner::USB_CONSOLE)
    return connection_controller.status().usbConsoleEnabled;
  return owner == smartui::AdcCalibrationService::Owner::USB_COMPANION &&
      interface_manager.getSelectedInterface() == InterfaceType::USB &&
      interface_manager.isInterfaceConnected(InterfaceType::USB);
}

static uint32_t adcServiceSession(smartui::AdcCalibrationService::Owner owner) {
  return owner == smartui::AdcCalibrationService::Owner::USB_COMPANION ?
      interface_manager.getSessionGeneration() : 0;
}

static void serviceAdcCalibrationWindow() {
  const auto owner = adc_calibration_service.owner();
  if (owner == smartui::AdcCalibrationService::Owner::NONE) {
#ifdef DISPLAY_CLASS
    ui_task.setAdcCalibrationServiceActive(false);
#endif
    return;
  }
  const bool active = adc_calibration_service.update(millis(),
      board.isUsbPowerConfirmed(), adcServiceOwnerConnected(owner),
      adcServiceSession(owner), connection_controller.deviceApiWritesAllowed());
#ifdef DISPLAY_CLASS
  ui_task.setAdcCalibrationServiceActive(active);
#endif
}

void stopSmartUiAdcCalibrationService() {
  adc_calibration_service.stop();
  serviceAdcCalibrationWindow();
}

static void handleAdcService(smartui::AdcCalibrationService::Owner requester,
                             const char* action, char* reply, size_t capacity,
                             bool writable) {
  serviceAdcCalibrationWindow();
  const bool supported = deviceSettingsCapabilities().adc_service;
  const bool external = board.isUsbPowerConfirmed();
  if (strcmp(action, "stop") == 0) stopSmartUiAdcCalibrationService();
  else if (strcmp(action, "start") == 0) {
    const auto result = adc_calibration_service.start(millis(), supported, writable,
        external, adcServiceOwnerConnected(requester), requester, adcServiceSession(requester));
    if (result != smartui::AdcCalibrationService::Result::OK) {
      using Result = smartui::AdcCalibrationService::Result;
      const char* error = result == Result::READONLY ? "readonly" :
          result == Result::UNSUPPORTED ? "unsupported" :
          result == Result::USB_REQUIRED ? "usb_required" : "busy";
      snprintf(reply, capacity, "ERR settings %s", error);
      return;
    }
  }
  serviceAdcCalibrationWindow();
  const uint32_t remaining = adc_calibration_service.remaining(millis());
  snprintf(reply, capacity,
      "OK settings adc_service supported=%u active=%u remaining_ms=%lu external=%u",
      supported ? 1U : 0U, remaining ? 1U : 0U,
      static_cast<unsigned long>(remaining), external ? 1U : 0U);
}

static void consoleAdcService(const char* action, char* reply, size_t capacity, bool writable) {
  handleAdcService(smartui::AdcCalibrationService::Owner::USB_CONSOLE,
                  action, reply, capacity, writable);
}

static void companionAdcService(const char* action, char* reply, size_t capacity, bool writable) {
  // A BLE/TCP client remains remote even when someone plugs a USB power cable in.
  const auto owner = interface_manager.getSelectedInterface() == InterfaceType::USB ?
      smartui::AdcCalibrationService::Owner::USB_COMPANION :
      smartui::AdcCalibrationService::Owner::NONE;
  handleAdcService(owner, action, reply, capacity, writable);
}
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
  if (radio_settings.handle(command, reply, capacity, allow_mutation)) return true;
  return device_settings.handle(command, reply, capacity, allow_mutation);
}

static smartui::RadioSettingsState readRadioSettings() {
  const NodePrefs& p = *the_mesh.getNodePrefs();
  smartui::RadioSettingsState s;
  s.frequency_mhz = p.freq;
  s.bandwidth_khz = p.bw;
  s.sf = p.sf;
  s.cr = p.cr;
  s.path_bytes = p.path_hash_mode + 1;
  s.tx_dbm = p.tx_power_dbm;
  s.repeat = p.isRepeatEn();
  s.advert_minutes = p.auto_advert_interval_mins;
  return s;
}

static void writeRadioSettings(const smartui::RadioSettingsState& s) {
  NodePrefs& p = *the_mesh.getNodePrefs();
  p.freq = s.frequency_mhz;
  p.bw = s.bandwidth_khz;
  p.sf = s.sf;
  p.cr = s.cr;
  p.path_hash_mode = s.path_bytes - 1;
  p.auto_advert_interval_mins = s.advert_minutes;
  // No assignments to TX power, repeat, identity or UI preferences.
}

static bool validateRadioSettings(const smartui::RadioSettingsState& s) {
  return the_mesh.validateLocalRadioSettings(s.frequency_mhz, s.bandwidth_khz, s.sf, s.cr);
}
static bool applyRadioSettings(const smartui::RadioSettingsState& s) {
  return the_mesh.applyLocalRadioSettings(s.frequency_mhz, s.bandwidth_khz, s.sf, s.cr);
}
static bool repeatFrequencyAllowed(uint32_t khz) { return the_mesh.localRepeatFrequencyAllowed(khz); }
static void applyAdvertSettings() { the_mesh.applyLocalAdvertInterval(); }
static bool radioSettingsBusy() {
  return connection_controller.deviceApiBusy() || the_mesh.localRadioSettingsBusy();
}
static bool radioSettingsHealthy() { return the_mesh.localRadioSettingsHealthy(); }

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

// Standard CMD66 carries short SmartUI commands. The archived 0.11 C9
// protocol, inbox ownership and event pushes are not enabled in this release.
bool executeSmartUiCliCommand(const char* command, char* reply, size_t capacity) {
  const bool writable = connection_controller.deviceApiWritesAllowed();
  if (strcmp(command, "ui hello") == 0) {
    snprintf(reply, capacity,
        "OK ui hello version=1 firmware=%s max_command=156 max_reply=156 write=%u sync=0 events=0",
        SMARTUI_VERSION, writable ? 1U : 0U);
    return true;
  }
  if (connection_controller.handleCliCommand(command, reply, capacity, writable)) return true;
  if (radio_settings.handle(command, reply, capacity, writable)) return true;
  const bool read = strncmp(command, "ui caps ", 8) == 0 ||
                    strncmp(command, "ui get ", 7) == 0 ||
                    strncmp(command, "ui melody ", 10) == 0 ||
                    strcmp(command, "ui adc service") == 0 ||
                    strcmp(command, "ui adc service stop") == 0;
  if (!read && connection_controller.deviceApiBusy()) {
    snprintf(reply, capacity, "ERR ui busy");
    return true;
  }
  if (!read && !writable) {
    snprintf(reply, capacity, "ERR ui readonly");
    return true;
  }
  // FEM changes must never interrupt TX, RX, queued radio work or maintenance.
  if (strncmp(command, "ui set fem_", 11) == 0 &&
      (the_mesh.hasPendingWork() || radio_driver.isReceiving() || !radio_driver.isInRecvMode())) {
    snprintf(reply, capacity, "ERR ui busy");
    return true;
  }
  return smartui::handleSmartUiSettingsCli(cli_device_settings, command, reply, capacity, writable);
}

void resetSmartUiCliSession() {
  if (adc_calibration_service.owner() == smartui::AdcCalibrationService::Owner::USB_COMPANION)
    stopSmartUiAdcCalibrationService();
  cli_device_settings.resetSession();
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
  settings_hooks.adcService = consoleAdcService;
  settings_hooks.adcCommitted = stopSmartUiAdcCalibrationService;
  device_settings.begin(settings_hooks);
  settings_hooks.melodyName = apiMelodyName;
  settings_hooks.setToneBridge = apiSetToneBridge;
  settings_hooks.adcService = companionAdcService;
  cli_device_settings.begin(settings_hooks);
  smartui::RadioSettingsHooks radio_hooks;
  radio_hooks.read = readRadioSettings;
  radio_hooks.write = writeRadioSettings;
  radio_hooks.save = saveDeviceSettings;
  radio_hooks.validate = validateRadioSettings;
  radio_hooks.repeatAllowed = repeatFrequencyAllowed;
  radio_hooks.applyRadio = applyRadioSettings;
  radio_hooks.applyAdvert = applyAdvertSettings;
  radio_hooks.busy = radioSettingsBusy;
  radio_hooks.healthy = radioSettingsHealthy;
  radio_settings.begin(radio_hooks);
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
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  serviceAdcCalibrationWindow();
#endif
#ifdef DISPLAY_CLASS
  ui_task.loop();
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
