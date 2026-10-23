"""npdl BGM1/BGM2 endpoint for ReviveShop (Flask).

Serves the Nintendo 3DS eShop background music.

The 3DS pulls its music from a static SpotPass URL roughly like

    https://npdl.c.app.nintendowifi.net/p01/nsa/CtfKXACbUPl8s7lk/BGM1/<region>_BGM1

(historically behind the Akamai host a248.e.akamai.net with a
/f/248/103046/10m/npdl.c.app.nintendowifi.net prefix).  The file is a
3DS BOSS container (keyslot 0x38, AES-128-CTR): an unencrypted 0x28
header plus the encrypted content header + payload content header + the
payload.  The RSA signatures are zeroed (`0x100` bytes each) - fake-ticket
era hardware (Luma) patches those checks.  The cleartext payload is a
brief XML header describing the audio followed by the raw AAC stream; the
eShop splits it into boss_xml1/boss_bgm1 in its user save data.

The old tracks are mapped to the real calendar: the current theme is the
track whose begin date is the latest one already reached, and BGM2 is the
next one (so the September 2013 track begins Sept 21 2026 and the December
2013 one takes over Dec 1 2026).  Tracks live in bgm/tracks/*.aac (ADTS AAC, 32kHz
stereo, matching the real boss_bgm1 stream) with metadata in metadata.json.
"""

import datetime
import hashlib
import json
import os
import re
import time

from Cryptodome.Cipher import AES
from flask import Blueprint, Response, request

BGM_DIR = os.path.join(os.path.dirname(__file__), "bgm", "tracks")

BOSS_AES_KEY = bytes.fromhex("6e78a3be9bddda09bfd569483f24fce0")
BOSS_APP_ID = "CtfKXACbUPl8s7lk"
BOSS_PROGRAM_ID = 0x0004001000021900  # eShop BGM boss app registration title id
CONTENT_DATATYPE = 0x00020001         # 3dbrew: eShop BOSS task strings show 0x20001 (0x10001 is the generic "usual")
NS_DATA_ID = 0x24
VERSION = 0
LOOP_SAMPLES_PER_FRAME = 1024

# Home Menu SpotPass system notifications are delivered by the BOSS task
# "basho0" (Home Menu title 0004003000008f02).  The downloaded BOSS container
# carries a payload whose target program id is the News/Notifications sysmodule
# and is flagged MARK_ARRIVED_PRIVILEGED.  Notification layout per 3dbrew
# NEWSS:SyncArrivedNotifications: 0x20 header + 0x40 UTF-16 title (0x60 total)
# + a fixed 0x1780-byte message buffer + optional image.
NEWS_SYSMODULE_TITLE = 0x0004013000003502
NOTIF_CONTENT_DATATYPE = 0x00010001
NOTIF_NS_DATA_ID = 0x1000
SPOTPASS_DIR = os.path.join(os.path.dirname(__file__), "spotpass")
SPOTPASS_FILE = os.path.join(SPOTPASS_DIR, "current.json")

END_YEAR = 2035            # active-until; keeps the served track "current" forever

SAFE_FILENAME = re.compile(r"^[A-Za-z0-9._-]+$")


