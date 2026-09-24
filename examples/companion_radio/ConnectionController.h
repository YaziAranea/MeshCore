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

private:
  static const size_t WIFI_SSID_MAX = 32;
  static const size_t WIFI_PASSWORD_MAX = 64;
  static const size_t CONSOLE_LINE_MAX = 96;
  static const size_t CONSOLE_TX_MAX = 512;

  enum class WifiSetupStage : uint8_t {
    IDLE = 0,
    WAIT_SSID,
    WAIT_PASSWORD,
    TESTING,
    TEST_OK,
    FAILED,
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
  bool _console_announced = false;
  bool _quarantine_latched = false;
  bool _wifi_radio_on = false;
  bool _wifi_was_associated = false;
  bool _wifi_attempt_active = false;
  uint32_t _wifi_attempt_started = 0;
  uint32_t _wifi_retry_at = 0;
  uint32_t _wifi_retry_delay = 0;
  uint32_t _wifi_setup_activity = 0;
  WifiSetupStage _wifi_setup_stage = WifiSetupStage::IDLE;
  char _candidate_ssid[WIFI_SSID_MAX + 1] = {};
  char _candidate_password[WIFI_PASSWORD_MAX + 1] = {};
  uint8_t _candidate_ssid_len = 0;
  uint8_t _candidate_password_len = 0;
  char _console_line[CONSOLE_LINE_MAX + 1] = {};
  uint8_t _console_line_len = 0;
  bool _console_line_overflow = false;
  bool _console_swallow_lf = false;
  char _console_tx[CONSOLE_TX_MAX] = {};
  uint16_t _console_tx_head = 0;
  uint16_t _console_tx_len = 0;

  bool mutationAllowed() const;
  ConnectionChangeError mutationError() const;
  bool consoleEnabled() const;
  uint8_t capabilities() const;
  bool modeAvailable(CompanionMode mode) const;
  bool applyMode(CompanionMode mode, bool reset_session);
  bool readConfigFile(const char* path, Config& config) const;
  bool writeConfigFile(const char* path, const Config& config) const;
  bool configsEqual(const Config& first, const Config& second) const;
  bool loadConfig();
  bool saveConfig(const Config& config, ConnectionChangeError* error = nullptr);
  bool forgetWifi();
  void scrubConfigArtifacts();
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
  void printHelp();
  void cancelWifiSetup(bool restore_selected_wifi);
  bool startWifiSetup();
  bool saveTestedWifi();
};

#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
extern ConnectionController connection_controller;
#endif
