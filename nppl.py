"""nppl policylist endpoint for ReviveShop (Flask).

BOSS (SpotPass) fetches a cleartext XML "policylist" from

    https://nppl.c.app.nintendowifi.net/p01/policylist/3/<country>

on every WiFi connect.  It lists SpotPass tasks and can STOP/EXPEDITE them.
The default is `DefaultStop=false` (tasks run), which is what upstream
(Pretendo / NetPass) serves.  We answer the same shape ourselves so the
console never depends on a third party for its policy.

The console here resolves the policylist host to `api.netpass.cafe` (NetPass
DNS); the mitm rewrite interposes on the /nppl path and sends it to us.
"""

import datetime

from flask import Blueprint, Response

nppl = Blueprint("nppl", "nppl")

# Same entries Pretendo/NetPass serve (Home Menu notifications, uploads,
# StreetPass relay).  Level is one of STOPPED | HIGH | EXPEDITE.
PRIORITIES = [
    ("0004003000008f02", "basho0", "EXPEDITE"),
    ("0004003000008f02", "sysmsg1", "HIGH"),
    ("0004003000008f02", "sysmsg2", "HIGH"),
    ("0004003000008f02", "sysmsg3", "HIGH"),
    ("000400300000bc00", "OlvNotf", "HIGH"),
    ("000400300000bd00", "OlvNotf", "HIGH"),
    ("000400300000be00", "OlvNotf", "HIGH"),
    ("0004003000008f02", "pl", "HIGH"),
    ("0004013000003400", "sprelay", "HIGH"),
]


def _policylist(major):
    items = "".join(
        "<Priority>"
        f"<TitleId>{title}</TitleId><TaskId>{task}</TaskId>"
        f"<Level>{level}</Level>"
        "<Persistent>true</Persistent><Revive>true</Revive>"
        "</Priority>"
        for title, task, level in PRIORITIES
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        "<PolicyList>"
        f"<MajorVersion>{major}</MajorVersion><MinorVersion>0</MinorVersion>"
        "<ListId>1891</ListId>"
        "<DefaultStop>false</DefaultStop><ForceVersionUp>false</ForceVersionUp>"
        f"<UpdateTime>{datetime.datetime.utcnow():%Y-%m-%dT%H:%M:%S}+0000</UpdateTime>"
        f"{items}"
        "</PolicyList>"
    )


@nppl.route("/nppl/p01/policylist/<major>/<country>", methods=["GET"])
@nppl.route("/p01/policylist/<major>/<country>", methods=["GET"])
def policylist(major, country):
    return Response(_policylist(major), mimetype="application/xml")


def register(app):
    app.register_blueprint(nppl)
    print("nppl policy services started")