class _Tracks:
    def __init__(self):
        self.entries = []
        self.loaded = False
        self.mtime = None

    @staticmethod
    def _frames(data: bytes) -> int:
        i = 0
        n = 0
        while i + 7 <= len(data) and data[i] == 0xFF and (data[i + 1] & 0xF6) == 0xF0:
            length = ((data[i + 3] & 0x3) << 11) | (data[i + 4] << 3) | (data[i + 5] >> 5)
            i += length
            n += 1
        return n

    def load(self):
        metadata_path = os.path.join(BGM_DIR, "metadata.json")
        self.mtime = os.path.getmtime(metadata_path) if os.path.isfile(metadata_path) else None
        if not os.path.isfile(metadata_path):
            self.entries = []
            self.loaded = True
            return
        self.entries = []
        for meta in json.load(open(metadata_path)):
            path = os.path.join(BGM_DIR, meta["file"])
            if not os.path.isfile(path):
                continue
            data = open(path, "rb").read()
            self.entries.append({
                "file": meta.get("file", ""),
                "begin": meta.get("begin", "2000-01-01"),
                "data": data,
                "data_size": len(data),
                "sample_rate": meta.get("sample_rate", 32000),
                "loop_end_frame": meta.get("loop_end_frame")
                or self._frames(data) * LOOP_SAMPLES_PER_FRAME,
            })
        self.entries.sort(key=lambda e: e["begin"])
        self.loaded = True

    def _maybe_reload(self):
        metadata_path = os.path.join(BGM_DIR, "metadata.json")
        mtime = os.path.getmtime(metadata_path) if os.path.isfile(metadata_path) else None
        if not self.loaded or mtime != self.mtime:
            self.load()

    def pick(self, offset: int) -> dict:
        self._maybe_reload()
        if not self.entries:
            return None
        # Follow the real calendar: BGM1 is the track whose begin date is
        # the latest one already reached (<= today). BGM2 is the next one
        # chronologically AFTER that (never an earlier/wrapped track, or the
        # shop sees an out-of-order campaign and refuses the pair).
        today = datetime.date.today().isoformat()
        current = 0
        for i, entry in enumerate(self.entries):
            if entry["begin"] <= today:
                current = i
        if offset == 0:
            return self.entries[current]
        for j in range(current + 1, len(self.entries)):
            if self.entries[j]["begin"] > self.entries[current]["begin"]:
                return self.entries[j]
        return self.entries[current]


TRACKS = _Tracks()


def _xml_header(meta: dict) -> bytes:
    def f(year, month, day):
        return year, int(month), int(day)

    begin_year, begin_month, begin_day = f(*meta["begin"].split("-"))
    # Give each track a plausibly historical begin date but a far-future end
    # so it is always a candidate "current" theme when the eShop opens.
    xml = (
        '<?xml version="1.0" encoding="utf-8"?><header>'
        f'<version>1</version><task>1</task><priority>128</priority>'
        f'<beginYear>{begin_year}</beginYear><beginMonth>{begin_month}</beginMonth>'
        f'<beginDay>{begin_day}</beginDay><beginHour>0</beginHour>'
        f'<beginMinute>0</beginMinute><beginSecond>0</beginSecond>'
        f'<endYear>{END_YEAR}</endYear><endMonth>01</endMonth><endDay>01</endDay>'
        f'<endHour>0</endHour><endMinute>0</endMinute><endSecond>0</endSecond>'
        f'<indefinite>1</indefinite>'
        f'<dataSize>{meta["data_size"]}</dataSize>'
        f'<loopStartFrame>0</loopStartFrame>'
        f'<loopEndFrame>{meta["loop_end_frame"]}</loopEndFrame>'
        '</header>'
    )
    return xml.encode("utf-8")


def _build_boss_container(payload: bytes, serial: int,
                          program_id: int = BOSS_PROGRAM_ID,
                          content_datatype: int = CONTENT_DATATYPE,
                          ns_data_id: int = NS_DATA_ID,
                          version: int = VERSION,
                          mark_arrived_privileged: bool = False) -> bytes:
    iv12 = os.urandom(12)

    # Content header (0x132 bytes): 0x12 flags/count + SHA-256 + zero RSA sig.
    # The first byte's bit 7 is the inverse of MARK_ARRIVED_PRIVILEGED
    # (see PreTendo boss-crypto encrypt3DS): flag set => bit7 clear.
    content_header = bytearray(0x12)
    if not mark_arrived_privileged:
        content_header[0] = 0x80
    content_header[0x10:0x12] = (1).to_bytes(2, "big")
    ch_hash = _sha256(bytes(content_header) + b"\x00\x00")
    content_header = bytes(content_header) + ch_hash + b"\x00" * 0x100

    # Payload content header (0x13C bytes): 0x1C fields + SHA-256 + zero sig.
    payload_header = bytearray(0x1C)
    payload_header[0x00:0x08] = int(program_id).to_bytes(8, "big")
    payload_header[0x0C:0x10] = int(content_datatype).to_bytes(4, "big")
    payload_header[0x10:0x14] = len(payload).to_bytes(4, "big")
    payload_header[0x14:0x18] = int(ns_data_id).to_bytes(4, "big")
    payload_header[0x18:0x1C] = int(version).to_bytes(4, "big")
    ph_hash = _sha256(bytes(payload_header) + b"\x00\x00" + payload)
    payload_header = bytes(payload_header) + ph_hash + b"\x00" * 0x100

    container = content_header + payload_header + payload

    header = bytearray(0x28)
    header[0x00:0x04] = b"boss"
    header[0x04:0x08] = (0x10001).to_bytes(4, "big")
    header[0x08:0x0C] = (0x28 + len(container)).to_bytes(4, "big")
    header[0x0C:0x14] = serial.to_bytes(8, "big")
    header[0x14:0x16] = (1).to_bytes(2, "big")
    header[0x18:0x1A] = (2).to_bytes(2, "big")  # hash type: SHA-256
    header[0x1A:0x1C] = (2).to_bytes(2, "big")  # RSA type: RSA-2048
    header[0x1C:0x28] = iv12

    # AES-128-CTR; counter block = iv12 + 0x00000001 (128-bit big-endian).
    # pycryptodome CTR only takes a 64-bit initial_value, so split the
    # counter into its 8-byte halves (verified identical to the manual stream).
    ctr = AES.new(BOSS_AES_KEY, AES.MODE_CTR,
                  nonce=iv12[0:8],
                  initial_value=int.from_bytes(iv12[8:12] + b"\x00\x00\x00\x01", "big"))
    return bytes(header) + ctr.encrypt(container)


