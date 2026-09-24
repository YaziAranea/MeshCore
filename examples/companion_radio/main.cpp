#include <Arduino.h>   // needed for PlatformIO
#include <Mesh.h>
#include "MyMesh.h"

#ifdef ESP32_PLATFORM
#include "esp_pm.h"
#include "esp_bt.h"
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
static void resetCompanionSession() {
  the_mesh.resetLocalAppSession();
}

static void setWifiSleepInhibit(bool inhibit) {
#if defined(ESP32)
  board.setInhibitSleep(inhibit);
#else
  (void)inhibit;
#endif
}

static bool isCompanionCliRescue() {
  return the_mesh.isCLIRescue();
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
  Serial.begin(115200);
  board.begin();

#ifdef HAS_EXTERNAL_WATCHDOG
  external_watchdog.begin();
#endif

#ifdef DISPLAY_CLASS
  DisplayDriver* disp = NULL;
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
  connection_controller.begin(
      store, interface_manager, Serial,
    #if defined(ESP32)
      &wifi_interface,
    #else
      nullptr,
    #endif
      connection_hooks);
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
#if defined(ARDUINO_USB_CDC_ON_BOOT) && ARDUINO_USB_CDC_ON_BOOT
  // Disable automatic light sleep for USB CDC Serial
  pm_config = { .max_freq_mhz = 80, .min_freq_mhz = 40, .light_sleep_enable = false };
#else
  pm_config = { .max_freq_mhz = 80, .min_freq_mhz = 40, .light_sleep_enable = true };
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
#if defined(HELTEC_WIRELESS_PAPER) && defined(DISPLAY_CLASS)
  // A bounded boot-time display failure must not make the node permanently
  // headless. E213 owns the exponential backoff and bounds each retry.
  if (!paper_display_attached && display.retryAfterMillis() == 0 && display.begin()) {
    paper_display_attached = ui_task.attachDisplay(&display);
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
  rtc_clock.tick();
#ifdef HAS_EXTERNAL_WATCHDOG
  external_watchdog.loop();
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
