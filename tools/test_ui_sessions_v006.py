"""Run extracted production compose, idle, wake and popup code on a host.

No persistent drafts, radio delivery or physical button/display execution.
"""
from pathlib import Path
import argparse
import shutil
import subprocess

import test_quick_target_flow as q

ROOT = Path(__file__).resolve().parents[1]


def function(source, marker):
    start = source.index(marker)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def run_cpp(code, out, name):
    out.mkdir(parents=True, exist_ok=True)
    cpp = out / (name + '.cpp')
    cpp.write_text(code, encoding='utf-8')
    include = ROOT / 'examples/companion_radio/ui-new'
    if shutil.which('g++'):
        exe = out / name
        subprocess.run(['g++', '-std=c++17', '-O1', '-Wall', '-Wextra', '-I', str(include),
                        '-I', str(ROOT / 'src'), str(cpp), '-o', str(exe)], check=True)
        return subprocess.check_output([str(exe)], text=True, encoding='utf-8')
    def linux(path):
        return subprocess.check_output(['wsl', '--exec', 'wslpath', '-a', str(path)], text=True).strip()
    exe = linux(out) + '/' + name
    subprocess.run(['wsl', '--exec', 'g++', '-std=c++17', '-O1', '-Wall', '-Wextra',
                    '-I', linux(include), '-I', linux(ROOT / 'src'), linux(cpp), '-o', exe], check=True)
    return subprocess.check_output(['wsl', '--exec', exe], text=True, encoding='utf-8')


