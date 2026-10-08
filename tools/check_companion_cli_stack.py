#!/usr/bin/env python3
"""Check actual ARM CLI stack frames from a PlatformIO compilation database.

Run after `pio run -e Heltec_t114_companion_radio_ble -t compiledb`.
The small per-function budgets prevent the specific nested-scratch regression;
they are not a whole-program worst-case stack or hardware stability proof.
"""
from pathlib import Path
import argparse
import json
import os
import re
import shlex
import subprocess
import tempfile


SOURCES = ("MyMesh.cpp", "SmartUiCli.cpp", "SmartUiConsoleCommands.cpp",
           "SmartUiCliSettings.cpp", "DeviceSettings.cpp")
BUDGETS = {
    "MyMesh::handleCmdFrame(": 64,
    "MyMesh::handleLocalCliFrame(": 64,
    "MyMesh::setQuickReplyOverride(": 128,
    "MyMesh::setLocalNodeName(": 96,
    "MyMesh::setLocalTxPower(": 80,
    "smartui::SmartUiCli::handle(": 160,
    "smartui::handleSmartUiConsoleCommand(": 384,
    "smartui::handleSmartUiSettingsCli(": 384,
    "smartui::DeviceSettings::handle(": 96,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compile-commands", type=Path, default=Path("compile_commands.json"))
    options = parser.parse_args()
    database = json.loads(options.compile_commands.read_text(encoding="utf-8"))
    records = []
    with tempfile.TemporaryDirectory(prefix="smartui-arm-stack-") as directory:
        for name in SOURCES:
            entries = [entry for entry in database
                       if entry["file"].replace("\\", "/").endswith("/" + name)]
            if len(entries) != 1:
                raise RuntimeError(f"Expected one production compile command for {name}, got {len(entries)}")
            entry = entries[0]
            command = entry.get("command", "")
            arguments = entry.get("arguments")
            compiler = str(arguments[0]) if arguments else command.split(" ", 1)[0]
            if "arm-none-eabi" not in compiler or "cortex-m4" not in str(arguments or command):
                raise RuntimeError("Use the production nRF52/ARM compilation database, not a host compiler")
            output = Path(directory) / (name + ".o")
            if arguments is not None or os.name != "nt":
                arguments = list(arguments) if arguments else shlex.split(command)
                arguments[arguments.index("-o") + 1] = str(output)
                arguments += ["-fstack-usage"]
                subprocess.run(arguments, cwd=entry["directory"], check=True)
            else:
                # Preserve the exact Windows/SCons escaping (not shlex's POSIX
                # backslash rules), and avoid cmd.exe's 8191-character limit.
                output_argument = subprocess.list2cmdline([str(output)])
                command, changed = re.subn(r"(?<!\S)-o\s+(?:\"[^\"]*\"|\S+)",
                    lambda _: "-o " + output_argument, command, count=1)
                if changed != 1:
                    raise RuntimeError("Missing output path in compilation database")
                subprocess.run(command + " -fstack-usage", cwd=entry["directory"], check=True)
            usage = output.with_suffix(".su")
            if not usage.exists():
                raise RuntimeError(f"Compiler did not emit stack usage: {usage.name}")
            for line in usage.read_text(encoding="utf-8").splitlines():
                identity, size, category = line.rsplit("\t", 2)
                records.append((identity, int(size), category))
        for function, limit in BUDGETS.items():
            matches = [record for record in records if function in record[0]]
            if not matches:
                raise RuntimeError(f"Missing production stack record for {function}")
            maximum = max(record[1] for record in matches)
            if any(record[2] != "static" for record in matches):
                raise RuntimeError(f"Unbounded/dynamic stack frame: {function}")
            print(f"{function} {maximum} B (budget {limit} B)", flush=True)
            if maximum > limit:
                raise RuntimeError(f"CLI stack regression: {function} uses {maximum} > {limit} bytes")
    print("PASS production ARM local CLI stack-frame budgets (not a full call-graph proof)")


if __name__ == "__main__":
    main()
