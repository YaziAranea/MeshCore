#!/usr/bin/env python3
"""Compile production sync journal and exact-generation UI action regressions."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

from test_ui_inbox_test1 import harness
from test_ui_sessions_v006 import function

ROOT = Path(__file__).resolve().parents[1]


def ui_source():
    source = (ROOT / "examples/companion_radio/ui-new/UITask.cpp").read_text(encoding="utf-8")
    code = harness(source)
    # Keep every existing inbox regression and extend the same production-method harness.
    extra = r'''
  {
    UITask sync_task;
    MsgPreviewScreen sync_inbox(&sync_task,&clock);
    sync_task.msg_preview=&sync_inbox; sync_task.curr=&sync_inbox;
    static unsigned callbacks=0;
    static uint32_t callback_generation=0, callback_value=0;
    static smartui::SyncAction callback_action=smartui::SyncAction::Received;
    sync_task._sync_action_callback=[](uint32_t gen,smartui::SyncAction action,uint32_t value) {
      ++callbacks;callback_generation=gen;callback_action=action;callback_value=value;
    };
    add(sync_inbox,1001,1);add(sync_inbox,1002,2);
    CHECK(sync_task.canSnoozeMessage(1001) && sync_task.canSnoozeMessage(1002));
    CHECK(!sync_task.canSnoozeMessage(0) && !sync_task.canSnoozeMessage(999));
    sync_task._important_notify_active=true;sync_task._important_notify_generation=1002;
    sync_task._ble_smart_notify_flags=1;sync_task._ble_smart_notify_generation=1002;
    CHECK(sync_task.applyMessageAction(1001,smartui::SyncAction::Snooze,900));
    CHECK(sync_task._important_notify_active && sync_task._ble_smart_notify_generation==1002);
    CHECK(sync_inbox.unread[sync_inbox.unreadIndexFromNewest(1)].snooze_until==uint32_t(now+900000));
    CHECK(callbacks==0); // Remote execution must not echo another local event.
    CHECK(sync_task.applyMessageAction(1001,smartui::SyncAction::Read));
    CHECK(sync_inbox.unreadPreviewCount()==1 && sync_inbox.unread[sync_inbox.head].generation==1002);
    CHECK(!sync_task.canSnoozeMessage(1001));
    CHECK(sync_task._important_notify_active && sync_task.stopped==0);
    now+=900001;
    sync_task._important_notify_active=false;sync_task._ble_smart_notify_flags=0;
    sync_task.snoozedMessageHandler();CHECK(sync_task.reminder_calls==0);
    sync_task._important_notify_active=true;sync_task._important_notify_generation=1002;
    CHECK(sync_task.applyMessageAction(1001,smartui::SyncAction::Read));
    CHECK(sync_task._important_notify_active && sync_inbox.unreadPreviewCount()==1);
    CHECK(!sync_task.applyMessageAction(0,smartui::SyncAction::Read));
    CHECK(!sync_task.applyMessageAction(1002,smartui::SyncAction::Snooze,0));
    CHECK(!sync_task.applyMessageAction(1002,smartui::SyncAction::Snooze,86401));
    CHECK(!sync_task.applyMessageAction(1002,smartui::SyncAction::Read,1));
    CHECK(!sync_task.applyMessageAction(1002,static_cast<smartui::SyncAction>(99)));
    CHECK(!sync_task.applyMessageAction(999,smartui::SyncAction::Snooze,900));
    CHECK(sync_task._important_notify_active && sync_inbox.unreadPreviewCount()==1);
    CHECK(sync_task.applyMessageAction(1002,smartui::SyncAction::Received));
    CHECK(sync_task._important_notify_active && sync_inbox.unreadPreviewCount()==1);
    CHECK(sync_task.localMessageSnooze(1002,2));
    CHECK(!sync_task._important_notify_active && callbacks==1);
    CHECK(callback_generation==1002 && callback_action==smartui::SyncAction::Snooze && callback_value==2);
    CHECK(sync_inbox.unreadPreviewCount()==1);
    now+=2001;sync_task.snoozedMessageHandler();
    CHECK(callbacks==2 && callback_action==smartui::SyncAction::Resume && callback_generation==1002);
    CHECK(sync_task._important_notify_active && sync_task.active_generation==1002);
    sync_task.localMessageDismiss(1002);
    CHECK(callbacks==3 && callback_action==smartui::SyncAction::Dismiss);
    CHECK(!sync_task._important_notify_active && sync_inbox.unreadPreviewCount()==1);
    CHECK(sync_inbox.unread[sync_inbox.head].snooze_until==0);
    CHECK(sync_task.localMessageSnooze(1002,1));
    sync_task.localMessageRead(1002);
    CHECK(callbacks==5 && callback_action==smartui::SyncAction::Read);
    CHECK(sync_inbox.unreadPreviewCount()==0 && sync_task._msgcount==0);
    now+=1001;sync_task.snoozedMessageHandler();CHECK(sync_task.reminder_calls==1);

    // A channel notification can exist without a direct-message preview.
    sync_task._important_notify_active=true;sync_task._important_notify_generation=2001;
    CHECK(!sync_task.canSnoozeMessage(2001));
    CHECK(sync_task.applyMessageAction(2001,smartui::SyncAction::Read));
    CHECK(!sync_task._important_notify_active && callbacks==5);
    // Reading an evicted opened detail closes only that saved detail, not B.
    add(sync_inbox,3000,3);sync_inbox.handleInput(KEY_ENTER);
    for(uint32_t gen=3001;gen<3006;++gen)add(sync_inbox,gen,4);
    CHECK(sync_inbox.detail_open && sync_inbox.opened_entry.generation==3000);
    CHECK(sync_task.applyMessageAction(3000,smartui::SyncAction::Read));
    CHECK(!sync_inbox.detail_open && sync_inbox.unreadPreviewCount()==4);
    // Local physical dismissal reports both independent active/pending generations.
    sync_task._important_notify_active=true;sync_task._important_notify_generation=3004;
    sync_task._ble_smart_notify_flags=1;sync_task._ble_smart_notify_generation=3005;
    sync_task.dismissCurrentMessageNotifications();
    CHECK(callbacks==7 && !sync_task._important_notify_active && sync_task._ble_smart_notify_flags==0);
    CHECK(sync_inbox.unreadPreviewCount()==4);
    // Resetting the opt-in flag never clears unread state.
    sync_task._explicit_read_policy=true;
    sync_task._important_notify_active=true;sync_task._important_notify_generation=3005;
    sync_task.messageTransferState(3005,1,UIMessageTransferState::queuedToCompanion,0);
    CHECK(sync_task._important_notify_active && sync_inbox.unreadPreviewCount()==4);
    sync_task._explicit_read_policy=false;
    CHECK(sync_inbox.unreadPreviewCount()==4);
  }
  {
    // Physical clear-all must reverse-sync every retained ID. Delivery callbacks
    // (including queue count zero) must never take this human-read path.
    UITask bulk;
    MsgPreviewScreen inbox(&bulk,&clock);
    bulk.msg_preview=&inbox;bulk.curr=&inbox;
    static smartui::SmartUiSync ledger;
    static unsigned calls=0;
    static uint32_t ids[8]={};
    CHECK(ledger.begin(123));
    bulk._sync_action_callback=[](uint32_t gen,smartui::SyncAction action,uint32_t value) {
      CHECK(action==smartui::SyncAction::Read && value==0 && calls<8);
      ids[calls++]=gen;
      CHECK(ledger.apply(gen,action,value)==smartui::SyncResult::Applied);
    };
    for(uint32_t gen=4001;gen<=4003;++gen) {
      add(inbox,gen,1);CHECK(ledger.noteMessage(gen,1)==smartui::SyncResult::Applied);
    }
    CHECK(bulk.applyMessageAction(4001,smartui::SyncAction::Snooze,900));
    CHECK(ledger.apply(4001,smartui::SyncAction::Snooze,900)==smartui::SyncResult::Applied);
    bulk._important_notify_active=true;bulk._important_notify_generation=4003;
    bulk._ble_smart_notify_flags=1;bulk._ble_smart_notify_generation=4002;
    for(unsigned explicit_mode=0;explicit_mode<2;++explicit_mode) {
      bulk._explicit_read_policy=explicit_mode!=0;
      bulk.msgRead(0,false);bulk.msgRead(2,false);
      CHECK(inbox.unreadPreviewCount()==3 && calls==0 && ledger.revision()==4);
      CHECK(bulk._important_notify_active && bulk._ble_smart_notify_generation==4002);
    }
    bulk._explicit_read_policy=false;
    bulk._important_notify_generation=0;bulk._ble_smart_notify_generation=0;bulk._ble_smart_notify_flags=0;
    bulk.msgRead(0,false);bulk.msgRead(2,false);
    CHECK(inbox.unreadPreviewCount()==3 && calls==0 && ledger.revision()==4);
    bulk._important_notify_generation=4003;bulk._ble_smart_notify_generation=4002;bulk._ble_smart_notify_flags=1;
    bulk.msgRead(0);
    CHECK(inbox.unreadPreviewCount()==0 && bulk._msgcount==0 && !inbox.detail_open);
    CHECK(!bulk._important_notify_active && bulk._ble_smart_notify_generation==0);
    CHECK(calls==3 && ids[0]==4001 && ids[1]==4002 && ids[2]==4003 && ledger.revision()==7);
    for(uint32_t gen=4001;gen<=4003;++gen) {
      smartui::SyncRecord record;CHECK(ledger.find(gen,record));
      CHECK(record.state==smartui::SYNC_READ && record.snooze_seconds==0);
    }
    bulk.msgRead(0);CHECK(calls==3 && ledger.revision()==7);
    now+=900001;bulk.snoozedMessageHandler();CHECK(bulk.reminder_calls==0);
    // Nonlocal buffer reset and unknown generation do not fabricate read IDs.
    add(inbox,4004,1);CHECK(ledger.noteMessage(4004,1)==smartui::SyncResult::Applied);
    inbox.clearPreviews(false);CHECK(calls==3);
    smartui::SyncRecord untouched;CHECK(ledger.find(4004,untouched) && untouched.state==0);
    add(inbox,0,1);bulk.msgRead(0);CHECK(calls==3 && inbox.unreadPreviewCount()==0);
  }
'''
    return code.replace('  printf("PASS %u production inbox/actions/per-message-snooze checks\\n",checks);',
                        extra + '\n  printf("PASS %u production shared UI sync-action assertions\\n",checks);')


def battery_source():
    source = (ROOT / "examples/companion_radio/ui-new/UITask.cpp").read_text(encoding="utf-8")
    code = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "BatteryDisplayCache.h"
#define UI_BATTERY_SAMPLE_MILLIS 1000
static uint32_t now=100;
static uint32_t millis() { return now; }
struct Board {
  unsigned reads=0;
  uint16_t values[3]={4000,5000,3999};
  uint16_t getBattMilliVolts() { return values[reads++ % 3]; }
};
struct UITask {
  Board* _board=nullptr;
  mutable smartui::BatteryDisplayCache _battery_display;
  mutable uint16_t _battery_sample_mv=0;
  mutable uint32_t _battery_sampled_at=0;
  mutable bool _battery_sample_valid=false;
  void invalidateBatteryCache();
  uint16_t getBattMilliVolts() const;
  bool peekBatterySample(uint16_t&,uint32_t&) const;
  smartui::BatteryReading readSafetyBattery() const;
};
'''
    code += '\n'.join(function(source, name) for name in (
        'void UITask::invalidateBatteryCache()', 'uint16_t UITask::getBattMilliVolts() const',
        'bool UITask::peekBatterySample(', 'smartui::BatteryReading UITask::readSafetyBattery() const'))
    return code + r'''
static unsigned checks=0;
#define CHECK(x) do { ++checks; assert(x); } while(0)
int main() {
  Board board;UITask task;task._board=&board;
  uint16_t mv=77;uint32_t at=77;
  CHECK(!task.peekBatterySample(mv,at) && mv==0 && at==0 && board.reads==0);
  CHECK(task.getBattMilliVolts()==4000 && board.reads==3);
  CHECK(task.peekBatterySample(mv,at) && mv==4000 && at==100);
  now=150;
  for(unsigned i=0;i<10000;++i) CHECK(task.peekBatterySample(mv,at) && mv==4000 && at==100);
  CHECK(board.reads==3);
  board.values[0]=3800;board.values[1]=0;board.values[2]=3800;
  CHECK(task.readSafetyBattery().millivolts==3800 && board.reads==6);
  CHECK(task.peekBatterySample(mv,at) && mv==3800 && at==150);
  now=200;
  CHECK(task.getBattMilliVolts()==4000 && board.reads==6);
  CHECK(task.peekBatterySample(mv,at) && mv==3800 && at==150); // Cached display read isn't a new sample.
  now=1100;board.values[0]=3700;board.values[1]=3700;board.values[2]=3701;
  CHECK(task.getBattMilliVolts()==3700 && board.reads==9);
  CHECK(task.peekBatterySample(mv,at) && mv==3700 && at==1100);
  task.invalidateBatteryCache();
  CHECK(!task.peekBatterySample(mv,at) && mv==0 && at==0 && board.reads==9);
  CHECK(task.getBattMilliVolts()==3700 && board.reads==12);
  board.values[0]=board.values[1]=board.values[2]=0;now=1110;
  CHECK(!task.readSafetyBattery().valid && board.reads==15);
  CHECK(!task.peekBatterySample(mv,at) && mv==0 && at==1110);
  UITask absent;CHECK(!absent.peekBatterySample(mv,at));
  CHECK(!absent.readSafetyBattery().valid);
  CHECK(!absent.peekBatterySample(mv,at) && mv==0 && at==0);
  now=UINT32_MAX;board.values[0]=board.values[1]=board.values[2]=3600;
  CHECK(task.readSafetyBattery().valid);
  CHECK(task.peekBatterySample(mv,at) && mv==3600 && at==UINT32_MAX);
  now=1;CHECK(task.peekBatterySample(mv,at) && at==UINT32_MAX);
  printf("PASS %u production cached battery observation/no-extra-ADC assertions\n",checks);
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix="smartui-sync-") as directory:
        folder = Path(directory)
        ui = folder / "sync_ui.cpp"
        ui.write_text(ui_source(), encoding="utf-8")
        battery = folder / "sync_battery.cpp"
        battery.write_text(battery_source(), encoding="utf-8")
        compiler = shutil.which("g++") or shutil.which("clang++")
        flags = ["-std=c++17", "-O1", "-Wall", "-Wextra", "-Werror"]
        if os.environ.get("SMARTUI_TEST_SANITIZE") == "1":
            flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
        includes = [ROOT / "examples/companion_radio", ROOT / "examples/companion_radio/ui-new", ROOT / "src"]
        for suite in (ROOT / "tools/test_smartui_sync.cpp", ui, battery):
            output = folder / suite.stem
            paths = [suite, ROOT / "examples/companion_radio/SmartUiSync.cpp"]
            if compiler:
                build = [compiler, *flags, *["-I" + str(path) for path in includes], *map(str, paths), "-o", str(output)]
                execute = [str(output)]
            elif os.name == "nt":
                def linux(path):
                    return subprocess.check_output(["wsl", "--exec", "wslpath", "-a", str(path)], text=True).strip()
                build = ["wsl", "--exec", "g++", *flags, *["-I" + linux(path) for path in includes],
                         *map(linux, paths), "-o", linux(output)]
                execute = ["wsl", "--exec", linux(output)]
            else:
                raise RuntimeError("Host C++ compiler required")
            subprocess.run(build, check=True, timeout=60)
            subprocess.run(execute, check=True, timeout=30)


if __name__ == "__main__":
    main()
