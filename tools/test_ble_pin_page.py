#!/usr/bin/env python3
"""Run production BLE PIN carousel/lifecycle code for all seven public profiles.

Host C++ execution only. The framebuffer checks live in test_connection_ui_v005.py;
this test does not pair Bluetooth, flash hardware, or change persisted settings.
"""
from __future__ import annotations

import argparse
import configparser
from pathlib import Path
import re
import shlex
import subprocess

from package_smartui_release import ESP_ENVS, NRF_ENVS
from test_ui_sessions_v006 import function, run_cpp

ROOT = Path(__file__).resolve().parents[1]
UI_PATH = ROOT / "examples/companion_radio/ui-new/UITask.cpp"


def resolved_profiles():
    """Resolve the release environments, including inherited flags/unflags."""
    config = configparser.ConfigParser(interpolation=None, strict=False,
                                       inline_comment_prefixes=(";",))
    config.read([ROOT / "platformio.ini", *sorted((ROOT / "variants").glob("*/platformio.ini"))],
                encoding="utf-8")

    def resolve(section, option, stack=()):
        key = (section, option)
        assert key not in stack, f"recursive build configuration: {key}"
        if not config.has_option(section, option):
            parents = re.split(r"[,\n]+", config[section].get("extends", ""))
            for parent in parents:
                if parent.strip():
                    value = resolve(parent.strip(), option, (*stack, key))
                    if value:
                        return value
            return ""
        return re.sub(r"\$\{([^}]+)\}", lambda match:
                      resolve(*match[1].rsplit(".", 1), (*stack, key)), config[section][option])

    def operations(text):
        tokens = iter(shlex.split(text))
        for token in tokens:
            if token in ("-D", "-U"):
                token += next(tokens)
            if token.startswith(("-D", "-U")):
                name, _, value = token[2:].partition("=")
                yield token[1], name, value or "1"

    profiles = []
    for env in (*NRF_ENVS, *ESP_ENVS):
        section = "env:" + env
        removed = set(operations(resolve(section, "build_unflags")))
        flags = {}
        for operation, name, value in operations(resolve(section, "build_flags")):
            if (operation, name, value) in removed:
                continue
            if operation == "U":
                flags.pop(name, None)
            else:
                flags[name] = value
        for name in ("UI_BLE_PIN_PAGE", "BLE_PIN_PERSIST_RANDOM", "SMARTUI_CONNECTION_SELECTOR"):
            assert flags.get(name) == "1", (env, name, flags.get(name))
        profiles.append((env, flags))
    assert len(profiles) == 7 and len({env for env, _ in profiles}) == 7
    return profiles


def _preprocessor(text):
    """Keep actual conditional/default directives without hardware declarations."""
    lines = []
    continuation = False
    for line in text.splitlines():
        directive = re.match(r"\s*#\s*(\w+)", line)
        keep = continuation or (directive and directive[1] in
                                ("if", "ifdef", "ifndef", "elif", "else", "endif", "define", "undef"))
        if keep:
            lines.append(line)
        continuation = bool(keep and line.rstrip().endswith("\\"))
    return "\n".join(lines) + "\n"


def production_defines(source, flags):
    """C++ resolves profile-dependent defaults exactly as the production UI does."""
    definitions = "\n".join(f"#define {name} {value}" for name, value in flags.items()
                              if name.startswith(("UI_", "HELTEC_", "PIN_", "AUTO_", "BLE_PIN"))
                              or name in ("PROMICRO", "ST7789", "ENV_INCLUDE_GPS",
                                          "SMARTUI_CONNECTION_SELECTOR", "LED_STATE_ON")) + "\n"
    header = UI_PATH.with_suffix(".h").read_text(encoding="utf-8")
    header = header[header.index("#ifndef LED_STATE_ON"):header.index("class UITask :")]
    defaults = source[source.index("#ifndef AUTO_OFF_MILLIS"):source.index("class HomeScreen :")]
    return definitions + _preprocessor(header) + _preprocessor(defaults)


