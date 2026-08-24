# -*- coding: utf-8 -*-
"""Static contract for the five-board SmartUI 2.1 development profile."""

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
meshcore_h = read("src/MeshCore.h")
nodeprefs = read("examples/companion_radio/NodePrefs.h")
datastore = read("examples/companion_radio/DataStore.cpp")
simulator = read("tools/simulate_smartui_ps17_qa.py")
oled_simulator = read("tools/simulate_v4_3_oled_qa.py")
adc_boards = {
    "T096": read("variants/heltec_t096/T096Board.cpp"),
    "T114": read("variants/heltec_t114/T114Board.h"),
    "ProMicro": read("variants/promicro/PromicroBoard.h"),
    "V4.3 OLED": read("variants/heltec_v4/HeltecV4Board.h") + read("variants/heltec_v4/HeltecV4Board.cpp"),
    "Wireless Paper": read("variants/heltec_v3/HeltecV3Board.h"),
}
e213 = read("src/helpers/ui/E213Display.h") + read("src/helpers/ui/E213Display.cpp")
wireless_simulator = read("tools/simulate_wireless_paper_ps17_qa.py")

config_sources = {
    "T096": read("variants/heltec_t096/platformio.ini"),
    "T114": read("variants/heltec_t114/platformio.ini"),
    "ProMicro": read("variants/promicro/platformio.ini"),
    "V4.3 OLED": read("variants/heltec_v4/platformio.ini"),
    "Wireless Paper WOOD": read("variants/heltec_wireless_paper/platformio.ini"),
    "Wireless Paper FULL": read("variants/heltec_wireless_paper/platformio.ini"),
}

target_sections = {
    "T096": "env:Heltec_t096_companion_radio_ble_femon",
    "T114": "env:Heltec_t114_companion_radio_ble",
    "ProMicro": "env:ProMicro_ra62_companion_radio_ble",
    "V4.3 OLED": "env:heltec_v4_3_companion_radio_ble_femon_smartui",
    "Wireless Paper WOOD": "env:Heltec_Wireless_Paper_companion_radio_ble_smartui_wood",
    "Wireless Paper FULL": "env:Heltec_Wireless_Paper_companion_radio_ble_smartui_full",
}

effective = {
    name: effective_ini_section(config_sources[name], target_sections[name])
    for name in target_sections
}

for name, block in effective.items():
    check(
        f"{name}: BLE PIN onboarding page enabled",
        "UI_BLE_PIN_PAGE=1" in block,
        "every published display profile must expose its active random BLE passkey",
    )

check(
    "All published profiles hide the duplicate legacy FIRST page",
    all("UI_HIDE_FIRST_PAGE=1" in block for block in effective.values()),
    "the dedicated BLE PIN page must be the only pairing page in the home carousel",
)

check(
    "BLE PIN page is capability-aware and survives Wireless Paper idle mode",
    has_all(
        uitask,
        (
            "#if UI_BLE_PIN_PAGE",
            "static int renderBlePinPage",
            "return !_settings_open && !_task->hasConnection() && the_mesh.getBLEPin() != 0;",
            "return renderBlePinPage(display, the_mesh.getBLEPin(), false);",
            "_page = HomePage::BLE_PIN;",
            "isBlePinPage()",
            "connected && idle_saver != NULL && curr == idle_saver",
        ),
    ),
    "the PIN must auto-open, remain visible through the e-paper saver and disappear after pairing",
)

reset_home_block = between(uitask, "void resetToFirstPage()", "void readGpsUiState")
connection_block = between(uitask, "void UITask::updateConnectionState()", "void UITask::handlePendingPopupWake()")
wake_block = between(uitask, "void UITask::markDisplayWake", "void UITask::resetButtonStateAfterWake")
popup_wake_block = between(uitask, "void UITask::handlePendingPopupWake()", "void UITask::shutdown")
check(
    "Auto-home and off-screen pairing cannot strand or hide the BLE PIN page",
    has_all(
        reset_home_block,
        (
            "_page = defaultHomePage();",
            "!_task->hasConnection() && the_mesh.getBLEPin() != 0",
            "_page = HomePage::BLE_PIN;",
        ),
    )
    and has_all(
        connection_block,
        (
            "connected && home != NULL && ((HomeScreen*)home)->isBlePinPage()",
            "((HomeScreen*)home)->resetToFirstPage();",
        ),
    )
    and "curr == home && ((HomeScreen*)home)->isBlePinPage()" not in connection_block
    and has_all(
        wake_block,
        (
            "!hasConnection() && the_mesh.getBLEPin() != 0",
            "curr != msg_preview",
            "reset_to_clock = true;",
            "gotoHomeFirstScreen();",
        ),
    )
    and has_all(
        popup_wake_block,
        (
            "setCurrScreen(msg_preview);",
            "markDisplayWake(false);",
        ),
    ),
    "reset paths must retain the PIN while disconnected without replacing a pending message popup",
)

