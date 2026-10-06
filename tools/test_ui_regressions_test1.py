"""Production navigation-deadline, chat-revision and stable-filter regressions."""
from pathlib import Path
import argparse
import test_quick_target_flow as q
from test_ui_sessions_v006 import function, run_cpp

ROOT=Path(__file__).resolve().parents[1]


def refresh_code(source):
    loop=source[source.index('void UITask::loop()'):]
    block=function(loop,'  if (c != 0 && curr) {')
    setter=function(source,'void UITask::setCurrScreen(UIScreen* c)')
    return r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <initializer_list>
#include "UiTiming.h"
#define UI_EINK_IDLE_SCREENSAVER 0
uint32_t now;
uint32_t millis(){return now;}
struct UIScreen {int inputs=0; void handleInput(char){++inputs;}};
struct MsgPreviewScreen : UIScreen {int closes=0;void closeDetails(){++closes;}};
struct UITask {
  UIScreen* curr=nullptr; UIScreen* msg_preview=nullptr;
  uint32_t _last_activity_ms=0,_next_refresh=0;
  int dismissals=0;
  void clearImportantNotify(){++dismissals;}
  void dismissCurrentMessageNotifications(){++dismissals;}
  void extendAutoOff(){}
  void setCurrScreen(UIScreen*);
  void input(char c){
''' + block + r'''
  }
};
''' + setter + r'''
int main(){
  UIScreen screen; MsgPreviewScreen inbox; UITask task; task.msg_preview=&inbox;
  for(uint32_t t:{0U,1000U,0x80000063U,0x80000064U,0xfffffff0U}){
    now=t;task.setCurrScreen(&screen);
    assert(smartui::deadlineDueOrImmediate(now,task._next_refresh));
    task.input('n');
    assert(smartui::deadlineDueOrImmediate(now,task._next_refresh));
  }
  task.setCurrScreen(&inbox);int before=task.dismissals;task.input('n');
  assert(task.dismissals==before); // Inbox owns generation-specific dismissal.
  task.setCurrScreen(&screen);assert(inbox.closes==1);
  puts("PASS navigation refresh at startup, 24.8-day boundary and rollover; inbox routing");
}
'''


def filter_code(source):
    start=source.index('  bool _quick_keyboard_open;',source.index('class HomeScreen'))
    fields=source[start:source.index('#endif',start)]
    methods='\n'.join(function(source,marker) for marker in (
        '  void captureChatFilterChoice()', '  bool handleChatFilterInput(char c)',
        '  void validateChatFilter()'))
    return q.PRELUDE + r'''
