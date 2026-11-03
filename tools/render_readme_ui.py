"""Render README demo scenes from current extracted C++ UI functions.

The host runs renderQuickKeyboard/renderQuickTargetPicker and their drawing
helpers. The display adapter records primitives; Python draws those primitives
with the firmware's embedded Roboto compact glyphs and ST7735 Graphite palette.
This is a framebuffer simulation, not a complete firmware or hardware test.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

from PIL import Image

from simulate_smartui_ps17_qa import BoardProfile, EmbeddedRaw, Frame, T096ExactFont
from test_ui_sessions_v006 import function, run_cpp

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / 'examples/companion_radio/ui-new/UITask.cpp'
DRIVER = ROOT / 'src/helpers/ui/ST7735Display.cpp'
TEXT = 'Буду к 19:00'


def rgb565(value):
    return ((value >> 11) * 255 // 31, ((value >> 5) & 63) * 255 // 63,
            (value & 31) * 255 // 31)


def production_palette():
    source = DRIVER.read_text(encoding='utf-8')
    row = source.split('static const ST7735Theme ST7735_THEMES[] = {', 1)[1].split('\n', 2)[1]
    colors = [rgb565(int(v, 16)) for v in re.findall(r'0x[0-9A-Fa-f]+', row)]
    assert len(colors) == 7 and 'Графит' in row
    return dict(zip(('light', 'bg', 'red', 'green', 'blue', 'yellow', 'orange'), colors))


PALETTE = production_palette()


class ProductionFrame(Frame):
    def color(self, name):
        return PALETTE['bg' if name == 'dark' else name]


def extract(source):
    start = source.index('enum QuickReplyKeyboardAction')
    constants = source[start:source.index('\n#endif', start)]
    markers = (
        'static void drawRichTextStaticEllipsized',
        'static int drawRichTextTailEllipsized',
        'static void drawRichTextCentered(',
        'static void drawRichTextCenteredEllipsized(',
        '  void drawQuickKeyboardKey(',
        '  void renderQuickTargetPicker(',
        '  void renderQuickKeyboard(',
        '  const QuickReplyKeyboardKey& currentQuickKeyboardKey()',
    )
    methods = [function(source, marker) for marker in markers]
    # The selected T096 compact font must remain the saved font's family.
    role = function(source, 'static uint8_t uiPushCompactSettingsFont')
    assert 'display.setUiFont(uiOledStyleFromFont(saved_font));' in role
    return constants, methods, role


def record(source, font, evidence):
    constants, methods, role = extract(source)
    characters = set(''.join(methods) + constants + TEXT + 'Анна#A12F')
    widths = ','.join('{%d,%d}' % (ord(c), font.width(c)) for c in sorted(characters))
    prelude = r'''
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <iostream>
#include <map>
#include <string>
#define UI_T096_PREMIUM_TFT 1
#define UI_NATIVE_TFT_PROFILE 0
#define PUB_KEY_SIZE 32
struct DisplayDriver {
  enum {DARK=0,LIGHT=1,RED=2,GREEN=3,BLUE=4,YELLOW=5,ORANGE=6};
  int color=LIGHT;
  const char* scene="";
  std::map<uint32_t,int> widths;
  int height() const {return 80;}
  int width() const {return 160;}
  int getTextLineHeight() const {return FONT_HEIGHT;}
  int getTextWidth(const char* value) const {
    const unsigned char* p=(const unsigned char*)value; int result=0;
    while(*p) {
      uint32_t cp=*p++;
      if ((cp&0xe0)==0xc0) {cp=(cp&0x1f)<<6; cp|=*p++&0x3f;}
      else if ((cp&0xf0)==0xe0) {cp=(cp&0x0f)<<12; cp|=(*p++&0x3f)<<6; cp|=*p++&0x3f;}
      result+=widths.at(cp);
    }
    return result;
  }
  void setColor(int c) {color=c;}
  void setBold(bool bold) {if(bold) std::abort();}
  void setTextSize(int size) {if(size!=1) std::abort();}
  void rectangle(const char* op,int x,int y,int w,int h) {
    std::cout<<scene<<'\t'<<op<<'\t'<<x<<'\t'<<y<<'\t'<<w<<'\t'<<h<<'\t'<<color<<'\n';
  }
  void fillRect(int x,int y,int w,int h) {rectangle("fill",x,y,w,h);}
  void drawRect(int x,int y,int w,int h) {rectangle("rect",x,y,w,h);}
  void text(int x,int y,const char* value) {
    std::cout<<scene<<"\ttext\t"<<x<<'\t'<<y<<'\t'<<color<<'\t'<<value<<'\n';
  }
  void drawTextRightAlign(int x,int y,const char* value) {text(x-getTextWidth(value),y,value);}
};
uint8_t uiPushCompactSettingsFont(DisplayDriver&) {return 0;}
void uiPopFont(DisplayDriver&,uint8_t) {}
// These scenes contain only plain UTF-8 text, no rich-text icon tokens.
int richTextWidth(DisplayDriver& d,const char* value) {return d.getTextWidth(value);}
void drawRichTextLine(DisplayDriver& d,int x,int y,const char* value) {d.text(x,y,value);}
// The demo deliberately fits without truncation. Abort if production changes
// cause either overflow path to run, rather than drawing invented fallback UI.
bool nextWrappedRichLine(DisplayDriver&,const char*&,char*,size_t,int) {std::abort();}
void drawRichTextEllipsized(DisplayDriver&,int,int,int,const char*) {std::abort();}
'''.replace('FONT_HEIGHT', str(font.logical_height))
    home = r'''
struct Home {
  uint8_t _quick_target_mode=QR_TARGET_CLOSED, _quick_keyboard_page=0, _quick_keyboard_cursor=2;
  bool _quick_confirm_open=false, _quick_confirm_send=true;
  uint16_t _quick_target_cursor=0, _quick_target_channel_id=0;
  uint8_t _quick_target_contact_pubkey[PUB_KEY_SIZE]={};
  const char* _quick_target_identity_label="Анна";
  const char* _quick_keyboard_text="Буду к 19:00";
  // Non-confirmation list state is unreachable in these two snapshots.
  uint16_t quickTargetTotalCount() {std::abort();}
  bool quickTargetIdentityMatchesCursor() {std::abort();}
  uint16_t quickTargetItemCount() {std::abort();}
  void captureQuickTargetIdentity() {std::abort();}
  const char* quickTargetTitle() {std::abort();}
  void quickTargetLabel(uint16_t,char*,size_t) {std::abort();}
'''
    code = prelude + constants + '\n' + '\n'.join(methods[:4]) + home + '\n'.join(methods[4:]) + r'''
};
int main() {
  DisplayDriver d; d.widths={WIDTHS}; Home h;
  d.scene="keyboard"; h.renderQuickKeyboard(d);
  d.scene="message"; h._quick_confirm_open=true; h._quick_target_mode=QR_TARGET_CONTACT;
  h._quick_target_contact_pubkey[30]=0xA1; h._quick_target_contact_pubkey[31]=0x2F;
  h.renderQuickTargetPicker(d);
}
'''.replace('WIDTHS', widths)
    output = run_cpp(code, evidence, 'readme_ui_host')
    (evidence / 'draw-operations.tsv').write_text(output, encoding='utf-8')
    fingerprint = hashlib.sha256((constants + '\n'.join(methods) + role).encode()).hexdigest()
    return output, fingerprint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'docs/assets/showcase')
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args()
    evidence = args.evidence or Path(tempfile.mkdtemp(prefix='smartui-readme-ui-'))
    evidence.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    font = T096ExactFont('Roboto compact / embedded profile 0', EmbeddedRaw('meshcore_font', 'meshcoreSmallFonts', 0))
    profile = BoardProfile('T096', font.name, 160, 80, 160, 80, font, font)
    source = UI.read_text(encoding='utf-8')
    operations, fingerprint = record(source, font, evidence)
    frames = {name: ProductionFrame(profile, name, True) for name in ('keyboard','message')}
    labels = {name: [] for name in frames}
    colors = ('dark','light','red','green','blue','yellow','orange')
    for line in operations.splitlines():
        parts = line.split('\t'); name, op = parts[:2]; frame = frames[name]
        if op == 'text':
            x,y,color = map(int,parts[2:5]); text = parts[5]
            shown = frame.text(x,y,text,colors[color],tag=f'{name}:{len(labels[name])}')
            assert shown == text, (text,shown)
            labels[name].append(text)
        else:
            x,y,w,h,color = map(int,parts[2:])
            frame.rect(x,y,w,h,colors[color],outline=op=='rect')
    assert TEXT in labels['keyboard'] and TEXT in labels['message']
    assert {'Анна','#A12F','Отправить','Назад'} <= set(labels['message'])
    artifacts = []
    for name,frame in frames.items():
        assert not frame.violations,frame.violations
        native = evidence / f'{name}-native.png'
        frame.image.save(native)
        target = args.out / f'readme-{name}.png'
        frame.image.resize((640,320),Image.Resampling.NEAREST).save(target,optimize=True)
        artifacts.append({'file':target.name,'size':[640,320],'native_size':[160,80],
                          'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
    report = {'scope':__doc__.strip(),'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'renderer_sha256':fingerprint,'ui_source_sha256':hashlib.sha256(UI.read_bytes()).hexdigest(),
              'driver_source_sha256':hashlib.sha256(DRIVER.read_bytes()).hexdigest(),
              'embedded_fonts_sha256':hashlib.sha256((ROOT / 'src/helpers/ui/EmbeddedBitmapFonts.h').read_bytes()).hexdigest(),
              'board':'Heltec T096','font':'embedded Roboto compact, meshcoreSmallFonts[0]',
              'theme':'ST7735 Graphite (Графит), production RGB565 converted to RGB888',
              'demo':{'contact':'Анна','id':'#A12F','message':TEXT},'artifacts':artifacts,'failures':[]}
    (evidence / 'ui-provenance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('PASS: 2 current C++ UI scenes, embedded glyphs, native 160x80, PNG 640x320')
    print('Evidence: ' + str(evidence / 'ui-provenance.json'))


if __name__ == '__main__':
    main()
