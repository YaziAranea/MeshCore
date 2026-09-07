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
from dataclasses import replace
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
    EmbeddedRaw,
    Element,
    glyph_ink_bounds,
    OledExactFont,
    T096ExactFont,
    T114ExactFont,
    T114_FONT_CHOICE_NAMES,
    T114_THEME_CHOICE_NAMES,
    t114_theme_colors,
    draw_scrollbar,
    make_profiles,
    make_t114_active_profiles,
    render_keyboard,
    render_target,
    render_send_confirmation,
    render_appearance_picker,
    render_unread_senders,
)
from simulate_oled_128x64 import Oled, STYLES as OLED_STYLES  # noqa: E402
from simulate_icon_alignment_beta2 import draw_frame_icon  # noqa: E402
from simulate_v4_3_oled_qa import draw_firmware_mute, draw_firmware_battery  # noqa: E402
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
UPTIME_SAMPLES = (59, 12 * 60, 7 * 3600, 40 * 3600 + 5 * 60, 3 * 86400, 2000 * 86400)


def format_clock_uptime(seconds: int) -> str:
    """Exact host equivalent of smartui::formatClockUptime()."""
    return f"U {seconds // 3600}h{seconds // 60 % 60:02d}m"


def clock_uptime_placement(width_fn, left_used: int, right_used: int,
                           seconds: int) -> tuple[str, int, int, int] | None:
    """Mirror drawClockUptimeBetween(), including its no-space fallback."""
    full = format_clock_uptime(seconds)
    for text, gap in ((full, 3), (full.replace(" ", "", 1), 2)):
        width = width_fn(text)
        right = right_used - gap
        left = right - width
        if left >= left_used + gap:
            right = left_used + (right_used - left_used + width) // 2
            left = right - width
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
        core_dir = temp / "core"
        subprocess.run([sys.executable,str(TOOLS/"simulate_smartui_ps17_qa.py"),
                        "--out",str(core_dir)],check=True)
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
            paper_dir / "idle_clock_final.png": OUT / "wireless-paper-clock.png",
            paper_dir / "ble_pin.png": OUT / "wireless-paper-ble-pin.png",
            paper_dir / "compact_settings_final.png": OUT / "wireless-paper-settings.png",
            paper_dir / "keyboard.png": OUT / "wireless-paper-full-keyboard.png",
            paper_dir / "send_confirmation.png": OUT / "wireless-paper-send-confirm.png",
            paper_dir / "target_home.png": OUT / "wireless-paper-target-home.png",
            paper_dir / "target_initial.png": OUT / "wireless-paper-target-initial.png",
            paper_dir / "contact_sheet_final.png":
                QA_OUT / "WIRELESS_PAPER_SMARTUI_2_1_EXACT_QA_MATRIX.png",
        }
        for name in ("T096_SMARTUI_PS17_EXACT_QA_MATRIX.png","T114_SMARTUI_PS17_EXACT_QA_MATRIX.png",
                     "OLED_SMARTUI_PS17_EXACT_QA_MATRIX.png","T114_SMARTUI_PS17_GPS_APPEARANCE_PHYSICAL_QA.png"):
            copies[core_dir/name]=QA_OUT/name
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
    draw_frame_icon(frame, x, y, "muted_icon", size, "red")
    frame.elements.append(Element("mute", frame.logical_box_to_physical(x, y, size, size)))


def aligned_icon_y(frame: Frame, y: int, size: int) -> int:
    """Mirror uiTextAlignedIconY and the bitmap ink-metric getters."""
    ink = glyph_ink_bounds(frame.font.raw.glyph("H"))
    top = int(ink[1] / frame.board.scale_y)
    height = math.ceil((ink[3] - ink[1]) / frame.board.scale_y)
    dy = top + int((height - size) / 2)
    return y + min(max(0, dy), max(0, frame.font.logical_height - size))


