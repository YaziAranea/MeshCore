#pragma once

#include "LocationProvider.h"
#include <MicroNMEA.h>
#include <RTClib.h>
#include <helpers/RefCountedDigitalPin.h>
#include <helpers/RTCClockQuality.h>
#include <string.h>

#ifndef GPS_EN
    #ifdef PIN_GPS_EN
        #define GPS_EN PIN_GPS_EN
    #else
        #define GPS_EN (-1)
    #endif
#endif

#ifndef GPS_EN_ACTIVE
    #ifdef PIN_GPS_EN_ACTIVE
        #define GPS_EN_ACTIVE PIN_GPS_EN_ACTIVE
    #else
        #define GPS_EN_ACTIVE HIGH
    #endif
#endif

#ifndef GPS_RESET
    #ifdef PIN_GPS_RESET
        #define GPS_RESET PIN_GPS_RESET
    #else
        #define GPS_RESET (-1)
    #endif
#endif

#ifndef GPS_RESET_ACTIVE
    #ifdef PIN_GPS_RESET_ACTIVE
        #define GPS_RESET_ACTIVE PIN_GPS_RESET_ACTIVE
    #else
        #define GPS_RESET_ACTIVE LOW
    #endif
#endif

class MicroNMEALocationProvider : public LocationProvider {
    char _nmeaBuffer[100];
    MicroNMEA nmea;
    mesh::RTCClock* _clock;
    Stream* _gps_serial;
    RefCountedDigitalPin* _peripher_power;
    bool _claimed = false;
    bool _enabled = false;
    int _pin_reset;
    int _pin_en;
    bool _input_seen = false, _fix_seen = false, _rmc_seen = false, _synced = false;
    uint8_t _time_samples = 0;
    uint32_t _last_input = 0, _last_fix = 0, _last_rmc = 0;
    uint32_t _last_time_sample = 0, _candidate_time = 0, _rmc_timestamp = 0;
    uint32_t _last_time_sync = 0;
    uint32_t _discard_rx = 0;
    static const uint32_t INPUT_TIMEOUT_MS = 10000;
    static const uint32_t TIME_SYNC_INTERVAL_MS = 1800000;

    void clearFreshness() {
        // clear() alone leaves a partial sentence in MicroNMEA's input buffer.
        nmea.setBuffer(_nmeaBuffer, sizeof(_nmeaBuffer));
        nmea.clear();
        _input_seen = _fix_seen = _rmc_seen = false;
        _time_samples = 0;
        _candidate_time = _rmc_timestamp = 0;
        const int queued = _gps_serial->available();
        _discard_rx = queued > 0 ? static_cast<uint32_t>(queued) : 0;
    }

    void expireFreshness(uint32_t now) {
        if (_fix_seen && static_cast<uint32_t>(now - _last_fix) >= INPUT_TIMEOUT_MS) {
            _fix_seen = false;
        }
        if (_rmc_seen && static_cast<uint32_t>(now - _last_rmc) >= INPUT_TIMEOUT_MS) {
            _rmc_seen = false;
        }
        if (_time_samples && static_cast<uint32_t>(now - _last_time_sample) >= INPUT_TIMEOUT_MS) {
            _time_samples = 0;
        }
    }

    bool validDate() const {
        const unsigned y = nmea.getYear(), m = nmea.getMonth(), d = nmea.getDay();
        if (y < 2024 || y > 2099 || m < 1 || m > 12 || d < 1 ||
            nmea.getHour() > 23 || nmea.getMinute() > 59 || nmea.getSecond() > 59) return false;
        static const uint8_t days[] = {31,28,31,30,31,30,31,31,30,31,30,31};
        unsigned limit = days[m - 1];
        if (m == 2 && y % 4 == 0 && (y % 100 != 0 || y % 400 == 0)) ++limit;
        return d <= limit;
    }

    static bool rmcHasDateTime(const char* sentence) {
        const char* field = strchr(sentence, ',');
        if (!field) return false;
        ++field;
        for (unsigned i = 0; i < 6; ++i) {
            if (field[i] < '0' || field[i] > '9') return false;
        }
        if (field[6] != '.' && field[6] != ',') return false;
        for (unsigned i = 1; i < 9; ++i) {
            field = strchr(field, ',');
            if (!field) return false;
            ++field;
        }
        for (unsigned i = 0; i < 6; ++i) {
            if (field[i] < '0' || field[i] > '9') return false;
        }
        return field[6] == ',' || field[6] == '*';
    }

