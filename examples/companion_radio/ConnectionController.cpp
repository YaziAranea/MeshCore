#include "ConnectionController.h"

#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR

#include <Arduino.h>
#include <helpers/MultiSerialInterface.h>
#include <helpers/StorageTransaction.h>

#include "DataStore.h"

#if defined(ESP32)
  #include <WiFi.h>
  #include <helpers/esp32/SerialWifiInterface.h>
#endif

#include <ctype.h>
#include <stdio.h>
#include <string.h>

namespace {

static const char* CONFIG_PATH = "/connection.cfg";
static const char* CONFIG_TEMP_PATH = "/connection.cfg.tmp";
static const char* CONFIG_BACKUP_PATH = "/connection.cfg.bak";
static const uint8_t CONFIG_MAGIC[] = {'M', 'C', 'C', '1'};
static const uint8_t CONFIG_VERSION = 1;
static const size_t CONFIG_HEADER_SIZE = 9;
static const size_t CONFIG_SSID_SIZE = 32;
static const size_t CONFIG_PASSWORD_SIZE = 64;
static const size_t CONFIG_BODY_SIZE =
    CONFIG_HEADER_SIZE + CONFIG_SSID_SIZE + CONFIG_PASSWORD_SIZE;
static const size_t CONFIG_RECORD_SIZE = CONFIG_BODY_SIZE + 4;
static const uint8_t CONFIG_FLAG_WIFI = 1u << 0;

static const uint32_t WIFI_CONNECT_TIMEOUT_MS = 15000UL;
static const uint32_t WIFI_RETRY_INITIAL_MS = 5000UL;
static const uint32_t WIFI_RETRY_MAX_MS = 60000UL;
static const uint32_t WIFI_SETUP_IDLE_TIMEOUT_MS = 120000UL;
static const uint8_t CONSOLE_BYTES_PER_LOOP = 48;
static const uint8_t CONSOLE_TX_BYTES_PER_LOOP = 64;

static void secureZero(void* data, size_t len) {
  volatile uint8_t* bytes = static_cast<volatile uint8_t*>(data);
  while (len-- > 0) *bytes++ = 0;
}

#if defined(ESP32)
static bool elapsed(uint32_t now, uint32_t started, uint32_t interval) {
  return static_cast<uint32_t>(now - started) >= interval;
}

static bool deadlineReached(uint32_t now, uint32_t deadline) {
  return static_cast<int32_t>(now - deadline) >= 0;
}
#endif

static const char* modeName(CompanionMode mode) {
  switch (mode) {
    case CompanionMode::BLE: return "BLE";
    case CompanionMode::USB: return "USB";
    case CompanionMode::WiFi: return "WiFi";
  }
  return "invalid";
}

static InterfaceType interfaceType(CompanionMode mode) {
  switch (mode) {
    case CompanionMode::BLE: return InterfaceType::Bluetooth;
    case CompanionMode::USB: return InterfaceType::USB;
    case CompanionMode::WiFi: return InterfaceType::WiFi;
  }
  return InterfaceType::NONE;
}

static File openConfigWrite(FILESYSTEM* fs, const char* path) {
#if defined(NRF52_PLATFORM) || defined(STM32_PLATFORM)
  return fs->open(path, FILE_O_WRITE);
#elif defined(RP2040_PLATFORM)
  return fs->open(path, "w");
#else
  return fs->open(path, "w", true);
#endif
}

static File openConfigRead(FILESYSTEM* fs, const char* path) {
#if defined(NRF52_PLATFORM) || defined(STM32_PLATFORM)
  return fs->open(path, FILE_O_READ);
#elif defined(RP2040_PLATFORM)
  return fs->open(path, "r");
#else
  return fs->open(path, "r", false);
#endif
}

static bool validSecretBytes(const uint8_t* value, size_t len) {
  for (size_t i = 0; i < len; ++i) {
    if (value[i] == 0 || value[i] < 0x20 || value[i] == 0x7f) return false;
  }
  return true;
}

static bool zeroPadding(const uint8_t* value, size_t used, size_t capacity) {
  for (size_t i = used; i < capacity; ++i) {
    if (value[i] != 0) return false;
  }
  return true;
}

static uint32_t readLe32(const uint8_t* value) {
  return static_cast<uint32_t>(value[0]) |
      (static_cast<uint32_t>(value[1]) << 8) |
      (static_cast<uint32_t>(value[2]) << 16) |
      (static_cast<uint32_t>(value[3]) << 24);
}

static void writeLe32(uint8_t* dest, uint32_t value) {
  dest[0] = static_cast<uint8_t>(value);
  dest[1] = static_cast<uint8_t>(value >> 8);
  dest[2] = static_cast<uint8_t>(value >> 16);
  dest[3] = static_cast<uint8_t>(value >> 24);
}

static void lowerAscii(char* value) {
  while (*value) {
    if (*value >= 'A' && *value <= 'Z') *value = static_cast<char>(*value - 'A' + 'a');
    ++value;
  }
}

static char* trimAscii(char* value) {
  while (*value == ' ' || *value == '\t') ++value;
  char* end = value + strlen(value);
  while (end > value && (end[-1] == ' ' || end[-1] == '\t')) --end;
  *end = 0;
  return value;
}

}  // namespace

