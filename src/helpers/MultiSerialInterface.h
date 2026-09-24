#pragma once

#include "BaseSerialInterface.h"

#ifndef MAX_INTERFACES
  // ble, usb, wifi, ethernet
  #define MAX_INTERFACES 4
#endif

enum class InterfaceType : uint8_t {
  NONE,
  Bluetooth,
  USB,
  WiFi,
  Ethernet,
  HardwareSerial
};

class MultiSerialInterface : public BaseSerialInterface {
private:

  struct RegisteredInterface {
    InterfaceType type = InterfaceType::NONE;
    BaseSerialInterface* instance = nullptr;
  };

  bool _enabled = false;
  RegisteredInterface _interfaces[MAX_INTERFACES] = {};

#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  InterfaceType _selected = InterfaceType::Bluetooth;
  mutable uint32_t _session_generation = 0;
  mutable uint32_t _observed_transport_generation = 0;

  RegisteredInterface* findInterface(InterfaceType type) {
    for (auto& iface : _interfaces) {
      if (iface.instance && iface.type == type) return &iface;
    }
    return nullptr;
  }

  const RegisteredInterface* findInterface(InterfaceType type) const {
    for (const auto& iface : _interfaces) {
      if (iface.instance && iface.type == type) return &iface;
    }
    return nullptr;
  }

  RegisteredInterface* selectedInterface() { return findInterface(_selected); }
  const RegisteredInterface* selectedInterface() const { return findInterface(_selected); }

  void advanceSessionGeneration() const {
    ++_session_generation;
    if (_session_generation == 0) ++_session_generation;
  }

  bool selectedConnectedRaw() const {
    const RegisteredInterface* iface = selectedInterface();
    return _enabled && iface && iface->instance->isEnabled() &&
           iface->instance->isConnected();
  }

  void observeSelectedSession() const {
    const RegisteredInterface* iface = selectedInterface();
    const uint32_t transport_generation =
        iface && iface->instance ? iface->instance->sessionGeneration() : 0;
    if (transport_generation != _observed_transport_generation) {
      _observed_transport_generation = transport_generation;
      advanceSessionGeneration();
    }
  }

  InterfaceType firstRegisteredType() const {
    for (const auto& iface : _interfaces) {
      if (iface.instance) return iface.type;
    }
    return InterfaceType::NONE;
  }
#endif

public:
  bool addInterface(InterfaceType type, BaseSerialInterface* iface) {
    // make sure an interface was provided
    if(iface == nullptr){
      return false;
    }

    // put it in the first free slot
    for(int i = 0; i < MAX_INTERFACES; i++){
      if(_interfaces[i].instance == nullptr){
        _interfaces[i].instance = iface;
        _interfaces[i].type = type;
        return true;
      }
    }

    // no free slots available
    return false;
  }

  bool hasInterface(InterfaceType type) const {
    for (const auto& iface : _interfaces) {
      if (iface.instance && iface.type == type) return true;
    }
    return false;
  }

#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
  bool selectExclusive(InterfaceType type) {
    RegisteredInterface* next = findInterface(type);
    if (!next) return false;

    if (_selected != type) {
      for (auto& iface : _interfaces) {
        if (iface.instance) iface.instance->disable();
      }
      _selected = type;
      _observed_transport_generation = next->instance->sessionGeneration();
      advanceSessionGeneration();
    } else {
      for (auto& iface : _interfaces) {
        if (iface.instance && iface.type != _selected) iface.instance->disable();
      }
    }
    if (_enabled && !next->instance->isEnabled()) next->instance->enable();
    observeSelectedSession();
    return true;
  }

  InterfaceType getSelectedInterface() const { return _selected; }

  bool isInterfaceEnabled(InterfaceType type) const {
    const RegisteredInterface* iface = findInterface(type);
    return iface && iface->instance->isEnabled();
  }

  bool isInterfaceConnected(InterfaceType type) const {
    const RegisteredInterface* iface = findInterface(type);
    return _enabled && iface && iface->instance->isEnabled() &&
           iface->instance->isConnected();
  }

  uint32_t getSessionGeneration() const {
    observeSelectedSession();
    return _session_generation;
  }

  uint32_t sessionGeneration() const override {
    return getSessionGeneration();
  }

  void noteSessionBoundary() {
    const RegisteredInterface* iface = selectedInterface();
    _observed_transport_generation =
        iface && iface->instance ? iface->instance->sessionGeneration() : 0;
    advanceSessionGeneration();
  }
#else
  InterfaceType getSelectedInterface() const { return InterfaceType::NONE; }
  uint32_t getSessionGeneration() const { return 0; }
  uint32_t sessionGeneration() const override { return 0; }
  void noteSessionBoundary() {}
#endif

  bool removeInterface(BaseSerialInterface* iface) {
    // make sure an interface was provided
    if(iface == nullptr){
      return false;
    }

    // find and remove interface
    for(int i = 0; i < MAX_INTERFACES; i++){
      if(_interfaces[i].instance == iface){
        _interfaces[i] = {};
        return true;
      }
    }

    // interface not found
    return false;
  }

