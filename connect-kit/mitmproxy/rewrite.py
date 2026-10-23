"""ReviveShop host-rewrite addon for mitmproxy (the free Charles replacement).

Rewrites eShop traffic from Nintendo hosts onto the local ReviveShop servers:

  ecs.c.shop.nintendowifi.net   -> <SERVER_IP>:8000  (ECS/IAS/CAS SOAP + CDN /ccs)
  ninja.ctr.shop.nintendo.net   -> <SERVER_IP>:9000  (Ninja metadata + Samurai web)

The 3DS eShop resolves the hostnames itself and often connects by IP, so we
also route direct-IP dials to this machine (port 443) by URL path:

  /ninja/*  /samurai/*  /admin/*  login/web UI  -> :9000  (Django)
  everything else (ecs/ias/cas/cdn)             -> :8000  (Flask)

Usage:
  RS_SERVER_IP=<this PC's LAN IP> \
    connect-kit/.venv-kit/bin/mitmdump \
      --listen-port 8888 --ssl-insecure \
      --set tls_version_client_min=TLSv1 \
      -s connect-kit/mitmproxy/rewrite.py

`--ssl-insecure` skips upstream cert validation (dev certs) and the TLS floor
is dropped to v1.0 so the 3DS's old SSL stack can handshake. Only run this
family of options against machines you control.
"""

import base64
import os
import time

from mitmproxy import http

SERVER_IP = os.environ.get("RS_SERVER_IP", "127.0.0.1")
FLASK_PORT = 8000     # ECS/IAS/CAS SOAP + CDN (Python Flask main.py)
DJANGO_PORT = 9000    # ninja metadata + samurai + web UI/admin (Django)

HOSTS = {
    "ecs.c.shop.nintendowifi.net": (SERVER_IP, FLASK_PORT),
    "ninja.ctr.shop.nintendo.net": (SERVER_IP, DJANGO_PORT),
    "ninja.ctr.shop.pretendo.cc": (SERVER_IP, DJANGO_PORT),
    "ecs.c.shop.pretendo.cc": (SERVER_IP, FLASK_PORT),
    "nus.c.shop.pretendo.cc": (SERVER_IP, FLASK_PORT),
    "l-npns.app.pretendo.cc": (SERVER_IP, FLASK_PORT),
    # nicoch.net / nicochristmann.net (custom CA/SSL patch)
    "ecs.c.shop.nicoch.net": (SERVER_IP, FLASK_PORT),
    "ninja.ctr.shop.nicoch.net": (SERVER_IP, DJANGO_PORT),
    "nus.c.shop.nicoch.net": (SERVER_IP, FLASK_PORT),
    "ias.c.shop.nicoch.net": (SERVER_IP, FLASK_PORT),
    "nasc.nicochristmann.net": (SERVER_IP, FLASK_PORT),  # NASC might be routed differently, but proxy will see it
    "service.spr.app.nicoch.net": (SERVER_IP, FLASK_PORT),
    "nppl.c.app.nicoch.net": (SERVER_IP, FLASK_PORT),
    "ctr-o2fgs.cdn.nicoch.net": (SERVER_IP, FLASK_PORT),
    # eShop background music (SpotPass/npdl). The 3DS may hit either the
    # npdl host directly or the old Akamai host with the npdl host embedded
    # in the URL path - both end up on the Flask npdl blueprint.
    "npdl.c.app.nintendowifi.net": (SERVER_IP, FLASK_PORT),
    "npdl.cdn.nintendowifi.net": (SERVER_IP, FLASK_PORT),
    "npdl.cdn.pretendo.cc": (SERVER_IP, FLASK_PORT),
    "npdl.app.pretendo.cc": (SERVER_IP, FLASK_PORT),
    # Other BOSS hosts (content info / file lists). Anything we do not handle
    # explicitly is logged and 404s, which is useful while reversing the
    # Home Menu notification task.
    "npdi.cdn.nintendowifi.net": (SERVER_IP, FLASK_PORT),
    "npdi.cdn.pretendo.cc": (SERVER_IP, FLASK_PORT),
    "npfl.c.app.nintendowifi.net": (SERVER_IP, FLASK_PORT),
    "npfl.c.app.pretendo.cc": (SERVER_IP, FLASK_PORT),
    "a248.e.akamai.net": (SERVER_IP, FLASK_PORT),
    # BOSS policylist (which SpotPass tasks run). Served by our Flask nppl.
    "nppl.c.app.nintendowifi.net": (SERVER_IP, FLASK_PORT),
    "nppl.cdn.nintendowifi.net": (SERVER_IP, FLASK_PORT),
    "nppl.app.pretendo.cc": (SERVER_IP, FLASK_PORT),
    "nppl.c.app.pretendo.cc": (SERVER_IP, FLASK_PORT),
    # Default/fallback for example.com hosts from settings
    "api.example.com": (SERVER_IP, DJANGO_PORT),
    "soap.example.com": (SERVER_IP, FLASK_PORT),
}