ConnectionController connection_controller;

ConnectionController::ConnectionController() = default;

bool ConnectionController::mutationAllowed() const {
  if (_hooks.isCliRescue && _hooks.isCliRescue()) return false;
  if (_hooks.isStorageQuarantined && _hooks.isStorageQuarantined()) return false;
  return true;
}

bool ConnectionController::consoleEnabled() const {
  if (!_started || !_console || _config.mode == CompanionMode::USB) return false;
  return !(_hooks.isCliRescue && _hooks.isCliRescue());
}

uint8_t ConnectionController::capabilities() const {
  if (!_interfaces) return 0;
  uint8_t result = 0;
  if (_interfaces->hasInterface(InterfaceType::Bluetooth)) result |= COMPANION_CAP_BLE;
  if (_interfaces->hasInterface(InterfaceType::USB)) result |= COMPANION_CAP_USB;
#if defined(ESP32)
  if (_wifi_interface && _interfaces->hasInterface(InterfaceType::WiFi)) {
    result |= COMPANION_CAP_WIFI;
  }
#endif
  return result;
}

bool ConnectionController::modeAvailable(CompanionMode mode) const {
  const uint8_t caps = capabilities();
  if (mode == CompanionMode::BLE) return (caps & COMPANION_CAP_BLE) != 0;
  if (mode == CompanionMode::USB) return (caps & COMPANION_CAP_USB) != 0;
  if (mode == CompanionMode::WiFi) return (caps & COMPANION_CAP_WIFI) != 0;
  return false;
}

bool ConnectionController::configsEqual(const Config& first,
                                         const Config& second) const {
  return first.mode == second.mode &&
      first.wifi_configured == second.wifi_configured &&
      first.ssid_len == second.ssid_len &&
      first.password_len == second.password_len &&
      memcmp(first.ssid, second.ssid, sizeof(first.ssid)) == 0 &&
      memcmp(first.password, second.password, sizeof(first.password)) == 0;
}

bool ConnectionController::readConfigFile(const char* path, Config& config) const {
  if (!_store) return false;
  FILESYSTEM* fs = _store->getPrimaryFS();
  if (!fs || !fs->exists(path)) return false;
  File file = openConfigRead(fs, path);
  if (!file || static_cast<size_t>(file.size()) != CONFIG_RECORD_SIZE) {
    if (file) file.close();
    return false;
  }

  uint8_t raw[CONFIG_RECORD_SIZE];
  const bool complete = file.read(raw, sizeof(raw)) == static_cast<int>(sizeof(raw));
  file.close();
  if (!complete || memcmp(raw, CONFIG_MAGIC, sizeof(CONFIG_MAGIC)) != 0 ||
      raw[4] != CONFIG_VERSION || raw[5] > static_cast<uint8_t>(CompanionMode::WiFi) ||
      (raw[6] & ~CONFIG_FLAG_WIFI) != 0 || raw[7] > CONFIG_SSID_SIZE ||
      raw[8] > CONFIG_PASSWORD_SIZE) {
    secureZero(raw, sizeof(raw));
    return false;
  }

  mesh::storage::Crc32 crc;
  crc.update(raw, CONFIG_BODY_SIZE);
  const bool checksum_ok = readLe32(raw + CONFIG_BODY_SIZE) == crc.value();
  const bool wifi_configured = (raw[6] & CONFIG_FLAG_WIFI) != 0;
  const size_t ssid_len = raw[7];
  const size_t password_len = raw[8];
  const uint8_t* ssid = raw + CONFIG_HEADER_SIZE;
  const uint8_t* password = ssid + CONFIG_SSID_SIZE;
  const bool credentials_ok = wifi_configured
      ? (ssid_len > 0 && validSecretBytes(ssid, ssid_len) &&
         (password_len == 0 || password_len >= 8) &&
         validSecretBytes(password, password_len))
      : (ssid_len == 0 && password_len == 0);
  const bool canonical = zeroPadding(ssid, ssid_len, CONFIG_SSID_SIZE) &&
      zeroPadding(password, password_len, CONFIG_PASSWORD_SIZE);
  if (!checksum_ok || !credentials_ok || !canonical) {
    secureZero(raw, sizeof(raw));
    return false;
  }

  Config candidate;
  candidate.mode = static_cast<CompanionMode>(raw[5]);
  candidate.wifi_configured = wifi_configured;
  candidate.ssid_len = static_cast<uint8_t>(ssid_len);
  candidate.password_len = static_cast<uint8_t>(password_len);
  memcpy(candidate.ssid, ssid, ssid_len);
  memcpy(candidate.password, password, password_len);
  config = candidate;
  secureZero(&candidate, sizeof(candidate));
  secureZero(raw, sizeof(raw));
  return true;
}

