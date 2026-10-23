"""Entry point: python -m vita [dump_path] [options]."""

import argparse
import sys

from . import assets, config, demo, firmware
from .model import HomeModel
from .render import Renderer


def build_parser():
    parser = argparse.ArgumentParser(
        prog="vita",
        description="LiveArea home screen - rebuilds the PS Vita home screen from a "
                    "decrypted firmware dump (vs0/ur0/ux0) or an app.db.")
    parser.add_argument("dump", nargs="?", help="path to a decrypted Vita dump or app.db")
    parser.add_argument("--theme-bg", help="override home screen background image")
    parser.add_argument("--demo", action="store_true", help="force the built-in demo set")
    parser.add_argument("--scale", type=float, default=1.0, help="initial window scale")
    parser.add_argument("--list", action="store_true", help="list detected apps and exit")
    return parser


def load_apps(dump_path, force_demo):
    dump = None
    apps = []
    if dump_path and not force_demo:
        try:
            dump = firmware.VitaDump(dump_path)
            apps = dump.scan_apps()
        except Exception as exc:
            print(f"[vita] could not read dump '{dump_path}': {exc}", file=sys.stderr)
            dump = None
    if not apps:
        apps = demo.build_demo_apps()
        dump = None
    return dump, apps


def main(argv=None):
    args = build_parser().parse_args(argv)
    dump, apps = load_apps(args.dump, args.demo)

    source = dump.root if dump else "built-in demo"
    print(f"[vita] {len(apps)} applications loaded from {source}")

    if args.list:
        for app in apps:
            icon = "icon" if app.icon_path else "----"
            live = "livearea" if app.livearea_dir else "--------"
            print(f"  {app.title_id}  {icon:6}  {live:8}  {app.title}")
        return 0

    model = HomeModel(apps)
    theme_bg = assets.load_image(args.theme_bg) if args.theme_bg else None
    renderer = Renderer(model, theme_bg=theme_bg)

    import tkinter as tk
    from .app import VitaShell

    root = tk.Tk()
    root.title("LiveArea - PS Vita Home Screen")
    root.configure(bg="#000000")
    root.geometry(f"{int(config.SCREEN_W * args.scale)}x{int(config.SCREEN_H * args.scale)}")

    VitaShell(root, model, renderer, dump=dump)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
