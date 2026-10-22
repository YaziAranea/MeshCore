#!/usr/bin/env python3
"""Check two filesystem regions sharing the pinned 4 KiB flash cache.

Uses the production region callbacks and mutex, the unmodified vendor cache,
and two host threads. The hardware program callback pauses until the second
filesystem attempts to acquire the cache lock, like an asynchronous flash op.
No hardware access or changes to installed framework sources.
"""
from pathlib import Path
import tempfile

from test_nrf52_flash_led_gate import (
    HostToolchain, find_pinned_flash_cache, COMMON_FUNC_H, WIRING_DIGITAL_H,
)
from test_nrf52_safe_mount import library_source

ROOT = Path(__file__).resolve().parents[1]

RTOS = r'''#pragma once
#include <cassert>
#include <cstdint>
#include <mutex>
struct StaticSemaphore_t { std::mutex native; };
using SemaphoreHandle_t = StaticSemaphore_t*;
using BaseType_t = int;
constexpr uint32_t portMAX_DELAY = UINT32_MAX;
constexpr int pdTRUE = 1, pdFALSE = 0;
extern void cache_lock_waiting();
inline SemaphoreHandle_t xSemaphoreCreateMutexStatic(StaticSemaphore_t* s) { return s; }
inline BaseType_t xSemaphoreTake(SemaphoreHandle_t s, uint32_t) {
  if (!s->native.try_lock()) { cache_lock_waiting(); s->native.lock(); }
  return pdTRUE;
}
inline BaseType_t xSemaphoreGive(SemaphoreHandle_t s) { s->native.unlock(); return pdTRUE; }
'''

FLASH = r'''#pragma once
#include <stdint.h>
#define FLASH_NRF52_PAGE_SIZE 4096
extern "C" {
int flash_nrf5x_write(uint32_t, const void*, uint32_t);
int flash_nrf5x_read(void*, uint32_t, uint32_t);
void flash_nrf5x_flush();
}
inline int flash_nrf5x_write8(uint32_t addr, uint8_t value) {
  return flash_nrf5x_write(addr, &value, 1);
}
'''

