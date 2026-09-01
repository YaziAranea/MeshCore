#include <Arduino.h>
#include "DataStore.h"
#include <helpers/AdvertDataHelpers.h>
#include <helpers/StorageTransaction.h>

#if defined(EXTRAFS) || defined(QSPIFLASH)
  #define MAX_BLOBRECS 100
#else
  #define MAX_BLOBRECS 20
#endif

DataStore::DataStore(FILESYSTEM& fs, mesh::RTCClock& clock) : _fs(&fs), _fsExtra(nullptr), _clock(&clock),
#if defined(NRF52_PLATFORM) || defined(STM32_PLATFORM)
    identity_store(fs, "")
#elif defined(RP2040_PLATFORM)
    identity_store(fs, "/identity")
#else
    identity_store(fs, "/identity")
#endif
{
}

#if defined(EXTRAFS) || defined(QSPIFLASH)
DataStore::DataStore(FILESYSTEM& fs, FILESYSTEM& fsExtra, mesh::RTCClock& clock) : _fs(&fs), _fsExtra(&fsExtra), _clock(&clock),
#if defined(NRF52_PLATFORM) || defined(STM32_PLATFORM)
    identity_store(fs, "")
#elif defined(RP2040_PLATFORM)
    identity_store(fs, "/identity")
#else
    identity_store(fs, "/identity")
#endif
{
}
#endif

static File openWrite(FILESYSTEM* fs, const char* filename) {
#if defined(NRF52_PLATFORM) || defined(STM32_PLATFORM)
  fs->remove(filename);
  return fs->open(filename, FILE_O_WRITE);
#elif defined(RP2040_PLATFORM)
  return fs->open(filename, "w");
#else
  return fs->open(filename, "w", true);
#endif
}

#if defined(NRF52_PLATFORM) || defined(STM32_PLATFORM)
  static uint32_t _ContactsChannelsTotalBlocks = 0;
#endif

void DataStore::begin() {
#if defined(RP2040_PLATFORM)
  identity_store.begin();
#endif

#if defined(NRF52_PLATFORM) || defined(STM32_PLATFORM)
  _ContactsChannelsTotalBlocks = _getContactsChannelsFS()->_getFS()->cfg->block_count;
  #if defined(EXTRAFS) || defined(QSPIFLASH)
  migrateToSecondaryFS();
  #endif
  checkAdvBlobFile();
#else
  // init 'blob store' support
  _fs->mkdir("/bl");
#endif
}

#if defined(ESP32)
  #include <SPIFFS.h>
  #include <nvs_flash.h>
#elif defined(RP2040_PLATFORM)
  #include <LittleFS.h>
#elif defined(NRF52_PLATFORM) || defined(STM32_PLATFORM)
  #if defined(QSPIFLASH)
    #include <CustomLFS_QSPIFlash.h>
  #elif defined(EXTRAFS)
    #include <CustomLFS.h>
  #else 
    #include <InternalFileSystem.h>
  #endif
#endif

#if defined(NRF52_PLATFORM) || defined(STM32_PLATFORM)
int _countLfsBlock(void *p, lfs_block_t block){
      if (block > _ContactsChannelsTotalBlocks) {
        MESH_DEBUG_PRINTLN("ERROR: Block %d exceeds filesystem bounds - CORRUPTION DETECTED!", block);
        return LFS_ERR_CORRUPT;  // return error to abort lfs_traverse() gracefully
    }
  lfs_size_t *size = (lfs_size_t*) p;
  *size += 1;
    return 0;
}

lfs_ssize_t _getLfsUsedBlockCount(FILESYSTEM* fs) {
  lfs_size_t size = 0;
  int err = lfs_traverse(fs->_getFS(), _countLfsBlock, &size);
  if (err) {
    MESH_DEBUG_PRINTLN("ERROR: lfs_traverse() error: %d", err);
    return 0;
  }
  return size;
}
#endif

uint32_t DataStore::getStorageUsedKb() const {
#if defined(ESP32)
  return SPIFFS.usedBytes() / 1024;
#elif defined(RP2040_PLATFORM)
  FSInfo info;
  info.usedBytes = 0;
  _fs->info(info);
  return info.usedBytes / 1024;
#elif defined(NRF52_PLATFORM) || defined(STM32_PLATFORM)
  const lfs_config* config = _getContactsChannelsFS()->_getFS()->cfg;
  int usedBlockCount = _getLfsUsedBlockCount(_getContactsChannelsFS());
  int usedBytes = config->block_size * usedBlockCount;
  return usedBytes / 1024;
#else
  return 0;
#endif
}

uint32_t DataStore::getStorageTotalKb() const {
#if defined(ESP32)
  return SPIFFS.totalBytes() / 1024;
#elif defined(RP2040_PLATFORM)
  FSInfo info;
  info.totalBytes = 0;
  _fs->info(info);
  return info.totalBytes / 1024;
#elif defined(NRF52_PLATFORM) || defined(STM32_PLATFORM)
  const lfs_config* config = _getContactsChannelsFS()->_getFS()->cfg;
  int totalBytes = config->block_size * config->block_count;
  return totalBytes / 1024;
#else
  return 0;
#endif
}

File DataStore::openRead(const char* filename) {
#if defined(NRF52_PLATFORM) || defined(STM32_PLATFORM)
  return _fs->open(filename, FILE_O_READ);
#elif defined(RP2040_PLATFORM)
  return _fs->open(filename, "r");
#else
  return _fs->open(filename, "r", false);
#endif
}

