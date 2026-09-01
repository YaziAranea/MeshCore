# -*- coding: utf-8 -*-
"""Static contract for the five-board SmartUI 2.1 beta profile.

The assertions below intentionally describe behaviour and recovery boundaries,
not one historical spelling of an implementation.  Native tests exercise the
small policy helpers; this audit connects those helpers to the actual firmware
entry points and to every published display profile.
"""

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
uitask_h = read("examples/companion_radio/ui-new/UITask.h")
uitask_live = without_if_zero(uitask)
mymesh = read("examples/companion_radio/MyMesh.cpp")
mymesh_h = read("examples/companion_radio/MyMesh.h")
meshcore_h = read("src/MeshCore.h")
nodeprefs = read("examples/companion_radio/NodePrefs.h")
datastore = read("examples/companion_radio/DataStore.cpp")
battery_policy = read("examples/companion_radio/ui-new/BatteryShutdownPolicy.h")
clock_uptime = read("examples/companion_radio/ui-new/ClockUptime.h")
ui_timing = read("examples/companion_radio/ui-new/UiTiming.h")
adc_ui_policy = read("examples/companion_radio/ui-new/AdcCalibrationUi.h")
adc_calibration = read("src/helpers/AdcCalibration.h")
config_serializer = read("src/helpers/ConfigSerializer.cpp") + read("src/helpers/ConfigSerializer.h")
identity_store = read("src/helpers/IdentityStore.cpp") + read("src/helpers/IdentityStore.h")
storage_transaction = read("src/helpers/StorageTransaction.h")
main_source = read("examples/companion_radio/main.cpp")
rtc_sources = (
    meshcore_h
    + read("src/helpers/RTCClockQuality.h")
    + read("src/helpers/ArduinoHelpers.h")
    + read("src/helpers/ESP32Board.h")
    + read("src/helpers/AutoDiscoverRTCClock.h")
    + read("src/helpers/AutoDiscoverRTCClock.cpp")
    + read("src/helpers/BaseChatMesh.cpp")
)
frame_validation = read("examples/companion_radio/CompanionFrameValidation.h")
channel_busy_policy = read("examples/companion_radio/ChannelBusyPolicy.h")
native_policy_tests = (
    read("test/test_ui_runtime_policy/test_ui_runtime_policy.cpp")
    + read("test/test_battery_shutdown_policy/test_battery_shutdown_policy.cpp")
    + read("test/test_storage_transaction/test_storage_transaction.cpp")
    + read("test/test_config_serializer/test_config_serializer.cpp")
    + read("test/test_companion_frame_validation/test_companion_frame_validation.cpp")
    + read("test/test_contact_time_bootstrap/test_contact_time_bootstrap.cpp")
)
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
        f"{name}: manual stable BLE PIN page enabled",
        "UI_BLE_PIN_PAGE=1" in block and "BLE_PIN_PERSIST_RANDOM=1" in block,
        "every published display profile must expose a passkey that survives ordinary reboots",
    )

check(
    "All published profiles hide the duplicate legacy FIRST page",
    all("UI_HIDE_FIRST_PAGE=1" in block for block in effective.values()),
    "the dedicated BLE PIN page must be the only pairing page in the home carousel",
)

home_constructor_block = between(uitask, "HomeScreen(UITask*", "void resetToFirstPage()")
check(
    "BLE PIN page is manual and never replaces boot or Wireless Paper idle clock",
    has_all(
        uitask,
        (
            "#if UI_BLE_PIN_PAGE",
            "static int renderBlePinPage",
            "return !_settings_open && !_task->hasConnection() && the_mesh.getBLEPin() != 0;",
            "isBlePinPage()",
        ),
    )
    and "return renderBlePinPage(display, the_mesh.getBLEPin(), false);" not in uitask
    and "_page = HomePage::BLE_PIN;" not in home_constructor_block
    and has_all(
        mymesh,
        (
            "BLE_PIN_PERSIST_RANDOM",
            "_prefs.ble_pin = _active_ble_pin;",
            "if (!_store->savePrefs(_prefs))",
            "_prefs.ble_pin = 0;",
            "_active_ble_pin = BLE_PIN_CODE;",
        ),
    ),
    "the PIN must be opened by the user, never hijack idle UI, and remain stable until erase/reset",
)

