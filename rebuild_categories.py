"""Rebuild the shop category set so it mirrors Universal-DB's installable
(CIA-capable) categories, and regenerate all category art in the house style.

Universal-DB 3DS taxonomy is:
    Games, Emulators, Apps, Utilities, Plugins, FIRMs, Exploits,
    Multimedia, Save Tools
Plugins / FIRMs / Exploits are not installable CIAs, so they are omitted -
they would be permanently empty shelves in the eShop.

Resulting set (order controls the on-console sequence):
    All Games            (standard, always first)
    Games
    Emulators
    Apps
    Utilities
    Multimedia
    Save Tools
    ReviveShop Selects

"Videos" is renamed to Multimedia and absorbs "Video And Chatting".

Run:
    .venv/bin/python rebuild_categories.py
"""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "reviveshop.settings")
import django

django.setup()

from datetime import date  # noqa: E402

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from shopdeckdb.models import Title, category  # noqa: E402

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
OUT = "assetcdn"
ASSETS = "https://192.168.4.34:8000/assets/"

# (name, order, icon_top_rgb, icon_bottom_rgb)
# Hues chosen to be distinct from each other and from the existing art.
LAYOUT = [
    ("All Games",          -1, (255, 213, 62), (12, 40, 113)),   # existing gold->blue
    ("Games",               1, (120, 220, 90), (10, 70, 30)),    # green
    ("Emulators",           3, (90, 140, 255), (16, 24, 96)),    # blue
    ("Apps",                5, (255, 130, 190), (96, 12, 72)),   # pink
    ("Utilities",           7, (200, 200, 210), (44, 48, 62)),   # graphite
    ("Multimedia",          9, (255, 120, 62), (86, 14, 74)),    # orange->plum (was cat 5)
    ("Save Tools",         11, (255, 205, 90), (110, 60, 10)),   # amber
    ("ReviveShop Selects", 13, (91, 229, 255), (58, 12, 111)),   # existing cyan->purple
]


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
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        e = t ** 0.85
        row = tuple(int(round(top[i] + (bottom[i] - top[i]) * e)) for i in range(3))
        for x in range(w):
            px[x, y] = row
    return img


def tile(fname, w, h, top, bottom, label):
    img = vertical_gradient(w, h, top, bottom)
    d = ImageDraw.Draw(img)
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
        y = (h - (sum(heights) + gap)) / 2
        for ln, b, lh in zip(lines, boxes, heights):
            tw = b[2] - b[0]
            d.text(((w - tw) / 2 - b[0], y - b[1]), ln, fill=(255, 255, 255), font=font)
            y += lh + gap

    img.save(os.path.join(OUT, fname), "JPEG", quality=90)
    return ASSETS + fname


def slug(name):
    return name.lower().replace(" ", "_")


def main():
    os.makedirs(OUT, exist_ok=True)

    # 1. Rename Videos -> Multimedia so the 4 existing movies keep their shelf.
    vids = category.objects.filter(name="Videos").first()
    if vids:
        vids.name = "Multimedia"
        vids.save()
        print(f"  renamed category {vids.id}: Videos -> Multimedia")

    # 2. Retire 'Video And Chatting' (id 5) after moving its titles out.
    vac = category.objects.filter(name="Video And Chatting").first()
    if vac:
        moved = list(Title.objects.filter(category=vac))
        target = category.objects.get(name="Multimedia")
        for t in moved:
            t.category = target
            t.save()
            print(f"  moved title {t.name!r} -> Multimedia")
        if not Title.objects.filter(category=vac).exists():
            vac.delete()
            print(f"  deleted emptied category {vac.id} 'Video And Chatting'")

    # 3. Create / update every category in the layout with fresh art.
    for name, order, top, bottom in LAYOUT:
        fname_icon = f"cat_icon_{slug(name)}.jpg"
        fname_banner = f"cat_banner_{slug(name)}.jpg"
        icon = tile(fname_icon, 128, 96, top, bottom, name)
        banner = tile(fname_banner, 512, 160, top, bottom, name)

        existing = category.objects.filter(name=name).first()
        if existing:
            existing.order = order
            existing.icon_url = icon
            existing.banner_url = banner
            existing.save()
            print(f"  updated  id={existing.id:<3} order={order:<3} {name}")
        else:
            last = category.objects.order_by("-id").first()
            new_id = (last.id if last else 0) + 1
            category.objects.create(
                id=new_id, name=name, order=order, index=0, standard=False,
                new=True, icon_url=icon, banner_url=banner,
            )
            print(f"  created  id={new_id:<3} order={order:<3} {name}")

    # 4. 'All Games' must stay the standard/first entry.
    ag = category.objects.get(name="All Games")
    ag.standard = True
    ag.order = -1
    ag.save()

    print("\n=== FINAL ===")
    for c in category.objects.all().order_by("order"):
        n = Title.objects.filter(category=c).count()
        print(f"  order={c.order:<3} id={c.id:<3} {c.name!r:<22} titles={n} std={c.standard}")


if __name__ == "__main__":
    main()
