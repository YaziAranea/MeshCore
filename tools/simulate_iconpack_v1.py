"""MeshCore SMART icon pack experiment.

The firmware has to render monochrome symbols on very small displays.  This
script deliberately designs on a 12x12 integer grid and previews the exact
nearest-neighbour result at the sizes used by T114 and T096.
"""

from pathlib import Path
import re

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "qa_outputs" / "iconpack_v1"
OUT.mkdir(parents=True, exist_ok=True)

GRID = 12
BG = (3, 9, 12)
PANEL = (10, 22, 27)
GRID_COLOR = (34, 55, 60)
WHITE = (232, 247, 244)
MUTED = (120, 151, 151)
GREEN = (35, 238, 125)
YELLOW = (255, 221, 64)
CYAN = (54, 200, 255)
RED = (255, 81, 91)

FONT = Path("C:/Windows/Fonts/DejaVuSans.ttf")
FONT_BOLD = Path("C:/Windows/Fonts/DejaVuSans-Bold.ttf")


def font(size: int, bold: bool = False):
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT), size)


class PixelIcon:
    def __init__(self):
        self.image = Image.new("1", (GRID, GRID), 0)
        self.d = ImageDraw.Draw(self.image)

    def p(self, *points):
        for point in points:
            self.image.putpixel(point, 1)

    def line(self, points, width=1):
        self.d.line(points, fill=1, width=width)

    def rect(self, box, fill=None, width=1):
        self.d.rectangle(box, outline=1, fill=1 if fill else None, width=width)

    def ellipse(self, box, fill=None, width=1):
        self.d.ellipse(box, outline=1, fill=1 if fill else None, width=width)

    def poly(self, points, fill=None):
        self.d.polygon(points, outline=1, fill=1 if fill else None)

    def cut(self, box):
        self.d.rectangle(box, fill=0)


def pixel_pattern(rows: tuple[str, ...]) -> Image.Image:
    width = len(rows[0])
    if not rows or any(len(row) != width for row in rows):
        raise ValueError("Pixel pattern rows must have equal width")
    image = Image.new("1", (width, len(rows)), 0)
    for y, row in enumerate(rows):
        for x, value in enumerate(row):
            if value == "#":
                image.putpixel((x, y), 1)
    return image


def face(kind: str) -> Image.Image:
    c = PixelIcon()
    c.ellipse((1, 1, 10, 10), width=1)
    if kind == "wink":
        c.line((3, 4, 5, 4))
        c.p((8, 4))
    elif kind == "cool":
        c.rect((2, 3, 5, 5))
        c.rect((7, 3, 10, 5))
        c.line((5, 4, 7, 4))
    elif kind == "love":
        c.poly(((2, 3), (3, 2), (4, 3), (5, 2), (6, 3), (4, 6)), fill=True)
        c.poly(((6, 3), (7, 2), (8, 3), (9, 2), (10, 3), (8, 6)), fill=True)
    elif kind == "sleep":
        c.line((3, 4, 5, 4))
        c.line((7, 4, 9, 4))
        c.line((9, 1, 11, 1, 9, 3, 11, 3))
    elif kind == "think":
        c.p((4, 4), (8, 4))
        c.line((4, 8, 8, 7))
        c.ellipse((9, 8, 11, 10), fill=True)
    elif kind == "party":
        c.p((4, 4), (8, 4))
        c.line((4, 8, 8, 7))
        c.poly(((6, 1), (8, 0), (9, 3)), fill=True)
        c.line((0, 2, 2, 3))
    elif kind == "unknown":
        c.p((4, 4))
        c.line((7, 3, 9, 3, 9, 5, 7, 7))
        c.p((7, 9))
    else:
        c.p((4, 4), (8, 4))

    if kind in ("smile", "wink", "love", "cool", "party"):
        c.line((3, 7, 4, 8, 6, 9, 8, 8, 9, 7))
    elif kind == "grin":
        c.rect((3, 7, 9, 9))
        c.line((4, 8, 8, 8))
    elif kind == "laugh":
        c.poly(((3, 7), (9, 7), (8, 10), (4, 10)), fill=True)
        c.line((4, 8, 8, 8), width=1)
    elif kind == "neutral":
        c.line((3, 8, 9, 8))
    elif kind == "wow":
        c.ellipse((5, 7, 7, 9))
    elif kind == "cry":
        c.line((3, 7, 4, 8, 6, 7, 8, 8, 9, 7))
        c.line((2, 5, 1, 8, 2, 9))
    elif kind == "angry":
        c.line((2, 3, 5, 4))
        c.line((7, 4, 10, 3))
        c.line((3, 9, 5, 7, 7, 7, 9, 9))
    elif kind == "sleep":
        c.line((4, 8, 8, 8))
    elif kind == "think":
        pass
    return c.image