File DataStore::openRead(FILESYSTEM* fs, const char* filename) {
#if defined(NRF52_PLATFORM) || defined(STM32_PLATFORM)
  return fs->open(filename, FILE_O_READ);
#elif defined(RP2040_PLATFORM)
  return fs->open(filename, "r");
#else
  return fs->open(filename, "r", false);
#endif
}

bool DataStore::removeFile(const char* filename) {
  return _fs->remove(filename);
}

bool DataStore::removeFile(FILESYSTEM* fs, const char* filename) {
  return fs->remove(filename);
}

bool DataStore::formatFileSystem() {
#if defined(NRF52_PLATFORM) || defined(STM32_PLATFORM)
  if (_fsExtra == nullptr) {
    return _fs->format();
  } else {
    return _fs->format() && _fsExtra->format();
  }
#elif defined(RP2040_PLATFORM)
  return LittleFS.format();
#elif defined(ESP32)
  bool fs_success = ((fs::SPIFFSFS *)_fs)->format();
  esp_err_t nvs_err = nvs_flash_erase(); // no need to reinit, will be done by reboot
  return fs_success && (nvs_err == ESP_OK);
#else
  #error "need to implement format()"
#endif
}

bool DataStore::loadMainIdentity(mesh::LocalIdentity &identity) {
  return loadMainIdentityStatus(identity) == IdentityLoadStatus::LOADED;
}

IdentityLoadStatus DataStore::loadMainIdentityStatus(mesh::LocalIdentity &identity) {
  return identity_store.loadWithStatus("_main", identity);
}

bool DataStore::saveMainIdentity(const mesh::LocalIdentity &identity) {
  return identity_store.save("_main", identity);
}

