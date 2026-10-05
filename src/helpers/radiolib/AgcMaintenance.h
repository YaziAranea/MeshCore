#pragma once

#include <stdint.h>

// Separate from the historical synchronous repeater resetAGC() API.
struct AgcMaintenanceStatus {
  bool active;
  int16_t last_error;
  uint32_t attempts;
  uint32_t completed;
  uint32_t failures;
  uint32_t cancellations;
};

enum class AgcMaintenanceStep : uint8_t {
  Idle, ReadGain, Suspend, Sleep, Wake, Calibrate, WaitCalibration, Image,
  Dio2, WriteGain, ReadPatch, WritePatch, StartRx, Sampling, RestoreRx,
  RecoveryWake, Probe, Sample
};

// Positive return is a safe deferral, not a hardware fault.
static constexpr int16_t AGC_MAINTENANCE_DEFER = 1;
static constexpr int16_t AGC_MAINTENANCE_RX_ACTIVITY = 1;
static constexpr int16_t AGC_MAINTENANCE_RX_READY = 2;
static constexpr int16_t AGC_MAINTENANCE_TIMEOUT = -1100;
static constexpr uint32_t AGC_MAINTENANCE_DEADLINE_MS = 1500;
static constexpr uint32_t AGC_MAINTENANCE_SAMPLE_MS = 350;
static constexpr uint32_t AGC_MAINTENANCE_SPI_TIMEOUT_MS = 50;
