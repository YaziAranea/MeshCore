#pragma once

#include <Adafruit_LittleFS.h>

namespace smartui {

// Startup only: call before BLE, application tasks, or other filesystem users.
// The base reference deliberately selects Adafruit_LittleFS::begin(), whose
// non-virtual implementation never calls the destructive derived begin().
inline bool mountAtStartupOrInitializeErased(Adafruit_LittleFS& fs, lfs_config* config) {
  if (!config) return false;
  // Install the bounded driver before the first mount, not after traversing
  // untrusted on-flash metadata. Refuse an already mounted different config.
  if (fs.begin(config)) return fs._getFS()->cfg == config;

  // These reads bypass the public filesystem API, so take its mutex. Release
  // it before format()/begin(), which acquire the same non-recursive mutex.
  // Startup ordering excludes another writer between the scan and format.
  fs._lockFS();
  const lfs_config* cfg = fs._getFS()->cfg;
  bool erased = cfg && cfg->read && cfg->block_count && cfg->block_size &&
                cfg->read_size && cfg->read_size <= 128 &&
                128 % cfg->read_size == 0 &&
                cfg->block_size % cfg->read_size == 0;
  uint8_t buffer[128];
  if (erased) {
    for (lfs_block_t block = 0; erased && block < cfg->block_count; ++block) {
      for (lfs_off_t offset = 0; erased && offset < cfg->block_size;) {
        const lfs_size_t remaining = cfg->block_size - offset;
        const lfs_size_t count = remaining < sizeof(buffer) ? remaining : sizeof(buffer);
        if (cfg->read(cfg, block, offset, buffer, count) != 0) {
          erased = false;
          break;
        }
        for (lfs_size_t i = 0; i < count; ++i) {
          if (buffer[i] != 0xFF) {
            erased = false;
            break;
          }
        }
        offset += count;
      }
    }
  }
  fs._unlockFS();

  // A mount error alone is never permission to erase existing data. A read
  // failure or even one non-erased byte leaves the entire region untouched.
  return erased && fs.format() && fs.begin();
}

}  // namespace smartui