def make_icon(kind: str) -> Image.Image:
    if kind in {
        "smile", "grin", "laugh", "wink", "cool", "love", "think",
        "neutral", "wow", "sleep", "party", "cry", "angry", "unknown",
    }:
        return face(kind)

    c = PixelIcon()

    if kind == "skull":
        c.ellipse((2, 1, 9, 8), fill=True)
        c.rect((3, 7, 8, 10), fill=True)
        c.cut((4, 4, 4, 5)); c.cut((7, 4, 7, 5))
        c.cut((5, 7, 6, 7)); c.cut((4, 9, 4, 10)); c.cut((7, 9, 7, 10))
    elif kind == "ghost":
        c.ellipse((2, 1, 9, 8), fill=True)
        c.rect((2, 5, 9, 10), fill=True)
        c.cut((4, 4, 4, 5)); c.cut((7, 4, 7, 5))
        c.cut((3, 10, 4, 11)); c.cut((7, 10, 8, 11))
    elif kind == "heart":
        c.poly(((1, 4), (2, 2), (4, 2), (6, 4), (8, 2), (10, 2),
                (11, 4), (10, 6), (6, 10), (2, 6)), fill=True)
    elif kind == "hundred":
        c.line((1, 3, 2, 2, 2, 9))
        c.ellipse((4, 2, 7, 9))
        c.ellipse((8, 2, 11, 9))
    elif kind in ("thumb_up", "thumb_down"):
        c.rect((1, 5, 3, 10), fill=True)
        c.poly(((4, 5), (6, 5), (7, 1), (9, 2), (9, 5), (11, 5),
                (10, 10), (4, 10)), fill=True)
        if kind == "thumb_down":
            c.image = c.image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    elif kind == "wave":
        c.poly(((2, 4), (3, 3), (4, 6), (4, 1), (6, 1), (6, 5),
                (7, 0), (8, 1), (8, 5), (10, 2), (11, 3), (9, 9),
                (6, 11), (3, 9)), fill=True)
        c.cut((5, 7, 6, 7))
    elif kind == "pray":
        c.poly(((3, 1), (5, 5), (5, 10), (2, 9), (1, 6)), fill=True)
        c.poly(((8, 1), (6, 5), (6, 10), (9, 9), (10, 6)), fill=True)
        c.cut((5, 7, 6, 11))
    elif kind == "person":
        c.ellipse((4, 0, 7, 3), fill=True)
        c.ellipse((1, 5, 10, 12), fill=True)
        c.cut((0, 10, 11, 11))
    elif kind == "group":
        c.ellipse((4, 1, 7, 4), fill=True)
        c.ellipse((0, 3, 3, 6), fill=True); c.ellipse((8, 3, 11, 6), fill=True)
        c.poly(((3, 6), (8, 6), (10, 11), (1, 11)), fill=True)
        c.rect((0, 7, 2, 10), fill=True); c.rect((9, 7, 11, 10), fill=True)
    elif kind == "pager":
        c.rect((1, 2, 10, 10), width=1)
        c.rect((3, 4, 8, 6), fill=True)
        c.p((4, 8), (6, 8), (8, 8))
        c.line((8, 2, 10, 0))
    elif kind == "battery":
        c.rect((1, 3, 9, 9), width=1)
        c.rect((10, 5, 11, 7), fill=True)
        c.rect((3, 5, 7, 7), fill=True)
    elif kind == "plug":
        c.line((4, 1, 4, 4)); c.line((8, 1, 8, 4))
        c.rect((3, 4, 9, 7), fill=True)
        c.line((6, 7, 6, 11), width=2)
    elif kind == "power":
        c.line((6, 1, 6, 6), width=2)
        c.d.arc((1, 2, 10, 11), 305, 235, fill=1, width=2)
    elif kind == "lamp":
        c.ellipse((2, 0, 9, 7), fill=True)
        c.cut((4, 5, 7, 7))
        c.rect((4, 7, 7, 10), fill=True)
        c.line((5, 11, 6, 11))
    elif kind == "clover":
        c.ellipse((2, 1, 6, 5), fill=True); c.ellipse((6, 1, 10, 5), fill=True)
        c.ellipse((2, 5, 6, 9), fill=True); c.ellipse((6, 5, 10, 9), fill=True)
        c.line((6, 7, 8, 11), width=1)
        c.p((6, 5))
    elif kind == "home":
        c.poly(((0, 5), (6, 0), (11, 5)), fill=True)
        c.rect((2, 5, 9, 11), fill=True)
        c.cut((5, 7, 7, 11)); c.cut((3, 6, 4, 7))
    elif kind == "office":
        c.rect((2, 1, 9, 11), fill=True)
        for y in (3, 6):
            c.cut((4, y, 4, y)); c.cut((7, y, 7, y))
        c.cut((5, 9, 6, 11))
    elif kind == "shop":
        c.rect((1, 4, 10, 11), fill=True)
        c.poly(((1, 2), (10, 2), (11, 5), (0, 5)), fill=True)
        c.cut((3, 3, 3, 4)); c.cut((6, 3, 6, 4)); c.cut((9, 3, 9, 4))
        c.cut((3, 7, 6, 10)); c.cut((8, 7, 9, 11))
    elif kind == "hospital":
        c.rect((1, 2, 10, 11), fill=True)
        c.cut((3, 4, 8, 9))
        c.rect((5, 4, 6, 9), fill=True); c.rect((3, 6, 8, 7), fill=True)
    elif kind == "bank":
        c.poly(((1, 4), (6, 0), (11, 4)), fill=True)
        c.line((1, 5, 11, 5), width=1); c.line((0, 11, 11, 11), width=2)
        for x in (2, 5, 8):
            c.rect((x, 6, x + 1, 10), fill=True)
    elif kind == "school":
        c.rect((2, 4, 10, 11), fill=True)
        c.poly(((1, 4), (6, 1), (11, 4)), fill=True)
        c.ellipse((5, 3, 7, 5)); c.cut((5, 7, 7, 11))
        c.line((2, 0, 2, 4)); c.poly(((2, 0), (5, 1), (2, 2)), fill=True)
    elif kind == "factory":
        c.rect((1, 5, 10, 11), fill=True)
        c.poly(((1, 5), (4, 2), (4, 5), (7, 2), (7, 5), (10, 3), (10, 6)), fill=True)
        c.rect((9, 0, 10, 5), fill=True)
        c.cut((3, 7, 4, 8)); c.cut((7, 7, 8, 8))
    elif kind == "construction":
        c.line((2, 1, 2, 11), width=2)
        c.line((1, 2, 10, 2))
        c.line((4, 0, 4, 4))
        c.line((9, 2, 9, 7))
        c.line((9, 7, 7, 7))
        c.line((1, 11, 5, 11))
    elif kind == "camp":
        c.poly(((0, 11), (6, 1), (11, 11)), fill=True)
        c.cut((5, 5, 6, 11))
        c.line((1, 11, 10, 11))
    elif kind == "sofa":
        c.rect((2, 5, 9, 9), fill=True)
        c.rect((0, 6, 2, 10), fill=True); c.rect((9, 6, 11, 10), fill=True)
        c.line((1, 10, 10, 10), width=2)
        c.cut((5, 5, 5, 8))
    elif kind == "pin":
        c.ellipse((2, 0, 9, 7), fill=True)
        c.poly(((3, 5), (8, 5), (6, 11)), fill=True)
        c.cut((5, 2, 6, 3))
    elif kind == "clip":
        c.d.arc((2, 0, 9, 11), 270, 90, fill=1, width=2)
        c.d.arc((4, 2, 8, 9), 90, 270, fill=1, width=1)
    elif kind == "gear":
        c.ellipse((2, 2, 9, 9), fill=True)
        c.rect((5, 0, 6, 11), fill=True); c.rect((0, 5, 11, 6), fill=True)
        c.poly(((2, 1), (10, 9), (9, 10), (1, 2)), fill=True)
        c.poly(((9, 1), (1, 9), (2, 10), (10, 2)), fill=True)
        c.cut((5, 5, 6, 6))
    elif kind == "wrench":
        c.ellipse((0, 0, 5, 5), fill=True); c.cut((0, 0, 2, 2))
        c.line((4, 4, 10, 10), width=3)
        c.cut((9, 9, 10, 10))
    elif kind == "hammer":
        c.poly(((1, 1), (7, 1), (8, 3), (6, 5), (1, 4)), fill=True)
        c.line((6, 4, 10, 10), width=2)
    elif kind == "screwdriver":
        c.poly(((1, 1), (4, 1), (5, 4), (3, 6), (1, 4)), fill=True)
        c.line((4, 5, 10, 11), width=2)
    elif kind == "nut":
        c.poly(((3, 1), (8, 1), (11, 6), (8, 10), (3, 10), (0, 6)), fill=True)
        c.cut((4, 4, 7, 7))
    elif kind == "pick":
        c.d.arc((0, 0, 11, 7), 190, 350, fill=1, width=2)
        c.line((6, 5, 4, 11), width=2)
    elif kind == "antenna":
        c.line((6, 4, 6, 11), width=2)
        c.line((3, 11, 9, 11), width=1)
        c.d.arc((3, 1, 9, 7), 205, 335, fill=1, width=1)
        c.d.arc((0, 0, 11, 9), 205, 335, fill=1, width=1)
        c.p((6, 4))
    elif kind == "signal":
        c.rect((1, 8, 2, 11), fill=True); c.rect((4, 6, 5, 11), fill=True)
        c.rect((7, 3, 8, 11), fill=True); c.rect((10, 0, 11, 11), fill=True)
    elif kind == "radio":
        c.rect((1, 3, 10, 10), width=1)
        c.line((8, 3, 10, 0))
        c.ellipse((3, 5, 6, 8)); c.p((8, 5), (8, 7))
    elif kind == "phone":
        c.rect((3, 0, 8, 11), width=1)
        c.rect((4, 2, 7, 8)); c.line((5, 10, 6, 10))
    elif kind == "pc":
        c.rect((1, 1, 10, 8), width=1)
        c.rect((3, 3, 8, 6), fill=True)
        c.line((6, 8, 6, 10)); c.line((3, 11, 9, 11), width=1)
    elif kind == "camera":
        c.rect((1, 3, 10, 10), width=1)
        c.rect((3, 1, 7, 3), fill=True); c.ellipse((4, 5, 7, 8), fill=True)
    elif kind in ("sound", "mute"):
        c.poly(((1, 5), (4, 5), (7, 2), (7, 10), (4, 7), (1, 7)), fill=True)
        if kind == "sound":
            c.d.arc((6, 3, 10, 9), 285, 75, fill=1, width=1)
            c.d.arc((7, 1, 11, 11), 285, 75, fill=1, width=1)
        else:
            c.line((8, 4, 11, 8), width=2); c.line((11, 4, 8, 8), width=2)
    elif kind == "check":
        c.line((1, 6, 4, 9, 10, 2), width=2)
    elif kind == "cross":
        c.line((2, 2, 9, 9), width=2); c.line((9, 2, 2, 9), width=2)
    elif kind == "warning":
        c.poly(((6, 0), (11, 10), (0, 10)))
        c.line((6, 3, 6, 7), width=2); c.p((6, 9))
    elif kind == "star":
        c.poly(((6, 0), (7, 4), (11, 4), (8, 7), (9, 11),
                (6, 9), (3, 11), (4, 7), (1, 4), (5, 4)), fill=True)
    elif kind == "fire":
        c.poly(((6, 0), (8, 4), (10, 3), (11, 7), (9, 11), (3, 11),
                (1, 8), (3, 3), (5, 6)), fill=True)
        c.cut((5, 7, 6, 10))
    elif kind == "rocket":
        c.poly(((2, 9), (4, 3), (8, 0), (9, 4), (6, 9)), fill=True)
        c.cut((6, 3, 7, 4)); c.line((3, 8, 1, 11), width=2); c.line((6, 9, 5, 11), width=2)
    elif kind == "compass":
        c.ellipse((1, 1, 10, 10))
        c.poly(((7, 2), (6, 7), (3, 9), (5, 5)), fill=True)
    elif kind == "map":
        c.poly(((0, 2), (4, 1), (8, 3), (11, 1), (11, 9), (8, 11), (4, 9), (0, 11)))
        c.line((4, 1, 4, 9)); c.line((8, 3, 8, 11))
    elif kind == "car":
        c.poly(((1, 6), (3, 3), (8, 3), (10, 6), (11, 7), (10, 9), (1, 9), (0, 7)), fill=True)
        c.cut((4, 4, 7, 5)); c.cut((2, 8, 3, 10)); c.cut((8, 8, 9, 10))
    elif kind == "truck":
        c.rect((0, 3, 7, 8), fill=True)
        c.poly(((7, 5), (9, 5), (11, 7), (11, 9), (7, 9)), fill=True)
        c.cut((8, 6, 9, 7)); c.cut((2, 8, 3, 10)); c.cut((8, 8, 9, 10))
    elif kind == "bike":
        c.ellipse((0, 6, 4, 10)); c.ellipse((7, 6, 11, 10))
        c.line((2, 8, 5, 4, 8, 8, 4, 8, 2, 8))
        c.line((5, 4, 8, 4)); c.line((8, 4, 9, 8))
    elif kind == "walk":
        c.ellipse((5, 0, 7, 2), fill=True)
        c.line((6, 3, 5, 7, 2, 11), width=2)
        c.line((5, 5, 9, 6)); c.line((5, 7, 9, 11), width=2)
    elif kind == "satellite":
        return pixel_pattern((
            "..........#.",
            "........#...",
            "......#.....",
            "...######...",
            "..########..",
            ".##......##.",
            "..########..",
            "...######...",
            ".....##.....",
            "....####....",
            "...######...",
            "............",
        ))
    elif kind == "alarm":
        c.d.arc((3, 3, 8, 10), 180, 360, fill=1, width=2)
        c.rect((3, 6, 8, 9), fill=True)
        c.line((2, 10, 9, 10), width=2)
        c.line((1, 3, 0, 2)); c.line((10, 3, 11, 2)); c.line((6, 1, 6, 0))
    elif kind in ("lock", "unlock"):
        c.rect((2, 5, 9, 11), fill=True)
        if kind == "lock":
            c.d.arc((3, 0, 8, 7), 180, 360, fill=1, width=2)
        else:
            c.d.arc((5, 0, 10, 7), 180, 320, fill=1, width=2)
        c.cut((5, 7, 6, 9))
    elif kind == "key":
        c.ellipse((0, 1, 5, 6), width=2)
        c.line((4, 5, 10, 11), width=2)
        c.line((8, 9, 10, 7)); c.line((9, 10, 11, 8))
    elif kind == "message":
        c.rect((1, 1, 10, 8), fill=True)
        c.poly(((3, 8), (3, 11), (7, 8)), fill=True)
        c.cut((3, 4, 8, 4))
    elif kind == "mail":
        c.rect((1, 2, 10, 9))
        c.line((1, 2, 6, 6, 10, 2)); c.line((1, 9, 4, 6)); c.line((10, 9, 8, 6))
    elif kind == "box":
        c.poly(((1, 3), (6, 0), (11, 3), (6, 6)))
        c.poly(((1, 3), (6, 6), (6, 11), (1, 8)))
        c.poly(((11, 3), (6, 6), (6, 11), (11, 8)))
        c.line((1, 3, 6, 6, 11, 3)); c.line((6, 6, 6, 11))
    elif kind == "note":
        c.rect((2, 1, 9, 10))
        c.line((4, 4, 8, 4)); c.line((4, 6, 8, 6)); c.line((4, 8, 7, 8))
        c.poly(((2, 8), (2, 11), (5, 10)), fill=True)
    elif kind == "calendar":
        c.rect((1, 2, 10, 10)); c.line((1, 5, 10, 5))
        c.line((3, 0, 3, 3), width=2); c.line((8, 0, 8, 3), width=2)
        c.p((4, 7), (6, 7), (8, 7), (4, 9), (6, 9))
    elif kind == "clock":
        c.ellipse((1, 1, 10, 10))
        c.line((6, 3, 6, 6, 9, 8), width=1); c.p((6, 6))
    elif kind == "temperature":
        c.ellipse((3, 7, 8, 11), fill=True)
        c.rect((5, 1, 7, 9)); c.line((6, 4, 6, 9), width=2)
    elif kind == "sun":
        c.ellipse((3, 3, 8, 8), fill=True)
        for a, b in (((6, 0), (6, 2)), ((6, 9), (6, 11)), ((0, 6), (2, 6)),
                     ((9, 6), (11, 6)), ((1, 1), (3, 3)), ((9, 9), (11, 11)),
                     ((9, 3), (11, 1)), ((1, 11), (3, 9))):
            c.line((a, b))
    elif kind == "cloud":
        c.ellipse((1, 5, 10, 10), fill=True); c.ellipse((3, 2, 8, 8), fill=True)
    elif kind in ("rain", "snow"):
        c.ellipse((1, 3, 10, 8), fill=True); c.ellipse((3, 1, 8, 6), fill=True)
        if kind == "rain":
            c.line((3, 9, 2, 11)); c.line((6, 9, 5, 11)); c.line((9, 9, 8, 11))
        else:
            c.p((2, 10), (5, 9), (8, 10), (10, 9))
    elif kind in ("ball", "football", "basketball", "tennis"):
        c.ellipse((1, 1, 10, 10))
        if kind == "football":
            c.poly(((6, 4), (8, 5), (7, 8), (4, 8), (3, 5)), fill=True)
            c.line((4, 2, 6, 4)); c.line((8, 5, 10, 4)); c.line((7, 8, 8, 10))
        elif kind == "basketball":
            c.line((6, 1, 6, 10)); c.line((1, 6, 10, 6))
            c.d.arc((2, 1, 9, 10), 90, 270, fill=1); c.d.arc((2, 1, 9, 10), 270, 90, fill=1)
        elif kind == "tennis":
            c.d.arc((-2, 1, 6, 10), 270, 90, fill=1)
            c.d.arc((5, 1, 13, 10), 90, 270, fill=1)
        else:
            c.d.arc((2, 2, 9, 9), 200, 350, fill=1)
    else:
        raise KeyError(kind)
    return c.image


