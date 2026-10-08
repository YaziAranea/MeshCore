"""Run production history/phrase/send methods with bounded host-only doubles."""
from pathlib import Path
import argparse
from test_ui_sessions_v006 import function, run_cpp

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'qa_outputs/chat-backend-test1')
    args = parser.parse_args()
    mesh = (ROOT / 'examples/companion_radio/MyMesh.cpp').read_text(encoding='utf-8')
    methods = '\n'.join(function(mesh, name) for name in (
        'void MyMesh::noteChannelChat(',
        'int MyMesh::getRecentChannelMessages(',
        'int MyMesh::getRecentChannelMessagesForChannel(',
        'const char* MyMesh::getQuickReplyOverride(',
        'bool MyMesh::setQuickReplyOverride('))
    code = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <helpers/SmartUiQuickReplies.h>
#define PUB_KEY_SIZE 32
#define RECENT_CHAT_TABLE_SIZE 12
#define OUT_PATH_UNKNOWN 255
namespace mesh { struct Packet { uint8_t path_len=1; bool isRouteFlood(){return true;} float getSNR(){return 3;} }; }
struct RecentChatEntry {
 uint32_t recv_timestamp=0; uint8_t path_len=0,flags=0; int8_t snr_q4=0,rssi=0;
 char origin[32]={},text[160]={}; uint8_t channel_idx=255,channel_identity[32]={};
};
struct ChannelDetails { struct {uint8_t secret[32]={};} channel; };
struct NodePrefs {
 char quick_replies[SMARTUI_QUICK_REPLY_COUNT][SMARTUI_QUICK_REPLY_MAX_BYTES+1]={};
 double node_lat=1.25,node_lon=2.5;
 unsigned unrelated=1234;
};
void splitChannelText(const char* name,const char* text,char* origin,size_t n,char* dest,size_t len) {
 snprintf(origin,n,"%s",name); snprintf(dest,len,"%s",text);
}
class MyMesh {
public:
 struct Clock { uint32_t now=0; uint32_t getCurrentTime(){return now;} } clock;
 RecentChatEntry recent_chat[RECENT_CHAT_TABLE_SIZE];
 uint32_t recent_chat_revision=0; int recent_chat_head=0; int8_t last_rx_rssi=-72;
 ChannelDetails channels[3]; NodePrefs _prefs;
 bool storage_recovery_required=false,_cli_rescue=false,save_ok=true;
 unsigned save_count=0; NodePrefs stored;
 Clock* getRTCClock(){return &clock;}
 int getRouteStatusFlags(int){return 0;}
 bool getChannel(uint8_t i,ChannelDetails& out){if(i>=3)return false;out=channels[i];return true;}
 bool savePrefs(){
   ++save_count; _prefs.node_lat=55.5; _prefs.node_lon=73.25;
   if(save_ok)stored=_prefs;
   return save_ok;
 }
 void noteChannelChat(const char*,mesh::Packet*,const char*,uint8_t);
 int getRecentChannelMessages(RecentChatEntry*,int);
 int getRecentChannelMessagesForChannel(RecentChatEntry*,int,const uint8_t*);
 const char* getQuickReplyOverride(uint8_t)const;
 bool setQuickReplyOverride(uint8_t,const char*);
};
''' + methods + r'''
int main(){
 unsigned checks=0;
 #define CHECK(x) do{++checks;assert(x);}while(0)
 MyMesh m; RecentChatEntry rows[12];
 m.channels[0].channel.secret[0]=1;m.channels[1].channel.secret[0]=2;
 m.channels[2].channel.secret[0]=1; // Alias of the same cryptographic channel.
 CHECK(m.getRecentChannelMessages(rows,12)==0);
 m.noteChannelChat("zero",nullptr,"before clock sync",0);
 CHECK(m.getRecentChannelMessages(rows,12)==1 && rows[0].recv_timestamp==0);
 CHECK(m.recent_chat_revision==1);
 m.noteChannelChat("one",nullptr,"other channel",1);
 CHECK(m.recent_chat_revision==2); // Same second still invalidates the UI cache.
 CHECK(m.getRecentChannelMessagesForChannel(rows,12,m.channels[0].channel.secret)==1);
 CHECK(!strcmp(rows[0].text,"before clock sync"));
 m.channels[0].channel.secret[0]=3; // Reassigned slot must not expose old messages.
 CHECK(m.getRecentChannelMessagesForChannel(rows,12,m.channels[0].channel.secret)==0);
 CHECK(m.getRecentChannelMessagesForChannel(rows,12,m.channels[2].channel.secret)==1);
 CHECK(m.getRecentChannelMessages(rows,1)==1 && !strcmp(rows[0].text,"other channel"));
 CHECK(m.getRecentChannelMessages(nullptr,12)==0);
 CHECK(m.getRecentChannelMessages(rows,-1)==0);
 for(int i=0;i<30;++i){char text[24];snprintf(text,sizeof(text),"message%d",i);m.noteChannelChat("one",nullptr,text,1);}
 CHECK(m.getRecentChannelMessages(rows,12)==12 && !strcmp(rows[0].text,"message29"));
 CHECK(!strcmp(rows[11].text,"message18"));
 m.recent_chat_revision=0xffffffffU;m.noteChannelChat("one",nullptr,"rollover",1);
 CHECK(m.recent_chat_revision==1);
 CHECK(!m.getQuickReplyOverride(0)[0] && !m.getQuickReplyOverride(99)[0]);
 CHECK(m.setQuickReplyOverride(0,"На месте") && !strcmp(m.getQuickReplyOverride(0),"На месте"));
 CHECK(m.save_count==1 && !strcmp(m.stored.quick_replies[0],"На месте"));
 CHECK(m._prefs.node_lat==55.5 && m._prefs.node_lon==73.25);
 m._prefs.node_lat=10.25;m._prefs.node_lon=20.75;
 strcpy(m._prefs.quick_replies[1],"keep another slot");
 // Preserve all bytes, not only the visible phrase, on failed persistence.
 m._prefs.quick_replies[0][SMARTUI_QUICK_REPLY_MAX_BYTES-1]='z';
 char before[SMARTUI_QUICK_REPLY_MAX_BYTES+1];memcpy(before,m._prefs.quick_replies[0],sizeof(before));
 m.save_ok=false;CHECK(!m.setQuickReplyOverride(0,"Подхожу"));
 CHECK(!strcmp(m.getQuickReplyOverride(0),"На месте"));
 CHECK(!memcmp(before,m._prefs.quick_replies[0],sizeof(before)));
 CHECK(m._prefs.node_lat==10.25 && m._prefs.node_lon==20.75);
 CHECK(!strcmp(m._prefs.quick_replies[1],"keep another slot") && m._prefs.unrelated==1234);
 CHECK(m.save_count==2 && !strcmp(m.stored.quick_replies[0],"На месте"));
 m.save_ok=true;CHECK(m.setQuickReplyOverride(0,"") && !m.getQuickReplyOverride(0)[0]);
 CHECK(m._prefs.node_lat==55.5 && m._prefs.node_lon==73.25 && !m.stored.quick_replies[0][0]);
 for(char value:m._prefs.quick_replies[0])CHECK(value==0);
 unsigned saves_before=m.save_count;
 CHECK(!m.setQuickReplyOverride(9,"bad") && !m.setQuickReplyOverride(0,nullptr));
 CHECK(!m.setQuickReplyOverride(0,"bad\nline") && !m.setQuickReplyOverride(0,"\xD0"));
 char long_text[66];memset(long_text,'a',65);long_text[65]=0;
 CHECK(!m.setQuickReplyOverride(0,long_text));CHECK(m.save_count==saves_before);long_text[64]=0;
 CHECK(m.setQuickReplyOverride(8,long_text) && strlen(m.getQuickReplyOverride(8))==64);
 m.storage_recovery_required=true;CHECK(!m.setQuickReplyOverride(8,"unsafe"));
 m.storage_recovery_required=false;m._cli_rescue=true;CHECK(!m.setQuickReplyOverride(8,"unsafe"));
 CHECK(m.save_count==saves_before+1);
 printf("PASS %u production history/filter/revision/phrase checks\n",checks);
}
'''
    print(run_cpp(code, args.out.resolve(), 'chat_backend'), end='')
    base = (ROOT / 'src/helpers/BaseChatMesh.cpp').read_text(encoding='utf-8')
    sender = function(base, 'bool BaseChatMesh::sendGroupMessage(')
    send_code = r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include <cstdint>
#define MAX_TEXT_LEN 160
#define PAYLOAD_TYPE_GRP_TXT 1
namespace mesh { struct GroupChannel{}; struct Packet{}; }
class BaseChatMesh {
 public:
 std::vector<uint8_t> payload;unsigned sent=0;mesh::Packet packet;
 mesh::Packet* createGroupDatagram(int,mesh::GroupChannel&,uint8_t* data,int len){payload.assign(data,data+len);return &packet;}
 void sendFloodScoped(mesh::GroupChannel&,mesh::Packet*){++sent;}
 bool sendGroupMessage(uint32_t,mesh::GroupChannel&,const char*,const char*,size_t);
};
''' + sender + r'''
int main(){
 BaseChatMesh m;mesh::GroupChannel channel;std::string name(31,'A'),text;
 for(int i=0;i<70;++i)text+="Я";
 assert(!m.sendGroupMessage(100,channel,name.c_str(),text.c_str(),text.size()));
 assert(m.sent==0 && m.payload.empty());
 text.resize(126);assert(m.sendGroupMessage(100,channel,name.c_str(),text.c_str(),text.size()));
 assert(m.sent==1 && m.payload.back()==0xAF); // Complete UTF-8 letter.
 text=std::string(127,'B');assert(m.sendGroupMessage(101,channel,name.c_str(),text.c_str(),text.size()));
 assert(m.payload.size()==165);text+='B';
 assert(!m.sendGroupMessage(102,channel,name.c_str(),text.c_str(),text.size()));
 assert(m.sent==2);
 text=std::string(95,'C');assert(m.sendGroupMessage(103,channel,name.c_str(),text.c_str(),text.size()));
 assert(m.payload.size()==5+33+95);
 puts("PASS channel byte budget: oversized text rejected intact, Cyrillic and onboard keyboard preserved");
}
'''
    print(run_cpp(send_code, args.out.resolve(), 'group_text_budget'), end='')


if __name__ == '__main__':
    main()
