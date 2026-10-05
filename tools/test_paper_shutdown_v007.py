#!/usr/bin/env python3
"""Execute production Paper shutdown and E213 rendering with host hardware stubs.

The screenshot uses the real C++ renderer, E213Display.cpp and embedded font/icon
bytes. Tests cover power-transition ordering and bounded BUSY failure; they do
not claim a physical panel or radio test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from PIL import Image

import test_e213_driver_flow as driver
from test_ui_sessions_v006 import function

ROOT = Path(__file__).resolve().parents[1]

PIXEL_STUB = r'''
extern unsigned char panel_pixels[122][250];
extern int panel_clipped;
inline void panelPixel(int x, int y, uint16_t color) {
  if (x < 0 || x >= 250 || y < 0 || y >= 122) { ++panel_clipped; return; }
  panel_pixels[y][x] = color == BLACK ? 0 : 255;
}
'''

PRELUDE = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>
#include "src/helpers/ui/E213Display.h"

static uint32_t fake_now = 100;
static bool detect_read = false, busy_stuck = false;
static int vext_off_writes = 0;
int stub_update_attempts = 0, panel_clipped = 0;
unsigned char panel_pixels[122][250];
std::vector<std::string> events;
unsigned long millis() { return fake_now; }
void delay(unsigned long value) { fake_now += (uint32_t)value; }
void yield() { ++fake_now; }
void pinMode(int, int) {}
void digitalWrite(int pin, int value) {
  if (pin == DISP_RST && value == LOW) detect_read = true;
  if (pin == PIN_VEXT_EN && value == HIGH) ++vext_off_writes;
}
int digitalRead(int pin) {
  assert(pin == DISP_BUSY);
  if (detect_read) { detect_read = false; return HIGH; }
  return busy_stuck ? HIGH : LOW;
}
struct Mesh {
  bool flush_ok = true;
  bool flushPendingStorage() { events.push_back("flush"); return flush_ok; }
} the_mesh;
struct Board {
  int powered_off = 0, rebooted = 0;
  void powerOff() { ++powered_off; events.push_back("poweroff"); }
  void reboot() { ++rebooted; events.push_back("reboot"); }
};
struct Manager { void disable() { events.push_back("disable"); } };
struct RecordingDisplay : E213Display {
  int frames = 0, icons = 0;
  std::vector<std::string> labels;
  void startFrame(ColorVal color = UIColor::window_bkg) override {
    ++frames; events.push_back("frame"); E213Display::startFrame(color);
  }
  void print(const char* text) override {
    labels.emplace_back(text); E213Display::print(text);
  }
  void drawXbm(int x, int y, const uint8_t* bits, int w, int h) override {
    ++icons; assert(w == 32 && h == 32);
    E213Display::drawXbm(x, y, bits, w, h);
  }
};
struct Saver { void render(DisplayDriver&) { assert(!"idle clock at Paper shutdown"); } };
struct UITask {
  Board* _board;
  DisplayDriver* _display;
  Manager* _interfaceManager;
  Saver* idle_saver = nullptr;
  unsigned _next_refresh = 99;
  int alerts = 0;
  bool button_pressed = false;
  bool isButtonPressed() const { return button_pressed; }
  void showAlert(const char* message, int duration) {
    assert(!strcmp(message, "Не выключено: память") && duration == 1600);
    ++alerts; events.push_back("alert");
  }
  void shutdown(bool restart = false, bool preserve_eink_frame = false,
                bool emergency = false);
};
'''

CASES = r'''
int main(int argc, char** argv) {
  assert(argc == 2);
  const std::string out = argv[1];
  unsigned cases = 0;
#if defined(HELTEC_WIRELESS_PAPER)
  // User-selected font never affects the terminal message. Exercise every
  // production Paper profile, beginning from a different existing screen.
  for (unsigned font = 0; font < 5; ++font) {
    RecordingDisplay display;
    assert(display.begin());
    display.setUiFont(font);
    display.setTextSize(1);
    display.startFrame(); display.setCursor(0, 0); display.print("12:34"); display.endFrame();
    display.frames = display.icons = 0; display.labels.clear();
    Board board; Manager manager; UITask task{&board, &display, &manager};
    events.clear(); task.shutdown();
    assert((events == std::vector<std::string>{"flush", "disable", "frame", "poweroff"}));
    assert(board.powered_off == 1 && board.rebooted == 0);
    assert(display.frames == 1 && display.icons == 1);
    assert((display.labels == std::vector<std::string>{"Выключено"}));
    assert(display.getUiFont() == font);
    assert(display.lastError() == E213_DISPLAY_OK);
    assert(panel_clipped == 0 && vext_off_writes == 0);
    std::ofstream image(out + "/paper-" + std::to_string(font) + ".pgm", std::ios::binary);
    image << "P5\n250 122\n255\n";
    image.write((const char*)panel_pixels, sizeof panel_pixels);
    ++cases;
  }
  {
    RecordingDisplay display; assert(display.begin()); display.turnOff();
    Board board; Manager manager; UITask task{&board, &display, &manager};
    task.shutdown();
    assert(display.frames == 1 && board.powered_off == 1);
    assert(display.lastError() == E213_DISPLAY_OK); ++cases;
  }
  {
    // Low-battery message is already on the panel. Preserve it byte-for-byte.
    RecordingDisplay display; assert(display.begin());
    memset(panel_pixels, 0x55, sizeof panel_pixels);
    Board board; Manager manager; UITask task{&board, &display, &manager};
    const int updates = stub_update_attempts;
    events.clear(); task.shutdown(false, true, true);
    assert((events == std::vector<std::string>{"flush", "disable", "poweroff"}));
    assert(display.frames == 0 && stub_update_attempts == updates);
    for (auto& row : panel_pixels) for (auto px : row) assert(px == 0x55);
    assert(board.powered_off == 1); ++cases;
  }
  {
    // Failed init must not call startFrame on an unusable panel or block off.
    RecordingDisplay display; Board board; Manager manager;
    UITask task{&board, &display, &manager}; busy_stuck = true;
    const uint32_t started = millis(); task.shutdown();
    assert(display.frames == 0 && board.powered_off == 1);
    assert(display.lastError() == E213_DISPLAY_BUSY_TIMEOUT);
    assert(millis() - started <= E213_INIT_BUDGET_MILLIS + 100);
    assert(vext_off_writes == 0); busy_stuck = false; ++cases;
  }
  {
    // A panel stuck during refresh still reaches board powerOff once.
    RecordingDisplay display; assert(display.begin());
    Board board; Manager manager; UITask task{&board, &display, &manager};
    busy_stuck = true; const uint32_t started = millis(); task.shutdown();
    assert(display.frames == 1 && board.powered_off == 1);
    assert(display.lastError() == E213_DISPLAY_BUSY_TIMEOUT);
    assert(millis() - started <= E213_FRAME_BUDGET_MILLIS + 160);
    assert(vext_off_writes == 0); busy_stuck = false; ++cases;
  }
#else
  {
    // Other companion boards do not acquire a new shutdown frame.
    RecordingDisplay display; assert(display.begin());
    Board board; Manager manager; UITask task{&board, &display, &manager};
    task.shutdown();
    assert(display.frames == 0 && board.powered_off == 1); ++cases;
  }
#endif
  {
    RecordingDisplay display; assert(display.begin());
    Board board; Manager manager; UITask task{&board, &display, &manager};
    events.clear(); task.shutdown(true);
    assert((events == std::vector<std::string>{"flush", "disable", "reboot"}));
    assert(board.rebooted == 1 && board.powered_off == 0 && display.frames == 0); ++cases;
  }
  {
    // A cancelled controlled shutdown must never paint a false "off" state.
    RecordingDisplay display; assert(display.begin());
    Board board; Manager manager; UITask task{&board, &display, &manager};
    the_mesh.flush_ok = false; events.clear(); task.shutdown();
    assert((events == std::vector<std::string>{"flush", "alert"}));
    assert(task.alerts == 1 && task._next_refresh == 0);
    assert(board.powered_off == 0 && board.rebooted == 0 && display.frames == 0);
    task.shutdown(false, true, true);
    assert(board.powered_off == 1 && display.frames == 0);
    the_mesh.flush_ok = true; ++cases;
  }
  {
    Board board; Manager manager; UITask task{&board, nullptr, &manager};
    task.shutdown(); assert(board.powered_off == 1); ++cases;
  }
  {
    // Execute the actual HomeScreen poll path: a failed flush cancels the
    // pending confirmation, without another write attempt on subsequent polls.
    RecordingDisplay display; assert(display.begin());
    Board board; Manager manager; UITask task{&board, &display, &manager};
    HomeScreen home{&task, true}; the_mesh.flush_ok = false;
    task.button_pressed = true; events.clear(); home.poll();
    assert(events.empty() && home._shutdown_init);
    task.button_pressed = false; home.poll();
    assert((events == std::vector<std::string>{"flush", "alert"}));
    assert(!home._shutdown_init && task.alerts == 1 && display.frames == 0);
    events.clear(); home.poll(); home.poll(); assert(events.empty());
    the_mesh.flush_ok = true; ++cases;
  }
  assert(vext_off_writes == 0);
  std::cout << cases << " shutdown scenarios passed\n";
}
'''


def run_host(work: Path, out: Path, paper: bool) -> str:
    cxx = driver.compiler()
    if cxx:
        prefix, path = [], str
    else:
        # Windows development hosts use their existing WSL compiler, as the
        # other production-C++ UI tests do. Missing compiler is a failure.
        prefix, cxx = ["wsl", "--exec"], "g++"

        def path(value):
            return subprocess.check_output(
                ["wsl", "--exec", "wslpath", "-a", str(value)], text=True).strip()

    binary = work / ("paper_shutdown" if paper else "other_shutdown")
    if os.name == "nt" and not prefix:
        binary = binary.with_suffix(".exe")
    definitions = [
        "DISP_RST=6", "DISP_BUSY=7", "PIN_VEXT_EN=45",
        "SMARTUI_CONNECTION_SELECTOR=1", "UI_EINK_IDLE_SCREENSAVER=0",
        "MESHCORE_E213_PROFILE_FONTS=1", "E213_FULL_REFRESH_EVERY=0",
        "E213_BUSY_TIMEOUT_MILLIS=50", "E213_INIT_BUDGET_MILLIS=100",
        "E213_FRAME_BUDGET_MILLIS=8", "E213_RETRY_DELAY_MILLIS=5",
        "E213_RETRY_MAX_DELAY_MILLIS=20", "E213_KEEP_SHARED_VEXT_ON=1",
    ]
    if paper:
        definitions.append("HELTEC_WIRELESS_PAPER=1")
    subprocess.run(prefix + [cxx, "-std=c++17", "-O1", "-Wall", "-Wextra",
        "-I", path(work / "stubs"), "-I", path(work),
        *[f"-D{value}" for value in definitions], path(work / "shutdown.cpp"),
        path(work / "src/helpers/ui/E213Display.cpp"), "-o", path(binary)],
        check=True, timeout=60)
    return subprocess.check_output(prefix + [path(binary), path(out)],
                                   text=True, timeout=30).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "qa_outputs/paper-shutdown-v007")
    parser.add_argument("--asset", type=Path, help="Optional tracked screenshot output")
    args = parser.parse_args()
    out = args.out.resolve()
    work = out / "host"
    ui = work / "src/helpers/ui"
    stubs = work / "stubs"
    ui.mkdir(parents=True, exist_ok=True)
    (stubs / "helpers").mkdir(parents=True, exist_ok=True)
    source = (ROOT / "examples/companion_radio/ui-new/UITask.cpp").read_text(encoding="utf-8")
    render = function(source, "static void uiRenderPaperShutdownFrame(")
    shutdown = function(source, "void UITask::shutdown(")
    home_source = source[source.index("class HomeScreen"):]
    poll = function(home_source, "  void poll() override").replace(" override", "")
    icon_source = (ROOT / "examples/companion_radio/ui-new/icons.h").read_text(encoding="utf-8")
    icon_start = icon_source.index("static const uint8_t power_icon[]")
    icon = icon_source[icon_start:icon_source.index("};", icon_start) + 2]
    # Scope guards complement executable scenarios: ordinary idle clock and
    # low-battery handoff stay independent of this terminal frame.
    assert "idle_saver->render(*_display)" in shutdown.split("#elif UI_EINK_IDLE_SCREENSAVER", 1)[1]
    assert "setCurrScreen(idle_saver);" in source
    assert "shutdown(false, true, true);" in source
    assert shutdown.index("flushPendingStorage()") < shutdown.index("uiRenderPaperShutdownFrame")
    for name in ("E213Display.cpp", "E213Display.h", "E213BusyGuard.h",
                 "DisplayDriver.h", "Utf8Cyrillic5x7.h"):
        shutil.copy2(ROOT / "src/helpers/ui" / name, ui / name)
    (work / "src/MeshCore.h").write_text("#pragma once\n", encoding="utf-8")
    eink = driver.EINK.replace("class BaseDisplay", PIXEL_STUB + "\nclass BaseDisplay", 1)
    eink = eink.replace("void fillRect(int,int,int,int,uint16_t){}", """
  void fillRect(int x,int y,int w,int h,uint16_t color) {
    for(int yy=y; yy<y+h; ++yy) for(int xx=x; xx<x+w; ++xx) panelPixel(xx,yy,color);
  }""")
    eink = eink.replace("void drawPixel(int,int,uint16_t){}",
                        "void drawPixel(int x,int y,uint16_t color){panelPixel(x,y,color);}")
    for name, content in {
        "Arduino.h": driver.ARDUINO, "SPI.h": "#pragma once\n#include <Arduino.h>\n",
        "Wire.h": "#pragma once\n", "heltec-eink-modules.h": eink,
        "CRC32.h": driver.CRC, "helpers/RefCountedDigitalPin.h": driver.REFCOUNT,
    }.items():
        (stubs / name).write_text(content, encoding="utf-8")
    (work / "shutdown.cpp").write_text(PRELUDE + "\n" + icon +
        "\n#if defined(HELTEC_WIRELESS_PAPER)\n" + render + "\n#endif\n" +
        shutdown + "\nstruct HomeScreen { UITask* _task; bool _shutdown_init;\n" +
        poll + "\n};\n" + CASES, encoding="utf-8")
    results = [run_host(work, out, paper) for paper in (True, False)]
    frames = [Image.open(out / f"paper-{font}.pgm").copy() for font in range(5)]
    assert all(frame.tobytes() == frames[0].tobytes() for frame in frames[1:])
    frame = frames[0]
    ink = frame.point(lambda px: 255 - px)
    bbox = ink.getbbox()
    assert bbox is not None and 0 < bbox[0] < bbox[2] < 250 and 0 < bbox[1] < bbox[3] < 122
    assert ink.crop((0, 32, 250, 64)).getbbox() is not None, "power icon missing"
    assert ink.crop((0, 76, 250, 90)).getbbox() is not None, "shutdown label missing"
    assert ink.crop((0, 64, 250, 76)).getbbox() is None, "icon/text overlap"
    screenshot = frame.resize((1000, 488), Image.Resampling.NEAREST)
    screenshot.save(out / "WIRELESS_PAPER_SHUTDOWN.png")
    if args.asset:
        args.asset.resolve().parent.mkdir(parents=True, exist_ok=True)
        screenshot.save(args.asset.resolve())
    report = {
        "results": results, "font_profiles": 5, "ink_bbox": bbox,
        "renderer_sha256": hashlib.sha256((render + shutdown + icon).encode()).hexdigest(),
        "pixels_sha256": hashlib.sha256(frame.tobytes()).hexdigest(),
        "scope": "extracted production shutdown/renderer + production E213 driver/fonts; stub hardware, no physical panel/radio test",
        "failures": [],
    }
    (out / "REPORT.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("PASS Paper shutdown: " + "; ".join(results) + "; 5 real-font renders identical")


if __name__ == "__main__":
    main()
