#pragma once

#include "DisplayDriver.h"
#include <Wire.h>
#include <Adafruit_GFX.h>
#define SSD1306_NO_SPLASH
#include <Adafruit_SSD1306.h>
#include <helpers/RefCountedDigitalPin.h>

#ifndef PIN_OLED_RESET
  #define PIN_OLED_RESET        21 // Reset pin # (or -1 if sharing Arduino reset pin)
#endif

#ifndef DISPLAY_ADDRESS
  #define DISPLAY_ADDRESS   0x3C
#endif

class SSD1306Display : public DisplayDriver {
  Adafruit_SSD1306 display;
  bool _isOn;
  uint8_t _color;
  uint8_t _text_size;
  bool _bold_text;
  uint8_t _ui_font;
  RefCountedDigitalPin* _peripher_power;

  bool i2c_probe(TwoWire& wire, uint8_t addr);
  bool useBoldStroke() const;
  bool useLegacyFont() const;
  const struct MeshcoreBitmapFont* currentFont() const;
  const struct MeshcoreBitmapGlyph* glyphForCodepoint(uint16_t codepoint) const;
  uint8_t fontLineHeight() const;
  uint16_t readCodepoint(const char*& str) const;
  uint16_t codepointWidth(uint16_t codepoint) const;
  void drawLegacyCodepoint(uint16_t codepoint);
  void drawCodepoint(uint16_t codepoint);
public:
  SSD1306Display(RefCountedDigitalPin* peripher_power=NULL) : DisplayDriver(128, 64), 
      display(128, 64, &Wire, PIN_OLED_RESET),
      _peripher_power(peripher_power)
  {
    _isOn = false; 
    _text_size = 1;
    _bold_text = false;
    _ui_font = 0;
  }
  bool begin();

  bool isOn() override { return _isOn; }
  void turnOn() override;
  void turnOff() override;
  void clear() override;
  void startFrame(ColorVal bkg = UIColor::window_bkg) override;
  void setTextSize(int sz) override;
  void setBold(bool bold) override;
  uint8_t getTextLineHeight() const override { return fontLineHeight(); }
  void setUiFont(uint8_t font_id) override;
  uint8_t getUiFont() const override { return _ui_font; }
  uint8_t getUiFontCount() const override;
  const char* getUiFontName(uint8_t font_id) const override;
  void setColor(ColorVal c) override;
  void setCursor(int x, int y) override;
  void print(const char* str) override;
  void printWordWrap(const char* str, int max_width) override;
  void fillRect(int x, int y, int w, int h) override;
  void drawRect(int x, int y, int w, int h) override;
  void drawXbm(int x, int y, const uint8_t* bits, int w, int h) override;
  uint16_t getTextWidth(const char* str) override;
  void translateUTF8ToBlocks(char* dest, const char* src, size_t dest_size) override;
  void drawTextEllipsized(int x, int y, int max_width, const char* str) override;
  void endFrame() override;
};
