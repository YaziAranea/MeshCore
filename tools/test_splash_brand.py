"""Bounded production-C++ SplashScreen rendering with real driver font metrics.

Executes the checked-in render method and role helpers with recording stubs,
then paints their recorded coordinates from the actual bitmap/glyph tables.
Not complete UITask, display electronics, button timing or e-paper BUSY testing.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess

from PIL import Image, ImageDraw

from embedded_bitmap_fonts import EmbeddedRaw
from simulate_oled_128x64 import STYLES, glyph_for
from simulate_smartui_ps17_qa import glyph_ink_bounds, label_font
from simulate_wireless_paper_ps17_qa import PROFILES


ROOT = Path(__file__).resolve().parents[1]
UI_PATH = ROOT / "examples/companion_radio/ui-new/UITask.cpp"
SX, SY = 1.875, 2.109375
BOARDS = (
    ("T096", "t096", 160, 80, 160, 80, range(5, 20), 10),
    ("T114", "t114", 128, 64, 240, 135, range(10), 0),
    ("ProMicro RA62", "oled", 128, 64, 128, 64, range(5), 0),
    ("Heltec V3", "oled", 128, 64, 128, 64, range(5), 0),
    ("Heltec V4.3", "oled", 128, 64, 128, 64, range(5), 0),
    ("Wireless Paper", "paper", 250, 122, 250, 122, range(5), 0),
)
MARKER_FILES = {"T096": "heltec_t096", "T114": "heltec_t114", "ProMicro RA62": "promicro",
                "Heltec V3": "heltec_v3", "Heltec V4.3": "heltec_v4", "Wireless Paper": "heltec_wireless_paper"}


def board_marker(name):
    config = (ROOT / "variants" / MARKER_FILES[name] / "platformio.ini").read_text(encoding="utf-8")
    values = re.findall(r'MESHCORE_UI_VERSION\s*=\s*\'"([^"\n]+)"\'', config)
    assert values, f"missing binary marker for {name}"
    return values[-1]


@lru_cache(maxsize=None)
def raw_font(kind, font, size):
    if kind == "t096":
        return EmbeddedRaw("meshcore_font", "meshcoreSmallFonts", font)
    source = (ROOT / "src/helpers/ui/ST7789Display.cpp").read_text(encoding="utf-8")
    table = source.split("ST7789_FONT_PROFILES[] = {", 1)[1].split("};", 1)[0]
    entries = [(int(a), int(b)) for a, b in re.findall(r'\{(\d+),\s*(\d+),\s*"', table)]
    index = entries[font][1 if size > 1 else 0]
    return EmbeddedRaw("meshcore_st7789_font", "meshcoreSt7789Fonts", index)


def metrics(kind, font, size, bold, text):
    if kind in ("t096", "t114"):
        raw = raw_font(kind, font, size)
        ink = glyph_ink_bounds(raw.glyph("H"))
        assert ink
        extra = int(bold and (kind == "t114" or size == 1))
        if kind == "t114":
            width = sum(math.ceil((raw.glyph(ch)["x_advance"] + extra) / SX) for ch in text)
            return width, int(ink[1] / SY), math.ceil((ink[3] - ink[1]) / SY), math.ceil(raw.height / SY)
        width = sum(raw.glyph(ch)["x_advance"] * size + extra for ch in text)
        return width, ink[1] * size, (ink[3] - ink[1]) * size, raw.height * size
    if kind == "oled":
        _, advance, style_bold = STYLES[font]
        weight = (style_bold or bold) and size == 1
        if weight:
            advance = max(6, advance)
            if font != 4:
                advance = max(7, advance)
        return len(text) * advance * size, 0, 7 * size, 8 * size
    advance, gap, weight, fixed = list(PROFILES.values())[font]
    extra = int(bold or weight)
    width = sum((4 if ch == " " and not fixed else advance) * size + extra for ch in text)
    return width, 0, 7 * size, (10 if size > 1 else 8 + gap) * size


def production_code(source):
    start = source.index("class SplashScreen :")
    render = source.index("  int render(DisplayDriver& display) override {", start)
    end = source.index("\n  void poll() override", render)
    method = source[render:end].rstrip()
    helpers = source[source.index("static const uint8_t UI_OLED_FONT_M"):
                     source.index("static void drawOledCompactMenuPage")]
    centered = source.index("static void drawRichTextCentered(DisplayDriver&")
    helpers = source[centered:source.index("\n}", centered) + 2] + "\n" + helpers
    release = re.search(r'#ifndef SMARTUI_RELEASE_LABEL\s+.*?#endif', source, re.S)
    assert release and '"0.05"' in release.group(), "release-label fallback must be 0.05"
    assert "Мешкор" not in method and "Омск" not in method
    assert not re.search(r'draw[^;\n]*MESHCORE_UI_VERSION', method), "internal marker must not be displayed"
    assert "_version_info" not in method
    assert "const volatile char* release_metadata = MESHCORE_UI_VERSION;" in method
    assert method.count("MESHCORE_UI_VERSION") == 2, "internal marker belongs only to the metadata anchor"
    assert "i < sizeof(MESHCORE_UI_VERSION)" in method and "(void)release_metadata[i]" in method
    assert method.count('"MeshCore"') >= 1 and "SMARTUI_RELEASE_LABEL" in method
    return method, helpers, release.group()


def execute_cpp(kind, method, helpers, release, output, marker=None, name=None):
    count = 20 if kind == "t096" else 10 if kind == "t114" else 5
    width, height = {"t096": (160, 80), "t114": (128, 64), "oled": (128, 64), "paper": (250, 122)}[kind]
    flags = {"UI_T096_PREMIUM_TFT": int(kind == "t096"),
             "UI_V4_3_OLED_PROFILE": int(kind in ("t096", "oled")),
             "UI_NATIVE_TFT_PROFILE": int(kind == "t114"),
             "UI_WIRELESS_PAPER_BIG_CLOCK": int(kind == "paper")}
    marker = marker or board_marker(next(board[0] for board in BOARDS if board[1] == kind))
    slug = (name or kind).lower().replace(" ", "-")
    code = "".join(f"#define {flag} {value}\n" for flag, value in flags.items()) + release + "\n"
    code += "#define MESHCORE_UI_VERSION " + json.dumps(marker, ensure_ascii=False) + "\n"
    code += r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <map>
#include <string>
#include <tuple>
#include <vector>
struct Metric { int brand,label,top,ink,line; };
struct Draw { std::string text; int x,y,font,size,bold,color,width; };
struct DisplayDriver {
  enum { BLUE=1, LIGHT=2 };
  int w,h,count,font=0,size=1,color=LIGHT; bool bold=false;
  std::map<std::tuple<int,int,bool>,Metric> table;
  std::vector<Draw> draws;
  int width() const { return w; } int height() const { return h; }
  uint8_t getUiFont() const { return font; }
  uint8_t getUiFontCount() const { return count; }
  void setUiFont(uint8_t value) { assert(value<count); font=value; }
  void setTextSize(int value) { size=value; }
  void setBold(bool value) { bold=value; }
  void setColor(int value) { color=value; }
  const Metric& metric() const { return table.at({font,size,bold}); }
  int getTextWidth(const char* text) const {
    assert(!strcmp(text,"MeshCore") || !strcmp(text,"0.05"));
    return !strcmp(text,"MeshCore") ? metric().brand : metric().label;
  }
  int getTextInkTop() const { return metric().top; }
  int getTextInkHeight() const { return metric().ink; }
  int getTextLineHeight() const { return metric().line; }
};
int richTextWidth(DisplayDriver& d,const char* text) { return d.getTextWidth(text); }
int drawRichTextLine(DisplayDriver& d,int x,int y,const char* text) {
  int width=d.getTextWidth(text);
  d.draws.push_back({text,x,y,d.font,d.size,d.bold,d.color,width});
  return width;
}
struct UIScreen { virtual int render(DisplayDriver&)=0; virtual ~UIScreen()=default; };
'''
    code += helpers + "\nstruct SplashScreen : UIScreen {\n" + method + "\n};\nint main() {\n"
    code += f"DisplayDriver d; d.w={width}; d.h={height}; d.count={count};\n"
    for font in range(count):
        for size in (1, 2):
            for bold in (False, True):
                a = metrics(kind, font, size, bold, "MeshCore")
                b = metrics(kind, font, size, bold, "0.05")
                code += f"d.table[{{{font},{size},{str(bold).lower()}}}]={{{a[0]},{b[0]},{a[1]},{a[2]},{a[3]}}};\n"
    first = 5 if kind == "t096" else 0
    code += f"for(int initial={first};initial<{count};++initial) {{\n"
    code += r'''
  d.font=initial; d.size=1; d.bold=false; d.draws.clear(); SplashScreen splash;
  assert(splash.render(d)==1000);
  assert(d.font==initial && d.size==1 && !d.bold);
  assert(d.draws.size()==2 && d.draws[0].text=="MeshCore" && d.draws[1].text=="0.05");
  for(const auto& draw:d.draws) {
    assert(draw.x>=4 && draw.x+draw.width<=d.w-4);
    assert(draw.x==d.w/2-draw.width/2);
    std::cout << initial << '\t' << draw.text << '\t' << draw.x << '\t' << draw.y << '\t'
              << draw.font << '\t' << draw.size << '\t' << draw.bold << '\t' << draw.color << '\t' << draw.width << '\n';
  }
}
}
'''
    output.mkdir(parents=True, exist_ok=True)
    cpp = output / f"splash_{slug}.cpp"
    cpp.write_text(code, encoding="utf-8")
    if shutil.which("g++"):
        binary = output / f"splash_{slug}"
        compile_cmd = ["g++", "-std=c++17", "-O2", "-flto", "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections", "-Wall", "-Wextra", str(cpp), "-o", str(binary)]
        run_cmd = [str(binary)]
    else:
        linux = subprocess.check_output(["wsl", "--exec", "wslpath", "-a", output.resolve().as_posix()], text=True).strip()
        binary = output / f"splash_{slug}"
        compile_cmd = ["wsl", "--exec", "g++", "-std=c++17", "-O2", "-flto", "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections", "-Wall", "-Wextra", linux + f"/splash_{slug}.cpp", "-o", linux + f"/splash_{slug}"]
        run_cmd = ["wsl", "--exec", linux + f"/splash_{slug}"]
    subprocess.run(compile_cmd, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert marker.encode("utf-8") + b"\0" in binary.read_bytes(), f"board marker lost under LTO/linker GC: {marker}"
    result = subprocess.check_output(run_cmd, text=True, encoding="utf-8")
    records = {}
    for line in result.splitlines():
        initial, text, *values = line.split("\t")
        records.setdefault(int(initial), []).append({"text": text, **dict(zip(
            ("x", "y", "font", "size", "bold", "color", "width"), map(int, values)))})
    return records


def paint(kind, image, record, color):
    """Driver-faithful glyph pixels at the C++-recorded native coordinates."""
    font, size, bold, text = (record[key] for key in ("font", "size", "bold", "text"))
    x, y = record["x"], record["y"]
    points = []
    if kind in ("t096", "t114"):
        raw = raw_font(kind, font, size)
        cursor, top = (int(x * SX), int(y * SY) + 1) if kind == "t114" else (x, y)
        scale = 1 if kind == "t114" else size
        weight = int(bold and (kind == "t114" or size == 1))
        for char in text:
            glyph = raw.glyph(char)
            for row in range(glyph["height"]):
                for col in range(glyph["width"]):
                    if glyph["data"][row * glyph["row_bytes"] + col // 8] & (1 << (col & 7)):
                        points.extend((cursor + (glyph["x_offset"] + col) * scale + dx, top + row * scale + dy)
                                      for dx in range(scale + weight) for dy in range(scale))
            cursor += glyph["x_advance"] * scale + weight
    else:
        if kind == "oled":
            _, advance, style_bold = STYLES[font]
            weight = int((style_bold or bold) and size == 1)
            if weight:
                advance = max(6 if font == 4 else 7, advance)
            advance = advance * size
        else:
            advance, _, weight, _ = list(PROFILES.values())[font]
            weight = int(bold or weight)
            advance = advance * size + weight
        cursor = x
        for char in text:
            for col, bits in enumerate(glyph_for(char)):
                for row in range(8):
                    if bits & (1 << row):
                        points.extend((cursor + col * size + dx, y + row * size + dy)
                                      for dx in range(size + weight) for dy in range(size))
            cursor += advance
    assert points, "mandatory splash text has no ink"
    assert all(0 <= px < image.width and 0 <= py < image.height for px, py in points), "splash ink clipped"
    draw = ImageDraw.Draw(image)
    for point in points:
        draw.point(point, fill=color)
    return min(px for px, _ in points), min(py for _, py in points), max(px for px, _ in points) + 1, max(py for _, py in points) + 1


def rgb565(value):
    return ((value >> 11 & 31) * 255 // 31, (value >> 5 & 63) * 255 // 63, (value & 31) * 255 // 31)


def native_preview(kind, records):
    t096_source = (ROOT / "src/helpers/ui/ST7735Display.cpp").read_text(encoding="utf-8")
    first_theme = t096_source.split("ST7735_THEMES[] = {", 1)[1].split("\n", 2)[1]
    palette = [int(value, 16) for value in re.findall(r"0x[0-9A-Fa-f]+", first_theme)]
    width, height = {"t096": (160, 80), "t114": (240, 135), "oled": (128, 64), "paper": (250, 122)}[kind]
    bg = rgb565(palette[1]) if kind == "t096" else (255, 255, 255) if kind == "paper" else (0, 0, 0)
    image = Image.new("RGB", (width, height), bg)
    boxes = []
    for record in records:
        color = rgb565(palette[4 if record["color"] == 1 else 0]) if kind == "t096" else (0, 0, 0) if kind == "paper" else (255, 255, 255)
        boxes.append(paint(kind, image, record, color))
    return image, boxes


def render_splash_preview(kind, font, out=None):
    """Source-backed native preview for legacy gallery callers."""
    method, helpers, release = production_code(UI_PATH.read_text(encoding="utf-8"))
    records = execute_cpp(kind, method, helpers, release, out or ROOT / "qa_outputs/splash-smartui-v5/legacy")[font]
    return native_preview(kind, records)[0]


def main(out, preview):
    source = UI_PATH.read_text(encoding="utf-8")
    method, helpers, release = production_code(source)
    actual = {name: execute_cpp(kind, method, helpers, release, out, board_marker(name), name)
              for name, kind, *_ in BOARDS}
    defaults, checks = [], 0
    for name, kind, width, height, physical_w, physical_h, fonts, default in BOARDS:
        for initial in fonts:
            records = actual[name][initial]
            image, boxes = native_preview(kind, records)
            assert image.size == (physical_w, physical_h)
            assert boxes[0][3] + 4 <= boxes[1][1], f"brand/release overlap: {name}/{initial}"
            brand = records[0]
            _, brand_top, brand_ink, _ = metrics(kind, brand["font"], brand["size"], brand["bold"], "MeshCore")
            assert abs((brand["y"] + brand_top) * 2 + brand_ink - height) <= 1, "brand ink is not vertically centred"
            label = records[1]
            _, label_top, label_ink, _ = metrics(kind, label["font"], label["size"], label["bold"], "0.05")
            assert label["y"] + label_top + label_ink == height - (10 if height >= 96 else 6), "release label bottom margin differs"
            assert label["bold"] == 0, "release label inherited hero bold"
            assert records[1]["text"] == "0.05" and len(records) == 2
            image.save(out / f"{name.lower().replace(' ', '-')}-{initial}.png")
            checks += 1
            if initial == default:
                defaults.append((name, image))
    report = {"checks": checks, "failed": 0, "boards": len(BOARDS), "render_sha256": hashlib.sha256(method.encode()).hexdigest(),
              "binary_markers": {name: board_marker(name) for name, *_ in BOARDS},
              "marker_retention": "all six exact markers present under -O2 -flto -ffunction-sections -fdata-sections -Wl,--gc-sections",
              "scope": "actual SplashScreen render and role helpers; exact bitmap/OLED/E213 metrics and pixels; recording stubs, not whole firmware or hardware"}
    (out / "REPORT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tile_w, tile_h, gap = 520, 310, 16
    sheet = Image.new("RGB", (tile_w * 3 + gap * 2, tile_h * 2 + gap), (18, 22, 28))
    draw = ImageDraw.Draw(sheet)
    for index, (name, image) in enumerate(defaults):
        x, y = index % 3 * (tile_w + gap), index // 3 * (tile_h + gap)
        scale = {160: 3, 240: 2, 128: 4, 250: 2}[image.width]
        scaled = image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)
        draw.text((x + 10, y + 6), name + " — bitmap simulation", font=label_font(16), fill=(235, 241, 248))
        sheet.paste(scaled, (x + (tile_w - scaled.width) // 2, y + 32))
    preview.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(preview)
    print(f"PASS {checks} actual C++ splash/font scenarios across {len(BOARDS)} boards")
    print(preview)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "qa_outputs/splash-smartui-0.05")
    parser.add_argument("--preview", type=Path, default=ROOT / "docs/assets/ui/boot-smartui-0.05.png")
    arguments = parser.parse_args()
    main(arguments.out_dir, arguments.preview)
