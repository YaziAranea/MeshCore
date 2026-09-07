#pragma once

#include "EmbeddedBitmapFonts.h"

struct MeshcoreTextInk {
  int16_t top;
  uint8_t height;
};

// Generated glyphs contain full line-height blank padding. Bounding-box
// metadata alone is NOT the visible ink. Read the same bitmap as the driver.
static inline MeshcoreTextInk meshcoreBitmapCapitalInk(const MeshcoreBitmapFont* font) {
  const MeshcoreBitmapGlyph* glyph = meshcoreFindGlyph(font, 'H');
  if (!glyph) return {0, font->height};
  int first = glyph->height;
  int last = -1;
  for (int y = 0; y < glyph->height; ++y) {
    for (int x = 0; x < glyph->width; ++x) {
      uint8_t bits = font->bitmap[glyph->offset + y * glyph->rowBytes + x / 8];
      if (bits & (1U << (x & 7))) {
        if (y < first) first = y;
        last = y;
        break;
      }
    }
  }
  if (last < first) return {0, font->height};
  int top = font->ascent - glyph->yOffset - glyph->height + first;
  return {(int16_t)top, (uint8_t)(last - first + 1)};
}