CATEGORIES = [
    ("Лица", [
        ("smile", "улыбка", ":)"), ("grin", "оскал", ":D"), ("laugh", "смех", "xD"),
        ("wink", "подмиг.", ";)"), ("cool", "крутой", "B)"), ("love", "любовь", "[love]"),
        ("think", "думаю", "[think]"), ("neutral", "нейтр.", "[meh]"),
        ("wow", "удивл.", "[wow]"), ("sleep", "сон", "[sleep]"),
        ("party", "праздник", "[party]"), ("cry", "грусть", ":'("),
        ("angry", "злость", ">:("), ("unknown", "не знаю", "[emo]"),
        ("skull", "череп", "[skull]"), ("ghost", "призрак", "[ghost]"),
    ]),
    ("Жесты и люди", [
        ("heart", "сердце", "<3"), ("thumb_up", "палец +", "+1"),
        ("thumb_down", "палец -", "-1"), ("wave", "привет", "[hand]"),
        ("pray", "прошу", "pls"), ("person", "человек", "[usr]"), ("group", "группа", "[grp]"),
        ("hundred", "сто", "100"),
    ]),
    ("Места", [
        ("home", "дом", "[home]"), ("office", "офис", "[ofc]"), ("shop", "магазин", "[shop]"),
        ("hospital", "медицина", "[med]"), ("bank", "банк", "[bank]"),
        ("school", "школа", "[sch]"), ("factory", "завод", "[fab]"),
        ("construction", "стройка", "[build]"),
        ("camp", "лагерь", "[camp]"), ("sofa", "диван", "[sofa]"),
    ]),
    ("Связь и устройства", [
        ("pager", "пейджер", "[pg]"), ("antenna", "антенна", "[ant]"),
        ("signal", "сигнал", "[sig]"), ("radio", "радио", "[radio]"),
        ("phone", "телефон", "[tel]"), ("pc", "компьютер", "[pc]"),
        ("camera", "камера", "[cam]"), ("sound", "звук", "[snd]"), ("mute", "без звука", "[mute]"),
        ("battery", "батарея", "[bat]"), ("plug", "зарядка", "[chg]"), ("power", "питание", "[pow]"),
    ]),
    ("Инструменты", [
        ("gear", "настройки", "[cfg]"), ("wrench", "ключ", "[fix]"),
        ("hammer", "молоток", "[ham]"), ("screwdriver", "отвёртка", "[drv]"),
        ("nut", "гайка", "[nut]"), ("pick", "кирка", "[pick]"), ("lamp", "лампа", "[lamp]"),
    ]),
    ("Путь и транспорт", [
        ("pin", "геометка", "[loc]"), ("compass", "навигация", "[nav]"),
        ("map", "карта", "[map]"), ("satellite", "спутник", "[sat]"),
        ("car", "машина", "[car]"), ("truck", "грузовик", "[truck]"),
        ("bike", "велосипед", "[bike]"), ("walk", "пешком", "[walk]"), ("rocket", "ракета", "go"),
    ]),
    ("Сообщения и система", [
        ("message", "сообщение", "[msg]"), ("mail", "письмо", "[mail]"),
        ("box", "посылка", "[box]"), ("clip", "скрепка", "[clip]"),
        ("note", "заметка", "[note]"), ("calendar", "дата", "[date]"),
        ("clock", "время", "[time]"), ("alarm", "сирена", "[alarm]"),
        ("lock", "закрыто", "[lock]"), ("unlock", "открыто", "[open]"), ("key", "ключ", "[key]"),
        ("check", "готово", "OK"), ("cross", "ошибка", "X"), ("warning", "опасность", "[warn]"),
        ("star", "звезда", "*"), ("fire", "огонь", "hot"), ("clover", "удача", "[ok]"),
    ]),
    ("Погода и спорт", [
        ("temperature", "температ.", "[temp]"), ("sun", "солнце", "[sun]"),
        ("cloud", "облако", "[cloud]"), ("rain", "дождь", "[rain]"), ("snow", "снег", "[snow]"),
        ("ball", "мяч", "[ball]"), ("football", "футбол", "[foot]"),
        ("basketball", "баскетбол", "[basket]"), ("tennis", "теннис", "[tennis]"),
    ]),
]

