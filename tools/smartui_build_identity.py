"""Embed source identity without changing the MeshCore protocol version."""
import subprocess
from pathlib import Path

Import("env")

try:
    sha = subprocess.check_output(
        ["git", "rev-parse", "--short=8", "HEAD"],
        cwd=env.subst("$PROJECT_DIR"), text=True, stderr=subprocess.DEVNULL,
    ).strip()
    root = Path(env.subst("$PROJECT_DIR"))
    raw = subprocess.check_output(
        ["git", "diff", "--raw", "--no-renames", "--no-abbrev", "-z", "HEAD", "--"],
        cwd=root, stderr=subprocess.DEVNULL,
    ).split(b"\0")
    dirty = bool(subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard"], cwd=root).strip())
    # Inherited CRLF blobs may be reported dirty by Git's clean filter even
    # when their checkout bytes equal HEAD exactly. Do not ignore real edits.
    for index in range(0, len(raw) - 1, 2):
        fields = raw[index].split()
        relative = raw[index + 1].decode("utf-8")
        path = root / relative
        if (len(fields) != 5 or fields[0][1:] != fields[1] or
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
except (OSError, subprocess.CalledProcessError):
    sha = "unknown"
env.Append(CPPDEFINES=[("SMARTUI_BUILD_SHA", '\\"' + sha + '\\"')])
