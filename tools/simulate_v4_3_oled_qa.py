# -*- coding: utf-8 -*-
"""Exact 128x64 OLED checks for the Heltec V4.3 SmartUI profile.

This imports the firmware's Utf8Cyrillic5x7 tables through the existing OLED
simulator.  It specifically guards the GPS/mute/battery chrome that differs
from the GPS-less ProMicro profile.
"""

from __future__ import annotations

import argparse
import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw

from simulate_oled_128x64 import H, SCALE, STYLES, W, Oled, font


SCENES = ("GPS OFF + mute", "GPS ... + mute", "GPS FIX", "ADC calibration", "BLE PIN")
UPTIME_SAMPLES = (59, 12 * 60, 7 * 3600, 40 * 3600 + 5 * 60,
                  3 * 86400, 2000 * 86400, 999999 * 3600 + 59 * 60)
STATUS_ICON_SIZE = 8
BATTERY_ICON_X = W - 18 - 2


def format_clock_uptime(seconds: int) -> str:
    """Exact host equivalent of smartui::formatClockUptime()."""
    return f"U {seconds // 3600}h{seconds // 60 % 60:02d}m"


def clock_uptime_placement(
    oled: Oled, left_used: int, right_used: int, seconds: int
) -> tuple[str, int, int, int] | None:
    """Full-width row under the clock; neighbors no longer steal its space."""
    full = format_clock_uptime(seconds)
    for text, gap in ((full, 3), (full.replace(" ", "", 1), 2)):
        width = oled.text_width(text)
        left = (W - width) // 2
        right = left + width
        if left >= gap and right <= W - gap:
            return text, left, right, gap
    return None


def draw_firmware_battery(oled: Oled, milli_volts: int = 4090) -> int:
    """Generic HomeScreen battery geometry used by V4.3 and ProMicro."""
    icon_w, icon_h = 18, 8
    icon_x, icon_y = W - icon_w - 2, 0
    voltage = f"{milli_volts // 1000}.{(milli_volts % 1000) // 10:02d}V"
    voltage_x = icon_x - oled.text_width(voltage) - 3 if milli_volts else icon_x
    if milli_volts:
        oled.text(voltage_x, 0, voltage, tag="voltage", expected=voltage)
    oled.draw.rectangle((icon_x, icon_y, icon_x + icon_w - 1, icon_y + icon_h - 1), outline=1)
    oled.draw.rectangle((icon_x + icon_w, icon_y + 3, icon_x + icon_w + 1,
                         icon_y + icon_h - 4), fill=1)
    percent = max(0,min(100,int((milli_volts-3000)*100/1200))) if milli_volts else 0
    fill_w = ((icon_w - 4) * percent + 50) // 100
    if fill_w:
        oled.draw.rectangle((icon_x + 2, icon_y + 2, icon_x + 1 + fill_w,
                             icon_y + icon_h - 3), fill=1)
    pixels = {(x, y) for x in range(icon_x, W) for y in range(icon_y, icon_y+icon_h)
              if oled.img.getpixel((x, y))}
    oled.element("battery", (icon_x, icon_y, W, icon_y+icon_h), pixels)
    return voltage_x


