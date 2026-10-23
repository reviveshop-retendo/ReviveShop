"""Screen geometry, grid layout and default palette for the LiveArea shell."""

SCREEN_W = 960
SCREEN_H = 544

INFO_BAR_H = 40

GRID_COLS = 4
GRID_ROWS = 2
PER_PAGE = GRID_COLS * GRID_ROWS

BUBBLE_D = 148
BUBBLE_GAP_X = 34
BUBBLE_GAP_Y = 26
BUBBLE_LABEL_H = 30

GRID_TOP_Y = 108

MAX_PAGES = 10

TARGET_FPS = 60

VITA_MOUNTS = ("ux0", "ur0", "vs0", "os0", "app0", "gro0", "grw0", "tm0", "imc0", "xmc0")

SYSTEM_TITLE_PREFIX = "NPXS"

PALETTE = {
    "bg_top": (24, 26, 56),
    "bg_bottom": (12, 13, 30),
    "bg_wave": (46, 52, 104),
    "info_text": (235, 238, 248),
    "info_dim": (150, 156, 184),
    "bubble_sheen": (255, 255, 255, 92),
    "bubble_ring": (255, 255, 255, 46),
    "bubble_shadow": (0, 0, 0, 120),
    "label_text": (236, 239, 250),
    "dot_active": (245, 247, 255),
    "dot_inactive": (245, 247, 255, 96),
    "livearea_paper": (243, 244, 249),
    "gate_fill": (255, 255, 255),
    "gate_text": (34, 38, 60),
}
