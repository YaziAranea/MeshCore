#include "ConnectionController.h"
#include <helpers/SmartUiSleepPolicy.h>
#include <helpers/SmartUiQuickReplies.h>

#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR

#include <Arduino.h>
#include <helpers/MultiSerialInterface.h>
#include <helpers/SmartUiBuildInfo.h>
#include <helpers/StorageTransaction.h>

#include "DataStore.h"

#if defined(NRF52_PLATFORM)
  #include <Adafruit_LittleFS.h>
  #include <utility/debug.h>
#endif

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
// Existence, including an interrupted/empty write, forbids credential recovery.
static const char* CONFIG_FORGET_PATH = "/connection.forgot";
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

#if defined(NRF52_PLATFORM)
// Primary InternalFS has 224 blocks on published nRF52840 boards. Keep the
// diagnostic bounded even if a future build supplies a different filesystem.
static constexpr uint32_t STORAGE_DIAG_MAX_BLOCKS = 1024;
struct StorageBlockCount {
  uint32_t total = 0;
  uint32_t used = 0;
  uint32_t visits = 0;
  uint8_t seen[STORAGE_DIAG_MAX_BLOCKS / 8] = {};
};
static int countStorageBlock(void* context, lfs_block_t block) {
  auto& count = *static_cast<StorageBlockCount*>(context);
  if (block >= count.total || ++count.visits > count.total * 4U + 16U)
    return LFS_ERR_CORRUPT;
  const uint8_t mask = static_cast<uint8_t>(1U << (block & 7U));
  if (!(count.seen[block / 8] & mask)) {
    count.seen[block / 8] |= mask;
    ++count.used;
  }
  return 0;
}
// Caller holds the filesystem lock and has checked its mounted geometry.
static void readStorageStat(lfs_t* fs, const char* path, char (&metadata)[24]) {
  struct lfs_info info = {};
  const int rc = lfs_stat(fs, path, &info);
  if (rc == 0) {
    snprintf(metadata, sizeof(metadata), "0:%lu",
        static_cast<unsigned long>(static_cast<uint32_t>(info.size)));
  } else {
    snprintf(metadata, sizeof(metadata), "%d:-1", rc);
  }
}
#endif

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

