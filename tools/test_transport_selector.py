#!/usr/bin/env python3
"""Compile and run production selector transports against deterministic host fakes."""

from pathlib import Path
import os
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tools" / "transport_selector_test"
OUT = ROOT / "qa_outputs" / "transport-selector"


def linux(path: Path) -> str:
    resolved = path.resolve()
    return "/mnt/" + resolved.drive[0].lower() + resolved.as_posix()[2:]


def function_body(source: str, signature: str) -> str:
    begin = source.index(signature)
    brace = source.index("{", begin)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[begin:end]


def check_ble_session_source() -> None:
    header = (ROOT / "src/helpers/esp32/SerialBLEInterface.h").read_text(
        encoding="utf-8"
    )
    source = (ROOT / "src/helpers/esp32/SerialBLEInterface.cpp").read_text(
        encoding="utf-8"
    )
    assert "std::atomic<uint32_t> _session_generation" in header
    authentication = function_body(
        source, "void SerialBLEInterface::onAuthenticationComplete("
    )
    assert authentication.index("advanceSessionGeneration();") < authentication.index(
        "deviceConnected = true;"
    )
    disconnect = function_body(source, "void SerialBLEInterface::onDisconnect(")
    assert "clearBuffers();" not in disconnect
    assert "frame.session_generation = sessionGeneration();" in source
    assert "send_queue[0].session_generation != sessionGeneration()" in source


def main() -> None:
    check_ble_session_source()
    OUT.mkdir(parents=True, exist_ok=True)
    binary = OUT / "transport_selector_test"
    defines = [
        "-DSMARTUI_CONNECTION_SELECTOR=1",
        "-DSMARTUI_SERIAL_SESSION_LEASE_MS=300000UL",
        "-DSMARTUI_SERIAL_FRAME_TIMEOUT_MS=2000UL",
        "-DSMARTUI_WIFI_APPROVAL_TIMEOUT_MS=30000UL",
        "-DSMARTUI_WIFI_LISTENER_RETRY_MS=1000UL",
    ]
    sources = [
        FIXTURE / "transport_selector_test.cpp",
        ROOT / "src/helpers/ArduinoSerialInterface.cpp",
        ROOT / "src/helpers/esp32/SerialWifiInterface.cpp",
    ]
    includes = [FIXTURE / "mocks", ROOT / "test/mocks", ROOT / "src"]

    if os.name == "nt":
        command = ["wsl", "--exec", "g++", "-std=c++17", "-O1", "-Wall", "-Wextra",
                   "-Wno-unused-parameter", "-Wno-sign-compare"]
        command += defines
        for include in includes:
            command += ["-I", linux(include)]
        command += [linux(source) for source in sources]
        command += ["-o", linux(binary)]
        run = ["wsl", "--exec", linux(binary)]
    else:
        compiler = shutil.which("g++") or shutil.which("clang++")
        if not compiler:
            raise SystemExit("C++ compiler required")
        command = [compiler, "-std=c++17", "-O1", "-Wall", "-Wextra",
                   "-Wno-unused-parameter", "-Wno-sign-compare", *defines]
        for include in includes:
            command += ["-I", str(include)]
        command += [str(source) for source in sources]
        command += ["-o", str(binary)]
        run = [str(binary)]

    subprocess.run(command, check=True, timeout=60)
    subprocess.run(run, check=True, timeout=30)


if __name__ == "__main__":
    main()
