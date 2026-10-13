"""Embed source identity without changing the MeshCore protocol version."""
import subprocess
import sys
from pathlib import Path

Import("env")

# SCons does not guarantee that the extra script's directory is importable.
sys.path.insert(0, str(Path(env.subst("$PROJECT_DIR")) / "tools"))
try:
    from smartui_source_guard import build_override_reason, checkout_root
finally:
    sys.path.pop(0)

try:
    root = checkout_root(Path(env.subst("$PROJECT_DIR")))
    sha = subprocess.check_output(
        ["git", "rev-parse", "--short=8", "HEAD"],
        cwd=root, text=True, stderr=subprocess.DEVNULL,
    ).strip()
    raw = subprocess.check_output(
        ["git", "diff", "--raw", "--no-renames", "--no-abbrev", "-z", "HEAD", "--"],
        cwd=root, stderr=subprocess.DEVNULL,
    ).split(b"\0")
    dirty = bool(subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard"], cwd=root).strip())
    dirty = dirty or build_override_reason(
        root, project_config=env.GetProjectConfig().path) is not None
    if raw[-1] != b"" or (len(raw) - 1) % 2:
        raise ValueError("unexpected Git raw diff format")
    # Inherited CRLF blobs may be reported dirty by Git's clean filter even
    # when their checkout bytes equal HEAD exactly. Do not ignore real edits.
    for index in range(0, len(raw) - 1, 2):
        fields = raw[index].split()
        relative = raw[index + 1].decode("utf-8")
        path = root / relative
        if (len(fields) != 5 or not fields[0].startswith(b":") or
                fields[0][1:] != fields[1] or
                fields[1] not in (b"100644", b"100755") or
                not path.is_file() or path.is_symlink()):
            dirty = True
            break
        original = subprocess.check_output(["git", "show", "HEAD:" + relative], cwd=root)
        if path.read_bytes() != original:
            dirty = True
            break
    if dirty:
        sha += "+dirty"
except (OSError, subprocess.CalledProcessError, ValueError):
    sha = "unknown"
env.Append(CPPDEFINES=[("SMARTUI_BUILD_SHA", '\\"' + sha + '\\"')])