static const char* modeToken(CompanionMode mode) {
  switch (mode) {
    case CompanionMode::BLE: return "ble";
    case CompanionMode::USB: return "usb";
    case CompanionMode::WiFi: return "wifi";
  }
  return "none";
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

#if defined(ESP32)
static int hexNibble(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

static bool decodeApiSecret(const char* hex, char* dest, size_t capacity,
                            size_t minimum, size_t maximum, uint8_t& length) {
  secureZero(dest, capacity);
  length = 0;
  const size_t count = strlen(hex);
  if ((count & 1) || count / 2 < minimum || count / 2 > maximum || count / 2 >= capacity)
    return false;
  for (size_t i = 0; i < count / 2; ++i) {
    const int high = hexNibble(hex[2 * i]);
    const int low = hexNibble(hex[2 * i + 1]);
    if (high < 0 || low < 0) { secureZero(dest, capacity); return false; }
    dest[i] = static_cast<char>((high << 4) | low);
  }
  if (!validSecretBytes(reinterpret_cast<const uint8_t*>(dest), count / 2)) {
    secureZero(dest, capacity);
    return false;
  }
  length = static_cast<uint8_t>(count / 2);
  return true;
}
#endif

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
  return mutationError() == ConnectionChangeError::None;
}

ConnectionChangeError ConnectionController::mutationError() const {
  if (_hooks.isCliRescue && _hooks.isCliRescue()) return ConnectionChangeError::CliRescue;
  if (_hooks.isStorageQuarantined && _hooks.isStorageQuarantined()) {
    return ConnectionChangeError::StorageReadOnly;
  }
  if (_config_storage_error) return ConnectionChangeError::StorageReadOnly;
  return ConnectionChangeError::None;
}

bool ConnectionController::consoleEnabled() const {
  if (!_started || !_console || (_config.mode == CompanionMode::USB && !_config_storage_error)) return false;
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

bool ConnectionController::storageFailed(StoragePhase phase) {
  _storage_phase = phase;
  return false;
}

const char* ConnectionController::storagePhaseName(StoragePhase phase) {
  switch (phase) {
    case StoragePhase::NONE: return "none";
    case StoragePhase::UNAVAILABLE: return "unavailable";
    case StoragePhase::RECOVERY_BLOCKED: return "recovery-blocked";
    case StoragePhase::CLEAN_INVALID: return "clean-invalid";
    case StoragePhase::MARKER_OPEN: return "marker-open";
    case StoragePhase::MARKER_VERIFY: return "marker-verify";
    case StoragePhase::CLEAN_REMOVE: return "clean-primary-remove";
    case StoragePhase::CLEAN_OPEN: return "clean-primary-open";
    case StoragePhase::CLEAN_WRITE: return "clean-primary-write";
    case StoragePhase::CLEAN_VERIFY: return "clean-primary-verify";
    case StoragePhase::CLEAN_TEMP: return "clean-temp";
    case StoragePhase::CLEAN_BACKUP: return "clean-backup";
    case StoragePhase::CLEAN_FINAL_VERIFY: return "clean-final-verify";
    case StoragePhase::MARKER_REMOVE: return "marker-remove";
    case StoragePhase::RECOVER_REMOVE: return "recover-primary-remove";
    case StoragePhase::RECOVER_OPEN: return "recover-primary-open";
    case StoragePhase::RECOVER_WRITE: return "recover-primary-write";
    case StoragePhase::RECOVER_VERIFY: return "recover-primary-verify";
    case StoragePhase::RECOVER_TEMP: return "recover-temp-cleanup";
    case StoragePhase::SAVE_TEMP_REMOVE: return "save-temp-remove";
    case StoragePhase::SAVE_OPEN: return "save-temp-open";
    case StoragePhase::SAVE_WRITE: return "save-temp-write";
    case StoragePhase::SAVE_VERIFY: return "save-temp-verify";
    case StoragePhase::SAVE_ROTATE: return "save-rotate";
    case StoragePhase::SAVE_PUBLISH: return "save-publish";
    case StoragePhase::SAVE_FINAL_VERIFY: return "save-final-verify";
  }
  return "unknown";
}

bool ConnectionController::writeConfigFile(const char* path, const Config& config,
                                          StoragePhase open_failure,
                                          StoragePhase write_failure) {
  if (!_store) return storageFailed(StoragePhase::UNAVAILABLE);
  FILESYSTEM* fs = _store->getPrimaryFS();
  if (!fs) return storageFailed(StoragePhase::UNAVAILABLE);

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
    return storageFailed(open_failure);
  }
  const bool success = file.write(raw, sizeof(raw)) == sizeof(raw);
  file.flush();
  file.close();
  secureZero(raw, sizeof(raw));
  return success ? true : storageFailed(write_failure);
}

bool ConnectionController::saveConfig(const Config& config, ConnectionChangeError* error) {
  if (error) *error = ConnectionChangeError::None;
  const auto fail = [error](ConnectionChangeError reason) {
    if (error) *error = reason;
    return false;
  };
  const ConnectionChangeError blocked = mutationError();
  if (blocked != ConnectionChangeError::None) return fail(blocked);
  if (!_store) {
    storageFailed(StoragePhase::UNAVAILABLE);
    return fail(ConnectionChangeError::StorageUnavailable);
  }
  FILESYSTEM* fs = _store->getPrimaryFS();
  if (!fs) {
    storageFailed(StoragePhase::UNAVAILABLE);
    return fail(ConnectionChangeError::StorageUnavailable);
  }
  if (fs->exists(CONFIG_TEMP_PATH) && !fs->remove(CONFIG_TEMP_PATH)) {
    storageFailed(StoragePhase::SAVE_TEMP_REMOVE);
    return fail(ConnectionChangeError::TempCleanup);
  }
  if (!writeConfigFile(CONFIG_TEMP_PATH, config, StoragePhase::SAVE_OPEN,
                       StoragePhase::SAVE_WRITE)) return fail(ConnectionChangeError::Write);

  Config verified;
  const bool scratch_valid = readConfigFile(CONFIG_TEMP_PATH, verified) &&
      configsEqual(config, verified);
  secureZero(&verified, sizeof(verified));
  if (!scratch_valid) {
    fs->remove(CONFIG_TEMP_PATH);
    storageFailed(StoragePhase::SAVE_VERIFY);
    return fail(ConnectionChangeError::VerifyTemp);
  }

  Config current;
  const bool current_valid = readConfigFile(CONFIG_PATH, current);
  secureZero(&current, sizeof(current));
  const bool had_primary = fs->exists(CONFIG_PATH);
  bool rotated = false;
  if (had_primary && current_valid) {
    if (fs->exists(CONFIG_BACKUP_PATH) && !fs->remove(CONFIG_BACKUP_PATH)) {
      storageFailed(StoragePhase::SAVE_ROTATE);
      return fail(ConnectionChangeError::Rotate);
    }
    if (!fs->rename(CONFIG_PATH, CONFIG_BACKUP_PATH)) {
      storageFailed(StoragePhase::SAVE_ROTATE);
      return fail(ConnectionChangeError::Rotate);
    }
    rotated = true;
  } else if (had_primary && !fs->remove(CONFIG_PATH)) {
    storageFailed(StoragePhase::SAVE_ROTATE);
    return fail(ConnectionChangeError::Rotate);
  }

  if (!fs->rename(CONFIG_TEMP_PATH, CONFIG_PATH)) {
    if (rotated && !fs->exists(CONFIG_PATH) && fs->exists(CONFIG_BACKUP_PATH)) {
      fs->rename(CONFIG_BACKUP_PATH, CONFIG_PATH);
    }
    storageFailed(StoragePhase::SAVE_PUBLISH);
    return fail(ConnectionChangeError::Publish);
  }

  Config published;
  const bool success = readConfigFile(CONFIG_PATH, published) &&
      configsEqual(config, published);
  secureZero(&published, sizeof(published));
  if (!success) storageFailed(StoragePhase::SAVE_FINAL_VERIFY);
  return success ? true : fail(ConnectionChangeError::VerifyFinal);
}

bool ConnectionController::removeOrNeutralizeConfigFile(
    const char* path, const Config& clean) {
  if (!_store || !path) return false;
  FILESYSTEM* fs = _store->getPrimaryFS();
  if (!fs) return false;
  if (!fs->exists(path)) return true;
  // Treat an already-absent path as success even if the filesystem reports a
  // failed unlink.  This keeps cleanup idempotent after an interrupted retry.
  fs->remove(path);
  if (!fs->exists(path)) return true;

  // FILE_O_WRITE appends on Adafruit nRF52 LittleFS.  Never try to neutralize
  // an existing record by writing over it: that can preserve credentials and
  // create an invalid longer record.  A leftover is safe only when its exact
  // on-flash record already matches the credential-free configuration.
  Config verified;
  const bool safe = readConfigFile(path, verified) &&
      configsEqual(clean, verified);
  secureZero(&verified, sizeof(verified));
  return safe;
}

bool ConnectionController::persistCleanConfig(const Config& clean) {
  if (!mutationAllowed()) return storageFailed(StoragePhase::RECOVERY_BLOCKED);
  if (clean.wifi_configured) return storageFailed(StoragePhase::CLEAN_INVALID);
  if (!_store) return storageFailed(StoragePhase::UNAVAILABLE);
  FILESYSTEM* fs = _store->getPrimaryFS();
  if (!fs) return storageFailed(StoragePhase::UNAVAILABLE);

  Config verified;
  bool primary_clean = readConfigFile(CONFIG_PATH, verified) &&
      configsEqual(clean, verified);
  secureZero(&verified, sizeof(verified));
  // Normal BLE/USB boots must not write storage when there is no recovery work.
  // Besides avoiding flash wear, this prevents a transient marker write or
  // unlink failure from quarantining an otherwise valid configuration.
  if (primary_clean && !fs->exists(CONFIG_TEMP_PATH) &&
      !fs->exists(CONFIG_BACKUP_PATH) && !fs->exists(CONFIG_FORGET_PATH)) {
    return true;
  }

  // Keep a durable fail-closed barrier until every old generation is harmless.
  // A partial marker is intentional: its existence alone suppresses secrets.
  if (!fs->exists(CONFIG_FORGET_PATH)) {
    File marker = openConfigWrite(fs, CONFIG_FORGET_PATH);
    if (!marker) return storageFailed(StoragePhase::MARKER_OPEN);
    const uint8_t value = 1;
    marker.write(&value, sizeof(value));
    marker.flush();
    marker.close();
    if (!fs->exists(CONFIG_FORGET_PATH)) return storageFailed(StoragePhase::MARKER_VERIFY);
  }

  if (!primary_clean) {
    // Do not use saveConfig here: it truncates .tmp, which may be the sole
    // verified recovery generation. Preserve .tmp/.bak until primary verifies.
    // Remove an invalid primary before writing because nRF52 FILE_O_WRITE
    // appends instead of truncating.  The durable marker makes the gap safe.
    if (fs->exists(CONFIG_PATH)) {
      fs->remove(CONFIG_PATH);
      if (fs->exists(CONFIG_PATH)) return storageFailed(StoragePhase::CLEAN_REMOVE);
    }
    if (!writeConfigFile(CONFIG_PATH, clean, StoragePhase::CLEAN_OPEN,
                         StoragePhase::CLEAN_WRITE)) return false;
    primary_clean = readConfigFile(CONFIG_PATH, verified) &&
        configsEqual(clean, verified);
    secureZero(&verified, sizeof(verified));
    if (!primary_clean) return storageFailed(StoragePhase::CLEAN_VERIFY);
  }

  const bool temporary_safe = removeOrNeutralizeConfigFile(CONFIG_TEMP_PATH, clean);
  const bool backup_safe = removeOrNeutralizeConfigFile(CONFIG_BACKUP_PATH, clean);
  if (!temporary_safe) return storageFailed(StoragePhase::CLEAN_TEMP);
  if (!backup_safe) return storageFailed(StoragePhase::CLEAN_BACKUP);
  // Recheck the anchor before dropping the credential-recovery barrier.
  primary_clean = readConfigFile(CONFIG_PATH, verified) &&
      configsEqual(clean, verified);
  secureZero(&verified, sizeof(verified));
  if (!primary_clean) return storageFailed(StoragePhase::CLEAN_FINAL_VERIFY);
  if (fs->exists(CONFIG_FORGET_PATH)) fs->remove(CONFIG_FORGET_PATH);
  return !fs->exists(CONFIG_FORGET_PATH) ? true : storageFailed(StoragePhase::MARKER_REMOVE);
}

bool ConnectionController::loadConfig() {
  Config primary;
  Config temporary;
  Config backup;
  FILESYSTEM* fs = _store ? _store->getPrimaryFS() : nullptr;
  const bool forget_pending = fs && fs->exists(CONFIG_FORGET_PATH);
  const bool primary_valid = readConfigFile(CONFIG_PATH, primary) &&
      (!forget_pending || !primary.wifi_configured);
  const bool temporary_valid = readConfigFile(CONFIG_TEMP_PATH, temporary) &&
      (!forget_pending || !temporary.wifi_configured);
  const bool backup_valid = readConfigFile(CONFIG_BACKUP_PATH, backup) &&
      (!forget_pending || !backup.wifi_configured);
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

  if (!mutationAllowed()) {
    return !forget_pending && choice != mesh::storage::RecoveryCandidate::NONE
        ? true : storageFailed(StoragePhase::RECOVERY_BLOCKED);
  }
  if (!_config.wifi_configured) {
    return persistCleanConfig(_config);
  } else if (choice != mesh::storage::RecoveryCandidate::PRIMARY) {
    // The selected .tmp/.bak may be the sole durable credential-bearing copy.
    // Write the invalid/missing primary directly and preserve the source until
    // the new anchor is read back; normal saveConfig() consumes its scratch.
    // NRF FILE_O_WRITE does not necessarily truncate a malformed longer file.
    if (fs->exists(CONFIG_PATH) && !fs->remove(CONFIG_PATH)) return storageFailed(StoragePhase::RECOVER_REMOVE);
    if (!writeConfigFile(CONFIG_PATH, _config, StoragePhase::RECOVER_OPEN,
                         StoragePhase::RECOVER_WRITE)) return false;
    Config verified;
    const bool recovered = readConfigFile(CONFIG_PATH, verified) && configsEqual(_config, verified);
    secureZero(&verified, sizeof(verified));
    if (!recovered) return storageFailed(StoragePhase::RECOVER_VERIFY);
    if (fs->exists(CONFIG_TEMP_PATH) && !fs->remove(CONFIG_TEMP_PATH))
      storageFailed(StoragePhase::RECOVER_TEMP);  // Existing best-effort cleanup remains nonfatal.
    return true;
  } else if (fs->exists(CONFIG_TEMP_PATH)) {
    if (!fs->remove(CONFIG_TEMP_PATH)) storageFailed(StoragePhase::RECOVER_TEMP);
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
  _last_change_error = ConnectionChangeError::None;
  _started = false;
  _quarantine_latched = false;
  _config_reset_notice = false;
  _config_storage_error = false;
  _storage_phase = StoragePhase::NONE;
  _console_announced = false;
  secureZero(_console_line, sizeof(_console_line));
  _console_line_len = 0;
  _console_line_overflow = false;
  _console_swallow_lf = false;
  clearConsoleTx();
  _wifi_setup_stage = WifiSetupStage::IDLE;
  _api_wifi_setup = false;
  _api_wifi_result = WifiApiResult::NONE;
  _api_mode_pending = _api_mode_reply_queued = false;
  _api_mode_error = "none";
  _wifi_radio_on = false;
  _wifi_was_associated = false;
  _wifi_attempt_active = false;
  _wifi_attempt_started = 0;
  _wifi_retry_at = 0;
  _wifi_retry_delay = WIFI_RETRY_INITIAL_MS;
  scrubCandidate();
  _config_storage_error = !loadConfig();

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
  if (boot_quarantined || cli_rescue || _config_storage_error) {
    _interfaces->disable();
    stopWifiRadio(false);
    _quarantine_latched = boot_quarantined;
    return;
  }
  applyMode(_config.mode, false);
}

bool ConnectionController::setMode(CompanionMode mode) {
  if (_api_mode_pending) {
    _api_mode_pending = _api_mode_reply_queued = false;
    _api_mode_error = "cancelled";
  }
  _last_change_error = ConnectionChangeError::None;
  if (!_started) {
    _last_change_error = ConnectionChangeError::NotStarted;
    return false;
  }
  _last_change_error = mutationError();
  if (_last_change_error != ConnectionChangeError::None) return false;
  if (!modeAvailable(mode)) {
    _last_change_error = ConnectionChangeError::Unavailable;
    return false;
  }
  if (_config.mode == mode) return true;
  Config next = _config;
  next.mode = mode;
  if (!saveConfig(next, &_last_change_error)) {
    secureZero(&next, sizeof(next));
    return false;
  }
  const bool applied = applyMode(mode, true);
  if (applied) _config = next;
  else _last_change_error = ConnectionChangeError::Apply;
  secureZero(&next, sizeof(next));
  return applied;
}

bool ConnectionController::resolveWifiClient(uint32_t request_id, bool approve) {
#if defined(ESP32)
  if (!_started || !_wifi_interface || request_id == 0) return false;
  if (approve && (!mutationAllowed() || _config.mode != CompanionMode::WiFi ||
      _wifi_setup_stage != WifiSetupStage::IDLE || !_config.wifi_configured ||
      !_wifi_radio_on || WiFi.status() != WL_CONNECTED)) return false;
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
  result.storageRecoveryRequired = _config_storage_error;
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
      _api_wifi_setup = false;
      _api_wifi_result = WifiApiResult::CANCELLED;
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
    if (_api_wifi_setup) _api_wifi_result = WifiApiResult::TIMED_OUT;
    else printConsole("WiFi setup timed out; credentials were not saved.\r\n");
    cancelWifiSetup(true);
    return;
  }
  if (_wifi_interface->hasPendingClientApproval()) {
    // Wi-Fi companion access is automatic on the selected, saved network.
    // No UI interaction is required; provisional setup networks and expired
    // requests are not admitted. The transport still permits only one client.
    const bool accept = _config.mode == CompanionMode::WiFi &&
        _wifi_setup_stage == WifiSetupStage::IDLE && _config.wifi_configured &&
        _wifi_radio_on && WiFi.status() == WL_CONNECTED &&
        !deadlineReached(now, _wifi_interface->getPendingClientDeadline());
    _wifi_interface->resolvePendingClient(
        _wifi_interface->getPendingClientRequestId(), accept);
  }
  const bool associated = _wifi_radio_on && WiFi.status() == WL_CONNECTED;
  if (_wifi_setup_stage == WifiSetupStage::TESTING) {
    if (associated) {
      _wifi_attempt_active = false;
      _wifi_setup_stage = WifiSetupStage::TEST_OK;
      _wifi_setup_activity = now;
      if (!_api_wifi_setup) printConsole("WiFi test passed. Type 'wifi save' to store it.\r\n");
    } else if (_wifi_attempt_active &&
               elapsed(now, _wifi_attempt_started, WIFI_CONNECT_TIMEOUT_MS)) {
      _wifi_setup_stage = WifiSetupStage::FAILED;
      if (_api_wifi_setup) _api_wifi_result = WifiApiResult::FAILED;
      else printConsole("WiFi test failed; credentials were not saved.\r\n");
      cancelWifiSetup(true);
    }
    return;
  }

  // A passed candidate remains provisional until Save or Cancel.  Do not
  // reconnect the previously stored network if its test association drops.
  if (_wifi_setup_stage != WifiSetupStage::IDLE) return;

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
  if (_api_wifi_setup) return false;
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
  // Helper resynchronization sends cancel even when no wizard is active.
  // Do not disturb an already-associated network or its companion session.
  if (_wifi_setup_stage == WifiSetupStage::IDLE) return;
  scrubCandidate();
  _wifi_setup_stage = WifiSetupStage::IDLE;
  _api_wifi_setup = false;
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
  _api_wifi_setup = false;
  _wifi_setup_activity = 0;
  if (_config.mode == CompanionMode::WiFi) {
    _interfaces->selectExclusive(InterfaceType::WiFi);
    // The candidate association may have disappeared while awaiting Save.
    // Explicitly activate the newly persisted network, never a stale link.
    _wifi_retry_delay = WIFI_RETRY_INITIAL_MS;
    startWifiAttempt(_config.ssid, _config.password, false);
  } else {
    stopWifiRadio(false);
  }
  return true;
}

void ConnectionController::resetApiSession() {
  if (_api_wifi_setup) cancelWifiSetup(true);
  _api_wifi_result = WifiApiResult::NONE;
  if (_api_mode_pending) _api_mode_error = "cancelled";
  _api_mode_pending = _api_mode_reply_queued = false;
}

void ConnectionController::apiReplyQueued() {
  if (_api_mode_pending) _api_mode_reply_queued = true;
}

void ConnectionController::serviceApiMode() {
  if (!_api_mode_pending) return;
  // Controller.loop runs before the companion router observes its session
  // epoch. A fast reconnect can already look connected, so bind the deferred
  // switch to the session which requested it, not only the current link state.
  if (!_interfaces || _interfaces->sessionGeneration() != _api_mode_session ||
      !_interfaces->isInterfaceConnected(interfaceType(_config.mode))) {
    _api_mode_pending = _api_mode_reply_queued = false;
    _api_mode_error = "cancelled";
    return;
  }
  const uint32_t age = static_cast<uint32_t>(millis() - _api_mode_started);
  if (age >= 2000U || !mutationAllowed()) {
    _api_mode_error = age >= 2000U ? "timeout" : "readonly";
    _api_mode_pending = _api_mode_reply_queued = false;
    return;
  }
  if (!_api_mode_reply_queued || age < 100U || !_interfaces || _interfaces->hasPendingTx()) return;
  const CompanionMode target = _api_mode_target;
  _api_mode_pending = _api_mode_reply_queued = false;
  if (setMode(target)) _api_mode_error = "none";
  else _api_mode_error = _last_change_error == ConnectionChangeError::Apply ? "apply" : "storage";
}

const char* ConnectionController::wifiStageName() const {
  if (_wifi_setup_stage == WifiSetupStage::WAIT_SSID) return "ssid";
  if (_wifi_setup_stage == WifiSetupStage::WAIT_PASSWORD) return "password";
  if (_wifi_setup_stage == WifiSetupStage::READY) return "ready";
  if (_wifi_setup_stage == WifiSetupStage::TESTING) return "testing";
  if (_wifi_setup_stage == WifiSetupStage::TEST_OK) return "test_ok";
  if (_api_wifi_result == WifiApiResult::SAVED) return "saved";
  if (_api_wifi_result == WifiApiResult::CANCELLED) return "cancelled";
  if (_api_wifi_result == WifiApiResult::FAILED) return "failed";
  if (_api_wifi_result == WifiApiResult::TIMED_OUT) return "timeout";
  return "idle";
}

bool ConnectionController::handleCliCommand(const char* command, char* reply,
                                            size_t capacity, bool allow_mutation) {
  if (!command) return false;
  if (strcmp(command, "ui reply") == 0 || strncmp(command, "ui reply ", 9) == 0)
    return handleCliQuickReply(command, reply, capacity, allow_mutation);
  const bool connection = strcmp(command, "ui connection") == 0;
  const bool wifi = strcmp(command, "ui wifi") == 0 || strncmp(command, "ui wifi ", 8) == 0;
  const bool mode = strcmp(command, "ui mode") == 0 || strncmp(command, "ui mode ", 8) == 0;
  if (!connection && !wifi && !mode) return false;
  if (!reply || capacity == 0) return true;
  auto respond = [&](const char* text) { snprintf(reply, capacity, "%s", text); };
  // Reject before staging credentials or mode changes. The wire adds its own
  // optional three-byte prefix outside this 156-byte response contract.
  if (capacity < 157) { respond("ERR ui buffer"); return true; }
  size_t length = 0;
  while (length <= 156 && command[length]) {
    const uint8_t c = static_cast<uint8_t>(command[length]);
    if (c < 0x20 || c > 0x7e) { respond("ERR ui invalid"); return true; }
    ++length;
  }
  if (length > 156) { respond("ERR ui invalid"); return true; }
  if (connection) {
    const CompanionStatus current = status();
    snprintf(reply, capacity, "OK ui connection mode=%s client=%s caps=%u write=%u",
        modeToken(current.selected), current.clientConnected ? modeToken(current.connectedVia) : "none",
        static_cast<unsigned>(current.capabilities),
        allow_mutation && deviceApiWritesAllowed() ? 1U : 0U);
    return true;
  }
  if (strcmp(command, "ui wifi status") == 0) {
    const CompanionStatus current = status();
    snprintf(reply, capacity,
        "OK ui wifi state=%s supported=%u configured=%u associated=%u ip=%s",
        wifiStageName(), (capabilities() & COMPANION_CAP_WIFI) ? 1U : 0U,
        current.wifiConfigured ? 1U : 0U, current.wifiAssociated ? 1U : 0U,
        current.wifiLocalIp[0] ? current.wifiLocalIp : "none");
    return true;
  }
  if (strcmp(command, "ui mode status") == 0) {
    snprintf(reply, capacity, "OK ui mode pending=%s error=%s",
        _api_mode_pending ? modeToken(_api_mode_target) : "none", _api_mode_error);
    return true;
  }

  // Namespace adaptation only: do not duplicate the tested transactional
  // state machine, ownership, transport, timeout or response-drain policy.
  char api_command[158];
  char api_reply[256] = {};
  memcpy(api_command, "api", 3);
  memcpy(api_command + 3, command + 2, length - 1);  // Include terminating NUL.
  const bool handled = handleApiCommand(api_command, api_reply, sizeof(api_reply), allow_mutation);
  size_t reply_length = 0;
  while (reply_length < sizeof(api_reply) && api_reply[reply_length]) ++reply_length;
  if (!handled) respond("ERR ui invalid");
  else if (reply_length >= sizeof(api_reply) || reply_length > 157) respond("ERR ui buffer");
  else {
    const char* status_token = nullptr;
    const char* body = nullptr;
    if (strncmp(api_reply, "OK api ", 7) == 0) { status_token = "OK"; body = api_reply + 7; }
    else if (strncmp(api_reply, "ERR api ", 8) == 0) { status_token = "ERR"; body = api_reply + 8; }
    if (!body) respond("ERR ui invalid");
    else {
      const int written = snprintf(reply, capacity, "%s ui %s", status_token, body);
      if (written < 0 || written > 156 || static_cast<size_t>(written) >= capacity)
        respond("ERR ui buffer");
    }
  }
  secureZero(api_command, sizeof(api_command));
  secureZero(api_reply, sizeof(api_reply));
  return true;
}

bool ConnectionController::handleApiCommand(const char* command, char* reply,
                                            size_t capacity, bool allow_mutation) {
  if (!command) return false;
  const bool mode_command = strncmp(command, "api mode ", 9) == 0;
  if (!mode_command && strcmp(command, "api wifi") != 0 && strncmp(command, "api wifi ", 9) != 0)
    return false;
  if (!reply || capacity == 0) return true;
  auto respond = [&](const char* text) { snprintf(reply, capacity, "%s", text); };
  if (capacity < 256) { respond("ERR api buffer"); return true; }
  if (mode_command) {
    CompanionMode target;
    if (strcmp(command + 9, "ble") == 0) target = CompanionMode::BLE;
    else if (strcmp(command + 9, "usb") == 0) target = CompanionMode::USB;
    else if (strcmp(command + 9, "wifi") == 0) target = CompanionMode::WiFi;
    else { respond("ERR api invalid"); return true; }
    if (!_started || !modeAvailable(target)) respond("ERR api unsupported");
    else if (!allow_mutation || !mutationAllowed()) respond("ERR api readonly");
    else if (deviceApiBusy()) respond("ERR api busy");
    else if (target == CompanionMode::WiFi && !_config.wifi_configured) respond("ERR api unconfigured");
    else if (target == _config.mode) snprintf(reply, capacity, "OK api mode target=%s state=active", command + 9);
    else {
      _api_mode_target = target;
      _api_mode_pending = true;
      _api_mode_reply_queued = false;
      _api_mode_started = millis();
      _api_mode_session = _interfaces->sessionGeneration();
      _api_mode_error = "none";
      snprintf(reply, capacity, "OK api mode target=%s state=pending", command + 9);
    }
    return true;
  }
  if (strcmp(command, "api wifi status") == 0) {
    const CompanionStatus current = status();
    const char* stage = wifiStageName();
    snprintf(reply, capacity,
        "OK api wifi state=%s owner=%s supported=%u configured=%u associated=%u ip=%s ssid_set=%u password_set=%u mode_pending=%s last_mode_error=%s",
        stage, _api_wifi_setup ? "api" : _wifi_setup_stage != WifiSetupStage::IDLE ? "console" : "none",
        (capabilities() & COMPANION_CAP_WIFI) ? 1U : 0U, current.wifiConfigured ? 1U : 0U,
        current.wifiAssociated ? 1U : 0U, current.wifiLocalIp[0] ? current.wifiLocalIp : "none",
        _api_wifi_setup && _candidate_ssid_len ? 1U : 0U,
        _api_wifi_setup && (_wifi_setup_stage == WifiSetupStage::READY ||
            _wifi_setup_stage == WifiSetupStage::TESTING || _wifi_setup_stage == WifiSetupStage::TEST_OK) ? 1U : 0U,
        !_api_mode_pending ? "none" : _api_mode_target == CompanionMode::BLE ? "ble" :
            _api_mode_target == CompanionMode::USB ? "usb" : "wifi", _api_mode_error);
    return true;
  }
  if (!_started || !(capabilities() & COMPANION_CAP_WIFI)) {
    respond("ERR api unsupported");
    return true;
  }
  if (!allow_mutation || !mutationAllowed()) {
    respond("ERR api readonly");
    return true;
  }
#if defined(ESP32)
  // Testing candidate credentials disconnects Wi-Fi. Keep ownership on an
  // independent BLE/USB session so test-before-save and cancellation are real.
  if (_config.mode == CompanionMode::WiFi) {
    respond("ERR api transport");
    return true;
  }
  if (strcmp(command, "api wifi begin") == 0) {
    if (deviceApiBusy()) respond("ERR api busy");
    else {
      stopWifiRadio(false);
      scrubCandidate();
      _api_wifi_setup = true;
      _api_wifi_result = WifiApiResult::NONE;
      _wifi_setup_stage = WifiSetupStage::WAIT_SSID;
      _wifi_setup_activity = millis();
      respond("OK api wifi begin state=ssid");
    }
    return true;
  }
  if (!_api_wifi_setup) {
    respond(_wifi_setup_stage != WifiSetupStage::IDLE ? "ERR api busy" : "ERR api stale");
    return true;
  }
  if (strcmp(command, "api wifi cancel") == 0) {
    _api_wifi_result = WifiApiResult::CANCELLED;
    cancelWifiSetup(true);
    respond("OK api wifi cancel");
  } else if (strncmp(command, "api wifi ssid ", 14) == 0) {
    if (_wifi_setup_stage != WifiSetupStage::WAIT_SSID) respond("ERR api stale");
    else if (!decodeApiSecret(command + 14, _candidate_ssid, sizeof(_candidate_ssid),
                              1, WIFI_SSID_MAX, _candidate_ssid_len)) respond("ERR api invalid");
    else {
      _wifi_setup_stage = WifiSetupStage::WAIT_PASSWORD;
      _wifi_setup_activity = millis();
      respond("OK api wifi ssid state=password");
    }
  } else if (strncmp(command, "api wifi password ", 18) == 0) {
    if (_wifi_setup_stage != WifiSetupStage::WAIT_PASSWORD) respond("ERR api stale");
    else {
      const bool open = strcmp(command + 18, "-") == 0;
      bool valid = open;
      if (open) { secureZero(_candidate_password, sizeof(_candidate_password)); _candidate_password_len = 0; }
      else valid = decodeApiSecret(command + 18, _candidate_password, sizeof(_candidate_password),
                                   8, WIFI_PASSWORD_MAX, _candidate_password_len);
      if (valid && _candidate_password_len == 64) {
        for (size_t i = 0; i < 64; ++i) {
          if (hexNibble(_candidate_password[i]) < 0) { valid = false; break; }
        }
        if (!valid) { secureZero(_candidate_password, sizeof(_candidate_password)); _candidate_password_len = 0; }
      }
      if (!valid) respond("ERR api invalid");
      else {
        _wifi_setup_stage = WifiSetupStage::READY;
        _wifi_setup_activity = millis();
        respond("OK api wifi password state=ready");
      }
    }
  } else if (strcmp(command, "api wifi test") == 0) {
    if (_wifi_setup_stage != WifiSetupStage::READY) respond("ERR api stale");
    else {
      _wifi_setup_activity = millis();
      startWifiAttempt(_candidate_ssid, _candidate_password, true);
      respond("OK api wifi test state=testing");
    }
  } else if (strcmp(command, "api wifi save") == 0) {
    if (_wifi_setup_stage != WifiSetupStage::TEST_OK || WiFi.status() != WL_CONNECTED)
      respond("ERR api stale");
    else if (!saveTestedWifi()) respond("ERR api storage");
    else { _api_wifi_result = WifiApiResult::SAVED; respond("OK api wifi save"); }
  } else respond("ERR api invalid");
#else
  respond("ERR api unsupported");
#endif
  return true;
}

bool ConnectionController::forgetWifi() {
  // A failed local cleanup may be retried without reboot. External quarantine
  // and CLI ownership still forbid every persistent mutation.
  if ((_hooks.isCliRescue && _hooks.isCliRescue()) ||
      (_hooks.isStorageQuarantined && _hooks.isStorageQuarantined())) return false;
  const bool retry_recovery = _config_storage_error;
  _config_storage_error = false;
  Config clean;
  clean.mode = (capabilities() & COMPANION_CAP_BLE) ? CompanionMode::BLE
      : CompanionMode::USB;

  // Forget is deliberately monotonic rather than rollback-capable: no old
  // credential-bearing .bak/.tmp may become eligible recovery data later.
  if (_hooks.resetLocalSession) _hooks.resetLocalSession();
  stopWifiRadio(true);
  scrubCandidate();

  const bool saved = persistCleanConfig(clean);
  _config = clean;
  _wifi_setup_stage = WifiSetupStage::IDLE;
  _interfaces->selectExclusive(interfaceType(clean.mode));
  _config_storage_error = !saved;
  if (!saved) _interfaces->disable();
  else if (retry_recovery) _interfaces->enable();
  return saved;
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
      "Commands: info | status | mode ble | mode usb | mode wifi | wifi setup | "
      "wifi status | wifi save | wifi cancel | wifi forget | reply get N | reply set N HEX | help\r\n");
  // Preserve the legacy help grammar; new helpers negotiate this extension.
  if (_hooks.handleDeviceSettings) printConsole("Settings protocol: 1\r\n");
  printConsole("Credential input is not echoed. WiFi is saved only after a passed test.\r\n");
  printConsole("Read-only diagnostics: storage status; phase=last failure this boot; E:S:V=exists:size:valid, size=-1 if unreadable; marker valid means readable presence, even empty.\r\n");
  printConsole("storage usage | storage legacy: rc:size; -2=absent; -1=unknown.\r\n");
}

