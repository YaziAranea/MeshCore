"""Compile and execute the actual display-independent settings backend."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="smartui-settings-") as directory:
        output = Path(directory) / "device_settings_test"
        paths = [ROOT / "tools/device_settings_test.cpp",
                 ROOT / "examples/companion_radio/DeviceSettings.cpp",
                 ROOT / "examples/companion_radio/SmartUiCliSettings.cpp"]
        includes = [ROOT / "src", ROOT / "examples/companion_radio"]
        compiler = shutil.which("g++") or shutil.which("clang++")
        if compiler:
            build = [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O1",
                     *["-I" + str(path) for path in includes],
                     *map(str, paths), "-o", str(output)]
            execute = [str(output)]
        elif os.name == "nt":
            def linux(path):
                return subprocess.check_output(["wsl", "--exec", "wslpath", "-a", str(path)], text=True).strip()
            build = ["wsl", "--exec", "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O1",
                     *["-I" + linux(path) for path in includes],
                     *map(linux, paths), "-o", linux(output)]
            execute = ["wsl", "--exec", linux(output)]
        else:
            raise RuntimeError("Host C++ compiler required; no skipped test success")
        subprocess.run(build, check=True)
        subprocess.run(execute, check=True)
        # Exercise the strict fixed-point manual parser under the nRF52
        # optimization mode too. Invalid tokens must not reach float parsing.
        for optimization in ("-O1", "-Ofast"):
            manual_build = [part.replace("device_settings_test.cpp", "adc_manual_test.cpp")
                            if isinstance(part, str) else part for part in build]
            manual_build[manual_build.index("-O1")] = optimization
            subprocess.run(manual_build, check=True)
            subprocess.run(execute, check=True)


if __name__ == "__main__":
    main()
