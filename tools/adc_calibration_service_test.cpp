#include "AdcCalibrationService.h"
#include "ui-new/BatteryShutdownPolicy.h"
#include <cassert>
#include <cstdio>
#include <initializer_list>

using Service = smartui::AdcCalibrationService;
using Owner = Service::Owner;
using Result = Service::Result;
static unsigned checks = 0;
#define CHECK(x) do { ++checks; assert(x); } while (0)

int main() {
  for (uint32_t start : {0U, 100U, 0xffff0000U, 0xffffffffU}) {
    Service service;
    CHECK(service.owner() == Owner::NONE && service.remaining(start) == 0);
    CHECK(service.start(start, true, false, true, true, Owner::USB_CONSOLE, 0) == Result::READONLY);
    CHECK(service.start(start, false, true, true, true, Owner::USB_CONSOLE, 0) == Result::UNSUPPORTED);
    CHECK(service.start(start, true, true, false, true, Owner::USB_CONSOLE, 0) == Result::USB_REQUIRED);
    // Bluetooth/TCP cannot claim a local USB session, even with VBUS present.
    CHECK(service.start(start, true, true, true, false, Owner::NONE, 0) == Result::USB_REQUIRED);
    CHECK(service.start(start, true, true, true, true, Owner::USB_COMPANION, 7) == Result::OK);
    CHECK(service.remaining(start) == 120000U);
    CHECK(service.start(start + 30000, true, true, true, true, Owner::USB_COMPANION, 7) == Result::OK);
    CHECK(service.remaining(start + 30000) == 90000U);
    CHECK(service.start(start + 30001, true, true, true, true, Owner::USB_CONSOLE, 0) == Result::BUSY);
    CHECK(service.update(start + 119999, true, true, 7, true));
    CHECK(service.remaining(start + 119999) == 1);
    CHECK(!service.update(start + 120000, true, true, 7, true));
    CHECK(service.remaining(start + 120000) == 0);
    for (unsigned cause = 0; cause < 4; ++cause) {
      service.stop();
      CHECK(service.start(start, true, true, true, true, Owner::USB_COMPANION, 7) == Result::OK);
      CHECK(!service.update(start + 1, cause != 0, cause != 1, cause == 2 ? 8 : 7, cause != 3));
      // USB reconnect or permission recovery never implicitly restarts.
      CHECK(!service.update(start + 2, true, true, 7, true));
      CHECK(service.remaining(start + 2) == 0);
    }
    CHECK(service.start(start, true, true, true, true, Owner::USB_CONSOLE, 0) == Result::OK);
    service.stop();
    CHECK(!service.update(start + 1, true, true, 0, true));
  }
  // Existing normal/emergency thresholds are unchanged. A service hold only
  // selects zero after the production USB/session policy affirmed it.
  CHECK(smartui::batteryShutdownThreshold(true, 3200, 2700) == 3200);
  CHECK(smartui::batteryShutdownThreshold(false, 3200, 2700) == 2700);
  CHECK(smartui::effectiveBatteryShutdownThreshold(3200, 2700, true) == 2700);
  CHECK(smartui::nextLowBatteryStrikeCount(3, 2770, 3200, 3) == 3);
  CHECK(smartui::nextLowBatteryStrikeCount(3, 2770, 0, 3) == 0);
  CHECK(smartui::nextLowBatteryStrikeCount(0, 2600, 2700, 3) == 1);
  std::printf("PASS %u ADC service policy checks\n", checks);
}