reset_home_block = between(uitask, "void resetToFirstPage()", "void readGpsUiState")
connection_block = between(uitask, "void UITask::updateConnectionState()", "void UITask::handlePendingPopupWake()")
wake_block = between(uitask, "void UITask::markDisplayWake", "void UITask::resetButtonStateAfterWake")
popup_wake_block = between(uitask, "void UITask::handlePendingPopupWake()", "void UITask::shutdown")
check(
    "Messages, telemetry, auto-home and wake return to normal UI instead of BLE PIN",
    has_all(
        reset_home_block,
        ("_page = defaultHomePage();",),
    )
    and "getBLEPin" not in reset_home_block
    and "HomePage::BLE_PIN" not in reset_home_block
    and has_all(
        connection_block,
        (
            "connected && home != NULL && ((HomeScreen*)home)->isBlePinPage()",
            "((HomeScreen*)home)->resetToFirstPage();",
        ),
    )
    and "curr == home && ((HomeScreen*)home)->isBlePinPage()" not in connection_block
    and "connected && idle_saver != NULL && curr == idle_saver" not in connection_block
    and has_all(
        wake_block,
        ("gotoHomeFirstScreen();",),
    )
    and "getBLEPin" not in wake_block
    and "curr != msg_preview" not in wake_block
    and has_all(
        popup_wake_block,
        (
            "setCurrScreen(msg_preview);",
            "markDisplayWake(false);",
        ),
    ),
    "PIN onboarding must never take priority over the clock, saver, telemetry or message popup",
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
        "UI_UNREAD_DIRECT_ONLY=1" in block and "SmartUI 2.1.0-beta.1" in block,
        "every public profile must use DM-only unread and carry the 2.1 beta marker",
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

adc_cancel = between(uitask, "void cancelAdcEdit()", "#endif")
adc_setter = between(uitask, "bool UITask::setAdcMultiplier", "void UITask::toggleBuzzer")
adc_factory_reset = between(uitask, "bool restoreAdcDefault", "bool isBlePinPage")
check(
    "ADC calibration is bounded, transactional, cancellable and explicitly resettable",
    has_all(
        adc_calibration,
        (
            "board_default * 0.75f",
            "board_default * 1.25f",
            "!isfinite(requested)",
            "requested == 0.0f",
            "saturatingBatteryMilliVolts",
        ),
    )
    and all("normalizeAdcMultiplier" in source and "saturatingBatteryMilliVolts" in source
            for source in adc_boards.values())
    and has_all(
        adc_cancel,
        (
            "_task->setAdcMultiplier(_node_prefs->adc_multiplier, false)",
            "_task->setAdcMultiplier(0.0f, false)",
            "_adc_edit = false;",
        ),
    )
    and has_all(
        adc_setter,
        (
            "!isfinite(multiplier)",
            "if (!_board->setAdcMultiplier(multiplier))",
            "if (save)",
            "_node_prefs->adc_multiplier = multiplier;",
        ),
    )
    and has_all(
        adc_ui_policy + adc_factory_reset + native_policy_tests,
        (
            "adcFactoryResetGesture",
            "click_count == 2",
            "_task->setAdcMultiplier(0.0f, true)",
            "FactoryResetHasDistinctNonDestructiveGesture",
            "AcceptsResetAndSaneBoardSpecificWindow",
            "ConversionIsRoundedAndSaturating",
        ),
    ),
    "preview/cancel must not persist, accepted calibration stays within +/-25%, and only the dedicated 2x gesture stores the board-default sentinel",
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
            "bool startup_prefs_repaired = adc_prefs_repaired;",
            "startup_prefs_repaired = startup_prefs_repaired || notify_prefs_changed;",
            "if (startup_prefs_repaired && !_store->savePrefs(_prefs))",
        ),
    ),
    "repair the saved legacy tone pin once and commit it together with any independent ADC repair",
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

