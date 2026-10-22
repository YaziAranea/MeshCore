#pragma once

#include <Adafruit_LittleFS.h>
#include <flash/flash_nrf5x.h>

namespace smartui {

// InternalFS and ExtraFS use one vendor flash cache. Their separate filesystem
// mutexes cannot protect that shared buffer while a flash operation yields.
class Nrf52FlashCacheLock {
 public:
  Nrf52FlashCacheLock() : _storage{}, _mutex(nullptr) {}
  Nrf52FlashCacheLock(const Nrf52FlashCacheLock&) = delete;
  Nrf52FlashCacheLock& operator=(const Nrf52FlashCacheLock&) = delete;

  // Setup only, before either filesystem or BLE bonding can use the cache.
  bool begin() {
    if (!_mutex) _mutex = xSemaphoreCreateMutexStatic(&_storage);
    return _mutex != nullptr;
  }

  class Guard {
   public:
    explicit Guard(Nrf52FlashCacheLock& lock)
        : _mutex(lock._mutex), _held(_mutex && xSemaphoreTake(_mutex, portMAX_DELAY) == pdTRUE) {}
    ~Guard() { if (_held) xSemaphoreGive(_mutex); }
    explicit operator bool() const { return _held; }
    Guard(const Guard&) = delete;
    Guard& operator=(const Guard&) = delete;
   private:
    SemaphoreHandle_t _mutex;
    bool _held;
  };

 private:
  StaticSemaphore_t _storage;
  SemaphoreHandle_t _mutex;
};

// Match the pinned Adafruit/CustomLFS disk layout and flash-cache API. These
// objects must outlive every mount: LittleFS retains the config/context pointers.
class SafeNrf52FlashRegion {
 public:
  static constexpr uint32_t kBlockSize = 128;
  static constexpr uint32_t kInternalSize = 7 * 4096;
#if defined(NRF52840_XXAA)
  static constexpr uint32_t kInternalStart = 0xED000;
  static constexpr uint32_t kStorageEnd = 0xF4000;
#elif defined(NRF52832_XXAA)
  static constexpr uint32_t kInternalStart = 0x6D000;
  static constexpr uint32_t kStorageEnd = 0x74000;
#else
  #error SafeNrf52FlashRegion requires an explicitly supported nRF52840 or nRF52832
#endif
  static_assert(FLASH_NRF52_PAGE_SIZE == 4096, "Review the nRF52 flash geometry");
  static_assert(LFS_VERSION == 0x00010007, "Review the pinned LittleFS API/layout");

  SafeNrf52FlashRegion(uint32_t start, uint32_t size, Nrf52FlashCacheLock& cache_lock)
      : _start(start), _size(size), _cache_lock(cache_lock), _config{} {
    // Never access the SoftDevice-v6 or bootloader regions used by these boards.
    _valid = start >= 0x26000 && start < kStorageEnd && size > 0 &&
             start % FLASH_NRF52_PAGE_SIZE == 0 &&
             size % FLASH_NRF52_PAGE_SIZE == 0 && size <= kStorageEnd - start;
    _config.context = this;
    _config.read = read;
    _config.prog = program;
    _config.erase = erase;
    _config.sync = sync;
    _config.read_size = _config.prog_size = _config.block_size = kBlockSize;
    _config.block_count = size / kBlockSize;
    _config.lookahead = 128;
  }

  SafeNrf52FlashRegion(const SafeNrf52FlashRegion&) = delete;
  SafeNrf52FlashRegion& operator=(const SafeNrf52FlashRegion&) = delete;

  lfs_config* config() { return _valid ? &_config : nullptr; }

 private:
  uint32_t _start;
  uint32_t _size;
  bool _valid;
  Nrf52FlashCacheLock& _cache_lock;
  lfs_config _config;

  static bool address(const lfs_config* cfg, lfs_block_t block, lfs_off_t offset,
                      lfs_size_t size, uint32_t& result) {
    if (!cfg || !cfg->context) return false;
    const auto* region = static_cast<const SafeNrf52FlashRegion*>(cfg->context);
    // Validate before multiplication/addition, including a damaged CTZ link.
    if (!region->_valid || cfg != &region->_config ||
        cfg->block_size != kBlockSize || cfg->block_count != region->_size / kBlockSize ||
        block >= cfg->block_count || offset > kBlockSize || size > kBlockSize - offset)
      return false;
    result = region->_start + block * kBlockSize + offset;
    return true;
  }

  static int read(const lfs_config* cfg, lfs_block_t block, lfs_off_t offset,
                  void* buffer, lfs_size_t size) {
    uint32_t addr;
    if (!address(cfg, block, offset, size, addr)) return LFS_ERR_CORRUPT;
    if (size == 0) return 0;
    Nrf52FlashCacheLock::Guard lock(static_cast<SafeNrf52FlashRegion*>(cfg->context)->_cache_lock);
    if (!lock) return LFS_ERR_IO;
    return flash_nrf5x_read(buffer, addr, size) == static_cast<int>(size) ? 0 : LFS_ERR_IO;
  }

  static int program(const lfs_config* cfg, lfs_block_t block, lfs_off_t offset,
                     const void* buffer, lfs_size_t size) {
    uint32_t addr;
    if (!address(cfg, block, offset, size, addr)) return LFS_ERR_CORRUPT;
    if (size == 0) return 0;
    Nrf52FlashCacheLock::Guard lock(static_cast<SafeNrf52FlashRegion*>(cfg->context)->_cache_lock);
    if (!lock) return LFS_ERR_IO;
    // Negative error values are truthy: require the full byte count explicitly.
    return flash_nrf5x_write(addr, buffer, size) == static_cast<int>(size) ? 0 : LFS_ERR_IO;
  }

  static int erase(const lfs_config* cfg, lfs_block_t block) {
    uint32_t addr;
    if (!address(cfg, block, 0, kBlockSize, addr)) return LFS_ERR_CORRUPT;
    Nrf52FlashCacheLock::Guard lock(static_cast<SafeNrf52FlashRegion*>(cfg->context)->_cache_lock);
    if (!lock) return LFS_ERR_IO;
    // Preserve the vendor's 128-byte logical erase through its 4 KiB cache.
    for (uint32_t offset = 0; offset < kBlockSize; ++offset) {
      if (flash_nrf5x_write8(addr + offset, 0xFF) != 1) return LFS_ERR_IO;
    }
    return 0;
  }

  static int sync(const lfs_config* cfg) {
    uint32_t unused;
    if (!address(cfg, 0, 0, 0, unused)) return LFS_ERR_CORRUPT;
    Nrf52FlashCacheLock::Guard lock(static_cast<SafeNrf52FlashRegion*>(cfg->context)->_cache_lock);
    if (!lock) return LFS_ERR_IO;
    // The vendor flush API has no result; DataStore still verifies saved bytes.
    flash_nrf5x_flush();
    return 0;
  }
};

}  // namespace smartui
