"""Exercise the real SSD1306 renderer with a pixel-capturing host display.

Requires Python 3, g++ and nm; does not build firmware or need a physical OLED.
Compares compact builds with/without embedded fonts, checks all five styles,
and compiles both non-compact font configurations to catch accidental removal.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]

STUBS = {
    "Arduino.h": r"""
#pragma once
#include <stdint.h>
#define HIGH 1
#define LOW 0
#define OUTPUT 1
inline void pinMode(int, int) {}
inline void digitalWrite(int, int) {}
inline void delay(unsigned long) {}
""",
    "Wire.h": r"""
#pragma once
#include "Arduino.h"
class TwoWire {
public:
  void begin() {}
  void beginTransmission(uint8_t) {}
  uint8_t endTransmission() { return 0; }
};
inline TwoWire Wire;
""",
    "Adafruit_GFX.h": "#pragma once\n",
    "Adafruit_SSD1306.h": r"""
#pragma once
#include <algorithm>
#include <array>
#include "Wire.h"
#define SSD1306_BLACK 0
#define SSD1306_WHITE 1
#define SSD1306_SWITCHCAPVCC 2
#define SSD1306_DISPLAYON 0xAF
#define SSD1306_DISPLAYOFF 0xAE
class Adafruit_SSD1306 {
  int16_t x = 0, y = 0;
public:
  inline static Adafruit_SSD1306* last = nullptr;
  std::array<uint8_t, 128 * 64> pixels{};
  Adafruit_SSD1306(int, int, TwoWire*, int) { last = this; }
  bool begin(int, int, bool, bool) { return true; }
  void setRotation(int) {}
  void ssd1306_command(int) {}
  void clearDisplay() { pixels.fill(0); }
  void display() {}
  void setTextColor(int) {}
  void setTextSize(int) {}
  void cp437(bool) {}
  int16_t getCursorX() const { return x; }
  int16_t getCursorY() const { return y; }
  void setCursor(int16_t next_x, int16_t next_y) { x = next_x; y = next_y; }
  void fillRect(int px, int py, int w, int h, int color) {
    for (int yy = std::max(0, py); yy < std::min(64, py + h); ++yy)
      for (int xx = std::max(0, px); xx < std::min(128, px + w); ++xx)
        pixels[yy * 128 + xx] = color != 0;
  }
  void drawRect(int px, int py, int w, int h, int color) {
    fillRect(px, py, w, 1, color);
    fillRect(px, py + h - 1, w, 1, color);
    fillRect(px, py, 1, h, color);
    fillRect(px + w - 1, py, 1, h, color);
  }
  void drawBitmap(int px, int py, const uint8_t* data, int w, int h, int color) {
    for (int yy = 0; yy < h; ++yy)
      for (int xx = 0; xx < w; ++xx)
        if (data[yy * ((w + 7) / 8) + xx / 8] & (0x80 >> (xx & 7)))
          fillRect(px + xx, py + yy, 1, 1, color);
  }
};
""",
}

HARNESS = r"""
#include <cassert>
#include <cstdio>
#include <cstring>
#include "helpers/ui/SSD1306Display.h"

