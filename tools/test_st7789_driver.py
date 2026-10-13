"""Compile whole production ST7789/OLED drivers with host SPI and fault injection.

ASan/UBSan cover allocations, failed init/retry/destruction, clipped drawing and
the actual RGB565 SPI rows for all supported panel sizes and both buffer modes.
No physical display or embedded timing is simulated.

Viewport expectations are independent panel constants, not the driver's
centering formula. Heltec's 135x240 example uses rotation 3 (MX|MV), with
column start 53; rotation 1 (MY|MV) uses 52:
https://github.com/HelTecAutomation/Heltec_nRF52/blob/main/libraries/Adafruit-ST7735/Adafruit_ST7789.cpp
https://github.com/HelTecAutomation/Heltec_nRF52/blob/main/libraries/Heltec_nrf_lorawan/examples/Display/graphicstest_st7789/graphicstest_st7789.ino
"""
from pathlib import Path
import argparse
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

ARDUINO = r'''
#pragma once
#include <algorithm>
#include <cassert>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <map>
#include <string>
#include <vector>
using std::min; using std::max;
#define PROGMEM
#define pgm_read_byte(p) (*(const uint8_t*)(p))
#define OUTPUT 1
#define LOW 0
#define HIGH 1
#define PIN_TFT_VDD_CTL 1
#define PIN_TFT_LEDA_CTL 2
#define PIN_TFT_RST 3
#define PIN_TFT_DC 4
#define PIN_TFT_CS 5
#define PIN_TFT_SDA 6
#define PIN_TFT_SCL 7
#define ST7789_RESET PIN_TFT_RST
#define ST7789_RS PIN_TFT_DC
#define ST7789_CS PIN_TFT_CS
#define ST7789_SDA PIN_TFT_SDA
#define ST7789_MISO -1
#define ST7789_SCK PIN_TFT_SCL
inline int pins[256] = {};
void recordPinWrite(int,int);
inline void pinMode(int, int) {}
inline void digitalWrite(int p, int value) { assert(p>=0 && p<256); pins[p]=value; recordPinWrite(p,value); }
inline void delay(unsigned) {}
inline void yield() {}
class Print { public: virtual ~Print() = default; virtual size_t write(uint8_t)=0; };
class String {
  std::string value;
public:
  String(const char* s):value(s) {}
  size_t length() const { return value.size(); }
  const char* c_str() const { return value.c_str(); }
  void toCharArray(char* dst, size_t n) const { if(n) { std::strncpy(dst,value.c_str(),n); dst[n-1]=0; } }
};
void* driver_malloc(size_t);
void driver_free(void*);
#ifndef ESP_PLATFORM
#define rtos_malloc driver_malloc
#define rtos_free driver_free
#endif
'''

SPI = r'''
#pragma once
#include <Arduino.h>
#define MSBFIRST 1
#define SPI_MODE0 0
#define SPI_CLOCK_DIV2 2
struct SPISettings { SPISettings(unsigned=0,int=0,int=0) {} };
struct Row { unsigned x0,x1,y0,y1; std::vector<uint16_t> pixels; };
class SPIClass {
  uint8_t command=0;
  uint32_t data=0;
  unsigned count=0,x0=0,x1=0,y0=0,y1=0;
public:
  std::vector<Row> rows;
  unsigned transfers=0;
  uint8_t madctl=0;
  void begin(int=-1,int=-1,int=-1,int=-1) {}
  void setClockDivider(int) {}
  void beginTransaction(SPISettings) {}
  void endTransaction() {}
  uint8_t transfer(uint8_t value) {
    ++transfers;
    if(pins[PIN_TFT_DC]==LOW) { command=value; data=0; count=0; }
    else if(command==0x36) madctl=value;
    else if(command==0x2A || command==0x2B) {
      data=(data<<8)|value;
      if(++count==4) {
        if(command==0x2A) { x0=data>>16; x1=data&65535; }
        else { y0=data>>16; y1=data&65535; }
      }
    }
    return 0;
  }
  void transfer(void* pixels, void*, size_t bytes) {
    ++transfers;
    assert(command==0x2C && pins[PIN_TFT_DC]==HIGH);
    assert(x0<=x1 && x1<320 && y0==y1 && y1<240);
    assert(bytes==2*(x1-x0+1));
    auto* p=static_cast<uint16_t*>(pixels);
    rows.push_back({x0,x1,y0,y1,std::vector<uint16_t>(p,p+bytes/2)});
  }
  void transferBytes(uint8_t* pixels, void* out, size_t bytes) { transfer(pixels,out,bytes); }
};
inline SPIClass SPI, SPI1;
'''

