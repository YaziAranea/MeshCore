"""Read generated firmware bitmap bytes for QA without rerasterizing font files.

This module is independent of all simulators, so both the historical dense-UI
model and focused new-screen models can share exactly the same glyph source.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BITMAPS = (ROOT / "src/helpers/ui/EmbeddedBitmapFonts.h").read_text(encoding="utf-8")


class EmbeddedRaw:
    """Adapter matching the raw glyph API used by T096/T114 exact painters."""

    def __init__(self, prefix: str, table: str, index: int):
        key = f"{prefix}_{index}"
        table_match = re.search(rf"\b{re.escape(table)}\[\].*?=\s*\{{(.*?)\n\}};", BITMAPS, re.S)
        assert table_match, f"Missing firmware font table: {table}"
        row = re.search(
            rf"\{{{key}_name, \d+, (\d+), (\d+), (\d+), {key}_glyphs,", table_match.group(1),
        )
        assert row, (table, index)
        self.height, self.ascent, self.descent = map(int, row.groups())
        bitmap = re.search(rf"{key}_bitmap\[\] PROGMEM = \{{(.*?)\n\}};", BITMAPS, re.S)
        metrics = re.search(rf"{key}_glyphs\[\] PROGMEM = \{{(.*?)\n\}};", BITMAPS, re.S)
        assert bitmap and metrics, f"Missing bitmap or metrics for {key}"
        data = bytes(int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]+)", bitmap.group(1)))
        self.glyphs = {}
        for entry in re.findall(r"\{([^{}]+)\}", metrics.group(1)):
            cp, offset, width, height, row_bytes, advance, x_offset, y_offset = (
                int(value.strip(), 0) for value in entry.split(",")
            )
            # These fonts store full line-height rows. The existing driver/QA
            # painters therefore place bitmap row zero at the cursor y.
            assert self.ascent - (y_offset + height) == 0, (key, cp, "baseline")
            assert row_bytes * 8 >= width, (key, cp, "row width")
            assert 0 <= offset <= offset + height * row_bytes <= len(data), (key, cp, "bitmap bounds")
            self.glyphs[cp] = {
                "width": width, "height": height, "row_bytes": row_bytes,
                "x_advance": advance, "x_offset": x_offset,
                "data": data[offset:offset + height * row_bytes],
            }
        assert ord("?") in self.glyphs, f"Missing fallback glyph for {key}"

    def glyph(self, char: str) -> dict:
        return self.glyphs.get(ord(char), self.glyphs[ord("?")])
