#include "E213Display.h"

#if MESHCORE_E213_PROFILE_FONTS
#include "Utf8Cyrillic5x7.h"
#endif

#include "../../MeshCore.h"

ColorVal UIColor::window_bkg = DisplayDriver::DARK;
ColorVal UIColor::title_bkg = DisplayDriver::DARK;
ColorVal UIColor::title_txt = DisplayDriver::LIGHT;
ColorVal UIColor::primary_txt = DisplayDriver::LIGHT;
ColorVal UIColor::secondary_txt = DisplayDriver::LIGHT;
ColorVal UIColor::warning_txt = DisplayDriver::YELLOW;
ColorVal UIColor::popup_bkg = DisplayDriver::DARK;
ColorVal UIColor::popup_txt = DisplayDriver::LIGHT;
ColorVal UIColor::corp_blue = DisplayDriver::BLUE;

#ifndef E213_BUSY_TIMEOUT_MILLIS
#define E213_BUSY_TIMEOUT_MILLIS 0
#endif

#if MESHCORE_E213_PROFILE_FONTS
struct E213ProfileFont {
  const char* name;
  uint8_t body_scale;
  uint8_t advance_cols;
  uint8_t line_gap;
  uint8_t weight;
  bool fixed_width;
};

// These are deliberately small renderer profiles over one compact 5x7
// Cyrillic bitmap set.  They avoid the RAM/flash pressure and boot failures
// seen with the old 15-font Wireless Paper experiments.
static const E213ProfileFont e213_profile_fonts[] = {
  {"Стандарт", 1, 6, 3, 0, false},
  {"Четкий",   1, 7, 3, 1, false},
  {"Компакт",  1, 5, 2, 0, false},
  {"Моно",     1, 6, 3, 0, true},
  {"Плотный",  1, 6, 2, 1, true},
};

static const uint8_t E213_PROFILE_FONT_COUNT =
    sizeof(e213_profile_fonts) / sizeof(e213_profile_fonts[0]);

static uint16_t readDisplayCodepoint(const char*& str) {
  const char* start = str;
  uint8_t first = (uint8_t)*start;
  uint16_t cp = meshcoreReadUtf8Codepoint(str);
  if (cp == '?' && first >= 0x80 && str == start + 1) {
    uint16_t cp1251;
    if (meshcoreCp1251Codepoint(first, &cp1251)) return cp1251;
  }
  return cp;
}
#endif

#if E213_BUSY_TIMEOUT_MILLIS > 0
class E213WirelessPaperV11Safe : public EInkDisplay_WirelessPaperV1_1 {
protected:
  void wait() override {
    uint32_t started = millis();
    while (digitalRead(DISP_BUSY) == LOW) {
      if ((uint32_t)(millis() - started) >= E213_BUSY_TIMEOUT_MILLIS) return;
      yield();
    }
  }
};

class E213WirelessPaperV111Safe : public EInkDisplay_WirelessPaperV1_1_1 {
protected:
  void wait() override {
    uint32_t started = millis();
    while (digitalRead(DISP_BUSY) == HIGH) {
      if ((uint32_t)(millis() - started) >= E213_BUSY_TIMEOUT_MILLIS) return;
      yield();
    }
  }
};
#endif

BaseDisplay* E213Display::detectEInk() {
  // Determine the panel controller from BUSY polarity while reset is held.
  pinMode(DISP_RST, OUTPUT);
  digitalWrite(DISP_RST, LOW);
  delay(10);
  pinMode(DISP_BUSY, INPUT);
  bool busyLogic = digitalRead(DISP_BUSY);
  pinMode(DISP_RST, INPUT);

  if (busyLogic == LOW) {
#ifdef VISION_MASTER_E213
    return new EInkDisplay_VisionMasterE213;
#else
#if E213_BUSY_TIMEOUT_MILLIS > 0
    return new E213WirelessPaperV11Safe;
#else
    return new EInkDisplay_WirelessPaperV1_1;
#endif
#endif
  }

#ifdef VISION_MASTER_E213
  return new EInkDisplay_VisionMasterE213V1_1;
#else
#if E213_BUSY_TIMEOUT_MILLIS > 0
  return new E213WirelessPaperV111Safe;
#else
  return new EInkDisplay_WirelessPaperV1_1_1;
#endif
#endif
}