bool ConnectionController::writeConfigFile(const char* path,
                                            const Config& config) const {
  if (!_store) return false;
  FILESYSTEM* fs = _store->getPrimaryFS();
  if (!fs) return false;

  uint8_t raw[CONFIG_RECORD_SIZE] = {};
  memcpy(raw, CONFIG_MAGIC, sizeof(CONFIG_MAGIC));
  raw[4] = CONFIG_VERSION;
  raw[5] = static_cast<uint8_t>(config.mode);
  raw[6] = config.wifi_configured ? CONFIG_FLAG_WIFI : 0;
  raw[7] = config.wifi_configured ? config.ssid_len : 0;
  raw[8] = config.wifi_configured ? config.password_len : 0;
  if (config.wifi_configured) {
    memcpy(raw + CONFIG_HEADER_SIZE, config.ssid, config.ssid_len);
    memcpy(raw + CONFIG_HEADER_SIZE + CONFIG_SSID_SIZE,
           config.password, config.password_len);
  }
  mesh::storage::Crc32 crc;
  crc.update(raw, CONFIG_BODY_SIZE);
  writeLe32(raw + CONFIG_BODY_SIZE, crc.value());

  File file = openConfigWrite(fs, path);
  if (!file) {
    secureZero(raw, sizeof(raw));
    return false;
  }
  const bool success = file.write(raw, sizeof(raw)) == sizeof(raw);
  file.flush();
  file.close();
  secureZero(raw, sizeof(raw));
  return success;
}

bool ConnectionController::saveConfig(const Config& config) {
  if (!mutationAllowed() || !_store) return false;
  FILESYSTEM* fs = _store->getPrimaryFS();
  if (!fs) return false;
  if (fs->exists(CONFIG_TEMP_PATH) && !fs->remove(CONFIG_TEMP_PATH)) return false;
  if (!writeConfigFile(CONFIG_TEMP_PATH, config)) return false;

  Config verified;
  const bool scratch_valid = readConfigFile(CONFIG_TEMP_PATH, verified) &&
      configsEqual(config, verified);
  secureZero(&verified, sizeof(verified));
  if (!scratch_valid) {
    fs->remove(CONFIG_TEMP_PATH);
    return false;
  }

  Config current;
  const bool current_valid = readConfigFile(CONFIG_PATH, current);
  secureZero(&current, sizeof(current));
  const bool had_primary = fs->exists(CONFIG_PATH);
  bool rotated = false;
  if (had_primary && current_valid) {
    if (fs->exists(CONFIG_BACKUP_PATH) && !fs->remove(CONFIG_BACKUP_PATH)) return false;
    if (!fs->rename(CONFIG_PATH, CONFIG_BACKUP_PATH)) return false;
    rotated = true;
  } else if (had_primary && !fs->remove(CONFIG_PATH)) {
    return false;
  }

  if (!fs->rename(CONFIG_TEMP_PATH, CONFIG_PATH)) {
    if (rotated && !fs->exists(CONFIG_PATH) && fs->exists(CONFIG_BACKUP_PATH)) {
      fs->rename(CONFIG_BACKUP_PATH, CONFIG_PATH);
    }
    return false;
  }

  Config published;
  const bool success = readConfigFile(CONFIG_PATH, published) &&
      configsEqual(config, published);
  secureZero(&published, sizeof(published));
  return success;
}

void ConnectionController::scrubConfigArtifacts() {
  if (!_store) return;
  FILESYSTEM* fs = _store->getPrimaryFS();
  if (!fs) return;
  const char* paths[] = {CONFIG_PATH, CONFIG_TEMP_PATH, CONFIG_BACKUP_PATH};
  for (const char* path : paths) {
    if (fs->exists(path)) fs->remove(path);
  }
}

bool ConnectionController::removeOrNeutralizeConfigFile(
    const char* path, const Config& clean) {
  if (!_store || !path) return false;
  FILESYSTEM* fs = _store->getPrimaryFS();
  if (!fs) return false;
  if (!fs->exists(path)) return true;
  if (fs->remove(path) && !fs->exists(path)) return true;

  // Some flash filesystems can reject unlink while still allowing an existing
  // fixed-size file to be overwritten.  A verified credential-free record is
  // safe recovery input even when that stale filename cannot be removed.
  if (!writeConfigFile(path, clean)) return false;
  Config verified;
  const bool safe = readConfigFile(path, verified) &&
      configsEqual(clean, verified);
  secureZero(&verified, sizeof(verified));
  return safe;
}

bool ConnectionController::loadConfig() {
  Config primary;
  Config temporary;
  Config backup;
  const bool primary_valid = readConfigFile(CONFIG_PATH, primary);
  const bool temporary_valid = readConfigFile(CONFIG_TEMP_PATH, temporary);
  const bool backup_valid = readConfigFile(CONFIG_BACKUP_PATH, backup);
  FILESYSTEM* fs = _store ? _store->getPrimaryFS() : nullptr;
  const bool any_file = fs && (fs->exists(CONFIG_PATH) || fs->exists(CONFIG_TEMP_PATH) ||
                               fs->exists(CONFIG_BACKUP_PATH));
  const mesh::storage::RecoveryCandidate choice = mesh::storage::chooseRecoveryCandidate(
      primary_valid, temporary_valid, backup_valid);

  Config selected;
  if (choice == mesh::storage::RecoveryCandidate::PRIMARY) selected = primary;
  else if (choice == mesh::storage::RecoveryCandidate::TEMPORARY) selected = temporary;
  else if (choice == mesh::storage::RecoveryCandidate::BACKUP) selected = backup;
  else {
    selected = Config();
    _config_reset_notice = any_file;
  }
  _config = selected;

  secureZero(&primary, sizeof(primary));
  secureZero(&temporary, sizeof(temporary));
  secureZero(&backup, sizeof(backup));
  secureZero(&selected, sizeof(selected));

  if (!mutationAllowed()) return choice != mesh::storage::RecoveryCandidate::NONE;
  if (choice == mesh::storage::RecoveryCandidate::NONE) {
    scrubConfigArtifacts();
    return saveConfig(_config);
  }
  if (!_config.wifi_configured) {
    // A completed Forget operation must never resurrect credentials from a
    // stale transaction generation after a later unrelated read failure.
    if (fs->exists(CONFIG_TEMP_PATH)) fs->remove(CONFIG_TEMP_PATH);
    if (fs->exists(CONFIG_BACKUP_PATH)) fs->remove(CONFIG_BACKUP_PATH);
  } else if (choice != mesh::storage::RecoveryCandidate::PRIMARY) {
    return saveConfig(_config);
  } else if (fs->exists(CONFIG_TEMP_PATH)) {
    fs->remove(CONFIG_TEMP_PATH);
  }
  return true;
}

