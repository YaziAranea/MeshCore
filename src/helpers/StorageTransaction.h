#pragma once

#include <stddef.h>
#include <stdint.h>

// Small, platform-independent pieces of the persistent-storage transaction
// policy.  Keeping these free of Arduino FS types makes the recovery rules and
// integrity calculation directly testable in the native test suite.
namespace mesh {
namespace storage {

enum class RecoveryCandidate : uint8_t {
  NONE = 0,
  PRIMARY,
  TEMPORARY,
  BACKUP,
};

inline RecoveryCandidate chooseRecoveryCandidate(bool primary_valid,
                                                  bool temporary_valid,
                                                  bool backup_valid) {
  if (primary_valid) return RecoveryCandidate::PRIMARY;
  // A temporary file is only published after its complete contents have been
  // verified.  If power failed between rotating the old file and publishing
  // the new one, it is therefore the newest complete generation.
  if (temporary_valid) return RecoveryCandidate::TEMPORARY;
  if (backup_valid) return RecoveryCandidate::BACKUP;
  return RecoveryCandidate::NONE;
}

class Crc32 {
  uint32_t _state = 0xFFFFFFFFu;

public:
  void update(const uint8_t* data, size_t len) {
    while (len-- > 0) {
      _state ^= *data++;
      for (uint8_t bit = 0; bit < 8; ++bit) {
        const uint32_t mask = (uint32_t)-(int32_t)(_state & 1u);
        _state = (_state >> 1) ^ (0xEDB88320u & mask);
      }
    }
  }

  uint32_t value() const { return _state ^ 0xFFFFFFFFu; }
};

}  // namespace storage
}  // namespace mesh
