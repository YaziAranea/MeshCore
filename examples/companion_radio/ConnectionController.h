#pragma once

#include "ConnectionTypes.h"

#include <stddef.h>
#include <stdint.h>

class BaseSerialInterface;
class DataStore;
class MultiSerialInterface;
class SerialWifiInterface;
class Stream;

struct ConnectionControllerHooks {
  void (*resetLocalSession)() = nullptr;
  void (*setWifiSleepInhibit)(bool inhibit) = nullptr;
  bool (*isCliRescue)() = nullptr;
  bool (*isStorageQuarantined)() = nullptr;
  const char* (*getBoardName)() = nullptr;
  const char* (*getQuickReply)(uint8_t slot) = nullptr;
  bool (*setQuickReply)(uint8_t slot, const char* text) = nullptr;
  // The service returns one bounded ASCII line without CR/LF. It must enforce
  // allow_mutation for every persistent change and notification test.
  bool (*handleDeviceSettings)(const char* command, char* reply,
                               size_t capacity, bool allow_mutation) = nullptr;
};

class ConnectionController {
public:
  ConnectionController();

  void begin(DataStore& store, MultiSerialInterface& interfaces,
             Stream& usb_console, SerialWifiInterface* wifi_interface,
             const ConnectionControllerHooks& hooks);
  void loop();

  CompanionStatus status() const;
  bool setMode(CompanionMode mode);
  // Result of the latest setMode request, unaffected by background config saves.
  ConnectionChangeError lastChangeError() const { return _last_change_error; }
  bool resolveWifiClient(uint32_t request_id, bool approve);
  bool consoleActive(uint32_t now) const;
  // Public API shares quarantine/rescue guards with the USB console. Busy is
  // separate from permission so an API-owned Wi-Fi transaction can progress.
  bool deviceApiBusy() const { return _wifi_setup_stage != WifiSetupStage::IDLE || _api_mode_pending; }
  bool deviceApiWritesAllowed() const { return _started && mutationAllowed(); }
  bool handleApiCommand(const char* command, char* reply, size_t capacity,
                        bool allow_mutation);
  // Local CMD66 adapter. Same staged workflow/guards, replies <=156 bytes.
  bool handleCliCommand(const char* command, char* reply, size_t capacity,
                       bool allow_mutation);
  // Call only for a real companion session boundary, not USB console activity.
  void resetApiSession();
  // Confirm only a successfully queued reply to the pending api mode request.
  void apiReplyQueued();

private:
  static const size_t WIFI_SSID_MAX = 32;
  static const size_t WIFI_PASSWORD_MAX = 64;
  static const size_t CONSOLE_LINE_MAX = 160;
  static const size_t CONSOLE_TX_MAX = 512;

  enum class WifiSetupStage : uint8_t {
    IDLE = 0,
    WAIT_SSID,
    WAIT_PASSWORD,
    TESTING,
    TEST_OK,
    FAILED,
    READY,
  };

  enum class WifiApiResult : uint8_t { NONE, SAVED, CANCELLED, FAILED, TIMED_OUT };

  // Last failed persistence step in this boot. Diagnostic reads never change
  // this latch, retry recovery, or expose credential-bearing file contents.
  enum class StoragePhase : uint8_t {
    NONE, UNAVAILABLE, RECOVERY_BLOCKED, CLEAN_INVALID,
    MARKER_OPEN, MARKER_VERIFY, CLEAN_REMOVE, CLEAN_OPEN, CLEAN_WRITE,
    CLEAN_VERIFY, CLEAN_TEMP, CLEAN_BACKUP, CLEAN_FINAL_VERIFY, MARKER_REMOVE,
    RECOVER_REMOVE, RECOVER_OPEN, RECOVER_WRITE, RECOVER_VERIFY, RECOVER_TEMP,
    SAVE_TEMP_REMOVE, SAVE_OPEN, SAVE_WRITE, SAVE_VERIFY, SAVE_ROTATE,
    SAVE_PUBLISH, SAVE_FINAL_VERIFY,
  };

