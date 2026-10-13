"""Host QA for SmartUI companion connection and manual BLE PIN pages.

Compiles the production policy helper, checks UITask source wiring, then
extracts and runs the production render methods with checked-in firmware bitmap
metrics. This is not hardware execution; controller tests cover switching and
timeout.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

import simulate_dev2_settings as settings


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "qa_outputs/connection-ui-v005"
UI_PATH = ROOT / "examples/companion_radio/ui-new/UITask.cpp"
HEADER_PATH = ROOT / "examples/companion_radio/ui-new/UITask.h"
POLICY_PATH = ROOT / "examples/companion_radio/ui-new/ConnectionUiPolicy.h"


def compile_policy() -> int:
    code = f'''#include "../../examples/companion_radio/ui-new/ConnectionUiPolicy.h"
#include <cassert>
#include <cstdio>
int main() {{
  unsigned checks=0;
  #define CHECK(x) do {{ ++checks; assert(x); }} while(0)
  for (int e=1; e<=static_cast<int>(ConnectionChangeError::Apply); ++e) {{
    const auto error=static_cast<ConnectionChangeError>(e);
    CHECK(smartui::connectionChangeErrorTitle(error)[0]);
    CHECK(smartui::connectionChangeErrorHint(error)[0]);
    CHECK(smartui::connectionChangeErrorCode(error)[0]);
  }}
  CHECK(!smartui::connectionChangeErrorTitle(ConnectionChangeError::None)[0]);
  CompanionStatus nrf;
  nrf.capabilities=COMPANION_CAP_BLE|COMPANION_CAP_USB;
  nrf.selected=CompanionMode::BLE;
  CHECK(smartui::companionModeCount(nrf)==2);
  CHECK(smartui::companionModeAt(nrf,0)==CompanionMode::BLE);
  CHECK(smartui::companionModeAt(nrf,1)==CompanionMode::USB);
  CHECK(!smartui::companionModeSupported(nrf,CompanionMode::WiFi));

  CompanionStatus esp=nrf;
  esp.capabilities|=COMPANION_CAP_WIFI;
  esp.selected=CompanionMode::USB;
  CHECK(smartui::companionModeCount(esp)==3);
  CHECK(smartui::companionModeIndex(esp,CompanionMode::USB)==1);
  CHECK(smartui::wifiApprovalSurfaceSafe(true,true,smartui::ConnectionUiView::Status,false));
  CHECK(!smartui::wifiApprovalSurfaceSafe(true,true,smartui::ConnectionUiView::Picker,false));
  CHECK(!smartui::wifiApprovalSurfaceSafe(true,false,smartui::ConnectionUiView::Status,false));
  CHECK(smartui::wifiApprovalSurfaceSafe(false,false,smartui::ConnectionUiView::Status,true));

  smartui::ConnectionUiFlow flow;
  CHECK(flow.view()==smartui::ConnectionUiView::Status);
  flow.openPicker(esp);
  CHECK(flow.view()==smartui::ConnectionUiView::Picker && flow.cursor()==1);
  flow.movePicker(esp,1);
  CHECK(flow.cursor()==2);
  CHECK(flow.selectPicker(esp));
  CHECK(flow.view()==smartui::ConnectionUiView::Confirm);
  CHECK(flow.candidate()==CompanionMode::WiFi && !flow.confirmChange());
  flow.moveConfirm(); CHECK(flow.confirmChange());
  flow.cancelConfirm();
  CHECK(flow.view()==smartui::ConnectionUiView::Picker && !flow.confirmChange());
  flow.openPicker(esp);
  CHECK(!flow.selectPicker(esp));
  CHECK(flow.view()==smartui::ConnectionUiView::Status);
  flow.openPicker(esp);
  flow.movePicker(esp,1); flow.movePicker(esp,1);
  CHECK(flow.pickerOnBack(esp));
  CHECK(!flow.selectPicker(esp) && flow.view()==smartui::ConnectionUiView::Status);

  smartui::WifiApprovalUiFlow approval;
  CompanionStatus pending=esp;
  pending.wifiApprovalPending=true; pending.wifiRequestId=41;
  CHECK(approval.sync(pending));
  CHECK(approval.open() && approval.requestId()==41 && !approval.allow());
  approval.toggle(); CHECK(approval.allow());
  CHECK(!approval.sync(pending) && approval.allow());
  pending.wifiRequestId=42;
  CHECK(approval.sync(pending) && approval.requestId()==42 && !approval.allow());
  pending.wifiApprovalPending=false;
  CHECK(!approval.sync(pending) && !approval.open());
  std::printf("PASS %u production connection-policy C++ checks\\n",checks);
}}
'''
    OUT.mkdir(parents=True, exist_ok=True)
    cpp = OUT / "connection_policy.cpp"
    cpp.write_text(code, encoding="utf-8")
    if shutil.which("g++"):
        binary = OUT / "connection_policy"
        subprocess.run(["g++", "-std=c++17", "-O1", "-Wall", "-Wextra", "-Werror",
                        str(cpp), "-o", str(binary)], check=True)
        text = subprocess.check_output([str(binary)], text=True)
    else:
        linux = subprocess.check_output(
            ["wsl", "--exec", "wslpath", "-a", OUT.resolve().as_posix()], text=True
        ).strip()
        subprocess.run(["wsl", "--exec", "g++", "-std=c++17", "-O1", "-Wall", "-Wextra",
                        "-Werror", linux + "/connection_policy.cpp", "-o", linux + "/connection_policy"],
                       check=True)
        text = subprocess.check_output(["wsl", "--exec", linux + "/connection_policy"], text=True)
    print(text, end="")
    return int(text.split()[1])


def source_contract() -> int:
    source = UI_PATH.read_text(encoding="utf-8")
    header = HEADER_PATH.read_text(encoding="utf-8")
    checks = (
        '#include "ConnectionUiPolicy.h"',
        '#include "../ConnectionController.h"',
        'return "Подключение";',
        'smartui::companionModeName(_task->getCompanionStatus().selected)',
        'renderConnectionHeader(display, "Подключение", "Выбрать")',
        '"Связь разорвётся"',
        'if (!_connection_flow.confirmChange())',
        '_task->setCompanionMode(requested)',
        '"Настройте Wi-Fi через USB"',
        '"Разрешить доступ?"',
        'status.wifiClientIp',
        '"TCP: 5000 авто"',
        'smartui::connectionChangeErrorTitle(error)',
        'showAlert("Сервис: перезапуск", 5000)',
        'smartui::wifiApprovalSurfaceSafe(',
        '_settings_open, _page == HomePage::BLUETOOTH, _connection_flow.view()',
        '_popup_pending',
        '#if !SMARTUI_CONNECTION_SELECTOR\n  if (_ble_reenable_at != 0',
        'first_connection.selected == CompanionMode::BLE',
        'if (_interfaceManager != NULL) _interfaceManager->disable();',
        'SMARTUI_RELEASE_LABEL SMARTUI_VERSION',
    )
    for token in checks:
        assert token in source, f"missing production UI contract: {token}"
    for token in (
        "CompanionStatus getCompanionStatus() const;",
        "bool setCompanionMode(CompanionMode mode);",
        "bool resolveWifiClient(uint32_t request_id, bool approve);",
        "void connectionApprovalHandler();",
    ):
        assert token in header, f"missing UITask controller wrapper: {token}"

    block = source.split("int renderConnectionStatus", 1)[1].split("int renderConnectionPicker", 1)[0]
    assert "VBUS" not in block and "usbPower" not in block
    assert "status.clientConnected" in block and "status.connectedVia" in block
    confirm = source.split("bool handleConnectionInput", 1)[1].split("bool handleWifiApprovalInput", 1)[0]
    assert confirm.index("confirmChange()") < confirm.index("setCompanionMode(requested)")
    approval = source.split("void UITask::connectionApprovalHandler()", 1)[1].split(
        "void UITask::handlePendingPopupWake()", 1
    )[0]
    assert "clearWifiApproval()" in approval
    assert "syncWifiApproval(status)" not in approval
    assert "resolveWifiClient(" not in approval
    assert "turnOn()" not in approval
    print(f"PASS {len(checks) + 4 + 5} production UITask source contracts")
    return len(checks) + 9


def _extract_method_block(source: str, start_marker: str, end_marker: str) -> str:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end].rstrip()


def _text_ink_metrics(profile) -> tuple[int, int]:
    if profile.board in ("OLED", "Wireless Paper"):
        return 0, 7
    raw = profile.desired_font.raw
    glyph = raw.glyph("H")
    rows = []
    for row in range(glyph["height"]):
        if any(
            glyph["data"][row * glyph["row_bytes"] + col // 8] & (1 << (col & 7))
            for col in range(glyph["width"])
        ):
            rows.append(row)
    if not rows:
        return 0, profile.desired_font.logical_height
    # Generated glyphs contain the full padded line and use
    # yOffset=ascent-height, so the driver's ink top is the first set row.
    physical_top = rows[0]
    physical_height = rows[-1] - rows[0] + 1
    if profile.board == "T114":
        logical_top = int(physical_top / profile.scale_y)
        logical_height = int(physical_height / profile.scale_y + 0.999)
        return logical_top, max(1, logical_height)
    return physical_top, physical_height


def actual_connection_recordings(profiles):
    """Compile the production render methods against a recording DisplayDriver.

    The generated host runs the exact C++ geometry, strings, status branches,
    picker scrolling and safe-default choice rendering. Python only replays
    those recorded draw calls using the checked-in bitmap font pixels.
    """
    source = UI_PATH.read_text(encoding="utf-8")
    settings_header = _extract_method_block(
        source, "  void renderSettingsHeader(DisplayDriver& display", "\n  void renderCompactSettings"
    )
    renderers = _extract_method_block(
        source, "  void renderConnectionHeader(DisplayDriver& display", "\n  bool handleConnectionInput"
    )
    characters = set(
        " ?:-.|>0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
        "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
    )
    helper = "../../../examples/companion_radio/ui-new/ConnectionUiPolicy.h"
    code = f'''#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <map>
#include <string>
#include <vector>
#define UI_COMPACT_SETTINGS_MENU 1
#define UI_IDLE_REFRESH_MILLIS 1000
#include {json.dumps(helper)}

struct DrawOp {{
  char kind;
  char align;
  int x, y, w, h, color;
  std::string text;
}};

struct DisplayDriver {{
  enum {{ GREEN=1, LIGHT=2, YELLOW=3, DARK=4 }};
  int profile, viewport_w, viewport_h, line_h, ink_top, ink_h, color=LIGHT;
  const char* scene;
  std::map<uint32_t,int> advances;
  std::vector<DrawOp> ops;
  DisplayDriver(int p,const char* s,int w,int h,int lh,int it,int ih,const std::map<uint32_t,int>& a)
      : profile(p),viewport_w(w),viewport_h(h),line_h(lh),ink_top(it),ink_h(ih),scene(s),advances(a) {{}}
  int width() const {{ return viewport_w; }}
  int height() const {{ return viewport_h; }}
  int getTextLineHeight() const {{ return line_h; }}
  int getTextInkTop() const {{ return ink_top; }}
  int getTextInkHeight() const {{ return ink_h; }}
  void setBold(bool) {{}}
  void setColor(int value) {{ color=value; }}
  int getTextWidth(const char* text) const {{
    int result=0;
    const auto* p=reinterpret_cast<const unsigned char*>(text);
    while (*p) {{
      uint32_t cp=*p++;
      if ((cp&0xe0)==0xc0) {{ cp=(cp&0x1f)<<6; cp|=*p++&0x3f; }}
      else if ((cp&0xf0)==0xe0) {{ cp=(cp&0x0f)<<12; cp|=(*p++&0x3f)<<6; cp|=*p++&0x3f; }}
      else if ((cp&0xf8)==0xf0) {{ cp=(cp&7)<<18; cp|=(*p++&0x3f)<<12; cp|=(*p++&0x3f)<<6; cp|=*p++&0x3f; }}
      auto found=advances.find(cp);
      if (found==advances.end()) {{ std::cerr << "missing glyph " << cp << '\\n'; std::exit(3); }}
      result+=found->second;
    }}
    return result;
  }}
  void text(char align,int x,int y,int maximum,const char* value) {{
    ops.push_back({{'T',align,x,y,maximum,0,color,value}});
  }}
  void drawTextRightAlign(int x,int y,const char* value) {{ text('R',x,y,getTextWidth(value),value); }}
  void fillRect(int x,int y,int w,int h) {{ ops.push_back({{'F','-',x,y,w,h,color,""}}); }}
  void drawRect(int x,int y,int w,int h) {{ ops.push_back({{'O','-',x,y,w,h,color,""}}); }}
  void dump() const {{
    for (const auto& op:ops) {{
      std::cout << op.kind << '\\t' << profile << '\\t' << scene << '\\t' << op.align
                << '\\t' << op.x << '\\t' << op.y << '\\t' << op.w << '\\t' << op.h
                << '\\t' << op.color << '\\t' << op.text << '\\n';
    }}
  }}
}};
void drawRichTextStaticEllipsized(DisplayDriver& d,int x,int y,int maximum,const char* text) {{ d.text('L',x,y,maximum,text); }}
void drawRichTextCenteredEllipsized(DisplayDriver& d,int x,int y,int maximum,const char* text) {{ d.text('C',x,y,maximum,text); }}
uint8_t uiPushCompactSettingsFont(DisplayDriver&) {{ return 0; }}
void uiPopFont(DisplayDriver&,uint8_t) {{}}

struct TaskStub {{
  CompanionStatus value;
  ConnectionChangeError error=ConnectionChangeError::None;
  CompanionStatus getCompanionStatus() const {{ return value; }}
  ConnectionChangeError getCompanionChangeError() const {{ return error; }}
}};
struct RenderHost {{
  TaskStub* _task=nullptr;
  smartui::ConnectionUiFlow _connection_flow;
  smartui::WifiApprovalUiFlow _wifi_approval;
{settings_header}
{renderers}
}};

int main() {{
'''

    def metrics(profile):
        return ",".join(
            "{" + str(ord(char)) + "," + str(profile.desired_font.width(char)) + "}"
            for char in sorted(characters)
        )

    def emit_scene(index, profile, scene: str, wifi: bool, view: str) -> str:
        capabilities = "COMPANION_CAP_BLE|COMPANION_CAP_USB"
        if wifi:
            capabilities += "|COMPANION_CAP_WIFI"
        ink_top, ink_height = _text_ink_metrics(profile)
        setup = [
            f'DisplayDriver d({index},{json.dumps(scene)},{profile.logical_w},{profile.logical_h},'
            f'{profile.desired_font.logical_height},{ink_top},{ink_height},metric);',
            "CompanionStatus status{};",
            f"status.capabilities={capabilities};",
            "status.usbConsoleEnabled=true;",
            "TaskStub task; RenderHost host; host._task=&task;",
        ]
        if view == "status":
            if wifi:
                setup += [
                    "status.selected=CompanionMode::WiFi; status.clientConnected=true;",
                    "status.connectedVia=CompanionMode::WiFi; status.wifiConfigured=true;",
                    'status.wifiAssociated=true; std::strcpy(status.wifiLocalIp,"192.168.100.250");',
                ]
            setup += ["task.value=status;", "host.renderConnectionStatus(d,status);"]
        elif view == "picker":
            setup += ["task.value=status;", "host._connection_flow.openPicker(status);"]
            setup += ["host._connection_flow.movePicker(status,1);" for _ in range(3 if wifi else 2)]
            setup += ["host.renderConnectionPicker(d,status);"]
        elif view == "confirm":
            setup += ["task.value=status;", "host._connection_flow.openPicker(status);"]
            setup += ["host._connection_flow.movePicker(status,1);" for _ in range(2 if wifi else 1)]
            setup += ["host._connection_flow.selectPicker(status);", "host.renderConnectionConfirm(d,status);"]
        elif view.startswith("error_"):
            setup += [f"task.error=ConnectionChangeError::{view[6:]};",
                      "host.renderConnectionStatus(d,status);"]
        elif view == "approval":
            setup += [
                "status.wifiApprovalPending=true; status.wifiRequestId=41; status.wifiApprovalRemainingMs=30000;",
                'std::strcpy(status.wifiClientIp,"192.168.100.250"); task.value=status;',
                "host._wifi_approval.sync(status); host.renderWifiApproval(d);",
            ]
        setup.append("d.dump();")
        return "  { " + " ".join(setup) + " }\n"

    expected_scenes = {}
    for index, profile in enumerate(profiles):
        code += "  { std::map<uint32_t,int> metric={" + metrics(profile) + "};\n"
        scenarios = []
        if profile.board in ("T096", "T114", "OLED"):
            scenarios += [(f"{name}_nrf", False, name) for name in ("status", "picker", "confirm")]
        if profile.board in ("OLED", "Wireless Paper"):
            scenarios += [(f"{name}_wifi", True, name) for name in ("status", "picker", "confirm", "approval")]
        for error in ("NotStarted", "CliRescue", "StorageReadOnly", "Unavailable",
                      "StorageUnavailable", "TempCleanup", "Write", "VerifyTemp",
                      "Rotate", "Publish", "VerifyFinal", "Apply"):
            scenarios.append(("error_" + error, False, "error_" + error))
        expected_scenes[index] = [name for name, _, _ in scenarios]
        for scene, wifi, view in scenarios:
            code += emit_scene(index, profile, scene, wifi, view)
        code += "  }\n"
    code += "}\n"

    native = OUT / "connection_actual_cpp"
    native.mkdir(parents=True, exist_ok=True)
    cpp = native / "renderer.cpp"
    cpp.write_text(code, encoding="utf-8")
    if shutil.which("g++"):
        binary = native / "renderer"
        compile_command = ["g++", "-std=c++17", "-O1", "-Wall", "-Wextra", "-Werror",
                           str(cpp), "-o", str(binary)]
        run_command = [str(binary)]
        engine = "g++"
    else:
        linux = subprocess.check_output(
            ["wsl", "--exec", "wslpath", "-a", native.resolve().as_posix()], text=True
        ).strip()
        compile_command = ["wsl", "--exec", "g++", "-std=c++17", "-O1", "-Wall", "-Wextra",
                           "-Werror", linux + "/renderer.cpp", "-o", linux + "/renderer"]
        run_command = ["wsl", "--exec", linux + "/renderer"]
        engine = "WSL g++"
    subprocess.run(compile_command, check=True)
    output = subprocess.check_output(run_command, text=True, encoding="utf-8")
    recordings = {}
    for line in output.splitlines():
        kind, index, scene, align, x, y, w, h, color, text = line.split("\t", 9)
        key = (int(index), scene)
        recordings.setdefault(key, []).append(
            (kind, align, int(x), int(y), int(w), int(h), int(color), text)
        )
    for index, scenes in expected_scenes.items():
        for scene in scenes:
            assert (index, scene) in recordings, f"production renderer emitted no operations: {index}/{scene}"
    report = {
        "sha256": hashlib.sha256((settings_header + renderers).encode()).hexdigest(),
        "engine": engine,
        "scenes": sum(len(value) for value in expected_scenes.values()),
        "scope": "extracted production C++ render methods + recording DisplayDriver + real bitmap metrics",
    }
    (native / "REPORT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return recordings, report


def replay(profile, operations, name: str):
    frame = settings.SettingsFrame(profile, name, True)
    colors = {1: "green", 2: "light", 3: "yellow", 4: "dark"}
    selected_box = None
    for ordinal, (kind, align, x, y, w, h, color, text) in enumerate(operations):
        tag = f"actual {ordinal}"
        if kind in ("F", "O"):
            frame.rect(x, y, w, h, colors[color], outline=kind == "O", tag=tag)
            if kind == "F" and color in (1, 3):
                selected_box = (x, y, w, h)
            continue
        shown = frame.text(
            x, y, text, colors[color], center=align == "C", right=align == "R",
            max_w=w, tag=tag,
        )
        assert shown == text, (profile.board, profile.profile, name, text, shown)
        if color == 4 and selected_box is not None:
            frame.assert_element_inside(tag, selected_box)
            ink = frame.elements[-1].physical_box
            fill = frame.logical_box_to_physical(*selected_box)
            assert ink is not None and ink[1] > fill[1], (
                profile.board, profile.profile, name, "selected ink touches highlight edge"
            )
    assert not frame.violations, f"{profile.board}/{profile.profile}/{name}: {frame.violations}"
    return frame


def geometry_and_previews() -> int:
    all_profiles = settings.profiles()
    recordings, report = actual_connection_recordings(all_profiles)
    frames = {
        key: replay(all_profiles[key[0]], operations, key[1])
        for key, operations in recordings.items()
    }
    checks = len(frames)

    by_board = {
        "T096": (all_profiles.index(next(p for p in all_profiles if p.board == "T096" and p.profile == "Noto")), "nrf"),
        "T114": (all_profiles.index(next(p for p in all_profiles if p.board == "T114")), "nrf"),
        "V3": (all_profiles.index(next(p for p in all_profiles if p.board == "OLED" and p.profile == "Classic")), "wifi"),
        "V4": (all_profiles.index(next(p for p in all_profiles if p.board == "OLED" and p.profile == "Air")), "wifi"),
        "ProMicro": (all_profiles.index(next(p for p in all_profiles if p.board == "OLED" and p.profile == "Strong")), "nrf"),
        "Paper": (all_profiles.index(next(p for p in all_profiles if p.board == "Wireless Paper")), "wifi"),
    }
    # Keep the documentation preview small: one real status surface per board,
    # plus one representative picker, confirmation and Wi-Fi approval. The
    # hidden geometry sweep above still executes every applicable font/mode.
    scenes = []
    for board, (index, capability) in by_board.items():
        scenes.append((f"{board}: статус", frames[(index, f"status_{capability}")]))
    t114_index, _ = by_board["T114"]
    t096_index, _ = by_board["T096"]
    v4_index, _ = by_board["V4"]
    scenes.extend([
        ("T114: выбор", frames[(t114_index, "picker_nrf")]),
        ("T096: подтверждение", frames[(t096_index, "confirm_nrf")]),
        ("V4: причина отказа", frames[(v4_index, "error_CliRescue")]),
    ])
    preview = OUT / "CONNECTION_UI_ALL_SIX.png"
    settings.make_matrix(scenes, preview, columns=3)
    print(f"PASS {checks} source-backed exact-font renderer scenes ({report['engine']}); preview {preview}")
    return checks


def ble_pin_rendering() -> int:
    """Execute the real PIN renderer and font-role helpers for every release board.

    Reachability/lifecycle belong to test_ble_pin_page.py. Here only recorded
    production draw calls are painted, using committed glyph bytes and the
    drivers' pixel scale/weight rules; no Python copy of the page layout exists.
    """
    from PIL import Image, ImageDraw
    from embedded_bitmap_fonts import EmbeddedRaw
    from simulate_oled_128x64 import STYLES, glyph_for
    from simulate_wireless_paper_ps17_qa import PROFILES as PAPER_FONTS
    from test_ble_pin_page import production_defines, resolved_profiles
    from test_ui_sessions_v006 import function, run_cpp

    source = UI_PATH.read_text(encoding="utf-8")
    roles = _extract_method_block(source, "static const uint8_t UI_OLED_FONT_M",
                                  "\nstatic void drawOledCompactMenuPage")
    renderer = function(source, "static int renderBlePinPage(")
    t114_source = (ROOT / "src/helpers/ui/ST7789Display.cpp").read_text(encoding="utf-8")
    t114_table = t114_source.split("ST7789_FONT_PROFILES[] = {", 1)[1].split("};", 1)[0]
    t114_fonts = [(int(body), int(clock), name) for body, clock, name in
                  re.findall(r'\{(\d+),\s*(\d+),\s*"([^"]+)"\}', t114_table)]
    assert len(t114_fonts) == 10
    profiles = resolved_profiles()
    assert len(profiles) == 7 and len({env for env, _ in profiles}) == 7
    native = OUT / "ble-pin-actual-cpp"
    native.mkdir(parents=True, exist_ok=True)
    records, preview_rows = [], []

    @lru_cache(maxsize=None)
    def raw_font(kind, index):
        return EmbeddedRaw("meshcore_st7789_font" if kind == "T114" else "meshcore_font",
                           "meshcoreSt7789Fonts" if kind == "T114" else "meshcoreSmallFonts", index)

    def pixels(kind, font, size, bold, cx, y, text):
        # Match driver widths before positioning centred text. T114 converts
        # each glyph advance to logical coordinates, then paints physical ink.
        if kind in ("T096", "T114"):
            index = t114_fonts[font][int(size > 1)] if kind == "T114" else font
            raw = raw_font(kind, index)
            scale = 1 if kind == "T114" else size
            extra = int(bold and size == 1)
            advances = [raw.glyph(ch)["x_advance"] * scale + extra for ch in text]
            width = sum(int(advance / 1.875 + .999) for advance in advances) if kind == "T114" else sum(advances)
            x = cx - width // 2
            if kind == "T114":
                x, y = int(x * 1.875), int(y * 2.109375) + 1
            points = set()
            for ch, advance in zip(text, advances):
                glyph = raw.glyph(ch)
                for row in range(glyph["height"]):
                    for col in range(glyph["width"]):
                        if glyph["data"][row * glyph["row_bytes"] + col // 8] & (1 << (col & 7)):
                            for dy in range(scale):
                                for dx in range(scale + extra):
                                    points.add((x + (glyph["x_offset"] + col) * scale + dx,
                                                y + row * scale + dy))
                x += advance
            return points
        if kind == "Paper":
            advance, _gap, weight, fixed = list(PAPER_FONTS.values())[font]
            weight = int(bold or weight)
            widths = [(advance if ch != " " or fixed else 4) * size + weight for ch in text]
        else:
            _name, advance, style_bold = STYLES[font]
            weight = int((bold or style_bold) and size == 1)
            if weight and advance < 6:
                advance = 6
            if weight and advance < 7 and font != 4:
                advance = 7
            widths = [advance * size] * len(text)
        x = cx - sum(widths) // 2
        points = set()
        for ch, advance in zip(text, widths):
            if ch != " ":
                for col, bits in enumerate(glyph_for(ch)):
                    for row in range(8):
                        if bits & (1 << row):
                            for dy in range(size):
                                for dx in range(size + weight):
                                    points.add((x + col * size + dx, y + row * size + dy))
            x += advance
        return points

    for board_index, (env, flags) in enumerate(profiles):
        if "t096" in env:
            kind, dimensions, fonts, count = "T096", (160, 80, 160, 80), range(5, 20), 20
        elif "t114" in env:
            kind, dimensions, fonts, count = "T114", (128, 64, 240, 135), range(10), 10
        elif "Paper" in env:
            kind, dimensions, fonts, count = "Paper", (250, 122, 250, 122), range(5), 5
        else:
            kind, dimensions, fonts, count = "OLED", (128, 64, 128, 64), range(5), 5
        w, h, physical_w, physical_h = dimensions
        code = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <initializer_list>
''' + production_defines(source, flags) + f'''
struct DisplayDriver {{
  enum {{ GREEN=1, LIGHT=2, YELLOW=3 }};
  int font, size=1, color=LIGHT; bool bold=false;
  int initial, scene;
  int width() const {{return {w};}}
  int height() const {{return {h};}}
  uint8_t getUiFont() const {{return font;}}
  uint8_t getUiFontCount() const {{return {count};}}
  void setUiFont(uint8_t value) {{assert(value<getUiFontCount());font=value;}}
  void setTextSize(int value) {{size=value;}}
  void setBold(bool value) {{bold=value;}}
  void setColor(int value) {{color=value;}}
}};
void drawRichTextCentered(DisplayDriver& d,int x,int y,const char* text) {{
  std::cout<<d.initial<<'\\t'<<d.scene<<'\\t'<<d.font<<'\\t'<<d.size<<'\\t'
           <<d.bold<<'\\t'<<x<<'\\t'<<y<<'\\t'<<d.color<<'\\t'<<text<<'\\n';
}}
''' + roles + "\n" + renderer + "\nint main(){\n"
        for font in fonts:
            # Include zero's defensive placeholder, leading zeroes, and the
            # valid six-digit extremes. Every connection/enabled combination
            # is executed, including stale connected=true while BLE is off.
            for pin_index, pin in enumerate((0, 1, 100000, 428731, 999999)):
                for enabled in (False, True):
                    for connected in (False, True):
                        scene = pin_index * 4 + int(enabled) * 2 + int(connected)
                        code += (f'{{DisplayDriver d{{{font},1,2,false,{font},{scene}}};'
                                 f'int refresh=renderBlePinPage(d,{pin},{str(connected).lower()},'
                                 f'{str(enabled).lower()});assert(refresh>0);'
                                 f'assert(d.font=={font});}}\n')
        code += "}\n"
        output = run_cpp(code, native, f"ble_pin_{board_index}")
        scenes = {}
        for line in output.splitlines():
            initial, scene, font, size, bold, x, y, color, text = line.split("\t", 8)
            key = int(initial), int(scene)
            scenes.setdefault(key, []).append((int(font), int(size), bool(int(bold)),
                                               int(x), int(y), int(color), text))
        assert len(scenes) == len(fonts) * 20, (env, "missing renderer scene")
        picked, font_frames = [], {}
        for (initial, scene), ops in scenes.items():
            pin = (0, 1, 100000, 428731, 999999)[scene // 4]
            enabled, connected = bool(scene & 2), bool(scene & 1)
            texts = [op[-1] for op in ops]
            expected = ["ПИНКОД BLE", f"{pin:06d}" if pin else "------"]
            if kind == "Paper":
                expected += (["BLUETOOTH ВЫКЛ", "НАСТРОЙКИ > СИСТЕМА", "ПОДКЛЮЧЕНИЕ > BLE"]
                             if not enabled else ["BLE ПОДКЛЮЧЕН"] if connected else
                             ["ОТКРОЙТЕ MESHCORE", "УСТРОЙСТВА > ДОБАВИТЬ", "PIN / PASSKEY: ЭТИ 6 ЦИФР"])
            else:
                expected += ["Включите BLE" if not enabled else "BLE подключен" if connected else "код в приложении"]
            assert texts == expected, (env, initial, scene, texts, expected)
            image = Image.new("RGB", (physical_w, physical_h), "white" if kind == "Paper" else "black")
            draw = ImageDraw.Draw(image)
            boxes = []
            for font, size, bold, x, y, color, text in ops:
                ink = pixels(kind, font, size, bold, x, y, text)
                assert ink, (env, initial, scene, "missing glyph ink", text)
                box = (min(p[0] for p in ink), min(p[1] for p in ink),
                       max(p[0] for p in ink) + 1, max(p[1] for p in ink) + 1)
                assert 0 <= box[0] < box[2] <= physical_w and 0 <= box[1] < box[3] <= physical_h, (env, initial, scene, text, box)
                # Header/page-indicator chrome ends at physical logical y=16.
                chrome_end = int(16 * 2.109375) + 1 if kind == "T114" else 16
                assert box[1] >= chrome_end, (env, initial, scene, "chrome collision", text, box)
                for other in boxes:
                    assert box[2] <= other[0] or other[2] <= box[0] or box[3] <= other[1] or other[3] <= box[1], (env, initial, scene, "overlapping rows", box, other)
                boxes.append(box)
                # SSD1306 and the ST7789 driver's one-bit framebuffer collapse
                # semantic colours to foreground; only T096 paints RGB roles.
                paint = ("black" if kind == "Paper" else "white" if kind in ("OLED", "T114")
                         else {1: "#1df07a", 2: "#f4faf8", 3: "#ffe04a"}[color])
                for point in ink:
                    draw.point(point, fill=paint)
            records.append(dict(environment=env, font=initial, scene=scene, texts=texts, ink_boxes=boxes))
            if scene in (12, 14, 15):
                font_frames.setdefault(initial, []).append((scene, image))
                if initial == (10 if kind == "T096" else 0):
                    picked.append((scene, image))
        styles = Image.new("RGB", (3 * 520, len(fonts) * 290), "#20242b")
        style_draw = ImageDraw.Draw(styles)
        for row, (initial, frames) in enumerate(sorted(font_frames.items())):
            style_draw.text((8, row * 290 + 4), f"{env} font={initial}: BLE off / waiting / connected", fill="white")
            for column, (_scene, frame) in enumerate(sorted(frames)):
                frame = frame.resize((frame.width * 2, frame.height * 2), Image.Resampling.NEAREST)
                styles.paste(frame, (column * 520 + 8, row * 290 + 20))
        styles.save(native / f"BLE_PIN_{board_index}_ALL_FONTS.png")
        preview_rows.append((env, sorted(picked)))

    # Seven separate board rows prevent aliases such as generic "OLED" from
    # silently dropping V3, V4.3, R8, or ProMicro coverage.
    sheet = Image.new("RGB", (3 * 520, 7 * 290), "#20242b")
    draw = ImageDraw.Draw(sheet)
    for row, (env, scenes) in enumerate(preview_rows):
        draw.text((8, row * 290 + 4), env, fill="white")
        for column, (scene, frame) in enumerate(scenes):
            frame = frame.resize((frame.width * 2, frame.height * 2), Image.Resampling.NEAREST)
            sheet.paste(frame, (column * 520 + 8, row * 290 + 20))
    sheet.save(OUT / "BLE_PIN_ALL_SEVEN.png")
    report = dict(boards=7, scenes=len(records), font_profiles=sum(len({r['font'] for r in records if r['environment']==env}) for env, _ in profiles),
                  renderer_sha256=hashlib.sha256((roles + renderer).encode()).hexdigest(),
                  scope="production C++ renderer/font roles, resolved release macros, committed bitmap pixels; no hardware execution",
                  records=records)
    (native / "REPORT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS {len(records)} production BLE PIN framebuffer scenes across all seven boards")
    return len(records)


def main():
    total = compile_policy() + source_contract() + geometry_and_previews() + ble_pin_rendering()
    print(f"PASS {total} SmartUI connection UI checks")


if __name__ == "__main__":
    main()