int main() {
  SSD1306Display renderer;
  assert(renderer.begin());
  const auto count = renderer.getUiFontCount();
#if SSD1306_COMPACT_STYLE_PROFILE
  assert(count == 5);
  const char* names[] = {
    "Classic 6x8", "Air 7x8", "Strong 7x8", "Narrow 5x8", "Dense 6x8"
  };
  const int advances[] = {6, 7, 7, 5, 6};
#elif defined(HELTEC_LORA_V4_OLED)
  assert(count == 21);
  assert(strcmp(renderer.getUiFontName(0), "V4 6x8") == 0);
  assert(strcmp(renderer.getUiFontName(1), "Roboto L") == 0);
#else
  assert(count == 20);
  assert(strcmp(renderer.getUiFontName(0), "Roboto L") == 0);
#endif
  // Every external font ID must be normalized before any table access.
  for (unsigned id = 0; id < 256; ++id) {
    renderer.setUiFont(id);
    assert(renderer.getUiFont() == (id < count ? id : 0));
    assert(strcmp(renderer.getUiFontName(id),
                  renderer.getUiFontName(id < count ? id : 0)) == 0);
  }
  const char* samples[] = {
    "GPS off Привет!", "AB\nЯz\rЁё", "Короткое сообщение test",
    "АБВ абв длинный текст", "? \t unsupported: \xf0\x9f\x94\x8b"
  };
  for (unsigned font = 0; font < count; ++font) {
    for (unsigned size = 1; size <= 3; ++size) {
      for (unsigned bold = 0; bold <= 1; ++bold) {
        for (unsigned sample = 0; sample < 5; ++sample) {
          renderer.startFrame();
          renderer.setUiFont(font);
          renderer.setTextSize(size);
          renderer.setBold(bold != 0);
          renderer.setCursor(3, 2);
#if SSD1306_COMPACT_STYLE_PROFILE
          assert(strcmp(renderer.getUiFontName(font), names[font]) == 0);
          assert(renderer.getTextLineHeight() == 8 * size);
          const bool has_bold = (bold || font == 2 || font == 4) && size == 1;
          int advance = advances[font];
          if (has_bold && advance < 6) advance = 6;
          if (has_bold && advance < 7 && font != 4) advance = 7;
          assert(renderer.getTextWidth("AЯё") == 3 * advance * size);
          assert(renderer.getTextWidth("A\nЯё") == 2 * advance * size);
#endif
          if (sample == 2) renderer.printWordWrap(samples[sample], 97);
          else if (sample == 3) renderer.drawTextEllipsized(3, 2, 97, samples[sample]);
          else renderer.print(samples[sample]);
          const auto* output = Adafruit_SSD1306::last;
          uint64_t hash = 14695981039346656037ULL;
          for (auto pixel : output->pixels) hash = (hash ^ pixel) * 1099511628211ULL;
          std::printf("%u:%u:%u:%u:%s:%u:%u:%d:%d:%llu\n", font, size, bold, sample,
                      renderer.getUiFontName(font), renderer.getTextLineHeight(),
                      renderer.getTextWidth(samples[sample]), output->getCursorX(),
                      output->getCursorY(), static_cast<unsigned long long>(hash));
        }
      }
    }
  }
}
"""


def run(command: list[str]) -> str:
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    parser.add_argument("--nm", default="nm")
    args = parser.parse_args()
    for tool in (args.cxx, args.nm):
        if not shutil.which(tool):
            parser.error(f"required tool not found: {tool}")

    with tempfile.TemporaryDirectory(prefix="smartui-ssd1306-") as directory:
        temp = Path(directory)
        for name, source in STUBS.items():
            (temp / name).write_text(source, encoding="utf-8")
        harness = temp / "main.cpp"
        harness.write_text(HARNESS, encoding="utf-8")

        def build(name: str, defines: list[str]) -> tuple[str, str]:
            binary = temp / name
            run([args.cxx, "-std=c++17", "-O0", f"-I{temp}", f"-I{ROOT / 'src'}",
                 *[f"-D{define}" for define in defines], str(harness),
                 str(ROOT / "src/helpers/ui/SSD1306Display.cpp"), "-o", str(binary)])
            return run([str(binary)]), run([args.nm, "-C", str(binary)])

        compact, symbols = build("compact", ["PROMICRO=1"])
        reference, _ = build("compact-with-bitmap", [
            "PROMICRO=1", "SSD1306_USE_EMBEDDED_FONTS=1",
        ])
        assert compact == reference, "compact pixels/cursors/metrics differ"
        assert not re.search(r"meshcoreSmallFonts|meshcore_font_", symbols), \
            "compact binary still contains embedded bitmap font tables"
        for board in ("HELTEC_LORA_V3", "HELTEC_LORA_V4_3_OLED"):
            output, board_symbols = build(board, [f"{board}=1"])
            assert output == compact, f"{board}: compact profile changed"
            assert not re.search(r"meshcoreSmallFonts|meshcore_font_", board_symbols)
        for name, defines in (("bitmap", []), ("v4-mixed", ["HELTEC_LORA_V4_OLED=1"])):
            output, bitmap_symbols = build(name, defines)
            assert output and "meshcoreSmallFonts" in bitmap_symbols, \
                f"{name}: embedded fonts were accidentally removed"

    print("PASS: 150 compact pixel/metric cases identical with/without bitmap tables;")
    print("      ProMicro/V3/V4.3 compact tables absent; bitmap/mixed profiles preserved.")


if __name__ == "__main__":
    main()
