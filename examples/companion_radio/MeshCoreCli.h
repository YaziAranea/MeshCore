#pragma once

#include <stddef.h>
#include <stdint.h>

namespace smartui {

// The companion commands of upstream MeshCore (dev, PR #3298 and follow-ups),
// accepted on the same local CMD66 as `ui ...`. Replies keep upstream's text
// ("OK", "> value", "Error, ...") so an app written for upstream reads them.
// Settings that SmartUI has no backend for answer "Error: unsupported" rather
// than "Unknown command", so a client can tell a known command from a typo.
struct MeshCoreCliState {
  float freq = 0, bw = 0;
  uint8_t sf = 0, cr = 0;
  int8_t tx_dbm = 0;
  int8_t max_tx_dbm = 0;
  float airtime_factor = 0;
  float rx_delay = 0;
  uint8_t multi_acks = 0;
  uint8_t path_hash_mode = 0;
  bool rx_gain = false;
  int16_t tz_minutes = 0;
};

enum class MeshCoreCliResult : uint8_t { OK, STORAGE, UNSUPPORTED, BUSY };

struct MeshCoreCliHooks {
  MeshCoreCliState (*read)() = nullptr;
  MeshCoreCliResult (*setName)(const char* name) = nullptr;
  MeshCoreCliResult (*setPin)(uint32_t pin) = nullptr;
  MeshCoreCliResult (*setTxPower)(int8_t dbm) = nullptr;
  MeshCoreCliResult (*setTuning)(float rx_delay, float airtime_factor) = nullptr;
  MeshCoreCliResult (*setMultiAcks)(uint8_t count) = nullptr;
  MeshCoreCliResult (*setPathHashMode)(uint8_t mode) = nullptr;
  MeshCoreCliResult (*setRxGain)(bool boosted) = nullptr;
  MeshCoreCliResult (*setTimezoneMinutes)(int16_t minutes) = nullptr;
  // `set radio` runs through the existing `ui radio set` transaction, so the
  // validation, rollback and path-bytes rules stay in one place.
  bool (*radioCommand)(const char* command, char* reply, size_t capacity,
                       bool allow_mutation) = nullptr;
  // Return only on failure; a successful reboot or power-off never returns,
  // exactly as upstream, which sends no reply to either.
  MeshCoreCliResult (*reboot)() = nullptr;
  MeshCoreCliResult (*powerOff)() = nullptr;
  // False when the build has no Wi-Fi transport.
  bool (*wifiStatus)(bool& associated, char* ip, size_t ip_capacity) = nullptr;
  bool (*busy)() = nullptr;
};

class MeshCoreCli {
public:
  void begin(const MeshCoreCliHooks& hooks) { _hooks = hooks; }
  // False for a command upstream does not have either; the caller answers
  // "Unknown command". The reply is at most 156 bytes plus NUL.
  bool handle(const char* command, char* reply, size_t capacity, bool allow_mutation);

private:
  MeshCoreCliHooks _hooks;
};

}  // namespace smartui
