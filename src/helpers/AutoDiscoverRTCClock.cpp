#include "AutoDiscoverRTCClock.h"
#include "RTClib.h"
#include <Melopero_RV3028.h>
#include "RTC_RX8130CE.h"

static RTC_DS3231 rtc_3231;
static bool ds3231_success = false;

static Melopero_RV3028 rtc_rv3028;
static bool rv3028_success = false;

static RTC_PCF8563 rtc_8563;
static bool rtc_8563_success = false;

static RTC_RX8130CE rtc_8130;
static bool rtc_8130_success = false;

#define DS3231_ADDRESS   0x68
#define RV3028_ADDRESS   0x52
#define PCF8563_ADDRESS  0x51
#define RX8130CE_ADDRESS 0x32

bool AutoDiscoverRTCClock::hasHardwareRTC() const {
  return ds3231_success || rv3028_success || rtc_8563_success || rtc_8130_success;
}

bool AutoDiscoverRTCClock::i2c_probe(TwoWire& wire, uint8_t addr) {
  wire.beginTransmission(addr);
  uint8_t error = wire.endTransmission();
  return (error == 0);
}

void AutoDiscoverRTCClock::begin(TwoWire& wire) {
  #if !defined(DISABLE_DS3231_PROBE)
  if (i2c_probe(wire, DS3231_ADDRESS)) {
    ds3231_success = rtc_3231.begin(&wire);
  }
  #endif

  if (i2c_probe(wire, RV3028_ADDRESS)) {
    rtc_rv3028.initI2C(wire);
    rtc_rv3028.writeToRegister(0x35, 0x00);
    rtc_rv3028.writeToRegister(0x37, 0xB4); // Direct Switching Mode (DSM): when VDD < VBACKUP, switchover occurs from VDD to VBACKUP
    rtc_rv3028.set24HourMode(); // Set the device to use the 24hour format (default) instead of the 12 hour format
    rv3028_success = true;
  }

  if (i2c_probe(wire, PCF8563_ADDRESS)) {
    MESH_DEBUG_PRINTLN("PCF8563: Found");
    rtc_8563_success = rtc_8563.begin(&wire);
  }

  if (i2c_probe(wire, RX8130CE_ADDRESS)) {
    MESH_DEBUG_PRINTLN("RX8130CE: Found");
    rtc_8130.begin(&wire);
    rtc_8130_success = true;
    MESH_DEBUG_PRINTLN("RX8130CE: Initialized");
  }

  _hardware_time_trusted = hasHardwareRTC() &&
                           meshRtcTimestampPlausible(readHardwareTime());
}

uint32_t AutoDiscoverRTCClock::readHardwareTime() {
  if (ds3231_success) {
    return rtc_3231.now().unixtime();
  }

  if (rv3028_success) {
    return DateTime(
        rtc_rv3028.getYear(),
        rtc_rv3028.getMonth(),
        rtc_rv3028.getDate(),
        rtc_rv3028.getHour(),
        rtc_rv3028.getMinute(),
        rtc_rv3028.getSecond()
    ).unixtime();
  }

  if (rtc_8563_success) {
    return rtc_8563.now().unixtime();
  }

  if (rtc_8130_success) {
    MESH_DEBUG_PRINTLN("RX8130CE: Reading time");
    return rtc_8130.now().unixtime();
  }

  return 0;
}

uint32_t AutoDiscoverRTCClock::getCurrentTime() {
  if (_hardware_time_trusted && hasHardwareRTC()) {
    uint32_t hardware_time = readHardwareTime();
    if (meshRtcTimestampPlausible(hardware_time)) return hardware_time;
    _hardware_time_trusted = false;
  }
  return _fallback != NULL ? _fallback->getCurrentTime() : 0;
}

void AutoDiscoverRTCClock::setCurrentTime(uint32_t time) { 
  if (ds3231_success) {
    rtc_3231.adjust(DateTime(time));
  } else if (rv3028_success) {
    auto dt = DateTime(time);
	  uint8_t weekday = (dt.day() + (uint16_t)((2.6 * dt.month()) - 0.2) - (2 * (dt.year() / 100)) + dt.year() + (uint16_t)(dt.year() / 4) + (uint16_t)(dt.year() / 400)) % 7;
    rtc_rv3028.setTime(dt.year(), dt.month(), weekday, dt.day(), dt.hour(), dt.minute(), dt.second());
  } else if (rtc_8563_success) {
    rtc_8563.adjust(DateTime(time));
  } else if (rtc_8130_success) {
    MESH_DEBUG_PRINTLN("RX8130CE: Setting time");
    rtc_8130.adjust(DateTime(time));
  }
  // Mirror explicit fixes into the software clock as a safe fallback if the
  // external RTC later stops responding or loses validity.
  if (_fallback != NULL) _fallback->setCurrentTime(time);
  if (hasHardwareRTC()) {
    _hardware_time_trusted = meshRtcTimestampPlausible(time);
  }
}

bool AutoDiscoverRTCClock::isTimeTrusted() {
  if (_hardware_time_trusted && hasHardwareRTC()) {
    if (meshRtcTimestampPlausible(readHardwareTime())) return true;
    _hardware_time_trusted = false;
  }
  return _fallback != NULL && _fallback->isTimeTrusted();
}

void AutoDiscoverRTCClock::setEstimatedTime(uint32_t time) {
  if (isTimeTrusted()) return;

  if (_fallback != NULL) {
    _fallback->setEstimatedTime(time);
  }

  // Never write an estimate to a battery-backed chip: after reboot there is no
  // durable source-quality bit with which to distinguish it from a real RTC
  // fix.  The fallback keeps the estimate for packet ordering only.
  _hardware_time_trusted = false;
}
