// Host-only fixture for test_nrf52_safe_mount.py; never part of a firmware build.
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <climits>
#include <vector>
#include <InternalFileSystem.h>
#include <CustomLFS.h>
#include <helpers/nrf52/SafeLittleFsMount.h>
#include <helpers/nrf52/SafeNrf52FlashRegion.h>

using Region = smartui::SafeNrf52FlashRegion;
unsigned lock_acquisitions = 0;
bool filesystem_locked = false, cache_locked = false, creating_shared_mutex = false;
bool fail_mutex_creation = false;
static std::vector<uint8_t> disk;
static uint32_t disk_start;
static unsigned reads, writes, flushes, read_fault_lock, scenarios;
static int read_result = INT_MAX, write_result = INT_MAX;
// Only the single-threaded compatibility setup uses the unmodified old driver.
// All production-driver cases must still acquire the shared cache mutex.
static bool legacy_driver_active = false;
static unsigned physical_erases, compatibility_cases;

extern "C" {
void* pvPortMalloc(size_t n) { return std::malloc(n); }
void vPortFree(void* p) { std::free(p); }
int flash_nrf5x_read(void* p, uint32_t address, uint32_t n) {
  assert(filesystem_locked && cache_locked == !legacy_driver_active && address >= disk_start);
  assert(address-disk_start <= disk.size() && n <= disk.size()-(address-disk_start));
  ++reads;
  if (read_fault_lock && lock_acquisitions == read_fault_lock) return -1;
  if (read_result != INT_MAX) return read_result;
  std::memcpy(p, disk.data()+address-disk_start, n); return static_cast<int>(n);
}
int flash_nrf5x_write(uint32_t address, const void* p, uint32_t n) {
  assert(filesystem_locked && cache_locked == !legacy_driver_active && address >= disk_start);
  assert(address-disk_start <= disk.size() && n <= disk.size()-(address-disk_start));
  ++writes;
  if (write_result != INT_MAX) return write_result;
  std::memcpy(disk.data()+address-disk_start, p, n); return static_cast<int>(n);
}
void flash_nrf5x_flush() {
  assert(filesystem_locked && cache_locked == !legacy_driver_active); ++flushes;
}
bool flash_nrf5x_erase(uint32_t address) {
  // Legacy destructive begin() uses this path outside its filesystem mutex.
  // Compatibility cases deliberately create an image through base format().
  assert(legacy_driver_active && !cache_locked && address >= disk_start);
  assert(address-disk_start <= disk.size() &&
         FLASH_NRF52_PAGE_SIZE <= disk.size()-(address-disk_start));
  ++physical_erases;
  std::memset(disk.data()+address-disk_start,255,FLASH_NRF52_PAGE_SIZE); return true;
}
}