def draw_battery(frame: Frame, x: int, y: int, w: int, h: int, pct: int = 82) -> None:
    """Exact drawUiBatteryIcon(): ``w`` is the body, nub extends two pixels."""
    frame.rect(x, y, w, h, "green", outline=True, tag="battery")
    frame.rect(x + w, y + 3, 2, max(1, h - 6), "green", tag="battery nub")
    fill_w = max(1, ((w - 4) * pct + 50) // 100)
    frame.rect(x + 2, y + 2, fill_w, max(1, h - 4), "green", tag="battery fill")
    frame.elements.append(Element("battery", frame.logical_box_to_physical(x, y, w + 2, h)))


def draw_page_dots(frame: Frame, active: int = 1, count: int = 6) -> None:
    step = min(10, max(4, (frame.board.logical_w - 4) // max(1, count - 1)))
    x = (frame.board.logical_w - step * (count - 1)) // 2
    for index in range(count):
        if index == active:
            frame.rect(x - 1, 13, 3, 3, "light", tag="page active")
        else:
            frame.rect(x, 14, 1, 1, "light", tag="page dot")
        x += step


def render_rows(profile: BoardProfile, title: str, rows: list[tuple[str, str]], selected: int,
                *, root_menu: bool = False, action: str = "Выбрать") -> Frame:
    """Firmware-equivalent compact menu with caller-provided real labels."""
    frame = Frame(profile, title, True)
    w, h = profile.logical_w, profile.logical_h
    line_h = max(8, frame.font.logical_height)
    row_y = 14 + line_h + 1
    if h <= 64 and row_y < 28:
        row_y = 28
    row_h = max(12, line_h)
    visible = max(1, min(8 if profile.board=="Wireless Paper" else 4, (h - row_y) // row_h))
    item_count = len(rows)
    selected = min(max(0, selected), item_count - 1)
    start = max(0, selected - visible + 1) if selected >= visible else 0
    if item_count > visible and start + visible > item_count:
        start = item_count - visible

    if root_menu: action="Закрыть" if rows[selected][0]=="Закрыть" else "Открыть"
    hint_w=frame.font.width(action)
    frame.text(2, 14, title, "green", max_w=w-hint_w-8, tag="menu title")
    frame.text(w - 2, 14, action, "light", right=True, max_w=hint_w, tag="menu hint")
    value_width = 66 if w > 140 else 50
    has_scrollbar = item_count > visible
    for row in range(visible):
        index = start + row
        if index >= item_count:
            break
        label, value = rows[index]
        marker = ">" if root_menu and label!="Закрыть" else ""
        if root_menu: value=""
        y = row_y + row * row_h
        chosen = index == selected
        if chosen:
            frame.rect(0, y, w - (3 if has_scrollbar else 0), min(row_h, h - y),
                       "yellow", tag=f"row {row} fill")
        color = "dark" if chosen else "light"
        value_x = w - value_width
        marker_w=frame.font.width(marker)+4 if marker else 0
        label_w = value_x - 5 if value else w - 3 - marker_w - 5
        frame.text(3, y, label, color, max_w=label_w, tag=f"row {row} label")
        if value:
            frame.text(value_x, y, value, "dark" if chosen else "green",
                       max_w=value_width - 1, tag=f"row {row} value")
        if marker:
            frame.text(w-5,y,marker,color,right=True,max_w=frame.font.width(marker),tag=f"row {row} open")
    if has_scrollbar:
        draw_scrollbar(frame, start, visible, item_count, row_y,
                       min(h - row_y, visible * row_h - 2), "yellow")
    return frame


def render_picker(profile: BoardProfile, names: list[str], active: int = 0, cursor: int = 0) -> Frame:
    return render_appearance_picker(profile,font_picker=True,cursor=cursor,active=active,choices=names)


def render_status(profile: BoardProfile, *, gps: bool, fem: bool,
                  mv: int = 4096, ble: str = "СВЯЗЬ", rssi: int = -72,
                  snr: float = 8.2, gps_state: str = "FIX") -> Frame:
    """Mirror the final DEVICE_STATUS branch, including GPS-less SX1262 text."""
    frame = Frame(profile, "Состояние", True)
    w, h = profile.logical_w, profile.logical_h
    frame.text(w // 2, 14, "Состояние", "green", center=True, max_w=w, tag="status title")
    y=max(28,14+frame.font.logical_height+1)
    row_h=max(12,frame.font.logical_height)
    radio = f"RSSI {rssi}  SNR {snr:.1f}"
    if frame.font.width(radio)>w-2: radio=f"R{rssi} S{snr:.1f}"
    voltage = f"{mv/1000:.3f}V" if mv else "--V"
    lines = [
        f"{voltage} BLE:{ble}",
        radio,
        (f"GPS {gps_state}  FEM " + ("ВКЛ" if fem else "НЕТ")) if gps
        else ("FEM ВКЛ" if fem else "Радио SX1262"),
    ]
    for index, line in enumerate(lines):
        shown=frame.text(1, y + row_h * index, line, "light", max_w=w - 2,
                         tag=f"status line {index}")
        if shown != line: frame.violations.append(f"critical status value truncated: {line} -> {shown}")
    return frame


def make_t096_clock_profiles() -> list[BoardProfile]:
    base = make_profiles()["T096"]
    result = []
    for index in range(VISIBLE_FONT_FIRST, VISIBLE_FONT_FIRST + VISIBLE_FONT_COUNT):
        chrome = T096ExactFont("chrome", load_font(index, "S"))
        result.append(replace(base[index % 5], profile=profile_name(index), font_id=index,
                              desired_font=chrome, current_font=chrome))
    return result


def render_clock_t096(profile: BoardProfile, uptime_seconds: int = 40 * 3600 + 5 * 60,
                      muted: bool = True, *, gps_state: str = "FIX", sats: int = 12,
                      time_valid: bool = True) -> Frame:
    frame = Frame(profile, "T096 clock", True)
    w = profile.logical_w
    gps = f"GPS {gps_state}"
    if not muted and gps_state != "OFF" and sats>=0: gps += f" {min(sats,99)}"
    frame.text(1, 0, gps, "green", max_w=10000, tag="gps")
    gps_right = 1 + frame.font.width(gps)
    icon_x, icon_y, icon_w, icon_h = w - 22 - 4, 1, 22, 13
    icon_y = aligned_icon_y(frame, 0, icon_h)
    voltage = "4.09V"
    voltage_x = icon_x - frame.font.width(voltage) - 3
    frame.text(voltage_x, 0, voltage, "green", max_w=frame.font.width(voltage), tag="voltage")
    draw_battery(frame, icon_x, icon_y, icon_w, icon_h)
    status_right = gps_right
    if muted:
        mute_x = gps_right + 4
        if mute_x + 16 <= voltage_x - 3:
            draw_mute(frame, mute_x, aligned_icon_y(frame, 0, 16), 16)
            status_right = mute_x + 16
        else:
            frame.violations.append("required mute icon hidden")

    clock_font = T096ExactFont("clock", load_font(profile.font_id, "L"))
    time = "17:08" if time_valid else "--:--"
    clock_font.draw(frame.image, (w - clock_font.width(time, True)) // 2, 15, time,
                    frame.color("green"), True)
    frame.elements.append(Element("time", clock_font.ink_box((w - clock_font.width(time, True)) // 2, 15, time, True), time))
    frame.font = T096ExactFont("metadata", load_compact_settings_font(profile.font_id))
    draw_frame_clock_uptime(frame, 0, w, 35, uptime_seconds)
    frame.text(w // 2, 47, "07.09.2026" if time_valid else "--.--.----", "light", center=True, max_w=w, tag="date")
    frame.text(1, 47, "Н:3", "red", max_w=35, tag="unread")

    frame.rect(0, 63, 117, 17, "green", outline=True, tag="load box")
    frame.rect(0, 63, 3, 17, "green", tag="load accent")
    frame.text(5, 63, "CH1.2% AIR0.03%", "light", max_w=110, tag="load")
    frame.rect(120, 63, 40, 17, "green", outline=True, tag="temp box")
    frame.rect(120, 63, 3, 17, "green", tag="temp accent")
    frame.text(140, 63, "29C", "light", center=True, max_w=34, tag="temp")
    return frame


def render_clock_t114(profile: BoardProfile, uptime_seconds: int = 40 * 3600 + 5 * 60,
                      muted: bool = True, *, gps_state: str = "FIX", time_valid: bool = True) -> Frame:
    # Chrome remains in the selected T114 font; it is not the forced compact
    # menu font.  This distinction is why the active-profile sweep is needed.
    frame = Frame(profile, "T114 clock", False)
    w = profile.logical_w
    gps = f"GPS {gps_state}"
    frame.text(0, 0, gps, "green", max_w=10000, tag="gps")
    gps_right = frame.font.width(gps)
    icon_x, icon_y, icon_w, icon_h = w - 18 - 2, 2, 18, 10
    icon_y = aligned_icon_y(frame, 0, icon_h)
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
            draw_mute(frame, mute_x, aligned_icon_y(frame, 0, icon_size), icon_size)
            status_right = mute_x + icon_size
        else:
            frame.violations.append("required mute icon hidden")
    draw_page_dots(frame)

    raw_clock = EmbeddedRaw("meshcore_st7789_font", "meshcoreSt7789Fonts", 15)
    clock_font = T114ExactFont("Roboto clock", raw_clock)
    time = "17:08" if time_valid else "--:--"
    clock_font.draw(frame.image, (w - clock_font.width(time)) // 2, 17, time,
                    frame.color("green"))
    frame.elements.append(Element("time", clock_font.ink_box((w - clock_font.width(time)) // 2, 17, time), time))
    saved_font = frame.font
    frame.font = T114ExactFont("metadata", EmbeddedRaw("meshcore_st7789_font", "meshcoreSt7789Fonts", 0))
    date = "07.09" if time_valid else "--.--"
    date_left = w - 1 - frame.font.width(date)
    frame.text(w - 1, 34, date, "light", right=True, max_w=frame.font.width(date), tag="date")
    draw_frame_clock_uptime(frame, 0, date_left - 4, 34, uptime_seconds)
    frame.font = saved_font
    frame.text(0, 42, "CH1.2% A0.03%", "light", max_w=94, tag="load")
    frame.text(w - 1, 42, "29C", "green", right=True, max_w=28, tag="temp")
    frame.text(0, 52, "Н:3  MSG/h 5", "light", max_w=w, tag="messages")
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
                      uptime_seconds: int = 40 * 3600 + 5 * 60,
                      muted: bool = True,
                      errors: list[str] | None = None) -> Image.Image:
    from simulate_v4_3_oled_qa import clock_scene
    # Same measured OLED path on ProMicro, with no invented GPS badge.
    image, failures = clock_scene(style, "", muted, uptime_seconds)
    if errors is not None:
        errors.extend(failures)
    return image.convert("RGB")


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
        foreground, background = t114_theme_colors()[0]
        image = Image.new("RGB", (240, 135), background)
        draw = ImageDraw.Draw(image)
        font = FirmwareT114Font(family, size_px, height_px, height_px - 4, 4)
        font.draw_logical(draw, 2, 3, name, foreground)
        font.draw_logical(draw, 2, 25, "Связь 123", foreground)
        font.draw_logical(draw, 2, 47, "ЛС принято", foreground)
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
        errors = list(frame.violations)
        for index, first in enumerate(frame.elements):
            if first.physical_box is None:
                errors.append(f"{first.tag}: required text disappeared")
                continue
            for second in frame.elements[index + 1:]:
                if second.physical_box is None:
                    continue
                a, b = first.physical_box, second.physical_box
                if max(a[0], b[0]) < min(a[2], b[2]) and max(a[1], b[1]) < min(a[3], b[3]):
                    errors.append(f"{first.tag}/{second.tag}: overlapping ink boxes {a}/{b}")
        if frame.facts.get("clock_uptime") == "hidden-no-room":
            errors.append("uptime unexpectedly hidden")
        return errors

    for profile in make_t096_clock_profiles():
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
        for gps_state,sats in (("OFF",-1),("...",0),("FIX",99)):
            for muted in (False,True):
                frame=render_clock_t096(profile,muted=muted,gps_state=gps_state,sats=sats,time_valid=False)
                checks+=1
                failures.extend(f"T096/{profile.profile}/{gps_state}/mute={muted}: {e}" for e in chrome_violations(frame))

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
        for gps_state in ("OFF","...","FIX"):
            for muted in (False,True):
                frame=render_clock_t114(profile,muted=muted,gps_state=gps_state,time_valid=False)
                checks+=1
                failures.extend(f"T114/{profile.profile}/{gps_state}/mute={muted}: {e}" for e in chrome_violations(frame))

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
    for board,profiles in make_profiles().items():
        for profile in profiles:
            for ble,mv in (("СВЯЗЬ",4096),("ЖДЁТ",0),("ВЫКЛ",2700)):
                frame=render_status(profile,gps=board!="OLED",fem=board=="T096",
                                    ble=ble,mv=mv,rssi=-130,snr=-20.0)
                checks+=1
                failures.extend(f"status/{board}/{profile.profile}/{ble}: {e}" for e in frame.violations)

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
        ("Избранное", ""),
        ("Уведомления", ""),
        ("Звук и вибро", ""),
        ("Экран", ""),
        ("Радио и GPS", ""),
        ("Система", ""),
        ("Дополнительно", ""),
        ("Закрыть", ""),
    ]
    promicro_root = [
        ("Избранное", ""),
        ("Уведомления", ""),
        ("Звук и вибро", ""),
        ("Экран", ""),
        ("Радио", ""),
        ("Система", ""),
        ("Дополнительно", ""),
        ("Закрыть", ""),
    ]
    t096_names = [profile_name(index) for index in range(VISIBLE_FONT_FIRST,
                                                          VISIBLE_FONT_FIRST + VISIBLE_FONT_COUNT)]
    oled_names = [style[0] for style in OLED_STYLES]

    board_scenes: dict[str, list[tuple[str, Image.Image]]] = {
        "T096 FEM": [
            ("clock", render_clock_t096(make_t096_clock_profiles()[5]).image),
            ("settings", render_rows(t096, "Настройки", common_root, 0,root_menu=True).image),
            ("fonts", render_picker(t096, t096_names, 0, 0).image),
            ("keyboard", render_keyboard(t096, desired=True, cursor=21).image),
            ("target", render_target(t096, desired=True, count=12, cursor=4).image),
            ("status", render_status(t096, gps=True, fem=True).image),
        ],
        "T114": [
            ("clock", render_clock_t114(t114).image),
            ("settings", render_rows(t114, "Настройки", common_root, 0,root_menu=True).image),
            ("fonts", render_picker(t114, list(T114_FONT_CHOICE_NAMES), 0, 0).image),
            ("keyboard", render_keyboard(t114, desired=True, cursor=21).image),
            ("target", render_target(t114, desired=True, count=12, cursor=4).image),
            ("status", render_status(t114, gps=True, fem=False).image),
        ],
        "ProMicro RA62": [
            ("clock", render_clock_oled()),
            ("settings", render_rows(oled, "Настройки", promicro_root, 0,root_menu=True).image),
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

    for board,profile in (("T096 FEM",t096),("T114",t114),("ProMicro RA62",oled)):
        extra = (
            ("send-confirm",render_send_confirmation(profile)),
            ("keyboard-typing",render_keyboard(profile,desired=True,page=1,cursor=14)),
            ("target-home",render_target(profile,desired=True,count=4,cursor=0,kind="Контакты",
                         labels=["* Мария","* Александр","Все контакты >","По букве >"])),
            ("target-initial",render_target(profile,desired=True,count=5,cursor=2,kind="Первая буква",
                         labels=["A","А","Е","М","#"])),
        )
        for scene,frame in extra:
            if frame.violations: raise RuntimeError(f"{board}/{scene}: {frame.violations}")
            save_preview(frame.image,f"{slugs[board]}-{scene}",scales[board])

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
    make_catalog([(name, render_clock_t114(replace(t114, theme_id=index)).image)
                  for index, name in enumerate(T114_THEME_CHOICE_NAMES)],
                 columns=2, native_scale=2).save(OUT / "theme-catalog-t114.png")
    oled_font_samples().save(OUT / "font-catalog-promicro-ra62.png")
    generate_esp32_docs_assets()
    print(OUT)


if __name__ == "__main__":
    main()