def _sha256(data: bytes) -> bytes:
    import hashlib
    return hashlib.sha256(data).digest()


def _stable_serial(identifier: str) -> int:
    # Real BOSS content has a fixed serial per content revision; keep it stable
    # so the shop doesn't see the "same" content changing every fetch.
    import hashlib
    return int.from_bytes(hashlib.sha256(identifier.encode()).digest()[:8], "big")


def _payload_for(offset: int):
    meta = TRACKS.pick(offset)
    if meta is None:
        return None
    payload = _xml_header(meta) + meta["data"]
    return _stable_serial(meta["file"]), payload


npdl = Blueprint("npdl", "npdl")


def _serve_bgm(appid, task, name, reg=None):
    if appid.lower() != BOSS_APP_ID.lower():
        return Response(b"Not Found", status=404)
    if not SAFE_FILENAME.match(task) or not SAFE_FILENAME.match(name):
        return Response(b"Not Found", status=404)

    offset = 1 if task.upper().startswith("BGM2") else 0
    result = _payload_for(offset)
    if result is None:
        return Response(b"Service Unavailable", status=503)
    serial, payload = result

    container = _build_boss_container(payload, serial)
    resp = Response(container, mimetype="application/octet-stream")
    resp.headers["Content-Length"] = str(len(container))
    resp.headers["Cache-Control"] = "no-cache"
    return resp


def _build_notification_payload(title, message, image=None, browser_url=None,
                                source_program_id=0, jump_param=0):
    """Build a BOSS notification blob (3dbrew NEWSS:SyncArrivedNotifications).

    Layout: 0x20 header + 0x40 UTF-16 title + 0x1780 UTF-16 message + image.
    """
    title_bytes = title.encode("utf-16-le")[:0x3e]
    title_bytes += b"\x00\x00"
    title_bytes = title_bytes.ljust(0x40, b"\x00")[:0x40]

    message_bytes = message.encode("utf-16-le")
    if browser_url:
        message_bytes += b"\x00\x00" + browser_url.encode("utf-8")
    if not message_bytes.endswith(b"\x00\x00"):
        message_bytes += b"\x00\x00"
    message_bytes = message_bytes[:0x1780].ljust(0x1780, b"\x00")

    header = bytearray(0x60)
    header[0x00] = 1                         # valid
    header[0x01] = 1                         # unread
    header[0x02] = 1 if image else 0         # image data is JPEG
    header[0x03] = 1                         # SpotPass notification
    header[0x04] = 0                         # opted in
    header[0x05] = 1 if browser_url else 0   # message has a browser link
    header[0x08:0x10] = int(source_program_id).to_bytes(8, "big")
    header[0x10:0x18] = int(jump_param).to_bytes(8, "big")
    header[0x20:0x60] = title_bytes

    payload = bytes(header) + message_bytes
    if image:
        payload += image
    return payload


