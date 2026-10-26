"""Compile and run the real PromicroBoard ADC/cache implementation with host stubs."""

from pathlib import Path
import configparser
import os
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    config = configparser.ConfigParser(interpolation=None)
    config.read(ROOT / "variants/promicro/platformio.ini", encoding="utf-8")
    limits = re.findall(r"-D\s+(ADC_CALIBRATION_MAX=\S+)", config["Promicro"]["build_flags"])
    assert len(limits) == 1, "ProMicro must supply one common ADC upper limit"
    flags = ["-D" + limits[0]]
    with tempfile.TemporaryDirectory(prefix="smartui-promicro-adc-") as directory:
        output = Path(directory) / "promicro_adc_cache_test"
        # Execute the actual menu bounds and clamp, without compiling display hardware.
        ui = (ROOT / "examples/companion_radio/ui-new/UITask.cpp").read_text(encoding="utf-8")
        bounds = ui[ui.index("#ifndef UI_ADC_MULTIPLIER_MIN"):ui.index("#if UI_HAS_JOYSTICK", ui.index("#ifndef UI_ADC_MULTIPLIER_MIN"))]
        start = ui.index("  float clampAdcMultiplier(float value) const {")
        clamp = ui[start:ui.index("\n  }", start) + len("\n  }")]
        (Path(directory) / "adc_ui_bounds.h").write_text(
            bounds + "\nstruct AdcMenu {\n" + clamp + "\n};\n", encoding="utf-8")
        sources = [ROOT / "tools/promicro_adc_cache_test.cpp",
                   ROOT / "examples/companion_radio/DeviceSettings.cpp",
                   ROOT / "examples/companion_radio/SmartUiCliSettings.cpp"]
        includes = [ROOT / "tools/test_stubs/promicro", ROOT / "src", ROOT,
                    ROOT / "examples/companion_radio", Path(directory)]
        compiler = shutil.which("g++") or shutil.which("clang++")
        if compiler:
            build = [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O1",
                     *flags, *["-I" + str(path) for path in includes],
                     *map(str, sources), "-o", str(output)]
            execute = [str(output)]
        elif os.name == "nt":
            def linux(path):
                return subprocess.check_output(
                    ["wsl", "--exec", "wslpath", "-a", str(path)], text=True
                ).strip()
            build = ["wsl", "--exec", "g++", "-std=c++17", "-Wall", "-Wextra",
                     "-Werror", "-O1", *flags, *["-I" + linux(path) for path in includes],
                     *map(linux, sources), "-o", linux(output)]
            execute = ["wsl", "--exec", linux(output)]
        else:
            raise RuntimeError("Host C++ compiler required; no skipped test success")
        for optimization in ("-O1", "-Ofast"):
            optimized = [optimization if part == "-O1" else part for part in build]
            subprocess.run(optimized, check=True)
            subprocess.run(execute, check=True)
            print(f"PASS real ProMicro ADC cache, menu range and settings persistence {optimization}")


if __name__ == "__main__":
    main()
