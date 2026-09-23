#!/usr/bin/env python3
"""Run the production optional GPS provider and pinned MicroNMEA on host stubs.

UART/RTC/pins are simulated; parsing, freshness, scanning and budget code are real.
Run after PlatformIO installs the ProMicro dependencies (no board required).
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / '.pio/libdeps/ProMicro_ra62_companion_radio_ble/MicroNMEA/src'
ARDUINO = r'''
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <ctype.h>
#include <stdlib.h>
#include <stdio.h>
#include <string>
extern uint32_t now_ms;
inline uint32_t millis() { return now_ms; }
enum {OUTPUT=1, HIGH=1, LOW=0};
inline void pinMode(int,int) {}
inline void digitalWrite(int,int) {}
class Stream {
public:
  virtual ~Stream() = default;
  virtual size_t write(uint8_t) {return 1;}
  size_t print(const char* s) {size_t n=0; while (*s) {n+=write(*s++);} return n;}
  size_t print(char c) {return write(c);}
  size_t println(const char* s) {return print(s)+print("\r\n");}
  size_t println() {return print("\r\n");}
};
'''
MESH = r'''
#pragma once
#include <Arduino.h>
namespace mesh { class RTCClock {
public:
  unsigned writes=0; uint32_t value=0;
  void setCurrentTime(uint32_t t) {++writes; value=t;}
  uint32_t getCurrentTime() {return value;}
}; }
'''
RTC = r'''
#pragma once
#include <stdint.h>
// Stub epoch conversion only: changing seconds retains monotonic UTC semantics.
class DateTime {
  uint32_t value;
public:
  DateTime(int,int,int,int h,int m,int s) : value(1789603200U+h*3600+m*60+s) {}
  uint32_t unixtime() const {return value;}
};
'''
SOURCE = r'''
#include <assert.h>
#include <deque>
#include <vector>
#include <helpers/sensors/OptionalUartNmeaLocationProvider.h>
#include "RecoveryBatteryGuard.h"
uint32_t now_ms=0;
void LocationProvider::sendSentence(const char*) {}
static unsigned checks=0;
#define CHECK(x) do {++checks; if (!(x)) {fprintf(stderr,"line %d: %s\n",__LINE__,#x); abort();}} while(0)
struct Uart : Stream {
  std::deque<char> input; std::vector<uint32_t> rates;
  unsigned reads=0, ends=0; int rx=-1,tx=-1;bool started=false;
  void end(){CHECK(started);started=false;++ends; input.clear();}
  void setPins(int r,int t){rx=r;tx=t;}
  void begin(uint32_t b){CHECK(!started);started=true;rates.push_back(b);}
  bool available(){return !input.empty();}
  int read(){++reads; char c=input.front();input.pop_front();return c;}
  void feed(std::string s){for(char c:s) input.push_back(c);}
};
static std::string sentence(std::string payload) {
  unsigned char sum=0; for(char c:payload)sum^=c;
  char tail[8];snprintf(tail,sizeof(tail),"*%02X\r\n",sum);
  return "$"+payload+tail;
}
static std::string rmc(unsigned sec=0,const char* date="230926",const char* status="A") {
  char p[180];snprintf(p,sizeof(p),"GNRMC,1200%02u.00,%s,5545.000,N,03737.000,E,0.0,0.0,%s,,,A",sec,status,date);
  return sentence(p);
}
int main(){
  Uart u;mesh::RTCClock clock;
  OptionalUartNmeaLocationProvider<Uart> gps(u,&clock,3,4,5);
  CHECK(!gps.isEnabled());CHECK(!gps.isValid());CHECK(u.rates.empty());
  gps.stop();CHECK(u.rates.empty());CHECK(!gps.hasRecentInput());
  gps.begin();CHECK(u.rx==3 && u.tx==4);CHECK(gps.getBaudRate()==9600);
  CHECK(u.ends==0);
  gps.begin();CHECK(u.rates.size()==1);
  now_ms=2400;gps.loop();CHECK(gps.getBaudRate()==38400);
  u.feed("$GNRMC,garbage*00\r\n");gps.loop();CHECK(!gps.hasRecentInput());
  u.feed(sentence("GNXXX,120000.00,A"));gps.loop();CHECK(!gps.hasRecentInput());
  u.feed(rmc());gps.loop();CHECK(gps.hasRecentInput());CHECK(gps.isValid());
  CHECK(gps.getLatitude()==55750000L);CHECK(clock.writes==0);
  now_ms+=1000;u.feed(rmc(1));gps.loop();CHECK(clock.writes==0);
  now_ms+=1000;u.feed(rmc(2));gps.loop();CHECK(clock.writes==1);
  CHECK(!gps.waitingTimeSync());CHECK(gps.getBaudRate()==38400);
  now_ms+=3000;u.feed(rmc(5));gps.loop();CHECK(gps.getBaudRate()==38400);
  CHECK(clock.writes==1);
  now_ms+=10001;gps.loop();CHECK(!gps.hasRecentInput());CHECK(!gps.isValid());
  CHECK(gps.getTimestamp()==0);
  now_ms+=2400;gps.loop();CHECK(gps.getBaudRate()==115200);
  gps.stop();CHECK(!gps.isValid());CHECK(!gps.isEnabled());CHECK(gps.getBaudRate()==0);
  gps.begin();gps.syncTime();
  for(unsigned i=0;i<4;++i){now_ms+=1000;u.feed(rmc(i,"310226"));gps.loop();}
  CHECK(clock.writes==1);CHECK(gps.getTimestamp()==0);
  u.feed(rmc(4,"230926"));gps.loop();
  u.feed(rmc(5,""));gps.loop();CHECK(gps.getTimestamp()==0);
  u.feed(rmc(4,"230926","V"));gps.loop();CHECK(!gps.isValid());
  unsigned before=u.reads;u.feed(std::string(2000,'X'));gps.loop();CHECK(u.reads-before==256);
  gps.stop();now_ms=0xfffffff0U;gps.begin();u.feed(rmc());gps.loop();
  now_ms+=1000;u.feed(rmc(1));gps.loop();CHECK(gps.hasRecentInput());CHECK(gps.isValid());
  now_ms+=10000;gps.loop();CHECK(!gps.hasRecentInput());CHECK(!gps.isValid());
  smartui::RecoveryBatteryGuard guard;
  CHECK(!guard.update(0,3199,false,3200));
  CHECK(!guard.update(999,3199,false,3200));
  CHECK(!guard.update(1000,3199,false,3200));
  CHECK(guard.update(2000,3199,false,3200));
  CHECK(!guard.update(3000,3000,true,3200));
  CHECK(!guard.update(4000,0,false,3200));
  CHECK(!guard.update(5000,3200,false,3200));
  CHECK(!guard.update(6000,3100,false,3200));
  CHECK(!guard.update(7000,0,false,3200));
  CHECK(!guard.update(8000,3100,false,3200));
  CHECK(guard.update(9000,3100,false,3200));
  smartui::RecoveryBatteryGuard wrapped;
  CHECK(!wrapped.update(0xfffffff0U,3100,false,3200));
  CHECK(!wrapped.update(984,3100,false,3200));
  CHECK(wrapped.update(1984,3100,false,3200));
  printf("PASS: %u optional UART GPS / recovery safety checks (real provider + MicroNMEA)\n",checks);
}
'''

def linux(path):
    return subprocess.check_output(['wsl','--exec','wslpath','-a',str(path)],text=True).strip()

def main():
    if not (LIB/'MicroNMEA.cpp').exists():
        raise SystemExit('Install pinned ProMicro PlatformIO dependencies first.')
    with tempfile.TemporaryDirectory(prefix='smartui-gps-') as tmp:
        folder=Path(tmp)
        for name,source in [('Arduino.h',ARDUINO),('Mesh.h',MESH),('RTClib.h',RTC),('test.cpp',SOURCE)]:
            (folder/name).write_text(source,encoding='utf-8')
        paths=[folder,ROOT/'src',LIB,ROOT/'examples/companion_radio/ui-new']
        flags=['-std=c++11','-Wall','-Wextra','-O2']
        if shutil.which('g++'):
            inc=[v for p in paths for v in ['-I',str(p)]]
            subprocess.run(['g++',*flags,*inc,str(folder/'test.cpp'),str(LIB/'MicroNMEA.cpp'),'-o',str(folder/'test')],check=True)
            subprocess.run([str(folder/'test')],check=True)
        else:
            inc=[v for p in paths for v in ['-I',linux(p)]]
            subprocess.run(['wsl','--exec','g++',*flags,*inc,linux(folder/'test.cpp'),linux(LIB/'MicroNMEA.cpp'),'-o',linux(folder/'test')],check=True)
            subprocess.run(['wsl','--exec',linux(folder/'test')],check=True)

if __name__=='__main__':main()
