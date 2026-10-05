#!/usr/bin/env python3
"""Production prefs save/reclaim/commit, with allocation and filesystem faults."""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        if source.startswith('//', end):
            end = source.index('\n', end)
            continue
        if source.startswith('/*', end):
            end = source.index('*/', end + 2) + 2
            continue
        if source[end] in ('"', "'"):
            quote = source[end]
            end += 1
            while source[end] != quote:
                end += 2 if source[end] == '\\' else 1
            end += 1
            continue
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def linux(path):
    path = Path(path).resolve()
    return '/mnt/' + path.drive[0].lower() + path.as_posix()[2:] if os.name == 'nt' else str(path)


HARNESS = r'''
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <map>
#include <memory>
#include <new>
#include <set>
#include <string>
struct Record {
  std::array<char,585> replies{};std::string text;bool valid=true;int marker=1;
  bool operator==(const Record&b)const{return replies==b.replies&&text==b.text&&valid==b.valid&&marker==b.marker;}
};
Record record(const char*message){
  Record r;std::strcpy(r.replies.data(),message);
  r.text="{name:\"node\",lat:0,lon:0,radio:{freq:868},gps:{en:0},repeat:{disable:1},comp:{auto_max:3},smart_ui:{adc:4.9}}";
  r.text.resize(1500,' ');return r;
}
struct FakeFS {
  std::map<std::string,Record> files;
  std::map<std::string,unsigned> fail_open,fail_read,fail_remove,fail_seek,opens,removes;
  std::map<std::string,std::set<unsigned>> fail_open_number;
  unsigned fail_rename_at=0,rename_count=0,write_failures=0,flush_failures=0,corrupt_readbacks=0;
  unsigned mutations=0,save_calls=0,backup_remove_success=0,format_calls=0;
  size_t capacity=100000;int expected_scratch_seed=-1;
  bool exists(const char*path){return files.count(path);}
  bool rejectOpen(const char*path){
    unsigned n=++opens[path];if(fail_open_number[path].erase(n))return true;
    if(fail_open[path]){--fail_open[path];return true;}return false;
  }
  bool remove(const char*path){
    ++removes[path];if(fail_remove[path]){--fail_remove[path];return false;}
    ++mutations;bool ok=files.erase(path)!=0;
    if(ok&&std::string(path)=="/prefs.json.bak")++backup_remove_success;return ok;
  }
  bool rename(const char*from,const char*to){
    if(++rename_count==fail_rename_at)return false;
    auto it=files.find(from);if(it==files.end()||exists(to))return false;
    files[to]=it->second;files.erase(it);++mutations;return true;
  }
  size_t used()const{size_t n=0;for(const auto&i:files)n+=i.second.text.size();return n;}
};
#define FILESYSTEM FakeFS
struct File {
  FakeFS*fs=nullptr;std::string path;size_t offset=0;bool readable=true,opened=true;
  explicit operator bool()const{return fs&&opened&&fs->exists(path.c_str());}
  void flush(){if(fs&&path=="/prefs.json.tmp"&&fs->flush_failures){--fs->flush_failures;fs->files[path].valid=false;}}
  void close(){opened=false;}
  bool seek(size_t pos){if(!*this)return false;if(fs->fail_seek[path]){--fs->fail_seek[path];return false;}offset=pos;return true;}
  int available(){return *this&&readable?int(fs->files[path].text.size()-offset):0;}
  int read(){return available()?uint8_t(fs->files[path].text[offset++]):-1;}
};
File openRead(FakeFS*fs,const char*path){
  if(fs->rejectOpen(path))return {};
  File f{fs,path};if(fs->fail_read[path]){--fs->fail_read[path];f.readable=false;}return f;
}
File openStorageRead(FakeFS*fs,const char*path){return openRead(fs,path);}
static bool prepareScratch(FakeFS*fs,const char*path){return !fs->exists(path)||fs->remove(path);}
static File openScratch(FakeFS*fs,const char*path){
  if(fs->rejectOpen(path))return {};
  fs->files[path]={};++fs->mutations;return {fs,path};
}
struct NodePrefs {
  static bool allocation_fail;static int live_heap;
  char quick_replies[9][65]={};int marker=2;
  static void*operator new(size_t size,const std::nothrow_t&)noexcept{
    if(allocation_fail)return nullptr;void*p=std::malloc(size);if(p)++live_heap;return p;
  }
  static void operator delete(void*p)noexcept{if(p){--live_heap;std::free(p);}}
  static void operator delete(void*p,const std::nothrow_t&)noexcept{operator delete(p);}
  bool saveSerial(File&file){
    if(!file)return false;auto&fs=*file.fs;++fs.save_calls;
    Record r=record(quick_replies[0]);std::memcpy(r.replies.data(),quick_replies,sizeof(quick_replies));r.marker=marker;
    bool ok=fs.used()-fs.files[file.path].text.size()+r.text.size()<=fs.capacity;
    if(fs.write_failures){--fs.write_failures;ok=false;}
    if(!ok){r.valid=false;r.text.resize(100);}fs.files[file.path]=r;++fs.mutations;return ok;
  }
  bool loadSerial(File&file){
    if(!file||!file.readable)return false;auto&r=file.fs->files[file.path];if(!r.valid)return false;
    if(file.path=="/prefs.json.tmp"&&file.fs->expected_scratch_seed>=0)assert(marker==file.fs->expected_scratch_seed);
    std::memcpy(quick_replies,r.replies.data(),sizeof(quick_replies));marker=r.marker;
    if(file.path=="/prefs.json.tmp"&&file.fs->corrupt_readbacks){--file.fs->corrupt_readbacks;quick_replies[0][0]^=1;}
    return true;
  }
};
bool NodePrefs::allocation_fail=false;int NodePrefs::live_heap=0;
'''

