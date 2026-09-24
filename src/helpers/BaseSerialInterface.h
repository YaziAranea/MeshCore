#pragma once

#include <Arduino.h>

#define MAX_FRAME_SIZE  176   // +4 for transport codes (region scoping)

class BaseSerialInterface {
protected:
  BaseSerialInterface() { }

public:
  virtual void enable() = 0;
  virtual void disable() = 0;
  virtual bool isEnabled() const = 0;

  virtual bool isConnected() const = 0;
  // Monotonic local-session epoch.  Transports which can distinguish clients
  // increment this on each accepted session and disconnect.  Zero preserves
  // compatibility for legacy transports without session tracking.
  virtual uint32_t sessionGeneration() const { return 0; }
  virtual void loop() {};

  virtual bool isReadBusy() const = 0;
  virtual bool isWriteBusy() const = 0;
  virtual size_t writeFrame(const uint8_t src[], size_t len) = 0;
  virtual size_t checkRecvFrame(uint8_t dest[]) = 0;
};
