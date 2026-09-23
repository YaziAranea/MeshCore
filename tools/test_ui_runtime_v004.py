"""Bounded SmartUI 0.04 runtime regression checks.

Compiles the production ADC/timer helpers, then connects them to the exact
UITask call sites for draft calibration, night prompts, popup lifetime,
storage-safe shutdown/recovery, display hot-attach and preference commits.
This is host logic coverage; it does not emulate ADC hardware or flash faults.
"""

from pathlib import Path

from test_notify_pins_v4 import ROOT, run_cpp
from simulate_oled_128x64 import Oled, STYLES


UI = ROOT / "examples/companion_radio/ui-new/UITask.cpp"
UI_H = ROOT / "examples/companion_radio/ui-new/UITask.h"
OUT = ROOT / "qa_outputs/ui-runtime-v004"


def section(source: str, start: str, end: str) -> str:
    left = source.index(start)
    right = source.index(end, left + len(start))
    return source[left:right]


def require(block: str, *tokens: str) -> int:
    for token in tokens:
        assert token in block, token
    return len(tokens)


def helper_harness(source: str) -> str:
    adc = (ROOT / "examples/companion_radio/ui-new/AdcCalibrationUi.h").read_text(
        encoding="utf-8"
    ).replace("#pragma once", "")
    timing = (ROOT / "examples/companion_radio/ui-new/UiTiming.h").read_text(
        encoding="utf-8"
    ).replace("#pragma once", "")
    pin_gate = section(source, "static bool isNotifyGpioPinBlockedByBuild", "static int getNextNotifyGpioPin")
    return f"""
#include <cassert>
#include <cstdint>
#include <cstdio>
#define SMARTUI_OPTIONAL_UART_GPS 1
#define ENV_INCLUDE_GPS 1
#define PIN_GPS_RX 3
#define PIN_GPS_TX 4
#define PIN_GPS_EN 5
#define UI_BLOCK_BOARD_LED_NOTIFY 0
{adc}
{timing}
{pin_gate}
int main() {{
  unsigned checks = 0;
#define CHECK(x) do {{ ++checks; assert(x); }} while (0)
  // Draft display may show 3.075 V, but it is a pure calculation over the
  // committed 4.100 V reading and never mutates MainBoard calibration.
  CHECK(smartui::adcPreviewMilliVolts(4100, 1.0f, 0.75f) == 3075);
  CHECK(smartui::adcPreviewMilliVolts(4100, 1.0f, 1.25f) == 5125);
  CHECK(smartui::adcPreviewMilliVolts(4100, 0.0f, 0.75f) == 4100);
  CHECK(smartui::adcPreviewMilliVolts(4100, 1.0f, 0.0f) == 4100);
  CHECK(smartui::adcPreviewMilliVolts(65535, 0.5f, 2.0f) == 65535);

  // A deadline that lands exactly on zero must remain scheduled.
  CHECK(smartui::optionalDeadlineAfter(0xffffff9cU, 100U) == 1U);
  CHECK(smartui::optionalDeadlineAfter(100U, 50U) == 150U);
  CHECK(smartui::optionalDeadlinePending(0xfffffff0U, 0x10U));
  CHECK(!smartui::optionalDeadlinePending(0x10U, 0x10U));
  CHECK(smartui::deadlineReached(0x10U, 0x10U));
  CHECK(smartui::elapsedAtLeast(0x10U, 0xfffffff0U, 32U));
  CHECK(isNotifyGpioPinBlockedByBuild(3));
  CHECK(isNotifyGpioPinBlockedByBuild(4));
  CHECK(isNotifyGpioPinBlockedByBuild(5));
  CHECK(!isNotifyGpioPinBlockedByBuild(2));
  std::printf("PASS %u compiled production ADC/timer helper cases\\n", checks);
}}
"""


