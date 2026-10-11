"""Compile and execute the actual display-independent settings backend."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
from test_smartui_api import setting_effects_source
from test_sound_preview_runtime import main as test_sound_preview_runtime

ROOT = Path(__file__).resolve().parents[1]


def tone_boot_source():
    """Execute actual MyMesh tone initialization/load repair in both profiles."""
    mesh = (ROOT / "examples/companion_radio/MyMesh.cpp").read_text(encoding="utf-8")
    start = mesh.index("#if defined(UI_OPTIONAL_NOTIFY_TONE) && UI_OPTIONAL_NOTIFY_TONE")
    repair = mesh[start:mesh.index("  if (_prefs.notify_vibe_pin < -1)", start)]
    initialize = next(line for line in mesh.splitlines()
                      if "_prefs.notify_tone_pin = DEFAULT_NOTIFY_TONE_PIN;" in line
                      and line.strip().startswith("_prefs."))
    code = '#include <cassert>\n#include <cstdint>\n#include <cstdio>\n'
    code += 'struct NodePrefs { int8_t notify_tone_pin = -1; };\n'
    for name, optional, pin in (("optionalTone", 1, -1), ("fixedTone", 0, 13)):
        code += f'''#define UI_OPTIONAL_NOTIFY_TONE {optional}
#define PIN_MSG_TONE {pin}
#define DEFAULT_NOTIFY_TONE_PIN {pin}
static int {name}(int pin, bool fresh = false) {{
  NodePrefs _prefs;
  _prefs.notify_tone_pin = pin;
  if (fresh) {{ {initialize} }}
{repair}
  return _prefs.notify_tone_pin;
}}
#undef UI_OPTIONAL_NOTIFY_TONE
#undef PIN_MSG_TONE
#undef DEFAULT_NOTIFY_TONE_PIN
'''
    return code + r'''
int main() {
  assert(optionalTone(35, true) == -1);
  assert(optionalTone(-1) == -1);
  assert(optionalTone(35) == 35);
  assert(optionalTone(-128) == -1);
  assert(fixedTone(-1, true) == 13);
  assert(fixedTone(-1) == 13);
  assert(fixedTone(-128) == 13);
  assert(fixedTone(35) == 35);
  puts("PASS production tone boot: optional off/selection/corrupt repair, fixed-pin defaults preserved");
}
'''


def main():
    test_sound_preview_runtime()
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
        # Reuse only the current production hook fixture, not the archived C9
        # protocol suites. This exercises real main.cpp read/write/apply/rollback.
        runtime = Path(directory) / "device_settings_runtime.cpp"
        runtime.write_text(setting_effects_source(), encoding="utf-8")
        runtime_build = [part.replace("device_settings_test.cpp", "device_settings_runtime.cpp")
                         if isinstance(part, str) else part for part in build]
        original = str(paths[0]) if compiler else linux(paths[0])
        runtime_build[runtime_build.index(original.replace("device_settings_test.cpp", "device_settings_runtime.cpp"))] = (
            str(runtime) if compiler else linux(runtime))
        subprocess.run(runtime_build, check=True)
        subprocess.run(execute, check=True)
        # A persisted -1 must remain disabled at boot, while fixed-pin nRF
        # profiles keep their previous negative-value repair/default behavior.
        runtime.write_text(tone_boot_source(), encoding="utf-8")
        subprocess.run(runtime_build, check=True)
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
