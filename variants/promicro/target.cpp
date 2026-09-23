#include <Arduino.h>
#include "target.h"
#include <helpers/ArduinoHelpers.h>

PromicroBoard board;

RADIO_CLASS radio = new Module(P_LORA_NSS, P_LORA_DIO_1, P_LORA_RESET, P_LORA_BUSY, SPI);

WRAPPER_CLASS radio_driver(radio, board);

VolatileRTCClock fallback_clock;
AutoDiscoverRTCClock rtc_clock(fallback_clock);
#if ENV_INCLUDE_GPS
  #if defined(SMARTUI_OPTIONAL_UART_GPS) && SMARTUI_OPTIONAL_UART_GPS
  #include <helpers/sensors/OptionalUartNmeaLocationProvider.h>
  OptionalUartNmeaLocationProvider<decltype(Serial1)> nmea(Serial1, &rtc_clock,
      PIN_GPS_RX, PIN_GPS_TX, PIN_GPS_EN);
  #else
  #include <helpers/sensors/MicroNMEALocationProvider.h>
  MicroNMEALocationProvider nmea = MicroNMEALocationProvider(Serial1, &rtc_clock);
  #endif
  EnvironmentSensorManager sensors = EnvironmentSensorManager(nmea);
#else
  EnvironmentSensorManager sensors;
#endif

#ifdef DISPLAY_CLASS
  DISPLAY_CLASS display;
  MomentaryButton user_btn(PIN_USER_BTN, 1000, true, true);
#endif

bool radio_init() {
  rtc_clock.begin(Wire);
  
  return radio.std_init(&SPI);
}

mesh::LocalIdentity radio_new_identity() {
  RadioNoiseListener rng(radio);
  return mesh::LocalIdentity(&rng);  // create new random identity
}


