"""Exercise the production quiet-status renderer with measured font widths.

Tests placement/selection, not physical display electronics or icon recognition.
The separate icon renderer checks the actual pixels used by the fallback.
"""
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "qa_outputs/quiet-status"


def main():
    from generate_docs_assets import make_t096_clock_profiles, make_t114_active_profiles
    from simulate_oled_128x64 import Oled, STYLES
    from simulate_smartui_ps17_qa import Frame

    widths = {Frame(profile, "quiet status", profile.board == "T096").font.width("ТИХО")
              for profile in [*make_t096_clock_profiles(), *make_t114_active_profiles()]}
    widths.update(Oled(style).text_width("ТИХО") for style in STYLES)
    source = (ROOT / "examples/companion_radio/ui-new/UITask.cpp").read_text(encoding="utf-8")
    start = source.index("static int drawUiQuietStatus(")
    body = source[start:source.index("\n}", start) + 2]
    code = r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <initializer_list>
using uint8_t = unsigned char;
static const uint8_t muted_icon[] = {0};
struct DisplayDriver {
  int text_width, icon_size, calls=0, x=-1, width=0;
  bool text=false;
  int getTextWidth(const char* label) { assert(!strcmp(label,"ТИХО")); return text_width; }
  void drawTextLeftAlign(int xx,int,const char* label) {
    assert(!strcmp(label,"ТИХО")); ++calls; x=xx; width=text_width; text=true;
  }
};
static int uiStatusIconSize(DisplayDriver& d) { return d.icon_size; }
static int uiTextAlignedIconY(DisplayDriver&,int y,int) { return y; }
static void drawUiIcon(DisplayDriver& d,int x,int,const uint8_t* icon,int size) {
  assert(icon==muted_icon); ++d.calls; d.x=x; d.width=size;
}
'''
    code += body + r'''
int main() {
  unsigned checks=0;
  for(int label_width : {WIDTHS}) for(int icon_size : {8,9,10,11,12,16})
    for(int available=-2; available<=100; ++available) {
      DisplayDriver d{label_width,icon_size};
      int used=drawUiQuietStatus(d,7,0,available);
      assert(used>=0);
      if(available<8) { assert(!d.calls && !used); }
      else {
        assert(d.calls==1 && d.x==7 && used==d.width && used<=available);
        assert(d.text==(label_width<=available));
        if(!d.text) assert(used==(icon_size<=available ? icon_size : 8));
      }
      ++checks;
    }
  printf("PASS %u actual C++ quiet-status placement cases\n",checks);
}
'''.replace("WIDTHS", ",".join(map(str, sorted(widths))))
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