bool E213Display::begin() {
  if (_init) return true;

  powerOn();
  if (display == NULL) display = detectEInk();
  display->begin();
  display->setRotation(3);

  _init = true;
  _isOn = true;
  clear();
  display->fastmodeOn();
  applyTextColor();
  return true;
}

void E213Display::powerOn() {
  if (_periph_power) {
    _periph_power->claim();
  } else {
#ifdef PIN_VEXT_EN
    pinMode(PIN_VEXT_EN, OUTPUT);
#ifdef PIN_VEXT_EN_ACTIVE
    digitalWrite(PIN_VEXT_EN, PIN_VEXT_EN_ACTIVE);
#else
    digitalWrite(PIN_VEXT_EN, LOW);
#endif
#endif
  }
  delay(50);
}

void E213Display::powerOff() {
  if (_periph_power) {
    _periph_power->release();
  } else {
#ifdef PIN_VEXT_EN
#ifdef PIN_VEXT_EN_ACTIVE
    digitalWrite(PIN_VEXT_EN, !PIN_VEXT_EN_ACTIVE);
#else
    digitalWrite(PIN_VEXT_EN, HIGH);
#endif
#endif
  }
}

void E213Display::turnOn() {
  if (!_init) {
    begin();
  } else if (!_isOn) {
    powerOn();
    display->fastmodeOn();
  }
  _isOn = true;
}

void E213Display::turnOff() {
  if (_isOn) {
    powerOff();
    _isOn = false;
  }
}

void E213Display::clear() {
  if (display) display->clear();
}

void E213Display::startFrame(ColorVal bkg) {
  display_crc.reset();
  display_crc.update<ColorVal>(bkg);
#if MESHCORE_E213_PROFILE_FONTS
  display_crc.update<uint8_t>(_ui_font);
  _bold_text = false;
#endif

  // UI color semantics are OLED-like: DARK is the background, all other
  // roles are foreground.  Map those roles to paper white/black here.
  _curr_color = BLACK;
  applyTextColor();
  display->fillRect(0, 0, width(), height(), bkg == DisplayDriver::DARK ? WHITE : BLACK);
}

void E213Display::setTextSize(int sz) {
  if (sz < 1) sz = 1;
  display_crc.update<int>(sz);
#if MESHCORE_E213_PROFILE_FONTS
  _text_size = (uint8_t)sz;
#else
  display->setTextSize(sz);
#endif
}

void E213Display::setBold(bool bold) {
  display_crc.update<uint8_t>(bold ? 1 : 0);
#if MESHCORE_E213_PROFILE_FONTS
  _bold_text = bold;
#else
  (void)bold;
#endif
}

uint8_t E213Display::getTextLineHeight() const {
#if MESHCORE_E213_PROFILE_FONTS
  return fontLineHeight();
#else
  return 11;
#endif
}

void E213Display::setUiFont(uint8_t font_id) {
#if MESHCORE_E213_PROFILE_FONTS
  if (font_id >= E213_PROFILE_FONT_COUNT) font_id = 0;
  _ui_font = font_id;
#else
  (void)font_id;
#endif
}

uint8_t E213Display::getUiFont() const {
#if MESHCORE_E213_PROFILE_FONTS
  return _ui_font;
#else
  return 0;
#endif
}

uint8_t E213Display::getUiFontCount() const {
#if MESHCORE_E213_PROFILE_FONTS
  return E213_PROFILE_FONT_COUNT;
#else
  return 1;
#endif
}

const char* E213Display::getUiFontName(uint8_t font_id) const {
#if MESHCORE_E213_PROFILE_FONTS
  if (font_id >= E213_PROFILE_FONT_COUNT) font_id = 0;
  return e213_profile_fonts[font_id].name;
#else
  (void)font_id;
  return "Стандарт";
#endif
}

void E213Display::applyTextColor() {
  if (display) display->setTextColor(_curr_color);
}

void E213Display::setColor(ColorVal c) {
  display_crc.update<ColorVal>(c);
  _curr_color = (c == DisplayDriver::DARK) ? WHITE : BLACK;
  applyTextColor();
}

