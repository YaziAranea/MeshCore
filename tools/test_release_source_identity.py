#!/usr/bin/env python3
"""Reject stale or dirty release inputs, including split UF2 string payloads."""
from pathlib import Path
import os
import runpy
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from package_smartui_release import validate_source_identity
from release_source_test_support import GitCheckoutFixture
from smartui_source_guard import BUILD_OVERRIDE_ENV

BUILD_SCRIPT = Path(__file__).with_name("smartui_build_identity.py")


class BuildIdentityTests(GitCheckoutFixture, unittest.TestCase):
    def identity(self, root=None, *, config=None, script=BUILD_SCRIPT):
        project_root = root or self.root
        definitions = []
        env = SimpleNamespace(
            subst=lambda value: str(project_root) if value == "$PROJECT_DIR" else value,
            GetProjectConfig=lambda: SimpleNamespace(path=str(config or project_root / "platformio.ini")),
            Append=lambda **values: definitions.extend(values["CPPDEFINES"]),
        )
        runpy.run_path(str(script), init_globals={"env": env, "Import": lambda name: None})
        self.assertEqual(len(definitions), 1)
        self.assertEqual(definitions[0][0], "SMARTUI_BUILD_SHA")
        return definitions[0][1]

    def expected(self, dirty=False):
        sha = self.git("rev-parse", "--short=8", "HEAD").decode().strip()
        return '\\"' + sha + ("+dirty" if dirty else "") + '\\"'

    def test_clean_identity_accepts_original_crlf_bytes(self):
        self.assertIn(b"source.cpp", self.git("diff", "--name-only", "HEAD", "--"))
        self.assertEqual(self.identity(), self.expected())

    def test_local_config_marks_build_dirty_even_when_empty(self):
        local = self.root / "platformio.local.ini"
        for contents in (b"", b"[env:test]\nbuild_flags = -DLOCAL_OVERRIDE=1\n"):
            with self.subTest(contents=contents):
                local.write_bytes(contents)
                self.assertEqual(self.identity(), self.expected(dirty=True))
        local.unlink()
        self.assertEqual(self.identity(), self.expected())

    def test_environment_overrides_mark_build_dirty(self):
        for name in BUILD_OVERRIDE_ENV:
            with self.subTest(name=name), patch.dict(os.environ, {name: "private-value"}):
                self.assertEqual(self.identity(), self.expected(dirty=True))

    def test_alternate_project_config_marks_build_dirty(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "custom.ini"
            config.write_text("[env:test]\nbuild_flags = -DEXTERNAL=1\n")
            self.assertEqual(self.identity(config=config), self.expected(dirty=True))

    def test_real_source_edit_marks_build_dirty(self):
        (self.root / "source.cpp").write_bytes(b"int value = 2;\r\n")
        self.assertEqual(self.identity(), self.expected(dirty=True))

    def test_staged_source_edit_marks_build_dirty(self):
        (self.root / "source.cpp").write_bytes(b"int value = 2;\n")
        self.git("add", "source.cpp")
        self.assertEqual(self.identity(), self.expected(dirty=True))

    def test_untracked_source_marks_build_dirty(self):
        (self.root / "new.cpp").write_bytes(b"int new_source = 1;\n")
        self.assertEqual(self.identity(), self.expected(dirty=True))

    def test_deleted_source_marks_build_dirty(self):
        (self.root / "source.cpp").unlink()
        self.assertEqual(self.identity(), self.expected(dirty=True))

    def test_staged_mode_change_marks_build_dirty(self):
        self.git("update-index", "--chmod=+x", "source.cpp")
        self.assertEqual(self.identity(), self.expected(dirty=True))

    def test_output_environment_does_not_mark_build_dirty(self):
        with patch.dict(os.environ, {"PLATFORMIO_BUILD_DIR": str(self.root / ".pio"),
                                     "PLATFORMIO_UPLOAD_PORT": "unused"}):
            self.assertEqual(self.identity(), self.expected())

    def test_subdirectory_uses_actual_worktree_root(self):
        child = self.root / "nested"
        child.mkdir()
        config = self.root / "platformio.ini"
        self.assertEqual(self.identity(child, config=config), self.expected())
        (self.root / "platformio.local.ini").write_bytes(b"")
        self.assertEqual(self.identity(child, config=config), self.expected(dirty=True))

    def test_linked_worktree_checks_its_own_local_config(self):
        with tempfile.TemporaryDirectory() as folder:
            worktree = Path(folder) / "linked"
            self.git("worktree", "add", "--quiet", "--detach", str(worktree), "HEAD")
            try:
                self.assertTrue((worktree / ".git").is_file())
                self.assertEqual(self.identity(worktree), self.expected())
                (self.root / "platformio.local.ini").write_bytes(b"")
                self.assertEqual(self.identity(worktree), self.expected())
                (worktree / "platformio.local.ini").write_bytes(b"")
                self.assertEqual(self.identity(worktree), self.expected(dirty=True))
            finally:
                self.git("worktree", "remove", "--force", str(worktree))

    def test_no_git_identity_is_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(self.identity(Path(folder)), '\\"unknown\\"')

class IdentityTests(unittest.TestCase):
    def check(self, payload, *, uf2=False, accepted=False):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / ('image.uf2' if uf2 else 'image.bin')
            if uf2:
                payload = b''.join(b'\0'*32 + payload[i:i+256].ljust(256, b'\xff') + b'\0'*224
                                   for i in range(0, len(payload), 256))
            path.write_bytes(payload)
            if accepted:
                validate_source_identity(path, '12345678' + '0'*32)
            else:
                with self.assertRaises(ValueError):
                    validate_source_identity(path, '12345678' + '0'*32)

    def test_current(self):
        self.check(b'prefixSmartUI-source:12345678\0suffix', accepted=True)
    def test_stale(self):
        self.check(b'SmartUI-source:87654321\0')
    def test_dirty(self):
        self.check(b'SmartUI-source:12345678+dirty\0')
    def test_unknown(self):
        self.check(b'SmartUI-source:unknown\0')
    def test_missing(self):
        self.check(b'T114 SmartUI 0.06\0')
    def test_mixed(self):
        self.check(b'SmartUI-source:12345678\0SmartUI-source:87654321\0')
    def test_split_uf2(self):
        self.check(b'\xff'*250+b'SmartUI-source:12345678\0', uf2=True, accepted=True)

if __name__ == '__main__':
    unittest.main()
