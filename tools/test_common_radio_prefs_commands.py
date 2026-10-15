"""Compile the actual shared radio CLI with hostile numeric inputs, including -Ofast."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

from test_ui_sessions_v006 import function

ROOT = Path(__file__).resolve().parents[1]


def main():
    compiler = shutil.which("g++") or shutil.which("clang++")
    with tempfile.TemporaryDirectory(prefix="common-radio-commands-") as directory:
        folder = Path(directory)

        def path(value):
            if compiler or os.name != "nt":
                return str(value)
            return "/mnt/" + value.drive[0].lower() + value.as_posix()[2:]

        (folder / "target.h").write_text(r'''#pragma once
#include <cstdlib>
#include <cstdio>
template <class T> T constrain(T value, T low, T high) {
  return value < low ? low : value > high ? high : value;
}
struct TestRadio {
  bool setRxBoostedGainMode(bool) { return true; }
  void setTxPower(int) {}
};
extern TestRadio radio_driver;
''', encoding="utf-8")
        parser = function((ROOT / "src/Utils.cpp").read_text(encoding="utf-8"),
                          "int Utils::parseTextParts(")
        (folder / "parse.cpp").write_text('#include "Utils.h"\nnamespace mesh {\n' + parser + '\n}\n', encoding="utf-8")
        sources = [ROOT / "tools/common_radio_prefs_commands_test.cpp",
                   ROOT / "src/helpers/CommonRadioPrefs.cpp",
                   ROOT / "src/helpers/CommonRadioPrefsKeys.cpp", folder / "parse.cpp"]
        for optimization in ("-Ofast", "-O1"):
            output = folder / ("test" + optimization)
            flags = ["-std=c++17", optimization, "-Wall", "-Wextra", "-Werror",
                     "-Wno-unused-parameter", "-Wno-sign-compare"]
            flags += ["-I" + path(p) for p in (folder, ROOT / "src", ROOT / "test/mocks")]
            if os.environ.get("SMARTUI_TEST_SANITIZE") == "1":
                flags += ["-fsanitize=address,undefined,float-cast-overflow", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie"]
            prefix = [compiler] if compiler else ["wsl", "--exec", "g++"]
            subprocess.run(prefix + flags + [path(p) for p in sources] + ["-o", path(output)], check=True)
            subprocess.run([str(output)] if compiler else ["wsl", "--exec", path(output)], check=True)


if __name__ == "__main__":
    main()
