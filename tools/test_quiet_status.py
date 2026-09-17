"""Exercise the production icon-only mute renderer with real font metrics.

Tests placement/selection, not physical display electronics or icon recognition.
The separate icon renderer checks the actual pixels. The C++ display stub has
no text drawing API: reintroducing a text label fails compilation.
"""
from pathlib import Path
import math
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "qa_outputs/quiet-status"


def main():
    from generate_docs_assets import make_t096_clock_profiles, make_t114_active_profiles
    from simulate_smartui_ps17_qa import Frame
    from generate_docs_assets import glyph_ink_bounds

    metrics = {(8, 0, 7)}  # SSD1306 profiles share vertical ink metrics.
    for profile in [*make_t096_clock_profiles(), *make_t114_active_profiles()]:
        frame = Frame(profile, "mute icon", profile.board == "T096")
        ink = glyph_ink_bounds(frame.font.raw.glyph("H"))
        metrics.add((frame.font.logical_height, int(ink[1] / frame.board.scale_y),
                     math.ceil((ink[3] - ink[1]) / frame.board.scale_y)))
    source = (ROOT / "examples/companion_radio/ui-new/UITask.cpp").read_text(encoding="utf-8")
    assert '"тихо"' not in source.lower(), "Text mute status returned to firmware"
    start = source.index("static int drawUiMuteStatusIcon(")
    body = source[start:source.index("\n}", start) + 2]
    start = source.index("static int uiTextAlignedIconY(")
    alignment = source[start:source.index("\n}", start) + 2]
    code = r'''
#include <cassert>
#include <cstdio>
#include <initializer_list>
using uint8_t = unsigned char;
static const uint8_t muted_icon[] = {0};
struct DisplayDriver {
  int line_height, ink_top, ink_height, icon_size, calls=0, x=-1, y=-1, width=0;
  int getTextLineHeight() { return line_height; }
  int getTextInkTop() { return ink_top; }
  int getTextInkHeight() { return ink_height; }
};
static int uiStatusIconSize(DisplayDriver& d) { return d.icon_size; }
static void drawUiIcon(DisplayDriver& d,int x,int y,const uint8_t* icon,int size) {
  assert(icon==muted_icon); ++d.calls; d.x=x; d.y=y; d.width=size;
}
'''
    code += alignment + "\n" + body + r'''
int main() {
  unsigned checks=0;
  const int metrics[][3] = {METRICS};
  for(const auto& font : metrics) for(int icon_size : {8,9,10,11,12,16})
    for(int available=-2; available<=100; ++available) {
      DisplayDriver d{font[0],font[1],font[2],icon_size};
      int used=drawUiMuteStatusIcon(d,7,2,available);
      assert(used>=0);
      if(available<8) { assert(!d.calls && !used); }
      else {
        assert(d.calls==1 && d.x==7 && used==d.width && used<=available);
        assert(used==(icon_size<=available ? icon_size : 8));
        assert(d.y>=2);
        assert(d.y+used<=2+(font[0]>used ? font[0] : used));
      }
      ++checks;
    }
  printf("PASS %u actual C++ icon-only mute placement cases\n",checks);
}
'''.replace("METRICS", ",".join("{"+",".join(map(str,m))+"}" for m in sorted(metrics)))
    OUT.mkdir(parents=True, exist_ok=True)
    cpp = OUT / "quiet.cpp"
    cpp.write_text(code, encoding="utf-8")
    if shutil.which("g++"):
        binary = OUT / "quiet"
        subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", str(cpp), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
    else:
        folder = subprocess.check_output(["wsl", "--exec", "wslpath", "-a", OUT.as_posix()]).decode().strip()
        subprocess.run(["wsl", "--exec", "g++", "-std=c++17", "-Wall", "-Wextra", folder+"/quiet.cpp", "-o", folder+"/quiet"], check=True)
        subprocess.run(["wsl", "--exec", folder+"/quiet"], check=True)


if __name__ == "__main__":
    main()
