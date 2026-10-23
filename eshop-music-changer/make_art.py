"""Generate the eShop Music Changer icon + banner in the ReviveShop house style.

Icon   : 48x48  RGBA (SMDH small icon)
Banner : 256x128 RGBA (CIA banner)

Style matches the category art: vertical gradient (bright -> dark), centred
bold white text.

Usage:  .venv/bin/python eshop-music-changer/make_art.py
"""

import os

from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(__file__), "meta")

# House hue - a warm amber/gold reads as "music".
TOP = (255, 196, 84)
BOTTOM = (120, 58, 12)


def font(size):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ):
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                pass
    return ImageFont.load_default()


def gradient(w, h):
    img = Image.new("RGB", (1, h))
    px = img.load()
    for y in range(h):
        t = y / max(1, h - 1)
        px[0, y] = tuple(
            int(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3)
        )
    return img.resize((w, h), Image.NEAREST)


def centred(draw, box, text, fnt):
    x0, y0, x1, y1 = box
    l, t, r, b = draw.textbbox((0, 0), text, font=fnt)
    draw.text(
        (x0 + (x1 - x0 - (r - l)) / 2 - l, y0 + (y1 - y0 - (b - t)) / 2 - t),
        text,
        font=fnt,
        fill=(255, 255, 255, 255),
    )


def make_icon():
    size = 48
    img = gradient(size, size).convert("RGBA")
    d = ImageDraw.Draw(img)
    # A filled music note reads better than text at 48px.
    f = font(30)
    centred(d, (0, 0, size, size - 2), "\u266b", f)
    img.save(os.path.join(OUT, "icon.png"))
    print("  wrote icon.png (48x48)")


def make_banner():
    w, h = 256, 128
    img = gradient(w, h).convert("RGBA")
    d = ImageDraw.Draw(img)
    centred(d, (0, 24, w, 62), "eShop", font(34))
    centred(d, (0, 62, w, 96), "Music Changer", font(24))
    img.save(os.path.join(OUT, "banner.png"))
    print("  wrote banner.png (256x128)")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    make_icon()
    make_banner()
