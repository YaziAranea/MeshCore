#!/usr/bin/env python3
"""Execute production contact loading/saving around the first-200 migration.

Load/save/trim/format logic comes from production. The fake filesystem injects
truncate/flush/format faults; LittleFS power-cut behavior is tested separately
by test_contact_limit_migration.py. No device or persistent test data is used.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

from test_contact_persistence import HARNESS, ROOT, function, linux


def harness():
    code = """
#define NRF52_PLATFORM 1
#define FILE_O_READ "r"
#define FILE_O_WRITE "a"
""" + HARNESS.split("class MyMesh :", 1)[0]
    changes = {
        "struct ContactInfo {": """
namespace mesh {
struct Identity {
  uint8_t pub_key[32] = {};
  Identity() = default;
  explicit Identity(const uint8_t* key) { std::memcpy(pub_key, key, 32); }
};
}
struct ContactInfo {
""",
        "struct { uint8_t pub_key[32] = {}; } id;": "mesh::Identity id;",
        "unsigned short_write_at = 0;": """
  unsigned short_write_at = 0;
  bool fail_trim = false, corrupt_after_trim = false, trim_pending = false;
  unsigned trim_attempts = 0, trim_size = 0;
  bool format_ok = true;
  unsigned format_calls = 0;
  bool format() {
    ++format_calls;
    if (!format_ok) return false;
    files.clear();
    return true;
  }
""",
        "bool create);": "bool create = false);",
        "if (mode[0] == 'w') files[path].clear();": """
  if (mode[0] == 'w') files[path].clear();
  if (mode[0] == 'a' && !exists(path)) files[path] = {};
""",
        "void flush() { ++fs->flushes; }": """
  bool truncate(uint32_t size) {
    ++fs->trim_attempts;
    if (fs->fail_trim) return false;
    fs->trim_pending = true; fs->trim_size = size;
    return true;
  }
  void flush() {
    ++fs->flushes;
    if (!fs->trim_pending) return;
    fs->trim_pending = false;
    fs->files[path].resize(fs->trim_size);
    if (fs->corrupt_after_trim && !fs->files[path].empty()) fs->files[path][0] ^= 1;
  }
""",
        "virtual bool getContactForSave(uint32_t idx, ContactInfo& contact) = 0;": """
  virtual bool onContactLoaded(const ContactInfo& contact) = 0;
  virtual bool getContactForSave(uint32_t idx, ContactInfo& contact) = 0;
""",
        "FakeFS* _fs;": """
  FakeFS* _fs;
  FakeFS* _fsExtra = nullptr;
  bool _contacts_limit_ready = true;
  uint32_t _contacts_limit_crc = 0;
  bool _contacts_limit_crc_pending = false;
""",
        "unsigned deleted_blobs = 0;": """
  unsigned deleted_blobs = 0;
  bool contactLimitReady() const { return _contacts_limit_ready; }
  bool contactLimitCrcPending() const { return _contacts_limit_crc_pending; }
  void loadContacts(DataStoreHost* host);
  uint8_t formatFileSystemDetailed();
  File openRead(FILESYSTEM* fs, const char* filename);
  DataStore(FakeFS& primary, FakeFS& secondary) : _fs(&primary), _fsExtra(&secondary) {}
""",
        "FakeFS* _getContactsChannelsFS() { return _fs; }":
            "FakeFS* _getContactsChannelsFS() { return _fsExtra ? _fsExtra : _fs; }",
    }
    for before, after in changes.items():
        assert code.count(before) == 1, before
        code = code.replace(before, after)
    return code


def production():
    source = (ROOT / "examples/companion_radio/DataStore.cpp").read_text(encoding="utf-8")
    header = (ROOT / "examples/companion_radio/DataStore.h").read_text(encoding="utf-8")
    names = ("static bool prepareScratch(", "static File openScratch(",
             "static File openStorageRead(", "static bool digestFile(",
             "static bool commitScratch(", "static bool fixedRecordFileValid(",
             "static bool encodedPathLenValid(", "static bool contactRecordFileValid(",
             "static mesh::storage::RecoveryCandidate chooseContactCandidate(",
             "static const char* candidatePath(")
    code = function(header, "enum StorageFormatFailure") + ";\n"
    code += function(source, "struct FileDigest") + ";\n"
    code += "\n".join(function(source, name) for name in names)
    code += "\n#if defined(SMARTUI_CONTACT_LIMIT)\n"
    code += function(source, "static bool contactPrefixCrc(") + "\n"
    code += function(source, "static bool trimContactsToLimit(") + "\n#endif\n"
    for name in ("File DataStore::openRead(FILESYSTEM* fs, const char* filename)",
                 "uint8_t DataStore::formatFileSystemDetailed(",
                 "void DataStore::loadContacts(", "bool DataStore::saveContacts("):
        code += function(source, name) + "\n"
    return code


TESTS = r'''
static Bytes records(unsigned count) {
  Bytes result(count * 152, 0);
  for (unsigned i = 0; i < count; ++i) {
    auto* record = result.data() + i*152;
    std::memcpy(record, &i, sizeof(i));
    std::snprintf(reinterpret_cast<char*>(record+32), 32, "contact-%03u", i);
    record[64] = ADV_TYPE_CHAT; record[71] = OUT_PATH_UNKNOWN;
    std::memcpy(record+140, &i, sizeof(i));
  }
  return result;
}
struct Host : DataStoreHost {
  unsigned capacity, loads = 0, replacements = 0;
  std::vector<ContactInfo> contacts;
  explicit Host(unsigned size) : capacity(size) {}
  bool onContactLoaded(const ContactInfo& contact) override {
    ++loads;
    if (contacts.size() < capacity) contacts.push_back(contact);
    else contacts[replacements++ % capacity] = contact;
    return true;  // Simulate overwrite-enabled host, not a rejecting cap.
  }
  bool getContactForSave(uint32_t index, ContactInfo& contact) override {
    if (index >= contacts.size()) return false;
    contact = contacts[index]; return true;
  }
  void expectPrefix(unsigned count) const {
    expect(loads == count && contacts.size() == count && replacements == 0);
    for (unsigned i = 0; i < count; ++i) {
      unsigned key = UINT32_MAX;
      std::memcpy(&key, contacts[i].id.pub_key, sizeof(key));
      expect(key == i && contacts[i].lastmod == i);
    }
  }
};
#if defined(SMARTUI_CONTACT_LIMIT)
static void testLoadsFirst200DespiteOverwriteHost() {
  for (const char* path : {"/contacts3", "/contacts3.bak", "/contacts3.tmp"}) {
    for (bool fail : {false, true}) {
      FakeFS fs; fs.files[path] = records(350); fs.fail_trim = fail;
      fs.files["/unrelated"] = {22, 33};
      DataStore store(fs); Host host(200);
      store.loadContacts(&host);
      host.expectPrefix(200);
      expect(store.contactLimitReady() == !fail);
      expect(fs.trim_attempts == 1);
      expect(fs.files[path] == records(fail ? 350 : 200));
      expect(fs.files["/unrelated"] == Bytes({22, 33}));
      expect(fs.writes == 0 && fs.rename_calls == 0);
    }
  }
}
static void testFailedMigrationGuardsSavesAndCanRecover() {
  for (const char* path : {"/contacts3", "/contacts3.bak", "/contacts3.tmp"}) {
    FakeFS fs; fs.files[path] = records(350); fs.fail_trim = true;
    fs.files["/unrelated"] = {22, 33};
    DataStore store(fs); Host host(200); store.loadContacts(&host);
    std::strcpy(host.contacts[0].name, "live mutation");
    const auto before = fs.files;
    for (unsigned attempt = 0; attempt < 3; ++attempt) {
      expect(!store.saveContacts(&host));
      expect(!store.contactLimitReady() && fs.files == before);
      expect(fs.writes == 0 && fs.rename_calls == 0);
    }
    expect(fs.trim_attempts == 4);
    fs.fail_trim = false;
    expect(store.saveContacts(&host));
    expect(store.contactLimitReady());
    expect(fs.files["/contacts3"].size() == 200*152);
    expect(std::strcmp(reinterpret_cast<const char*>(fs.files["/contacts3"].data()+32), "live mutation") == 0);
    expect(fs.files["/unrelated"] == Bytes({22, 33}));
  }
}
static void testReloadEmptyResetsMigrationGuard() {
  FakeFS fs; fs.files["/contacts3"] = records(350); fs.fail_trim = true;
  DataStore store(fs); Host previous(200); store.loadContacts(&previous);
  expect(!store.contactLimitReady());
  fs.files.clear();  // Explicit erase/rebuild then reload on this same object.
  Host empty(200); store.loadContacts(&empty);
  expect(empty.loads == 0 && store.contactLimitReady());
  expect(store.saveContacts(&empty));
  expect(fs.files.count("/contacts3") == 1 && fs.files["/contacts3"].empty());
}
static void testPendingChecksumSurvivesNonemptyReload() {
  for (const char* path : {"/contacts3", "/contacts3.bak", "/contacts3.tmp"}) {
    FakeFS fs; fs.files[path] = records(350); fs.corrupt_after_trim = true;
    DataStore store(fs); Host original(200); store.loadContacts(&original);
    expect(!store.contactLimitReady() && store.contactLimitCrcPending());
    expect(fs.files[path].size() == 200*152);
    expect(contactRecordFileValid(&fs, path));  // Key corruption stays structural.
    const auto damaged = fs.files;
    Host reloaded(200); store.loadContacts(&reloaded);
    expect(reloaded.loads == 200);
    expect(!store.contactLimitReady() && store.contactLimitCrcPending());
    expect(!store.saveContacts(&reloaded));
    expect(fs.files == damaged && fs.writes == 0);

    // No usable candidate is different from no files at all.
    fs.files[path] = {99};
    const auto invalid = fs.files;
    Host none(200); store.loadContacts(&none);
    expect(none.loads == 0);
    expect(!store.contactLimitReady() && store.contactLimitCrcPending());
    expect(!store.saveContacts(&none));
    expect(fs.files == invalid && fs.writes == 0);

    // Repairing the exact original prefix permits the same object to recover.
    fs.files[path] = records(200); fs.corrupt_after_trim = false;
    Host repaired(200); store.loadContacts(&repaired);
    repaired.expectPrefix(200);
    expect(store.contactLimitReady() && !store.contactLimitCrcPending());
    expect(store.saveContacts(&repaired));
  }
}
static void testFormatResetsGuardOnlyOnCompleteSuccess() {
  for (bool secondary : {false, true}) {
    const unsigned cases = secondary ? 4 : 2;
    for (unsigned failures = 0; failures < cases; ++failures) {
      FakeFS primary, extra;
      FakeFS& contacts_fs = secondary ? extra : primary;
      contacts_fs.files["/contacts3"] = records(350);
      contacts_fs.fail_trim = true;
      DataStore single(primary), dual(primary, extra);
      DataStore& store = secondary ? dual : single;
      Host host(200); store.loadContacts(&host);
      host.expectPrefix(200);
      expect(!store.contactLimitReady() && store.contactLimitCrcPending());
      primary.format_ok = (failures & 1) == 0;
      extra.format_ok = (failures & 2) == 0;
      expect(store.formatFileSystemDetailed() == failures);
      expect(primary.format_calls == 1);
      expect(extra.format_calls == (secondary ? 1U : 0U));
      if (failures == 0) {
        expect(store.contactLimitReady() && !store.contactLimitCrcPending());
        // CLI rebuild saves current RAM immediately; it does not reload first.
        expect(store.saveContacts(&host));
        expect(contacts_fs.files["/contacts3"] == records(200));
      } else {
        const auto before = contacts_fs.files;
        expect(!store.contactLimitReady() && store.contactLimitCrcPending());
        expect(!store.saveContacts(&host));
        expect(contacts_fs.files == before && contacts_fs.writes == 0);
      }
    }
  }
}
#endif
static void testUnchangedAtOrBelow200() {
  for (unsigned count : {0U, 1U, 199U, 200U}) {
    FakeFS fs; fs.files["/contacts3"] = records(count);
    fs.files["/contacts3.bak"] = records(count);
    const auto before = fs.files;
    DataStore store(fs); Host host(400); store.loadContacts(&host);
    host.expectPrefix(count);
    expect(store.contactLimitReady() && fs.trim_attempts == 0);
    expect(fs.files == before && fs.writes == 0 && fs.rename_calls == 0);
  }
}
int main() {
  testUnchangedAtOrBelow200();
#if defined(SMARTUI_CONTACT_LIMIT)
  testLoadsFirst200DespiteOverwriteHost();
  testFailedMigrationGuardsSavesAndCanRecover();
  testReloadEmptyResetsMigrationGuard();
  testPendingChecksumSurvivesNonemptyReload();
  testFormatResetsGuardOnlyOnCompleteSuccess();
  std::printf("PASS %u capped load/save/format assertions: first200, overwrite host, CRC guard through reload, invalid files, full/partial format\n", checks);
#else
  FakeFS fs; fs.files["/contacts3"] = records(350);
  const auto before = fs.files;
  DataStore store(fs); Host host(400); store.loadContacts(&host);
  host.expectPrefix(350);
  expect(fs.files == before && fs.trim_attempts == 0);
  std::printf("PASS %u non-capped load assertions: all350 retained and no migration writes\n", checks);
#endif
}
'''


def main():
    source = harness() + production() + TESTS
    with tempfile.TemporaryDirectory(prefix="contact-load-migration-") as folder:
        folder = Path(folder)
        cpp, binary = folder / "test.cpp", folder / "test"
        cpp.write_text(source, encoding="utf-8")
        compiler = shutil.which("g++")
        prefix = [] if compiler else ["wsl", "--exec"]
        path = str if compiler else linux
        for capped in (True, False):
            flags = ["-DSMARTUI_CONTACT_LIMIT=200"] if capped else []
            subprocess.run([*prefix, compiler or "g++", "-std=c++17", "-Wall", "-Wextra",
                            "-Werror", "-Wno-unused-variable", "-pedantic", "-O2", *flags,
                            "-I", path(ROOT / "src"), path(cpp), "-o", path(binary)],
                           check=True, timeout=60)
            subprocess.run([*prefix, path(binary)], check=True, timeout=30)


if __name__ == "__main__":
    main()