  void enableBluetooth() {
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
    if (selectExclusive(InterfaceType::Bluetooth)) return;
#endif
    for(auto iface : _interfaces){
      if(iface.instance && iface.type == InterfaceType::Bluetooth){
        iface.instance->enable();
      }
    }
  }

  void disableBluetooth() {
    for(auto iface : _interfaces){
      if(iface.instance && iface.type == InterfaceType::Bluetooth){
        iface.instance->disable();
      }
    }
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
    observeSelectedSession();
#endif
  }

  bool isBluetoothEnabled() {
    for(auto iface : _interfaces){
      if(iface.instance && iface.type == InterfaceType::Bluetooth){
        return iface.instance->isEnabled();
      }
    }
    return false; 
  }

  // enable all interfaces
  void enable() override {
    _enabled = true;
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
    if (!hasInterface(_selected)) _selected = firstRegisteredType();
    for (auto& iface : _interfaces) {
      if (!iface.instance) continue;
      if (iface.type == _selected) iface.instance->enable();
      else iface.instance->disable();
    }
    RegisteredInterface* selected = selectedInterface();
    _observed_transport_generation =
        selected && selected->instance ? selected->instance->sessionGeneration() : 0;
    return;
#endif
    for(auto iface : _interfaces){
      if(iface.instance){
        iface.instance->enable();
      }
    }
  }

  // disable all interfaces
  void disable() override {
    _enabled = false;
    for(auto iface : _interfaces){
      if(iface.instance){
        iface.instance->disable();
      }
    }
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
    observeSelectedSession();
#endif
  }

  bool isEnabled() const override { 
    return _enabled; 
  }

  bool isConnected() const override {
    // not connected when disabled
    if(!_enabled){
      return false;
    }
    
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
    observeSelectedSession();
    return selectedConnectedRaw();
#else
    // check if any interface is connected
    for(auto iface : _interfaces){
      if(iface.instance && iface.instance->isConnected()) {
        return true;
      }
    }

    // nothing connected
    return false;
#endif
  }

  // loop all interfaces
  void loop() override {
#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
    RegisteredInterface* iface = selectedInterface();
    if (_enabled && iface && iface->instance->isEnabled()) {
      iface->instance->loop();
    }
    observeSelectedSession();
    return;
#endif
    for(auto iface : _interfaces){
      if(iface.instance){
        iface.instance->loop();
      }
    }
  }

  bool isReadBusy() const override {
    // not busy when disabled
    if (!_enabled) {
      return false;
    }

#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
    const RegisteredInterface* iface = selectedInterface();
    return iface && iface->instance->isEnabled() &&
           iface->instance->isReadBusy();
#else
    // check if any interface is busy
    for (auto iface : _interfaces) {
      if (iface.instance && iface.instance->isEnabled() && iface.instance->isReadBusy()) {
        return true;
      }
    }

    // nothing busy
    return false;
#endif
  }

  bool isWriteBusy() const override {
    // not busy when disabled
    if(!_enabled){
      return false;
    }

#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
    const RegisteredInterface* iface = selectedInterface();
    return iface && iface->instance->isEnabled() &&
           iface->instance->isWriteBusy();
#else
    // check if any interface is busy
    for(auto iface : _interfaces){
      if(iface.instance && iface.instance->isEnabled() && iface.instance->isWriteBusy()){
        return true;
      }
    }

    // nothing busy
    return false;
#endif
  }

  size_t writeFrame(const uint8_t src[], size_t len) override {
    // don't write when disabled or nothing provided
    if(!_enabled || len == 0){
      return 0;
    }

#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
    RegisteredInterface* iface = selectedInterface();
    if (!iface || !iface->instance->isEnabled()) return 0;
    return iface->instance->writeFrame(src, len);
#else
    // write frame to all enabled interfaces
    bool allSuccessful = true;
    for(auto iface : _interfaces){
      if(iface.instance && iface.instance->isEnabled()){
        if(iface.instance->writeFrame(src, len) != len){
          allSuccessful = false;
        }
      }
    }

    // report success if all writes completed successfully
    return allSuccessful ? len : 0; 
#endif
  }

  size_t checkRecvFrame(uint8_t dest[]) override {
    // don't read when disabled
    if(!_enabled){
      return 0;
    }

#if defined(SMARTUI_CONNECTION_SELECTOR) && SMARTUI_CONNECTION_SELECTOR
    RegisteredInterface* iface = selectedInterface();
    if (!iface || !iface->instance->isEnabled()) return 0;
    const size_t frameSize = iface->instance->checkRecvFrame(dest);
    observeSelectedSession();
    return frameSize;
#else
    // try to read a frame from any enabled interface
    for(auto iface : _interfaces){
      if(iface.instance && iface.instance->isEnabled()){
        size_t frameSize = iface.instance->checkRecvFrame(dest);
        if(frameSize > 0){
          return frameSize; 
        }
      }
    }

    // no frame received
    return 0;
#endif
  }

};
