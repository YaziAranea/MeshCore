"""Compile and exercise the production SmartUI binary API router on the host."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def extract_scope(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def main_adapter_source():
    """Compile the actual dispatcher body with recording host dependencies."""
    source = (ROOT / "examples/companion_radio/main.cpp").read_text(encoding="utf-8")

    def function(signature):
        return extract_scope(source, signature)

    declarations = r'''
#include "SmartUiApi.h"
#include "SmartUiSyncApi.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#define SMARTUI_VERSION "0.11-test"
static constexpr unsigned COMPANION_CAP_WIFI = 4;
static unsigned checks, backend_calls, backend_resets, connection_calls, connection_resets;
static bool backend_permission;
#define CHECK(x) do { ++checks; assert(x); } while (0)
enum class CompanionMode { BLE, USB, WiFi };
struct CompanionStatus {
  CompanionMode selected = CompanionMode::BLE, connectedVia = CompanionMode::BLE;
  bool clientConnected = true, wifiConfigured = false, wifiAssociated = false;
  unsigned capabilities = 7;
  char wifiLocalIp[32] = {};
};
struct Controller {
  CompanionStatus current;
  bool busy = false, writable = true;
  CompanionStatus status() const { return current; }
  bool deviceApiBusy() const { return busy; }
  bool deviceApiWritesAllowed() const { return writable; }
  bool handleApiCommand(const char* command, char* reply, size_t capacity, bool allowed) {
    ++connection_calls;
    if (strncmp(command, "api wifi ", 9) != 0 && strncmp(command, "api mode ", 9) != 0) return false;
    snprintf(reply, capacity, "%s", allowed || strcmp(command, "api wifi status") == 0 ?
             "OK api connection_action" : "ERR api readonly");
    return true;
  }
  void resetApiSession() { ++connection_resets; }
} connection_controller;
struct Mesh { bool pending = false; bool hasPendingWork() const { return pending; } } the_mesh;
struct Radio {
  bool receiving = false, recv = true;
  bool isReceiving() const { return receiving; }
  bool isInRecvMode() const { return recv; }
} radio_driver;
struct Backend {
  bool handle(const char*, char* reply, size_t capacity, bool allowed) {
    ++backend_calls; backend_permission = allowed;
    snprintf(reply, capacity, "OK api test"); return true;
  }
  void resetSession() { ++backend_resets; }
} api_device_settings;
static smartui::SmartUiApi smartui_api;
static smartui::SmartUiSync smartui_sync;
static smartui::SmartUiSyncApi smartui_sync_api;
static uint32_t sync_hint_cursor = 0;
static unsigned sync_actions = 0;
static bool explicit_policy = false;
static uint32_t notification_generation = 0;
static uint32_t syncNotificationGeneration() { return notification_generation; }
struct SettingsSnapshot { bool muted = false; } settings_snapshot;
static SettingsSnapshot readDeviceSettings() { return settings_snapshot; }
static void syncPolicy(bool enabled) { explicit_policy = enabled; }
static bool syncAction(uint32_t, smartui::SyncAction, uint32_t) { ++sync_actions; return true; }
'''
    bodies = "\n".join(function(signature) for signature in (
        "static const char* apiTransportName(",
        "static bool executeSmartUiApi(",
        "size_t handleSmartUiApiFrame(",
        "void resetSmartUiApiSession(",
    ))
    assertions = r'''
static void fresh() {
  backend_calls = backend_resets = connection_calls = connection_resets = 0; backend_permission = false;
  connection_controller = Controller{}; the_mesh = Mesh{}; radio_driver = Radio{};
  CHECK(smartui_sync.begin(1));
  smartui::SyncApiHooks hooks; hooks.policy = syncPolicy; hooks.action = syncAction;
  smartui_sync_api.begin(smartui_sync, hooks);
  sync_hint_cursor = 0; sync_actions = 0; notification_generation = 0; settings_snapshot = SettingsSnapshot{};
  smartui_api.begin(executeSmartUiApi);
}
static std::string command(const char* input, bool allowed = true) {
  char output[480]; memset(output, '!', sizeof(output));
  CHECK(executeSmartUiApi(input, output, sizeof(output), allowed));
  CHECK(memchr(output, 0, sizeof(output)) != nullptr);
  return output;
}
static uint8_t frame(const char* input, uint16_t id = 1) {
  std::vector<uint8_t> request = {201, 'S', 'U', 'I', 1, uint8_t(id), uint8_t(id >> 8), 1};
  request.insert(request.end(), input, input + strlen(input));
  uint8_t response[177]; memset(response, 0xa5, sizeof(response));
  const auto size = handleSmartUiApiFrame(request.data(), request.size(), response, sizeof(response));
  CHECK(size >= 13 && size <= smartui::SmartUiApi::MAX_FRAME && response[176] == 0xa5);
  return response[8];
}
int main() {
  fresh();
  for (const char* text : {"settings set volume 2", "settings adc reset", "wifi forget", "reboot", "apix get", ""}) {
    CHECK(command(text) == "ERR api unsupported");
    CHECK(backend_calls == 0);
  }
  CHECK(command("api hello", false).find("write=0") != std::string::npos);
  CHECK(command("api hello").find("stage=release") != std::string::npos);
  CHECK(command("api hello").find("firmware=0.11-test") != std::string::npos);
  CHECK(command("api hello").find("events=1 sync=1") != std::string::npos);
  CHECK(command("api hello").find("max_reply=479") != std::string::npos);
  CHECK(command("api hello").find("wifi_setup=1") != std::string::npos);
  CHECK(command("api connection", false).find("readonly=1") != std::string::npos);
  CHECK(backend_calls == 0);
  for (const char* text : {"api caps", "api get", "api melody 0"}) {
    CHECK(command(text, false) == "OK api test");
    CHECK(!backend_permission);
  }
  for (const char* text : {"api set volume 2", "api adc preview 4120", "api adc apply 1", "api adc reset", "api test"}) {
    const auto before = backend_calls;
    CHECK(command(text, false) == "ERR api readonly");
    CHECK(backend_calls == before);
  }
  fresh(); connection_controller.busy = true;
  CHECK(command("api set volume 2", false) == "ERR api busy" && backend_calls == 0);
  CHECK(command("api caps", false) == "OK api test");
  CHECK(command("api wifi status", false) == "OK api connection_action");
  CHECK(command("api wifi save") == "OK api connection_action");
  CHECK(backend_calls == 1 && connection_calls == 4);
  for (const char* text : {"api set fem_lna 1", "api set fem_pa 0"}) {
    fresh(); the_mesh.pending = true;
    CHECK(command(text) == "ERR api busy" && backend_calls == 0);
    fresh(); radio_driver.receiving = true;
    CHECK(command(text) == "ERR api busy" && backend_calls == 0);
    fresh(); radio_driver.recv = false;
    CHECK(command(text) == "ERR api busy" && backend_calls == 0);
    fresh();
    CHECK(command(text) == "OK api test" && backend_calls == 1 && backend_permission);
  }
  fresh(); connection_controller.current.selected = CompanionMode::WiFi;
  CHECK(command("api hello").find("wifi_setup=0") != std::string::npos);
  CHECK(frame("api set volume 2") == smartui::SmartUiApi::OK && backend_calls == 1 && backend_permission);
  CHECK(frame("api caps", 2) == smartui::SmartUiApi::OK && backend_calls == 2 && backend_permission);
  CHECK(frame("api adc preview 4120", 3) == smartui::SmartUiApi::OK && backend_calls == 3);
  fresh(); connection_controller.writable = false;
  CHECK(frame("api set volume 2") == smartui::SmartUiApi::DENIED && backend_calls == 0);
  CHECK(frame("api get", 2) == smartui::SmartUiApi::OK && !backend_permission);
  fresh(); connection_controller.current.selected = CompanionMode::USB;
  CHECK(frame("api set volume 2") == smartui::SmartUiApi::OK && backend_permission);
  fresh();
  CHECK(frame("api set volume 2") == smartui::SmartUiApi::OK && backend_permission);
  resetSmartUiApiSession();
  CHECK(backend_resets == 1 && connection_resets == 1);
  uint8_t fetch[] = {201, 'S', 'U', 'I', 1, 1, 0, 2, 0, 0};
  uint8_t response[177];
  CHECK(handleSmartUiApiFrame(fetch, sizeof(fetch), response, sizeof(response)) == 13);
  CHECK(response[8] == smartui::SmartUiApi::STALE && backend_calls == 1);
  CHECK(frame("api get") == smartui::SmartUiApi::OK && backend_calls == 2);
  fresh(); connection_controller.busy = true;
  CHECK(command("api sync status", false).find("explicit=0") != std::string::npos);
  CHECK(command("api sync enable", false) == "ERR api readonly" && !explicit_policy);
  CHECK(command("api sync enable").find("explicit=1") != std::string::npos && explicit_policy);
  CHECK(command("api events subscribe 15", false).find("subscribed=15") != std::string::npos);
  CHECK(smartui_sync.noteMessage(77, 1) == smartui::SyncResult::Applied);
  CHECK(command("api inbox read 0000000000000001 0000004d", false) == "ERR api readonly");
  CHECK(command("api inbox read 0000000000000001 0000004d") == "OK api inbox read id=0000004d state=2 changed=1");
  CHECK(sync_actions == 1 && backend_calls == 0);
  notification_generation = 77; settings_snapshot.muted = true;
  CHECK(command("api notify status", false) == "OK api notify active=1 id=0000004d muted=1");
  CHECK(backend_calls == 0);
  resetSmartUiApiSession();
  CHECK(!explicit_policy && !smartui_sync_api.enabled() && smartui_sync_api.subscriptions() == 0);
  CHECK(smartui_sync.recordCount() == 1 && sync_hint_cursor == smartui_sync.newestEvent());
  CHECK(command("api inbox read 0000000000000001 0000004d") == "ERR api negotiate");
  printf("PASS %u production main.cpp SmartUI authorization/session adapter assertions\n", checks);
}
'''
    return declarations + bodies + assertions


def setting_effects_source():
    """Exercise production read/write/save/apply hooks with the real backend."""
    source = (ROOT / "examples/companion_radio/main.cpp").read_text(encoding="utf-8")
    declarations = r'''
#include "DeviceSettings.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#define DISPLAY_CLASS HostDisplay
#define ENV_INCLUDE_GPS 1
static unsigned checks, saves, applies, adc_calls, gps_calls, led_calls, lna_calls, pa_calls;
static unsigned notification_stops, battery_changes, radio_calls, global_applies, preview_calls;
static unsigned presentation_calls;
static bool save_ok;
#define CHECK(x) do { ++checks; assert(x); } while (0)
struct NodePrefs {
  float adc_multiplier = 0;
  double node_lat = 10, node_lon = 20;
  uint8_t notify_mode = 7, important_notify_mode = 7, buzzer_quiet = 0, vibe_quiet = 0;
  uint8_t notify_tone_volume = 10, notify_tone_id = 0, notify_tone_dm_id = 0;
  uint8_t notify_tone_mention_id = 0, notify_tone_system_id = 0;
  uint8_t board_leds_enabled = 1, unread_led_enabled = 1, gps_enabled = 0, gps_source = 0;
  uint8_t low_battery_shutdown_enabled = 1, notifications_muted = 0, night_quiet_active = 0;
  uint8_t smart_profile_id = 0, agc_reset_enabled = 0, radio_fem_rxgain = 0, radio_fem_txgain = 0;
  uint8_t notify_tone_bridge_enabled = 0;
  int8_t notify_gpio_pin = 35, notify_tone_pin = 36, notify_vibe_pin = -1;
  uint8_t notify_tone_8bit_enabled = 0, notify_tone_high_drive_enabled = 0;
  uint16_t notify_tone_resonance_hz = 3000;
  uint8_t offline_dm_led_enabled = 1, ble_dm_led_enabled = 1, msg_popup_enabled = 1;
  uint8_t ui_font = 10, ui_theme = 0, ui_top_color = 1, ui_bottom_color = 0;
  uint8_t backlight_timeout_idx = 0, advert_loc_policy = 0;
  uint32_t gps_interval = 0;
};
struct Mesh {
  NodePrefs prefs, persisted;
  NodePrefs* getNodePrefs() { return &prefs; }
  bool savePrefs() {
    ++saves; prefs.node_lat = 100; prefs.node_lon = 200;
    if (save_ok) persisted = prefs;
    return save_ok;
  }
  void applyGpsPrefs() { CHECK(save_ok && saves > 0); ++gps_calls; }
  void applyUiPrefsRuntime() { ++global_applies; ++radio_calls; }
} the_mesh;
struct Board {
  float adc = 4.0f; bool lna = false, pa = false;
  void setAdcMultiplier(float value) { CHECK(save_ok && saves > 0); ++adc_calls; adc = value ? value : 4.0f; }
  void setLoRaFemLnaEnabled(bool value) { CHECK(save_ok && saves > 0); ++lna_calls; lna = value; }
  void setLoRaFemPaGainEnabled(bool value) { CHECK(save_ok && saves > 0); ++pa_calls; pa = value; }
} board;
struct Radio { void setRxBoostedGainMode(bool) { ++radio_calls; } } radio_driver;
struct Ui {
  uint8_t getUiFontChoiceIndex() { return the_mesh.prefs.ui_font - 10; }
  uint8_t storedUiFontChoice(uint8_t choice) { return choice + 10; }
  void applyDeviceSettingsAppearanceAndPins() { CHECK(save_ok && saves > 0); ++presentation_calls; }
  void applyDeviceSettingsRuntime(bool battery_changed) {
    CHECK(save_ok && saves > 0); ++notification_stops; battery_changes += battery_changed;
  }
} ui_task;
static void meshcoreSetBoardLedsEnabled(bool) { CHECK(save_ok && saves > 0); ++led_calls; }
'''
    effects = source[source.index("enum DeviceSettingEffect"):
                     source.index("static smartui::DeviceSettingsState readDeviceSettings(")]
    bodies = "\n".join(extract_scope(source, signature) for signature in (
        "static smartui::DeviceSettingsState readDeviceSettings(",
        "static void writeDeviceSettings(",
        "static bool saveDeviceSettings(",
        "static void applyDeviceSettings(",
    ))
    assertions = r'''
static smartui::DeviceSettings service, other_service;
static smartui::DeviceSettingsCaps capabilities() {
  smartui::DeviceSettingsCaps caps;
  caps.adc = caps.sound = caps.board_led = caps.unread_led = caps.vibration = true;
  caps.gps = caps.battery_protection = caps.agc_reset = caps.fem_lna = caps.fem_pa = true;
  caps.melody_max = 30; caps.adc_default = 4.0f;
  caps.effective_notify_mode = the_mesh.prefs.important_notify_mode;
  caps.display = caps.notify_pins = caps.profiles = caps.colors = true;
  caps.tone_8bit = caps.high_drive = caps.resonance = caps.phone_gps = true;
  caps.notify_mask = 7; caps.font_count = 5; caps.theme_count = 3;
  return caps;
}
static uint16_t battery() { return 4000; }
static float multiplier() { return board.adc; }
static uint32_t clockMillis() { return 100; }
static void trackedApply(bool battery_changed) { ++applies; applyDeviceSettings(battery_changed); }
static void previewNotification() { ++preview_calls; }
static bool pinAllowed(const char*, int pin) { return pin == -1 || pin == 35 || pin == 36 || pin == 37; }
static void fresh() {
  saves = applies = adc_calls = gps_calls = led_calls = lna_calls = pa_calls = 0;
  notification_stops = battery_changes = radio_calls = global_applies = preview_calls = 0;
  presentation_calls = 0;
  save_ok = true; the_mesh = Mesh{}; board = Board{}; device_setting_effects = 0;
  smartui::DeviceSettingsHooks hooks;
  hooks.read = readDeviceSettings; hooks.write = writeDeviceSettings; hooks.save = saveDeviceSettings;
  hooks.apply = trackedApply; hooks.caps = capabilities; hooks.batteryMilliVolts = battery;
  hooks.adcMultiplier = multiplier; hooks.millis = clockMillis; hooks.testNotification = previewNotification;
  hooks.pinAllowed = pinAllowed;
  service = smartui::DeviceSettings{}; other_service = smartui::DeviceSettings{};
  service.begin(hooks); other_service.begin(hooks);
}
static std::string command(const char* text, bool second = false) {
  char reply[480];
  CHECK((second ? other_service : service).handle(text, reply, sizeof(reply), true));
  return reply;
}
static void effects(unsigned adc, unsigned gps, unsigned led, unsigned lna, unsigned pa,
                    unsigned notifications, unsigned battery_changed) {
  CHECK(adc_calls == adc && gps_calls == gps && led_calls == led && lna_calls == lna && pa_calls == pa);
  CHECK(notification_stops == notifications && battery_changes == battery_changed);
  CHECK(radio_calls == 0 && global_applies == 0);
}
int main() {
  fresh();
  CHECK(command("api set agc_reset 1") == "OK api set key=agc_reset value=1");
  CHECK(the_mesh.prefs.agc_reset_enabled == 1 && saves == 1 && applies == 1);
  effects(0, 0, 0, 0, 0, 0, 0);
  CHECK(device_setting_effects == 0);
  fresh();
  CHECK(command("api set melody 12") == "OK api set key=melody value=12");
  CHECK(the_mesh.prefs.notify_tone_id == 12 && the_mesh.prefs.notify_tone_dm_id == 12 &&
        the_mesh.prefs.notify_tone_mention_id == 12 && the_mesh.prefs.notify_tone_system_id == 12);
  effects(0, 0, 0, 0, 0, 1, 0);
  fresh();
  CHECK(command("api set gps 1") == "OK api set key=gps value=1");
  effects(0, 1, 0, 0, 0, 0, 0);
  fresh();
  CHECK(command("api set board_led 0") == "OK api set key=board_led value=0");
  effects(0, 0, 1, 0, 0, 1, 0);
  fresh();
  CHECK(command("api set fem_lna 1") == "OK api set key=fem_lna value=1");
  effects(0, 0, 0, 1, 0, 0, 0);
  fresh();
  CHECK(command("api set fem_pa 1") == "OK api set key=fem_pa value=1");
  effects(0, 0, 0, 0, 1, 0, 0);
  fresh();
  CHECK(command("api set battery_protection 0") == "OK api set key=battery_protection value=0");
  effects(0, 0, 0, 0, 0, 1, 1);
  fresh();
  unsigned long token = 0;
  CHECK(sscanf(command("api adc preview 4120").c_str(), "OK api adc_preview token=%lu", &token) == 1);
  effects(0, 0, 0, 0, 0, 0, 0);
  CHECK(saves == 0 && applies == 0);
  CHECK(command((std::string("api adc apply ") + std::to_string(token)).c_str()) == "OK api adc_apply");
  CHECK(fabs(board.adc - 4.12f) < 0.00001f);
  effects(1, 0, 0, 0, 0, 1, 1);
  CHECK(command("api adc reset") == "OK api adc_reset");
  effects(2, 0, 0, 0, 0, 2, 2);
  for (const char* change : {"api set volume 2", "api set unread_led 0", "api set vibration 0",
                            "api set sound_quiet 1", "api set muted 1"}) {
    fresh(); CHECK(command(change).find("OK api set ") == 0);
    effects(0, 0, 0, 0, 0, 1, 0);
  }
  // Successful no-op setters do not restart notifications or touch hardware.
  for (const char* change : {"api set volume 10", "api set board_led 1", "api set gps 0",
                            "api set fem_lna 0", "api set fem_pa 0", "api set agc_reset 0"}) {
    fresh(); CHECK(command(change).find("OK api set ") == 0);
    effects(0, 0, 0, 0, 0, 0, 0);
  }
  // Failure restores preferences and incidental savePrefs coordinates without
  // applying rollback effects. Reads/previews leave hardware unchanged; the
  // next successful write recomputes flags, including across the two services.
  for (const char* change : {"api set volume 2", "api set board_led 0", "api set gps 1",
                            "api set fem_lna 1", "api set fem_pa 1", "api set agc_reset 1"}) {
    fresh(); const auto before = readDeviceSettings(); save_ok = false;
    CHECK(command(change) == "ERR api storage");
    const auto after = readDeviceSettings();
    CHECK(memcmp(&before, &after, sizeof(before)) == 0);
    CHECK(the_mesh.prefs.node_lat == 10 && the_mesh.prefs.node_lon == 20 && applies == 0);
    effects(0, 0, 0, 0, 0, 0, 0);
    CHECK(command("api get").find("OK api get ") == 0);
    CHECK(command("api test") == "OK api test" && preview_calls == 1 && applies == 0);
    effects(0, 0, 0, 0, 0, 0, 0);
    save_ok = true;
    CHECK(command("api set agc_reset 1", true) == "OK api set key=agc_reset value=1");
    CHECK(applies == 1 && device_setting_effects == 0);
    effects(0, 0, 0, 0, 0, 0, 0);
  }
  fresh();
  CHECK(sscanf(command("api adc preview 4120").c_str(), "OK api adc_preview token=%lu", &token) == 1);
  save_ok = false;
  CHECK(command((std::string("api adc apply ") + std::to_string(token)).c_str()) == "ERR api storage");
  CHECK(the_mesh.prefs.adc_multiplier == 0 && board.adc == 4.0f && applies == 0);
  effects(0, 0, 0, 0, 0, 0, 0);
  save_ok = true;
  CHECK(command("api set volume 10", true) == "OK api set key=volume value=10");
  effects(0, 0, 0, 0, 0, 0, 0);
  CHECK(device_setting_effects == 0);
  for (const char* change : {"settings set ui_font 2", "settings set ui_theme 2", "settings set led_pin 37",
       "settings set tone_pin 37", "settings set vibe_pin 37", "settings set backlight_timeout 2",
       "settings set ui_top_color 2", "settings set msg_popup 0"}) {
    fresh(); const auto before = readDeviceSettings(); save_ok = false;
    CHECK(command(change) == "ERR settings storage");
    const auto after = readDeviceSettings();
    CHECK(memcmp(&before, &after, sizeof(before)) == 0);
    CHECK(presentation_calls == 0 && applies == 0);
    save_ok = true;
    CHECK(command(change).find("OK settings set ") == 0);
    CHECK(presentation_calls == 1 && applies == 1);
    effects(0, 0, 0, 0, 0, 0, 0);
  }
  fresh(); CHECK(command("settings set gps_interval 30").find("OK settings ") == 0);
  CHECK(the_mesh.prefs.gps_interval == 30 && gps_calls == 1 && presentation_calls == 0 && radio_calls == 0);
  fresh(); CHECK(command("settings set ui_font 4").find("OK settings ") == 0);
  CHECK(the_mesh.prefs.ui_font == 14 && readDeviceSettings().ui_font == 4);
  fresh(); CHECK(command("settings adc set 4.1") == "OK settings adc_set");
  CHECK(presentation_calls == 0 && the_mesh.prefs.ui_font == 10 && the_mesh.prefs.notify_vibe_pin == -1);
  printf("PASS %u production DeviceSettings/main.cpp selective-effect/rollback assertions\n", checks);
}
'''
    return declarations + effects + bodies + assertions


def tone_bridge_source():
    """Use the production shared bridge operation with recording pins/store."""
    source = (ROOT / "examples/companion_radio/ui-new/UITask.cpp").read_text(encoding="utf-8")
    declarations = r'''
#include "DeviceSettings.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#define UI_TONE_BRIDGE_PAGE 1
#define PIN_MSG_TONE 1
#define PIN_MSG_ALERT 6
#define DEFAULT_NOTIFY_TONE_PIN 1
#define DEFAULT_NOTIFY_TONE_BRIDGE_PIN 2
#define OUTPUT 1
#define LOW 0
static unsigned checks, saves, stops, beeps, alerts, pin_changes, global_radio_applies;
static bool save_ok;
#define CHECK(x) do { ++checks; assert(x); } while (0)
struct NodePrefs {
  double node_lat = 10, node_lon = 20;
  uint8_t notify_tone_bridge_enabled = 0;
  int8_t notify_gpio_pin = 1, notify_tone_pin = 5, notify_vibe_pin = 2;
  uint8_t unrelated = 77;
};
static NodePrefs prefs, persisted;
struct Mesh {
  bool quarantined = false, rescue = false;
  bool isStorageRecoveryRequired() const { return quarantined; }
  bool isCLIRescue() const { return rescue; }
  bool savePrefs() {
    ++saves; prefs.node_lat = 100; prefs.node_lon = 200;
    if (save_ok) persisted = prefs;
    return save_ok;
  }
  const char* getPrefsSaveErrorText() const { return "storage"; }
  void applyUiPrefsRuntime() { ++global_radio_applies; }
} the_mesh;
[[maybe_unused]] static void pinMode(int pin, int mode) { CHECK(pin == 2 && mode == OUTPUT); ++pin_changes; }
[[maybe_unused]] static void digitalWrite(int pin, int level) { CHECK(pin == 2 && level == LOW); ++pin_changes; }
[[maybe_unused]] static void uiStopToneBridge(int first, int second) { CHECK(first == 1 && second == 2); ++pin_changes; }
class UITask {
public:
  NodePrefs* _node_prefs = &prefs;
  int _msg_alert_pin = 1, _msg_tone_pin = 5, _msg_vibe_pin = 2;
  int _next_refresh = 99;
  bool isNotifyToneBridgeEnabled() const;
  bool supportsNotifyToneBridge() const;
  bool setNotifyToneBridgeEnabled(bool enabled);
  void toggleNotifyToneBridge();
  void stopNotifyOutputs() { ++stops; }
  int getDefaultNotifyGpioPin() const { return 1; }
  int getNextNotifyGpioPinExcept(int, int first, int second) const { CHECK(first == 1 && second == 2); return 6; }
  void configureMsgTonePin(int pin) { ++pin_changes; _msg_tone_pin = pin; prefs.notify_tone_pin = pin; }
  void configureMsgAlertPin(int pin) { ++pin_changes; _msg_alert_pin = pin; prefs.notify_gpio_pin = pin; }
  void configureMsgVibePin(int pin) { ++pin_changes; _msg_vibe_pin = pin; prefs.notify_vibe_pin = pin; }
  void showAlert(const char*, unsigned) { ++alerts; }
  void startMsgTone() { ++beeps; }
} ui;
'''
    bodies = "\n".join(extract_scope(source, signature) for signature in (
        "bool UITask::isNotifyToneBridgeEnabled(",
        "bool UITask::supportsNotifyToneBridge(",
        "bool UITask::setNotifyToneBridgeEnabled(",
        "void UITask::toggleNotifyToneBridge(",
    ))
    assertions = r'''
static smartui::DeviceSettings service;
static smartui::DeviceSettingsState readState() { smartui::DeviceSettingsState s; s.bridge = prefs.notify_tone_bridge_enabled; return s; }
static void writeState(const smartui::DeviceSettingsState&) { CHECK(false); }
static bool saveState() { CHECK(false); return false; }
static void applyState(bool) { CHECK(false); }
static smartui::DeviceSettingsCaps capabilities() { smartui::DeviceSettingsCaps c; c.bridge = ui.supportsNotifyToneBridge(); return c; }
static uint16_t battery() { return 4000; }
static float multiplier() { return 4; }
static uint32_t clockMillis() { return 100; }
static bool bridge(bool enabled) { return ui.setNotifyToneBridgeEnabled(enabled); }
static void fresh() {
  saves = stops = beeps = alerts = pin_changes = global_radio_applies = 0;
  save_ok = true; prefs = NodePrefs{}; persisted = prefs; the_mesh = Mesh{}; ui = UITask{};
  smartui::DeviceSettingsHooks hooks;
  hooks.read = readState; hooks.write = writeState; hooks.save = saveState; hooks.apply = applyState;
  hooks.caps = capabilities; hooks.batteryMilliVolts = battery; hooks.adcMultiplier = multiplier;
  hooks.millis = clockMillis; hooks.setToneBridge = bridge;
  service = smartui::DeviceSettings{}; service.begin(hooks);
}
static std::string command(const char* input) {
  char reply[480]; CHECK(service.handle(input, reply, sizeof(reply), true)); return reply;
}
static void untouched() {
  CHECK(saves == 0 && stops == 0 && beeps == 0 && pin_changes == 0 && global_radio_applies == 0);
  CHECK(prefs.notify_tone_bridge_enabled == 0 && prefs.notify_gpio_pin == 1 && prefs.notify_tone_pin == 5 && prefs.notify_vibe_pin == 2);
}
int main() {
  fresh();
#if UI_TONE_BRIDGE_PAGE == 1
  CHECK(ui.supportsNotifyToneBridge());
  fresh(); CHECK(ui.setNotifyToneBridgeEnabled(false)); untouched();
  CHECK(command("api set bridge 1") == "OK api set key=bridge value=1");
  CHECK(prefs.notify_tone_bridge_enabled == 1 && prefs.notify_tone_pin == 1);
  CHECK(prefs.notify_gpio_pin == 6 && prefs.notify_vibe_pin == -1 && prefs.unrelated == 77);
  CHECK(ui._msg_tone_pin == 1 && ui._msg_alert_pin == 6 && ui._msg_vibe_pin == -1);
  CHECK(persisted.notify_tone_bridge_enabled == 1 && persisted.notify_gpio_pin == 6 && persisted.notify_vibe_pin == -1);
  CHECK(saves == 1 && stops == 1 && beeps == 0 && alerts == 0 && global_radio_applies == 0);
  const auto changes = pin_changes;
  CHECK(command("api set bridge 1") == "OK api set key=bridge value=1");
  CHECK(ui.setNotifyToneBridgeEnabled(true));
  CHECK(saves == 1 && stops == 1 && pin_changes == changes);
  CHECK(command("api get").find("bridge=1") != std::string::npos);
  CHECK(command("api set bridge 0") == "OK api set key=bridge value=0");
  CHECK(prefs.notify_tone_bridge_enabled == 0 && prefs.notify_tone_pin == 1 && prefs.notify_gpio_pin == 6 && prefs.notify_vibe_pin == -1);
  CHECK(saves == 2 && stops == 2 && beeps == 0 && alerts == 0 && global_radio_applies == 0);
  fresh(); save_ok = false;
  CHECK(command("api set bridge 1") == "ERR api storage");
  CHECK(prefs.notify_tone_bridge_enabled == 0 && prefs.notify_tone_pin == 5 && prefs.notify_gpio_pin == 1 && prefs.notify_vibe_pin == 2);
  CHECK(ui._msg_tone_pin == 5 && ui._msg_alert_pin == 1 && ui._msg_vibe_pin == 2);
  CHECK(prefs.node_lat == 10 && prefs.node_lon == 20 && prefs.unrelated == 77);
  CHECK(saves == 1 && stops == 1 && beeps == 0 && alerts == 0 && global_radio_applies == 0);
  save_ok = true;
  CHECK(command("api set bridge 1") == "OK api set key=bridge value=1");
  save_ok = false;
  CHECK(command("api set bridge 0") == "ERR api storage");
  CHECK(prefs.notify_tone_bridge_enabled == 1 && ui._msg_tone_pin == 1 && ui._msg_alert_pin == 6 && ui._msg_vibe_pin == -1);
  CHECK(beeps == 0 && alerts == 0 && global_radio_applies == 0);
  fresh(); the_mesh.quarantined = true;
  CHECK(!ui.setNotifyToneBridgeEnabled(true)); untouched();
  fresh(); the_mesh.rescue = true;
  CHECK(!ui.setNotifyToneBridgeEnabled(true)); untouched();
  fresh(); ui._node_prefs = nullptr;
  CHECK(!ui.setNotifyToneBridgeEnabled(true)); untouched();
  fresh(); prefs.notify_gpio_pin = ui._msg_alert_pin = 7; prefs.notify_vibe_pin = ui._msg_vibe_pin = 8;
  CHECK(ui.setNotifyToneBridgeEnabled(true));
  CHECK(prefs.notify_gpio_pin == 7 && prefs.notify_vibe_pin == 8);
  fresh(); ui.toggleNotifyToneBridge();
  CHECK(prefs.notify_tone_bridge_enabled == 1 && saves == 1 && alerts == 1 && beeps == 1);
  save_ok = false; ui.toggleNotifyToneBridge();
  CHECK(prefs.notify_tone_bridge_enabled == 1 && saves == 2 && alerts == 2 && beeps == 1);
  CHECK(global_radio_applies == 0);
#else
  CHECK(!ui.supportsNotifyToneBridge());
  CHECK(!ui.setNotifyToneBridgeEnabled(true)); untouched();
  CHECK(command("api caps").find("bridge=0") != std::string::npos);
  CHECK(command("api set bridge 1") == "ERR api unsupported"); untouched();
  ui.toggleNotifyToneBridge();
  CHECK(alerts == 1 && beeps == 0 && saves == 0);
#endif
  printf("PASS %u production tone-bridge/API pin-transaction assertions\n", checks);
}
'''
    return declarations + bodies + assertions


def main():
    with tempfile.TemporaryDirectory(prefix="smartui-api-") as directory:
        adapter = Path(directory) / "smartui_api_adapter_test.cpp"
        adapter.write_text(main_adapter_source(), encoding="utf-8")
        effects = Path(directory) / "smartui_setting_effects_test.cpp"
        effects.write_text(setting_effects_source(), encoding="utf-8")
        bridge = Path(directory) / "smartui_tone_bridge_test.cpp"
        bridge_source = tone_bridge_source()
        bridge.write_text(bridge_source, encoding="utf-8")
        no_bridge = Path(directory) / "smartui_no_tone_bridge_test.cpp"
        no_bridge.write_text(bridge_source.replace("#define UI_TONE_BRIDGE_PAGE 1",
                                                   "#define UI_TONE_BRIDGE_PAGE 0"), encoding="utf-8")
        includes = [ROOT / "examples/companion_radio", ROOT / "src"]
        compiler = shutil.which("g++") or shutil.which("clang++")
        flags = ["-std=c++17", "-Wall", "-Wextra", "-Werror", "-O1"]
        if os.environ.get("SMARTUI_TEST_SANITIZE") == "1":
            flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
        for suite in (ROOT / "tools/smartui_api_test.cpp", adapter, effects, bridge, no_bridge):
            output = Path(directory) / suite.stem
            paths = [suite, ROOT / "examples/companion_radio/SmartUiApi.cpp"]
            if suite == adapter:
                paths += [ROOT / "examples/companion_radio/SmartUiSync.cpp",
                          ROOT / "examples/companion_radio/SmartUiSyncApi.cpp"]
            if suite in (effects, bridge, no_bridge):
                paths = [suite, ROOT / "examples/companion_radio/DeviceSettings.cpp"]
            if compiler:
                build = [compiler, *flags, *["-I" + str(path) for path in includes],
                         *map(str, paths), "-o", str(output)]
                execute = [str(output)]
            elif os.name == "nt":
                def linux(path):
                    return subprocess.check_output(
                        ["wsl", "--exec", "wslpath", "-a", str(path)], text=True).strip()
                build = ["wsl", "--exec", "g++", *flags,
                         *["-I" + linux(path) for path in includes],
                         *map(linux, paths), "-o", linux(output)]
                execute = ["wsl", "--exec", linux(output)]
            else:
                raise RuntimeError("Host C++ compiler required; no skipped test success")
            subprocess.run(build, check=True)
            subprocess.run(execute, check=True)


if __name__ == "__main__":
    main()
