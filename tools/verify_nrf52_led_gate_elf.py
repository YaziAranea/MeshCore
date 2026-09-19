"""Fail the release build if the actual flash-cache code bypasses the LED gate.

Inspects the linked ARM ELF, not just flags or a host-only model. The adjacent
UF2 is built from this ELF by the ordinary create_uf2 target. No hardware claim.
"""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess


def function(disassembly, name):
    match = re.search(r"(?m)^[0-9a-f]+ <" + re.escape(name) + r">:\s*\n(.*?)(?=\n[0-9a-f]+ <|\Z)",
                      disassembly, re.S)
    if not match:
        raise ValueError("Missing linked function: " + name)
    return match[1]


def verify(disassembly):
    cache = function(disassembly, "flash_cache_flush")
    gate = function(disassembly, "__wrap_ledOn")
    if "<__wrap_ledOn>" not in cache or "<ledOn>" in cache:
        raise ValueError("flash_cache_flush must call the gate, never ledOn directly")
    # Demangled disassembly makes the C++ getter name stable/readable.
    if not re.search(r"<meshcoreBoardLedsEnabled\(\)>", gate):
        raise ValueError("Wrapper does not consult the production master switch")
    if "<ledOn>" not in gate:
        raise ValueError("Wrapper lost passthrough to the real LED implementation")
    if "<ledOff>" not in cache:
        raise ValueError("Flash-cache OFF edge unexpectedly changed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf", type=Path)
    args = parser.parse_args()
    core = Path(os.environ.get("PLATFORMIO_CORE_DIR", Path.home() / ".platformio"))
    suffix = ".exe" if os.name == "nt" else ""
    candidates = sorted((core / "packages").glob("toolchain-gccarmnoneeabi*/bin/arm-none-eabi-objdump" + suffix))
    executable = shutil.which("arm-none-eabi-objdump") or (str(candidates[0]) if candidates else None)
    if executable is None:
        raise RuntimeError("ARM objdump is required; install the build's PlatformIO toolchain")
    output = subprocess.check_output([executable, "-d", "-C", str(args.elf)], text=True)
    verify(output)
    print("PASS linked ARM flash_cache_flush -> __wrap_ledOn -> board LED policy; real ledOn/ledOff preserved")


if __name__ == "__main__":
    main()
