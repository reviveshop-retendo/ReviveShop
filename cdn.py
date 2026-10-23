from flask import Blueprint, make_response, request
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'shopdeck.settings')
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
from shopdeckdb.models import *
from django.core.exceptions import ObjectDoesNotExist
import os.path

print("Title CDN Services Starting Up")

#Implementing a system for games update soon

ccs = Blueprint("ccs", "ccs")

# request.path -> monotonic start time, used only to time CCS responses
g_ccs_started = {}

CDN_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "cdn"))


def _cdn_dir(tid):
    """Resolve cdn/<tid>/ tolerantly.

    The console sends title ids in uppercase while CIAs are extracted with the
    lowercase id pyctr reports, so the directory on disk may not match the case
    in the URL. Accept either spelling instead of 404ing.
    """
    name = os.path.basename(str(tid))
    direct = os.path.join(CDN_ROOT, name)
    if os.path.isdir(direct):
        return direct
    want = name.lower()
    try:
        entries = os.listdir(CDN_ROOT)
    except OSError:
        return direct
    for entry in entries:
        if entry.lower() == want:
            return os.path.join(CDN_ROOT, entry)
    return direct


def _cdn_file(tid, fname):
    """Resolve cdn/<tid>/<fname> tolerantly (same case-insensitive logic as
    _cdn_dir). The console sends content IDs uppercase (from the TMD) while
    CIA extraction writes them lowercase, so match either spelling."""
    directory = _cdn_dir(tid)
    direct = os.path.join(directory, fname)
    if os.path.isfile(direct):
        return direct
    want = fname.lower()
    try:
        entries = os.listdir(directory)
    except OSError:
        return direct
    for entry in entries:
        if entry.lower() == want:
            return os.path.join(directory, entry)
    return direct


def _serve(path, label):
    """Serve a CDN file with Range/HEAD support (the 3DS downloader resumes
    large .app downloads with byte ranges, so conditional responses matter)."""
    if not os.path.isfile(path):
        print("CCS MISS %s -> %s" % (label, path), flush=True)
        return "error", 404
    print("CCS %s %s range=%s" % (request.method, label, request.headers.get("Range")), flush=True)
    started = time.time()
    g_ccs_started[request.path] = started
    resp = send_file(path, mimetype="application/octet-stream",
                     conditional=True, etag=True,
                     last_modified=os.path.getmtime(path))
    resp.headers["Accept-Ranges"] = "bytes"
    return resp


@ccs.after_request
def _log_ccs_response(response):
    """send_file streams lazily, so this only proves the response was *started*.

    It is still worth having: paired with mitmproxy's `<< 200 OK <size>` line it
    brackets a transfer, and it confirms the Range/206 negotiation per request.
    """
    started = g_ccs_started.pop(request.path, None)
    if started is not None:
        print("CCS SENT %s -> %s bytes=%s %.2fs" % (
            request.path, response.status_code,
            response.headers.get("Content-Length"), time.time() - started), flush=True)
    return response


@ccs.route("/ccs/download/<tid>/tmd.<version>", methods=['GET'])
def download_tmd(tid, version):
    try:
        title = Title.objects.get(tid=str(tid))
    except ObjectDoesNotExist:
        return "Error"
    try:
        ds = Client3DS.objects.get(consoleid=request.args.get('deviceId'))
    except ObjectDoesNotExist:
        return "Error"
    try:
        owned = ownedTitle.objects.get(title=title, owner=ds)
    except ObjectDoesNotExist:
        return "error"
    if owned.version < title.version:
        owned.version = title.version
        owned.save()
    path = str(os.path.dirname(__file__))+"/cdn/"+str(tid)+"/tmd.bin"
    if not os.path.isfile(path):
        return "error"
    f = open(path, mode="rb")
    r = make_response(f.read())
    r.headers.set("Content-Type", "application/octet-stream")
    return r
@ccs.route("/ccs/download/<tid>/<app>", methods=['GET'])
def download_app(tid, app):
    return _serve(_cdn_file(tid, os.path.basename(str(app)) + ".app"),
                  "app %s/%s" % (tid, app))