namespace {

struct FileDigest {
  uint32_t size = 0;
  uint32_t crc32 = 0;
};

static bool makeSiblingPath(const char* filename, const char* suffix,
                            char* dest, size_t dest_size) {
  const int n = snprintf(dest, dest_size, "%s%s", filename, suffix);
  return n > 0 && (size_t)n < dest_size;
}

// Only the scratch file is removed before opening.  The currently committed
// generation is never truncated in place.
static bool prepareScratch(FILESYSTEM* fs, const char* filename) {
  return !fs->exists(filename) || fs->remove(filename);
}

static File openScratch(FILESYSTEM* fs, const char* filename) {
#if defined(NRF52_PLATFORM) || defined(STM32_PLATFORM)
  return fs->open(filename, FILE_O_WRITE);
#elif defined(RP2040_PLATFORM)
  return fs->open(filename, "w");
#else
  return fs->open(filename, "w", true);
#endif
}

static File openStorageRead(FILESYSTEM* fs, const char* filename) {
#if defined(NRF52_PLATFORM) || defined(STM32_PLATFORM)
  return fs->open(filename, FILE_O_READ);
#elif defined(RP2040_PLATFORM)
  return fs->open(filename, "r");
#else
  return fs->open(filename, "r", false);
#endif
}

static bool digestFile(FILESYSTEM* fs, const char* filename, FileDigest& digest) {
  if (!fs->exists(filename)) return false;
  File file = openStorageRead(fs, filename);
  if (!file) return false;

  mesh::storage::Crc32 crc;
  uint8_t buffer[64];
  uint32_t total = 0;
  bool success = true;
  while (true) {
    const int n = file.read(buffer, sizeof(buffer));
    if (n < 0) {
      success = false;
      break;
    }
    if (n == 0) break;
    crc.update(buffer, (size_t)n);
    total += (uint32_t)n;
  }
  const uint32_t reported_size = (uint32_t)file.size();
  file.close();
  if (!success || total != reported_size) return false;
  digest.size = total;
  digest.crc32 = crc.value();
  return true;
}

static bool filesMatch(FILESYSTEM* first_fs, const char* first,
                       FILESYSTEM* second_fs, const char* second) {
  FileDigest a;
  FileDigest b;
  return digestFile(first_fs, first, a) && digestFile(second_fs, second, b) &&
         a.size == b.size && a.crc32 == b.crc32;
}

// Publish an already-written and validated .tmp generation.  The previous
// generation remains as .bak, so every interruption point leaves at least one
// complete candidate for the next boot.
static bool commitScratch(FILESYSTEM* fs, const char* target,
                          const char* scratch, const char* backup,
                          bool target_valid = true) {
  const bool had_target = fs->exists(target);
  bool rotated_target = false;
  if (had_target && target_valid) {
    if (fs->exists(backup) && !fs->remove(backup)) return false;
    if (!fs->rename(target, backup)) return false;
    rotated_target = true;
  } else if (had_target) {
    // Never rotate a known-bad primary over the last good backup.  Remove the
    // corrupt generation and leave .bak intact until the new file is live.
    if (!fs->remove(target)) return false;
  }

  if (fs->rename(scratch, target)) return true;

  // Best-effort rollback.  A failure still leaves the complete backup and
  // scratch files for recovery on the next boot.
  if (rotated_target && !fs->exists(target) && fs->exists(backup)) {
    fs->rename(backup, target);
  }
  return false;
}

static bool prefsFileValid(FILESYSTEM* fs, const char* filename,
                           const NodePrefs& defaults) {
  if (!fs->exists(filename)) return false;
  File file = openStorageRead(fs, filename);
  if (!file) return false;
  NodePrefs candidate(defaults);
  const bool valid = candidate.loadSerial(file);
  file.close();
  return valid;
}

static bool fixedRecordFileValid(FILESYSTEM* fs, const char* filename,
                                 uint32_t record_size) {
  if (!fs->exists(filename) || record_size == 0) return false;
  FileDigest digest;
  return digestFile(fs, filename, digest) && (digest.size % record_size) == 0;
}

static bool encodedPathLenValid(uint8_t path_len) {
  if (path_len == OUT_PATH_UNKNOWN) return true;
  const uint8_t hash_count = path_len & 63;
  const uint8_t hash_size = (path_len >> 6) + 1;
  return hash_size != 4 && (uint16_t)hash_count * hash_size <= MAX_PATH_SIZE;
}

static bool contactRecordFileValid(FILESYSTEM* fs, const char* filename) {
  static const uint32_t RECORD_SIZE = 152;
  if (!fixedRecordFileValid(fs, filename, RECORD_SIZE)) return false;
  File file = openStorageRead(fs, filename);
  if (!file) return false;
  uint8_t record[RECORD_SIZE];
  bool valid = true;
  while (file.available() > 0) {
    if (file.read(record, sizeof(record)) != (int)sizeof(record)) {
      valid = false;
      break;
    }
    // Layout: pubkey[32], name[32], type, flags, reserved,
    // sync_since[4], out_path_len, ...
    const bool terminated_name = memchr(record + 32, 0, 32) != nullptr;
    const uint8_t type = record[64];
    const uint8_t path_len = record[71];
    if (!terminated_name || type < ADV_TYPE_CHAT || type > ADV_TYPE_SENSOR ||
        !encodedPathLenValid(path_len)) {
      valid = false;
      break;
    }
  }
  file.close();
  return valid;
}

static bool channelRecordFileValid(FILESYSTEM* fs, const char* filename) {
  static const uint32_t RECORD_SIZE = 68;
  if (!fixedRecordFileValid(fs, filename, RECORD_SIZE)) return false;
  File file = openStorageRead(fs, filename);
  if (!file) return false;
  uint8_t record[RECORD_SIZE];
  bool valid = true;
  while (file.available() > 0) {
    if (file.read(record, sizeof(record)) != (int)sizeof(record) ||
        memchr(record + 4, 0, 32) == nullptr) {
      valid = false;
      break;
    }
  }
  file.close();
  return valid;
}

static mesh::storage::RecoveryCandidate chooseContactCandidate(
    FILESYSTEM* fs, const char* target, const char* scratch,
    const char* backup) {
  return mesh::storage::chooseRecoveryCandidate(
      contactRecordFileValid(fs, target),
      contactRecordFileValid(fs, scratch),
      contactRecordFileValid(fs, backup));
}

static mesh::storage::RecoveryCandidate chooseChannelCandidate(
    FILESYSTEM* fs, const char* target, const char* scratch,
    const char* backup) {
  return mesh::storage::chooseRecoveryCandidate(
      channelRecordFileValid(fs, target),
      channelRecordFileValid(fs, scratch),
      channelRecordFileValid(fs, backup));
}

static const char* candidatePath(mesh::storage::RecoveryCandidate candidate,
                                 const char* target, const char* scratch,
                                 const char* backup) {
  switch (candidate) {
    case mesh::storage::RecoveryCandidate::PRIMARY: return target;
    case mesh::storage::RecoveryCandidate::TEMPORARY: return scratch;
    case mesh::storage::RecoveryCandidate::BACKUP: return backup;
    default: return nullptr;
  }
}

// Cross-filesystem copy used by the EXTRAFS migration.  Source removal is the
// caller's responsibility and is only allowed after this function has compared
// both byte count and CRC.
static bool copyFileTransactional(FILESYSTEM* source_fs, const char* source,
                                  FILESYSTEM* dest_fs, const char* dest) {
  char scratch[64];
  char backup[64];
  if (!makeSiblingPath(dest, ".tmp", scratch, sizeof(scratch)) ||
      !makeSiblingPath(dest, ".bak", backup, sizeof(backup))) return false;

#if defined(NRF52_PLATFORM) || defined(STM32_PLATFORM)
  File input = source_fs->open(source, FILE_O_READ);
#elif defined(RP2040_PLATFORM)
  File input = source_fs->open(source, "r");
#else
  File input = source_fs->open(source, "r", false);
#endif
  if (!input) return false;
  if (!prepareScratch(dest_fs, scratch)) {
    input.close();
    return false;
  }
  File output = openScratch(dest_fs, scratch);
  if (!output) {
    input.close();
    return false;
  }

  uint8_t buffer[64];
  bool success = true;
  while (true) {
    const int n = input.read(buffer, sizeof(buffer));
    if (n < 0) {
      success = false;
      break;
    }
    if (n == 0) break;
    if (output.write(buffer, (size_t)n) != (size_t)n) {
      success = false;
      break;
    }
  }
  output.flush();
  input.close();
  output.close();

  success = success && filesMatch(source_fs, source, dest_fs, scratch);
  if (success) success = commitScratch(dest_fs, dest, scratch, backup);
  if (!success && dest_fs->exists(scratch)) dest_fs->remove(scratch);
  return success && filesMatch(source_fs, source, dest_fs, dest);
}

}  // namespace