void ConnectionController::handleDeviceSettingsCommand(const char* line) {
  const bool service_read_or_stop = strcmp(line, "settings adc service") == 0 ||
      strcmp(line, "settings adc manual") == 0 ||
      strcmp(line, "settings adc service stop") == 0;
  if (_wifi_setup_stage != WifiSetupStage::IDLE && !service_read_or_stop) {
    printConsole("ERR settings busy\r\n");
    return;
  }
  if (!_hooks.handleDeviceSettings) {
    printConsole("ERR settings unsupported\r\n");
    return;
  }
  secureZero(_settings_response, sizeof(_settings_response));
  const bool handled = _hooks.handleDeviceSettings(
      line, _settings_response, sizeof(_settings_response), mutationAllowed());
  const char* end = static_cast<const char*>(
      memchr(_settings_response, 0, sizeof(_settings_response)));
  bool valid = handled && end &&
      (strncmp(_settings_response, "OK settings ", 12) == 0 ||
       strncmp(_settings_response, "ERR settings ", 13) == 0);
  if (valid) {
    for (const char* c = _settings_response; c != end; ++c) {
      if (*c < 0x20 || *c > 0x7e) { valid = false; break; }
    }
  }
  if (!handled) printConsole("ERR settings unsupported\r\n");
  else if (!valid) printConsole("ERR settings internal\r\n");
  else {
    printConsole(_settings_response);
    printConsole("\r\n");
  }
  secureZero(_settings_response, sizeof(_settings_response));
}

