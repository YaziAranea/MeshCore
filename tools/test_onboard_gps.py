#!/usr/bin/env python3
"""Execute production onboard GPS + GPSv2 manager with pinned MicroNMEA.

Only UART, GPIO, I2C and RTC hardware are stubbed. UTC conversion uses timegm.
Both onboard and optional-UART manager paths are compiled and exercised.
"""

from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / ".pio/libdeps/ProMicro_ra62_companion_radio_ble/MicroNMEA/src"

ARDUINO = r'''#pragma once
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <ctype.h>
#include <stdlib.h>
#include <stdio.h>
#include <deque>
#include <string>
#include <vector>
extern uint32_t now_ms;
extern int pin_values[64];
extern unsigned pin_writes[64];
inline uint32_t millis() { return now_ms; }
inline void delay(unsigned ms) { now_ms += ms; }
enum {OUTPUT=1, INPUT=0, HIGH=1, LOW=0};
inline void pinMode(int,int) {}
inline void digitalWrite(int pin,int value) { if(pin>=0 && pin<64) {pin_values[pin]=value;++pin_writes[pin];} }
inline int digitalRead(int pin) { return pin_values[pin]; }
class Stream {
public:
  virtual ~Stream() = default;
  virtual int available() = 0;
  virtual int read() = 0;
  virtual size_t write(uint8_t) { return 1; }
  size_t print(const char* s) {size_t n=0;while(*s)n+=write(*s++);return n;}
  size_t print(char c) {return write(c);}
  size_t println(const char* s) {return print(s)+print("\r\n");}
  size_t println() {return print("\r\n");}
};
class TestUart : public Stream {
public:
  std::deque<char> input;
  unsigned reads=0, begins=0, ends=0;
  uint32_t baud=0;
  int rx=-1,tx=-1;
  bool started=false;
  int available() override {return static_cast<int>(input.size());}
  int read() override {if(input.empty())return -1;++reads;int c=input.front();input.pop_front();return c;}
  void feed(const std::string& s) {for(char c:s)input.push_back(c);}
  void setPins(int r,int t) {rx=r;tx=t;}
  void begin(uint32_t b) {started=true;baud=b;++begins;}
  void end() {started=false;input.clear();++ends;}
};
extern TestUart Serial1;
'''

MESH = r'''#pragma once
#include <Arduino.h>
#define MESH_DEBUG_PRINTLN(...) do {} while(0)
#define POWERSAVING_DEBUG_PRINTLN(...) do {} while(0)
namespace mesh { class RTCClock {
public:
  unsigned writes=0;
  uint32_t value=0;
  void setCurrentTime(uint32_t t) {++writes;value=t;}
  uint32_t getCurrentTime() {return value;}
}; }
'''

RTC = r'''#pragma once
#include <stdint.h>
#include <time.h>
class DateTime {
  uint32_t value;
public:
  DateTime(int y,int m,int d,int h,int min,int s) {
    struct tm date={};date.tm_year=y-1900;date.tm_mon=m-1;date.tm_mday=d;
    date.tm_hour=h;date.tm_min=min;date.tm_sec=s;
    value=static_cast<uint32_t>(timegm(&date));
  }
  uint32_t unixtime() const {return value;}
};
'''

WIRE = r'''#pragma once
class TwoWire {
public:
  void beginTransmission(unsigned) {}
  int endTransmission() {return 1;}
};
extern TwoWire Wire;
'''

CAYENNE = r'''#pragma once
class CayenneLPP {
public:
  unsigned gps_records=0;
  void addGPS(unsigned,double,double,double) {++gps_records;}
};
'''