// PowerSaving-v16 wrote its fixed legacy fields through byte 139, then
// appended the SmartUI extension.  Stock PowerSaving-v17 migrates only the
// fixed prefix to prefs.json and deliberately leaves /new_prefs in place.
static const uint32_t LEGACY_SMART_UI_PREFS_OFFSET = 140;

static bool isPrefsKeyChar(char c) {
  return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || c == '_';
}

// ConfigSerializer emits a compact JSON-like object with unquoted keys.  Scan
// only root-level keys and ignore quoted values, so a node name containing the
// text "smart_ui" cannot suppress the legacy migration.
static bool prefsHasRootKey(File& file, const char* wanted) {
  int depth = 0;
  bool in_string = false;
  bool escaped = false;
  char key[16];
  size_t key_len = 0;

  file.seek(0);
  while (file.available() > 0) {
    int value = file.read();
    if (value < 0) break;
    char c = (char)value;

    if (in_string) {
      if (escaped) {
        escaped = false;
      } else if (c == '\\') {
        escaped = true;
      } else if (c == '"') {
        in_string = false;
      }
      continue;
    }

    if (c == '"') {
      in_string = true;
      key_len = 0;
      continue;
    }
    if (c == '{') {
      depth++;
      key_len = 0;
      continue;
    }
    if (c == '}') {
      if (depth > 0) depth--;
      key_len = 0;
      continue;
    }
    if (depth != 1) {
      key_len = 0;
      continue;
    }

    if (isPrefsKeyChar(c)) {
      if (key_len + 1 < sizeof(key)) key[key_len++] = c;
      continue;
    }

    if (c == ':' && key_len > 0) {
      key[key_len] = 0;
      if (strcmp(key, wanted) == 0) return true;
    }
    key_len = 0;
  }
  return false;
}

// Read a prefix of the known PS16 SmartUI tail.  Stop at the first incomplete
// field: continuing after a truncated multi-byte value would shift every
// following setting and could route the buzzer to an unrelated GPIO.
static bool readLegacySmartUiTail(File& file, NodePrefs& prefs) {
  bool loaded = false;
#define READ_LEGACY_SMART_UI_FIELD(field)                                                \
  do {                                                                                   \
    if (file.available() < (int)sizeof(prefs.field)) return loaded;                      \
    if (file.read((uint8_t *)&prefs.field, sizeof(prefs.field)) != sizeof(prefs.field))  \
      return loaded;                                                                     \
    loaded = true;                                                                       \
  } while (0)
  READ_LEGACY_SMART_UI_FIELD(radio_fem_rxgain);
  READ_LEGACY_SMART_UI_FIELD(adc_multiplier);
  READ_LEGACY_SMART_UI_FIELD(notify_mode);
  READ_LEGACY_SMART_UI_FIELD(notify_gpio_pin);
  READ_LEGACY_SMART_UI_FIELD(notify_tone_pin);
  READ_LEGACY_SMART_UI_FIELD(notify_tone_id);
  READ_LEGACY_SMART_UI_FIELD(notify_tone_volume);
  READ_LEGACY_SMART_UI_FIELD(auto_advert_interval_mins);
  READ_LEGACY_SMART_UI_FIELD(ch2_mode);
  READ_LEGACY_SMART_UI_FIELD(board_leds_enabled);
  READ_LEGACY_SMART_UI_FIELD(ui_font);
  READ_LEGACY_SMART_UI_FIELD(ui_theme);
  READ_LEGACY_SMART_UI_FIELD(unread_led_enabled);
  READ_LEGACY_SMART_UI_FIELD(msg_popup_enabled);
  READ_LEGACY_SMART_UI_FIELD(important_notify_mode);
  READ_LEGACY_SMART_UI_FIELD(notifications_muted);
  READ_LEGACY_SMART_UI_FIELD(ui_top_color);
  READ_LEGACY_SMART_UI_FIELD(ui_bottom_color);
  READ_LEGACY_SMART_UI_FIELD(backlight_timeout_idx);
  READ_LEGACY_SMART_UI_FIELD(notify_vibe_pin);
  READ_LEGACY_SMART_UI_FIELD(offline_dm_led_enabled);
  READ_LEGACY_SMART_UI_FIELD(ble_dm_led_enabled);
  READ_LEGACY_SMART_UI_FIELD(low_battery_shutdown_enabled);
  READ_LEGACY_SMART_UI_FIELD(notify_tone_bridge_enabled);
  READ_LEGACY_SMART_UI_FIELD(notify_tone_8bit_enabled);
  READ_LEGACY_SMART_UI_FIELD(notify_tone_high_drive_enabled);
  READ_LEGACY_SMART_UI_FIELD(notify_tone_resonance_hz);
  READ_LEGACY_SMART_UI_FIELD(notify_tone_dm_id);
  READ_LEGACY_SMART_UI_FIELD(notify_tone_mention_id);
  READ_LEGACY_SMART_UI_FIELD(notify_tone_system_id);
  READ_LEGACY_SMART_UI_FIELD(smart_profile_id);
  READ_LEGACY_SMART_UI_FIELD(favorite_setting_1);
  READ_LEGACY_SMART_UI_FIELD(favorite_setting_2);
  READ_LEGACY_SMART_UI_FIELD(favorite_setting_3);
  READ_LEGACY_SMART_UI_FIELD(night_prompt_day);
  READ_LEGACY_SMART_UI_FIELD(night_quiet_active);
  READ_LEGACY_SMART_UI_FIELD(gps_source);
#undef READ_LEGACY_SMART_UI_FIELD
  return loaded;
}