bool ConnectionController::handleCliQuickReply(const char* command, char* reply,
                                                size_t capacity, bool allow_mutation) {
  if (!reply || !capacity) return true;
  auto respond = [&](const char* text) { snprintf(reply, capacity, "%s", text); };
  if (capacity < 157) { respond("ERR ui buffer"); return true; }
  size_t length = 0;
  while (length <= 156 && command[length]) {
    const uint8_t c = static_cast<uint8_t>(command[length++]);
    if (c < 0x20 || c > 0x7e) { respond("ERR ui invalid"); return true; }
  }
  if (length > 156) { respond("ERR ui invalid"); return true; }
  const bool get = strncmp(command, "ui reply get ", 13) == 0;
  const bool set = strncmp(command, "ui reply set ", 13) == 0;
  if ((!get && !set) || length < 14) { respond("ERR ui invalid"); return true; }
  const char* value = command + 13;
  if (value[0] < '1' || value[0] > '9' ||
      (get ? value[1] != 0 : value[1] != ' ')) {
    respond("ERR ui invalid"); return true;
  }
  if (!_hooks.getQuickReply || !_hooks.setQuickReply) {
    respond("ERR ui unsupported"); return true;
  }
  const uint8_t slot = static_cast<uint8_t>(value[0] - '1');
  if (get) {
    const char* text = _hooks.getQuickReply(slot);
    if (!smartui::validQuickReply(text)) { respond("ERR ui internal"); return true; }
    size_t used = static_cast<size_t>(snprintf(reply, capacity, "OK ui reply slot=%u hex=", slot + 1));
    static const char digits[] = "0123456789abcdef";
    if (!text[0]) reply[used++] = '-';
    for (size_t i = 0; text[i]; ++i) {
      const uint8_t byte = static_cast<uint8_t>(text[i]);
      reply[used++] = digits[byte >> 4];
      reply[used++] = digits[byte & 15];
    }
    reply[used] = 0;
    return true;
  }
  if (!allow_mutation || !deviceApiWritesAllowed()) { respond("ERR ui readonly"); return true; }
  if (deviceApiBusy()) { respond("ERR ui busy"); return true; }
  const char* hex = value + 2;
  const size_t size = strcmp(hex, "-") == 0 ? 0 : strlen(hex);
  char text[SMARTUI_QUICK_REPLY_MAX_BYTES + 1] = {};
  bool valid = size <= SMARTUI_QUICK_REPLY_MAX_BYTES * 2 && size % 2 == 0 && hex[0];
  for (size_t i = 0; valid && i < size; i += 2) {
    uint8_t byte = 0;
    for (unsigned half = 0; half < 2; ++half) {
      const char c = hex[i + half];
      if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) { valid = false; break; }
      byte = static_cast<uint8_t>((byte << 4) | (c <= '9' ? c - '0' : c - 'a' + 10));
    }
    if (!byte) valid = false;
    text[i / 2] = static_cast<char>(byte);
  }
  valid = valid && smartui::validQuickReply(text);
  if (!valid) respond("ERR ui invalid");
  else if (!_hooks.setQuickReply(slot, text)) respond("ERR ui storage");
  else snprintf(reply, capacity, "OK ui reply_saved slot=%u", slot + 1);
  secureZero(text, sizeof(text));
  return true;
}

