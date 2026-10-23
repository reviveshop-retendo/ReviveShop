"""Generate eShop Music Changer title art in the ReviveShop house style.

Produces, in assetcdn/:
    eshop_music_112x112.jpg   thumbnail
    eshop_music_128x128.jpg   icon
    eshop_music_512x160.jpg   banner

Style: vertical gradient (bright -> dark), centred bold white text - the same
recipe used for the category art.

Usage:  .venv/bin/python eshop-music-changer/make_title_art.py
"""

import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assetcdn")

# Warm amber/gold, matching the app icon.
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


def save(img, name, q=90):
    img.convert("RGB").save(os.path.join(OUT, name), quality=q, optimize=True)
    print(f"  wrote {name} ({img.size[0]}x{img.size[1]})")


def make_square(size, out_name):
    img = gradient(size, size).convert("RGBA")
    d = ImageDraw.Draw(img)
    centred(d, (0, 0, size, size - 2), "\u266b", font(int(size * 0.62)))
    save(img, out_name)


def make_banner():
    w, h = 512, 160
    img = gradient(w, h).convert("RGBA")
    d = ImageDraw.Draw(img)
    centred(d, (0, 28, w, 84), "eShop", font(56))
    centred(d, (0, 84, w, 128), "Music Changer", font(40))
    save(img, "eshop_music_512x160.jpg")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    make_square(112, "eshop_music_112x112.jpg")
    make_square(128, "eshop_music_128x128.jpg")
    make_banner()
