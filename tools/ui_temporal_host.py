"""Bounded actual-C++ timing/refresh tests; no radio, panel or scheduler emulation.

The exact uiMarqueeOffset and E213Display::endFrame bodies are compiled with
recording stubs. Synthetic CRCs stand for changed operation streams, NOT for
rendered pixels. This proves branch/count policy only, not BUSY timing/ghosting.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    end = source.index("\n}", start) + 2
    return source[start:end]


def marquee_parameters() -> tuple[int, int]:
    source = (ROOT / "examples/companion_radio/ui-new/UITask.cpp").read_text(encoding="utf-8")
    return tuple(int(re.search(rf"#define\s+{name}\s+(\d+)", source).group(1))
                 for name in ("UI_TEXT_MARQUEE_STEP_MS", "UI_TEXT_MARQUEE_EDGE_PAUSE_STEPS"))


def marquee_window(text: str, width_fn, max_width: int, millis: int) -> str:
    """Plain Unicode text only; rich emoji/formatting tokenization is not modelled."""
    text = text.split("\n", 1)[0].split("\r", 1)[0]
    if width_fn(text) <= max_width:
        return text
    def fit(value):
        out = ""
        for char in value:
            if out and width_fn(out + char) > max_width:
                break
            out += char
            if len(out.encode("utf-8")) >= 159:
                break
        return out
    initial = fit(text)
    maximum = max(0, len(text) - len(initial))
    step, pause = marquee_parameters()
    phase = (millis // step) % (pause + maximum + pause)
    offset = 0 if phase < pause else min(maximum, phase - pause + 1)
    return fit(text[offset:].lstrip(" "))


def run_temporal_host(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    ui = (ROOT / "examples/companion_radio/ui-new/UITask.cpp").read_text(encoding="utf-8")
    e213 = (ROOT / "src/helpers/ui/E213Display.cpp").read_text(encoding="utf-8")
    config = (ROOT / "variants/heltec_wireless_paper/platformio.ini").read_text(encoding="utf-8")
    every = int(re.search(r"E213_FULL_REFRESH_EVERY=(\d+)", config).group(1))
    step, pause = marquee_parameters()
    code = r'''
#include <stdint.h>
#include <stdio.h>
static uint32_t now_ms;
uint32_t millis() { return now_ms; }
void yield() {}
struct CRC { uint32_t value; uint32_t finalize() { return value; } };
struct Panel {
 int updates=0, full=0; bool fast=true;
 void fastmodeOff() { fast=false; }
 void fastmodeOn(bool) { fast=true; }
 void update() { ++updates; if (!fast) ++full; }
};
struct E213Display {
 CRC display_crc{0}; uint32_t last_display_crc_value=0;
 int _partial_refresh_count=0; Panel panel; Panel* display=&panel;
 void endFrame();
};
'''
    code += f"\n#define UI_TEXT_MARQUEE_STEP_MS {step}\n#define UI_TEXT_MARQUEE_EDGE_PAUSE_STEPS {pause}\n#define E213_FULL_REFRESH_EVERY {every}\n"
    code += function_body(ui, "static uint16_t uiMarqueeOffset(") + "\n"
    code += function_body(e213, "void E213Display::endFrame()") + "\n"
    code += r'''
int main() {
 for (int fit : {4,7,12}) for (int phase=0; phase<40; ++phase) {
   now_ms=phase*UI_TEXT_MARQUEE_STEP_MS;
   printf("M %d %d %u\n", fit, phase, uiMarqueeOffset(20,fit));
 }
 E213Display d;
 // Clock entry, same-frame redraw, keyboard/recipient/DM/return, then enough
 // changed operation CRCs to cross two full-refresh boundaries.
 for (int change=1; change<=2*E213_FULL_REFRESH_EVERY+1; ++change) {
   d.display_crc.value=change; d.endFrame(); d.endFrame();
   printf("E %d %d %d %d\n", change,d.panel.updates,d.panel.full,d._partial_refresh_count);
 }
}
'''
    code = "#include <initializer_list>\n" + code
    path = out / "ui_temporal.cpp"
    path.write_text(code, encoding="utf-8")
    if shutil.which("g++"):
        binary = out / "ui_temporal"
        subprocess.run(["g++", "-std=c++17", "-Os", str(path), "-o", str(binary)], check=True)
        data = subprocess.check_output([str(binary)]).decode()
    else:
        linux = subprocess.check_output(["wsl", "--exec", "wslpath", "-a", out.as_posix()]).decode().strip()
        subprocess.run(["wsl", "--exec", "g++", "-std=c++17", "-Os", linux+"/ui_temporal.cpp", "-o", linux+"/ui_temporal"], check=True)
        data = subprocess.check_output(["wsl", "--exec", linux+"/ui_temporal"]).decode()
    checks = 0
    refreshes = []
    for line in data.splitlines():
        kind, *numbers = line.split()
        values = list(map(int, numbers))
        if kind == "M":
            fit, phase, observed = values
            maximum = 20-fit
            p = phase % (pause+maximum+pause)
            expected = 0 if p < pause else min(maximum, p-pause+1)
            assert observed == expected, (line, expected)
        else:
            change, updates, full, partial = values
            assert (updates, full, partial) == (change, change//every, change%every), line
            refreshes.append({"changed_operation_crc":change, "updates":updates,
                              "full":full, "partial_count":partial})
        checks += 1
    report = {"checks": checks, "failures": [], "full_refresh_every":every,
              "marquee_start": "global millis; not reset on page entry",
              "proof": "actual C++ uiMarqueeOffset and E213 endFrame with recording stubs",
              "limits": "No firmware scheduler/button/radio execution; no real CRC implementation, panel BUSY, duration, battery draw or ghosting proof.",
              "refresh_sequence":refreshes}
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
