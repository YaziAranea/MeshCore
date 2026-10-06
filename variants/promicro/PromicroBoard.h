#pragma once

#include <MeshCore.h>
#include <Arduino.h>
#include <helpers/NRF52Board.h>
#include <helpers/AdcCalibration.h>

#define  PIN_VBAT_READ 17
#define  ADC_MULTIPLIER   (1.815f) // dependent on voltage divider resistors. TODO: more accurate battery tracking

class PromicroBoard : public NRF52BoardDCDC {
protected:
  uint8_t btn_prev_state;
  float adc_mult = ADC_MULTIPLIER;
  mesh::BatteryCalibrationSampleCache battery_calibration;

public:
  PromicroBoard() : NRF52Board("ProMicro_OTA") {}
  void begin();

  #define BATTERY_SAMPLES 8

  uint16_t getBattMilliVolts() override {
    const bool source_disturbed_before = isExternalPowered();
    analogReadResolution(12);

    uint32_t raw = 0;
    for (int i = 0; i < BATTERY_SAMPLES; i++) {
      raw += analogRead(PIN_VBAT_READ);
    }
    raw = raw / BATTERY_SAMPLES;
    const uint16_t millivolts = mesh::saturatingBatteryMilliVolts(adc_mult * raw);
    // USB power changes the sensed voltage on supported ProMicro/SuperMini
    // hardware. Keep the last battery-only sample for USB calibration instead
    // of silently deriving a multiplier from that mixed-power reading.
    battery_calibration.capture(millivolts, adc_mult, millis(),
                                source_disturbed_before || isExternalPowered());
    return millivolts;
  }

  bool setAdcMultiplier(float multiplier) override {
    float applied = adc_mult;
    if (!mesh::normalizeAdcMultiplier(multiplier, ADC_MULTIPLIER, applied)) return false;
    if (applied != adc_mult) battery_calibration.invalidate();
    adc_mult = applied;
    return true;
  }
  float getAdcMultiplier() const override {
    if (adc_mult == 0.0f) {
      return ADC_MULTIPLIER;
    } else {
      return adc_mult;
    }
  }
  bool getBatteryCalibrationSample(uint16_t& millivolts, float& multiplier,
                                   uint32_t& age_ms) override {
    // BLE callers can refresh safely while battery-powered. USB callers must
    // use the last pre-USB reading because the live power path is distorted.
    if (!isExternalPowered()) getBattMilliVolts();
    return battery_calibration.read(millis(), millivolts, multiplier, age_ms);
  }

  const char* getManufacturerName() const override {
    return "ProMicro DIY";
  }

  int buttonStateChanged() {
    #ifdef BUTTON_PIN
      uint8_t v = digitalRead(BUTTON_PIN);
      if (v != btn_prev_state) {
        btn_prev_state = v;
        return (v == LOW) ? 1 : -1;
      }
    #endif
      return 0;
  }
};
