#!/usr/bin/env python3
"""Contact transaction quota/fault tests, executing the production C++ writer.

The default test needs only a host C++ compiler (or WSL on Windows).
--littlefs additionally requires the installed pinned Adafruit littlefs1 library;
absence is an error, never a silent skip. No board or persistent storage is used.
"""
from pathlib import Path
import argparse
import configparser
import re
import shlex
import shutil
import subprocess
import tempfile

from test_contact_persistence import HARNESS, ROOT, function, linux


def production():
    source = (ROOT / "examples/companion_radio/DataStore.cpp").read_text(encoding="utf-8")
    names = ("static bool prepareScratch(", "static File openScratch(",
             "static File openStorageRead(", "static bool digestFile(",
             "static bool commitScratch(", "static bool fixedRecordFileValid(",
             "static bool encodedPathLenValid(", "static bool contactRecordFileValid(",
             "bool DataStore::saveContacts(")
    return function(source, "struct FileDigest") + ";\n" + "\n".join(
        function(source, name) for name in names)


def quota_harness():
    code = HARNESS.split("class MyMesh :", 1)[0]
    changes = {
        "unsigned short_write_at = 0;": """
  unsigned short_write_at = 0;
  size_t capacity = static_cast<size_t>(-1);
  unsigned scratch_opens = 0, backup_removes = 0, fail_scratch_opens = 0;
  bool corrupt_scratch = false, truncate_scratch = false;
  size_t used() const {
    size_t total = 0;
    for (const auto& entry : files) total += entry.second.size();
    return total;
  }
""",
        "return files.erase(path) != 0;": """
    if (std::string(path) == "/contacts3.bak") {
      ++backup_removes;
      // The failed scratch must be gone before reclaiming recovery data.
      // A successful commit is the exception: its complete scratch is live.
    }
    return files.erase(path) != 0;
""",
        "auto& bytes = fs->files[path];\n    bytes.insert": """
    const size_t used = fs->used();
    count = std::min(count, used < fs->capacity ? fs->capacity - used : size_t(0));
    auto& bytes = fs->files[path];
    bytes.insert""",
        "void flush() { ++fs->flushes; }": """
  void flush() {
    ++fs->flushes;
    auto& bytes = fs->files[path];
    if (path == "/contacts3.tmp" && !bytes.empty()) {
      if (fs->corrupt_scratch) bytes[0] ^= 1;
      if (fs->truncate_scratch) bytes.pop_back();
    }
  }
""",
        "if (path == open_fail) return {};": """
  if (std::string(path) == "/contacts3.tmp" && mode[0] == 'w') {
    ++scratch_opens;
    if (fail_scratch_opens) { --fail_scratch_opens; return {}; }
  }
  if (path == open_fail) return {};
""",
    }
    for before, after in changes.items():
        assert code.count(before) == 1, before
        code = code.replace(before, after)
    return code


HOST = r'''
struct Host : DataStoreHost {
  std::vector<ContactInfo> contacts;
  explicit Host(unsigned count) {
    for (unsigned i = 0; i < count; ++i) {
      ContactInfo c;
      std::memcpy(c.id.pub_key, &i, sizeof(i));
      std::snprintf(c.name, sizeof(c.name), "contact %u", i);
      contacts.push_back(c);
    }
  }
  bool getContactForSave(uint32_t idx, ContactInfo& c) override {
    if (idx >= contacts.size()) return false;
    c = contacts[idx]; return true;
  }
};
'''


