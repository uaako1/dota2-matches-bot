import hashlib
import io
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps

Image.MAX_IMAGE_PIXELS = 20_000_000

IMG_W_RESULT = 1700
IMG_H_RESULT = 1020
IMG_W_PREVIEW = 1280
IMG_H_PREVIEW = 1280

BG_TOP = ImageColor.getrgb("#08121a")
BG_MID = ImageColor.getrgb("#132634")
BG_BOTTOM = ImageColor.getrgb("#0b161f")
PANEL = ImageColor.getrgb("#142935")
PANEL_ALT = ImageColor.getrgb("#1a3342")
RIBBON = ImageColor.getrgb("#dfe6e8")
LINE = ImageColor.getrgb("#5a99ac")
WHITE = ImageColor.getrgb("#f4f7f7")
TEXT = ImageColor.getrgb("#d7e1e3")
MUTED = ImageColor.getrgb("#9fb1b8")
GOLD = ImageColor.getrgb("#f2c88b")
GREEN = ImageColor.getrgb("#58d8a8")
RED = ImageColor.getrgb("#ff838b")
BLUE = ImageColor.getrgb("#91c8ff")
BLACK = ImageColor.getrgb("#071014")

ASSET_HEROES = Path("hero_portraits")
ASSET_LOGOS = Path("team_logos")
ASSET_ITEMS = Path("item_icons")
ASSET_FONTS = Path("assets/fonts")
for asset_dir in (ASSET_HEROES, ASSET_LOGOS, ASSET_ITEMS):
    asset_dir.mkdir(exist_ok=True)

MAX_REMOTE_IMAGE_BYTES = 8 * 1024 * 1024


