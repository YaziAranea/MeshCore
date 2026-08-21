from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont


ROOT = Path(__file__).resolve().parents[1]
NOTO_SRC = ROOT / "tools" / "font_sources" / "noto_sans_2_015"
READABLE_SRC = ROOT / "tools" / "font_sources" / "ui_readable_10"
OUT = ROOT / "src" / "helpers" / "ui" / "EmbeddedBitmapFonts.h"

FONT_TOP = -8
FONT_BOTTOM = 2
FONT_ASCENT = -FONT_TOP
FONT_DESCENT = FONT_BOTTOM
FONT_HEIGHT = FONT_ASCENT + FONT_DESCENT

FONT_FAMILIES = [
    ("Roboto", READABLE_SRC / "RobotoCondensed-wght.ttf", [430]),
    ("Noto", NOTO_SRC / "NotoSans-CondensedMedium.ttf", None),
    ("OpenSans", READABLE_SRC / "OpenSans-wdth-wght.ttf", [540, 92]),
    ("PT Narrow", READABLE_SRC / "PTSansNarrow-Bold.ttf", None),
    ("Oswald", READABLE_SRC / "Oswald-wght.ttf", [440]),
]

SMALL_SIZES = [
    ("L", 12, 16, 13, 3),
    ("XL", 14, 18, 15, 3),
    ("XXL", 16, 21, 17, 4),
    ("Hero", 18, 24, 20, 4),
]

FONTS = [
    (f"{family} {suffix}", path, size, axes, height, ascent, descent)
    for suffix, size, height, ascent, descent in SMALL_SIZES
    for family, path, axes in FONT_FAMILIES
]

ST7789_FAMILIES = FONT_FAMILIES

ST7789_SIZES = [
    ("L", 18, 24, 20, 4),
    ("XL", 19, 25, 21, 4),
    ("XXL", 20, 26, 22, 4),
]

ST7789_FONTS = [
    (f"{family} {suffix}", path, size, axes, height, ascent, descent)
    for suffix, size, height, ascent, descent in ST7789_SIZES
    for family, path, axes in ST7789_FAMILIES
] + [
    ("Roboto Clock", READABLE_SRC / "RobotoCondensed-wght.ttf", 28, [430], 36, 30, 6),
]

E213_SIZES = [
    ("M", 12, 17, 14, 3),
    ("S", 10, 15, 12, 3),
    ("L", 14, 19, 15, 4),
]

E213_FONTS = [
    (f"{family} {suffix}", path, size, axes, height, ascent, descent)
    for suffix, size, height, ascent, descent in E213_SIZES
    for family, path, axes in ST7789_FAMILIES
]

EXTRAS = [
    0x00A0, 0x00AB, 0x00BB, 0x00B0, 0x2116,
    0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2026,
    0x2190, 0x2191, 0x2192, 0x2193,
]


def codepoints():
    cps = set(range(32, 127))
    cps.update(range(0x0400, 0x0460))
    cps.update([0x0490, 0x0491])
    cps.update(EXTRAS)
    return sorted(cps)


def font_cmap(path):
    cmap = set()
    font = TTFont(str(path), lazy=True)
    for table in font["cmap"].tables:
        cmap.update(table.cmap.keys())
    return cmap


def render_glyph(font, cp, ascent=FONT_ASCENT, descent=FONT_DESCENT, height=FONT_HEIGHT, antialias_threshold=None):
    ch = chr(cp)
    bbox = font.getbbox(ch, anchor="ls")
    advance = int(round(font.getlength(ch)))

    if cp == 0x00A0:
        advance = int(round(font.getlength(" ")))
        return {
            "codepoint": cp,
            "width": 0,
            "height": height,
            "row_bytes": 0,
            "x_advance": max(1, advance),
            "x_offset": 0,
            "y_offset": -descent,
            "data": [],
        }

    x_shift = -min(0, bbox[0])
    width = max(0, bbox[2] + x_shift, advance)
    row_bytes = (width + 7) // 8
    img = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(img)
    draw.fontmode = "L" if antialias_threshold is not None else "1"
    draw.text((x_shift, ascent), ch, font=font, fill=255, anchor="ls")

    data = []
    threshold = antialias_threshold if antialias_threshold is not None else 0
    for y in range(height):
        for byte_index in range(row_bytes):
            value = 0
            for bit in range(8):
                x = byte_index * 8 + bit
                if x < width and img.getpixel((x, y)) > threshold:
                    value |= 1 << bit
            data.append(value)

    return {
        "codepoint": cp,
        "width": width,
        "height": height,
        "row_bytes": row_bytes,
        "x_advance": max(1, advance, width),
        "x_offset": 0,
        "y_offset": -descent,
        "data": data,
    }


def format_array(name, values):
    lines = [f"static const uint8_t {name}[] PROGMEM = {{"]
    for i in range(0, len(values), 16):
        chunk = values[i:i + 16]
        lines.append("  " + ", ".join(f"0x{v:02X}" for v in chunk) + ",")
    lines.append("};")
    return "\n".join(lines)