SOURCE = r'''
#include <cassert>
#include <cmath>
#include <helpers/sensors/MicroNMEALocationProvider.h>
#include <helpers/sensors/OptionalUartNmeaLocationProvider.h>
#include <helpers/sensors/EnvironmentSensorManager.h>
#include <Wire.h>
uint32_t now_ms=0;
int pin_values[64]={};
unsigned pin_writes[64]={};
TestUart Serial1;
TwoWire Wire;
void LocationProvider::sendSentence(const char*) {}
static unsigned checks=0;
#define CHECK(x) do {++checks;if(!(x)){fprintf(stderr,"line %d: %s\n",__LINE__,#x);abort();}} while(0)
static std::string sentence(const std::string& payload) {
  unsigned char sum=0;for(char c:payload)sum^=c;
  char tail[8];snprintf(tail,sizeof(tail),"*%02X\r\n",sum);
  return "$"+payload+tail;
}
static std::string rmc(unsigned sec=0,const char* date="280926",const char* status="A",const char* time=nullptr) {
  char utc[16];snprintf(utc,sizeof(utc),"1200%02u.00",sec);
  std::string payload="GNRMC,";
  return sentence(payload+(time?time:utc)+","+status+",5545.000,N,03737.000,E,0.0,0.0,"+date+",,,A");
}
static std::string gga(const char* time="120000.00",const char* quality="1") {
  return sentence(std::string("GNGGA,")+time+",5545.000,N,03737.000,E,"+quality+",08,1.0,123.0,M,0.0,M,,");
}
static void sample(MicroNMEALocationProvider& gps,TestUart& uart,unsigned sec,const char* date="280926") {
  now_ms+=1000;uart.feed(rmc(sec,date));gps.loop();
}
static void testFreshnessAndRtc() {
  now_ms=0;
  TestUart uart;mesh::RTCClock clock;
  MicroNMEALocationProvider gps(uart,&clock,-1,-1);
  CHECK(!gps.isEnabled() && !gps.isValid());
  gps.begin();uart.feed(gga());uart.feed(rmc());gps.loop();
  CHECK(gps.isValid() && gps.satellitesCount()==8);
  for(unsigned i=0;i<5;++i){now_ms+=1000;gps.loop();}
  CHECK(clock.writes==0); // No advancing RMC, regardless of loop ticks.
  sample(gps,uart,1);CHECK(clock.writes==0);
  sample(gps,uart,2);CHECK(clock.writes==1);
  CHECK(clock.value==DateTime(2026,9,28,12,0,2).unixtime());
  CHECK(gps.getLastValidTimeSync()==clock.value && !gps.waitingTimeSync());
  const long rmc_time=gps.getTimestamp();
  uart.feed(gga("235959.00"));gps.loop();
  CHECK(gps.getTimestamp()==rmc_time); // GGA cannot mutate the cached RMC date/time.
  now_ms+=9999;CHECK(gps.isValid());
  now_ms+=1;CHECK(!gps.isValid() && gps.getTimestamp()==0 && gps.satellitesCount()==0);
  clock.value+=1801;const uint32_t advanced_rtc=clock.value;
  now_ms+=1800001;gps.loop();
  CHECK(!gps.isValid() && clock.writes==1 && clock.value==advanced_rtc);
  // Even repeated identical RMC at the periodic sync deadline cannot write RTC.
  for(unsigned i=0;i<4;++i)sample(gps,uart,2);
  CHECK(clock.writes==1);
  gps.syncTime();sample(gps,uart,10);sample(gps,uart,11);
  CHECK(clock.writes==1);sample(gps,uart,12);CHECK(clock.writes==2);
  CHECK(clock.value==DateTime(2026,9,28,12,0,12).unixtime());
  gps.syncTime();sample(gps,uart,20);sample(gps,uart,19);sample(gps,uart,20);
  CHECK(clock.writes==2);sample(gps,uart,21);CHECK(clock.writes==3);
  gps.syncTime();sample(gps,uart,30);sample(gps,uart,40);sample(gps,uart,41);
  CHECK(clock.writes==3);sample(gps,uart,42);CHECK(clock.writes==4);
  uart.feed(rmc(43,"280926","V"));gps.loop();CHECK(!gps.isValid());
  gps.stop();CHECK(!gps.isEnabled() && !gps.isValid() && gps.getTimestamp()==0);
}
static void testDatesAndQualification() {
  for(const char* date : {"", "280923", "310226", "290226", "000926", "281326", "280026"}) {
    TestUart uart;mesh::RTCClock clock;MicroNMEALocationProvider gps(uart,&clock,-1,-1);gps.begin();
    for(unsigned i=0;i<3;++i)sample(gps,uart,i,date);
    CHECK(clock.writes==0 && gps.getTimestamp()==0);
  }
  for(const char* time : {"", "240000.00", "126000.00", "120060.00"}) {
    TestUart uart;mesh::RTCClock clock;MicroNMEALocationProvider gps(uart,&clock,-1,-1);gps.begin();
    uart.feed(rmc());gps.loop(); // Missing UTC must not inherit the old parsed time.
    uart.feed(rmc(1,"280926","A",time));gps.loop();
    CHECK(clock.writes==0 && gps.getTimestamp()==0);
  }
  for(const char* date : {"290228", "280940"}) {
    TestUart uart;mesh::RTCClock clock;MicroNMEALocationProvider gps(uart,&clock,-1,-1);gps.begin();
    for(unsigned i=0;i<3;++i)sample(gps,uart,i,date);
    CHECK(clock.writes==1 && gps.isValid()); // No obsolete year<2030 cutoff.
  }
  TestUart uart;mesh::RTCClock clock;MicroNMEALocationProvider gps(uart,&clock,-1,-1);gps.begin();
  sample(gps,uart,0);sample(gps,uart,1);
  now_ms+=10000;sample(gps,uart,2);CHECK(clock.writes==0);
  sample(gps,uart,3);CHECK(clock.writes==0);sample(gps,uart,4);CHECK(clock.writes==1);
  gps.syncTime();uart.feed(sentence("GNXXX,120000.00,A"));gps.loop();CHECK(!gps.hasRecentInput());
  std::string bad=rmc();bad[bad.size()-4]='X';uart.feed(bad);gps.loop();CHECK(!gps.hasRecentInput());
}
static void testBudgetLifecycleWrap() {
  TestUart uart;mesh::RTCClock clock;RefCountedDigitalPin shared(15);shared.begin();
  shared.claim(); // Another peripheral owns the same rail.
  MicroNMEALocationProvider gps(uart,&clock,14,13,&shared);
  gps.stop();CHECK(digitalRead(15)==HIGH);
  gps.begin();const unsigned writes=pin_writes[15];gps.begin();CHECK(pin_writes[15]==writes);
  gps.reset();CHECK(pin_writes[15]==writes && digitalRead(13)==GPS_EN_ACTIVE);
  gps.stop();gps.stop();CHECK(digitalRead(15)==HIGH);
  shared.release();CHECK(digitalRead(15)==LOW); // No leaked begin()/reset() claims.
  uart.feed(rmc()+rmc(1)+rmc(2));gps.begin();gps.loop();
  CHECK(clock.writes==0 && !gps.isValid()); // Buffered previous session is discarded.
  uart.feed(rmc());gps.loop();CHECK(gps.isValid());
  uart.feed(std::string(2000,'X'));unsigned before=uart.reads;gps.loop();CHECK(uart.reads-before==256);
  gps.stop();before=uart.reads;gps.loop();CHECK(uart.reads==before);
  uart.input.clear();gps.begin();uart.feed("$GNRMC,1200");gps.loop();gps.reset();
  uart.feed(rmc());gps.loop();CHECK(gps.isValid()); // Partial parser state was cleared.
  digitalWrite(13,!GPS_EN_ACTIVE);CHECK(!gps.isEnabled() && !gps.isValid());
  before=uart.reads;gps.loop();CHECK(uart.reads==before);
  gps.stop();uart.input.clear();now_ms=0xfffffff0U;gps.begin();
  sample(gps,uart,0);sample(gps,uart,1);sample(gps,uart,2);
  CHECK(gps.isValid() && clock.writes==1);
  now_ms+=10000;CHECK(!gps.isValid() && gps.getTimestamp()==0);
  gps.stop();CHECK(digitalRead(15)==LOW);
}

class TestManager : public EnvironmentSensorManager {
public:
  explicit TestManager(LocationProvider& provider):EnvironmentSensorManager(provider){}
  bool awake() const {return gps_wake;}
  bool active() const {return gps_active;}
  void dropProvider(){_location=nullptr;gps_detected=false;}
};

static void testScheduler() {
  now_ms=100;
  Serial1.input.clear();mesh::RTCClock clock;
#if SMARTUI_OPTIONAL_UART_GPS
  OptionalUartNmeaLocationProvider<TestUart> gps(Serial1,&clock,3,4,13);
#else
  MicroNMEALocationProvider gps(Serial1,&clock,14,13);
#endif
  uint8_t saving=1;gps.setPowerSavingProfile(saving,2,3);
  TestManager manager(gps);CHECK(manager.begin());
  CHECK(!manager.active() && !manager.awake() && !gps.isEnabled());
  const unsigned boot_begins=Serial1.begins;
  gps.syncTime();now_ms+=10000000;manager.loop();
  CHECK(!manager.awake() && !gps.isEnabled() && Serial1.begins==boot_begins);
  CHECK(manager.setSettingValue("gps","1"));manager.loop();CHECK(manager.awake());
  // Repeated ON must not restart or discard a partially qualified fix.
  Serial1.feed(rmc());manager.loop();CHECK(manager.setSettingValue("gps","1"));
  now_ms+=500;Serial1.feed(rmc(1));manager.loop();
  CHECK(clock.writes==0 && manager.awake());
  CHECK(manager.setSettingValue("gps_interval","60"));
  now_ms+=500;Serial1.feed(gga());Serial1.feed(rmc(2));manager.loop();
  CHECK(clock.writes==1 && !manager.awake() && manager.active());
  CHECK(std::fabs(manager.node_lat-55.75)<0.00001 && std::fabs(manager.node_altitude-123.0)<0.001);
  CHECK(!gps.isEnabled()); // Last fix copied before early sleep clears provider.
  now_ms+=2999;manager.loop();CHECK(!manager.awake());
  now_ms+=1;manager.loop();CHECK(manager.awake());
  now_ms+=2000;manager.loop();CHECK(!manager.awake()); // No fix: bounded wake window.
  saving=0;manager.loop();CHECK(manager.awake() && manager.active());
  now_ms+=100000;manager.loop();CHECK(manager.awake());
  saving=1;manager.loop();CHECK(manager.awake());
  now_ms+=2000;manager.loop();CHECK(!manager.awake());
  CHECK(manager.setSettingValue("gps","0"));gps.syncTime();
  now_ms+=100000;manager.loop();CHECK(!manager.awake() && !manager.active());
  saving=0;manager.loop();CHECK(!manager.awake());
  CayenneLPP telemetry;manager.querySensors(TELEM_PERM_LOCATION,telemetry);CHECK(telemetry.gps_records==0);
  // Deadline arithmetic remains correct across millis() rollover.
  saving=1;now_ms=0xfffffff0U;CHECK(manager.setSettingValue("gps","1"));manager.loop();
  now_ms+=1999;manager.loop();CHECK(manager.awake());
  now_ms+=1;manager.loop();CHECK(!manager.awake());
  now_ms+=2999;manager.loop();CHECK(!manager.awake());
  now_ms+=1;manager.loop();CHECK(manager.awake());
  CHECK(manager.setSettingValue("gps","0"));manager.dropProvider();
  manager.loop();CHECK(manager.begin());manager.loop();CHECK(!manager.setSettingValue("gps","1"));
}
int main() {
  testFreshnessAndRtc();testDatesAndQualification();testBudgetLifecycleWrap();testScheduler();
  printf("PASS: %u onboard GPS/GPSv2 checks (real providers + MicroNMEA + manager, optional=%d)\n",checks,SMARTUI_OPTIONAL_UART_GPS);
}
'''