def test_code(source, flags):
    home_source = source[source.index("class HomeScreen :"):]
    enum = function(home_source, "  enum HomePage") + ";\n"
    methods = "\n".join(function(home_source, marker) for marker in (
        "  bool isSettingsItem(", "  bool isPageVisibleInCurrentMenu(",
        "  uint8_t nextVisiblePage(", "  static uint8_t defaultHomePage()",
        "  uint8_t visiblePageCount()", "  uint8_t visiblePageIndex()",
        "  void resetToFirstPage()", "  bool isClockPage()", "  bool isBlePinPage()",
        "  void poll() override"))
    task_methods = "\n".join(function(source, marker) for marker in (
        "void UITask::updateConnectionState()", "void UITask::gotoHomeFirstScreen()",
        "void UITask::markDisplayWake(bool reset_to_clock)"))
    # The real constructor must use the same tested default, never a PIN popup.
    constructor = function(home_source, "  HomeScreen(UITask*")
    assert "_page(defaultHomePage())" in constructor
    return production_defines(source, flags) + r'''
#include <cstdio>
#include <cstdint>
#include <set>
#include "UiTiming.h"
#include "../ConnectionTypes.h"
uint32_t now=100;
uint32_t millis() { return now; }
unsigned checks=0, failures=0;
#define CHECK(x) do { ++checks; if (!(x)) { if (++failures <= 12) \
  std::fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); } } while (0)
struct Mesh {
  uint32_t pin=123456;
  uint32_t getBLEPin() const { return pin; }
} the_mesh;
struct UIScreen { virtual ~UIScreen()=default; virtual void poll() {} };
struct UITask {
  bool connected=false, pressed=false;
  CompanionStatus status;
  unsigned shutdowns=0;
  bool _last_connection_state=false;
  uint32_t _ble_state_changed_at=0, _next_refresh=555;
  UIScreen* home=nullptr;
  UIScreen* curr=nullptr;
  uint32_t _display_recover_until=0, _display_recover_next=0;
  bool _display_recover_reset_to_clock=false, _button_wake_pending=false;
  uint32_t _button_wake_pending_until=0, _display_wake_lock_until=0, _last_activity_ms=0;
  bool hasConnection() const { return connected; }
  CompanionStatus getCompanionStatus() const { return status; }
  bool supportsPeriodicAgcReset() const { return true; }
  bool hasUiFontChoices() const { return true; }
  bool hasUiThemeChoices() const { return true; }
  bool isButtonPressed() const { return pressed; }
  void shutdown() { ++shutdowns; }
  void invalidateBatteryCache() {}
  bool hasActiveComposeSession() const { return false; }
  bool hasActiveInboxSession() const { return false; }
  void extendAutoOff(unsigned long) {}
  void setCurrScreen(UIScreen* screen) { curr=screen; }
  void updateConnectionState();
  void gotoHomeFirstScreen();
  void markDisplayWake(bool reset_to_clock);
};
struct Resettable { void reset() {} };
struct HomeScreen : UIScreen { public:
''' + enum + r'''
  UITask* _task;
  uint8_t _page=defaultHomePage();
  bool _settings_open=false, _shutdown_init=false, _quick_reply_open=false;
  uint8_t _quick_reply_idx=0;
  Resettable _connection_flow, _notify_picker;
  bool _chat_filter_open=false, _adc_edit=false;
  float _adc_draft=0;
  uint8_t _compact_settings_depth=0, _compact_settings_group=0, _compact_settings_cursor=0;
  uint8_t _timezone_picker_cursor=0, _font_picker_cursor=0, _theme_picker_cursor=0;
  uint8_t _tone_picker_cursor=0, _hardware_test_step=0;
  int _chat_scroll_px=0, _chat_scroll_dir=0, _chat_pause_until=0, _chat_latest_ts=0;
  bool _chat_layout_valid=false;
  int _chat_layout_total_h=0, _chat_item_h[UI_CHAT_LIST_SIZE]={};
  explicit HomeScreen(UITask& task):_task(&task) { task.home=this; task.curr=this; }
  void cancelAdcEdit() {}
  void resetQuickKeyboard() {}
''' + methods + "\n};\n" + task_methods + r'''
int main() {
  const CompanionMode modes[]={CompanionMode::BLE, CompanionMode::USB, CompanionMode::WiFi};
  for (auto mode : modes) for (bool connected : {false,true}) {
    UITask task;
    task.status.selected=mode;
    task.connected=connected;
    HomeScreen home(task);
    CHECK(home.isClockPage());
    CHECK(!home.isBlePinPage());
    CHECK(home.defaultHomePage()!=HomeScreen::BLE_PIN);
    for (uint32_t pin : {1U,123456U,999999U}) {
      the_mesh.pin=pin;
      home._settings_open=false;
      CHECK(home.isPageVisibleInCurrentMenu(HomeScreen::BLE_PIN));
      const unsigned count=home.visiblePageCount();
      // Both carousel directions reach PIN once, return to the start, and
      // report matching page dots. Execute the actual navigation functions.
      for (int direction : {-1,1}) {
        home._page=home.defaultHomePage();
        std::set<unsigned> pages, indices;
        for (unsigned i=0;i<count;++i) {
          CHECK(home.isPageVisibleInCurrentMenu(home._page));
          CHECK(pages.insert(home._page).second);
          CHECK(indices.insert(home.visiblePageIndex()).second);
          CHECK(home.visiblePageIndex()<count);
          home._page=home.nextVisiblePage(home._page,direction);
        }
        CHECK(home._page==home.defaultHomePage());
        CHECK(pages.count(HomeScreen::BLE_PIN)==1);
      }
      home._settings_open=true;
      CHECK(!home.isPageVisibleInCurrentMenu(HomeScreen::BLE_PIN));
      home._settings_open=false;
      home._page=HomeScreen::BLE_PIN;
      CHECK(home.isBlePinPage());
      home.poll();
      CHECK(home._page==HomeScreen::BLE_PIN && task.shutdowns==0);
      CHECK(task.status.selected==mode && the_mesh.pin==pin);
      // A connect or disconnect edge redraws this page, never dismisses it.
      task._last_connection_state=!connected;
      task._next_refresh=555;
      task._ble_state_changed_at=0;
      task.updateConnectionState();
      CHECK(home.isBlePinPage() && task.curr==&home);
      CHECK(task._last_connection_state==connected);
      CHECK(task._ble_state_changed_at==now && task._next_refresh==0);
      task._next_refresh=555;
      task.updateConnectionState();
      CHECK(task._next_refresh==555);
      // Ordinary clock wake remains ordinary clock wake; no automatic PIN.
      task.markDisplayWake(true);
      CHECK(home.isClockPage() && !home.isBlePinPage());
      CHECK(task.status.selected==mode && the_mesh.pin==pin);
      task._last_connection_state=!connected;
      task.updateConnectionState();
      CHECK(home.isClockPage());
      home._page=HomeScreen::BLE_PIN;
      task.markDisplayWake(false);
      CHECK(home.isBlePinPage());
      // Zero means pairing PIN disabled: no phantom entry or extra page dot.
      the_mesh.pin=0;
      CHECK(!home.isPageVisibleInCurrentMenu(HomeScreen::BLE_PIN));
      CHECK(unsigned(home.visiblePageCount())+1==count);
      home._page=home.defaultHomePage();
      for (unsigned i=0;i<count;++i) {
        home._page=home.nextVisiblePage(home._page,1);
        CHECK(home._page!=HomeScreen::BLE_PIN);
      }
      the_mesh.pin=pin;
    }
    // Background PIN state must not replace another active screen or its timer.
    UIScreen other;
    home._page=HomeScreen::BLE_PIN;
    task.curr=&other;
    task._last_connection_state=!connected;
    task._next_refresh=555;
    task.updateConnectionState();
    CHECK(task.curr==&other && home._page==HomeScreen::BLE_PIN && task._next_refresh==555);
    task.home=nullptr;
    task._last_connection_state=!connected;
    task.updateConnectionState();
    CHECK(task.curr==&other && task._next_refresh==555);
    // Removing PIN-specific poll logic must preserve the one-shot shutdown.
    task.pressed=true;
    home._shutdown_init=true;
    home.poll();
    CHECK(task.shutdowns==0 && home._shutdown_init);
    task.pressed=false;
    home.poll(); home.poll();
    CHECK(task.shutdowns==1 && !home._shutdown_init);
  }
  std::printf("%s %u production BLE PIN navigation/lifecycle checks (%u failures)\n",
              failures ? "FAIL" : "PASS",checks,failures);
  return failures ? 1 : 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=UI_PATH,
                        help="UITask.cpp snapshot for before/after regression verification")
    parser.add_argument("--out", type=Path, default=ROOT / "qa_outputs/ble-pin-page")
    args = parser.parse_args()
    source = args.source.read_text(encoding="utf-8")
    profiles = resolved_profiles()
    failed = []
    for index, (env, flags) in enumerate(profiles):
        print(env, flush=True)
        try:
            print(run_cpp(test_code(source, flags), args.out, f"ble_pin_{index}"), end="", flush=True)
        except subprocess.CalledProcessError as error:
            failed.append(env)
            if error.output:
                print(error.output, end="", flush=True)
    if failed:
        raise SystemExit("FAIL public profiles: " + ", ".join(failed))
    print("PASS all seven public build profiles; no device execution")


if __name__ == "__main__":
    main()