HARNESS = r'''
#include <Arduino.h>
static unsigned allocation_calls=0,fail_at=0;
static std::map<void*,size_t> allocations;
void* driver_malloc(size_t size) {
  ++allocation_calls;
  if(fail_at && allocation_calls>=fail_at) return nullptr;
  void* p=std::malloc(size);
  assert(p); allocations[p]=size; return p;
}
void driver_free(void* p) {
  if(!p) return;
  size_t owned=allocations.erase(p);
  std::free(p); // ASan reports the call stack for any invalid or repeated free.
  assert(owned==1);
}
char* driver_strdup(const char* source) {
  size_t n=std::strlen(source)+1;
  char* copy=static_cast<char*>(driver_malloc(n));
  if(copy) std::memcpy(copy,source,n);
  return copy;
}
// Only production allocation sites are redirected; their full implementation
// and the actual driver class/vtable are compiled without source extraction.
#define malloc driver_malloc
#define free driver_free
#define strdup driver_strdup
#include "ST7789Display.h"
#include "OLEDDisplay.cpp"
#undef malloc
#undef free
#undef strdup
#include "OLEDDisplayFonts.cpp"
#include "ST7789Display.cpp"

static size_t backlight_on_rows=0;
static uint8_t backlight_on_madctl=0;
void recordPinWrite(int pin,int value) {
#ifdef PIN_TFT_LEDA_CTL_ACTIVE
  const int active=PIN_TFT_LEDA_CTL_ACTIVE;
#else
  const int active=LOW;
#endif
  if(pin!=PIN_TFT_LEDA_CTL || value!=active) return;
#if defined(HELTEC_VISION_MASTER_T190) || defined(THINKNODE_M9)
  const auto& spi=SPI;
#else
  const auto& spi=SPI1;
#endif
  backlight_on_rows=spi.rows.size(); backlight_on_madctl=spi.madctl;
}

static unsigned checks=0;
#define CHECK(x) do { ++checks; if(!(x)) { std::fprintf(stderr,"line %d: %s\n",__LINE__,#x); std::abort(); } } while(0)
static constexpr unsigned buffers =
#ifdef OLEDDISPLAY_DOUBLE_BUFFER
  2;
#else
  1;
#endif

class OffsetDisplay : public OLEDDisplay {
public:
  bool reachable=true;
  unsigned displays=0;
  char* log() const { return logBuffer; }
  unsigned filled() const { return logBufferFilled; }
  void display() override { ++displays; }
  bool connect() override { return reachable; }
  int getBufferOffset() override { return 4; }
  void sendCommand(uint8_t) override {}
};

void drawWithoutBuffer(OLEDDisplay& d) {
  const uint8_t image[]={0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF};
  d.clear(); d.resetDisplay(); d.setPixel(0,0); d.clearPixel(0,0);
  d.setPixelColor(0,0,WHITE); d.drawHorizontalLine(0,0,20);
  d.drawVerticalLine(0,0,20); d.fillRect(-2,-2,20,20);
  d.drawRect(-2,-2,20,20); d.drawXbm(0,0,8,8,image);
  d.drawFastImage(0,0,8,8,image); d.display();
}

void allocationLifecycle() {
  { OffsetDisplay neverInitialized; drawWithoutBuffer(neverInitialized); }
  CHECK(allocations.empty());
  for(unsigned failed=1;failed<=buffers;++failed) {
    OffsetDisplay d;
    fail_at=allocation_calls+failed;
    CHECK(!d.init()); CHECK(d.buffer==nullptr);
#ifdef OLEDDISPLAY_DOUBLE_BUFFER
    CHECK(d.buffer_back==nullptr);
#endif
    CHECK(allocations.empty()); drawWithoutBuffer(d);
    fail_at=0; CHECK(d.allocateBuffer()); CHECK(allocations.size()==buffers);
    CHECK(allocations.count(d.buffer-4)==1);
    CHECK(d.init()); d.end(); d.end(); CHECK(allocations.empty());
    drawWithoutBuffer(d); CHECK(d.init());
  }
  CHECK(allocations.empty());
  {
    OffsetDisplay d; d.reachable=false;
    auto calls=allocation_calls; CHECK(!d.init()); CHECK(calls==allocation_calls);
    d.reachable=true; CHECK(d.init());
    CHECK(d.setLogBuffer(3,8)); d.write("a\nb\nc\n");
    d.write("d\n"); // overlapping retained lines must use memmove
    char* saved=d.log(); auto size=allocations.size();
    CHECK(d.init()); CHECK(d.log()==saved && allocations.size()==size);
    fail_at=allocation_calls+1; CHECK(!d.setLogBuffer(2,10));
    CHECK(d.log()==nullptr); CHECK(d.write(uint8_t('x'))==1);
    CHECK(d.drawString(0,0,String("read-only source"))==0);
    fail_at=0; CHECK(d.setLogBuffer(2,10)); CHECK(d.setLogBuffer(0,0));
    CHECK(d.log()==nullptr); CHECK(!d.setLogBuffer(65535,65535));
    CHECK(d.write(uint8_t('x'))==1); d.end(); CHECK(d.write(uint8_t('x'))==1);
  }
  CHECK(allocations.empty());
}

void panel(unsigned width,unsigned height,unsigned ox,unsigned oy,unsigned unflipped_y) {
  SPIClass spi;
  ST7789Spi d(&spi,PIN_TFT_RST,PIN_TFT_DC,PIN_TFT_CS,GEOMETRY_RAWMODE,width,height);
  fail_at=allocation_calls+1; CHECK(!d.init()); drawWithoutBuffer(d);
  CHECK(spi.rows.empty()); fail_at=0; CHECK(d.init());
  CHECK(spi.rows.size()==height);
  CHECK(spi.madctl==0x60);
  for(unsigned y=0;y<height;++y) {
    const auto& row=spi.rows[y];
    CHECK(row.x0==ox && row.x1==ox+width-1 && row.y0==oy+y);
    CHECK(row.pixels.size()==width);
    for(auto pixel:row.pixels) CHECK(pixel==0);
  }
  auto allocated=allocation_calls;
  fail_at=allocated+1; // all future allocations fail, rendering must not allocate
  spi.rows.clear(); d.setRGB(0xF800); d.setBackgroundRGB(0x001F);
  d.setColor(WHITE); d.setPixel(width-1,height-1); d.display();
#ifdef OLEDDISPLAY_DOUBLE_BUFFER
  CHECK(spi.rows.size()==(height-1)%8+1);
  CHECK(spi.rows.back().pixels.size()==1);
#else
  CHECK(spi.rows.size()==height);
  CHECK(spi.rows.back().pixels.size()==width);
#endif
  CHECK(spi.rows.back().pixels.back()==0x00F8);
  CHECK(spi.rows.back().y0==oy+height-1);
  spi.rows.clear(); d.display();
#ifdef OLEDDISPLAY_DOUBLE_BUFFER
  CHECK(spi.rows.empty());
#else
  CHECK(spi.rows.size()==height);
#endif
  const uint8_t image[8]={255,255,255,255,255,255,255,255};
  for(unsigned iteration=0;iteration<10;++iteration) {
    d.clear(); d.fillRect(-10,-10,width+20,height+20);
    d.setColor(BLACK); d.drawRect(-1,-1,width+2,height+2);
    d.drawVerticalLine(width-1,height-1,50);
    d.drawHorizontalLine(width-1,height-1,50);
    d.drawFastImage(width-3,height-3,8,8,image);
    d.drawXbm(-3,-3,8,8,image); d.setPixel(width,height); d.clearPixel(-1,-1);
    d.setColor(WHITE); d.setPixelColor(width-1,height-1,WHITE);
    spi.rows.clear(); d.forceFullRefresh(); d.display();
    for(const auto& row:spi.rows) CHECK(row.y0>=oy && row.y0<oy+height);
  }
  // Different page contents, including a full white bitmap, must repaint every
  // visible edge after a theme change. Filling the back buffer with 0xFF is not
  // a valid invalidation sentinel: whole white pages would stay the old color.
  d.clear(); d.setColor(WHITE); d.fillRect(0,0,width,height); d.display();
  d.setRGB(0x07E0); d.setBackgroundRGB(0x001F);
  spi.rows.clear(); d.forceFullRefresh(); d.display();
  CHECK(spi.rows.size()==height);
  for(unsigned y=0;y<height;++y) {
    const auto& row=spi.rows[y];
    CHECK(row.x0==ox && row.x1==ox+width-1 && row.y0==oy+y);
    for(auto pixel:row.pixels) CHECK(pixel==0xE007);
  }
  // Test actual commands as well as literal viewport ranges in each supported
  // landscape orientation, without changing framebuffer contents.
  struct Orientation { void (ST7789Spi::*select)(); unsigned control,origin; };
  const Orientation orientations[]={
    {&ST7789Spi::flipScreenVertically,0xA0,unflipped_y},
    {&ST7789Spi::mirrorScreen,0xE0,oy},
    {&ST7789Spi::resetOrientation,0x20,unflipped_y},
    {&ST7789Spi::landscapeScreen,0x60,oy}
  };
  for(const auto& orientation:orientations) {
    spi.rows.clear(); (d.*orientation.select)(); d.display();
    CHECK(spi.madctl==orientation.control); CHECK(spi.rows.size()==height);
    for(unsigned y=0;y<height;++y) {
      const auto& row=spi.rows[y];
      CHECK(row.x0==ox && row.x1==ox+width-1 && row.y0==orientation.origin+y);
      for(auto pixel:row.pixels) CHECK(pixel==0xE007);
    }
    spi.rows.clear(); d.clear(); d.display();
    CHECK(spi.rows.size()==height);
    for(const auto& row:spi.rows) for(auto pixel:row.pixels) CHECK(pixel==0x1F00);
    d.fillRect(0,0,width,height); d.display();
  }
  CHECK(allocation_calls==allocated); fail_at=0;
  d.end(); drawWithoutBuffer(d); CHECK(d.init());
}

void checkWrapperViewport() {
#if defined(HELTEC_VISION_MASTER_T190)
  const auto& spi=SPI; const unsigned width=320,height=170,ox=0,oy=35;
#elif defined(THINKNODE_M9)
  const auto& spi=SPI; const unsigned width=320,height=240,ox=0,oy=0;
#else
  const auto& spi=SPI1; const unsigned width=240,height=135,ox=40;
  const unsigned oy=
#ifdef DISPLAY_FLIP_VERTICALLY
    52;
#else
    53;
#endif
#endif
#ifdef DISPLAY_FLIP_VERTICALLY
  CHECK(spi.madctl==0xA0);
#else
  CHECK(spi.madctl==0x60);
#endif
  CHECK(spi.rows.size()>=height);
  CHECK(backlight_on_rows==spi.rows.size() && backlight_on_madctl==spi.madctl);
  for(unsigned y=0;y<height;++y) {
    const auto& row=spi.rows[spi.rows.size()-height+y];
    CHECK(row.x0==ox && row.x1==ox+width-1 && row.y0==oy+y);
    for(auto pixel:row.pixels) CHECK(pixel==0); // clean visible RAM on boot/wake
  }
}

void wrapperLifecycle() {
  for(unsigned failed=1;failed<=buffers;++failed) {
    ST7789Display wrapper;
    fail_at=allocation_calls+failed;
    CHECK(!wrapper.begin()); CHECK(!wrapper.isOn());
#ifdef PIN_TFT_LEDA_CTL_ACTIVE
    CHECK(pins[PIN_TFT_LEDA_CTL]!=PIN_TFT_LEDA_CTL_ACTIVE);
#else
    CHECK(pins[PIN_TFT_LEDA_CTL]==HIGH);
#endif
    CHECK(pins[PIN_TFT_VDD_CTL]==HIGH && pins[PIN_TFT_RST]==LOW);
    auto transfers=SPI.transfers+SPI1.transfers;
    const uint8_t bits[8]={255,255,255,255,255,255,255,255};
    wrapper.clear(); wrapper.startFrame(); wrapper.setCursor(0,0);
    wrapper.print("Привет"); wrapper.fillRect(0,0,128,64);
    wrapper.drawRect(-1,-1,130,66); wrapper.drawXbm(0,0,bits,8,8); wrapper.endFrame();
    CHECK(SPI.transfers+SPI1.transfers==transfers);
    wrapper.turnOn(); CHECK(!wrapper.isOn()); // failure still armed
    fail_at=0; wrapper.turnOn(); CHECK(wrapper.isOn());
    checkWrapperViewport();
    auto calls=allocation_calls;
    for(unsigned wake=0;wake<8;++wake) {
      CHECK(wrapper.begin()); wrapper.startFrame(); wrapper.print("Retry");
      wrapper.fillRect(-1,-1,2,2); wrapper.endFrame(); wrapper.turnOff();
      CHECK(!wrapper.isOn()); transfers=SPI.transfers+SPI1.transfers;
      wrapper.endFrame(); CHECK(SPI.transfers+SPI1.transfers==transfers);
      wrapper.turnOn(); CHECK(wrapper.isOn());
      checkWrapperViewport();
    }
    CHECK(allocation_calls==calls);
  }
  CHECK(allocations.empty());
}

int main() {
  allocationLifecycle();
  panel(240,135,40,53,52); panel(320,170,0,35,35); panel(320,240,0,0,0);
  {
    SPIClass spi;
    ST7789Spi oversized(&spi,3,4,5,GEOMETRY_RAWMODE,321,241);
    CHECK(!oversized.init()); oversized.display(); CHECK(spi.rows.empty());
    ST7789Spi absent(nullptr,3,4,5); CHECK(!absent.init()); absent.display();
  }
  CHECK(allocations.empty()); wrapperLifecycle();
  std::printf("ST7789/OLED real driver: %u checks, allocations balanced, buffers=%u\n",checks,buffers);
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='smartui-st7789-') as directory:
        temp = Path(directory)
        (temp / 'Arduino.h').write_text(ARDUINO, encoding='utf-8')
        (temp / 'SPI.h').write_text(SPI, encoding='utf-8')
        (temp / 'Wire.h').write_text('#pragma once\nclass TwoWire {};\n', encoding='utf-8')
        (temp / 'Adafruit_GFX.h').write_text('#pragma once\n', encoding='utf-8')
        cpp = temp / 'driver.cpp'
        cpp.write_text(HARNESS, encoding='utf-8')
        native = bool(shutil.which('g++'))
        prefix = [] if native else ['wsl', '--exec']

        def path(value):
            return str(value) if native else subprocess.check_output(
                ['wsl', '--exec', 'wslpath', '-a', str(value)], text=True).strip()

        include = path(args.source_root / 'src/helpers/ui')
        temp_include = path(temp)
        source = path(cpp)
        for profile, flags in (
                ('t114', []),
                ('t114-flipped', ['-DDISPLAY_FLIP_VERTICALLY']),
                ('t190', ['-DHELTEC_VISION_MASTER_T190', '-DESP_PLATFORM', '-DPIN_TFT_LEDA_CTL_ACTIVE=1']),
                ('m9', ['-DTHINKNODE_M9', '-DESP_PLATFORM', '-DDISPLAY_SCALE_X=2.5f', '-DDISPLAY_SCALE_Y=3.75f'])):
            for reduced in (False, True):
                name = profile + ('-single' if reduced else '-double')
                exe = temp_include + '/' + name
                command = prefix + ['g++', '-std=c++17', '-O1', '-g',
                    '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                    '-fno-omit-frame-pointer', '-fno-pie', '-no-pie',
                    '-DARDUINO', '-DST7789', '-I', temp_include, '-I', include]
                if reduced:
                    command.append('-DOLEDDISPLAY_REDUCE_MEMORY')
                subprocess.run(command + flags + [source, '-o', exe], check=True)
                result = subprocess.check_output(prefix + [exe], text=True, encoding='utf-8')
                print(name + ': ' + result.strip(), flush=True)


if __name__ == '__main__':
    main()
