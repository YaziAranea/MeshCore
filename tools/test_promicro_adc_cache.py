"""Compile and run the real PromicroBoard ADC/cache implementation with host stubs."""

from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="smartui-promicro-adc-") as directory:
        output = Path(directory) / "promicro_adc_cache_test"
        source = ROOT / "tools/promicro_adc_cache_test.cpp"
        includes = [ROOT / "tools/test_stubs/promicro", ROOT / "src", ROOT]
        compiler = shutil.which("g++") or shutil.which("clang++")
        if compiler:
            build = [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O1",
                     *["-I" + str(path) for path in includes], str(source), "-o", str(output)]
            execute = [str(output)]
        elif os.name == "nt":
            def linux(path):
                return subprocess.check_output(
                    ["wsl", "--exec", "wslpath", "-a", str(path)], text=True
                ).strip()
            build = ["wsl", "--exec", "g++", "-std=c++17", "-Wall", "-Wextra",
                     "-Werror", "-O1", *["-I" + linux(path) for path in includes],
                     linux(source), "-o", linux(output)]
            execute = ["wsl", "--exec", linux(output)]
        else:
            raise RuntimeError("Host C++ compiler required; no skipped test success")
        subprocess.run(build, check=True)
        subprocess.run(execute, check=True)
        print("PASS real PromicroBoard battery-only ADC cache checks")


if __name__ == "__main__":
    main()
