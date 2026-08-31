#include "SSD1306Display.h"
#if SSD1306_USE_EMBEDDED_FONTS
#include "EmbeddedBitmapFonts.h"
#endif
#include "Utf8Cyrillic5x7.h"

// PowerSaving-v17 semantic palette for monochrome OLEDs.
ColorVal UIColor::window_bkg = SSD1306_BLACK;
ColorVal UIColor::title_bkg = SSD1306_BLACK;
ColorVal UIColor::title_txt = SSD1306_WHITE;
ColorVal UIColor::primary_txt = SSD1306_WHITE;
ColorVal UIColor::secondary_txt = SSD1306_WHITE;
ColorVal UIColor::warning_txt = SSD1306_WHITE;
ColorVal UIColor::popup_bkg = SSD1306_BLACK;
ColorVal UIColor::popup_txt = SSD1306_WHITE;
ColorVal UIColor::corp_blue = SSD1306_WHITE;

#ifndef SSD1306_REINIT_ON_TURNON
  #define SSD1306_REINIT_ON_TURNON 0
#endif

#ifndef SSD1306_REINIT_WIRE_END_ON_TURNON
  #define SSD1306_REINIT_WIRE_END_ON_TURNON 0
#endif

#ifndef SSD1306_REINIT_CLEAR_ON_TURNON
  #define SSD1306_REINIT_CLEAR_ON_TURNON 0
#endif

#ifndef SSD1306_REINIT_DELAY_MS
  #define SSD1306_REINIT_DELAY_MS 0
#endif

#ifndef SSD1306_WAKE_RETRY_COUNT
  #define SSD1306_WAKE_RETRY_COUNT 1
#endif

#ifndef SSD1306_WAKE_RETRY_DELAY_MS
  #define SSD1306_WAKE_RETRY_DELAY_MS 80
#endif

#ifndef SSD1306_I2C_RECOVER_ON_TURNON
  #define SSD1306_I2C_RECOVER_ON_TURNON 0
#endif

#ifndef SSD1306_VALIDATE_ON_TURNON
  #define SSD1306_VALIDATE_ON_TURNON 0
#endif

#ifndef SSD1306_WIRE_TIMEOUT_MS
  #define SSD1306_WIRE_TIMEOUT_MS 0
#endif

#ifndef SSD1306_HARD_RESET_ON_REINIT
  #define SSD1306_HARD_RESET_ON_REINIT 0
#endif

#ifndef SSD1306_HARD_RESET_LOW_MS
  #define SSD1306_HARD_RESET_LOW_MS 10
#endif

#ifndef SSD1306_HARD_RESET_SETTLE_MS
  #define SSD1306_HARD_RESET_SETTLE_MS 20
#endif

#ifndef SSD1306_POWER_SETTLE_MS
  #define SSD1306_POWER_SETTLE_MS 0
#endif

static void ssd1306ApplyWireTimeout() {
#if SSD1306_WIRE_TIMEOUT_MS > 0
  Wire.setTimeOut(SSD1306_WIRE_TIMEOUT_MS);
#endif
}

static void ssd1306BeginWire() {
#if defined(ESP32_PLATFORM) && defined(PIN_BOARD_SDA) && defined(PIN_BOARD_SCL)
#if PIN_BOARD_SDA >= 0 && PIN_BOARD_SCL >= 0
  Wire.begin(PIN_BOARD_SDA, PIN_BOARD_SCL);
#else
  Wire.begin();
#endif
#else
  Wire.begin();
#endif
  ssd1306ApplyWireTimeout();
}

