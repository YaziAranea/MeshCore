#!/usr/bin/env python3
"""Execute production E213Display.cpp against deterministic host stubs.

Linux CI has a host C++ compiler. Windows release hosts may not; there the
real Paper PlatformIO build remains the compile gate and this test reports a
clear skip. No hardware behavior is claimed by this fault-injection harness.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src/helpers/ui"

ARDUINO = r'''#pragma once
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#define LOW 0
#define HIGH 1
#define INPUT 0
#define OUTPUT 1
unsigned long millis();
void delay(unsigned long value);
void yield();
void pinMode(int pin, int mode);
void digitalWrite(int pin, int value);
int digitalRead(int pin);
'''

DISPLAY_DRIVER = r'''#pragma once
#include <Arduino.h>
using ColorVal = uint16_t;
struct UIColor {
  static ColorVal window_bkg, title_bkg, title_txt, primary_txt, secondary_txt;
  static ColorVal warning_txt, popup_bkg, popup_txt, corp_blue;
};
class DisplayDriver {
  int _width, _height;
public:
  static constexpr ColorVal DARK=0, LIGHT=1, YELLOW=2, BLUE=3, RED=4;
  DisplayDriver(int width, int height): _width(width), _height(height) {}
  virtual ~DisplayDriver() {}
  int width() const { return _width; }
  int height() const { return _height; }
  virtual bool isOn()=0; virtual bool isEink(){return false;}
  virtual void turnOn()=0; virtual void turnOff()=0; virtual void clear()=0;
  virtual void startFrame(ColorVal)=0; virtual void endFrame()=0;
  virtual void setTextSize(int)=0; virtual void setBold(bool)=0;
  virtual uint8_t getTextLineHeight() const=0; virtual uint8_t getTextInkHeight() const=0;
  virtual void setUiFont(uint8_t)=0; virtual uint8_t getUiFont() const=0;
  virtual uint8_t getUiFontCount() const=0; virtual const char* getUiFontName(uint8_t) const=0;
  virtual void setColor(ColorVal)=0; virtual void setCursor(int,int)=0;
  virtual void print(const char*)=0; virtual void printWordWrap(const char*,int)=0;
  virtual void fillRect(int,int,int,int)=0; virtual void drawRect(int,int,int,int)=0;
  virtual void drawXbm(int,int,const uint8_t*,int,int)=0;
  virtual uint16_t getTextWidth(const char*)=0;
  virtual void translateUTF8ToBlocks(char* dest,const char* src,size_t size) {
    if (!size) return; strncpy(dest, src ? src : "", size-1); dest[size-1]=0;
  }
};
'''

EINK = r'''#pragma once
#include <Arduino.h>
#define BLACK 0
#define WHITE 1
extern int stub_update_attempts;
class BaseDisplay {
protected:
  virtual void wait() {}
public:
  virtual ~BaseDisplay() {}
  void begin(){ wait(); }
  void setRotation(int){}
  void clear(){ wait(); }
  void fastmodeOn(bool=true){ wait(); }
  void fastmodeOff(){ wait(); }
  void update(){ ++stub_update_attempts; wait(); }
  void fillRect(int,int,int,int,uint16_t){}
  void drawPixel(int,int,uint16_t){}
  void setTextColor(uint16_t){}
  void setTextSize(int){}
  void setCursor(int,int){}
  void print(const char*){}
  void getTextBounds(const char* text,int,int,int16_t* x,int16_t* y,uint16_t* w,uint16_t* h){
    *x=0; *y=0; *w=(uint16_t)(text ? strlen(text)*6 : 0); *h=8;
  }
};
class StubEinkV11 : public BaseDisplay {};
class StubEinkV111 : public BaseDisplay {};
using EInkDisplay_WirelessPaperV1_1 = StubEinkV11;
using EInkDisplay_WirelessPaperV1_1_1 = StubEinkV111;
'''

CRC = r'''#pragma once
#include <stdint.h>
#include <stddef.h>
class CRC32 {
  uint32_t value=2166136261u;
public:
  void reset(){ value=2166136261u; }
  template<class T> void update(T item){ update((const uint8_t*)&item,sizeof(item)); }
  template<class T> void update(const T* data,size_t count){
    const uint8_t* bytes=(const uint8_t*)data;
    for(size_t i=0;i<count*sizeof(T);++i){ value^=bytes[i]; value*=16777619u; }
  }
  uint32_t finalize() const { return value; }
};
'''

REFCOUNT = r'''#pragma once
class RefCountedDigitalPin { public: void claim(){} void release(){} };
'''

HARNESS = r'''#include <cassert>
#include <cstdint>
#include "src/helpers/ui/E213Display.h"

static uint32_t fake_now=0;
static bool detect_read=false;
static bool busy_stuck=false;
static int vext_off_writes=0;
int stub_update_attempts=0;

unsigned long millis(){ return fake_now; }
void delay(unsigned long value){ fake_now += (uint32_t)value; }
void yield(){ ++fake_now; }
void pinMode(int,int){}
void digitalWrite(int pin,int value){
  if(pin==DISP_RST && value==LOW) detect_read=true;
  if(pin==PIN_VEXT_EN && value==HIGH) ++vext_off_writes;
}
int digitalRead(int pin){
  assert(pin==DISP_BUSY);
  if(detect_read){ detect_read=false; return HIGH; }
  return busy_stuck ? HIGH : LOW;
}

int main(){
  E213Display display;

  // First boot: stuck BUSY exits at whole-init budget, reports error, and
  // never drives shared GPIO45/VEXT off.
  busy_stuck=true;
  assert(!display.begin());
  assert(!display.isOn());
  assert(display.lastError()==E213_DISPLAY_BUSY_TIMEOUT);
  assert(display.hasPendingRetry());
  assert(display.lastOperationMillis()==E213_INIT_BUDGET_MILLIS);
  assert(display.retryAfterMillis()==E213_RETRY_DELAY_MILLIS);
  assert(vext_off_writes==0);

  // First retry succeeds after cooldown and clears error/backoff state.
  fake_now += display.retryAfterMillis();
  busy_stuck=false;
  assert(display.isOn());
  assert(display.lastError()==E213_DISPLAY_OK);
  assert(!display.hasPendingRetry());

  // One healthy frame is cached; identical content does not update twice.
  display.startFrame(DisplayDriver::DARK);
  display.setCursor(2,3);
  display.print("ok");
  display.endFrame();
  assert(stub_update_attempts==1);
  display.startFrame(DisplayDriver::DARK);
  display.setCursor(2,3);
  display.print("ok");
  display.endFrame();
  assert(stub_update_attempts==1);

  // New frame times out at whole-frame budget. Failed CRC is not accepted.
  busy_stuck=true;
  display.startFrame(DisplayDriver::DARK);
  display.setCursor(4,5);
  display.print("failed-frame");
  display.endFrame();
  assert(stub_update_attempts==2);
  assert(!display.isOn());
  assert(display.lastError()==E213_DISPLAY_BUSY_TIMEOUT);
  assert(display.lastOperationMillis()==E213_FRAME_BUDGET_MILLIS);
  assert(display.retryAfterMillis()==E213_RETRY_DELAY_MILLIS);
  assert(vext_off_writes==0);

  // Persistent first retry fails; exponential delay grows, not a tight loop.
  fake_now += display.retryAfterMillis();
  assert(!display.isOn());
  assert(display.retryAfterMillis()==E213_RETRY_DELAY_MILLIS*2);
  assert(vext_off_writes==0);

  // Later healthy retry succeeds. Same failed frame is physically attempted
  // again, proving timeout did not mark its CRC successful.
  fake_now += display.retryAfterMillis();
  busy_stuck=false;
  assert(display.isOn());
  display.startFrame(DisplayDriver::DARK);
  display.setCursor(4,5);
  display.print("failed-frame");
  display.endFrame();
  assert(stub_update_attempts==3);
  assert(display.lastError()==E213_DISPLAY_OK);
  assert(vext_off_writes==0);
  return 0;
}
'''


def compiler() -> str | None:
    choices = [os.environ.get("CXX"), "c++", "g++", "clang++"]
    for choice in choices:
        if choice and shutil.which(choice):
            return choice
    return None


def main() -> None:
    cxx = compiler()
    if cxx is None:
        if os.environ.get("CI"):
            raise SystemExit("[FAIL] CI host C++ compiler missing")
        print("[SKIP] host C++ compiler missing; use Linux CI plus Paper PlatformIO build")
        return
    with tempfile.TemporaryDirectory(prefix="smartui-e213-host-") as raw:
        root = Path(raw)
        ui = root / "src/helpers/ui"
        stubs = root / "stubs"
        (stubs / "helpers").mkdir(parents=True)
        ui.mkdir(parents=True)
        shutil.copy2(UI / "E213Display.cpp", ui / "E213Display.cpp")
        shutil.copy2(UI / "E213Display.h", ui / "E213Display.h")
        shutil.copy2(UI / "E213BusyGuard.h", ui / "E213BusyGuard.h")
        (ui / "DisplayDriver.h").write_text(DISPLAY_DRIVER, encoding="utf-8")
        (root / "src/MeshCore.h").write_text("#pragma once\n", encoding="utf-8")
        (stubs / "Arduino.h").write_text(ARDUINO, encoding="utf-8")
        (stubs / "SPI.h").write_text("#pragma once\n#include <Arduino.h>\n", encoding="utf-8")
        (stubs / "Wire.h").write_text("#pragma once\n", encoding="utf-8")
        (stubs / "heltec-eink-modules.h").write_text(EINK, encoding="utf-8")
        (stubs / "CRC32.h").write_text(CRC, encoding="utf-8")
        (stubs / "helpers/RefCountedDigitalPin.h").write_text(REFCOUNT, encoding="utf-8")
        (root / "driver_flow.cpp").write_text(HARNESS, encoding="utf-8")
        binary = root / ("driver_flow.exe" if os.name == "nt" else "driver_flow")
        definitions = [
            "WIRELESS_PAPER=1", "DISP_RST=6", "DISP_BUSY=7", "PIN_VEXT_EN=45",
            "MESHCORE_E213_PROFILE_FONTS=0", "E213_FULL_REFRESH_EVERY=0",
            "E213_BUSY_TIMEOUT_MILLIS=50", "E213_INIT_BUDGET_MILLIS=100",
            "E213_FRAME_BUDGET_MILLIS=8", "E213_RETRY_DELAY_MILLIS=5",
            "E213_RETRY_MAX_DELAY_MILLIS=20", "E213_KEEP_SHARED_VEXT_ON=1",
        ]
        command = [cxx, "-std=c++17", "-O0", "-I", str(stubs), "-I", str(root),
                   *[f"-D{name}" for name in definitions], str(root / "driver_flow.cpp"),
                   str(ui / "E213Display.cpp"), "-o", str(binary)]
        built = subprocess.run(command, capture_output=True, text=True, timeout=60)
        if built.returncode:
            raise SystemExit("[FAIL] E213 host compile:\n" + built.stdout + built.stderr)
        ran = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
        if ran.returncode:
            raise SystemExit("[FAIL] E213 host flow:\n" + ran.stdout + ran.stderr)
    print("[PASS] production E213Display flow: init/frame timeout, CRC retry, exponential recovery, shared VEXT")


if __name__ == "__main__":
    main()
