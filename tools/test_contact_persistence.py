#!/usr/bin/env python3
"""Execute extracted production contact handlers and transactional file writer.

Host-only tests: no firmware flashing, device access, or persistent test files.
The fake filesystem injects faults; handler/writer/policy code comes from sources.
"""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def block(source, start):
    opening = source.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def function(source, signature):
    return block(source, source.index(signature))


def linux(path):
    path = Path(path).resolve()
    return "/mnt/" + path.drive[0].lower() + path.as_posix()[2:] if os.name == "nt" else str(path)


HARNESS = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <map>
#include <string>
#include <vector>
#include "helpers/DeferredSavePolicy.h"
#include "helpers/DeferredSaveResponseGate.h"
#include "helpers/StorageTransaction.h"
#include "helpers/WrapTimer.h"
#define PUB_KEY_SIZE 32
#define MAX_PATH_SIZE 64
#define OUT_PATH_UNKNOWN 0xFF
#define ADV_TYPE_NONE 0
#define ADV_TYPE_CHAT 1
#define ADV_TYPE_SENSOR 4
#define MESH_DEBUG_PRINTLN(...) do {} while (false)
using Bytes = std::vector<uint8_t>;
static unsigned checks = 0;
static void expect(bool value) { assert(value); ++checks; }
struct ContactInfo {
  struct { uint8_t pub_key[32] = {}; } id;
  char name[32] = {};
  uint8_t type = ADV_TYPE_CHAT, flags = 0, out_path_len = 0;
  uint8_t out_path[64] = {};
  uint32_t last_advert_timestamp = 0, lastmod = 0;
  int32_t gps_lat = 0, gps_lon = 0;
  uint32_t sync_since = 0;
};
struct FakeClock {
  uint32_t now = 1000;
  uint32_t getMillis() const { return now; }
  uint32_t getCurrentTime() const { return 123456; }
};
struct FakeSerial {
  bool queue_responses = false;
  unsigned pending = 0;
  uint32_t generation = 1;
  bool hasPendingTx() const { return pending != 0; }
  uint32_t sessionGeneration() const { return generation; }
};
struct FakePacketManager {
  unsigned getOutboundTotal() const { return 0; }
};
struct File;
struct FakeFS {
  std::map<std::string, Bytes> files;
  unsigned writes = 0, flushes = 0, rename_calls = 0;
  unsigned short_write_at = 0;
  std::string remove_fail, open_fail, read_fail, size_mismatch;
  std::string rename_fail_source;
  bool rollback_fail = false;
  FakeClock* clock = nullptr;
  uint32_t write_duration = 0;
  bool exists(const char* path) const { return files.count(path) != 0; }
  bool remove(const char* path) {
    if (path == remove_fail) return false;
    return files.erase(path) != 0;
  }
  bool rename(const char* from, const char* to) {
    ++rename_calls;
    if ((rollback_fail && std::string(from) == "/contacts3.bak") ||
        from == rename_fail_source || !exists(from)) return false;
    files[to] = files[from]; files.erase(from); return true;
  }
  File open(const char* path, const char* mode, bool create);
};
struct File {
  FakeFS* fs = nullptr;
  std::string path;
  size_t pos = 0;
  explicit operator bool() const { return fs && fs->exists(path.c_str()); }
  size_t write(const uint8_t* data, size_t count) {
    ++fs->writes;
    if (fs->clock) fs->clock->now += fs->write_duration;
    if (fs->short_write_at == fs->writes) --count;
    auto& bytes = fs->files[path];
    bytes.insert(bytes.end(), data, data + count);
    return count;
  }
  int read(uint8_t* data, size_t count) {
    if (path == fs->read_fail) return -1;
    auto& bytes = fs->files[path];
    count = std::min(count, bytes.size() - pos);
    std::copy_n(bytes.data() + pos, count, data);
    pos += count; return static_cast<int>(count);
  }
  size_t size() const { return fs->files[path].size() + (path == fs->size_mismatch); }
  int available() const { return static_cast<int>(fs->files[path].size() - pos); }
  void flush() { ++fs->flushes; }
  void close() {}
};
File FakeFS::open(const char* path, const char* mode, bool) {
  if (path == open_fail) return {};
  if (mode[0] == 'w') files[path].clear();
  if (!exists(path)) return {};
  return {this, path, 0};
}
#define FILESYSTEM FakeFS
struct DataStoreHost {
  virtual bool getContactForSave(uint32_t idx, ContactInfo& contact) = 0;
  virtual ~DataStoreHost() = default;
};
class DataStore {
  FakeFS* _fs;
  FakeFS* _getContactsChannelsFS() { return _fs; }
public:
  unsigned deleted_blobs = 0;
  explicit DataStore(FakeFS& fs) : _fs(&fs) {}
  bool saveContacts(DataStoreHost* host, bool (*filter)(const ContactInfo&) = nullptr);
  bool deleteBlobByKey(const uint8_t*, int) { ++deleted_blobs; return true; }
};
class MyMesh : public DataStoreHost {
public:
  FakeClock clock;
  FakeClock* _ms = &clock;
  FakeFS fs;
  DataStore store{fs};
  DataStore* _store = &store;
  std::vector<ContactInfo> contacts;
  mesh::storage::DeferredSavePolicy dirty_contacts;
  mesh::storage::DeferredSaveResponseGate contacts_save_response_gate;
  FakeSerial serial;
  FakeSerial* _serial = &serial;
  FakePacketManager manager;
  FakePacketManager* _mgr = &manager;
  bool storage_recovery_required = false;
  bool reject_update = false, reject_add = false, reject_remove = false;
  std::vector<int> responses;
  std::vector<unsigned> writes_at_response;
  uint8_t cmd_frame[176] = {};
  MyMesh() { fs.clock = &clock; }
  bool getContactForSave(uint32_t idx, ContactInfo& contact) override {
    if (idx >= contacts.size()) return false;
    contact = contacts[idx]; return true;
  }
  ContactInfo* lookupContactByPubKey(const uint8_t* key, int size) {
    for (auto& contact : contacts)
      if (std::memcmp(contact.id.pub_key, key, size) == 0) return &contact;
    return nullptr;
  }
  FakeClock* getRTCClock() { return &clock; }
  bool updateContactFromFrame(ContactInfo& contact, uint32_t&, uint8_t* frame, size_t) {
    if (reject_update) return false;
    std::memcpy(contact.id.pub_key, frame + 1, PUB_KEY_SIZE);
    std::strcpy(contact.name, "updated contact");
    contact.type = ADV_TYPE_CHAT;
    return true;
  }
  bool addContact(const ContactInfo& contact) {
    if (reject_add) return false;
    contacts.push_back(contact); return true;
  }
  bool removeContact(const ContactInfo& contact) {
    if (reject_remove) return false;
    for (auto it = contacts.begin(); it != contacts.end(); ++it) {
      if (!std::memcmp(it->id.pub_key, contact.id.pub_key, PUB_KEY_SIZE)) {
        contacts.erase(it); return true;
      }
    }
    return false;
  }
  void writeOKFrame() {
    responses.push_back(0); writes_at_response.push_back(fs.writes);
    if (serial.queue_responses) ++serial.pending;
  }
  void writeErrFrame(uint8_t error) { responses.push_back(error); writes_at_response.push_back(fs.writes); }
  void scheduleContactsSave();
  bool saveContacts();
  bool flushPendingStorage();
  bool hasPendingWork() const;
  void serviceStorage();
  void handleContacts(size_t len);
  void command(uint8_t cmd, uint8_t key = 1) {
    std::memset(cmd_frame, 0, sizeof(cmd_frame));
    cmd_frame[0] = cmd; cmd_frame[1] = key;
    handleContacts(176);
  }
};
'''

TESTS = r'''
static void testEspPendingIsNotThrottle() {
  esp_tx::SerialBLEInterface ble;
  esp_tx::tick = 1000; ble._last_write = 1000;
  expect(ble.isWriteBusy() && !ble.hasPendingTx());
  esp_tx::tick += 60; ble.send_queue_len = 1;
  expect(!ble.isWriteBusy() && ble.hasPendingTx());
  ble.send_queue_len = 0; expect(!ble.hasPendingTx());
}
static ContactInfo contact(uint8_t key = 1) {
  ContactInfo c;
  c.id.pub_key[0] = key;
  for (unsigned i = 1; i < 32; ++i) c.id.pub_key[i] = 0;
  std::strcpy(c.name, "original contact");
  c.flags = 0xA5; c.out_path_len = 3;
  for (unsigned i = 0; i < 64; ++i) c.out_path[i] = static_cast<uint8_t>(i * 3 + key);
  c.sync_since = 0x12345678; c.last_advert_timestamp = 0x87654321;
  c.lastmod = 0xABCDEF01; c.gps_lat = -12345678; c.gps_lon = 23456789;
  return c;
}
// Independent reference: the pre-0.08 sequence of twelve field writes.
static Bytes legacyBytes(const ContactInfo& c) {
  Bytes bytes;
  auto append = [&bytes](const void* ptr, size_t size) {
    const auto* begin = static_cast<const uint8_t*>(ptr);
    bytes.insert(bytes.end(), begin, begin + size);
  };
  const uint8_t unused = 0;
  append(c.id.pub_key, 32); append(c.name, 32); append(&c.type, 1);
  append(&c.flags, 1); append(&unused, 1); append(&c.sync_since, 4);
  append(&c.out_path_len, 1); append(&c.last_advert_timestamp, 4);
  append(c.out_path, 64); append(&c.lastmod, 4);
  append(&c.gps_lat, 4); append(&c.gps_lon, 4);
  return bytes;
}
static void seed(MyMesh& mesh) {
  mesh.contacts.push_back(contact());
  mesh.fs.files["/contacts3"] = legacyBytes(mesh.contacts.front());
}
static void testResetAndSchedule() {
  MyMesh m; seed(m);
  const Bytes before = m.fs.files["/contacts3"];
  m.command(CMD_RESET_PATH);
  expect(m.responses.back() == 0 && m.writes_at_response.back() == 0);
  expect(m.contacts.front().out_path_len == OUT_PATH_UNKNOWN);
  expect(m.contacts.front().lastmod == contact().lastmod);
  expect(m.contacts.front().sync_since == contact().sync_since);
  expect(!std::memcmp(m.contacts.front().out_path, contact().out_path, 64));
  expect(m.dirty_contacts.pending());
  expect(m.fs.files["/contacts3"] == before && m.fs.writes == 0);
  m.clock.now = 5999; m.serviceStorage(); expect(m.fs.writes == 0);
  m.clock.now = 6000; m.serviceStorage();
  expect(m.fs.writes == 1 && !m.dirty_contacts.pending());
  expect(m.fs.files["/contacts3"][71] == OUT_PATH_UNKNOWN);
  expect(m.fs.files["/contacts3.bak"] == before);
  m.command(CMD_RESET_PATH, 99);
  expect(m.responses.back() == ERR_CODE_NOT_FOUND);
  expect(!m.dirty_contacts.pending() && m.fs.writes == 1);
  m.contacts.front().out_path_len = OUT_PATH_UNKNOWN;
  m.command(CMD_RESET_PATH); expect(m.responses.back() == 0);
  expect(m.dirty_contacts.pending() && m.fs.writes == 1);
}
static void testTimersAndFlush() {
  MyMesh m; seed(m);
  m.command(CMD_RESET_PATH);
  for (m.clock.now = 5000; m.clock.now < 31000; m.clock.now += 4000) {
    m.command(CMD_RESET_PATH); m.serviceStorage(); expect(m.fs.writes == 0);
  }
  m.clock.now = 31000; m.serviceStorage();
  expect(m.fs.writes == 1 && !m.dirty_contacts.pending());

  MyMesh wrap; seed(wrap); wrap.clock.now = 0xFFFFFFF0U;
  wrap.command(CMD_RESET_PATH);
  wrap.clock.now += 4999; wrap.serviceStorage(); expect(wrap.fs.writes == 0);
  ++wrap.clock.now; wrap.serviceStorage(); expect(wrap.fs.writes == 1);

  MyMesh fail; seed(fail); const Bytes previous = fail.fs.files["/contacts3"];
  fail.command(CMD_RESET_PATH); fail.fs.short_write_at = 1;
  fail.fs.write_duration = 8000; fail.clock.now = 6000; fail.serviceStorage();
  expect(fail.clock.now == 14000 && fail.dirty_contacts.pending());
  expect(fail.fs.files["/contacts3"] == previous);
  expect(fail.contacts.front().out_path_len == OUT_PATH_UNKNOWN);
  fail.serviceStorage(); expect(fail.fs.writes == 1);
  fail.clock.now = 18999; fail.serviceStorage(); expect(fail.fs.writes == 1);
  fail.clock.now = 19000; fail.fs.write_duration = 0; fail.serviceStorage();
  expect(fail.fs.writes == 2 && !fail.dirty_contacts.pending());

  MyMesh flush; seed(flush); flush.command(CMD_RESET_PATH);
  flush.fs.short_write_at = 1;
  expect(!flush.flushPendingStorage() && flush.dirty_contacts.pending());
  expect(flush.flushPendingStorage() && !flush.dirty_contacts.pending());
  expect(flush.fs.writes == 2);
  expect(flush.flushPendingStorage() && flush.fs.writes == 2);
  flush.command(CMD_RESET_PATH); flush.storage_recovery_required = true;
  expect(!flush.flushPendingStorage() && flush.dirty_contacts.pending());
  expect(flush.fs.writes == 2);
}
static void testDurableCommands() {
  for (bool fail : {false, true}) {
    MyMesh update; seed(update); const Bytes old = legacyBytes(update.contacts.front());
    update.fs.short_write_at = fail ? 1 : 0;
    update.command(CMD_ADD_UPDATE_CONTACT);
    expect(update.responses.back() == (fail ? ERR_CODE_FILE_IO_ERROR : 0));
    expect(update.writes_at_response.back() == 1);
    expect(fail ? legacyBytes(update.contacts.front()) == old
                : update.contacts.front().lastmod == update.clock.getCurrentTime());
    expect(fail ? update.fs.files["/contacts3"] == old
                : update.fs.files["/contacts3"] == legacyBytes(update.contacts.front()));

    MyMesh add; seed(add); add.fs.short_write_at = fail ? 2 : 0;
    add.command(CMD_ADD_UPDATE_CONTACT, 2);
    expect(add.responses.back() == (fail ? ERR_CODE_FILE_IO_ERROR : 0));
    expect(add.writes_at_response.back() == 2 && add.contacts.size() == (fail ? 1 : 2));
    if (fail) expect(add.fs.files["/contacts3"] == old);

    MyMesh remove; seed(remove); remove.contacts.push_back(contact(2));
    remove.fs.short_write_at = fail ? 1 : 0;
    remove.command(CMD_REMOVE_CONTACT);
    expect(remove.responses.back() == (fail ? ERR_CODE_FILE_IO_ERROR : 0));
    expect(remove.writes_at_response.back() == 1);
    expect(remove.contacts.size() == (fail ? 2 : 1));
    expect(remove.store.deleted_blobs == (fail ? 0 : 1));
    if (fail) {
      uint8_t key[32] = {1};
      expect(legacyBytes(*remove.lookupContactByPubKey(key, 32)) == old);
      expect(remove.fs.files["/contacts3"] == old);
    }
  }
  MyMesh invalid; seed(invalid); invalid.reject_update = true;
  invalid.command(CMD_ADD_UPDATE_CONTACT);
  expect(invalid.responses.back() == ERR_CODE_ILLEGAL_ARG && invalid.fs.writes == 0);
  invalid.command(CMD_REMOVE_CONTACT, 99);
  expect(invalid.responses.back() == ERR_CODE_NOT_FOUND && invalid.fs.writes == 0);
  invalid.reject_update = false; invalid.reject_add = true;
  invalid.command(CMD_ADD_UPDATE_CONTACT, 2);
  expect(invalid.responses.back() == ERR_CODE_TABLE_FULL && invalid.fs.writes == 0);
}
static void testQueuedResponseBeforeOldBatchSave() {
  MyMesh old; seed(old); old.scheduleContactsSave();
  old.clock.now += MAX_DIRTY_CONTACTS_AGE;
  old.serial.queue_responses = true;
  old.command(CMD_RESET_PATH);
  expect(old.serial.pending == 1 && old.fs.writes == 0);
  old.serviceStorage();
  expect(old.fs.writes == 0 && !old.hasPendingWork());
  old.clock.now += 60;
  old.serial.pending = 0;  // Transport loop drained its application queue.
  expect(old.hasPendingWork());
  old.serviceStorage();
  expect(old.fs.writes == 1 && !old.dirty_contacts.pending());
  expect(!old.hasPendingWork());

  MyMesh stuck; seed(stuck); stuck.scheduleContactsSave();
  stuck.clock.now += MAX_DIRTY_CONTACTS_AGE;
  stuck.serial.queue_responses = true;
  stuck.command(CMD_RESET_PATH); stuck.serviceStorage();
  const uint32_t start = stuck.clock.now;
  for (unsigned elapsed : {1U, 100U, 500U, 999U}) {
    stuck.clock.now = start + elapsed;
    stuck.command(CMD_RESET_PATH); stuck.serviceStorage();
    expect(stuck.fs.writes == 0 && !stuck.hasPendingWork());
  }
  stuck.clock.now = start + CONTACTS_RESPONSE_DRAIN_LIMIT;
  expect(stuck.hasPendingWork());
  stuck.command(CMD_RESET_PATH); stuck.serviceStorage();
  expect(stuck.fs.writes == 1 && stuck.serial.pending != 0);

  // A failed write has already spent the batch's grant; neither retry nor
  // another reset can indefinitely replace its one-second budget.
  MyMesh retry; seed(retry); retry.scheduleContactsSave();
  retry.clock.now += MAX_DIRTY_CONTACTS_AGE;
  retry.serial.queue_responses = true; retry.command(CMD_RESET_PATH);
  retry.serviceStorage(); retry.clock.now += CONTACTS_RESPONSE_DRAIN_LIMIT;
  retry.fs.short_write_at = 1; retry.serviceStorage();
  expect(retry.fs.writes == 1 && retry.dirty_contacts.pending());
  retry.command(CMD_RESET_PATH); retry.clock.now += LAZY_CONTACTS_WRITE_DELAY;
  retry.serviceStorage(); expect(retry.fs.writes == 2 && !retry.dirty_contacts.pending());

  // After a successful commit the next dirty batch receives its own grant.
  retry.command(CMD_RESET_PATH); retry.clock.now += LAZY_CONTACTS_WRITE_DELAY;
  retry.serviceStorage(); expect(retry.fs.writes == 2 && !retry.hasPendingWork());
  retry.clock.now += CONTACTS_RESPONSE_DRAIN_LIMIT; retry.serviceStorage();
  expect(retry.fs.writes == 3);

  // Switching/disconnecting sessions releases the old response's grant.
  MyMesh changed; seed(changed); changed.scheduleContactsSave();
  changed.clock.now += MAX_DIRTY_CONTACTS_AGE;
  changed.serial.queue_responses = true; changed.command(CMD_RESET_PATH);
  changed.serviceStorage(); expect(changed.fs.writes == 0);
  ++changed.serial.generation;
  expect(changed.hasPendingWork()); changed.serviceStorage();
  expect(changed.fs.writes == 1);

  MyMesh wrap; seed(wrap); wrap.clock.now = UINT32_MAX - MAX_DIRTY_CONTACTS_AGE - 50;
  wrap.scheduleContactsSave(); wrap.clock.now += MAX_DIRTY_CONTACTS_AGE;
  wrap.serial.queue_responses = true; wrap.command(CMD_RESET_PATH);
  wrap.serviceStorage(); wrap.clock.now += CONTACTS_RESPONSE_DRAIN_LIMIT - 1;
  wrap.serviceStorage(); expect(wrap.fs.writes == 0 && !wrap.hasPendingWork());
  ++wrap.clock.now; wrap.serviceStorage(); expect(wrap.fs.writes == 1);

  // Explicit shutdown flush remains synchronous and is not held by a client.
  MyMesh shutdown; seed(shutdown); shutdown.serial.queue_responses = true;
  shutdown.command(CMD_RESET_PATH); expect(shutdown.flushPendingStorage());
  expect(shutdown.fs.writes == 1 && !shutdown.dirty_contacts.pending());

  MyMesh no_transport; seed(no_transport); no_transport.scheduleContactsSave();
  no_transport.clock.now += MAX_DIRTY_CONTACTS_AGE; no_transport._serial = nullptr;
  no_transport.command(CMD_RESET_PATH); no_transport.serviceStorage();
  expect(no_transport.fs.writes == 1);
}
static void testLayoutAndStorageFailures() {
  MyMesh layout; seed(layout);
  layout.contacts.push_back(contact(2));
  auto ignored = contact(3); ignored.type = ADV_TYPE_NONE; layout.contacts.push_back(ignored);
  layout.contacts[0].out_path_len = OUT_PATH_UNKNOWN;
  layout.contacts[1].out_path_len = 0x42;
  Bytes expected = legacyBytes(layout.contacts[0]);
  const Bytes second = legacyBytes(layout.contacts[1]);
  expected.insert(expected.end(), second.begin(), second.end());
  expect(layout.saveContacts());
  expect(layout.fs.writes == 2 && layout.fs.files["/contacts3"] == expected);
  expect(expected.size() == 304 && expected[66] == 0 && expected[218] == 0);
  expect(contactRecordFileValid(&layout.fs, "/contacts3"));
  MyMesh empty; seed(empty); empty.contacts.clear();
  expect(empty.saveContacts() && empty.fs.writes == 0);
  expect(empty.fs.files["/contacts3"].empty());

  for (unsigned fault = 0; fault < 8; ++fault) {
    MyMesh m; seed(m); const Bytes old = m.fs.files["/contacts3"];
    m.contacts.front().out_path_len = OUT_PATH_UNKNOWN;
    if (fault == 0) m.fs.short_write_at = 1;
    if (fault == 1) m.fs.open_fail = "/contacts3.tmp";
    if (fault == 2) m.fs.read_fail = "/contacts3.tmp";
    if (fault == 3) m.fs.size_mismatch = "/contacts3.tmp";
    if (fault == 4) m.fs.rename_fail_source = "/contacts3.tmp";
    if (fault == 5) m.fs.rename_fail_source = "/contacts3";
    if (fault == 6) {
      m.fs.files["/contacts3.bak"] = old; m.fs.remove_fail = "/contacts3.bak";
    }
    if (fault == 7) {
      m.fs.files["/contacts3.tmp"] = {99}; m.fs.remove_fail = "/contacts3.tmp";
    }
    expect(!m.saveContacts());
    expect(m.fs.files["/contacts3"] == old);
    if (fault != 7) expect(!m.fs.exists("/contacts3.tmp"));
  }
  // Never overwrite the known-good backup with a corrupt primary.
  MyMesh corrupt; seed(corrupt); const Bytes good = corrupt.fs.files["/contacts3"];
  corrupt.fs.files["/contacts3.bak"] = good;
  corrupt.fs.files["/contacts3"] = {99};
  corrupt.contacts.front().out_path_len = OUT_PATH_UNKNOWN;
  expect(corrupt.saveContacts());
  expect(corrupt.fs.files["/contacts3.bak"] == good);
  expect(corrupt.fs.files["/contacts3"] == legacyBytes(corrupt.contacts.front()));

  // If publish and rollback both fail, boot still has the intact old backup.
  MyMesh rollback; seed(rollback);
  rollback.fs.rename_fail_source = "/contacts3.tmp";
  rollback.fs.rollback_fail = true;
  expect(!rollback.saveContacts());
  expect(!rollback.fs.exists("/contacts3"));
  expect(rollback.fs.files["/contacts3.bak"] == good);
  expect(contactRecordFileValid(&rollback.fs, "/contacts3.bak"));

  // A full address book still uses exactly one write per persisted contact.
  MyMesh full;
  for (unsigned i = 0; i < 400; ++i) full.contacts.push_back(contact(i % 255));
  expect(full.saveContacts());
  expect(full.fs.writes == 400 && full.fs.files["/contacts3"].size() == 400 * 152);
}
int main() {
  testResetAndSchedule(); testTimersAndFlush();
  testDurableCommands(); testLayoutAndStorageFailures();
  testQueuedResponseBeforeOldBatchSave();
  testEspPendingIsNotThrottle();
  std::printf("PASS: %u contact persistence assertions (extracted production C++)\n", checks);
}
'''


def main():
    mesh = (ROOT / "examples/companion_radio/MyMesh.cpp").read_text(encoding="utf-8")
    store = (ROOT / "examples/companion_radio/DataStore.cpp").read_text(encoding="utf-8")
    esp_ble = (ROOT / "src/helpers/esp32/SerialBLEInterface.cpp").read_text(encoding="utf-8")
    symbols = ["CMD_RESET_PATH", "CMD_ADD_UPDATE_CONTACT", "CMD_REMOVE_CONTACT",
               "ERR_CODE_NOT_FOUND", "ERR_CODE_FILE_IO_ERROR", "ERR_CODE_ILLEGAL_ARG",
               "ERR_CODE_TABLE_FULL", "LAZY_CONTACTS_WRITE_DELAY", "MAX_DIRTY_CONTACTS_AGE",
               "CONTACTS_RESPONSE_DRAIN_LIMIT"]
    defines = "\n".join(re.search(r"^#define\s+" + name + r"\s+.*$", mesh, re.M).group()
                        for name in symbols)
    helpers = ["static bool prepareScratch(", "static File openScratch(",
               "static File openStorageRead(", "static bool digestFile(",
               "static bool commitScratch(", "static bool fixedRecordFileValid(",
               "static bool encodedPathLenValid(", "static bool contactRecordFileValid("]
    production = function(store, "struct FileDigest") + ";\n"
    production += "\n".join(function(store, name) for name in helpers)
    production += function(store, "bool DataStore::saveContacts(")
    production += function(mesh, "static bool save_filter(")
    production += function(mesh, "void MyMesh::scheduleContactsSave(")
    production += function(mesh, "bool MyMesh::saveContacts(")
    production += function(mesh, "bool MyMesh::flushPendingStorage(")
    production += function(mesh, "bool MyMesh::hasPendingWork(")
    branches = [block(mesh, mesh.index("if (cmd_frame[0] == " + name))
                for name in ["CMD_RESET_PATH", "CMD_ADD_UPDATE_CONTACT", "CMD_REMOVE_CONTACT"]]
    assert "saveContacts(" not in branches[0], "Reset must not synchronously persist contacts"
    production += "void MyMesh::handleContacts(size_t len) {" + " else ".join(branches) + "}\n"
    timer_start = mesh.index("const uint32_t storage_now =")
    timer_end = block(mesh, mesh.index("if (dirty_contacts.due(", timer_start))
    production += "void MyMesh::serviceStorage() {" + mesh[timer_start:mesh.index(timer_end, timer_start)] + timer_end + "}\n"
    production += r'''
