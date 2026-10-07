#pragma once

#include <stdint.h>

namespace smartui {

// Volatile, bounded permission to correct a bad ADC scale while USB supplies
// power. Never persisted, refreshed by polling, or inferred from transport alone.
class AdcCalibrationService {
public:
  static constexpr uint32_t DURATION_MS = 120000U;
  enum class Owner : uint8_t { NONE, USB_CONSOLE, USB_COMPANION };
  enum class Result : uint8_t { OK, READONLY, UNSUPPORTED, USB_REQUIRED, BUSY };

  Result start(uint32_t now, bool supported, bool writable,
               bool external_confirmed, bool local_usb, Owner owner,
               uint32_t session) {
    if (!writable) return Result::READONLY;
    if (!supported) return Result::UNSUPPORTED;
    if (!external_confirmed || !local_usb || owner == Owner::NONE)
      return Result::USB_REQUIRED;
    if (_owner != Owner::NONE) {
      // A retransmitted start is idempotent, not a lease renewal.
      return _owner == owner && _session == session ? Result::OK : Result::BUSY;
    }
    _started = now;
    _session = session;
    _owner = owner;
    return Result::OK;
  }

  bool update(uint32_t now, bool external_confirmed, bool owner_connected,
              uint32_t session, bool writable) {
    if (_owner != Owner::NONE && (!external_confirmed || !owner_connected ||
        session != _session || !writable ||
        static_cast<uint32_t>(now - _started) >= DURATION_MS)) stop();
    return _owner != Owner::NONE;
  }
  void stop() { _owner = Owner::NONE; }
  Owner owner() const { return _owner; }
  uint32_t remaining(uint32_t now) const {
    const uint32_t elapsed = static_cast<uint32_t>(now - _started);
    return _owner != Owner::NONE && elapsed < DURATION_MS ? DURATION_MS - elapsed : 0;
  }

private:
  uint32_t _started = 0;
  uint32_t _session = 0;
  Owner _owner = Owner::NONE;
};

}  // namespace smartui
