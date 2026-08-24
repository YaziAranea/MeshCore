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
STATUS_ICON_SIZE = 10
BATTERY_ICON_X = W - 18 - 2


def clock_scene(style: tuple[str, int, bool], gps_label: str, muted: bool) -> tuple[Image.Image, list[str]]:
    oled = Oled(style)
    voltage = "4.09V"
    voltage_width = oled.text_width(voltage)
    voltage_x = BATTERY_ICON_X - voltage_width - 3
    name_right = voltage_x - 2
    gps_right = oled.text_width(gps_label)
    mute_x = gps_right + 3

    if gps_right > name_right:
        oled.overflows.append(f"{style[0]}: {gps_label} reaches battery group at {gps_right}>{name_right}")
    if muted and mute_x + STATUS_ICON_SIZE > name_right:
        oled.overflows.append(
            f"{style[0]}: mute {mute_x}..{mute_x + STATUS_ICON_SIZE} overlaps battery group at {name_right}"
        )

    oled.text(0, 0, gps_label)
    if muted and mute_x + STATUS_ICON_SIZE <= name_right:
        oled.mute(mute_x, 0)
    oled.text(BATTERY_ICON_X - 3, 0, voltage, right=True)
    oled.battery(W - 16, 1, 82)

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

    checks = len(STYLES) * len(SCENES)
    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}")
    print(f"V4.3 OLED exact QA: {checks - len(failures)} passed, {len(failures)} failed")
    print(f"Saved {matrix}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
