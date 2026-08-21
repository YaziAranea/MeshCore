from pathlib import Path
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont
from generate_t096_design_bitmap_fonts import render_glyph


W, H = 160, 80
SCALE = 4

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "qa_outputs" / "t096_premium"
NETWORK_MATRIX = OUT_DIR / "T096_NETWORK_ALL_FONTS_SMARTUI_PS17.png"
COMPACT_MATRIX = OUT_DIR / "T096_SMARTUI_PS17_MATRIX.png"
FONT_SRC = ROOT / "tools" / "font_sources"
FALLBACK_FONT = FONT_SRC / "noto_sans_2_015" / "NotoSans-CondensedMedium.ttf"

THEMES = [
    ("Графит", "#F4FAF8", "#000000", "#FF4D4D", "#1DF07A", "#36C8FF", "#FFE04A", "#FF9B2F"),
    ("Полночь", "#EAF7FF", "#010816", "#FF5A6A", "#24E083", "#38BDF8", "#FACC15", "#FB923C"),
    ("Хвоя", "#EEFFE8", "#031006", "#FF6B5F", "#23D17C", "#2DD4BF", "#FDE047", "#F97316"),
    ("Бумага", "#101820", "#FFF8E7", "#DC2626", "#0F7A4D", "#0369A1", "#B45309", "#C2410C"),
    ("Бордо", "#FFE8F0", "#100007", "#FF4D7A", "#2BEA84", "#60A5FA", "#FDE047", "#FB7185"),
    ("Север", "#E8F4FF", "#000C10", "#F87171", "#34D399", "#22D3EE", "#FDE047", "#FB923C"),
    ("Высокий", "#E8F4FF", "#000000", "#FF4D4D", "#1DF07A", "#36C8FF", "#FFE04A", "#FF9B2F"),
]

FAMILIES = [
    ("Roboto", FONT_SRC / "ui_readable_10" / "RobotoCondensed-wght.ttf", [430]),
    ("Noto", FONT_SRC / "noto_sans_2_015" / "NotoSans-CondensedMedium.ttf", None),
    ("OpenSans", FONT_SRC / "ui_readable_10" / "OpenSans-wdth-wght.ttf", [540, 92]),
    ("PT Narrow", FONT_SRC / "ui_readable_10" / "PTSansNarrow-Bold.ttf", None),
    ("Oswald", FONT_SRC / "ui_readable_10" / "Oswald-wght.ttf", [440]),
]

ROLE_SIZES = {"S": 12, "M": 14, "L": 18, "XL": 22}
FIRMWARE_SIZES = {
    "L": (12, 16, 13, 3),
    "XL": (14, 18, 15, 3),
    "XXL": (16, 21, 17, 4),
    "Hero": (18, 24, 20, 4),
}
VISIBLE_FONT_FIRST = 5
VISIBLE_FONT_COUNT = 15
DEFAULT_PROFILE = 10


def rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def theme(idx):
    name, fg, bg, red, green, blue, yellow, orange = THEMES[idx % len(THEMES)]
    return {
        "name": name,
        "fg": rgb(fg),
        "bg": rgb(bg),
        "red": rgb(red),
        "green": rgb(green),
        "blue": rgb(blue),
        "yellow": rgb(yellow),
        "orange": rgb(orange),
    }


def profile_name(profile):
    if profile < VISIBLE_FONT_FIRST:
        profile += VISIBLE_FONT_FIRST
    family = profile % 5
    group = profile // 5
    suffix = ("L", "XL", "XXL", "Hero")[group]
    return f"{FAMILIES[family][0]} {suffix}"


def profile_role(profile, role):
    if profile < VISIBLE_FONT_FIRST:
        profile += VISIBLE_FONT_FIRST
    family = profile % 5
    group = profile // 5
    role_group = group
    if role == "S":
        role_group = group - 1 if group > 1 else 1
    elif role in ("L", "XL"):
        role_group = min(group + 1, 3)
    if role_group == 0:
        role_group = 1
    suffix = ("L", "XL", "XXL", "Hero")[role_group]
    return family, suffix


