#pragma once

#include <Mesh.h>
#include <Arduino.h>
#include <Wire.h>
#include "RTCClockQuality.h"

class AutoDiscoverRTCClock : public mesh::RTCClock {
  mesh::RTCClock* _fallback;
  bool _hardware_time_trusted;

  bool i2c_probe(TwoWire& wire, uint8_t addr);
  bool hasHardwareRTC() const;
  uint32_t readHardwareTime();

public:
  explicit AutoDiscoverRTCClock(mesh::RTCClock& fallback)
      : _fallback(&fallback), _hardware_time_trusted(false) { }

  void begin(TwoWire& wire);
  uint32_t getCurrentTime() override;
  void setCurrentTime(uint32_t time) override;
  void setEstimatedTime(uint32_t time) override;
  bool isTimeTrusted() override;

  void tick() override {
    _fallback->tick();   // is typically VolatileRTCClock, which now needs tick()
  }
};