def main() -> None:
    source = UI.read_text(encoding="utf-8")
    header = UI_H.read_text(encoding="utf-8")
    checks = 0

    adjust = section(source, "void adjustAdcMultiplier", "void cancelAdcEdit")
    cancel = section(source, "void cancelAdcEdit", "#endif")
    safety = section(source, "smartui::BatteryReading UITask::readSafetyBattery", "bool UITask::hasTrustedTime")
    adc_set = section(source, "bool UITask::setAdcMultiplier", "void UITask::toggleBuzzer")
    checks += require(adjust, "_adc_draft = clampAdcMultiplier")
    assert "setAdcMultiplier" not in adjust; checks += 1
    checks += require(cancel, "_adc_edit = false;", "_adc_draft = 0.0f;")
    assert "setAdcMultiplier" not in cancel; checks += 1
    assert safety.count("_board->getBattMilliVolts()") == 3; checks += 1
    assert "getAdcPreviewMilliVolts" not in safety; checks += 1
    checks += require(adc_set, "const float previous_multiplier", "commitUiPrefs(before)",
                      "_board->setAdcMultiplier(previous_multiplier)",
                      "_low_batt_strikes = 0;")

    idle = section(source, "bool isIdleForNightPrompt() const", "#if UI_ADC_MULTIPLIER_PAGE == 1\n  bool restoreAdcDefaultConfirmed")
    checks += require(idle, "_settings_open", "_quick_reply_open", "_shutdown_init",
                      "_quick_keyboard_open", "_quick_confirm_open", "_adc_edit",
                      "_adc_reset_confirm", "_compact_settings_depth != 0")
    night = section(source, "void UITask::nightModeHandler()", "void UITask::beginImportantNotify")
    idle_gate = night.index("isIdleForNightPrompt()")
    mark_day = night.index("_node_prefs->night_prompt_day = local_day;")
    assert idle_gate < mark_day; checks += 1
    assert "gotoHomeFirstScreen" not in night; checks += 1
    checks += require(night, "local_day > _node_prefs->night_prompt_day",
                      "commitPrefsOrRollback(before)", "optionalDeadlineAfter(")

    popup = section(source, "void UITask::handlePendingPopupWake()", "void UITask::shutdown")
    assert popup.index("setCurrScreen(msg_preview);") < popup.index("_last_activity_ms = now;"); checks += 1
    checks += require(popup, "extendAutoOff(now);", "_storage_recovery_active")
    loop = section(source, "void UITask::loop()", "void UITask::messageTransferState")
    assert loop.index("handlePendingPopupWake();") < loop.index("UI_MENU_AUTO_HOME_MILLIS"); checks += 1

    shutdown = section(source, "void UITask::shutdown", "bool UITask::isButtonPressed")
    assert shutdown.index("the_mesh.flushPendingStorage()") < shutdown.index("_board->reboot()"); checks += 1
    checks += require(shutdown, "if (!storage_flushed && !emergency)",
                      'showAlert("Не выключено: память"', "return;")
    checks += require(source, "shutdown(false, true, true);",
                      "void UITask::storageRecoveryRequired(StorageRecoveryReason reason)",
                      "reason != StorageRecoveryReason::factoryResetFailed",
                      "ОШИБКА ПАМЯТИ", "Обычная работа остановлена")

    attach = section(source, "bool UITask::attachDisplay", "void UITask::showAlert")
    checks += require(attach, "display->turnOn();", "if (!display->isOn()) return false;",
                      "_display = display;", "setUiTheme", "markDisplayWake(false);")
    assert "gotoHome" not in attach and "reset" not in attach; checks += 1
    checks += require(header, "bool attachDisplay(DisplayDriver* display);",
                      "void shutdown(bool restart = false, bool preserve_eink_frame = false,",
                      "bool emergency = false);")

    pin_gate = section(source, "static bool isNotifyGpioPinBlockedByBuild", "static int getNextNotifyGpioPin")
    checks += require(pin_gate, "SMARTUI_OPTIONAL_UART_GPS", "PIN_GPS_RX", "PIN_GPS_TX", "PIN_GPS_EN")
    assert pin_gate.index("PIN_GPS_RX") < pin_gate.index("UI_BLOCK_BOARD_LED_NOTIFY"); checks += 1

    gps_page = section(source, "} else if (_page == HomePage::GPS)", "#if UI_SENSORS_PAGE == 1")
    checks += require(gps_page, "nmea->supportsInputStatus()", "nmea->hasRecentInput()",
                      'recent_input ? "Поиск спутников" : "Нет данных UART"')
    # The exact checked-in 5x7 glyphs and all five OLED spacing styles keep the
    # two new statuses intact inside the production GPS row allocation.
    for style in STYLES:
        for wait_text in ("Нет данных UART", "Поиск спутников"):
            oled = Oled(style)
            oled.text(0, 18, "МОДУЛЬ", tag="source", expected="МОДУЛЬ")
            oled.text(127, 18, "ПОИСК", right=True, tag="fix", expected="ПОИСК")
            oled.text(0, 26, "СПУТН.", tag="sat", expected="СПУТН.")
            oled.text(127, 26, "0", right=True, tag="sat-count", expected="0")
            oled.text(0, 34, wait_text, max_width=128, tag="wait", expected=wait_text)
            oled.validate_elements(("source", "fix", "sat", "sat-count", "wait"))
            assert not oled.overflows, f"{style[0]} / {wait_text}: {oled.overflows}"
            checks += 1

    assert "the_mesh.savePrefs();" not in source; checks += 1
    checks += require(source, "bool UITask::commitUiPrefs(const NodePrefs& before)",
                      "the_mesh.commitPrefsOrRollback(before)", 'showAlert("Не сохранено: память"')

    print(run_cpp(helper_harness(source), "helpers", OUT), end="")
    print(f"PASS {checks} exact UITask 0.04 source-wiring checks")


if __name__ == "__main__":
    main()
