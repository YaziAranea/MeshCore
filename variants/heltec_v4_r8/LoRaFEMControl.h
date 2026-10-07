#pragma once

typedef enum {
  KCT8103L_PA,
  OTHER_FEM_TYPES
} LoRaFEMType;

class LoRaFEMControl {
public:
  LoRaFEMControl() { }
  virtual ~LoRaFEMControl() { }
  void init(void);
  void setSleepModeEnable(void);
  void setTxModeEnable(void);
  void setRxModeEnable(void);
  void setRxModeEnableWhenMCUSleep(void);
  void setLNAEnable(bool enabled);
  bool isLnaCanControl(void) const { return true; }
  bool isLNAEnabled(void) const { return lna_enabled; }
  void setLnaCanControl(bool can_control) { }
  LoRaFEMType getFEMType(void) const { return KCT8103L_PA; }

private:
  bool lna_enabled = false;
};
