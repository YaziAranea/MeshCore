"""Execute extracted production inbox/actions/snooze methods; no device claim."""
from pathlib import Path
import argparse

from test_ui_sessions_v006 import function, run_cpp

ROOT = Path(__file__).resolve().parents[1]


def harness(source):
    inbox = source[source.index('class MsgPreviewScreen'):source.index('void UITask::begin(')]
    fields = inbox[inbox.index('  UITask* _task;'):inbox.index('  int unreadIndexFromNewest')]
    methods = '\n'.join(function(inbox, marker).replace(' override', '') for marker in (
        '  int unreadIndexFromNewest(', '  MsgPreviewScreen(UITask*',
        '  bool hasUnreadPreviews()', '  int unreadPreviewCount()',
        '  int selectedOffset()', '  void selectNewest()', '  void closeDetails()', '  bool isReading()',
        '  bool removePreviewById(', '  bool snoozePreviewById(', '  bool takeDueReminder(',
        '  bool applyActionByGeneration(',
        '  bool containsGeneration(',
        '  bool removeOldestPreview(', '  void clearPreviews(', '  void addPreview(',
        '  bool handleInput(char c)',
    ))
    handler = '\n'.join(function(source, name) for name in (
        'void UITask::snoozedMessageHandler()', 'void UITask::dismissMessageNotification(',
        'void UITask::localMessageRead(', 'bool UITask::hasActiveInboxSession() const',
        'void UITask::localMessageDismiss(', 'bool UITask::localMessageSnooze(',
        'bool UITask::applyMessageAction(', 'void UITask::dismissCurrentMessageNotifications(',
        'bool UITask::canSnoozeMessage(',
        'void UITask::msgRead(int msgcount)', 'void UITask::msgRead(int msgcount, bool',
        'void UITask::directMsgRead(', 'void UITask::messageTransferState('))
    return r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include "UiTiming.h"