namespace esp_tx {
static uint32_t tick = 0;
static uint32_t millis() { return tick; }
class SerialBLEInterface {
public:
  unsigned long _last_write = 0;
  int send_queue_len = 0;
  bool isWriteBusy() const;
  bool hasPendingTx() const;
};
'''
    production += re.search(r"^#define\s+BLE_WRITE_MIN_INTERVAL\s+.*$", esp_ble, re.M).group() + "\n"
    production += function(esp_ble, "bool SerialBLEInterface::isWriteBusy(")
    production += function(esp_ble, "bool SerialBLEInterface::hasPendingTx(") + "}\n"
    with tempfile.TemporaryDirectory(prefix="contact-persistence-") as folder:
        folder = Path(folder)
        cpp, binary = folder / "test.cpp", folder / "test"
        cpp.write_text(defines + "\n" + HARNESS + production + TESTS, encoding="utf-8")
        compiler = shutil.which("g++")
        prefix = [] if compiler else ["wsl", "--exec"]
        path = str if compiler else linux
        subprocess.run([*prefix, compiler or "g++", "-std=c++17", "-Wall", "-Wextra",
                        "-Werror", "-pedantic", "-O2", "-I", path(ROOT / "src"),
                        path(cpp), "-o", path(binary)], check=True, timeout=60)
        subprocess.run([*prefix, path(binary)], check=True, timeout=30)
    print("[PASS] Reset RAM/ACK/deferred save; bounded session-aware TX drain before due save; durable add/update/remove rollback; timers, retries, shutdown flush; contacts3 byte layout, filtered records, one write/record, transactional I/O faults")


if __name__ == "__main__":
    main()