void E213Display::setCursor(int x, int y) {
  display_crc.update<int>(x);
  display_crc.update<int>(y);
#if MESHCORE_E213_PROFILE_FONTS
  _cursor_x = x;
  _cursor_y = y;
#endif
  display->setCursor(x, y);
}

#if MESHCORE_E213_PROFILE_FONTS
const E213ProfileFont* E213Display::currentProfile() const {
  uint8_t font_id = _ui_font;
  if (font_id >= E213_PROFILE_FONT_COUNT) font_id = 0;
  return &e213_profile_fonts[font_id];
}

uint8_t E213Display::effectiveProfileScale() const {
  if (_text_size > 1) return _text_size;
  uint8_t scale = currentProfile()->body_scale;
  return scale < 1 ? 1 : scale;
}

const uint8_t* E213Display::profileGlyphForCodepoint(uint16_t codepoint) const {
  if (codepoint == '\t') codepoint = ' ';
  const uint8_t* glyph = meshcoreAsciiGlyph5x7(codepoint);
  if (!glyph) glyph = meshcoreCyrillicGlyph5x7(codepoint);
  if (glyph) return glyph;
  return meshcoreAsciiGlyph5x7('?');
}

uint8_t E213Display::fontLineHeight() const {
  const E213ProfileFont* profile = currentProfile();
  uint8_t scale = effectiveProfileScale();
  uint8_t gap = (_text_size > 1) ? 2 : profile->line_gap;
  return (8 + gap) * scale;
}

uint16_t E213Display::codepointWidth(uint16_t codepoint) const {
  if (codepoint == '\r' || codepoint == '\n') return 0;
  const E213ProfileFont* profile = currentProfile();
  uint8_t scale = effectiveProfileScale();
  uint8_t advance_cols = profile->advance_cols;
  if (codepoint == '\t') advance_cols *= 2;
  if (codepoint == ' ') advance_cols = profile->fixed_width ? profile->advance_cols : 4;
  uint16_t extra = (_bold_text || profile->weight) ? 1 : 0;
  return advance_cols * scale + extra;
}

void E213Display::drawCodepoint(uint16_t codepoint) {
  if (codepoint == '\r') return;
  if (codepoint == '\n') {
    setCursor(0, _cursor_y + fontLineHeight());
    return;
  }

  const E213ProfileFont* profile = currentProfile();
  const uint8_t* glyph = profileGlyphForCodepoint(codepoint);
  if (!glyph) return;

  uint8_t scale = effectiveProfileScale();
  uint8_t weight = (_bold_text || profile->weight) ? 1 : 0;
  int left = _cursor_x;
  int top = _cursor_y;

  if (codepoint != ' ') {
    for (int col = 0; col < 5; col++) {
      uint8_t bits = glyph[col];
      for (int row = 0; row < 8; row++) {
        if (bits & (1 << row)) {
          fillRectClipped(left + col * scale, top + row * scale,
                          scale + weight, scale, _curr_color);
        }
      }
    }
  }

  _cursor_x += codepointWidth(codepoint);
  display->setCursor(_cursor_x, _cursor_y);
}
#endif

void E213Display::print(const char* str) {
  if (str == NULL) return;
  display_crc.update<char>(str, strlen(str));
#if MESHCORE_E213_PROFILE_FONTS
  uint8_t glyphs_since_yield = 0;
  while (*str) {
    drawCodepoint(readDisplayCodepoint(str));
    if (++glyphs_since_yield >= 12) {
      glyphs_since_yield = 0;
      yield();
    }
  }
#else
  display->print(str);
#endif
}

void E213Display::printWordWrap(const char* str, int max_width) {
#if MESHCORE_E213_PROFILE_FONTS
  if (str == NULL || max_width <= 0) return;
  display_crc.update<char>(str, strlen(str));
  display_crc.update<int>(max_width);
  int left = _cursor_x;
  int right = left + max_width;
  uint8_t glyphs_since_yield = 0;
  while (*str) {
    uint16_t cp = readDisplayCodepoint(str);
    uint16_t glyph_width = codepointWidth(cp);
    if (cp == '\n') {
      drawCodepoint(cp);
      setCursor(left, _cursor_y);
      continue;
    }
    if (glyph_width > 0 && _cursor_x + glyph_width > right && _cursor_x > left) {
      setCursor(left, _cursor_y + fontLineHeight());
      if (cp == ' ') continue;
    }
    drawCodepoint(cp);
    if (++glyphs_since_yield >= 12) {
      glyphs_since_yield = 0;
      yield();
    }
  }
#else
  (void)max_width;
  print(str);
#endif
}

