"""Execute test.1 message/filter renderers using checked-in bitmap font metrics.

Records production C++ layout and wrapping; paints glyph ink for every compact
font profile. Hardware display timing, emoji rasterization and radio delivery
are outside this host test.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw
import simulate_dev2_settings as settings
from test_ui_sessions_v006 import function, run_cpp

ROOT = Path(__file__).resolve().parents[1]
SENDER = 'ОченьДлинноеИмяУзлаABCDEFGHIJKLMN'
SHORT = 'Встреча у моста в 18:30.'
LONG = 'Начало. ' + 'Длинное сообщение UTF8 12345. ' * 2 + '\nПоследняя строка.'
WORD = 'Я' * 55
CHANNEL = 'ДлинныйКаналABCDEFG'


def recordings(source, profiles, out):
    assert len(SENDER.encode()) < 62 and len(CHANNEL.encode()) < 32
    assert all(len(value.encode()) < 161 for value in (SHORT, LONG, WORD))
    preview = source[source.index('class MsgPreviewScreen'):]
    methods = '\n'.join(function(preview, marker).replace(' override', '') for marker in (
        '  void appendFittedEllipsis(', '  void drawFittedUnreadText(',
        '  int renderDetailText(', '  int render(DisplayDriver& display)'))
    home = '\n'.join(function(source, marker) for marker in (
        '  void renderChatFilter(DisplayDriver& display)',
        '  void renderChatFilterHeader(DisplayDriver& display, int height)'))
    wrapping = function(source, 'static bool nextWrappedRichLine(DisplayDriver& display, const char*& src, char* out, size_t out_len, int max_width) {')
    wrapping += '\n' + function(source, 'static bool nextWrappedUnreadLine(')
    role = function(source, 'static uint8_t uiPushCompactSettingsFont(')
    assert 'display.setUiFont(0);' in role and 'uiPushCompactChromeFont(display)' in role
    assert methods.count('uiPushCompactSettingsFont(display)') == 1
    assert home.count('uiPushCompactSettingsFont(display)') == 2
    characters = set(SENDER + SHORT + LONG + WORD + CHANNEL +
                     'ЛС 0123456789ABCDEF#/.Нет непрочитанныхУдерж:читатьназад'
                     'ОтветитьПрочитаноНапомнить 15мНазадКлик / удерж: OK'
                     'Все каналыКанал лентыКлик: выборУдерж: применитьCH40?')
    characters.discard('\n')
    code = r'''
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <iostream>
#include <map>
#include <string>
#include <initializer_list>
#include "UiTiming.h"
#define UI_QUICK_REPLY_KEYBOARD 1
#define UI_UNREAD_USE_MONO_5X7 0
#define UI_UNREAD_TEXT_LEN 161
#define UI_CHAT_SCROLL_STEP_PX 3
#define UI_CHAT_EDGE_PAUSE_MILLIS 1800
#define UI_EINK_SCROLL_REFRESH_MILLIS 1000
#define UI_CHAT_REFRESH_MILLIS 100
#define AUTO_OFF_MILLIS 1
uint32_t millis() { return 100; }
struct DisplayDriver {
  enum {GREEN=1,LIGHT=2,YELLOW=3,DARK=4};
  int profile,w,h,line_h,color=LIGHT;
  std::string scene;
  std::map<uint32_t,int> widths;
  int width() const { return w; }
  int height() const { return h; }
  int getTextLineHeight() const { return line_h; }
  void setTextSize(int) {}
  void setBold(bool) {}
  void setColor(int c) { color=c; }
  int getTextWidth(const char* value) const {
    const unsigned char* p=(const unsigned char*)value;int n=0;
    while(*p) {
      uint32_t cp=*p++;
      if((cp&0xe0)==0xc0) {cp=(cp&0x1f)<<6;cp|=*p++&0x3f;}
      if(cp=='\r'||cp=='\n')continue;
      auto found=widths.find(cp);
      if(found==widths.end()) {std::cerr<<"Missing glyph "<<cp<<'\n';std::abort();}
      n+=found->second;
    }
    return n;
  }
  void text(char align,int x,int y,int limit,const char* value,const char* tag="text") {
    std::cout<<profile<<'\t'<<scene<<'\t'<<tag<<'\t'<<align<<'\t'<<x<<'\t'<<y<<'\t'
             <<limit<<'\t'<<color<<'\t'<<value<<'\n';
  }
  void drawTextRightAlign(int x,int y,const char* text) { this->text('R',x,y,w,text,"identity"); }
  void fillRect(int,int,int,int) {}
};
uint8_t uiPushCompactSettingsFont(DisplayDriver&) { return 0; }
void uiPopFont(DisplayDriver&,uint8_t) {}
void drawRichTextCenteredEllipsized(DisplayDriver& d,int x,int y,int width,const char* text) { d.text('C',x,y,width,text); }
void drawRichTextStaticEllipsized(DisplayDriver& d,int x,int y,int width,const char* text) { d.text('L',x,y,width,text,"sender"); }
void drawUnreadTextLine(DisplayDriver& d,int x,int y,const char* text,bool=false) { d.text('L',x,y,d.width()-4,text,"body"); }
int richTextWidth(DisplayDriver& d,const char* text) { return d.getTextWidth(text); }
int unreadTextWidth(DisplayDriver& d,const char* text) { return d.getTextWidth(text); }
const uint8_t* richEmojiIconAt(const char*,size_t*) { return nullptr; }
bool richIgnorableUtf8Mark(const char*,size_t*) { return false; }
''' + function(source, 'static size_t richUtf8Len(') + '\n' + wrapping + r'''
struct Preview {
  struct MsgEntry {
    uint32_t preview_id=1;
    uint8_t sender_id_len=4,sender_id[4]={0x01,0x23,0xAB,0xCD};
    char sender[62]={0},msg[UI_UNREAD_TEXT_LEN]={0};
  } unread[1],opened_entry;
  int num_unread=1,scroll_px=0,scroll_dir=1;
  uint32_t selected_preview_id=0,scroll_pause_until=10000;
  bool detail_open=false;
  uint8_t detail_action=0;
  char header_line[40],fitted_line[80];
  int selectedOffset() const { return num_unread>1?num_unread-1:0; }
  int unreadIndexFromNewest(int) const { return 0; }
''' + methods + r'''
};
struct Home {
  int _chat_filter_cursor=0,_chat_filter_pick_id=39,_chat_filter_channel_id=39;
  bool _chat_filter_pick_valid=true,_chat_filter_active=false;
  char _chat_filter_pick_label[32]={0},_chat_filter_label[32]={0};
''' + home + r'''
};
int main() {
'''
    for index, profile in enumerate(profiles):
        widths = ','.join('{'+str(ord(c))+','+str(profile.desired_font.width(c))+'}' for c in sorted(characters))
        code += f'{{DisplayDriver d{{{index},{profile.logical_w},{profile.logical_h},{profile.desired_font.logical_height},2,"",{{{widths}}}}};\n'
        code += f'Preview p;strcpy(p.unread[0].sender,{json.dumps(SENDER, ensure_ascii=False)});\n'
        code += f'strcpy(p.unread[0].msg,{json.dumps(LONG, ensure_ascii=False)});p.opened_entry=p.unread[0];\n'
        code += 'for(int count:{0,1,24}) {p.num_unread=count;d.scene="list_"+std::to_string(count);p.render(d);}\n'
        code += 'p.detail_open=true;p.num_unread=1;\n'
        for text_index, value in enumerate((SHORT, LONG, WORD)):
            code += f'strcpy(p.opened_entry.msg,{json.dumps(value, ensure_ascii=False)});\n'
            code += 'for(int action=0;action<4;++action) for(int scroll:{0,1,d.line_h-1,d.line_h,999}) {\n'
            code += f'd.scene="detail_{text_index}_"+std::to_string(action)+"_"+std::to_string(scroll);p.detail_action=action;p.scroll_px=scroll;p.render(d);}}\n'
        code += f'Home h;strcpy(h._chat_filter_pick_label,{json.dumps(CHANNEL, ensure_ascii=False)});strcpy(h._chat_filter_label,h._chat_filter_pick_label);\n'
        code += 'for(int cursor:{0,1,2}) {h._chat_filter_cursor=cursor;h._chat_filter_pick_valid=cursor!=2;d.scene="filter_"+std::to_string(cursor);h.renderChatFilter(d);}\n'
        code += 'for(bool active:{false,true}) {h._chat_filter_active=active;d.scene=active?"header_filtered":"header_all";h.renderChatFilterHeader(d,d.line_h+2);}\n}\n'
    code += '}\n'
    output = run_cpp(code, out, 'test1_render')
    result = {}
    for line in output.splitlines():
        index, scene, tag, align, x, y, width, color, value = line.split('\t', 8)
        result.setdefault((int(index), scene), []).append((tag, align, int(x), int(y), int(width), int(color), value))
    return result, hashlib.sha256((methods + home + wrapping).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT/'qa_outputs/ui-test1-render')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    source = (ROOT/'examples/companion_radio/ui-new/UITask.cpp').read_text(encoding='utf-8')
    profiles = settings.profiles()
    ops, fingerprint = recordings(source, profiles, out)
    frames, metrics, failures = {}, [], []
    for (index, scene), calls in ops.items():
        profile = profiles[index]
        frame = settings.SettingsFrame(profile, scene, True)
        boxes = []
        for row, (tag, align, x, y, width, color, value) in enumerate(calls):
            shown = frame.text(x, y, value, {1:'green',2:'light',3:'yellow'}[color],
                               max_w=width, center=align=='C', right=align=='R',
                               tag=f'{tag}_{row}', allow_clip=True)
            # Only names, message snippets and long channel labels may elide.
            may_elide = tag=='sender' or value==SENDER or value.startswith('CH40 ')
            if shown != value and not may_elide:
                failures.append((profile.board, profile.profile, scene, 'unexpected truncation', value, shown))
            box = frame.elements[-1].physical_box
            frame.check_physical_box(f'{tag}_{row}', box)
            if box:
                for prev in boxes:
                    if box[0] < prev[2] and prev[0] < box[2] and box[1] < prev[3] and prev[1] < box[3]:
                        failures.append((profile.board,profile.profile,scene,'overlap',prev,box))
                boxes.append(box)
                if tag=='body' and scene.startswith('detail_'):
                    line_h=profile.desired_font.logical_height
                    top,bottom=line_h+2,profile.logical_h-line_h*2-2
                    frame.assert_element_inside(f'{tag}_{row}',(0,top,profile.logical_w,bottom-top))
            metrics.append(dict(board=profile.board,font=profile.profile,scene=scene,tag=tag,text=shown,ink=box))
        failures.extend((profile.board,profile.profile,scene,error) for error in frame.violations)
        frames[index,scene] = frame
    picks=[('T096','T096','Noto'),('T114','T114',None),('V3','OLED','Classic'),
           ('V4.3','OLED','Air'),('ProMicro','OLED','Strong'),('Paper','Wireless Paper',None)]
    sheet=Image.new('RGB',(1480,6*225),(25,28,31));draw=ImageDraw.Draw(sheet)
    for row,(name,board,font) in enumerate(picks):
        index=next(i for i,p in enumerate(profiles) if p.board==board and (font is None or p.profile==font))
        for col,scene in enumerate(('list_24','detail_1_2_0','filter_1')):
            image=frames[index,scene].image
            scale=max(1,min(3,460//image.width,180//image.height))
            draw.text((col*490+8,row*225+5),f'{name}: {scene}',fill=(255,255,255))
            sheet.paste(image.resize((image.width*scale,image.height*scale),Image.Resampling.NEAREST),(col*490+8,row*225+28))
    sheet.save(out/'TEST1_ALL_SIX.png')
    (out/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'REPORT.json').write_text(json.dumps(dict(scenes=len(frames),font_profiles=len(profiles),
        renderer_sha256=fingerprint,scope='production C++ layout/wrapping + bitmap glyph ink; no hardware or emoji rasterization',
        failures=failures),ensure_ascii=False,indent=2),encoding='utf-8')
    assert not failures, failures[:8]
    print(f'PASS {len(frames)} message/filter real-font scenes; all six release board profiles')


if __name__=='__main__':
    main()
