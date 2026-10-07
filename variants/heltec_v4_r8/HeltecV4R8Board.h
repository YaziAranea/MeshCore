#pragma once

#include <Arduino.h>
#include <driver/rtc_io.h>
#include <helpers/ESP32Board.h>
#include <helpers/AdcCalibration.h>
#include <helpers/RefCountedDigitalPin.h>
#include "LoRaFEMControl.h"

#ifndef ADC_MULTIPLIER
  #define ADC_MULTIPLIER (4.9f * 1.035f)
#endif

class HeltecV4R8Board : public ESP32Board {
protected:
  float adc_mult = ADC_MULTIPLIER;

public:
  RefCountedDigitalPin periph_power;
  LoRaFEMControl loRaFEMControl;

  HeltecV4R8Board() : periph_power(PIN_VEXT_EN, PIN_VEXT_EN_ACTIVE) { }

  void begin();
  void onBeforeTransmit(void) override;
  void onAfterTransmit(void) override;
  void shutdownPeripherals() override;
  bool setLoRaFemLnaEnabled(bool enable) override;
  bool canControlLoRaFemLna() const override { return true; }
  bool isLoRaFemLnaEnabled() const override { return loRaFEMControl.isLNAEnabled(); }
  uint16_t getBattMilliVolts() override;
  bool setAdcMultiplier(float multiplier) override {
    float applied = adc_mult;
    if (!mesh::normalizeAdcMultiplier(multiplier, ADC_MULTIPLIER, applied)) return false;
    adc_mult = applied;
    return true;
  }
  float getAdcMultiplier() const override { return adc_mult; }
  const char* getManufacturerName() const override;
};
