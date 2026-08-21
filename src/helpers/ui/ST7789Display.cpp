#ifdef ST7789

#include "ST7789Display.h"
#include "EmbeddedBitmapFonts.h"
#include "Utf8Cyrillic5x7.h"

#ifndef X_OFFSET
#define X_OFFSET 0  // No offset needed for landscape
#endif

#ifndef Y_OFFSET
#define Y_OFFSET 1  // Vertical offset to prevent top row cutoff
#endif

#ifdef HELTEC_VISION_MASTER_T190
  #define SCALE_X  2.5f        // 320 / 128
  #define SCALE_Y  2.65625f    // 170 / 64
#else
  #define SCALE_X  1.875f      // 240 / 128
  #define SCALE_Y  2.109375f   // 135 / 64
#endif

#ifdef DISPLAY_SCALE_X
  #undef SCALE_X
  #define SCALE_X DISPLAY_SCALE_X
#endif

#ifdef DISPLAY_SCALE_Y
  #undef SCALE_Y
  #define SCALE_Y DISPLAY_SCALE_Y
#endif

// PowerSaving-v17 semantic palette.  SmartUI themes still select the actual
// foreground/background colours used by the monochrome framebuffer.
ColorVal UIColor::window_bkg = OLEDDISPLAY_COLOR::BLACK;
ColorVal UIColor::title_bkg = OLEDDISPLAY_COLOR::BLACK;
ColorVal UIColor::title_txt = OLEDDISPLAY_COLOR::WHITE;
ColorVal UIColor::primary_txt = OLEDDISPLAY_COLOR::WHITE;
ColorVal UIColor::secondary_txt = OLEDDISPLAY_COLOR::WHITE;
ColorVal UIColor::warning_txt = OLEDDISPLAY_COLOR::WHITE;
ColorVal UIColor::popup_bkg = OLEDDISPLAY_COLOR::BLACK;
ColorVal UIColor::popup_txt = OLEDDISPLAY_COLOR::WHITE;
ColorVal UIColor::corp_blue = OLEDDISPLAY_COLOR::WHITE;

static int scaleXBoundary(int x) {
  return (int)(x * SCALE_X) + X_OFFSET;
}

static int scaleYBoundary(int y) {
  return (int)(y * SCALE_Y) + Y_OFFSET;
}

static uint16_t physicalToLogicalX(int px) {
  if (px <= 0) return 0;
  int logical = (int)((float)px / SCALE_X + 0.999f);
  return logical < 1 ? 1 : (uint16_t)logical;
}

static uint8_t physicalToLogicalY(int px) {
  if (px <= 0) return 0;
  int logical = (int)((float)px / SCALE_Y + 0.999f);
  return logical < 1 ? 1 : (uint8_t)logical;
}

static const uint16_t ST7789_THEME_FG[] = {
  ST77XX_WHITE,   // standard
  ST77XX_CYAN,    // cyan
  ST77XX_YELLOW,  // amber
  0x2104,         // graphite on warm paper
  ST77XX_RED,     // red
  0xFBE0,         // strong orange
  0x87F0          // green screen
};

static const uint16_t ST7789_THEME_BG[] = {
  ST77XX_BLACK,   // standard
  ST77XX_BLACK,   // cyan
  0x0008,         // deep night blue
  0xFFDE,         // warm paper
  ST77XX_BLACK,   // red
  0x1000,         // strong orange
  0x0020          // green screen
};

static const char* const ST7789_THEME_NAMES[] = {
  "Стандарт",
  "Циан",
  "Янтарь",
  "Бумага",
  "Красный",
  "Рыжий",
  "Зеленый"
};

struct ST7789FontProfile {
  uint8_t body_font_id;
  uint8_t clock_font_id;
  const char* name;
};

static const ST7789FontProfile ST7789_FONT_PROFILES[] = {
  {0, 15, "Roboto L"},
  {1, 15, "Noto L"},
  {2, 15, "OpenSans L"},
  {3, 15, "PT Narrow L"},
  {4, 15, "Oswald L"},
  {5, 15, "Roboto XL"},
  {7, 15, "OpenSans XL"},
  {9, 15, "Oswald XL"},
  {11, 15, "Noto XXL"},
  {13, 15, "PT Narrow XXL"},
};

