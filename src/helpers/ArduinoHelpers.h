#pragma once

#include <Mesh.h>
#include <Arduino.h>
#include "RTCClockQuality.h"

#ifdef NRF52_PLATFORM
// v2 invalidates the old marker because previous firmware persisted its
// hardcoded 2026 seed as if it had been synchronised.
#define CLOCK_MAGIC_NUM        0xAA55CC34

extern uint32_t persistent_magic;
extern uint32_t persistent_time;
#endif

class VolatileRTCClock : public mesh::RTCClock {
  uint32_t base_time;
  uint64_t accumulator;
  unsigned long prev_millis;
  bool time_trusted;

public:
  VolatileRTCClock() {
#ifdef NRF52_PLATFORM
    if (persistent_magic == CLOCK_MAGIC_NUM && meshRtcTimestampPlausible(persistent_time)) {
      base_time = persistent_time;
      time_trusted = true;
    } else {
      base_time = 0;
      time_trusted = false;
    }
#else
    base_time = 0;
    time_trusted = false;
#endif

    accumulator = 0;
    prev_millis = millis();
  }

  uint32_t getCurrentTime() override { return base_time + accumulator/1000; }

  bool isTimeTrusted() override {
    return time_trusted && meshRtcTimestampPlausible(getCurrentTime());
  }

  void setCurrentTime(uint32_t time) override {
    base_time = time;
    accumulator = 0;
    prev_millis = millis();
    time_trusted = meshRtcTimestampPlausible(time);

#ifdef NRF52_PLATFORM
    if (time_trusted) {
      persistent_magic = CLOCK_MAGIC_NUM;
      persistent_time = time;
    } else {
      persistent_magic = 0;
      persistent_time = 0;
    }
#endif
  }

  void setEstimatedTime(uint32_t time) override {
    if (isTimeTrusted()) return;
    base_time = time;
    accumulator = 0;
    prev_millis = millis();
    time_trusted = false;
#ifdef NRF52_PLATFORM
    persistent_magic = 0;
    persistent_time = 0;
#endif
  }

  void tick() override {
    unsigned long now = millis();
    accumulator += (now - prev_millis);
    prev_millis = now;

#ifdef NRF52_PLATFORM
    if (time_trusted) {
      persistent_magic = CLOCK_MAGIC_NUM;
      persistent_time = getCurrentTime();
    }
#endif
  }
};

class ArduinoMillis : public mesh::MillisecondClock {
public:
  unsigned long getMillis() override { return millis(); }
};

class StdRNG : public mesh::RNG {
public:
  void begin(long seed) { randomSeed(seed); }
  void random(uint8_t* dest, size_t sz) override {
    for (int i = 0; i < sz; i++) {
      dest[i] = (::random(0, 256) & 0xFF);
    }
  }
};
