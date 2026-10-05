#!/usr/bin/env python3
"""RAM-only reproduction with installed Adafruit littlefs1; never accesses a board."""
from pathlib import Path
import os
import subprocess
import tempfile


def linux(path):
    path = Path(path).resolve()
    return '/mnt/' + path.drive[0].lower() + path.as_posix()[2:] if os.name == 'nt' else str(path)


CODE = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "lfs.h"
static unsigned char disk[28*1024];
void *pvPortMalloc(size_t n){return malloc(n);}
void vPortFree(void*p){free(p);}
static int rd(const struct lfs_config*c,lfs_block_t b,lfs_off_t o,void*p,lfs_size_t n){(void)c;memcpy(p,disk+b*128+o,n);return 0;}
static int wr(const struct lfs_config*c,lfs_block_t b,lfs_off_t o,const void*p,lfs_size_t n){(void)c;memcpy(disk+b*128+o,p,n);return 0;}
static int er(const struct lfs_config*c,lfs_block_t b){(void)c;memset(disk+b*128,255,128);return 0;}
static int sy(const struct lfs_config*c){(void)c;return 0;}
static struct lfs_config cfg={.read=rd,.prog=wr,.erase=er,.sync=sy,.read_size=128,.prog_size=128,.block_size=128,.block_count=224,.lookahead=128};
static int put(lfs_t*l,const char*path,size_t length,unsigned char value){
  lfs_file_t f;int e=lfs_file_open(l,&f,path,LFS_O_RDWR|LFS_O_CREAT);if(e)return e;
  // Single-character writes match ConfigSerializer::putChar/Adafruit File.
  for(size_t i=0;i<length;++i){int n=lfs_file_write(l,&f,&value,1);if(n!=1){e=n<0?n:-999;break;}}
  int sync=lfs_file_sync(l,&f);int close=lfs_file_close(l,&f);return e?e:(sync?sync:close);
}
static void verify(lfs_t*l,const char*path,size_t length,unsigned char value){
  lfs_file_t f;assert(lfs_file_open(l,&f,path,LFS_O_RDONLY)==0);assert(lfs_file_size(l,&f)==(int)length);
  for(size_t i=0;i<length;++i){unsigned char actual=0;assert(lfs_file_read(l,&f,&actual,1)==1);assert(actual==value);}
  assert(lfs_file_close(l,&f)==0);
}
int main(void){
  assert(LFS_VERSION==0x00010007);
  for(size_t filler=18000;filler<27000;filler+=64){
    memset(disk,255,sizeof(disk));lfs_t l={0};assert(lfs_format(&l,&cfg)==0);assert(lfs_mount(&l,&cfg)==0);
    int seed=put(&l,"/prefs.json",1500,'P')||put(&l,"/prefs.json.bak",1500,'B')||put(&l,"/_main.id",152,'I')||put(&l,"/unrelated",filler,'U');
    if(seed){lfs_unmount(&l);continue;}
    int first=put(&l,"/prefs.json.tmp",1500,'N');
    if(first!=LFS_ERR_NOSPC){lfs_unmount(&l);continue;}
    assert(lfs_remove(&l,"/prefs.json.tmp")==0);
    verify(&l,"/prefs.json",1500,'P');assert(lfs_remove(&l,"/prefs.json.bak")==0);
    // Power loss after reclaim still retains valid primary and unrelated data.
    assert(lfs_unmount(&l)==0);assert(lfs_mount(&l,&cfg)==0);
    verify(&l,"/prefs.json",1500,'P');verify(&l,"/_main.id",152,'I');verify(&l,"/unrelated",filler,'U');
    int second=put(&l,"/prefs.json.tmp",1500,'N');
    if(second){lfs_unmount(&l);continue;}
    verify(&l,"/prefs.json.tmp",1500,'N');
    assert(lfs_rename(&l,"/prefs.json","/prefs.json.bak")==0);
    assert(lfs_rename(&l,"/prefs.json.tmp","/prefs.json")==0);
    assert(lfs_unmount(&l)==0);assert(lfs_mount(&l,&cfg)==0);
    verify(&l,"/prefs.json",1500,'N');verify(&l,"/prefs.json.bak",1500,'P');
    verify(&l,"/_main.id",152,'I');verify(&l,"/unrelated",filler,'U');assert(lfs_unmount(&l)==0);
    printf("PASS littlefs1.7 28KiB: filler=%zu, first=%d, reclaim+retry=0; reboot-safe primary/identity/unrelated preserved\n",filler,first);
    return 0;
  }
  fprintf(stderr,"No capacity-pressure reproduction found\n");return 1;
}
'''


def main():
    packages = Path.home() / '.platformio/packages'
    candidates = list(packages.glob('framework-arduinoadafruitnrf52*/libraries/Adafruit_LittleFS/src/littlefs'))
    if not candidates:
        raise SystemExit('Installed Adafruit nRF52 littlefs source required for this optional hardware-library test')
    library = next((p for p in candidates if p.parents[3].name == 'framework-arduinoadafruitnrf52'), candidates[0])
    with tempfile.TemporaryDirectory(prefix='littlefs-capacity-') as folder:
        folder = Path(folder)
        source, binary = folder / 'test.c', folder / 'test'
        source.write_text(CODE, encoding='utf-8')
        prefix = ['wsl', '--exec'] if os.name == 'nt' else []
        subprocess.run([*prefix, 'gcc', '-std=c99', '-O2', '-I', linux(library), linux(source),
                        linux(library / 'lfs.c'), linux(library / 'lfs_util.c'), '-o', linux(binary)], check=True, timeout=60)
        subprocess.run([*prefix, linux(binary)], check=True, timeout=30)


if __name__ == '__main__':
    main()