prefs_root_scan = between(datastore, "static bool prefsHasRootKey", "static bool readLegacySmartUiTail")
prefs_loader = between(datastore, "void DataStore::loadPrefs", "bool DataStore::loadPrefsInt")
check(
    "SmartUI migration recognises only an exact root key and commits the legacy tail once",
    has_all(
        prefs_root_scan,
        (
            "bool in_string = false;",
            "if (depth != 1)",
            "strcmp(key, wanted) == 0",
        ),
    )
    and has_all(
        prefs_loader,
        (
            'const char* candidates[] = {target, scratch, backup};',
            "NodePrefs candidate(prefs);",
            'has_smart_ui = prefsHasRootKey(file, "smart_ui");',
            "prefs_ok = candidate.loadSerial(file);",
            "prefs = candidate;",
            "if (!has_smart_ui && _fs->exists(\"/new_prefs\"))",
            "NodePrefs migrated(prefs);",
            "readLegacySmartUiTail(legacy, migrated)",
            "prefs = migrated;",
            "savePrefs(prefs);",
        ),
    )
    and "LEGACY_SMART_UI_PREFS_OFFSET = 140" in datastore,
    "nested/string occurrences must not suppress migration; malformed candidates must not partially mutate live prefs, and saving smart_ui is the durable one-time marker",
)

check(
    "ConfigSerializer accepts exactly one complete root object for recovery",
    has_all(
        config_serializer,
        (
            "bool root_started = false;",
            "bool root_closed = false;",
            "if (sp != 0 || root_closed)",
            "root_closed = true;",
            "if (root_closed && context.success)",
            "if (!is_whitespace((char)value))",
            "!root_started || !root_closed || sp != 0 || next_tok == TOK_ERROR",
            "return context.success;",
        ),
    )
    and has_all(
        native_policy_tests,
        (
            "LoadSerial_RejectsEmptyOrWhitespaceOnlyInput",
            "LoadSerial_RejectsTrailingPartialData",
            "LoadSerial_UnmatchedBraces",
            "SaveSerial_ReportsMidStreamWriteFailure",
        ),
    ),
    "empty, truncated, multiple/trailing or failed-write generations must be rejected so .tmp/.bak recovery is not suppressed",
)

prefs_saver = between(datastore, "bool DataStore::savePrefs", "void DataStore::loadContacts")
contacts_storage = between(datastore, "void DataStore::loadContacts", "void DataStore::loadChannels")
channels_storage = between(datastore, "void DataStore::loadChannels", "#if defined(NRF52_PLATFORM) || defined(STM32_PLATFORM)")
check(
    "Preferences, contacts and channels publish verified tmp generations with bak recovery",
    has_all(
        prefs_saver,
        (
            'scratch = "/prefs.json.tmp"',
            'backup = "/prefs.json.bak"',
            "_prefs.saveSerial(file)",
            "verification.loadSerial(verify_file)",
            "commitScratch(_fs, target, scratch, backup,",
            "prefsFileValid(_fs, target, _prefs)",
        ),
    )
    and has_all(
        contacts_storage,
        (
            '"/contacts3.tmp"',
            '"/contacts3.bak"',
            "chooseContactCandidate",
            "commitScratch(",
            'fs, "/contacts3", "/contacts3.tmp", "/contacts3.bak",',
            'contactRecordFileValid(fs, "/contacts3")',
            "digestFile",
        ),
    )
    and has_all(
        channels_storage,
        (
            '"/channels2.tmp"',
            '"/channels2.bak"',
            "chooseChannelCandidate",
            "commitScratch(",
            'fs, "/channels2", "/channels2.tmp", "/channels2.bak",',
            'channelRecordFileValid(fs, "/channels2")',
            "digestFile",
        ),
    )
    and has_all(
        storage_transaction + native_policy_tests,
        (
            "chooseRecoveryCandidate",
            "RecoveryCandidate::TEMPORARY",
            "RecoveryCandidate::BACKUP",
            "RecoversValidatedTemporaryAfterRotationInterruption",
            "FallsBackToBackupWhenNewGenerationIsIncomplete",
            "Crc32MatchesStandardVectorAndStreamingUpdates",
        ),
    ),
    "a power loss at any publish step must leave a complete primary, verified temporary or backup generation",
)