#include "../SmartUiSync.h"
#define PUB_KEY_SIZE 32
#define UI_UNREAD_MSG_LIMIT 4
#define UI_UNREAD_TEXT_LEN 181
#define UI_UNREAD_DIRECT_ONLY 1
#define UI_MSG_FLAG_NONE 0
#define UI_MSG_FLAG_DIRECT 1
#define UI_MSG_FLAG_MENTION 2
#define UI_MSG_FLAG_IMPORTANT 4
#define NOTIFY_MODE_SILENT 0
#define UI_CHAT_EDGE_PAUSE_MILLIS 2000
#define KEY_PREV 'p'
#define KEY_LEFT '<'
#define KEY_NEXT 'n'
#define KEY_RIGHT '>'
#define KEY_ENTER '\r'
#define KEY_SELECT 's'
static uint32_t now=1000;
uint32_t millis() { return now; }
namespace mesh { struct RTCClock { uint32_t getCurrentTime() { return 1760000000; } }; }
struct StrHelper { static void strncpy(char* out,const char* in,size_t size) { std::snprintf(out,size,"%s",in); } };
enum class UIMessageTransferState : uint8_t { queuedToCompanion };
struct UITask {
  void* msg_preview=nullptr;
  void* curr=nullptr;
  bool _storage_recovery_active=false, muted=false, _important_notify_active=false;
  bool _popup_pending=false, _popup_pending_important=false;
  bool _explicit_read_policy=false;
  void (*_sync_action_callback)(uint32_t,smartui::SyncAction,uint32_t)=nullptr;
  uint8_t _ble_smart_notify_flags=0;
  uint8_t _important_msg_flags=0;
  int notify_mode=1, replies=0, homes=0, reminder_calls=0, _msgcount=0, stopped=0;
  uint32_t active_generation=0;
  uint32_t _important_notify_generation=0, _ble_smart_notify_generation=0, _next_refresh=0;
  uint8_t replied_key[32]={};
  char alert[80]={};
  void showAlert(const char* value,int) { std::snprintf(alert,sizeof(alert),"%s",value); }
  bool replyToIncomingMessage(const uint8_t* key,uint8_t len,const char*) {
    if(len!=32) return false;
    std::memcpy(replied_key,key,32); ++replies; return true;
  }
  void gotoHomeScreen() { ++homes; }
  void localMessageRead(uint32_t);
  void localMessageDismiss(uint32_t);
  bool localMessageSnooze(uint32_t,uint32_t);
  bool applyMessageAction(uint32_t,smartui::SyncAction,uint32_t=0);
  bool canSnoozeMessage(uint32_t) const;
  void dismissCurrentMessageNotifications();
  void dismissMessageNotification(uint32_t);
  void clearBleSmartNotify() { _ble_smart_notify_flags=0; _ble_smart_notify_generation=0; }
  void clearImportantNotify() { finishImportantNotify(true,true); }
  void finishImportantNotify(bool stop_tone,bool clear_pending) {
    _important_notify_active=false; _important_notify_generation=0;
    if(stop_tone) ++stopped;
    if(clear_pending) clearBleSmartNotify();
  }
  bool areNotificationsMuted() { return muted; }
  uint8_t getImportantNotifyMode() { return notify_mode; }
  bool areMsgPopupsEnabled() { return true; }
  void beginImportantNotify(uint8_t,uint32_t generation,bool) {
    ++reminder_calls; _important_notify_active=true; active_generation=generation;
    _important_notify_generation=generation;
  }
  void snoozedMessageHandler();
  bool hasActiveInboxSession() const;
  void directMsgRead(bool);
  void msgRead(int);
  void msgRead(int,bool);
  void messageTransferState(uint32_t,uint8_t,UIMessageTransferState,int);
};
struct MsgPreviewScreen { public:
''' + fields + methods + '\n};\n' + handler + r'''
static unsigned checks=0;
#define CHECK(x) do { ++checks; assert(x); } while (0)
void add(MsgPreviewScreen& inbox,uint32_t generation,uint8_t key,const char* text="hello") {
  uint8_t identity[32]={}; identity[0]=key; identity[31]=key;
  inbox.addPreview(0,"Same displayed name",text,UI_MSG_FLAG_DIRECT,generation,identity,32);
}
int main() {
  mesh::RTCClock clock;
  UITask task;
  MsgPreviewScreen inbox(&task,&clock); task.msg_preview=&inbox; task.curr=&inbox;
  add(inbox,101,1,"ch2 literal text"); add(inbox,102,2);
  CHECK(inbox.unreadPreviewCount()==2);
  inbox.handleInput(KEY_ENTER); // Newest B, without marking it read.
  CHECK(inbox.detail_open && inbox.opened_entry.generation==102);
  CHECK(task.hasActiveInboxSession());
  CHECK(task._msgcount==0 && inbox.unreadPreviewCount()==2);
  inbox.handleInput(KEY_NEXT); inbox.handleInput(KEY_ENTER); // Read B only.
  CHECK(inbox.unreadPreviewCount()==1 && task._msgcount==1);
  CHECK(!task.hasActiveInboxSession());
  CHECK(inbox.unread[inbox.head].generation==101);
  CHECK(!std::strcmp(inbox.unread[inbox.head].msg,"ch2 literal text"));
  task.messageTransferState(101,UI_MSG_FLAG_DIRECT,UIMessageTransferState::queuedToCompanion,1);
  task.directMsgRead(false);
  CHECK(inbox.unreadPreviewCount()==1 && inbox.unread[inbox.head].generation==101);
  task.messageTransferState(102,UI_MSG_FLAG_DIRECT,UIMessageTransferState::queuedToCompanion,0);
  CHECK(inbox.unreadPreviewCount()==1); // Local B-read followed by A/B sync never reorders human reads.

  inbox.handleInput(KEY_ENTER); // Open A, then another message arrives.
  add(inbox,103,3,"new message while reading");
  CHECK(inbox.opened_entry.generation==101);
  inbox.handleInput(KEY_ENTER); // Reply stays addressed to A's complete key.
  CHECK(task.replies==1 && task.replied_key[0]==1 && task.replied_key[31]==1);
  CHECK(inbox.unreadPreviewCount()==2); // Reply does not imply human read.

  // Snoozing/reading A does not stop active B or its companion watcher.
  task._important_notify_active=true; task._important_notify_generation=103;
  task._ble_smart_notify_flags=1; task._ble_smart_notify_generation=103;
  task.dismissMessageNotification(101);
  CHECK(task._important_notify_active && task._important_notify_generation==103 && task.stopped==0);
  CHECK(task._ble_smart_notify_flags==1 && task._ble_smart_notify_generation==103);
  task.localMessageRead(999); // An absent older generation cannot stop B either.
  CHECK(task._important_notify_active && task._ble_smart_notify_flags==1 && task.stopped==0);
  task.dismissMessageNotification(103);
  CHECK(!task._important_notify_active && task._ble_smart_notify_flags==0 && task.stopped==1);

  const uint32_t a_id=inbox.unread[inbox.unreadIndexFromNewest(1)].preview_id;
  CHECK(inbox.snoozePreviewById(a_id));
  const int before_count=inbox.unreadPreviewCount();
  now+=899999;
  task.snoozedMessageHandler(); CHECK(task.reminder_calls==0);
  add(inbox,104,4); // New message gets no inherited snooze.
  CHECK(inbox.unread[inbox.head].snooze_until==0);
  task._important_notify_active=true; task.active_generation=104;
  now+=2;
  task.snoozedMessageHandler();
  CHECK(task.reminder_calls==0 && task.active_generation==104);
  task._important_notify_active=false;
  task.snoozedMessageHandler();
  CHECK(task.reminder_calls==1 && task.active_generation==101);
  CHECK(inbox.unreadPreviewCount()==before_count+1 && !task.muted);
  CHECK(task._popup_pending && task._popup_pending_important);
  task._important_notify_active=false; task.snoozedMessageHandler();
  CHECK(task.reminder_calls==1); // Deadline consumed once; normal reminder policy owns it now.

  CHECK(inbox.snoozePreviewById(a_id));
  CHECK(inbox.removePreviewById(a_id));
  now+=900001; task.snoozedMessageHandler(); CHECK(task.reminder_calls==1);
  CHECK(inbox.unreadPreviewCount()==2);

  // Wrap-safe deadline, without turning zero into "no reminder".
  now=uint32_t(0)-900000U;
  inbox.selectNewest(); const uint32_t selected=inbox.unread[inbox.head].preview_id;
  CHECK(inbox.snoozePreviewById(selected));
  CHECK(inbox.unread[inbox.head].snooze_until==1);
  now=0; task.snoozedMessageHandler(); CHECK(task.reminder_calls==1);
  now=1; task.snoozedMessageHandler(); CHECK(task.reminder_calls==2);

  // A bounded saved detail remains stable even after its ring entry is evicted.
  inbox.handleInput(KEY_ENTER); const uint32_t opened=inbox.opened_entry.preview_id;
  const uint32_t generation=inbox.opened_entry.generation;
  for(uint32_t i=0;i<8;++i) add(inbox,200+i,uint8_t(20+i));
  CHECK(inbox.unreadPreviewCount()==4);
  task.messageTransferState(101,UI_MSG_FLAG_DIRECT,UIMessageTransferState::queuedToCompanion,0);
  task.directMsgRead(true);
  CHECK(inbox.unreadPreviewCount()==4); // Evicted/absent transport generations cannot delete retained previews.
  CHECK(inbox.opened_entry.preview_id==opened && inbox.opened_entry.generation==generation);
  CHECK(!inbox.snoozePreviewById(opened));
  CHECK(!inbox.removePreviewById(opened));
  CHECK(inbox.unreadPreviewCount()==4);

  // Read targeted middle entry compacts only the selected item, retaining new arrivals.
  const uint32_t middle=inbox.unread[inbox.unreadIndexFromNewest(2)].preview_id;
  const uint32_t newest=inbox.unread[inbox.head].generation;
  CHECK(inbox.removePreviewById(middle));
  CHECK(inbox.unreadPreviewCount()==3 && inbox.unread[inbox.head].generation==newest);
  inbox.clearPreviews(true);
  CHECK(!inbox.detail_open && !inbox.hasUnreadPreviews());
  printf("PASS %u production inbox/actions/per-message-snooze checks\n",checks);
}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'qa_outputs/ui-inbox-test1')
    args=parser.parse_args()
    source=(ROOT/'examples/companion_radio/ui-new/UITask.cpp').read_text(encoding='utf-8')
    mesh=(ROOT/'examples/companion_radio/MyMesh.cpp').read_text(encoding='utf-8')
    sync=mesh[mesh.index('} else if (cmd_frame[0] == CMD_SYNC_NEXT_MESSAGE)'):mesh.index('} else if (cmd_frame[0] == CMD_SET_RADIO_PARAMS')]
    assert '_ui->msgRead(offline_queue_len, false);' in sync
    assert '_ui->messageTransferState(' in sync and 'directMsgRead' not in sync
    print(run_cpp(harness(source),args.out.resolve(),'inbox'),end='')


if __name__=='__main__': main()