  struct Config {
    CompanionMode mode = CompanionMode::BLE;
    bool wifi_configured = false;
    uint8_t ssid_len = 0;
    uint8_t password_len = 0;
    char ssid[WIFI_SSID_MAX + 1] = {};
    char password[WIFI_PASSWORD_MAX + 1] = {};
  };

  DataStore* _store = nullptr;
  MultiSerialInterface* _interfaces = nullptr;
  Stream* _console = nullptr;
  SerialWifiInterface* _wifi_interface = nullptr;
  ConnectionControllerHooks _hooks = {};
  Config _config = {};
  ConnectionChangeError _last_change_error = ConnectionChangeError::None;
  bool _started = false;
  bool _config_reset_notice = false;
  bool _config_storage_error = false;
  StoragePhase _storage_phase = StoragePhase::NONE;
  bool _console_announced = false;
  bool _console_input_seen = false;
  uint32_t _console_last_input = 0;
  bool _quarantine_latched = false;
  bool _wifi_radio_on = false;
  bool _wifi_was_associated = false;
  bool _wifi_attempt_active = false;
  uint32_t _wifi_attempt_started = 0;
  uint32_t _wifi_retry_at = 0;
  uint32_t _wifi_retry_delay = 0;
  uint32_t _wifi_setup_activity = 0;
  WifiSetupStage _wifi_setup_stage = WifiSetupStage::IDLE;
  bool _api_wifi_setup = false;
  WifiApiResult _api_wifi_result = WifiApiResult::NONE;
  bool _api_mode_pending = false;
  bool _api_mode_reply_queued = false;
  CompanionMode _api_mode_target = CompanionMode::BLE;
  uint32_t _api_mode_started = 0;
  uint32_t _api_mode_session = 0;
  const char* _api_mode_error = "none";
  char _candidate_ssid[WIFI_SSID_MAX + 1] = {};
  char _candidate_password[WIFI_PASSWORD_MAX + 1] = {};
  uint8_t _candidate_ssid_len = 0;
  uint8_t _candidate_password_len = 0;
  char _console_line[CONSOLE_LINE_MAX + 1] = {};
  uint8_t _console_line_len = 0;
  bool _console_line_overflow = false;
  bool _console_swallow_lf = false;
  char _console_tx[CONSOLE_TX_MAX] = {};
  // Keep the full settings snapshot off the small nRF52 main-task stack.
  char _settings_response[480] = {};
  uint16_t _console_tx_head = 0;
  uint16_t _console_tx_len = 0;

  bool mutationAllowed() const;
  ConnectionChangeError mutationError() const;
  bool consoleEnabled() const;
  uint8_t capabilities() const;
  bool modeAvailable(CompanionMode mode) const;
  bool applyMode(CompanionMode mode, bool reset_session);
  bool readConfigFile(const char* path, Config& config) const;
  bool writeConfigFile(const char* path, const Config& config,
                       StoragePhase open_failure, StoragePhase write_failure);
  bool storageFailed(StoragePhase phase);
  static const char* storagePhaseName(StoragePhase phase);
  bool configsEqual(const Config& first, const Config& second) const;
  bool loadConfig();
  bool saveConfig(const Config& config, ConnectionChangeError* error = nullptr);
  bool persistCleanConfig(const Config& clean);
  bool forgetWifi();
  bool removeOrNeutralizeConfigFile(const char* path, const Config& clean);
  void scrubCandidate();
  void stopWifiRadio(bool erase_sdk_credentials = false);
  void startWifiAttempt(const char* ssid, const char* password, bool test_only);
  void serviceWifi();
  void serviceConsole();
  void serviceConsoleTx();
  void clearConsoleTx();
  void handleConsoleLine(char* line);
  void printConsole(const char* text);
  void printStatus();
  void printInfo();
  void printStorageStatus();
  void printStorageUsage();
  void printStorageLegacy();
  void printHelp();
  void handleQuickReplyCommand(const char* line);
  void handleDeviceSettingsCommand(const char* line);
  void cancelWifiSetup(bool restore_selected_wifi);
  bool startWifiSetup();
  bool saveTestedWifi();
  void serviceApiMode();
  const char* wifiStageName() const;
};

#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
extern ConnectionController connection_controller;
#endif