void ConnectionController::scrubCandidate() {
  secureZero(_candidate_ssid, sizeof(_candidate_ssid));
  secureZero(_candidate_password, sizeof(_candidate_password));
  _candidate_ssid_len = 0;
  _candidate_password_len = 0;
}

void ConnectionController::stopWifiRadio(bool erase_sdk_credentials) {
#if defined(ESP32)
  if (_wifi_interface) _wifi_interface->disable();
  if (_wifi_radio_on || erase_sdk_credentials) {
    WiFi.setAutoReconnect(false);
    WiFi.disconnect(true, erase_sdk_credentials);
    WiFi.mode(WIFI_OFF);
  }
#else
  (void)erase_sdk_credentials;
#endif
  _wifi_radio_on = false;
  _wifi_was_associated = false;
  _wifi_attempt_active = false;
  _wifi_attempt_started = 0;
  _wifi_retry_at = 0;
  _wifi_retry_delay = WIFI_RETRY_INITIAL_MS;
  _wifi_setup_activity = 0;
  if (_hooks.setWifiSleepInhibit) _hooks.setWifiSleepInhibit(false);
}

void ConnectionController::startWifiAttempt(const char* ssid, const char* password,
                                             bool test_only) {
#if defined(ESP32)
  if (!_wifi_interface || !ssid || !ssid[0]) return;
  if (_hooks.setWifiSleepInhibit) _hooks.setWifiSleepInhibit(true);
  WiFi.persistent(false);
  WiFi.setAutoReconnect(false);
  WiFi.mode(WIFI_STA);
  WiFi.disconnect(false, false);
  WiFi.begin(ssid, password && password[0] ? password : nullptr);
  _wifi_radio_on = true;
  _wifi_was_associated = false;
  _wifi_attempt_active = true;
  _wifi_attempt_started = millis();
  _wifi_retry_at = 0;
  if (test_only) _wifi_setup_stage = WifiSetupStage::TESTING;
#else
  (void)ssid;
  (void)password;
  (void)test_only;
#endif
}

bool ConnectionController::applyMode(CompanionMode mode, bool reset_session) {
  if (!_interfaces || !modeAvailable(mode)) return false;
  if (reset_session && _hooks.resetLocalSession) _hooks.resetLocalSession();

  if (_wifi_setup_stage != WifiSetupStage::IDLE) {
    cancelWifiSetup(false);
  }
  if (mode != CompanionMode::WiFi) stopWifiRadio(false);
  if (!_interfaces->selectExclusive(interfaceType(mode))) return false;
  _config.mode = mode;

  if (mode == CompanionMode::WiFi) {
    if (_config.wifi_configured) {
      _wifi_retry_delay = WIFI_RETRY_INITIAL_MS;
      startWifiAttempt(_config.ssid, _config.password, false);
    } else {
      // WiFi may be selected before provisioning.  Keep the selected transport
      // inactive and the radio/server off while USB remains a service console.
      stopWifiRadio(false);
    }
  } else if (mode == CompanionMode::USB) {
    // Do not drain the shared stream here: bytes following the command may
    // already be the first framed companion request.
    secureZero(_console_line, sizeof(_console_line));
    _console_line_len = 0;
    _console_line_overflow = false;
    _console_swallow_lf = false;
    _console_announced = false;
    clearConsoleTx();
  }
  return true;
}

