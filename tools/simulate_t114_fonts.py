# -*- coding: utf-8 -*-
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from generate_t096_design_bitmap_fonts import render_glyph


ROOT = Path(__file__).resolve().parents[1]
NOTO_SRC = ROOT / "tools" / "font_sources" / "noto_sans_2_015"
READABLE_SRC = ROOT / "tools" / "font_sources" / "ui_readable_10"
OUT = ROOT / "qa_outputs" / "t114_fonts" / "T114_SMARTUI_PS17_MATRIX.png"

LOG_W = 128
LOG_H = 64
PHYS_W = 240
PHYS_H = 135
SCALE_X = 1.875
SCALE_Y = 2.109375
Y_OFFSET = 1

COL_LABEL_H = 20
ROW_LABEL_W = 92
GAP = 8

COLORS = {
    "bg": "#20141f",
    "panel": "#15141c",
    "grid": "#4d3948",
    "light": "#f7f2c8",
    "muted": "#a7b0c1",
    "green": "#45f0a1",
    "yellow": "#f6e96b",
    "orange": "#ffb347",
    "red": "#ff5b62",
    "blue": "#62d8ff",
}

FONT_FAMILIES = {
    "Roboto": (READABLE_SRC / "RobotoCondensed-wght.ttf", [430]),
    "Noto": (NOTO_SRC / "NotoSans-CondensedMedium.ttf", None),
    "OpenSans": (READABLE_SRC / "OpenSans-wdth-wght.ttf", [540, 92]),
    "PT Narrow": (READABLE_SRC / "PTSansNarrow-Bold.ttf", None),
    "Oswald": (READABLE_SRC / "Oswald-wght.ttf", [440]),
}

PROFILES = [
    ("Roboto L", "Roboto", 18, 24),
    ("Noto L", "Noto", 18, 24),
    ("OpenSans L", "OpenSans", 18, 24),
    ("PT Narrow L", "PT Narrow", 18, 24),
    ("Oswald L", "Oswald", 18, 24),
    ("Roboto XL", "Roboto", 19, 25),
    ("OpenSans XL", "OpenSans", 19, 25),
    ("Oswald XL", "Oswald", 19, 25),
    ("Noto XXL", "Noto", 20, 26),
    ("PT Narrow XXL", "PT Narrow", 20, 26),
]

PAGES = [
    "Часы", "Компакт", "Избр", "Звук", "Мелодии", "Система", "Статус", "Тест",
    "Зуммер", "8-bit", "Громк", "Резон", "Сеть", "Чат", "Иконки", "Popup",
]


def load_font(family: str, px_size: int) -> ImageFont.FreeTypeFont:
    path, axes = FONT_FAMILIES[family]
    font = ImageFont.truetype(str(path), size=px_size)
    if axes and hasattr(font, "set_variation_by_axes"):
        try:
            font.set_variation_by_axes(axes)
        except Exception:
            pass
    return font


