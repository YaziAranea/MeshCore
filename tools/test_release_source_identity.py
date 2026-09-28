#!/usr/bin/env python3
"""Reject stale or dirty release inputs, including split UF2 string payloads."""
from pathlib import Path
import tempfile
import unittest
from package_smartui_release import validate_source_identity

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