struct Home { public:
  FakeTask task;FakeTask* _task=&task;
  bool _quick_reply_open=true,_chat_layout_valid=true;
  uint32_t _chat_latest_ts=7;int _chat_scroll_px=9;
''' + fields + methods + r'''
};
int main(){
  ChannelDetails channel;strcpy(channel.name,"Public");channel.channel.secret[0]=42;
  the_mesh.channels.push_back(channel);Home h;h._chat_filter_open=true;
  h.handleChatFilterInput(KEY_NEXT);assert(h._chat_filter_pick_valid);
  the_mesh.channels[0].channel.secret[0]=99;
  h.handleChatFilterInput(KEY_ENTER);
  assert(!h._chat_filter_active && h._chat_filter_open);
  assert(!strcmp(h.task.alert,"Канал изменился"));
  h.handleChatFilterInput(KEY_NEXT);h.handleChatFilterInput(KEY_ENTER);
  assert(!h._chat_filter_open && !h._chat_filter_active);
  h._chat_filter_open=true;h._chat_filter_cursor=0;h.captureChatFilterChoice();
  h.handleChatFilterInput(KEY_NEXT);h.handleChatFilterInput(KEY_ENTER);
  assert(h._chat_filter_active && h._chat_filter_identity[0]==99);
  assert(!h._chat_layout_valid && h._chat_latest_ts==0 && h._chat_scroll_px==0);
  strcpy(the_mesh.channels[0].name,"Renamed");h.validateChatFilter();
  assert(!h._chat_filter_active && !strcmp(h.task.alert,"Фильтр сброшен"));
  h._chat_filter_open=true;h._chat_filter_cursor=0;h.captureChatFilterChoice();
  h.handleChatFilterInput(KEY_NEXT);the_mesh.channels.clear();
  h.handleChatFilterInput(KEY_ENTER);assert(h._chat_filter_open && !h._chat_filter_active);
  h.handleChatFilterInput(KEY_NEXT);h.handleChatFilterInput(KEY_ENTER);
  assert(!h._chat_filter_open); // Vanished pinned channel still has a distinct Back.
  h._chat_filter_open=true;h._chat_filter_cursor=0;h.handleChatFilterInput(KEY_ENTER);
  assert(!h._chat_filter_active && !h._chat_filter_open);
  puts("PASS channel filter identity replacement, rename, removal, All and Back");
}
'''


def cache_code(source):
    methods='\n'.join(function(source,marker) for marker in (
        '  int selectChatRenderCount(', '  int renderChatFeed(',
        '  void renderChatFilterHeader(', '  void renderChatList('))
    return r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include "UiTiming.h"
#define UI_CHAT_RENDER_LINE_LIMIT 0
#define UI_T096_PREMIUM_TFT 0
#define UI_T114_APPEARANCE_MENU 0
#define UI_NATIVE_TFT_PROFILE 0
#define UI_QUICK_REPLY_KEYBOARD 0
#define NETWORK_STATUS_VIA_RELAY 1
#define UI_CHAT_EDGE_PAUSE_MILLIS 2000
#define UI_CHAT_SCROLL_STEP_PX 1
uint32_t now=1000;
uint32_t millis(){return now;}
struct Mesh {uint32_t revision=1;uint32_t getRecentChannelMessagesRevision(){return revision;}} the_mesh;
struct DisplayDriver {
  enum {YELLOW=1,GREEN=2,DARK=3};
  int width()const{return 128;}int height()const{return 64;}
  int getUiFont()const{return 0;}int getTextLineHeight()const{return 8;}
  void setColor(int){}void setBold(bool){}void fillRect(int,int,int,int){}
};
uint8_t uiPushCompactSettingsFont(DisplayDriver&){return 0;}
void uiPopFont(DisplayDriver&,uint8_t){}
int uiRichLineHeight(DisplayDriver&){return 8;}
int uiLineIconAdvance(DisplayDriver&){return 10;}
int relay_packet_icon=1,direct_packet_icon=0;
void drawUiLineIcon(DisplayDriver&,int,int,int){}
void drawOriginNameRich(DisplayDriver&,int,int,const char*){}
void drawRichTextLine(DisplayDriver&,int,int,const char*){}
void drawRichTextStaticEllipsized(DisplayDriver&,int,int,int,const char*){}
bool nextWrappedRichLine(DisplayDriver&,const char*& source,char* out,size_t capacity,int width){
  if(!*source)return false;
  size_t n=std::min(strlen(source),std::min(capacity-1,size_t(width/6)));
  memcpy(out,source,n);out[n]=0;source+=n;return n!=0;
}
struct Task{int getUiBottomColor(){return 0;}};
struct Entry{uint32_t recv_timestamp;int flags=0;char origin[32];char text[160];};
struct Home {
  Task task;Task* _task=&task;Entry chat[12]{};int _chat_item_h[12]{};
  bool _chat_layout_valid=false;
  uint32_t _chat_layout_ts=0,_chat_latest_ts=0,_chat_pause_until=0;
  int _chat_layout_count=0,_chat_layout_font=0,_chat_layout_width=0,_chat_layout_total_h=0;
  int _chat_scroll_px=0,_chat_scroll_dir=-1;
''' + methods + r'''
};
int main(){
  DisplayDriver display;Home home;
  const uint32_t times[12]={110,109,108,107,106,105,104,103,102,101,101,100};
  for(int i=0;i<12;++i){home.chat[i].recv_timestamp=times[i];strcpy(home.chat[i].origin,"Alice");strcpy(home.chat[i].text,"a");}
  home.renderChatList(display,12);const int old_height=home._chat_layout_total_h;
  for(int i=11;i>0;--i)home.chat[i]=home.chat[i-1];
  home.chat[0].recv_timestamp=111;memset(home.chat[0].text,'a',159);home.chat[0].text[159]=0;
  ++the_mesh.revision;now+=1000;home.renderChatList(display,12);
  const int measured=home.renderChatFeed(display,12,0,0,false);
  assert(home._chat_layout_total_h==measured && measured>old_height);
  assert(home._chat_scroll_px==measured-(display.height()-10));
  strcpy(home.chat[0].text,"same-second replacement");
  ++the_mesh.revision;home.renderChatList(display,12);
  assert(home._chat_layout_total_h==home.renderChatFeed(display,12,0,0,false));
  assert(home._chat_latest_ts==the_mesh.revision);
  puts("PASS chat height/reveal revision after old XOR collision and same-second content changes");
}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'qa_outputs/ui-regressions-test1')
    args=parser.parse_args()
    source=(ROOT/'examples/companion_radio/ui-new/UITask.cpp').read_text(encoding='utf-8')
    for name,code in [('refresh',refresh_code(source)),('filter',filter_code(source)),('cache',cache_code(source))]:
        print(run_cpp(code,args.out.resolve(),name),end='')


if __name__=='__main__': main()
