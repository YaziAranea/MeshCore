"""Shared checks for known local inputs outside the committed build config.

This is a source/configuration guard, not a claim of hermetic toolchains or
bit-for-bit reproducibility of downloaded dependencies.
"""

from pathlib import Path
import os
import subprocess


# PlatformIO 6.x project options that can change compiled sources or flags.
# Keep the legacy option aliases too. Cache/output locations and upload/monitor
# options do not change the source configuration and are deliberately omitted.
BUILD_OVERRIDE_ENV = (
    "PLATFORMIO_BUILD_FLAGS",
    "PLATFORMIO_BUILD_SRC_FLAGS",
    "PLATFORMIO_SRC_BUILD_FLAGS",
    "PLATFORMIO_BUILD_UNFLAGS",
    "PLATFORMIO_BUILD_SRC_FILTER",
    "PLATFORMIO_SRC_FILTER",
    "PLATFORMIO_EXTRA_SCRIPTS",
    "PLATFORMIO_LIB_EXTRA_DIRS",
    "PLATFORMIO_INCLUDE_DIR",
    "PLATFORMIO_SRC_DIR",
    "PLATFORMIO_LIB_DIR",
    "PLATFORMIO_DATA_DIR",
    "PLATFORMIO_BOARDS_DIR",
)


def checkout_root(path: Path) -> Path:
    """Resolve this worktree's root, including calls from a subdirectory."""
    result = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], cwd=path,
        text=True, stderr=subprocess.DEVNULL,
    ).strip()
    if not result:
        raise ValueError("Git did not return a checkout root")
    return Path(result).resolve()


def build_override_reason(root: Path, *, environ=None, project_config=None) -> str | None:
    """Return a diagnostic without disclosing environment variable contents."""
    local = root / "platformio.local.ini"
    # Reject even an empty file or a dangling symlink. Local configuration is
    # opt-in developer input; its absence is the release contract.
    if local.exists() or local.is_symlink():
        return "local build override: platformio.local.ini"
    if project_config is not None:
        config = Path(project_config)
        if not config.is_absolute():
            config = root / config
        if config.resolve() != (root / "platformio.ini").resolve():
            return "local build override: alternate PlatformIO project config"
    for name in BUILD_OVERRIDE_ENV:
        if (os.environ if environ is None else environ).get(name):
            return "local build override environment: " + name
    return None
