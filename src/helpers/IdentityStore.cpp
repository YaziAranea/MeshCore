#include "IdentityStore.h"

#include <helpers/StorageTransaction.h>

namespace {

static bool makeIdentityPath(const char* dir, const char* name,
                             char* dest, size_t dest_size) {
  const int n = snprintf(dest, dest_size, "%s/%s.id", dir, name);
  return n > 0 && (size_t)n < dest_size;
}

static bool makeSiblingPath(const char* filename, const char* suffix,
                            char* dest, size_t dest_size) {
  const int n = snprintf(dest, dest_size, "%s%s", filename, suffix);
  return n > 0 && (size_t)n < dest_size;
}

static File openIdentityRead(FILESYSTEM* fs, const char* filename) {
#if defined(NRF52_PLATFORM) || defined(STM32_PLATFORM)
  return fs->open(filename, FILE_O_READ);
#elif defined(RP2040_PLATFORM)
  return fs->open(filename, "r");
#else
  return fs->open(filename, "r", false);
#endif
}

static bool prepareIdentityScratch(FILESYSTEM* fs, const char* filename) {
  return !fs->exists(filename) || fs->remove(filename);
}

static File openIdentityScratch(FILESYSTEM* fs, const char* filename) {
#if defined(NRF52_PLATFORM) || defined(STM32_PLATFORM)
  return fs->open(filename, FILE_O_WRITE);
#elif defined(RP2040_PLATFORM)
  return fs->open(filename, "w");
#else
  return fs->open(filename, "w", true);
#endif
}

static bool identityIsCoherent(const mesh::LocalIdentity& identity) {
  // LocalIdentity::writeTo() is not const in every supported MeshCore target,
  // so validate an isolated copy instead of mutating the caller's identity.
  mesh::LocalIdentity candidate = identity;
  uint8_t serialized[PRV_KEY_SIZE + PUB_KEY_SIZE];
  if (candidate.writeTo(serialized, sizeof(serialized)) != sizeof(serialized)) return false;

  // Re-derive the public half from the stored private key.  This catches
  // same-length corruption which a simple file-size check cannot detect.
  mesh::LocalIdentity derived;
  derived.readFrom(serialized, PRV_KEY_SIZE);
  return derived.matches(candidate);
}

static bool identityFileHasExpectedSize(FILESYSTEM* fs, const char* filename) {
  if (!fs->exists(filename)) return false;
  File file = openIdentityRead(fs, filename);
  if (!file) return false;
  const uint32_t size = (uint32_t)file.size();
  mesh::LocalIdentity candidate;
  const bool readable = candidate.readFrom(file);
  file.close();
  // Legacy files are raw public+private key bytes, optionally followed by the
  // fixed 32-byte display name. Preserve that format for compatibility.
  return readable && identityIsCoherent(candidate) &&
         (size == (PUB_KEY_SIZE + PRV_KEY_SIZE) ||
          size == (PUB_KEY_SIZE + PRV_KEY_SIZE + 32));
}

static mesh::storage::RecoveryCandidate chooseIdentityCandidate(
    FILESYSTEM* fs, const char* target, const char* scratch,
    const char* backup) {
  return mesh::storage::chooseRecoveryCandidate(
      identityFileHasExpectedSize(fs, target),
      identityFileHasExpectedSize(fs, scratch),
      identityFileHasExpectedSize(fs, backup));
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

static bool commitIdentityScratch(FILESYSTEM* fs, const char* target,
                                  const char* scratch, const char* backup) {
  const bool had_target = fs->exists(target);
  const bool target_valid = identityFileHasExpectedSize(fs, target);
  bool rotated_target = false;
  if (had_target && target_valid) {
    if (fs->exists(backup) && !fs->remove(backup)) return false;
    if (!fs->rename(target, backup)) return false;
    rotated_target = true;
  } else if (had_target) {
    // Preserve a valid backup when the primary is known to be corrupt.
    if (!fs->remove(target)) return false;
  }
  if (fs->rename(scratch, target)) return true;
  if (rotated_target && !fs->exists(target) && fs->exists(backup)) {
    fs->rename(backup, target);
  }
  return false;
}

static bool loadIdentityFile(FILESYSTEM* fs, const char* filename,
                             mesh::LocalIdentity& id, char* display_name,
                             int max_name_sz) {
  File file = openIdentityRead(fs, filename);
  if (!file) return false;

  mesh::LocalIdentity candidate;
  bool loaded = candidate.readFrom(file) && identityIsCoherent(candidate);
  if (loaded && display_name && max_name_sz > 0) {
    char stored_name[32];
    memset(stored_name, 0, sizeof(stored_name));
    if (file.available() > 0) {
      const size_t got = file.read((uint8_t*)stored_name, sizeof(stored_name));
      loaded = got == sizeof(stored_name);
    }
    if (loaded) {
      int n = max_name_sz - 1;
      if (n > 31) n = 31;
      if (n > 0) memcpy(display_name, stored_name, (size_t)n);
      display_name[n > 0 ? n : 0] = 0;
    }
  }
  file.close();
  if (loaded) id = candidate;
  return loaded;
}

static bool verifyIdentityScratch(FILESYSTEM* fs, const char* filename,
                                  const mesh::LocalIdentity& expected,
                                  uint32_t expected_size) {
  File file = openIdentityRead(fs, filename);
  if (!file || (uint32_t)file.size() != expected_size) {
    if (file) file.close();
    return false;
  }
  mesh::LocalIdentity actual;
  bool success = actual.readFrom(file) && actual.matches(expected);
  file.close();
  if (success) {
    uint8_t expected_bytes[PRV_KEY_SIZE + PUB_KEY_SIZE];
    uint8_t actual_bytes[PRV_KEY_SIZE + PUB_KEY_SIZE];
    // The buffer serializer is logically const (it only copies the keys), but
    // its legacy declaration lacks a const qualifier.
    const size_t expected_len = const_cast<mesh::LocalIdentity&>(expected).writeTo(
        expected_bytes, sizeof(expected_bytes));
    const size_t actual_len = actual.writeTo(actual_bytes, sizeof(actual_bytes));
    success = expected_len == sizeof(expected_bytes) &&
              actual_len == sizeof(actual_bytes) &&
              memcmp(expected_bytes, actual_bytes, sizeof(expected_bytes)) == 0;
  }
  return success;
}

}  // namespace

bool IdentityStore::hasAnyGeneration(const char *name) const {
  char filename[64];
  char scratch[64];
  char backup[64];
  if (!makeIdentityPath(_dir, name, filename, sizeof(filename)) ||
      !makeSiblingPath(filename, ".tmp", scratch, sizeof(scratch)) ||
      !makeSiblingPath(filename, ".bak", backup, sizeof(backup))) return false;
  return _fs->exists(filename) || _fs->exists(scratch) || _fs->exists(backup);
}

IdentityLoadStatus IdentityStore::loadWithStatus(const char *name,
                                                 mesh::LocalIdentity& id) {
  char filename[64];
  char scratch[64];
  char backup[64];
  if (!makeIdentityPath(_dir, name, filename, sizeof(filename)) ||
      !makeSiblingPath(filename, ".tmp", scratch, sizeof(scratch)) ||
      !makeSiblingPath(filename, ".bak", backup, sizeof(backup))) {
    return IdentityLoadStatus::CORRUPT_OR_IO;
  }

  const bool any_generation = _fs->exists(filename) || _fs->exists(scratch) ||
                              _fs->exists(backup);

  const char* selected = candidatePath(
      chooseIdentityCandidate(_fs, filename, scratch, backup),
      filename, scratch, backup);
  if (!selected) {
    return any_generation ? IdentityLoadStatus::CORRUPT_OR_IO
                          : IdentityLoadStatus::NOT_FOUND;
  }
  return loadIdentityFile(_fs, selected, id, nullptr, 0)
             ? IdentityLoadStatus::LOADED
             : IdentityLoadStatus::CORRUPT_OR_IO;
}

bool IdentityStore::load(const char *name, mesh::LocalIdentity& id) {
  return loadWithStatus(name, id) == IdentityLoadStatus::LOADED;
}

bool IdentityStore::load(const char *name, mesh::LocalIdentity& id,
                         char display_name[], int max_name_sz) {
  if (display_name && max_name_sz > 0) display_name[0] = 0;
  char filename[64];
  char scratch[64];
  char backup[64];
  if (!makeIdentityPath(_dir, name, filename, sizeof(filename)) ||
      !makeSiblingPath(filename, ".tmp", scratch, sizeof(scratch)) ||
      !makeSiblingPath(filename, ".bak", backup, sizeof(backup))) return false;

  const char* selected = candidatePath(
      chooseIdentityCandidate(_fs, filename, scratch, backup),
      filename, scratch, backup);
  return selected && loadIdentityFile(_fs, selected, id, display_name, max_name_sz);
}

bool IdentityStore::save(const char *name, const mesh::LocalIdentity& id) {
  // Never make an internally inconsistent private/public key pair durable.
  if (!identityIsCoherent(id)) return false;

  char filename[64];
  char scratch[64];
  char backup[64];
  if (!makeIdentityPath(_dir, name, filename, sizeof(filename)) ||
      !makeSiblingPath(filename, ".tmp", scratch, sizeof(scratch)) ||
      !makeSiblingPath(filename, ".bak", backup, sizeof(backup))) return false;

  if (!prepareIdentityScratch(_fs, scratch)) return false;
  File file = openIdentityScratch(_fs, scratch);
  if (!file) return false;
  bool success = id.writeTo(file);
  file.flush();
  file.close();
  success = success && verifyIdentityScratch(
      _fs, scratch, id, PUB_KEY_SIZE + PRV_KEY_SIZE);
  if (success) success = commitIdentityScratch(_fs, filename, scratch, backup);
  if (!success && _fs->exists(scratch)) _fs->remove(scratch);
  MESH_DEBUG_PRINTLN("IdentityStore::save() transactional write - %s",
                     success ? "OK" : "Err");
  return success;
}

bool IdentityStore::save(const char *name, const mesh::LocalIdentity& id,
                         const char display_name[]) {
  // Never make an internally inconsistent private/public key pair durable.
  if (!identityIsCoherent(id)) return false;

  char filename[64];
  char scratch[64];
  char backup[64];
  if (!makeIdentityPath(_dir, name, filename, sizeof(filename)) ||
      !makeSiblingPath(filename, ".tmp", scratch, sizeof(scratch)) ||
      !makeSiblingPath(filename, ".bak", backup, sizeof(backup))) return false;

  if (!prepareIdentityScratch(_fs, scratch)) return false;
  File file = openIdentityScratch(_fs, scratch);
  if (!file) return false;
  bool success = id.writeTo(file);

  uint8_t stored_name[32];
  memset(stored_name, 0, sizeof(stored_name));
  if (display_name) {
    size_t n = strlen(display_name);
    if (n > sizeof(stored_name) - 1) n = sizeof(stored_name) - 1;
    memcpy(stored_name, display_name, n);
  }
  success = success && file.write(stored_name, sizeof(stored_name)) == sizeof(stored_name);
  file.flush();
  file.close();
  success = success && verifyIdentityScratch(
      _fs, scratch, id, PUB_KEY_SIZE + PRV_KEY_SIZE + sizeof(stored_name));
  if (success) success = commitIdentityScratch(_fs, filename, scratch, backup);
  if (!success && _fs->exists(scratch)) _fs->remove(scratch);
  return success;
}
