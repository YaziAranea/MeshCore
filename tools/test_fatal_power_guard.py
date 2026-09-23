#!/usr/bin/env python3
"""Execute actual main.cpp fatal-loop functions with host board/display stubs."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]

def linux(path):
    return subprocess.check_output(['wsl','--exec','wslpath','-a',str(path)],text=True).strip()

def main():
    source=(ROOT/'examples/companion_radio/main.cpp').read_text(encoding='utf-8')
    code=r'''
#include <stdint.h>
#include <assert.h>
#include <stdio.h>
#include "RecoveryBatteryGuard.h"
#define AUTO_SHUTDOWN_MILLIVOLTS 3200
#define DISPLAY_CLASS TestDisplay
#define HAS_EXTERNAL_WATCHDOG 1
uint32_t now=0,stop_at=60000;
uint32_t millis(){return now;}
struct Stop {int reason;};
void delay(unsigned value){now+=value;if(now>=stop_at)throw Stop{2};}
struct Board {
  uint16_t mv=3190;bool usb=false;unsigned offs=0,reads=0;
  uint16_t getBattMilliVolts(){++reads;return mv;}
  bool isExternalPowered(){return usb;}
  void powerOff(){++offs;throw Stop{1};}
} board;
struct Display {unsigned offs=0;void turnOff(){++offs;}} display;
struct Radio {unsigned offs=0;void powerOff(){++offs;}} radio_driver;
struct Watchdog {unsigned loops=0;void loop(){++loops;}} external_watchdog;
bool radio_initialized=true;
''' + function(source,'static void serviceFatalBatterySafety()') + '\n' + function(source,'void halt()') + r'''
int main(){
  try{halt();assert(false);}catch(Stop s){assert(s.reason==1);}
  assert(now==2000 && board.offs==1 && board.reads==3);
  assert(radio_driver.offs==1 && display.offs==0 && external_watchdog.loops>0);
  now=10000;stop_at=41000;board.usb=true;board.reads=0;
  try{halt();assert(false);}catch(Stop s){assert(s.reason==2);}
  assert(board.offs==1 && board.reads<=32 && display.offs==1);
  assert(radio_driver.offs==2);
  now=50000;stop_at=53000;board.usb=false;board.mv=0;radio_initialized=false;
  try{halt();assert(false);}catch(Stop s){assert(s.reason==2);}
  assert(board.offs==1 && radio_driver.offs==2);
  puts("PASS: actual fatal-loop battery cutoff, USB/ADC handling, radio off, display timeout and scheduler/watchdog service");
}
'''
    with tempfile.TemporaryDirectory(prefix='smartui-fatal-') as tmp:
        folder=Path(tmp)
        (folder/'test.cpp').write_text(code,encoding='utf-8')
        include=ROOT/'examples/companion_radio/ui-new'
        flags=['-std=c++11','-Wall','-Wextra','-Werror','-O2']
        if shutil.which('g++'):
            subprocess.run(['g++',*flags,'-I',str(include),str(folder/'test.cpp'),'-o',str(folder/'test')],check=True)
            subprocess.run([str(folder/'test')],check=True)
        else:
            subprocess.run(['wsl','--exec','g++',*flags,'-I',linux(include),linux(folder/'test.cpp'),'-o',linux(folder/'test')],check=True)
            subprocess.run(['wsl','--exec',linux(folder/'test')],check=True)

if __name__=='__main__':main()
