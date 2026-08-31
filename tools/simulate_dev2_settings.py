"""Bounded dev.2 settings layout QA; not hardware screenshots/full UITask execution.

Models renderNotifyPicker/renderCompactSettings geometry, with source-contract
checks. TFT glyphs/advances come from the checked-in EmbeddedBitmapFonts.h,
OLED/E213 pixels from Utf8Cyrillic5x7.h. T114 uses the real 240x135/Y+1 mapping.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from simulate_smartui_ps17_qa import (
    BoardProfile, ExactFont, Frame, OledExactFont, T096ExactFont, T114ExactFont,
    assert_tags_do_not_overlap, label_font, make_matrix, union_boxes,
)
from simulate_oled_128x64 import STYLES
from simulate_wireless_paper_ps17_qa import PROFILES, glyph
from embedded_bitmap_fonts import EmbeddedRaw


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "qa_outputs/dev2-settings"
UI = (ROOT / "examples/companion_radio/ui-new/UITask.cpp").read_text(encoding="utf-8")


class PaperFont(ExactFont):
    def __init__(self, name: str):
        self.name = name
        self.advance, gap, self.weight, self.fixed = PROFILES[name]
        self.logical_height = 8 + gap

    def advance_for(self, char: str, bold: bool) -> int:
        return (4 if char == " " and not self.fixed else self.advance) + int(bold or self.weight)

    def width(self, text: str, bold: bool = False) -> int:
        return sum(self.advance_for(ch, bold) for ch in text)

    def points(self, x: int, y: int, text: str, bold: bool):
        weight = int(bold or self.weight)
        for ch in text:
            if ch != " ":
                for col, bits in enumerate(glyph(ch)):
                    for row in range(8):
                        if bits & (1 << row):
                            yield x + col, y + row
                            if weight:
                                yield x + col + 1, y + row
            x += self.advance_for(ch, bold)

    def draw(self, image, x, y, text, color, bold=False):
        draw = ImageDraw.Draw(image)
        for point in self.points(x, y, text, bold):
            draw.point(point, fill=color)

    def ink_box(self, x, y, text, bold=False):
        return union_boxes((px, py, px + 1, py + 1) for px, py in self.points(x, y, text, bold))


class SettingsFrame(Frame):
    def __post_init__(self):
        super().__post_init__()
        # The generic QA Frame adds a decorative border; it is not part of
        # renderNotifyPicker, so keep this isolated preview free of it.
        self.draw.rectangle((0, 0, self.image.width, self.image.height), fill=self.color("bg"))

    def color(self, name):
        if self.board.board == "Wireless Paper":
            return (255, 255, 255) if name in ("bg", "dark") else (0, 0, 0)
        return super().color(name)


def profiles():
    result = []
    for index, family in enumerate(("Roboto", "Noto", "OpenSans", "PT Narrow", "Oswald")):
        font = T096ExactFont(family, EmbeddedRaw("meshcore_font", "meshcoreSmallFonts", index))
        result.append(BoardProfile("T096", family, 160, 80, 160, 80, font, font))
    font = T114ExactFont("Roboto L forced", EmbeddedRaw("meshcore_st7789_font", "meshcoreSt7789Fonts", 0))
    result.append(BoardProfile("T114", "Forced compact Roboto L", 128, 64, 240, 135,
                               font, font, 1.875, 2.109375, 1))
    for index, style in enumerate(STYLES):
        font = OledExactFont(index, style)
        result.append(BoardProfile("OLED", style[0], 128, 64, 128, 64, font, font, oled=True))
    for name in PROFILES:
        font = PaperFont(name)
        result.append(BoardProfile("Wireless Paper", name, 250, 122, 250, 122, font, font))
    return result


def source_contract():
    block = UI.split("void renderNotifyPicker(DisplayDriver& display) const {", 1)[1].split(
        "void applyNotifyPickerChoice", 1)[0]
    for token in (
        "int row_y = 14 + line_h + 1;", "row_y < 28) row_y = 28;",
        "int row_h = line_h > 12 ? line_h : 12;", "display.width() - 38",
        'display.width() - 2, 14, "<>OK"', '"Отмена"',
        '"%d/10"', '"%d Гц"', '"D%d"',
        "int right_guard = has_scrollbar ? 5 : 3;",
        'display.getTextWidth("OK") + 4', "visible_rows * row_h - 2",
    ):
        assert token in block, f"renderNotifyPicker changed; update geometry model: {token}"
    assert "display.setUiFont(0);" in UI.split("static uint8_t uiPushCompactSettingsFont", 1)[1].split("static void uiPopFont", 1)[0]
    assert "int value_width = display.width() > 140 ? 66 : 50;" in UI
    return hashlib.sha256(block.encode()).hexdigest()


def geometry(profile, count, cursor):
    line_h = max(8, profile.desired_font.logical_height)
    row_y = 14 + line_h + 1
    if profile.logical_h <= 64:
        row_y = max(28, row_y)
    row_h = max(12, line_h)
    maximum = 8 if profile.board == "Wireless Paper" else 4
    visible = max(1, min(maximum, (profile.logical_h - row_y) // row_h))
    start = max(0, cursor - visible + 1)
    if count > visible and start + visible > count:
        start = count - visible
    return row_y, row_h, visible, start


def heading(frame, title):
    w = frame.board.logical_w
    frame.text(2, 14, title, "green", max_w=w - 38, tag="title")
    # This firmware call is not ellipsized; measure it before drawing.
    assert frame.font.width("<>OK") <= 36, "header hint exceeds reserved space"
    frame.text(w - 2, 14, "<>OK", right=True, max_w=36, tag="hint")
    assert_tags_do_not_overlap(frame, "title", "hint")


def scrollbar(frame, y, row_h, visible, count, start):
    w = frame.board.logical_w
    track_h = visible * row_h - 2
    thumb_h = max(4, track_h * visible // count)
    thumb_y = y + (track_h - thumb_h) * start // (count - visible)
    frame.rect(w - 2, y, 2, track_h, "light", outline=True, tag="scrollbar")
    frame.rect(w - 2, thumb_y, 2, thumb_h, "yellow", tag="thumb")


def picker(profile, title, labels, cursor, active):
    frame = SettingsFrame(profile, title, True)
    w = profile.logical_w
    row_y, row_h, visible, start = geometry(profile, len(labels) + 1, cursor)
    scrolling = len(labels) + 1 > visible
    heading(frame, title)
    for row, index in enumerate(range(start, min(start + visible, len(labels) + 1))):
        y, selected = row_y + row * row_h, index == cursor
        if selected:
            frame.rect(0, y, w - (3 if scrolling else 0), row_h, "yellow")
        color = "dark" if selected else "light"
        guard = 5 if scrolling else 3
        is_active = index == active and index < len(labels)
        marker = frame.font.width("OK", selected) + 4 if is_active else 0
        label = labels[index] if index < len(labels) else "Отмена"
        tag = f"row{row}"
        shown = frame.text(3, y, label, color, max_w=w - 3 - guard - marker,
                           bold=selected, tag=tag)
        assert shown == label, f"{profile.board}/{profile.profile}: option unexpectedly truncated: {label} -> {shown}"
        frame.assert_element_inside(tag, (3, y, w - 3 - guard - marker, row_h))
        if is_active:
            frame.text(w - guard, y, "OK", color, max_w=marker, right=True, bold=selected, tag=f"ok{row}")
            frame.assert_element_inside(f"ok{row}", (w - guard - marker, y, marker, row_h))
            assert_tags_do_not_overlap(frame, tag, f"ok{row}")
    if scrolling:
        scrollbar(frame, row_y, row_h, visible, len(labels) + 1, start)
    frame.facts.update(cursor=cursor, active=active, visible_rows=visible)
    return frame


def battery(profile, enabled):
    frame = SettingsFrame(profile, "Защита АКБ", True)
    heading(frame, "Система")
    w = profile.logical_w
    row_y, row_h, visible, _ = geometry(profile, 10, 3)
    value_width = 66 if w > 140 else 50
    values = ("ВКЛ 3.2", "ВЫК 2.7")
    entries = [("Bluetooth", "ВКЛ"), ("Защита АКБ", values[0 if enabled else 1]), ("Назад", "")]
    for row, (label, value) in enumerate(entries[:visible]):
        y, selected = row_y + row * row_h, row == 1
        if selected:
            frame.rect(0, y, w - 3, row_h, "yellow")
        color = "dark" if selected else "light"
        frame.text(3, y, label, color, max_w=w - value_width - 5 if value else w - 5,
                   bold=selected, tag=f"label{row}")
        if value:
            shown = frame.text(w - value_width, y, value, color, max_w=value_width - 1,
                               bold=selected, tag=f"value{row}")
            assert shown == value, f"battery value clipped: {profile.board}/{profile.profile}: {shown}"
            frame.assert_element_inside(f"value{row}", (w - value_width, y, value_width - 2, row_h))
            assert_tags_do_not_overlap(frame, f"label{row}", f"value{row}")
    scrollbar(frame, row_y, row_h, visible, 10, 2)
    return frame


def docs_sheet(scenes, output):
    """Integer-pixel enlargement; only board-applicable scenes belong here."""
    scale = 3 if scenes[0][1].image.width <= 160 else 2
    screen_w, screen_h = scenes[0][1].image.size
    tile_w, tile_h, gap, label_h = screen_w * scale, screen_h * scale, 14, 32
    rows = (len(scenes) + 1) // 2
    image = Image.new("RGB", (tile_w * 2 + gap, (tile_h + label_h) * rows + gap * (rows - 1)), (13, 17, 22))
    draw = ImageDraw.Draw(image)
    for index, (label, frame) in enumerate(scenes):
        x = (index % 2) * (tile_w + gap)
        y = (index // 2) * (tile_h + label_h + gap)
        draw.text((x + 3, y + 5), label, font=label_font(13), fill=(225, 235, 240))
        image.paste(frame.image.resize((tile_w, tile_h), Image.Resampling.NEAREST), (x, y + label_h))
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def docs_previews(configurations):
    out = ROOT / "docs/assets/ui"
    t096 = next(p for p in configurations if p.board == "T096")
    pm = next(p for p in configurations if p.board == "OLED")
    t114 = next(p for p in configurations if p.board == "T114")
    paper = next(p for p in configurations if p.board == "Wireless Paper")
    t096_pins = [f"D{x}" for x in (29, 31, 33, 34, 35, 36, 37, 39, 43, 45)]
    pm_pins = [f"D{x}" for x in (0, 1, 9, 18, 19, 20, 22)]
    resonance = [f"{hz} Гц" for hz in range(1800, 4201, 400)]
    docs_sheet([
        ("T096: GPIO, мост ВЫКЛ", picker(t096, "Выход звука", t096_pins, 1, 1)),
        ("T096: отмена выбора GPIO", picker(t096, "Выход звука", t096_pins, len(t096_pins), 1)),
        ("T096: выбор резонанса", picker(t096, "Резонанс", resonance, 1, 0)),
        ("T096: отмена резонанса", picker(t096, "Резонанс", resonance, len(resonance), 0)),
    ], out / "dev2-t096-confirmed-settings.png")
    docs_sheet([
        ("ProMicro RA62: выбор GPIO", picker(pm, "Выход звука", pm_pins, 2, 2)),
        ("ProMicro RA62: отмена GPIO", picker(pm, "Выход звука", pm_pins, len(pm_pins), 2)),
        ("ProMicro RA62: защита ВКЛ", battery(pm, True)),
        ("ProMicro RA62: защита ВЫКЛ", battery(pm, False)),
    ], out / "dev2-promicro-confirmed-settings.png")
    docs_sheet([
        ("T114: выбор резонанса", picker(t114, "Резонанс", resonance, 1, 0)),
        ("T114: отмена резонанса", picker(t114, "Резонанс", resonance, len(resonance), 0)),
        ("T114: защита ВКЛ", battery(t114, True)),
        ("T114: защита ВЫКЛ", battery(t114, False)),
    ], out / "dev2-t114-confirmed-settings.png")
    docs_sheet([
        ("Wireless Paper: защита ВКЛ", battery(paper, True)),
        ("Wireless Paper: защита ВЫКЛ", battery(paper, False)),
    ], out / "dev2-wireless-paper-battery.png")


def main():
    fingerprint = source_contract()
    OUT.mkdir(parents=True, exist_ok=True)
    configurations = profiles()
    lists = {
        "Выход звука": [f"D{x}" for x in (29, 31, 33, 34, 35, 36, 37, 39, 43, 45)],
        "Выход света": [f"D{x}" for x in range(32)],
        "Вибрация": [f"D{x}" for x in (-1, 35, 40, 41, 47, 48)],
        "Резонанс": [f"{x} Гц" for x in range(1800, 4201, 400)],
        "Громкость": [f"{x}/10" for x in range(1, 11)],
    }
    checks, failures = 0, []
    for profile in configurations:
        for title, labels in lists.items():
            # All cursor positions; active marker both inside/outside selection.
            for cursor in range(len(labels) + 1):
                for active in {0, min(cursor, len(labels) - 1)}:
                    frame = picker(profile, title, labels, cursor, active)
                    checks += 1
                    failures.extend(f"{profile.board}/{profile.profile}/{title}: {x}" for x in frame.violations)
        for enabled in (True, False):
            frame = battery(profile, enabled)
            checks += 1
            failures.extend(f"{profile.board}/{profile.profile}/battery: {x}" for x in frame.violations)
    for board in ("T096", "T114", "OLED", "Wireless Paper"):
        profile = next(p for p in configurations if p.board == board)
        scenes = []
        for title in ("Выход звука", "Резонанс", "Громкость"):
            labels = lists[title]
            scenes.append((title + " — выбор", picker(profile, title, labels, 1, 0)))
            scenes.append((title + " — отмена", picker(profile, title, labels, len(labels), 0)))
        scenes.extend((label, battery(profile, enabled)) for label, enabled in (("Защита ВКЛ", True), ("Защита ВЫКЛ", False)))
        make_matrix(scenes, OUT / f"{board.replace(' ', '_')}.png", columns=2)
    report = {
        "kind": "source-bound geometry model; real glyph tables; not full firmware/hardware execution",
        "renderNotifyPicker_sha256": fingerprint, "profiles": len(configurations),
        "checks": checks, "failures": failures,
        "coverage": "all list cursors including Cancel, active marker, 32-item GPIO stress, resonance, volume, both battery values",
        "t114": "forced bitmap font0: real 24px line; logical128x64 -> physical240x135; Y_OFFSET=1",
        "pins": "layout samples/stress only, not a whitelist or wiring recommendation",
        "top_chrome": "isolated settings body only; status/battery header from enclosing UITask omitted",
        "selection_alignment": "glyph row zero equals selection top; no negative baseline on SSD1306/E213, intentionally no added top padding",
    }
    (OUT / "REPORT.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"checks": checks, "profiles": len(configurations), "failures": len(failures)}, ensure_ascii=False))
    if failures:
        print("\n".join(failures[:20]))
        raise SystemExit(1)
    docs_previews(configurations)


if __name__ == "__main__":
    main()
