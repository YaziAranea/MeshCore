"""Execute production UI cutoff block and recovery policy with board stubs."""
from pathlib import Path
import argparse
from test_ui_sessions_v006 import run_cpp

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'qa_outputs/ui-battery-test1')
    args=parser.parse_args()
    source=(ROOT/'examples/companion_radio/ui-new/UITask.cpp').read_text(encoding='utf-8')
    loop=source[source.index('void UITask::loop()'):source.index('void UITask::messageTransferState(')]
    block=loop[loop.rindex('#if defined(AUTO_SHUTDOWN_MILLIVOLTS)'):loop.rindex('#endif')+6]
    code=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include "BatteryShutdownPolicy.h"
#include "RecoveryBatteryGuard.h"
#include "UiTiming.h"
#define AUTO_SHUTDOWN_MILLIVOLTS 3200
#define LOW_BATTERY_SHUTDOWN_FLOOR_MILLIVOLTS 2700
#define LOW_BATTERY_SHUTDOWN_CONFIRM_COUNT 3
#define LOW_BATTERY_SHUTDOWN_CHECK_MILLIS 1000
uint32_t now=0;
uint32_t millis() { return now; }
struct Board {
  bool external=false, confirmed=false;
  bool isExternalPowered() { return external; }
  bool isUsbPowerConfirmed() { return confirmed; }
};
struct Task {
  Board board; Board* _board=&board;
  uint16_t threshold=3200, mv=3100, _low_batt_threshold=0;
  uint8_t _low_batt_strikes=0;
  bool _adc_calibration_service_active=false, _storage_recovery_active=false;
  uint32_t next_batt_chck=0;
  int shutdowns=0;
  uint16_t getLowBatteryShutdownThreshold() { return threshold; }
  smartui::BatteryReading readSafetyBattery() { return smartui::batteryReading(mv); }
  void shutdown(bool,bool,bool) { ++shutdowns; }
  void checkBattery() {
''' + block + r'''
  }
  void tick(uint16_t value,bool external) {
    now+=1000; mv=value; board.external=external; checkBattery();
  }
};
static int checks=0;
#define CHECK(x) do { ++checks; assert(x); } while(0)
int main() {
  Task usb;
  for(int i=0;i<10;++i) usb.tick(3100,true);
  CHECK(usb.shutdowns==0 && usb._low_batt_strikes==0);
  usb.tick(2699,true); usb.tick(2699,true); CHECK(usb.shutdowns==0);
  usb.tick(2699,true); CHECK(usb.shutdowns==1);
  Task unplug;
  unplug.tick(3100,true); unplug.tick(3100,false); unplug.tick(3100,false);
  CHECK(unplug.shutdowns==0 && unplug._low_batt_strikes==2);
  unplug.tick(3100,false); CHECK(unplug.shutdowns==1);
  Task transition;
  transition.tick(3100,false); transition.tick(3100,false);
  transition.tick(2600,true); CHECK(transition.shutdowns==0 && transition._low_batt_strikes==1);
  transition.tick(0,true); CHECK(transition._low_batt_strikes==1);
  transition.tick(2600,true); CHECK(transition.shutdowns==0);
  transition.tick(2600,true); CHECK(transition.shutdowns==1);
  Task invalid;
  for(int i=0;i<10;++i) invalid.tick(0,false);
  CHECK(invalid.shutdowns==0 && invalid._low_batt_strikes==0);
  Task unknown; unknown._board=nullptr;
  unknown.tick(3100,false); unknown.tick(3100,false); unknown.tick(3100,false);
  CHECK(unknown.shutdowns==1); // Unknown external-power detection never bypasses normal protection.
  Task disabled; disabled.threshold=2700;
  for(int i=0;i<3;++i) disabled.tick(3100,false);
  CHECK(disabled.shutdowns==0);
  for(int i=0;i<3;++i) disabled.tick(2600,false);
  CHECK(disabled.shutdowns==1);

  Task calibration;
  calibration.board.confirmed=true;
  calibration._adc_calibration_service_active=true;
  calibration._low_batt_strikes=2;
  for(int i=0;i<150;++i) calibration.tick(2600,true);
  CHECK(calibration.shutdowns==0 && calibration._low_batt_strikes==0);
  // The production service owner ends the window on timeout, abort or save.
  calibration._adc_calibration_service_active=false;
  calibration.tick(2600,true); CHECK(calibration._low_batt_strikes==1);
  calibration.tick(2600,true); CHECK(calibration.shutdowns==0);
  calibration.tick(2600,true); CHECK(calibration.shutdowns==1);
  Task unconfirmed;
  unconfirmed._adc_calibration_service_active=true;
  for(int i=0;i<3;++i) unconfirmed.tick(2600,true);
  CHECK(unconfirmed.shutdowns==1); // Fail-safe external=true is not affirmative USB evidence.
  Task recovery_hold;
  recovery_hold.board.confirmed=true;
  recovery_hold._adc_calibration_service_active=true;
  recovery_hold._storage_recovery_active=true;
  for(int i=0;i<3;++i) recovery_hold.tick(2600,true);
  CHECK(recovery_hold.shutdowns==1); // A service window never bypasses storage recovery safety.
  Task lost_usb;
  lost_usb.board.confirmed=true;
  lost_usb._adc_calibration_service_active=true;
  lost_usb.tick(2600,true); CHECK(lost_usb.shutdowns==0);
  lost_usb.board.confirmed=false;
  for(int i=0;i<3;++i) lost_usb.tick(2600,false);
  CHECK(lost_usb.shutdowns==1);

  smartui::RecoveryBatteryGuard recovery;
  CHECK(!recovery.update(0,3100,true,3200));
  CHECK(!recovery.update(1000,3100,true,3200));
  CHECK(!recovery.update(2000,3100,true,3200));
  CHECK(!recovery.update(3000,2600,true,3200));
  CHECK(!recovery.update(4000,0,true,3200));
  CHECK(!recovery.update(5000,2600,true,3200));
  CHECK(recovery.update(6000,2600,true,3200));
  smartui::RecoveryBatteryGuard swap;
  CHECK(!swap.update(0,3100,false,3200));
  CHECK(!swap.update(1000,3100,false,3200));
  CHECK(!swap.update(2000,2600,true,3200));
  CHECK(!swap.update(3000,2600,true,3200));
  CHECK(swap.update(4000,2600,true,3200));
  printf("PASS %d production UI/recovery external-power, emergency-floor and ADC checks\n",checks);
}
'''
    print(run_cpp(code,args.out.resolve(),'battery'),end='')


if __name__=='__main__': main()