static void reset(uint32_t start, unsigned bytes) {
  assert(!filesystem_locked); disk_start=start; disk.assign(bytes, 255);
  reads=writes=flushes=physical_erases=read_fault_lock=lock_acquisitions=0;
  read_result=write_result=INT_MAX;
}
static void initCache(smartui::Nrf52FlashCacheLock& lock) {
  creating_shared_mutex=true; assert(lock.begin()); creating_shared_mutex=false;
}
// A destructive derived begin() must never be selected, even on fresh flash.
struct DerivedFileSystem : Adafruit_LittleFS {
  unsigned destructive_calls=0;
  DerivedFileSystem() : Adafruit_LittleFS(nullptr) {}
  bool begin() { ++destructive_calls; return false; }
};
static bool mount(DerivedFileSystem& fs, Region& region) {
  const bool result=smartui::mountAtStartupOrInitializeErased(fs,region.config());
  assert(fs.destructive_calls==0);
  return result;
}
static void put(Adafruit_LittleFS& fs, const char* path, size_t bytes, uint8_t value) {
  fs._lockFS(); lfs_file_t file{}; std::vector<uint8_t> data(bytes, value);
  assert(lfs_file_open(fs._getFS(), &file, path, LFS_O_RDWR|LFS_O_CREAT)==0);
  assert(lfs_file_write(fs._getFS(), &file, data.data(), data.size())==(int)data.size());
  assert(lfs_file_close(fs._getFS(), &file)==0); fs._unlockFS();
}
static void verify(Adafruit_LittleFS& fs, const char* path, size_t bytes, uint8_t value) {
  fs._lockFS(); lfs_file_t file{}; std::vector<uint8_t> data(bytes);
  assert(lfs_file_open(fs._getFS(), &file, path, LFS_O_RDONLY)==0);
  assert(lfs_file_size(fs._getFS(), &file)==(int)bytes);
  assert(lfs_file_read(fs._getFS(), &file, data.data(), data.size())==(int)data.size());
  assert(std::all_of(data.begin(), data.end(), [value](uint8_t v){return v==value;}));
  assert(lfs_file_close(fs._getFS(), &file)==0); fs._unlockFS();
}
static void legacyCompatibilityCase(Adafruit_LittleFS& legacy, uint32_t start, unsigned bytes) {
  reset(start,bytes);
  const bool internal=bytes==Region::kInternalSize;
  auto checkFiles=[internal](Adafruit_LittleFS& fs, bool create) {
    auto file=[&](const char* path,size_t count,uint8_t value) {
      if (create) put(fs,path,count,value); else verify(fs,path,count,value);
    };
    if (internal) {
      file("/_main.id",96,0x31); file("/prefs.json",1500,0x52);
      file("/adafruit/bond/peer",193,0x73);
    } else {
      // Exercise the old 350-contact layout, including multi-level CTZ links.
      file("/contacts3",350*152,0x31); file("/channels2",40*68,0x52);
      file("/adv_blobs",18000,0x73);
    }
  };

  // Compile and execute the actual pinned legacy callbacks and configuration,
  // not a second copy of the new driver or a hand-written layout approximation.
  legacy_driver_active=true;
  assert(legacy.format() && legacy.begin());
  if (internal) assert(legacy.mkdir("/adafruit/bond"));
  checkFiles(legacy,true); legacy.end();
  assert(writes>0 && physical_erases==0);
  legacy_driver_active=false;
  const auto old_image=disk;
  writes=flushes=0;

  smartui::Nrf52FlashCacheLock cache; initCache(cache);
  Region region(start,bytes,cache);
  {
    DerivedFileSystem upgraded;
    assert(mount(upgraded,region));
    checkFiles(upgraded,false);
    assert(disk==old_image && writes==0 && flushes==0 && physical_erases==0);
    ++compatibility_cases; ++scenarios;

    put(upgraded,"/new-setting",513,0x94); upgraded.end();
  }
  const auto new_image=disk;
  writes=flushes=0;
  // A newly written file remains readable by the old layout as well.
  legacy_driver_active=true;
  assert(legacy.begin()); checkFiles(legacy,false);
  verify(legacy,"/new-setting",513,0x94); legacy.end();
  legacy_driver_active=false;
  assert(disk==new_image && writes==0 && flushes==0 && physical_erases==0);
  ++compatibility_cases; ++scenarios;
}
static void mountCases(uint32_t start, unsigned bytes) {
  smartui::Nrf52FlashCacheLock cache; initCache(cache);
  Region region(start,bytes,cache); assert(region.config()); reset(start,bytes);
  {
    DerivedFileSystem fs;
    assert(mount(fs,region)); assert(writes>0);
    if (bytes==Region::kInternalSize) {
      put(fs,"/_main.id",96,0x31); put(fs,"/prefs.json",1500,0x52); put(fs,"/bonds",128,0x73);
    } else {
      put(fs,"/contacts3",200*152,0x31); put(fs,"/channels2",40*68,0x52); put(fs,"/adv_blobs",18000,0x73);
    }
    fs.end(); ++scenarios;
  }
  const auto existing=disk; writes=flushes=lock_acquisitions=0;
  {
    DerivedFileSystem fs;
    assert(mount(fs,region)); assert(writes==0 && flushes==0);
    if (bytes==Region::kInternalSize) {
      verify(fs,"/_main.id",96,0x31); verify(fs,"/prefs.json",1500,0x52); verify(fs,"/bonds",128,0x73);
    } else {
      verify(fs,"/contacts3",200*152,0x31); verify(fs,"/channels2",40*68,0x52); verify(fs,"/adv_blobs",18000,0x73);
    }
    fs.end(); assert(disk==existing && writes==0 && flushes==0); ++scenarios;
  }
  lock_acquisitions=0; read_fault_lock=1;
  {
    DerivedFileSystem fs;
    assert(!mount(fs,region)); assert(writes==0 && disk==existing); ++scenarios;
  }
  for (unsigned pos : {0U, bytes/2, bytes-1}) {
    reset(start,bytes); disk[pos]=0; const auto unchanged=disk;
    DerivedFileSystem fs;
    assert(!mount(fs,region)); assert(writes==0 && disk==unchanged); ++scenarios;
  }
  reset(start,bytes); read_fault_lock=2; // Failure during the erased-region scan.
  {
    DerivedFileSystem fs; assert(!mount(fs,region)); assert(writes==0); ++scenarios;
  }
  reset(start,bytes); write_result=-1;
  {
    DerivedFileSystem fs; assert(!mount(fs,region)); assert(writes>0); ++scenarios;
  }
  reset(start,bytes); read_fault_lock=4; // Post-format mount must also succeed.
  {
    DerivedFileSystem fs; assert(!mount(fs,region)); assert(writes>0 && lock_acquisitions==4); ++scenarios;
  }
}