# NetPass (netpass.cafe) is a third-party StreetPass service the console's DNS
# points the SpotPass hosts at. We interpose only on the BOSS paths (policy
# list + downloads) and pass everything else (StreetPass relay etc.) through.
NETPASS_HOST = "api.netpass.cafe"
# A 3DS BOSS (SpotPass) session asks NetPass for these service paths:
#   /nppl/p01/policylist/...   (which tasks run)
#   /npfl/p01/filelist/...     (what files a task has)
#   /npdl/p01/nsa/...          (the file content)
#   /npdi/p01/data/...         (direct data)
#   /npts/...                  (task status/upload)
# We interpose on all of them so the Home Menu notification task is served by
# us instead of NetPass, and pass everything else (StreetPass relay) through.
NETPASS_PATHS = ("/nppl/", "/npfl/", "/npdl/", "/npdi/", "/npts/")

# Local SAN addresses (dials straight at this PC) plus the configured server IP.
LOCAL_IPS = {"192.168.4.34", "192.168.4.35", "127.0.0.1", SERVER_IP}

# account.pretendo.cc (PreTendo's account/OAuth server) went NODATA in late
# 2025 (PreTendo explicitly does not support eShop revivals). The eShop still
# needs an account token to open a shop session, so we fabricate the whole
# account flow locally - nothing leaves this machine. Our own ninja/ECS accept
# the token, so a fixed fake one is fine.
ACCOUNT_HOST = "account.pretendo.cc"
ACCOUNT_HOSTS = {"account.pretendo.cc", "act.nicochristmann.net"}
_ACCOUNT_TOKEN = "083491f8ecc32088f82e0a73e9d715c5"
_ACCOUNT_REFRESH = "dd811e4ab4bb2e1eb5f92dfc25fe744bb129061d"
_SERVICE_TOKEN = "62380B4ADF540AED099D9ABFF05D71BD"
_PROFILE_XML = (
    '<?xml version="1.0"?><person><active_flag>Y</active_flag>'
    '<birth_date>1990-01-01</birth_date><country>US</country>'
    '<create_date>2026-08-10T22:08:56</create_date><device_attributes/>'
    '<gender>M</gender><language>en</language>'
    '<updated>2026-08-10T22:08:56</updated><marketing_flag>Y</marketing_flag>'
    '<off_device_flag>Y</off_device_flag><pid>1296142408</pid>'
    '<email><address>thecatlinkids2@gmail.com</address><id>2744453103</id>'
    '<parent>Y</parent><primary>Y</primary><reachable>Y</reachable>'
    '<type>DEFAULT</type><updated_by>USER</updated_by><validated>Y</validated>'
    '<validated_date>2026-08-15T14:08:00</validated_date></email>'
    '<mii><status>COMPLETED</status><id>2954036663</id>'
    '<mii_hash>c87309d6ac646c</mii_hash><name>Rhyker</name>'
    '<primary>Y</primary></mii><region>825360384</region>'
    '<tz_name>America/New_York</tz_name><user_id>thecatlinkids2</user_id>'
    '<utc_offset>-18000</utc_offset></person>'
)
_NOT_FOUND_XML = (
    '<?xml version="1.0"?><errors><error><cause/><code>0008</code>'
    '<message>Not Found</message></error></errors>'
)


def _reply(flow: http.HTTPFlow, code: int, text: str) -> None:
    flow.response = http.Response.make(
        code, text.encode("utf-8"), {"Content-Type": "text/xml; charset=utf-8"}
    )


def _fabricate_account(flow: http.HTTPFlow) -> None:
    path = flow.request.path.split("?", 1)[0]
    if path.startswith("/v1/api/oauth20/access_token/generate"):
        _reply(flow, 200,
               '<?xml version="1.0"?><OAuth20><access_token>'
               f'<token>{_ACCOUNT_TOKEN}</token>'
               f'<refresh_token>{_ACCOUNT_REFRESH}</refresh_token>'
               '<expires_in>2147483647</expires_in></access_token></OAuth20>')
    elif path.startswith("/v1/api/people/@me/profile"):
        _reply(flow, 200, _PROFILE_XML)
    elif path.startswith("/v1/api/provider/service_token"):
        _reply(flow, 200,
               f'<service_token><token>{_SERVICE_TOKEN}</token>'
               '<expires_in>2147483647</expires_in></service_token>')
    else:
        # e.g. /people/@me/devices/@current/attributes - the console treats a
        # 404 as "no attributes" and carries on.
        _reply(flow, 404, _NOT_FOUND_XML)
    print(f"[stub]    {ACCOUNT_HOST} {flow.request.method} {path} -> "
          f"{flow.response.status_code}", flush=True)