class FirmwareFont:
    def __init__(self, path, size, axes, height, ascent, descent, bold=False):
        self.font = ImageFont.truetype(str(path), size=size)
        if axes and hasattr(self.font, "set_variation_by_axes"):
            self.font.set_variation_by_axes(axes)
        self.height = height
        self.ascent = ascent
        self.descent = descent
        self.bold = bold
        self.glyphs = {}

    def glyph(self, char):
        cp = ord(char)
        if cp not in self.glyphs:
            self.glyphs[cp] = render_glyph(
                self.font, cp, self.ascent, self.descent, self.height, antialias_threshold=104
            )
        return self.glyphs[cp]

    def width(self, text):
        return sum(glyph["x_advance"] + (1 if self.bold else 0) for glyph in map(self.glyph, text))

    def draw(self, draw, x, y, text, fill):
        cursor_x = x
        for char in text:
            glyph = self.glyph(char)
            for row in range(glyph["height"]):
                for col in range(glyph["width"]):
                    byte = glyph["data"][row * glyph["row_bytes"] + col // 8]
                    if byte & (1 << (col & 7)):
                        draw.point((cursor_x + glyph["x_offset"] + col, y + row), fill=fill)
                        if self.bold:
                            draw.point((cursor_x + glyph["x_offset"] + col + 1, y + row), fill=fill)
            cursor_x += glyph["x_advance"] + (1 if self.bold else 0)


@lru_cache(maxsize=None)
def load_font(profile, role="M", bold=False):
    family, suffix = profile_role(profile, role)
    name, path, axes = FAMILIES[family]
    size, height, ascent, descent = FIRMWARE_SIZES[suffix]
    if path.exists():
        return FirmwareFont(path, size, axes, height, ascent, descent, bold)
    return FirmwareFont(FALLBACK_FONT, size, None, height, ascent, descent, bold)


@lru_cache(maxsize=None)
def load_compact_settings_font(profile):
    normalized = profile if profile >= VISIBLE_FONT_FIRST else profile + VISIBLE_FONT_FIRST
    family = normalized % 5
    _, path, axes = FAMILIES[family]
    size, height, ascent, descent = FIRMWARE_SIZES["L"]
    if not path.exists():
        path = FALLBACK_FONT
        axes = None
    return FirmwareFont(path, size, axes, height, ascent, descent)


def text_w(draw, text, fnt):
    if isinstance(fnt, FirmwareFont):
        return fnt.width(text)
    box = draw.textbbox((0, 0), text, font=fnt)
    return box[2] - box[0]


def draw_text(draw, x, y, text, fnt, fill):
    if isinstance(fnt, FirmwareFont):
        fnt.draw(draw, x, y, text, fill)
    else:
        draw.text((x, y), text, font=fnt, fill=fill)


def ellipsize(draw, text, fnt, max_w):
    if text_w(draw, text, fnt) <= max_w:
        return text
    suffix = "..."
    while text and text_w(draw, text + suffix, fnt) > max_w:
        text = text[:-1]
    return text + suffix


def center(draw, y, text, fnt, fill, max_w=W - 4):
    text = ellipsize(draw, text, fnt, max_w)
    draw_text(draw, (W - text_w(draw, text, fnt)) // 2, y, text, fnt, fill)


def left(draw, x, y, text, fnt, fill, max_w=None):
    draw_text(draw, x, y, ellipsize(draw, text, fnt, max_w or (W - x - 2)), fnt, fill)


def right(draw, x, y, text, fnt, fill):
    draw_text(draw, x - text_w(draw, text, fnt), y, text, fnt, fill)


def battery_icon(draw, x, y, pct, color):
    draw.rectangle((x, y, x + 17, y + 9), outline=color)
    draw.rectangle((x + 18, y + 3, x + 19, y + 6), fill=color)
    fill_w = max(0, min(14, round(14 * pct / 100)))
    if fill_w:
        draw.rectangle((x + 2, y + 2, x + 1 + fill_w, y + 7), fill=color)


def gps_icon(draw, x, y, color):
    draw.rectangle((x + 5, y + 4, x + 7, y + 6), fill=color)
    draw.rectangle((x + 1, y + 4, x + 3, y + 5), fill=color)
    draw.rectangle((x + 9, y + 4, x + 11, y + 5), fill=color)
    draw.line((x + 6, y + 3, x + 6, y + 1), fill=color)
    draw.point((x + 8, y + 1), fill=color)
    draw.point((x + 10, y), fill=color)
    draw.point((x + 10, y + 2), fill=color)
    draw.line((x + 5, y + 8, x + 5, y + 9), fill=color)
    draw.line((x + 7, y + 8, x + 7, y + 9), fill=color)


def new_screen(theme_id=0, border=True):
    t = theme(theme_id)
    img = Image.new("RGB", (W, H), t["bg"])
    draw = ImageDraw.Draw(img)
    if border:
        draw.rectangle((0, 0, W - 1, H - 1), outline=t["blue"])
    return img, draw, t


def chrome(draw, t, profile, page_idx, page_count=9):
    small = load_font(profile, "S")
    left(draw, 3, 2, "T096 Омск", small, t["green"], 78)
    battery_icon(draw, W - 20, 2, 92, t["green"])
    right(draw, W - 24, 0, "4.09V", small, t["green"])
    step = min(10, (W - 8) // max(1, page_count - 1))
    x = (W - step * (page_count - 1)) // 2
    for i in range(page_count):
        if i == page_idx:
            draw.rectangle((x - 1, 14, x + 1, 16), fill=t["fg"])
        else:
            draw.point((x, 15), fill=t["fg"])
        x += step


def draw_splash():
    profile = DEFAULT_PROFILE
    img, draw, t = new_screen(0, False)
    center(draw, 18, "Мешкор Омск", load_font(profile, "L"), t["green"])
    center(draw, 48, "T096 SmartUI PS17 FEM", load_font(profile, "S"), t["green"])
    return "01_splash", img


def draw_clock():
    profile = DEFAULT_PROFILE
    img, draw, t = new_screen(0, False)
    small = load_font(profile, "S")
    gps_icon(draw, 1, 3, t["green"])
    left(draw, 12, 0, "8", small, t["green"], 18)
    battery_icon(draw, W - 20, 2, 92, t["green"])
    right(draw, W - 24, 0, "4.09V", small, t["green"])
    center(draw, 17, "12:48", load_font(profile, "L"), t["green"])
    center(draw, 43, "21.08.2026", small, t["fg"])
    draw.rectangle((0, 60, 116, 78), outline=t["green"])
    draw.rectangle((0, 60, 2, 78), fill=t["green"])
    left(draw, 5, 62, "CH1.2% AIR0.03%", small, t["fg"], 110)
    draw.rectangle((120, 60, 159, 78), outline=t["green"])
    draw.rectangle((120, 60, 122, 78), fill=t["green"])
    temp = "37C"
    temp_x = 120 + (40 - text_w(draw, temp, small)) // 2
    draw_text(draw, temp_x, 62, temp, small, t["fg"])
    return "02_clock", img


def draw_ble_pin():
    profile = 10
    img, draw, t = new_screen(1, False)
    chrome(draw, t, profile, 1)
    center(draw, 21, "ПИНКОД BLE", load_font(profile, "S"), t["yellow"])
    center(draw, 35, "123456", load_font(profile, "XL"), t["green"])
    center(draw, 61, "ввести в приложении", load_font(profile, "S"), t["fg"])
    return "03_ble_pin", img


def menu_screen(name, lines, theme_id, profile, page_idx, accent_key="green", footer="OK / далее"):
    img, draw, t = new_screen(theme_id, False)
    chrome(draw, t, profile, page_idx)
    center(draw, 20, name, load_font(profile, "M"), t[accent_key])
    rows = list(lines[:3])
    if footer and len(rows) < 3:
        rows.append(footer)
    y = 38
    for line in rows:
        left(draw, 6, y, line, load_font(profile, "S"), t["fg"], W - 12)
        y += 12
    return img


def draw_font(profile):
    img, draw, t = new_screen(0, False)
    chrome(draw, t, profile, 2)
    center(draw, 20, "Шрифт", load_font(profile, "M"), t["green"])
    center(draw, 35, profile_name(profile), load_font(profile, "L"), t["yellow"])
    center(draw, 56, "15 шрифтов", load_font(profile, "S"), t["fg"])
    return f"04_font_{profile_name(profile).replace(' ', '_')}", img


def draw_theme_sample(theme_id):
    profile = DEFAULT_PROFILE
    img, draw, t = new_screen(theme_id, False)
    chrome(draw, t, profile, 3)
    center(draw, 20, "Цвет / фон", load_font(profile, "M"), t["green"])
    center(draw, 36, t["name"], load_font(profile, "L"), t["yellow"])
    colors = [t["red"], t["green"], t["blue"], t["yellow"], t["orange"]]
    x = 44
    for color in colors:
        draw.rectangle((x, 58, x + 9, 67), fill=color)
        x += 14
    return f"theme_{theme_id + 1}_{t['name']}", img


def draw_radio():
    return "08_radio_fem", menu_screen(
        "Радио",
        ["869.618 MHz   BW 62.5", "TX: FEM profile", "FEM: RX gain ON"],
        2,
        3,
        4,
        "green",
        "FEM включен в сборке",
    )


def draw_settings():
    return "09_settings", menu_screen(
        "Настройки",
        ["радио / BLE / экран", "сигналы / CH2 / АЦП", "GPS / уведомления"],
        3,
        12,
        5,
        "blue",
        "вход: OK",
    )


def compact_settings_screen(title, rows, selected=0, theme_id=0, start=0):
    img, draw, t = new_screen(theme_id, False)
    chrome(draw, t, DEFAULT_PROFILE, 5)
    font = load_compact_settings_font(DEFAULT_PROFILE)
    left(draw, 1, 14, title, font, t["green"], 118)
    left(draw, 125, 14, "<>OK", font, t["green"], 33)
    y = 27
    visible = rows[start:start + 4]
    for offset, (label, value) in enumerate(visible):
        index = start + offset
        color = t["yellow"] if index == selected else t["fg"]
        prefix = ">" if index == selected else ""
        left(draw, 0, y, prefix, font, color, 7)
        left(draw, 8 if prefix else 2, y, label, font, color, 86)
        if value:
            left(draw, 94, y, value, font, t["yellow"] if index == selected else t["green"], 62)
        y += 13
    if len(rows) > 4:
        track_y, track_h = 27, 51
        draw.rectangle((158, track_y, 159, track_y + track_h - 1), fill=t["blue"])
        thumb_h = max(4, track_h * 4 // len(rows))
        max_start = len(rows) - 4
        thumb_y = track_y + (track_h - thumb_h) * min(start, max_start) // max_start
        draw.rectangle((158, thumb_y, 159, thumb_y + thumb_h - 1), fill=t["green"])
    return img


def draw_compact_hub():
    rows = [
        ("Избранное", "3"),
        ("Уведомления", "Звук"),
        ("Звук и вибро", "МАКС"),
        ("Экран", "Noto XXL"),
        ("Радио и GPS", "GPS ВКЛ"),
        ("Система", "SmartUI"),
        ("Закрыть", ""),
    ]
    return "16_b11_hub", compact_settings_screen("Настройки", rows, selected=1)


def draw_compact_favorites():
    rows = [
        ("Режим уведомлений", "Звук"),
        ("Мелодия системы", "Лебеди"),
        ("Bluetooth", "ВКЛ"),
        ("Назад", ""),
    ]
    return "17_b11_favorites", compact_settings_screen("Избранное", rows, selected=0)


def draw_compact_sound():
    rows = [
        ("Мелодия", "Лебеди"),
        ("Стиль", "8-bit"),
        ("Громкость", "МАКСИМУМ"),
        ("Резонанс", "3000 Гц"),
        ("Назад", ""),
    ]
    return "18_b12_sound", compact_settings_screen("Звук и вибро", rows, selected=0)


def draw_tone_picker():
    rows = [
        ("Пинг", ""),
        ("Дубль", ""),
        ("Рост", ""),
        ("Мягкая", ""),
        ("Ода короткая", ""),
        ("Аркада", ""),
        ("Лифт", ""),
        ("Nova", ""),
        ("Radar", ""),
        ("Лебеди", "ВЫБРАНА"),
        ("Назад", ""),
    ]
    return "19_b12_tone_list", compact_settings_screen("Мелодия", rows, selected=9, start=7)


def draw_compact_system():
    rows = [
        ("Bluetooth", "ВКЛ"),
        ("LED платы", "ВКЛ"),
        ("Избранное 1", "Уведомления"),
        ("Избранное 2", "Мелодия"),
        ("Избранное 3", "Состояние"),
        ("Отменить изменение", "ГОТОВО"),
        ("Состояние", ""),
        ("Тест оборудования", ""),
        ("Назад", ""),
    ]
    return "20_b12_system", compact_settings_screen("Система", rows, selected=6, start=5)


def draw_device_status():
    rows = [
        ("АКБ 4.096В", "BLE СВЯЗЬ"),
        ("RSSI -72", "SNR 8.2"),
        ("GPS ВКЛ", "FEM ВКЛ"),
        ("Работа 12ч", "34м"),
    ]
    return "21_b12_status", compact_settings_screen("Состояние", rows, selected=-1)


def draw_hardware_test():
    rows = [
        ("Шаг 5/7", "АКБ / АЦП"),
        ("OK", "следующий"),
        ("<>", "назад"),
    ]
    return "22_b12_selftest", compact_settings_screen("Тест оборудования", rows, selected=0)


def make_compact_settings_sheet(items):
    label_font = ImageFont.truetype(str(FALLBACK_FONT), 12)
    gap = 10
    label_h = 18
    cell_w = W * SCALE
    cell_h = H * SCALE + label_h
    sheet = Image.new("RGB", (len(items) * cell_w + (len(items) - 1) * gap, cell_h), (12, 15, 17))
    draw = ImageDraw.Draw(sheet)
    for index, (name, image) in enumerate(items):
        x = index * (cell_w + gap)
        draw.text((x + 4, 1), name, font=label_font, fill=(225, 230, 234))
        sheet.paste(image.resize((cell_w, H * SCALE), Image.Resampling.NEAREST), (x, label_h))
    COMPACT_MATRIX.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(COMPACT_MATRIX)


def draw_network(profile=DEFAULT_PROFILE):
    img, draw, t = new_screen(0, False)
    chrome(draw, t, profile, 6)
    row_font = load_font(profile, "S")
    rows = [
        ("РД", t["yellow"], "слон ретранслятор длинный", "S+13 R-40", t["green"]),
        ("НД", t["green"], "Wan1 T096 очень длинная нода", "S+8 R-72", t["green"]),
        ("Н", t["green"], "пейджер дом дальний", "S-9 R-122", t["red"]),
    ]
    row_h = max(16, row_font.height)
    y = 17
    for label, label_color, name, metric, metric_color in rows:
        right(draw, W, y, metric, row_font, metric_color)
        metric_w = text_w(draw, metric, row_font)
        label_w = text_w(draw, label, row_font)
        left(draw, 0, y, label, row_font, label_color, label_w)
        name_x = label_w + 2
        left(draw, name_x, y, name, row_font, label_color, W - metric_w - name_x - 2)
        y += row_h
    return "10_network_sdvig", img


def make_network_font_matrix():
    gap = 8
    label_h = 18
    cell_w = W * SCALE
    cell_h = H * SCALE + label_h
    cols = 3
    profiles = list(range(VISIBLE_FONT_FIRST, VISIBLE_FONT_FIRST + VISIBLE_FONT_COUNT))
    rows = (len(profiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell_w + (cols - 1) * gap, rows * cell_h + (rows - 1) * gap), (12, 15, 17))
    draw = ImageDraw.Draw(sheet)
    label_font = ImageFont.truetype(str(FALLBACK_FONT), 12)
    for idx, profile in enumerate(profiles):
        col = idx % cols
        row = idx // cols
        x = col * (cell_w + gap)
        y = row * (cell_h + gap)
        font = load_font(profile, "S")
        label = f"{profile_name(profile)}  row={max(16, font.height)}px"
        draw.text((x + 4, y), label, font=label_font, fill=(225, 230, 234))
        _, img = draw_network(profile)
        sheet.paste(img.resize((cell_w, H * SCALE), Image.Resampling.NEAREST), (x, y + label_h))
    NETWORK_MATRIX.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(NETWORK_MATRIX)


def draw_gps():
    img = menu_screen(
        "GPS",
        ["PULSE     фикс", "спут: 8", "55.0000 73.0000"],
        6,
        DEFAULT_PROFILE,
        7,
        "blue",
        "перекл: OK",
    )
    draw = ImageDraw.Draw(img)
    gps_icon(draw, 7, 50, theme(6)["green"])
    return "10_gps", img


def draw_adc():
    return "11_adc", menu_screen(
        "АЦП",
        ["Батарея: 4.09V", "Коэф: 4.900", "точная подстройка"],
        5,
        1,
        8,
        "yellow",
        "OK сохранить",
    )


def draw_tone_bridge():
    return "12_tone_bridge", menu_screen(
        "Схема зуммера",
        ["Режим: МОСТ", "D31 <-> D29", "Свет: D45"],
        0,
        DEFAULT_PROFILE,
        9,
        "green",
        "",
    )


def draw_tone_style():
    return "13_tone_style", menu_screen(
        "Стиль звука",
        ["Режим: 8-bit", "ретро-арпеджио", "OK / сменить"],
        0,
        DEFAULT_PROFILE,
        9,
        "green",
        "",
    )


def draw_tone_drive():
    return "14_tone_drive", menu_screen(
        "Громкость GPIO",
        ["Режим: МАКСИМУМ", "усиленный выход", "H0H1 + резонанс"],
        0,
        DEFAULT_PROFILE,
        9,
        "green",
        "",
    )


def draw_tone_resonance():
    return "15_tone_resonance", menu_screen(
        "Резонанс пьезо",
        ["Частота: 3000 Гц", "нажать и слушать", "1800...4200 Гц"],
        0,
        DEFAULT_PROFILE,
        9,
        "green",
        "",
    )


def save_scaled(img, path):
    img.save(path)
    img.resize((W * SCALE, H * SCALE), Image.Resampling.NEAREST).save(
        path.with_name(path.stem + "_x4.png")
    )


def make_sheet(items):
    gap = 12
    label_h = 16
    cell_w = W * SCALE
    cell_h = H * SCALE + label_h
    cols = 3
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell_w + (cols - 1) * gap, rows * cell_h + (rows - 1) * gap), (12, 15, 17))
    draw = ImageDraw.Draw(sheet)
    label_font = ImageFont.truetype(str(FALLBACK_FONT), 11)
    for idx, (name, img) in enumerate(items):
        col = idx % cols
        row = idx // cols
        x = col * (cell_w + gap)
        y = row * (cell_h + gap)
        draw.text((x + 4, y), name, font=label_font, fill=(225, 230, 234))
        sheet.paste(img.resize((cell_w, H * SCALE), Image.Resampling.NEAREST), (x, y + label_h))
    sheet.save(OUT_DIR / "t096_5_4_ux_sheet.png")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    screens = [
        draw_splash(),
        draw_clock(),
        draw_ble_pin(),
        draw_font(10),
        draw_font(15),
        draw_theme_sample(0),
        draw_theme_sample(3),
        draw_theme_sample(4),
        draw_radio(),
        draw_settings(),
        draw_network(),
        draw_gps(),
        draw_adc(),
        draw_tone_bridge(),
        draw_tone_style(),
        draw_tone_drive(),
        draw_tone_resonance(),
        draw_compact_hub(),
        draw_compact_favorites(),
        draw_compact_sound(),
        draw_tone_picker(),
        draw_compact_system(),
        draw_device_status(),
        draw_hardware_test(),
    ]
    for name, img in screens:
        save_scaled(img, OUT_DIR / f"{name}.png")
    make_sheet(screens)
    make_compact_settings_sheet(
        [
            draw_compact_hub(),
            draw_compact_favorites(),
            draw_compact_sound(),
            draw_tone_picker(),
            draw_compact_system(),
            draw_device_status(),
            draw_hardware_test(),
        ]
    )
    make_network_font_matrix()
    print(OUT_DIR)
    print(NETWORK_MATRIX)
    print(COMPACT_MATRIX)


if __name__ == "__main__":
    main()
