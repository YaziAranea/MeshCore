# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import re

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "qa_outputs" / "oled_128x64"
OUT = OUT_DIR / "OLED_128x64_AUDIT_STYLE_MATRIX.png"
COMPACT_OUT = OUT_DIR / "OLED_128x64_COMPACT_B10_MATRIX.png"
FONT_PATH = ROOT / "tools" / "font_sources" / "noto_sans_2_015" / "NotoSans-CondensedMedium.ttf"
GLYPH_HEADER = ROOT / "src" / "helpers" / "ui" / "Utf8Cyrillic5x7.h"

W = 128
H = 64
SCALE = 4
ROW_LABEL = 86
COL_LABEL = 18
GAP = 6

STYLES = [
    ("Classic", 6, False),
    ("Air", 7, False),
    ("Strong", 7, True),
    ("Narrow", 5, False),
    ("Dense", 6, True),
]
PAGES = ("Часы", "Сеть", "Чат", "Popup", "Настройки", "Прокрутка")


COMPACT_CASES = (
    ("PM root", "Настройки", (("Уведомления", "Зуммер"), ("Звук и вибро", "ОБЫЧ"), ("Экран", "Classic 6x8")), 0),
    ("PM уведом.", "Уведомления", (("Обычные", "Зуммер"), ("ЛС / упомин.", "Зуммер"), ("Всплывающие", "ВКЛ")), 1),
    ("PM звук", "Звук и вибро", (("Мелодия", "Пульс"), ("Громкость", "ОБЫЧ"), ("Пин вибро", "ВЫКЛ")), 0),
    ("PM экран", "Экран", (("Шрифт", "Classic 6x8"), ("Назад", "")), 0),
    ("PM радио", "Радио и GPS", (("Параметры", "869.525"), ("Авто-анонс", "30 мин"), ("Назад", "")), 1),
    ("PM система", "Система", (("Bluetooth", "ВКЛ"), ("LED платы", "ВКЛ"), ("Назад", "")), 0),
    ("FT радио", "Радио и GPS", (("Авто-анонс", "30 мин"), ("АЦП", "1.815"), ("Назад", "")), 1),
    ("FT система", "Система", (("Bluetooth", "ВКЛ"), ("LED платы", "ВКЛ"), ("Защита АКБ", "ВКЛ")), 2),
)


def font(size: int = 8) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), size=size)


FONT_LABEL = font(12)


def glyph_table(name: str) -> list[tuple[int, ...]]:
    source = GLYPH_HEADER.read_text(encoding="utf-8")
    match = re.search(rf"{name}\[\]\[5\]\s*=\s*\{{(.*?)\n\}};", source, re.S)
    if not match:
        raise RuntimeError(f"Missing glyph table {name}")
    return [
        tuple(int(value, 16) for value in re.findall(r"0x([0-9A-Fa-f]+)", row))
        for row in re.findall(r"\{([^{}]+)\}", match.group(1))
    ]


ASCII_GLYPHS = glyph_table("meshcore_ascii_5x7")
CYRILLIC_UPPER_GLYPHS = glyph_table("meshcore_cyrillic_5x7")
CYRILLIC_LOWER_GLYPHS = glyph_table("meshcore_cyrillic_lower_5x7")


def glyph_for(char: str) -> tuple[int, ...]:
    codepoint = ord(char)
    if 32 <= codepoint <= 126:
        return ASCII_GLYPHS[codepoint - 32]
    if char == "Ё":
        return CYRILLIC_UPPER_GLYPHS[5]
    if char == "ё":
        return CYRILLIC_LOWER_GLYPHS[5]
    if 0x0410 <= codepoint <= 0x042F:
        return CYRILLIC_UPPER_GLYPHS[codepoint - 0x0410]
    if 0x0430 <= codepoint <= 0x044F:
        return CYRILLIC_LOWER_GLYPHS[codepoint - 0x0430]
    return ASCII_GLYPHS[ord("?") - 32]


def clean_text(text: str) -> str:
    if "Р" not in text and "С" not in text:
        return text
    try:
        return text.encode("cp1251").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