QUOTA_TESTS = r'''
struct Fixture {
  Host host{200};
  FakeFS fs;
  DataStore store{fs};
  Bytes primary, backup;
  Fixture() {
    expect(store.saveContacts(&host));
    primary = fs.files["/contacts3"];
    backup = primary; backup[0] ^= 0x40;
    fs.files["/contacts3.bak"] = backup;
    fs.files["/unrelated"] = Bytes(77, 0x55);
    std::strcpy(host.contacts[0].name, "changed");
    fs.scratch_opens = fs.backup_removes = 0;
  }
  void tight() { fs.capacity = primary.size() * 2 + 77; }
  void unchanged() {
    expect(fs.files["/contacts3"] == primary);
    expect(fs.files["/contacts3.bak"] == backup);
    expect(fs.files["/unrelated"] == Bytes(77, 0x55));
  }
};
int main() {
  // A transient read/open failure is not proof that the sole remaining file
  // is corrupt. Do not erase scratch or replace an unreadable primary/backup.
  for (int fault = 0; fault < 5; ++fault) {
    Fixture f;
    f.fs.files.erase("/contacts3");
    f.fs.files.erase("/contacts3.bak");
    f.fs.files["/contacts3.tmp"] = f.primary;
    if (fault == 0) f.fs.read_fail = "/contacts3.tmp";
    if (fault == 1) f.fs.open_fail = "/contacts3.tmp";
    if (fault == 2) {
      f.fs.files["/contacts3"] = f.primary;
      f.fs.read_fail = "/contacts3";
    }
    if (fault == 3) {
      f.fs.files["/contacts3.bak"] = f.backup;
      f.fs.read_fail = "/contacts3.bak";
    }
    if (fault == 4) f.fs.size_mismatch = "/contacts3.tmp";
    const auto before = f.fs.files;
    f.fs.writes = f.fs.rename_calls = 0;
    expect(!f.store.saveContacts(&f.host));
    expect(f.fs.files == before);
    expect(f.fs.writes == 0 && f.fs.scratch_opens == 0 && f.fs.rename_calls == 0);
  }
  // A fully readable but structurally invalid first scratch may be discarded.
  for (int fault = 0; fault < 2; ++fault) {
    Fixture f;
    f.fs.files.erase("/contacts3");
    f.fs.files.erase("/contacts3.bak");
    f.fs.files["/contacts3.tmp"] = fault == 0 ? Bytes(1, 0x55) : f.primary;
    if (fault == 1) f.fs.files["/contacts3.tmp"][64] = 0;
    expect(f.store.saveContacts(&f.host));
    expect(f.fs.files["/contacts3"].size() == f.primary.size());
    expect(std::strcmp(reinterpret_cast<const char*>(f.fs.files["/contacts3"].data()+32), "changed") == 0);
    expect(!f.fs.exists("/contacts3.tmp"));
  }
  // An unreadable primary is not known-bad when publishing a new generation.
  // A subsequent rename failure must not turn the read fault into data loss.
  {
    Fixture f;
    f.fs.files.erase("/contacts3.bak");
    f.fs.read_fail = "/contacts3";
    f.fs.rename_fail_source = "/contacts3.tmp";
    f.fs.rename_calls = 0;
    const auto before = f.fs.files;
    expect(!f.store.saveContacts(&f.host));
    expect(f.fs.files == before);
    expect(f.fs.rename_calls == 0 && f.fs.scratch_opens == 1);
  }
  // A recovered scratch may be the only readable generation. The writer must
  // publish it before reusing its path, including when the next write fails.
  for (int fault = 0; fault < 4; ++fault) {
    Fixture f;
    f.fs.files.erase("/contacts3");
    f.fs.files.erase("/contacts3.bak");
    f.fs.files["/contacts3.tmp"] = f.primary;
    if (fault == 0) f.fs.fail_scratch_opens = 1;
    if (fault == 1) f.fs.rename_fail_source = "/contacts3.tmp";
    if (fault == 2) {
      f.fs.files["/contacts3"] = Bytes(1, 0x55);
      f.fs.remove_fail = "/contacts3";
    }
    const auto before = f.fs.files;
    const bool saved = f.store.saveContacts(&f.host);
    if (fault == 3) {
      expect(saved);
      expect(f.fs.files["/contacts3.bak"] == f.primary);
      expect(f.fs.files["/contacts3"].size() == f.primary.size());
      expect(std::strcmp(reinterpret_cast<const char*>(f.fs.files["/contacts3"].data()+32), "changed") == 0);
      expect(!f.fs.exists("/contacts3.tmp"));
      expect(f.fs.scratch_opens == 1);
    } else if (fault == 0) {
      expect(!saved);
      expect(f.fs.files["/contacts3"] == f.primary);
      expect(!f.fs.exists("/contacts3.tmp"));
      expect(f.fs.scratch_opens == 1);
    } else {
      expect(!saved);
      expect(f.fs.files == before);
      expect(f.fs.scratch_opens == 0);
    }
    expect(f.fs.files["/unrelated"] == Bytes(77, 0x55));
  }
  {
    Fixture f; f.tight();
    expect(f.store.saveContacts(&f.host));
    expect(f.fs.scratch_opens == 2 && f.fs.backup_removes == 1);
    expect(f.fs.files["/contacts3.bak"] == f.primary);
    expect(f.fs.files["/contacts3"].size() == f.primary.size());
    expect(std::strcmp(reinterpret_cast<const char*>(f.fs.files["/contacts3"].data()+32), "changed") == 0);
    expect(!f.fs.exists("/contacts3.tmp"));
    expect(f.fs.files["/unrelated"] == Bytes(77, 0x55));
  }
  {
    Fixture f; f.fs.fail_scratch_opens = 1;
    expect(f.store.saveContacts(&f.host));
    expect(f.fs.scratch_opens == 2 && f.fs.files["/contacts3.bak"] == f.primary);
  }
  // A complete primary is required before deleting any recovery copy.
  for (int fault = 0; fault < 6; ++fault) {
    Fixture f; f.tight();
    if (fault == 0) f.fs.files.erase("/contacts3");
    if (fault == 1) f.fs.files["/contacts3"].pop_back();
    if (fault == 2) f.fs.files["/contacts3"][64] = 0;
    if (fault == 3) std::memset(f.fs.files["/contacts3"].data()+32, 'X', 32);
    if (fault == 4) f.fs.files["/contacts3"][71] = 0xC1;
    if (fault == 5) f.fs.read_fail = "/contacts3";
    const auto damaged_files = f.fs.files;
    f.fs.fail_scratch_opens = 1;
    expect(!f.store.saveContacts(&f.host));
    expect(f.fs.files == damaged_files);
    expect(f.fs.scratch_opens == 1 && f.fs.backup_removes == 0);
  }
  // A failed cleanup cannot justify deleting the backup.
  {
    Fixture f; f.tight(); f.fs.remove_fail = "/contacts3.tmp";
    expect(!f.store.saveContacts(&f.host)); f.unchanged();
    expect(f.fs.backup_removes == 0 && f.fs.scratch_opens == 1);
  }
  {
    Fixture f; f.tight(); f.fs.remove_fail = "/contacts3.bak";
    expect(!f.store.saveContacts(&f.host)); f.unchanged();
    expect(f.fs.scratch_opens == 1 && !f.fs.exists("/contacts3.tmp"));
  }
  // Read faults and same-length corruption must never trigger reclaim.
  for (int fault = 0; fault < 3; ++fault) {
    Fixture f;
    if (fault == 0) f.fs.read_fail = "/contacts3.tmp";
    if (fault == 1) f.fs.corrupt_scratch = true;
    if (fault == 2) f.fs.size_mismatch = "/contacts3.tmp";
    expect(!f.store.saveContacts(&f.host)); f.unchanged();
    expect(f.fs.backup_removes == 0 && f.fs.scratch_opens == 1);
    expect(!f.fs.exists("/contacts3.tmp"));
  }
  // A delayed short flush can retry once, but must not report success.
  {
    Fixture f; f.fs.truncate_scratch = true;
    expect(!f.store.saveContacts(&f.host));
    expect(f.fs.scratch_opens == 2 && f.fs.backup_removes == 1);
    expect(f.fs.files["/contacts3"] == f.primary);
    expect(!f.fs.exists("/contacts3.tmp"));
  }
  // If even two copies cannot fit, fail honestly and retain the primary.
  {
    Fixture f; f.fs.capacity = f.primary.size() + 77;
    expect(!f.store.saveContacts(&f.host));
    expect(f.fs.files["/contacts3"] == f.primary);
    expect(f.fs.scratch_opens == 2 && !f.fs.exists("/contacts3.tmp"));
  }
  // A commit/rename failure does not run the capacity retry.
  {
    Fixture f; f.fs.rename_fail_source = "/contacts3.tmp";
    expect(!f.store.saveContacts(&f.host));
    expect(f.fs.files["/contacts3"] == f.primary);
    expect(f.fs.scratch_opens == 1 && !f.fs.exists("/contacts3.tmp"));
  }
  std::printf("PASS %u contacts quota/fault assertions: one reclaim, primary/backup safety, payload CRC, bounded failure\n", checks);
}
'''