check(
    "Wireless Paper exact simulator covers the BLE PIN page",
    has_all(
        wireless_simulator,
        (
            "def render_ble_pin",
            'Canvas("ble_pin")',
            '"ПИНКОД BLE"',
            '"PIN / PASSKEY: ЭТИ 6 ЦИФР"',
        ),
    ),
    "the onboarding page must use the real embedded 5x7 Cyrillic glyph metrics",
)

check(
    "T096 and T114 exact simulators sweep the BLE PIN page",
    has_all(
        simulator,
        (
            "def render_ble_pin",
            'profiles["T096"]',
            "for profile in t114_active",
            '"no_pin_overlap"',
        ),
    ),
    "all T096 families and all ten T114 public fonts must keep the complete PIN page in bounds",
)

check(
    "V4.3 and ProMicro OLED styles sweep the BLE PIN page",
    has_all(
        oled_simulator,
        (
            '"BLE PIN"',
            "def ble_pin_scene",
            '"код в приложении"',
            "for row, style in enumerate(STYLES)",
        ),
    ),
    "all five 128x64 OLED spacing styles must keep the onboarding page in bounds",
)

keyboard_targets = ("T096", "T114", "ProMicro", "V4.3 OLED", "Wireless Paper FULL")

for name, block in effective.items():
    check(
        f"{name}: DM-only profile and development marker",
        "UI_UNREAD_DIRECT_ONLY=1" in block and "SmartUI 2.1.0-dev.1" in block,
        "every public profile must use DM-only unread and carry the 2.1 development marker",
    )
    check(
        f"{name}: experimental Phone GPS is disabled",
        "UI_PHONE_GPS=1" not in block,
        "SmartUI PS17 must not inherit UI_PHONE_GPS=1",
    )

for name in keyboard_targets:
    check(
        f"{name}: keyboard and targeted send enabled",
        "UI_QUICK_REPLY_KEYBOARD=1" in effective[name],
        "feature-parity builds must expose the keyboard and target picker",
    )

check(
    "Wireless Paper WOOD avoids per-keystroke e-paper refresh",
    "UI_QUICK_REPLY_KEYBOARD=1" not in effective["Wireless Paper WOOD"],
    "the recommended WOOD profile deliberately omits the e-paper keyboard",
)

