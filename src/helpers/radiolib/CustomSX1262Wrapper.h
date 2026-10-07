#pragma once

#include "CustomSX1262.h"
#include "RadioLibWrappers.h"
#include "SX126xReset.h"

#ifndef USE_SX1262
#define USE_SX1262
#endif

class CustomSX1262Wrapper : public RadioLibWrapper {
public:
  // Ask the radio rather than assume RadioLib's 5000 us default: startReceive-
  // DutyCycle subtracts tcxoDelay + 1000 from the sleep and the register
  // underflows below that, so the floor is a property of this board's TCXO. A
  // board without one can duty cycle with a far shorter sleep. The 100 us on
  // top clears the 15.625 us register tick that must remain.
  uint32_t rxPowerSavingTransitionUs() const override {
    return ((CustomSX1262 *)_radio)->getTcxoDelay() + 1000;
  }

  CustomSX1262Wrapper(CustomSX1262& radio, mesh::MainBoard& board) : RadioLibWrapper(radio, board) { }

  void setParams(float freq, float bw, uint8_t sf, uint8_t cr) override {
    (void)setParamsChecked(freq, bw, sf, cr);
  }

  bool validateParams(float freq, float bw, uint8_t sf, uint8_t cr) const override {
    return validSX1262LoRaParams(freq, bw, sf, cr);
  }

  bool setParamsChecked(float freq, float bw, uint8_t sf, uint8_t cr) override {
    if (!validateParams(freq, bw, sf, cr)) return false;
    float canonical_bw;
    if (!canonicalSX1262Bandwidth(bw, canonical_bw)) return false;
    bw = canonical_bw; // Same exact bandwidth for the chip and time-on-air cache.
    // A caller can restore the previous parameters after a partial SPI error.
    // Until a complete application succeeds, never send on an unknown channel.
    _config_valid = false;
    idle();
    if (((CustomSX1262 *)_radio)->setFrequency(freq) != RADIOLIB_ERR_NONE ||
        ((CustomSX1262 *)_radio)->setSpreadingFactor(sf) != RADIOLIB_ERR_NONE ||
        ((CustomSX1262 *)_radio)->setBandwidth(bw) != RADIOLIB_ERR_NONE ||
        ((CustomSX1262 *)_radio)->setCodingRate(cr) != RADIOLIB_ERR_NONE ||
        _radio->setPreambleLength(preambleLengthForSF(sf)) != RADIOLIB_ERR_NONE) {
      _radio->standby();
      return false;
    }
    _preamble_sf = sf;
    PacketMillis pm = calcMaxPacketMillis(sf, bw, cr, preambleLengthForSF(sf));
    ((CustomSX1262 *)_radio)->setPreambleMillis(pm.preambleMillis);
    ((CustomSX1262 *)_radio)->setMaxPayloadMillis(pm.payloadMillis);
    _config_valid = true;
    return true;
  }

  bool isReceivingPacket() override {
    if (agcOwnsHardware()) return false;
    // While duty-cycling, BUSY marks the sleep phase: probing IRQ flags over
    // SPI there could wake the chip and break the cycle. Only skip the probe
    // in that case - outside RXPS this must stay a real channel check, since
    // Dispatcher::checkSend() relies on it to avoid transmitting over others.
    if (_rx_ps_armed && ((CustomSX1262 *)_radio)->isChipBusy()) return false;
    return ((CustomSX1262 *)_radio)->isReceiving();
  }
  bool isChipBusy() override {
    return ((CustomSX1262 *)_radio)->isChipBusy();
  }
  float getCurrentRSSI() override {
    if (agcOwnsHardware()) return _last_metrics_valid ? _last_rssi : _noise_floor;
    return ((CustomSX1262 *)_radio)->getRSSI(false);
  }