def run_quota():
    with tempfile.TemporaryDirectory(prefix="contact-capacity-") as folder:
        folder = Path(folder)
        cpp, binary = folder / "test.cpp", folder / "test"
        cpp.write_text(quota_harness() + production() + HOST + QUOTA_TESTS, encoding="utf-8")
        compiler = shutil.which("g++")
        prefix = [] if compiler else ["wsl", "--exec"]
        path = str if compiler else linux
        subprocess.run([*prefix, compiler or "g++", "-std=c++17", "-Wall", "-Wextra",
                        "-Werror", "-pedantic", "-O2", "-I", path(ROOT / "src"),
                        path(cpp), "-o", path(binary)], check=True, timeout=60)
        subprocess.run([*prefix, path(binary)], check=True, timeout=30)


def check_profiles():
    config = configparser.ConfigParser(interpolation=None, strict=False,
                                       inline_comment_prefixes=(";",))
    config.read([ROOT / "platformio.ini", ROOT / "platformio.smartui-headless.ini",
                 *sorted((ROOT / "variants").glob("*/platformio.ini"))], encoding="utf-8")

    def resolve(section, option):
        if not config.has_option(section, option):
            for parent in re.split(r"[,\n]+", config[section].get("extends", "")):
                if parent.strip():
                    value = resolve(parent.strip(), option)
                    if value:
                        return value
            return ""
        return re.sub(r"\$\{([^}]+)\}", lambda match:
                      resolve(*match[1].rsplit(".", 1)), config[section][option])

    def defines(text):
        tokens = iter(shlex.split(text))
        for token in tokens:
            if token == "-D":
                token += next(tokens)
            if token.startswith("-D"):
                yield token[2:]

    limits = {
        "Heltec_t096_companion_radio_ble_femon": 200,
        "Heltec_t096_companion_radio_ble_femoff": 200,
        "SmartUI_T096_headless": 200,
        "Heltec_t114_companion_radio_ble": 200,
        "SmartUI_T114_headless": 200,
        "ProMicro_ra62_companion_radio_ble": 200,
        "SmartUI_ProMicro_headless": 200,
        "Heltec_t096_companion_radio_usb": 350,
        "Heltec_t114_without_display_companion_radio_ble": 350,
        "Heltec_t114_without_display_companion_radio_usb": 350,
        "Heltec_t114_companion_radio_usb": 350,
        "ProMicro_companion_radio_ble": 350,
        "ProMicro_companion_radio_usb": 350,
        "Heltec_v3_companion_radio_ble_smartui": 350,
        "heltec_v4_3_companion_radio_ble_femon_smartui": 350,
        "Heltec_Wireless_Paper_companion_radio_ble_smartui_full": 350,
        "heltec_v4_r8_companion_radio_ble_femon_smartui": 350,
    }
    for env, expected in limits.items():
        section = "env:" + env
        removed = set(defines(resolve(section, "build_unflags")))
        active = [value for value in defines(resolve(section, "build_flags"))
                  if value.startswith("MAX_CONTACTS=") and value not in removed]
        assert active == [f"MAX_CONTACTS={expected}"], (env, active, expected)
        migration = [value for value in defines(resolve(section, "build_flags"))
                     if value.startswith("SMARTUI_CONTACT_LIMIT=") and value not in removed]
        assert migration == (["SMARTUI_CONTACT_LIMIT=200"] if expected == 200 else []), (env, migration)
    print("PASS contact limits: four nRF release profiles and inherited variants use 200; independent profiles unchanged")


