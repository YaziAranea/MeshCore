#!/usr/bin/env python3
"""Production truncation fault tests; optional littlefs1.7 power-cut tests.

The default test needs a host C++ compiler (or WSL). --littlefs also requires
the installed Adafruit nRF52 LittleFS library, like the firmware-build CI job.
The 100 KiB RAM disk includes full advert storage and three generations of 40
channels. Cuts occur before, halfway through, and after every program/erase
operation of the truncation transaction. No board is accessed.
"""
from pathlib import Path
import argparse
import shutil
import subprocess
import tempfile

import test_littlefs_prefs_capacity as real
from test_contact_persistence import HARNESS, ROOT, function, linux


def native_source():
    source = (ROOT / "examples/companion_radio/DataStore.cpp").read_text(encoding="utf-8")
    code = """
#define NRF52_PLATFORM 1
#define SMARTUI_CONTACT_LIMIT 200
#define MAX_CONTACTS 200
#define FILE_O_READ "r"
#define FILE_O_WRITE "a"
""" + HARNESS.split("class MyMesh :", 1)[0]
    changes = {
        "unsigned short_write_at = 0;": """
  unsigned short_write_at = 0, truncates = 0;
  bool truncate_fail = false, silent_flush_fail = false, corrupt_prefix = false;
  bool short_read = false, read_fail_after_truncate = false;
  bool truncate_pending = false;
  size_t truncate_size = 0;
""",
        "bool create);": "bool create = false);",
        "count = std::min(count, bytes.size() - pos);": """
    count = std::min(count, bytes.size() - pos);
    if (fs->short_read && count) --count;
""",
        "void flush() { ++fs->flushes; }": """
  bool truncate(uint32_t size) {
    ++fs->truncates;
    if (fs->truncate_fail) return false;
    fs->truncate_pending = true; fs->truncate_size = size; return true;
  }
  void flush() {
    ++fs->flushes;
    if (!fs->truncate_pending) return;
    fs->truncate_pending = false;
    if (!fs->silent_flush_fail) fs->files[path].resize(fs->truncate_size);
    if (fs->corrupt_prefix && !fs->files[path].empty()) fs->files[path][0] ^= 1;
    if (fs->read_fail_after_truncate) fs->read_fail = path;
  }
""",
    }
    for before, after in changes.items():
        assert code.count(before) == 1, before
        code = code.replace(before, after)
    code += function(source, "struct FileDigest") + ";\n"
    for signature in ("static File openStorageRead(", "static bool digestFile(",
                      "static bool fixedRecordFileValid(", "static bool encodedPathLenValid(",
                      "static bool contactRecordFileValid(", "static bool contactPrefixCrc(",
                      "static bool trimContactsToLimit("):
        code += function(source, signature) + "\n"
    return code + r'''
static Bytes contacts(unsigned count) {
  Bytes bytes(count*152, 0);
  for (unsigned i = 0; i < count; ++i) {
    uint8_t* record = bytes.data()+i*152;
    std::memcpy(record, &i, sizeof(i));
    // Names sort in the opposite order: migration must retain file order.
    std::snprintf(reinterpret_cast<char*>(record+32), 32, "name-%03u", 999-i);
    record[64] = ADV_TYPE_CHAT; record[71] = OUT_PATH_UNKNOWN;
  }
  return bytes;
}
int main() {
  static_assert(SMARTUI_CONTACT_LIMIT == MAX_CONTACTS, "limits agree");
  const Bytes original = contacts(350), prefix(original.begin(), original.begin()+200*152);
  for (const char* path : {"/contacts3", "/contacts3.bak", "/contacts3.tmp"}) {
    FakeFS fs; fs.files[path] = original;
    fs.files["/unrelated"] = Bytes(77, 0x55);
    expect(trimContactsToLimit(&fs, path));
    expect(fs.files[path] == prefix && fs.truncates == 1);
    expect(fs.files["/unrelated"] == Bytes(77, 0x55));
    expect(trimContactsToLimit(&fs, path));
    expect(fs.files[path] == prefix && fs.truncates == 1);
  }
  for (unsigned count : {0U, 1U, 199U, 200U}) {
    FakeFS fs; fs.files["/contacts3"] = contacts(count);
    const auto before = fs.files;
    expect(trimContactsToLimit(&fs, "/contacts3"));
    expect(fs.files == before && fs.truncates == 0);
  }
  for (unsigned fault = 0; fault < 6; ++fault) {
    FakeFS fs; fs.files["/contacts3"] = original;
    if (fault == 0) fs.truncate_fail = true;
    if (fault == 1) fs.silent_flush_fail = true;
    if (fault == 2) fs.short_read = true;
    if (fault == 3) fs.read_fail = "/contacts3";
    if (fault == 4) fs.open_fail = "/contacts3";
    if (fault == 5) fs.files["/contacts3"][64] = 0;
    const auto before = fs.files;
    expect(!trimContactsToLimit(&fs, "/contacts3"));
    expect(fs.files == before);
    // Repairing a transient fault allows the exact same migration to finish.
    fs.truncate_fail = fs.silent_flush_fail = fs.short_read = false;
    fs.read_fail.clear(); fs.open_fail.clear(); fs.files["/contacts3"] = original;
    expect(trimContactsToLimit(&fs, "/contacts3"));
    expect(fs.files["/contacts3"] == prefix);
  }
  for (bool corrupt : {false, true}) {
    FakeFS fs; fs.files["/contacts3"] = original;
    fs.corrupt_prefix = corrupt; fs.read_fail_after_truncate = !corrupt;
    expect(!trimContactsToLimit(&fs, "/contacts3"));
    expect(fs.truncates == 1);
    expect(fs.files["/contacts3"].size() == 200*152);
  }
  {
    FakeFS fs; fs.files["/contacts3"] = original;
    uint32_t expected_crc = 0, retry_crc = 0; bool retry_pending = false;
    expect(contactPrefixCrc(&fs, "/contacts3", 200*152, expected_crc));
    fs.corrupt_prefix = true;
    expect(!trimContactsToLimit(&fs, "/contacts3", &retry_crc, &retry_pending));
    expect(retry_pending && retry_crc == expected_crc && fs.truncates == 1);
    expect(fs.files["/contacts3"].size() == 200*152 && fs.files["/contacts3"] != prefix);
    // Fitting the new limit cannot make corrupted data an accepted baseline.
    for (unsigned attempt = 0; attempt < 3; ++attempt) {
      expect(!trimContactsToLimit(&fs, "/contacts3", &retry_crc, &retry_pending));
      expect(retry_pending && retry_crc == expected_crc && fs.truncates == 1);
    }
    fs.files["/contacts3"] = prefix;
    expect(trimContactsToLimit(&fs, "/contacts3", &retry_crc, &retry_pending));
    expect(!retry_pending && retry_crc == expected_crc && fs.truncates == 1);
  }
  {
    FakeFS fs; fs.files["/contacts3"] = original;
    uint32_t expected_crc = 0, retry_crc = 0; bool retry_pending = false;
    expect(contactPrefixCrc(&fs, "/contacts3", 200*152, expected_crc));
    fs.read_fail_after_truncate = true;
    expect(!trimContactsToLimit(&fs, "/contacts3", &retry_crc, &retry_pending));
    expect(retry_pending && retry_crc == expected_crc && fs.files["/contacts3"] == prefix);
    expect(!trimContactsToLimit(&fs, "/contacts3", &retry_crc, &retry_pending));
    expect(retry_pending && retry_crc == expected_crc && fs.truncates == 1);
    fs.read_fail.clear();
    expect(trimContactsToLimit(&fs, "/contacts3", &retry_crc, &retry_pending));
    expect(!retry_pending && retry_crc == expected_crc && fs.truncates == 1);
  }
  {
    FakeFS fs; fs.files["/contacts3"] = original;
    uint32_t expected_crc = 0, retry_crc = 0; bool retry_pending = false;
    expect(contactPrefixCrc(&fs, "/contacts3", 200*152, expected_crc));
    fs.silent_flush_fail = true;
    expect(!trimContactsToLimit(&fs, "/contacts3", &retry_crc, &retry_pending));
    expect(retry_pending && retry_crc == expected_crc && fs.files["/contacts3"] == original);
    // Even a retry of the original-sized file must retain the old checksum.
    fs.files["/contacts3"][0] ^= 1; fs.silent_flush_fail = false;
    expect(!trimContactsToLimit(&fs, "/contacts3", &retry_crc, &retry_pending));
    expect(retry_pending && retry_crc == expected_crc && fs.truncates == 1);
    fs.files["/contacts3"] = original;
    expect(trimContactsToLimit(&fs, "/contacts3", &retry_crc, &retry_pending));
    expect(!retry_pending && retry_crc == expected_crc && fs.files["/contacts3"] == prefix);
  }
  {
    FakeFS fs; uint32_t crc = 0;
    expect(!trimContactsToLimit(&fs, "/contacts3"));
    fs.files["/contacts3"] = prefix; fs.files["/contacts3"].pop_back();
    expect(!contactPrefixCrc(&fs, "/contacts3", 200*152, crc));
    expect(fs.truncates == 0);
  }
  std::printf("PASS %u production migration assertions: first200 file order, all candidates, idempotence, failed truncate/flush/read, CRC mismatch retained across retries\n", checks);
}
'''