static void ssd1306RecoverI2CBus() {
#if SSD1306_I2C_RECOVER_ON_TURNON && defined(ESP32_PLATFORM) && defined(PIN_BOARD_SDA) && defined(PIN_BOARD_SCL)
#if PIN_BOARD_SDA >= 0 && PIN_BOARD_SCL >= 0
  pinMode(PIN_BOARD_SDA, INPUT_PULLUP);
  pinMode(PIN_BOARD_SCL, INPUT_PULLUP);
  delayMicroseconds(10);

  pinMode(PIN_BOARD_SCL, OUTPUT_OPEN_DRAIN);
  for (uint8_t i = 0; i < 9 && digitalRead(PIN_BOARD_SDA) == LOW; i++) {
    digitalWrite(PIN_BOARD_SCL, LOW);
    delayMicroseconds(6);
    digitalWrite(PIN_BOARD_SCL, HIGH);
    delayMicroseconds(6);
  }

  pinMode(PIN_BOARD_SDA, OUTPUT_OPEN_DRAIN);
  digitalWrite(PIN_BOARD_SDA, LOW);
  delayMicroseconds(6);
  digitalWrite(PIN_BOARD_SCL, HIGH);
  delayMicroseconds(6);
  digitalWrite(PIN_BOARD_SDA, HIGH);
  delayMicroseconds(6);
#endif
#endif
}

static void ssd1306HardResetController() {
#if SSD1306_HARD_RESET_ON_REINIT && defined(PIN_OLED_RESET)
#if PIN_OLED_RESET >= 0
  pinMode(PIN_OLED_RESET, OUTPUT);
  digitalWrite(PIN_OLED_RESET, HIGH);
  delay(1);
  digitalWrite(PIN_OLED_RESET, LOW);
  delay(SSD1306_HARD_RESET_LOW_MS);
  digitalWrite(PIN_OLED_RESET, HIGH);
  delay(SSD1306_HARD_RESET_SETTLE_MS);
#endif
#endif
}

static bool ssd1306UseLegacyFontId(uint8_t font_id) {
#if !SSD1306_USE_EMBEDDED_FONTS
  (void)font_id;
  return true;
#elif SSD1306_COMPACT_STYLE_PROFILE
  return font_id < 5;
#elif defined(HELTEC_LORA_V4_OLED)
  return font_id == 0;
#else
  (void)font_id;
  return false;
#endif
}

#if SSD1306_USE_EMBEDDED_FONTS
static uint8_t ssd1306BitmapFontIndex(uint8_t font_id) {
#if SSD1306_COMPACT_STYLE_PROFILE
  return font_id;
#elif defined(HELTEC_LORA_V4_OLED)
  return font_id > 0 ? font_id - 1 : 0;
#else
  return font_id;
#endif
}
#endif

static const char* const SSD1306_FONT_NAMES[] = {
  "Базовый",
  "Тонкий"
};

#if SSD1306_COMPACT_STYLE_PROFILE
static const char* const SSD1306_V43_PIXEL_FONT_NAMES[] = {
  "Classic 6x8",
  "Air 7x8",
  "Strong 7x8",
  "Narrow 5x8",
  "Dense 6x8"
};

static uint8_t ssd1306LegacyAdvance(uint8_t font_id) {
  switch (font_id) {
    case 1: return 7;  // Air: same glyphs, more tracking.
    case 2: return 7;  // Strong: one-pixel stroke, safe spacing.
    case 3: return 5;  // Narrow: maximum fit, no tracking column.
    case 4: return 6;  // Dense: one-pixel stroke with classic spacing.
    default: return 6; // Classic UI66 spacing.
  }
}

static bool ssd1306LegacyStyleBold(uint8_t font_id) {
  return font_id == 2 || font_id == 4;
}
#else
static uint8_t ssd1306LegacyAdvance(uint8_t font_id) {
  (void)font_id;
  return 6;
}

static bool ssd1306LegacyStyleBold(uint8_t font_id) {
  (void)font_id;
  return false;
}
#endif