migration_storage = between(datastore, "static bool copyFileTransactional", "}  // namespace") + between(
    datastore, "void DataStore::migrateToSecondaryFS", "bool DataStore::putBlobByKey"
)
check(
    "Secondary-filesystem migration verifies size and CRC before deleting either source",
    has_all(
        migration_storage,
        (
            "copyFileTransactional",
            "filesMatch(source_fs, source, dest_fs, scratch)",
            "filesMatch(source_fs, source, dest_fs, dest)",
            "safe_to_remove_source",
            "if (safe_to_remove_source)",
            "_fs->remove(path)",
            "_fsExtra->remove(path)",
        ),
    )
    and has_all(storage_transaction, ("class Crc32", "0xEDB88320u")),
    "cross-filesystem copy must be byte-for-byte verified and preserve both copies on ambiguity or interruption",
)

check(
    "Identity corruption and filesystem mount failure stop before radio/BLE startup",
    has_all(
        identity_store,
        (
            "IdentityLoadStatus",
            "identityIsCoherent",
            "chooseIdentityCandidate",
            "CORRUPT_OR_IO",
            "NOT_FOUND",
            "commitIdentityScratch",
            'makeSiblingPath(filename, ".tmp"',
            'makeSiblingPath(filename, ".bak"',
        ),
    )
    and has_all(
        mymesh,
        (
            "loadMainIdentityStatus",
            "IdentityLoadStatus::CORRUPT_OR_IO",
            "IdentityLoadStatus::NOT_FOUND",
            "saveMainIdentity(self_id)",
        ),
    )
    and has_all(
        main_source,
        (
            "storage_ready = InternalFS.begin();",
            "storage_ready = LittleFS.begin();",
            "storage_ready = SPIFFS.begin(false);",
            "if (!storage_ready)",
            'showFatalStorageError(disp, "STORAGE ERROR"',
            "if (!mesh_started)",
            'showFatalStorageError(disp, "IDENTITY ERROR"',
            "halt();",
            "bluetooth_interface.begin",
        ),
    )
    and main_source.index("if (!mesh_started)") < main_source.index("bluetooth_interface.begin"),
    "mount failure must never auto-format, and a corrupt existing identity must never be silently replaced or advertised",
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
    "RTC source quality is explicit: estimates remain untrusted and never become retained truth",
    has_all(
        rtc_sources,
        (
            "virtual bool isTimeTrusted()",
            "virtual void setEstimatedTime(uint32_t time)",
            "meshRtcTimestampPlausible",
            "CLOCK_MAGIC_NUM        0xAA55CC34",
            "RTC_BACKUP_MAGIC  0xAA55CC34",
            "time_trusted = false;",
            "_time_trusted = false;",
            "_hardware_time_trusted = false;",
            "rtc->setEstimatedTime(estimate);",
        ),
    )
    and "base_time = 1772323200" not in rtc_sources
    and "tv.tv_sec = 1772323200" not in rtc_sources
    and has_all(
        uitask + native_policy_tests,
        (
            "rtc_clock.isTimeTrusted()",
            "meshRtcTimestampPlausible(rtc_clock.getCurrentTime())",
            "if (!hasTrustedTime() || rtc_now < UI_RTC_VALID_MIN) return;",
            "PlausibilityDoesNotAcceptBootSeedsOrAbsurdDates",
            "SelectsOnlyTheNewestPlausibleContactTimestamp",
            "ProducesAOneSecondEstimateWithoutOverflow",
        ),
    ),
    "contact timestamps may improve packet ordering, but only BLE/GPS or plausible hardware/retained RTC may enable clocks and scheduled night mode",
)