  float packetScore(float snr, int packet_len) override {
    int sf = ((CustomSX1262 *)_radio)->spreadingFactor;
    return packetScoreInt(snr, sf, packet_len);
  }
  uint8_t getSpreadingFactor() const override { return ((CustomSX1262 *)_radio)->spreadingFactor; }
  virtual void powerOff() override {
    abortAgcMaintenanceForRadioChange();
    if (_rx_ps_armed) stopReceiveDutyCycle();
    ((CustomSX1262 *)_radio)->sleep(false);
  }

  bool supportsRxPowerSaving() const override { return true; }
  bool supportsAgcMaintenance() const override { return true; }

protected:
  // RadioLib register helpers hide some transport failures. Maintenance uses
  // the checked stream API instead, and restores the normal timeout on exit.
  int16_t agcReadRegister(uint16_t address, uint8_t& value) {
    const uint8_t command[] = {RADIOLIB_SX126X_CMD_READ_REGISTER,
                              uint8_t(address >> 8), uint8_t(address)};
    return ((CustomSX1262*)_radio)->mod->SPIreadStream(command, 3, &value, 1);
  }
  int16_t agcWriteRegister(uint16_t address, uint8_t value) {
    const uint8_t command[] = {RADIOLIB_SX126X_CMD_WRITE_REGISTER,
                              uint8_t(address >> 8), uint8_t(address)};
    return ((CustomSX1262*)_radio)->mod->SPIwriteStream(command, 3, &value, 1);
  }
  int16_t agcHardwareStep(AgcMaintenanceStep step, int16_t& value) override {
    CustomSX1262* chip = (CustomSX1262*)_radio;
    struct TimeoutScope {
      Module* mod;
      uint32_t saved;
      explicit TimeoutScope(Module* m) : mod(m), saved(m->spiConfig.timeout) {
        mod->spiConfig.timeout = AGC_MAINTENANCE_SPI_TIMEOUT_MS;
      }
      ~TimeoutScope() { mod->spiConfig.timeout = saved; }
    } timeout(chip->mod);
    switch (step) {
      case AgcMaintenanceStep::Probe: {
        // BUSY during an RXPS sleep is normal; do not wake the receiver merely
        // to ask whether maintenance can begin.
        if (_rx_ps_armed && chip->isChipBusy()) return AGC_MAINTENANCE_DEFER;
        uint8_t irq[2] = {};
        int16_t error = chip->mod->SPIreadStream(RADIOLIB_SX126X_CMD_GET_IRQ_STATUS, irq, 2);
        if (error != RADIOLIB_ERR_NONE) return error;
        const uint16_t flags = (uint16_t(irq[0]) << 8) | irq[1];
        value = (flags & (RADIOLIB_SX126X_IRQ_RX_DONE | RADIOLIB_SX126X_IRQ_CRC_ERR))
          ? AGC_MAINTENANCE_RX_READY
          : ((flags & (RADIOLIB_SX126X_IRQ_PREAMBLE_DETECTED | RADIOLIB_SX126X_IRQ_HEADER_VALID))
             ? AGC_MAINTENANCE_RX_ACTIVITY : 0);
        return RADIOLIB_ERR_NONE;
      }
      case AgcMaintenanceStep::ReadGain:
        return agcReadRegister(RADIOLIB_SX126X_REG_RX_GAIN, _agc_gain);
      case AgcMaintenanceStep::Suspend: {
        int16_t error = chip->standby();
        if (error != RADIOLIB_ERR_NONE || !_rx_ps_armed) return error;
        error = agcWriteRegister(RADIOLIB_SX126X_REG_RTC_CTRL, 0);
        if (error != RADIOLIB_ERR_NONE) return error;
        uint8_t event = 0;
        error = agcReadRegister(RADIOLIB_SX126X_REG_EVENT_MASK, event);
        return error == RADIOLIB_ERR_NONE ? agcWriteRegister(RADIOLIB_SX126X_REG_EVENT_MASK, event | 2) : error;
      }
      case AgcMaintenanceStep::Sleep: return chip->sleep(true); // RadioLib's bounded 1 ms chip guard.
      case AgcMaintenanceStep::Wake:
      case AgcMaintenanceStep::RecoveryWake: {
        int16_t error = chip->mod->SPIwriteStream(RADIOLIB_SX126X_CMD_NOP, nullptr, 0, false, false);
        return error == RADIOLIB_ERR_NONE ? chip->standby(RADIOLIB_SX126X_STANDBY_RC) : error;
      }
      case AgcMaintenanceStep::Calibrate: {
        uint8_t all = RADIOLIB_SX126X_CALIBRATE_ALL;
        // Waiting for CALIBRATE's BUSY is a separate cooperative stage.
        return chip->mod->SPIwriteStream(RADIOLIB_SX126X_CMD_CALIBRATE, &all, 1, false, false);
      }
      case AgcMaintenanceStep::WaitCalibration:
        return chip->mod->SPIwriteStream(RADIOLIB_SX126X_CMD_NOP, nullptr, 0);
      case AgcMaintenanceStep::Image: return chip->calibrateImage(chip->freqMHz);
      case AgcMaintenanceStep::Dio2:
        #ifdef SX126X_DIO2_AS_RF_SWITCH
        return chip->setDio2AsRfSwitch(SX126X_DIO2_AS_RF_SWITCH);
        #else
        return RADIOLIB_ERR_NONE;
        #endif
      case AgcMaintenanceStep::WriteGain:
        return _agc_gain_valid ? agcWriteRegister(RADIOLIB_SX126X_REG_RX_GAIN, _agc_gain) : RADIOLIB_ERR_NONE;
      case AgcMaintenanceStep::ReadPatch:
        #ifdef SX126X_REGISTER_PATCH
        return agcReadRegister(0x8B5, _agc_patch);
        #else
        return RADIOLIB_ERR_NONE;
        #endif
      case AgcMaintenanceStep::WritePatch:
        #ifdef SX126X_REGISTER_PATCH
        return agcWriteRegister(0x8B5, _agc_patch | 1);
        #else
        return RADIOLIB_ERR_NONE;
        #endif
      case AgcMaintenanceStep::StartRx: return chip->startReceive();
      case AgcMaintenanceStep::RestoreRx: return startReceiveMode();
      case AgcMaintenanceStep::Sample: {
        uint8_t raw = 0;
        int16_t error = chip->mod->SPIreadStream(RADIOLIB_SX126X_CMD_GET_RSSI_INST, &raw, 1);
        value = -int16_t(raw) / 2;
        return error;
      }
      default: return RADIOLIB_ERR_UNSUPPORTED;
    }
  }
  int16_t armDutyCycle(RadioLibIrqFlags_t irq_flags, RadioLibIrqFlags_t irq_mask,
                       uint32_t* eff_rx_us, uint32_t* eff_sleep_us) override {
    // RadioLib programs the SX126x with exactly what we ask for (it only
    // subtracts the wake-up transition from the sleep period internally).
    *eff_rx_us = _rx_ps_rx_us;
    *eff_sleep_us = _rx_ps_sleep_us;
    return ((CustomSX1262 *)_radio)->startReceiveDutyCycle(
        _rx_ps_rx_us, _rx_ps_sleep_us, irq_flags, irq_mask);
  }

  int16_t stopDutyCycleHardware() override {
    int16_t standby_err = _radio->standby();
    int16_t rtc_err = ((CustomSX1262 *)_radio)->stopRTC();
    return standby_err != RADIOLIB_ERR_NONE ? standby_err : rtc_err;
  }

public:
  bool setRxBoostedGainMode(bool en) override {
    prepareForRadioConfig();
    return ((CustomSX1262 *)_radio)->setRxBoostedGainMode(en) == RADIOLIB_ERR_NONE;
  }
  bool getRxBoostedGainMode() const override {
    return ((CustomSX1262 *)_radio)->getRxBoostedGainMode();
  }

  void doResetAGC() override { sx126xResetAGC((SX126x *)_radio, getRxBoostedGainMode()); }
};