static void callbackCases() {
  reset(Region::kInternalStart,Region::kInternalSize);
  smartui::Nrf52FlashCacheLock cache; initCache(cache);
  Region region(disk_start,static_cast<unsigned>(disk.size()),cache); auto* c=region.config();
  DerivedFileSystem lock; uint8_t data[128]={}; lock._lockFS();
  for (lfs_block_t block : {c->block_count, UINT32_MAX}) {
    assert(c->read(c,block,0,data,128)==LFS_ERR_CORRUPT);
    assert(c->prog(c,block,0,data,128)==LFS_ERR_CORRUPT);
    assert(c->erase(c,block)==LFS_ERR_CORRUPT); ++scenarios;
  }
  for (lfs_off_t offset : {129U,UINT32_MAX}) {
    assert(c->read(c,0,offset,data,1)==LFS_ERR_CORRUPT);
    assert(c->prog(c,0,offset,data,1)==LFS_ERR_CORRUPT); ++scenarios;
  }
  for (lfs_size_t count : {2U,UINT32_MAX}) {
    assert(c->read(c,c->block_count-1,127,data,count)==LFS_ERR_CORRUPT);
    assert(c->prog(c,c->block_count-1,127,data,count)==LFS_ERR_CORRUPT); ++scenarios;
  }
  assert(reads==0 && writes==0);
  assert(c->read(c,c->block_count-1,128,data,0)==0);
  assert(c->prog(c,c->block_count-1,128,data,0)==0);
  assert(reads==0 && writes==0); ++scenarios;
  for (int result : {-1,0,127}) {
    read_result=result; assert(c->read(c,0,0,data,128)==LFS_ERR_IO);
    write_result=result; assert(c->prog(c,0,0,data,128)==LFS_ERR_IO); ++scenarios;
  }
  write_result=-1; const unsigned before=writes;
  assert(c->erase(c,0)==LFS_ERR_IO && writes==before+1); ++scenarios;
  read_result=write_result=INT_MAX;
  assert(c->prog(c,c->block_count-1,127,data,1)==0);
  assert(c->read(c,c->block_count-1,127,data,1)==0); ++scenarios;
  lock._unlockFS();

  for (auto pair : {std::pair<uint32_t,uint32_t>{0,4096}, {UINT32_MAX,4096},
                    {Region::kInternalStart,UINT32_MAX}, {Region::kInternalStart+1,4096},
                    {Region::kInternalStart,0}, {Region::kStorageEnd,4096}}) {
    Region invalid(pair.first,pair.second,cache); DerivedFileSystem fs;
    assert(!invalid.config() && !mount(fs,invalid)); ++scenarios;
  }
  for (bool fail_initialization : {false,true}) {
    reset(Region::kInternalStart,Region::kInternalSize);
    smartui::Nrf52FlashCacheLock unavailable;
    if (fail_initialization) {
      fail_mutex_creation=true; assert(!unavailable.begin()); fail_mutex_creation=false;
    }
    Region blocked(disk_start,static_cast<unsigned>(disk.size()),unavailable);
    auto* config=blocked.config(); DerivedFileSystem fs;
    fs._lockFS();
    assert(config->read(config,0,0,data,sizeof(data))==LFS_ERR_IO);
    assert(config->prog(config,0,0,data,sizeof(data))==LFS_ERR_IO);
    assert(config->erase(config,0)==LFS_ERR_IO);
    assert(config->sync(config)==LFS_ERR_IO);
    fs._unlockFS(); assert(reads==0 && writes==0 && flushes==0); ++scenarios;
  }
}

