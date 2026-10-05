"""Execute the production companion AGC scheduler with a fake clock/radio.

No physical radio, current-consumption or packet-delivery claims.
"""
from pathlib import Path
from test_ui_sessions_v006 import function, run_cpp

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = (ROOT / "examples/companion_radio/MyMesh.cpp").read_text(encoding="utf-8")
    loop = function(source, "void MyMesh::loop()")
    assert loop.index("servicePeriodicAgcReset(false)") < loop.index("BaseChatMesh::loop()")
    assert loop.index("servicePeriodicAgcReset(true)") > loop.index("checkSerialInterface()")
    assert loop.index("servicePeriodicAgcReset(true)") > loop.index("updateAutoAdvertTimer()")
    assert "periodic_agc" not in function(source, "bool MyMesh::hasPendingWork()")
    methods = "\n".join(function(source, name) for name in (
        "bool MyMesh::supportsPeriodicAgcReset()",
        "void MyMesh::logTx(",
        "void MyMesh::servicePeriodicAgcReset("))
    prelude = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <initializer_list>
#include <helpers/PeriodicAgcPolicy.h>
#define MAX_TRANS_UNIT 255
#define PAYLOAD_TYPE_TRACE 9
#define SEND_TIMEOUT_BASE_MILLIS 500
#define DIRECT_SEND_PERHOP_FACTOR 6.0f
#define DIRECT_SEND_PERHOP_EXTRA_MILLIS 250
namespace mesh {
struct Packet { bool flood=true; uint8_t path_len=1, type=0;
  uint16_t payload_len=0; uint8_t payload[600]={};
  bool isRouteFlood() const { return flood; }
  uint8_t getPayloadType() const { return type; }
};
}
struct Radio {
  bool supported=true, active=false, receive=true, accept=true;
  unsigned requests=0, cancellations=0, air_len=0;
  bool supportsAgcMaintenance() const { return supported; }
  bool requestAgcMaintenance() { ++requests; if(accept)active=true; return accept; }
  void cancelAgcMaintenance() { if(active)++cancellations; active=false; }
  bool isAgcMaintenanceActive() const { return active; }
  bool isInRecvMode() const { return receive; }
  uint32_t getEstAirtimeFor(int len) { air_len=len; return 1000; }
} radio_driver;
struct MyMesh {
  smartui::PeriodicAgcPolicy periodic_agc;
  struct Prefs { uint8_t agc_reset_enabled=0; } _prefs;
  struct Clock { uint32_t now=0; uint32_t getMillis(){return now;} } clock;
  Clock* _ms=&clock;
  struct Manager { int queued=0; int getOutboundTotal(){return queued;} } manager;
  Manager* _mgr=&manager;
  struct Link { bool active=false; } link_test;
  Radio* _radio=&radio_driver;
  bool storage_recovery_required=false, _cli_rescue=false;
  bool supportsPeriodicAgcReset() const;
  void logTx(mesh::Packet*,int);
  void servicePeriodicAgcReset(bool);
  uint32_t calcFloodTimeoutMillisFor(uint32_t t) const { return 500+16*t; }
  uint32_t calcDirectTimeoutMillisFor(uint32_t t,uint8_t path) const {
    return 500+(6*t+250)*((path&63)+1);
  }
};
'''
    tests = r'''