NEW_LEGACY_ICONS = [
    ("emoji_pray_icon", "pray"),
    ("emoji_office_icon", "office"),
    ("emoji_shop_icon", "shop"),
    ("emoji_hospital_icon", "hospital"),
    ("emoji_bank_icon", "bank"),
    ("emoji_school_icon", "school"),
    ("emoji_construction_icon", "construction"),
    ("emoji_camp_icon", "camp"),
    ("emoji_clip_icon", "clip"),
    ("emoji_power_icon", "power"),
    ("emoji_hammer_icon", "hammer"),
    ("emoji_screwdriver_icon", "screwdriver"),
    ("emoji_nut_icon", "nut"),
    ("emoji_compass_icon", "compass"),
    ("emoji_truck_icon", "truck"),
    ("emoji_unlock_icon", "unlock"),
    ("emoji_ball_icon", "ball"),
    ("emoji_football_icon", "football"),
    ("emoji_basketball_icon", "basketball"),
    ("emoji_tennis_icon", "tennis"),
]

FIRMWARE_ICON_MAP = [
    ("smile", ["emoji_smile_icon"]),
    ("grin", ["emoji_grin_icon"]),
    ("laugh", ["emoji_laugh_icon"]),
    ("wink", ["emoji_wink_icon"]),
    ("cool", ["emoji_cool_icon"]),
    ("love", ["emoji_love_face_icon"]),
    ("think", ["emoji_think_icon"]),
    ("neutral", ["emoji_neutral_icon"]),
    ("wow", ["emoji_surprise_icon", "client_repeat_unknown_icon"]),
    ("sleep", ["emoji_sleep_icon"]),
    ("party", ["emoji_party_icon"]),
    ("cry", ["emoji_cry_icon", "emoji_sad_icon"]),
    ("angry", ["emoji_angry_icon"]),
    ("unknown", ["emoji_unknown_icon"]),
    ("skull", ["emoji_skull_icon"]),
    ("ghost", ["emoji_ghost_icon"]),
    ("heart", ["emoji_heart_icon"]),
    ("hundred", ["emoji_100_icon"]),
    ("thumb_up", ["emoji_thumb_up_icon"]),
    ("thumb_down", ["emoji_thumb_down_icon"]),
    ("wave", ["emoji_hand_icon"]),
    ("pray", ["emoji_pray_icon"]),
    ("person", ["emoji_person_icon"]),
    ("group", ["emoji_group_icon"]),
    ("pager", ["emoji_pager_icon", "pager_route_icon"]),
    ("battery", ["emoji_battery_icon"]),
    ("plug", ["emoji_plug_icon"]),
    ("power", ["emoji_power_icon"]),
    ("lamp", ["emoji_lamp_icon"]),
    ("clover", ["emoji_clover_icon"]),
    ("office", ["emoji_building_icon", "emoji_office_icon"]),
    ("shop", ["emoji_shop_icon"]),
    ("hospital", ["emoji_hospital_icon"]),
    ("bank", ["emoji_bank_icon"]),
    ("school", ["emoji_school_icon"]),
    ("construction", ["emoji_construction_icon"]),
    ("factory", ["emoji_factory_icon"]),
    ("home", ["emoji_home_icon"]),
    ("camp", ["emoji_camp_icon"]),
    ("pin", ["emoji_pin_icon", "emoji_location_icon"]),
    ("clip", ["emoji_clip_icon"]),
    ("sofa", ["emoji_sofa_icon"]),
    ("gear", ["emoji_gear_icon"]),
    ("wrench", ["emoji_tool_icon"]),
    ("hammer", ["emoji_hammer_icon"]),
    ("screwdriver", ["emoji_screwdriver_icon"]),
    ("nut", ["emoji_nut_icon"]),
    ("pick", ["emoji_pick_icon"]),
    ("antenna", ["emoji_antenna_icon"]),
    ("signal", ["emoji_signal_icon", "mesh_traffic_icon"]),
    ("radio", ["emoji_radio_icon"]),
    ("phone", ["emoji_phone_icon"]),
    ("pc", ["emoji_pc_icon"]),
    ("camera", ["emoji_camera_icon"]),
    ("sound", ["emoji_sound_icon"]),
    ("mute", ["muted_icon"]),
    ("check", ["emoji_check_icon"]),
    ("cross", ["emoji_cross_icon"]),
    ("warning", ["emoji_warn_icon"]),
    ("star", ["emoji_star_icon"]),
    ("fire", ["emoji_fire_icon"]),
    ("rocket", ["emoji_rocket_icon"]),
    ("compass", ["emoji_compass_icon"]),
    ("map", ["emoji_map_icon"]),
    ("car", ["emoji_car_icon"]),
    ("truck", ["emoji_truck_icon"]),
    ("bike", ["emoji_bike_icon"]),
    ("walk", ["emoji_walk_icon"]),
    ("satellite", ["satellite_icon"]),
    ("alarm", ["emoji_alarm_icon"]),
    ("lock", ["emoji_lock_icon"]),
    ("unlock", ["emoji_unlock_icon"]),
    ("key", ["emoji_key_icon"]),
    ("message", ["emoji_msg_icon"]),
    ("mail", ["emoji_mail_icon", "direct_packet_icon"]),
    ("box", ["emoji_box_icon"]),
    ("note", ["emoji_note_icon"]),
    ("calendar", ["emoji_date_icon"]),
    ("clock", ["emoji_time_icon"]),
    ("temperature", ["emoji_temp_icon"]),
    ("sun", ["emoji_sun_icon"]),
    ("cloud", ["emoji_cloud_icon"]),
    ("rain", ["emoji_rain_icon"]),
    ("snow", ["emoji_snow_icon"]),
    ("ball", ["emoji_ball_icon"]),
    ("football", ["emoji_football_icon"]),
    ("basketball", ["emoji_basketball_icon"]),
    ("tennis", ["emoji_tennis_icon"]),
]