def run_littlefs():
    # Reuse the pinned littlefs1 RAM-disk/compiler setup; keep this optional
    # hardware-library reproduction separate from the required quota tests.
    import test_littlefs_prefs_capacity as real
    prefix = real.CODE.split("int main(void)", 1)[0]
    prefix = prefix.replace("disk[28*1024]", "disk[100*1024]").replace(
        ".block_count=224", ".block_count=800")
    real.CODE = prefix + r'''
static int exists(lfs_t* l, const char* path) {
  struct lfs_info info;
  return lfs_stat(l, path, &info) == 0;
}
static unsigned reclaim_retries = 0;
// Capacity model of the production scratch/reclaim/rotate sequence. The
// mandatory quota harness above runs the actual writer and its validators.
static int save_contacts(lfs_t* l, size_t records, unsigned char value) {
  for (unsigned attempt = 0; attempt < 2; ++attempt) {
    if (exists(l, "/contacts3.tmp")) assert(lfs_remove(l, "/contacts3.tmp") == 0);
    int err = put(l, "/contacts3.tmp", records*152, value);
    if (!err) {
      verify(l, "/contacts3.tmp", records*152, value);
      if (exists(l, "/contacts3.bak")) assert(lfs_remove(l, "/contacts3.bak") == 0);
      if (exists(l, "/contacts3")) assert(lfs_rename(l, "/contacts3", "/contacts3.bak") == 0);
      return lfs_rename(l, "/contacts3.tmp", "/contacts3");
    }
    if (exists(l, "/contacts3.tmp")) assert(lfs_remove(l, "/contacts3.tmp") == 0);
    if (attempt || !exists(l, "/contacts3") || !exists(l, "/contacts3.bak")) return err;
    assert(lfs_remove(l, "/contacts3.bak") == 0);
    ++reclaim_retries;
  }
  return -999;
}
static void verify_other_files(lfs_t* l) {
  verify(l, "/adv_blobs", 18000, 'A');
  verify(l, "/channels2", 2720, 'C');
  verify(l, "/channels2.bak", 2720, 'B');
  verify(l, "/channels2.tmp", 2720, 'T');
}
static void exercise_200_contacts(void) {
  memset(disk, 255, sizeof(disk)); lfs_t l = {0};
  assert(lfs_format(&l, &cfg) == 0); assert(lfs_mount(&l, &cfg) == 0);
  assert(put(&l, "/adv_blobs", 18000, 'A') == 0);
  assert(put(&l, "/channels2", 2720, 'C') == 0);
  assert(put(&l, "/channels2.bak", 2720, 'B') == 0);
  // Include even a third channel generation left by an interrupted save.
  assert(put(&l, "/channels2.tmp", 2720, 'T') == 0);
  assert(save_contacts(&l, 200, 'P') == 0);
  assert(save_contacts(&l, 200, 'Q') == 0);
  for (unsigned i = 0; i < 12; ++i) {
    assert(save_contacts(&l, 200, 'R'+i) == 0);
    assert(lfs_unmount(&l) == 0); assert(lfs_mount(&l, &cfg) == 0);
    verify(&l, "/contacts3", 200*152, 'R'+i);
    verify(&l, "/contacts3.bak", 200*152, i ? 'R'+i-1 : 'Q');
    verify_other_files(&l);
  }
  assert(reclaim_retries == 12);
  puts("PASS 200 contacts: 12 dirty updates/reclaims/remounts; full adv_blobs and three 40-channel generations preserved");
  assert(save_contacts(&l, 199, 'D') == 0);
  assert(lfs_unmount(&l) == 0); assert(lfs_mount(&l, &cfg) == 0);
  verify(&l, "/contacts3", 199*152, 'D'); verify_other_files(&l);
  assert(save_contacts(&l, 0, 'E') == 0);
  assert(lfs_unmount(&l) == 0); assert(lfs_mount(&l, &cfg) == 0);
  verify(&l, "/contacts3", 0, 'E'); verify_other_files(&l);
  assert(save_contacts(&l, 200, 'N') == 0);
  assert(lfs_unmount(&l) == 0); assert(lfs_mount(&l, &cfg) == 0);
  verify(&l, "/contacts3", 200*152, 'N'); verify_other_files(&l);
  assert(lfs_unmount(&l) == 0);
  puts("PASS 200 -> 199 delete, 199 -> 0 empty, 0 -> 200 refill with remounts");

  // A reduced RAM limit is not a migration: the old full list still occupies
  // flash while the new snapshot is staged. Failure must retain the old file.
  memset(disk, 255, sizeof(disk)); memset(&l, 0, sizeof(l));
  assert(lfs_format(&l, &cfg) == 0); assert(lfs_mount(&l, &cfg) == 0);
  assert(put(&l, "/adv_blobs", 18000, 'A') == 0);
  assert(put(&l, "/channels2", 2720, 'C') == 0);
  assert(put(&l, "/channels2.bak", 2720, 'B') == 0);
  assert(put(&l, "/contacts3", 350*152, 'O') == 0);
  assert(save_contacts(&l, 200, 'M') == LFS_ERR_NOSPC);
  assert(!exists(&l, "/contacts3.tmp"));
  assert(lfs_unmount(&l) == 0); assert(lfs_mount(&l, &cfg) == 0);
  verify(&l, "/contacts3", 350*152, 'O');
  verify(&l, "/adv_blobs", 18000, 'A');
  verify(&l, "/channels2", 2720, 'C'); verify(&l, "/channels2.bak", 2720, 'B');
  assert(lfs_unmount(&l) == 0);
  puts("PASS legacy 350 -> 200 copy cannot fit; NOSPC retains all 350 original records");
}
int main(void) {
  assert(LFS_VERSION == 0x00010007);
  exercise_200_contacts();
  // The production ExtraFS is 100 KiB, with a preallocated 100*180-byte
  // adv_blobs file and up to 40*68-byte channels2 primary/backup generations.
  size_t counts[] = {100, 150, 180, 200, 250, 300, 320, 350};
  int reclaim_case = 0, impossible_case = 0;
  for (unsigned i = 0; i < sizeof(counts)/sizeof(counts[0]); ++i) {
    const size_t bytes = counts[i]*152;
    memset(disk, 255, sizeof(disk)); lfs_t l = {0};
    assert(lfs_format(&l, &cfg) == 0); assert(lfs_mount(&l, &cfg) == 0);
    assert(put(&l, "/adv_blobs", 18000, 'A') == 0);
    assert(put(&l, "/channels2", 2720, 'C') == 0);
    assert(put(&l, "/channels2.bak", 2720, 'B') == 0);
    int primary = put(&l, "/contacts3", bytes, 'P');
    int backup = put(&l, "/contacts3.bak", bytes, 'B');
    int scratch = put(&l, "/contacts3.tmp", bytes, 'N');
    int retry = -999;
    if (!primary && !backup && scratch == LFS_ERR_NOSPC) {
      assert(lfs_remove(&l, "/contacts3.tmp") == 0);
      verify(&l, "/contacts3", bytes, 'P');
      assert(lfs_remove(&l, "/contacts3.bak") == 0);
      // Reboot between reclaim and retry must keep the valid primary.
      assert(lfs_unmount(&l) == 0); assert(lfs_mount(&l, &cfg) == 0);
      verify(&l, "/contacts3", bytes, 'P');
      retry = put(&l, "/contacts3.tmp", bytes, 'N');
      if (!retry) {
        verify(&l, "/contacts3.tmp", bytes, 'N');
        assert(lfs_rename(&l, "/contacts3", "/contacts3.bak") == 0);
        assert(lfs_rename(&l, "/contacts3.tmp", "/contacts3") == 0);
        assert(lfs_unmount(&l) == 0); assert(lfs_mount(&l, &cfg) == 0);
        verify(&l, "/contacts3", bytes, 'N');
        verify(&l, "/contacts3.bak", bytes, 'P');
        ++reclaim_case;
      }
    }
    verify(&l, "/adv_blobs", 18000, 'A');
    verify(&l, "/channels2", 2720, 'C');
    verify(&l, "/channels2.bak", 2720, 'B');
    if (counts[i] == 350 && !primary && backup == LFS_ERR_NOSPC) ++impossible_case;
    printf("contacts=%zu primary=%d backup=%d third=%d reclaim_retry=%d\n",
           counts[i], primary, backup, scratch, retry);
    assert(lfs_unmount(&l) == 0);
  }
  assert(reclaim_case > 0 && impossible_case == 1);
  puts("PASS littlefs1.7 100KiB: bounded reclaim and reboot recovery; 350-record double-copy limit remains explicit");
}
'''
    real.main()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--littlefs", action="store_true")
    args = parser.parse_args()
    check_profiles()
    run_quota()
    if args.littlefs:
        run_littlefs()
