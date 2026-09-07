#!/usr/bin/env python3
"""Run the actual C++ icon helpers, with pixel recording instead of hardware.

Unlike design previews this compiles drawUiIcon from UITask.cpp verbatim.
The baseline is the beta.1 tag; only a host compiler and Pillow are needed.
T114 uses rectangle-boundary mapping, including Y_OFFSET=1. Labels outside
the frame are illustrative, never used as replacement firmware fonts.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from functools import lru_cache
from pathlib import Path
import shutil
import subprocess

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
UI = "examples/companion_radio/ui-new/"
BASE = "v2.1.0-beta.1"


@lru_cache(maxsize=256)
def firmware_icon_rects(symbol: str, size: int) -> tuple[tuple[int, int, int, int], ...]:
    """Source-backed fast replay, verified pixel-for-pixel against C++ below."""
    import simulate_iconpack_v1 as pack
    kind = next(kind for kind,names in pack.FIRMWARE_ICON_MAP if symbol in names)
    if symbol == "satellite_icon":
        raise ValueError("GPS has a text+wave badge; use the GPS badge renderer")
    grid = 8 if size < 12 else 12
    name = f"iconpack_v2_small_{kind}" if size < 12 else f"iconpack_v1_{kind}"
    header = (ROOT / UI / "iconpack_v1.h").read_text(encoding="utf-8")
    match = re.search(rf"{name}\[\d+\] PROGMEM = \{{(.*?)\}};",header,re.S)
    assert match, name
    rows = [int(v,16) for v in re.findall(r"0x[0-9a-fA-F]+",match.group(1))]
    rects=[]
    for y in range(size):
        sy=min(grid-1,((y*2+1)*grid)//(size*2))
        start=-1
        for x in range(size+1):
            sx=min(grid-1,((x*2+1)*grid)//(size*2))
            on=x<size and bool(rows[sy] & (1<<(grid-1-sx)))
            if on and start<0: start=x
            if not on and start>=0:
                rects.append((start,y,x-start,1)); start=-1
    return tuple(rects)


def draw_frame_icon(frame, x: int, y: int, symbol: str, size: int,
                    color: str = "light") -> None:
    if frame.board.board == "T114" and size == 8:
        # Identity-size fitted XBM deliberately takes the driver's fast path:
        # origin is rounded once, then each bitmap row/column is rounded.
        # This is not the same fractional phase as fillRect(x+dx,y+dy).
        frame.check_logical_box(f"icon:{symbol}",x,y,size,size)
        x0=frame.boundary_x(x); y0=frame.boundary_y(y)
        for dx,dy,w,h in firmware_icon_rects(symbol,size):
            for col in range(dx,dx+w):
                x1=x0+int(col*frame.board.scale_x)
                x2=x0+int((col+1)*frame.board.scale_x)
                y1=y0+int(dy*frame.board.scale_y)
                y2=y0+int((dy+1)*frame.board.scale_y)
                frame.draw.rectangle((x1,y1,x2-1,y2-1),fill=frame.color(color))
        return
    # Frame.rect applies ST7789 scale to absolute boundaries. Scaling a
    # completed icon mask would lose fractional phase at x/y != 0.
    for dx,dy,w,h in firmware_icon_rects(symbol,size):
        frame.rect(x+dx,y+dy,w,h,color,tag=f"icon:{symbol}")


def audit_ink_metrics(out):
    """Compile the shared firmware helper against every embedded font."""
    folder=out/"metrics_host"; folder.mkdir(parents=True,exist_ok=True)
    code=r'''
#include <stdio.h>
#define ST7789
#include "BitmapTextMetrics.h"
int main() {
 for(int table=0;table<2;++table) {
  int count=table?MESHCORE_ST7789_FONT_COUNT:MESHCORE_SMALL_FONT_COUNT;
  for(int i=0;i<count;++i) {
   auto f=table?meshcoreGetSt7789Font(i):meshcoreGetSmallFont(i);
   auto m=meshcoreBitmapCapitalInk(f);
   printf("%d %d %d %d\n",table,i,m.top,m.height);
  }
 }
}
'''
    path=folder/"metrics.cpp"; path.write_text(code,encoding="utf-8")
    if shutil.which("g++"):
        binary=folder/"metrics"
        subprocess.run(["g++","-std=c++17","-Os","-I",str(ROOT/"src/helpers/ui"),str(path),"-o",str(binary)],check=True)
        data=subprocess.check_output([str(binary)]).decode()
    else:
        linux=subprocess.check_output(["wsl","--exec","wslpath","-a",folder.as_posix()]).decode().strip()
        include=subprocess.check_output(["wsl","--exec","wslpath","-a",(ROOT/"src/helpers/ui").as_posix()]).decode().strip()
        subprocess.run(["wsl","--exec","g++","-std=c++17","-Os","-I",include,linux+"/metrics.cpp","-o",linux+"/metrics"],check=True)
        data=subprocess.check_output(["wsl","--exec",linux+"/metrics"]).decode()
    from embedded_bitmap_fonts import EmbeddedRaw
    from simulate_smartui_ps17_qa import glyph_ink_bounds, T096ExactFont, T114ExactFont
    checks=0; rows=[]
    for entry in data.splitlines():
        table,index,top,height=map(int,entry.split())
        raw=EmbeddedRaw("meshcore_st7789_font" if table else "meshcore_font",
                        "meshcoreSt7789Fonts" if table else "meshcoreSmallFonts",index)
        ink=glyph_ink_bounds(raw.glyph("H"))
        assert ink and (top,height)==(ink[1],ink[3]-ink[1]), (table,index,top,height,ink)
        checks+=1
        for size in (8,10,13,16,24):
            scale=2.109375 if table else 1
            line_h=math.ceil(raw.height/scale); ink_top=int(top/scale); ink_h=math.ceil(height/scale)
            before=max(0,int((line_h-size)/2))
            after=max(0,min(max(0,line_h-size),ink_top+int((ink_h-size)/2)))
            assert after>=0 and after+size<=max(line_h,size)
            checks+=1
        if (not table and index in (0,5,10,15)) or (table and index in (0,5,11)):
            rows.append((f"{'T114' if table else 'T096'} / font {index}",table,raw,top,height))
    label_font=ImageFont.truetype(str(ROOT/"tools/font_sources/noto_sans_2_015/NotoSans-CondensedMedium.ttf"),18)
    sheet=Image.new("RGB",(1080,65+len(rows)*130),"#111c23"); d=ImageDraw.Draw(sheet)
    d.text((12,8),"Выравнивание с реальным bitmap ink H (не glyph.height)",font=label_font,fill="white")
    d.text((235,35),"До / центр строки",font=label_font,fill="#90dae4")
    d.text((660,35),"После / центр видимого текста",font=label_font,fill="#90dae4")
    for r,(label,table,raw,top,height) in enumerate(rows):
        sy=2.109375 if table else 1; sx=1.875 if table else 1; offset=1 if table else 0
        line_h=math.ceil(raw.height/sy); icon_h=10 if table else 13
        dy_old=max(0,int((line_h-icon_h)/2))
        dy_new=max(0,min(max(0,line_h-icon_h),int(top/sy)+int((math.ceil(height/sy)-icon_h)/2)))
        font=T114ExactFont(label,raw) if table else T096ExactFont(label,raw)
        d.text((12,78+r*130),label,font=label_font,fill="white")
        for col,dy in enumerate((dy_old,dy_new)):
            im=Image.new("RGB",(240 if table else 160,max(36,raw.height+6)),"#111c23")
            font.draw(im,20,2,"Сеть 4.09V",(230,245,235))
            draw=ImageDraw.Draw(im)
            for x,y,w,h in firmware_icon_rects("muted_icon",icon_h):
                x1=int((x+2)*sx); x2=int((x+2+w)*sx)
                y1=int((y+2+dy)*sy)+offset; y2=int((y+2+dy+h)*sy)+offset
                draw.rectangle((x1,y1,x2-1,y2-1),fill="#ffaf90")
            zoom=1 if table else 2
            im=im.resize((im.width*zoom,im.height*zoom),Image.Resampling.NEAREST)
            sheet.paste(im,(230+col*425,68+r*130))
            d.text((230+col*425,158+r*130),f"icon offset {dy}px; cap {top}..{top+height}",font=label_font,fill="#90dae4")
    sheet.save(out/"TEXT_ICON_INK_ALIGNMENT.png")
    return checks


def source(path, baseline=False):
    if baseline:
        return subprocess.check_output(["git", "show", f"{BASE}:{path}"], cwd=ROOT).decode("utf-8")
    return (ROOT / path).read_text(encoding="utf-8")


def run_host(out, baseline=False):
    folder = out / ("baseline_host" if baseline else "current_host")
    folder.mkdir(parents=True, exist_ok=True)
    cpp = source(UI + "UITask.cpp", baseline)
    helpers = cpp[cpp.index("static void drawUiXbmScaled("):cpp.index("static ColorVal uiGpsStatusColor(")]
    for name in ("icons.h", "iconpack_v1.h"):
        (folder / name).write_text(source(UI + name, baseline), encoding="utf-8")
    # Every mapped emoji plus the two route fallbacks, not just showcase icons.
    import simulate_iconpack_v1 as pack
    symbols = sorted({s for _, names in pack.FIRMWARE_ICON_MAP for s in names} |
                     {"tower_route_icon", "relay_status_icon", "relay_packet_icon"})
    cases = ",\n".join('{"' + name + '",' + name + '}' for name in symbols)
    preamble = r'''
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <vector>
#define PROGMEM
#define pgm_read_byte(p) (*(const uint8_t*)(p))
#define pgm_read_word(p) (*(const uint16_t*)(p))
struct Rect {int x,y,w,h;};
class DisplayDriver {
public:
 std::vector<Rect> rects;
 void fillRect(int x,int y,int w,int h) {if(w>0 && h>0) rects.push_back({x,y,w,h});}
 void drawRect(int x,int y,int w,int h) {
   fillRect(x,y,w,1); fillRect(x,y+h-1,w,1);
   fillRect(x,y,1,h); fillRect(x+w-1,y,1,h);
 }
 void drawXbm(int x,int y,const uint8_t* bits,int w,int h) {
   for(int j=0;j<h;j++) for(int i=0;i<w;i++)
     if(bits[j*((w+7)/8)+i/8] & (0x80>>(i&7))) fillRect(x+i,y+j,1,1);
 }
};
#include "icons.h"
'''
    tail = r'''
struct Item {const char* name; const uint8_t* icon;};
Item items[] = {CASES};
int main() {
 bool first=true; puts("[");
 for (const auto& item: items) for(int size: {8,9,10,11,12,16,24}) {
   DisplayDriver d; drawUiIcon(d,0,0,item.icon,size);
   printf("%s{\"name\":\"%s\",\"size\":%d,\"rects\":[",first?"":",",item.name,size);
   first=false; bool rfirst=true;
   for(const auto&r:d.rects) {
     printf("%s[%d,%d,%d,%d]",rfirst?"":",",r.x,r.y,r.w,r.h); rfirst=false;
   }
   puts("]}");
 }
 puts("]");
}
'''.replace("CASES", cases)
    path = folder / "icon_host.cpp"
    path.write_text(preamble + helpers + tail, encoding="utf-8")
    result = {}
    for mode in (0, 1):
        binary = folder / f"icons_{mode}"
        flags = ["-std=c++17", "-Os", f"-DUI_T096_PREMIUM_TFT={mode}"]
        if shutil.which("g++"):
            subprocess.run(["g++", *flags, str(path), "-o", str(binary)], check=True)
            raw = subprocess.check_output([str(binary)])
        else:
            linux = subprocess.check_output(["wsl", "--exec", "wslpath", "-a", folder.as_posix()]).decode().strip()
            subprocess.run(["wsl", "--exec", "g++", *flags, linux + "/icon_host.cpp", "-o", linux + f"/icons_{mode}"], check=True)
            raw = subprocess.check_output(["wsl", "--exec", linux + f"/icons_{mode}"])
        result[mode] = {(r["name"], r["size"]): r["rects"] for r in json.loads(raw)}
    return result


def raster(rects, size, t114=False):
    width = max(size, max((x+w for x,y,w,h in rects), default=size))
    scale_x, scale_y, offset = (1.875, 2.109375, 1) if t114 else (1, 1, 0)
    im = Image.new("1", (int(width*scale_x), int(size*scale_y)+offset), 0)
    d = ImageDraw.Draw(im)
    for x,y,w,h in rects:
        x1,x2 = int(x*scale_x), int((x+w)*scale_x)
        y1,y2 = int(y*scale_y)+offset, int((y+h)*scale_y)+offset
        if x2>x1 and y2>y1:
            d.rectangle((x1,y1,x2-1,y2-1), fill=1)
    return im


def contact_sheet(out, before, after):
    selected = [
        ("Дом", "emoji_home_icon"), ("Офис", "emoji_building_icon"),
        ("Завод", "emoji_factory_icon"), ("Геометка", "emoji_location_icon"),
        ("Пейджер", "emoji_pager_icon"), ("Звук", "emoji_sound_icon"),
        ("Без звука", "muted_icon"), ("Внимание", "emoji_warn_icon"),
        ("Сообщение", "emoji_msg_icon"), ("Письмо", "emoji_mail_icon"),
        ("Заметка", "emoji_note_icon"), ("Готово", "emoji_check_icon"),
        ("Улыбка", "emoji_smile_icon"), ("Зарядка", "emoji_plug_icon"),
    ]
    font = ImageFont.truetype(str(ROOT / "tools/font_sources/noto_sans_2_015/NotoSans-CondensedMedium.ttf"), 18)
    columns = [("Mono до",before,0,8,False), ("Mono после",after,0,8,False),
               ("T114 после",after,1,9,True), ("T096 после",after,1,16,False)]
    image = Image.new("RGB", (960, 72+len(selected)*75), "#111c23")
    d = ImageDraw.Draw(image)
    d.text((12,10), "БЕТА 2 — фактический C++ drawUiIcon, пиксельный рендер", font=font, fill="white")
    for col,(label,*_) in enumerate(columns):
        d.text((190+col*185,42),label,font=font,fill="#90dae4")
    for row,(label,symbol) in enumerate(selected):
        y=72+row*75
        d.line((0,y,960,y),fill="#293a43")
        d.text((12,y+20),label,font=font,fill="white")
        for col,(_,data,mode,size,t114) in enumerate(columns):
            mask=raster(data[mode][(symbol,size)],size,t114)
            scale=min(6,58//max(mask.size))
            mask=mask.resize((mask.width*scale,mask.height*scale),Image.Resampling.NEAREST)
            tile=Image.new("RGB",mask.size,"#111c23")
            tile.paste("#dcf5e9",mask=mask)
            image.paste(tile,(215+col*185,y+(75-mask.height)//2))
    image.save(out / "ICON_BEFORE_AFTER_ALL_BOARDS.png")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,default=ROOT/"qa_outputs"/"icon_alignment_beta2")
    args=parser.parse_args(); out=args.out.resolve(); out.mkdir(parents=True,exist_ok=True)
    before=run_host(out,True); after=run_host(out)
    checks=0
    for mode,icons in after.items():
        for (name,size),rects in icons.items():
            width=25*(2 if size>=14 else 1) if name=="satellite_icon" else size
            assert rects, ("empty",name,size)
            assert all(x>=0 and y>=0 and x+w<=width and y+h<=size for x,y,w,h in rects), ("overflow",name,size,rects)
            checks+=1
            if mode==1:
                assert raster(rects,size).tobytes()==raster(after[0][(name,size)],size).tobytes(), ("platform drift",name,size)
                checks+=1
            if name not in ("satellite_icon","tower_route_icon","relay_status_icon","relay_packet_icon"):
                assert raster(rects,size).tobytes()==raster(firmware_icon_rects(name,size),size).tobytes(), ("Python replay drift",name,size)
                checks+=1
    for a,b in [("emoji_sound_icon","muted_icon"),("emoji_home_icon","emoji_building_icon"),
                ("emoji_building_icon","emoji_factory_icon"),("emoji_msg_icon","emoji_mail_icon"),
                ("emoji_note_icon","emoji_mail_icon"),("emoji_plug_icon","emoji_battery_icon"),
                ("emoji_location_icon","satellite_icon"),("emoji_key_icon","emoji_lock_icon")]:
        for size in (8,9,12,16):
            assert raster(after[0][(a,size)],size).tobytes()!=raster(after[0][(b,size)],size).tobytes(), ("ambiguous",a,b,size)
            checks+=1
    contact_sheet(out,before,after)
    checks+=audit_ink_metrics(out)
    records=[{"name":name,"size":size,"rects":rects} for (name,size),rects in after[0].items()]
    (out/"icon_rects.json").write_text(json.dumps(records),encoding="utf-8")
    report={"baseline":BASE,"checks":checks,"icons":len(after[0])//7,
            "sizes":[8,9,10,11,12,16,24],"renderer":"actual UITask.cpp C++ helpers",
            "boards":["T096","T114","ProMicro RA62","Heltec V4.3 OLED","Wireless Paper WOOD/FULL"],
            "physical_hardware_test":False}
    (out/"icon_audit.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))


if __name__=="__main__":
    main()