static const uint8_t cyrillic_5x7[][5] = {
  {0x7E, 0x11, 0x11, 0x11, 0x7E}, // А
  {0x7F, 0x49, 0x49, 0x49, 0x31}, // Б
  {0x7F, 0x49, 0x49, 0x49, 0x36}, // В
  {0x7F, 0x01, 0x01, 0x01, 0x03}, // Г
  {0x70, 0x2F, 0x21, 0x21, 0x7F}, // Д
  {0x7F, 0x49, 0x49, 0x49, 0x41}, // Е
  {0x63, 0x14, 0x7F, 0x14, 0x63}, // Ж
  {0x41, 0x49, 0x49, 0x49, 0x36}, // З
  {0x7F, 0x20, 0x18, 0x04, 0x7F}, // И
  {0x7F, 0x20, 0x19, 0x04, 0x7F}, // Й
  {0x7F, 0x08, 0x14, 0x22, 0x41}, // К
  {0x60, 0x1C, 0x03, 0x01, 0x7F}, // Л
  {0x7F, 0x02, 0x0C, 0x02, 0x7F}, // М
  {0x7F, 0x08, 0x08, 0x08, 0x7F}, // Н
  {0x3E, 0x41, 0x41, 0x41, 0x3E}, // О
  {0x7F, 0x01, 0x01, 0x01, 0x7F}, // П
  {0x7F, 0x09, 0x09, 0x09, 0x06}, // Р
  {0x3E, 0x41, 0x41, 0x41, 0x22}, // С
  {0x01, 0x01, 0x7F, 0x01, 0x01}, // Т
  {0x47, 0x28, 0x10, 0x08, 0x07}, // У
  {0x1C, 0x22, 0x7F, 0x22, 0x1C}, // Ф
  {0x63, 0x14, 0x08, 0x14, 0x63}, // Х
  {0x7F, 0x40, 0x40, 0x7F, 0x60}, // Ц
  {0x07, 0x08, 0x08, 0x08, 0x7F}, // Ч
  {0x7F, 0x40, 0x7F, 0x40, 0x7F}, // Ш
  {0x7F, 0x40, 0x7F, 0x40, 0xFF}, // Щ
  {0x01, 0x7F, 0x48, 0x48, 0x30}, // Ъ
  {0x7F, 0x48, 0x48, 0x30, 0x7F}, // Ы
  {0x7F, 0x48, 0x48, 0x48, 0x30}, // Ь
  {0x22, 0x41, 0x49, 0x49, 0x3E}, // Э
  {0x7F, 0x08, 0x3E, 0x41, 0x3E}, // Ю
  {0x46, 0x29, 0x19, 0x09, 0x7F}, // Я
};

static const uint8_t* getCyrillicGlyph(uint16_t codepoint) {
  return meshcoreCyrillicGlyph5x7(codepoint);
  if (codepoint == 0x0451) codepoint = 0x0401; // ё -> Ё
  if (codepoint >= 0x0430 && codepoint <= 0x044F) codepoint -= 0x20; // lower -> upper
  if (codepoint == 0x0401) return cyrillic_5x7[5]; // Ё uses Е on 5x7 OLED
  if (codepoint >= 0x0410 && codepoint <= 0x042F) {
    return cyrillic_5x7[codepoint - 0x0410];
  }
  return NULL;
}

bool SSD1306Display::i2c_probe(TwoWire& wire, uint8_t addr) {
  ssd1306ApplyWireTimeout();
  wire.beginTransmission(addr);
  uint8_t error = wire.endTransmission();
  return (error == 0);
}

bool SSD1306Display::begin() {
  bool was_on = _isOn;
  if (!was_on) {
    if (_peripher_power) {
      _peripher_power->claim();
#if SSD1306_POWER_SETTLE_MS > 0
      delay(SSD1306_POWER_SETTLE_MS);
#endif
    }
  }
  ssd1306ApplyWireTimeout();
  bool ok = display.begin(SSD1306_SWITCHCAPVCC, DISPLAY_ADDRESS, true, false) && i2c_probe(Wire, DISPLAY_ADDRESS);
  ssd1306ApplyWireTimeout();
  if (ok) {
    _isOn = true;
  #ifdef DISPLAY_ROTATION
    display.setRotation(DISPLAY_ROTATION);
  #endif
  } else {
    if ((was_on || _peripher_power) && _peripher_power) _peripher_power->release();
    _isOn = false;
  }
  return ok;
}

