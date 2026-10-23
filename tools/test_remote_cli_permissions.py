"""Exercise local Remote CLI provisioning grammar and production persistence."""
from pathlib import Path
import tempfile
from test_nrf52_flash_led_gate import HostToolchain

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "examples/companion_radio"
HARNESS = r'''
#include "RemoteCliPermissions.h"
#include <cassert>
#include <cstring>
#include <string>
#include <cstdio>
static bool enabled=false, found=true, durable=true;
static unsigned reads=0,writes=0;
static bool read(const uint8_t key[32],bool& value) {
  ++reads; assert(key[0]==0xab && key[31]==0xab); value=enabled; return found;
}
static bool write(const uint8_t key[32],bool value) {
  ++writes; assert(key[0]==0xab && key[31]==0xab);
  if (durable) enabled=value;
  return durable;
}
static std::string run(const std::string& command,bool writable=true,bool busy=false,size_t capacity=157) {
  char reply[158]; memset(reply,0xcc,sizeof(reply)); reply[157]='Z';
  assert(smartui::handleRemoteCliPermissionCommand(command.c_str(),reply,capacity,writable,busy,read,write));
  assert(reply[157]=='Z'); return reply;
}
int main() {
  std::string key;
  for(unsigned i=0;i<32;++i) key+="ab";
  const std::string get="get remote.cli "+key, set="set remote.cli "+key;
  assert(run(get)=="> off");
  assert(run(set+" on",false)=="Error: readonly" && writes==0);
  assert(run(set+" on",true,true)=="Error: busy" && writes==0);
  assert(run(set+" on",true,false,20)=="Error: buffer" && writes==0);
  assert(run(set+" on")=="OK" && enabled && writes==1);
  assert(run(set+" on")=="OK" && writes==1);
  assert(run(get,false,true)=="> on");
  durable=false;
  assert(run(set+" off")=="Error: storage" && enabled && writes==2);
  durable=true;
  assert(run(set+" off")=="OK" && !enabled && writes==3);
  found=false;
  assert(run(set+" on")=="Error: contact not found" && writes==3);
  found=true;
  for (const char* suffix : {"", " 1", " true", " ON", " on ", " on\nreboot", " off now"}) {
    assert(run(set+suffix)=="Error: invalid argument" && writes==3);
  }
  for(size_t n=0;n<64;++n) {
    assert(run("get remote.cli "+key.substr(0,n))=="Error: invalid argument");
    assert(run("set remote.cli "+key.substr(0,n)+" on")!="OK");
  }
  const unsigned before=reads;
  for(size_t at=0;at<64;++at) for(char bad : {'g','/',' ','|','\n','-'}) {
    auto malformed=key; malformed[at]=bad;
    assert(run("set remote.cli "+malformed+" on")=="Error: invalid key");
  }
  assert(reads==before && writes==3);
  assert(run(get+" x")=="Error: invalid argument");
  assert(run(set+std::string(200,'x'))=="Error: invalid argument");
  char output[157]={};
  assert(!smartui::handleRemoteCliPermissionCommand("get remote.client",output,sizeof(output),true,false,read,write));
  assert(!smartui::handleRemoteCliPermissionCommand("get name",output,sizeof(output),true,false,read,write));
  assert(smartui::handleRemoteCliPermissionCommand((set+" on").c_str(),nullptr,0,true,false,read,write));
  assert(writes==3);
  puts("PASS remote CLI permission grammar: full keys, exact scope, guards, no-op, storage errors, malformed input");
}
'''

