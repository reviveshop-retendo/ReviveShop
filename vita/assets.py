"""Image helpers: fonts, masks, gradients, icon loading and the default wallpaper."""

import math
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import config

_FONT_CANDIDATES = (
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ("/usr/share/fonts/truetype/ubuntu/Ubuntu-Bold.ttf",
     "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ("/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
     "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
)


@lru_cache(maxsize=64)
def font(size, bold=False):
    for bold_path, reg_path in _FONT_CANDIDATES:
        path = bold_path if bold else reg_path
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


@lru_cache(maxsize=32)
def circle_mask(size, supersample=4):
    big = size * supersample
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, big - 1, big - 1), fill=255)
    return mask.resize((size, size), Image.LANCZOS)


def vertical_gradient(size, top, bottom):
    w, h = size
    grad = Image.new("RGB", (1, h))
    px = grad.load()
    for y in range(h):
        t = y / max(1, h - 1)
        px[0, y] = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return grad.resize((w, h), Image.BILINEAR)


def default_background(size):
    w, h = size
    img = vertical_gradient(size, config.PALETTE["bg_top"], config.PALETTE["bg_bottom"]).convert("RGBA")

    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    wave = config.PALETTE["bg_wave"]
    spacing = 34
    amplitude = 16
    for x in range(-h, w + h, spacing):
        pts = []
        for y in range(0, h + 1, 8):
            xx = x + amplitude * math.sin((y / h) * math.pi * 1.4 + x * 0.02)
            pts.append((xx, y))
        draw.line(pts, fill=(wave[0], wave[1], wave[2], 26), width=2)
    for x in range(-h, w + h, spacing):
        pts = []
        for y in range(0, h + 1, 8):
            xx = x - amplitude * math.sin((y / h) * math.pi * 1.4 + x * 0.02)
            pts.append((xx, y))
        draw.line(pts, fill=(wave[0], wave[1], wave[2], 18), width=2)

    return Image.alpha_composite(img, overlay)


def contain(img, size):
    w, h = size
    iw, ih = img.size
    if iw == 0 or ih == 0:
        return Image.new("RGBA", size, (0, 0, 0, 0))
    scale = min(w / iw, h / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    resized = img.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.paste(resized, ((w - nw) // 2, (h - nh) // 2), resized)
    return canvas


def cover(img, size):
    w, h = size
    iw, ih = img.size
    if iw == 0 or ih == 0:
        return Image.new("RGBA", size, (0, 0, 0, 0))
    scale = max(w / iw, h / ih)
    nw, nh = max(1, int(round(iw * scale))), max(1, int(round(ih * scale)))
    resized = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - w) // 2
    top = (nh - h) // 2
    return resized.crop((left, top, left + w, top + h))


def load_image(path, mode="RGBA"):
    with Image.open(path) as im:
        return im.convert(mode)


def circular_icon(path, size):
    try:
        img = load_image(path)
    except Exception:
        return None
    img = contain(img, (size, size))
    img.putalpha(circle_mask(size))
    return img


def placeholder_icon(title, size):
    seed = sum(ord(c) for c in (title or "?"))
    hue = seed % 360
    r, g, b = _hsv_to_rgb(hue, 0.45, 0.78)
    top = (min(255, r + 30), min(255, g + 30), min(255, b + 30))
    base = vertical_gradient((size, size), top, (r, g, b)).convert("RGBA")
    base.putalpha(circle_mask(size))

    draw = ImageDraw.Draw(base)
    letter = (title or "?").strip()[:1].upper() or "?"
    f = font(int(size * 0.46), bold=True)
    bbox = draw.textbbox((0, 0), letter, font=f)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]),
              letter, font=f, fill=(255, 255, 255, 235))
    return base


def _hsv_to_rgb(h, s, v):
    i = int(h // 60) % 6
    f = (h / 60) - int(h // 60)
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)
    r, g, b = [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][i]
    return int(r * 255), int(g * 255), int(b * 255)


def sheen(size):
    if isinstance(size, int):
        size = (size, size)
    w, h = size
    s = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = s.load()
    for y in range(h):
        t = y / max(1, h - 1)
        if t < 0.55:
            a = int(90 * (1 - t / 0.55) ** 1.5)
        else:
            a = 0
        for x in range(w):
            px[x, y] = (255, 255, 255, a)
    s.putalpha(Image.composite(s.getchannel("A"), Image.new("L", (w, h), 0), circle_mask(w)))
    return s