def _read_spotpass():
    try:
        with open(SPOTPASS_FILE, "r") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _spotpass_container():
    data = _read_spotpass()
    if not data or not data.get("enabled"):
        return None

    image = None
    image_name = data.get("image")
    if image_name:
        image_path = os.path.join(SPOTPASS_DIR, os.path.basename(image_name))
        if os.path.isfile(image_path):
            with open(image_path, "rb") as f:
                image = f.read()

    payload = _build_notification_payload(
        (data.get("title") or "")[:31],
        data.get("message") or "",
        image=image,
        browser_url=data.get("url") or None,
    )
    serial = int(data.get("serial") or _stable_serial(str(data.get("id", "spotpass"))))
    return _build_boss_container(
        payload, serial,
        program_id=int(data.get("program_id") or NEWS_SYSMODULE_TITLE),
        content_datatype=NOTIF_CONTENT_DATATYPE,
        ns_data_id=int(data.get("ns_data_id") or NOTIF_NS_DATA_ID),
        version=0,
        mark_arrived_privileged=True,
    )


def _serve_spotpass():
    container = _spotpass_container()
    if container is None:
        return Response(b"Not Found", status=404)
    resp = Response(container, mimetype="application/octet-stream")
    resp.headers["Content-Length"] = str(len(container))
    resp.headers["Cache-Control"] = "no-cache"
    return resp


def _notif_file_name(task):
    m = re.search(r"(\d)", task)
    return "sysmsg" + (m.group(1) if m else "0")


def _spotpass_filelist(appid, task):
    """3DS BOSS file-list (npfl): SHA1 line + size line + one file line."""
    container = _spotpass_container()
    if container is None:
        files = []
    else:
        files = [{
            "name": _notif_file_name(task),
            "desc": "",
            "a1": "", "a2": "", "a3": "",
            "size": len(container),
            "updated": int(time.time()),
        }]

    size = 40 + 2 + 10 + 2  # SHA1 line + size line, both CRLF-terminated
    body = ""
    for f in files:
        line = "\t".join([
            f["name"], f["desc"], f["a1"], f["a2"], f["a3"],
            str(f["size"]), str(f["updated"]),
        ]) + "\r\n"
        body += line
        size += len(line)

    body = f"{size:>10}\r\n" + body
    digest = hashlib.sha1(body.encode("utf-8")).hexdigest()
    body = f"{digest}\r\n" + body
    resp = Response(body, mimetype="text/plain")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@npdl.route("/p01/filelist/<appid>/<task>", methods=["GET"])
@npdl.route("/npfl/p01/filelist/<appid>/<task>", methods=["GET"])
def filelist(appid, task):
    print(f"[npfl] filelist app={appid} task={task} q={dict(request.args)}", flush=True)
    return _spotpass_filelist(appid, task)


def _dispatch_nsa(appid, task, name, reg=None):
    # Home Menu SpotPass system-notification task (bashoX downloads sysmsgX).
    if task.lower().startswith(("basho", "sysmsg")) or name.lower().startswith("sysmsg"):
        print(f"[npdl] spotpass task={task!r} app={appid} name={name}", flush=True)
        return _serve_spotpass()
    if task.upper().startswith("BGM"):
        return _serve_bgm(appid, task, name, reg)
    print(f"[npdl] unhandled BOSS task app={appid} task={task} name={name}", flush=True)
    return Response(b"Not Found", status=404)


@npdl.route("/p01/nsa/<appid>/<task>/<name>", methods=["GET"])
@npdl.route("/p01/nsa/<appid>/<task>/<reg>/<name>", methods=["GET"])
def bgm(appid, task, name, reg=None):
    return _dispatch_nsa(appid, task, name, reg)


_REUSE = re.compile(r".*\/p01\/nsa\/([A-Za-z0-9]+)\/([A-Za-z0-9]+)\/.*$")


@npdl.route("/<path:suffix>", methods=["GET"])
def bgm_reused(suffix):
    # Some clients hit the old Akamai form:
    #   /f/248/103046/10m/npdl.c.app.nintendowifi.net/p01/nsa/<app>/<task>/<name>
    match = _REUSE.match("/" + suffix)
    if not match:
        print(f"[npdl] unhandled path /{suffix}", flush=True)
        return Response(b"Not Found", status=404)
    return _dispatch_nsa(match.group(1), match.group(2), suffix.split("/")[-1])


def register(app):
    app.register_blueprint(npdl)
    print("npdl BGM services started")