static uint8_t st7789FontProfileCount() {
  return sizeof(ST7789_FONT_PROFILES) / sizeof(ST7789_FONT_PROFILES[0]);
}

static const ST7789FontProfile& st7789FontProfile(uint8_t profile_id) {
  if (profile_id >= st7789FontProfileCount()) profile_id = 0;
  return ST7789_FONT_PROFILES[profile_id];
}

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

bool ST7789Display::begin() {
  if(!_isOn) {
    pinMode(PIN_TFT_VDD_CTL, OUTPUT);
    pinMode(PIN_TFT_LEDA_CTL, OUTPUT);
    digitalWrite(PIN_TFT_VDD_CTL, LOW);
  #ifdef PIN_TFT_LEDA_CTL_ACTIVE
    digitalWrite(PIN_TFT_LEDA_CTL, PIN_TFT_LEDA_CTL_ACTIVE);
  #else
    digitalWrite(PIN_TFT_LEDA_CTL, LOW);
  #endif
    digitalWrite(PIN_TFT_RST, HIGH);

    display.init();
    display.landscapeScreen();
  #ifdef DISPLAY_FLIP_VERTICALLY
    display.flipScreenVertically();
  #endif
    display.displayOn();
    applyTheme();
    setCursor(0,0);

    _isOn = true;
  }
  return true;
}

void ST7789Display::turnOn() {
  if (!_isOn) {
    // Restore power to the display but keep backlight off
    digitalWrite(PIN_TFT_VDD_CTL, LOW);
    digitalWrite(PIN_TFT_RST, HIGH);
    
    // Re-initialize the display
    display.init();
    display.displayOn();
  #ifdef DISPLAY_FLIP_VERTICALLY
    display.flipScreenVertically();
  #endif
    applyTheme();
    delay(20);

    // Now turn on the backlight
  #ifdef PIN_TFT_LEDA_CTL_ACTIVE
    digitalWrite(PIN_TFT_LEDA_CTL, PIN_TFT_LEDA_CTL_ACTIVE);
  #else
    digitalWrite(PIN_TFT_LEDA_CTL, LOW);
  #endif    
    _isOn = true;
  }
}

void ST7789Display::turnOff() {
  digitalWrite(PIN_TFT_VDD_CTL, HIGH);
#ifdef PIN_TFT_LEDA_CTL_ACTIVE
  digitalWrite(PIN_TFT_LEDA_CTL, !PIN_TFT_LEDA_CTL_ACTIVE);
#else
  digitalWrite(PIN_TFT_LEDA_CTL, HIGH);
#endif
  digitalWrite(PIN_TFT_RST, LOW);
  _isOn = false;
}

void ST7789Display::clear() {
  display.clear();
}

void ST7789Display::applyTheme() {
  uint8_t count = sizeof(ST7789_THEME_FG) / sizeof(ST7789_THEME_FG[0]);
  if (_ui_theme >= count) _ui_theme = 0;
  uint16_t next_fg = ST7789_THEME_FG[_ui_theme];
  uint16_t next_bg = ST7789_THEME_BG[_ui_theme];
  bool changed = next_fg != _theme_fg || next_bg != _theme_bg;
  _theme_fg = next_fg;
  _theme_bg = next_bg;
  display.setRGB(_theme_fg);
  display.setBackgroundRGB(_theme_bg);
  if (changed) display.forceFullRefresh();
}

void ST7789Display::startFrame(ColorVal bkg) {
  (void)bkg;
  applyTheme();
  display.clear();
  _color = _theme_fg;
  display.setColor(OLEDDISPLAY_COLOR::WHITE);
  _text_size = 1;
  _bold_text = false;
}

void ST7789Display::setTextSize(int sz) {
  if (sz < 1) sz = 1;
  _text_size = (uint8_t)sz;
}

void ST7789Display::setBold(bool bold) {
  _bold_text = bold;
}

uint8_t ST7789Display::fontRenderScale() const {
  return _text_size > 1 ? 1 : _text_size;
}