check(
    "Publication scope is five boards with two explicit Wireless Paper profiles",
    tuple(target_sections) == (
        "T096", "T114", "ProMicro", "V4.3 OLED", "Wireless Paper WOOD", "Wireless Paper FULL"
    ),
    "keep the three nRF52 targets, V4.3 OLED and the two documented e-paper profiles",
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

for name in target_sections:
    check(
        f"{name}: obsolete profile and export/import pages stay hidden",
        "UI_SMART_B12_TONE_LIST=1" in effective[name],
        "B12 is also the established gate that removes SMART_PROFILE and SETTINGS_TRANSFER",
    )

for name in target_sections:
    check(
        f"{name}: real ADC calibration page enabled",
        "UI_ADC_MULTIPLIER_PAGE=1" in effective[name],
        "all five supported boards implement a mutable battery ADC multiplier",
    )

for name in target_sections:
    check(
        f"{name}: backward BLE time correction enabled",
        "BLE_TIME_SYNC_ACCEPT_BACKWARD=1" in effective[name],
        "a bad future RTC value must not block correction from the companion app",
    )

check(
    "V4.3 profile is OLED, FEM-on and never invents a buzzer",
    has_all(
        effective["V4.3 OLED"],
        (
            "UI_V4_3_OLED_PROFILE=1",
            "RADIO_FEM_RXGAIN=1",
            "UI_TONE_FALLBACK_TO_ALERT=0",
            "UI_SOUND_SETTINGS_GROUP=0",
        ),
    )
    and "PIN_MSG_TONE" not in effective["V4.3 OLED"],
    "the requested target is the 128x64 OLED V4.3 with LNA/FEM, not TFT and not a fake tone pin",
)

for name in ("Wireless Paper WOOD", "Wireless Paper FULL"):
    check(
        f"{name}: shared e-paper/LoRa rail is protected",
        has_all(
            effective[name],
            ("AUTO_OFF_MILLIS=0", "MESHCORE_E213_PROFILE_FONTS=1", "UI_SOUND_SETTINGS_GROUP=0"),
        ),
        "GPIO45/VEXT powers both display and radio; auto-off would kill LoRa",
    )

for name, source in adc_boards.items():
    check(
        f"{name}: ADC multiplier is a real board capability",
        has_all(source, ("setAdcMultiplier", "getAdcMultiplier"))
        and ("adc_mult" in source or name in ("T096", "ProMicro")),
        "do not expose a calibration page whose Board setter always returns false",
    )

check(
    "ADC preview is finite, transactional and cancellable",
    has_all(
        uitask,
        (
            "!isfinite(multiplier)",
            "void cancelAdcEdit()",
            "_task->setAdcMultiplier(_node_prefs->adc_multiplier, false);",
            "if (save) {\n    _node_prefs->adc_multiplier = multiplier;",
        ),
    )
    and uitask.count("cancelAdcEdit();") >= 3,
    "preview must not leak into persisted prefs or survive leaving the settings page",
)

check(
    "Legacy buzzer GPIO repair is compiled and applied",
    has_all(
        mymesh + nodeprefs,
        (
            "#ifndef DEFAULT_NOTIFY_REPAIR_LEGACY",
            "#if DEFAULT_NOTIFY_REPAIR_LEGACY",
            'def("pin_fix", _parent->notify_pin_fix_version);',
            "inline bool migrateLegacyNotifyPins",
            "prefs.notify_tone_pin == alert_pin",
            "prefs.notify_pin_fix_version = target_version;",
            "if (notify_prefs_changed) _store->savePrefs(_prefs);",
        ),
    ),
    "repair the saved legacy tone pin once, then preserve an explicit shared alert/tone choice",
)

check(
    "Notification pages and favorite fallbacks follow board capabilities",
    all("UI_NOTIFICATION_SETTINGS=0" in effective[name] for name in ("Wireless Paper WOOD", "Wireless Paper FULL"))
    and has_all(
        uitask,
        (
            "#ifndef UI_NOTIFICATION_SETTINGS",
            "uint8_t resolvedFavoritePageAt(uint8_t slot) const",
            "return defaultFavoritePageAt(slot);",
            "if (page == HomePage::ALERTS || page == HomePage::IMPORTANT_NOTIFY) return false;",
            'snprintf(out, out_len, "ЭКРАН");',
        ),
    ),
    "boards without any alert/tone output must not expose dead pages or fall back to ALERTS",
)

check(
    "Compact-settings landing page reports the real group count",
    has_all(
        uitask,
        (
            'snprintf(tmp, sizeof(tmp), "%u компактных разделов",',
            "(unsigned)COMPACT_SETTINGS_GROUP_COUNT",
        ),
    )
    and '"7 компактных разделов"' not in uitask,
    "profiles without the sound group must not claim seven sections",
)

check(
    "SmartUI settings survive a stock PS17 JSON migration",
    has_all(
        datastore,
        (
            "LEGACY_SMART_UI_PREFS_OFFSET = 140",
            'prefsHasRootKey(file, "smart_ui")',
            "readLegacySmartUiTail",
            "prefs_ok && !has_smart_ui",
            "savePrefs(prefs);",
        ),
    ),
    "merge only the retained SmartUI tail once; never overwrite current JSON on every boot",
)

check(
    "BLE time sync validates range and can repair a future RTC",
    has_all(
        mymesh + meshcore_h,
        (
            "BLE_TIME_SYNC_MIN_UNIX 1704067200UL",
            "BLE_TIME_SYNC_MAX_UNIX 2208988800UL",
            "bool backward = secs < curr;",
            "bool sane_time = secs >= BLE_TIME_SYNC_MIN_UNIX",
            "!backward || BLE_TIME_SYNC_ACCEPT_BACKWARD",
            "rtc->setCurrentTimeAndRebaseUnique(secs);",
            "last_unique = applied > 0 ? applied - 1 : 0;",
        ),
    ),
    "phone time must be sane, while enabled targets may move the RTC backward",
)

check(
    "Wireless Paper driver uses exact Cyrillic profiles and clipped e-paper drawing",
    has_all(
        e213,
        (
            '"Стандарт"',
            '"Четкий"',
            '"Компакт"',
            '"Моно"',
            '"Плотный"',
            "meshcoreReadUtf8Codepoint",
            "fillRectClipped",
            "display_crc.update<ColorVal>(bkg)",
            "E213_FULL_REFRESH_EVERY",
        ),
    ),
    "the 250x122 target must not fall back to the stock Latin renderer or draw outside the panel",
)

check(
    "No SmartUI PS17 target config retains Phone GPS",
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
    "Exact SmartUI PS17 simulator covers every display contract and stress case",
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
            "T114_SMARTUI_PS17_GPS_APPEARANCE_PHYSICAL_QA.png",
        ),
    ),
    "do not replace exact bitmap/driver QA with a generic TrueType 5x7 mock-up",
)

passed = sum(result.ok for result in results)
failed = len(results) - passed
print(f"Smart UI 2.1 five-board contract audit: {passed} passed, {failed} failed")
for result in results:
    print(f"[{'PASS' if result.ok else 'FAIL'}] {result.label}")
    if not result.ok:
        print(f"       {result.detail}")

raise SystemExit(1 if failed else 0)
