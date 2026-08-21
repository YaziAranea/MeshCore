#pragma once

#include <MeshCore.h>
#include <helpers/ui/DisplayDriver.h>
#include <helpers/ui/UIScreen.h>
#include <helpers/SensorManager.h>
#include <helpers/MultiSerialInterface.h>
#include <Arduino.h>

#ifdef PIN_BUZZER
  #include <helpers/ui/buzzer.h>
#endif

#include "NodePrefs.h"

enum class UIEventType {
    none,
    contactMessage,
    channelMessage,
    roomMessage,
    newContactMessage,
    ack
};

#define UI_MSG_FLAG_NONE       0x00
#define UI_MSG_FLAG_DIRECT     0x01
#define UI_MSG_FLAG_MENTION    0x02
#define UI_MSG_FLAG_IMPORTANT  0x04

class AbstractUITask {
protected:
  mesh::MainBoard* _board;
  MultiSerialInterface* _interfaceManager;
  bool _connected;

  AbstractUITask(mesh::MainBoard* board, MultiSerialInterface* interfaceManager) : _board(board), _interfaceManager(interfaceManager) {
    _connected = false;
  }

public:
  void setHasConnection(bool connected) { _connected = connected; }
  bool hasConnection() const { return _connected; }
  virtual uint16_t getBattMilliVolts() const { return _board->getBattMilliVolts(); }
  bool isBluetoothEnabled() const { return _interfaceManager->isBluetoothEnabled(); }
  void enableBluetooth() { _interfaceManager->enableBluetooth(); }
  void disableBluetooth() { _interfaceManager->disableBluetooth(); }
  virtual void msgRead(int msgcount) = 0;
  virtual void msgRead(int msgcount, bool dismiss_notification) {
    (void)dismiss_notification;
    msgRead(msgcount);
  }
  virtual void directMsgRead(bool dismiss_notification) {
    (void)dismiss_notification;
  }
  // Keep the four-argument hook for stock PS17 UIs.  SmartUI overrides the
  // flagged form; the default bridge lets either implementation coexist.
  virtual void newMsg(uint8_t path_len, const char* from_name, const char* text,
                      int msgcount) {
    (void)path_len;
    (void)from_name;
    (void)text;
    (void)msgcount;
  }
  virtual void newMsg(uint8_t path_len, const char* from_name, const char* text,
                      int msgcount, uint8_t flags) {
    (void)flags;
    newMsg(path_len, from_name, text, msgcount);
  }
  virtual void notify(UIEventType t = UIEventType::none) = 0;
  virtual void applyImportedPrefs() {}
  virtual void loop() = 0;
};
