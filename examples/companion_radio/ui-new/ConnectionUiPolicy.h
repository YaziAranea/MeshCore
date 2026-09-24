#pragma once

#include "../ConnectionTypes.h"

namespace smartui {

inline uint8_t companionModeCapability(CompanionMode mode) {
  switch (mode) {
    case CompanionMode::BLE: return COMPANION_CAP_BLE;
    case CompanionMode::USB: return COMPANION_CAP_USB;
    case CompanionMode::WiFi: return COMPANION_CAP_WIFI;
    default: return 0;
  }
}

inline bool companionModeSupported(const CompanionStatus& status, CompanionMode mode) {
  return (status.capabilities & companionModeCapability(mode)) != 0;
}

inline const char* companionModeName(CompanionMode mode) {
  switch (mode) {
    case CompanionMode::BLE: return "BLE";
    case CompanionMode::USB: return "USB";
    case CompanionMode::WiFi: return "Wi-Fi";
    default: return "?";
  }
}

inline uint8_t companionModeCount(const CompanionStatus& status) {
  uint8_t count = 0;
  if (companionModeSupported(status, CompanionMode::BLE)) count++;
  if (companionModeSupported(status, CompanionMode::USB)) count++;
  if (companionModeSupported(status, CompanionMode::WiFi)) count++;
  return count;
}

inline CompanionMode companionModeAt(const CompanionStatus& status, uint8_t index) {
  static const CompanionMode modes[] = {
    CompanionMode::BLE, CompanionMode::USB, CompanionMode::WiFi
  };
  for (uint8_t i = 0; i < sizeof(modes) / sizeof(modes[0]); ++i) {
    if (!companionModeSupported(status, modes[i])) continue;
    if (index == 0) return modes[i];
    index--;
  }
  return status.selected;
}

inline uint8_t companionModeIndex(const CompanionStatus& status, CompanionMode mode) {
  const uint8_t count = companionModeCount(status);
  for (uint8_t i = 0; i < count; ++i) {
    if (companionModeAt(status, i) == mode) return i;
  }
  return count;  // Back row when a stale/unsupported value is reported.
}

enum class ConnectionUiView : uint8_t {
  Status,
  Picker,
  Confirm,
};

inline bool wifiApprovalSurfaceSafe(bool settings_open, bool connection_page,
                                    ConnectionUiView connection_view,
                                    bool default_or_clock_page) {
  if (connection_view != ConnectionUiView::Status) return false;
  // Reading the connection status/IP is the natural place to initiate a
  // Wi-Fi client. The modal overlays it and returns without losing settings.
  if (settings_open) return connection_page;
  return default_or_clock_page;
}

class ConnectionUiFlow {
  ConnectionUiView _view;
  uint8_t _cursor;
  CompanionMode _candidate;
  bool _confirm_change;

public:
  ConnectionUiFlow()
      : _view(ConnectionUiView::Status), _cursor(0),
        _candidate(CompanionMode::BLE), _confirm_change(false) {}

  void reset() {
    _view = ConnectionUiView::Status;
    _cursor = 0;
    _candidate = CompanionMode::BLE;
    _confirm_change = false;
  }

  ConnectionUiView view() const { return _view; }
  uint8_t cursor() const { return _cursor; }
  CompanionMode candidate() const { return _candidate; }
  bool confirmChange() const { return _confirm_change; }

  void openPicker(const CompanionStatus& status) {
    _view = ConnectionUiView::Picker;
    _cursor = companionModeIndex(status, status.selected);
    _confirm_change = false;
  }

  void movePicker(const CompanionStatus& status, int8_t delta) {
    const uint8_t item_count = companionModeCount(status) + 1;  // Back.
    if (item_count == 0) return;
    if (_cursor >= item_count) _cursor = item_count - 1;
    _cursor = delta < 0
        ? (_cursor + item_count - 1) % item_count
        : (_cursor + 1) % item_count;
  }

  bool pickerOnBack(const CompanionStatus& status) const {
    return _cursor >= companionModeCount(status);
  }

  // Returns true only when a mode change needs confirmation.
  bool selectPicker(const CompanionStatus& status) {
    if (pickerOnBack(status)) {
      reset();
      return false;
    }
    _candidate = companionModeAt(status, _cursor);
    if (_candidate == status.selected) {
      reset();
      return false;
    }
    _view = ConnectionUiView::Confirm;
    _confirm_change = false;  // Safe default: keep current connection.
    return true;
  }

  void moveConfirm() { _confirm_change = !_confirm_change; }

  void cancelConfirm() {
    _view = ConnectionUiView::Picker;
    _confirm_change = false;
  }
};

class WifiApprovalUiFlow {
  bool _open;
  uint32_t _request_id;
  bool _allow;

public:
  WifiApprovalUiFlow() : _open(false), _request_id(0), _allow(false) {}

  bool open() const { return _open; }
  uint32_t requestId() const { return _request_id; }
  bool allow() const { return _allow; }

  // Returns true only when a new request was opened. Repeated snapshots keep
  // the local cursor, while a new request always returns to DENY.
  bool sync(const CompanionStatus& status) {
    if (!status.wifiApprovalPending || status.wifiRequestId == 0) {
      reset();
      return false;
    }
    if (_open && _request_id == status.wifiRequestId) return false;
    _open = true;
    _request_id = status.wifiRequestId;
    _allow = false;
    return true;
  }

  void toggle() {
    if (_open) _allow = !_allow;
  }

  void reset() {
    _open = false;
    _request_id = 0;
    _allow = false;
  }
};

}  // namespace smartui