void DataStore::loadPrefs(NodePrefs& prefs) {
  static const char* target = "/prefs.json";
  static const char* scratch = "/prefs.json.tmp";
  static const char* backup = "/prefs.json.bak";
  const char* candidates[] = {target, scratch, backup};

  bool prefs_ok = false;
  bool has_smart_ui = false;
  for (size_t i = 0; i < sizeof(candidates) / sizeof(candidates[0]); ++i) {
    if (!_fs->exists(candidates[i])) continue;
    File file = openRead(_fs, candidates[i]);
    if (!file) continue;

    NodePrefs candidate(prefs);
    has_smart_ui = prefsHasRootKey(file, "smart_ui");
    file.seek(0);
    prefs_ok = candidate.loadSerial(file);
    file.close();
    if (prefs_ok) {
      // Parsing is transactional too: malformed/truncated JSON never leaves a
      // half-updated live settings object.
      prefs = candidate;
      break;
    }
  }

  if (prefs_ok) {
    // A stock PS17 boot may already have created prefs.json without knowing
    // about SmartUI.  Merge only the retained PS16 extension, once.  Saving
    // adds the smart_ui root object, which is the durable migration marker.
    if (!has_smart_ui && _fs->exists("/new_prefs")) {
      File legacy = openRead(_fs, "/new_prefs");
      NodePrefs migrated(prefs);
      if (legacy && legacy.size() > LEGACY_SMART_UI_PREFS_OFFSET &&
          legacy.seek(LEGACY_SMART_UI_PREFS_OFFSET) &&
          readLegacySmartUiTail(legacy, migrated)) {
        legacy.close();
        prefs = migrated;
        savePrefs(prefs);
      } else if (legacy) {
        legacy.close();
      }
    }
  } else if (_fs->exists("/new_prefs")) {
    NodePrefs migrated(prefs);
    if (loadPrefsInt("/new_prefs", migrated)) {
      prefs = migrated;
      savePrefs(prefs);  // keep /new_prefs as a final legacy recovery copy
    }
  }
}

bool DataStore::loadPrefsInt(const char *filename, NodePrefs& _prefs) {
  File file = openRead(_fs, filename);
  if (file && file.size() >= LEGACY_SMART_UI_PREFS_OFFSET) {
    NodePrefs candidate(_prefs);
    uint8_t pad[8];
#define READ_REQUIRED(address, length)                                      \
    do {                                                                    \
      if (file.read((uint8_t *)(address), (length)) != (int)(length)) {      \
        file.close();                                                       \
        return false;                                                       \
      }                                                                     \
    } while (0)

    READ_REQUIRED(&candidate.airtime_factor, sizeof(candidate.airtime_factor));             // 0
    READ_REQUIRED(candidate.node_name, sizeof(candidate.node_name));                         // 4
    READ_REQUIRED(pad, 4);                                                                    // 36
    READ_REQUIRED(&candidate.node_lat, sizeof(candidate.node_lat));                          // 40
    READ_REQUIRED(&candidate.node_lon, sizeof(candidate.node_lon));                          // 48
    READ_REQUIRED(&candidate.freq, sizeof(candidate.freq));                                  // 56
    READ_REQUIRED(&candidate.sf, sizeof(candidate.sf));                                      // 60
    READ_REQUIRED(&candidate.cr, sizeof(candidate.cr));                                      // 61
    READ_REQUIRED(&candidate._client_repeat, sizeof(candidate._client_repeat));              // 62
    READ_REQUIRED(&candidate.manual_add_contacts, sizeof(candidate.manual_add_contacts));    // 63
    READ_REQUIRED(&candidate.bw, sizeof(candidate.bw));                                      // 64
    READ_REQUIRED(&candidate.tx_power_dbm, sizeof(candidate.tx_power_dbm));                  // 68
    READ_REQUIRED(&candidate.telemetry_mode_base, sizeof(candidate.telemetry_mode_base));    // 69
    READ_REQUIRED(&candidate.telemetry_mode_loc, sizeof(candidate.telemetry_mode_loc));      // 70
    READ_REQUIRED(&candidate.telemetry_mode_env, sizeof(candidate.telemetry_mode_env));      // 71
    READ_REQUIRED(&candidate.rx_delay_base, sizeof(candidate.rx_delay_base));                // 72
    READ_REQUIRED(&candidate.advert_loc_policy, sizeof(candidate.advert_loc_policy));        // 76
    READ_REQUIRED(&candidate.multi_acks, sizeof(candidate.multi_acks));                      // 77
    READ_REQUIRED(&candidate.path_hash_mode, sizeof(candidate.path_hash_mode));              // 78
    READ_REQUIRED(pad, 1);                                                                    // 79
    READ_REQUIRED(&candidate.ble_pin, sizeof(candidate.ble_pin));                            // 80
    READ_REQUIRED(&candidate.buzzer_quiet, sizeof(candidate.buzzer_quiet));                  // 84
    READ_REQUIRED(&candidate.gps_enabled, sizeof(candidate.gps_enabled));                    // 85
    READ_REQUIRED(&candidate.gps_interval, sizeof(candidate.gps_interval));                  // 86
    READ_REQUIRED(&candidate.autoadd_config, sizeof(candidate.autoadd_config));              // 87
    READ_REQUIRED(&candidate.autoadd_max_hops, sizeof(candidate.autoadd_max_hops));          // 88
    READ_REQUIRED(&candidate.rx_boosted_gain, sizeof(candidate.rx_boosted_gain));            // 89
    READ_REQUIRED(candidate.default_scope_name, sizeof(candidate.default_scope_name));       // 90
    READ_REQUIRED(candidate.default_scope_key, sizeof(candidate.default_scope_key));         // 121
#undef READ_REQUIRED
    candidate.node_name[sizeof(candidate.node_name) - 1] = 0;
    candidate.default_scope_name[sizeof(candidate.default_scope_name) - 1] = 0;

    // SmartUI on PowerSaving-v16 appended its settings to /new_prefs.  Read
    // only a complete prefix so stock legacy files keep constructor defaults.
    if (!file.seek(LEGACY_SMART_UI_PREFS_OFFSET)) {
      file.close();
      return false;
    }
    readLegacySmartUiTail(file, candidate);

    // migrate old fields
    candidate.setRepeatEn(candidate._client_repeat != 0);

    file.close();
    _prefs = candidate;
    return true;
  }
  if (file) file.close();
  return false;
}

