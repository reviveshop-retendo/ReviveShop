"""In-memory model of the home screen: applications, bubbles and pages."""

from . import config


class AppEntry:
    def __init__(self, title_id, title, app_dir, icon_path=None,
                 livearea_dir=None, pic0_path=None, mount=None):
        self.title_id = title_id
        self.title = title or title_id
        self.app_dir = app_dir
        self.icon_path = icon_path
        self.livearea_dir = livearea_dir
        self.pic0_path = pic0_path
        self.mount = mount
        self.livearea = None
        self.icon = None
        self.page = None
        self.slot = None

    @property
    def is_system(self):
        return self.title_id.startswith(config.SYSTEM_TITLE_PREFIX)

    def __repr__(self):
        return f"<AppEntry {self.title_id} {self.title!r}>"


class Bubble:
    def __init__(self, app, col, row):
        self.app = app
        self.col = col
        self.row = row
        self.x = 0
        self.y = 0
        self.w = config.BUBBLE_D
        self.h = config.BUBBLE_D + config.BUBBLE_LABEL_H

    def contains(self, px, py):
        cx = self.x + self.w / 2
        cy = self.y + self.w / 2
        r = self.w / 2
        return (px - cx) ** 2 + (py - cy) ** 2 <= r * r


def _grid_origin():
    total_w = config.GRID_COLS * config.BUBBLE_D + (config.GRID_COLS - 1) * config.BUBBLE_GAP_X
    left = (config.SCREEN_W - total_w) // 2
    return left, config.GRID_TOP_Y


def layout_page(apps):
    left, top = _grid_origin()
    bubbles = []
    for idx, app in enumerate(apps):
        col = idx % config.GRID_COLS
        row = idx // config.GRID_COLS
        b = Bubble(app, col, row)
        b.x = left + col * (config.BUBBLE_D + config.BUBBLE_GAP_X)
        b.y = top + row * (config.BUBBLE_D + config.BUBBLE_GAP_Y + config.BUBBLE_LABEL_H)
        bubbles.append(b)
    return bubbles


class HomeModel:
    def __init__(self, apps):
        self.apps = list(apps)
        self.pages = []
        for i in range(0, len(self.apps), config.PER_PAGE):
            chunk = self.apps[i:i + config.PER_PAGE]
            for slot, app in enumerate(chunk):
                app.page = len(self.pages)
                app.slot = slot
            self.pages.append(layout_page(chunk))
        if not self.pages:
            self.pages.append([])

    def __len__(self):
        return len(self.pages)

    def page(self, index):
        return self.pages[index % len(self.pages)]
