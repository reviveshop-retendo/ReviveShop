"""ReviveShop Control Panel - backends.

One place to read/write the three revival stacks that live on this PC:

  3DS  -> "Default Project" (Shopdeck/ReviveShop): Django ORM + cdn/<tid>/ files
  WiiU -> ~/Documents/wiiu-stack: SOAP/Grove + titles/wup/<kind>/<tid>/ + catalog.json
  Wii  -> ~/Documents/wii-shop: WiiMart (Tomcat + Postgres in Docker)

Nothing here is console-facing; it is purely the operator's backend.
"""
import os
import re
import sys
import json
import time
import uuid
import secrets
import shutil
import socket
import threading
import subprocess
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths / constants
# --------------------------------------------------------------------------- #
PANEL_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(os.environ.get("RS_PROJECT_ROOT", PANEL_DIR.parent))

# 3DS
DS_CDN = PROJECT_ROOT / "cdn"
DS_CIAS = PROJECT_ROOT / "3ds-media" / "cias"

# Wii U
WIIU_ROOT = Path(os.environ.get("RS_WIIU_ROOT", str(Path.home() / "Documents" / "wiiu-stack")))
WIIU_TITLES = WIIU_ROOT / "SOAP" / "titles" / "wup"
WIIU_CATALOG = WIIU_ROOT / "ReviveNUSspli" / "catalog.json"
WIIU_KINDS = ["title", "patch", "aoc"]

# Wii
WII_ROOT = Path(os.environ.get("RS_WII_ROOT", str(Path.home() / "Documents" / "wii-shop")))
WII_COMPOSE = WII_ROOT / "tomcat-deploy"
WII_PG_CONTAINER = "wiimart-pg"
WII_DB = "wiisoap"
WII_DB_USER = "wiisoap"
WII_CONTAINERS = ["wiimart-pg", "wiimart-tomcat", "wiimart-dns"]

PORTS = {
    "3ds-ecs": 8000,
    "3ds-ninja": 9000,
    "3ds-proxy": 8888,
    "wiiu-soap": 7001,
    "wiiu-grove": 7100,
    "wii-tomcat": 443,
}

LOG_DIR = Path("/tmp/opencode")


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def run(cmd, cwd=None, timeout=120):
    """Run a command, return (ok, combined_output)."""
    try:
        p = subprocess.run(
            cmd, cwd=str(cwd) if cwd else None,
            capture_output=True, text=True, timeout=timeout,
        )
        return p.returncode == 0, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError as e:
        return False, f"command not found: {e}"
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s: {' '.join(cmd)}"