void ConnectionController::handleQuickReplyCommand(const char* line) {
  const bool get = strncmp(line, "reply get ", 10) == 0;
  const bool set = strncmp(line, "reply set ", 10) == 0;
  const char* value = line + 10;
  if ((!get && !set) || value[0] < '1' || value[0] > '9' ||
      (get ? value[1] != 0 : value[1] != ' ')) {
    printConsole("Invalid reply command.\r\n");
    return;
  }
  const uint8_t slot = static_cast<uint8_t>(value[0] - '1');
  if (!_hooks.getQuickReply || !_hooks.setQuickReply) {
    printConsole("Quick replies unavailable.\r\n");
    return;
  }
  if (get) {
    const char* text = _hooks.getQuickReply(slot);
    if (!smartui::validQuickReply(text)) text = "";
    char response[160];
    size_t used = static_cast<size_t>(snprintf(response, sizeof(response), "Reply=%u hex=", slot + 1));
    static const char digits[] = "0123456789abcdef";
    if (!text[0]) response[used++] = '-';
    for (size_t i = 0; text[i]; ++i) {
      const uint8_t byte = static_cast<uint8_t>(text[i]);
      response[used++] = digits[byte >> 4];
      response[used++] = digits[byte & 15];
    }
    response[used++] = '\r'; response[used++] = '\n'; response[used] = 0;
    printConsole(response);
    return;
  }
  if (!mutationAllowed() || _wifi_setup_stage != WifiSetupStage::IDLE) {
    printConsole("Quick reply save failed.\r\n");
    return;
  }
  const char* hex = value + 2;
  const size_t size = strcmp(hex, "-") == 0 ? 0 : strlen(hex);
  char text[SMARTUI_QUICK_REPLY_MAX_BYTES + 1] = {};
  bool valid = size <= SMARTUI_QUICK_REPLY_MAX_BYTES * 2 && size % 2 == 0 && hex[0];
  for (size_t i = 0; valid && i < size; i += 2) {
    uint8_t byte = 0;
    for (unsigned half = 0; half < 2; ++half) {
      const char c = hex[i + half];
      if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) { valid = false; break; }
      byte = static_cast<uint8_t>((byte << 4) | (c <= '9' ? c - '0' : c - 'a' + 10));
    }
    if (!byte) valid = false;
    text[i / 2] = static_cast<char>(byte);
  }
  valid = valid && smartui::validQuickReply(text);
  if (!valid) printConsole("Invalid quick reply.\r\n");
  else if (!_hooks.setQuickReply(slot, text)) printConsole("Quick reply save failed.\r\n");
  else {
    char response[32];
    snprintf(response, sizeof(response), "Reply %u saved.\r\n", slot + 1);
    printConsole(response);
  }
  secureZero(text, sizeof(text));
}