def append_font_set(chunks, fonts, prefix, table_name, count_name, getter_name,
                    height, ascent, descent, antialias_threshold=None, guard=None):
    if guard:
        chunks.append(f"#if {guard}")
        chunks.append("")
    cps = codepoints()
    font_refs = []
    for index, font_def in enumerate(fonts):
        name, path, size, axes = font_def[:4]
        font_height = font_def[4] if len(font_def) > 4 else height
        font_ascent = font_def[5] if len(font_def) > 5 else ascent
        font_descent = font_def[6] if len(font_def) > 6 else descent
        present = font_cmap(path)
        font = ImageFont.truetype(str(path), size=size)
        if axes:
            font.set_variation_by_axes(axes)
        glyphs = []
        bitmap = []

        for cp in cps:
            if cp not in present and cp != 0x00A0:
                continue
            glyph = render_glyph(font, cp, font_ascent, font_descent, font_height, antialias_threshold)
            glyph["offset"] = len(bitmap)
            bitmap.extend(glyph["data"])
            glyphs.append(glyph)

        max_width = max(g["width"] for g in glyphs)
        chunks.append(format_array(f"{prefix}_{index}_bitmap", bitmap))
        chunks.append("")
        chunks.append(f"static const MeshcoreBitmapGlyph {prefix}_{index}_glyphs[] PROGMEM = {{")
        for g in glyphs:
            chunks.append(
                "  {"
                f"0x{g['codepoint']:04X}, {g['offset']}, {g['width']}, {g['height']}, "
                f"{g['row_bytes']}, {g['x_advance']}, {g['x_offset']}, {g['y_offset']}"
                "},"
            )
        chunks.append("};")
        chunks.append("")
        chunks.append(f"static const char {prefix}_{index}_name[] = \"{name}\";")
        chunks.append("")
        font_refs.append((index, max_width, len(glyphs), font_height, font_ascent, font_descent))

    chunks.append(f"static const MeshcoreBitmapFont {table_name}[] = {{")
    for index, max_width, glyph_count, font_height, font_ascent, font_descent in font_refs:
        chunks.append(
            f"  {{{prefix}_{index}_name, {max_width}, {font_height}, {font_ascent}, "
            f"{font_descent}, {prefix}_{index}_glyphs, {glyph_count}, {prefix}_{index}_bitmap}},"
        )
    chunks.append("};")
    chunks.append("")
    chunks.append(f"static const uint8_t {count_name} = sizeof({table_name}) / sizeof({table_name}[0]);")
    chunks.append("")
    chunks.append(f"static inline const MeshcoreBitmapFont* {getter_name}(uint8_t font_id) {{")
    chunks.append(f"  if (font_id >= {count_name}) font_id = 0;")
    chunks.append(f"  return &{table_name}[font_id];")
    chunks.append("}")
    chunks.append("")
    if guard:
        chunks.append("#endif")
        chunks.append("")


def main():
    chunks = [
        "#pragma once",
        "#include <stdint.h>",
        "#include <stddef.h>",
        "",
        "#ifndef PROGMEM",
        "#define PROGMEM",
        "#endif",
        "",
        "// Generated by tools/generate_t096_design_bitmap_fonts.py.",
        "// Source fonts: Roboto Condensed, Noto Sans Condensed, Open Sans, PT Sans Narrow, and Oswald.",
        "// Source repositories: https://github.com/google/fonts, https://github.com/notofonts/latin-greek-cyrillic, and upstream SIL/OFL releases.",
        "// meshcoreSmallFonts are readable T096/TFT logical fonts, starting at L size.",
        "// meshcoreSt7789Fonts are native-pixel fonts for T114 ST7789.",
        "// meshcoreE213Fonts are logical-pixel fonts for Heltec Wireless Paper E213.",
        "",
        "struct MeshcoreBitmapGlyph {",
        "  uint16_t codepoint;",
        "  uint16_t offset;",
        "  uint8_t width;",
        "  uint8_t height;",
        "  uint8_t rowBytes;",
        "  uint8_t xAdvance;",
        "  int8_t xOffset;",
        "  int8_t yOffset;",
        "};",
        "",
        "struct MeshcoreBitmapFont {",
        "  const char* name;",
        "  uint8_t maxWidth;",
        "  uint8_t height;",
        "  uint8_t ascent;",
        "  uint8_t descent;",
        "  const MeshcoreBitmapGlyph* glyphs;",
        "  uint16_t glyphCount;",
        "  const uint8_t* bitmap;",
        "};",
        "",
    ]

    append_font_set(chunks, FONTS, "meshcore_font", "meshcoreSmallFonts",
                    "MESHCORE_SMALL_FONT_COUNT", "meshcoreGetSmallFont",
                    FONT_HEIGHT, FONT_ASCENT, FONT_DESCENT,
                    antialias_threshold=104)
    append_font_set(chunks, ST7789_FONTS, "meshcore_st7789_font", "meshcoreSt7789Fonts",
                    "MESHCORE_ST7789_FONT_COUNT", "meshcoreGetSt7789Font",
                    22, 18, 4,
                    antialias_threshold=92,
                    guard="defined(ST7789)")
    append_font_set(chunks, E213_FONTS, "meshcore_e213_font", "meshcoreE213Fonts",
                    "MESHCORE_E213_FONT_COUNT", "meshcoreGetE213Font",
                    17, 14, 3,
                    antialias_threshold=92,
                    guard="defined(HELTEC_WIRELESS_PAPER)")

    chunks.append("static inline const MeshcoreBitmapGlyph* meshcoreFindGlyph(const MeshcoreBitmapFont* font, uint16_t codepoint) {")
    chunks.append("  if (font == NULL) return NULL;")
    chunks.append("  int lo = 0;")
    chunks.append("  int hi = (int)font->glyphCount - 1;")
    chunks.append("  while (lo <= hi) {")
    chunks.append("    int mid = (lo + hi) / 2;")
    chunks.append("    uint16_t cp = font->glyphs[mid].codepoint;")
    chunks.append("    if (cp == codepoint) return &font->glyphs[mid];")
    chunks.append("    if (cp < codepoint) lo = mid + 1;")
    chunks.append("    else hi = mid - 1;")
    chunks.append("  }")
    chunks.append("  return NULL;")
    chunks.append("}")
    chunks.append("")

    OUT.write_text("\n".join(chunks), encoding="utf-8")


if __name__ == "__main__":
    main()
