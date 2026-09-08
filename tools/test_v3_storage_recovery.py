#!/usr/bin/env python3
"""Exercise the real V3StorageRecovery.h with host ESP/display/flash stubs.

The SHA256 stub controls the digest: this tests authorization/control flow,
NOT cryptography. validate_release_v3.py checks the real packaged SHA256.
No firmware build, hardware access, or formatting of an actual filesystem.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HEADERS = ROOT / "examples/companion_radio/ui-new"
STUB = r'''
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <algorithm>
#include <vector>
#include <utility>

using esp_err_t = int;
constexpr int ESP_OK=0, ESP_FAIL=-1, ESP_ERR_NO_MEM=0x101;
constexpr int ESP_PARTITION_TYPE_DATA=1, ESP_PARTITION_SUBTYPE_DATA_SPIFFS=0x82;
constexpr int PIN_USER_BTN=0, INPUT_PULLUP=1, USER_BTN_PRESSED=0;
struct esp_partition_t { unsigned address, size; char label[17]; bool encrypted; };
using esp_partition_iterator_t = int*;
struct esp_vfs_spiffs_conf_t {
  const char* base_path; const char* partition_label; unsigned max_files;
  bool format_if_mount_failed;
};
struct Stop { int reason; };
static int checks=0;
static void expect_impl(bool value, const char* file, int line) {
  ++checks;
  if (!value) { fprintf(stderr,"failed check %d at %s:%d\n",checks,file,line); throw Stop{99}; }
}
#define expect(value) expect_impl((value),__FILE__,__LINE__)
static unsigned now_ms=0, deadline=20000, flash_size=0x800000;
static int partition_count=1, iterator_value=1, releases=0;
static esp_partition_t part={0x670000,0x180000,"spiffs",false};
static int read_calls=0, fail_read_call=-1;
static size_t read_bytes=0, hash_bytes=0;
static bool exact_digest=true, erased=false;
static int begin_calls=0, format_calls=0, end_calls=0, reg_calls=0, unreg_calls=0;
static int power_calls=0, reboot_calls=0;
static bool default_begin=false, format_result=true;
static std::vector<bool> begin_results;
static std::vector<std::pair<unsigned,bool>> button_events;
static esp_err_t register_result=ESP_FAIL, unregister_result=ESP_OK;
static const char* esp_err_to_name(int) { return "mock-error"; }
struct ESPStub {
  unsigned getFreeHeap() const { return 100000; }
  unsigned getFlashChipSize() const { return flash_size; }
} ESP;
struct SerialStub {
  template<class... A> void printf(const char*, A...) {}
  void println(const char*) {}
} Serial;
struct BoardStub {
  void powerOff() { ++power_calls; throw Stop{1}; }
  void reboot() { ++reboot_calls; throw Stop{2}; }
} board;
struct SPIFFSStub {
  bool begin(bool format) {
    expect(!format); ++begin_calls;
    return static_cast<size_t>(begin_calls)<=begin_results.size()
        ? begin_results[begin_calls-1] : default_begin;
  }
  bool format() { ++format_calls; return format_result; }
  void end() { ++end_calls; }
} SPIFFS;
struct UIColor { static constexpr int warning_txt=1; };
struct DisplayDriver {
  void startFrame() {} void endFrame() {} void setTextSize(int) {}
  void setColor(int) {} int width() const { return 128; }
  void drawTextCentered(int,int,const char*) {}
  void drawTextLeftAlign(int,int,const char*) {}
};
static unsigned millis() { return now_ms; }
static void delay(unsigned delta) {
  now_ms+=delta; if(now_ms>deadline) throw Stop{3};
}
static void pinMode(int,int) {}
static int digitalRead(int) {
  bool pressed=false;
  for(const auto& event: button_events) {
    if(event.first>now_ms) break;
    pressed=event.second;
  }
  return pressed ? USER_BTN_PRESSED : 1;
}
static esp_partition_iterator_t esp_partition_find(int type,int subtype,const char* label) {
  expect(type==1 && subtype==0x82 && label==nullptr);
  return partition_count ? &iterator_value : nullptr;
}
static const esp_partition_t* esp_partition_get(esp_partition_iterator_t) { return &part; }
static esp_partition_iterator_t esp_partition_next(esp_partition_iterator_t) {
  return partition_count>1 ? &iterator_value : nullptr;
}
static void esp_partition_iterator_release(esp_partition_iterator_t) { ++releases; }
static esp_err_t esp_partition_read(const esp_partition_t* p,size_t offset,void* dst,size_t len) {
  expect(p->address==part.address && offset==read_bytes && len==512);
  expect(offset+len<=part.size);
  ++read_calls;
  if(read_calls==fail_read_call) return ESP_FAIL;
  read_bytes+=len; memset(dst,erased ? 0xff : 0xa5,len); return ESP_OK;
}
static esp_err_t esp_vfs_spiffs_register(const esp_vfs_spiffs_conf_t* conf) {
  expect(!conf->format_if_mount_failed && conf->partition_label==nullptr);
  ++reg_calls; return register_result;
}
static esp_err_t esp_vfs_spiffs_unregister(const char* label) {
  expect(label==nullptr); ++unreg_calls; return unregister_result;
}
class SHA256 {
public:
  void update(const void*,size_t len) { hash_bytes+=len; }
  void finalize(void* data,size_t len) {
    expect(len==32 && hash_bytes==part.size);
    const char* value="debe417f42a5bdda6c6e81539f9a3519b4653ab70cefeba01885ecc4b2d3cf5b";
    auto* out=static_cast<unsigned char*>(data);
    for(size_t i=0;i<len;++i) {
      unsigned v=0; sscanf(value+2*i,"%2x",&v); out[i]=static_cast<unsigned char>(v);
    }
    if(!exact_digest || erased) out[0]^=1;
  }
};
'''

SOURCE = r'''
#include "stub.h"
#include "V3StorageRecovery.h"
static DisplayDriver display;
static void reset() {
  now_ms=0; deadline=20000; flash_size=0x800000; partition_count=1;
  releases=0; part={0x670000,0x180000,"spiffs",false};
  read_calls=0; fail_read_call=-1; read_bytes=hash_bytes=0;
  exact_digest=true; erased=false;
  begin_calls=format_calls=end_calls=reg_calls=unreg_calls=0;
  power_calls=reboot_calls=0; default_begin=false; format_result=true;
  begin_results.clear(); button_events.clear();
  register_result=ESP_FAIL; unregister_result=ESP_OK;
  smartui::v3StorageMountError=ESP_FAIL;
}
static unsigned script_time=100;
static void startScript(unsigned start=100) { script_time=start; button_events.clear(); }
static void press(unsigned duration) {
  button_events.push_back({script_time,true});
  button_events.push_back({script_time+duration,false});
  script_time+=duration+100;
}
static void powerScript(unsigned start=100) {
  startScript(start); press(100); press(100); press(2100);
}
template<class F> static void stopped(F operation,int reason) {
  bool caught=false;
  try { operation(); } catch(const Stop& stop) {
    if(stop.reason==99) throw;
    if(stop.reason!=reason) fprintf(stderr,"stop reason %d expected %d at check %d\n",stop.reason,reason,checks);
    expect(stop.reason==reason); caught=true;
  }
  expect(caught);
}
int main() {
  using namespace smartui;
  // Every layout/capacity ambiguity denies authorization before any flash read.
  for(int case_id=0;case_id<8;++case_id) {
    reset();
    switch(case_id) {
      case 0: partition_count=0; break;
      case 1: partition_count=2; break;
      case 2: part.address=0x290000; break;
      case 3: part.size=0x170000; break;
      case 4: strcpy(part.label,"other"); break;
      case 5: part.encrypted=true; break;
      case 6: flash_size=0x400000; break;
      case 7: flash_size=0x7effff; break;
    }
    expect(!v3HasExactFactoryEmptyStorage());
    expect(read_calls==0 && hash_bytes==0 && format_calls==0);
    expect(releases==(case_id==1 ? 1 : 0));
  }
  reset(); expect(v3HasExactFactoryEmptyStorage());
  expect(read_calls==3072 && read_bytes==0x180000 && hash_bytes==read_bytes);
  expect(format_calls==0); // recognition is not formatting itself
  reset(); exact_digest=false; expect(!v3HasExactFactoryEmptyStorage());
  expect(read_bytes==0x180000 && format_calls==0);
  reset(); erased=true; expect(!v3HasExactFactoryEmptyStorage());
  expect(read_bytes==0x180000 && format_calls==0);
  reset(); fail_read_call=10; expect(!v3HasExactFactoryEmptyStorage());
  expect(read_calls==10 && read_bytes==9*512 && hash_bytes==read_bytes && format_calls==0);

  // An already mounted normal installation never reaches the factory guard.
  reset(); default_begin=true; expect(v3MountStorage(&display));
  expect(begin_calls==1 && reg_calls==0 && read_calls==0 && format_calls==0);
  expect(v3StorageMountError==ESP_OK);
  // SDK successful probe must be unregistered before the Arduino retry.
  reset(); begin_results={false,true}; register_result=ESP_OK;
  expect(v3TryMountStorage());
  expect(begin_calls==2 && reg_calls==1 && unreg_calls==1 && format_calls==0);
  expect(v3StorageMountError==ESP_OK);
  reset(); register_result=ESP_OK; unregister_result=ESP_ERR_NO_MEM;
  expect(!v3TryMountStorage());
  expect(begin_calls==1 && unreg_calls==1 && v3StorageMountError==ESP_ERR_NO_MEM);
  reset(); register_result=ESP_ERR_NO_MEM; expect(!v3TryMountStorage());
  expect(unreg_calls==0 && v3StorageMountError==ESP_ERR_NO_MEM && format_calls==0);
  reset(); register_result=ESP_OK; expect(!v3TryMountStorage());
  expect(begin_calls==2 && unreg_calls==1 && v3StorageMountError==ESP_FAIL);

  // Only a successful full digest check allows automatic native initialization.
  reset(); begin_results={false,true}; expect(v3MountStorage(&display));
  expect(format_calls==1 && end_calls==1 && read_bytes==0x180000);
  expect(begin_calls==2 && reg_calls==1);
  reset(); exact_digest=false; powerScript(1000);
  stopped([]{v3MountStorage(&display);},1);
  expect(format_calls==0 && power_calls==1 && read_bytes==0x180000);
  reset(); fail_read_call=10; powerScript(1000);
  stopped([]{v3MountStorage(&display);},1);
  expect(format_calls==0 && power_calls==1 && read_bytes==9*512);
  reset(); format_result=false; powerScript(1000);
  stopped([]{v3MountStorage(&display);},1);
  expect(format_calls==1 && begin_calls==1); // failed native format is not retried silently

  // Actual menu/policy integration: default Retry does not erase anything.
  reset(); startScript(); press(2100); script_time+=800;
  press(100); press(100); press(2100);
  stopped([]{v3StorageRecoveryMenu(&display,false);},1);
  expect(begin_calls==1 && format_calls==0 && power_calls==1);
  // Reset opens a separate confirmation; default Cancel remains safe.
  reset(); startScript(); press(100); press(2100); press(2100);
  press(100); press(100); press(2100);
  stopped([]{v3StorageRecoveryMenu(&display,false);},1);
  expect(format_calls==0 && power_calls==1);
  // Destructive flow requires selecting Reset, holding, selecting Erase, holding.
  reset(); default_begin=true; startScript();
  press(100); press(2100); press(100); press(2100);
  expect(v3StorageRecoveryMenu(&display,false));
  expect(format_calls==1 && begin_calls==1);
  // No display means no visible consent, even with the same button sequence.
  reset(); startScript(); press(100); press(2100); press(100); press(2100);
  stopped([]{v3StorageRecoveryMenu(nullptr,false);},3);
  expect(format_calls==0 && begin_calls==0);
  // BOOT already held on entry never counts as selection/confirmation.
  reset(); button_events={{0,true},{5000,false}}; deadline=6000;
  stopped([]{v3StorageRecoveryMenu(&display,false);},3);
  expect(format_calls==0 && begin_calls==0 && power_calls==0);
  // Identity recovery Retry reboots without trying to mount or format.
  reset(); startScript(); press(2100);
  stopped([]{v3StorageRecoveryMenu(&display,true);},2);
  expect(reboot_calls==1 && begin_calls==0 && format_calls==0);
  printf("PASS: %d V3 recovery assertions (actual C++ header; mock SHA256, not crypto validation)\n",checks);
}
'''


def linux_path(path: Path) -> str:
    return subprocess.check_output(
        ["wsl", "--exec", "wslpath", "-a", path.as_posix()], text=True).strip()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="smartui-v3-storage-") as directory:
        folder = Path(directory)
        (folder / "stub.h").write_text(STUB, encoding="utf-8")
        for name in ("SHA256.h", "esp_partition.h", "esp_spiffs.h", "SPIFFS.h"):
            (folder / name).write_text('#include "stub.h"\n', encoding="utf-8")
        (folder / "test.cpp").write_text(SOURCE, encoding="utf-8")
        flags = ["-std=c++11", "-Wall", "-Wextra", "-Werror", "-pedantic", "-O2"]
        compiler = shutil.which("g++")
        if compiler:
            binary = folder / "test"
            subprocess.run([compiler, *flags, "-I", str(folder), "-I", str(HEADERS),
                            str(folder / "test.cpp"), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)
        elif shutil.which("wsl"):
            base, include = linux_path(folder), linux_path(HEADERS)
            subprocess.run(["wsl", "--exec", "g++", *flags, "-I", base, "-I", include,
                            base + "/test.cpp", "-o", base + "/test"], check=True)
            subprocess.run(["wsl", "--exec", base + "/test"], check=True)
        else:
            raise SystemExit("A native g++ or WSL with g++ is required.")


if __name__ == "__main__":
    main()
