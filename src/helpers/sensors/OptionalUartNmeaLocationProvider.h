#pragma once

#include "LocationProvider.h"
#include <MicroNMEA.h>
#include <RTClib.h>
#include <helpers/RTCClockQuality.h>
#include <string.h>

// Optional 3.3 V UART/NMEA receiver. No serial probe or delay at boot, no
// receiver-specific configuration commands, and no dependency on a phone app.
template <typename Uart>
class OptionalUartNmeaLocationProvider : public LocationProvider {
  static constexpr uint32_t INPUT_TIMEOUT_MS = 10000;
  static constexpr uint32_t SCAN_INTERVAL_MS = 2400;
  static constexpr uint32_t TIME_SYNC_INTERVAL_MS = 1800000;
  char _buffer[128] = {};
  MicroNMEA _nmea;
  Uart& _serial;
  mesh::RTCClock* _clock;
  int _rx, _tx, _en;
  bool _enabled = false, _input_seen = false, _fix_seen = false;
  bool _uart_started = false;
  bool _locked = false, _rmc_seen = false, _synced = false;
  uint8_t _rate_index = 0, _good_sentences = 0, _time_samples = 0;
  uint32_t _rate = 0, _rate_since = 0, _last_input = 0, _last_fix = 0;
  uint32_t _last_rmc = 0, _last_sync = 0, _candidate_time = 0;
  long _latitude = 0, _longitude = 0, _altitude = 0;

  static bool rmcHasDate(const char* sentence) {
    const char* field = sentence;
    for (unsigned i = 0; i < 9; ++i) {
      field = strchr(field, ',');
      if (!field) return false;
      ++field;
    }
    for (unsigned i = 0; i < 6; ++i) {
      if (field[i] < '0' || field[i] > '9') return false;
    }
    return field[6] == ',' || field[6] == '*';
  }

  static uint32_t baudAt(uint8_t index) {
    static const uint32_t rates[] = {9600, 38400, 115200, 4800, 19200, 57600};
    return rates[index % 6];
  }

  void startRate() {
    // Adafruit nRF52 Uart::end() is not safe before the first begin().
    if (_uart_started) _serial.end();
    // Adafruit nRF52 Uart::setPins expects NODE RX first, NODE TX second.
    _serial.setPins(_rx, _tx);
    _rate = baudAt(_rate_index);
    _serial.begin(_rate);
    _uart_started = true;
    _rate_since = millis();
    _nmea.clear();
    _good_sentences = _time_samples = 0;
    _input_seen = _fix_seen = _rmc_seen = false;
  }

  bool validDate() const {
    const unsigned y = _nmea.getYear(), m = _nmea.getMonth(), d = _nmea.getDay();
    if (y < 2024 || y > 2099 || m < 1 || m > 12 || d < 1 ||
        _nmea.getHour() > 23 || _nmea.getMinute() > 59 || _nmea.getSecond() > 59) return false;
    static const uint8_t days[] = {31,28,31,30,31,30,31,31,30,31,30,31};
    unsigned limit = days[m - 1];
    if (m == 2 && y % 4 == 0 && (y % 100 != 0 || y % 400 == 0)) ++limit;
    return d <= limit;
  }