void ConnectionController::printStatus() {
  const CompanionStatus current = status();
  char line[256];
  snprintf(line, sizeof(line),
      "Mode=%s companion=%s via=%s USB-service=%s WiFi-config=%s link=%s IP=%s approval=%s storage=%s\r\n",
      modeName(current.selected), current.clientConnected ? "connected" : "idle",
      current.clientConnected ? modeName(current.connectedVia) : "none",
      current.usbConsoleEnabled ? "on" : "off",
      current.wifiConfigured ? "yes" : "no",
      current.wifiAssociated ? "associated" : "down",
      current.wifiLocalIp[0] ? current.wifiLocalIp : "none",
      current.wifiApprovalPending ? "pending" : "none",
      current.storageRecoveryRequired ? "recovery-required" : "ok");
  printConsole(line);
}

void ConnectionController::printInfo() {
  const uint8_t caps = capabilities();
  const char* board = _hooks.getBoardName ? _hooks.getBoardName() : nullptr;
  char line[448];
  snprintf(line, sizeof(line),
      "SmartUI=%s core=%s build=%s upstream=%s capabilities=%s%s%s board=%.96s\r\n",
      SMARTUI_VERSION, SMARTUI_CORE_VERSION, SMARTUI_BUILD_SHA, SMARTUI_UPSTREAM_SHA,
      (caps & COMPANION_CAP_BLE) ? "BLE" : "",
      (caps & COMPANION_CAP_USB) ? ((caps & COMPANION_CAP_BLE) ? ",USB" : "USB") : "",
      (caps & COMPANION_CAP_WIFI) ? ((caps & (COMPANION_CAP_BLE | COMPANION_CAP_USB))
          ? ",WiFi" : "WiFi") : "",
      board && board[0] ? board : "unknown");
  printConsole(line);
}