SMALL8_PATTERNS = {
    "mute": (
        "........", "..#...#.", ".##.#.#.", "####.#..",
        "####.#..", ".##.#.#.", "..#...#.", "........",
    ),
    "sound": (
        "........", "..#..#..", ".##...#.", "###....#",
        "###....#", ".##...#.", "..#..#..", "........",
    ),
    "satellite": (
        "......#.", "....#.#.", "..####..", ".######.",
        "##....##", ".######.", "...##...", "..####..",
    ),
    "pager": (
        ".######.", "#......#", "#.####.#", "#.#..#.#",
        "#.####.#", "#......#", "#.#.#..#", ".######.",
    ),
    "home": (
        "...##...", "..####..", ".######.", "##....##",
        ".######.", ".##..##.", ".##..##.", ".######.",
    ),
    "office": (
        ".######.", ".#.##.#.", ".#.##.#.", ".#.##.#.",
        ".#.##.#.", ".#....#.", ".#.##.#.", ".######.",
    ),
    "shop": (
        ".######.", "########", "#.#.#.##", "########",
        "#......#", "#.####.#", "#.#..#.#", "########",
    ),
    "hospital": (
        "...##...", "...##...", ".######.", ".######.",
        "...##...", "...##...", "...##...", "........",
    ),
    "bank": (
        "...##...", "..####..", ".######.", "########",
        ".#.#.#..", ".#.#.#..", ".#.#.#..", "########",
    ),
    "school": (
        ".#......", ".####...", ".#......", "...##...",
        "..####..", ".######.", ".##..##.", ".######.",
    ),
    "factory": (
        "......##", "......##", ".#.#..##", ".###.###",
        "########", "##.##.##", "##.##.##", "########",
    ),
    "construction": (
        ".#.#....", ".#######", ".#....#.", ".#....#.",
        ".#....##", ".#.....#", ".#......", "####....",
    ),
    "camp": (
        "...##...", "..####..", "..####..", ".##..##.",
        ".##..##.", "##....##", "##....##", "########",
    ),
    "wave": (
        ".#.#.#..", ".######.", ".######.", ".######.",
        ".#####..", "..####..", "...##...", "........",
    ),
    "pray": (
        ".#....#.", ".##..##.", ".##..##.", "..#..#..",
        "..####..", "...##...", "...##...", "........",
    ),
    "person": (
        "...##...", "..####..", "..####..", "...##...",
        ".######.", "########", "##....##", "........",
    ),
    "group": (
        ".##..##.", ".##..##.", "..####..", ".######.",
        "########", "##.##.##", "##.##.##", "........",
    ),
    "pin": (
        "..####..", ".######.", "##....##", "##.##.##",
        "##....##", ".######.", "...##...", "...##...",
    ),
    "compass": (
        "...##...", "..####..", ".##.###.", "##..#.##",
        "##.#..##", ".###.##.", "..####..", "...##...",
    ),
    "truck": (
        "........", ".#####..", ".#####..", ".#######",
        ".####..#", "########", "..##..##", "........",
    ),
    "unlock": (
        "....###.", "...#....", "...#....", ".######.",
        ".#....#.", ".#..#.#.", ".######.", "........",
    ),
    "hammer": (
        ".#####..", ".#####..", "...##...", "...##...",
        "....##..", "....##..", ".....##.", "........",
    ),
    "screwdriver": (
        ".###....", ".###....", "..#.....", "..##....",
        "...##...", "....##..", ".....##.", "........",
    ),
    "nut": (
        "..####..", ".##..##.", "##....##", "##.##.##",
        "##.##.##", "##....##", ".##..##.", "..####..",
    ),
    "clip": (
        "...###..", "..#...#.", "..#...#.", "..#.#.#.",
        "..#.#.#.", "..#.#...", "...#....", "........",
    ),
    "box": (
        "...##...", ".######.", "##.##.##", "##.##.##",
        "##.##.##", ".######.", "...##...", "........",
    ),
    "calendar": (
        ".#....#.", ".######.", "########", "#......#",
        "#.##.#.#", "#.#.##.#", "#......#", ".######.",
    ),
    "alarm": (
        ".#....#.", "..####..", ".######.", ".#....#.",
        ".#....#.", ".######.", "########", "........",
    ),
    "temperature": (
        "...##...", "..#..#..", "..#..#..", "..#.##..",
        "..#.##..", ".##..##.", ".######.", "..####..",
    ),
}


def pattern8_image(rows: tuple[str, ...]) -> Image.Image:
    if len(rows) != 8 or any(len(row) != 8 for row in rows):
        raise ValueError("Every SMALL8 pattern must be exactly 8x8")
    image = Image.new("1", (8, 8), 0)
    for y, row in enumerate(rows):
        for x, value in enumerate(row):
            if value == "#":
                image.putpixel((x, y), 1)
    return image


def source_legacy_bytes() -> dict[str, list[int]]:
    source = (ROOT / "examples" / "companion_radio" / "ui-new" / "icons.h").read_text(encoding="utf-8")
    result = {}
    pattern = re.compile(r"static const uint8_t\s+(\w+)\s*\[\]\s*=\s*\{([^{}]+)\};", re.MULTILINE)
    for symbol, body in pattern.findall(source):
        values = [int(value, 16) for value in re.findall(r"0x([0-9a-fA-F]{2})", body)]
        if len(values) == 8:
            result[symbol] = values
    return result


def firmware_small8(kind: str, legacy: dict[str, list[int]]) -> list[int]:
    if kind in SMALL8_PATTERNS:
        pixels = pattern8_image(SMALL8_PATTERNS[kind])
        return [
            sum((0x80 >> x) for x in range(8) if pixels.getpixel((x, y)))
            for y in range(8)
        ]
    symbols = dict(FIRMWARE_ICON_MAP)[kind]
    for symbol in symbols:
        if symbol in legacy:
            return legacy[symbol]
    return firmware_xbm8(kind)


def firmware_rows(kind: str) -> list[int]:
    pixels = make_icon(kind)
    return [
        sum((1 << (GRID - 1 - x)) for x in range(GRID) if pixels.getpixel((x, y)))
        for y in range(GRID)
    ]


def firmware_xbm8(kind: str) -> list[int]:
    pixels = make_icon(kind).resize((8, 8), Image.Resampling.NEAREST)
    return [
        sum((0x80 >> x) for x in range(8) if pixels.getpixel((x, y)))
        for y in range(8)
    ]


