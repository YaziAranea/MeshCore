"""Exercise production helper name/TX adapters with real MeshCore CLI parsing."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    compiler = shutil.which("g++") or shutil.which("clang++")
    with tempfile.TemporaryDirectory(prefix="core-settings-") as directory:
        def path(p):
            if compiler or os.name != "nt":
                return str(p)
            return subprocess.check_output(["wsl", "--exec", "wslpath", "-a", str(p)], text=True).strip()
        for optimization in ("-O1", "-Ofast"):
            include = ROOT / "examples/companion_radio"
            output = Path(directory) / ("test" + optimization)
            sources = [ROOT / "tools/core_settings_commands_test.cpp", include / "CoreSettingsCommands.cpp", include / "MeshCoreCli.cpp"]
            flags = ["-std=c++17", optimization, "-Wall", "-Wextra", "-Werror", "-I" + path(include), "-I" + path(ROOT / "src")]
            if os.environ.get("SMARTUI_TEST_SANITIZE") == "1":
                flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie"]
            prefix = [compiler] if compiler else ["wsl", "--exec", "g++"]
            subprocess.run(prefix + flags + [path(p) for p in sources] + ["-o", path(output)], check=True)
            subprocess.run([str(output)] if compiler else ["wsl", "--exec", path(output)], check=True)

if __name__ == "__main__":
    main()
