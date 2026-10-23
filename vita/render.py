"""Draws the home screen and LiveArea paper into PIL framebuffers."""

import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from . import assets, config

P = config.PALETTE

GATE_W = 300
GATE_H = 74
GATE_CX = config.SCREEN_W // 2
GATE_Y = config.SCREEN_H - 168


def gate_rect():
    return (GATE_CX - GATE_W // 2, GATE_Y, GATE_CX + GATE_W // 2, GATE_Y + GATE_H)


def peel_rect():
    return (config.SCREEN_W - 60, 0, config.SCREEN_W, 60)


def _wrap(draw, text, fnt, max_w):
    words = (text or "").split()
    lines, cur = [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=fnt) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


class Renderer:
    def __init__(self, home, theme_bg=None):
        self.home = home
        self.theme_bg = theme_bg
        self._bg = None
        self._icon_cache = {}
        self._sheen = assets.sheen(config.BUBBLE_D)
        self._shadow = self._make_shadow()

    def _make_shadow(self):
        d = config.BUBBLE_D
        shadow = Image.new("RGBA", (d + 40, d + 40), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).ellipse((18, 24, 18 + d, 24 + d), fill=(0, 0, 0, 150))
        return shadow.filter(ImageFilter.GaussianBlur(9))

    def background(self):
        if self._bg is None:
            if self.theme_bg is not None:
                self._bg = assets.cover(self.theme_bg, (config.SCREEN_W, config.SCREEN_H))
            else:
                self._bg = assets.default_background((config.SCREEN_W, config.SCREEN_H))
        return self._bg

    def icon(self, app):
        if app.title_id in self._icon_cache:
            return self._icon_cache[app.title_id]
        img = None
        if app.icon_path is not None and Path(app.icon_path).is_file():
            img = assets.circular_icon(app.icon_path, config.BUBBLE_D)
        if img is None:
            img = assets.placeholder_icon(app.title, config.BUBBLE_D)
        self._icon_cache[app.title_id] = img
        return img

    def _draw_bubble(self, frame, draw, bubble, offset_x, pressed=False):
        app = bubble.app
        d = config.BUBBLE_D
        x = bubble.x + offset_x
        y = bubble.y
        if x + d < -60 or x > config.SCREEN_W + 60:
            return

        shadow = self._shadow
        frame.alpha_composite(shadow, (int(x + d / 2 - shadow.width / 2),
                                       int(y + d / 2 - shadow.height / 2 + 4)))

        icon = self.icon(app)
        px, py = int(x), int(y)
        frame.alpha_composite(icon, (px, py))

        ring_a = 120 if pressed else P["bubble_ring"][3]
        draw.ellipse((px, py, px + d - 1, py + d - 1),
                     outline=(255, 255, 255, ring_a), width=2)

        frame.alpha_composite(self._sheen, (px, py))

        if app.title:
            fnt = assets.font(16)
            max_w = config.BUBBLE_D + config.BUBBLE_GAP_X - 12
            lines = _wrap(draw, app.title, fnt, max_w)[:2]
            ty = py + d + 4
            for i, line in enumerate(lines):
                tw = draw.textlength(line, font=fnt)
                tx = x + d / 2 - tw / 2
                draw.text((tx + 1, ty + i * 18 + 1), line, font=fnt, fill=(0, 0, 0, 150))
                draw.text((tx, ty + i * 18), line, font=fnt, fill=P["label_text"])

    def render_home(self, page_index, dx=0.0, pressed=None, now=None):
        frame = self.background().copy()
        draw = ImageDraw.Draw(frame, "RGBA")
        pages = self.home.pages
        n = len(pages)

        for i in range(n):
            x_off = int((i - page_index) * config.SCREEN_W + dx)
            if x_off <= -config.SCREEN_W or x_off >= config.SCREEN_W:
                continue
            for bubble in pages[i]:
                self._draw_bubble(frame, draw, bubble, x_off,
                                  pressed=(pressed is not None and pressed.app is bubble.app))

        self._draw_info_bar(frame, now)
        self._draw_page_dots(frame, page_index, dx)
        return frame

    def _draw_info_bar(self, frame, now=None):
        draw = ImageDraw.Draw(frame, "RGBA")
        now = now or time.localtime()
        fnt = assets.font(19)
        clock = time.strftime("%H:%M", now)
        draw.text((20, 9), clock, font=fnt, fill=P["info_text"])
        draw.text((88, 9), time.strftime("%d/%m/%Y", now), font=assets.font(15), fill=P["info_dim"])

        right = config.SCREEN_W - 24
        self._draw_battery(frame, right - 30, 14)
        self._draw_wifi(frame, right - 78, 15)
        self._draw_bell(frame, right - 122, 12, "3")

    def _draw_wifi(self, frame, x, y):
        draw = ImageDraw.Draw(frame, "RGBA")
        col = P["info_text"]
        for i, r in enumerate((6, 11, 16)):
            a = 235 - i * 20
            draw.arc((x - r, y + 14 - r, x + r, y + 14 + r), start=200, end=340,
                     fill=(col[0], col[1], col[2], a), width=3)
        draw.ellipse((x - 3, y + 11, x + 3, y + 17), fill=col)

    def _draw_battery(self, frame, x, y):
        draw = ImageDraw.Draw(frame, "RGBA")
        col = P["info_text"]
        draw.rounded_rectangle((x, y, x + 30, y + 15), radius=3, outline=col, width=2)
        draw.rectangle((x + 31, y + 5, x + 34, y + 10), fill=col)
        draw.rounded_rectangle((x + 3, y + 3, x + 24, y + 12), radius=2, fill=col)

    def _draw_bell(self, frame, x, y, count):
        draw = ImageDraw.Draw(frame, "RGBA")
        draw.rounded_rectangle((x, y, x + 32, y + 20), radius=10,
                               fill=(70, 110, 200, 220))
        fnt = assets.font(14, bold=True)
        tw = draw.textlength(count, font=fnt)
        draw.text((x + 16 - tw / 2, y + 2), count, font=fnt, fill=(255, 255, 255))

    def _draw_page_dots(self, frame, page_index, dx):
        draw = ImageDraw.Draw(frame, "RGBA")
        n = len(self.home.pages)
        if n <= 1:
            return
        spacing = 22
        total = (n - 1) * spacing
        start_x = config.SCREEN_W / 2 - total / 2
        y = config.SCREEN_H - 26
        frac = -dx / config.SCREEN_W
        for i in range(n):
            pos = i - frac
            x = start_x + pos * spacing
            active = abs(pos) < 0.5
            r = 5 if active else 4
            col = P["dot_active"] if active else P["dot_inactive"]
            draw.ellipse((x - r, y - r, x + r, y + r), fill=col)

    def render_livearea(self, app, template, progress=1.0, status=None, now=None):
        frame = Image.new("RGBA", (config.SCREEN_W, config.SCREEN_H), (0, 0, 0, 255))

        bg = None
        if template and template.background and Path(template.livearea_dir or "").is_dir():
            candidate = Path(template.livearea_dir) / template.background
            if candidate.is_file():
                bg = assets.cover(assets.load_image(candidate), (config.SCREEN_W, config.SCREEN_H))
        if bg is None and app.pic0_path and Path(app.pic0_path).is_file():
            bg = assets.cover(assets.load_image(app.pic0_path), (config.SCREEN_W, config.SCREEN_H))
        if bg is None:
            bg = assets.vertical_gradient((config.SCREEN_W, config.SCREEN_H), (78, 92, 150), (36, 42, 78)).convert("RGBA")

        frame = bg
        dim = Image.new("RGBA", frame.size, (10, 12, 26, 90))
        frame = Image.alpha_composite(frame, dim)

        self._draw_livearea_header(frame, app, template)

        gate_y = GATE_Y
        startup = None
        if template:
            for name in template.startup_images:
                candidate = Path(template.livearea_dir or "") / name
                if candidate.is_file():
                    startup = assets.contain(assets.load_image(candidate), (300, 180))
                    break
        if startup is not None:
            frame.alpha_composite(startup, (config.SCREEN_W // 2 - 150, gate_y - 190))

        label = template.gate_label if template else "Start"
        self._draw_gate(frame, config.SCREEN_W // 2, gate_y, label)

        if template and template.frames:
            self._draw_frames(frame, template)

        if status:
            draw = ImageDraw.Draw(frame, "RGBA")
            fnt = assets.font(16)
            tw = draw.textlength(status, font=fnt)
            draw.rounded_rectangle((config.SCREEN_W / 2 - tw / 2 - 16, 14,
                                    config.SCREEN_W / 2 + tw / 2 + 16, 44),
                                   radius=8, fill=(0, 0, 0, 150))
            draw.text((config.SCREEN_W / 2 - tw / 2, 20), status, font=fnt, fill=(255, 255, 255))

        self._draw_peel(frame, progress)
        return frame

    def _draw_livearea_header(self, frame, app, template):
        draw = ImageDraw.Draw(frame, "RGBA")
        icon = self.icon(app).resize((64, 64), Image.LANCZOS)
        frame.alpha_composite(icon, (30, 34))
        fnt = assets.font(24, bold=True)
        title = app.title
        draw.text((110, 42), title, font=fnt, fill=(255, 255, 255))
        draw.text((110, 74), app.title_id, font=assets.font(15), fill=(220, 226, 240, 200))

    def _draw_gate(self, frame, cx, y, label):
        draw = ImageDraw.Draw(frame, "RGBA")
        w, h = GATE_W, GATE_H
        x = cx - w / 2
        draw.rounded_rectangle((x + 2, y + 4, x + w + 2, y + h + 4), radius=37, fill=(0, 0, 0, 90))
        draw.rounded_rectangle((x, y, x + w, y + h), radius=37, fill=(255, 255, 255, 240))
        draw.polygon([(x + 40, y + 24), (x + 40, y + 50), (x + 64, y + 37)], fill=(60, 78, 130))
        fnt = assets.font(26, bold=True)
        tw = draw.textlength(label, font=fnt)
        draw.text((x + w / 2 - tw / 2 + 18, y + 22), label, font=fnt, fill=P["gate_text"])

    def _draw_frames(self, frame, template):
        draw = ImageDraw.Draw(frame, "RGBA")
        x = 640
        y = 150
        w = 280
        for frameobj in template.frames:
            if frameobj.texts:
                for text in frameobj.texts[:2]:
                    fnt = assets.font(15)
                    lines = _wrap(draw, text, fnt, w - 20)[:3]
                    box_h = len(lines) * 20 + 16
                    draw.rounded_rectangle((x, y, x + w, y + box_h), radius=10, fill=(0, 0, 0, 70))
                    for i, line in enumerate(lines):
                        draw.text((x + 10, y + 8 + i * 20), line, font=fnt, fill=(240, 243, 250))
                    y += box_h + 12
            if frameobj.targets:
                fnt = assets.font(14)
                label = frameobj.targets[0]
                label = label[:34] + ("..." if len(label) > 34 else "")
                draw.rounded_rectangle((x, y, x + w, y + 30), radius=8, fill=(90, 130, 210, 120))
                draw.text((x + 12, y + 7), label, font=fnt, fill=(255, 255, 255))
                y += 42

    def _draw_peel(self, frame, progress):
        draw = ImageDraw.Draw(frame, "RGBA")
        size = 46
        x0 = config.SCREEN_W - size
        draw.polygon([(x0, 0), (config.SCREEN_W, size), (config.SCREEN_W, 0)], fill=(255, 255, 255, 235))
        draw.polygon([(x0, 0), (config.SCREEN_W, size), (x0 + 6, size - 6)], fill=(206, 212, 226, 255))
