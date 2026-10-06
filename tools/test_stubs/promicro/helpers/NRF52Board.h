#pragma once

#include <stdint.h>

bool promicroTestExternalPower();

class NRF52Board {
public:
  NRF52Board() = default;
  explicit NRF52Board(const char*) {}
  virtual ~NRF52Board() = default;
  virtual void begin() {}
  virtual uint16_t getBattMilliVolts() { return 0; }
  virtual bool setAdcMultiplier(float) { return false; }
  virtual float getAdcMultiplier() const { return 0.0f; }
  virtual bool getBatteryCalibrationSample(uint16_t&, float&, uint32_t&) { return false; }
  virtual const char* getManufacturerName() const { return "test"; }
  bool isExternalPowered() { return promicroTestExternalPower(); }
};

class NRF52BoardDCDC : virtual public NRF52Board {
public:
  NRF52BoardDCDC() {}
};
