#pragma once

#include "DisplayDriver.h"
#include <Wire.h>
#include <SPI.h>
#include <Adafruit_GFX.h>
#include "ST7789Spi.h"

class ST7789Display : public DisplayDriver {
  ST7789Spi display;
  bool _isOn;
  uint16_t _color;
  int _x=0, _y=0;
  int _logical_x=0, _logical_y=0;
  uint8_t _text_size=1;
  bool _bold_text=false;
  uint8_t _ui_font=0;
  uint8_t _ui_theme=0;
  uint16_t _theme_fg=0xFFFF;
  uint16_t _theme_bg=0x0000;

  bool i2c_probe(TwoWire& wire, uint8_t addr);
  void applyTheme();
  const struct MeshcoreBitmapFont* currentFont() const;
  const struct MeshcoreBitmapGlyph* glyphForCodepoint(uint16_t codepoint) const;
  uint8_t fontRenderScale() const;
  uint8_t fontLineHeight() const;
  uint16_t codepointWidth(uint16_t codepoint);
  void drawCodepoint(uint16_t codepoint);
public:
#if defined(HELTEC_VISION_MASTER_T190)
  ST7789Display() : DisplayDriver(128, 64), display(&SPI, PIN_TFT_RST, PIN_TFT_DC, PIN_TFT_CS, GEOMETRY_RAWMODE, 320, 170,PIN_TFT_SDA,-1,PIN_TFT_SCL) {_isOn = false;}
#elif defined(THINKNODE_M9)
  ST7789Display() : DisplayDriver(128, 64), display(&SPI, ST7789_RESET, ST7789_RS, ST7789_CS, GEOMETRY_RAWMODE, 320, 240, ST7789_SDA, ST7789_MISO, ST7789_SCK) {_isOn = false;}
#else
  ST7789Display() : DisplayDriver(128, 64), display(&SPI1, PIN_TFT_RST, PIN_TFT_DC, PIN_TFT_CS, GEOMETRY_RAWMODE, 240, 135) {_isOn = false;}
#endif
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
  void setUiTheme(uint8_t theme_id) override;
  uint8_t getUiTheme() const override { return _ui_theme; }
  uint8_t getUiThemeCount() const override { return 7; }
  const char* getUiThemeName(uint8_t theme_id) const override;
  void setColor(ColorVal c) override;
  void setCursor(int x, int y) override;
  void print(const char* str) override;
  void printWordWrap(const char* str, int max_width) override;
  void translateUTF8ToBlocks(char* dest, const char* src, size_t dest_size) override;
  void fillRect(int x, int y, int w, int h) override;
  void drawRect(int x, int y, int w, int h) override;
  void drawXbm(int x, int y, const uint8_t* bits, int w, int h) override;
  uint16_t getTextWidth(const char* str) override;
  void endFrame() override;
};