def port_open(port, host="127.0.0.1"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((host, int(port))) == 0


def tail(path, lines=40):
    p = Path(path)
    if not p.is_file():
        return f"(no log at {p})"
    try:
        data = p.read_text(errors="replace").splitlines()
        return "\n".join(data[-lines:]) or "(empty)"
    except Exception as e:
        return f"(could not read {p}: {e})"


def human_size(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024


# --------------------------------------------------------------------------- #
# Django ORM bootstrapping (3DS data lives in the ReviveShop Django DB)
# --------------------------------------------------------------------------- #
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shopdeck.settings")

try:
    import django
    django.setup()
    from shopdeckdb import models as m
    DJANGO_READY = True
    DJANGO_ERROR = ""
except Exception as e:  # pragma: no cover
    DJANGO_READY = False
    DJANGO_ERROR = str(e)


# =========================================================================== #
# 3DS
# =========================================================================== #
def ds_counts():
    if not DJANGO_READY:
        return {}
    return {
        "titles": m.Title.objects.count(),
        "news": m.announcement.objects.count(),
        "videos": m.movie.objects.count(),
        "categories": m.category.objects.count(),
        "consoles": m.Client3DS.objects.count(),
    }


def ds_list_news():
    return list(m.announcement.objects.order_by("-date"))


def ds_get_news(pk):
    return m.announcement.objects.get(pk=pk)


def _parse_dt(value):
    value = (value or "").strip()
    if not value:
        return None
    from datetime import datetime
    from django.utils import timezone
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


def ds_save_news(pk, title, content, is_banner, banner_url,
                 publish_date=None, expire_date=None):
    obj = m.announcement.objects.get(pk=pk) if pk else m.announcement()
    obj.title = title
    obj.content = content
    obj.is_banner = bool(is_banner)
    obj.banner_url = banner_url or ""
    obj.publish_date = _parse_dt(publish_date)
    obj.expire_date = _parse_dt(expire_date)
    obj.save()
    return obj


def ds_delete_news(pk):
    m.announcement.objects.filter(pk=pk).delete()


# --- Home Menu SpotPass notifications ------------------------------------- #
SPOTPASS_DIR = PROJECT_ROOT / "spotpass"


def ds_list_spotpass():
    return list(m.spotpassMessage.objects.order_by("-date"))


def ds_get_spotpass(pk):
    return m.spotpassMessage.objects.get(pk=pk)


def ds_save_spotpass(pk, title, message, image_url):
    obj = m.spotpassMessage.objects.get(pk=pk) if pk else m.spotpassMessage()
    obj.title = title
    obj.message = message
    obj.image_url = image_url or ""
    obj.save()
    return obj


def ds_delete_spotpass(pk):
    obj = m.spotpassMessage.objects.filter(pk=pk).first()
    if obj and obj.enabled:
        ds_unpublish_spotpass()
    m.spotpassMessage.objects.filter(pk=pk).delete()


def ds_publish_spotpass(pk):
    import hashlib
    obj = m.spotpassMessage.objects.get(pk=pk)
    m.spotpassMessage.objects.all().update(enabled=False)
    obj.enabled = True
    obj.save()
    SPOTPASS_DIR.mkdir(parents=True, exist_ok=True)
    image_name = ""
    if obj.image_url:
        base = os.path.basename(obj.image_url.split("?")[0])
        src = ASSET_DIR / base
        if src.is_file():
            image_name = "notification" + src.suffix.lower()
            shutil.copyfile(src, SPOTPASS_DIR / image_name)
    digest = hashlib.sha256((obj.title + "\u0000" + obj.message).encode()).digest()
    data = {
        "id": obj.id,
        "title": obj.title,
        "message": obj.message,
        "image": image_name,
        "url": "",
        "enabled": True,
        "serial": int.from_bytes(digest[:8], "big"),
        "ns_data_id": 0x1000 + (int.from_bytes(digest[8:10], "big") % 0x8000),
    }
    with open(SPOTPASS_DIR / "current.json", "w") as f:
        json.dump(data, f, indent=2)
    return obj


def ds_unpublish_spotpass():
    m.spotpassMessage.objects.all().update(enabled=False)
    try:
        (SPOTPASS_DIR / "current.json").unlink()
    except OSError:
        pass


def ds_list_movies():
    return list(m.movie.objects.order_by("-date"))


def ds_get_movie(pk):
    return m.movie.objects.get(pk=pk)


def ds_save_movie(pk, data):
    obj = m.movie.objects.get(pk=pk) if pk else m.movie()
    for f in ("name", "thumbnail_url", "banner_url", "moflex_url"):
        setattr(obj, f, data.get(f, "") or "")
    obj.is_3d = bool(data.get("is_3d"))
    obj.new = bool(data.get("new"))
    obj.time_in_sec = int(data.get("time_in_sec") or 0)
    obj.price = int(data.get("price") or 0)
    obj.public = bool(data.get("public"))
    obj.description = data.get("description") or ""
    if data.get("date"):
        obj.date = data["date"]
    cat = data.get("category")
    obj.category_id = int(cat) if cat else None
    obj.save()
    return obj


def ds_delete_movie(pk):
    m.movie.objects.filter(pk=pk).delete()


def ds_list_titles():
    return list(m.Title.objects.select_related("publisher", "genre", "platform", "category").order_by("-date"))


def ds_get_title(pk):
    return m.Title.objects.get(pk=pk)


def ds_save_title(pk, data):
    obj = m.Title.objects.get(pk=pk) if pk else m.Title()
    obj.tid = (data.get("tid") or "").strip().lower()
    obj.name = (data.get("name") or "").strip()
    obj.desc = data.get("desc") or ""
    obj.thumbnail_url = data.get("thumbnail_url") or ""
    obj.icon_url = data.get("icon_url") or ""
    obj.banner_url = data.get("banner_url") or ""
    obj.product_code = data.get("product_code") or ""
    obj.new = bool(data.get("new"))
    obj.public = bool(data.get("public"))
    obj.in_app_purchase = bool(data.get("in_app_purchase"))
    obj.is_not_downloadable = bool(data.get("is_not_downloadable"))
    obj.retail_sales = bool(data.get("retail_sales"))
    obj.ticket_available = bool(data.get("ticket_available"))
    obj.price = int(data.get("price") or 0)
    obj.version = int(data.get("version") or 1024)
    obj.size = int(data.get("size") or 0)
    if data.get("date"):
        obj.date = data["date"]
    obj.publisher_id = int(data["publisher"]) if data.get("publisher") else None
    obj.genre_id = int(data["genre"]) if data.get("genre") else None
    obj.platform_id = int(data["platform"]) if data.get("platform") else None
    obj.category_id = int(data["category"]) if data.get("category") else None
    obj.save()
    return obj


def ds_delete_title(pk):
    m.Title.objects.filter(pk=pk).delete()


# --------------------------------------------------------------------------- #
# Ratings (Vote rows written by the console's "Rate this title" screen)
# --------------------------------------------------------------------------- #
def ds_rating_rows():
    """Per-title vote stats, most-loved first."""
    votes = list(m.Vote.objects.select_related("voted_title", "client"))
    by_title = {}
    for v in votes:
        by_title.setdefault(v.voted_title_id, []).append(v)
    rows = []
    for t in m.Title.objects.select_related("publisher").order_by("name"):
        tvs = by_title.get(t.id, [])
        stars = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        total_score = 0
        for v in tvs:
            try:
                s = int(float(v.q3))
            except (TypeError, ValueError):
                continue
            if 1 <= s <= 5:
                stars[s] += 1
                total_score += s
        n = sum(stars.values())
        avg = round(total_score / n, 2) if n else 0
        rows.append({"title": t, "votes": tvs, "count": n,
                     "avg": avg, "stars": [stars[i] for i in range(1, 6)]})
    rows.sort(key=lambda r: (-r["avg"], -r["count"], (r["title"].name or "").lower()))
    return rows


def ds_delete_vote(pk):
    m.Vote.objects.filter(pk=pk).delete()


def ds_clear_title_votes(title_pk):
    return m.Vote.objects.filter(voted_title_id=title_pk).delete()[0]


def ds_clear_all_votes():
    return m.Vote.objects.all().delete()[0]


# --------------------------------------------------------------------------- #
# Title images (top image + upper/lower screenshot pairs shown on the title
# detail page in the eShop). Lists are stored " \ "-separated like other
# shopdeck forks; the panel edits them as one URL per line.
# --------------------------------------------------------------------------- #
_IMG_SEP = r" \ "


def ds_split_imgs(raw):
    return [u.strip() for u in (raw or "").split(_IMG_SEP) if u.strip()]


def ds_title_images(pk):
    t = m.Title.objects.get(pk=pk)
    return {
        "title": t,
        "top": t.top_image_url or "",
        "upper": ds_split_imgs(t.screenshot_upper_url),
        "lower": ds_split_imgs(t.screenshot_lower_url),
        "merged": ds_split_imgs(t.screenshot_merged_url),
    }


def ds_save_title_images(pk, top, upper_lines, lower_lines):
    t = m.Title.objects.get(pk=pk)
    t.top_image_url = (top or "").strip()
    t.screenshot_upper_url = _IMG_SEP.join(
        u.strip() for u in (upper_lines or "").splitlines() if u.strip())
    t.screenshot_lower_url = _IMG_SEP.join(
        u.strip() for u in (lower_lines or "").splitlines() if u.strip())
    t.save()
    return t


def ds_titles_image_counts():
    """{title_pk: (n_upper, n_lower, has_top)} for the list view."""
    out = {}
    for t in m.Title.objects.all():
        out[t.id] = (len(ds_split_imgs(t.screenshot_upper_url)),
                     len(ds_split_imgs(t.screenshot_lower_url)),
                     bool(t.top_image_url))
    return out


def _new_ticket_id():
    """Same shape the shop hands out when a title is bought/redeemed."""
    return (b"\x00\x04" + os.urandom(6)).hex()


def ds_owned_map():
    """{title_pk: {console_pk: ticketid}} for every existing entitlement."""
    out = {}
    for row in m.ownedTitle.objects.select_related("title", "owner"):
        out.setdefault(row.title_id, {})[row.owner_id] = row.ticketid
    return out


def ds_set_title_owned(title_pk, console_pk, owned):
    """Grant or revoke one title for one console.

    console_pk may be the string "all" to apply to every registered console,
    which is the usual case when there is only one 3DS on the network.
    """
    title = m.Title.objects.get(pk=title_pk)
    if console_pk in (None, "", "all"):
        targets = list(m.Client3DS.objects.all())
    else:
        targets = [m.Client3DS.objects.get(pk=int(console_pk))]

    changed = 0
    for ds in targets:
        if owned:
            row, created = m.ownedTitle.objects.get_or_create(
                title=title, owner=ds,
                defaults={"ticketid": _new_ticket_id(), "version": title.version},
            )
            if not created and row.version != title.version:
                row.version = title.version
                row.save()
            changed += 1
        else:
            changed += m.ownedTitle.objects.filter(title=title, owner=ds).delete()[0]
    return changed


def ds_owned_count(title_pk):
    return m.ownedTitle.objects.filter(title_id=title_pk).count()


def ds_list_lookup(model_name):
    return list(getattr(m, model_name).objects.order_by("id"))


def ds_save_lookup(model_name, pk, data):
    model = getattr(m, model_name)
    obj = model.objects.get(pk=pk) if pk else model()
    id_field = model._meta.pk.name
    if not pk and data.get(id_field):
        obj.pk = int(data[id_field])
    for field in model._meta.fields:
        name = field.name
        if name == "id" or not field.editable:
            continue
        if name in data:
            val = data.get(name)
            if hasattr(field, "choices") and field.choices:
                setattr(obj, name, val)
            else:
                setattr(obj, name, val)
    obj.save()
    return obj


def ds_delete_lookup(model_name, pk):
    getattr(m, model_name).objects.filter(pk=pk).delete()


def ds_list_consoles():
    return list(m.Client3DS.objects.order_by("id"))


def ds_get_console(pk):
    return m.Client3DS.objects.get(pk=pk)


def ds_fund_console(pk, amount, mode="add"):
    """Top up (mode='add') or directly set (mode='set') a console's balance."""
    obj = m.Client3DS.objects.get(pk=pk)
    amount = int(amount)
    if mode == "set":
        obj.balance = amount
    else:
        obj.balance = obj.balance + amount
    obj.save()
    return obj


def ds_list_cards():
    return list(m.redeemableCard.objects.order_by("-id"))


def ds_get_card(pk):
    return m.redeemableCard.objects.get(pk=pk)


# eShop download codes never contain I, O or Z (they read them as 1/0/2 on the
# console's on-screen keyboard), so generated codes must avoid them too.
CARD_CODE_ALPHABET = "0123456789ABCDEFGHJKLMNPQRSTUVWXY"


def gen_card_code(length=16):
    return "".join(secrets.choice(CARD_CODE_ALPHABET) for _ in range(length))


def ds_create_card(code, content, is_money=True):
    code = (code or "").strip().upper()
    if not code:
        code = gen_card_code()
    bad = sorted(set(code) - set(CARD_CODE_ALPHABET))
    if bad:
        raise ValueError("code cannot use " + " ".join(bad) + " (eShop excludes I, O, Z)")
    content = str(content).strip()
    if not content:
        raise ValueError("a value is required" if is_money else "pick a title")
    if m.redeemableCard.objects.filter(code=code).exists():
        raise ValueError(f"a card with code {code} already exists")
    return m.redeemableCard.objects.create(
        code=code, content=content, is_money=bool(is_money), used=False)


def ds_delete_card(pk):
    m.redeemableCard.objects.filter(pk=pk).delete()


def ds_title_names_by_tid():
    """Map a 16-char title id (what a download card stores) to a title name."""
    return {t.tid: t.name for t in m.Title.objects.all()}


def ds_esh_link(tid):
    """ESHOP:// deep link the 3DS camera accepts for a title, or None."""
    t = m.Title.objects.filter(tid__iexact=tid).first()
    if not t:
        return None
    return "ESHOP://%d" % m.title_content_id(t.id)


def ds_list_accounts():
    return list(m.RtAccount.objects.order_by("-created"))


def ds_list_links():
    return list(m.RtConsoleLink.objects.select_related("account", "console")
                .order_by("-linked"))


def ds_create_account(user_id, password, email="", mii_name=""):
    from django.contrib.auth.hashers import make_password
    from django.db.models import Max
    user_id = (user_id or "").strip()
    if not user_id:
        raise ValueError("a user ID is required")
    if not password:
        raise ValueError("a password is required")
    if m.RtAccount.objects.filter(user_id__iexact=user_id).exists():
        raise ValueError(f"account {user_id} already exists")
    top = m.RtAccount.objects.aggregate(x=Max("pid"))["x"] or 1000000000
    return m.RtAccount.objects.create(
        user_id=user_id, email=email or "",
        password=make_password(password), pid=top + 1,
        mii_name=mii_name or user_id,
    )


def ds_set_account_password(pk, password):
    from django.contrib.auth.hashers import make_password
    if not password:
        raise ValueError("a password is required")
    a = m.RtAccount.objects.get(pk=pk)
    a.password = make_password(password)
    a.save()
    return a


def ds_delete_account(pk):
    m.RtAccount.objects.filter(pk=pk).delete()


def ds_link_console(account_pk, console_pk):
    a = m.RtAccount.objects.get(pk=account_pk)
    c = m.Client3DS.objects.get(pk=console_pk)
    link, _ = m.RtConsoleLink.objects.get_or_create(account=a, console=c)
    return link


def ds_delete_link(pk):
    m.RtConsoleLink.objects.filter(pk=pk).delete()


def ds_account_tokens(pk):
    return list(m.RtToken.objects.filter(account_id=pk))


def web_base_url():
    """Base URL of the Django web UI, where /ecommerce/add lives."""
    override = os.environ.get("RS_WEB_BASE_URL")
    if override:
        return override.rstrip("/")
    return "https://%s:%d" % (lan_ip(), PORTS["3ds-ninja"])


def redeem_code_url(code):
    """URL a phone hits when it scans a card's QR (web redemption page)."""
    from urllib.parse import quote
    return "%s/ecommerce/add?card=%s" % (web_base_url(), quote(code))


def qr_png(data, scale=6, border=2):
    """Render `data` as a QR code PNG (bytes)."""
    import io
    import segno
    qr = segno.make(data, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=scale, border=border)
    return buf.getvalue()


def ds_rows(model_name, fields):
    """Generic row dump for simple lookup tables."""
    out = []
    for obj in ds_list_lookup(model_name):
        out.append({f: getattr(obj, f, "") for f in fields})
    return out


def _tmd_version(tmd: bytes) -> int:
    sig_type = int.from_bytes(tmd[0:4], "big")
    header = {0x00010003: 0x240, 0x00010004: 0x140, 0x00010005: 0x80}.get(sig_type, 0x140)
    return int.from_bytes(tmd[header + 0x9C: header + 0x9E], "big")


# --------------------------------------------------------------------------- #
# CIA library: keep uploaded CIAs and attach one to the store
# --------------------------------------------------------------------------- #
def _tmd_matching(tmd_bytes, chunk_info):
    """Rebuild a TMD so it actually describes the bytes we are going to serve.

    Repacked CIAs routinely ship a TMD whose chunk hashes no longer match their
    own content; the console verifies every downloaded chunk against the TMD, so
    serving such a TMD fails no matter how good the transfer is. chunk_info is
    [(content_id, size, sha256), ...] in TMD chunk-record order.
    """
    import io
    from hashlib import sha256
    from pyctr.type.tmd import TitleMetadataReader

    meta = TitleMetadataReader.load(io.BytesIO(tmd_bytes), verify_hashes=False)
    chunks = [cr._replace(id=cid, size=size, hash=digest)
              for cr, (cid, size, digest) in zip(meta.chunk_records, chunk_info)]
    meta.chunk_records = tuple(chunks)
    meta.content_count = len(chunks)
    if meta.info_records:
        meta.info_records = (meta.info_records[0]._replace(
            index_offset=0, command_count=len(chunks),
            hash=sha256(b"".join(bytes(c) for c in chunks)).digest()),)
    return bytes(meta)


def cia_store(upload_stream, original_name):
    """Keep an uploaded CIA so it can be attached later."""
    DS_CIAS.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.\- ]", "_", original_name).strip() or "upload.cia"
    dest = DS_CIAS / safe
    if dest.exists():
        n = 1
        while (DS_CIAS / ("%s (%d).cia" % (dest.stem, n))).exists():
            n += 1
        dest = DS_CIAS / ("%s (%d).cia" % (dest.stem, n))
    with open(dest, "wb") as f:
        shutil.copyfileobj(upload_stream, f, length=1024 * 1024)
    return dest


def cia_meta(path):
    """Cheap header read: identity and content list, no hashing."""
    from pyctr.type.cia import CIAReader

    c = CIAReader(str(path))
    recs = c.tmd.chunk_records
    size = os.path.getsize(path)
    return {
        "name": os.path.basename(path),
        "path": str(path),
        "size": size,
        "human": human_size(size),
        "tid": str(c.tmd.title_id),
        "version": str(c.tmd.title_version),
        "title_version": str(c.tmd.title_version),
        "contents": [{"id": r.id, "size": r.size, "human": human_size(r.size)}
                     for r in recs],
    }


def cdn_state_for_tid(tid):
    """What is currently extracted for a title, for the title form."""
    d = DS_CDN / str(tid)
    if not d.is_dir():
        return None
    files, total = {}, 0
    for f in sorted(d.iterdir()):
        if f.is_file():
            files[f.name] = f.stat().st_size
            total += f.stat().st_size
    return {
        "files": files,
        "total": total,
        "human": human_size(total),
        "apps": [n for n in files if n.endswith(".app")],
        "has_tmd": "tmd.bin" in files,
        "has_tik": "title.tik" in files,
        "path": str(d),
    }


def cia_list():
    out = []
    if not DS_CIAS.is_dir():
        return out
    for p in sorted(DS_CIAS.glob("*.cia")):
        try:
            out.append(cia_meta(p))
        except Exception as e:
            out.append({"name": p.name, "path": str(p),
                        "size": os.path.getsize(p),
                        "human": human_size(os.path.getsize(p)),
                        "error": str(e)})
    return out


def cia_delete(name):
    (DS_CIAS / os.path.basename(name)).unlink()


def cia_verify(name):
    """Hash a stored CIA's content and report whether its own TMD agrees."""
    from hashlib import sha256
    from pyctr.type.cia import CIAReader

    path = DS_CIAS / os.path.basename(name)
    c = CIAReader(str(path))
    with open(path, "rb") as raw:
        rows, ok = [], True
        for cr in c.tmd.chunk_records:
            r = c.sections[cr.cindex]
            raw.seek(r.offset)
            h, left = sha256(), r.size
            while left > 0:
                b = raw.read(min(1 << 20, left))
                if not b:
                    break
                h.update(b)
                left -= len(b)
            match = (left == 0 and h.digest() == cr.hash and r.size == cr.size)
            ok = ok and match
            rows.append({"id": cr.id, "size": r.size, "match": match,
                         "tmd_hash": cr.hash.hex(), "real_hash": h.hexdigest()})
    return {"name": os.path.basename(name), "ok": ok, "contents": rows}


def cia_attach(name, title_pk=None):
    """Extract a stored CIA into cdn/<tid>/ so the eShop can really download it.

    Writes the real ticket, the real encrypted content, and a TMD rebuilt to
    match those bytes. Returns a report dict.
    """
    from hashlib import sha256
    from pyctr.type.cia import CIAReader, CIASection

    path = DS_CIAS / os.path.basename(name)
    c = CIAReader(str(path))
    tid = str(c.tmd.title_id)
    dest = DS_CDN / tid
    dest.mkdir(parents=True, exist_ok=True)

    info, stale, total = [], [], 0
    with open(path, "rb") as raw:
        for cr in c.tmd.chunk_records:
            r = c.sections[cr.cindex]
            raw.seek(r.offset)
            h, left = sha256(), r.size
            with open(dest / ("%s.app" % cr.id), "wb") as of:
                while left > 0:
                    b = raw.read(min(1 << 20, left))
                    if not b:
                        break
                    of.write(b)
                    h.update(b)
                    total += len(b)
                    left -= len(b)
            size = r.size - left
            info.append((cr.id, size, h.digest()))
            if h.digest() != cr.hash or size != cr.size:
                stale.append(cr.id)

        r = c.sections[CIASection.Ticket]
        raw.seek(r.offset)
        ticket = raw.read(r.size)
        (dest / "title.tik").write_bytes(ticket)

        r = c.sections[CIASection.TitleMetadata]
        raw.seek(r.offset)
        tmd_bytes = raw.read(r.size)

    (dest / "tmd.bin").write_bytes(_tmd_matching(tmd_bytes, info))

    from pyctr.type.tmd import TitleMetadataReader
    with open(dest / "tmd.bin", "rb") as fh:
        check = TitleMetadataReader.load(fh, verify_hashes=True)

    version = _tmd_version(tmd_bytes) or 1024

    product_code, display = "", ""
    try:
        ncch = c.contents[c.tmd.chunk_records[0].cindex]
        product_code = getattr(ncch, "product_code", "") or ""
        try:
            i = ncch.exefs.icon.get_app_title()
            display = i.short_desc or i.long_desc or ""
        except Exception:
            pass
    except Exception:
        pass

    obj = None
    if title_pk:
        obj = m.Title.objects.filter(pk=title_pk).first()
        if obj is not None and str(obj.tid).lower() != tid.lower():
            obj = None
    if obj is None:
        obj = (m.Title.objects.filter(tid__iexact=tid).first()
               or m.Title(tid=tid))
    obj.version = version
    obj.size = total
    obj.public = True
    if not obj.name:
        obj.name = (display or os.path.basename(path))[:25]
    if obj.product_code is None:
        obj.product_code = product_code
    if obj.publisher_id is None:
        pub = m.publisher.objects.first()
        if pub:
            obj.publisher = pub
    if obj.genre_id is None:
        g = m.genre.objects.first()
        if g:
            obj.genre = g
    if obj.platform_id is None:
        pl = m.platform.objects.filter(id=10).first() or m.platform.objects.first()
        if pl:
            obj.platform = pl
    obj.save()

    return {
        "tid": tid,
        "version": version,
        "title": obj.name,
        "contents": [{"id": cid, "size": size} for cid, size, _ in info],
        "total": total,
        "human": human_size(total),
        "ticket": len(ticket),
        "stale": stale,
        "verified": str(check.title_id) == tid.lower(),
        "product_code": product_code,
        "path": str(dest),
    }


def ds_import_cia(upload_stream, original_name):
    """Ingest a CIA via the library, so the TMD always matches the content.

    Returns (title_obj, report_dict).
    """
    stored = cia_store(upload_stream, original_name)
    rep = cia_attach(stored.name)
    obj = m.Title.objects.filter(tid__iexact=rep["tid"]).first()
    if obj is not None and not obj.desc:
        obj.desc = "Imported from %s" % stored.name
        obj.save()
    report = {
        "tid": rep["tid"],
        "version": rep["version"],
        "contents": [c["id"] for c in rep["contents"]],
        "size": rep["total"],
        "human": rep["human"],
        "product_code": rep.get("product_code", ""),
        "stale": rep["stale"],
        "verified": rep["verified"],
        "stored": stored.name,
        "path": rep["path"],
    }
    return obj, report


def ds_cdn_titles():
    """List cdn/<tid>/ folders and their files."""
    out = []
    if not DS_CDN.is_dir():
        return out
    for d in sorted(DS_CDN.iterdir()):
        if not d.is_dir():
            continue
        files = []
        total = 0
        for f in sorted(d.iterdir()):
            if f.is_file():
                sz = f.stat().st_size
                total += sz
                files.append({"name": f.name, "size": sz, "human": human_size(sz)})
        out.append({"tid": d.name, "path": str(d), "files": files, "total": total,
                    "human": human_size(total)})
    return out


# =========================================================================== #
# Wii U
# =========================================================================== #
def wiiu_titles():
    """List {kind: [{tid, files:[...]}]}."""
    result = {k: [] for k in WIIU_KINDS}
    for kind in WIIU_KINDS:
        base = WIIU_TITLES / kind
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            if not d.is_dir():
                continue
            files = []
            total = 0
            for f in sorted(d.iterdir()):
                if f.is_file():
                    sz = f.stat().st_size
                    total += sz
                    files.append({"name": f.name, "size": sz, "human": human_size(sz)})
            result[kind].append({"tid": d.name, "files": files, "total": total,
                                 "human": human_size(total)})
    return result


def wiiu_title_detail(kind, tid):
    base = WIIU_TITLES / kind / tid
    if not base.is_dir():
        return None
    files = []
    for f in sorted(base.iterdir()):
        if f.is_file():
            files.append({"name": f.name, "size": f.stat().st_size, "human": human_size(f.stat().st_size)})
    return {"kind": kind, "tid": tid, "path": str(base), "files": files}


def wiiu_create_title(kind, tid):
    tid = re.sub(r"[^0-9A-Fa-f]", "", tid).lower()
    if len(tid) != 16:
        raise ValueError("title id must be 16 hex chars")
    if kind not in WIIU_KINDS:
        raise ValueError("bad kind")
    d = WIIU_TITLES / kind / tid
    d.mkdir(parents=True, exist_ok=True)
    return d


def wiiu_delete_title(kind, tid):
    d = WIIU_TITLES / kind / tid
    if d.is_dir():
        shutil.rmtree(d)


def wiiu_save_upload(kind, tid, files):
    d = WIIU_TITLES / kind / tid
    d.mkdir(parents=True, exist_ok=True)
    saved = []
    for f in files:
        if not f or not f.filename:
            continue
        name = os.path.basename(f.filename)
        f.save(str(d / name))
        saved.append(name)
    return saved


def wiiu_delete_file(kind, tid, name):
    name = os.path.basename(name)
    p = WIIU_TITLES / kind / tid / name
    if p.is_file():
        p.unlink()


def wiiu_catalog():
    if WIIU_CATALOG.is_file():
        try:
            return json.loads(WIIU_CATALOG.read_text())
        except Exception:
            return []
    return []


def wiiu_catalog_add(tid, name):
    data = wiiu_catalog()
    data = [e for e in data if e.get("tid") != tid]
    data.append({"tid": tid.lower(), "name": name})
    WIIU_CATALOG.write_text(json.dumps(data, indent=2))
    return data


def wiiu_catalog_remove(tid):
    data = [e for e in wiiu_catalog() if e.get("tid") != tid]
    WIIU_CATALOG.write_text(json.dumps(data, indent=2))
    return data


def wiiu_control(action):
    return run([str(WIIU_ROOT / "start-wiiu.sh"), action], cwd=WIIU_ROOT)


# =========================================================================== #
# Wii (WiiMart)
# =========================================================================== #
def _psql(sql, timeout=30):
    try:
        p = subprocess.run(
            ["docker", "exec", "-i", WII_PG_CONTAINER, "psql", "-U", WII_DB_USER, "-d", WII_DB, "-tAF", "|"],
            input=sql, capture_output=True, text=True, timeout=timeout,
        )
        return p.returncode == 0, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return False, str(e)


def wii_available():
    return port_open(5432)


def wii_query_rows(sql):
    """Return list of dicts, splitting psql '|' output. Needs '\\pset' friendly SQL."""
    ok, out = _psql(sql)
    if not ok:
        return [{"error": out.strip()}]
    rows = []
    lines = [ln for ln in out.splitlines() if ln and not ln.startswith("(")]
    header = None
    # We instead rely on explicit column order from the caller; return raw lines.
    return lines


def wii_titles():
    # service_titles: item_id, price_code, price, title_id, reference_id
    ok, out = _psql("SELECT item_id, price_code, price, title_id, coalesce(reference_id,'') FROM service_titles ORDER BY item_id;")
    rows = []
    if ok:
        for ln in out.splitlines():
            if not ln.strip():
                continue
            parts = ln.split("|")
            if len(parts) >= 5:
                rows.append({"item_id": parts[0], "price_code": parts[1], "price": parts[2],
                             "title_id": parts[3], "reference_id": parts[4]})
    return rows


def wii_save_title(item_id, price_code, price, title_id, reference_id):
    ref = reference_id or None
    ref_sql = "NULL" if ref is None else "'" + ref.replace("'", "''") + "'"
    if item_id:
        sql = (f"UPDATE service_titles SET price_code={int(price_code)}, price={int(price)}, "
               f"title_id='{title_id}', reference_id={ref_sql} WHERE item_id={int(item_id)};")
    else:
        sql = (f"INSERT INTO service_titles (price_code, price, title_id, reference_id) "
               f"VALUES ({int(price_code)}, {int(price)}, '{title_id}', {ref_sql});")
    return _psql(sql)


def wii_delete_title(item_id):
    return _psql(f"DELETE FROM service_titles WHERE item_id={int(item_id)};")


def wii_accounts():
    ok, out = _psql("SELECT account_id, device_id, coalesce(region,''), coalesce(country,''), coalesce(points,'0') FROM userbase ORDER BY account_id;")
    rows = []
    if ok:
        for ln in out.splitlines():
            if not ln.strip():
                continue
            parts = ln.split("|")
            if len(parts) >= 5:
                rows.append({"account_id": parts[0], "device_id": parts[1], "region": parts[2],
                             "country": parts[3], "points": parts[4]})
    return rows


def wii_owned():
    ok, out = _psql("SELECT account_id, title_id, coalesce(version,0) FROM owned_titles ORDER BY account_id;")
    rows = []
    if ok:
        for ln in out.splitlines():
            if not ln.strip():
                continue
            parts = ln.split("|")
            if len(parts) >= 3:
                rows.append({"account_id": parts[0], "title_id": parts[1], "version": parts[2]})
    return rows


def wii_control(action):
    if action == "start":
        ok, out = run(["docker", "start", *WII_CONTAINERS], timeout=180)
    elif action == "stop":
        ok, out = run(["docker", "stop", *WII_CONTAINERS], timeout=180)
    elif action == "restart":
        run(["docker", "stop", *WII_CONTAINERS], timeout=180)
        ok, out = run(["docker", "start", *WII_CONTAINERS], timeout=180)
    else:
        return False, "unknown action"
    return ok, out


def wii_containers():
    ok, out = run(["docker", "ps", "-a", "--format", "{{.Names}}|{{.Status}}|{{.Image}}"], timeout=30)
    rows = []
    if ok:
        for ln in out.splitlines():
            parts = ln.split("|")
            if len(parts) == 3:
                rows.append({"name": parts[0], "status": parts[1], "image": parts[2]})
    return rows


# =========================================================================== #
# Service status / control for all stacks
# =========================================================================== #
def all_status():
    return {
        "3ds": {
            "ecs(flask:8000)": port_open(PORTS["3ds-ecs"]),
            "ninja(django:9000)": port_open(PORTS["3ds-ninja"]),
            "proxy(mitm:8888)": port_open(PORTS["3ds-proxy"]),
        },
        "wiiu": {
            "soap(:7001)": port_open(PORTS["wiiu-soap"]),
            "grove(:7100)": port_open(PORTS["wiiu-grove"]),
        },
        "wii": {
            "tomcat(:443)": port_open(PORTS["wii-tomcat"]),
            "postgres(:5432)": port_open(5432),
        },
    }


def stack_control(stack, action):
    if stack == "3ds":
        if action == "start":
            return run([str(PROJECT_ROOT / "dev-up.sh")], cwd=PROJECT_ROOT, timeout=120)
        if action == "stop":
            cmd = ["pkill", "-f", "runserver_plus 0.0.0.0:9000"]
            run(cmd)
            run(["pkill", "-f", "flask --app main run"])
            run(["pkill", "-f", "mitmdump --listen-port 8888"])
            return True, "stopped 3DS stack"
        return False, "unknown action"
    if stack == "wiiu":
        return wiiu_control(action)
    if stack == "wii":
        return wii_control(action)
    return False, "unknown stack"


# =========================================================================== #
# Maintenance toggle (reviveshop/settings.py -> IN_MAINTENANCE)
# =========================================================================== #
SETTINGS_PY = PROJECT_ROOT / "reviveshop" / "settings.py"
_MAINT_RE = re.compile(r"^IN_MAINTENANCE\s*=\s*(True|False)", re.M)


def maintenance_status():
    """Return True if IN_MAINTENANCE is on, False otherwise (or on error)."""
    try:
        m = _MAINT_RE.search(SETTINGS_PY.read_text(encoding="utf-8"))
        return m is not None and m.group(1) == "True"
    except Exception:
        return False


def set_maintenance(enabled):
    """Rewrite the IN_MAINTENANCE = True/False line in settings.py."""
    try:
        text = SETTINGS_PY.read_text(encoding="utf-8")
    except Exception as e:
        return False, f"cannot read {SETTINGS_PY}: {e}"
    if not _MAINT_RE.search(text):
        return False, "IN_MAINTENANCE line not found in settings.py"
    new_text = _MAINT_RE.sub(
        f"IN_MAINTENANCE = {'True' if enabled else 'False'}", text, count=1
    )
    if new_text == text:
        return True, "already set"
    try:
        SETTINGS_PY.write_text(new_text, encoding="utf-8")
    except Exception as e:
        return False, f"cannot write {SETTINGS_PY}: {e}"
    return True, f"IN_MAINTENANCE = {'True' if enabled else 'False'}"


def logs():
    files = {
        "3ds-ecs": LOG_DIR / "rs-dev" / "flask.log",
        "3ds-ninja": LOG_DIR / "rs-dev" / "django.log",
        "3ds-proxy": LOG_DIR / "rs-dev" / "mitm.log",
        "wiiu-soap": LOG_DIR / "soap.log",
        "wiiu-grove": LOG_DIR / "grove.log",
    }
    return {name: tail(path, 60) for name, path in files.items()}


# =========================================================================== #
# Image / asset hosting
#
# Uploaded files are written into the project's asset CDN folder, which the
# 3DS ECS Flask server (assetcdn.py) already serves at
#     https://<lan-ip>:8000/assets/<name>
# so a returned URL can be stored directly in thumbnail_url / banner_url /
# icon_url and the console will fetch it.
# =========================================================================== #
ASSET_DIR = PROJECT_ROOT / "assetcdn"
ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico"}
ASSET_FLASK_PORT = 8000


def lan_ip():
    override = os.environ.get("RS_SERVER_IP")
    if override:
        return override
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("1.1.1.1", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def asset_base_url():
    """Base URL the *consoles* use to fetch assets (served by the 3DS ECS)."""
    override = os.environ.get("RS_ASSET_BASE_URL")
    if override:
        return override if override.endswith("/") else override + "/"
    return "https://%s:%d/assets/" % (lan_ip(), ASSET_FLASK_PORT)


def save_asset(stream, original_name):
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in ALLOWED_IMAGE_EXT:
        raise ValueError(f"unsupported image type '{ext}' (allowed: {', '.join(sorted(ALLOWED_IMAGE_EXT))})")
    stem = re.sub(r"[^A-Za-z0-9._-]", "_",
                  os.path.splitext(os.path.basename(original_name))[0]).strip("._")[:40] or "image"
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    name, i = f"{stem}{ext}", 1
    while (ASSET_DIR / name).exists():
        name = f"{stem}_{i}{ext}"
        i += 1
    with open(ASSET_DIR / name, "wb") as f:
        shutil.copyfileobj(stream, f, length=1024 * 1024)
    return name, asset_base_url() + name


def list_assets():
    out = []
    if ASSET_DIR.is_dir():
        for p in sorted(ASSET_DIR.iterdir()):
            if p.is_file():
                sz = p.stat().st_size
                out.append({
                    "name": p.name, "size": sz, "human": human_size(sz),
                    "url": asset_base_url() + p.name, "ext": p.suffix.lower(),
                })
    return out


def delete_asset(name):
    p = ASSET_DIR / os.path.basename(name)
    if p.is_file():
        p.unlink()
        return True
    return False


# --------------------------------------------------------------------------- #
# eShop videos (.moflex)
#
# NOTE: MOFLEX is Nintendo's proprietary Mobiclip container. There is no free
# encoder: ffmpeg can only *read* it (demux), and the only writer is Nintendo's
# licensed "Mobiclip Multicore Encoder". So this hosts an existing .moflex (and
# reads its duration), and can also stage a normal video into an encoder-ready
# 400x240 clip. It cannot produce a playable .moflex by itself.
# --------------------------------------------------------------------------- #
ALLOWED_VIDEO_EXT = {".moflex", ".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}


def video_duration(path):
    ok, out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                   "-of", "default=nw=1:nk=1", str(path)], timeout=60)
    if ok and out.strip():
        try:
            return int(round(float(out.strip().splitlines()[-1])))
        except ValueError:
            return None
    return None


def save_video(stream, original_name):
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in ALLOWED_VIDEO_EXT:
        raise ValueError(f"unsupported video type '{ext}' "
                         f"(allowed: {', '.join(sorted(ALLOWED_VIDEO_EXT))})")
    stem = re.sub(r"[^A-Za-z0-9._-]", "_",
                  os.path.splitext(os.path.basename(original_name))[0]).strip("._")[:40] or "video"
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    name, i = f"{stem}{ext}", 1
    while (ASSET_DIR / name).exists():
        name = f"{stem}_{i}{ext}"
        i += 1
    dest = ASSET_DIR / name
    with open(dest, "wb") as f:
        shutil.copyfileobj(stream, f, length=4 * 1024 * 1024)
    return {
        "name": name, "url": asset_base_url() + name, "path": str(dest),
        "duration": video_duration(dest), "is_moflex": ext == ".moflex",
        "human": human_size(dest.stat().st_size),
    }


def prepare_video(name, is_3d=False):
    """Transcode a hosted video into an encoder-ready clip (400x240, or
    400x480 for 3D) for the Mobiclip Multicore Encoder."""
    src = ASSET_DIR / os.path.basename(name)
    if not src.is_file():
        raise ValueError("source video not found")
    w, h = (400, 480) if is_3d else (400, 240)
    out = src.with_name(src.stem + "_mme.mp4")
    cmd = ["ffmpeg", "-y", "-i", str(src),
           "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                  f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
           str(out)]
    ok, log = run(cmd, timeout=7200)
    if not ok:
        raise RuntimeError("ffmpeg failed: " + log[-400:])
    return out.name, human_size(out.stat().st_size)


# --------------------------------------------------------------------------- #
# MOFLEX encoding (3DS eShop videos)
#
# Uses "mobipeg" (https://github.com/quatric/mobipeg) - an OSS FFmpeg fork with
# a real MobiClip encoder + moflex muxer. Installed under tools/mobipeg/.
# --------------------------------------------------------------------------- #
MOBIPEG = PROJECT_ROOT / "tools" / "mobipeg"
MOBIPEG_FFMPEG = MOBIPEG / "ffmpeg"
MOBIPEG_FFPROBE = MOBIPEG / "ffprobe"

MOFLEX_LAYOUTS = {
    "2d":     {"scale": "400:240", "mo_layout": "6", "label": "2D (400x240)"},
    "3d_sbs": {"scale": "800:240", "mo_layout": "4", "label": "3D side-by-side (800x240)"},
    "3d_tb":  {"scale": "400:480", "mo_layout": "2", "label": "3D top-bottom (400x480)"},
}
MOFLEX_QUALITY = {"high": 16, "normal": 22, "small": 28}

_convert_jobs = {}
_convert_lock = threading.Lock()


def moflex_available():
    return MOBIPEG_FFMPEG.is_file() and os.access(str(MOBIPEG_FFMPEG), os.X_OK)


def get_moflex_job(job_id):
    with _convert_lock:
        return dict(_convert_jobs.get(job_id) or {}) or None


def _run_moflex_job(job_id, src_path, out_name, layout, quality):
    job = _convert_jobs[job_id]
    try:
        L = MOFLEX_LAYOUTS.get(layout) or MOFLEX_LAYOUTS["2d"]
        qp = MOFLEX_QUALITY.get(quality, 22)
        out = ASSET_DIR / out_name
        src_secs = video_duration(src_path)
        cmd = [str(MOBIPEG_FFMPEG), "-hide_banner", "-loglevel", "error", "-y",
               "-i", str(src_path),
               "-vf", f"scale={L['scale']}",
               "-c:v", "mobiclip", "-pix_fmt", "yuv420p", "-qp", str(qp),
               "-c:a", "pcm_s16le", "-mo_audio", "adpcm",
               "-mo_layout", L["mo_layout"], str(out)]
        with _convert_lock:
            job["status"] = "running"
            job["message"] = f"Encoding {layout} at QP {qp}..."
        ok, log = run(cmd, timeout=14400)
        if not ok or not out.is_file() or out.stat().st_size == 0:
            raise RuntimeError(log.strip()[-600:] or "mobipeg produced no output")
        with _convert_lock:
            job.update(status="done", message="Encoded",
                       name=out.name, url=asset_base_url() + out.name,
                       duration=src_secs or video_duration(out),
                       human=human_size(out.stat().st_size))
    except Exception as e:
        with _convert_lock:
            job.update(status="error", message="Failed", error=str(e))
    finally:
        try:
            os.unlink(src_path)
        except OSError:
            pass
        with _convert_lock:
            job["finished"] = time.time()


def start_moflex_job(stream, original_name, layout="2d", quality="normal"):
    if not moflex_available():
        raise RuntimeError(
            "mobipeg not installed. Put its ffmpeg/ffprobe in tools/mobipeg/.")
    layout = layout if layout in MOFLEX_LAYOUTS else "2d"
    quality = quality if quality in MOFLEX_QUALITY else "normal"
    stem = re.sub(r"[^A-Za-z0-9._-]", "_",
                  os.path.splitext(os.path.basename(original_name))[0]).strip("._")[:40] or "video"
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    out_name, i = f"{stem}.moflex", 1
    while (ASSET_DIR / out_name).exists():
        out_name = f"{stem}_{i}.moflex"
        i += 1
    tmp_dir = PROJECT_ROOT / "tools" / "_convert"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    src = tmp_dir / f"{uuid.uuid4().hex}_{stem}"
    with open(src, "wb") as f:
        shutil.copyfileobj(stream, f, length=4 * 1024 * 1024)
    job_id = uuid.uuid4().hex[:12]
    with _convert_lock:
        _convert_jobs[job_id] = {
            "id": job_id, "status": "queued", "message": "Queued",
            "started": time.time(), "finished": None, "layout": layout,
            "quality": quality, "error": None,
        }
    t = threading.Thread(target=_run_moflex_job,
                         args=(job_id, str(src), out_name, layout, quality),
                         daemon=True)
    t.start()
    return get_moflex_job(job_id)


# --------------------------------------------------------------------------- #
# Image resizer
# --------------------------------------------------------------------------- #
IMAGE_PRESETS = {
    "cat_icon":     (128, 96,  "Category icon"),
    "cat_banner":   (512, 160, "Category banner"),
    "title_icon":   (128, 128, "Title icon"),
    "title_thumb":  (112, 112, "Title thumbnail"),
    "title_banner": (512, 160, "Title banner"),
    "movie_thumb":  (128, 96,  "Video thumbnail"),
    "movie_banner": (512, 160, "Video banner"),
    "news_banner":  (300, 126, "News banner"),
    "spotpass_image": (400, 240, "SpotPass image"),
    "home_icon":    (48, 48,   "Home Menu icon"),
}


def _parse_color(value, default=(0, 0, 0)):
    value = (value or "").strip().lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    if len(value) == 6:
        try:
            return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
        except ValueError:
            pass
    return default + (255,)


def resize_image(stream, original_name, width, height, mode="cover",
                 bg="#000000", fmt="png", quality=90):
    """Resize/convert an uploaded image to an eShop asset size.

    mode: 'cover' (fill + centre-crop), 'contain' (fit + pad with bg), 'stretch'.
    """
    from PIL import Image
    tw, th = max(1, int(width)), max(1, int(height))
    img = Image.open(stream).convert("RGBA")
    if mode == "stretch":
        out = img.resize((tw, th), Image.LANCZOS)
    elif mode == "contain":
        fitted = img.copy()
        fitted.thumbnail((tw, th), Image.LANCZOS)
        out = Image.new("RGBA", (tw, th), _parse_color(bg))
        out.paste(fitted, ((tw - fitted.width) // 2, (th - fitted.height) // 2), fitted)
    else:  # cover
        ratio = max(tw / img.width, th / img.height)
        nw, nh = max(tw, round(img.width * ratio)), max(th, round(img.height * ratio))
        resized = img.resize((nw, nh), Image.LANCZOS)
        left, top = (nw - tw) // 2, (nh - th) // 2
        out = resized.crop((left, top, left + tw, top + th))
    stem = re.sub(r"[^A-Za-z0-9._-]", "_",
                  os.path.splitext(os.path.basename(original_name))[0]).strip("._")[:40] or "image"
    ext = "jpg" if str(fmt).lower() in ("jpg", "jpeg") else "png"
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    name, i = f"{stem}_{tw}x{th}.{ext}", 1
    while (ASSET_DIR / name).exists():
        name = f"{stem}_{tw}x{th}_{i}.{ext}"
        i += 1
    dest = ASSET_DIR / name
    out = out.convert("RGB")
    if ext == "jpg":
        out.save(dest, "JPEG", quality=int(quality), optimize=True)
    else:
        out.save(dest, "PNG", optimize=True)
    return {"name": name, "url": asset_base_url() + name,
            "size": f"{tw}x{th}", "human": human_size(dest.stat().st_size)}


# --------------------------------------------------------------------------- #
# eShop background music (BOSS/npdl BGM)
#
# The 3DS pulls BGM from the npdl SpotPass endpoint (npdl.py). Tracks live in
# bgm/tracks/ as ADTS AAC (32 kHz stereo) with metadata.json describing the
# calendar window each track is valid for. npdl plays the newest track whose
# begin date has been reached ("current") and offers the next one as BGM2.
# --------------------------------------------------------------------------- #
BGM_TRACKS_DIR = PROJECT_ROOT / "bgm" / "tracks"
BGM_META = BGM_TRACKS_DIR / "metadata.json"
BGM_ALLOWED_EXT = {".mp3", ".aac", ".m4a", ".wav", ".flac", ".ogg", ".opus", ".wma"}
BGM_SAMPLE_RATE = 32000
BGM_FRAME_SAMPLES = 1024


def bgm_available():
    ok, _ = run(["ffmpeg", "-version"], timeout=15)
    return ok


def _bgm_read_meta():
    if not BGM_META.is_file():
        return []
    try:
        data = json.loads(BGM_META.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _bgm_write_meta(entries):
    BGM_TRACKS_DIR.mkdir(parents=True, exist_ok=True)
    BGM_META.write_text(json.dumps(entries, indent=2))


def _bgm_adts_frames(data: bytes) -> int:
    i = n = 0
    while i + 7 <= len(data) and data[i] == 0xFF and (data[i + 1] & 0xF6) == 0xF0:
        length = ((data[i + 3] & 0x3) << 11) | (data[i + 4] << 3) | (data[i + 5] >> 5)
        if length <= 0:
            break
        i += length
        n += 1
    return n


def _bgm_valid_date(s):
    try:
        time.strptime(s, "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False


def bgm_pick(entries):
    """Mirror npdl.py: return (current_entry, next_entry) by calendar."""
    if not entries:
        return None, None
    ordered = sorted(entries, key=lambda e: e.get("begin", "2000-01-01"))
    today = time.strftime("%Y-%m-%d")
    cur = 0
    for i, e in enumerate(ordered):
        if e.get("begin", "") <= today:
            cur = i
    nxt = ordered[cur]
    for j in range(cur + 1, len(ordered)):
        if ordered[j].get("begin", "") > ordered[cur].get("begin", ""):
            nxt = ordered[j]
            break
    return ordered[cur], nxt


def bgm_list():
    entries = _bgm_read_meta()
    cur, nxt = bgm_pick(entries)
    cur_f = cur.get("file") if cur else None
    nxt_f = nxt.get("file") if nxt else None
    out = []
    for e in entries:
        p = BGM_TRACKS_DIR / e.get("file", "")
        sz = p.stat().st_size if p.is_file() else 0
        out.append({
            "file": e.get("file", ""), "name": e.get("name", ""),
            "begin": e.get("begin", ""), "data_size": e.get("data_size", sz),
            "loop_end_frame": e.get("loop_end_frame", 0),
            "size": sz, "human": human_size(sz), "exists": p.is_file(),
            "is_current": e.get("file") == cur_f,
            "is_next": e.get("file") == nxt_f and e.get("file") != cur_f,
        })
    out.sort(key=lambda e: (e.get("begin", ""), e.get("file", "")))
    return out


def bgm_save(file, name="", begin=""):
    entries = _bgm_read_meta()
    hit = next((e for e in entries if e.get("file") == file), None)
    if hit is None:
        raise ValueError("track not found")
    if name:
        hit["name"] = name
    if begin:
        if not _bgm_valid_date(begin):
            raise ValueError("begin must be YYYY-MM-DD")
        hit["begin"] = begin
    _bgm_write_meta(entries)
    return hit


def bgm_delete(file):
    entries = _bgm_read_meta()
    hit = next((e for e in entries if e.get("file") == file), None)
    if hit is None:
        return False
    _bgm_write_meta([e for e in entries if e.get("file") != file])
    base = os.path.basename(file)
    p = BGM_TRACKS_DIR / base
    try:
        if p.is_file():
            p.unlink()
    except OSError:
        pass
    if base.startswith("track_") and base.endswith(".aac"):
        stem = base[len("track_"):-len(".aac")]
        for extra in BGM_TRACKS_DIR.glob(f"src_{stem}.*"):
            try:
                extra.unlink()
            except OSError:
                pass
    return True


def bgm_add(stream, original_name, name="", begin=""):
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in BGM_ALLOWED_EXT:
        raise ValueError(f"unsupported audio type '{ext}' "
                         f"(allowed: {', '.join(sorted(BGM_ALLOWED_EXT))})")
    if not bgm_available():
        raise RuntimeError("ffmpeg is required to convert tracks")
    stem = re.sub(r"[^A-Za-z0-9._-]", "_",
                  os.path.splitext(os.path.basename(original_name))[0]).strip("._")[:40] or "track"
    BGM_TRACKS_DIR.mkdir(parents=True, exist_ok=True)
    base, i = stem, 1
    while ((BGM_TRACKS_DIR / f"track_{base}.aac").exists()
           or (BGM_TRACKS_DIR / f"src_{base}{ext}").exists()):
        i += 1
        base = f"{stem}_{i}"
    src = BGM_TRACKS_DIR / f"src_{base}{ext}"
    with open(src, "wb") as f:
        shutil.copyfileobj(stream, f, length=1024 * 1024)
    out = BGM_TRACKS_DIR / f"track_{base}.aac"
    ok, log = run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
                   "-ar", str(BGM_SAMPLE_RATE), "-ac", "2", "-c:a", "aac", "-b:a", "128k",
                   "-f", "adts", str(out)], timeout=1800)
    if not ok or not out.is_file() or out.stat().st_size == 0:
        try:
            src.unlink()
        except OSError:
            pass
        raise RuntimeError("ffmpeg failed: " + log.strip()[-400:])
    data = out.read_bytes()
    entry = {
        "file": out.name,
        "name": name or os.path.splitext(os.path.basename(original_name))[0],
        "begin": begin if _bgm_valid_date(begin) else time.strftime("%Y-%m-%d"),
        "data_size": len(data),
        "sample_rate": BGM_SAMPLE_RATE,
        "loop_end_frame": _bgm_adts_frames(data) * BGM_FRAME_SAMPLES,
    }
    entries = [e for e in _bgm_read_meta() if e.get("file") != out.name]
    entries.append(entry)
    _bgm_write_meta(entries)
    return entry