bool DataStore::savePrefs(NodePrefs& _prefs) {
  static const char* target = "/prefs.json";
  static const char* scratch = "/prefs.json.tmp";
  static const char* backup = "/prefs.json.bak";

  if (!prepareScratch(_fs, scratch)) return false;
  File file = openScratch(_fs, scratch);
  if (!file) return false;
  bool success = _prefs.saveSerial(file);
  file.flush();
  file.close();

  // Re-open and parse the exact bytes which will be published.  A short write
  // or syntactically complete-but-unreadable file never replaces good prefs.
  NodePrefs verification(_prefs);
  File verify_file = openRead(_fs, scratch);
  success = success && verify_file && verification.loadSerial(verify_file);
  if (verify_file) verify_file.close();
  if (success) {
    success = commitScratch(_fs, target, scratch, backup,
                            prefsFileValid(_fs, target, _prefs));
  }
  if (!success && _fs->exists(scratch)) _fs->remove(scratch);
  return success;
}

void DataStore::loadContacts(DataStoreHost* host) {
    static const uint32_t CONTACT_RECORD_SIZE = 152;
    FILESYSTEM* fs = _getContactsChannelsFS();
    const char* selected = candidatePath(
        chooseContactCandidate(fs, "/contacts3", "/contacts3.tmp",
                               "/contacts3.bak"),
        "/contacts3", "/contacts3.tmp", "/contacts3.bak");
    if (!selected) return;
    File file = openRead(fs, selected);
    if (file) {
      bool full = false;
      while (!full) {
        ContactInfo c = {};
        uint8_t pub_key[32];
        uint8_t unused;

        bool success = (file.read(pub_key, 32) == 32);
        success = success && (file.read((uint8_t *)&c.name, 32) == 32);
        success = success && (file.read(&c.type, 1) == 1);
        success = success && (file.read(&c.flags, 1) == 1);
        success = success && (file.read(&unused, 1) == 1);
        success = success && (file.read((uint8_t *)&c.sync_since, 4) == 4); // was 'reserved'
        success = success && (file.read((uint8_t *)&c.out_path_len, 1) == 1);
        success = success && (file.read((uint8_t *)&c.last_advert_timestamp, 4) == 4);
        success = success && (file.read(c.out_path, 64) == 64);
        success = success && (file.read((uint8_t *)&c.lastmod, 4) == 4);
        success = success && (file.read((uint8_t *)&c.gps_lat, 4) == 4);
        success = success && (file.read((uint8_t *)&c.gps_lon, 4) == 4);

        if (!success) break; // EOF

        c.name[sizeof(c.name) - 1] = 0;
        if (c.type < ADV_TYPE_CHAT || c.type > ADV_TYPE_SENSOR ||
            !encodedPathLenValid(c.out_path_len)) break;
        c.id = mesh::Identity(pub_key);
        if (!host->onContactLoaded(c)) full = true;
      }
      file.close();
    }
}

bool DataStore::saveContacts(DataStoreHost* host, bool (*filter)(const ContactInfo& c)) {
  static const uint32_t CONTACT_RECORD_SIZE = 152;
  FILESYSTEM* fs = _getContactsChannelsFS();
  if (!prepareScratch(fs, "/contacts3.tmp")) return false;
  File file = openScratch(fs, "/contacts3.tmp");
  if (file) {
    uint32_t idx = 0;
    uint32_t records_written = 0;
    ContactInfo c;
    uint8_t unused = 0;
    bool success = true;

    while (host->getContactForSave(idx, c)) {
      if (filter && !filter(c)) {
        idx++;  // advance to next contact
        continue;
      }
      success = (file.write(c.id.pub_key, 32) == 32);
      success = success && (file.write((uint8_t *)&c.name, 32) == 32);
      success = success && (file.write(&c.type, 1) == 1);
      success = success && (file.write(&c.flags, 1) == 1);
      success = success && (file.write(&unused, 1) == 1);
      success = success && (file.write((uint8_t *)&c.sync_since, 4) == 4);
      success = success && (file.write((uint8_t *)&c.out_path_len, 1) == 1);
      success = success && (file.write((uint8_t *)&c.last_advert_timestamp, 4) == 4);
      success = success && (file.write(c.out_path, 64) == 64);
      success = success && (file.write((uint8_t *)&c.lastmod, 4) == 4);
      success = success && (file.write((uint8_t *)&c.gps_lat, 4) == 4);
      success = success && (file.write((uint8_t *)&c.gps_lon, 4) == 4);

      if (!success) break; // write failed

      records_written++;
      idx++;  // advance to next contact
    }
    file.flush();
    file.close();

    FileDigest digest;
    success = success && digestFile(fs, "/contacts3.tmp", digest) &&
              digest.size == records_written * CONTACT_RECORD_SIZE;
    if (success) {
      success = commitScratch(
          fs, "/contacts3", "/contacts3.tmp", "/contacts3.bak",
          contactRecordFileValid(fs, "/contacts3"));
    }
    if (!success && fs->exists("/contacts3.tmp")) fs->remove("/contacts3.tmp");
    return success;
  }
  return false;
}

