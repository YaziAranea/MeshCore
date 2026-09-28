"""Extract quick-reply/About C++ renderers; verify actual embedded glyph ink.

Uses the same compact roles as firmware, including T114 physical scaling.
No hardware display/button or full firmware execution is claimed.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw
import simulate_dev2_settings as settings
from test_connection_ui_v005 import _text_ink_metrics
from test_ui_sessions_v006 import function, run_cpp

ROOT=Path(__file__).resolve().parents[1]


def recordings(source, profiles, out):
    methods='\n'.join(function(source, marker) for marker in (
        '  void renderQuickReplyMenu(DisplayDriver& display) const',
        '  void renderBuildInfo(DisplayDriver& display) const'))
    # Confirm the profiles below use the production compact font selection,
    # independent of the selected large body/clock font.
    role=function(source,'static uint8_t uiPushCompactSettingsFont')
    assert 'display.setUiFont(uiOledStyleFromFont(saved_font));' in role
    assert 'display.setUiFont(0);' in role
    assert 'return uiPushCompactChromeFont(display);' in role
    assert methods.count('uiPushCompactSettingsFont(display)')==2
    labels=['Написать...']+re.findall(r'"([^"]+)"',source.split('static const char* quick_reply_texts[]',1)[1].split('};',1)[0])+['Назад']
    characters=set(''.join(labels)+'Быстрый ответклик: далее / удерж: OKО прошивкеSmartUI SHA Core0123456789abcdef+dirtyunknown. ')
    code=r'''
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <map>
#include <string>
#define SMARTUI_BUILD_SHA "12345678+dirty"
#include <helpers/SmartUiBuildInfo.h>
struct DisplayDriver {
  enum {GREEN=1,LIGHT=2,YELLOW=3};
  int profile,w,h,top,ink,color=LIGHT;
  const char* scene;
  std::map<uint32_t,int> widths;
  int width() const {return w;}
  int height() const {return h;}
  int getTextInkTop() const {return top;}
  int getTextInkHeight() const {return ink;}
  void setColor(int c) {color=c;}
  int getTextWidth(const char* value) const {
    const unsigned char* p=(const unsigned char*)value; int n=0;
    while(*p) {
      uint32_t cp=*p++;
      if ((cp&0xe0)==0xc0) {cp=(cp&0x1f)<<6; cp|=*p++&0x3f;}
      auto it=widths.find(cp); if(it==widths.end()) {std::cerr<<"missing "<<cp; std::abort();}
      n+=it->second;
    }
    return n;
  }
};
uint8_t uiPushCompactSettingsFont(DisplayDriver&) {return 0;}
void uiPopFont(DisplayDriver&,uint8_t) {}
void drawRichTextCenteredEllipsized(DisplayDriver& d,int x,int y,int width,const char* value) {
  std::cout<<d.profile<<'\t'<<d.scene<<'\t'<<x<<'\t'<<y<<'\t'<<width<<'\t'<<d.color<<'\t'<<value<<'\n';
}
struct Home {
  const char* label;
  const char* quickReplyLabel() const {return label;}
''' + methods + '\n};\nint main(){\n'
    for index, profile in enumerate(profiles):
        widths=','.join('{'+str(ord(c))+','+str(profile.desired_font.width(c))+'}' for c in sorted(characters))
        top,ink=_text_ink_metrics(profile)
        for number,label in enumerate(labels+['about']):
            scene='about' if label=='about' else 'reply_'+str(number)
            code+=f'{{DisplayDriver d{{{index},{profile.logical_w},{profile.logical_h},{top},{ink},2,{json.dumps(scene)},{{{widths}}}}};'
            code+=f'Home h{{{json.dumps(label,ensure_ascii=False)}}};h.'+('renderBuildInfo' if scene=='about' else 'renderQuickReplyMenu')+'(d);}\n'
    code+='}\n'
    output=run_cpp(code,out,'ui_render')
    result={}
    for line in output.splitlines():
        profile,scene,x,y,width,color,value=line.split('\t',6)
        result.setdefault((int(profile),scene),[]).append((int(x),int(y),int(width),int(color),value))
    return result,hashlib.sha256(methods.encode()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'qa_outputs/ui-v006-render')
    args=parser.parse_args(); out=args.out.resolve(); out.mkdir(parents=True,exist_ok=True)
    source=(ROOT/'examples/companion_radio/ui-new/UITask.cpp').read_text(encoding='utf-8')
    profiles=settings.profiles()
    ops,fingerprint=recordings(source,profiles,out)
    frames={}; metrics=[]
    for (index,scene),calls in ops.items():
        profile=profiles[index]
        frame=settings.SettingsFrame(profile,scene,True)
        boxes=[]
        for row,(x,y,width,color,text) in enumerate(calls):
            # Negative cursor Y is valid when the font's padded ascent would
            # otherwise waste top space. Verify actual ink, not cursor origin.
            shown=frame.text(x,y,text,{1:'green',2:'light',3:'yellow'}[color],
                             center=True,max_w=width,tag=str(row),allow_clip=True)
            assert shown==text,(profile.board,profile.profile,scene,'text truncated',text,shown)
            box=frame.elements[-1].physical_box
            frame.check_physical_box(str(row),box)
            if box:
                for previous in boxes:
                    assert box[1]>=previous[3],(profile.board,profile.profile,scene,'rows overlap',previous,box)
                boxes.append(box)
            metrics.append(dict(board=profile.board,font=profile.profile,scene=scene,text=text,ink=box))
        assert not frame.violations,(profile.board,profile.profile,scene,frame.violations)
        frames[index,scene]=frame
    picks=[('T096','T096','Noto'),('T114','T114',None),('V3','OLED','Classic'),
           ('V4','OLED','Air'),('ProMicro','OLED','Strong'),('Paper','Wireless Paper',None)]
    sheet=Image.new('RGB',(1000,6*235),(25,28,31)); draw=ImageDraw.Draw(sheet)
    for row,(name,board,font) in enumerate(picks):
        index=next(i for i,p in enumerate(profiles) if p.board==board and (font is None or p.profile==font))
        for col,scene in enumerate(('reply_0','about')):
            frame=frames[index,scene]; image=frame.image
            scale=min(3,440//image.width,190//image.height)
            scale=max(scale,1)
            draw.text((col*500+8,row*235+5),f'{name}: {scene}',fill=(255,255,255))
            sheet.paste(image.resize((image.width*scale,image.height*scale),Image.Resampling.NEAREST),(col*500+8,row*235+30))
    sheet.save(out/'UI006_ALL_SIX.png')
    (out/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
    report=dict(scenes=len(frames),compact_font_profiles=len(profiles),renderer_sha256=fingerprint,
                scope='extracted production C++ geometry + embedded glyphs, not full firmware/hardware',
                sha_display='example dirty identity 12345678+dirty',failures=[])
    (out/'REPORT.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(f'PASS {len(frames)} real-font quick-reply/About scenes; all six display profiles')


if __name__=='__main__':
    main()