void ConnectionController::begin(DataStore& store, MultiSerialInterface& interfaces,
                                 Stream& usb_console,
                                 SerialWifiInterface* wifi_interface,
                                 const ConnectionControllerHooks& hooks) {
  _store = &store;
  _interfaces = &interfaces;
  _console = &usb_console;
  _wifi_interface = wifi_interface;
  _hooks = hooks;
  _started = false;
  _quarantine_latched = false;
  _config_reset_notice = false;
  _console_announced = false;
  secureZero(_console_line, sizeof(_console_line));
  _console_line_len = 0;
  _console_line_overflow = false;
  _console_swallow_lf = false;
  clearConsoleTx();
  _wifi_setup_stage = WifiSetupStage::IDLE;
  _wifi_radio_on = false;
  _wifi_was_associated = false;
  _wifi_attempt_active = false;
  _wifi_attempt_started = 0;
  _wifi_retry_at = 0;
  _wifi_retry_delay = WIFI_RETRY_INITIAL_MS;
  scrubCandidate();
  loadConfig();

  if (!modeAvailable(_config.mode)) {
    Config fallback = _config;
    fallback.mode = (capabilities() & COMPANION_CAP_BLE) ? CompanionMode::BLE
        : ((capabilities() & COMPANION_CAP_USB) ? CompanionMode::USB
                                               : CompanionMode::WiFi);
    if (mutationAllowed()) saveConfig(fallback);
    _config = fallback;
  }
  _started = true;

  const bool boot_quarantined = _hooks.isStorageQuarantined &&
      _hooks.isStorageQuarantined();
  const bool cli_rescue = _hooks.isCliRescue && _hooks.isCliRescue();
  if (boot_quarantined || cli_rescue) {
    _interfaces->disable();
    stopWifiRadio(false);
    _quarantine_latched = boot_quarantined;
    return;
  }
  applyMode(_config.mode, false);
}

bool ConnectionController::setMode(CompanionMode mode) {
  if (!_started || !mutationAllowed() || !modeAvailable(mode)) return false;
  if (_config.mode == mode) return true;
  Config next = _config;
  next.mode = mode;
  if (!saveConfig(next)) {
    secureZero(&next, sizeof(next));
    return false;
  }
  const bool applied = applyMode(mode, true);
  if (applied) _config = next;
  secureZero(&next, sizeof(next));
  return applied;
}

bool ConnectionController::resolveWifiClient(uint32_t request_id, bool approve) {
#if defined(ESP32)
  if (!_started || !_wifi_interface || request_id == 0) return false;
  if (approve && !mutationAllowed()) return false;
  return _wifi_interface->resolvePendingClient(request_id, approve);
#else
  (void)request_id;
  (void)approve;
  return false;
#endif
}

CompanionStatus ConnectionController::status() const {
  CompanionStatus result;
  result.capabilities = capabilities();
  result.selected = _config.mode;
  result.connectedVia = _config.mode;
  result.usbConsoleEnabled = consoleEnabled();
  result.wifiConfigured = _config.wifi_configured;
  if (!_started || !_interfaces) {
    return result;
  }

  result.clientConnected = _interfaces->isInterfaceConnected(interfaceType(_config.mode));
#if defined(ESP32)
  result.wifiAssociated = _wifi_radio_on && WiFi.status() == WL_CONNECTED;
  if (result.wifiAssociated) {
    const String ip = WiFi.localIP().toString();
    snprintf(result.wifiLocalIp, sizeof(result.wifiLocalIp), "%s", ip.c_str());
  }
  if (_wifi_interface && _wifi_interface->hasPendingClientApproval()) {
    result.wifiApprovalPending = true;
    result.wifiRequestId = _wifi_interface->getPendingClientRequestId();
    _wifi_interface->copyPendingClientPeer(
        result.wifiClientIp, sizeof(result.wifiClientIp));
    const uint32_t now = millis();
    const uint32_t deadline = _wifi_interface->getPendingClientDeadline();
    if (!deadlineReached(now, deadline)) {
      result.wifiApprovalRemainingMs = static_cast<uint32_t>(deadline - now);
    }
  }
#endif
  return result;
}

void ConnectionController::serviceWifi() {
#if defined(ESP32)
  if (!_wifi_interface) return;
  const uint32_t now = millis();
  if (!mutationAllowed()) {
    if (_wifi_setup_stage != WifiSetupStage::IDLE) {
      scrubCandidate();
      _wifi_setup_stage = WifiSetupStage::IDLE;
      stopWifiRadio(false);
    }
    // Quarantine/CLI rescue may keep an already approved client alive long
    // enough to receive its terminal response, but no new peer is admitted.
    if (_wifi_interface->hasPendingClientApproval()) {
      _wifi_interface->resolvePendingClient(
          _wifi_interface->getPendingClientRequestId(), false);
    }
    return;
  }
  if (_wifi_setup_stage != WifiSetupStage::IDLE &&
      elapsed(now, _wifi_setup_activity, WIFI_SETUP_IDLE_TIMEOUT_MS)) {
    printConsole("WiFi setup timed out; credentials were not saved.\r\n");
    cancelWifiSetup(true);
    return;
  }
  if (_wifi_interface->hasPendingClientApproval() &&
      deadlineReached(now, _wifi_interface->getPendingClientDeadline())) {
    _wifi_interface->resolvePendingClient(
        _wifi_interface->getPendingClientRequestId(), false);
  }
  const bool associated = _wifi_radio_on && WiFi.status() == WL_CONNECTED;
  if (_wifi_setup_stage == WifiSetupStage::TESTING) {
    if (associated) {
      _wifi_attempt_active = false;
      _wifi_setup_stage = WifiSetupStage::TEST_OK;
      _wifi_setup_activity = now;
      printConsole("WiFi test passed. Type 'wifi save' to store it.\r\n");
    } else if (_wifi_attempt_active &&
               elapsed(now, _wifi_attempt_started, WIFI_CONNECT_TIMEOUT_MS)) {
      _wifi_setup_stage = WifiSetupStage::FAILED;
      printConsole("WiFi test failed; credentials were not saved.\r\n");
      cancelWifiSetup(true);
    }
    return;
  }

  if (_config.mode != CompanionMode::WiFi || !_config.wifi_configured) return;
  if (associated) {
    _wifi_was_associated = true;
    _wifi_attempt_active = false;
    _wifi_retry_at = 0;
    _wifi_retry_delay = WIFI_RETRY_INITIAL_MS;
    return;
  }
  if (_wifi_was_associated) {
    _wifi_was_associated = false;
    _wifi_attempt_active = false;
    _wifi_retry_at = now + WIFI_RETRY_INITIAL_MS;
    _wifi_retry_delay = WIFI_RETRY_INITIAL_MS;
    return;
  }
  if (_wifi_attempt_active) {
    if (!elapsed(now, _wifi_attempt_started, WIFI_CONNECT_TIMEOUT_MS)) return;
    _wifi_attempt_active = false;
    WiFi.disconnect(false, false);
    _wifi_retry_at = now + _wifi_retry_delay;
    _wifi_retry_delay = _wifi_retry_delay >= WIFI_RETRY_MAX_MS / 2
        ? WIFI_RETRY_MAX_MS : _wifi_retry_delay * 2;
    return;
  }
  if (_wifi_retry_at != 0 && deadlineReached(now, _wifi_retry_at)) {
    startWifiAttempt(_config.ssid, _config.password, false);
  }
#endif
}

