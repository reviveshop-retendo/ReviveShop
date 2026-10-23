"""Generate category icon/banner art in the same house style as the existing
cat_icon_*_v2 / cat_banner_*_v2 files.

House style (sampled from the shipped art):
  * vertical gradient, bright hue at the top fading to a dark base at the bottom
  * centred bold white label text
  * icon  128x96, banner 512x160, saved as quality-90 RGB JPEG

Run:
    .venv/bin/python make_cat_art.py
"""
import os

from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
OUT = "assetcdn"

# (id, label, top colour, bottom colour) - each category gets its own hue.
# Existing reference points: 1 = gold->blue, 2 = gold->red, 4 = cyan->purple.
CATEGORIES = [
    (5, "Video And Chatting", (255, 120, 62), (86, 14, 74)),
]

ASSETS = "https://192.168.4.34:8000/assets/"


def _font_for(draw, text, max_w, max_h, start):
    size = start
    while size > 8:
        font = ImageFont.truetype(FONT, size)
        box = draw.textbbox((0, 0), text, font=font)
        if (box[2] - box[0]) <= max_w and (box[3] - box[1]) <= max_h:
            return font
        size -= 2
    return ImageFont.load_default()


def vertical_gradient(w, h, top, bottom):
    """Bright at the top, dark at the bottom - matches the shipped banners."""
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        # ease so the bright band sits in the top third, like the existing art
        e = t ** 0.85
        row = tuple(int(round(top[i] + (bottom[i] - top[i]) * e)) for i in range(3))
        for x in range(w):
            px[x, y] = row
    return img


def tile(fname, w, h, top, bottom, label):
    img = vertical_gradient(w, h, top, bottom)
    d = ImageDraw.Draw(img)
    # wrap long labels onto two lines so "Video And Chatting" stays legible
    words = label.split()
    lines = [label]
    if w < 300 and len(words) > 2:
        mid = (len(words) + 1) // 2
        lines = [" ".join(words[:mid]), " ".join(words[mid:])]

    if len(lines) == 1:
        font = _font_for(d, label, int(w * 0.88), int(h * 0.72), int(h * 0.62))
        box = d.textbbox((0, 0), label, font=font)
        tw, th = box[2] - box[0], box[3] - box[1]
        d.text(((w - tw) / 2 - box[0], (h - th) / 2 - box[1]), label,
               fill=(255, 255, 255), font=font)
    else:
        font = _font_for(d, lines[0], int(w * 0.9), int(h * 0.42), int(h * 0.38))
        boxes = [d.textbbox((0, 0), ln, font=font) for ln in lines]
        heights = [b[3] - b[1] for b in boxes]
        gap = 2
        total = sum(heights) + gap
        y = (h - total) / 2
        for ln, b, lh in zip(lines, boxes, heights):
            tw = b[2] - b[0]
            d.text(((w - tw) / 2 - b[0], y - b[1]), ln,
                   fill=(255, 255, 255), font=font)
            y += lh + gap

    img.save(os.path.join(OUT, fname), "JPEG", quality=90)
    return ASSETS + fname


def main():
    os.makedirs(OUT, exist_ok=True)
    for cid, label, top, bottom in CATEGORIES:
        icon = tile("cat_icon_%d_v2.jpg" % cid, 128, 96, top, bottom, label)
        banner = tile("cat_banner_%d_v2.jpg" % cid, 512, 160, top, bottom, label)
        print("category %d: %s" % (cid, label))
        print("  icon   :", icon)
        print("  banner :", banner)


if __name__ == "__main__":
    main()
