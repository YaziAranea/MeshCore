#!/usr/bin/env python3
"""Compile and exercise the actual pure-C++ storage recovery button policy.

No build of firmware, filesystem formatting, flashing, or device interaction.
Temporary host sources/binaries are created only inside a temporary directory.
"""

from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
HEADER_DIR = ROOT / "examples/companion_radio/ui-new"
SOURCE = r'''
#include <stdint.h>
#include <stdio.h>
#include <assert.h>
#include "StorageRecoveryPolicy.h"
using smartui::StorageRecoveryAction;
using smartui::StorageRecoveryPolicy;
using Action = StorageRecoveryAction;

static int checks = 0;
static void expect(bool condition) { assert(condition); ++checks; }

struct Rig {
  uint32_t now;
  StorageRecoveryPolicy policy;
  explicit Rig(uint32_t start=0, bool pressed=false)
      : now(start), policy(start,pressed) {}
  Action sample(uint32_t elapsed, bool pressed) {
    now += elapsed;
    return policy.update(now,pressed);
  }
  void arm() {
    expect(sample(30,false)==Action::None);
    expect(policy.selectedIndex()==0 && !policy.confirmingReset());
  }
  Action gesture(uint32_t held) {
    expect(held>=30);
    expect(sample(1,true)==Action::None);
    expect(sample(30,true)==Action::None);
    expect(sample(held-30,false)==Action::None); // No action on raw release.
    expect(sample(29,false)==Action::None);
    return sample(1,false);
  }
  void click() { expect(gesture(90)==Action::None); }
};

int main() {
  // All actions occur on stable release, never while the button is held.
  {
    Rig r; r.arm();
    expect(r.sample(1,true)==Action::None);
    expect(r.sample(30,true)==Action::None);
    expect(r.sample(5000,true)==Action::None);
    expect(r.sample(0,false)==Action::None);
    expect(r.sample(29,false)==Action::None);
    expect(r.sample(1,false)==Action::RetryMount);
    expect(r.sample(5000,false)==Action::None); // Exactly one action.
  }
  // A held BOOT button on entry cannot accidentally invoke any operation.
  {
    Rig r(100,true);
    expect(r.sample(5000,true)==Action::None);
    expect(r.sample(1,false)==Action::None);
    expect(r.sample(20,true)==Action::None); // Release bounced; still disarmed.
    expect(r.sample(3000,true)==Action::None);
    expect(r.sample(1,false)==Action::None);
    expect(r.sample(29,false)==Action::None);
    expect(r.sample(1,false)==Action::None);
    expect(r.policy.selectedIndex()==0 && !r.policy.confirmingReset());
    expect(r.gesture(2000)==Action::RetryMount);
  }
  // Main menu cycles on short clicks; no click can emit an action.
  {
    Rig r; r.arm();
    r.click(); expect(r.policy.selectedIndex()==1);
    r.click(); expect(r.policy.selectedIndex()==2);
    r.click(); expect(r.policy.selectedIndex()==0);
    r.click(); r.click();
    expect(r.gesture(2500)==Action::PowerOff);
    expect(r.policy.selectedIndex()==0 && !r.policy.confirmingReset());
  }
  // One long hold on ResetData ONLY opens confirmation. Cancel is default.
  {
    Rig r; r.arm(); r.click();
    expect(r.gesture(2000)==Action::None);
    expect(r.policy.confirmingReset() && r.policy.selectedIndex()==0);
    expect(r.sample(5000,false)==Action::None);
    expect(r.gesture(2000)==Action::None); // Hold default Cancel.
    expect(!r.policy.confirmingReset() && r.policy.selectedIndex()==0);
  }
  // Erasing requires an explicit second selection and second hold/release.
  {
    Rig r; r.arm(); r.click();
    expect(r.gesture(2000)==Action::None);
    r.click(); expect(r.policy.confirmingReset() && r.policy.selectedIndex()==1);
    r.click(); expect(r.policy.selectedIndex()==0); // Two-choice wrap.
    r.click(); expect(r.policy.selectedIndex()==1);
    expect(r.gesture(2000)==Action::FormatStorage);
    expect(!r.policy.confirmingReset() && r.policy.selectedIndex()==0);
    expect(r.sample(5000,false)==Action::None);
  }
  // Debounce: sub-30ms presses do not count; release bounce is one click.
  {
    Rig r; r.arm();
    expect(r.sample(1,true)==Action::None);
    expect(r.sample(29,false)==Action::None);
    expect(r.sample(30,false)==Action::None);
    expect(r.policy.selectedIndex()==0);
    expect(r.sample(1,true)==Action::None);
    expect(r.sample(30,true)==Action::None);
    expect(r.sample(70,false)==Action::None);
    expect(r.sample(10,true)==Action::None);
    expect(r.sample(10,false)==Action::None);
    expect(r.sample(30,false)==Action::None);
    expect(r.policy.selectedIndex()==1);
    expect(r.sample(300,false)==Action::None);
    expect(r.policy.selectedIndex()==1);
  }
  // Exact threshold: the release debounce must not promote 1999ms to hold.
  {
    Rig r; r.arm();
    expect(r.gesture(1999)==Action::None);
    expect(r.policy.selectedIndex()==1 && !r.policy.confirmingReset());
    expect(r.gesture(2000)==Action::None);
    expect(r.policy.confirmingReset() && r.policy.selectedIndex()==0);
  }
  // The same threshold and release filtering work across millis wrap.
  {
    Rig r(UINT32_MAX-1000U); r.arm();
    expect(r.gesture(2000)==Action::RetryMount);
    Rig b(UINT32_MAX-15U,true);
    expect(b.sample(1,false)==Action::None);
    expect(b.sample(29,false)==Action::None);
    expect(b.sample(1,false)==Action::None);
    b.click(); expect(b.policy.selectedIndex()==1);
    expect(b.gesture(2000)==Action::None);
    b.click(); expect(b.gesture(2000)==Action::FormatStorage);
  }
  // A new press before the initial released input was stable is ignored.
  {
    Rig r;
    expect(r.sample(20,true)==Action::None);
    expect(r.sample(4000,true)==Action::None);
    expect(r.sample(1,false)==Action::None);
    expect(r.sample(30,false)==Action::None);
    expect(r.policy.selectedIndex()==0);
    expect(r.gesture(2000)==Action::RetryMount);
  }
  printf("PASS: %d storage recovery policy assertions (actual C++ header)\n",checks);
}
'''


def linux_path(path: Path) -> str:
    return subprocess.check_output(
        ["wsl", "--exec", "wslpath", "-a", path.as_posix()], text=True).strip()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="smartui-storage-recovery-") as directory:
        folder = Path(directory)
        source = folder / "recovery.cpp"
        source.write_text(SOURCE, encoding="utf-8")
        flags = ["-std=c++11", "-Wall", "-Wextra", "-Werror", "-pedantic", "-O2"]
        compiler = shutil.which("g++")
        if compiler:
            binary = folder / "recovery-test"
            subprocess.run([compiler, *flags, "-I", str(HEADER_DIR), str(source),
                            "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)
        elif shutil.which("wsl"):
            base, include = linux_path(folder), linux_path(HEADER_DIR)
            subprocess.run(["wsl", "--exec", "g++", *flags, "-I", include,
                            base + "/recovery.cpp", "-o", base + "/recovery-test"], check=True)
            subprocess.run(["wsl", "--exec", base + "/recovery-test"], check=True)
        else:
            raise SystemExit("A native g++ or WSL with g++ is required for this host test.")


if __name__ == "__main__":
    main()