bool ConnectionController::startWifiSetup() {
#if defined(ESP32)
  if (!mutationAllowed() || !(capabilities() & COMPANION_CAP_WIFI)) return false;
  if (_config.mode == CompanionMode::USB) return false;
  // A restarted wizard must not leave its previous candidate association or
  // sleep inhibit alive while waiting for new input.
  stopWifiRadio(false);
  scrubCandidate();
  _wifi_setup_stage = WifiSetupStage::WAIT_SSID;
  _wifi_setup_activity = millis();
  printConsole("SSID input is hidden; enter SSID, then Enter:\r\n");
  return true;
#else
  return false;
#endif
}

void ConnectionController::cancelWifiSetup(bool restore_selected_wifi) {
  scrubCandidate();
  _wifi_setup_stage = WifiSetupStage::IDLE;
  _wifi_setup_activity = 0;
  if (restore_selected_wifi && _config.mode == CompanionMode::WiFi &&
      _config.wifi_configured) {
    _interfaces->selectExclusive(InterfaceType::WiFi);
    startWifiAttempt(_config.ssid, _config.password, false);
  } else {
    stopWifiRadio(false);
  }
}

bool ConnectionController::saveTestedWifi() {
  if (!mutationAllowed() || _wifi_setup_stage != WifiSetupStage::TEST_OK ||
      _candidate_ssid_len == 0) return false;
  Config next = _config;
  secureZero(next.ssid, sizeof(next.ssid));
  secureZero(next.password, sizeof(next.password));
  next.wifi_configured = true;
  next.ssid_len = _candidate_ssid_len;
  next.password_len = _candidate_password_len;
  memcpy(next.ssid, _candidate_ssid, next.ssid_len);
  memcpy(next.password, _candidate_password, next.password_len);
  if (!saveConfig(next)) {
    secureZero(&next, sizeof(next));
    return false;
  }
  _config = next;
  secureZero(&next, sizeof(next));
  scrubCandidate();
  _wifi_setup_stage = WifiSetupStage::IDLE;
  _wifi_setup_activity = 0;
  if (_config.mode == CompanionMode::WiFi) {
    _interfaces->selectExclusive(InterfaceType::WiFi);
  } else {
    stopWifiRadio(false);
  }
  return true;
}

bool ConnectionController::forgetWifi() {
  if (!mutationAllowed()) return false;
  Config clean;
  clean.mode = (capabilities() & COMPANION_CAP_BLE) ? CompanionMode::BLE
      : CompanionMode::USB;

  // Forget is deliberately monotonic rather than rollback-capable: no old
  // credential-bearing .bak/.tmp may become eligible recovery data later.
  if (_hooks.resetLocalSession) _hooks.resetLocalSession();
  stopWifiRadio(true);
  scrubCandidate();

  FILESYSTEM* fs = _store ? _store->getPrimaryFS() : nullptr;
  bool neutralized = fs != nullptr;
  if (fs) {
    // Neutralize recovery generations first.  Once primary is removed or
    // overwritten, no later recovery candidate can resurrect credentials.
    neutralized = removeOrNeutralizeConfigFile(CONFIG_TEMP_PATH, clean) && neutralized;
    neutralized = removeOrNeutralizeConfigFile(CONFIG_BACKUP_PATH, clean) && neutralized;
    neutralized = removeOrNeutralizeConfigFile(CONFIG_PATH, clean) && neutralized;
  }
  const bool saved = neutralized && saveConfig(clean);
  _config = clean;
  _wifi_setup_stage = WifiSetupStage::IDLE;
  _interfaces->selectExclusive(interfaceType(clean.mode));
  if (fs) {
    if (fs->exists(CONFIG_TEMP_PATH)) fs->remove(CONFIG_TEMP_PATH);
    if (fs->exists(CONFIG_BACKUP_PATH)) fs->remove(CONFIG_BACKUP_PATH);
  }
  Config verified;
  const bool primary_clean = fs && readConfigFile(CONFIG_PATH, verified) &&
      configsEqual(clean, verified);
  secureZero(&verified, sizeof(verified));
  return saved && primary_clean && !fs->exists(CONFIG_TEMP_PATH) &&
      !fs->exists(CONFIG_BACKUP_PATH);
}