void SSD1306Display::turnOn() {
  bool was_off = !_isOn;
  bool ready = _isOn;
#if SSD1306_VALIDATE_ON_TURNON
  if (ready && !i2c_probe(Wire, DISPLAY_ADDRESS)) {
    ready = false;
    was_off = true;
    _isOn = false;
  }
#endif
#if SSD1306_REINIT_ON_TURNON
  if (was_off) {
    const uint8_t attempts = SSD1306_WAKE_RETRY_COUNT < 1 ? 1 : SSD1306_WAKE_RETRY_COUNT;
    for (uint8_t attempt = 0; attempt < attempts && !ready; attempt++) {
#if SSD1306_REINIT_WIRE_END_ON_TURNON
      Wire.end();
      delay(2);
#endif
      ssd1306RecoverI2CBus();
      ssd1306BeginWire();
#if SSD1306_HARD_RESET_ON_REINIT
      ssd1306HardResetController();
#endif
#if SSD1306_REINIT_DELAY_MS > 0
      delay(SSD1306_REINIT_DELAY_MS);
#endif
      ready = begin();
      if (!ready && attempt + 1 < attempts) {
        delay(SSD1306_WAKE_RETRY_DELAY_MS);
      }
    }
  }
#else
  if (was_off) {
    ready = begin();
  }
#endif
  if (!ready) return;
  display.ssd1306_command(SSD1306_DISPLAYON);
#if SSD1306_REINIT_CLEAR_ON_TURNON
  if (was_off) {
    display.clearDisplay();
    display.display();
  }
#endif
}

void SSD1306Display::turnOff() {
  display.ssd1306_command(SSD1306_DISPLAYOFF);
  if (_isOn) {
    if (_peripher_power) {
#if PIN_OLED_RESET >= 0
      digitalWrite(PIN_OLED_RESET, LOW);
#endif
      _peripher_power->release();
    }
    _isOn = false;
  }
}

void SSD1306Display::clear() {
  display.clearDisplay();
  display.display();
}

void SSD1306Display::startFrame(ColorVal bkg) {
  display.clearDisplay();  // TODO: apply 'bkg'
  _color = SSD1306_WHITE;
  display.setTextColor(_color);
  display.setTextSize(1);
  _text_size = 1;
  _bold_text = false;
  display.cp437(true);         // Use full 256 char 'Code Page 437' font
}

void SSD1306Display::setTextSize(int sz) {
  if (sz < 1) sz = 1;
  _text_size = (uint8_t)sz;
  display.setTextSize(sz);
}

void SSD1306Display::setBold(bool bold) {
  _bold_text = bold;
}

bool SSD1306Display::useBoldStroke() const {
  return _bold_text && _text_size == 1 && useLegacyFont();
}

bool SSD1306Display::useLegacyFont() const {
  return ssd1306UseLegacyFontId(_ui_font);
}

#if SSD1306_USE_EMBEDDED_FONTS
const MeshcoreBitmapFont* SSD1306Display::currentFont() const {
  return meshcoreGetSmallFont(ssd1306BitmapFontIndex(_ui_font));
}

const MeshcoreBitmapGlyph* SSD1306Display::glyphForCodepoint(uint16_t codepoint) const {
  const MeshcoreBitmapFont* font = currentFont();
  const MeshcoreBitmapGlyph* glyph = meshcoreFindGlyph(font, codepoint == '\t' ? ' ' : codepoint);
  if (glyph) return glyph;
  return meshcoreFindGlyph(font, '?');
}
#endif

uint8_t SSD1306Display::fontLineHeight() const {
#if SSD1306_USE_EMBEDDED_FONTS
  if (!useLegacyFont()) return currentFont()->height * _text_size;
#endif
  return 8 * _text_size;
}

void SSD1306Display::setUiFont(uint8_t font_id) {
  if (font_id >= getUiFontCount()) font_id = 0;
  _ui_font = font_id;
}

uint8_t SSD1306Display::getUiFontCount() const {
#if SSD1306_COMPACT_STYLE_PROFILE
  return 5;
#elif defined(HELTEC_LORA_V4_OLED)
  return MESHCORE_SMALL_FONT_COUNT + 1;
#else
  return MESHCORE_SMALL_FONT_COUNT;
#endif
}

