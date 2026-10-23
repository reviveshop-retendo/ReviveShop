"""Fallback application set used when no real firmware dump is available."""

from .model import AppEntry

DEMO_APPS = (
    ("NPXS10015", "Settings"),
    ("NPXS10008", "Content Manager"),
    ("NPXS10003", "Browser"),
    ("NPXS10013", "Photos"),
    ("NPXS10014", "Music"),
    ("NPXS10009", "Videos"),
    ("NPXS10024", "Near"),
    ("NPXS10016", "Trophies"),
    ("NPXS10011", "Friends"),
    ("NPXS10006", "Party"),
    ("NPXS10007", "Messages"),
    ("NPXS10005", "Email"),
    ("NPXS10020", "Calendar"),
    ("NPXS10030", "Welcome Park"),
    ("NPXS10031", "Remote Play"),
    ("NPXS10032", "Maps"),
    ("PCSA00001", "Demo Game"),
)


def build_demo_apps():
    return [AppEntry(tid, name, None) for tid, name in DEMO_APPS]