void ConnectionController::printConsole(const char* text) {
  if (!consoleEnabled() || !text) return;
  const size_t len = strlen(text);
  if (len == 0 || len > CONSOLE_TX_MAX - _console_tx_len) return;
  uint16_t tail = static_cast<uint16_t>(
      (_console_tx_head + _console_tx_len) % CONSOLE_TX_MAX);
  for (size_t i = 0; i < len; ++i) {
    _console_tx[tail] = text[i];
    tail = static_cast<uint16_t>((tail + 1) % CONSOLE_TX_MAX);
  }
  _console_tx_len = static_cast<uint16_t>(_console_tx_len + len);
}

void ConnectionController::clearConsoleTx() {
  secureZero(_console_tx, sizeof(_console_tx));
  _console_tx_head = 0;
  _console_tx_len = 0;
}

void ConnectionController::serviceConsoleTx() {
  if (!consoleEnabled()) {
    clearConsoleTx();
    return;
  }
  int writable = _console->availableForWrite();
  if (writable <= 0 || _console_tx_len == 0) return;
  size_t count = static_cast<size_t>(writable);
  if (count > CONSOLE_TX_BYTES_PER_LOOP) count = CONSOLE_TX_BYTES_PER_LOOP;
  if (count > _console_tx_len) count = _console_tx_len;
  const size_t contiguous = CONSOLE_TX_MAX - _console_tx_head;
  if (count > contiguous) count = contiguous;
  const size_t written = _console->write(
      reinterpret_cast<const uint8_t*>(_console_tx + _console_tx_head), count);
  if (written == 0 || written > count) return;
  secureZero(_console_tx + _console_tx_head, written);
  _console_tx_head = static_cast<uint16_t>(
      (_console_tx_head + written) % CONSOLE_TX_MAX);
  _console_tx_len = static_cast<uint16_t>(_console_tx_len - written);
}

void ConnectionController::printHelp() {
  printConsole(
      "Commands: status | mode ble | mode usb | mode wifi | wifi setup | "
      "wifi status | wifi save | wifi cancel | wifi forget | help\r\n"
      "Credential input is not echoed. WiFi is saved only after a passed test.\r\n");
}

void ConnectionController::printStatus() {
  const CompanionStatus current = status();
  char line[256];
  snprintf(line, sizeof(line),
      "Mode=%s companion=%s via=%s USB-service=%s WiFi-config=%s link=%s IP=%s approval=%s\r\n",
      modeName(current.selected), current.clientConnected ? "connected" : "idle",
      current.clientConnected ? modeName(current.connectedVia) : "none",
      current.usbConsoleEnabled ? "on" : "off",
      current.wifiConfigured ? "yes" : "no",
      current.wifiAssociated ? "associated" : "down",
      current.wifiLocalIp[0] ? current.wifiLocalIp : "none",
      current.wifiApprovalPending ? "pending" : "none");
  printConsole(line);
}

