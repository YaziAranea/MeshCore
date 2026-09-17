#!/usr/bin/env python3
"""Exercise exact-source packaging against real Git line-ending edge cases."""

from pathlib import Path
import subprocess
import tempfile
import unittest

from package_smartui_release import require_clean_checkout


class SourceGuardTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="smartui-source-guard-")
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.git("init", "--quiet")
        self.git("config", "user.name", "Source guard test")
        self.git("config", "user.email", "source-guard@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.git("config", "core.filemode", "false")
        (self.root / ".gitattributes").write_bytes(b"*.cpp -text\n")
        (self.root / "source.cpp").write_bytes(b"int value = 1;\r\n")
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "Inherited CRLF source")
        (self.root / ".gitattributes").write_bytes(b"*.cpp text eol=lf\n")
        self.git("add", ".gitattributes")
        self.git("commit", "--quiet", "-m", "New newline policy")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root,
                              capture_output=True, check=True).stdout

    def rejected(self):
        with self.assertRaisesRegex(ValueError, "dirty tracked checkout"):
            require_clean_checkout(self.root)

    def test_exact_crlf_blob_is_not_a_source_change(self):
        self.assertIn(b"source.cpp", self.git("diff", "--name-only", "HEAD", "--"))
        require_clean_checkout(self.root)

    def test_normalized_clean_checkout(self):
        self.git("add", "source.cpp")
        self.git("commit", "--quiet", "-m", "Normalize source")
        require_clean_checkout(self.root)

    def test_actual_code_edit_is_rejected(self):
        (self.root / "source.cpp").write_bytes(b"int value = 2;\r\n")
        self.rejected()

    def test_trailing_whitespace_edit_is_rejected(self):
        (self.root / "source.cpp").write_bytes(b"int value = 1; \r\n")
        self.rejected()

    def test_staged_code_edit_is_rejected(self):
        (self.root / "source.cpp").write_bytes(b"int value = 2;\n")
        self.git("add", "source.cpp")
        self.rejected()

    def test_deleted_source_is_rejected(self):
        (self.root / "source.cpp").unlink()
        self.rejected()

    def test_added_tracked_source_is_rejected(self):
        (self.root / "new.cpp").write_bytes(b"int another = 3;\n")
        self.git("add", "new.cpp")
        self.rejected()

    def test_staged_mode_change_is_rejected(self):
        self.git("update-index", "--chmod=+x", "source.cpp")
        self.rejected()


if __name__ == "__main__":
    unittest.main()