TEST = r'''
unsigned checks=0;
#define CHECK(x)do{++checks;if(!(x)){std::fprintf(stderr,"line %d: %s\n",__LINE__,#x);return 1;}}while(0)
void seed(FakeFS&fs){
  fs.files["/prefs.json"]=record("primary");fs.files["/prefs.json.bak"]=record("backup");
  fs.files["/_main.id"]=record("identity");fs.files["/contacts3"]=record("contacts");
  fs.files["/channels2"]=record("channels");fs.files["/new_prefs"]=record("legacy");
}
bool unrelated(const FakeFS&fs,const std::map<std::string,Record>&before){
  for(const char*path:{"/_main.id","/contacts3","/channels2","/new_prefs"}){
    auto it=fs.files.find(path);if(it==fs.files.end()||!(it->second==before.at(path)))return false;
  }return fs.format_calls==0;
}
int main(){
  NodePrefs next;std::strcpy(next.quick_replies[0],"replacement");
  {
    FakeFS fs;seed(fs);auto before=fs.files;DataStore store(fs);
    CHECK(store.savePrefs(next));CHECK(store.getPrefsSaveError()==PrefsSaveError::NONE);CHECK(fs.save_calls==1);
    CHECK(fs.files["/prefs.json.bak"]==before["/prefs.json"]);CHECK(unrelated(fs,before));CHECK(NodePrefs::live_heap==0);
  }
  {
    FakeFS fs;seed(fs);auto before=fs.files;fs.capacity=fs.used()+100;fs.expected_scratch_seed=next.marker;DataStore store(fs);
    CHECK(store.savePrefs(next));CHECK(fs.save_calls==2);CHECK(fs.backup_remove_success==1);
    CHECK(fs.files["/prefs.json.bak"]==before["/prefs.json"]);CHECK(unrelated(fs,before));
    CHECK(std::strcmp(fs.files["/prefs.json"].replies.data(),"replacement")==0);
    CHECK(store.getPrefsSaveError()==PrefsSaveError::NONE);CHECK(NodePrefs::live_heap==0);
  }
  for(unsigned fault=0;fault<5;++fault){
    FakeFS fs;seed(fs);auto before=fs.files;DataStore store(fs);
    if(fault==0)NodePrefs::allocation_fail=true;
    if(fault==1)fs.corrupt_readbacks=1;
    if(fault==2){fs.files["/prefs.json.tmp"]=record("stale");fs.fail_remove["/prefs.json.tmp"]=1;}
    if(fault==3)fs.fail_rename_at=1;if(fault==4)fs.fail_rename_at=2;
    CHECK(!store.savePrefs(next));NodePrefs::allocation_fail=false;
    CHECK(fs.files["/prefs.json"]==before["/prefs.json"]);CHECK(unrelated(fs,before));CHECK(NodePrefs::live_heap==0);
    if(fault<3)CHECK(fs.backup_remove_success==0);
    if(fault==0){CHECK(fs.mutations==0);CHECK(store.getPrefsSaveError()==PrefsSaveError::NO_MEMORY);}
    if(fault==1)CHECK(store.getPrefsSaveError()==PrefsSaveError::VERIFY_CONTENT);
    if(fault==2)CHECK(store.getPrefsSaveError()==PrefsSaveError::SCRATCH_REMOVE);
    if(fault>=3)CHECK(store.getPrefsSaveError()==PrefsSaveError::COMMIT);
  }
  for(unsigned fault=0;fault<10;++fault){
    FakeFS fs;seed(fs);auto backup=fs.files["/prefs.json.bak"];
    if(fault==0)fs.files.erase("/prefs.json");
    if(fault==1)fs.files["/prefs.json"].valid=false;
    if(fault==2)fs.files["/prefs.json"].text="{}";
    if(fault==3)fs.files["/prefs.json"].text="{name:\"n\",radio:{},smart_ui:{}}";
    if(fault==4)fs.fail_open["/prefs.json"]=1;
    if(fault==5)fs.fail_read["/prefs.json"]=1;
    if(fault==6)fs.fail_seek["/prefs.json"]=1;
    if(fault==7)fs.files["/prefs.json"].text="{name:\"n\",lat:0,lon:0,radio:{},gps:{},repeat:{},comp:{},smart_ui:{}}";
    if(fault==8){auto&p=fs.files["/prefs.json"].text;p.replace(p.find("freq:"),5,"wrong:");}
    if(fault==9)fs.files["/prefs.json"].text="{name:\"radio:{freq:868},gps:{en:0},repeat:{disable:1},comp:{auto_max:3},smart_ui:{adc:4.9}\",lat:0,lon:0}";
    auto before=fs.files;fs.write_failures=1;DataStore store(fs);
    CHECK(!store.savePrefs(next));CHECK(fs.files==before);CHECK(fs.save_calls==1);
    CHECK(fs.backup_remove_success==0);CHECK(fs.files["/prefs.json.bak"]==backup);CHECK(NodePrefs::live_heap==0);
  }
  for(unsigned fault=0;fault<4;++fault){
    FakeFS fs;seed(fs);auto before=fs.files;DataStore store(fs);
    if(fault==0)fs.fail_open["/prefs.json.tmp"]=1;if(fault==1)fs.write_failures=1;
    if(fault==2)fs.fail_read["/prefs.json.tmp"]=1;if(fault==3)fs.flush_failures=1;
    CHECK(store.savePrefs(next));CHECK(fs.backup_remove_success==1);CHECK(unrelated(fs,before));
    CHECK(store.getPrefsSaveError()==PrefsSaveError::NONE);CHECK(fs.save_calls<=2);CHECK(NodePrefs::live_heap==0);
  }
  for(unsigned fault=0;fault<3;++fault){
    FakeFS fs;seed(fs);auto before=fs.files;DataStore store(fs);
    if(fault==0)fs.fail_open_number["/prefs.json.tmp"]={2};
    if(fault==1)fs.fail_open_number["/prefs.json.tmp"]={2,4};
    if(fault==2){fs.write_failures=1;fs.fail_open_number["/prefs.json.tmp"]={2};}
    CHECK(store.savePrefs(next)==(fault==0));CHECK(fs.backup_remove_success==1);CHECK(unrelated(fs,before));
    if(fault){CHECK(fs.files["/prefs.json"]==before["/prefs.json"]);CHECK(!fs.exists("/prefs.json.tmp"));}
    if(fault==1)CHECK(store.getPrefsSaveError()==PrefsSaveError::VERIFY_OPEN);
    if(fault==2)CHECK(store.getPrefsSaveError()==PrefsSaveError::SCRATCH_OPEN);
    CHECK(NodePrefs::live_heap==0);
  }
  {
    FakeFS fs;seed(fs);auto before=fs.files;fs.write_failures=2;DataStore store(fs);
    CHECK(!store.savePrefs(next));CHECK(fs.save_calls==2);CHECK(fs.backup_remove_success==1);
    CHECK(fs.files["/prefs.json"]==before["/prefs.json"]);CHECK(unrelated(fs,before));
    CHECK(!fs.exists("/prefs.json.tmp"));CHECK(store.getPrefsSaveError()==PrefsSaveError::WRITE);
    CHECK(store.savePrefs(next));CHECK(store.getPrefsSaveError()==PrefsSaveError::NONE);
  }
  {
    FakeFS fs;seed(fs);auto before=fs.files;fs.write_failures=1;fs.fail_remove["/prefs.json.bak"]=1;DataStore store(fs);
    CHECK(!store.savePrefs(next));CHECK(fs.files==before);CHECK(fs.save_calls==1);CHECK(NodePrefs::live_heap==0);
  }
  {
    FakeFS fs;seed(fs);auto before=fs.files;fs.fail_remove["/prefs.json.bak"]=1;DataStore store(fs);
    CHECK(!store.savePrefs(next));CHECK(fs.files==before);CHECK(fs.save_calls==1);
    CHECK(store.getPrefsSaveError()==PrefsSaveError::COMMIT);CHECK(NodePrefs::live_heap==0);
  }
  {
    FakeFS fs;seed(fs);auto before=fs.files;fs.write_failures=1;fs.fail_remove["/prefs.json.tmp"]=1;DataStore store(fs);
    CHECK(!store.savePrefs(next));CHECK(fs.files["/prefs.json"]==before["/prefs.json"]);
    CHECK(fs.files["/prefs.json.bak"]==before["/prefs.json.bak"]);CHECK(fs.save_calls==1);CHECK(unrelated(fs,before));
  }
  {
    FakeFS fs;seed(fs);auto before=fs.files;fs.write_failures=1;fs.fail_rename_at=2;DataStore store(fs);
    CHECK(!store.savePrefs(next));CHECK(fs.files["/prefs.json"]==before["/prefs.json"]);
    CHECK(store.getPrefsSaveError()==PrefsSaveError::COMMIT);CHECK(unrelated(fs,before));CHECK(NodePrefs::live_heap==0);
  }
  {
    FakeFS fs;seed(fs);fs.write_failures=1;
    fs.files["/prefs.json"].text=" { name: \"n\",lat:0,lon:0,radio: {\n freq:868},gps:{ en:0},repeat:{disable:1},comp:{auto_max:3},smart_ui:{adc:4.9}} ";
    DataStore store(fs);CHECK(store.savePrefs(next));CHECK(fs.backup_remove_success==1);
  }
  CHECK(std::strcmp(next.quick_replies[0],"replacement")==0);CHECK(next.marker==2);
  std::printf("Prefs production transactions/reclaim: %u checks PASS\n",checks);
}
'''