static unsigned checks=0;
#define CHECK(x) do { ++checks; assert(x); } while(0)
int main() {
  smartui::PeriodicAgcPolicy p;
  CHECK(!p.ready(100000,false));
  p.setEnabled(true,100);
  CHECK(!p.ready(60099,false)); CHECK(p.ready(60100,false));
  CHECK(!p.ready(60100,true)); CHECK(p.ready(60100,false));
  p.attempted(60100);
  CHECK(!p.ready(120099,false)); CHECK(p.ready(120100,false));
  p.deferForReply(120100,10000);
  p.deferForReply(120101,1); // A shorter guard never truncates a longer reply.
  CHECK(!p.ready(130099,false)); CHECK(p.ready(130100,false));
  p.deferForReply(130100,20000); p.deferForReply(130101,30000);
  CHECK(!p.ready(160100,false)); CHECK(p.ready(160101,false));
  p.setEnabled(false,160101); CHECK(!p.ready(999999,false));
  p.setEnabled(true,999999);
  CHECK(!p.ready(1059998,false)); CHECK(p.ready(1059999,false));
  // Timestamp zero is valid; both interval and reply guards survive wrap.
  smartui::PeriodicAgcPolicy wrap;
  const uint32_t start=0xfffffff0U;
  wrap.setEnabled(true,start);
  CHECK(!wrap.ready(start+59999U,false)); CHECK(wrap.ready(start+60000U,false));
  wrap.deferForReply(0xfffffff0U,60001);
  CHECK(!wrap.ready(start+60000U,false)); CHECK(wrap.ready(start+60001U,false));
  wrap.attempted(0); CHECK(!wrap.ready(59999,false)); CHECK(wrap.ready(60000,false));
  // A reply begun while OFF still protects an immediate later enable.
  smartui::PeriodicAgcPolicy late;
  late.deferForReply(0,120000); late.setEnabled(true,1);
  CHECK(!late.ready(60001,false)); CHECK(late.ready(120000,false));

  MyMesh m;
#ifdef USE_SX1262
  CHECK(m.supportsPeriodicAgcReset());
  m.clock.now=100000; m.servicePeriodicAgcReset(true);
  CHECK(radio_driver.requests==0);
  m._prefs.agc_reset_enabled=1; m.servicePeriodicAgcReset(false);
  m.clock.now=159999; m.servicePeriodicAgcReset(true);
  CHECK(radio_driver.requests==0);
  m.clock.now=160000;
  m.manager.queued=1; m.servicePeriodicAgcReset(true); CHECK(!radio_driver.requests);
  m.manager.queued=0; m.link_test.active=true;
  m.servicePeriodicAgcReset(true); CHECK(!radio_driver.requests);
  m.link_test.active=false; radio_driver.receive=false;
  m.servicePeriodicAgcReset(true); CHECK(!radio_driver.requests);
  radio_driver.receive=true;
  m.servicePeriodicAgcReset(false); CHECK(!radio_driver.requests);
  radio_driver.accept=false;
  m.servicePeriodicAgcReset(true); CHECK(radio_driver.requests==1 && !radio_driver.active);
  radio_driver.accept=true;
  m.servicePeriodicAgcReset(true); CHECK(radio_driver.requests==2 && radio_driver.active);
  m.clock.now+=60000;
  m.servicePeriodicAgcReset(true); CHECK(radio_driver.requests==2); // no overlapping procedure
  m._prefs.agc_reset_enabled=0; m.servicePeriodicAgcReset(false);
  CHECK(!radio_driver.active && radio_driver.cancellations==1);
  m._prefs.agc_reset_enabled=1; m.servicePeriodicAgcReset(false);
  m.clock.now+=60000;
  // Actual TX completion protects ACK/response even if the minute is due.
  mesh::Packet packet;
  m.logTx(&packet,5); CHECK(radio_driver.air_len==MAX_TRANS_UNIT);
  m.servicePeriodicAgcReset(true); CHECK(radio_driver.requests==2);
  m.clock.now+=16499; m.servicePeriodicAgcReset(true); CHECK(radio_driver.requests==2);
  ++m.clock.now; m.servicePeriodicAgcReset(true); CHECK(radio_driver.requests==3);
  radio_driver.active=false;
  m.clock.now+=60000;
  packet.flood=false; packet.path_len=0x80|63; // multi-byte path: low six bits count hops
  m.logTx(&packet,5);
  m.clock.now+=400499; m.servicePeriodicAgcReset(true); CHECK(radio_driver.requests==3);
  ++m.clock.now; m.servicePeriodicAgcReset(true); CHECK(radio_driver.requests==4);
  m.storage_recovery_required=true; m.servicePeriodicAgcReset(false);
  CHECK(!radio_driver.active && radio_driver.cancellations==2);
  m.storage_recovery_required=false; m.servicePeriodicAgcReset(false);
  m.clock.now+=60000; m._cli_rescue=true; m.servicePeriodicAgcReset(true);
  CHECK(radio_driver.requests==4);
  m._cli_rescue=false; radio_driver.supported=false; m.servicePeriodicAgcReset(true);
  CHECK(!m.supportsPeriodicAgcReset() && radio_driver.requests==4);
  radio_driver.supported=true; m._prefs.agc_reset_enabled=255;
  m.servicePeriodicAgcReset(true); CHECK(radio_driver.requests==4);
  // Trace path is in payload, including multi-byte hashes and >=64 hops.
  for (unsigned bits=0; bits<4; ++bits) {
    for (unsigned hops : {1U,8U,63U,64U}) {
      MyMesh trace;
      trace._prefs.agc_reset_enabled=1;
      trace.servicePeriodicAgcReset(false);
      trace.clock.now=60000;
      packet.type=PAYLOAD_TYPE_TRACE; packet.flood=false; packet.path_len=0;
      packet.payload[8]=bits; packet.payload_len=9+(hops<<bits);
      trace.logTx(&packet,5);
      const uint32_t wait=500+6250*(hops+1);
      trace.clock.now+=wait-1;
      const unsigned before=radio_driver.requests;
      trace.servicePeriodicAgcReset(true); CHECK(radio_driver.requests==before);
      ++trace.clock.now;
      trace.servicePeriodicAgcReset(true); CHECK(radio_driver.requests==before+1);
      radio_driver.active=false;
    }
  }
#else
  CHECK(!m.supportsPeriodicAgcReset());
  m._prefs.agc_reset_enabled=1; m.clock.now=600000;
  m.servicePeriodicAgcReset(true); CHECK(radio_driver.requests==0);
#endif
  printf("PASS %u production AGC scheduling checks\n",checks);
}
'''
    for supported in (True, False):
        defines = "#define USE_SX1262 1\n#define WRAPPER_CLASS Fake\n" if supported else ""
        print(run_cpp(defines + prelude + methods + tests,
                      ROOT / "qa_outputs/periodic-agc", f"scheduler-{int(supported)}"), end="")


if __name__ == "__main__":
    main()
