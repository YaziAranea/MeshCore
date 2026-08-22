#!/usr/bin/env python3
"""Pixel-accurate static QA for the 250x122 SmartUI PS17 Wireless Paper UI.

This intentionally models the small E213 profile renderer from E213Display.cpp,
not Pillow fonts and not the 128x64 OLED/T096 simulators.  The glyph arrays are
read directly from Utf8Cyrillic5x7.h so source and simulation cannot silently
drift apart.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
FONT_HEADER = ROOT / "src/helpers/ui/Utf8Cyrillic5x7.h"
DEFAULT_OUT = ROOT / "qa_outputs" / "wireless_paper_ps17"
W, H = 250, 122

PROFILES = {
    "Стандарт": (6, 3, 0, False),
    "Четкий": (7, 3, 1, False),
    "Компакт": (5, 2, 0, False),
    "Моно": (6, 3, 0, True),
    "Плотный": (6, 2, 1, True),
}


def parse_array(source: str, name: str) -> list[list[int]]:
    match = re.search(
        rf"static const uint8_t {re.escape(name)}\[\]\[5\]\s*=\s*\{{(.*?)\n\}};",
        source,
        re.S,
    )
    if not match:
        raise RuntimeError(f"cannot find {name}")
    rows = []
    for body in re.findall(r"\{([^{}]+)\}", match.group(1)):
        values = [int(v, 16) for v in re.findall(r"0x[0-9A-Fa-f]+", body)]
        if len(values) == 5:
            rows.append(values)
    return rows


SOURCE = FONT_HEADER.read_text(encoding="utf-8")
ASCII = parse_array(SOURCE, "meshcore_ascii_5x7")
CYR_UPPER = parse_array(SOURCE, "meshcore_cyrillic_5x7")
CYR_LOWER = parse_array(SOURCE, "meshcore_cyrillic_lower_5x7")


def glyph(ch: str) -> list[int]:
    cp = ord(ch)
    if 32 <= cp <= 126:
        return ASCII[cp - 32]
    if ch == "Ё":
        return CYR_UPPER[5]
    if ch == "ё":
        return CYR_LOWER[5]
    if 0x410 <= cp <= 0x42F:
        return CYR_UPPER[cp - 0x410]
    if 0x430 <= cp <= 0x44F:
        return CYR_LOWER[cp - 0x430]
    return ASCII[ord("?") - 32]


class Canvas:
    def __init__(self, name: str):
        self.name = name
        self.px = [[0] * W for _ in range(H)]  # 0 paper, 1 ink
        self.owner = [[""] * W for _ in range(H)]
        self.collisions: Counter[tuple[str, str]] = Counter()
        self.clipped = 0

    def pixel(self, x: int, y: int, ink: bool = True, layer: str = "ui") -> None:
        if not (0 <= x < W and 0 <= y < H):
            self.clipped += 1
            return
        if ink and self.px[y][x] and self.owner[y][x] and self.owner[y][x] != layer:
            self.collisions[tuple(sorted((self.owner[y][x], layer)))] += 1
        self.px[y][x] = int(ink)
        self.owner[y][x] = layer if ink else ""

    def fill(self, x: int, y: int, w: int, h: int, ink: bool = True, layer: str = "ui") -> None:
        if w <= 0 or h <= 0:
            return
        # Mirrors E213Display::fillRectClipped; attempts outside are recorded.
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.pixel(xx, yy, ink, layer)

    def line(self, x0: int, y0: int, x1: int, y1: int, layer: str = "ui") -> None:
        dx, sx = abs(x1 - x0), (1 if x0 < x1 else -1)
        dy, sy = -abs(y1 - y0), (1 if y0 < y1 else -1)
        err = dx + dy
        while True:
            self.pixel(x0, y0, True, layer)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def rect(self, x: int, y: int, w: int, h: int, ink: bool = True, layer: str = "ui") -> None:
        self.fill(x, y, w, 1, ink, layer)
        self.fill(x, y + h - 1, w, 1, ink, layer)
        self.fill(x, y, 1, h, ink, layer)
        self.fill(x + w - 1, y, 1, h, ink, layer)

    def text_width(self, text: str, profile: str = "Стандарт", size: int = 1, bold: bool = False) -> int:
        advance, _gap, weight, fixed = PROFILES[profile]
        scale = max(1, size)
        total = 0
        for ch in text:
            if ch in "\r\n":
                continue
            cols = advance
            if ch == " ":
                cols = advance if fixed else 4
            total += cols * scale + int(bold or weight)
        return total

    def text(self, x: int, y: int, text: str, *, profile: str = "Стандарт", size: int = 1,
             bold: bool = False, ink: bool = True, layer: str = "text") -> int:
        advance, _gap, profile_weight, fixed = PROFILES[profile]
        scale = max(1, size)
        weight = int(bold or profile_weight)
        start_x = x
        for ch in text:
            if ch == "\r":
                continue
            if ch == "\n":
                x = start_x
                y += (8 + (2 if size > 1 else PROFILES[profile][1])) * scale
                continue
            if ch != " ":
                for col, bits in enumerate(glyph(ch)):
                    for row in range(8):
                        if bits & (1 << row):
                            self.fill(x + col * scale, y + row * scale, scale + weight, scale, ink, layer)
            cols = advance if (ch != " " or fixed) else 4
            x += cols * scale + weight
        return x

    def centered(self, cx: int, y: int, text: str, **kw) -> None:
        self.text(cx - self.text_width(text, kw.get("profile", "Стандарт"), kw.get("size", 1), kw.get("bold", False)) // 2,
                  y, text, **kw)

    def right(self, right: int, y: int, text: str, **kw) -> None:
        self.text(right - self.text_width(text, kw.get("profile", "Стандарт"), kw.get("size", 1), kw.get("bold", False)),
                  y, text, **kw)

    def ellipsize(self, text: str, max_w: int, **kw) -> str:
        if self.text_width(text, kw.get("profile", "Стандарт"), kw.get("size", 1), kw.get("bold", False)) <= max_w:
            return text
        out = text
        while out and self.text_width(out + "...", kw.get("profile", "Стандарт"), kw.get("size", 1), kw.get("bold", False)) > max_w:
            out = out[:-1]
        return out + "..."

    def image(self, scale: int = 4) -> Image.Image:
        image = Image.new("L", (W, H), 255)
        image.putdata([0 if self.px[y][x] else 255 for y in range(H) for x in range(W)])
        return image.resize((W * scale, H * scale), Image.Resampling.NEAREST)

    def stats(self) -> dict:
        xs, ys = [], []
        for y in range(H):
            for x in range(W):
                if self.px[y][x]:
                    xs.append(x)
                    ys.append(y)
        return {
            "name": self.name,
            "ink_pixels": len(xs),
            "ink_bbox": [min(xs), min(ys), max(xs), max(ys)] if xs else None,
            "clipped_pixel_attempts": self.clipped,
            "overlap_pixels": {" + ".join(k): v for k, v in sorted(self.collisions.items())},
        }


def pine(c: Canvas, x: int, base_y: int, height: int) -> None:
    height = max(8, height)
    top = base_y - height
    c.line(x, top, x, base_y, "forest")
    for y in range(top + 3, base_y, 4):
        span = min((y - top) // 2 + 2, height // 3)
        c.line(x, y, x - span, y + 3, "forest")
        c.line(x, y, x + span, y + 3, "forest")
    c.fill(x - 1, base_y - 2, 3, 2, layer="forest")


def mountain_texture(c: Canvas, x0: int, y0: int, x1: int, y1: int, seed: int) -> None:
    for x in range(x0, x1 + 1, 7):
        y = y0 + ((x + seed) % 11)
        c.line(x, y, x + 10, y - 5, "forest")
    for x in range(x0 + 4, x1 + 1, 13):
        y = y1 - ((x + seed) % 9)
        c.line(x, y, x + 8, y + 3, "forest")


def forest(c: Canvas, seed: int = 17) -> None:
    ridge_y, right = H - 22, W - 70
    c.line(0, ridge_y - 5, 26, ridge_y - 18, "forest")
    c.line(26, ridge_y - 18, 56, ridge_y - 6, "forest")
    c.line(right, ridge_y - 7, right + 30, ridge_y - 25, "forest")
    c.line(right + 30, ridge_y - 25, W - 1, ridge_y - 8, "forest")
    mountain_texture(c, 4, ridge_y - 30, 56, ridge_y - 5, seed)
    mountain_texture(c, right, ridge_y - 30, W - 10, ridge_y - 5, seed)
    tower_x, tower_top = 22 + seed % 3, ridge_y - 40
    c.line(tower_x, tower_top, tower_x - 7, ridge_y - 14, "forest")
    c.line(tower_x, tower_top, tower_x + 7, ridge_y - 14, "forest")
    c.line(tower_x - 7, ridge_y - 14, tower_x + 7, ridge_y - 14, "forest")
    c.line(tower_x, tower_top, tower_x, ridge_y - 8, "forest")
    c.rect(tower_x - 2, tower_top + 7, 5, 5, layer="forest")
    c.line(tower_x - 12, tower_top + 4, tower_x - 4, tower_top + 8, "forest")
    c.line(tower_x + 4, tower_top + 8, tower_x + 12, tower_top + 4, "forest")
    for x in range(5, W, 18):
        if 58 < x < W - 58:
            continue
        pine(c, x, H - 2, 17 + ((x + seed) % 11))
    for x in range(W - 68, W, 13):
        pine(c, x, ridge_y + 10, 23 + ((x + seed * 3) % 15))
    c.line(0, 18, 36, 14, "forest")
    c.line(36, 14, 70, 24, "forest")
    c.line(70, 24, 103, 11, "forest")
    c.line(103, 11, 143, 25, "forest")
    c.line(143, 25, 188, 14, "forest")
    c.line(188, 14, W - 1, 23, "forest")
    for x in range(W - 112, W, 15):
        pine(c, x, 30, 20 + ((x + seed) % 8))


def battery(c: Canvas, mv: int = 3870) -> None:
    label = f"{mv // 1000}.{(mv % 1000) // 10:02d}V"
    c.right(W - 26, 4, label, layer="battery_text")
    x, y = W - 24, 3
    c.rect(x, y, 21, 10, layer="battery_icon")
    c.fill(x + 21, y + 3, 2, 4, layer="battery_icon")
    bars = 5 if mv >= 4100 else 4 if mv >= 3950 else 3 if mv >= 3800 else 2 if mv >= 3650 else 1 if mv >= 3450 else 0
    for i in range(bars):
        c.fill(x + 2 + i * 3, y + 2, 2, 6, layer="battery_icon")


def main_battery(c: Canvas, profile: str, mv: int = 3870) -> None:
    """Generic HomeScreen::renderBatteryIndicator geometry (non-T096)."""
    icon_w, icon_h = 18, 10
    icon_x, icon_y = W - icon_w - 2, 2
    label = f"{mv // 1000}.{(mv % 1000) // 10:02d}V"
    label_x = icon_x - c.text_width(label, profile) - 3
    if label_x > 0:
        c.text(label_x, 0, label, profile=profile, layer="battery_text")
    c.rect(icon_x, icon_y, icon_w, icon_h, layer="battery_icon")
    c.fill(icon_x + icon_w, icon_y + 3, 2, 4, layer="battery_icon")
    pct = max(0, min(100, (mv - 3000) * 100 // (4200 - 3000))) if mv > 0 else 0
    fill_w = ((icon_w - 4) * pct + 50) // 100
    if fill_w:
        c.fill(icon_x + 2, icon_y + 2, fill_w, icon_h - 4, layer="battery_icon")


def render_wood(profile: str = "Стандарт") -> Canvas:
    c = Canvas("wood_clock")
    forest(c)
    title = c.ellipsize("Мешкор Омск", W - 72, profile=profile)
    c.text(4, 4, title, profile=profile, layer="header")
    battery(c)
    c.centered(W // 2, 39, "23:47", profile=profile, size=4, bold=True, layer="time")
    c.centered(W // 2, 78, "22.08.2026", profile=profile, size=2, layer="date")
    c.centered(W // 2, 101, "Непроч: 12", profile=profile, layer="unread")
    return c


def render_wood_safe(profile: str = "Стандарт") -> Canvas:
    """Minimal collision-free variant proposed by the QA pass.

    The artwork remains unchanged; two paper-white quiet zones are restored
    after it: one for the central information card and one for the battery.
    """
    c = Canvas("wood_clock_final")
    forest(c)
    c.fill(45, 34, 161, 64, ink=False, layer="quiet_zone")
    c.fill(190, 0, 60, 15, ink=False, layer="quiet_zone")
    title = c.ellipsize("Лесная нода Омск", W - 72, profile=profile)
    c.text(4, 4, title, profile=profile, layer="header")
    battery(c)
    c.centered(W // 2, 39, "23:47", profile=profile, size=4, bold=True, layer="time")
    c.centered(W // 2, 78, "22.08.2026", profile=profile, size=2, layer="date")
    c.centered(W // 2, 101, "Непроч: 12", profile=profile, layer="unread")
    return c


def render_main_clock(profile: str = "Стандарт") -> Canvas:
    c = Canvas("main_clock")
    c.text(4, 4, c.ellipsize("Heltec WP SmartUI", W - 82, profile=profile), profile=profile, layer="header")
    main_battery(c, profile)
    c.centered(W // 2, 25, "23:47", profile=profile, size=4, bold=True, layer="time")
    c.centered(W // 2, 61, "22.08.2026", profile=profile, size=2, layer="date")
    c.centered(W // 2, 86, "ChUtil 12.3%  Air 0.42%", profile=profile, layer="channel")
    c.centered(W // 2, 101, "Msg/h 128", profile=profile, layer="messages")
    c.right(W - 4, 101, "42C", profile=profile, layer="temperature")
    return c


def render_settings(profile: str = "Стандарт") -> Canvas:
    c = Canvas("compact_settings")
    line_h = max(8, (8 + PROFILES[profile][1]))
    c.text(2, 14, "Настройки", profile=profile, layer="title")
    c.right(W - 2, 14, "<>OK", profile=profile, layer="hint")
    rows = [("Быстрые", "3 пункта"), ("Сигналы", "СВЕТ"), ("Экран", profile), ("Радио", "22 dBm")]
    row_y, row_h = 14 + line_h + 1, max(line_h, 12)
    for i, (label, value) in enumerate(rows):
        y = row_y + i * row_h
        selected = i == 0
        if selected:
            c.fill(0, y, W - 3, row_h, layer="selection")
        ink = not selected
        c.text(3, y, c.ellipsize(label, 176, profile=profile, bold=selected), profile=profile,
               bold=selected, ink=ink, layer=f"row{i}_label")
        c.text(W - 66, y, c.ellipsize(value, 65, profile=profile), profile=profile,
               bold=selected, ink=ink, layer=f"row{i}_value")
    c.rect(W - 2, row_y, 2, len(rows) * row_h - 2, layer="scroll_track")
    c.fill(W - 2, row_y, 2, 16, layer="scroll_thumb")
    return c


def render_settings_8(profile: str = "Стандарт") -> Canvas:
    """Wireless Paper proposal: use all eight safe 12 px rows."""
    c = Canvas("compact_settings_final")
    line_h = max(8, 8 + PROFILES[profile][1])
    c.text(2, 14, "Настройки", profile=profile, layer="title")
    c.right(W - 2, 14, "<>OK", profile=profile, layer="hint")
    rows = [
        ("Избранное", "3 пункта"), ("Уведомления", "ЭКРАН"),
        ("Экран", profile), ("Радио", "868.700"),
        ("Система", "BLE ВКЛ"), ("Дополнительно", "СЕРВИС"),
        ("Закрыть", ""),
    ]
    row_y, row_h = 14 + line_h + 1, max(line_h, 12)
    for i, (label, value) in enumerate(rows):
        y = row_y + i * row_h
        selected = i == 0
        if selected:
            c.fill(0, y, W, row_h, layer="selection")
        c.text(3, y, c.ellipsize(label, 176, profile=profile, bold=selected), profile=profile,
               bold=selected, ink=not selected, layer=f"row{i}_label")
        if value:
            c.text(W - 66, y, c.ellipsize(value, 65, profile=profile), profile=profile,
                   bold=selected, ink=not selected, layer=f"row{i}_value")
    return c


def render_font_picker(profile: str = "Стандарт") -> Canvas:
    c = Canvas("font_picker")
    line_h = max(8, 8 + PROFILES[profile][1])
    c.text(2, 14, "Шрифт", profile=profile, layer="title")
    c.right(W - 2, 14, "<>OK", profile=profile, layer="hint")
    items = list(PROFILES) + ["Назад"]
    row_y, row_h, visible = 14 + line_h + 1, max(line_h, 12), min(8, len(items))
    for row, label in enumerate(items[:visible]):
        y = row_y + row * row_h
        selected = row == 0
        if selected:
            c.fill(0, y, W - 3, row_h, layer="selection")
        c.text(3, y, label, profile=profile, bold=selected, ink=not selected, layer=f"font{row}")
        if row == 0:
            c.right(W - 5, y, "OK", profile=profile, bold=True, ink=False, layer="active")
    c.rect(W - 2, row_y, 2, visible * row_h - 2, layer="scroll_track")
    c.fill(W - 2, row_y, 2, 28, layer="scroll_thumb")
    return c


def wrap(c: Canvas, text: str, max_w: int, profile: str) -> list[str]:
    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = word if not current else current + " " + word
        if c.text_width(trial, profile) <= max_w:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render_chat(profile: str = "Стандарт") -> Canvas:
    c = Canvas("chat")
    line_h = 8 + PROFILES[profile][1]
    y = 0
    entries = [
        ("(D) Александр Омск", "Проверка длинного сообщения: связь отличная, всё читается."),
        ("(R) Мария / поле", "Принято. Буду на связи через десять минут."),
        ("(D) Сергей", "Координаты получил!"),
    ]
    for idx, (name, message) in enumerate(reversed(entries)):
        c.text(10, y, c.ellipsize(name, W - 10, profile=profile, bold=True), profile=profile,
               bold=True, layer=f"chat{idx}_name")
        y += line_h + 1
        for line in wrap(c, message, W - 10, profile):
            c.text(10, y, line, profile=profile, layer=f"chat{idx}_text")
            y += line_h
        y += 2
    return c


def render_unread(profile: str = "Стандарт") -> Canvas:
    c = Canvas("unread_direct")
    line_h = 8 + PROFILES[profile][1]
    c.text(0, 0, "ЛС: 4 чел / 12", profile=profile, layer="header")
    c.fill(0, line_h + 1, W, 1, layer="divider")
    y = line_h + 3
    rows = [
        ("Александр Омск", "(5)", "Буду через десять минут"),
        ("Мария", "(3)", "Получила, спасибо!"),
        ("Сергей Поле-2", "(2)", "Координаты вижу"),
        ("ANX T114FIX", "(2)", "Раз два три, проверка"),
    ]
    for idx, (name, count, snippet) in enumerate(rows):
        count_w = c.text_width(count, profile)
        c.text(0, y, c.ellipsize(name, W - count_w - 3, profile=profile), profile=profile, layer=f"u{idx}_name")
        c.right(W, y, count, profile=profile, layer=f"u{idx}_count")
        y += line_h
        c.text(6, y, c.ellipsize(snippet, W - 6, profile=profile), profile=profile, layer=f"u{idx}_snippet")
        y += line_h + 2
    return c


def render_keyboard(profile: str = "Стандарт") -> Canvas:
    c = Canvas("keyboard")
    c.rect(0, 0, W - 1, 14, layer="preview_frame")
    c.text(3, 2, c.ellipsize("Встречаемся у северного входа", W - 6, profile=profile), profile=profile, layer="preview")
    keys = ["А", "Б", "В", "Г", "Д", "Е", "Ж", "З", "И", "Й", "К", "Л", "М", "Н", "О", "П", "Р", "С", "ТЯ", "_", "<-", "OK", "123", "X"]
    cell_w, grid_y = W // 6, 16
    cell_h = (H - grid_y) // 4
    for i, label in enumerate(keys):
        row, col = divmod(i, 6)
        x, y = col * cell_w, grid_y + row * cell_h
        kw = W - x if col == 5 else cell_w
        kh = H - y if row == 3 else cell_h
        selected = i == 21
        if selected:
            c.fill(x, y, kw, kh, layer="selection")
        if label == "_":
            c.fill(x + kw // 2 - 5, y + kh // 2 + 2, 10, 1, ink=not selected, layer="space")
        elif label == "<-":
            c.fill(x + kw // 2 - 4, y + kh // 2, 9, 1, ink=not selected, layer="delete")
        else:
            ty = y + max(0, (kh - 8) // 2)
            c.centered(x + kw // 2, ty, label, profile=profile, bold=selected, ink=not selected, layer=f"key{i}")
    return c


def render_target(profile: str = "Стандарт") -> Canvas:
    c = Canvas("target_picker")
    c.rect(0, 0, W - 1, 14, layer="header_frame")
    c.centered(W // 2, 2, "Куда отправить: контакт", profile=profile, layer="header")
    labels = ["Александр Омск", "Мария поле", "ANX T114FIX", "Сергей / машина", "Командир группы", "Тестовый компаньон", "Назад"]
    for row, label in enumerate(labels):
        y = 16 + row * 14
        selected = row == 1
        if selected:
            c.fill(0, y, W, 14, layer="selection")
        c.text(3, y + 2, c.ellipsize(label, W - 10, profile=profile, bold=selected), profile=profile,
               bold=selected, ink=not selected, layer=f"target{row}")
    c.rect(W - 2, 16, 2, 98, layer="scroll_track")
    c.fill(W - 2, 32, 2, 28, layer="scroll_thumb")
    return c


def make_contact_sheet(canvases: list[Canvas]) -> Image.Image:
    scale, label_h, columns = 3, 28, 2
    panel_w, panel_h = W * scale, H * scale
    rows = (len(canvases) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * panel_w, rows * (panel_h + label_h)), "#dad6c8")
    draw = ImageDraw.Draw(sheet)
    for idx, canvas in enumerate(canvases):
        col, row = idx % columns, idx // columns
        x, y = col * panel_w, row * (panel_h + label_h)
        draw.rectangle((x, y, x + panel_w - 1, y + label_h - 1), fill="#202020")
        draw.text((x + 8, y + 6), canvas.name, fill="white")
        sheet.paste(canvas.image(scale).convert("RGB"), (x, y + label_h))
    return sheet


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    canvases = [
        render_wood_safe(), render_main_clock(), render_settings_8(), render_font_picker(),
        render_chat(), render_unread(), render_keyboard(), render_target(),
    ]
    for canvas in canvases:
        canvas.image().save(out / f"{canvas.name}.png")
    make_contact_sheet(canvases).save(out / "contact_sheet_final.png")

    # Extremal font pass catches width/height errors hidden by the default profile.
    profile_matrix = []
    for profile in PROFILES:
        for renderer in (render_wood_safe, render_main_clock, render_settings_8, render_font_picker,
                         render_chat, render_unread, render_keyboard, render_target):
            canvas = renderer(profile)
            stat = canvas.stats()
            stat["profile"] = profile
            profile_matrix.append(stat)

    allowed_overlaps = {
        "scroll_thumb + scroll_track",
        "scroll_track + selection",
    }
    checks_total = 0
    failures: list[str] = []
    for stat in profile_matrix:
        label = f"{stat['profile']} / {stat['name']}"

        checks_total += 1
        bbox = stat["ink_bbox"]
        if bbox is None or not (0 <= bbox[0] <= bbox[2] < W and 0 <= bbox[1] <= bbox[3] < H):
            failures.append(f"{label}: ink bbox outside 250x122")

        checks_total += 1
        expected_clipped = 88 if stat["name"] == "wood_clock_final" else 0
        if stat["clipped_pixel_attempts"] != expected_clipped:
            failures.append(
                f"{label}: clipped={stat['clipped_pixel_attempts']}, expected={expected_clipped}"
            )

        checks_total += 1
        unexpected = set(stat["overlap_pixels"]) - allowed_overlaps
        if unexpected:
            failures.append(f"{label}: unexpected overlaps {sorted(unexpected)}")

        checks_total += 1
        if stat["ink_pixels"] <= 0:
            failures.append(f"{label}: empty framebuffer")

    report = {
        "display": [W, H],
        "renderer": "E213 profile fonts / Utf8Cyrillic5x7.h",
        "profiles": PROFILES,
        "screens": [c.stats() for c in canvases],
        "profile_matrix": profile_matrix,
        "summary": {
            "checks": checks_total,
            "passed": checks_total - len(failures),
            "failed": len(failures),
            "intentional_wood_clipped_endpoints": 88,
            "allowed_structural_overlaps": sorted(allowed_overlaps),
        },
        "failures": failures,
    }
    report_path = out / "qa_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wireless Paper exact QA: {checks_total - len(failures)} passed, {len(failures)} failed")
    print(out / "contact_sheet_final.png")
    print(report_path)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
