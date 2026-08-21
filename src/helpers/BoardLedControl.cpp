#include "BoardLedControl.h"

#ifndef BOARD_LEDS_DEFAULT
#define BOARD_LEDS_DEFAULT 1
#endif

static bool board_leds_enabled = BOARD_LEDS_DEFAULT != 0;

bool meshcoreBoardLedsEnabled() {
  return board_leds_enabled;
}

void meshcoreSetBoardLedsEnabled(bool enabled) {
  board_leds_enabled = enabled;
}