void DataStore::loadChannels(DataStoreHost* host) {
    static const uint32_t CHANNEL_RECORD_SIZE = 68;
    FILESYSTEM* fs = _getContactsChannelsFS();
    const char* selected = candidatePath(
        chooseChannelCandidate(fs, "/channels2", "/channels2.tmp",
                               "/channels2.bak"),
        "/channels2", "/channels2.tmp", "/channels2.bak");
    if (!selected) return;
    File file = openRead(fs, selected);
    if (file) {
      bool full = false;
      uint8_t channel_idx = 0;
      while (!full) {
        ChannelDetails ch = {};
        uint8_t unused[4];

        bool success = (file.read(unused, 4) == 4);
        success = success && (file.read((uint8_t *)ch.name, 32) == 32);
        success = success && (file.read((uint8_t *)ch.channel.secret, 32) == 32);

        if (!success) break; // EOF

        ch.name[sizeof(ch.name) - 1] = 0;
        if (host->onChannelLoaded(channel_idx, ch)) {
          channel_idx++;
        } else {
          full = true;
        }
      }
      file.close();
    }
}

bool DataStore::saveChannels(DataStoreHost* host) {
  static const uint32_t CHANNEL_RECORD_SIZE = 68;
  FILESYSTEM* fs = _getContactsChannelsFS();
  if (!prepareScratch(fs, "/channels2.tmp")) return false;
  File file = openScratch(fs, "/channels2.tmp");
  if (file) {
    uint8_t channel_idx = 0;
    uint32_t records_written = 0;
    ChannelDetails ch;
    uint8_t unused[4];
    memset(unused, 0, 4);
    bool success = true;

    while (host->getChannelForSave(channel_idx, ch)) {
      success = (file.write(unused, 4) == 4);
      success = success && (file.write((uint8_t *)ch.name, 32) == 32);
      success = success && (file.write((uint8_t *)ch.channel.secret, 32) == 32);

      if (!success) break; // write failed
      records_written++;
      channel_idx++;
    }
    file.flush();
    file.close();

    FileDigest digest;
    success = success && digestFile(fs, "/channels2.tmp", digest) &&
              digest.size == records_written * CHANNEL_RECORD_SIZE;
    if (success) {
      success = commitScratch(
          fs, "/channels2", "/channels2.tmp", "/channels2.bak",
          channelRecordFileValid(fs, "/channels2"));
    }
    if (!success && fs->exists("/channels2.tmp")) fs->remove("/channels2.tmp");
    return success;
  }
  return false;
}

#if defined(NRF52_PLATFORM) || defined(STM32_PLATFORM)

#define MAX_ADVERT_PKT_LEN   (2 + 32 + PUB_KEY_SIZE + 4 + SIGNATURE_SIZE + MAX_ADVERT_DATA_SIZE)

struct BlobRec {
  uint32_t timestamp;
  uint8_t  key[7];
  uint8_t  len;
  uint8_t  data[MAX_ADVERT_PKT_LEN];
};

void DataStore::checkAdvBlobFile() {
  if (!_getContactsChannelsFS()->exists("/adv_blobs")) {
    File file = openWrite(_getContactsChannelsFS(), "/adv_blobs");
    if (file) {
      BlobRec zeroes;
      memset(&zeroes, 0, sizeof(zeroes));
      for (int i = 0; i < MAX_BLOBRECS; i++) {     // pre-allocate to fixed size
        file.write((uint8_t *) &zeroes, sizeof(zeroes));
      }
      file.close();
    }
  }
}