def _font(size: int, bold: bool = False, condensed: bool = False):
    candidates = []
    if condensed and bold:
        candidates += [
            ASSET_FONTS / "DejaVuSans-Bold.ttf",
            "C:/Windows/Fonts/bahnschrift.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/impact.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
        ]
    if condensed and not bold:
        candidates += [
            ASSET_FONTS / "DejaVuSans.ttf",
            "C:/Windows/Fonts/bahnschrift.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
        ]
    if bold:
        candidates += [
            ASSET_FONTS / "DejaVuSans-Bold.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/seguisym.ttf",
            "C:/Windows/Fonts/msyhbd.ttc",
            "C:/Windows/Fonts/meiryob.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
    else:
        candidates += [
            ASSET_FONTS / "DejaVuSans.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/seguisym.ttf",
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/meiryo.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


FONT_PREVIEW_TITLE = _font(70, bold=True, condensed=True)
FONT_PREVIEW_TEAM = _font(46, bold=True, condensed=True)
FONT_PREVIEW_TEAM_MED = _font(40, bold=True, condensed=True)
FONT_PREVIEW_TEAM_SMALL = _font(32, bold=True, condensed=True)
FONT_PREVIEW_NAME = _font(20, bold=True)
FONT_PREVIEW_NAME_SMALL = _font(18, bold=True)
FONT_PREVIEW_HERO = _font(16, bold=False)
FONT_PREVIEW_BRAND = _font(30, bold=True, condensed=True)
FONT_PREVIEW_HANDLE = _font(24, bold=True)
FONT_PREVIEW_SUB = _font(18, bold=True, condensed=True)
FONT_RESULT_TITLE = _font(38, bold=True, condensed=True)
FONT_RESULT_META = _font(22, bold=True, condensed=True)
FONT_RESULT_TEAM = _font(25, bold=True)
FONT_RESULT_SIDE = _font(17, bold=True, condensed=True)
FONT_RESULT_HEAD = _font(16, bold=True)
FONT_RESULT_NAME = _font(18, bold=True)
FONT_RESULT_HERO = _font(15)
FONT_RESULT_STAT = _font(18, bold=True)
FONT_RESULT_SMALL = _font(14, bold=True)
FONT_RESULT_BRAND = _font(24, bold=True, condensed=True)
FONT_RESULT_STAT_FIT = _font(16, bold=True)
FONT_RESULT_STAT_TINY = _font(14, bold=True)


def _tw(draw, text, font):
    box = draw.textbbox((0, 0), str(text), font=font)
    return box[2] - box[0]


def _fit(draw, text, font, width):
    text = str(text or "").strip()
    if _tw(draw, text, font) <= width:
        return text
    while text and _tw(draw, f"{text}...", font) > width:
        text = text[:-1]
    return f"{text}..." if text else ""


def _fit_font(draw, text, fonts, width):
    for font in fonts:
        if _tw(draw, str(text or ""), font) <= width:
            return str(text or "").strip(), font
    return _fit(draw, text, fonts[-1], width), fonts[-1]


def _fmt_k(value):
    value = int(value or 0)
    return f"{value / 1000:.1f}k" if value >= 1000 else str(value)


def _fmt_duration(seconds):
    minutes, seconds = divmod(int(seconds or 0), 60)
    return f"{minutes}:{seconds:02d}"


def _map_label(match: dict) -> str:
    game_number = int(match.get("game_number") or 0)
    return f"Map {game_number}" if game_number else "Map"


def _safe_name(text):
    raw = str(text or "").strip()
    if not raw or raw == "-":
        return "Player"

    value = unicodedata.normalize("NFKC", raw)
    cleaned = []
    for char in value:
        category = unicodedata.category(char)
        if category.startswith("C") or category in {"Mn", "Me"}:
            continue
        if not char.isprintable():
            continue
        cleaned.append(char)

    value = " ".join("".join(cleaned).split()).strip()
    return value or raw or "Player"

def _gradient(img):
    draw = ImageDraw.Draw(img)
    for y in range(img.height):
        t = y / max(img.height - 1, 1)
        if t < 0.5:
            t2 = t / 0.5
            color = tuple(int(BG_TOP[i] * (1 - t2) + BG_MID[i] * t2) for i in range(3))
        else:
            t2 = (t - 0.5) / 0.5
            color = tuple(int(BG_MID[i] * (1 - t2) + BG_BOTTOM[i] * t2) for i in range(3))
        draw.line([(0, y), (img.width, y)], fill=color)


def _is_allowed_image_url(url: str) -> bool:
    try:
        parsed = urlparse(str(url or "").strip())
    except Exception:
        return False

    if parsed.scheme != "https" or not parsed.hostname:
        return False
    if parsed.username or parsed.password:
        return False
    return True


def _download_image(url: str) -> bytes | None:
    try:
        response = requests.get(url, timeout=15, stream=True)
        if response.status_code != 200:
            return None

        chunks = []
        total = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_REMOTE_IMAGE_BYTES:
                return None
            chunks.append(chunk)
        return b"".join(chunks)
    except Exception:
        return None


def _fetch_png(url: str, cache_dir: Path):
    if not url or not _is_allowed_image_url(url):
        return None
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    path = cache_dir / f"{digest}.png"
    if path.exists():
        try:
            return Image.open(path).convert("RGBA")
        except Exception:
            pass
    try:
        image_bytes = _download_image(url)
        if image_bytes:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
            image.save(path)
            return image
    except Exception:
        return None
    return None


def _hero_image(hero_short_name: str):
    if not hero_short_name:
        return None
    url = f"https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/{hero_short_name}.png"
    return _fetch_png(url, ASSET_HEROES)


def _spirit_bear_image():
    url = "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/abilities/lone_druid_spirit_bear.png"
    return _fetch_png(url, ASSET_HEROES)


def _asset_token(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.replace("item_", "")
    text = re.sub(r"(?<!^)(?=[A-Z])", "_", text).lower()
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def _item_image(item_short_name: str):
    token = _asset_token(item_short_name)
    if not token:
        return None
    candidates = [token]
    if token.startswith("recipe_") or token.endswith("_recipe"):
        candidates.append("recipe")
    for candidate in dict.fromkeys(candidates):
        url = f"https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items/{candidate}.png"
        image = _fetch_png(url, ASSET_ITEMS)
        if image:
            return image
    return None


def _item_icon(item: dict):
    if not item:
        return None
    for candidate in (item.get("short_name"), item.get("name"), item.get("display_name")):
        image = _item_image(candidate or "")
        if image:
            return image
    return None


def _team_logo(url: str):
    logo = _fetch_png(url, ASSET_LOGOS) if url else None
    return _remove_flat_logo_background(logo)


def _remove_flat_logo_background(image):
    if not image:
        return None
    logo = image.convert("RGBA")
    alpha = logo.getchannel("A")
    if alpha.getextrema()[0] < 255:
        return logo

    w, h = logo.size
    corners = [
        logo.getpixel((0, 0))[:3],
        logo.getpixel((w - 1, 0))[:3],
        logo.getpixel((0, h - 1))[:3],
        logo.getpixel((w - 1, h - 1))[:3],
    ]
    avg = tuple(sum(color[i] for color in corners) // 4 for i in range(3))
    if max(sum(abs(color[i] - avg[i]) for i in range(3)) for color in corners) > 36:
        return logo

    pixels = logo.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            distance = abs(r - avg[0]) + abs(g - avg[1]) + abs(b - avg[2])
            if distance <= 48:
                pixels[x, y] = (r, g, b, 0)
            elif distance <= 72:
                pixels[x, y] = (r, g, b, int(a * (distance - 48) / 24))
    return logo


def _hero_focus(hero_short_name: str, mode: str = "default") -> tuple[float, float]:
    special = {
        "lone_druid": (0.18, 0.10),
        "puck": (0.50, 0.12),
    }
    focus_x, focus_y = special.get(hero_short_name or "", (0.50, 0.16 if mode == "result" else 0.08))
    return focus_x, focus_y


def _team_badge_text(team_name: str) -> str:
    lowered = str(team_name or "").lower()
    if "betboom" in lowered:
        return "BB"
    if "spirit" in lowered:
        return "TS"
    if "liquid" in lowered:
        return "TL"
    if "falcons" in lowered:
        return "FL"
    parts = [p for p in str(team_name or "").replace("-", " ").split() if p.lower() not in {"team", "esports", "gaming"}]
    if not parts:
        parts = str(team_name or "TM").split()
    if len(parts) == 1:
        token = parts[0]
        caps = "".join(ch for ch in token if ch.isupper())
        if len(caps) >= 2:
            return caps[:2]
        return token[:2].upper()
    return "".join(part[:1] for part in parts[:2]).upper()


def _paste_contain(base, image, box, padding=0):
    if not image:
        return False
    x1, y1, x2, y2 = box
    target = (max(1, x2 - x1 - padding * 2), max(1, y2 - y1 - padding * 2))
    fitted = ImageOps.contain(image.convert("RGBA"), target, Image.Resampling.LANCZOS)
    pos = (x1 + (x2 - x1 - fitted.width) // 2, y1 + (y2 - y1 - fitted.height) // 2)
    base.paste(fitted, pos, fitted)
    return True


def _paste_circle_cover(base, image, box):
    if not image:
        return False
    x1, y1, x2, y2 = box
    size = max(1, min(x2 - x1, y2 - y1))
    source = image.convert("RGBA")
    fitted = ImageOps.fit(source, (size, size), Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    alpha = fitted.getchannel("A")
    fitted.putalpha(Image.composite(alpha, Image.new("L", (size, size), 0), mask))
    base.paste(fitted, (x1, y1), fitted)
    return True


def _paste_cover(base, image, box, focus_top=0.35, grayscale=False, focus_x=0.5):
    x1, y1, x2, y2 = box
    if not image:
        return False
    source = image.convert("RGBA")
    if grayscale:
        source = ImageOps.grayscale(source).convert("RGBA")
    sw, sh = source.size
    tw, th = x2 - x1, y2 - y1
    scale = max(tw / sw, th / sh)
    resized = source.resize((max(1, int(sw * scale)), max(1, int(sh * scale))), Image.Resampling.LANCZOS)
    crop_x = max(0, min(resized.width - tw, int((resized.width - tw) * focus_x)))
    crop_y = max(0, min(resized.height - th, int((resized.height - th) * focus_top)))
    cropped = resized.crop((crop_x, crop_y, crop_x + tw, crop_y + th))
    base.paste(cropped, (x1, y1), cropped)
    return True


def _draw_logo_box(base, draw, logo, box, fallback_text="TM"):
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=16, fill=None, outline=LINE, width=2)
    inner = [x1 + 6, y1 + 6, x2 - 6, y2 - 6]
    if logo and _paste_contain(base, logo, inner, padding=2):
        return
    draw.rounded_rectangle(box, radius=16, fill=(10, 18, 24), outline=LINE, width=2)
    text = (fallback_text or "TM")[:3].upper()
    font = _font(max(22, int((box[3] - box[1]) * 0.42)), bold=True, condensed=True)
    tw = _tw(draw, text, font)
    th_box = draw.textbbox((0, 0), text, font=font)
    th = th_box[3] - th_box[1]
    cx = (box[0] + box[2]) // 2
    cy = (box[1] + box[3]) // 2
    draw.text((cx - tw // 2, cy - th // 2 - 2), text, font=font, fill=WHITE)


def _draw_preview_logo_box(base, draw, logo, box, fallback_text="TM"):
    x1, y1, x2, y2 = box
    inner = [x1 + 8, y1 + 8, x2 - 8, y2 - 8]
    if logo:
        logo_rgba = logo.convert("RGBA")
        alpha = logo_rgba.getchannel("A")
        if alpha.getbbox():
            draw.rounded_rectangle(box, radius=16, fill=(12, 23, 30), outline=LINE, width=2)
            box_region = Image.new("RGBA", (x2 - x1, y2 - y1), (0, 0, 0, 0))
            draw_region = ImageDraw.Draw(box_region)
            draw_region.rounded_rectangle([9, 9, x2 - x1 - 9, y2 - y1 - 9], radius=14, fill=(12, 23, 30, 210))
            _paste_contain(box_region, logo_rgba, [10, 10, x2 - x1 - 10, y2 - y1 - 10], padding=2)
            base.paste(box_region, (x1, y1), box_region)
            return
    draw.rounded_rectangle(box, radius=16, fill=(20, 35, 44), outline=LINE, width=2)
    if logo and _paste_contain(base, logo, inner, padding=2):
        return
    text = (fallback_text or "TM")[:3].upper()
    font = _font(max(22, int((inner[3] - inner[1]) * 0.42)), bold=True, condensed=True)
    tw = _tw(draw, text, font)
    th_box = draw.textbbox((0, 0), text, font=font)
    th = th_box[3] - th_box[1]
    cx = (inner[0] + inner[2]) // 2
    cy = (inner[1] + inner[3]) // 2
    draw.text((cx - tw // 2, cy - th // 2 - 2), text, font=font, fill=WHITE)


def _draw_header_pill(draw, text, box, fill, outline, font, text_fill):
    draw.rounded_rectangle(box, radius=12, fill=fill, outline=outline, width=2)
    tw = _tw(draw, text, font)
    th_box = draw.textbbox((0, 0), text, font=font)
    th = th_box[3] - th_box[1]
    x1, y1, x2, y2 = box
    draw.text((x1 + (x2 - x1 - tw) // 2, y1 + (y2 - y1 - th) // 2 - 2), text, font=font, fill=text_fill)


def _draw_team_bar(draw, box, fill, title, title_font, title_fill):
    draw.rounded_rectangle(box, radius=10, fill=fill, outline=LINE, width=2)
    x1, y1, x2, y2 = box
    title, title_font = _fit_font(
        draw,
        title,
        [title_font, FONT_PREVIEW_TEAM_MED, FONT_PREVIEW_TEAM_SMALL],
        x2 - x1 - 190,
    )
    tw = _tw(draw, title, title_font)
    th_box = draw.textbbox((0, 0), title, font=title_font)
    th = th_box[3] - th_box[1]
    draw.text((x1 + (x2 - x1 - tw) // 2, y1 + (y2 - y1 - th) // 2 - 2), title, font=title_font, fill=title_fill)


def _hero_card(base, draw, player, box):
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=12, fill=PANEL, outline=LINE, width=1)
    hero_img = _hero_image(player.get("hero_short_name") or "")
    hero_short_name = player.get("hero_short_name") or ""
    focus_x, focus_y = _hero_focus(hero_short_name, mode="preview")
    inset = [x1 + 8, y1 + 8, x2 - 8, y2 - 58]
    draw.rounded_rectangle(inset, radius=10, fill=(13, 22, 29))
    if hero_short_name == "lone_druid":
        _paste_contain(base, hero_img, inset, padding=2)
    else:
        _paste_cover(base, hero_img, inset, focus_top=focus_y, focus_x=focus_x)
    overlay_top = y2 - 60
    draw.rounded_rectangle([x1 + 6, overlay_top, x2 - 6, y2 - 6], radius=10, fill=(8, 15, 20))
    raw_name = _safe_name(player.get("name"))
    name, name_font = _fit_font(draw, raw_name, [FONT_PREVIEW_NAME, FONT_PREVIEW_NAME_SMALL], x2 - x1 - 20)
    hero = _fit(draw, player.get("hero_name") or "", FONT_PREVIEW_HERO, x2 - x1 - 16)
    name_w = _tw(draw, name, name_font)
    hero_w = _tw(draw, hero.upper(), FONT_PREVIEW_HERO)
    draw.text((x1 + max(10, (x2 - x1 - name_w) // 2), overlay_top + 8), name, font=name_font, fill=WHITE)
    draw.text((x1 + max(10, (x2 - x1 - hero_w) // 2), overlay_top + 34), hero.upper(), font=FONT_PREVIEW_HERO, fill=TEXT)


def _draw_ban_strip(base, draw, bans, box):
    x1, y1, x2, y2 = box
    gap = 8
    slot_count = max(7, len(bans) or 0)
    slot_w = (x2 - x1 - gap * (slot_count - 1)) // slot_count
    for i in range(slot_count):
        sx1 = x1 + i * (slot_w + gap)
        sx2 = sx1 + slot_w
        draw.rounded_rectangle([sx1, y1, sx2, y2], radius=10, fill=(28, 43, 52), outline=(111, 151, 164), width=2)
        hero = bans[i] if i < len(bans) else None
        if hero:
            hero_img = _hero_image(hero.get("hero_short_name") or "")
            if hero_img:
                _paste_cover(base, hero_img, [sx1 + 3, y1 + 3, sx2 - 3, y2 - 3], focus_top=0.20, grayscale=True)
            else:
                fallback = _fit(draw, hero.get("hero_name") or "BAN", FONT_RESULT_SMALL, slot_w - 12)
                tw = _tw(draw, fallback.upper(), FONT_RESULT_SMALL)
                draw.text((sx1 + (slot_w - tw) // 2, y1 + (y2 - y1) // 2 - 8), fallback.upper(), font=FONT_RESULT_SMALL, fill=MUTED)


def _draw_item_slots(base, draw, items, box, cols, rows=1):
    x1, y1, x2, y2 = box
    gap = 4
    slot_w = (x2 - x1 - gap * (cols - 1)) // cols
    max_slot_h = (y2 - y1 - gap * (rows - 1)) // rows
    slot_h = min(max_slot_h, max(1, int(slot_w * 0.75)))
    top_offset = max(0, (max_slot_h - slot_h) // 2)
    idx = 0
    for row in range(rows):
        for col in range(cols):
            sx1 = x1 + col * (slot_w + gap)
            sy1 = y1 + top_offset + row * (max_slot_h + gap)
            sx2 = sx1 + slot_w
            sy2 = sy1 + slot_h
            draw.rounded_rectangle([sx1, sy1, sx2, sy2], radius=4, fill=(18, 33, 42), outline=LINE, width=1)
            item = items[idx] if idx < len(items) else None
            if item:
                icon = _item_icon(item)
                if not _paste_contain(base, icon, [sx1, sy1, sx2, sy2], padding=0):
                    label = _item_fallback_text(item)
                    label = _fit(draw, label, FONT_RESULT_SMALL, slot_w - 6).upper()
                    tw = _tw(draw, label, FONT_RESULT_SMALL)
                    th_box = draw.textbbox((0, 0), label, font=FONT_RESULT_SMALL)
                    th = th_box[3] - th_box[1]
                    draw.text((sx1 + (slot_w - tw) // 2, sy1 + (slot_h - th) // 2 - 1), label, font=FONT_RESULT_SMALL, fill=MUTED)
            idx += 1


def _draw_buff_slots(base, draw, items, box, cols):
    x1, y1, x2, y2 = box
    gap = 4
    slot_w = (x2 - x1 - gap * (cols - 1)) // cols
    diameter = max(1, min(slot_w, y2 - y1))
    top = y1 + (y2 - y1 - diameter) // 2
    for idx in range(cols):
        sx1 = x1 + idx * (slot_w + gap)
        sx2 = sx1 + diameter
        sy1 = top
        sy2 = top + diameter
        draw.ellipse([sx1, sy1, sx2, sy2], fill=(18, 33, 42), outline=LINE, width=1)
        item = items[idx] if idx < len(items) else None
        if not item:
            continue
        icon = _item_icon(item)
        if not _paste_circle_cover(base, icon, [sx1 + 1, sy1 + 1, sx2 - 1, sy2 - 1]):
            label = _item_fallback_text(item).upper()
            label = _fit(draw, label, FONT_RESULT_SMALL, diameter - 8)
            tw = _tw(draw, label, FONT_RESULT_SMALL)
            th_box = draw.textbbox((0, 0), label, font=FONT_RESULT_SMALL)
            th = th_box[3] - th_box[1]
            draw.text((sx1 + (diameter - tw) // 2, sy1 + (diameter - th) // 2 - 1), label, font=FONT_RESULT_SMALL, fill=MUTED)


def _item_fallback_text(item: dict) -> str:
    text = str(item.get("display_name") or item.get("short_name") or "ITEM").replace("_", " ").strip()
    words = [word for word in text.split() if word]
    if len(words) >= 2:
        return "".join(word[:1] for word in words[:3])
    return (words[0] if words else "IT")[:3]


def _result_columns():
    return {
        "hero": 18,
        "player": 126,
        "k": 380,
        "d": 448,
        "a": 516,
        "net": 595,
        "items": 700,
        "backpack": 1018,
        "neutral": 1158,
        "buffs": 1228,
        "gpm": 1328,
        "xpm": 1390,
        "dmg": 1452,
        "heal": 1538,
        "tower": 1604,
    }


def _result_header_widths():
    return {
        "hero": 78,
        "k": 28,
        "d": 28,
        "a": 28,
        "net": 56,
        "items": 300,
        "backpack": 126,
        "neutral": 54,
        "buffs": 90,
        "gpm": 56,
        "xpm": 56,
        "dmg": 72,
        "heal": 60,
        "tower": 72,
    }


def _fit_result_value_font(draw, value: str, font, width: int):
    for candidate in (font, FONT_RESULT_STAT_FIT, FONT_RESULT_STAT_TINY, FONT_RESULT_SMALL):
        if _tw(draw, value, candidate) <= width:
            return value, candidate
    return value, FONT_RESULT_SMALL


def _draw_result_cell_text(draw, cols: dict, widths: dict, key: str, y: int, text: str, font, fill):
    width = widths.get(key, 40)
    value = str(text)
    if key in {"gpm", "xpm", "dmg", "heal", "tower", "net"}:
        value, font = _fit_result_value_font(draw, value, font, width)
    else:
        value = _fit(draw, value, font, width)
    draw.text((cols[key] + (width - _tw(draw, value, font)) // 2, y), value, font=font, fill=fill)


def _result_player_rows(players):
    rows = []
    for player in players[:5]:
        rows.append(player)
        units = player.get("additional_units") or []
        if player.get("hero_short_name") == "lone_druid" and units:
            bear = units[0]
            rows.append(
                {
                    "is_bear_unit": True,
                    "hero_short_name": "spirit_bear",
                    "hero_name": "Spirit Bear",
                    "name": "Spirit Bear",
                    "items": bear.get("items") or [],
                    "backpack": bear.get("backpack") or [],
                    "buffs": bear.get("buffs") or [],
                    "neutral_item": bear.get("neutral_item"),
                }
            )
    return rows


def _draw_result_team(base, draw, team_name, score, players, logo, y, accent, status_label, status_fill):
    cols = _result_columns()
    section_x1 = 18
    section_x2 = IMG_W_RESULT - 18

    header_h = 62
    draw.rounded_rectangle([section_x1, y, section_x2, y + header_h], radius=10, fill=PANEL, outline=LINE, width=2)
    _draw_logo_box(base, draw, logo, [section_x1 + 10, y + 4, section_x1 + 92, y + 58], _team_badge_text(team_name))
    team_x = section_x1 + 106
    team_text, team_font = _fit_font(
        draw,
        team_name,
        [FONT_RESULT_TEAM, _font(23, bold=True), _font(21, bold=True)],
        270,
    )
    draw.text((team_x, y + 17), team_text, font=team_font, fill=WHITE)

    status_color = GREEN if status_label.upper() == "WIN" else RED
    status_box = [cols["k"] - 6, y + 13, cols["a"] + 60, y + 45]
    score_text = str(score)
    score_font = _font(25, bold=True, condensed=True)
    label_text = status_label.upper()
    label_font = _font(15, bold=True, condensed=True)
    gap = 8
    score_bbox = draw.textbbox((0, 0), score_text, font=score_font)
    label_bbox = draw.textbbox((0, 0), label_text, font=label_font)
    score_w = score_bbox[2] - score_bbox[0]
    score_h = score_bbox[3] - score_bbox[1]
    label_w = label_bbox[2] - label_bbox[0]
    label_h = label_bbox[3] - label_bbox[1]
    group_w = score_w + gap + label_w
    group_x = status_box[0] + (status_box[2] - status_box[0] - group_w) // 2
    baseline_y = status_box[1] + (status_box[3] - status_box[1] - score_h) // 2 - 2
    draw.text((group_x, baseline_y), score_text, font=score_font, fill=status_color)
    draw.text((group_x + score_w + gap, baseline_y + score_h - label_h - 2), label_text, font=label_font, fill=status_color)
    draw.line([(status_box[0] + 28, y + 46), (status_box[2] - 28, y + 46)], fill=status_color, width=2)

    header_y = y + 72
    headers = [
        ("hero", "HERO"),
        ("k", "K"),
        ("d", "D"),
        ("a", "A"),
        ("net", "NET"),
        ("items", "ITEMS"),
        ("backpack", "BACKPACK"),
        ("neutral", "NEUT"),
        ("buffs", "BUFFS"),
        ("gpm", "GPM"),
        ("xpm", "XPM"),
        ("dmg", "DMG"),
        ("heal", "HEAL"),
        ("tower", "TOWER"),
    ]
    draw.text((cols["player"], header_y), "PLAYER", font=FONT_RESULT_HEAD, fill=MUTED)
    header_widths = _result_header_widths()
    for key, label in headers:
        header_font = FONT_RESULT_SMALL if key in {"buffs", "neutral", "tower"} else FONT_RESULT_HEAD
        width = header_widths.get(key, 40)
        text = _fit(draw, label, header_font, width)
        draw.text((cols[key] + (width - _tw(draw, text, header_font)) // 2, header_y), text, font=header_font, fill=MUTED)

    display_rows = _result_player_rows(players)
    row_h = 60 if len(display_rows) > 5 else 72
    row_inner_h = row_h - 6
    row_y = header_y + 24
    for idx, player in enumerate(display_rows):
        y1 = row_y + idx * row_h
        y2 = y1 + row_inner_h
        draw.rectangle([section_x1, y1, section_x2, y2], fill=PANEL_ALT if idx % 2 == 0 else PANEL)
        draw.line([(section_x1, y2), (section_x2, y2)], fill=LINE, width=1)

        hero_short_name = player.get("hero_short_name") or ""
        focus_x, focus_y = _hero_focus(hero_short_name, mode="result")
        hero_w = 84
        hero_h = 48 if row_inner_h >= 56 else 42
        hero_x1 = section_x1 + 8
        hero_y1 = y1 + (row_inner_h - hero_h) // 2
        hero_box = [hero_x1, hero_y1, hero_x1 + hero_w, hero_y1 + hero_h]
        hero_img = _spirit_bear_image() if player.get("is_bear_unit") else _hero_image(hero_short_name)
        if player.get("is_bear_unit"):
            draw.rectangle(hero_box, fill=(13, 22, 29), outline=GOLD, width=1)
            _paste_contain(base, hero_img, hero_box, padding=1)
        elif hero_short_name == "lone_druid":
            draw.rectangle(hero_box, fill=(13, 22, 29), outline=LINE, width=1)
            _paste_contain(base, hero_img, hero_box, padding=1)
        else:
            _paste_cover(base, hero_img, hero_box, focus_top=focus_y, focus_x=focus_x)
        name = _fit(draw, _safe_name(player.get("name")), FONT_RESULT_NAME, 260)
        hero = _fit(draw, player.get("hero_name") or "", FONT_RESULT_HERO, 260)
        draw.text((cols["player"], y1 + 6), name, font=FONT_RESULT_NAME, fill=GOLD if player.get("is_bear_unit") else WHITE)
        draw.text((cols["player"], y1 + 30), hero, font=FONT_RESULT_HERO, fill=MUTED)

        stat_y = y1 + (row_inner_h // 2) - 8
        if player.get("is_bear_unit"):
            for key in ("k", "d", "a", "net"):
                _draw_result_cell_text(draw, cols, header_widths, key, stat_y, "-", FONT_RESULT_STAT, MUTED)
        else:
            _draw_result_cell_text(draw, cols, header_widths, "k", stat_y, str(player.get("kills", 0)), FONT_RESULT_STAT, WHITE)
            _draw_result_cell_text(draw, cols, header_widths, "d", stat_y, str(player.get("deaths", 0)), FONT_RESULT_STAT, WHITE)
            _draw_result_cell_text(draw, cols, header_widths, "a", stat_y, str(player.get("assists", 0)), FONT_RESULT_STAT, WHITE)
            _draw_result_cell_text(draw, cols, header_widths, "net", stat_y, _fmt_k(player.get("net_worth")), FONT_RESULT_STAT, GOLD)

        _draw_item_slots(base, draw, player.get("items") or [], [cols["items"], y1 + 5, cols["items"] + 300, y2 - 5], cols=6)
        _draw_item_slots(base, draw, list(player.get("backpack") or [])[:3], [cols["backpack"], y1 + 5, cols["backpack"] + 126, y2 - 5], cols=3)
        neutral = player.get("neutral_item")
        _draw_item_slots(base, draw, [neutral] if neutral else [], [cols["neutral"], y1 + 5, cols["neutral"] + 54, y2 - 5], cols=1)
        _draw_buff_slots(base, draw, list(player.get("buffs") or [])[:3], [cols["buffs"], y1 + 4, cols["buffs"] + 94, y2 - 4], cols=3)

        if player.get("is_bear_unit"):
            for key in ("gpm", "xpm", "dmg", "heal", "tower"):
                _draw_result_cell_text(draw, cols, header_widths, key, stat_y, "-", FONT_RESULT_STAT, MUTED)
        else:
            heal = int(player.get("hero_healing") or 0)
            tower = int(player.get("tower_damage") or 0)
            _draw_result_cell_text(draw, cols, header_widths, "gpm", stat_y, str(player.get("gold_per_min", 0)), FONT_RESULT_STAT, TEXT)
            _draw_result_cell_text(draw, cols, header_widths, "xpm", stat_y, str(player.get("xp_per_min", 0)), FONT_RESULT_STAT, TEXT)
            _draw_result_cell_text(draw, cols, header_widths, "dmg", stat_y, _fmt_k(player.get("hero_damage")), FONT_RESULT_STAT, RED)
            _draw_result_cell_text(draw, cols, header_widths, "heal", stat_y, _fmt_k(heal) if heal else "-", FONT_RESULT_STAT, GREEN if heal else MUTED)
            _draw_result_cell_text(draw, cols, header_widths, "tower", stat_y, _fmt_k(tower) if tower else "-", FONT_RESULT_STAT, BLUE if tower else MUTED)

    return row_y + len(display_rows) * row_h


def generate_match_preview_image(match: dict) -> io.BytesIO:
    img = Image.new("RGB", (IMG_W_PREVIEW, IMG_H_PREVIEW), BG_TOP)
    _gradient(img)
    draw = ImageDraw.Draw(img)

    league_name = match.get("league_name") or "Tournament"
    radiant_name = match.get("radiant_name") or "Radiant"
    dire_name = match.get("dire_name") or "Dire"
    players = match.get("players") or []
    radiant = [p for p in players if p.get("isRadiant")]
    dire = [p for p in players if not p.get("isRadiant")]
    bans = match.get("bans") or []
    radiant_bans = [b for b in bans if b.get("is_radiant")][:7]
    dire_bans = [b for b in bans if not b.get("is_radiant")][:7]
    radiant_logo = _team_logo(((match.get("radiant_team") or {}).get("logo_url")))
    dire_logo = _team_logo(((match.get("dire_team") or {}).get("logo_url")))

    draw.text((78, 44), "MATCH PREVIEW", font=FONT_PREVIEW_TITLE, fill=WHITE)
    league_font = _font(32, bold=True, condensed=True)
    draw.text((82, 138), _fit(draw, league_name.upper(), league_font, 820), font=league_font, fill=TEXT)
    _draw_header_pill(
        draw,
        "@dota2_matches",
        [IMG_W_PREVIEW - 360, 126, IMG_W_PREVIEW - 82, 176],
        BG_TOP,
        LINE,
        FONT_PREVIEW_HANDLE,
        WHITE,
    )

    ribbon_h = 74
    card_w = 214
    card_h = 208
    gap = 10
    total_cards_w = card_w * 5 + gap * 4
    start_x = (IMG_W_PREVIEW - total_cards_w) // 2

    _draw_team_bar(draw, [80, 216, IMG_W_PREVIEW - 80, 216 + ribbon_h], RIBBON, radiant_name, FONT_PREVIEW_TEAM, BLACK)
    _draw_preview_logo_box(img, draw, radiant_logo, [82, 208, 196, 312], _team_badge_text(radiant_name))

    for idx, player in enumerate(radiant[:5]):
        x1 = start_x + idx * (card_w + gap)
        _hero_card(img, draw, player, [x1, 328, x1 + card_w, 328 + card_h])

    _draw_ban_strip(img, draw, radiant_bans, [90, 566, IMG_W_PREVIEW - 90, 672])

    _draw_team_bar(draw, [80, 740, IMG_W_PREVIEW - 80, 740 + ribbon_h], RIBBON, dire_name, FONT_PREVIEW_TEAM, BLACK)
    _draw_preview_logo_box(img, draw, dire_logo, [82, 732, 196, 836], _team_badge_text(dire_name))

    for idx, player in enumerate(dire[:5]):
        x1 = start_x + idx * (card_w + gap)
        _hero_card(img, draw, player, [x1, 852, x1 + card_w, 852 + card_h])

    _draw_ban_strip(img, draw, dire_bans, [90, 1090, IMG_W_PREVIEW - 90, 1196])

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


def generate_match_result_image(match: dict) -> io.BytesIO:
    img = Image.new("RGB", (IMG_W_RESULT, IMG_H_RESULT), BG_TOP)
    _gradient(img)
    draw = ImageDraw.Draw(img)

    league_name = match.get("league_name") or "Tournament"
    radiant_name = match.get("radiant_name") or "Radiant"
    dire_name = match.get("dire_name") or "Dire"
    radiant_score = int(match.get("radiant_score") or 0)
    dire_score = int(match.get("dire_score") or 0)
    radiant_win = bool(match.get("radiant_win")) if match.get("radiant_win") is not None else radiant_score > dire_score
    duration = _fmt_duration(match.get("duration") or 0)
    map_label = _map_label(match)
    players = match.get("players") or []
    radiant_players = [p for p in players if p.get("isRadiant")]
    dire_players = [p for p in players if not p.get("isRadiant")]
    radiant_logo = _team_logo(((match.get("radiant_team") or {}).get("logo_url")))
    dire_logo = _team_logo(((match.get("dire_team") or {}).get("logo_url")))

    header_h = 94
    draw.rectangle([0, 0, IMG_W_RESULT, header_h], fill=(9, 20, 27))
    brand_box = [IMG_W_RESULT - 380, 24, IMG_W_RESULT - 54, 66]
    _draw_header_pill(
        draw,
        "@dota2_matches",
        brand_box,
        BG_TOP,
        LINE,
        FONT_RESULT_BRAND,
        WHITE,
    )
    title, title_font = _fit_font(
        draw,
        league_name.upper(),
        [FONT_RESULT_TITLE, _font(34, bold=True, condensed=True), _font(30, bold=True, condensed=True)],
        brand_box[0] - 220,
    )
    title_w = _tw(draw, title, title_font)
    draw.text((IMG_W_RESULT // 2 - title_w // 2, 24), title, font=title_font, fill=GOLD)
    map_box = [86, 26, 228, 62]
    draw.rounded_rectangle(map_box, radius=10, fill=BG_TOP, outline=LINE, width=2)
    map_font = _font(24, bold=True, condensed=True)
    map_bbox = draw.textbbox((0, 0), map_label, font=map_font)
    map_w = map_bbox[2] - map_bbox[0]
    map_h = map_bbox[3] - map_bbox[1]
    draw.text((map_box[0] + (map_box[2] - map_box[0] - map_w) // 2, map_box[1] + (map_box[3] - map_box[1] - map_h) // 2 - 2), map_label, font=map_font, fill=WHITE)

    time_box = [282, 26, 452, 62]
    draw.rounded_rectangle(time_box, radius=10, fill=BG_TOP, outline=LINE, width=2)
    time_font = _font(24, bold=True, condensed=True)
    time_bbox = draw.textbbox((0, 0), duration, font=time_font)
    time_w = time_bbox[2] - time_bbox[0]
    time_h = time_bbox[3] - time_bbox[1]
    draw.text((time_box[0] + (time_box[2] - time_box[0] - time_w) // 2, time_box[1] + (time_box[3] - time_box[1] - time_h) // 2 - 2), duration, font=time_font, fill=WHITE)
    top_y = 98
    bottom_y = 560
    _draw_result_team(
        img, draw, radiant_name, radiant_score, radiant_players, radiant_logo, top_y, GREEN,
        "WIN" if radiant_win else "LOSE",
        (20, 120, 80) if radiant_win else (110, 30, 38),
    )
    _draw_result_team(
        img, draw, dire_name, dire_score, dire_players, dire_logo, bottom_y, RED,
        "LOSE" if radiant_win else "WIN",
        (110, 30, 38) if radiant_win else (20, 120, 80),
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


def generate_match_image(match: dict) -> io.BytesIO:
    return generate_match_result_image(match)
