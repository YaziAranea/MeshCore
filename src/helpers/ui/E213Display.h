#pragma once

#include "DisplayDriver.h"

#include <SPI.h>
#include <Wire.h>
#include <heltec-eink-modules.h>
#include <CRC32.h>
#include <helpers/RefCountedDigitalPin.h>

#ifndef MESHCORE_E213_PROFILE_FONTS
#define MESHCORE_E213_PROFILE_FONTS 0
#endif

#ifndef E213_FULL_REFRESH_EVERY
#define E213_FULL_REFRESH_EVERY 0
#endif

// Display driver for E213 e-ink display
class E213Display : public DisplayDriver {
  BaseDisplay* display=NULL;
  bool _init = false;
  bool _isOn = false;
  RefCountedDigitalPin* _periph_power;
  CRC32 display_crc;
  uint32_t last_display_crc_value = 0;
#if E213_FULL_REFRESH_EVERY > 0
  uint16_t _partial_refresh_count = 0;
#endif
#if MESHCORE_E213_PROFILE_FONTS
  int _cursor_x = 0;
  int _cursor_y = 0;
  uint8_t _text_size = 1;
  bool _bold_text = false;
  uint8_t _ui_font = 0;
#endif
  uint16_t _curr_color = BLACK;

public:
  E213Display(RefCountedDigitalPin* periph_power = NULL) : DisplayDriver(250, 122), _periph_power(periph_power) {}
  ~E213Display(){
    if(display!=NULL) {
      delete display;
    }
  }
  bool begin();
  bool isOn() override { return _isOn; }
  bool isEink() override { return true; }
  void turnOn() override;
  void turnOff() override;
  void clear() override;
  void startFrame(ColorVal bkg = UIColor::window_bkg) override;
  void setTextSize(int sz) override;
  void setBold(bool bold) override;
  uint8_t getTextLineHeight() const override;
  void setUiFont(uint8_t font_id) override;
  uint8_t getUiFont() const override;
  uint8_t getUiFontCount() const override;
  const char* getUiFontName(uint8_t font_id) const override;
  void setColor(ColorVal c) override;
  void setCursor(int x, int y) override;
  void print(const char *str) override;
  void printWordWrap(const char* str, int max_width) override;
  void translateUTF8ToBlocks(char* dest, const char* src, size_t dest_size) override;
  void fillRect(int x, int y, int w, int h) override;
  void drawRect(int x, int y, int w, int h) override;
  void drawXbm(int x, int y, const uint8_t *bits, int w, int h) override;
  uint16_t getTextWidth(const char *str) override;
  void endFrame() override;

private:
  BaseDisplay* detectEInk();
  void powerOn();
  void powerOff();
#if MESHCORE_E213_PROFILE_FONTS
  const struct E213ProfileFont* currentProfile() const;
  const uint8_t* profileGlyphForCodepoint(uint16_t codepoint) const;
  uint8_t effectiveProfileScale() const;
  uint8_t fontLineHeight() const;
  uint16_t codepointWidth(uint16_t codepoint) const;
  void drawCodepoint(uint16_t codepoint);
#endif
  void applyTextColor();
  void fillRectClipped(int x, int y, int w, int h, uint16_t color);
  void drawPixelClipped(int x, int y, uint16_t color);
};
