#!/usr/bin/env python3
"""Build production sync command service and router; no Arduino dependencies."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

from test_smartui_api import extract_scope

ROOT = Path(__file__).resolve().parents[1]


def queue_source():
    source = (ROOT / "examples/companion_radio/MyMesh.cpp").read_text(encoding="utf-8")
    declarations = r'''
#include "SmartUiSync.h"
#include <helpers/OfflineQueueSync.h>
#include <cassert>
#include <cstdio>
#include <cstring>
#define MAX_FRAME_SIZE 176
#define OFFLINE_QUEUE_SIZE 8
#define MESH_DEBUG_PRINTLN(...) do {} while (0)
static unsigned checks=0;
#define CHECK(x) do { ++checks; assert(x); } while (0)
static smartui::SmartUiSync ledger;
static void noteSmartUiMessage(uint32_t generation,uint8_t flags) { ledger.noteMessage(generation,flags); }
struct MyMesh {
  struct Frame {
    int len=0;uint8_t buf[176]={};uint32_t ui_generation=0;uint8_t ui_flags=0;
    bool isChannelMsg() const { return buf[0]==8; }
  };
  uint32_t before=0xfeedface;
  Frame offline_queue[OFFLINE_QUEUE_SIZE];
  uint32_t after=0xaabbccdd;
  int offline_queue_len=0;
  uint32_t next_ui_message_generation=0;
  bool addToOfflineQueue(const uint8_t[],int,uint32_t=0,uint8_t=0);
  int peekOfflineQueue(uint8_t[],uint32_t&,uint8_t&) const;
  void commitOfflineQueue();
  uint32_t nextUiMessageGeneration();
  int apiPeekOfflineFrame(uint8_t[],uint32_t&,uint8_t&) const;
  bool apiReceiveOfflineFrame(uint32_t);
};
'''
    bodies = "\n".join(extract_scope(source, signature) for signature in (
        "bool MyMesh::addToOfflineQueue(", "int MyMesh::peekOfflineQueue(",
        "void MyMesh::commitOfflineQueue(", "uint32_t MyMesh::nextUiMessageGeneration(",
        "int MyMesh::apiPeekOfflineFrame(", "bool MyMesh::apiReceiveOfflineFrame(",
    ))
    assertions = r'''
int main() {
  CHECK(ledger.begin(123));MyMesh mesh;uint8_t frame[176]={7,1,2};
  CHECK(!mesh.addToOfflineQueue(nullptr,3));CHECK(!mesh.addToOfflineQueue(frame,0));
  CHECK(!mesh.addToOfflineQueue(frame,177));CHECK(mesh.next_ui_message_generation==0);
  const auto a=mesh.nextUiMessageGeneration();CHECK(mesh.addToOfflineQueue(frame,176,a,1));
  CHECK(mesh.addToOfflineQueue(frame,3)); // CLI/telemetry receives ID, but no unread record.
  const auto c=mesh.nextUiMessageGeneration();CHECK(mesh.addToOfflineQueue(frame,3,c,2));
  CHECK(a==1 && c==3 && mesh.offline_queue[1].ui_generation==2);
  CHECK(ledger.recordCount()==2 && ledger.newestEvent()==2);
  uint8_t output[178];memset(output,0xa5,sizeof(output));uint32_t gen=0;uint8_t flags=0;
  CHECK(mesh.apiPeekOfflineFrame(output+1,gen,flags)==176 && gen==1 && flags==1);
  CHECK(output[0]==0xa5 && output[177]==0xa5 && !memcmp(output+1,frame,176));
  CHECK(mesh.offline_queue_len==3);
  CHECK(!mesh.apiReceiveOfflineFrame(0) && !mesh.apiReceiveOfflineFrame(99));
  CHECK(mesh.apiReceiveOfflineFrame(2)); // Receipt of middle item never consumes head.
  CHECK(mesh.offline_queue_len==2 && mesh.offline_queue[0].ui_generation==1 && mesh.offline_queue[1].ui_generation==3);
  CHECK(!mesh.apiReceiveOfflineFrame(2) && mesh.offline_queue_len==2);
  CHECK(mesh.apiReceiveOfflineFrame(1));CHECK(mesh.apiPeekOfflineFrame(output+1,gen,flags)==3 && gen==3 && flags==2);
  CHECK(ledger.newestEvent()==2); // Queue receipt alone never marks metadata read.
  CHECK(mesh.apiReceiveOfflineFrame(3));CHECK(mesh.apiPeekOfflineFrame(output+1,gen,flags)==0 && gen==0 && flags==0);
  for(unsigned i=0;i<8;++i) CHECK(mesh.addToOfflineQueue(frame,3));
  CHECK(!mesh.addToOfflineQueue(frame,3));CHECK(mesh.offline_queue_len==8 && ledger.recordCount()==2);
  mesh.offline_queue[3].buf[0]=8;
  const auto oldest=mesh.offline_queue[0].ui_generation;
  const auto replaced=mesh.offline_queue[3].ui_generation;
  CHECK(mesh.addToOfflineQueue(frame,3));
  CHECK(mesh.offline_queue_len==8 && mesh.offline_queue[0].ui_generation==oldest);
  CHECK(!mesh.apiReceiveOfflineFrame(replaced));
  CHECK(mesh.offline_queue[7].ui_generation==mesh.next_ui_message_generation);
  mesh.next_ui_message_generation=UINT32_MAX-1;
  CHECK(mesh.nextUiMessageGeneration()==UINT32_MAX && mesh.nextUiMessageGeneration()==0);
  const auto count=mesh.offline_queue_len;
  CHECK(!mesh.addToOfflineQueue(frame,3) && mesh.offline_queue_len==count);
  CHECK(mesh.before==0xfeedface && mesh.after==0xaabbccdd);
  printf("PASS %u production MyMesh generation/queue/exact receipt assertions\n",checks);
}
'''
    return declarations + bodies + assertions


def observer_source():
    source = (ROOT / "examples/companion_radio/main.cpp").read_text(encoding="utf-8")
    declarations = r'''
#include "SmartUiApi.h"
#include "SmartUiSyncApi.h"
#include "DeviceSettings.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#define DISPLAY_CLASS HostDisplay
static unsigned checks=0;
#define CHECK(x) do { ++checks; assert(x); } while (0)
static uint32_t now=1000;
static uint32_t millis() { return now; }
static unsigned adc_reads=0,flash_writes=0;
enum class CompanionMode { BLE,USB,WiFi };
struct CompanionStatus { CompanionMode selected=CompanionMode::BLE; bool clientConnected=false,wifiAssociated=false,wifiConfigured=false; };
struct Controller { CompanionStatus current;CompanionStatus status() const { return current; } } connection_controller;
static smartui::DeviceSettingsState settings;
static smartui::DeviceSettingsState readDeviceSettings() { return settings; }
struct Ui {
  bool valid=true;uint16_t mv=4000;uint32_t sampled=1000,generation=0;unsigned peeks=0;
  bool peekBatterySample(uint16_t& value,uint32_t& at) { ++peeks;value=mv;at=sampled;return valid; }
  uint32_t notificationGeneration() const { return generation; }
  uint16_t getBattMilliVolts() { ++adc_reads;return mv; }
  bool savePrefs() { ++flash_writes;return true; }
} ui_task;
struct Interface {
  bool connected=false,pending=false,accept=true;unsigned attempts=0;
  std::vector<std::vector<uint8_t>> frames;
  bool isConnected() const { return connected; }
  bool hasPendingTx() const { return pending; }
  size_t writeFrame(const uint8_t* frame,size_t length) {
    ++attempts;if(!accept)return 0;frames.emplace_back(frame,frame+length);return length;
  }
} interface_manager;
static smartui::SmartUiSync smartui_sync;
static smartui::SmartUiSyncApi smartui_sync_api;
static uint32_t sync_hint_cursor=0,sync_hint_at=0;
'''
    bodies = "\n".join(extract_scope(source, signature) for signature in (
        "static uint32_t syncNotificationGeneration(", "static void serviceSmartUiSync(",
    ))
    assertions = r'''
static void command(const char* input) {
  char reply[480];CHECK(smartui_sync_api.handle(input,reply,sizeof(reply),true));
  CHECK(!strncmp(reply,"OK api ",7));
}
static std::string hint() {
  CHECK(!interface_manager.frames.empty());
  const auto& frame=interface_manager.frames.back();
  CHECK(frame.size()>=13 && frame.size()<=160);
  CHECK(frame[0]==201 && !memcmp(frame.data()+1,"SUI",3) && frame[4]==1);
  CHECK(frame[5]==0 && frame[6]==0 && frame[7]==3 && frame[8]==0 && frame[9]==0 && frame[10]==0);
  CHECK(size_t(frame[11]|uint16_t(frame[12])<<8)==frame.size()-13);
  return std::string(frame.begin()+13,frame.end());
}
static void tick(uint32_t delta=1000) { now+=delta;ui_task.sampled=now;serviceSmartUiSync(); }
int main() {
  CHECK(smartui_sync.begin(UINT64_C(0x0123456789abcdef)));
  smartui_sync_api.begin(smartui_sync,smartui::SyncApiHooks{});
  serviceSmartUiSync();
  CHECK(smartui_sync.newestEvent()==1 && interface_manager.frames.empty() && sync_hint_cursor==1);
  smartui::SyncEvent event;CHECK(smartui_sync.eventAfter(0,event)==smartui::SyncEventResult::Event);
  CHECK(event.kind==smartui::SyncEventKind::Battery && event.value==4000 && event.key==1);
  interface_manager.connected=true;
  settings.volume=4;tick();
  CHECK(interface_manager.frames.empty() && sync_hint_cursor==smartui_sync.newestEvent());
  command("api events subscribe 1");
  CHECK(smartui_sync.noteMessage(1,1)==smartui::SyncResult::Applied);
  serviceSmartUiSync();
  CHECK(interface_manager.frames.size()==1 && hint().find("mask=1")!=std::string::npos);
  CHECK(hint().find("boot=0123456789abcdef")!=std::string::npos);
  CHECK(smartui_sync.noteMessage(2,1)==smartui::SyncResult::Applied);
  tick(249);CHECK(interface_manager.frames.size()==1);
  tick(1);CHECK(interface_manager.frames.size()==2);
  interface_manager.pending=true;
  CHECK(smartui_sync.noteMessage(3,1)==smartui::SyncResult::Applied);
  const auto cursor=sync_hint_cursor;tick(250);
  CHECK(interface_manager.frames.size()==2 && sync_hint_cursor==cursor);
  interface_manager.pending=false;interface_manager.accept=false;serviceSmartUiSync();
  CHECK(interface_manager.frames.size()==2 && sync_hint_cursor==cursor);
  const auto attempts=interface_manager.attempts;
  interface_manager.accept=true;tick(249);CHECK(interface_manager.attempts==attempts);
  tick(1);CHECK(interface_manager.frames.size()==3 && sync_hint_cursor==smartui_sync.newestEvent());
  command("api events subscribe 2");
  CHECK(smartui_sync.noteMessage(4,1)==smartui::SyncResult::Applied);tick();
  CHECK(interface_manager.frames.size()==3 && sync_hint_cursor==smartui_sync.newestEvent());
  settings.melody=8;tick();CHECK(interface_manager.frames.size()==4 && hint().find("mask=2")!=std::string::npos);
  command("api events subscribe 4");
  connection_controller.current.selected=CompanionMode::USB;connection_controller.current.clientConnected=true;
  tick();CHECK(interface_manager.frames.size()==5 && hint().find("mask=4")!=std::string::npos);
  command("api events subscribe 8");
  auto revision=smartui_sync.newestEvent();
  for(unsigned i=1;i<=4;++i) { ui_task.mv=4000-i*10;tick();CHECK(smartui_sync.newestEvent()==revision); }
  ui_task.mv=3950;tick();
  CHECK(smartui_sync.newestEvent()==revision+1 && interface_manager.frames.size()==6 && hint().find("mask=8")!=std::string::npos);
  ui_task.mv=3300;tick();revision=smartui_sync.newestEvent();
  CHECK(smartui_sync.eventAfter(revision-1,event)==smartui::SyncEventResult::Event && event.key==2 && event.value==3300);
  ui_task.mv=3350;tick();revision=smartui_sync.newestEvent();
  CHECK(smartui_sync.eventAfter(revision-1,event)==smartui::SyncEventResult::Event && event.key==2);
  ui_task.mv=3400;tick();revision=smartui_sync.newestEvent();
  CHECK(smartui_sync.eventAfter(revision-1,event)==smartui::SyncEventResult::Event && event.key==1);
  ui_task.valid=false;tick();revision=smartui_sync.newestEvent();
  CHECK(smartui_sync.eventAfter(revision-1,event)==smartui::SyncEventResult::Event && event.key==3 && event.value==0);
  const auto invalid_revision=revision;tick();CHECK(smartui_sync.newestEvent()==invalid_revision);
  ui_task.valid=true;tick();CHECK(smartui_sync.newestEvent()==invalid_revision+1);
  now+=121000;serviceSmartUiSync();revision=smartui_sync.newestEvent();
  CHECK(smartui_sync.eventAfter(revision-1,event)==smartui::SyncEventResult::Event && event.key==3);
  command("api events subscribe 1");ui_task.generation=55;tick();
  CHECK(hint().find("mask=1")!=std::string::npos);
  ui_task.generation=0;tick();revision=smartui_sync.newestEvent();
  CHECK(smartui_sync.eventAfter(revision-1,event)==smartui::SyncEventResult::Event && event.kind==smartui::SyncEventKind::Notification && event.value==0);
  // Subscription is opt-in. Session reset preserves journal but prevents future pushes.
  smartui_sync_api.resetSession();auto frames=interface_manager.frames.size();
  CHECK(smartui_sync.noteMessage(5,1)==smartui::SyncResult::Applied);tick();
  CHECK(interface_manager.frames.size()==frames && sync_hint_cursor==smartui_sync.newestEvent());
  command("api events subscribe 15");interface_manager.connected=false;
  CHECK(smartui_sync.noteMessage(6,1)==smartui::SyncResult::Applied);tick();
  CHECK(interface_manager.frames.size()==frames && sync_hint_cursor==smartui_sync.newestEvent());
  interface_manager.connected=true;tick();CHECK(interface_manager.frames.size()==frames);
  // Journal overflow yields coalesced resnapshot hint, not a fabricated event stream.
  interface_manager.pending=true;
  for(unsigned i=0;i<40;++i) CHECK(smartui_sync.emitSetting(1,i));
  tick();CHECK(interface_manager.frames.size()==frames);
  interface_manager.pending=false;serviceSmartUiSync();
  CHECK(interface_manager.frames.size()==frames+1 && hint().find("mask=15")!=std::string::npos);
  // Hash persisted float representations without undefined numeric conversion.
  // Observation must remain safe even before preference repair normalizes them.
  const uint32_t adc_bits[]={0x7fc00000U,0x7f800000U,0x80000000U,0U};
  for(const auto bits:adc_bits) {
    memcpy(&settings.adc_override,&bits,sizeof(bits));
    revision=smartui_sync.newestEvent();tick();
    CHECK(smartui_sync.newestEvent()==revision+1);
    CHECK(smartui_sync.eventAfter(revision,event)==smartui::SyncEventResult::Event && event.kind==smartui::SyncEventKind::Setting);
  }
  CHECK(adc_reads==0 && flash_writes==0 && ui_task.peeks>0);
  printf("PASS %u production observer opt-in/mask/backpressure/battery/no-ADC assertions\n",checks);
}
'''
    return declarations + bodies + assertions


def main():
    source = ROOT / "examples/companion_radio"
    paths = [ROOT / "tools/test_smartui_sync_api.cpp", source / "SmartUiSync.cpp",
             source / "SmartUiSyncApi.cpp", source / "SmartUiApi.cpp"]
    compiler = shutil.which("g++") or shutil.which("clang++")
    flags = ["-std=c++17", "-O1", "-Wall", "-Wextra", "-Werror"]
    if os.environ.get("SMARTUI_TEST_SANITIZE") == "1":
        flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    with tempfile.TemporaryDirectory(prefix="smartui-sync-api-") as directory:
        queue = Path(directory) / "sync_queue.cpp"
        queue.write_text(queue_source(), encoding="utf-8")
        observer = Path(directory) / "sync_observer.cpp"
        observer.write_text(observer_source(), encoding="utf-8")
        for suite, selector in ((paths[0], 0), (paths[0], 1), (queue, 1), (observer, 1)):
            output = Path(directory) / f"{suite.stem}_{selector}"
            suite_paths = [suite, *paths[1:]]
            feature = f"-DSMARTUI_CONNECTION_SELECTOR={selector}"
            includes = [source, ROOT / "src"]
            if compiler:
                build = [compiler, *flags, feature, *["-I" + str(path) for path in includes], *map(str, suite_paths), "-o", str(output)]
                execute = [str(output)]
            elif os.name == "nt":
                def linux(path):
                    return subprocess.check_output(["wsl", "--exec", "wslpath", "-a", str(path)], text=True).strip()
                build = ["wsl", "--exec", "g++", *flags, feature, *["-I" + linux(path) for path in includes],
                         *map(linux, suite_paths), "-o", linux(output)]
                execute = ["wsl", "--exec", linux(output)]
            else:
                raise RuntimeError("Host C++ compiler required")
            subprocess.run(build, check=True, timeout=60)
            subprocess.run(execute, check=True, timeout=30)


if __name__ == "__main__":
    main()
