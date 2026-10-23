"""NASC (Nintendo Authentication Server Client) endpoint for ReviveShop (Flask).

The proxy (connect-kit/mitmproxy/rewrite.py) used to fabricate the NASC reply
inline. With the Nimbus-style IPS plugin there is no proxy, so the console's
``https://nasc.*/ac/`` request is rewritten straight to this box and must be
answered here.

The 3DS only uses the returned ``locator``/``token`` to open its (local) shop
session; the locator points at the old NEX host, which the eShop download path
does not actually use. Values default to the same fabricated constants the
proxy used and can be overridden with RS_NASC_* environment variables.
"""
import base64
import os
import time

from flask import Blueprint, Response, request

print("NASC Stub Server Starting Up")

nasc = Blueprint("nasc", "nasc")

# base64("54.37.200.246:30100")
LOCATOR = os.environ.get("RS_NASC_LOCATOR", "NTQuMzcuMjAwLjI0NjozMDEwMA")
TOKEN = os.environ.get("RS_NASC_TOKEN", (
    "wliEjwsfJgSoVZUoVUM3nLT0EzFGz3oJZV6k2xvGV1gyelGVxQofchBd5dyLnEwB28H"
    "xjoRnSqoDea3JcvLBBIp26cxBJCdCcvuseZcMkQKrvc7Sg4wM1YqLgH-gqcbd9gX1"
    "iehu6u9x3f3QDn8RQg"
))


def _body():
    dt = base64.b64encode(time.strftime("%Y%m%d%H%M%S").encode()).decode()
    return (f"locator={LOCATOR}**&retry=MA**&returncd=MDAx"
            f"&token={TOKEN}**&datetime={dt}*")


@nasc.route("/ac/", methods=["GET", "POST"])
def ac():
    print(f"[nasc] {request.method} {request.path} -> 200")
    return Response(_body(), mimetype="text/plain")


@nasc.route("/ac", methods=["GET", "POST"])
def ac_noslash():
    return ac()
