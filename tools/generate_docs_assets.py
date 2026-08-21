# -*- coding: utf-8 -*-
"""Generate publication screenshots for the SmartUI three-board release.

The repository-local generator imports the exact framebuffer simulator, then
renders documentation scenes with the same embedded glyph metrics:

* T096: native 160x80, thresholded bitmap fonts and exact xAdvance.
* T114: logical 128x64 mapped to physical 240x135 (1.875 x 2.109375, y+1).
* ProMicro OLED: native 128x64, actual Utf8Cyrillic5x7 glyph tables.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


# Repository-relative paths keep the documentation renderer reproducible after
# cloning on Windows, Linux or macOS.
ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.dont_write_bytecode = True
sys.path.insert(0, str(TOOLS))

from simulate_exp45_ui_qa import (  # noqa: E402
    BoardProfile,
    Frame,
    OledExactFont,
    T096ExactFont,
    T114ExactFont,
    T114_FONT_CHOICE_NAMES,
    draw_scrollbar,
    make_profiles,
    make_t114_active_profiles,
    render_keyboard,
    render_target,
    render_unread_senders,
)
from simulate_oled_128x64 import Oled, STYLES as OLED_STYLES  # noqa: E402
from simulate_t096_premium import (  # noqa: E402
    DEFAULT_PROFILE,
    VISIBLE_FONT_COUNT,
    VISIBLE_FONT_FIRST,
    load_compact_settings_font,
    load_font,
    profile_name,
)
from simulate_t114_fonts import (  # noqa: E402
    COLORS as T114_COLORS,
    FirmwareT114Font,
    PROFILES as T114_PROFILES,
    SCALE_X as T114_SCALE_X,
    SCALE_Y as T114_SCALE_Y,
    Y_OFFSET as T114_Y_OFFSET,
)


OUT = ROOT / "docs" / "assets" / "ui"
LABEL_FONT_PATH = TOOLS / "font_sources" / "noto_sans_2_015" / "NotoSans-CondensedMedium.ttf"


def label_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(LABEL_FONT_PATH), size=size)


def save_preview(image: Image.Image, stem: str, scale: int) -> Path:
    path = OUT / f"{stem}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST).save(path)
    return path


def draw_mute(frame: Frame, x: int, y: int, size: int) -> None:
    # Exact UI_ICONPACK_V1 procedural mute glyph from UITask.cpp: a compact
    # speaker body on the 12x12 design grid plus the rising strike-through.
    def fill(gx: int, gy: int, gw: int, gh: int) -> None:
        grid = 12
        x1 = x + (gx * size) // grid
        y1 = y + (gy * size) // grid
        x2 = x + ((gx + gw) * size + grid - 1) // grid
        y2 = y + ((gy + gh) * size + grid - 1) // grid
        frame.rect(x1, y1, max(1, x2 - x1), max(1, y2 - y1), "red", tag="mute")

    fill(1, 5, 3, 3)
    fill(4, 4, 2, 5)
    stroke = 2 if size >= 13 else 1
    diag_x = x + 1
    diag_y = y + 1
    diag_size = size - 2
    for i in range(0, diag_size, stroke):
        frame.rect(diag_x + i, diag_y + diag_size - 1 - i, stroke, stroke,
                   "red", tag="mute strike")


def draw_battery(frame: Frame, x: int, y: int, w: int, h: int, pct: int = 82) -> None:
    frame.rect(x, y, w - 2, h, "green", outline=True, tag="battery")
    frame.rect(x + w - 2, y + h // 3, 2, max(2, h // 3), "green", tag="battery nub")
    fill_w = max(1, ((w - 5) * pct) // 100)
    frame.rect(x + 2, y + 2, fill_w, max(1, h - 4), "green", tag="battery fill")


def draw_page_dots(frame: Frame, active: int = 1, count: int = 6) -> None:
    step = min(10, max(4, (frame.board.logical_w - 4) // max(1, count - 1)))
    x = (frame.board.logical_w - step * (count - 1)) // 2
    for index in range(count):
        if index == active:
            frame.rect(x - 1, 13, 3, 3, "light", tag="page active")
        else:
            frame.rect(x, 14, 1, 1, "light", tag="page dot")
        x += step


def render_rows(profile: BoardProfile, title: str, rows: list[tuple[str, str]], selected: int) -> Frame:
    """Firmware-equivalent compact menu with caller-provided real labels."""
    frame = Frame(profile, title, True)
    w, h = profile.logical_w, profile.logical_h
    line_h = max(8, frame.font.logical_height)
    row_y = 14 + line_h + 1
    if h <= 64 and row_y < 28:
        row_y = 28
    row_h = max(12, line_h)
    visible = max(1, min(4, (h - row_y) // row_h))
    item_count = len(rows)
    selected = min(max(0, selected), item_count - 1)
    start = max(0, selected - visible + 1) if selected >= visible else 0
    if item_count > visible and start + visible > item_count:
        start = item_count - visible

    frame.text(2, 14, title, "green", max_w=w - 38, tag="menu title")
    frame.text(w - 2, 14, "<>OK", "light", right=True, max_w=36, tag="menu hint")
    value_width = 66 if w > 140 else 50
    has_scrollbar = item_count > visible
    for row in range(visible):
        index = start + row
        if index >= item_count:
            break
        label, value = rows[index]
        y = row_y + row * row_h
        chosen = index == selected
        if chosen:
            frame.rect(0, y, w - (3 if has_scrollbar else 0), min(row_h, h - y),
                       "yellow", tag=f"row {row} fill")
        color = "dark" if chosen else "light"
        value_x = w - value_width
        label_w = value_x - 5 if value else w - 6
        frame.text(3, y, label, color, max_w=label_w, bold=chosen, tag=f"row {row} label")
        if value:
            frame.text(value_x, y, value, "dark" if chosen else "green",
                       max_w=value_width - 1, bold=chosen, tag=f"row {row} value")
    if has_scrollbar:
        draw_scrollbar(frame, start, visible, item_count, row_y,
                       min(h - row_y, visible * row_h - 2), "yellow")
    return frame


def render_picker(profile: BoardProfile, names: list[str], active: int = 0, cursor: int = 0) -> Frame:
    rows = [(name, "OK" if index == active else "") for index, name in enumerate(names)]
    rows.append(("Назад", ""))
    return render_rows(profile, "Шрифт", rows, cursor)


def render_status(profile: BoardProfile, *, gps: bool, fem: bool) -> Frame:
    """Mirror the final DEVICE_STATUS branch, including GPS-less SX1262 text."""
    frame = Frame(profile, "Состояние", True)
    w, h = profile.logical_w, profile.logical_h
    frame.text(w // 2, 14, "Состояние", "green", center=True, max_w=w, tag="status title")
    y = 27 if h > 64 else 28
    row_h = 13 if h > 64 else 12
    lines = [
        "АКБ 4.096В  BLE СВЯЗЬ",
        "RSSI -72  SNR 8.2",
        ("GPS ВКЛ  FEM " + ("ВКЛ" if fem else "НЕТ")) if gps
        else ("FEM ВКЛ" if fem else "Радио SX1262"),
    ]
    if h > 64:
        lines.append("Работа 12ч 34м")
    for index, line in enumerate(lines):
        frame.text(1, y + row_h * index, line, "light", max_w=w - 2,
                   tag=f"status line {index}")
    return frame


def render_clock_t096(profile: BoardProfile) -> Frame:
    frame = Frame(profile, "T096 clock", True)
    w = profile.logical_w
    gps = "GPS ON"
    frame.text(1, 1, gps, "green", max_w=58, tag="gps")
    gps_right = 1 + frame.font.width(gps)
    draw_mute(frame, gps_right + 4, 1, 16)
    draw_battery(frame, 140, 2, 18, 10)
    frame.text(136, 1, "4.09V", "green", right=True, max_w=40, tag="voltage")

    clock_font = T096ExactFont("Roboto clock", load_font(DEFAULT_PROFILE, "L"))
    time = "17:08"
    clock_font.draw(frame.image, (w - clock_font.width(time, True)) // 2, 17, time,
                    frame.color("green"), True)
    frame.text(w // 2, 43, "21.08.2026", "light", center=True, max_w=w, tag="date")
    frame.text(1, 43, "Н:3", "red", max_w=35, tag="unread")

    frame.rect(0, 60, 117, 19, "green", outline=True, tag="load box")
    frame.rect(0, 60, 3, 19, "green", tag="load accent")
    frame.text(5, 62, "CH1.2% AIR0.03%", "light", max_w=110, tag="load")
    frame.rect(120, 60, 40, 19, "green", outline=True, tag="temp box")
    frame.rect(120, 60, 3, 19, "green", tag="temp accent")
    frame.text(140, 62, "29C", "light", center=True, max_w=34, tag="temp")
    return frame


def render_clock_t114(profile: BoardProfile) -> Frame:
    frame = Frame(profile, "T114 clock", True)
    w = profile.logical_w
    gps = "GPS ON"
    frame.text(0, 0, gps, "green", max_w=48, tag="gps")
    gps_right = frame.font.width(gps)
    draw_mute(frame, gps_right + 3, 1, 10)
    draw_battery(frame, 112, 1, 14, 8)
    frame.text(109, 0, "4.09V", "green", right=True, max_w=35, tag="voltage")
    draw_page_dots(frame)

    raw_clock = FirmwareT114Font("Roboto", 28, 36, 30, 6)
    clock_font = T114ExactFont("Roboto clock", raw_clock)
    time = "17:08"
    clock_font.draw(frame.image, (w - clock_font.width(time, True)) // 2, 17, time,
                    frame.color("green"), True)
    frame.text(w // 2, 34, "21.08.2026", "light", center=True, max_w=w, tag="date")
    frame.text(0, 45, "CH1.2% A0.03%", "light", max_w=94, tag="load")
    frame.text(w - 1, 45, "29C", "green", right=True, max_w=28, tag="temp")
    frame.text(0, 54, "Н:3  MSG/h 5", "light", max_w=w, tag="messages")
    return frame


def render_clock_oled() -> Image.Image:
    oled = Oled(OLED_STYLES[0])
    # Final GPS-less contract: no permanent GPS OFF badge. Quiet-mode status
    # stays useful and therefore occupies the left edge of clock chrome.
    oled.mute(0, 0)
    oled.text(109, 0, "4.09V", right=True)
    oled.battery(112, 0, 82)
    for index, x in enumerate((39, 49, 59, 69, 79, 89)):
        if index == 1:
            oled.draw.rectangle((x - 1, 13, x + 1, 15), fill=1)
        else:
            oled.draw.point((x, 14), fill=1)
    oled.text(64, 18, "17:08", center=True, size=3)
    oled.text(0, 45, "CH1.2% A0.03%", max_width=128)
    oled.text(0, 55, "MSG/h 5", max_width=76)
    oled.text(127, 55, "29C", right=True)
    return oled.img.convert("RGB")


def t096_font_samples() -> Image.Image:
    cells: list[tuple[str, Image.Image]] = []
    compact = T096ExactFont("compact", load_compact_settings_font(DEFAULT_PROFILE))
    for profile_id in range(VISIBLE_FONT_FIRST, VISIBLE_FONT_FIRST + VISIBLE_FONT_COUNT):
        image = Image.new("RGB", (160, 80), (3, 9, 12))
        active = T096ExactFont(profile_name(profile_id), load_font(profile_id, "M"))
        compact.draw(image, 3, 2, "Шрифт", (29, 240, 122))
        name = profile_name(profile_id)
        shown = active.fit if False else name
        # Long names are safely reduced by dropping trailing glyphs; the label above the
        # contact sheet keeps the full public name.
        while shown and active.width(shown) > 154:
            shown = shown[:-1]
        active.draw(image, 3, 23, shown, (255, 224, 74))
        sample = "Связь 123"
        while sample and active.width(sample) > 154:
            sample = sample[:-1]
        active.draw(image, 3, 49, sample, (237, 245, 244))
        cells.append((name, image))
    return make_catalog(cells, columns=3, native_scale=2)


def t114_font_samples() -> Image.Image:
    cells: list[tuple[str, Image.Image]] = []
    for name, family, size_px, height_px in T114_PROFILES:
        image = Image.new("RGB", (240, 135), T114_COLORS["bg"])
        draw = ImageDraw.Draw(image)
        font = FirmwareT114Font(family, size_px, height_px, height_px - 4, 4)
        font.draw_logical(draw, 2, 3, name, T114_COLORS["yellow"])
        font.draw_logical(draw, 2, 25, "Связь 123", T114_COLORS["light"])
        font.draw_logical(draw, 2, 47, "ЛС принято", T114_COLORS["green"])
        cells.append((name, image))
    return make_catalog(cells, columns=2, native_scale=1)


def oled_font_samples() -> Image.Image:
    cells: list[tuple[str, Image.Image]] = []
    for style in OLED_STYLES:
        oled = Oled(style)
        oled.text(0, 2, style[0])
        oled.text(0, 20, "Связь 123")
        oled.text(0, 38, "ЛС принято")
        cells.append((style[0], oled.img.convert("RGB")))
    return make_catalog(cells, columns=2, native_scale=3)


def make_catalog(cells: list[tuple[str, Image.Image]], columns: int, native_scale: int) -> Image.Image:
    gap = 12
    title_h = 25
    scaled_w = cells[0][1].width * native_scale
    scaled_h = cells[0][1].height * native_scale
    rows = math.ceil(len(cells) / columns)
    sheet = Image.new("RGB", (columns * scaled_w + (columns - 1) * gap,
                              rows * (scaled_h + title_h) + (rows - 1) * gap), (13, 17, 22))
    draw = ImageDraw.Draw(sheet)
    font = label_font(16)
    for index, (name, image) in enumerate(cells):
        col = index % columns
        row = index // columns
        x = col * (scaled_w + gap)
        y = row * (scaled_h + title_h + gap)
        draw.text((x + 3, y + 2), name, font=font, fill=(225, 235, 240))
        preview = image.resize((scaled_w, scaled_h), Image.Resampling.NEAREST)
        sheet.paste(preview, (x, y + title_h))
    return sheet


def make_overview(items: dict[str, list[tuple[str, Image.Image]]]) -> Image.Image:
    labels = ["Часы и статус", "Настройки", "Шрифты", "Клавиатура", "Адресат", "Состояние"]
    cell_w, cell_h = 300, 165
    left_w, top_h, gap = 150, 35, 10
    width = left_w + len(labels) * cell_w + (len(labels) - 1) * gap
    height = top_h + len(items) * cell_h + (len(items) - 1) * gap
    sheet = Image.new("RGB", (width, height), (13, 17, 22))
    draw = ImageDraw.Draw(sheet)
    header = label_font(18)
    board_font = label_font(20)
    for col, title in enumerate(labels):
        draw.text((left_w + col * (cell_w + gap) + 5, 5), title, font=header, fill=(225, 235, 240))
    for row, (board, scenes) in enumerate(items.items()):
        y = top_h + row * (cell_h + gap)
        draw.text((8, y + cell_h // 2 - 12), board, font=board_font, fill=(98, 216, 255))
        for col, (_, image) in enumerate(scenes):
            x = left_w + col * (cell_w + gap)
            ratio = min((cell_w - 4) / image.width, (cell_h - 4) / image.height)
            render_w = max(1, int(image.width * ratio))
            render_h = max(1, int(image.height * ratio))
            preview = image.resize((render_w, render_h), Image.Resampling.NEAREST)
            sheet.paste(preview, (x + (cell_w - render_w) // 2, y + (cell_h - render_h) // 2))
            draw.rectangle((x, y, x + cell_w - 1, y + cell_h - 1), outline=(58, 77, 88))
    return sheet


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    profiles = make_profiles()
    t096 = profiles["T096"][0]
    t114 = make_t114_active_profiles()[0]
    oled = profiles["OLED"][0]

    common_root = [
        ("Избранное", "3 пункта"),
        ("Уведомления", "Звук"),
        ("Звук и вибро", "МАКС"),
        ("Экран", "Roboto L"),
        ("Радио и GPS", "GPS ВКЛ"),
        ("Система", "BLE ВКЛ"),
        ("Дополнительно", "СЕРВИС"),
        ("Закрыть", ""),
    ]
    promicro_root = [
        ("Избранное", "3 пункта"),
        ("Уведомления", "Звук"),
        ("Звук и вибро", "МАКС"),
        ("Экран", "Classic"),
        ("Радио", "869.618"),
        ("Система", "BLE ВКЛ"),
        ("Дополнительно", "СЕРВИС"),
        ("Закрыть", ""),
    ]
    t096_names = [profile_name(index) for index in range(VISIBLE_FONT_FIRST,
                                                          VISIBLE_FONT_FIRST + VISIBLE_FONT_COUNT)]
    oled_names = [style[0] for style in OLED_STYLES]

    board_scenes: dict[str, list[tuple[str, Image.Image]]] = {
        "T096 FEM": [
            ("clock", render_clock_t096(t096).image),
            ("settings", render_rows(t096, "Настройки", common_root, 0).image),
            ("fonts", render_picker(t096, t096_names, 0, 0).image),
            ("keyboard", render_keyboard(t096, desired=True, cursor=21).image),
            ("target", render_target(t096, desired=True, count=12, cursor=4).image),
            ("status", render_status(t096, gps=True, fem=True).image),
        ],
        "T114": [
            ("clock", render_clock_t114(t114).image),
            ("settings", render_rows(t114, "Настройки", common_root, 0).image),
            ("fonts", render_picker(t114, list(T114_FONT_CHOICE_NAMES), 0, 0).image),
            ("keyboard", render_keyboard(t114, desired=True, cursor=21).image),
            ("target", render_target(t114, desired=True, count=12, cursor=4).image),
            ("status", render_status(t114, gps=True, fem=False).image),
        ],
        "ProMicro RA62": [
            ("clock", render_clock_oled()),
            ("settings", render_rows(oled, "Настройки", promicro_root, 0).image),
            ("fonts", render_picker(oled, oled_names, 0, 0).image),
            ("keyboard", render_keyboard(oled, desired=True, cursor=21).image),
            ("target", render_target(oled, desired=True, count=12, cursor=4).image),
            ("status", render_status(oled, gps=False, fem=False).image),
        ],
    }

    slugs = {"T096 FEM": "t096", "T114": "t114", "ProMicro RA62": "promicro-ra62"}
    scales = {"T096 FEM": 4, "T114": 3, "ProMicro RA62": 4}
    for board, scenes in board_scenes.items():
        for scene, image in scenes:
            save_preview(image, f"{slugs[board]}-{scene}", scales[board])

    unread = {
        "t096-unread-dm": (render_unread_senders(t096, count=1, cursor=0).image, 4),
        "t114-unread-dm": (render_unread_senders(t114, count=1, cursor=0).image, 3),
        "promicro-ra62-unread-dm": (render_unread_senders(oled, count=1, cursor=0).image, 4),
    }
    for stem, (image, scale) in unread.items():
        save_preview(image, stem, scale)

    make_overview(board_scenes).save(OUT / "ui-overview-three-boards.png")
    t096_font_samples().save(OUT / "font-catalog-t096.png")
    t114_font_samples().save(OUT / "font-catalog-t114.png")
    oled_font_samples().save(OUT / "font-catalog-promicro-ra62.png")
    print(OUT)


if __name__ == "__main__":
    main()