void E213Display::translateUTF8ToBlocks(char* dest, const char* src, size_t dest_size) {
#if MESHCORE_E213_PROFILE_FONTS
  meshcoreCopySupportedUtf8(dest, src, dest_size);
#else
  DisplayDriver::translateUTF8ToBlocks(dest, src, dest_size);
#endif
}

void E213Display::fillRectClipped(int x, int y, int w, int h, uint16_t color) {
  if (w <= 0 || h <= 0 || x >= width() || y >= height()) return;
  if (x < 0) {
    w += x;
    x = 0;
  }
  if (y < 0) {
    h += y;
    y = 0;
  }
  if (w <= 0 || h <= 0) return;
  if (x + w > width()) w = width() - x;
  if (y + h > height()) h = height() - y;
  if (w <= 0 || h <= 0) return;
  display->fillRect(x, y, w, h, color);
}

void E213Display::drawPixelClipped(int x, int y, uint16_t color) {
  if (x < 0 || y < 0 || x >= width() || y >= height()) return;
  display->drawPixel(x, y, color);
}

void E213Display::fillRect(int x, int y, int w, int h) {
  display_crc.update<int>(x);
  display_crc.update<int>(y);
  display_crc.update<int>(w);
  display_crc.update<int>(h);
  fillRectClipped(x, y, w, h, _curr_color);
}

void E213Display::drawRect(int x, int y, int w, int h) {
  display_crc.update<int>(x);
  display_crc.update<int>(y);
  display_crc.update<int>(w);
  display_crc.update<int>(h);
  if (w <= 0 || h <= 0) return;
  fillRectClipped(x, y, w, 1, _curr_color);
  fillRectClipped(x, y + h - 1, w, 1, _curr_color);
  fillRectClipped(x, y, 1, h, _curr_color);
  fillRectClipped(x + w - 1, y, 1, h, _curr_color);
}

void E213Display::drawXbm(int x, int y, const uint8_t* bits, int w, int h) {
  if (bits == NULL || w <= 0 || h <= 0) return;
  display_crc.update<int>(x);
  display_crc.update<int>(y);
  display_crc.update<int>(w);
  display_crc.update<int>(h);
  uint16_t widthInBytes = (w + 7) / 8;
  display_crc.update<uint8_t>(bits, widthInBytes * h);

  for (int by = 0; by < h; by++) {
    for (int bx = 0; bx < w; bx++) {
      uint16_t byteOffset = (by * widthInBytes) + (bx / 8);
      uint8_t bitMask = 0x80 >> (bx & 7);
      if (bits[byteOffset] & bitMask) {
        drawPixelClipped(x + bx, y + by, _curr_color);
      }
    }
  }
}

uint16_t E213Display::getTextWidth(const char* str) {
  if (str == NULL) return 0;
#if MESHCORE_E213_PROFILE_FONTS
  uint16_t width_now = 0;
  uint16_t max_width = 0;
  while (*str) {
    uint16_t cp = readDisplayCodepoint(str);
    if (cp == '\n') {
      if (width_now > max_width) max_width = width_now;
      width_now = 0;
    } else {
      width_now += codepointWidth(cp);
    }
  }
  return width_now > max_width ? width_now : max_width;
#else
  int16_t x1, y1;
  uint16_t w, h;
  display->getTextBounds(str, 0, 0, &x1, &y1, &w, &h);
  return w;
#endif
}

void E213Display::endFrame() {
  uint32_t crc = display_crc.finalize();
  if (crc == last_display_crc_value) return;

  yield();
#if E213_FULL_REFRESH_EVERY > 0
  _partial_refresh_count++;
  if (_partial_refresh_count >= E213_FULL_REFRESH_EVERY) {
    display->fastmodeOff();
    display->update();
    display->fastmodeOn(false);
    _partial_refresh_count = 0;
  } else {
    display->update();
  }
#else
  display->update();
#endif
  yield();
  last_display_crc_value = crc;
}