void DataStore::migrateToSecondaryFS() {
  if (!_fsExtra) return;

  // Bulk data belongs on the secondary filesystem.  If both copies differ we
  // retain both rather than guessing which generation is newer.
  const char* secondary_files[] = {"/adv_blobs", "/contacts3", "/channels2"};
  for (size_t i = 0; i < sizeof(secondary_files) / sizeof(secondary_files[0]); ++i) {
    const char* path = secondary_files[i];
    if (!_fs->exists(path)) continue;

    bool safe_to_remove_source = false;
    if (_fsExtra->exists(path)) {
      safe_to_remove_source = filesMatch(_fs, path, _fsExtra, path);
    } else {
      safe_to_remove_source = copyFileTransactional(_fs, path, _fsExtra, path);
    }
    if (safe_to_remove_source) {
      _fs->remove(path);
    } else {
      MESH_DEBUG_PRINTLN("DataStore migration retained primary %s (copy not verified)", path);
    }
  }

  // Identity and legacy preferences belong on the primary filesystem.  These
  // test-era secondary copies are removed only after the destination bytes
  // have been re-read and matched by size and CRC.
  const char* primary_files[] = {"/_main.id", "/new_prefs"};
  for (size_t i = 0; i < sizeof(primary_files) / sizeof(primary_files[0]); ++i) {
    const char* path = primary_files[i];
    if (!_fsExtra->exists(path)) continue;
    if (_fs->exists(path)) {
      if (filesMatch(_fsExtra, path, _fs, path)) {
        _fsExtra->remove(path);
      } else {
        // The primary identity/preferences are authoritative once present.
        // Keep the differing secondary copy for manual recovery instead of
        // silently replacing the node identity or legacy configuration.
        MESH_DEBUG_PRINTLN("DataStore migration conflict retained both copies of %s", path);
      }
      continue;
    }
    if (copyFileTransactional(_fsExtra, path, _fs, path)) {
      _fsExtra->remove(path);
    } else {
      MESH_DEBUG_PRINTLN("DataStore migration retained secondary %s (copy not verified)", path);
    }
  }
}

uint8_t DataStore::getBlobByKey(const uint8_t key[], int key_len, uint8_t dest_buf[]) {
  if (key == NULL || dest_buf == NULL || key_len < 7) return 0;
  File file = openRead(_getContactsChannelsFS(), "/adv_blobs");
  uint8_t len = 0;  // 0 = not found
  if (file) {
    BlobRec tmp;
    while (file.read((uint8_t *) &tmp, sizeof(tmp)) == sizeof(tmp)) {
      if (memcmp(key, tmp.key, sizeof(tmp.key)) == 0) {  // only match by 7 byte prefix
        if (tmp.len <= sizeof(tmp.data)) {
          len = tmp.len;
          memcpy(dest_buf, tmp.data, len);
        }
        break;
      }
    }
    file.close();
  }
  return len;
}

bool DataStore::putBlobByKey(const uint8_t key[], int key_len, const uint8_t src_buf[], uint8_t len) {
  if (key == NULL || src_buf == NULL || key_len < 7 ||
      len < PUB_KEY_SIZE+4+SIGNATURE_SIZE || len > MAX_ADVERT_PKT_LEN) return false;
  checkAdvBlobFile();
  File file = _getContactsChannelsFS()->open("/adv_blobs", FILE_O_WRITE);
  if (file) {
    uint32_t pos = 0, found_pos = 0;
    uint32_t min_timestamp = 0xFFFFFFFF;

    // search for matching key OR evict by oldest timestamp
    BlobRec tmp = {};
    file.seek(0);
    while (file.read((uint8_t *) &tmp, sizeof(tmp)) == sizeof(tmp)) {
      if (memcmp(key, tmp.key, sizeof(tmp.key)) == 0) {  // only match by 7 byte prefix
        found_pos = pos;
        break;
      }
      if (tmp.timestamp < min_timestamp) {
        min_timestamp = tmp.timestamp;
        found_pos = pos;
      }

      pos += sizeof(tmp);
    }

    memcpy(tmp.key, key, sizeof(tmp.key));  // just record 7 byte prefix of key
    memcpy(tmp.data, src_buf, len);
    tmp.len = len;
    tmp.timestamp = _clock->getCurrentTime();

    file.seek(found_pos);
    const bool written = file.write((uint8_t *) &tmp, sizeof(tmp)) == sizeof(tmp);
    file.flush();

    file.close();
    return written;
  }
  return false; // error
}
bool DataStore::deleteBlobByKey(const uint8_t key[], int key_len) {
  return true; // this is just a stub on NRF52/STM32 platforms
}
#else
inline void makeBlobPath(const uint8_t key[], int key_len, char* path, size_t path_size) {
  char fname[18];
  if (key_len > 8) key_len = 8; // just use first 8 bytes (prefix)
  mesh::Utils::toHex(fname, key, key_len);
  snprintf(path, path_size, "/bl/%s", fname);
}

uint8_t DataStore::getBlobByKey(const uint8_t key[], int key_len, uint8_t dest_buf[]) {
  if (key == NULL || dest_buf == NULL || key_len <= 0) return 0;
  char path[64];
  makeBlobPath(key, key_len, path, sizeof(path));

  if (_fs->exists(path)) {
    File f = openRead(_fs, path);
    if (f) {
      int len = f.read(dest_buf, 255); // currently MAX 255 byte blob len supported!!
      f.close();
      return len;
    }
  }
  return 0; // not found
}

bool DataStore::putBlobByKey(const uint8_t key[], int key_len, const uint8_t src_buf[], uint8_t len) {
  if (key == NULL || src_buf == NULL || key_len <= 0) return false;
  char path[64];
  makeBlobPath(key, key_len, path, sizeof(path));

  File f = openWrite(_fs, path);
  if (f) {
    int n = f.write(src_buf, len);
    f.close();
    if (n == len) return true; // success!

    _fs->remove(path); // blob was only partially written!
  }
  return false; // error
}

bool DataStore::deleteBlobByKey(const uint8_t key[], int key_len) {
  if (key == NULL || key_len <= 0) return false;
  char path[64];
  makeBlobPath(key, key_len, path, sizeof(path));

  _fs->remove(path);
  
  return true; // return true even if file did not exist
}
#endif
