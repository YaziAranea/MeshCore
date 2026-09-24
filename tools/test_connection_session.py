#!/usr/bin/env python3
"""Run production MyMesh local-session boundaries against deterministic stubs."""
from pathlib import Path
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def function(source, name):
    begin = source.index("void MyMesh::" + name + "(")
    brace = source.index("{", begin)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[begin:end]


def main():
    source = (ROOT / "examples/companion_radio/MyMesh.cpp").read_text(encoding="utf-8")
    reset = function(source, "resetLocalAppSession")
    receive = function(source, "checkSerialInterface")
    loop = function(source, "loop")
    assert loop.index("sessionGeneration()") < loop.index("BaseChatMesh::loop()")
    assert "offline_queue" not in reset.split("// cmd_frame")[0]
    harness = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#define SMARTUI_CONNECTION_SELECTOR 1
#define RESP_CODE_CONTACT 3
#define RESP_CODE_END_OF_CONTACTS 4
static unsigned freed=0;
void checked_free(void* p) {
  for(unsigned i=0;i<4;++i) assert(static_cast<uint8_t*>(p)[i]==0);
  ++freed; std::free(p);
}
#define free checked_free
struct FakeSerial {
  uint32_t generation=1, next_generation=1;
  uint8_t next[4]={}; size_t next_len=0;
  uint32_t sessionGeneration() const {return generation;}
  size_t checkRecvFrame(uint8_t* out) {
    generation=next_generation; memcpy(out,next,next_len);
    size_t len=next_len; next_len=0; return len;
  }
  bool isWriteBusy() const {return false;}
  size_t writeFrame(const uint8_t*,size_t n) {return n;}
};
struct FakeUi {bool connected=true; void setHasConnection(bool b){connected=b;}};
struct ContactInfo {uint32_t lastmod=0;};
struct Iter {template<typename T> bool hasNext(T*,ContactInfo&){return false;}};
struct MyMesh {
  FakeSerial* _serial; FakeUi* _ui;
  uint32_t last_local_session_generation=1;
  bool _iter_started=true; uint32_t _iter_filter_since=9,_most_recent_lastmod=8;
  uint8_t app_target_ver=7; unsigned pending=5;
  uint8_t* sign_data=nullptr; uint32_t sign_data_len=0;
  uint8_t out_frame[32]={},cmd_frame[32]={};
  struct {uint8_t key[16];} send_scope;
  bool send_unscoped=true; Iter _iter;
  int offline_queue_len=2; uint8_t inbox[2]={41,42};
  unsigned handled=0, resets=0;
  void clearPendingReqs(){pending=0;++resets;}
  void writeContactRespFrame(uint8_t,const ContactInfo&){}
  void handleCmdFrame(size_t len){
    ++handled; assert(len>0);
    if(cmd_frame[0]==22) app_target_ver=cmd_frame[1];
  }
  void resetLocalAppSession(); void checkSerialInterface();
};
'''
    harness += reset + "\n" + receive + r'''
int main(){
  FakeSerial serial; FakeUi ui; MyMesh m{&serial,&ui};
  memset(m.out_frame,0xee,sizeof m.out_frame);
  memset(m.cmd_frame,0x16,sizeof m.cmd_frame);
  memset(m.send_scope.key,0xcc,sizeof m.send_scope.key);
  m.sign_data=static_cast<uint8_t*>(malloc(4)); m.sign_data_len=4;
  memset(m.sign_data,0x77,4);
  m.resetLocalAppSession();
  assert(freed==1 && !m.sign_data && m.sign_data_len==0);
  assert(!m._iter_started && m._iter_filter_since==0 && m._most_recent_lastmod==0);
  assert(m.app_target_ver==0 && m.pending==0 && !m.send_unscoped && !ui.connected);
  assert(m.cmd_frame[0]==0x16 && m.offline_queue_len==2 && m.inbox[1]==42);
  for(auto c:m.out_frame) assert(c==0);
  for(auto c:m.send_scope.key) assert(c==0);
  // The first USB query establishes the epoch DURING checkRecvFrame.
  serial.next_generation=2; serial.next[0]=22;serial.next[1]=3;serial.next_len=2;
  m.checkSerialInterface();
  assert(m.app_target_ver==3 && m.handled==1 && m.resets==2);
  // APP_START belongs to the same connection: do not erase negotiated version.
  serial.next[0]=1;serial.next_len=1;
  m.checkSerialInterface();
  assert(m.app_target_ver==3 && m.handled==2 && m.resets==2);
  // Disconnect/reconnect can happen between UI loops, with no false-connected gap.
  serial.generation=serial.next_generation=4; m._iter_started=true;m.pending=1;
  serial.next[0]=22;serial.next[1]=4;serial.next_len=2;
  m.checkSerialInterface();
  assert(m.app_target_ver==4 && m.handled==3 && m.resets==3 && m.pending==0);
  assert(m.offline_queue_len==2 && m.inbox[0]==41);
}
'''
    out = ROOT / "qa_outputs/connection-session"
    out.mkdir(parents=True, exist_ok=True)
    cpp = out / "session.cpp"
    binary = out / "session"
    cpp.write_text(harness, encoding="utf-8")
    if os.name == "nt":
        def linux(p):
            return "/mnt/" + p.drive[0].lower() + p.as_posix()[2:]
        build = ["wsl", "--exec", "g++", "-std=c++17", "-O1", linux(cpp), "-o", linux(binary)]
        run = ["wsl", "--exec", linux(binary)]
    else:
        cxx = shutil.which("g++") or shutil.which("clang++")
        if not cxx:
            raise SystemExit("C++ compiler required")
        build = [cxx, "-std=c++17", "-O1", str(cpp), "-o", str(binary)]
        run = [str(binary)]
    subprocess.run(build, check=True, timeout=60)
    subprocess.run(run, check=True, timeout=30)
    print("PASS actual MyMesh session reset, first-query preservation, reconnect and inbox retention")


if __name__ == "__main__":
    main()