@lru_cache(maxsize=16)
def firmware_mute_pixels(size: int) -> tuple[tuple[int, int], ...]:
    """Read the checked-in pack, never a visually similar replacement."""
    header = (Path(__file__).resolve().parents[1] /
              "examples/companion_radio/ui-new/iconpack_v1.h").read_text(encoding="utf-8")
    small = size < 12
    name = "iconpack_v2_small_mute" if small else "iconpack_v1_mute"
    match = re.search(rf"{name}\[\d+\] PROGMEM = \{{(.*?)\}};", header, re.S)
    assert match, name
    rows = [int(v, 16) for v in re.findall(r"0x[0-9a-fA-F]+", match.group(1))]
    grid = 8 if small else 12
    pixels = []
    for yy in range(size):
        sy = min(grid-1, ((yy*2+1)*grid)//(size*2))
        for xx in range(size):
            sx = min(grid-1, ((xx*2+1)*grid)//(size*2))
            if rows[sy] & (1 << (grid-1-sx)):
                pixels.append((xx, yy))
    return tuple(pixels)


def draw_firmware_mute(oled: Oled, x: int, y: int, size: int = STATUS_ICON_SIZE) -> None:
    for xx, yy in firmware_mute_pixels(size):
        oled.draw.point((x+xx, y+yy), fill=1)
    oled.element("mute", (x,y,x+size,y+size), {(x+xx,y+yy) for xx,yy in firmware_mute_pixels(size)})


def draw_firmware_gps(oled: Oled, x: int, y: int) -> None:
    from simulate_icon_alignment_beta2 import firmware_icon_rects
    pixels = set()
    for dx,dy,w,h in firmware_icon_rects("gps_status_icon",8):
        pixels.update((x+xx,y+yy) for xx in range(dx,dx+w) for yy in range(dy,dy+h))
    for point in pixels:
        oled.draw.point(point, fill=1)
    oled.element("satellite badge", (x,y,x+25,y+8), pixels)


def clock_scene(
    style: tuple[str, int, bool], gps_label: str, muted: bool,
    uptime_seconds: int = 40 * 3600 + 5 * 60,
    *, sats: int = -1, temperature: str = "29C", msg_hour: str = "5",
    millis: int = 0, time_valid: bool = True, milli_volts: int = 4090,
) -> tuple[Image.Image, list[str]]:
    oled = Oled(style)
    voltage = f"{milli_volts//1000}.{milli_volts%1000//10:02d}V"
    voltage_x = BATTERY_ICON_X - oled.text_width(voltage) - 3 if milli_volts else BATTERY_ICON_X
    name_right = voltage_x - 2
    gps_right = oled.text_width(gps_label)
    mute_x = gps_right + 3 if gps_label else 0
    status_right = gps_right

    if gps_right > name_right:
        oled.overflows.append(f"{style[0]}: {gps_label} reaches battery group at {gps_right}>{name_right}")
    if muted and mute_x + STATUS_ICON_SIZE > name_right:
        oled.overflows.append(
            f"{style[0]}: mute {mute_x}..{mute_x + STATUS_ICON_SIZE} overlaps battery group at {name_right}"
        )

    if gps_label:
        oled.text(0, 0, gps_label, tag="gps state", expected=gps_label)
    if muted and mute_x + STATUS_ICON_SIZE <= name_right:
        draw_firmware_mute(oled, mute_x, 0)
        status_right = mute_x + STATUS_ICON_SIZE
    placement = clock_uptime_placement(oled, status_right, name_right, uptime_seconds)
    if placement is not None:
        uptime, uptime_left, uptime_right, gap = placement
        if uptime_left < gap or uptime_right > W - gap:
            oled.overflows.append(f"{style[0]}: uptime row escapes screen")
        oled.text(uptime_right, 34, uptime, right=True, tag="uptime", expected=uptime)
    else:
        oled.overflows.append(f"{style[0]}: uptime unexpectedly hidden under clock")
    actual_battery_left = draw_firmware_battery(oled, milli_volts)
    if actual_battery_left != voltage_x:
        oled.overflows.append(
            f"{style[0]}: battery metric drift {actual_battery_left}!={voltage_x}"
        )

    for index, x in enumerate((39, 49, 59, 69, 79, 89)):
        if index == 1:
            oled.draw.rectangle((x - 1, 13, x + 1, 15), fill=1)
        else:
            oled.draw.point((x, 14), fill=1)
    time = "17:08" if time_valid else "--:--"
    oled.text(W // 2, 18, time, center=True, size=2, tag="time", expected=time)
    oled.text(0, 45, "CH1.2% A0.03%", max_width=W, tag="airtime", expected="CH1.2% A0.03%")
    detail_right = W-1
    if temperature:
        oled.text(detail_right, 55, temperature, right=True, tag="temperature", expected=temperature)
        detail_right -= oled.text_width(temperature)+4
    if sats >= 0:
        sat_text = str(min(sats,99))
        sat_icon_x = max(0, detail_right-oled.text_width(sat_text)-26)
        draw_firmware_gps(oled,sat_icon_x,55)
        oled.text(detail_right,55,sat_text,right=True,tag="satellites",expected=sat_text)
        detail_right = sat_icon_x-2
    if detail_right >= 8:
        options = (f"MSG/h {msg_hour}",f"M/h {msg_hour}",f"{msg_hour}/h")
        message = next((s for s in options if oled.text_width(s) <= detail_right+1), options[-1])
        oled.text(0,55,message,tag="messages",expected=message)
    required = ("battery","uptime","time","airtime","messages")
    if milli_volts: required += ("voltage",)
    if gps_label: required += ("gps state",)
    if muted: required += ("mute",)
    if sats >= 0: required += ("satellite badge","satellites")
    if temperature: required += ("temperature",)
    oled.validate_elements(required)
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
    draw_firmware_battery(oled)

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
    if name == "GPS ... + mute":
        return clock_scene(style, "GPS ...", True, sats=0)
    if name == "GPS FIX":
        return clock_scene(style, "GPS FIX", False, sats=12)
    if name == "BLE PIN":
        return ble_pin_scene(style)
    return adc_scene(style)


def validate_uptime_sweep() -> tuple[int, list[str]]:
    """Hours/minutes must remain visible in their own row on both OLED boards."""
    checks = 0
    failures: list[str] = []
    for style in STYLES:
        for board, cases in (
            ("V4.3", (("GPS OFF", True), ("GPS ...", True), ("GPS FIX", False))),
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
                        failures.append(f"{board} / {style[0]} / {seconds}s: uptime hidden")
                        continue
                    text, left, right, gap = placement
                    if left < gap or right > W - gap:
                        failures.append(
                            f"{board} / {style[0]} / {seconds}s: {text} at {left}..{right} "
                            f"escapes screen with gap {gap}"
                        )
    return checks, failures


def validate_clock_states() -> tuple[int, list[str]]:
    """Complete OLED frames: presence, ink and bbox are separate requirements."""
    checks, failures = 0, []
    for style in STYLES:
        for gps, satellites in (("",-1),("GPS OFF",-1),("GPS ...",0),
                                ("GPS FIX",1),("GPS FIX",12),("GPS FIX",99)):
            for muted in (False,True):
                for temperature, rate, valid, voltage in (
                    ("29C","5",True,4090),
                    ("-79C","99",False,0),
                    ("179C","9.9k",True,2700),
                    ("","999",False,4200),
                ):
                    _, errors = clock_scene(style,gps,muted,sats=satellites,
                                            temperature=temperature,msg_hour=rate,
                                            time_valid=valid,milli_volts=voltage)
                    checks += 1
                    failures.extend(f"{style[0]}/{gps}/{satellites}/{temperature}/{rate}: {e}" for e in errors)
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
    uptime_canonical, uptime_errors = clock_scene(STYLES[0], "GPS FIX", False, sats=12)
    failures.extend(f"uptime canonical: {error}" for error in uptime_errors)
    uptime_canonical.resize((W * 4, H * 4), Image.Resampling.NEAREST).save(
        args.out_dir / "V4_3_OLED_CLOCK_UPTIME.png"
    )

    sweep_checks, sweep_failures = validate_uptime_sweep()
    failures.extend(sweep_failures)
    state_checks, state_failures = validate_clock_states()
    failures.extend(state_failures)
    checks = len(STYLES) * len(SCENES) + sweep_checks + state_checks
    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}")
    print(f"V4.3 OLED exact QA: {checks - len(failures)} passed, {len(failures)} failed")
    print(f"Saved {matrix}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
