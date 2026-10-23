"""Locate and read a decrypted PS Vita filesystem dump (vs0/ur0/ux0 ...)."""

import re
import sqlite3
from pathlib import Path

from . import config
from .model import AppEntry
from .sfo import parse_file as parse_sfo
from .template import parse_file as parse_template

TITLE_ID_RE = re.compile(r"^[A-Z]{4}\d{5}$")

MOUNT_PRIORITY = {
    "ux0": 0,
    "ur0": 1,
    "imc0": 2,
    "xmc0": 3,
    "vs0": 4,
    "app0": 5,
    "os0": 6,
}


class VitaDump:
    def __init__(self, root):
        self.root = Path(root).expanduser()
        if not self.root.exists():
            raise FileNotFoundError(f"dump path not found: {self.root}")

        self.mounts = {}
        for mount in config.VITA_MOUNTS:
            d = self.root / mount
            if d.is_dir():
                self.mounts[mount] = d

        if not self.mounts and (self.root / "app").is_dir():
            self.mounts[self.root.name or "vs0"] = self.root

    @property
    def available(self):
        return bool(self.mounts)

    def resolve(self, uri):
        if ":" in uri:
            mount, _, rest = uri.partition(":")
            base = self.mounts.get(mount)
            if base is not None:
                candidate = base / rest.lstrip("/")
                if candidate.exists():
                    return candidate
        rel = uri.split(":", 1)[-1].lstrip("/")
        for mount in sorted(self.mounts, key=lambda m: MOUNT_PRIORITY.get(m, 99)):
            candidate = self.mounts[mount] / rel
            if candidate.exists():
                return candidate
        return None

    def _app_db(self):
        for candidate in (
            self.resolve("ur0:shell/db/app.db"),
            self.root / "shell" / "db" / "app.db",
        ):
            if candidate and Path(candidate).is_file():
                return Path(candidate)
        return None

    def read_app_order(self):
        path = self._app_db()
        if path is None:
            return []
        try:
            con = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
        except Exception:
            return []
        try:
            cur = con.cursor()
            tables = {r[0] for r in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            table = next((t for t in ("tbl_appinfo", "appinfo") if t in tables), None)
            if table is None:
                return []
            order, seen = [], set()
            for row in cur.execute(f"SELECT * FROM {table}"):
                for value in row:
                    if isinstance(value, str) and TITLE_ID_RE.match(value) and value not in seen:
                        seen.add(value)
                        order.append(value)
            return order
        except Exception:
            return []
        finally:
            con.close()

    def _appmeta_index(self):
        index = {}
        for base in self.mounts.values():
            am = base / "appmeta"
            if not am.is_dir():
                continue
            for d in am.iterdir():
                if d.is_dir():
                    index.setdefault(d.name.upper(), d)
        return index

    def _icon_for(self, app_dir, appmeta, tid, name):
        candidates = []
        if tid in appmeta:
            candidates.append(appmeta[tid] / name)
        candidates.append(app_dir / "sce_sys" / name)
        for c in candidates:
            if c.is_file():
                return c
        return None

    def _livearea_dir(self, app_dir, appmeta, tid):
        candidates = []
        if tid in appmeta:
            candidates.append(appmeta[tid] / "livearea" / "contents")
            candidates.append(appmeta[tid] / "contents")
        candidates.append(app_dir / "sce_sys" / "livearea" / "contents")
        for c in candidates:
            if (c / "template.xml").is_file() or c.is_dir():
                return c
        return None

    def scan_apps(self):
        appmeta = self._appmeta_index()
        found = {}

        for mount, base in self.mounts.items():
            app_root = base / "app"
            if not app_root.is_dir():
                continue
            for app_dir in sorted(app_root.iterdir()):
                sfo = app_dir / "sce_sys" / "param.sfo"
                if not app_dir.is_dir() or not sfo.is_file():
                    continue
                try:
                    info = parse_sfo(sfo)
                except Exception:
                    continue
                tid = (info.get("TITLE_ID") or app_dir.name).upper()
                title = info.get("TITLE") or tid

                entry = AppEntry(
                    title_id=tid,
                    title=title,
                    app_dir=app_dir,
                    icon_path=self._icon_for(app_dir, appmeta, tid, "icon0.png"),
                    livearea_dir=self._livearea_dir(app_dir, appmeta, tid),
                    pic0_path=self._icon_for(app_dir, appmeta, tid, "pic0.png"),
                    mount=mount,
                )

                rank = MOUNT_PRIORITY.get(mount, 99)
                if tid not in found or rank < found[tid][0]:
                    found[tid] = (rank, entry)

        apps = [entry for _, entry in found.values()]
        order = self.read_app_order()
        if order:
            rank = {tid: i for i, tid in enumerate(order)}
            apps.sort(key=lambda a: (rank.get(a.title_id, 1 << 30),
                                     not a.is_system, a.title.lower(), a.title_id))
        else:
            apps.sort(key=lambda a: (not a.is_system, a.title.lower(), a.title_id))
        return apps

    def load_livearea(self, app):
        if app.livearea is not None or app.livearea_dir is None:
            return app.livearea
        template = Path(app.livearea_dir) / "template.xml"
        if template.is_file():
            try:
                app.livearea = parse_template(template)
                app.livearea.livearea_dir = str(app.livearea_dir)
            except Exception:
                app.livearea = None
        return app.livearea