# nasc.pretendo.cc (NAS - the console's game-server login) now answers 503 for
# the eShop's title because PreTendo dropped eShop support. We answer it
# ourselves with the same shape the real server used to return. The 3DS only
# uses the token to open its (local) shop session; the locator points at the
# old NEX host, which this download path does not actually use.
NASC_HOST = "nasc.pretendo.cc"
_NASC_LOCATOR = "NTQuMzcuMjAwLjI0NjozMDEwMA"  # base64("54.37.200.246:30100")
_NASC_TOKEN = (
    "wliEjwsfJgSoVZUoVUM3nLT0EzFGz3oJZV6k2xvGV1gyelGVxQofchBd5dyLnEwB28H"
    "xjoRnSqoDea3JcvLBBIp26cxBJCdCcvuseZcMkQKrvc7Sg4wM1YqLgH-gqcbd9gX1"
    "iehu6u9x3f3QDn8RQg"
)


def _fabricate_nasc(flow: http.HTTPFlow) -> None:
    dt = base64.b64encode(time.strftime("%Y%m%d%H%M%S").encode()).decode()
    body = (f"locator={_NASC_LOCATOR}**&retry=MA**&returncd=MDAx"
            f"&token={_NASC_TOKEN}**&datetime={dt}*")
    flow.response = http.Response.make(
        200, body.encode("utf-8"), {"Content-Type": "text/plain"}
    )
    print(f"[stub]    {NASC_HOST} {flow.request.method} {flow.request.path} "
          f"-> 200", flush=True)


DJANGO_PATHS = ("/ninja", "/samurai", "/admin", "/login", "/signup", "/logout",
                "/title/", "/wishlist", "/ecommerce", "/downloaded", "/search")


def _route_by_path(path: str) -> int:
    lowercase = path.split("?", 1)[0].lower()
    return DJANGO_PORT if lowercase.startswith(DJANGO_PATHS) else FLASK_PORT


def _rewrite(flow: http.HTTPFlow, ip: str, port: int, reason: str) -> None:
    flow.request.host = ip
    flow.request.port = port
    flow.request.scheme = "https"
    print(f"[rewrite]{reason} {flow.request.pretty_host}:{flow.request.port} -> "
          f"{ip}:{port}{flow.request.path}", flush=True)


def request(flow: http.HTTPFlow) -> None:
    host = flow.request.pretty_host
    port = flow.request.port

    if host == ACCOUNT_HOST or host in ACCOUNT_HOSTS:
        # ReTendo/account server (Flask blueprint retendo.py).
        _rewrite(flow, SERVER_IP, FLASK_PORT, "(retendo)")
        return

    if host == NASC_HOST or host == "nasc.nicochristmann.net":
        _fabricate_nasc(flow)
        return

    if host in HOSTS:
        ip, server_port = HOSTS[host]
        _rewrite(flow, ip, server_port, "(host) ")
        return

    if host in LOCAL_IPS and port in (443, 8000, 9000):
        server_port = _route_by_path(flow.request.path)
        _rewrite(flow, SERVER_IP, server_port, "(ip)   ")
        return
    if host in LOCAL_IPS and port == 8888:
        server_port = _route_by_path(flow.request.path)
        _rewrite(flow, SERVER_IP, server_port, "(ip8888)")
        return

    if host == NETPASS_HOST and flow.request.path.startswith(NETPASS_PATHS):
        _rewrite(flow, SERVER_IP, FLASK_PORT, "(netpass)")
        return

    print(f"[pass]    {host}:{port}{flow.request.path}", flush=True)


LOG_BODIES_HOSTS = ("nasc.pretendo.cc", "account.pretendo.cc", "r2-cdn.pretendo.cc")


def response(flow: http.HTTPFlow) -> None:
    host = flow.request.pretty_host
    path = flow.request.path

    if host == NETPASS_HOST and path.startswith(NETPASS_PATHS):
        print(f"[boss]    {flow.request.method} {host}{path} -> "
              f"{flow.response.status_code}", flush=True)

    if host in LOG_BODIES_HOSTS:
        req = (flow.request.get_text() or "")[:1500].replace("\n", " ")
        resp = (flow.response.get_text() or "")[:1500].replace("\n", " ")
        loc = flow.response.headers.get("Location", "")
        print(f"[body>{host}] status={flow.response.status_code} loc={loc}", flush=True)
        print(f"  REQ  {req}", flush=True)
        print(f"  RESP {resp}", flush=True)

    # Body preview for our own local servers, to trace the download flow.
    if flow.request.host in LOCAL_IPS and flow.request.port in (8000, 9000):
        cookie = flow.request.headers.get("Cookie", "")[:200].replace("\n", " ")
        req = (flow.request.get_text() or "")[:600].replace("\n", " ")
        resp = (flow.response.get_text() or "")[:600].replace("\n", " ")
        print(f"[local>{flow.request.port}] {flow.request.method} {flow.request.path}", flush=True)
        print(f"  cookie={cookie}", flush=True)
        if req:
            print(f"  REQ  {req}", flush=True)
        print(f"  RESP {resp}", flush=True)