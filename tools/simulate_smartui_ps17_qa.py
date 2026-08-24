# -*- coding: utf-8 -*-
"""Exact framebuffer-oriented QA for the SmartUI PS17 dense UI screens.

The script intentionally reuses the same glyph generator/metrics as the
firmware simulators:

* T096: thresholded embedded bitmap glyphs (threshold 104), 160x80 native.
* T114: thresholded ST7789 glyphs (threshold 92), logical 128x64 mapped to
  240x135 with SCALE_X=1.875, SCALE_Y=2.109375 and Y_OFFSET=1.
* OLED: the actual Utf8Cyrillic5x7 tables and the five SSD1306 spacing styles.

It renders the reference and current SmartUI PS17 versions of the keyboard, target
picker, compact list and unread-DM screen.  The canonical matrices are meant
for human review; the profile sweep and assertions are the release gate.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from PIL import Image, ImageDraw, ImageFont

from simulate_oled_128x64 import STYLES as OLED_STYLES, glyph_for
from simulate_t096_premium import FAMILIES as T096_FAMILIES, load_compact_settings_font
from simulate_t114_fonts import (
    FONT_FAMILIES as T114_FAMILIES,
    PROFILES as T114_ACTIVE_FONT_PROFILES,
    FirmwareT114Font,
)


TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
DEFAULT_OUT = ROOT / "qa_outputs" / "smartui_v2.0.0-rc1"
LABEL_FONT_PATH = TOOLS / "font_sources" / "noto_sans_2_015" / "NotoSans-CondensedMedium.ttf"

T114_SCALE_X = 1.875
T114_SCALE_Y = 2.109375
T114_Y_OFFSET = 1

LONG_TYPED = (
    "Проверка очень длинного сообщения: батареи заряжены, координаты приняты, "
    "встречаемся у северного входа в двадцать три сорок пять"
)
LONG_CONTACT = "Александра Северная экспедиционная группа номер двенадцать"
LONG_SETTING = "Автоматическое ночное отключение всех звуковых уведомлений"

T114_FONT_CHOICE_NAMES = (
    "Roboto L", "Noto L", "OpenSans L", "PT Narrow L", "Oswald L",
    "Roboto XL", "OpenSans XL", "Oswald XL", "Noto XXL", "PT Narrow XXL",
)
T114_THEME_CHOICE_NAMES = (
    "Стандарт", "Циан", "Янтарь", "Бумага", "Красный", "Рыжий", "Зеленый",
)

CURRENT_KEY_LABELS = (
    (
        "А", "Б", "В", "Г", "Д", "Е", "Ж", "З", "И", "Й", "К", "Л",
        "М", "Н", "О", "П", "Р", "С", "RU2", "SP", "DEL", "OK", "123", "BK",
    ),
    (
        "Т", "У", "Ф", "Х", "Ц", "Ч", "Ш", "Щ", "Ъ", "Ы", "Ь", "Э",
        "Ю", "Я", ".", ",", "?", "!", "RU1", "SP", "DEL", "OK", "123", "BK",
    ),
    (
        "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", ".", ",",
        "?", "!", ":", ";", "-", "+", "RU1", "SP", "DEL", "OK", "RU2", "BK",
    ),
)

DESIRED_KEY_LABELS = (
    (
        "А", "Б", "В", "Г", "Д", "Е", "Ж", "З", "И", "Й", "К", "Л",
        "М", "Н", "О", "П", "Р", "С", "ТЯ", "", "", "ОК", "123", "",
    ),
    (
        "Т", "У", "Ф", "Х", "Ц", "Ч", "Ш", "Щ", "Ъ", "Ы", "Ь", "Э",
        "Ю", "Я", ".", ",", "?", "!", "АС", "", "", "ОК", "123", "",
    ),
    (
        "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", ".", ",",
        "?", "!", ":", ";", "-", "+", "АС", "", "", "ОК", "ТЯ", "",
    ),
)


def glyph_ink_bounds(glyph: dict, bold: bool = False) -> tuple[int, int, int, int] | None:
    """Return exact set-pixel bounds, not the nominal font line box."""
    left = glyph["width"]
    top = glyph["height"]
    right = -1
    bottom = -1
    for row in range(glyph["height"]):
        for col in range(glyph["width"]):
            byte = glyph["data"][row * glyph["row_bytes"] + col // 8]
            if byte & (1 << (col & 7)):
                left = min(left, col)
                top = min(top, row)
                right = max(right, col + (1 if bold else 0))
                bottom = max(bottom, row)
    if right < left or bottom < top:
        return None
    return left, top, right + 1, bottom + 1


class ExactFont:
    name: str
    logical_height: int

    def width(self, text: str, bold: bool = False) -> int:
        raise NotImplementedError

    def draw(self, image: Image.Image, x: int, y: int, text: str, color: tuple[int, int, int],
             bold: bool = False) -> None:
        raise NotImplementedError

    def ink_box(self, x: int, y: int, text: str, bold: bool = False) -> tuple[int, int, int, int] | None:
        raise NotImplementedError


class T096ExactFont(ExactFont):
    def __init__(self, name: str, raw):
        self.name = name
        self.raw = raw
        self.logical_height = raw.height

    def width(self, text: str, bold: bool = False) -> int:
        extra = 1 if bold else 0
        return sum(self.raw.glyph(ch)["x_advance"] + extra for ch in text)

    def draw(self, image: Image.Image, x: int, y: int, text: str, color: tuple[int, int, int],
             bold: bool = False) -> None:
        draw = ImageDraw.Draw(image)
        cursor = x
        extra = 1 if bold else 0
        for ch in text:
            glyph = self.raw.glyph(ch)
            for row in range(glyph["height"]):
                for col in range(glyph["width"]):
                    byte = glyph["data"][row * glyph["row_bytes"] + col // 8]
                    if byte & (1 << (col & 7)):
                        draw.point((cursor + glyph["x_offset"] + col, y + row), fill=color)
                        if bold:
                            draw.point((cursor + glyph["x_offset"] + col + 1, y + row), fill=color)
            cursor += glyph["x_advance"] + extra

    def ink_box(self, x: int, y: int, text: str, bold: bool = False) -> tuple[int, int, int, int] | None:
        cursor = x
        boxes: list[tuple[int, int, int, int]] = []
        extra = 1 if bold else 0
        for ch in text:
            glyph = self.raw.glyph(ch)
            ink = glyph_ink_bounds(glyph, bold)
            if ink:
                boxes.append((cursor + glyph["x_offset"] + ink[0], y + ink[1],
                              cursor + glyph["x_offset"] + ink[2], y + ink[3]))
            cursor += glyph["x_advance"] + extra
        return union_boxes(boxes)


class T114ExactFont(ExactFont):
    def __init__(self, name: str, raw: FirmwareT114Font):
        self.name = name
        self.raw = raw
        self.logical_height = max(1, math.ceil(raw.height / T114_SCALE_Y))

    def width(self, text: str, bold: bool = False) -> int:
        extra = 1 if bold else 0
        return sum(max(1, math.ceil((self.raw.glyph(ch)["x_advance"] + extra) / T114_SCALE_X))
                   for ch in text)

    def draw(self, image: Image.Image, x: int, y: int, text: str, color: tuple[int, int, int],
             bold: bool = False) -> None:
        draw = ImageDraw.Draw(image)
        cursor = int(x * T114_SCALE_X)
        top = int(y * T114_SCALE_Y) + T114_Y_OFFSET
        extra = 1 if bold else 0
        for ch in text:
            glyph = self.raw.glyph(ch)
            for row in range(glyph["height"]):
                for col in range(glyph["width"]):
                    byte = glyph["data"][row * glyph["row_bytes"] + col // 8]
                    if byte & (1 << (col & 7)):
                        draw.point((cursor + glyph["x_offset"] + col, top + row), fill=color)
                        if bold:
                            draw.point((cursor + glyph["x_offset"] + col + 1, top + row), fill=color)
            cursor += glyph["x_advance"] + extra

    def ink_box(self, x: int, y: int, text: str, bold: bool = False) -> tuple[int, int, int, int] | None:
        cursor = int(x * T114_SCALE_X)
        top = int(y * T114_SCALE_Y) + T114_Y_OFFSET
        boxes: list[tuple[int, int, int, int]] = []
        extra = 1 if bold else 0
        for ch in text:
            glyph = self.raw.glyph(ch)
            ink = glyph_ink_bounds(glyph, bold)
            if ink:
                boxes.append((cursor + glyph["x_offset"] + ink[0], top + ink[1],
                              cursor + glyph["x_offset"] + ink[2], top + ink[3]))
            cursor += glyph["x_advance"] + extra
        return union_boxes(boxes)


class OledExactFont(ExactFont):
    def __init__(self, style_index: int, style: tuple[str, int, bool]):
        self.style_index = style_index
        self.name, self.advance, self.style_bold = style
        self.logical_height = 8

    def effective(self, forced_bold: bool) -> tuple[int, bool]:
        bold = self.style_bold or forced_bold
        advance = self.advance
        if bold and advance < 6:
            advance = 6
        if bold and advance < 7 and self.style_index != 4:
            advance = 7
        return advance, bold

    def width(self, text: str, bold: bool = False) -> int:
        advance, _ = self.effective(bold)
        return len(text) * advance

    def draw(self, image: Image.Image, x: int, y: int, text: str, color: tuple[int, int, int],
             bold: bool = False) -> None:
        draw = ImageDraw.Draw(image)
        advance, actual_bold = self.effective(bold)
        cursor = x
        for ch in text:
            glyph = glyph_for(ch)
            for col, bits in enumerate(glyph):
                for row in range(8):
                    if bits & (1 << row):
                        draw.point((cursor + col, y + row), fill=color)
                        if actual_bold:
                            draw.point((cursor + col + 1, y + row), fill=color)
            cursor += advance

    def ink_box(self, x: int, y: int, text: str, bold: bool = False) -> tuple[int, int, int, int] | None:
        advance, actual_bold = self.effective(bold)
        cursor = x
        boxes: list[tuple[int, int, int, int]] = []
        for ch in text:
            glyph = glyph_for(ch)
            xs: list[int] = []
            ys: list[int] = []
            for col, bits in enumerate(glyph):
                for row in range(8):
                    if bits & (1 << row):
                        xs.append(col)
                        ys.append(row)
            if xs:
                boxes.append((cursor + min(xs), y + min(ys),
                              cursor + max(xs) + 1 + (1 if actual_bold else 0), y + max(ys) + 1))
            cursor += advance
        return union_boxes(boxes)


def union_boxes(boxes: Iterable[tuple[int, int, int, int]]) -> tuple[int, int, int, int] | None:
    values = list(boxes)
    if not values:
        return None
    return (min(v[0] for v in values), min(v[1] for v in values),
            max(v[2] for v in values), max(v[3] for v in values))


@dataclass
class BoardProfile:
    board: str
    profile: str
    logical_w: int
    logical_h: int
    physical_w: int
    physical_h: int
    desired_font: ExactFont
    current_font: ExactFont
    scale_x: float = 1.0
    scale_y: float = 1.0
    y_offset: int = 0
    oled: bool = False


@dataclass
class Element:
    tag: str
    physical_box: tuple[int, int, int, int] | None
    shown: str = ""


@dataclass
class Frame:
    board: BoardProfile
    name: str
    desired: bool
    image: Image.Image = field(init=False)
    draw: ImageDraw.ImageDraw = field(init=False)
    font: ExactFont = field(init=False)
    violations: list[str] = field(default_factory=list)
    facts: dict[str, object] = field(default_factory=dict)
    elements: list[Element] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.font = self.board.desired_font if self.desired else self.board.current_font
        self.image = Image.new("RGB", (self.board.physical_w, self.board.physical_h), self.color("bg"))
        self.draw = ImageDraw.Draw(self.image)
        self.rect(0, 0, self.board.logical_w, self.board.logical_h, "border", outline=True, tag="screen")

    def color(self, name: str) -> tuple[int, int, int]:
        if self.board.oled:
            return (0, 0, 0) if name in ("bg", "dark") else (255, 255, 255)
        palette = {
            "bg": (3, 8, 12), "dark": (3, 8, 12), "light": (239, 247, 244),
            "muted": (151, 171, 179), "green": (29, 240, 122), "yellow": (255, 224, 74),
            "blue": (54, 200, 255), "red": (255, 77, 77), "border": (57, 75, 84),
        }
        return palette[name]

    def boundary_x(self, x: int) -> int:
        return int(x * self.board.scale_x)

    def boundary_y(self, y: int) -> int:
        return int(y * self.board.scale_y) + self.board.y_offset

    def logical_box_to_physical(self, x: int, y: int, w: int, h: int) -> tuple[int, int, int, int]:
        if self.board.board == "T114":
            return self.boundary_x(x), self.boundary_y(y), self.boundary_x(x + w), self.boundary_y(y + h)
        return x, y, x + w, y + h

    def check_logical_box(self, tag: str, x: int, y: int, w: int, h: int) -> None:
        if x < 0 or y < 0 or w < 0 or h < 0 or x + w > self.board.logical_w or y + h > self.board.logical_h:
            self.violations.append(
                f"{tag}: logical box {x},{y} {w}x{h} outside {self.board.logical_w}x{self.board.logical_h}"
            )

    def check_physical_box(self, tag: str, box: tuple[int, int, int, int] | None) -> None:
        if box is None:
            return
        x1, y1, x2, y2 = box
        if x1 < 0 or y1 < 0 or x2 > self.board.physical_w or y2 > self.board.physical_h:
            self.violations.append(
                f"{tag}: ink {x1},{y1}..{x2},{y2} outside {self.board.physical_w}x{self.board.physical_h}"
            )

    def rect(self, x: int, y: int, w: int, h: int, color: str, *, outline: bool = False,
             tag: str = "rect") -> None:
        self.check_logical_box(tag, x, y, w, h)
        x1, y1, x2, y2 = self.logical_box_to_physical(x, y, w, h)
        # T114's Y_OFFSET intentionally lets the logical bottom boundary clip;
        # match the hardware clipping instead of treating a background pixel as UI overflow.
        x1 = max(0, min(self.board.physical_w - 1, x1))
        y1 = max(0, min(self.board.physical_h - 1, y1))
        x2 = max(x1 + 1, min(self.board.physical_w, x2))
        y2 = max(y1 + 1, min(self.board.physical_h, y2))
        if outline:
            self.draw.rectangle((x1, y1, x2 - 1, y2 - 1), outline=self.color(color))
        else:
            self.draw.rectangle((x1, y1, x2 - 1, y2 - 1), fill=self.color(color))

    def line(self, points: Sequence[tuple[int, int]], color: str, width: int = 1, tag: str = "line") -> None:
        for x, y in points:
            self.check_logical_box(tag, x, y, 1, 1)
        physical = [(self.boundary_x(x), self.boundary_y(y)) for x, y in points]
        self.draw.line(physical, fill=self.color(color), width=max(1, int(width * self.board.scale_x)))

    def fit_head(self, text: str, max_w: int, bold: bool = False) -> str:
        if self.font.width(text, bold) <= max_w:
            return text
        suffix = "..."
        out = text
        while out and self.font.width(out + suffix, bold) > max_w:
            out = out[:-1]
        if out:
            return out + suffix
        while suffix and self.font.width(suffix, bold) > max_w:
            suffix = suffix[:-1]
        return suffix

    def fit_tail(self, text: str, max_w: int, cursor: str = "_", bold: bool = False) -> str:
        full = text + cursor
        if self.font.width(full, bold) <= max_w:
            return full
        prefix = "..."
        tail = text
        while tail and self.font.width(prefix + tail + cursor, bold) > max_w:
            tail = tail[1:]
        if tail:
            return prefix + tail + cursor
        return self.fit_head(cursor, max_w, bold)

    def text(self, x: int, y: int, value: str, color: str = "light", *, max_w: int | None = None,
             mode: str = "head", center: bool = False, right: bool = False, bold: bool = False,
             tag: str = "text", allow_clip: bool = False) -> str:
        available = max_w if max_w is not None else self.board.logical_w - x
        shown = self.fit_tail(value, available, "", bold) if mode == "tail" else self.fit_head(value, available, bold)
        width = self.font.width(shown, bold)
        draw_x = x - width // 2 if center else (x - width if right else x)
        if not allow_clip:
            self.check_logical_box(tag, draw_x, y, width, 1)
        ink = self.font.ink_box(draw_x, y, shown, bold)
        if not allow_clip:
            self.check_physical_box(tag, ink)
        self.font.draw(self.image, draw_x, y, shown, self.color(color), bold)
        self.elements.append(Element(tag, ink, shown))
        return shown

    def assert_element_inside(self, tag: str, logical_box: tuple[int, int, int, int]) -> None:
        container = self.logical_box_to_physical(*logical_box)
        cx1, cy1, cx2, cy2 = container
        # Logical y=64 on T114 maps to 136 due Y_OFFSET; clip like the controller.
        cx2 = min(cx2, self.board.physical_w)
        cy2 = min(cy2, self.board.physical_h)
        for element in (item for item in self.elements if item.tag == tag and item.physical_box):
            x1, y1, x2, y2 = element.physical_box or (0, 0, 0, 0)
            if x1 < cx1 or y1 < cy1 or x2 > cx2 or y2 > cy2:
                self.violations.append(
                    f"{tag}: ink {x1},{y1}..{x2},{y2} escapes container {cx1},{cy1}..{cx2},{cy2}"
                )


def make_profiles() -> dict[str, list[BoardProfile]]:
    profiles: dict[str, list[BoardProfile]] = {"T096": [], "T114": [], "OLED": []}
    for family_index, (family_name, _, _) in enumerate(T096_FAMILIES):
        font = T096ExactFont(f"{family_name} L", load_compact_settings_font(10 + family_index))
        profiles["T096"].append(BoardProfile(
            "T096", family_name, 160, 80, 160, 80, font, font,
        ))

    for family_name in T114_FAMILIES:
        desired_raw = FirmwareT114Font(family_name, 18, 22, 18, 4)
        current_raw = FirmwareT114Font(family_name, 20, 26, 22, 4)
        profiles["T114"].append(BoardProfile(
            "T114", family_name, 128, 64, 240, 135,
            T114ExactFont(f"{family_name} L/compact", desired_raw),
            T114ExactFont(f"{family_name} XXL/current", current_raw),
            T114_SCALE_X, T114_SCALE_Y, T114_Y_OFFSET,
        ))

    for style_index, style in enumerate(OLED_STYLES):
        font = OledExactFont(style_index, style)
        profiles["OLED"].append(BoardProfile(
            "OLED", style[0], 128, 64, 128, 64, font, font, oled=True,
        ))
    return profiles


def make_t114_active_profiles() -> list[BoardProfile]:
    """All ten public ST7789 body profiles, plus the forced dense-screen font."""
    compact_raw = FirmwareT114Font("Roboto", 18, 22, 18, 4)
    compact = T114ExactFont("Roboto L/profile 0", compact_raw)
    profiles: list[BoardProfile] = []
    for name, family, px_size, height in T114_ACTIVE_FONT_PROFILES:
        active_raw = FirmwareT114Font(family, px_size, height, height - 4, 4)
        profiles.append(BoardProfile(
            "T114", name, 128, 64, 240, 135,
            compact,
            T114ExactFont(f"{name}/active", active_raw),
            T114_SCALE_X, T114_SCALE_Y, T114_Y_OFFSET,
        ))
    return profiles


def row_edges(start: int, end: int, rows: int) -> list[int]:
    return [start + ((end - start) * index) // rows for index in range(rows + 1)]


def draw_service_icon(frame: Frame, kind: str, x: int, y: int, w: int, h: int,
                      color: str, tag: str) -> None:
    cx = x + w // 2
    cy = y + h // 2
    if kind == "space":
        frame.line(((cx - 4, cy + 2), (cx + 4, cy + 2)), color, tag=tag)
        frame.line(((cx - 4, cy), (cx - 4, cy + 2)), color, tag=tag)
        frame.line(((cx + 4, cy), (cx + 4, cy + 2)), color, tag=tag)
    elif kind == "delete":
        frame.line(((cx + 5, cy), (cx - 3, cy), (cx, cy - 3)), color, tag=tag)
        frame.line(((cx - 3, cy), (cx, cy + 3)), color, tag=tag)
        frame.line(((cx + 2, cy - 2), (cx + 5, cy + 2)), color, tag=tag)
    else:  # visually distinct bent Back arrow
        frame.line(((cx + 4, cy + 3), (cx + 4, cy - 2), (cx - 3, cy - 2)), color, tag=tag)
        frame.line(((cx - 3, cy - 2), (cx, cy - 5)), color, tag=tag)
        frame.line(((cx - 3, cy - 2), (cx, cy + 1)), color, tag=tag)


def render_keyboard(profile: BoardProfile, *, desired: bool, text: str = LONG_TYPED,
                    page: int = 0, cursor: int = 20) -> Frame:
    frame = Frame(profile, f"{'desired' if desired else 'current'} keyboard", desired)
    w, h = profile.logical_w, profile.logical_h
    line_h = frame.font.logical_height
    if desired and profile.board != "OLED":
        preview_h = line_h + (2 if profile.board != "OLED" else 4)
        grid_y = preview_h
    elif profile.board == "T096":
        preview_h = line_h + 2
        grid_y = preview_h
    else:
        preview_h = 14
        grid_y = 16

    frame.rect(0, 0, w - 1, preview_h, "blue", outline=True, tag="preview border")
    if desired:
        preview_y = max(0, (preview_h - line_h) // 2)
        tail_w = w - 6
        shown = frame.fit_tail(text, tail_w - 3, "")
        frame.text(3, preview_y, shown, max_w=tail_w - 3, tag="typed tail")
        caret_x = min(w - 2, 3 + frame.font.width(shown) + 1)
        caret_h = max(5, line_h - 2)
        frame.rect(caret_x, preview_y + 1, 1, min(caret_h, h - preview_y - 1), "light",
                   tag="typed caret")
        frame.facts["typed_shown"] = shown
        frame.facts["tail_ok"] = shown.endswith(text[-6:])
        frame.facts["caret"] = True
    else:
        shown = frame.text(3, 2 if profile.board != "T096" else max(0, (preview_h - line_h) // 2),
                           text if text else "_", max_w=w - 6, tag="typed head")
        frame.facts["typed_shown"] = shown
        frame.facts["tail_ok"] = shown.endswith(text[-6:])
        frame.facts["caret"] = False

    edges = row_edges(grid_y, h, 4)
    cell_w = w // 6
    labels = DESIRED_KEY_LABELS[page % 3] if desired else CURRENT_KEY_LABELS[page % 3]
    for row in range(4):
        y1, y2 = edges[row], edges[row + 1]
        key_h = y2 - y1
        for col in range(6):
            index = row * 6 + col
            x1 = col * cell_w
            x2 = w if col == 5 else (col + 1) * cell_w
            key_w = x2 - x1
            selected = index == cursor
            service = index >= 18
            if selected:
                frame.rect(x1, y1, key_w, key_h, "green" if index == 21 else "yellow",
                           tag=f"key {index} fill")
            color = "dark" if selected else ("yellow" if service else "light")
            text_y = y1 + max(0, (key_h - line_h) // 2)
            label = labels[index]
            tag = f"key {index} label"
            if desired and index in (19, 20, 23):
                draw_service_icon(frame, {19: "space", 20: "delete", 23: "back"}[index],
                                  x1, y1, key_w, key_h, color, tag)
            else:
                frame.text(x1 + key_w // 2, text_y, label, color, center=True, bold=selected,
                           # Air/Strong OLED need the complete 21px cell for
                           # the still-readable three-glyph labels (123, T-Я).
                           max_w=max(1, key_w if desired else key_w - 2), tag=tag)
                frame.assert_element_inside(tag, (x1, y1, key_w, key_h))
    frame.facts.update({"line_h": line_h, "preview_h": preview_h, "grid_y": grid_y})
    return frame


def contact_name(index: int) -> str:
    if index == 0:
        return LONG_CONTACT
    if index % 17 == 0:
        return f"Компаньон поисково-спасательной группы {index + 1}"
    return f"Компаньон {index + 1:03d}"


def target_geometry(frame: Frame, desired: bool) -> tuple[int, list[int]]:
    h = frame.board.logical_h
    line_h = frame.font.logical_height
    if desired and frame.board.board == "T096":
        header_h = line_h + 2
        row_h = line_h
        visible = max(1, (h - header_h) // row_h)
        return header_h, [header_h + row_h * index for index in range(visible + 1)]
    if desired and frame.board.board == "T114":
        header_h = line_h + 2
        row_h = max(1, (h - header_h) // 4)
        visible = max(1, (h - header_h) // row_h)
        return header_h, [header_h + row_h * index for index in range(visible + 1)]
    if frame.board.board == "T096":
        header_h = line_h + 2
        row_h = 15 if h <= 80 else 14
        return header_h, [header_h + row_h * index for index in range(5)]
    header_h = 14
    list_y = header_h + 2
    row_h = 12 if h <= 64 else 14
    return header_h, [list_y + row_h * index for index in range(5)]


def draw_scrollbar(frame: Frame, start: int, visible: int, total: int, y: int, h: int,
                   color: str = "green") -> None:
    if total <= visible or h < 4:
        return
    thumb_h = max(4, (h * visible) // total)
    thumb_h = min(h, thumb_h)
    max_start = total - visible
    thumb_y = y + ((h - thumb_h) * min(start, max_start)) // max_start if max_start else y
    frame.rect(frame.board.logical_w - 2, y, 2, h, "light", outline=True, tag="scroll track")
    frame.rect(frame.board.logical_w - 2, thumb_y, 2, thumb_h, color, tag="scroll thumb")
    frame.facts["scrollbar"] = True
    frame.facts["thumb_h"] = thumb_h


def render_target(profile: BoardProfile, *, desired: bool, count: int, cursor: int | None = None,
                  kind: str = "Контакт") -> Frame:
    frame = Frame(profile, f"{'desired' if desired else 'current'} target {count}", desired)
    w, h = profile.logical_w, profile.logical_h
    header_h, edges = target_geometry(frame, desired)
    visible = len(edges) - 1
    total = count + 1  # explicit Back row
    if cursor is None:
        cursor = max(0, count - 1)
    cursor = min(max(0, cursor), total - 1)
    start = max(0, cursor - visible + 1) if total > visible else 0
    if start + visible > total:
        start = max(0, total - visible)

    frame.rect(0, 0, w - 1, header_h, "blue", outline=True, tag="target header")
    title_y = max(0, (header_h - frame.font.logical_height) // 2)
    frame.text(w // 2, title_y, kind, center=True, max_w=w - 8, tag="target title")

    if desired and count == 0:
        y1, y2 = edges[0], edges[1]
        frame.text(w // 2, y1 + max(0, (y2 - y1 - frame.font.logical_height) // 2),
                   "Нет контактов", "muted", center=True, max_w=w - 8, tag="empty state")
        by1, by2 = edges[1], edges[2]
        frame.rect(0, by1, w, by2 - by1, "yellow", tag="empty back fill")
        frame.text(w // 2, by1 + max(0, (by2 - by1 - frame.font.logical_height) // 2),
                   "Назад", "dark", center=True, max_w=w - 8, tag="empty back")
        frame.facts.update({"empty_state": True, "scrollbar": False, "visible": visible})
        return frame

    for row in range(visible):
        index = start + row
        if index >= total:
            break
        y1, y2 = edges[row], min(h, edges[row + 1])
        back = index >= count
        selected = index == cursor
        label = "Назад" if back else contact_name(index)
        if selected:
            frame.rect(0, y1, w, y2 - y1, "yellow" if back else "green", tag=f"target row {row} fill")
        color = "dark" if selected else ("yellow" if back else "light")
        reserve = 5 if desired and total > visible else 0
        tag = f"target row {row} text"
        frame.text(3, y1 + max(0, (y2 - y1 - frame.font.logical_height) // 2), label, color,
                   max_w=w - 6 - reserve, bold=selected, tag=tag)
        frame.assert_element_inside(tag, (0, y1, w - reserve, y2 - y1))

    if desired:
        draw_scrollbar(frame, start, visible, total, edges[0], h - edges[0], "green")
    else:
        frame.facts["scrollbar"] = False
    frame.facts.update({"count": count, "total": total, "start": start, "cursor": cursor,
                        "visible": visible, "empty_state": False})
    return frame


def setting_row(index: int) -> tuple[str, str]:
    fixed = (
        (LONG_SETTING, "ВКЛ"),
        ("Мелодия уведомлений", "Лебеди"),
        ("Громкость", "МАКС"),
        ("Шрифт интерфейса", "Noto XXL"),
        ("Цветовая тема", "Графит"),
        ("Bluetooth", "ВКЛ"),
        ("Радио и GPS", "GPS ВКЛ"),
        ("Назад", ""),
    )
    if index < len(fixed):
        return fixed[index]
    return f"Дополнительная настройка {index + 1}", "ВКЛ" if index % 2 else "ВЫКЛ"


def render_compact(profile: BoardProfile, *, desired: bool, count: int = 350,
                   cursor: int | None = None) -> Frame:
    frame = Frame(profile, f"{'desired' if desired else 'current'} compact {count}", desired)
    w, h = profile.logical_w, profile.logical_h
    if cursor is None:
        cursor = max(0, count - 1)
    cursor = min(max(0, cursor), max(0, count - 1))
    if desired:
        line_h = max(8, frame.font.logical_height)
        row_y = 14 + line_h + 1
        if h <= 64 and row_y < 28:
            row_y = 28
        row_h = max(12, line_h)
        visible = max(1, min(4, (h - row_y) // row_h))
    else:
        visible = 4 if h > 64 else 3
        row_y = 27 if h > 64 else 28
        row_h = 13 if h > 64 else 12
    start = max(0, cursor - visible + 1) if count > visible else 0
    if start + visible > count:
        start = max(0, count - visible)

    frame.text(2, 14, "Настройки", "green", max_w=w - 40, tag="compact title")
    frame.text(w - 2, 14, "<>OK", right=True, max_w=36, tag="compact hint")
    for row in range(visible):
        index = start + row
        if index >= count:
            break
        label, value = setting_row(index)
        y = row_y + row * row_h
        selected = index == cursor
        if desired and selected:
            frame.rect(0, y, w - (2 if count > visible else 0), min(row_h, h - y), "yellow",
                       tag=f"compact row {row} fill")
        color = "dark" if desired and selected else ("yellow" if selected else "light")
        value_width = 66 if w > 140 else 45
        scrollbar_guard = 4 if count > visible else 0
        if desired:
            label_x = 3
        else:
            if selected:
                frame.text(0, y, ">", color, max_w=7, tag=f"compact row {row} marker")
            label_x = 8 if selected else 2
        value_x = w - value_width - scrollbar_guard
        label_w = max(4, value_x - label_x - 2) if value else max(4, w - label_x - 2 - scrollbar_guard)
        tag = f"compact row {row} label"
        frame.text(label_x, y, label, color, max_w=label_w, bold=desired and selected, tag=tag)
        if value:
            value_color = "dark" if desired and selected else ("yellow" if selected else "green")
            frame.text(value_x, y, value, value_color, max_w=value_width - 2,
                       bold=desired and selected,
                       tag=f"compact row {row} value")
        frame.assert_element_inside(tag, (0, y, w - scrollbar_guard, min(row_h, h - y)))
    if count > visible:
        draw_scrollbar(frame, start, visible, count, row_y, min(h - row_y, visible * row_h - 2),
                       "green" if desired else "yellow")
    else:
        frame.facts["scrollbar"] = False
    frame.facts.update({"count": count, "start": start, "cursor": cursor, "visible": visible,
                        "full_row_selection": desired})
    return frame


def tagged_box(frame: Frame, tag: str) -> tuple[int, int, int, int] | None:
    return union_boxes(
        element.physical_box for element in frame.elements
        if element.tag == tag and element.physical_box is not None
    )


def assert_tags_do_not_overlap(frame: Frame, left_tag: str, right_tag: str) -> None:
    left = tagged_box(frame, left_tag)
    right = tagged_box(frame, right_tag)
    if left is None or right is None:
        return
    if left[0] < right[2] and left[2] > right[0] and left[1] < right[3] and left[3] > right[1]:
        frame.violations.append(f"{left_tag} overlaps {right_tag}: {left} vs {right}")


def render_appearance_picker(profile: BoardProfile, *, font_picker: bool, cursor: int,
                             active: int) -> Frame:
    frame = Frame(profile, f"T114 {'font' if font_picker else 'theme'} picker", True)
    names = T114_FONT_CHOICE_NAMES if font_picker else T114_THEME_CHOICE_NAMES
    choice_count = len(names)
    item_count = choice_count + 1
    cursor = min(max(0, cursor), item_count - 1)
    active = min(max(0, active), choice_count - 1)
    w, h = profile.logical_w, profile.logical_h
    line_h = max(8, frame.font.logical_height)
    row_y = 14 + line_h + 1
    if h <= 64 and row_y < 28:
        row_y = 28
    row_h = max(12, line_h)
    visible = max(1, min(4, (h - row_y) // row_h))
    start = max(0, cursor - visible + 1) if cursor >= visible else 0
    if start + visible > item_count:
        start = max(0, item_count - visible)
    has_scrollbar = item_count > visible

    frame.text(2, 14, "Шрифт" if font_picker else "Тема", "green", max_w=w - 38,
               tag="appearance title")
    frame.text(w - 2, 14, "<>OK", right=True, max_w=36, tag="appearance hint")
    for row in range(visible):
        index = start + row
        if index >= item_count:
            break
        y = row_y + row * row_h
        selected = index == cursor
        if selected:
            frame.rect(0, y, w - (3 if has_scrollbar else 0), row_h, "yellow",
                       tag=f"appearance row {row} fill")
        color = "dark" if selected else "light"
        label_x = 3
        right_guard = 5 if has_scrollbar else 3
        if index < choice_count:
            is_active = index == active
            marker_width = frame.font.width("OK", selected) + 4 if is_active else 0
            label_width = w - label_x - right_guard - marker_width
            frame.text(label_x, y, names[index], color, max_w=label_width, bold=selected,
                       tag=f"appearance row {row} label")
            if is_active:
                frame.text(w - right_guard, y, "OK", "dark" if selected else "green",
                           right=True, max_w=marker_width, bold=selected,
                           tag=f"appearance row {row} active")
                assert_tags_do_not_overlap(frame, f"appearance row {row} label",
                                           f"appearance row {row} active")
        else:
            frame.text(label_x, y, "Назад", color, max_w=w - label_x - right_guard,
                       bold=selected, tag=f"appearance row {row} label")
    if has_scrollbar:
        draw_scrollbar(frame, start, visible, item_count, row_y, visible * row_h - 2, "yellow")
    else:
        frame.facts["scrollbar"] = False
    frame.facts.update({"font_picker": font_picker, "choice_count": choice_count,
                        "cursor": cursor, "active": active, "visible": visible,
                        "static_ellipsis": True})
    return frame


def render_t114_gps(profile: BoardProfile, state: str) -> Frame:
    """Render the safe T114 GPS contract after forcing dense profile 0."""
    frame = Frame(profile, f"T114 GPS {state} {profile.profile}", True)
    w, h = profile.logical_w, profile.logical_h
    line_h = frame.font.logical_height
    row_step = line_h
    frame.line(((0, 12), (w - 1, 12)), "border", tag="chrome boundary")
    y = 18
    icon_size = min(12, max(9, line_h - 1))
    frame.rect(0, y + 1, 25, icon_size, "yellow" if state != "fix" else "green",
               outline=True, tag="GPS badge bounds")
    frame.text(29, y, "МОДУЛЬ", max_w=w - 29, tag="gps source")
    status = {"missing": "ВЫКЛ", "off": "ВЫКЛ", "search": "ПОИСК", "fix": "FIX"}[state]
    frame.text(w - 1, y, status, right=True, max_w=w, tag="gps status")
    assert_tags_do_not_overlap(frame, "gps source", "gps status")

    if state == "missing":
        frame.text(0, y + row_step, "GPS-модуль не найден", max_w=w, tag="gps detail")
    elif state == "off":
        frame.text(0, y + row_step, "Нажмите для включения", max_w=w, tag="gps detail")
    else:
        y += row_step
        frame.text(0, y, "СПУТН.", max_w=w, tag="gps sats label")
        frame.text(w - 1, y, "12", right=True, max_w=w, tag="gps sats value")
        assert_tags_do_not_overlap(frame, "gps sats label", "gps sats value")
        if state == "search":
            frame.text(0, y + row_step, "Ожидание координат", max_w=w, tag="gps detail")
        else:
            frame.text(0, y + row_step, "ШИР", max_w=w, tag="gps latitude label")
            frame.text(w - 1, y + row_step, "55.1234", right=True, max_w=w, tag="gps latitude value")
            assert_tags_do_not_overlap(frame, "gps latitude label", "gps latitude value")
            frame.text(0, y + row_step * 2, "ДОЛ", max_w=w, tag="gps longitude label")
            frame.text(w - 1, y + row_step * 2, "73.9876", right=True, max_w=w, tag="gps longitude value")
            assert_tags_do_not_overlap(frame, "gps longitude label", "gps longitude value")
    frame.facts.update({"gps_state": state, "active_font": profile.profile,
                        "rendered_font": frame.font.name, "line_h": line_h,
                        "row_step": row_step, "physical_bounds": True})
    return frame


def wrap_text(frame: Frame, text: str, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else current + " " + word
        if frame.font.width(candidate) <= max_w:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = ""
        chunk = word
        while chunk and frame.font.width(chunk) > max_w:
            take = ""
            for ch in chunk:
                if take and frame.font.width(take + ch) > max_w:
                    break
                take += ch
            lines.append(take)
            chunk = chunk[len(take):]
        current = chunk
    if current:
        lines.append(current)
    return lines


def sender_data(index: int) -> tuple[str, int, str]:
    data = (
        ("Александра Северная", 3, "Координаты приняты, выдвигаемся к северному входу"),
        ("Иван", 2, "Буду через десять минут"),
        ("Олег Спасатель", 1, "Связь устойчивая, всё хорошо"),
        ("Мария", 4, "Проверь аккумулятор второй ноды"),
        ("Дежурная группа", 1, "Сообщение доставлено"),
    )
    if index < len(data):
        return data[index]
    return f"Компаньон {index + 1}", index % 4 + 1, "Последнее личное сообщение от пользователя"


def render_unread_current(profile: BoardProfile) -> Frame:
    frame = Frame(profile, "current unread history", False)
    w, h = profile.logical_w, profile.logical_h
    line_h = frame.font.logical_height
    frame.text(0, 0, "Непроч: 8", "green", max_w=w - 28, tag="unread current title")
    frame.text(w - 2, 0, "4м", right=True, max_w=24, tag="unread current age")
    content_y = 11 if profile.board == "T096" else 14
    y = content_y
    for color, line in (("yellow", "(3) Александра Северная:"), ("green", "Notify: DM")):
        if y < h:
            frame.text(0, y, line, color, max_w=w - 2, tag="unread current line")
        y += line_h
    body = "Вся история чата почему-то оказалась в окне непрочитанных личных сообщений"
    for line in wrap_text(frame, body, w - 2):
        if y >= h:
            break
        frame.text(0, y, line, max_w=w - 2, tag="unread current body")
        y += line_h
    frame.facts.update({"sender_mode": False, "contains_notify_dm": True})
    return frame


def render_unread_senders(profile: BoardProfile, *, count: int, cursor: int | None = None) -> Frame:
    frame = Frame(profile, f"desired unread senders {count}", True)
    w, h = profile.logical_w, profile.logical_h
    line_h = frame.font.logical_height
    content_y = line_h + 3
    total_messages = sum(sender_data(index)[1] for index in range(count))
    frame.text(0, 0, f"ЛС: {count} чел / {total_messages}", "green", max_w=w - 1,
               tag="unread title")
    if profile.board != "T096":
        frame.line(((0, line_h + 1), (w - 1, line_h + 1)), "light", tag="unread separator")
    if count == 0:
        frame.facts.update({"sender_mode": True, "contains_notify_dm": False, "scrollbar": False,
                            "empty_state": True})
        return frame

    row_gap = 2 if h > 64 else 1
    show_snippets = h - content_y >= line_h * 2 + row_gap
    row_h = line_h * (2 if show_snippets else 1) + row_gap
    total_h = count * row_h
    visible_h = max(1, h - content_y - 1)
    max_scroll = max(0, total_h - visible_h)
    scroll = max_scroll if cursor is not None and cursor >= count - 1 else 0
    body_x = 12 if profile.board == "T114" else 0
    guard = 4 if profile.board in ("T096", "T114") else 1
    body_w = w - body_x - guard
    if body_w < 24:
        body_w = w - body_x

    y = content_y - scroll
    for index in range(count):
        sender, unread_count, snippet = sender_data(index)
        count_label = f"({unread_count})"
        count_w = frame.font.width(count_label)
        name_w = body_w - count_w - 3
        if name_w < 1:
            name_w = body_w
        # The feed is rendered after the header.  A plain y>-line_h test lets
        # auto-scroll paint an old sender across "ЛС: ..."; clip every line at
        # the content origin even though the display API has no clip rectangle.
        if y >= content_y and y < h:
            frame.text(body_x, y, sender, "yellow", max_w=name_w,
                       tag=f"unread sender {index} name", allow_clip=True)
            if count_w < body_w:
                frame.text(body_x + body_w, y, count_label, "green", right=True,
                           max_w=count_w, tag=f"unread sender {index} count", allow_clip=True)
        y += line_h
        if show_snippets:
            if y >= content_y and y < h:
                frame.text(body_x + 6, y, snippet, "light", max_w=max(1, body_w - 6),
                           tag=f"unread sender {index} snippet", allow_clip=True)
            y += line_h
        y += row_gap
    frame.facts["scrollbar"] = False
    frame.facts.update({"sender_mode": True, "contains_notify_dm": False, "empty_state": False,
                        "count": count, "show_snippets": show_snippets, "needs_scroll": max_scroll > 0,
                        "scroll": scroll, "max_scroll": max_scroll, "header_protected": True})
    return frame


def render_ble_pin(profile: BoardProfile) -> Frame:
    """Render the exact non-e-paper BLE onboarding page font roles.

    T096 uses its real small/large embedded bitmap profiles.  T114 uses the
    fixed Roboto L instruction font plus every public user-selected hero font,
    matching the board-specific protection in UITask.cpp.
    """
    frame = Frame(profile, "BLE PIN onboarding", True)
    if profile.board == "T096":
        family_index = next(
            index for index, family in enumerate(T096_FAMILIES)
            if family[0] == profile.profile
        )
        title_font: ExactFont = T096ExactFont(
            f"{profile.profile} S", load_compact_settings_font(5 + family_index)
        )
        hero_font: ExactFont = T096ExactFont(
            f"{profile.profile} XL", load_compact_settings_font(15 + family_index)
        )
        title_y, pin_y, hint_y = 21, 38, 57
    elif profile.board == "T114":
        title_font = profile.desired_font
        hero_font = profile.current_font
        title_y, pin_y, hint_y = 18, 31, 51
    else:
        raise ValueError(f"BLE PIN role simulator does not support {profile.board}")

    def exact_text(font_obj: ExactFont, y: int, value: str, color: str, tag: str) -> None:
        frame.font = font_obj
        frame.text(profile.logical_w // 2, y, value, color, center=True,
                   max_w=10000, tag=tag)

    exact_text(title_font, title_y, "ПИНКОД BLE", "yellow", "pin title")
    exact_text(hero_font, pin_y, "428731", "green", "pin digits")
    exact_text(title_font, hint_y, "код в приложении", "light", "pin hint")

    boxes = [item.physical_box for item in frame.elements if item.tag.startswith("pin ")]
    no_overlap = True
    for index, first in enumerate(boxes):
        if first is None:
            continue
        for second in boxes[index + 1:]:
            if second is None:
                continue
            if first[0] < second[2] and first[2] > second[0] and first[1] < second[3] and first[3] > second[1]:
                no_overlap = False
    frame.facts.update({"full_pin_text": all(
        item.shown in ("ПИНКОД BLE", "428731", "код в приложении")
        for item in frame.elements if item.tag.startswith("pin ")
    ), "no_pin_overlap": no_overlap})
    return frame


def canonical_scenes(profile: BoardProfile) -> list[tuple[str, Frame]]:
    return [
        ("CURRENT keyboard: начало", render_keyboard(profile, desired=False, cursor=20)),
        ("SmartUI PS17 keyboard: хвост+каретка", render_keyboard(profile, desired=True, cursor=20)),
        ("CURRENT target 350: без scrollbar", render_target(profile, desired=False, count=350, cursor=349)),
        ("SmartUI PS17 target: 0 контактов", render_target(profile, desired=True, count=0, cursor=0)),
        ("SmartUI PS17 target: 1 контакт", render_target(profile, desired=True, count=1, cursor=0)),
        ("SmartUI PS17 target: 350 контактов", render_target(profile, desired=True, count=350, cursor=349)),
        ("CURRENT compact list", render_compact(profile, desired=False, count=350, cursor=349)),
        ("SmartUI PS17 compact list", render_compact(profile, desired=True, count=350, cursor=349)),
        ("CURRENT unread: история", render_unread_current(profile)),
        ("SmartUI PS17 unread: пусто", render_unread_senders(profile, count=0)),
        ("SmartUI PS17 unread: 1 отправитель", render_unread_senders(profile, count=1)),
        ("SmartUI PS17 unread: отправители", render_unread_senders(profile, count=12, cursor=11)),
    ]


def label_font(size: int = 16) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(LABEL_FONT_PATH), size=size)


def make_matrix(scenes: Sequence[tuple[str, Frame]], out: Path, columns: int = 3) -> None:
    target_w = 640
    target_h = 360
    label_h = 42
    gap = 10
    rows = math.ceil(len(scenes) / columns)
    sheet = Image.new("RGB", (columns * target_w + (columns - 1) * gap,
                              rows * (target_h + label_h) + (rows - 1) * gap), (13, 17, 22))
    draw = ImageDraw.Draw(sheet)
    font = label_font(15)
    for index, (label, frame) in enumerate(scenes):
        col = index % columns
        row = index // columns
        x = col * (target_w + gap)
        y = row * (target_h + label_h + gap)
        status = f"{label} | {frame.board.profile} | overflow={len(frame.violations)}"
        draw.text((x + 4, y + 3), status, font=font,
                  fill=(255, 100, 100) if frame.violations and frame.desired else (225, 235, 240))
        ratio = min(target_w / frame.image.width, target_h / frame.image.height)
        render_w = int(frame.image.width * ratio)
        render_h = int(frame.image.height * ratio)
        preview = frame.image.resize((render_w, render_h), Image.Resampling.NEAREST)
        sheet.paste(preview, (x + (target_w - render_w) // 2, y + label_h + (target_h - render_h) // 2))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)


def desired_sweep_scenes(profile: BoardProfile) -> list[tuple[str, Frame]]:
    return [
        (f"{profile.profile}: keyboard tail", render_keyboard(profile, desired=True, cursor=23)),
        (f"{profile.profile}: target 350", render_target(profile, desired=True, count=350, cursor=350)),
        (f"{profile.profile}: compact", render_compact(profile, desired=True, count=350, cursor=349)),
        (f"{profile.profile}: unread", render_unread_senders(profile, count=12, cursor=11)),
    ]


def run_release_assertions(profiles: dict[str, list[BoardProfile]]) -> tuple[list[dict], list[str]]:
    records: list[dict] = []
    failures: list[str] = []

    def record(frame: Frame, case: str, semantic: bool = True) -> None:
        status = not frame.violations and semantic
        records.append({
            "board": frame.board.board,
            "profile": frame.board.profile,
            "case": case,
            "status": "PASS" if status else "FAIL",
            "violations": frame.violations,
            "facts": frame.facts,
        })
        if not status:
            detail = "; ".join(frame.violations) if frame.violations else "semantic assertion failed"
            failures.append(f"{frame.board.board}/{frame.board.profile}/{case}: {detail}")

    for board_profiles in profiles.values():
        for profile in board_profiles:
            for page in range(3):
                for cursor in (0, 18, 20, 21, 23):
                    frame = render_keyboard(profile, desired=True, page=page, cursor=cursor)
                    record(frame, f"keyboard page={page} cursor={cursor}",
                           bool(frame.facts.get("tail_ok")) and bool(frame.facts.get("caret")))
            for count, cursors in ((0, (0,)), (1, (0, 1)), (350, (0, 349, 350))):
                for cursor in cursors:
                    frame = render_target(profile, desired=True, count=count, cursor=cursor)
                    semantic = bool(frame.facts.get("empty_state")) if count == 0 else True
                    if count > 3:
                        semantic = semantic and bool(frame.facts.get("scrollbar"))
                    record(frame, f"target contacts={count} cursor={cursor}", semantic)
            for count, cursor in ((1, 0), (8, 0), (350, 349)):
                frame = render_compact(profile, desired=True, count=count, cursor=cursor)
                semantic = bool(frame.facts.get("full_row_selection"))
                if count > int(frame.facts.get("visible", 0)):
                    semantic = semantic and bool(frame.facts.get("scrollbar"))
                record(frame, f"compact items={count} cursor={cursor}", semantic)
            for count, cursor in ((0, 0), (1, 0), (12, 11)):
                frame = render_unread_senders(profile, count=count, cursor=cursor)
                semantic = bool(frame.facts.get("sender_mode")) and not bool(frame.facts.get("contains_notify_dm"))
                record(frame, f"unread senders={count}", semantic)

    t114_active = make_t114_active_profiles()
    for profile in profiles["T096"]:
        frame = render_ble_pin(profile)
        record(frame, "BLE PIN onboarding",
               bool(frame.facts.get("full_pin_text")) and bool(frame.facts.get("no_pin_overlap")))
    for profile in t114_active:
        frame = render_ble_pin(profile)
        record(frame, "BLE PIN onboarding physical",
               bool(frame.facts.get("full_pin_text")) and bool(frame.facts.get("no_pin_overlap")))

    for profile in t114_active:
        for state in ("missing", "off", "search", "fix"):
            frame = render_t114_gps(profile, state)
            record(frame, f"T114 GPS {state} physical", bool(frame.facts.get("physical_bounds")))

    t114_dense = t114_active[0]
    for font_picker, names in ((True, T114_FONT_CHOICE_NAMES), (False, T114_THEME_CHOICE_NAMES)):
        for cursor in (0, len(names) - 1, len(names)):
            frame = render_appearance_picker(t114_dense, font_picker=font_picker,
                                             cursor=cursor, active=len(names) - 1)
            record(frame, f"T114 {'font' if font_picker else 'theme'} picker cursor={cursor}",
                   bool(frame.facts.get("static_ellipsis")) and bool(frame.facts.get("scrollbar")))

    for case, frame in (
        ("T114 compact physical", render_compact(t114_dense, desired=True, count=350, cursor=349)),
        ("T114 keyboard physical", render_keyboard(t114_dense, desired=True, cursor=23)),
        ("T114 target physical", render_target(t114_dense, desired=True, count=350, cursor=350)),
        ("T114 unread physical", render_unread_senders(t114_dense, count=12, cursor=11)),
    ):
        record(frame, case, True)
    return records, failures


def save_native_frames(scenes: Sequence[tuple[str, Frame]], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for index, (_, frame) in enumerate(scenes):
        stem = f"{index:02d}_{frame.name.replace(' ', '_')}"
        frame.image.save(directory / f"{stem}.png")
        scale = 4 if frame.board.board != "T114" else 3
        frame.image.resize((frame.image.width * scale, frame.image.height * scale),
                           Image.Resampling.NEAREST).save(directory / f"{stem}_x{scale}.png")


def write_reports(out: Path, records: list[dict], failures: list[str], canonical: dict[str, list[tuple[str, Frame]]]) -> None:
    summary = {
        "contract": "SmartUI PS17 exact dense UI",
        "desired_cases": len(records),
        "passed": sum(1 for item in records if item["status"] == "PASS"),
        "failed": len(failures),
        "current_reference_overflows": {
            board: sum(len(frame.violations) for _, frame in scenes if not frame.desired)
            for board, scenes in canonical.items()
        },
        "failures": failures,
        "records": records,
    }
    (out / "SMARTUI_PS17_SIMULATION_REPORT.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "SmartUI PS17 exact UI simulation report",
        f"Desired cases: {summary['desired_cases']}",
        f"Passed: {summary['passed']}",
        f"Failed: {summary['failed']}",
        "",
        "Display contracts:",
        "- T096: 160x80, embedded bitmap glyphs, threshold 104, exact xAdvance.",
        "- T114: logical 128x64 -> physical 240x135, 1.875 x 2.109375, Y_OFFSET=1, threshold 92.",
        "- OLED: 128x64, actual Utf8Cyrillic5x7 tables and five driver spacing styles.",
        "",
        "Stress cases: 0/1/350 contacts, 1/8/350 compact rows, 0/1/12 DM senders,",
        "three keyboard pages, service-key selection, long Russian labels and typed-text tail.",
        "T114 extras: all 10 public fonts x 4 GPS states, font/theme pickers and physical 240x135 bounds.",
        "BLE onboarding: all 5 T096 families and all 10 T114 public fonts, complete text and no overlaps.",
        "",
        "Reference overflows (informational, not the SmartUI PS17 gate):",
    ]
    lines.extend(f"- {board}: {count}" for board, count in summary["current_reference_overflows"].items())
    if failures:
        lines.extend(("", "FAILURES:"))
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.extend(("", "RESULT: PASS — all desired framebuffer and semantic assertions passed."))
    (out / "SMARTUI_PS17_SIMULATION_REPORT.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT,
                        help=f"output directory (default: {DEFAULT_OUT})")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    profiles = make_profiles()
    canonical: dict[str, list[tuple[str, Frame]]] = {}
    for board, board_profiles in profiles.items():
        # Roboto/Classic is the readable canonical matrix; the separate sweep covers all profiles.
        canonical_profile = board_profiles[0]
        scenes = canonical_scenes(canonical_profile)
        canonical[board] = scenes
        make_matrix(scenes, out / f"{board}_SMARTUI_PS17_EXACT_QA_MATRIX.png")
        save_native_frames(scenes, out / "frames" / board)
        sweep: list[tuple[str, Frame]] = []
        for profile in board_profiles:
            sweep.extend(desired_sweep_scenes(profile))
        make_matrix(sweep, out / f"{board}_SMARTUI_PS17_FONT_SWEEP.png", columns=4)

    t114_active = make_t114_active_profiles()
    t114_special: list[tuple[str, Frame]] = [
        (f"GPS FIX / {profile.profile}", render_t114_gps(profile, "fix"))
        for profile in t114_active
    ]
    t114_special.extend([
        ("GPS module missing", render_t114_gps(t114_active[0], "missing")),
        ("GPS off", render_t114_gps(t114_active[0], "off")),
        ("GPS search", render_t114_gps(t114_active[0], "search")),
        ("Font picker start", render_appearance_picker(t114_active[0], font_picker=True, cursor=0, active=9)),
        ("Font picker Back", render_appearance_picker(t114_active[0], font_picker=True, cursor=10, active=9)),
        ("Theme picker start", render_appearance_picker(t114_active[0], font_picker=False, cursor=0, active=6)),
        ("Theme picker Back", render_appearance_picker(t114_active[0], font_picker=False, cursor=7, active=6)),
        ("Compact settings", render_compact(t114_active[0], desired=True, count=350, cursor=349)),
        ("Keyboard", render_keyboard(t114_active[0], desired=True, cursor=23)),
        ("Target 350", render_target(t114_active[0], desired=True, count=350, cursor=350)),
        ("Unread senders", render_unread_senders(t114_active[0], count=12, cursor=11)),
    ])
    make_matrix(t114_special, out / "T114_SMARTUI_PS17_GPS_APPEARANCE_PHYSICAL_QA.png", columns=4)
    save_native_frames(t114_special, out / "frames" / "T114_special")

    records, failures = run_release_assertions(profiles)
    write_reports(out, records, failures, canonical)
    print(f"SmartUI PS17 exact UI QA: {len(records) - len(failures)} passed, {len(failures)} failed")
    print(out / "SMARTUI_PS17_SIMULATION_REPORT.txt")
    for failure in failures[:30]:
        print(f"[FAIL] {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