    void acceptSentence(uint32_t now) {
        const char* sentence = nmea.getSentence();
        if (!sentence || sentence[0] != '$' || !MicroNMEA::testChecksum(sentence)) return;
        const bool rmc = strcmp(nmea.getMessageID(), "RMC") == 0;
        if (!rmc && strcmp(nmea.getMessageID(), "GGA") != 0) return;
        _input_seen = true;
        _last_input = now;
        _fix_seen = nmea.isValid() && nmea.getLatitude() >= -90000000L &&
            nmea.getLatitude() <= 90000000L && nmea.getLongitude() >= -180000000L &&
            nmea.getLongitude() <= 180000000L;
        if (_fix_seen) _last_fix = now;
        else _time_samples = 0;
        if (!rmc) return;
        if (!rmcHasDateTime(sentence) || !validDate()) {
            _rmc_seen = false;
            _time_samples = 0;
            return;
        }
        _rmc_timestamp = DateTime(nmea.getYear(), nmea.getMonth(), nmea.getDay(),
            nmea.getHour(), nmea.getMinute(), nmea.getSecond()).unixtime();
        _rmc_seen = true;
        _last_rmc = now;
        if (!_fix_seen || !meshRtcTimestampPlausible(_rmc_timestamp)) {
            _time_samples = 0;
            return;
        }
        // Qualification belongs to distinct, advancing UTC samples. Repeated
        // sentences and loop ticks cannot qualify or refresh an old timestamp.
        const bool advancing = _time_samples == 0 || _rmc_timestamp > _candidate_time;
        if (_time_samples == 0 || _rmc_timestamp < _candidate_time ||
            _rmc_timestamp > _candidate_time + 5) {
            _time_samples = 1;
            _last_time_sample = now;
        } else if (_rmc_timestamp > _candidate_time) {
            if (_time_samples < 3) ++_time_samples;
            _last_time_sample = now;
        }
        _candidate_time = _rmc_timestamp;
        if (_clock && advancing && _time_samples >= 3 &&
            (_time_sync_needed || !_synced ||
             static_cast<uint32_t>(now - _last_time_sync) >= TIME_SYNC_INTERVAL_MS)) {
            _clock->setCurrentTime(_rmc_timestamp);
            _last_valid_time_sync = _rmc_timestamp;
            _time_sync_needed = false;
            _synced = true;
            _last_time_sync = now;
        }
    }

public :
    MicroNMEALocationProvider(Stream& ser, mesh::RTCClock* clock = NULL, int pin_reset = GPS_RESET, int pin_en = GPS_EN,RefCountedDigitalPin* peripher_power=NULL) :
    nmea(_nmeaBuffer, sizeof(_nmeaBuffer)), _clock(clock), _gps_serial(&ser), _peripher_power(peripher_power), _pin_reset(pin_reset), _pin_en(pin_en) {
        if (_pin_reset != -1) {
            pinMode(_pin_reset, OUTPUT);
            digitalWrite(_pin_reset, GPS_RESET_ACTIVE);
        }
        if (_pin_en != -1) {
            pinMode(_pin_en, OUTPUT);
            digitalWrite(_pin_en, !GPS_EN_ACTIVE);
        }
    }

    void claim() {
        if (_claimed) return;
        _claimed = true;
        if (_peripher_power) _peripher_power->claim();
    }

    void release() {
        if (!_claimed) return;
        _claimed = false;
        if (_peripher_power) _peripher_power->release();
    }

    void begin() override {
        if (_enabled) return;
        _enabled = true;
        clearFreshness();
        _time_sync_needed = true;
        claim();
        if (_pin_en != -1) {
            digitalWrite(_pin_en, GPS_EN_ACTIVE);
        }
        if (_pin_reset != -1) {
            digitalWrite(_pin_reset, !GPS_RESET_ACTIVE);
        }
    }

    void reset() override {
        clearFreshness();
        if (!_enabled) return;
        if (_pin_reset != -1) {
            digitalWrite(_pin_reset, GPS_RESET_ACTIVE);
            delay(10);
            digitalWrite(_pin_reset, !GPS_RESET_ACTIVE);
        }
    }

    void stop() override {
        _enabled = false;
        clearFreshness();
        _time_sync_needed = false;
        if (_pin_en != -1) {
            digitalWrite(_pin_en, !GPS_EN_ACTIVE);
        }
        if (_pin_reset != -1) {
            digitalWrite(_pin_reset, GPS_RESET_ACTIVE);
        }
        release();
    }

    bool isEnabled() override {
        // directly read the enable pin if present as gps can be
        // activated/deactivated outside of here ...
        if (!_enabled) return false;
        if (_pin_en != -1) {
            return digitalRead(_pin_en) == GPS_EN_ACTIVE;
        } else {
            return true; // No power gate: logical stop still ignores UART input.
        }
    }

    void setPinEn(int pin_en) override {
        _pin_en = pin_en;
    }

    int getPinEn() override {
        return _pin_en;
    }

    void syncTime() override { clearFreshness(); _time_sync_needed = true; }
    bool supportsInputStatus() const override { return true; }
    bool hasRecentInput() const override {
        return _enabled && _input_seen &&
            static_cast<uint32_t>(millis() - _last_input) < INPUT_TIMEOUT_MS;
    }
    long getLatitude() override { return nmea.getLatitude(); }
    long getLongitude() override { return nmea.getLongitude(); }
    long getAltitude() override { 
        long alt = 0;
        nmea.getAltitude(alt);
        return alt;
    }
    long satellitesCount() override { return hasRecentInput() ? nmea.getNumSatellites() : 0; }
    bool isValid() override {
        return isEnabled() && hasRecentInput() && _fix_seen && nmea.isValid() &&
            static_cast<uint32_t>(millis() - _last_fix) < INPUT_TIMEOUT_MS;
    }

    long getTimestamp() override { 
        if (!_enabled || !_rmc_seen ||
            static_cast<uint32_t>(millis() - _last_rmc) >= INPUT_TIMEOUT_MS) return 0;
        return static_cast<long>(_rmc_timestamp);
    } 

    void sendSentence(const char *sentence) override {
        if (isEnabled()) nmea.sendSentence(*_gps_serial, sentence);
    }

    void loop() override {

        if (!isEnabled()) return;
        const uint32_t now = millis();
        expireFreshness(now);
        // UART noise must not starve the cooperative radio/UI loop.
        for (unsigned budget = 0; budget < 256 && _gps_serial->available(); ++budget) {
            const int value = _gps_serial->read();
            if (value < 0) break;
            if (_discard_rx) { --_discard_rx; continue; }
            const char c = static_cast<char>(value);
            #ifdef GPS_NMEA_DEBUG
            Serial.print(c);
            #endif
            if (nmea.process(c)) acceptSentence(now);
        }
    }
};