timezone_picker_input = between(
    uitask,
    "if (_page == HomePage::TIMEZONE_PICKER)",
    "#endif\n#if UI_APPEARANCE_MENU",
)
check(
    "Timezone is persisted in minutes and saved only by explicit picker confirmation",
    has_all(
        nodeprefs + mymesh,
        (
            "int16_t timezone_offset_minutes = 360;",
            'def("tz_min", _parent->timezone_offset_minutes);',
            "timezone_offset_minutes = other.timezone_offset_minutes;",
            "normalizeTimezoneOffsetMinutes",
            "value < -720 || value > 840 || value % 30 != 0",
        ),
    )
    and has_all(
        uitask,
        (
            "static const int16_t TIMEZONE_MINUTES_MIN = -720;",
            "static const int16_t TIMEZONE_MINUTES_MAX = 840;",
            "static const int16_t TIMEZONE_MINUTES_STEP = 30;",
            "(TIMEZONE_MINUTES_MAX - TIMEZONE_MINUTES_MIN) / TIMEZONE_MINUTES_STEP + 1;",
            "return (int16_t)(TIMEZONE_MINUTES_MIN + index * TIMEZONE_MINUTES_STEP);",
            'snprintf(out, out_len, "UTC%c%02d:%02d"',
            "bool changed = selected != _task->getTimezoneOffsetMinutes();",
            "if (changed) _task->setTimezoneOffsetMinutes(selected, true);",
            "return uiApplyTimezoneOffset(utc_time, getTimezoneOffsetSeconds());",
        ),
    )
    and has_all(
        timezone_picker_input,
        (
            "if (c == KEY_LEFT || c == KEY_PREV)",
            "if (c == KEY_NEXT || c == KEY_RIGHT)",
            "if (c != KEY_ENTER) return false;",
            "if (_timezone_picker_cursor < TIMEZONE_CHOICE_COUNT)",
            "_page = HomePage::SETTINGS;",
        ),
    )
    and "the_mesh.savePrefs" not in between(
        timezone_picker_input, "if (c == KEY_LEFT", "if (c != KEY_ENTER)"
    ),
    "the civil range is UTC-12:00..UTC+14:00 in 30-minute steps; scrolling or Cancel must not write flash",
)