class FirmwareT114Font:
    def __init__(self, family: str, px_size: int, height: int, ascent: int, descent: int):
        path, axes = FONT_FAMILIES[family]
        self.font = ImageFont.truetype(str(path), size=px_size)
        if axes and hasattr(self.font, "set_variation_by_axes"):
            self.font.set_variation_by_axes(axes)
        self.height = height
        self.ascent = ascent
        self.descent = descent
        self.glyphs = {}

    def glyph(self, char: str):
        cp = ord(char)
        if cp not in self.glyphs:
            self.glyphs[cp] = render_glyph(
                self.font, cp, self.ascent, self.descent, self.height, antialias_threshold=92
            )
        return self.glyphs[cp]

    def width_logical(self, text: str) -> int:
        return sum(max(1, math.ceil(self.glyph(char)["x_advance"] / SCALE_X)) for char in text)

    def draw_logical(self, draw: ImageDraw.ImageDraw, x: int, y: int, text: str, fill: str):
        cursor_x = int(x * SCALE_X)
        top = int(y * SCALE_Y) + Y_OFFSET
        for char in text:
            glyph = self.glyph(char)
            for row in range(glyph["height"]):
                for col in range(glyph["width"]):
                    byte = glyph["data"][row * glyph["row_bytes"] + col // 8]
                    if byte & (1 << (col & 7)):
                        draw.point((cursor_x + glyph["x_offset"] + col, top + row), fill=fill)
            cursor_x += glyph["x_advance"]


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def shorten(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_px: int) -> str:
    if text_size(draw, text, font)[0] <= max_px:
        return text
    ell = "…"
    out = text
    while out and text_size(draw, out + ell, font)[0] > max_px:
        out = out[:-1]
    return (out + ell) if out else ell


class T114Preview:
    def __init__(self, profile: tuple[str, str, int, int]):
        self.name, self.family, self.size_px, self.height_px = profile
        self.img = Image.new("RGB", (PHYS_W, PHYS_H), COLORS["bg"])
        self.draw = ImageDraw.Draw(self.img)
        self.font1 = FirmwareT114Font(
            self.family, self.size_px, self.height_px, self.height_px - 4, 4
        )
        self.compact_font = FirmwareT114Font(self.family, 18, 22, 18, 4)
        self.clock_font = FirmwareT114Font("Roboto", 28, 36, 30, 6)
        self.overflow: list[str] = []

    def px(self, x: int, y: int) -> tuple[int, int]:
        return int(x * SCALE_X), int(y * SCALE_Y) + Y_OFFSET

    def logical_line_h(self, mult: int = 1) -> int:
        if mult > 1:
            return max(1, math.ceil(36 / SCALE_Y))
        return max(1, math.ceil(self.height_px / SCALE_Y))

    def status_icon_size(self) -> int:
        line_h = self.logical_line_h()
        size = line_h - 1
        if size < 9:
            return 9
        if size > 12:
            return 12
        return size

    def line_icon_size(self) -> int:
        line_h = self.logical_line_h()
        if line_h >= 18:
            return 14
        if line_h > 8:
            size = line_h - 1
            if size < 9:
                size = 9
            if size > 12:
                size = 12
            return size
        return 8

    def clear(self):
        self.draw.rectangle((0, 0, PHYS_W, PHYS_H), fill=COLORS["bg"])
        self.draw.rectangle((0, 0, PHYS_W - 1, PHYS_H - 1), outline=COLORS["grid"])

    def font(self, mult: int = 1) -> FirmwareT114Font:
        return self.clock_font if mult > 1 else self.font1

    def text_w_log(self, text: str, mult: int = 1, small: bool = False) -> int:
        return self.font(mult).width_logical(text)

    def text(self, x: int, y: int, value: str, color: str = "light", max_w: int | None = None,
             mult: int = 1, center: bool = False, right: bool = False, small: bool = False):
        font = self.font(mult)
        max_logical = max_w if max_w is not None else LOG_W
        shown = value
        if font.width_logical(shown) > max_logical:
            ellipsis = "..."
            while shown and font.width_logical(shown + ellipsis) > max_logical:
                shown = shown[:-1]
            shown = (shown + ellipsis) if shown else ellipsis
        logical_w = font.width_logical(shown)
        if center:
            x -= logical_w // 2
        if right:
            x -= logical_w
        px_x, px_y = self.px(x, y)
        if px_x < 0 or x + logical_w > LOG_W or px_y < 0 or px_y + font.height > PHYS_H:
            self.overflow.append(f"{self.name}: text '{value}' at {x},{y}")
        font.draw_logical(self.draw, x, y, shown, COLORS[color])

    def rect(self, x: int, y: int, w: int, h: int, color: str = "grid", fill: str | None = None):
        x1, y1 = self.px(x, y)
        x2, y2 = self.px(x + w, y + h)
        self.draw.rectangle((x1, y1, x2, y2), outline=COLORS[color], fill=COLORS[fill] if fill else None)

    def icon(self, x: int, y: int, kind: str, size_log: int, color: str):
        x1, y1 = self.px(x, y)
        x2, y2 = self.px(x + size_log, y + size_log)
        w = max(4, x2 - x1)
        h = max(4, y2 - y1)
        c = COLORS[color]
        lw = max(1, min(w, h) // 10)
        if kind == "battery":
            self.draw.rectangle((x1, y1 + h // 4, x1 + w - 4, y1 + (h * 3) // 4), outline=c, width=lw)
            self.draw.rectangle((x1 + w - 3, y1 + h // 3, x1 + w - 1, y1 + (h * 2) // 3), fill=c)
            self.draw.rectangle((x1 + 3, y1 + h // 4 + 3, x1 + w - 8, y1 + (h * 3) // 4 - 3), fill=c)
        elif kind == "mute":
            self.draw.polygon((x1 + 1, y1 + h // 2 - 2, x1 + w // 3, y1 + h // 2 - 2,
                               x1 + w // 2, y1 + h // 3, x1 + w // 2, y1 + (h * 2) // 3,
                               x1 + w // 3, y1 + h // 2 + 2, x1 + 1, y1 + h // 2 + 2), outline=c)
            self.draw.line((x1 + 2, y1 + h - 2, x1 + w - 2, y1 + 2), fill=c, width=lw)
        elif kind == "gps":
            body = (x1 + (w * 5) // 12, y1 + (h * 4) // 12, x1 + (w * 8) // 12, y1 + (h * 7) // 12)
            self.draw.rectangle(body, fill=c)
            self.draw.rectangle((x1 + 1, y1 + (h * 4) // 12, x1 + (w * 4) // 12, y1 + (h * 6) // 12), fill=c)
            self.draw.rectangle((x1 + (w * 9) // 12, y1 + (h * 4) // 12, x1 + w - 1, y1 + (h * 6) // 12), fill=c)
            self.draw.line((x1 + w // 2, y1 + (h * 4) // 12, x1 + w // 2, y1 + 1), fill=c, width=lw)
            for px, py in ((7, 1), (9, 0), (10, 2)):
                dx = x1 + (w * px) // 12
                dy = y1 + (h * py) // 12
                self.draw.rectangle((dx, dy, dx + lw, dy + lw), fill=c)
            self.draw.line((x1 + (w * 5) // 12, y1 + (h * 8) // 12, x1 + (w * 5) // 12, y1 + h - 1), fill=c, width=lw)
            self.draw.line((x1 + (w * 7) // 12, y1 + (h * 8) // 12, x1 + (w * 7) // 12, y1 + h - 1), fill=c, width=lw)
        elif kind == "home":
            self.draw.polygon((x1 + 1, y1 + h // 2, x1 + w // 2, y1 + 1, x1 + w - 1, y1 + h // 2), outline=c)
            self.draw.rectangle((x1 + w // 4, y1 + h // 2, x1 + (w * 3) // 4, y1 + h - 2), outline=c, width=lw)
            self.draw.rectangle((x1 + w // 2 - 2, y1 + (h * 2) // 3, x1 + w // 2 + 1, y1 + h - 2), fill=c)
        elif kind == "tower":
            self.draw.line((x1 + w // 2, y1 + 2, x1 + w // 2, y1 + h - 2), fill=c, width=lw)
            self.draw.line((x1 + 3, y1 + h - 2, x1 + w - 3, y1 + h - 2), fill=c, width=lw)
            self.draw.line((x1 + w // 4, y1 + h // 2, x1 + (w * 3) // 4, y1 + h // 2), fill=c, width=lw)
            self.draw.arc((x1 + 1, y1, x1 + w - 1, y1 + h // 2), 200, 340, fill=c, width=lw)
        elif kind == "pager":
            self.draw.rectangle((x1 + 1, y1 + 2, x1 + w - 1, y1 + h - 2), outline=c, width=lw)
            self.draw.rectangle((x1 + 4, y1 + 5, x1 + w - 4, y1 + h // 2), fill=c)
            for bx in (4, 7, 10):
                if x1 + bx < x1 + w - 1:
                    self.draw.rectangle((x1 + bx, y1 + h - 5, x1 + bx + 1, y1 + h - 4), fill=c)
        elif kind == "signal":
            self.draw.rectangle((x1 + 2, y1 + (h * 3) // 4, x1 + 4, y1 + h - 1), fill=c)
            self.draw.rectangle((x1 + w // 2 - 1, y1 + h // 2, x1 + w // 2 + 1, y1 + h - 1), fill=c)
            self.draw.rectangle((x1 + w - 4, y1 + h // 4, x1 + w - 2, y1 + h - 1), fill=c)
        elif kind == "msg":
            self.draw.rectangle((x1 + 1, y1 + h // 4, x1 + w - 2, y1 + (h * 3) // 4), outline=c, width=lw)
            self.draw.line((x1 + 2, y1 + h // 4 + 1, x1 + w // 2, y1 + h // 2), fill=c, width=lw)
            self.draw.line((x1 + w - 3, y1 + h // 4 + 1, x1 + w // 2, y1 + h // 2), fill=c, width=lw)
        elif kind == "relay":
            pts = [(x1 + 2, y1 + 3), (x1 + w - 4, y1 + 3), (x1 + w // 2, y1 + h - 4)]
            self.draw.line((pts[0], pts[2]), fill=c, width=lw)
            self.draw.line((pts[1], pts[2]), fill=c, width=lw)
            for px, py in pts:
                self.draw.rectangle((px - 1, py - 1, px + 2, py + 2), fill=c)
        elif kind == "face":
            self.draw.arc((x1 + 1, y1 + 1, x1 + w - 1, y1 + h - 1), 0, 360, fill=c, width=lw)
            self.draw.rectangle((x1 + w // 3, y1 + h // 3, x1 + w // 3 + 1, y1 + h // 3 + 2), fill=c)
            self.draw.rectangle((x1 + (w * 2) // 3, y1 + h // 3, x1 + (w * 2) // 3 + 1, y1 + h // 3 + 2), fill=c)
            self.draw.arc((x1 + w // 3, y1 + h // 2, x1 + (w * 2) // 3, y1 + h - 2), 10, 170, fill=c, width=lw)
        elif kind == "warn":
            self.draw.polygon((x1 + w // 2, y1 + 1, x1 + w - 2, y1 + h - 2, x1 + 2, y1 + h - 2), outline=c)
            self.draw.line((x1 + w // 2, y1 + h // 3, x1 + w // 2, y1 + (h * 2) // 3), fill=c, width=lw)
            self.draw.rectangle((x1 + w // 2, y1 + h - 4, x1 + w // 2 + 1, y1 + h - 3), fill=c)
        else:
            self.draw.ellipse((x1 + 1, y1 + 1, x1 + w - 1, y1 + h - 1), outline=c, width=lw)

    def rich(self, x: int, y: int, value: str, color: str = "light", max_w: int | None = None):
        parts = value.split(" ")
        cursor = x
        max_right = x + (max_w if max_w is not None else LOG_W)
        for part in parts:
            if part in ("[home]", "🏠"):
                self.icon(cursor, y, "home", self.line_icon_size(), color)
                cursor += self.line_icon_size() + 2
            elif part == "[sat]":
                self.icon(cursor, y, "gps", self.line_icon_size(), color)
                cursor += self.line_icon_size() + 2
            elif part in (":)", "[face]"):
                self.icon(cursor, y, "face", self.line_icon_size(), color)
                cursor += self.line_icon_size() + 2
            elif part == "[msg]":
                self.icon(cursor, y, "msg", self.line_icon_size(), color)
                cursor += self.line_icon_size() + 2
            elif part == "[warn]":
                self.icon(cursor, y, "warn", self.line_icon_size(), color)
                cursor += self.line_icon_size() + 2
            else:
                remaining = max_right - cursor
                if remaining <= 0:
                    return
                word = part + " "
                self.text(cursor, y, word, color=color, max_w=remaining)
                cursor += self.text_w_log(word)

    def chrome(self, title: str, muted: bool = True, clock: bool = False):
        self.rect(0, 0, LOG_W, 10, fill="panel")
        icon_size = self.status_icon_size()
        battery_x = 112
        self.icon(battery_x, 1, "battery", 13, "green")
        muted_x = battery_x
        if muted and not clock:
            muted_x = battery_x - icon_size - 3
            self.icon(muted_x, 2, "mute", icon_size, "red")
        voltage_w = self.text_w_log("4.09V")
        voltage_x = muted_x - voltage_w - 3
        self.text(voltage_x, 0, "4.09V", "green", max_w=voltage_w + 2)
        max_title = max(18, voltage_x - 2)
        self.text(0, 0, title, "green", max_w=max_title)

    def page_clock(self):
        self.clear()
        self.chrome("ANX T114", muted=True, clock=True)
        self.text(LOG_W // 2, 17, "12:34", "green", mult=2, center=True, max_w=LOG_W)
        clock_w = self.text_w_log("12:34", mult=2)
        side_size = self.status_icon_size()
        side_y = 21
        left_x = LOG_W // 2 - clock_w // 2 - side_size - 5
        if left_x >= 1:
            self.icon(left_x, side_y, "mute", side_size, "red")
        right_x_status = LOG_W // 2 + clock_w // 2 + 5
        if right_x_status + side_size + self.text_w_log("7") + 2 < LOG_W:
            self.icon(right_x_status, side_y, "gps", side_size, "green")
            self.text(right_x_status + side_size + 2, side_y - 1, "7", "green", max_w=8)
        if self.logical_line_h() < 13:
            self.text(LOG_W // 2, 34, "21.08.2026", "muted", center=True, max_w=LOG_W)
        self.text(0, 45, "Н:3", "red", max_w=22)
        right_x = 127
        self.text(right_x, 45, "29C", "green", right=True, max_w=24)
        right_x -= self.text_w_log("29C") + 4
        self.text(24, 45, "MSG/h 5", "yellow", max_w=max(18, right_x - 24))

    def page_menu(self):
        self.clear()
        self.chrome("Настройки", muted=False)
        y = 16
        for color, label in [
            ("green", "Шрифт: " + self.name),
            ("yellow", "Пин вибро: D9"),
            ("light", "Авто-анонс: 30 мин"),
        ]:
            self.text(1, y, label, color, max_w=126)
            y += max(13, self.logical_line_h() + 3)

    def compact_rows(self, title, rows, selected, start=0):
        self.clear()
        saved_font = self.font1
        self.font1 = self.compact_font
        self.chrome("ANX T114", muted=False)
        self.text(1, 14, title, "green", max_w=91)
        self.text(127, 14, "<>OK", "green", right=True, max_w=34)
        y = 28
        visible = rows[start:start + 3]
        for offset, (label, value) in enumerate(visible):
            index = start + offset
            color = "yellow" if index == selected else "light"
            prefix = ">" if index == selected else ""
            if prefix:
                self.text(0, y, prefix, color, max_w=7)
            self.text(8 if prefix else 2, y, label, color, max_w=70)
            if value:
                self.text(76, y, value, "yellow" if index == selected else "green", max_w=49)
            y += 12
        if len(rows) > 3:
            track_y, track_h = 28, 36
            self.rect(126, track_y, 2, track_h, fill="panel")
            thumb_h = max(4, track_h * 3 // len(rows))
            max_start = len(rows) - 3
            thumb_y = track_y + (track_h - thumb_h) * min(start, max_start) // max_start
            self.rect(126, thumb_y, 2, thumb_h, fill="green")
        self.font1 = saved_font

    def page_compact_hub(self):
        self.compact_rows(
            "Настройки",
            [
                ("Избранное", "3"),
                ("Уведомления", "Звук"),
                ("Звук и вибро", "МАКС"),
                ("Экран", "Noto XXL"),
                ("Радио и GPS", "GPS ВКЛ"),
                ("Система", "SmartUI"),
                ("Закрыть", ""),
            ],
            1,
        )

    def page_compact_favorites(self):
        self.compact_rows(
            "Избранное",
            [
                ("Уведомления", "Звук"),
                ("Мелодия системы", "Лебеди"),
                ("Bluetooth", "ВКЛ"),
                ("Назад", ""),
            ],
            0,
        )

    def page_compact_sound(self):
        self.compact_rows(
            "Звук и вибро",
            [
                ("Мелодия", "Лебеди"),
                ("Стиль", "8-bit"),
                ("Громкость", "МАКС"),
                ("Резонанс", "3000 Гц"),
            ],
            0,
        )

    def page_tone_picker(self):
        self.compact_rows(
            "Мелодия",
            [
                ("Пинг", ""),
                ("Дубль", ""),
                ("Рост", ""),
                ("Мягкая", ""),
                ("Ода короткая", ""),
                ("Аркада", ""),
                ("Лифт", ""),
                ("Nova", ""),
                ("Radar", ""),
                ("Лебеди", "ВЫБРАНА"),
                ("Назад", ""),
            ],
            9,
            7,
        )

    def page_compact_system(self):
        self.compact_rows(
            "Система",
            [
                ("Bluetooth", "ВКЛ"),
                ("LED платы", "ВКЛ"),
                ("Избранное 1", "Уведомл."),
                ("Избранное 2", "Мелодия"),
                ("Избранное 3", "Состояние"),
                ("Отменить", "ГОТОВО"),
                ("Состояние", ""),
                ("Тест оборудования", ""),
            ],
            6,
            5,
        )

    def page_device_status(self):
        self.compact_rows(
            "Состояние",
            [
                ("АКБ 4.096В", "BLE"),
                ("RSSI -72", "SNR 8.2"),
                ("GPS ВКЛ", "FEM НЕТ"),
            ],
            -1,
        )

    def page_hardware_test(self):
        self.compact_rows(
            "Тест оборудования",
            [
                ("Шаг 5/7", "АКБ / АЦП"),
                ("OK", "следующий"),
                ("<>", "назад"),
            ],
            0,
        )

    def page_tone_bridge(self):
        self.clear()
        self.chrome("ANX T114", muted=False)
        self.text(LOG_W // 2, 18, "Схема зуммера", "green", center=True, max_w=LOG_W)
        self.text(1, 34, "Режим: МОСТ", "green", max_w=126)
        self.text(1, 50, "D13 <-> D16", "yellow", max_w=126)

    def page_tone_style(self):
        self.clear()
        self.chrome("ANX T114", muted=False)
        self.text(LOG_W // 2, 18, "Стиль звука", "green", center=True, max_w=LOG_W)
        self.text(1, 34, "Режим: 8-bit", "green", max_w=126)
        self.text(1, 50, "ретро-арпеджио", "yellow", max_w=126)

    def page_tone_drive(self):
        self.clear()
        self.chrome("ANX T114", muted=False)
        self.text(LOG_W // 2, 18, "Громкость GPIO", "green", center=True, max_w=LOG_W)
        self.text(1, 34, "Режим: МАКСИМУМ", "green", max_w=126)
        self.text(1, 50, "усиленный выход", "yellow", max_w=126)

    def page_tone_resonance(self):
        self.clear()
        self.chrome("ANX T114", muted=False)
        self.text(LOG_W // 2, 18, "Резонанс пьезо", "green", center=True, max_w=LOG_W)
        self.text(1, 34, "Частота: 3000 Гц", "green", max_w=126)
        self.text(1, 50, "нажать и слушать", "yellow", max_w=126)

    def page_network(self):
        self.clear()
        self.chrome("Сеть", muted=False)
        y = 16
        rows = [
            ("РД", "yellow", "слон ретранслятор длинный", "S+13 R-40", "green"),
            ("НД", "green", "Wan1 T114 очень длинная нода", "S+8 R-72", "green"),
            ("Н", "green", "пейджер дом дальний", "S-9 R-122", "red"),
        ]
        row_h = max(13, self.logical_line_h() + 3)
        for label, label_color, name, metric, metric_color in rows:
            metric_w = self.text_w_log(metric)
            self.text(LOG_W, y, metric, metric_color, right=True, max_w=metric_w)
            label_w = self.text_w_log(label)
            self.text(0, y, label, label_color, max_w=label_w + 1)
            name_x = label_w + 2
            self.rich(name_x, y, name, label_color, max_w=max(10, LOG_W - metric_w - name_x - 2))
            y += row_h

    def page_chat(self):
        self.clear()
        y = 2
        row_h = max(13, self.logical_line_h() + 3)
        for color, line in [
            ("green", ":) [home] слон: тест дома"),
            ("yellow", "[msg] [sat] ретр: путь найден"),
            ("light", "Bog1: Архипоскуин..."),
            ("red", "[warn] R-102 слабый сигнал"),
        ]:
            self.rich(1, y, line, color, max_w=126)
            y += row_h

    def page_icons(self):
        self.clear()
        self.chrome("Иконки", muted=True)
        size = self.line_icon_size()
        y = 15
        rows = [
            [("face", "green"), ("home", "green"), ("msg", "yellow"), ("gps", "green"), ("mute", "red")],
            [("tower", "yellow"), ("pager", "green"), ("relay", "yellow"), ("signal", "red"), ("warn", "red")],
        ]
        labels = ["смайлы / ЛС", "ретр / пейджер"]
        for row, label in zip(rows, labels):
            x = 2
            for kind, color in row:
                self.icon(x, y, kind, size, color)
                x += size + 4
            self.text(x + 1, y - 1, label, "light", max_w=LOG_W - x - 2)
            y += max(14, self.logical_line_h() + 8)

    def page_popup(self):
        self.page_chat()
        line_h = self.logical_line_h()
        text = "Сеть"
        pad_x = 5
        pad_y = 3
        box_w = min(LOG_W - 4, self.text_w_log(text) + pad_x * 2)
        box_h = min(LOG_H - 4, line_h + pad_y * 2)
        x = (LOG_W - box_w) // 2
        y = (LOG_H - box_h) // 2
        self.rect(x, y, box_w, box_h, color="green", fill="bg")
        self.text(LOG_W // 2, y + pad_y, text, "green", center=True, max_w=box_w - pad_x * 2)


def render_matrix() -> tuple[Image.Image, list[str]]:
    label_font = load_font("Roboto", 16)
    sheet_w = ROW_LABEL_W + len(PAGES) * PHYS_W + (len(PAGES) + 1) * GAP
    sheet_h = COL_LABEL_H + len(PROFILES) * PHYS_H + (len(PROFILES) + 1) * GAP
    sheet = Image.new("RGB", (sheet_w, sheet_h), "#0e1018")
    draw = ImageDraw.Draw(sheet)
    overflows: list[str] = []

    for col, page in enumerate(PAGES):
        x = ROW_LABEL_W + GAP + col * (PHYS_W + GAP)
        draw.text((x, 2), page, font=label_font, fill=COLORS["muted"])

    for row, profile in enumerate(PROFILES):
        y = COL_LABEL_H + GAP + row * (PHYS_H + GAP)
        preview = T114Preview(profile)
        label = f"{preview.name} h={preview.logical_line_h()} i={preview.line_icon_size()}/{preview.status_icon_size()}"
        draw.text((4, y + 4), label, font=label_font, fill=COLORS["muted"])
        for col, page in enumerate(PAGES):
            preview = T114Preview(profile)
            if page == "Часы":
                preview.page_clock()
            elif page == "Компакт":
                preview.page_compact_hub()
            elif page == "Избр":
                preview.page_compact_favorites()
            elif page == "Звук":
                preview.page_compact_sound()
            elif page == "Мелодии":
                preview.page_tone_picker()
            elif page == "Система":
                preview.page_compact_system()
            elif page == "Статус":
                preview.page_device_status()
            elif page == "Тест":
                preview.page_hardware_test()
            elif page == "Зуммер":
                preview.page_tone_bridge()
            elif page == "8-bit":
                preview.page_tone_style()
            elif page == "Громк":
                preview.page_tone_drive()
            elif page == "Резон":
                preview.page_tone_resonance()
            elif page == "Сеть":
                preview.page_network()
            elif page == "Чат":
                preview.page_chat()
            elif page == "Иконки":
                preview.page_icons()
            else:
                preview.page_popup()
            x = ROW_LABEL_W + GAP + col * (PHYS_W + GAP)
            sheet.paste(preview.img, (x, y))
            overflows.extend([f"{page}: {item}" for item in preview.overflow])
    return sheet, overflows


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    sheet, overflows = render_matrix()
    sheet.save(OUT)
    print(OUT)
    for profile in PROFILES:
        preview = T114Preview(profile)
        print(
            f"{preview.name}: line_h={preview.logical_line_h()} "
            f"line_icon={preview.line_icon_size()} status_icon={preview.status_icon_size()}"
        )
    if overflows:
        print("WARN overflow candidates:")
        for item in overflows[:40]:
            print("  " + item)


if __name__ == "__main__":
    main()
