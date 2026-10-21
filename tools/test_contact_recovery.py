#!/usr/bin/env python3
"""Exercise production contact recovery and interrupted publish operations.

Legacy contacts3 has no persisted record count or checksum. These tests verify
candidate preference and structural rejection, not proof of complete file data.
No board or persistent storage is used.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

from test_contact_persistence import HARNESS, ROOT, function, linux


def production():
    source = (ROOT / "examples/companion_radio/DataStore.cpp").read_text(encoding="utf-8")
    names = ("static File openStorageRead(", "static bool digestFile(",
             "static bool commitScratch(", "static bool fixedRecordFileValid(",
             "static bool encodedPathLenValid(", "static bool contactRecordFileValid(",
             "static mesh::storage::RecoveryCandidate chooseContactCandidate(",
             "static const char* candidatePath(")
    return function(source, "struct FileDigest") + ";\n" + "\n".join(
        function(source, name) for name in names)


def recovery_harness():
    code = HARNESS.split("class MyMesh :", 1)[0]
    changes = {
        "struct FakeFS {": """
struct PowerCut {};
struct FakeFS {
  unsigned mutation = 0, cut_before = 0, cut_after = 0;
  void beforeMutation() {
    if (++mutation == cut_before) throw PowerCut{};
  }
  void afterMutation() {
    if (mutation == cut_after) throw PowerCut{};
  }
""",
        "return files.erase(path) != 0;": """
    beforeMutation();
    const bool removed = files.erase(path) != 0;
    afterMutation();
    return removed;
""",
        "files[to] = files[from]; files.erase(from); return true;": """
    beforeMutation();
    files[to] = files[from]; files.erase(from);
    afterMutation();
    return true;
""",
    }
    for before, after in changes.items():
        assert code.count(before) == 1, before
        code = code.replace(before, after)
    return code


TESTS = r'''
using mesh::storage::RecoveryCandidate;
static Bytes records(unsigned count, uint8_t generation) {
  Bytes result(count * 152, 0);
  for (unsigned i = 0; i < count; ++i) {
    const unsigned offset = i * 152;
    result[offset] = static_cast<uint8_t>(i);
    result[offset + 1] = generation;
    std::memcpy(result.data() + offset + 32, "contact", 8);
    result[offset + 64] = ADV_TYPE_CHAT;
    result[offset + 71] = OUT_PATH_UNKNOWN;
  }
  return result;
}
static RecoveryCandidate selected(FakeFS& fs) {
  const auto before = fs.files;
  const auto result = chooseContactCandidate(
      &fs, "/contacts3", "/contacts3.tmp", "/contacts3.bak");
  expect(fs.files == before);  // Merely loading never removes recovery data.
  return result;
}
static Bytes selectedBytes(FakeFS& fs) {
  const char* path = candidatePath(selected(fs), "/contacts3", "/contacts3.tmp",
                                   "/contacts3.bak");
  expect(path != nullptr);
  return fs.files.at(path);
}
static void testAlignedTruncationCannotSupersedeBackup() {
  for (bool missing_primary : {false, true}) {
    for (unsigned complete_prefix : {0U, 1U}) {
      FakeFS fs;
      const Bytes committed = records(2, 1);
      fs.files["/contacts3.bak"] = committed;
      fs.files["/contacts3.tmp"] = records(complete_prefix, 2);
      if (!missing_primary) fs.files["/contacts3"] = {99};
      // An interrupted write at a record boundary passes legacy validation.
      expect(contactRecordFileValid(&fs, "/contacts3.tmp"));
      expect(selected(fs) == RecoveryCandidate::BACKUP);
      expect(selectedBytes(fs) == committed);
    }
  }
}
static void testCutsAroundPublishMutations() {
  const Bytes old = records(2, 1), next = records(3, 2);
  for (bool after : {false, true}) {
    for (unsigned cut = 1; cut <= 3; ++cut) {
      FakeFS fs;
      fs.files["/contacts3"] = old;
      fs.files["/contacts3.bak"] = records(1, 0);
      fs.files["/contacts3.tmp"] = next;
      fs.files["/unrelated"] = {11, 22};
      if (after) fs.cut_after = cut; else fs.cut_before = cut;
      bool interrupted = false;
      try {
        commitScratch(&fs, "/contacts3", "/contacts3.tmp", "/contacts3.bak", true);
      } catch (const PowerCut&) { interrupted = true; }
      expect(interrupted);
      // Mutations: remove old backup; primary->backup; temporary->primary.
      // Before publication the durable old generation wins over scratch.
      const bool published = after && cut == 3;
      expect(selectedBytes(fs) == (published ? next : old));
      expect(fs.files["/unrelated"] == Bytes({11, 22}));
    }
  }
  // Both publication and rollback may fail; the old backup remains preferable
  // even though this scratch happened to finish writing before the failures.
  FakeFS fs;
  fs.files["/contacts3"] = old; fs.files["/contacts3.tmp"] = next;
  fs.rename_fail_source = "/contacts3.tmp"; fs.rollback_fail = true;
  expect(!commitScratch(&fs, "/contacts3", "/contacts3.tmp", "/contacts3.bak", true));
  expect(selected(fs) == RecoveryCandidate::BACKUP);
  expect(selectedBytes(fs) == old);
}
static void testFirstCreateAndUnavailableCommittedCopies() {
  const Bytes next = records(2, 2);
  for (bool after : {false, true}) {
    FakeFS fs; fs.files["/contacts3.tmp"] = next;
    if (after) fs.cut_after = 1; else fs.cut_before = 1;
    bool interrupted = false;
    try {
      commitScratch(&fs, "/contacts3", "/contacts3.tmp", "/contacts3.bak", false);
    } catch (const PowerCut&) { interrupted = true; }
    expect(interrupted);
    expect(selected(fs) == (after ? RecoveryCandidate::PRIMARY : RecoveryCandidate::TEMPORARY));
    expect(selectedBytes(fs) == next);
  }
  for (int fault = 0; fault < 6; ++fault) {
    FakeFS fs;
    fs.files["/contacts3.bak"] = records(2, 1);
    fs.files["/contacts3.tmp"] = next;
    if (fault == 0) fs.files["/contacts3.bak"].pop_back();
    if (fault == 1) fs.files["/contacts3.bak"][64] = 0;
    if (fault == 2) std::memset(fs.files["/contacts3.bak"].data() + 32, 'X', 32);
    if (fault == 3) fs.files["/contacts3.bak"][71] = 0xC1;
    if (fault == 4) fs.read_fail = "/contacts3.bak";
    if (fault == 5) fs.open_fail = "/contacts3.bak";
    expect(selected(fs) == RecoveryCandidate::TEMPORARY);
    expect(selectedBytes(fs) == next);
    fs.files["/contacts3.tmp"].pop_back();
    expect(selected(fs) == RecoveryCandidate::NONE);
  }
  FakeFS empty;
  expect(selected(empty) == RecoveryCandidate::NONE);
  // A published empty address book is valid and must not revive old contacts.
  empty.files["/contacts3"] = {};
  empty.files["/contacts3.bak"] = next;
  expect(selected(empty) == RecoveryCandidate::PRIMARY);
  expect(selectedBytes(empty).empty());
}
static void testLegacyValidationLimitRemainsExplicit() {
  FakeFS fs;
  fs.files["/contacts3"] = records(1, 1);
  fs.files["/contacts3.bak"] = records(2, 0);
  fs.files["/contacts3.tmp"] = records(3, 2);
  // Without a persisted CRC/count, a flipped key or a record-aligned prefix
  // can be structurally valid. This policy does not claim to detect either.
  fs.files["/contacts3"][0] ^= 0x40;
  expect(contactRecordFileValid(&fs, "/contacts3"));
  expect(selected(fs) == RecoveryCandidate::PRIMARY);
  fs.files.erase("/contacts3"); fs.files.erase("/contacts3.bak");
  fs.files["/contacts3.tmp"].resize(152);
  expect(selected(fs) == RecoveryCandidate::TEMPORARY);
}
int main() {
  testAlignedTruncationCannotSupersedeBackup();
  testCutsAroundPublishMutations();
  testFirstCreateAndUnavailableCommittedCopies();
  testLegacyValidationLimitRemainsExplicit();
  std::printf("PASS %u contact recovery assertions: backup before unpublished scratch; publish cuts, first create, structural/read faults; legacy CRC/count limit explicit\n", checks);
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix="contact-recovery-") as folder:
        folder = Path(folder)
        cpp, binary = folder / "test.cpp", folder / "test"
        cpp.write_text(recovery_harness() + production() + TESTS, encoding="utf-8")
        compiler = shutil.which("g++")
        prefix = [] if compiler else ["wsl", "--exec"]
        path = str if compiler else linux
        subprocess.run([*prefix, compiler or "g++", "-std=c++17", "-Wall", "-Wextra",
                        "-Werror", "-pedantic", "-O2", "-I", path(ROOT / "src"),
                        path(cpp), "-o", path(binary)], check=True, timeout=60)
        subprocess.run([*prefix, path(binary)], check=True, timeout=30)


if __name__ == "__main__":
    main()