static void corruptCtzCase() {
#if defined(NRF52840_XXAA)
  const uint32_t start=0xD4000, bytes=0x19000, contact_count=200;
#else
  const uint32_t start=Region::kInternalStart, bytes=Region::kInternalSize, contact_count=101;
#endif
  smartui::Nrf52FlashCacheLock cache; initCache(cache);
  Region region(start,bytes,cache); reset(start,bytes); lfs_block_t head;
  {
    DerivedFileSystem fs; assert(mount(fs,region)); put(fs,"/contacts3",contact_count*152,0x55);
    fs._lockFS(); lfs_file_t file{};
    assert(lfs_file_open(fs._getFS(),&file,"/contacts3",LFS_O_RDONLY)==0);
    head=file.head; assert(lfs_file_close(fs._getFS(),&file)==0); fs._unlockFS(); fs.end();
  }
  // A single damaged CTZ pointer is outside directory CRC coverage: mounting
  // still succeeds, but the old callback dereferenced an out-of-flash address.
  uint32_t link; std::memcpy(&link,disk.data()+head*128,4); link^=0x10000;
  std::memcpy(disk.data()+head*128,&link,4);
  const auto corrupted=disk; writes=0;
  {
    DerivedFileSystem fs; assert(mount(fs,region));
    fs._lockFS(); lfs_file_t file{}; uint8_t record[152];
    assert(lfs_file_open(fs._getFS(),&file,"/contacts3",LFS_O_RDONLY)==0);
    assert(lfs_file_read(fs._getFS(),&file,record,sizeof(record))==LFS_ERR_CORRUPT);
    assert(lfs_file_close(fs._getFS(),&file)==0); fs._unlockFS(); fs.end();
    assert(disk==corrupted && writes==0); ++scenarios;
  }
}

int main() {
  assert(LFS_VERSION==0x00010007);
  {
    InternalFileSystem legacy;
    legacyCompatibilityCase(legacy,Region::kInternalStart,Region::kInternalSize);
  }
  mountCases(Region::kInternalStart,Region::kInternalSize);
#if defined(NRF52840_XXAA)
  {
    CustomLFS legacy(0xD4000,0x19000,128);
    legacyCompatibilityCase(legacy,0xD4000,0x19000);
  }
  mountCases(0xD4000,0x19000);
#else
  smartui::Nrf52FlashCacheLock cache;
  Region unsupported_extra(0xD4000,0x19000,cache);
  assert(!unsupported_extra.config()); ++scenarios;
#endif
  callbackCases(); corruptCtzCase(); assert(!filesystem_locked);
  std::printf("PASS %u legacy/guarded compatibility cases: pinned InternalFS/CustomLFS files preserved; mount/read performed no writes\n",compatibility_cases);
  std::printf("PASS nRF52 safe mount/bounds: %u scenarios, InternalFS=0x%05X; production drivers and pinned Adafruit/LittleFS1.7\n",scenarios,Region::kInternalStart);
}