def session_code(source):
    constants = source[source.index('static const char* quick_reply_texts[]'):source.index('static ColorVal uiSemanticColor(')]
    start = source.index('  bool _quick_keyboard_open;', source.index('class HomeScreen'))
    fields = source[start:source.index('#endif', start)]
    start = source.index('  uint8_t quickReplyMenuCount() const')
    methods = source[start:source.index('  void drawQuickKeyboardKey(', start)] + '\n#endif\n'
    home_methods = '\n'.join(function(source, marker) for marker in (
        '  bool hasActiveComposeSession() const', '  void resetToFirstPage()', '  bool isClockPage() const',
        '  void captureChatFilterChoice()'))
    start = source.index('  bool handleInput(char c) override', source.index('class HomeScreen'))
    start = source.index('    if (_quick_reply_open)', start)
    input_block = source[start:source.index('#if UI_COMPACT_SETTINGS_MENU == 1', start)]
    host_methods = '\n'.join(function(source, marker).replace('UITask::', '') for marker in (
        'void UITask::gotoHomeFirstScreen()', 'bool UITask::hasActiveComposeSession() const',
        'void UITask::markDisplayWake(bool reset_to_clock)', 'void UITask::handlePendingPopupWake()',
        'bool UITask::shouldHoldLightSleepLock() const'))
    loop = source[source.index('void UITask::loop()'):]
    idle_start = loop.index('#if UI_EINK_IDLE_SCREENSAVER\n  if (idle_saver')
    idle = loop[idle_start:loop.index('  if (_display != NULL && _display->isOn())', idle_start)]
    return q.PRELUDE + r'''
#include "UiTiming.h"
#define UI_MENU_AUTO_HOME_MILLIS 30000UL
#define UI_EINK_IDLE_SCREENSAVER 1
#define UI_EINK_IDLE_SCREENSAVER_MILLIS 45000UL
#define UI_CHAT_LIST_SIZE 12
#define UI_DISPLAY_WAKE_LOCK_MS 100
#define UI_DISPLAY_WAKE_RENDER_DELAY_MS 10
#define UI_POPUP_WAKE_WHEN_BLE_CONNECTED 1
#define UI_POPUP_BLE_STATE_SETTLE_MS 100
#define UI_DISPLAY_RECOVER_RETRY_MS 50
uint32_t now=100;
uint32_t millis() { return now; }
enum class HomePage { CLOCK, CHAT };
HomePage defaultHomePage() { return HomePage::CLOCK; }
''' + constants + r'''
class HomeScreen { public:
  FakeTask task; FakeTask* _task=&task;
  HomePage _page=HomePage::CHAT;
  bool _settings_open=false, _quick_reply_open=false, _shutdown_init=false;
  uint8_t _quick_reply_idx=0;
  int _chat_scroll_px=0, _chat_scroll_dir=0, _chat_pause_until=0, _chat_latest_ts=0;
  bool _chat_layout_valid=false;
  int _chat_layout_total_h=0, _chat_item_h[UI_CHAT_LIST_SIZE]={};
''' + fields + methods + home_methods + '\n bool handleInput(char c) {\n' + input_block + r'''
  return false;
 }
};
struct Display { bool on=true; bool isOn() { return on; } void turnOn() { on=true; } };
struct UITask {
  HomeScreen* home; void* curr; void* splash=nullptr;
  void* msg_preview=(void*)2; void* idle_saver=(void*)3;
  Display panel; Display* _display=&panel;
  bool _storage_recovery_active=false, _popup_pending=false, popups=true;
  bool _display_recover_reset_to_clock=false, _button_wake_pending=false;
  uint32_t _alert_expiry=0, _last_activity_ms=100, _next_refresh=0;
  uint32_t _display_recover_until=0, _display_recover_next=0;
  uint32_t _button_wake_pending_until=0, _display_wake_lock_until=0, _ble_state_changed_at=0;
  UITask(HomeScreen& h):home(&h),curr(&h) {}
  void setCurrScreen(void* next) { curr=next; }
  void invalidateBatteryCache() {}
  void extendAutoOff(unsigned long) {}
  void scheduleDisplayRecover(bool, unsigned long) {}
  bool areMsgPopupsEnabled() { return popups; }
  bool reading=false;
  bool hasActiveInboxSession() const { return reading; }
''' + host_methods + '\n void checkIdle() {\n' + idle + r'''
 }
};
int main() {
  unsigned checks=0;
  #define CHECK(x) do { ++checks; assert(x); } while(0)
  for (int stage=0; stage<3; ++stage) {
    HomeScreen h; h.openQuickKeyboard(); h._quick_reply_open=true;
    CHECK(h.appendQuickKeyboardText("ВСТРЕЧА У МОСТА"));
    if (stage) h._quick_target_mode=QR_TARGET_KIND;
    if (stage==2) h._quick_confirm_open=true;
    UITask task(h); now=30099; task.checkIdle();
    CHECK(h.hasActiveComposeSession());
    now=30100; task.checkIdle();
    CHECK(h.hasActiveComposeSession() && !strcmp(h._quick_keyboard_text,"ВСТРЕЧА У МОСТА"));
    now=60100; task.checkIdle(); // includes e-paper idle saver
    CHECK(task.curr==&h && h.hasActiveComposeSession());
    task._popup_pending=true; task.handlePendingPopupWake();
    CHECK(task.curr==&h && task._popup_pending);
    task.panel.on=false; task.handlePendingPopupWake();
    CHECK(task.shouldHoldLightSleepLock());
    CHECK(!task.panel.on && task.curr==&h && task._popup_pending);
    task.panel.turnOn(); task.markDisplayWake(true); // UI_WAKE_SHOW_CLOCK path
    CHECK(task.curr==&h && h.hasActiveComposeSession());
    CHECK(!strcmp(h._quick_keyboard_text,"ВСТРЕЧА У МОСТА"));
    CHECK(h._quick_confirm_open==(stage==2));
    task.gotoHomeFirstScreen(); // explicit triple-home still discards, not a draft
    CHECK(!h.hasActiveComposeSession() && !h._quick_keyboard_text[0]);
    task.handlePendingPopupWake();
    CHECK(task.curr==task.msg_preview && !task._popup_pending);
    h._page=HomePage::CHAT; task.curr=&h; task.markDisplayWake(true);
    CHECK(h._page==HomePage::CLOCK);
  }
  // Execute actual HomeScreen canned menu branch: no direct send, no channel 0.
  HomeScreen canned; canned._quick_reply_open=true; canned._quick_reply_idx=1;
  CHECK(canned.handleInput(KEY_ENTER));
  CHECK(canned.hasActiveComposeSession() && canned._quick_target_mode==QR_TARGET_KIND);
  CHECK(!strcmp(canned._quick_keyboard_text,quick_reply_texts[0]) && the_mesh.sent==0);
  ChannelDetails ch0; strcpy(ch0.name,"Public"); ch0.channel.secret[0]=7;
  ChannelDetails ch1; strcpy(ch1.name,"Private channel"); ch1.channel.secret[0]=8;
  the_mesh.channels={ch0,ch1};
  canned.selectQuickTarget(); canned.handleQuickTargetInput(KEY_NEXT);
  canned.selectQuickTarget(); CHECK(canned._quick_confirm_open && the_mesh.sent==0);
  the_mesh.channels[1].channel.secret[0]=9;
  canned.selectQuickTarget(); CHECK(the_mesh.sent==0 && canned._quick_keyboard_text[0]);
  the_mesh.channels[1].channel.secret[0]=8;
  canned.selectQuickTarget(); CHECK(the_mesh.sent==1 && the_mesh.last_channel==1);
  CHECK(!canned.hasActiveComposeSession() && !canned._quick_keyboard_text[0]);
  UITask completed(canned); completed._popup_pending=true;
  completed.handlePendingPopupWake(); CHECK(completed.curr==completed.msg_preview);
  // No active session: ordinary idle still returns Home.
  canned._page=HomePage::CHAT; completed.curr=&canned; now=30100;
  completed._last_activity_ms=100; completed.checkIdle();
  CHECK(canned._page==HomePage::CLOCK);
  completed.panel.on=false; completed._display_wake_lock_until=0; completed._alert_expiry=0;
  now=completed._last_activity_ms+120000U;
  CHECK(!completed.shouldHoldLightSleepLock());
#if UI_WIRELESS_PAPER_BIG_CLOCK
  // A static e-paper image remains on indefinitely: it must not pin CPU awake.
  completed.panel.on=true; completed._last_activity_ms=0;
  now=119999; CHECK(completed.shouldHoldLightSleepLock());
  now=120000; CHECK(!completed.shouldHoldLightSleepLock());
  completed._last_activity_ms=0xfffffff0U;
  now=0x20; CHECK(completed.shouldHoldLightSleepLock());
  now=completed._last_activity_ms+120000U;
  CHECK(!completed.shouldHoldLightSleepLock());
  completed._display_wake_lock_until=now+100;
  CHECK(completed.shouldHoldLightSleepLock());
  completed._display_wake_lock_until=0; completed._alert_expiry=now+100;
  CHECK(completed.shouldHoldLightSleepLock());
  completed._alert_expiry=0; canned.openQuickKeyboard();
  CHECK(completed.shouldHoldLightSleepLock());
  canned.resetQuickKeyboard(); CHECK(!completed.shouldHoldLightSleepLock());
#endif
  // A long message view survives ordinary idle and a display wake, without
  // converting it into a compose session or a persistent draft.
  canned._page=HomePage::CHAT; completed.curr=(void*)99; completed.reading=true;
  completed._alert_expiry=0; completed._last_activity_ms=100; now=60100;
  completed.checkIdle(); CHECK(completed.curr==(void*)99);
  completed.markDisplayWake(true); CHECK(completed.curr==(void*)99 && canned._page==HomePage::CHAT);
  completed.reading=false; now+=30001; completed.checkIdle();
  CHECK(completed.curr==&canned && canned._page==HomePage::CLOCK);
  printf("PASS %u actual compose/idle/wake/popup/canned checks\n",checks);
}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'qa_outputs/ui-v006')
    args=parser.parse_args()
    source=(ROOT/'examples/companion_radio/ui-new/UITask.cpp').read_text(encoding='utf-8')
    assert 'the_mesh.sendQuickReply(' not in source
    assert 'HomePage::ABOUT' in source.split('static const uint8_t advanced_pages[]',1)[1].split('};',1)[0]
    assert 'if (_page == HomePage::ABOUT) skip_chrome = true;' in source
    code=session_code(source)
    print(run_cpp(code,args.out.resolve(),'ui_sessions'),end='')
    print('Paper: '+run_cpp('#define UI_WIRELESS_PAPER_BIG_CLOCK 1\n'+code,
                           args.out.resolve(),'ui_sessions_paper'),end='')


if __name__=='__main__':
    main()
