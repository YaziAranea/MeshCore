#pragma once

#include <stdint.h>

enum class CompanionMode : uint8_t {
  BLE = 0,
  USB = 1,
  WiFi = 2,
};

enum class ConnectionChangeError : uint8_t {
  None = 0,
  NotStarted,
  CliRescue,
  StorageReadOnly,
  Unavailable,
  StorageUnavailable,
  TempCleanup,
  Write,
  VerifyTemp,
  Rotate,
  Publish,
  VerifyFinal,
  Apply,
};

enum CompanionCapability : uint8_t {
  COMPANION_CAP_BLE = 1u << 0,
  COMPANION_CAP_USB = 1u << 1,
  COMPANION_CAP_WIFI = 1u << 2,
};

struct CompanionStatus {
  uint8_t capabilities = 0;
  CompanionMode selected = CompanionMode::BLE;
  bool clientConnected = false;
  CompanionMode connectedVia = CompanionMode::BLE;
  bool usbConsoleEnabled = true;
  bool wifiConfigured = false;
  bool wifiAssociated = false;
  char wifiLocalIp[16] = {};
  bool wifiApprovalPending = false;
  uint32_t wifiRequestId = 0;
  char wifiClientIp[16] = {};
  uint32_t wifiApprovalRemainingMs = 0;
};
