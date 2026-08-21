# -*- coding: utf-8 -*-
"""Static release contract for the three-board SmartUI v2.0.0-rc1 port."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def has_all(text: str, values: tuple[str, ...]) -> bool:
    return all(value in text for value in values)


def without_if_zero(text: str) -> str:
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"(?ms)^\s*#if\s+0\s*$.*?^\s*#endif\s*$", "", text)
    return text


def parse_ini_sections(text: str) -> dict[str, str]:
    matches = list(re.finditer(r"(?m)^\[([^]]+)\]\s*$", text))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[match.group(1)] = text[match.end():end]
    return sections


def effective_ini_section(text: str, section: str) -> str:
    sections = parse_ini_sections(text)
    seen: set[str] = set()

    def collect(name: str) -> str:
        if name in seen:
            return ""
        seen.add(name)
        block = sections.get(name, "")
        parent_match = re.search(r"(?m)^extends\s*=\s*([^\r\n]+)", block)
        inherited = ""
        if parent_match:
            for parent in re.split(r"\s*,\s*|\s+", parent_match.group(1).strip()):
                if not parent:
                    continue
                candidate = parent if parent in sections else f"env:{parent}"
                inherited += collect(candidate)
        return inherited + "\n" + block

    return collect(section)


def between(text: str, start: str, end: str) -> str:
    left = text.find(start)
    right = text.find(end, left + len(start)) if left >= 0 else -1
    return text[left:right] if left >= 0 and right >= 0 else ""


@dataclass
class Result:
    label: str
    ok: bool
    detail: str


results: list[Result] = []


def check(label: str, condition: bool, detail: str) -> None:
    results.append(Result(label, bool(condition), detail))


uitask = read("examples/companion_radio/ui-new/UITask.cpp")
uitask_live = without_if_zero(uitask)
mymesh = read("examples/companion_radio/MyMesh.cpp")
mymesh_h = read("examples/companion_radio/MyMesh.h")
simulator = read("tools/simulate_exp45_ui_qa.py")

config_sources = {
    "T096": read("variants/heltec_t096/platformio.ini"),
    "T114": read("variants/heltec_t114/platformio.ini"),
    "ProMicro": read("variants/promicro/platformio.ini"),
}

target_sections = {
    "T096": "env:Heltec_t096_companion_radio_ble_femon",
    "T114": "env:Heltec_t114_companion_radio_ble",
    "ProMicro": "env:ProMicro_ra62_companion_radio_ble",
}

effective = {
    name: effective_ini_section(config_sources[name], target_sections[name])
    for name in target_sections
}

for name, block in effective.items():
    check(
        f"{name}: EXP45 keyboard and DM-only profile",
        "UI_QUICK_REPLY_KEYBOARD=1" in block
        and "UI_UNREAD_DIRECT_ONLY=1" in block
        and "SmartUI 2.0.0-rc1" in block,
        "the effective target profile must enable keyboard, DM-only unread and carry the RC marker",
    )
    check(
        f"{name}: experimental Phone GPS is disabled",
        "UI_PHONE_GPS=1" not in block,
        "EXP45 must not inherit UI_PHONE_GPS=1",
    )

check(
    "Publication scope contains exactly the three supported targets",
    tuple(target_sections) == ("T096", "T114", "ProMicro"),
    "do not silently advertise or gate the release on an untested fourth board",
)

check(
    "ProMicro enables the same extended Smart UI settings",
    "UI_SMART_B11_EXTRAS=1" in effective["ProMicro"],
    "ProMicro must expose the same favourites/status UI as T096 and T114",
)

check(
    "ProMicro explicitly removes inherited GPS hardware support",
    "-UENV_INCLUDE_GPS" in effective["ProMicro"],
    "the RA62 target has no onboard GPS and must not inherit the generic ProMicro GPS flag",
)

gpsless_clock_guard = between(
    uitask,
    "// A GPS-less board must not advertise a permanently disabled",
    "} else\n#endif",
)
device_status = between(uitask, "else if (_page == HomePage::DEVICE_STATUS)", "else if (_page == HomePage::HARDWARE_TEST)")
check(
    "GPS-less clock and device status hide nonexistent GPS chrome",
    has_all(
        gpsless_clock_guard + device_status,
        (
            "#if ENV_INCLUDE_GPS == 1 || UI_PHONE_GPS == 1",
            "drawUiIcon(display, name_x, 1, muted_icon, icon_size);",
            "#elif defined(RADIO_FEM_RXGAIN)",
            'snprintf(tmp, sizeof(tmp), "Радио SX1262");',
        ),
    ),
    "a board without GPS must not show a permanent GPS OFF/НЕТ label",
)

for name in ("T096", "T114", "ProMicro"):
    check(
        f"{name}: one common melody list",
        "UI_SMART_B12_TONE_LIST=1" in effective[name],
        "the tone-capable target must use the common B12 melody selector",
    )

check(
    "No EXP45 target config retains Phone GPS",
    all("UI_PHONE_GPS=1" not in text for text in config_sources.values()),
    "remove the old positive Phone GPS build flag instead of hiding the menu only",
)

check(
    "Disabled Phone GPS is hardened at runtime and BLE boundary",
    has_all(
        mymesh + mymesh_h,
        (
            "#if UI_PHONE_GPS != 1",
            "source = GPS_SOURCE_HW;",
            "_prefs.gps_source = GPS_SOURCE_HW;",
            "writeErrFrame(ERR_CODE_UNSUPPORTED_CMD);",
            "return false;",
            "if (dp != (char *)&out_frame[1]) *dp++ = ',';",
        ),
    )
    and "#if UI_PHONE_GPS == 1\n    if (dp != (char *)&out_frame[1])" in mymesh,
    "old PHONE prefs, command 44 and custom vars must not reactivate the rejected feature",
)

check(
    "Keyboard keeps the UTF-8 tail and a visible caret",
    has_all(
        uitask,
        (
            "drawRichTextTailEllipsized",
            "while (*visible && richTextWidth(display, visible) > suffix_width)",
            "if ((lead & 0xE0) == 0xC0) advance = 2;",
            "display.fillRect(cursor_x + 1, y + 1, 1, caret_h);",
            "drawRichTextTailEllipsized(display, 3, preview_text_y, w - 6, _quick_keyboard_text, true);",
        ),
    ),
    "tail clipping must advance by a complete UTF-8 codepoint and render the caret",
)

static_ellipsis = between(
    uitask,
    "static void drawRichTextStaticEllipsized",
    "static int drawRichTextTailEllipsized",
)
check(
    "Dense lists use a stable UTF-8 static ellipsis",
    has_all(
        static_ellipsis,
        (
            "nextWrappedRichLine",
            'const char* ellipsis = "...";',
            "memcpy(&line[len], ellipsis, 4);",
        ),
    )
    and uitask.count("drawRichTextStaticEllipsized") >= 10,
    "pickers must not marquee several rows independently while the user scans a list",
)

check(
    "Keyboard action keys use compact pictograms and readable page labels",
    has_all(
        uitask,
        (
            'QR_KB_PAGE_KEY("ТЯ", 1)',
            'QR_KB_PAGE_KEY("АС", 0)',
            "drawQuickKeyboardKey",
            "key.action == QR_KB_SPACE",
            "key.action == QR_KB_DELETE",
            "key.action == QR_KB_BACK",
        ),
    )
    and not any(f'showAlert("{word}"' in uitask_live for word in ("Full", "Empty", "Back", "Err")),
    "RU1/RU2/DEL/BK and live English editor errors must not return",
)

compact_helper = between(
    uitask,
    "static uint8_t uiPushCompactSettingsFont",
    "static void uiPopFont",
)
check(
    "T114 dense screens force the stable profile-0 bitmap font",
    has_all(
        compact_helper,
        (
            "#elif UI_NATIVE_TFT_PROFILE",
            "display.setUiFont(0);",
            "display.setTextSize(1);",
        ),
    )
    and uitask.count("#if UI_T096_PREMIUM_TFT || UI_NATIVE_TFT_PROFILE") >= 4,
    "keyboard and target picker must not inherit an XXL T114 body font",
)

target_renderer = between(uitask, "void renderQuickTargetPicker", "void renderQuickKeyboard")
check(
    "Target picker derives rows from real line height",
    has_all(
        target_renderer,
        (
            "const int line_h = display.getTextLineHeight();",
            "const int row_h = line_h;",
            "const int row_h = (h - list_y) / 4;",
            "int visible = (h - list_y) / row_h;",
        ),
    ),
    "T096 and T114 need separate, metric-aware dense-list geometry",
)
check(
    "Target picker reserves and draws a proportional 2px scrollbar",
    has_all(
        target_renderer,
        (
            "int text_right_guard = total > (uint16_t)visible ? 7 : 3;",
            "int thumb_h = (track_h * visible) / total;",
            "if (thumb_h < 4) thumb_h = 4;",
            "display.drawRect(track_x, track_y, 2, track_h);",
            "display.fillRect(track_x, thumb_y, 2, thumb_h);",
        ),
    ),
    "a 350-contact list needs measured text guard and a visible scroll position",
)

compact_renderer = between(uitask, "void renderCompactSettings", "void renderTonePicker")
check(
    "Compact settings use metric rows and full-row selection",
    has_all(
        compact_renderer,
        (
            "int line_h = display.getTextLineHeight();",
            "int row_y = 14 + line_h + 1;",
            "int row_h = line_h > 12 ? line_h : 12;",
            "uint8_t visible_rows = (display.height() - row_y) / row_h;",
            "display.fillRect(0, y, display.width() - (item_count > visible_rows ? 3 : 0), row_h);",
            "display.setColor(DisplayDriver::DARK);",
        ),
    ),
    "fixed 13px T096 rows clip real L glyphs and a single '>' is too weak a selection state",
)

appearance_picker = between(uitask, "void renderAppearancePicker", "void renderTonePicker")
check(
    "Font and theme choices are real scrollable list pickers",
    has_all(
        appearance_picker,
        (
            "getUiFontCount() : _task->getUiThemeCount()",
            "choice_count + 1",
            "getUiFontChoiceName(index)",
            "getUiThemeChoiceName(index)",
            "drawRichTextStaticEllipsized",
            "display.drawTextRightAlign(display.width() - right_guard, y, \"OK\");",
            "display.fillRect(display.width() - 2, thumb_y, 2, thumb_h);",
            '"Назад"',
        ),
    ),
    "font/theme settings must open measured lists with active marker, Back and scrollbar",
)

gps_page = between(
    uitask,
    "} else if (_page == HomePage::GPS)",
    "#if UI_SENSORS_PAGE == 1",
)
check(
    "T114 GPS page fits the physical 240x135 framebuffer",
    has_all(
        gps_page,
        (
            "uint8_t gps_saved_font = uiPushCompactSettingsFont(display);",
            "int row_step = display.getTextLineHeight();",
            "if (row_step < 8) row_step = 8;",
            "y += row_step;",
            "uiPopFont(display, gps_saved_font);",
        ),
    )
    and "y += 12;" not in gps_page,
    "fixed y=18/30/42/54 clips the longitude row in every public T114 font profile",
)

unread_class = between(uitask, "class MsgPreviewScreen", "void UITask::begin")
check(
    "Unread preview is an aggregated direct-sender list",
    has_all(
        unread_class,
        (
            "char sender[62];",
            "senderWasShownFromNewer",
            "senderMessageCount",
            "uniqueDirectSenderCount",
            "renderUnreadSenders",
            '"ЛС: %d чел / %d"',
            "drawFittedUnreadText",
        ),
    )
    and "Notify: DM" not in unread_class
    and "snprintf(p->origin" not in unread_class
    and '"(CH2)' not in unread_class
    and '"(П)' not in unread_class
    and "(void)path_len;" in unread_class,
    "the screen must show clean companion names, per-sender counts and the latest snippet, not hop prefixes/history",
)

unread_render = between(unread_class, "int render(DisplayDriver& display) override", "bool handleInput")
check(
    "Unread sender list uses the compact font contract",
    "uiPushCompactSettingsFont(display)" in unread_render,
    "T114 unread must not inherit XXL; use the same compact font guard as other dense lists",
)

check(
    "Unread auto-scroll cannot paint over its header",
    unread_class.count("y >= y_start && y < display.height()") >= 2,
    "both sender and snippet rows must be clipped at content_y/y_start, not merely at -line_h",
)

check(
    "DM-only read/dequeue synchronization uses a no-double-delete debt",
    has_all(
        uitask,
        (
            "if (direct_preview) {",
            "preview->addPreview(path_len, from_name, text, important_flags);",
            "uint16_t direct_sync_debt = 0;",
            "if (locally_dismissed) addDirectSyncDebt(1);",
            "if (locally_dismissed && num_unread > 0) addDirectSyncDebt((uint16_t)num_unread);",
            "if (num_unread >= MAX_UNREAD_MSGS)",
            "if (!preview->consumeDirectSyncDebt()) preview->removeOldestPreview(false);",
            "_msgcount = preview->unreadPreviewCount();",
            "should_show_preview = should_show_preview && direct_preview;",
        ),
    ),
    "local dismiss, clear and ring eviction must be acknowledged once by BLE without deleting the next visible DM",
)

night_handler = between(uitask, "void UITask::nightModeHandler", "void UITask::beginImportantNotify")
new_msg = between(uitask, "void UITask::newMsg", "void UITask::userLedHandler")
check(
    "Important messages preempt the modal night-mode prompt",
    has_all(
        night_handler + new_msg,
        (
            "_ble_smart_notify_flags != UI_MSG_FLAG_NONE || _popup_pending",
            "if (_msg_tone_active) return;",
            "if (_night_prompt_active && important_flags != UI_MSG_FLAG_NONE)",
            "closeNightPrompt(false, true);",
        ),
    ),
    "a pending or newly arrived DM must not remain hidden under a modal prompt that steals button input",
)

check(
    "Targeted send keeps 16-bit indexes and filters repeaters",
    has_all(
        uitask + mymesh + mymesh_h,
        (
            "uint16_t quickTargetItemCount() const",
            "uint16_t quickTargetTotalCount() const",
            "bool MyMesh::getQuickReplyContact(uint16_t list_idx",
            "candidate.type != ADV_TYPE_CHAT",
            "recipient == NULL || recipient->type != ADV_TYPE_CHAT",
            "sendQuickReplyToContact(_quick_target_cursor, _quick_keyboard_text)",
        ),
    ),
    "350-contact stress requires uint16_t navigation and companion-only contact filtering",
)

check(
    "Exact EXP45 simulator covers every display contract and stress case",
    has_all(
        simulator,
        (
            "threshold 104",
            "threshold 92",
            "T114_SCALE_X = 1.875",
            "T114_SCALE_Y = 2.109375",
            "T114_Y_OFFSET = 1",
            "glyph_for",
            "(0, (0,))",
            "(350, (0, 349, 350))",
            "LONG_TYPED",
            "run_release_assertions",
            "make_t114_active_profiles",
            "render_t114_gps",
            "render_appearance_picker",
            "T114_EXP45_GPS_APPEARANCE_PHYSICAL_QA.png",
        ),
    ),
    "do not replace exact bitmap/driver QA with a generic TrueType 5x7 mock-up",
)

passed = sum(result.ok for result in results)
failed = len(results) - passed
print(f"Smart UI v2.0.0-rc1 contract audit: {passed} passed, {failed} failed")
for result in results:
    print(f"[{'PASS' if result.ok else 'FAIL'}] {result.label}")
    if not result.ok:
        print(f"       {result.detail}")

raise SystemExit(1 if failed else 0)