void ConnectionController::printStorageStatus() {
  // Do not call loadConfig/persistCleanConfig here: even a diagnostic query
  // during quarantine must not retry writes, clear the failure latch, or reset
  // a companion session. Only these four fixed paths may be inspected.
  FILESYSTEM* fs = _store ? _store->getPrimaryFS() : nullptr;
  const char* paths[] = {CONFIG_PATH, CONFIG_TEMP_PATH, CONFIG_BACKUP_PATH, CONFIG_FORGET_PATH};
  char metadata[4][32];
  for (unsigned i = 0; i < 4; ++i) {
    if (!fs || !fs->exists(paths[i])) {
      strcpy(metadata[i], "0:0:0");
      continue;
    }
    File file = openConfigRead(fs, paths[i]);
    if (!file) {
      strcpy(metadata[i], "1:-1:0");
      continue;
    }
    const unsigned long size = static_cast<unsigned long>(file.size());
    file.close();
    Config checked;
    // A forget barrier is deliberately valid even after an empty/partial write.
    // Unlike the three records, its contents are never read or interpreted.
    const bool valid = i == 3 || readConfigFile(paths[i], checked);
    secureZero(&checked, sizeof(checked));
    snprintf(metadata[i], sizeof(metadata[i]), "1:%lu:%u", size, valid ? 1U : 0U);
  }
  const bool quarantined = _hooks.isStorageQuarantined && _hooks.isStorageQuarantined();
  char line[320];
  snprintf(line, sizeof(line),
      "Storage v=1 phase=%s local=%u global=%u fs=%u primary=%s temp=%s backup=%s marker=%s\r\n",
      storagePhaseName(_storage_phase), _config_storage_error ? 1U : 0U,
      quarantined ? 1U : 0U, fs ? 1U : 0U,
      metadata[0], metadata[1], metadata[2], metadata[3]);
  printConsole(line);
}

void ConnectionController::printStorageUsage() {
  FILESYSTEM* fs = _store ? _store->getPrimaryFS() : nullptr;
  // main.cpp halts on mount failure before begin(), as required by all existing
  // controller file operations. No runtime unmount is allowed during queries.
  const bool mounted = _started && fs;
  bool inspect_files = fs && mounted;
  const char* result = inspect_files ? "unsupported" : "unavailable";
  uint32_t total = 0, block_size = 0;
  long used = -1;
  long heap_free = -1;
  int error = 0;
  const char* paths[] = {CONFIG_FORGET_PATH, "/prefs.json", "/prefs.json.tmp",
      "/prefs.json.bak", "/new_prefs", "/_main.id", "/contacts3"};
  char metadata[7][24];
  for (auto& value : metadata) strcpy(value, "-1:-1");
#if defined(NRF52_PLATFORM)
  // This core uses heap_3/malloc, not FreeRTOS heap_4: minimum-ever free is
  // unavailable. Free bytes do not prove a sufficiently large contiguous block.
  heap_free = dbgHeapFree();
  if (inspect_files) {
    // This is a read-only traversal: never mount, repair, format, sync, or call
    // File methods while holding the non-recursive filesystem lock.
    fs->_lockFS();
    lfs_t* lfs = fs->_getFS();
    if (lfs && lfs->cfg) {
      total = lfs->cfg->block_count;
      block_size = lfs->cfg->block_size;
      if (total && total <= STORAGE_DIAG_MAX_BLOCKS && block_size) {
        StorageBlockCount count;
        count.total = total;
        error = lfs_traverse(lfs, countStorageBlock, &count);
        result = error == 0 ? "ok" : "traverse-error";
        if (!error) used = static_cast<long>(count.used);
        // Direct stat retains exact errno; exists() would hide I/O/corruption as
        // an absent file. Read metadata only, never open or read file contents.
        for (unsigned i = 0; i < 7; ++i) readStorageStat(lfs, paths[i], metadata[i]);
      } else {
        result = "geometry";
        inspect_files = false;
      }
    } else {
      result = "unavailable";
      inspect_files = false;
    }
    fs->_unlockFS();
  }
#else
  // Generic adapters do not expose stat errno or filesystem geometry. Preserve
  // that uncertainty instead of claiming exists(false) means LFS_ERR_NOENT.
  if (inspect_files) for (unsigned i = 0; i < 7; ++i) {
    if (fs->exists(paths[i])) {
      File file = openConfigRead(fs, paths[i]);
      if (file) {
        snprintf(metadata[i], sizeof(metadata[i]), "0:%lu",
            static_cast<unsigned long>(static_cast<uint32_t>(file.size())));
        file.close();
      }
    }
  }
#endif
  char line[512];
  snprintf(line, sizeof(line),
      "StorageUsage v=1 source=primary mounted=%u result=%s block_size=%lu total_blocks=%lu used_blocks=%ld error=%d heap_free=%ld heap_min=-1 marker=%s prefs=%s prefs_tmp=%s prefs_bak=%s legacy=%s identity=%s contacts=%s\r\n",
      mounted ? 1U : 0U, result, static_cast<unsigned long>(block_size),
      static_cast<unsigned long>(total), used, error, heap_free,
      metadata[0], metadata[1], metadata[2], metadata[3], metadata[4],
      metadata[5], metadata[6]);
  printConsole(line);
}