def run_native():
    with tempfile.TemporaryDirectory(prefix="contact-migration-") as directory:
        directory = Path(directory)
        cpp, binary = directory / "test.cpp", directory / "test"
        cpp.write_text(native_source(), encoding="utf-8")
        compiler = shutil.which("g++")
        prefix = [] if compiler else ["wsl", "--exec"]
        path = str if compiler else linux
        subprocess.run([*prefix, compiler or "g++", "-std=c++17", "-Wall", "-Wextra",
                        "-Werror", "-pedantic", "-O2", "-I", path(ROOT / "src"),
                        path(cpp), "-o", path(binary)], check=True, timeout=60)
        subprocess.run([*prefix, path(binary)], check=True, timeout=30)


CODE = r'''
#include <assert.h>
#include <setjmp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "lfs.h"

static unsigned char disk[100*1024], baseline[100*1024];
static unsigned char read_buffer[128], prog_buffer[128], lookahead_buffer[16], file_buffer[128];
static jmp_buf power_cut;
static unsigned operations, cut_operation, cut_phase;
static lfs_t mounted;
void* pvPortMalloc(size_t size) { return malloc(size); }
void vPortFree(void* pointer) { free(pointer); }

static int rd(const struct lfs_config* cfg, lfs_block_t block, lfs_off_t off,
              void* buffer, lfs_size_t length) {
  (void)cfg; memcpy(buffer, disk + block*128 + off, length); return 0;
}
static void mutate(unsigned char* destination, const void* source,
                   lfs_size_t length, int erase) {
  ++operations;
  const int trigger = cut_operation && operations == cut_operation;
  if (trigger && cut_phase == 0) longjmp(power_cut, 1);
  const lfs_size_t written = trigger && cut_phase == 1 ? length/2 : length;
  if (erase) memset(destination, 255, written);
  else memcpy(destination, source, written);
  if (trigger) longjmp(power_cut, 1);
}
static int wr(const struct lfs_config* cfg, lfs_block_t block, lfs_off_t off,
              const void* buffer, lfs_size_t length) {
  (void)cfg; mutate(disk + block*128 + off, buffer, length, 0); return 0;
}
static int er(const struct lfs_config* cfg, lfs_block_t block) {
  (void)cfg; mutate(disk + block*128, NULL, 128, 1); return 0;
}
static int sy(const struct lfs_config* cfg) { (void)cfg; return 0; }
static const struct lfs_config cfg = {
  .read=rd, .prog=wr, .erase=er, .sync=sy,
  .read_size=128, .prog_size=128, .block_size=128, .block_count=800,
  .lookahead=128, .read_buffer=read_buffer, .prog_buffer=prog_buffer,
  .lookahead_buffer=lookahead_buffer, .file_buffer=file_buffer,
};

static void mount_disk(void) {
  memset(&mounted, 0, sizeof(mounted));
  memset(read_buffer, 0, sizeof(read_buffer)); memset(prog_buffer, 0, sizeof(prog_buffer));
  memset(lookahead_buffer, 0, sizeof(lookahead_buffer)); memset(file_buffer, 0, sizeof(file_buffer));
  assert(lfs_mount(&mounted, &cfg) == 0);
}
static void record_bytes(unsigned index, unsigned generation, unsigned char record[152]) {
  memset(record, 0, 152);
  for (unsigned i = 0; i < 32; ++i) record[i] = (unsigned char)(index*13 + i*7);
  memcpy(record, &index, sizeof(index));
  snprintf((char*)record+32, 32, "contact-%03u-g%u", index, generation);
  record[64] = 1; record[65] = index & 1; record[71] = 0xff;
  memcpy(record+140, &index, sizeof(index));
}
static int write_contacts(const char* path, unsigned count, unsigned generation) {
  lfs_file_t file;
  int err = lfs_file_open(&mounted, &file, path, LFS_O_RDWR|LFS_O_CREAT|LFS_O_TRUNC);
  if (err) return err;
  for (unsigned i = 0; i < count; ++i) {
    unsigned char record[152]; record_bytes(i, generation, record);
    int written = lfs_file_write(&mounted, &file, record, sizeof(record));
    if (written != sizeof(record)) { err = written < 0 ? written : -999; break; }
  }
  int synced = lfs_file_sync(&mounted, &file);
  int closed = lfs_file_close(&mounted, &file);
  return err ? err : (synced ? synced : closed);
}
static unsigned verify_contacts(const char* path, unsigned generation) {
  lfs_file_t file; assert(lfs_file_open(&mounted, &file, path, LFS_O_RDONLY) == 0);
  int bytes = lfs_file_size(&mounted, &file);
  assert(bytes == 200*152 || bytes == 350*152);
  for (unsigned i = 0; i < (unsigned)bytes/152; ++i) {
    unsigned char expected[152], actual[152]; record_bytes(i, generation, expected);
    assert(lfs_file_read(&mounted, &file, actual, sizeof(actual)) == sizeof(actual));
    assert(memcmp(actual, expected, sizeof(actual)) == 0);
  }
  assert(lfs_file_close(&mounted, &file) == 0);
  return (unsigned)bytes/152;
}
static void fill_file(const char* path, unsigned size, unsigned char value) {
  lfs_file_t file; assert(lfs_file_open(&mounted, &file, path, LFS_O_RDWR|LFS_O_CREAT) == 0);
  for (unsigned i = 0; i < size; ++i) assert(lfs_file_write(&mounted, &file, &value, 1) == 1);
  assert(lfs_file_sync(&mounted, &file) == 0); assert(lfs_file_close(&mounted, &file) == 0);
}
static void verify_file(const char* path, unsigned size, unsigned char value) {
  lfs_file_t file; assert(lfs_file_open(&mounted, &file, path, LFS_O_RDONLY) == 0);
  assert(lfs_file_size(&mounted, &file) == size);
  for (unsigned i = 0; i < size; ++i) {
    unsigned char actual; assert(lfs_file_read(&mounted, &file, &actual, 1) == 1);
    assert(actual == value);
  }
  assert(lfs_file_close(&mounted, &file) == 0);
}
static void verify_other_files(void) {
  verify_file("/adv_blobs", 18000, 'A');
  verify_file("/channels2", 2720, 'C');
  verify_file("/channels2.bak", 2720, 'B');
  verify_file("/channels2.tmp", 2720, 'T');
}
static uint32_t prefix_crc(const char* path) {
  lfs_file_t file; assert(lfs_file_open(&mounted, &file, path, LFS_O_RDONLY) == 0);
  uint32_t crc = 0xffffffffu;
  for (unsigned i = 0; i < 200*152; ++i) {
    unsigned char value; assert(lfs_file_read(&mounted, &file, &value, 1) == 1);
    crc ^= value;
    for (unsigned bit = 0; bit < 8; ++bit) crc = (crc >> 1) ^ (0xedb88320u & (0u-(crc&1u)));
  }
  assert(lfs_file_close(&mounted, &file) == 0);
  return crc ^ 0xffffffffu;
}
static void trim_to_200(const char* path) {
  uint32_t before = prefix_crc(path);
  lfs_file_t file; assert(lfs_file_open(&mounted, &file, path, LFS_O_RDWR) == 0);
  assert(lfs_file_truncate(&mounted, &file, 200*152) == 0);
  assert(lfs_file_sync(&mounted, &file) == 0);
  assert(lfs_file_close(&mounted, &file) == 0);
  assert(prefix_crc(path) == before);
}
static void finish_and_save(const char* source) {
  trim_to_200(source); assert(verify_contacts(source, 0) == 200);
  if (strcmp(source, "/contacts3")) assert(lfs_rename(&mounted, source, "/contacts3") == 0);
  // A normal complete snapshot now fits next to the truncated primary.
  assert(write_contacts("/contacts3.tmp", 200, 1) == 0);
  assert(verify_contacts("/contacts3.tmp", 1) == 200);
  assert(lfs_rename(&mounted, "/contacts3", "/contacts3.bak") == 0);
  assert(lfs_rename(&mounted, "/contacts3.tmp", "/contacts3") == 0);
  assert(lfs_unmount(&mounted) == 0); mount_disk();
  assert(verify_contacts("/contacts3", 1) == 200);
  assert(verify_contacts("/contacts3.bak", 0) == 200);
  verify_other_files(); assert(lfs_unmount(&mounted) == 0);
}
int main(void) {
  assert(LFS_VERSION == 0x00010007);
  const char* candidates[] = {"/contacts3", "/contacts3.bak", "/contacts3.tmp"};
  unsigned total_cuts = 0, old_states = 0, trimmed_states = 0;
  for (unsigned candidate = 0; candidate < 3; ++candidate) {
    const char* source = candidates[candidate];
    cut_operation = 0; memset(disk, 255, sizeof(disk));
    assert(lfs_format(&mounted, &cfg) == 0); mount_disk();
    fill_file("/adv_blobs", 18000, 'A'); fill_file("/channels2", 2720, 'C');
    fill_file("/channels2.bak", 2720, 'B'); fill_file("/channels2.tmp", 2720, 'T');
    assert(write_contacts(source, 350, 0) == 0);
    assert(verify_contacts(source, 0) == 350); assert(lfs_unmount(&mounted) == 0);
    memcpy(baseline, disk, sizeof(disk));
    mount_disk(); operations = 0; trim_to_200(source);
    const unsigned mutation_count = operations;
    assert(mutation_count > 0); finish_and_save(source);

    for (unsigned point = 1; point <= mutation_count; ++point) {
      for (unsigned phase = 0; phase < 3; ++phase) {
        memcpy(disk, baseline, sizeof(disk)); cut_operation = 0; mount_disk();
        operations = 0; cut_operation = point; cut_phase = phase;
        if (setjmp(power_cut) == 0) {
          trim_to_200(source);
          assert(!"expected simulated power cut");
        }
        // Discard every live filesystem/file cache, just like a reboot.
        cut_operation = 0; mount_disk();
        unsigned records = verify_contacts(source, 0);
        if (records == 350) ++old_states; else ++trimmed_states;
        verify_other_files(); finish_and_save(source); ++total_cuts;
      }
    }
    printf("PASS %s: %u program/erase operations x 3 cut phases; old350 or exact first200; completion+save200 survives\n",
           source, mutation_count);
  }
  assert(old_states > 0 && trimmed_states > 0);
  printf("PASS %u power cuts: old350=%u, first200=%u; full advert/channel files preserved\n",
         total_cuts, old_states, trimmed_states);
  return 0;
}
'''


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--littlefs", action="store_true")
    args = parser.parse_args()
    run_native()
    if args.littlefs:
        real.CODE = CODE
        real.main()
