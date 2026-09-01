# -*- coding: utf-8 -*-
"""Generate publication screenshots for every SmartUI 2.1 target.

The repository-local generator imports the exact framebuffer simulator, then
renders documentation scenes with the same embedded glyph metrics:

* T096: native 160x80, thresholded bitmap fonts and exact xAdvance.
* T114: logical 128x64 mapped to physical 240x135 (1.875 x 2.109375, y+1).
* ProMicro OLED: native 128x64, actual Utf8Cyrillic5x7 glyph tables.
* Heltec V4.3 OLED: exact 128x64 GPS/mute/battery layout.
* Wireless Paper: native 250x122 one-bit E213 renderer profiles.
"""

from __future__ import annotations

import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


# Repository-relative paths keep the documentation renderer reproducible after
# cloning on Windows, Linux or macOS.
ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.dont_write_bytecode = True
sys.path.insert(0, str(TOOLS))

from simulate_smartui_ps17_qa import (  # noqa: E402
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
QA_OUT = ROOT / "docs" / "assets" / "qa"
LABEL_FONT_PATH = TOOLS / "font_sources" / "noto_sans_2_015" / "NotoSans-CondensedMedium.ttf"
UPTIME_SAMPLES = (59, 12 * 60, 7 * 3600, 12 * 3600, 3 * 86400, 2000 * 86400)


def format_clock_uptime(seconds: int) -> str:
    """Exact host equivalent of smartui::formatClockUptime()."""
    if seconds < 3600:
        return f"U {seconds // 60}m"
    if seconds < 86400:
        return f"U {seconds // 3600}h"
    days = seconds // 86400
    return "U 999+d" if days > 999 else f"U {days}d"


def clock_uptime_placement(width_fn, left_used: int, right_used: int,
                           seconds: int) -> tuple[str, int, int, int] | None:
    """Mirror drawClockUptimeBetween(), including its no-space fallback."""
    full = format_clock_uptime(seconds)
    for text, gap in ((full, 3), (full.replace(" ", "", 1), 2)):
        width = width_fn(text)
        right = right_used - gap
        left = right - width
        if left >= left_used + gap:
            return text, left, right, gap
    return None


def draw_frame_clock_uptime(frame: Frame, left_used: int, right_used: int,
                            y: int, seconds: int) -> tuple[str, int, int, int] | None:
    placement = clock_uptime_placement(frame.font.width, left_used, right_used, seconds)
    if placement is None:
        frame.facts["clock_uptime"] = "hidden-no-room"
        return None
    text, left, right, gap = placement
    if left < left_used + gap or right > right_used - gap:
        frame.violations.append(
            f"uptime {text} at {left}..{right} escapes {left_used}..{right_used} gap={gap}"
        )
    frame.text(right, y, text, "light", right=True, max_w=frame.font.width(text), tag="uptime")
    frame.facts["clock_uptime"] = {
        "text": text, "left": left, "right": right, "gap": gap,
        "left_used": left_used, "right_used": right_used,
    }
    return placement


def generate_esp32_docs_assets() -> None:
    """Run the exact ESP32 display simulators and publish canonical images."""
    QA_OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="smartui-docs-") as temp_dir:
        temp = Path(temp_dir)
        v4_dir = temp / "v4"
        paper_dir = temp / "wireless-paper"
        subprocess.run(
            [sys.executable, str(TOOLS / "simulate_v4_3_oled_qa.py"),
             "--out-dir", str(v4_dir)],
            check=True,
        )
        subprocess.run(
            [sys.executable, str(TOOLS / "simulate_wireless_paper_ps17_qa.py"),
             "--out-dir", str(paper_dir)],
            check=True,
        )

        copies = {
            v4_dir / "V4_3_OLED_CLOCK_UPTIME.png": OUT / "v4-3-oled-clock.png",
            v4_dir / "V4_3_OLED_SMARTUI_2_1_EXACT_QA_MATRIX.png":
                QA_OUT / "V4_3_OLED_SMARTUI_2_1_EXACT_QA_MATRIX.png",
            paper_dir / "wood_clock_final.png": OUT / "wireless-paper-wood-clock.png",
            paper_dir / "ble_pin.png": OUT / "wireless-paper-ble-pin.png",
            paper_dir / "compact_settings_final.png": OUT / "wireless-paper-settings.png",
            paper_dir / "keyboard.png": OUT / "wireless-paper-full-keyboard.png",
            paper_dir / "contact_sheet_final.png":
                QA_OUT / "WIRELESS_PAPER_SMARTUI_2_1_EXACT_QA_MATRIX.png",
        }
        for source, destination in copies.items():
            shutil.copyfile(source, destination)


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
    """Exact drawUiBatteryIcon(): ``w`` is the body, nub extends two pixels."""
    frame.rect(x, y, w, h, "green", outline=True, tag="battery")
    frame.rect(x + w, y + 3, 2, max(1, h - 6), "green", tag="battery nub")
    fill_w = max(1, ((w - 4) * pct + 50) // 100)
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
    for index, line in enumerate(lines):
        frame.text(1, y + row_h * index, line, "light", max_w=w - 2,
                   tag=f"status line {index}")
    return frame


def render_clock_t096(profile: BoardProfile, uptime_seconds: int = 12 * 3600,
                      muted: bool = True) -> Frame:
    frame = Frame(profile, "T096 clock", True)
    w = profile.logical_w
    gps = "GPS ON"
    frame.text(1, 1, gps, "green", max_w=58, tag="gps")
    gps_right = 1 + frame.font.width(gps)
    icon_x, icon_y, icon_w, icon_h = w - 22 - 4, 1, 22, 13
    voltage = "4.09V"
    voltage_x = icon_x - frame.font.width(voltage) - 3
    frame.text(voltage_x, 0, voltage, "green", max_w=frame.font.width(voltage), tag="voltage")
    draw_battery(frame, icon_x, icon_y, icon_w, icon_h)
    status_right = gps_right
    if muted:
        mute_x = gps_right + 4
        if mute_x + 16 <= voltage_x - 3:
            draw_mute(frame, mute_x, 1, 16)
            status_right = mute_x + 16
    draw_frame_clock_uptime(frame, status_right, voltage_x, 1, uptime_seconds)

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


def render_clock_t114(profile: BoardProfile, uptime_seconds: int = 12 * 3600,
                      muted: bool = True) -> Frame:
    # Chrome remains in the selected T114 font; it is not the forced compact
    # menu font.  This distinction is why the active-profile sweep is needed.
    frame = Frame(profile, "T114 clock", False)
    w = profile.logical_w
    gps = "GPS ON"
    frame.text(0, 0, gps, "green", max_w=48, tag="gps")
    gps_right = frame.font.width(gps)
    icon_x, icon_y, icon_w, icon_h = w - 18 - 2, 2, 18, 10
    voltage = "4.09V"
    voltage_x = icon_x - frame.font.width(voltage) - 3
    frame.text(voltage_x, 0, voltage, "green", max_w=frame.font.width(voltage), tag="voltage")
    draw_battery(frame, icon_x, icon_y, icon_w, icon_h)
    name_right = voltage_x - 2
    status_right = gps_right
    if muted:
        icon_size = min(12, max(9, frame.font.logical_height - 1))
        mute_x = gps_right + 3
        if mute_x + icon_size <= name_right:
            draw_mute(frame, mute_x, 1, icon_size)
            status_right = mute_x + icon_size
    draw_frame_clock_uptime(frame, status_right, name_right, 0, uptime_seconds)
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


def draw_oled_mute(oled: Oled, x: int, y: int, size: int = 8) -> None:
    """Procedural uiIconDrawMute() raster at the firmware's actual size."""
    grid = 12
    for gx, gy, gw, gh in ((1, 5, 3, 3), (4, 4, 2, 5)):
        x1 = x + (gx * size) // grid
        y1 = y + (gy * size) // grid
        x2 = x + ((gx + gw) * size + grid - 1) // grid
        y2 = y + ((gy + gh) * size + grid - 1) // grid
        oled.draw.rectangle((x1, y1, max(x1, x2 - 1), max(y1, y2 - 1)), fill=1)
    diag_size = size - 2
    for index in range(diag_size):
        oled.draw.point((x + 1 + index, y + 1 + diag_size - 1 - index), fill=1)


def draw_oled_battery(oled: Oled, milli_volts: int = 4090) -> int:
    icon_w, icon_h = 18, 10
    icon_x, icon_y = 128 - icon_w - 2, 2
    voltage = f"{milli_volts // 1000}.{(milli_volts % 1000) // 10:02d}V"
    voltage_x = icon_x - oled.text_width(voltage) - 3
    oled.text(voltage_x, 0, voltage)
    oled.draw.rectangle((icon_x, icon_y, icon_x + icon_w - 1, icon_y + icon_h - 1), outline=1)
    oled.draw.rectangle((icon_x + icon_w, icon_y + 3, icon_x + icon_w + 1,
                         icon_y + icon_h - 4), fill=1)
    fill_w = ((icon_w - 4) * 91 + 50) // 100
    oled.draw.rectangle((icon_x + 2, icon_y + 2, icon_x + 1 + fill_w,
                         icon_y + icon_h - 3), fill=1)
    return voltage_x


def render_clock_oled(style: tuple[str, int, bool] = OLED_STYLES[0],
                      uptime_seconds: int = 12 * 3600,
                      muted: bool = True,
                      errors: list[str] | None = None) -> Image.Image:
    oled = Oled(style)
    # Final GPS-less contract: no permanent GPS OFF badge. Quiet-mode status
    # stays useful and therefore occupies the left edge of clock chrome.
    status_right = -3
    if muted:
        draw_oled_mute(oled, 0, 1)
        status_right = 8
    battery_left = 108 - oled.text_width("4.09V") - 3
    name_right = battery_left - 2
    placement = clock_uptime_placement(oled.text_width, status_right, name_right, uptime_seconds)
    if placement is not None:
        uptime, left, right, gap = placement
        if left < status_right + gap or right > name_right - gap:
            oled.overflows.append(
                f"{style[0]}: uptime {uptime} at {left}..{right} escapes "
                f"{status_right}..{name_right} gap={gap}"
            )
        oled.text(right, 0, uptime, right=True)
    else:
        full = format_clock_uptime(uptime_seconds)
        if (name_right - 3 - oled.text_width(full) >= status_right + 3 or
                name_right - 2 - oled.text_width(full.replace(" ", "", 1)) >= status_right + 2):
            oled.overflows.append(f"{style[0]}: uptime hidden despite available room")
    actual_battery_left = draw_oled_battery(oled)
    if actual_battery_left != battery_left:
        oled.overflows.append(
            f"{style[0]}: battery metric drift {actual_battery_left}!={battery_left}"
        )
    for index, x in enumerate((39, 49, 59, 69, 79, 89)):
        if index == 1:
            oled.draw.rectangle((x - 1, 13, x + 1, 15), fill=1)
        else:
            oled.draw.point((x, 14), fill=1)
    oled.text(64, 18, "17:08", center=True, size=3)
    oled.text(0, 45, "CH1.2% A0.03%", max_width=128)
    oled.text(0, 55, "MSG/h 5", max_width=76)
    oled.text(127, 55, "29C", right=True)
    if errors is not None:
        errors.extend(oled.overflows)
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


def validate_clock_asset_layouts() -> int:
    """Real-font chrome sweep for every non-e-paper documentation target."""
    failures: list[str] = []
    checks = 0

    def chrome_violations(frame: Frame) -> list[str]:
        prefixes = ("uptime:", "gps:", "voltage:", "battery", "mute")
        return [item for item in frame.violations if item.startswith(prefixes)]

    for profile in make_profiles()["T096"]:
        for seconds in UPTIME_SAMPLES:
            for muted in (False, True):
                frame = render_clock_t096(profile, seconds, muted)
                checks += 1
                failures.extend(
                    f"T096 / {profile.profile} / {seconds}s / mute={muted}: {item}"
                    for item in chrome_violations(frame)
                )
                if (seconds == 12 * 3600 and not muted and
                        frame.facts.get("clock_uptime") == "hidden-no-room"):
                    failures.append(f"T096 / {profile.profile}: representative uptime is hidden")

    for profile in make_t114_active_profiles():
        for seconds in UPTIME_SAMPLES:
            for muted in (False, True):
                frame = render_clock_t114(profile, seconds, muted)
                checks += 1
                failures.extend(
                    f"T114 / {profile.profile} / {seconds}s / mute={muted}: {item}"
                    for item in chrome_violations(frame)
                )
                if (seconds == 12 * 3600 and not muted and
                        frame.facts.get("clock_uptime") == "hidden-no-room"):
                    failures.append(f"T114 / {profile.profile}: representative uptime is hidden")

    for style in OLED_STYLES:
        for seconds in UPTIME_SAMPLES:
            for muted in (False, True):
                errors: list[str] = []
                render_clock_oled(style, seconds, muted, errors)
                checks += 1
                failures.extend(
                    f"ProMicro / {style[0]} / {seconds}s / mute={muted}: {item}"
                    for item in errors
                )

    # DEVICE_STATUS is now telemetry only.  Uptime belongs exclusively to the
    # clock page, so stale documentation text must fail generation.
    status_profiles = (
        (make_profiles()["T096"][0], True, True),
        (make_t114_active_profiles()[0], True, False),
        (make_profiles()["OLED"][0], False, False),
    )
    for profile, gps, fem in status_profiles:
        frame = render_status(profile, gps=gps, fem=fem)
        checks += 1
        shown = " ".join(element.shown for element in frame.elements)
        if "Аптайм" in shown or "Работа 12" in shown or "U 12h" in shown:
            failures.append(f"{profile.board} status: stale uptime text remains")

    if failures:
        raise RuntimeError("clock asset QA failed:\n" + "\n".join(failures))
    print(f"Documentation clock chrome QA: {checks} passed, 0 failed")
    return checks


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    validate_clock_asset_layouts()
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
    generate_esp32_docs_assets()
    print(OUT)


if __name__ == "__main__":
    main()