INTEGRATION = r'''
#include "RemoteCliPermissions.h"
#include <helpers/ContactInfo.h>
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>

struct Clock {
  uint32_t now=1700000000;
  unsigned reads=0;
  uint32_t getCurrentTime() { ++reads; return now; }
};
class BaseChatMesh {
public:
  ContactInfo contacts[2]{};
  int num_contacts=2;
  ContactInfo* lookupContactByPubKey(const uint8_t*,int);
};
class MyMesh : public BaseChatMesh {
public:
  Clock clock;
  bool durable=true;
  unsigned saves=0;
  std::array<ContactInfo,2> saved{};
  Clock* getRTCClock() { return &clock; }
  bool saveContacts() {
    ++saves;
    if (durable) for(unsigned i=0;i<2;++i) saved[i]=contacts[i];
    return durable;
  }
  bool setRemoteCliPermission(const uint8_t pub_key[PUB_KEY_SIZE],bool enabled);
} the_mesh;
struct Controller {
  bool writable=true,busy=false;
  bool deviceApiWritesAllowed() const { return writable; }
  bool deviceApiBusy() const { return busy; }
} connection_controller;
static unsigned fallback_calls=0;
struct Cli {
  bool handle(const char*,char* reply,size_t capacity,bool) {
    ++fallback_calls; snprintf(reply,capacity,"fallback"); return true;
  }
} meshcore_cli;
static bool executeSmartUiCliCommand(const char*,char*,size_t) { return false; }
namespace smartui {
using Executor=bool (*)(const char*,char*,size_t);
bool handleSmartUiConsoleCommand(const char*,char*,size_t,Executor) { return false; }
}
@@PRODUCTION@@

static std::string keyHex(const uint8_t key[32]) {
  const char* digits="0123456789abcdef";
  std::string result;
  for(unsigned i=0;i<32;++i) { result+=digits[key[i]>>4]; result+=digits[key[i]&15]; }
  return result;
}
static bool sameContact(const ContactInfo& a,const ContactInfo& b) {
  return !memcmp(&a,&b,sizeof(a));
}
static std::string dispatch(const std::string& command,bool allow=true,bool through_cli=false) {
  char response[158]; memset(response,0xcc,sizeof(response)); response[157]='Z';
  const bool handled=through_cli
      ? executeMeshCoreCliCommand(command.c_str(),response,157)
      : handleCompanionRemoteCliPermission(command.c_str(),response,157,allow);
  assert(handled && response[157]=='Z' && memchr(response,0,157));
  return response;
}
int main() {
  // Same first 31 bytes: a shortened key lookup would grant the wrong node.
  for(unsigned c=0;c<2;++c) {
    ContactInfo& contact=the_mesh.contacts[c];
    memset(&contact,0,sizeof(contact));
    for(unsigned i=0;i<32;++i) contact.id.pub_key[i]=static_cast<uint8_t>(i*7+3);
    contact.id.pub_key[31]+=c;
    contact.flags=0xef; // favorite, telemetry and unrelated reserved bits; CLI off
    contact.type=1; strcpy(contact.name,c ? "second" : "first");
    contact.lastmod=123; contact.sync_since=444;
    contact.last_advert_timestamp=555; contact.out_path_len=2;
    contact.out_path[0]=0x31; contact.out_path[1]=0x32;
    contact.remote_cli_timestamp=987654;
    the_mesh.saved[c]=contact;
  }
  const ContactInfo first=the_mesh.contacts[0];
  const ContactInfo before=the_mesh.contacts[1];
  const std::string get="get remote.cli "+keyHex(before.id.pub_key);
  const std::string set="set remote.cli "+keyHex(before.id.pub_key);
  assert(dispatch(get)=="> off" && the_mesh.saves==0);
  assert(dispatch(set+" on")=="OK" && the_mesh.saves==1);
  ContactInfo expected=before;
  expected.flags|=0x10; expected.lastmod=the_mesh.clock.now;
  assert(sameContact(the_mesh.contacts[0],first));
  assert(sameContact(the_mesh.contacts[1],expected) && sameContact(the_mesh.saved[1],expected));
  assert(the_mesh.clock.reads==1 && the_mesh.contacts[1].remote_cli_timestamp==987654);
  assert(dispatch(set+" on")=="OK" && the_mesh.saves==1 && the_mesh.clock.reads==1);

  // Gate both caller permission and controller state before invoking the setter.
  assert(dispatch(set+" off",false)=="Error: readonly" && the_mesh.saves==1);
  connection_controller.writable=false;
  assert(dispatch(set+" off")=="Error: readonly" && the_mesh.saves==1);
  assert(dispatch(get)=="> on");
  assert(dispatch(set+" off",true,true)=="Error: readonly" && the_mesh.saves==1);
  connection_controller.writable=true; connection_controller.busy=true;
  assert(dispatch(set+" off")=="Error: busy" && the_mesh.saves==1);
  assert(dispatch(get)=="> on");
  connection_controller.busy=false;

  // Failed persistence must roll back the complete contact, including lastmod
  // and the transient replay watermark, without changing durable permissions.
  the_mesh.durable=false; ++the_mesh.clock.now;
  assert(dispatch(set+" off")=="Error: storage" && the_mesh.saves==2);
  assert(sameContact(the_mesh.contacts[1],expected) && sameContact(the_mesh.saved[1],expected));
  assert(dispatch(get)=="> on");
  the_mesh.durable=true;
  assert(dispatch(set+" off",true,true)=="OK" && the_mesh.saves==3);
  expected.flags&=~0x10; expected.lastmod=the_mesh.clock.now;
  assert(sameContact(the_mesh.contacts[1],expected) && sameContact(the_mesh.saved[1],expected));
  assert(sameContact(the_mesh.contacts[0],first) && fallback_calls==0);

  uint8_t unknown[32]; memcpy(unknown,before.id.pub_key,32); unknown[31]^=0x80;
  assert(dispatch("set remote.cli "+keyHex(unknown)+" on")=="Error: contact not found");
  assert(!the_mesh.setRemoteCliPermission(nullptr,true));
  assert(!the_mesh.setRemoteCliPermission(unknown,true) && the_mesh.saves==3);
  assert(dispatch(get,true,true)=="> off" && fallback_calls==0);
  assert(dispatch("get name",true,true)=="fallback" && fallback_calls==1);
  puts("PASS production Remote CLI provisioning integration: full-key collision, flag isolation, replay watermark preserved, durable save/rollback, caller/controller read-only, busy, CLI routing");
}
'''


