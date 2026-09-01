# -*- coding: utf-8 -*-
"""Exact 128x64 OLED checks for the Heltec V4.3 SmartUI profile.

This imports the firmware's Utf8Cyrillic5x7 tables through the existing OLED
simulator.  It specifically guards the GPS/mute/battery chrome that differs
from the GPS-less ProMicro profile.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

from simulate_oled_128x64 import H, SCALE, STYLES, W, Oled, font


SCENES = ("GPS OFF + mute", "GPS ON + mute", "GPS ON", "ADC calibration", "BLE PIN")
UPTIME_SAMPLES = (59, 12 * 60, 7 * 3600, 12 * 3600, 3 * 86400, 2000 * 86400)
STATUS_ICON_SIZE = 8
BATTERY_ICON_X = W - 18 - 2


def format_clock_uptime(seconds: int) -> str:
    """Exact host equivalent of smartui::formatClockUptime()."""
    if seconds < 3600:
        return f"U {seconds // 60}m"
    if seconds < 86400:
        return f"U {seconds // 3600}h"
    days = seconds // 86400
    return "U 999+d" if days > 999 else f"U {days}d"


def clock_uptime_placement(
    oled: Oled, left_used: int, right_used: int, seconds: int
) -> tuple[str, int, int, int] | None:
    """Mirror drawClockUptimeBetween(), including its no-space fallback."""
    full = format_clock_uptime(seconds)
    for text, gap in ((full, 3), (full.replace(" ", "", 1), 2)):
        width = oled.text_width(text)
        right = right_used - gap
        left = right - width
        if left >= left_used + gap:
            return text, left, right, gap
    return None


def draw_firmware_battery(oled: Oled, milli_volts: int = 4090) -> int:
    """Generic HomeScreen battery geometry used by V4.3 and ProMicro."""
    icon_w, icon_h = 18, 10
    icon_x, icon_y = W - icon_w - 2, 2
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


def draw_firmware_mute(oled: Oled, x: int, y: int, size: int = STATUS_ICON_SIZE) -> None:
    """Exact procedural uiIconDrawMute() raster."""
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


def clock_scene(
    style: tuple[str, int, bool], gps_label: str, muted: bool,
    uptime_seconds: int = 12 * 3600,
) -> tuple[Image.Image, list[str]]:
    oled = Oled(style)
    voltage_x = BATTERY_ICON_X - oled.text_width("4.09V") - 3
    name_right = voltage_x - 2
    gps_right = oled.text_width(gps_label)
    mute_x = gps_right + 3
    status_right = gps_right

    if gps_right > name_right:
        oled.overflows.append(f"{style[0]}: {gps_label} reaches battery group at {gps_right}>{name_right}")
    if muted and mute_x + STATUS_ICON_SIZE > name_right:
        oled.overflows.append(
            f"{style[0]}: mute {mute_x}..{mute_x + STATUS_ICON_SIZE} overlaps battery group at {name_right}"
        )

    oled.text(0, 0, gps_label)
    if muted and mute_x + STATUS_ICON_SIZE <= name_right:
        draw_firmware_mute(oled, mute_x, 1)
        status_right = mute_x + STATUS_ICON_SIZE
    placement = clock_uptime_placement(oled, status_right, name_right, uptime_seconds)
    if placement is not None:
        uptime, uptime_left, uptime_right, gap = placement
        if uptime_left < status_right + gap:
            oled.overflows.append(
                f"{style[0]}: uptime starts at {uptime_left}, status ends at {status_right}, gap={gap}"
            )
        if uptime_right > name_right - gap:
            oled.overflows.append(
                f"{style[0]}: uptime ends at {uptime_right}, battery starts at {name_right}, gap={gap}"
            )
        oled.text(uptime_right, 0, uptime, right=True)
    else:
        # Hiding is valid only if both exact firmware candidates really do not fit.
        full = format_clock_uptime(uptime_seconds)
        if (name_right - 3 - oled.text_width(full) >= status_right + 3 or
                name_right - 2 - oled.text_width(full.replace(" ", "", 1)) >= status_right + 2):
            oled.overflows.append(f"{style[0]}: uptime hidden despite available room")
    actual_battery_left = draw_firmware_battery(oled)
    if actual_battery_left != voltage_x:
        oled.overflows.append(
            f"{style[0]}: battery metric drift {actual_battery_left}!={voltage_x}"
        )

    for index, x in enumerate((39, 49, 59, 69, 79, 89)):
        if index == 1:
            oled.draw.rectangle((x - 1, 13, x + 1, 15), fill=1)
        else:
            oled.draw.point((x, 14), fill=1)
    oled.text(W // 2, 18, "17:08", center=True, size=3)
    oled.text(0, 45, "CH1.2% A0.03%", max_width=96)
    oled.text(W - 1, 55, "29C", right=True)
    return oled.img, oled.overflows


def adc_scene(style: tuple[str, int, bool]) -> tuple[Image.Image, list[str]]:
    oled = Oled(style)
    oled.text(W // 2, 14, "Калибр. АКБ", center=True, max_width=W - 2)
    oled.text(W // 2, 28, "АКБ: 4.09В", center=True, max_width=W - 2)
    oled.text(W // 2, 40, "Коэф: 5.420", center=True, max_width=W - 2)
    oled.text(W // 2, 52, "+/-", center=True, max_width=W - 2)
    return oled.img, oled.overflows


def ble_pin_scene(style: tuple[str, int, bool]) -> tuple[Image.Image, list[str]]:
    """Exact shared 128x64 onboarding page used by V4.3 and ProMicro."""
    oled = Oled(style)
    voltage = "4.09V"
    voltage_width = oled.text_width(voltage)
    name_right = BATTERY_ICON_X - voltage_width - 5
    oled.ellipsized(0, 0, "Heltec V4.3", name_right)
    oled.text(BATTERY_ICON_X - 3, 0, voltage, right=True)
    oled.battery(W - 16, 1, 82)

    page_count, active = 7, 1
    step = 10
    x = (W - step * (page_count - 1)) // 2
    for index in range(page_count):
        if index == active:
            oled.draw.rectangle((x - 1, 13, x + 1, 15), fill=1)
        else:
            oled.draw.point((x, 14), fill=1)
        x += step

    oled.text(W // 2, 21, "ПИНКОД BLE", center=True)
    oled.text(W // 2, 38, "428731", center=True, size=2)
    oled.text(W // 2, 55, "код в приложении", center=True)
    return oled.img, oled.overflows


def render_scene(style: tuple[str, int, bool], name: str) -> tuple[Image.Image, list[str]]:
    if name == "GPS OFF + mute":
        return clock_scene(style, "GPS OFF", True)
    if name == "GPS ON + mute":
        return clock_scene(style, "GPS ON", True)
    if name == "GPS ON":
        return clock_scene(style, "GPS ON", False)
    if name == "BLE PIN":
        return ble_pin_scene(style)
    return adc_scene(style)


def validate_uptime_sweep() -> tuple[int, list[str]]:
    """Exercise every compact value against V4.3 and GPS-less ProMicro chrome."""
    checks = 0
    failures: list[str] = []
    for style in STYLES:
        for board, cases in (
            ("V4.3", (("GPS OFF", True), ("GPS ON", True), ("GPS ON", False))),
            ("ProMicro", (("", True), ("", False))),
        ):
            for gps_label, muted in cases:
                oled = Oled(style)
                battery_left = BATTERY_ICON_X - oled.text_width("4.09V") - 3
                right_used = battery_left - 2
                gps_right = oled.text_width(gps_label)
                status_right = gps_right
                if muted:
                    mute_x = gps_right + (3 if gps_label else 0)
                    if mute_x + STATUS_ICON_SIZE <= right_used:
                        status_right = mute_x + STATUS_ICON_SIZE
                for seconds in UPTIME_SAMPLES:
                    placement = clock_uptime_placement(oled, status_right, right_used, seconds)
                    checks += 1
                    if placement is None:
                        full = format_clock_uptime(seconds)
                        full_fits = right_used - 3 - oled.text_width(full) >= status_right + 3
                        compact = full.replace(" ", "", 1)
                        compact_fits = right_used - 2 - oled.text_width(compact) >= status_right + 2
                        if full_fits or compact_fits:
                            failures.append(
                                f"{board} / {style[0]} / {seconds}s: hidden though a candidate fits"
                            )
                        continue
                    text, left, right, gap = placement
                    if left < status_right + gap or right > right_used - gap:
                        failures.append(
                            f"{board} / {style[0]} / {seconds}s: {text} at {left}..{right} "
                            f"escapes {status_right}..{right_used} with gap {gap}"
                        )
    return checks, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "qa_outputs" / "v4_3_oled",
    )
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    label_w = 84
    label_h = 20
    gap = 6
    cell_w = W * SCALE
    cell_h = H * SCALE
    sheet = Image.new(
        "RGB",
        (label_w + len(SCENES) * (cell_w + gap) - gap,
         label_h + len(STYLES) * (cell_h + gap) - gap),
        "#15171a",
    )
    draw = ImageDraw.Draw(sheet)
    label_font = font(12)
    failures: list[str] = []

    for column, scene in enumerate(SCENES):
        draw.text((label_w + column * (cell_w + gap) + 4, 2), scene, font=label_font, fill="white")

    for row, style in enumerate(STYLES):
        y = label_h + row * (cell_h + gap)
        draw.text((4, y + 8), style[0], font=label_font, fill="white")
        for column, scene in enumerate(SCENES):
            image, errors = render_scene(style, scene)
            failures.extend(f"{style[0]} / {scene}: {error}" for error in errors)
            preview = image.resize((cell_w, cell_h), Image.Resampling.NEAREST).convert("RGB")
            x = label_w + column * (cell_w + gap)
            sheet.paste(preview, (x, y))

    matrix = args.out_dir / "V4_3_OLED_SMARTUI_2_1_EXACT_QA_MATRIX.png"
    sheet.save(matrix)
    canonical, canonical_errors = clock_scene(STYLES[0], "GPS OFF", True)
    failures.extend(f"canonical: {error}" for error in canonical_errors)
    canonical.resize((W * 4, H * 4), Image.Resampling.NEAREST).save(
        args.out_dir / "V4_3_OLED_CLOCK_GPS_MUTE.png"
    )
    uptime_canonical, uptime_errors = clock_scene(STYLES[0], "GPS ON", False)
    failures.extend(f"uptime canonical: {error}" for error in uptime_errors)
    uptime_canonical.resize((W * 4, H * 4), Image.Resampling.NEAREST).save(
        args.out_dir / "V4_3_OLED_CLOCK_UPTIME.png"
    )

    sweep_checks, sweep_failures = validate_uptime_sweep()
    failures.extend(sweep_failures)
    checks = len(STYLES) * len(SCENES) + sweep_checks
    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}")
    print(f"V4.3 OLED exact QA: {checks - len(failures)} passed, {len(failures)} failed")
    print(f"Saved {matrix}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
