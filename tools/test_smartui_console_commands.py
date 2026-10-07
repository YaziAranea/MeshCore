#!/usr/bin/env python3
"""Compile the production friendly-console adapter, without board dependencies."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    compiler = shutil.which("g++") or shutil.which("clang++")
    flags = ["-std=c++17", "-Wall", "-Wextra", "-Werror"]
    if os.environ.get("SMARTUI_TEST_SANITIZE") == "1":
        flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie"]
    include = ROOT / "examples/companion_radio"
    sources = [ROOT / "tools/smartui_console_commands_test.cpp", include / "SmartUiConsoleCommands.cpp"]
    with tempfile.TemporaryDirectory(prefix="smartui-console-") as directory:
        for optimization in ("-O1", "-Ofast"):
            output = Path(directory) / ("console" + optimization)
            if compiler:
                build = [compiler, *flags, optimization, "-I" + str(include), *map(str, sources), "-o", str(output)]
                execute = [str(output)]
            elif os.name == "nt":
                def linux(path):
                    return subprocess.check_output(["wsl", "--exec", "wslpath", "-a", str(path)], text=True).strip()
                build = ["wsl", "--exec", "g++", *flags, optimization, "-I" + linux(include), *map(linux, sources), "-o", linux(output)]
                execute = ["wsl", "--exec", linux(output)]
            else:
                raise RuntimeError("Host C++ compiler required; tests were not run")
            print(f"SmartUI friendly console {optimization}", flush=True)
            subprocess.run(build, check=True)
            subprocess.run(execute, check=True)


if __name__ == "__main__":
    main()