HARNESS = r'''
#include <array>
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <thread>
#include <helpers/nrf52/SafeNrf52FlashRegion.h>
#include "flash_cache.h"

static std::array<uint8_t, 1024*1024> disk;
static std::array<uint8_t, FLASH_CACHE_SIZE> cache;
static flash_cache_t fc;
static std::mutex event_mutex;
static std::condition_variable events;
static bool program_pending, competing_waiter;
static std::atomic<bool> pause_program{false};
static uint32_t first_address;

void cache_lock_waiting() {
  std::lock_guard<std::mutex> lock(event_mutex);
  if (program_pending) { competing_waiter=true; events.notify_all(); }
}
static void check_range(uint32_t addr, uint32_t n) {
  assert(addr<disk.size() && n<=disk.size()-addr);
}
static uint32_t read_flash(void* p, uint32_t addr, uint32_t n) {
  check_range(addr,n); std::memcpy(p,disk.data()+addr,n); return n;
}
static bool erase_flash(uint32_t addr) {
  check_range(addr,FLASH_CACHE_SIZE); std::memset(disk.data()+addr,255,FLASH_CACHE_SIZE);
  return true;
}
static bool verify_flash(uint32_t addr, const void* p, uint32_t n) {
  check_range(addr,n); return std::memcmp(disk.data()+addr,p,n)==0;
}
static uint32_t program_flash(uint32_t addr, const void* p, uint32_t n) {
  check_range(addr,n);
  if (pause_program.exchange(false)) {
    std::unique_lock<std::mutex> lock(event_mutex);
    program_pending=true; events.notify_all();
    assert(events.wait_for(lock,std::chrono::seconds(5),[]{ return competing_waiter; }));
    // The other filesystem is waiting, not replacing the in-flight buffer.
    assert(addr==first_address && fc.cache_addr==first_address);
    assert(static_cast<const uint8_t*>(p)[0]==0x41);
    program_pending=false;
  }
  std::memcpy(disk.data()+addr,p,n); return n;
}
extern "C" {
void ledOn(uint32_t) {}
void ledOff(uint32_t) {}
int flash_nrf5x_write(uint32_t addr,const void* p,uint32_t n) {
  return flash_cache_write(&fc,addr,p,n);
}
int flash_nrf5x_read(void* p,uint32_t addr,uint32_t n) {
  return flash_cache_read(&fc,p,addr,n);
}
void flash_nrf5x_flush() { flash_cache_flush(&fc); }
}

static void run(bool internal_first) {
  disk.fill(255); cache.fill(255); fc={};
  fc.erase=erase_flash; fc.program=program_flash; fc.read=read_flash;
  fc.verify=verify_flash; fc.cache_addr=FLASH_CACHE_INVALID_ADDR; fc.cache_buf=cache.data();
  program_pending=competing_waiter=false;
  smartui::Nrf52FlashCacheLock shared;
  assert(shared.begin());
  assert(shared.begin()); // Idempotent: never replace a live mutex.
  smartui::SafeNrf52FlashRegion primary(0xED000,28*1024,shared);
  smartui::SafeNrf52FlashRegion extra(0xD4000,100*1024,shared);
  auto* a=internal_first ? primary.config() : extra.config();
  auto* b=internal_first ? extra.config() : primary.config();
  first_address=internal_first ? 0xED000 : 0xD4000;
  const uint32_t second_address=internal_first ? 0xD4000 : 0xED000;
  const uint8_t av=0x41,bv=0x42;
  assert(a->prog(a,0,0,&av,1)==0);
  pause_program=true;
  std::thread writer_a([&]{ assert(a->sync(a)==0); });
  std::thread writer_b([&]{
    {
      std::unique_lock<std::mutex> lock(event_mutex);
      assert(events.wait_for(lock,std::chrono::seconds(5),[]{return program_pending;}));
    }
    assert(b->prog(b,0,0,&bv,1)==0); assert(b->sync(b)==0);
  });
  writer_a.join(); writer_b.join();
  assert(competing_waiter && disk[first_address]==av && disk[second_address]==bv);
  uint8_t value=0;
  assert(a->read(a,0,0,&value,1)==0 && value==av);
  assert(b->read(b,0,0,&value,1)==0 && value==bv);
  // A logical 128-byte erase preserves neighbors in the same physical page.
  assert(a->prog(a,1,0,&bv,1)==0); assert(a->sync(a)==0);
  assert(a->erase(a,0)==0); assert(a->sync(a)==0);
  assert(disk[first_address]==255 && disk[first_address+128]==bv);
  assert(disk[second_address]==bv);
}
int main() {
  for(unsigned i=0;i<8;++i) { run(false); run(true); }
  puts("PASS 16 coordinated two-filesystem writes: shared cache serialized; neighboring blocks preserved");
}
'''


def main():
    cache_source = find_pinned_flash_cache()
    library = library_source()
    toolchain = HostToolchain()
    with tempfile.TemporaryDirectory(prefix="nrf52-flash-serialization-") as folder:
        folder = Path(folder)
        (folder / 'flash').mkdir()
        files = {
            'rtos.h': RTOS, 'flash/flash_nrf5x.h': FLASH,
            'Stream.h': '#pragma once\n#include <cstdint>\n#include <cstddef>\n'
                        'class Stream { public: virtual ~Stream() = default; };\n',
            'common_func.h': COMMON_FUNC_H,
            'variant.h': '#pragma once\n#define LED_BUILTIN 35\n',
            'wiring_digital.h': WIRING_DIGITAL_H,
            'test.cpp': HARNESS,
        }
        for name, content in files.items():
            (folder/name).write_text(content, encoding='utf-8')
        includes = ['-I', toolchain.path(folder), '-I', toolchain.path(library),
                    '-I', toolchain.path(ROOT/'src'), '-I', toolchain.path(cache_source.parent)]
        obj, binary = folder/'cache.o', folder/'test'
        toolchain.run('gcc', ['-std=c99','-O2',*includes,'-c',toolchain.path(cache_source),
                              '-o',toolchain.path(obj)])
        toolchain.run('g++', ['-std=c++17','-O2','-pthread','-DNRF52840_XXAA',*includes,
                              toolchain.path(folder/'test.cpp'),toolchain.path(obj),
                              '-o',toolchain.path(binary)])
        print(toolchain.output(binary), end='')


if __name__ == '__main__':
    main()
