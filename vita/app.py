"""Tk desktop shell: window, input handling and animation loop."""

import time
import tkinter as tk

from PIL import Image, ImageTk

from . import config, render

SNAP_DUR = 0.30
OPEN_DUR = 0.35


def ease_out_cubic(p):
    return 1 - (1 - p) ** 3


class VitaShell:
    def __init__(self, root, model, renderer, dump=None):
        self.root = root
        self.model = model
        self.renderer = renderer
        self.dump = dump

        self.scroll = 0.0
        self.anim = None
        self.mode = "home"
        self.current_app = None
        self.current_template = None
        self.open_t = 0.0
        self.status = None
        self.status_until = 0.0
        self.pressed = None

        self._down = None
        self._scroll_start = 0.0
        self._drag_mode = None
        self._moved = False
        self._pressed_gate = False

        self._scale = 1.0
        self._ox = 0.0
        self._oy = 0.0
        self.photo = None
        self._img_id = None
        self._dirty = True
        self._last_clock = 0.0

        self.canvas = tk.Canvas(root, highlightthickness=0, bg="#000000")
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self._go_page(-1))
        self.canvas.bind("<Button-5>", lambda e: self._go_page(1))
        self.canvas.bind("<Configure>", lambda e: self._mark_dirty())

        root.bind("<Escape>", lambda e: self._back())
        root.bind("<Left>", lambda e: self._go_page(-1))
        root.bind("<Right>", lambda e: self._go_page(1))
        root.bind("<Return>", lambda e: self._activate())
        root.bind("<space>", lambda e: self._activate())
        root.bind("<Home>", lambda e: self._start_anim("scroll", self.scroll, 0.0, SNAP_DUR))

        self.root.after(16, self._tick)

    def _mark_dirty(self):
        self._dirty = True

    def _to_vita(self, ex, ey):
        return ((ex - self._ox) / self._scale, (ey - self._oy) / self._scale)

    def _page_and_dx(self):
        w = config.SCREEN_W
        n = len(self.model.pages)
        page = int(round(self.scroll / w))
        page = max(0, min(n - 1, page))
        return page, page * w - self.scroll

    def _clamp_scroll(self, s):
        w = config.SCREEN_W
        n = len(self.model.pages)
        maxs = (n - 1) * w
        if s < 0:
            return s * 0.4
        if s > maxs:
            return maxs + (s - maxs) * 0.4
        return s

    def _start_anim(self, name, a, b, dur):
        self.anim = {"name": name, "a": a, "b": b, "t0": time.monotonic(), "dur": dur}
        self._dirty = True

    def _go_page(self, delta):
        w = config.SCREEN_W
        n = len(self.model.pages)
        page = int(round(self.scroll / w)) + delta
        page = max(0, min(n - 1, page))
        self._start_anim("scroll", self.scroll, page * w, SNAP_DUR)

    def _snap(self):
        w = config.SCREEN_W
        n = len(self.model.pages)
        target = round(self.scroll / w) * w
        target = max(0, min((n - 1) * w, target))
        self._start_anim("scroll", self.scroll, target, SNAP_DUR)

    def _hit_bubble(self, vx, vy):
        w = config.SCREEN_W
        for i, page in enumerate(self.model.pages):
            off = i * w - self.scroll
            if off <= -w or off >= w:
                continue
            for bubble in page:
                if bubble.contains(vx - off, vy):
                    return bubble
        return None

    def _open_livearea(self, app):
        self.current_app = app
        template = self.dump.load_livearea(app) if self.dump else None
        self.current_template = template
        self.mode = "livearea"
        self.open_t = 0.0
        self._start_anim("open", 0.0, 1.0, OPEN_DUR)

    def _close_livearea(self):
        self._start_anim("open", self.open_t, 0.0, OPEN_DUR)

    def _back(self):
        if self.mode == "livearea":
            self._close_livearea()

    def _activate(self):
        if self.mode == "livearea":
            self._gate_press()

    def _gate_press(self):
        if self.current_app is None:
            return
        self.status = f"Cannot start {self.current_app.title} (no OS kernel)"
        self.status_until = time.monotonic() + 2.6
        self._dirty = True

    def _on_press(self, event):
        vx, vy = self._to_vita(event.x, event.y)
        self._down = (vx, vy)
        self._moved = False
        self._pressed_gate = False
        self.pressed = None

        if self.mode == "home":
            bubble = self._hit_bubble(vx, vy)
            if bubble is not None:
                self.pressed = bubble
                self._drag_mode = "bubble"
            else:
                self._drag_mode = "page"
            self._scroll_start = self.scroll
        else:
            px0, py0, px1, py1 = render.peel_rect()
            gx0, gy0, gx1, gy1 = render.gate_rect()
            if px0 <= vx <= px1 and py0 <= vy <= py1:
                self._drag_mode = "peel"
            elif gx0 <= vx <= gx1 and gy0 <= vy <= gy1:
                self._drag_mode = "gate"
                self._pressed_gate = True
            else:
                self._drag_mode = None
        self._mark_dirty()

    def _on_motion(self, event):
        if self._down is None:
            return
        vx, vy = self._to_vita(event.x, event.y)
        dx = vx - self._down[0]
        dy = vy - self._down[1]
        if abs(dx) > 6 or abs(dy) > 6:
            self._moved = True
        if self._drag_mode == "page":
            self.scroll = self._clamp_scroll(self._scroll_start - dx)
            self._mark_dirty()

    def _on_release(self, event):
        vx, vy = self._to_vita(event.x, event.y)

        if self.mode == "home":
            if self._drag_mode == "bubble" and not self._moved and self.pressed is not None:
                self._open_livearea(self.pressed.app)
            elif self._drag_mode == "page":
                if self._moved:
                    self._snap()
                elif self._hit_bubble(vx, vy) is None:
                    pass
            self.pressed = None
        else:
            if self._drag_mode == "peel":
                self._close_livearea()
            elif self._drag_mode == "gate" and self._pressed_gate:
                gx0, gy0, gx1, gy1 = render.gate_rect()
                if gx0 <= vx <= gx1 and gy0 <= vy <= gy1:
                    self._gate_press()

        self._down = None
        self._drag_mode = None
        self._pressed_gate = False
        self._mark_dirty()

    def _on_wheel(self, event):
        self._go_page(-1 if event.delta > 0 else 1)

    def _advance_anim(self, now):
        anim = self.anim
        if anim is None:
            return
        p = (now - anim["t0"]) / anim["dur"]
        if p > 1:
            p = 1
        e = ease_out_cubic(p)
        val = anim["a"] + (anim["b"] - anim["a"]) * e

        if anim["name"] == "scroll":
            self.scroll = val
        elif anim["name"] == "open":
            self.open_t = val

        if p >= 1:
            self.anim = None
            if anim["name"] == "open" and anim["b"] <= 0.0:
                self.mode = "home"
                self.current_app = None
                self.current_template = None
        self._mark_dirty()

    def _build_frame(self):
        if self.mode == "livearea" and self.current_app is not None:
            page, dx = self._page_and_dx()
            home = self.renderer.render_home(page, dx)
            offset = int((1.0 - self.open_t) * config.SCREEN_H)
            la = self.renderer.render_livearea(
                self.current_app, self.current_template, progress=self.open_t)
            frame = home.copy()
            if offset > 0:
                frame.alpha_composite(la, (0, offset))
            else:
                frame = la
            if self.status and time.monotonic() < self.status_until:
                self._draw_status(frame)
            return frame
        page, dx = self._page_and_dx()
        return self.renderer.render_home(page, dx, pressed=self.pressed)

    def _draw_status(self, frame):
        from PIL import ImageDraw
        from . import assets
        draw = ImageDraw.Draw(frame, "RGBA")
        fnt = assets.font(16)
        tw = draw.textlength(self.status, font=fnt)
        x = config.SCREEN_W / 2 - tw / 2
        draw.rounded_rectangle((x - 18, config.SCREEN_H - 92, x + tw + 18, config.SCREEN_H - 60),
                               radius=10, fill=(0, 0, 0, 170))
        draw.text((x, config.SCREEN_H - 86), self.status, font=fnt, fill=(255, 255, 255))

    def _present(self, img):
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 2 or ch < 2:
            return
        scale = min(cw / config.SCREEN_W, ch / config.SCREEN_H)
        dw, dh = max(1, int(config.SCREEN_W * scale)), max(1, int(config.SCREEN_H * scale))
        if (dw, dh) != (config.SCREEN_W, config.SCREEN_H):
            disp = img.resize((dw, dh), Image.BILINEAR)
        else:
            disp = img
        self._scale = scale
        self._ox = (cw - dw) / 2
        self._oy = (ch - dh) / 2
        self.photo = ImageTk.PhotoImage(disp)
        if self._img_id is None:
            self._img_id = self.canvas.create_image(cw // 2, ch // 2, image=self.photo)
        else:
            self.canvas.itemconfig(self._img_id, image=self.photo)
            self.canvas.coords(self._img_id, cw // 2, ch // 2)

    def _tick(self):
        now = time.monotonic()
        if now - self._last_clock > 15.0:
            self._last_clock = now
            self._mark_dirty()
        if self.status and now >= self.status_until:
            self.status = None
            self._mark_dirty()
        if self.anim is not None:
            self._advance_anim(now)
        if self._dirty or self.anim is not None:
            self._present(self._build_frame())
            self._dirty = False
        self.root.after(16, self._tick)
