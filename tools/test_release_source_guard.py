#!/usr/bin/env python3
"""Exercise exact-source packaging against real Git line-ending edge cases."""

import os
import unittest
from unittest.mock import patch

from package_smartui_release import require_clean_checkout
from release_source_test_support import GitCheckoutFixture
from smartui_source_guard import BUILD_OVERRIDE_ENV


class SourceGuardTests(GitCheckoutFixture, unittest.TestCase):
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

    def test_untracked_source_is_rejected(self):
        (self.root / "new.cpp").write_bytes(b"int another = 3;\n")
        with self.assertRaisesRegex(ValueError, "untracked files"):
            require_clean_checkout(self.root)

    def test_staged_mode_change_is_rejected(self):
        self.git("update-index", "--chmod=+x", "source.cpp")
        self.rejected()

    def test_ignored_local_config_is_rejected_even_when_empty(self):
        local = self.root / "platformio.local.ini"
        for contents in (b"", b"[env:test]\nbuild_flags = -DLOCAL_OVERRIDE=1\n"):
            with self.subTest(contents=contents):
                local.write_bytes(contents)
                self.assertIn(b"platformio.local.ini", self.git("check-ignore", str(local)))
                with self.assertRaisesRegex(ValueError, "local build override: platformio.local.ini"):
                    require_clean_checkout(self.root)
        local.unlink()
        require_clean_checkout(self.root)

    def test_environment_build_overrides_are_rejected(self):
        for name in BUILD_OVERRIDE_ENV:
            with self.subTest(name=name), patch.dict(os.environ, {name: "private-value"}):
                with self.assertRaisesRegex(ValueError, "environment: " + name) as raised:
                    require_clean_checkout(self.root)
                self.assertNotIn("private-value", str(raised.exception))

    def test_output_environment_and_ignored_artifacts_remain_allowed(self):
        output = self.root / ".pio"
        output.mkdir()
        (output / "firmware.bin").write_bytes(b"cached output")
        with patch.dict(os.environ, {"PLATFORMIO_BUILD_DIR": str(output),
                                     "PLATFORMIO_UPLOAD_PORT": "unused"}):
            require_clean_checkout(self.root)

    def test_subdirectory_still_checks_worktree_root(self):
        child = self.root / "nested"
        child.mkdir()
        require_clean_checkout(child)
        (self.root / "platformio.local.ini").write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "platformio.local.ini"):
            require_clean_checkout(child)


if __name__ == "__main__":
    unittest.main()