void ConnectionController::handleConsoleLine(char* raw_line) {
  if (_wifi_setup_stage == WifiSetupStage::WAIT_SSID) {
    if (strcmp(raw_line, "cancel") == 0) {
      cancelWifiSetup(true);
      printConsole("WiFi setup cancelled.\r\n");
      return;
    }
    const size_t len = strlen(raw_line);
    if (len == 0 || len > WIFI_SSID_MAX ||
        !validSecretBytes(reinterpret_cast<const uint8_t*>(raw_line), len)) {
      printConsole("Invalid hidden SSID; enter 1..32 bytes or 'cancel'.\r\n");
      return;
    }
    memcpy(_candidate_ssid, raw_line, len);
    _candidate_ssid[len] = 0;
    _candidate_ssid_len = static_cast<uint8_t>(len);
    _wifi_setup_stage = WifiSetupStage::WAIT_PASSWORD;
    printConsole("Password input is hidden; enter 8..64 bytes, blank for open WiFi, or 'cancel':\r\n");
    return;
  }
  if (_wifi_setup_stage == WifiSetupStage::WAIT_PASSWORD) {
    if (strcmp(raw_line, "cancel") == 0) {
      cancelWifiSetup(true);
      printConsole("WiFi setup cancelled.\r\n");
      return;
    }
    const size_t len = strlen(raw_line);
    if (len > WIFI_PASSWORD_MAX || (len > 0 && len < 8) ||
        !validSecretBytes(reinterpret_cast<const uint8_t*>(raw_line), len)) {
      printConsole("Invalid hidden password; use blank or 8..64 bytes.\r\n");
      return;
    }
    memcpy(_candidate_password, raw_line, len);
    _candidate_password[len] = 0;
    _candidate_password_len = static_cast<uint8_t>(len);
    printConsole("Testing WiFi without saving...\r\n");
    startWifiAttempt(_candidate_ssid, _candidate_password, true);
    return;
  }

  char* line = trimAscii(raw_line);
  lowerAscii(line);
  if (!line[0]) return;
  const bool quarantined = _hooks.isStorageQuarantined &&
      _hooks.isStorageQuarantined();
  if (quarantined && strcmp(line, "status") != 0) {
    printConsole("Connection settings are read-only during storage recovery.\r\n");
    return;
  }
  if (strcmp(line, "status") == 0 || strcmp(line, "wifi status") == 0) {
    printStatus();
  } else if (strcmp(line, "help") == 0) {
    printHelp();
  } else if (strcmp(line, "mode ble") == 0) {
    printConsole(setMode(CompanionMode::BLE) ? "Mode BLE saved.\r\n" :
                                              "BLE mode unavailable or save failed.\r\n");
  } else if (strcmp(line, "mode wifi") == 0) {
    printConsole(setMode(CompanionMode::WiFi) ? "Mode WiFi saved.\r\n" :
                                               "WiFi mode unavailable or save failed.\r\n");
  } else if (strcmp(line, "mode usb") == 0) {
    printConsole("Switching to USB companion; service console is closing.\r\n");
    if (!setMode(CompanionMode::USB)) {
      printConsole("USB mode unavailable or save failed.\r\n");
    }
  } else if (strcmp(line, "wifi setup") == 0) {
    if (!startWifiSetup()) printConsole("WiFi setup unavailable.\r\n");
  } else if (strcmp(line, "wifi save") == 0) {
    printConsole(saveTestedWifi() ? "Tested WiFi saved.\r\n" :
                                    "Nothing saved; pass WiFi test first.\r\n");
  } else if (strcmp(line, "wifi cancel") == 0) {
    cancelWifiSetup(true);
    printConsole("WiFi setup cancelled.\r\n");
  } else if (strcmp(line, "wifi forget") == 0) {
    printConsole("Forgetting WiFi and falling back to BLE...\r\n");
    printConsole(forgetWifi() ? "WiFi credentials forgotten.\r\n" :
                                "WiFi cleared in RAM; persistent cleanup failed.\r\n");
  } else {
    printConsole("Unknown command. Type 'help'.\r\n");
  }
}

void ConnectionController::serviceConsole() {
  if (!consoleEnabled()) {
    secureZero(_console_line, sizeof(_console_line));
    _console_line_len = 0;
    _console_line_overflow = false;
    _console_swallow_lf = false;
    _console_announced = false;
    clearConsoleTx();
    return;
  }
  if (!_console_announced) {
    _console_announced = true;
    printConsole("SmartUI service console. Type 'help'. Input is not echoed.\r\n");
    if (_config_reset_notice) {
      printConsole("Invalid connection settings reset to BLE; identity was not changed.\r\n");
      _config_reset_notice = false;
    }
  }

  uint8_t budget = CONSOLE_BYTES_PER_LOOP;
  while (budget-- > 0 && _console->available() > 0) {
    const int value = _console->read();
    if (value < 0) break;
    if (_wifi_setup_stage != WifiSetupStage::IDLE) {
      _wifi_setup_activity = millis();
    }
    const char c = static_cast<char>(value);
    if (c == '\n' && _console_swallow_lf) {
      _console_swallow_lf = false;
      continue;
    }
    if (c == '\r' || c == '\n') {
      _console_swallow_lf = c == '\r';
      if (_console_line_overflow) {
        printConsole("Input too long; discarded.\r\n");
      } else if (_console_line_len > 0 ||
                 _wifi_setup_stage == WifiSetupStage::WAIT_PASSWORD) {
        _console_line[_console_line_len] = 0;
        handleConsoleLine(_console_line);
      }
      secureZero(_console_line, sizeof(_console_line));
      _console_line_len = 0;
      _console_line_overflow = false;
      if (!consoleEnabled()) break;
    } else if (c == '\b' || c == 0x7f) {
      _console_swallow_lf = false;
      if (_console_line_len > 0) {
        _console_line[--_console_line_len] = 0;
      }
    } else if (static_cast<uint8_t>(c) >= 0x20) {
      _console_swallow_lf = false;
      if (_console_line_len < CONSOLE_LINE_MAX) {
        _console_line[_console_line_len++] = c;
      } else {
        _console_line_overflow = true;
      }
    } else {
      _console_swallow_lf = false;
    }
  }
  serviceConsoleTx();
}

void ConnectionController::loop() {
  if (!_started) return;
  const bool quarantined = _hooks.isStorageQuarantined &&
      _hooks.isStorageQuarantined();
  if (quarantined && !_quarantine_latched) {
    if (_wifi_setup_stage != WifiSetupStage::IDLE) {
      // Candidate/test credentials are not persistent and must be scrubbed.
      // Do not re-enable an old transport while recovery is terminal.
      scrubCandidate();
      _wifi_setup_stage = WifiSetupStage::IDLE;
      stopWifiRadio(false);
    }
    _quarantine_latched = true;
  }
  serviceWifi();
  serviceConsole();
}

#endif  // SMARTUI_CONNECTION_SELECTOR