def function(source, signature):
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def production_integration():
    mesh = (SOURCE / "MyMesh.cpp").read_text(encoding="utf-8")
    base = (ROOT / "src/helpers/BaseChatMesh.cpp").read_text(encoding="utf-8")
    main = (SOURCE / "main.cpp").read_text(encoding="utf-8")
    methods = [function(base, "ContactInfo* BaseChatMesh::lookupContactByPubKey("),
               function(mesh, "bool MyMesh::setRemoteCliPermission(")]
    for signature in ("static bool readRemoteCliPermission(",
                      "static bool writeRemoteCliPermission(",
                      "static bool handleCompanionRemoteCliPermission(",
                      "bool executeMeshCoreCliCommand("):
        methods.append(function(main, signature))
    assert "connection_hooks.handleRemoteCliPermission = handleCompanionRemoteCliPermission;" in main
    return INTEGRATION.replace("@@PRODUCTION@@", "\n\n".join(methods))


def main():
    toolchain = HostToolchain()
    with tempfile.TemporaryDirectory(prefix="remote-cli-permissions-") as raw:
        folder = Path(raw)
        source, binary = folder / "test.cpp", folder / "test"
        source.write_text(HARNESS, encoding="utf-8")
        toolchain.run("g++", ["-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
            "-I", toolchain.path(SOURCE), toolchain.path(source),
            toolchain.path(SOURCE / "RemoteCliPermissions.cpp"), "-o", toolchain.path(binary)])
        print(toolchain.output(binary), end="")
        # ContactInfo is the production definition; only Arduino/mesh identity
        # dependencies and persistence are host stubs, without firmware changes.
        (folder / "Arduino.h").write_text(
            "#pragma once\n#include <cstdint>\n#include <cstring>\n", encoding="utf-8")
        (folder / "Mesh.h").write_text(
            "#pragma once\n#include <cstdint>\n#define PUB_KEY_SIZE 32\n#define MAX_PATH_SIZE 64\n"
            "namespace mesh { struct Identity { uint8_t pub_key[32]; };\n"
            "struct LocalIdentity { void calcSharedSecret(uint8_t*,const uint8_t*) const {} }; }\n",
            encoding="utf-8")
        integration = folder / "integration.cpp"
        integration.write_text(production_integration(), encoding="utf-8")
        integration_binary = folder / "integration"
        toolchain.run("g++", ["-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
            "-I", toolchain.path(folder), "-I", toolchain.path(ROOT / "src"),
            "-I", toolchain.path(SOURCE), toolchain.path(integration),
            toolchain.path(SOURCE / "RemoteCliPermissions.cpp"), "-o", toolchain.path(integration_binary)])
        print(toolchain.output(integration_binary), end="")


if __name__ == "__main__":
    main()