clock_uptime_renderer = between(
    uitask, "static bool drawClockUptimeBetween", "#if UI_BLE_PIN_PAGE"
)
paper_idle_clock = between(
    uitask, "static int renderPaperIdleClock", "class PaperIdleClockScreen"
)
check(
    "Uptime exists only as collision-aware secondary text on every clock layout",
    has_all(
        clock_uptime,
        (
            "formatClockUptime",
            '"U %lum"',
            '"U %luh"',
            '"U %lud"',
            '"U 999+d"',
            "clockUptimeRightEdge",
            "if (left < (int32_t)left_used + gap) return -1;",
        ),
    )
    and has_all(
        clock_uptime_renderer,
        (
            "display.getTextWidth(text)",
            "clockUptimeRightEdge",
            "if (right < 0) return false;",
            "display.drawTextRightAlign(right, y, text);",
        ),
    )
    and uitask.count("drawClockUptimeBetween(display, _task") >= 6
    and has_all(
        paper_idle_clock,
        (
            "formatClockUptime",
            "display.getTextWidth(uptime_text)",
            "int node_width = uptime_left - 8;",
            "display.drawTextRightAlign(uptime_right, 4, uptime_text);",
        ),
    )
    and has_all(
        uitask_h + uitask + native_policy_tests,
        (
            "uint64_t _uptime_accumulated_ms;",
            "_uptime_accumulated_ms += (uint32_t)(now - _uptime_last_millis);",
            "updateUptime((uint32_t)millis());",
            "UsesCompactLowChurnUnits",
            "PlacementUsesMeasuredWidthAndNeverOverlapsNeighbours",
        ),
    )
    and "HomePage::UPTIME" not in uitask
    and '"Аптайм"' not in uitask,
    "T096/T114/ProMicro/V4 and both Wireless Paper clock paths must reserve real-font space; uptime must not consume a carousel/menu page",
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

phone_command = between(mymesh, "} else if (cmd_frame[0] == CMD_SET_PHONE_GPS)",
                        "} else if (cmd_frame[0] == CMD_GET_DEVICE_TIME)")
phone_source = between(mymesh, "void MyMesh::setGpsSource", "bool MyMesh::setPhoneGpsFix")
phone_fix = between(mymesh, "bool MyMesh::setPhoneGpsFix", "bool MyMesh::getShareableLocation")
phone_enabled = between(mymesh_h, "bool isPhoneGpsEnabled() const", "bool isPhoneGpsFresh() const")
custom_vars = between(mymesh, "} else if (cmd_frame[0] == CMD_GET_CUSTOM_VARS)",
                      "} else if (cmd_frame[0] == CMD_SET_CUSTOM_VAR")
phone_vars = between(custom_vars, "#if UI_PHONE_GPS == 1", "#endif")
check(
    "Disabled Phone GPS is hardened at runtime and BLE boundary",
    has_all(phone_command, ("#if UI_PHONE_GPS == 1", "#else\n    writeErrFrame(ERR_CODE_UNSUPPORTED_CMD);"))
    and "#else\n  source = GPS_SOURCE_HW;" in phone_source
    and "#if UI_PHONE_GPS != 1" in phone_fix and "return false;\n#else" in phone_fix
    and "#else\n    return false;" in phone_enabled
    and "_prefs.gps_source = GPS_SOURCE_HW;" in mymesh
    and has_all(phone_vars, ('vars.append("gps_source",', 'vars.append("phone_gps",'))
    and custom_vars.count('vars.append("gps_source",') == 1
    and custom_vars.count('vars.append("phone_gps",') == 1
    and has_all(custom_vars, (
        "smartui::CustomVarsWriter vars((char *)&out_frame[1], sizeof(out_frame) - 1);",
        "if (!vars.append(sensors.getSettingName(i), sensors.getSettingValue(i))) break;",
        "_serial->writeFrame(out_frame, 1 + vars.size());",
    ))
    and "strcpy(" not in custom_vars,
    "old PHONE prefs and command 44 stay disabled; both Phone GPS fields remain gated inside the bounded writer",
)

companion_handler = between(mymesh, "void MyMesh::handleCmdFrame", "void MyMesh::checkCLIRescueCmd")
serial_reader = between(mymesh, "void MyMesh::checkSerialInterface", "void MyMesh::loop")
check(
    "Companion frames are shape-checked before any command field is read",
    has_all(
        frame_validation,
        (
            "class FrameReader",
            "minimumCommandFrameLength",
            "validateCommandFrame",
            "kFrameTooShort",
            "kFrameInvalidPath",
            "kFrameInvalidShape",
            "encodedPathByteLength",
            "length > capacity",
        ),
    )
    and has_all(
        companion_handler,
        (
            "companion::validateCommandFrame(",
            "if (frame_status != companion::kFrameValid)",
            "writeErrFrame(ERR_CODE_ILLEGAL_ARG);",
            "return;",
        ),
    )
    and companion_handler.index("validateCommandFrame") < companion_handler.index("cmd_frame[0]")
    and has_all(serial_reader, ("memset(cmd_frame, 0, sizeof(cmd_frame));",
                                "_serial->checkRecvFrame(cmd_frame)"))
    and has_all(
        native_policy_tests,
        (
            "NeverAdvancesPastTheProvidedFrame",
            "EveryCommandAndInRangeLengthHasABoundedResult",
            "DestructiveAndScopeCommandsRequireCompleteShapes",
            "OversizeFramesAreRejectedBeforeParsing",
        ),
    ),
    "short/truncated/path-invalid commands must fail at the transport boundary and a new frame must never inherit stale bytes from the previous command",
)

check(
    "Channel-busy accounting is sampled, wrap-safe and rebased after sleep gaps",
    has_all(
        channel_busy_policy + mymesh,
        (
            "channelBusySampleDue",
            "static_cast<uint32_t>(now - previous)",
            "elapsed > interval_ms * 2U",
            "static const uint32_t SAMPLE_INTERVAL_MS = 100;",
            "channelBusyElapsedToAccount",
            "_radio->isReceiving()",
        ),
    )
    and has_all(
        native_policy_tests,
        (
            "PollsOnlyAtTheConfiguredWrapSafeInterval",
            "AccountsShortSamplesButNotSleepSizedGaps",
        ),
    ),
    "SPI radio-state polling must not run in the hot loop, and an instantaneous RX state after sleep must not be charged to the whole sleep interval",
)

mention_handler = between(mymesh, "bool MyMesh::textMentionsNodeName", "#ifndef UI_FONT_PREF_MAX")
check(
    "Mention disambiguation computes one network snapshot outside the loop-task stack",
    has_all(
        mymesh_h + mention_handler,
        (
            "NetworkStatusEntry mention_status_scratch[NETWORK_STATUS_TABLE_SIZE];",
            "int recent_count = -1;",
            "if (recent_count < 0)",
            "getRecentNetworkStatus(mention_status_scratch",
            "const NetworkStatusEntry& entry = mention_status_scratch[i];",
        ),
    )
    and "NetworkStatusEntry recent[NETWORK_STATUS_TABLE_SIZE]" not in mention_handler,
    "a channel mention must not allocate about 1 KB per callback or recompute the same network table for every ambiguous token",
)

notify_handler = between(uitask, "bool handleCompactSettingsInput(char c)", "bool isSettingsItem")
notify_picker_input = between(notify_handler, "if (_page == HomePage::NOTIFY_PICKER)",
                              "#if UI_APPEARANCE_MENU")
notify_navigation = between(notify_picker_input, "if (c == KEY_LEFT", "if (c != KEY_ENTER) return false;")
check(
    "Notification picker navigation and cancellation cannot save or apply hardware",
    has_all(notify_navigation, ("_notify_picker.move(-1);", "_notify_picker.move(1);"))
    and not any(token in notify_navigation for token in
                ("savePrefs", "applyNotifyPickerChoice", "configureMsg", "_node_prefs->"))
    and has_all(notify_picker_input, (
        "if (c != KEY_ENTER) return false;",
        "if (_notify_picker.selected(value)) {",
        "applyNotifyPickerChoice(value);",
        "_notify_picker.reset();",
        "_page = HomePage::SETTINGS;",
    ))
    and notify_picker_input.count("applyNotifyPickerChoice(value);") == 1
    and "savePrefs" not in notify_picker_input,
    "browsing changes only the draft; Enter applies a real option once and Cancel only returns to settings",
)

notify_setter_specs = (
    ("setNotifyLedPin(int pin)", "setNotifyTonePin", "getMsgAlertPin() == pin"),
    ("setNotifyTonePin(int pin)", "setNotifyVibePin", "getMsgTonePin() == pin"),
    ("setNotifyVibePin(int pin)", "cycleNotifySound", "getMsgVibePin() == pin"),
    ("setNotifyToneVolume(uint8_t volume)", "toggleNotifyTone8Bit", "getNotifyToneVolume() == volume"),
    ("setNotifyToneResonanceHz(uint16_t frequency)", "toggleNotifyToneBridge", "getNotifyToneResonanceHz() == frequency"),
)
notify_setter_blocks = [
    (between(uitask, f"void UITask::{start}", f"void UITask::{end}"), unchanged)
    for start, end, unchanged in notify_setter_specs
]
check(
    "Confirmed notification setters skip unchanged values and save only once",
    all(block.count("the_mesh.savePrefs();") == 1
        and unchanged in block
        and block.index(unchanged) < block.index("the_mesh.savePrefs();")
        and "return;" in block[:block.index("the_mesh.savePrefs();")]
        for block, unchanged in notify_setter_blocks)
    and "if (changed) the_mesh.savePrefs();" in between(
        uitask, "void UITask::setCommonNotifyTone", "uint8_t UITask::getNotifyToneVolume"),
    "confirmation must not rewrite unchanged settings or duplicate the one durable preference write",
)

battery_getter = between(uitask, "uint16_t UITask::getLowBatteryShutdownThreshold() const",
                         "void UITask::toggleLowBatteryShutdown")
battery_toggle = between(uitask, "void UITask::toggleLowBatteryShutdown()", "uint8_t UITask::getUiFontCount")
check(
    "Battery shutdown uses an independent raw safety path with explicit validity",
    has_all(battery_getter, (
        "#if defined(AUTO_SHUTDOWN_MILLIVOLTS)",
        "smartui::batteryShutdownThreshold(isLowBatteryShutdownEnabled(),",
        "AUTO_SHUTDOWN_MILLIVOLTS, LOW_BATTERY_SHUTDOWN_FLOOR_MILLIVOLTS)",
        "#else\n  return 0;",
    ))
    and "_low_batt_strikes = 0;" in battery_toggle
    and has_all(uitask, (
        "const uint16_t shutdownThreshold = getLowBatteryShutdownThreshold();",
        "const smartui::BatteryReading reading = readSafetyBattery();",
        "_low_batt_strikes = smartui::nextLowBatteryStrikeCount(_low_batt_strikes,",
        "reading, shutdownThreshold, LOW_BATTERY_SHUTDOWN_CONFIRM_COUNT);",
        "smartui::deadlineDueOrImmediate",
        "LOW_BATTERY_SHUTDOWN_CONFIRM_COUNT",
    ))
    and has_all(
        battery_policy,
        (
            "struct BatteryReading",
            "millivolts != 0",
            "if (!reading.valid) return strikes",
            "if (reading.millivolts >= threshold) return 0;",
            "medianBatteryReading",
        ),
    )
    and has_all(
        between(uitask, "smartui::BatteryReading UITask::readSafetyBattery", "bool UITask::hasTrustedTime"),
        (
            "_board->getBattMilliVolts()",
            "medianBatteryReading(a, b, c)",
        ),
    )
    and uitask.count("_board->getBattMilliVolts();") >= 4
    and has_all(
        native_policy_tests,
        (
            "SevereUndervoltageNeverFailsOpen",
            "AbsentReadingDoesNotCountOrEraseEvidence",
            "SafetyMedianIgnoresAbsentSamples",
            "DeadlineComparisonSurvivesMillisWrap",
        ),
    ),
    "0 alone means unavailable; every nonzero undervoltage must count, display EMA must not feed shutdown, and the 3.2/2.7 V policy must survive millis rollover",
)

check(
    "Every beta profile defaults to 3.2 V protection with a non-disableable 2.7 V floor",
    all(
        has_all(block, ("AUTO_SHUTDOWN_MILLIVOLTS=3200",
                        "LOW_BATTERY_SHUTDOWN_FLOOR_MILLIVOLTS=2700"))
        and "DISABLE_LOW_BATTERY_SHUTDOWN=1" not in block
        for block in effective.values()
    )
    and has_all(
        mymesh + nodeprefs + battery_policy,
        (
            "LOW_BATTERY_SHUTDOWN_DEFAULT_ENABLED",
            "_prefs.low_battery_shutdown_enabled = LOW_BATTERY_SHUTDOWN_DEFAULT_ENABLED ? 1 : 0;",
            "return enabled ? normal : floor;",
        ),
    ),
    "the UI toggle may select the emergency floor, but it must never remove undervoltage protection entirely",
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
            "int gps_top = display.height() - 4 * row_step;",
            "if (gps_top >= 14 && y > gps_top) y = gps_top;",
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
    "Targeted send snapshots immutable channel/contact identity before confirmation",
    has_all(
        uitask + mymesh + mymesh_h,
        (
            "uint16_t quickTargetItemCount() const",
            "uint16_t quickTargetTotalCount() const",
            "bool MyMesh::getQuickReplyContact(uint16_t list_idx, ContactInfo& contact)",
            "candidate.type != ADV_TYPE_CHAT",
            "recipient == NULL || recipient->type != ADV_TYPE_CHAT",
            "captureQuickTargetIdentity()",
            "memcpy(_quick_target_contact_pubkey, contact.id.pub_key",
            "sendQuickReplyToChannelId(_quick_target_channel_id, _quick_keyboard_text)",
            "sendQuickReplyToContactPubKey(_quick_target_contact_pubkey, _quick_keyboard_text)",
            "lookupContactByPubKey(pub_key, PUB_KEY_SIZE)",
            "uint8_t recipient_pub_key[PUB_KEY_SIZE];",
            "memcpy(entry.recipient_pub_key, recipient_pub_key, PUB_KEY_SIZE);",
            "lookupContactByPubKey(expected_ack_table[i].recipient_pub_key, PUB_KEY_SIZE)",
        ),
    ),
    "a mutable sorted list must not redirect a confirmation to a different row; 350-contact navigation remains 16-bit and repeaters stay filtered",
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