def export_firmware_header():
    path = ROOT / "examples" / "companion_radio" / "ui-new" / "iconpack_v1.h"
    lines = [
        "#pragma once",
        "",
        "// Generated by tools/simulate_iconpack_v1.py.",
        "// Monochrome 12x12 masters for T096/T114 plus unique 8x8 fallbacks.",
        "",
    ]
    for symbol, kind in NEW_LEGACY_ICONS:
        values = ", ".join(f"0x{value:02x}" for value in firmware_xbm8(kind))
        lines += [
            f"static const uint8_t {symbol}[] = {{",
            f"  {values}",
            "};",
            "",
        ]
    legacy = source_legacy_bytes()
    for kind, _ in FIRMWARE_ICON_MAP:
        values = ", ".join(f"0x{value:02x}" for value in firmware_small8(kind, legacy))
        lines += [
            f"static const uint8_t iconpack_v2_small_{kind}[8] PROGMEM = {{",
            f"  {values}",
            "};",
            "",
        ]
    for kind, _ in FIRMWARE_ICON_MAP:
        values = ", ".join(f"0x{value:03x}" for value in firmware_rows(kind))
        lines += [
            f"static const uint16_t iconpack_v1_{kind}[12] PROGMEM = {{",
            f"  {values}",
            "};",
            "",
        ]
    lines += [
        "struct MeshcoreIconpackV2Glyph {",
        "  const uint8_t* small;",
        "  const uint16_t* large;",
        "};",
        "",
        "static const MeshcoreIconpackV2Glyph iconpack_v2_glyphs[] = {",
    ]
    for kind, _ in FIRMWARE_ICON_MAP:
        lines.append(f"  {{iconpack_v2_small_{kind}, iconpack_v1_{kind}}},")
    lines += [
        "};",
        "",
        "static inline const MeshcoreIconpackV2Glyph* meshcoreIconpackV2Glyph(const uint8_t* icon) {",
        "  if (icon == NULL) return NULL;",
    ]
    for index, (kind, symbols) in enumerate(FIRMWARE_ICON_MAP):
        condition = " || ".join(f"icon == {symbol}" for symbol in symbols)
        lines.append(f"  if ({condition}) return &iconpack_v2_glyphs[{index}];")
    lines += [
        "  return NULL;",
        "}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def colored_icon(kind: str, size: int, color=WHITE) -> Image.Image:
    mask = make_icon(kind).resize((size, size), Image.Resampling.NEAREST)
    out = Image.new("RGB", (size, size), (0, 0, 0))
    out.paste(color, mask=mask)
    return out


def draw_catalog():
    columns = 8
    tile_w, tile_h = 148, 140
    title_h = 62
    category_h = 36
    rows = sum((len(items) + columns - 1) // columns for _, items in CATEGORIES)
    height = title_h + len(CATEGORIES) * category_h + rows * tile_h + 30
    image = Image.new("RGB", (columns * tile_w + 30, height), BG)
    d = ImageDraw.Draw(image)
    d.text((18, 12), "SMART ICONPACK V1 — сетка 12×12", font=font(28, True), fill=WHITE)
    d.text((18, 43), "Увеличение ×6; внизу каждой карточки — фактические 8 / 12 / 16 / 24 px",
           font=font(14), fill=MUTED)
    y = title_h
    colors = [GREEN, CYAN, YELLOW, WHITE]
    for cat_index, (category, items) in enumerate(CATEGORIES):
        d.rectangle((0, y, image.width, y + category_h - 1), fill=PANEL)
        d.text((18, y + 6), category, font=font(20, True), fill=colors[cat_index % len(colors)])
        y += category_h
        for index, (kind, label, alias) in enumerate(items):
            col = index % columns
            if col == 0 and index:
                y += tile_h
            x = 15 + col * tile_w
            d.rounded_rectangle((x, y + 5, x + tile_w - 10, y + tile_h - 7), radius=8,
                                fill=(7, 17, 21), outline=GRID_COLOR)
            icon = colored_icon(kind, 72, colors[cat_index % len(colors)])
            image.paste(icon, (x + 33, y + 10), icon.convert("L"))
            d.text((x + 8, y + 84), label, font=font(14, True), fill=WHITE)
            d.text((x + 8, y + 104), alias, font=font(12), fill=MUTED)
            actual_x = x + 64
            for size in (8, 12, 16, 24):
                tiny = colored_icon(kind, size, colors[cat_index % len(colors)])
                image.paste(tiny, (actual_x, y + 102 + (24 - size)), tiny.convert("L"))
                actual_x += size + 5
        y += tile_h
    image.save(OUT / "ICONPACK_V1_CATALOG.png")


def draw_grid_audit():
    selected = [
        ("pager", "пейджер"), ("home", "дом"), ("office", "офис"), ("shop", "магазин"),
        ("hospital", "медицина"), ("bank", "банк"), ("school", "школа"), ("factory", "завод"),
        ("pin", "геометка"), ("compass", "компас"), ("satellite", "спутник"),
        ("car", "машина"), ("truck", "грузовик"), ("lock", "закрыто"), ("unlock", "открыто"),
        ("wrench", "ключ"), ("hammer", "молоток"), ("screwdriver", "отвёртка"), ("nut", "гайка"),
        ("football", "футбол"),
    ]
    cols, cell_w, cell_h = 5, 240, 210
    image = Image.new("RGB", (cols * cell_w + 20, 4 * cell_h + 64), BG)
    d = ImageDraw.Draw(image)
    d.text((16, 12), "Проверка пиксельной сетки и различимости", font=font(27, True), fill=WHITE)
    for i, (kind, label) in enumerate(selected):
        x = 10 + (i % cols) * cell_w
        y = 58 + (i // cols) * cell_h
        d.rounded_rectangle((x + 5, y + 5, x + cell_w - 5, y + cell_h - 5), 9,
                            fill=PANEL, outline=GRID_COLOR)
        ox, oy, scale = x + 22, y + 22, 11
        pixels = make_icon(kind)
        for py in range(GRID):
            for px in range(GRID):
                box = (ox + px * scale, oy + py * scale,
                       ox + (px + 1) * scale - 1, oy + (py + 1) * scale - 1)
                d.rectangle(box, fill=GREEN if pixels.getpixel((px, py)) else BG, outline=GRID_COLOR)
        d.text((x + 164, y + 30), label, font=font(16, True), fill=WHITE)
        d.text((x + 164, y + 58), "12 px", font=font(12), fill=MUTED)
        for row, size in enumerate((8, 12, 16, 24)):
            tiny = colored_icon(kind, size, YELLOW if size == 8 else WHITE)
            image.paste(tiny, (x + 165, y + 82 + row * 27), tiny.convert("L"))
            d.text((x + 196, y + 82 + row * 27), f"{size}×{size}", font=font(12), fill=MUTED)
    image.save(OUT / "ICONPACK_V1_GRID_AUDIT.png")


def draw_semantic_split():
    groups = [
        ("Здания", "home", [
            ("home", "дом"), ("office", "офис"), ("shop", "магазин"), ("hospital", "медицина"),
            ("bank", "банк"), ("school", "школа"), ("factory", "завод"), ("camp", "лагерь"),
        ]),
        ("Положение", "satellite", [
            ("pin", "геометка"), ("compass", "навигация"), ("satellite", "спутник"), ("map", "карта"),
        ]),
        ("Транспорт", "car", [("car", "машина"), ("truck", "грузовик"), ("bike", "велосипед"), ("walk", "пешком")]),
        ("Доступ", "lock", [("lock", "закрыто"), ("unlock", "открыто"), ("key", "ключ")]),
        ("Инструменты", "wrench", [
            ("wrench", "ключ"), ("hammer", "молоток"), ("screwdriver", "отвёртка"),
            ("nut", "гайка"), ("pick", "кирка"),
        ]),
    ]
    width = 1420
    row_h = 180
    image = Image.new("RGB", (width, 78 + len(groups) * row_h), BG)
    d = ImageDraw.Draw(image)
    d.text((18, 12), "Главное исправление: один смысл — один силуэт", font=font(29, True), fill=WHITE)
    d.text((18, 48), "Слева показана текущая смысловая коллизия, справа — разделение в EXP1",
           font=font(15), fill=MUTED)
    for row, (title, old_kind, new_items) in enumerate(groups):
        y = 78 + row * row_h
        d.rectangle((0, y, width, y + row_h - 3), fill=PANEL if row % 2 == 0 else BG)
        d.text((18, y + 15), title, font=font(19, True), fill=YELLOW)
        d.text((170, y + 18), "СЕЙЧАС", font=font(14, True), fill=RED)
        old = colored_icon(old_kind, 72, RED)
        image.paste(old, (184, y + 48), old.convert("L"))
        d.text((274, y + 61), "один рисунок для", font=font(14), fill=MUTED)
        d.text((274, y + 84), f"{len(new_items)} разных понятий", font=font(14, True), fill=WHITE)
        d.line((475, y + 20, 475, y + row_h - 20), fill=GRID_COLOR, width=2)
        d.text((505, y + 18), "EXP1", font=font(14, True), fill=GREEN)
        x = 505
        for kind, label in new_items:
            tile = colored_icon(kind, 60, GREEN)
            image.paste(tile, (x, y + 48), tile.convert("L"))
            d.text((x - 4, y + 116), label, font=font(12, True), fill=WHITE)
            x += 105
    image.save(OUT / "ICONPACK_V1_SEMANTIC_SPLIT.png")


def scale_source_overlap(mask: Image.Image, size: int) -> Image.Image:
    """Reproduce the faulty B16 source-driven ceil/floor renderer."""
    out = Image.new("1", (size, size), 0)
    d = ImageDraw.Draw(out)
    for sy in range(GRID):
        y1 = (sy * size) // GRID
        y2 = ((sy + 1) * size + GRID - 1) // GRID
        for sx in range(GRID):
            if not mask.getpixel((sx, sy)):
                continue
            x1 = (sx * size) // GRID
            x2 = ((sx + 1) * size + GRID - 1) // GRID
            d.rectangle((x1, y1, x2 - 1, y2 - 1), fill=1)
    return out


def scale_destination_nearest(mask: Image.Image, size: int) -> Image.Image:
    """Reproduce the corrected destination-driven firmware renderer."""
    return scale_any_destination(mask, size)


def scale_any_destination(mask: Image.Image, size: int) -> Image.Image:
    out = Image.new("1", (size, size), 0)
    for dy in range(size):
        sy = min(mask.height - 1, ((dy * 2 + 1) * mask.height) // (size * 2))
        for dx in range(size):
            sx = min(mask.width - 1, ((dx * 2 + 1) * mask.width) // (size * 2))
            out.putpixel((dx, dy), mask.getpixel((sx, sy)))
    return out


def logical_to_t114(mask: Image.Image) -> Image.Image:
    width = int(mask.width * 1.875)
    height = int(mask.height * 2.109375)
    out = Image.new("1", (width, height), 0)
    d = ImageDraw.Draw(out)
    for y in range(mask.height):
        y1 = int(y * 2.109375)
        y2 = int((y + 1) * 2.109375)
        for x in range(mask.width):
            if not mask.getpixel((x, y)):
                continue
            x1 = int(x * 1.875)
            x2 = int((x + 1) * 1.875)
            d.rectangle((x1, y1, max(x1, x2 - 1), max(y1, y2 - 1)), fill=1)
    return out


def gps_badge_mask(size: int) -> Image.Image:
    scale = 2 if size >= 14 else 1
    width = 25 * scale
    image = Image.new("1", (width, size), 0)
    glyphs = (
        (0x7, 0x4, 0x5, 0x5, 0x7),
        (0x6, 0x5, 0x6, 0x4, 0x4),
        (0x7, 0x4, 0x7, 0x1, 0x7),
    )
    yy = max(0, (size - 5 * scale) // 2)
    d = ImageDraw.Draw(image)

    def block(px: int, py: int):
        d.rectangle((px, py, px + scale - 1, py + scale - 1), fill=1)

    waves_left = (0x24, 0x12, 0x12, 0x12, 0x24)
    waves_right = (0x09, 0x12, 0x12, 0x12, 0x09)
    for row, bits in enumerate(waves_left):
        for col in range(6):
            if bits & (1 << (5 - col)):
                block(col * scale, yy + row * scale)
    text_x = 7 * scale
    for glyph_index, rows in enumerate(glyphs):
        gx = text_x + glyph_index * 4 * scale
        for row, bits in enumerate(rows):
            for col in range(3):
                if bits & (1 << (2 - col)):
                    block(gx + col * scale, yy + row * scale)
    right_x = 19 * scale
    for row, bits in enumerate(waves_right):
        for col in range(6):
            if bits & (1 << (5 - col)):
                block(right_x + col * scale, yy + row * scale)
    return image


def paint_mask(mask: Image.Image, color, zoom: int) -> Image.Image:
    scaled = mask.resize((mask.width * zoom, mask.height * zoom), Image.Resampling.NEAREST)
    out = Image.new("RGB", scaled.size, BG)
    out.paste(color, mask=scaled)
    return out


def draw_hardware_scale_audit():
    selected = [
        ("mute", "без звука"), ("satellite", "спутник"), ("pager", "пейджер"),
        ("home", "дом"), ("office", "офис"), ("shop", "магазин"),
        ("hospital", "медицина"), ("pin", "геометка"), ("compass", "компас"),
        ("car", "машина"), ("truck", "грузовик"), ("lock", "закрыто"),
        ("unlock", "открыто"), ("smile", "улыбка"), ("think", "думаю"),
        ("thumb_up", "палец +"), ("wave", "привет"), ("message", "сообщение"),
    ]
    columns = [
        ("МАСТЕР 12×12", "master"),
        ("B16 / T114", "old114"),
        ("FIX / T114", "new114"),
        ("B16 / T096", "old096"),
        ("FIX / T096", "new096"),
    ]
    label_w, col_w, row_h = 180, 190, 116
    image = Image.new("RGB", (label_w + col_w * len(columns) + 20, 72 + row_h * len(selected)), BG)
    d = ImageDraw.Draw(image)
    d.text((16, 10), "АППАРАТНЫЙ АУДИТ МАСШТАБИРОВАНИЯ", font=font(27, True), fill=WHITE)
    d.text((16, 42), "T114: 9 логических px → 16×18 физических; T096: 16×16 px",
           font=font(14), fill=MUTED)
    for col, (title, _) in enumerate(columns):
        d.text((label_w + col * col_w + 8, 48), title, font=font(12, True), fill=YELLOW)
    for row, (kind, label) in enumerate(selected):
        y = 72 + row * row_h
        if row % 2 == 0:
            d.rectangle((0, y, image.width, y + row_h - 1), fill=PANEL)
        d.text((16, y + 18), label, font=font(16, True), fill=WHITE)
        d.text((16, y + 44), kind, font=font(12), fill=MUTED)
        master = make_icon(kind)
        variants = [
            master,
            logical_to_t114(scale_source_overlap(master, 9)),
            logical_to_t114(scale_destination_nearest(master, 9)),
            scale_source_overlap(master, 16),
            scale_destination_nearest(master, 16),
        ]
        colors = [CYAN, RED, GREEN, RED, GREEN]
        for col, (variant, color) in enumerate(zip(variants, colors)):
            zoom = min(6, 78 // max(variant.width, variant.height))
            rendered = paint_mask(variant, color, zoom)
            x = label_w + col * col_w + (col_w - rendered.width) // 2
            image.paste(rendered, (x, y + 12), rendered.convert("L"))
    image.save(OUT / "ICONPACK_V2_HARDWARE_SCALE_AUDIT.png")


def draw_hardware_catalog():
    items = [item for _, category_items in CATEGORIES for item in category_items]
    columns, tile_w, tile_h = 6, 210, 124
    rows = (len(items) + columns - 1) // columns
    image = Image.new("RGB", (columns * tile_w + 20, 72 + rows * tile_h), BG)
    d = ImageDraw.Draw(image)
    d.text((16, 10), "ПОЛНЫЙ КАТАЛОГ В ФАКТИЧЕСКОМ МАСШТАБЕ", font=font(27, True), fill=WHITE)
    d.text((16, 42), "Слева T114: 9 логических px → физические; справа T096: 16×16 px",
           font=font(14), fill=MUTED)
    for index, (kind, label, alias) in enumerate(items):
        col, row = index % columns, index // columns
        x, y = 10 + col * tile_w, 68 + row * tile_h
        d.rounded_rectangle((x + 3, y + 3, x + tile_w - 5, y + tile_h - 5), 7,
                            fill=PANEL if row % 2 == 0 else (5, 14, 18), outline=GRID_COLOR)
        master = make_icon(kind)
        t114 = logical_to_t114(scale_destination_nearest(master, 9))
        t096 = scale_destination_nearest(master, 16)
        left = paint_mask(t114, CYAN, 3)
        right = paint_mask(t096, GREEN, 3)
        image.paste(left, (x + 14, y + 12), left.convert("L"))
        image.paste(right, (x + 91, y + 10), right.convert("L"))
        d.text((x + 8, y + 73), label, font=font(13, True), fill=WHITE)
        d.text((x + 8, y + 94), alias, font=font(11), fill=MUTED)
        d.text((x + 155, y + 94), "114 / 096", font=font(9), fill=MUTED)
    image.save(OUT / "ICONPACK_V2_HARDWARE_CATALOG.png")


def legacy_icon_masks() -> dict[str, Image.Image]:
    source = (
        (ROOT / "examples" / "companion_radio" / "ui-new" / "icons.h").read_text(encoding="utf-8")
        + "\n"
        + (ROOT / "examples" / "companion_radio" / "ui-new" / "iconpack_v1.h").read_text(encoding="utf-8")
    )
    arrays = {}
    pattern = re.compile(
        r"static const uint8_t\s+(\w+)\s*\[\]\s*=\s*\{([^{}]+)\};",
        re.MULTILINE,
    )
    for symbol, body in pattern.findall(source):
        values = [int(value, 16) for value in re.findall(r"0x([0-9a-fA-F]{2})", body)]
        if len(values) != 8:
            continue
        mask = Image.new("1", (8, 8), 0)
        for y, value in enumerate(values):
            for x in range(8):
                if value & (0x80 >> x):
                    mask.putpixel((x, y), 1)
        arrays[symbol] = mask
    return arrays


def draw_hybrid_hardware_catalog():
    legacy = source_legacy_bytes()
    items = [item for _, category_items in CATEGORIES for item in category_items]
    columns, tile_w, tile_h = 6, 210, 124
    rows = (len(items) + columns - 1) // columns
    image = Image.new("RGB", (columns * tile_w + 20, 72 + rows * tile_h), BG)
    d = ImageDraw.Draw(image)
    d.text((16, 10), "ГИБРИД V2: ОТДЕЛЬНЫЙ 8×8 ДЛЯ T114", font=font(27, True), fill=WHITE)
    d.text((16, 42), "Слева T114 использует 8×8 без уменьшения; справа T096 сохраняет мастер 12×12",
           font=font(14), fill=MUTED)
    for index, (kind, label, alias) in enumerate(items):
        col, row = index % columns, index // columns
        x, y = 10 + col * tile_w, 68 + row * tile_h
        d.rounded_rectangle((x + 3, y + 3, x + tile_w - 5, y + tile_h - 5), 7,
                            fill=PANEL if row % 2 == 0 else (5, 14, 18), outline=GRID_COLOR)
        master = make_icon(kind)
        if kind == "satellite":
            t114 = logical_to_t114(gps_badge_mask(9))
            t096 = gps_badge_mask(16)
        else:
            small = Image.new("1", (8, 8), 0)
            for py, value in enumerate(firmware_small8(kind, legacy)):
                for px in range(8):
                    if value & (0x80 >> px):
                        small.putpixel((px, py), 1)
            t114 = logical_to_t114(scale_any_destination(small, 9))
            t096 = scale_destination_nearest(master, 16)
        left = paint_mask(t114, CYAN, 3)
        right = paint_mask(t096, GREEN, 3)
        image.paste(left, (x + 14, y + 12), left.convert("L"))
        image.paste(right, (x + 91, y + 10), right.convert("L"))
        d.text((x + 8, y + 73), label, font=font(13, True), fill=WHITE)
        d.text((x + 8, y + 94), alias, font=font(11), fill=MUTED)
        d.text((x + 155, y + 94), "114 / 096", font=font(9), fill=MUTED)
    image.save(OUT / "ICONPACK_V2_HYBRID_HARDWARE_CATALOG.png")


def draw_gps_badge_audit():
    t114 = logical_to_t114(gps_badge_mask(9))
    t096 = gps_badge_mask(16)
    image = Image.new("RGB", (900, 360), BG)
    d = ImageDraw.Draw(image)
    d.text((18, 12), "GPS-БЕЙДЖ С РАДИОВОЛНАМИ", font=font(28, True), fill=WHITE)
    d.text((18, 48), "Буквы являются смыслом; волны остаются вторичным декоративным признаком",
           font=font(14), fill=MUTED)
    left = paint_mask(t114, CYAN, 8)
    right = paint_mask(t096, GREEN, 8)
    image.paste(left, (40, 100), left.convert("L"))
    image.paste(right, (500, 100), right.convert("L"))
    d.text((40, 300), "T114 — фактическая геометрия", font=font(16, True), fill=CYAN)
    d.text((500, 300), "T096 — 16 px", font=font(16, True), fill=GREEN)
    image.save(OUT / "ICONPACK_V3_GPS_BADGE_AUDIT.png")


def draw_dish_candidates():
    candidates = {
        "A": SMALL8_PATTERNS["satellite"],
        "B": (
            ".#......", ".##...#.", ".###.#..", ".####...",
            "..###...", "...##...", "...##...", "..####..",
        ),
        "C": (
            "......#.", "....#.#.", "..####..", ".######.",
            "##....##", ".######.", "...##...", "..####..",
        ),
        "D": (
            ".......#", ".....#..", ".######.", "..#####.",
            "...###..", "...##...", "...##...", "..####..",
        ),
        "E": (
            "....#.#.", "..#...#.", ".######.", "..#####.",
            "...###..", "...##...", "..####..", ".######.",
        ),
    }
    image = Image.new("RGB", (820, 330), BG)
    d = ImageDraw.Draw(image)
    d.text((18, 12), "СПУТНИКОВАЯ ТАРЕЛКА — КАНДИДАТЫ T114", font=font(26, True), fill=WHITE)
    d.text((18, 46), "Каждый вариант показан в фактической физической геометрии и увеличен ×7",
           font=font(14), fill=MUTED)
    for index, (name, rows) in enumerate(candidates.items()):
        logical = scale_any_destination(pattern8_image(rows), 9)
        physical = logical_to_t114(logical)
        rendered = paint_mask(physical, CYAN, 7)
        x = 18 + index * 158
        image.paste(rendered, (x, 86), rendered.convert("L"))
        d.text((x + 48, 250), name, font=font(24, True), fill=YELLOW)
    image.save(OUT / "ICONPACK_V3_DISH_CANDIDATES.png")


def draw_screen(title: str, physical: tuple[int, int], icon_size: int, scale: int, path: str):
    w, h = physical
    screen = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(screen)
    d.rectangle((0, 0, w - 1, h - 1), outline=GRID_COLOR)
    d.rectangle((0, 0, w, max(15, icon_size + 3)), fill=PANEL)
    d.text((5, 2), title, font=font(max(9, icon_size - 5), True), fill=GREEN)
    status = [("signal", GREEN), ("satellite", CYAN), ("battery", YELLOW)]
    sx = w - 5
    for kind, color in reversed(status):
        sx -= icon_size
        tiny = colored_icon(kind, icon_size, color)
        screen.paste(tiny, (sx, 2), tiny.convert("L"))
        sx -= 3

    messages = [
        (GREEN, "home", "Анна: уже дома"),
        (CYAN, "pager", "Сетка: принято"),
        (YELLOW, "pin", "Миша: у школы"),
    ]
    y = max(19, icon_size + 6)
    row_h = max(icon_size + 5, (h - y) // 3)
    text_font = font(max(8, min(12, row_h - 7)), True)
    for color, kind, text in messages:
        tiny = colored_icon(kind, icon_size, color)
        icon_y = y + max(0, (row_h - icon_size) // 2)
        screen.paste(tiny, (4, icon_y), tiny.convert("L"))
        tx = 8 + icon_size
        d.text((tx, y + max(0, (row_h - text_font.size) // 2 - 2)),
               text, font=text_font, fill=WHITE)
        y += row_h

    enlarged = screen.resize((w * scale, h * scale), Image.Resampling.NEAREST)
    canvas = Image.new("RGB", (w * scale + 32, h * scale + 72), (18, 25, 28))
    cd = ImageDraw.Draw(canvas)
    cd.text((16, 12), f"{title}: реальные {w}×{h}, пиктограмма {icon_size}px",
            font=font(20, True), fill=WHITE)
    canvas.paste(enlarged, (16, 50))
    canvas.save(OUT / path)


def main():
    export_firmware_header()
    draw_catalog()
    draw_grid_audit()
    draw_semantic_split()
    draw_hardware_scale_audit()
    draw_hardware_catalog()
    draw_hybrid_hardware_catalog()
    draw_gps_badge_audit()
    draw_dish_candidates()
    draw_screen("T096 / Чат", (160, 80), 16, 4, "ICONPACK_V1_T096_CHAT.png")
    draw_screen("T114 / Чат", (240, 135), 22, 3, "ICONPACK_V1_T114_CHAT.png")
    print(f"Written to {OUT}")


if __name__ == "__main__":
    main()