const MeshcoreBitmapFont* ST7789Display::currentFont() const {
  const ST7789FontProfile& profile = st7789FontProfile(_ui_font);
  return meshcoreGetSt7789Font(_text_size > 1 ? profile.clock_font_id : profile.body_font_id);
}

const MeshcoreBitmapGlyph* ST7789Display::glyphForCodepoint(uint16_t codepoint) const {
  const MeshcoreBitmapFont* font = currentFont();
  const MeshcoreBitmapGlyph* glyph = meshcoreFindGlyph(font, codepoint == '\t' ? ' ' : codepoint);
  if (glyph) return glyph;
  return meshcoreFindGlyph(font, '?');
}

uint8_t ST7789Display::fontLineHeight() const {
  return physicalToLogicalY(currentFont()->height * fontRenderScale());
}

void ST7789Display::setUiFont(uint8_t font_id) {
  if (font_id >= getUiFontCount()) font_id = 0;
  _ui_font = font_id;
}

const char* ST7789Display::getUiFontName(uint8_t font_id) const {
  if (font_id >= getUiFontCount()) font_id = 0;
  return st7789FontProfile(font_id).name;
}

uint8_t ST7789Display::getUiFontCount() const {
  return st7789FontProfileCount();
}

void ST7789Display::setUiTheme(uint8_t theme_id) {
  if (theme_id >= getUiThemeCount()) theme_id = 0;
  _ui_theme = theme_id;
  applyTheme();
}

const char* ST7789Display::getUiThemeName(uint8_t theme_id) const {
  if (theme_id >= getUiThemeCount()) theme_id = 0;
  return ST7789_THEME_NAMES[theme_id];
}

void ST7789Display::setColor(ColorVal c) {
  switch (c) {
    case DisplayDriver::DARK :
      display.setColor(OLEDDISPLAY_COLOR::BLACK);
      break;
    default:
      display.setColor(OLEDDISPLAY_COLOR::WHITE);
      break;
  }
  _color = (c == DisplayDriver::DARK) ? _theme_bg : _theme_fg;
}

void ST7789Display::setCursor(int x, int y) {
  _logical_x = x;
  _logical_y = y;
  _x = x*SCALE_X + X_OFFSET;
  _y = y*SCALE_Y + Y_OFFSET;
}

uint16_t ST7789Display::codepointWidth(uint16_t codepoint) {
  if (codepoint == '\r' || codepoint == '\n') return 0;
  const MeshcoreBitmapGlyph* glyph = glyphForCodepoint(codepoint);
  if (!glyph) return 0;
  uint8_t scale = fontRenderScale();
  uint16_t extra = (_bold_text && scale == 1) ? 1 : 0;
  return physicalToLogicalX(glyph->xAdvance * scale + extra);
}

void ST7789Display::drawCodepoint(uint16_t codepoint) {
  if (codepoint == '\r') return;
  if (codepoint == '\n') {
    setCursor(0, _logical_y + fontLineHeight());
    return;
  }

  const MeshcoreBitmapFont* font = currentFont();
  const MeshcoreBitmapGlyph* glyph = glyphForCodepoint(codepoint);
  if (!glyph) return;
  uint8_t scale = fontRenderScale();

  int baseline = _y + font->ascent * scale;
  int top = baseline - (glyph->yOffset + glyph->height) * scale;
  int left = _x + glyph->xOffset * scale;
  bool bold = _bold_text && scale == 1;

  for (int row = 0; row < glyph->height; row++) {
    int run_start = -1;
    for (int col = 0; col <= glyph->width; col++) {
      bool set = false;
      if (col < glyph->width) {
        uint8_t bits = font->bitmap[glyph->offset + row * glyph->rowBytes + col / 8];
        set = (bits & (1 << (col & 7))) != 0;
      }
      if (set) {
        if (run_start < 0) run_start = col;
      } else if (run_start >= 0) {
        int px = left + run_start * scale;
        int py = top + row * scale;
        int run_w = (col - run_start) * scale + (bold ? 1 : 0);
        display.fillRect(px, py, run_w, scale);
        run_start = -1;
      }
    }
  }
  uint16_t advance_px = glyph->xAdvance * scale + (bold ? 1 : 0);
  _x += advance_px;
  _logical_x += physicalToLogicalX(advance_px);
}

