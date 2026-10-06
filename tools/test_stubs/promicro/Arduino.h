#pragma once

#include <stdint.h>

#define HIGH 1
#define LOW 0

void analogReadResolution(int resolution);
uint32_t analogRead(uint32_t pin);
uint32_t millis();
int digitalRead(uint32_t pin);