def host_path(path: Path) -> str:
    if os.name != "nt":
        return str(path)
    return "/mnt/" + path.drive[0].lower() + path.as_posix()[2:]


def main() -> None:
    if not (LIB / "MicroNMEA.cpp").exists():
        raise SystemExit("Install pinned ProMicro PlatformIO dependencies first.")
    with tempfile.TemporaryDirectory(prefix="smartui-onboard-gps-") as raw:
        folder = Path(raw)
        for name, content in (("Arduino.h", ARDUINO), ("Mesh.h", MESH), ("RTClib.h", RTC),
                              ("Wire.h", WIRE), ("CayenneLPP.h", CAYENNE), ("test.cpp", SOURCE)):
            (folder / name).write_text(content, encoding="utf-8")
        include = [arg for path in (folder, ROOT / "src", LIB) for arg in ("-I", host_path(path))]
        sources = [folder / "test.cpp", LIB / "MicroNMEA.cpp",
                   ROOT / "src/helpers/sensors/EnvironmentSensorManager.cpp"]
        for optional in (0, 1):
            binary = folder / f"gps-{optional}"
            args = ["-std=c++11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter", "-O2",
                    "-DENV_INCLUDE_GPS=1", "-DENV_SKIP_GPS_DETECT=1", "-DPIN_GPS_TX=3", "-DPIN_GPS_RX=4",
                    f"-DSMARTUI_OPTIONAL_UART_GPS={optional}", *include,
                    *map(host_path, sources), "-o", host_path(binary)]
            compiler = ["wsl", "--exec", "g++"] if os.name == "nt" else [shutil.which("g++") or "g++"]
            subprocess.run([*compiler, *args], check=True, timeout=60)
            run = ["wsl", "--exec", host_path(binary)] if os.name == "nt" else [str(binary)]
            subprocess.run(run, check=True, timeout=20)


if __name__ == "__main__":
    main()