def main():
    source = (ROOT / 'examples/companion_radio/DataStore.cpp').read_text(encoding='utf-8')
    header = (ROOT / 'examples/companion_radio/DataStore.h').read_text(encoding='utf-8')
    enum = function(header, 'enum class PrefsSaveError') + ';\n'
    saving = function(source, 'bool DataStore::savePrefs(')
    assert saving.index('if (!verification)') < saving.index('prepareScratch(')
    assert 'NodePrefs candidate' not in function(source, 'static bool prefsFileValid(')
    store = r'''
class DataStore {
  FakeFS* _fs;PrefsSaveError _prefs_save_error=PrefsSaveError::NONE;
public:
  explicit DataStore(FakeFS&fs):_fs(&fs){}
  bool savePrefs(NodePrefs&prefs);
  PrefsSaveError getPrefsSaveError()const{return _prefs_save_error;}
};
'''
    helpers = '\n'.join(function(source, signature) for signature in (
        'static bool isPrefsKeyChar(', 'static bool prefsHasRootKey(',
        'static bool commitScratch(', 'static bool prefsFileValid(',
        'static bool prefsPrimaryAllowsBackupReclaim('))
    with tempfile.TemporaryDirectory(prefix='quick-reply-prefs-') as folder:
        folder = Path(folder)
        cpp, binary = folder / 'test.cpp', folder / 'test'
        cpp.write_text(HARNESS + enum + store + helpers + saving + '\n#line 1 "CASES"\n' + TEST, encoding='utf-8')
        prefix = ['wsl', '--exec'] if os.name == 'nt' else []
        subprocess.run([*prefix, 'g++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                        '-Wno-misleading-indentation', linux(cpp), '-o', linux(binary)], check=True, timeout=60)
        subprocess.run([*prefix, linux(binary)], check=True, timeout=15)


if __name__ == '__main__':
    main()