const char* SSD1306Display::getUiFontName(uint8_t font_id) const {
  if (font_id >= getUiFontCount()) font_id = 0;
#if SSD1306_COMPACT_STYLE_PROFILE
  return SSD1306_V43_PIXEL_FONT_NAMES[font_id];
#else
  if (ssd1306UseLegacyFontId(font_id)) return "V4 6x8";
  return meshcoreGetSmallFont(ssd1306BitmapFontIndex(font_id))->name;
#endif
}

void SSD1306Display::setColor(ColorVal c) {
  _color = (c != 0) ? SSD1306_WHITE : SSD1306_BLACK;
  display.setTextColor(_color);
}

void SSD1306Display::setCursor(int x, int y) {
  display.setCursor(x, y);
}

uint16_t SSD1306Display::readCodepoint(const char*& str) const {
  const char* start = str;
  uint8_t first = (uint8_t)*start;
  uint16_t cp = meshcoreReadUtf8Codepoint(str);
  if (cp == '?' && first >= 0x80 && str == start + 1) {
    uint16_t cp1251;
    if (meshcoreCp1251Codepoint(first, &cp1251)) return cp1251;
  }
  return cp;
}

uint16_t SSD1306Display::codepointWidth(uint16_t codepoint) const {
  if (codepoint == '\r') return 0;
  if (codepoint == '\n') return 0;
  if (useLegacyFont()) {
    uint8_t advance = ssd1306LegacyAdvance(_ui_font);
    bool bold = (ssd1306LegacyStyleBold(_ui_font) || _bold_text) && _text_size == 1;
    if (bold && advance < 6) advance = 6;
    if (bold && advance < 7 && _ui_font != 4) advance = 7;
    return advance * _text_size;
  }
#if SSD1306_USE_EMBEDDED_FONTS
  const MeshcoreBitmapGlyph* glyph = glyphForCodepoint(codepoint);
  if (!glyph) return 0;
  uint16_t extra = (_bold_text && _text_size == 1) ? 1 : 0;
  return glyph->xAdvance * _text_size + extra;
#else
  return 0; // All font IDs are handled by the legacy path in compact builds.
#endif
}

void SSD1306Display::drawLegacyCodepoint(uint16_t codepoint) {
  if (codepoint == '\r') return;
  if (codepoint == '\n') {
    display.setCursor(0, display.getCursorY() + fontLineHeight());
    return;
  }

  const uint8_t* glyph = meshcoreAsciiGlyph5x7(codepoint);
  if (glyph == NULL) glyph = getCyrillicGlyph(codepoint);
  if (glyph == NULL) glyph = meshcoreAsciiGlyph5x7('?');
  if (glyph == NULL) return;

  int16_t x = display.getCursorX();
  int16_t y = display.getCursorY();
  bool bold = (ssd1306LegacyStyleBold(_ui_font) || _bold_text) && _text_size == 1;

  for (int col = 0; col < 5; col++) {
    uint8_t bits = glyph[col];
    for (int row = 0; row < 8; row++) {
      if (bits & (1 << row)) {
        int px = x + col * _text_size;
        int py = y + row * _text_size;
        display.fillRect(px, py, _text_size, _text_size, _color);
        if (bold) display.fillRect(px + 1, py, _text_size, _text_size, _color);
      }
    }
  }

  display.setCursor(x + codepointWidth(codepoint), y);
}

void SSD1306Display::drawCodepoint(uint16_t codepoint) {
  if (useLegacyFont()) {
    drawLegacyCodepoint(codepoint);
    return;
  }

#if SSD1306_USE_EMBEDDED_FONTS
  if (codepoint == '\r') return;
  if (codepoint == '\n') {
    display.setCursor(0, display.getCursorY() + fontLineHeight());
    return;
  }

  const MeshcoreBitmapFont* font = currentFont();
  const MeshcoreBitmapGlyph* glyph = glyphForCodepoint(codepoint);
  if (!glyph) return;

  int16_t x = display.getCursorX();
  int16_t y = display.getCursorY();
  int baseline = y + font->ascent * _text_size;
  int top = baseline - (glyph->yOffset + glyph->height) * _text_size;
  int left = x + glyph->xOffset * _text_size;
  bool bold = _bold_text && _text_size == 1;

  for (int row = 0; row < glyph->height; row++) {
    for (int col = 0; col < glyph->width; col++) {
      uint8_t bits = font->bitmap[glyph->offset + row * glyph->rowBytes + col / 8];
      if (bits & (1 << (col & 7))) {
        int px = left + col * _text_size;
        int py = top + row * _text_size;
        display.fillRect(px, py, _text_size, _text_size, _color);
        if (bold) {
          display.fillRect(px + 1, py, _text_size, _text_size, _color);
        }
      }
    }
  }
  display.setCursor(x + codepointWidth(codepoint), y);
#endif
}