void ST7789Display::print(const char* str) {
  if (str == NULL) return;
  while (*str) {
    drawCodepoint(readDisplayCodepoint(str));
  }
}

void ST7789Display::printWordWrap(const char* str, int max_width) {
  if (str == NULL) return;
  int left = _logical_x;
  int right = left + max_width;
  while (*str) {
    uint16_t cp = readDisplayCodepoint(str);
    uint16_t w = codepointWidth(cp);
    if (cp == '\n') {
      drawCodepoint(cp);
      setCursor(left, _logical_y);
      continue;
    }
    if (w > 0 && _logical_x + w > right && _logical_x > left) {
      setCursor(left, _logical_y + fontLineHeight());
      if (cp == ' ') continue;
    }
    drawCodepoint(cp);
  }
}

void ST7789Display::translateUTF8ToBlocks(char* dest, const char* src, size_t dest_size) {
  meshcoreCopySupportedUtf8(dest, src, dest_size);
}

void ST7789Display::fillRect(int x, int y, int w, int h) {
  if (w <= 0 || h <= 0) return;
  int x1 = scaleXBoundary(x);
  int y1 = scaleYBoundary(y);
  int x2 = scaleXBoundary(x + w);
  int y2 = scaleYBoundary(y + h);
  int sw = x2 - x1;
  int sh = y2 - y1;
  if (sw < 1) sw = 1;
  if (sh < 1) sh = 1;
  display.fillRect(x1, y1, sw, sh);
}

void ST7789Display::drawRect(int x, int y, int w, int h) {
  if (w <= 0 || h <= 0) return;
  int x1 = scaleXBoundary(x);
  int y1 = scaleYBoundary(y);
  int x2 = scaleXBoundary(x + w);
  int y2 = scaleYBoundary(y + h);
  int sw = x2 - x1;
  int sh = y2 - y1;
  if (sw < 1) sw = 1;
  if (sh < 1) sh = 1;
  display.drawRect(x1, y1, sw, sh);
}

void ST7789Display::drawXbm(int x, int y, const uint8_t* bits, int w, int h) {
  // Calculate the base position in display coordinates
  uint16_t startX = x * SCALE_X + X_OFFSET;
  uint16_t startY = y * SCALE_Y + Y_OFFSET;
  
  // Width in bytes for bitmap processing
  uint16_t widthInBytes = (w + 7) / 8;
  
  // Process the bitmap row by row
  for (uint16_t by = 0; by < h; by++) {
    // Calculate the target y-coordinates for this logical row
    int y1 = startY + (int)(by * SCALE_Y);
    int y2 = startY + (int)((by + 1) * SCALE_Y);
    int block_h = y2 - y1;
    
    // Scan across the row bit by bit
    for (uint16_t bx = 0; bx < w; bx++) {
      // Calculate the target x-coordinates for this logical column
      int x1 = startX + (int)(bx * SCALE_X);
      int x2 = startX + (int)((bx + 1) * SCALE_X);
      int block_w = x2 - x1;
      
      // Get the current bit
      uint16_t byteOffset = (by * widthInBytes) + (bx / 8);
      uint8_t bitMask = 0x80 >> (bx & 7);
      bool bitSet = pgm_read_byte(bits + byteOffset) & bitMask;
      
      // If the bit is set, draw a block of pixels
      if (bitSet) {
        // Draw the block as a filled rectangle
        display.fillRect(x1, y1, block_w, block_h);
      }
    }
  }
}

uint16_t ST7789Display::getTextWidth(const char* str) {
  if (str == NULL) return 0;
  uint16_t w = 0;
  uint16_t max_w = 0;
  while (*str) {
    uint16_t cp = readDisplayCodepoint(str);
    if (cp == '\n') {
      if (w > max_w) max_w = w;
      w = 0;
    } else {
      w += codepointWidth(cp);
    }
  }
  return w > max_w ? w : max_w;
}

void ST7789Display::endFrame() {
  applyTheme();
  display.display();
}

#endif
