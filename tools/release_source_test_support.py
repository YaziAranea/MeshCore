"""Isolated Git fixtures shared by release guard and build identity tests."""

from pathlib import Path
import os
import subprocess
import tempfile
from unittest.mock import patch

from smartui_source_guard import BUILD_OVERRIDE_ENV


class GitCheckoutFixture:
    def setUp(self):
        self.env_patch = patch.dict(os.environ, {name: "" for name in BUILD_OVERRIDE_ENV})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.folder = tempfile.TemporaryDirectory(prefix="smartui-source-guard-")
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.git("init", "--quiet")
        self.git("config", "user.name", "Source guard test")
        self.git("config", "user.email", "source-guard@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.git("config", "core.filemode", "false")
        (self.root / ".gitignore").write_bytes(b"platformio.local.ini\n.pio/\n")
        (self.root / "platformio.ini").write_bytes(
            b"[platformio]\nextra_configs = platformio.local.ini\n"
            b"[env:test]\nbuild_flags = -DFIXTURE_BASE=1\n")
        (self.root / ".gitattributes").write_bytes(b"*.cpp -text\n")
        (self.root / "source.cpp").write_bytes(b"int value = 1;\r\n")
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "Inherited CRLF source")
        (self.root / ".gitattributes").write_bytes(b"*.cpp text eol=lf\n")
        self.git("add", ".gitattributes")
        self.git("commit", "--quiet", "-m", "New newline policy")
        # Force Git to recheck bytes after the attributes changed. Otherwise
        # the stat cache can legitimately retain the previous clean result.
        source = self.root / "source.cpp"
        stat = source.stat()
        os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root,
                              capture_output=True, check=True).stdout