void SSD1306Display::print(const char* str) {
  while (str && *str) {
    drawCodepoint(readCodepoint(str));
  }
}

void SSD1306Display::printWordWrap(const char* str, int max_width) {
  if (str == NULL) return;
  int16_t left = display.getCursorX();
  int16_t right = left + max_width;
  while (*str) {
    const char* before = str;
    uint16_t cp = readCodepoint(str);
    uint16_t w = codepointWidth(cp);
    if (cp == '\n') {
      drawCodepoint(cp);
      display.setCursor(left, display.getCursorY());
      continue;
    }
    if (w > 0 && display.getCursorX() + w > right && display.getCursorX() > left) {
      display.setCursor(left, display.getCursorY() + fontLineHeight());
      if (cp == ' ') continue;
    }
    (void)before;
    drawCodepoint(cp);
  }
}

void SSD1306Display::fillRect(int x, int y, int w, int h) {
  display.fillRect(x, y, w, h, _color);
}

void SSD1306Display::drawRect(int x, int y, int w, int h) {
  display.drawRect(x, y, w, h, _color);
}

void SSD1306Display::drawXbm(int x, int y, const uint8_t* bits, int w, int h) {
  display.drawBitmap(x, y, bits, w, h, SSD1306_WHITE);
}

uint16_t SSD1306Display::getTextWidth(const char* str) {
  if (str == NULL) return 0;
  uint16_t w = 0;
  uint16_t max_w = 0;
  while (*str) {
    uint16_t cp = readCodepoint(str);
    if (cp == '\n') {
      if (w > max_w) max_w = w;
      w = 0;
    } else {
      w += codepointWidth(cp);
    }
  }
  if (w > max_w) max_w = w;
  return max_w;
}

void SSD1306Display::translateUTF8ToBlocks(char* dest, const char* src, size_t dest_size) {
  meshcoreCopySupportedUtf8(dest, src, dest_size);
  return;
  if (dest_size == 0) return;
  size_t j = 0;
  while (src && *src && j < dest_size - 1) {
    const char* start = src;
    uint16_t cp = readCodepoint(src);
    size_t len = src - start;
    bool supported = (cp >= 32 && cp <= 126) || cp == '\n' || cp == '\r' || getCyrillicGlyph(cp) != NULL;
    if (!supported) {
      dest[j++] = '?';
      continue;
    }
    if (j + len >= dest_size) break;
    memcpy(&dest[j], start, len);
    j += len;
  }
  dest[j] = 0;
}

void SSD1306Display::drawTextEllipsized(int x, int y, int max_width, const char* str) {
  if (str == NULL) return;
  if (getTextWidth(str) <= max_width) {
    setCursor(x, y);
    print(str);
    return;
  }

  const char* ellipsis = "...";
  int ellipsis_width = getTextWidth(ellipsis);
  if (max_width <= ellipsis_width) {
    setCursor(x, y);
    print(ellipsis);
    return;
  }

  char temp[256];
  size_t out_len = 0;
  uint16_t width = 0;
  const char* p = str;
  while (*p && out_len < sizeof(temp) - 1) {
    const char* start = p;
    uint16_t cp = readCodepoint(p);
    size_t len = p - start;
    uint16_t next_width = width + codepointWidth(cp);
    if (next_width + ellipsis_width > max_width || out_len + len >= sizeof(temp) - 4) break;
    memcpy(&temp[out_len], start, len);
    out_len += len;
    width = next_width;
  }
  temp[out_len] = 0;
  strcat(temp, ellipsis);

  setCursor(x, y);
  print(temp);
}

void SSD1306Display::endFrame() {
  display.display();
}
