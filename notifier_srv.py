"""Plain-HTTP delivery endpoint for the 3DS notifier homebrew.

The console-side notifier (3ds-notifier/) polls GET /pending over plain HTTP and
posts whatever it finds into the Notifications applet, then acknowledges it with
GET /ack?serial=N.  Plain HTTP is used deliberately: the notifier runs before
any of the console's TLS/proxy configuration is available, so it cannot talk to
the HTTPS Flask listener on :8000.

SpotPass content delivery proper (BOSS) is not used here because a policylist
can only re-prioritise tasks that already exist in the console's local BOSS
database - it cannot create them - so on a console that has only ever reached
NetPass no notification task is ever scheduled and no file-list is requested.

Acknowledgement is keyed on the notification's serial (a hash of its title and
message) rather than its row id, so editing and republishing an existing draft
becomes pending again.
"""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

SPOTPASS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spotpass")
CURRENT_PATH = os.path.join(SPOTPASS_DIR, "current.json")
STATE_PATH = os.path.join(SPOTPASS_DIR, "notifier_state.json")

NOTIFY_PORT = 8001


def _load_current():
    try:
        with open(CURRENT_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _acked_serial():
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            return int(json.load(fh).get("serial", 0))
    except (OSError, ValueError, TypeError):
        return 0


def _ack_serial(serial):
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"serial": int(serial)}, fh)
    os.replace(tmp, STATE_PATH)


def _pending_body():
    """Return the notifier wire-format body, or None when nothing is pending."""
    current = _load_current()
    if not current or not current.get("enabled"):
        return b"NONE\n"
    serial = int(current.get("serial") or 0)
    if not serial or serial == _acked_serial():
        return b"NONE\n"

    title = str(current.get("title") or "").encode("utf-8")
    message = str(current.get("message") or "").encode("utf-8")

    image = b""
    name = str(current.get("image") or "")
    if name:
        # Only ever hand over a JPEG: NEWS_AddNotification's jpeg flag is set.
        if not name.lower().endswith((".jpg", ".jpeg")):
            name += ".jpg"
        try:
            with open(os.path.join(SPOTPASS_DIR, name), "rb") as fh:
                if fh.read(2) == b"\xff\xd8":
                    fh.seek(0)
                    image = fh.read()
        except OSError:
            image = b""

    header = "REVIVE1 %d %d %d %d\n" % (serial, len(title), len(message), len(image))
    return header.encode("ascii") + title + message + image


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    server_version = "ReviveShopNotifier/1.0"

    def _reply(self, body, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        route = url.path.rstrip("/") or "/"

        if route == "/pending":
            self._reply(_pending_body())
        elif route == "/ack":
            serial = parse_qs(url.query).get("serial", ["0"])[0]
            try:
                _ack_serial(int(serial))
            except ValueError:
                pass
            self._reply(b"OK\n")
        elif route == "/ping":
            self._reply(b"pong\n")
        else:
            self._reply(b"not found\n", 404)

    def log_message(self, fmt, *args):
        print("[notifier] %s" % (fmt % args))


def start():
    """Start the notifier endpoint in a background thread."""
    server = ThreadingHTTPServer(("0.0.0.0", NOTIFY_PORT), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print("Notifier endpoint on http://0.0.0.0:%d/pending" % NOTIFY_PORT)
    return server