#!/usr/bin/env python3
"""Regression for phone CMD66 ADC writes; also guard the small-stack router."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def function(source, signature):
    start = source.index(signature)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def main():
    source = (ROOT / "examples/companion_radio/MyMesh.cpp").read_text(encoding="utf-8")
    header = (ROOT / "examples/companion_radio/MyMesh.h").read_text(encoding="utf-8")
    dispatch = function(source, "void MyMesh::handleCmdFrame(")
    assert "validateCommandFrame(" in dispatch
    assert dispatch.index("validateCommandFrame(") < dispatch.index("handleLocalCliFrame(len);")
    assert dispatch.index("handleLocalCliFrame(len);") < dispatch.index("handleStandardCmdFrame(len);")
    assert "CMD_DEVICE_QUERY" not in dispatch and "NodePrefs" not in dispatch
    assert "handleStandardCmdFrame(size_t length) __attribute__((noinline));" in header
    compiler = shutil.which("g++") or shutil.which("clang++")
    flags = ["-std=c++17", "-Wall", "-Wextra", "-Werror"]
    if os.environ.get("SMARTUI_TEST_SANITIZE") == "1":
        flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie"]
    include = ROOT / "examples/companion_radio"
    sources = [ROOT / "tools/adc_companion_cli_test.cpp"] + [include / name for name in (
        "SmartUiCli.cpp", "SmartUiConsoleCommands.cpp", "SmartUiCliSettings.cpp", "DeviceSettings.cpp")]
    with tempfile.TemporaryDirectory(prefix="smartui-adc-cli-") as directory:
        for optimization in ("-O1", "-Os", "-Ofast"):
            output = Path(directory) / ("adc-cli" + optimization)
            if compiler:
                build = [compiler, *flags, optimization, "-I" + str(include),
                         "-I" + str(ROOT / "src"), *map(str, sources), "-o", str(output)]
                execute = [str(output)]
            elif os.name == "nt":
                def linux(path):
                    return subprocess.check_output(["wsl", "--exec", "wslpath", "-a", str(path)], text=True).strip()
                build = ["wsl", "--exec", "g++", *flags, optimization,
                         "-I" + linux(include), "-I" + linux(ROOT / "src"),
                         *map(linux, sources), "-o", linux(output)]
                execute = ["wsl", "--exec", linux(output)]
            else:
                raise RuntimeError("Host C++ compiler required; tests were not run")
            print(f"Companion ADC regression {optimization}", flush=True)
            subprocess.run(build, check=True)
            subprocess.run(execute, check=True)


if __name__ == "__main__":
    main()
