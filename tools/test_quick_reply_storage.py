#!/usr/bin/env python3
"""Execute production prefs save/validation with allocation and I/O faults."""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def function(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def linux(path):
    path = Path(path).resolve()
    return "/mnt/" + path.drive[0].lower() + path.as_posix()[2:] if os.name == "nt" else str(path)


HARNESS = r'''
#include <array>
#include <cassert>
#include <cstring>
#include <cstdlib>
#include <map>
#include <memory>
#include <new>
#include <string>
using Record = std::array<char, 585>;
struct FakeFS {
  std::map<std::string, Record> files;
  bool short_write = false, corrupt_readback = false, commit_fail = false;
  unsigned mutations = 0;
  bool exists(const char* path) { return files.count(path); }
  bool remove(const char* path) { ++mutations; return files.erase(path) != 0; }
};
#define FILESYSTEM FakeFS
struct File {
  FakeFS* fs = nullptr;
  std::string path;
  explicit operator bool() const { return fs && fs->files.count(path); }
  void flush() {}
  void close() {}
};
struct NodePrefs {
  static bool allocation_fail;
  static int live_heap;
  char quick_replies[9][65] = {};
  static void* operator new(size_t size, const std::nothrow_t&) noexcept {
    if (allocation_fail) return nullptr;
    void* ptr = std::malloc(size); if (ptr) ++live_heap; return ptr;
  }
  static void operator delete(void* ptr) noexcept { if (ptr) { --live_heap; std::free(ptr); } }
  static void operator delete(void* ptr, const std::nothrow_t&) noexcept { operator delete(ptr); }
  bool saveSerial(File& file) {
    if (!file) return false;
    std::memcpy(file.fs->files[file.path].data(), quick_replies, sizeof(quick_replies));
    ++file.fs->mutations;
    return !file.fs->short_write;
  }
  bool loadSerial(File& file) {
    if (!file) return false;
    std::memcpy(quick_replies, file.fs->files[file.path].data(), sizeof(quick_replies));
    if (file.fs->corrupt_readback && file.path == "/prefs.json.tmp") quick_replies[0][0] ^= 1;
    return true;
  }
};
bool NodePrefs::allocation_fail = false;
int NodePrefs::live_heap = 0;
static File openRead(FakeFS* fs, const char* path) { return {fs,path}; }
static File openStorageRead(FakeFS* fs, const char* path) { return openRead(fs,path); }
static bool prepareScratch(FakeFS* fs, const char* path) { if (fs->exists(path)) fs->remove(path); return true; }
static File openScratch(FakeFS* fs, const char* path) { fs->files[path] = {}; ++fs->mutations; return {fs,path}; }
static bool commitScratch(FakeFS* fs, const char* target, const char* scratch, const char* backup, bool valid) {
  if (fs->commit_fail) return false;
  if (valid) fs->files[backup] = fs->files[target];
  fs->files[target] = fs->files[scratch]; fs->files.erase(scratch); ++fs->mutations;
  return true;
}
class DataStore {
  FakeFS* _fs;
public:
  explicit DataStore(FakeFS& fs) : _fs(&fs) {}
  bool savePrefs(NodePrefs& prefs);
};
'''

TEST = r'''
int main() {
  for (unsigned fault = 0; fault < 4; ++fault) {
    FakeFS fs;
    Record previous{}; std::strcpy(previous.data(), "previous");
    fs.files["/prefs.json"] = previous;
    NodePrefs next; std::strcpy(next.quick_replies[0], "replacement");
    DataStore store(fs);
    NodePrefs::allocation_fail = fault == 1;
    fs.short_write = fault == 2;
    fs.corrupt_readback = fault == 3;
    assert(store.savePrefs(next) == (fault == 0));
    assert(NodePrefs::live_heap == 0);
    assert(std::strcmp(next.quick_replies[0], "replacement") == 0);
    if (fault) assert(fs.files["/prefs.json"] == previous);
    else assert(std::strcmp(fs.files["/prefs.json"].data(), "replacement") == 0);
    if (fault == 1) assert(fs.mutations == 0);
    assert(!fs.exists("/prefs.json.tmp"));
  }
  NodePrefs::allocation_fail = false;
  FakeFS fs; Record old{}; std::strcpy(old.data(), "old"); fs.files["/prefs.json"] = old;
  fs.commit_fail = true; DataStore store(fs); NodePrefs prefs;
  assert(!store.savePrefs(prefs)); assert(fs.files["/prefs.json"] == old);
  assert(NodePrefs::live_heap == 0);
}
'''


def main():
    source = (ROOT / "examples/companion_radio/DataStore.cpp").read_text(encoding="utf-8")
    validation = function(source, "static bool prefsFileValid(")
    saving = function(source, "bool DataStore::savePrefs(")
    assert "NodePrefs candidate" not in validation
    assert "NodePrefs verification(" not in saving
    assert saving.index("if (!verification) return false;") < saving.index("prepareScratch(")
    with tempfile.TemporaryDirectory(prefix="quick-reply-prefs-") as folder:
        folder = Path(folder)
        cpp, binary = folder / "test.cpp", folder / "test"
        cpp.write_text(HARNESS + validation + saving + TEST, encoding="utf-8")
        prefix = ["wsl", "--exec"] if os.name == "nt" else []
        subprocess.run([*prefix, "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", linux(cpp), "-o", linux(binary)], check=True, timeout=60)
        subprocess.run([*prefix, linux(binary)], check=True, timeout=15)
    print("[PASS] Production DataStore save: checked heap allocation before mutation, reusable verifier, exact quick-reply readback, short write/commit failure preserve primary, RAII cleanup")


if __name__ == "__main__":
    main()