class Oled:
    def __init__(self, style: tuple[str, int, bool]):
        self.name, self.advance, self.bold = style
        self.img = Image.new("1", (W, H), 0)
        self.draw = ImageDraw.Draw(self.img)
        self.overflows: list[str] = []

    def text_width(self, text: str, size: int = 1) -> int:
        return len(text) * self.advance * size

    def text(self, x: int, y: int, text: str, *, right: bool = False, center: bool = False,
             max_width: int | None = None, size: int = 1) -> None:
        text = clean_text(text)
        if max_width is not None:
            max_chars = max(1, max_width // (self.advance * size))
            text = text[:max_chars]
        width = self.text_width(text, size)
        if right:
            x -= width
        elif center:
            x -= width // 2
        if x < 0 or x + width > W or y < 0 or y + 8 * size > H:
            self.overflows.append(f"{self.name}: '{text}' at {x},{y}")
        cursor_x = x
        for char in text:
            for col, bits in enumerate(glyph_for(char)):
                for row in range(8):
                    if bits & (1 << row):
                        px = cursor_x + col * size
                        py = y + row * size
                        self.draw.rectangle((px, py, px + size - 1, py + size - 1), fill=1)
                        if self.bold and size == 1:
                            self.draw.point((px + 1, py), fill=1)
            cursor_x += self.advance * size

    def battery(self, x: int, y: int, level: int = 75) -> None:
        self.draw.rectangle((x, y, x + 13, y + 7), outline=1)
        self.draw.rectangle((x + 14, y + 2, x + 15, y + 5), fill=1)
        fill = max(0, min(10, round(level / 10)))
        if fill:
            self.draw.rectangle((x + 2, y + 2, x + 1 + fill, y + 5), fill=1)

    def gps(self, x: int, y: int) -> None:
        self.draw.rectangle((x + 4, y + 3, x + 7, y + 6), fill=1)
        self.draw.line((x, y + 3, x + 3, y + 4), fill=1)
        self.draw.line((x + 8, y + 4, x + 11, y + 3), fill=1)
        self.draw.line((x + 5, y + 2, x + 5, y), fill=1)
        self.draw.point((x + 9, y), fill=1)
        self.draw.line((x + 4, y + 7, x + 3, y + 9), fill=1)
        self.draw.line((x + 7, y + 7, x + 8, y + 9), fill=1)

    def mute(self, x: int, y: int) -> None:
        self.draw.polygon((x, y + 4, x + 3, y + 4, x + 6, y + 1, x + 6, y + 8, x + 3, y + 5, x, y + 5), fill=1)
        self.draw.line((x + 1, y + 9, x + 9, y), fill=1)

    def popup(self, title: str, body: str) -> None:
        self.draw.rectangle((5, 14, 122, 49), outline=1)
        self.text(64, 17, title, center=True, max_width=108)
        self.text(64, 31, body, center=True, max_width=108)
        self.text(64, 42, "нажать OK", center=True, max_width=108)

    def ellipsized(self, x: int, y: int, text: str, max_width: int) -> None:
        text = clean_text(text)
        max_chars = max(1, max_width // self.advance)
        if len(text) > max_chars:
            text = text[:max(1, max_chars - 3)] + "..."
        self.text(x, y, text, max_width=max_width)

    def compact_settings(self, title: str, rows: tuple[tuple[str, str], ...], selected: int) -> None:
        title = clean_text(title)
        self.ellipsized(max(0, (W - self.text_width(title)) // 2), 14, title, W - 2)
        value_width = 50
        for row, (label, value) in enumerate(rows[:3]):
            y = 28 + row * 12
            marker = row == selected
            if marker:
                self.text(0, y, ">")
            label_x = 8 if marker else 2
            value_x = W - value_width
            label_width = value_x - label_x - 2 if value else W - label_x - 2
            self.ellipsized(label_x, y, label, label_width)
            if value:
                self.ellipsized(value_x, y, value, value_width - 1)


def draw_page(style: tuple[str, int, bool], page: str) -> tuple[Image.Image, list[str]]:
    oled = Oled(style)
    if page == "Часы":
        oled.text(0, 0, "Мешкор Омск", max_width=82)
        oled.text(90, 0, "3.92V")
        oled.battery(112, 0)
        oled.mute(8, 23)
        oled.text(64, 17, "17:08", center=True, size=2)
        oled.gps(105, 23)
        oled.text(119, 24, "8", right=True)
        oled.text(0, 51, "CH 0% AIR 0%")
        oled.text(127, 51, "29C", right=True)
    elif page == "Сеть":
        oled.text(0, 0, "Последние услышанные", max_width=96)
        oled.text(127, 0, "3.92V", right=True)
        rows = (
            ("Р", "PDO_Rep_Telemetry", "S+10 R-93"),
            ("Н", "Слон Домашний", "S+7 R-103"),
            ("НД", "Wan9-Omsk-Center", "S+6 R-108"),
        )
        for idx, (role, name, metrics) in enumerate(rows):
            y = 18 + idx * 14
            oled.text(0, y, role)
            metrics_width = oled.text_width(metrics)
            name_x = oled.text_width(role) + 2
            oled.text(name_x, y, name, max_width=126 - name_x - metrics_width - 2)
            oled.text(127, y, metrics, right=True)
    elif page == "Чат":
        oled.text(0, 0, "Слон Домашний", max_width=94)
        oled.text(127, 0, "12:41", right=True)
        oled.text(0, 16, "Проверка сообщения:", max_width=126)
        oled.text(0, 29, "кириллица читается", max_width=126)
        oled.text(0, 42, "и размер сопоставим.", max_width=126)
        oled.text(127, 54, "2/8", right=True)
    elif page == "Popup":
        oled.text(0, 0, "Новое ЛС", max_width=90)
        oled.battery(112, 0, 35)
        oled.popup("Слон Домашний", "Встречаемся в 18:30")
    elif page == "Настройки":
        oled.text(64, 3, "Защита АКБ", center=True, max_width=124)
        oled.text(0, 20, "Статус: ВКЛ")
        oled.text(0, 33, "Порог: 2.80V")
        oled.text(0, 46, "клик: изменить")
        oled.text(127, 56, style[0], right=True)
    else:
        oled.text(0, 0, "Длинное имя пользователя", max_width=126)
        oled.text(0, 17, "имя пользователя Омск", max_width=126)
        oled.text(0, 34, "пользователя Омск Центр", max_width=126)
        oled.text(0, 51, "Омск Центр Ретранслятор", max_width=126)

    return oled.img.resize((W * SCALE, H * SCALE), Image.Resampling.NEAREST), oled.overflows


def main() -> None:
    cell_w = W * SCALE
    cell_h = H * SCALE
    out_w = ROW_LABEL + len(PAGES) * cell_w + (len(PAGES) - 1) * GAP
    out_h = COL_LABEL + len(STYLES) * cell_h + (len(STYLES) - 1) * GAP
    sheet = Image.new("RGB", (out_w, out_h), "#15171a")
    draw = ImageDraw.Draw(sheet)
    errors: list[str] = []

    for col, page in enumerate(PAGES):
        x = ROW_LABEL + col * (cell_w + GAP)
        draw.text((x + 4, 1), clean_text(page), font=FONT_LABEL, fill="#f3f5f7")

    for row, style in enumerate(STYLES):
        y = COL_LABEL + row * (cell_h + GAP)
        draw.text((4, y + 8), style[0], font=FONT_LABEL, fill="#f3f5f7")
        draw.text((4, y + 28), f"{style[1]}px", font=FONT_LABEL, fill="#8dd9ff")
        for col, page in enumerate(PAGES):
            x = ROW_LABEL + col * (cell_w + GAP)
            preview, overflows = draw_page(style, page)
            errors.extend(f"{page}: {error}" for error in overflows)
            sheet.paste(preview.convert("RGB"), (x, y))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(OUT)
    print(f"Saved {OUT}")
    print(f"Checked {len(STYLES) * len(PAGES)} OLED page/style combinations")
    if errors:
        print("Overflow notes:")
        for error in errors:
            print(f"- {error}")


def make_compact_matrix() -> None:
    cell_w = W * SCALE
    cell_h = H * SCALE
    out_w = ROW_LABEL + len(COMPACT_CASES) * cell_w + (len(COMPACT_CASES) - 1) * GAP
    out_h = COL_LABEL + len(STYLES) * cell_h + (len(STYLES) - 1) * GAP
    sheet = Image.new("RGB", (out_w, out_h), "#15171a")
    draw = ImageDraw.Draw(sheet)
    errors: list[str] = []

    for col, (case_name, _, _, _) in enumerate(COMPACT_CASES):
        x = ROW_LABEL + col * (cell_w + GAP)
        draw.text((x + 4, 1), case_name, font=FONT_LABEL, fill="#f3f5f7")

    for row, style in enumerate(STYLES):
        y = COL_LABEL + row * (cell_h + GAP)
        draw.text((4, y + 8), style[0], font=FONT_LABEL, fill="#f3f5f7")
        draw.text((4, y + 28), f"{style[1]}px", font=FONT_LABEL, fill="#8dd9ff")
        for col, (case_name, title, rows, selected) in enumerate(COMPACT_CASES):
            oled = Oled(style)
            oled.compact_settings(title, rows, selected)
            errors.extend(f"{case_name}: {error}" for error in oled.overflows)
            preview = oled.img.resize((cell_w, cell_h), Image.Resampling.NEAREST)
            x = ROW_LABEL + col * (cell_w + GAP)
            sheet.paste(preview.convert("RGB"), (x, y))

    COMPACT_OUT.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(COMPACT_OUT)
    print(f"Saved {COMPACT_OUT}")
    print(f"Checked {len(STYLES) * len(COMPACT_CASES)} compact OLED combinations")
    if errors:
        print("Compact overflow notes:")
        for error in errors:
            print(f"- {error}")


if __name__ == "__main__":
    main()
    make_compact_matrix()