  void acceptSentence(uint32_t now) {
    const char* sentence = _nmea.getSentence();
    if (!sentence || sentence[0] != '$' || !MicroNMEA::testChecksum(sentence)) return;
    const char* id = _nmea.getMessageID();
    const bool rmc = strcmp(id, "RMC") == 0;
    if (!rmc && strcmp(id, "GGA") != 0) return;
    _input_seen = true;
    _last_input = now;
    if (_good_sentences < 2) ++_good_sentences;
    if (_good_sentences >= 2) _locked = true;
    if (_nmea.isValid() && _nmea.getLatitude() >= -90000000L &&
        _nmea.getLatitude() <= 90000000L && _nmea.getLongitude() >= -180000000L &&
        _nmea.getLongitude() <= 180000000L) {
      _fix_seen = true;
      _last_fix = now;
      _latitude = _nmea.getLatitude();
      _longitude = _nmea.getLongitude();
      long altitude = 0;
      if (_nmea.getAltitude(altitude)) _altitude = altitude;
    } else {
      _fix_seen = false;
      _time_samples = 0;
    }
    if (!rmc) return;
    if (!rmcHasDate(sentence) || !validDate()) {
      _rmc_seen = false;
      _time_samples = 0;
      return;
    }
    _rmc_seen = true;
    _last_rmc = now;
    const uint32_t timestamp = static_cast<uint32_t>(getTimestamp());
    if (!_fix_seen || !meshRtcTimestampPlausible(timestamp)) {
      _time_samples = 0;
      return;
    }
    // Require advancing UTC samples, not several sentences for the same fix.
    if (_time_samples == 0 || timestamp < _candidate_time || timestamp > _candidate_time + 5) {
      _time_samples = 1;
    } else if (timestamp > _candidate_time && _time_samples < 3) {
      ++_time_samples;
    }
    _candidate_time = timestamp;
    if (_clock && _time_samples >= 3 && (_time_sync_needed || !_synced ||
        static_cast<uint32_t>(now - _last_sync) >= TIME_SYNC_INTERVAL_MS)) {
      _clock->setCurrentTime(timestamp);
      _last_valid_time_sync = timestamp;
      _time_sync_needed = false;
      _synced = true;
      _last_sync = now;
    }
  }

public:
  OptionalUartNmeaLocationProvider(Uart& serial, mesh::RTCClock* clock,
      int rx, int tx, int enable = -1)
      : _nmea(_buffer, sizeof(_buffer)), _serial(serial), _clock(clock),
        _rx(rx), _tx(tx), _en(enable) {}

  void begin() override {
    if (_enabled) return;
    _enabled = true;
    _time_sync_needed = true;
    _locked = false;
    _rate_index = 0;
    if (_en >= 0) { pinMode(_en, OUTPUT); digitalWrite(_en, HIGH); }
    startRate();
  }
  void stop() override {
    if (_uart_started) _serial.end();
    _uart_started = false;
    _enabled = _input_seen = _fix_seen = _locked = _rmc_seen = false;
    _time_samples = 0;
    if (_en >= 0) { pinMode(_en, OUTPUT); digitalWrite(_en, LOW); }
    _nmea.clear();
  }
  void reset() override {
    _nmea.clear();
    _input_seen = _fix_seen = _rmc_seen = false;
    _time_samples = 0;
  }
  void loop() override {
    if (!_enabled) return;
    const uint32_t now = millis();
    // UART noise cannot monopolize the cooperative radio/UI loop.
    for (unsigned budget = 0; budget < 256 && _serial.available(); ++budget) {
      const int c = _serial.read();
      if (c >= 0 && _nmea.process(static_cast<char>(c))) acceptSentence(now);
    }
    if (_locked && !hasRecentInput()) {
      _locked = false;
      _rate_since = now;
    }
    if (!_locked && static_cast<uint32_t>(now - _rate_since) >= SCAN_INTERVAL_MS) {
      _rate_index = (_rate_index + 1) % 6;
      startRate();
    }
  }
  bool isEnabled() override { return _enabled; }
  bool supportsInputStatus() const override { return true; }
  bool hasRecentInput() const override {
    return _enabled && _input_seen && static_cast<uint32_t>(millis() - _last_input) < INPUT_TIMEOUT_MS;
  }
  uint32_t getBaudRate() const override { return _enabled ? _rate : 0; }
  bool isValid() override {
    return hasRecentInput() && _fix_seen && _nmea.isValid() &&
        static_cast<uint32_t>(millis() - _last_fix) < INPUT_TIMEOUT_MS;
  }
  long getLatitude() override { return _latitude; }
  long getLongitude() override { return _longitude; }
  long getAltitude() override { return _altitude; }
  long satellitesCount() override { return hasRecentInput() ? _nmea.getNumSatellites() : 0; }
  long getTimestamp() override {
    if (!_rmc_seen || !validDate() || static_cast<uint32_t>(millis() - _last_rmc) >= INPUT_TIMEOUT_MS) return 0;
    return DateTime(_nmea.getYear(), _nmea.getMonth(), _nmea.getDay(),
        _nmea.getHour(), _nmea.getMinute(), _nmea.getSecond()).unixtime();
  }
  void sendSentence(const char* sentence) override {
    if (_enabled) MicroNMEA::sendSentence(_serial, sentence);
  }
  void setPinEn(int enable) override { if (!_enabled) _en = enable; }
  int getPinEn() override { return _en; }
};