void ConnectionController::printStorageLegacy() {
  FILESYSTEM* fs = _store ? _store->getPrimaryFS() : nullptr;
  const bool mounted = _started && fs;
  const char* result = mounted ? "unsupported" : "unavailable";
  // Fixed metadata allowlist only. Never enumerate names or read contents.
  // Migration may retain primary siblings and failed/unequal bulk copies.
  const char* paths[] = {"/contacts3", "/contacts3.tmp", "/contacts3.bak",
      "/channels2", "/channels2.tmp", "/channels2.bak",
      "/_main.id.tmp", "/_main.id.bak", "/adv_blobs"};
  char metadata[9][24];
  for (auto& value : metadata) strcpy(value, "-1:-1");
#if defined(NRF52_PLATFORM)
  if (mounted) {
    fs->_lockFS();
    lfs_t* lfs = fs->_getFS();
    if (lfs && lfs->cfg) {
      if (lfs->cfg->block_count && lfs->cfg->block_count <= STORAGE_DIAG_MAX_BLOCKS &&
          lfs->cfg->block_size) {
        result = "ok";
        for (unsigned i = 0; i < 9; ++i) readStorageStat(lfs, paths[i], metadata[i]);
      } else result = "geometry";
    } else result = "unavailable";
    fs->_unlockFS();
  }
#else
  if (mounted) for (unsigned i = 0; i < 9; ++i) {
    if (fs->exists(paths[i])) {
      File file = openConfigRead(fs, paths[i]);
      if (file) {
        snprintf(metadata[i], sizeof(metadata[i]), "0:%lu",
            static_cast<unsigned long>(static_cast<uint32_t>(file.size())));
        file.close();
      }
    }
  }
#endif
  char line[384];
  snprintf(line, sizeof(line),
      "StorageLegacy v=1 source=primary mounted=%u result=%s contacts=%s contacts_tmp=%s contacts_bak=%s channels=%s channels_tmp=%s channels_bak=%s identity_tmp=%s identity_bak=%s blobs=%s\r\n",
      mounted ? 1U : 0U, result, metadata[0], metadata[1], metadata[2],
      metadata[3], metadata[4], metadata[5], metadata[6], metadata[7], metadata[8]);
  printConsole(line);
}

void ConnectionController::handleConsoleLine(char* raw_line) {
  // These fail-safe commands never become an SSID/password or require writes.
  if (strcmp(raw_line, "settings adc service") == 0 ||
      strcmp(raw_line, "settings adc manual") == 0 ||
      strcmp(raw_line, "settings adc service stop") == 0) {
    handleDeviceSettingsCommand(raw_line);
    return;
  }
  if (_api_wifi_setup) {
    printConsole("WiFi setup is owned by the companion API; use that client to finish or cancel.\r\n");
    return;
  }
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
  if (strcmp(line, "settings") == 0 || strncmp(line, "settings ", 9) == 0) {
    // The backend allows capability/current-value reads during recovery, but
    // receives an explicit false for every mutation. Keep its machine grammar
    // distinct from the human-readable legacy connection recovery response.
    handleDeviceSettingsCommand(line);
    return;
  }
  const bool quarantined = _hooks.isStorageQuarantined &&
      _hooks.isStorageQuarantined();
  const bool read_only_command = strcmp(line, "status") == 0 ||
      strcmp(line, "wifi status") == 0 || strcmp(line, "info") == 0 ||
      strcmp(line, "help") == 0 || strcmp(line, "storage status") == 0 ||
      strcmp(line, "storage usage") == 0 || strcmp(line, "storage legacy") == 0;
  const bool reply_read = strncmp(line, "reply get ", 10) == 0;
  if ((quarantined || _config_storage_error) && !read_only_command && !reply_read &&
      (quarantined || strcmp(line, "wifi forget") != 0)) {
    printConsole("Connection settings are read-only during storage recovery.\r\n");
    return;
  }
  if (strcmp(line, "status") == 0 || strcmp(line, "wifi status") == 0) {
    printStatus();
  } else if (strcmp(line, "storage status") == 0) {
    printStorageStatus();
  } else if (strcmp(line, "storage usage") == 0) {
    printStorageUsage();
  } else if (strcmp(line, "storage legacy") == 0) {
    printStorageLegacy();
  } else if (strcmp(line, "info") == 0) {
    printInfo();
  } else if (strcmp(line, "help") == 0) {
    printHelp();
  } else if (strncmp(line, "reply get ", 10) == 0 || strncmp(line, "reply set ", 10) == 0) {
    handleQuickReplyCommand(line);
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
                                "WiFi cleared in RAM; persistent cleanup failed. Do not assume credentials were erased. Retry 'wifi forget'.\r\n");
  } else {
    printConsole("Unknown command. Type 'help'.\r\n");
  }
}

bool ConnectionController::consoleActive(uint32_t now) const {
  return consoleEnabled() && (_wifi_setup_stage != WifiSetupStage::IDLE ||
      smartui::serialServiceWindow(_console_input_seen, now, _console_last_input));
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
    if (_config_storage_error) {
      printConsole("Connection storage recovery failed; settings are read-only and transports are disabled.\r\n");
    }
  }

  // A settings snapshot can occupy nearly the entire queue. Do not consume a
  // second command until the previous response has drained, including when
  // the host has stopped reading. This also prevents accidental lost ACKs.
  if (_console_tx_len != 0) {
    serviceConsoleTx();
    return;
  }

  uint8_t budget = CONSOLE_BYTES_PER_LOOP;
  while (budget-- > 0 && _console->available() > 0) {
    const int value = _console->read();
    if (value < 0) break;
    _console_input_seen = true;
    _console_last_input = millis();
    if (_wifi_setup_stage != WifiSetupStage::IDLE && !_api_wifi_setup) {
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
      if (_console_tx_len != 0) break;
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
      _api_wifi_setup = false;
      _api_wifi_result = WifiApiResult::CANCELLED;
      stopWifiRadio(false);
    }
    _quarantine_latched = true;
  }
  serviceWifi();
  serviceApiMode();
  serviceConsole();
}

#endif  // SMARTUI_CONNECTION_SELECTOR
