#!/usr/bin/env python3
"""Exercise the production ESP32 sleep guard; no physical current claim."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CODE = r'''
#include "SmartUiSleepPolicy.h"
#include <cassert>
int main() {
  using namespace smartui;
  assert(!holdCompanionLightSleep(false, false, false, false, false));
  for (unsigned bits = 1; bits < 32; ++bits)
    assert(holdCompanionLightSleep(bits&1, bits&2, bits&4, bits&8, bits&16));
  assert(!serialServiceWindow(false, 0, 0));
  assert(serialServiceWindow(true, 0, 0));
  assert(serialServiceWindow(true, 119999, 0));
  assert(!serialServiceWindow(true, 120000, 0));
  assert(serialServiceWindow(true, 0x20, 0xfffffff0));
  assert(!serialServiceWindow(true, 120000, 0xfffffff0));
}
'''

def main():
    source = (ROOT / 'examples/companion_radio/main.cpp').read_text(encoding='utf-8')
    assert 'ESP_PM_NO_LIGHT_SLEEP' in source
    assert 'ui_task.shouldHoldLightSleepLock()' in source
    assert 'connection_controller.consoleActive(millis())' in source
    assert 'connection_controller.status().selected == CompanionMode::USB' in source
    assert source.index('holdCompanionLightSleep(') < source.index('vTaskDelay(')
    with tempfile.TemporaryDirectory(prefix='smartui-sleep-') as raw:
        work = Path(raw)
        shutil.copy2(ROOT / 'src/helpers/SmartUiSleepPolicy.h', work)
        (work / 'test.cpp').write_text(CODE, encoding='utf-8')
        if os.name == 'nt':
            path = '/mnt/' + work.drive[0].lower() + work.as_posix()[2:]
            compile_cmd = ['wsl', '--exec', 'g++', '-std=c++11', '-Wall', '-Wextra', '-Werror', path+'/test.cpp', '-o', path+'/test']
            run_cmd = ['wsl', '--exec', path+'/test']
        else:
            compile_cmd = ['g++', '-std=c++11', '-Wall', '-Wextra', '-Werror', str(work/'test.cpp'), '-o', str(work/'test')]
            run_cmd = [str(work/'test')]
        subprocess.run(compile_cmd, check=True, timeout=30)
        subprocess.run(run_cmd, check=True, timeout=10)
    print('[PASS] ESP32 runtime transport sleep guard and rollover window')

if __name__ == '__main__':
    main()
