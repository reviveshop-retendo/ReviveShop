"""ReTendo - our Nintendo Network ID / account server.

Serves account.pretendo.cc: OAuth20 token issue, @me profile, service tokens
and the web signup/login/authorize pages the console's webview opens when you
create or link an NNID.

Accounts live in the Django DB (RtAccount / RtToken / RtConsoleLink). For any
token or credential we don't recognise we fall back to the old fabricated
constants so the already-working eShop session keeps running unchanged.
"""
import os
import secrets
import datetime

from flask import Blueprint, request, redirect, make_response, render_template_string

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'reviveshop.settings')
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
from shopdeckdb.models import RtAccount, RtToken, RtConsoleLink, Client3DS
from django.contrib.auth.hashers import make_password, check_password
from django.db.models import Max

print("ReTendo Account Server Starting Up")

retendo = Blueprint("retendo", "retendo")

FALLBACK_ACCESS = "083491f8ecc32088f82e0a73e9d715c5"
FALLBACK_REFRESH = "dd811e4ab4bb2e1eb5f92dfc25fe744bb129061d"
FALLBACK_SERVICE = "62380B4ADF540AED099D9ABFF05D71BD"
FALLBACK_PROFILE = (
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
NOT_FOUND = (
    '<?xml version="1.0"?><errors><error><cause/><code>0008</code>'
    '<message>Not Found</message></error></errors>'
)
INVALID_PW = (
    '<?xml version="1.0"?><errors><error><cause/><code>0106</code>'
    '<message>Invalid account or password</message></error></errors>'
)


def _xml(text, code=200):
    r = make_response(text, code)
    r.headers["Content-Type"] = "text/xml; charset=utf-8"
    return r


def _rand():
    return secrets.token_hex(16).upper()


def _next_pid():
    top = RtAccount.objects.aggregate(m=Max("pid"))["m"] or 1000000000
    return top + 1


def _issue_token(account):
    tok = RtToken.objects.filter(account=account).first()
    if tok is None:
        tok = RtToken.objects.create(
            account=account,
            access_token=_rand(),
            refresh_token=_rand(),
            service_token=_rand(),
        )
    return tok


def _identify():
    """Return (account, token_string) for the request, or (None, token)."""
    tok = None
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        tok = auth[7:].strip()
    for h in ("X-Nintendo-ServiceToken", "X-Nintendo-AccessToken",
              "X-Nintendo-RefreshToken", "X-Nintendo-Param"):
        if not tok and request.headers.get(h):
            tok = request.headers.get(h).strip()
    if not tok:
        tok = (request.values.get("access_token")
               or request.values.get("service_token")
               or request.values.get("refresh_token"))
    if not tok:
        return None, None
    for field in ("access_token", "service_token", "refresh_token"):
        rt = RtToken.objects.filter(**{field: tok}).select_related("account").first()
        if rt:
            return rt.account, tok
    return None, tok


def _profile_xml(a):
    created = a.created.strftime("%Y-%m-%dT%H:%M:%S") if a.created else "2026-01-01T00:00:00"
    birth = a.birth_date.isoformat() if a.birth_date else "1990-01-01"
    return (
        '<?xml version="1.0"?><person><active_flag>Y</active_flag>'
        f'<birth_date>{birth}</birth_date><country>{a.country}</country>'
        f'<create_date>{created}</create_date><device_attributes/>'
        f'<gender>{a.gender}</gender><language>{a.language}</language>'
        f'<updated>{created}</updated><marketing_flag>Y</marketing_flag>'
        '<off_device_flag>Y</off_device_flag>'
        f'<pid>{a.pid}</pid>'
        f'<email><address>{a.email or a.user_id + "@retendo.local"}</address>'
        f'<id>{a.pid}</id>'
        '<parent>Y</parent><primary>Y</primary><reachable>Y</reachable>'
        '<type>DEFAULT</type><updated_by>USER</updated_by><validated>Y</validated>'
        f'<validated_date>{created}</validated_date></email>'
        f'<mii><status>COMPLETED</status><id>{a.mii_id or "0"}</id>'
        f'<mii_hash>{a.mii_hash or "0"}</mii_hash><name>{a.mii_name}</name>'
        '<primary>Y</primary></mii><region>825360384</region>'
        '<tz_name>America/New_York</tz_name>'
        f'<user_id>{a.user_id}</user_id>'
        '<utc_offset>-18000</utc_offset></person>'
    )


def _oauth_xml(access, refresh):
    return (
        '<?xml version="1.0"?><OAuth20><access_token>'
        f'<token>{access}</token>'
        f'<refresh_token>{refresh}</refresh_token>'
        '<expires_in>2147483647</expires_in></access_token></OAuth20>'
    )


def _service_xml(token):
    return (f'<service_token><token>{token}</token>'
            '<expires_in>2147483647</expires_in></service_token>')


def find_account(login):
    """Look up by user_id (NNID) or email."""
    if not login:
        return None
    a = RtAccount.objects.filter(user_id__iexact=login).first()
    if a is None:
        a = RtAccount.objects.filter(email__iexact=login).first()
    return a


def create_account(user_id, password, email="", country="US", language="en",
                   mii_name="Player", gender="M", birth_date=None):
    a = RtAccount.objects.create(
        user_id=user_id,
        email=email,
        password=make_password(password) if password else "",
        pid=_next_pid(),
        mii_name=mii_name or "Player",
        country=country or "US",
        language=language or "en",
        gender=gender or "M",
        birth_date=birth_date,
    )
    return a


# --------------------------------------------------------------------------
# Nintendo Network account API
# --------------------------------------------------------------------------

@retendo.route("/v1/api/oauth20/access_token/generate",
               methods=["GET", "POST"])
def access_token_generate():
    grant = request.values.get("grant_type", "password")
    if grant == "refresh_token":
        rt = RtToken.objects.filter(
            refresh_token=request.values.get("refresh_token", "")).first()
        if rt:
            a, _ = _identify_rt(rt)
            return _xml(_oauth_xml(rt.access_token, rt.refresh_token))
        return _xml(_oauth_xml(FALLBACK_ACCESS, FALLBACK_REFRESH))

    login = request.values.get("username") or request.values.get("user_id", "")
    password = request.values.get("password", "")
    a = find_account(login)
    if a and a.password and check_password(password, a.password):
        tok = _issue_token(a)
        print(f"[retendo] login OK {a.user_id} pid={a.pid}", flush=True)
        return _xml(_oauth_xml(tok.access_token, tok.refresh_token))
    if a:
        print(f"[retendo] login FAILED {login}", flush=True)
        return _xml(INVALID_PW, 401)
    # Unknown account: keep the old fabricated session working.
    return _xml(_oauth_xml(FALLBACK_ACCESS, FALLBACK_REFRESH))


def _identify_rt(rt):
    return rt.account, rt.access_token


@retendo.route("/v1/api/people", methods=["POST"])
def people_register():
    user_id = request.values.get("user_id") or request.values.get("username", "")
    password = request.values.get("password", "")
    email = request.values.get("email", "")
    if not user_id or not password:
        return _xml(INVALID_PW, 400)
    if find_account(user_id):
        return _xml(INVALID_PW, 409)
    birth = None
    if request.values.get("birth_date"):
        try:
            birth = datetime.date.fromisoformat(request.values["birth_date"])
        except ValueError:
            birth = None
    a = create_account(
        user_id, password, email=email,
        country=request.values.get("country", "US"),
        language=request.values.get("language", "en"),
        mii_name=request.values.get("mii_name", "Player"),
        gender=request.values.get("gender", "M"),
        birth_date=birth,
    )
    print(f"[retendo] created {a.user_id} pid={a.pid}", flush=True)
    return _xml(_profile_xml(a), 201)


@retendo.route("/v1/api/people/@me/profile", methods=["GET"])
def people_profile():
    a, _ = _identify()
    if a:
        return _xml(_profile_xml(a))
    return _xml(FALLBACK_PROFILE)


@retendo.route("/v1/api/provider/service_token", methods=["GET"])
@retendo.route("/v1/api/provider/service_token/@me", methods=["GET"])
def service_token():
    a, _ = _identify()
    if a:
        tok = _issue_token(a)
        return _xml(_service_xml(tok.service_token))
    return _xml(_service_xml(FALLBACK_SERVICE))


@retendo.route("/v1/api/<path:rest>", methods=["GET", "POST", "PUT", "DELETE"])
def account_catchall(rest):
    # e.g. people/@me/devices/@current/attributes -> 404 = "no attributes".
    return _xml(NOT_FOUND, 404)


# --------------------------------------------------------------------------
# Web pages (console webview + browser)
# --------------------------------------------------------------------------

_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ReTendo Account</title>
<style>
body{font-family:sans-serif;background:#1b1b1f;color:#eee;margin:0;padding:24px}
.card{max-width:420px;margin:40px auto;background:#2a2a31;padding:24px;border-radius:12px}
h1{color:#ff6a00;font-size:20px;margin-top:0}
label{display:block;margin:12px 0 4px;font-size:13px;color:#bbb}
input{width:100%;padding:10px;border-radius:8px;border:1px solid #444;background:#1b1b1f;color:#eee;box-sizing:border-box}
button{margin-top:18px;width:100%;padding:12px;border:0;border-radius:8px;background:#ff6a00;color:#fff;font-size:15px;font-weight:bold}
.err{color:#ff6b6b;margin-top:12px}
.ok{color:#5bd66f;margin-top:12px;word-break:break-all}
a{color:#ff9d5c}
</style></head><body><div class="card">{{ body|safe }}</div></body></html>"""


def _page(body):
    return render_template_string(_PAGE, body=body)


@retendo.route("/", methods=["GET"])
def index():
    return redirect("/signup")


@retendo.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        user_id = request.form.get("user_id", "").strip()
        password = request.form.get("password", "")
        email = request.form.get("email", "").strip()
        if not user_id or not password:
            return _page('<h1>Create ReTendo ID</h1>'
                         '<form method="post"><label>User ID</label>'
                         '<input name="user_id"><label>Password</label>'
                         '<input type="password" name="password">'
                         '<label>Email (optional)</label><input name="email">'
                         '<button>Create</button></form>'
                         '<div class="err">User ID and password are required.</div>')
        if find_account(user_id):
            return _page('<h1>Create ReTendo ID</h1>'
                         '<div class="err">That user ID is taken.</div>'
                         '<p><a href="/signup">Try again</a></p>')
        a = create_account(user_id, password, email=email,
                           mii_name=request.form.get("mii_name", user_id))
        tok = _issue_token(a)
        print(f"[retendo] web signup {a.user_id} pid={a.pid}", flush=True)
        return _page(f'<h1>Welcome, {a.user_id}!</h1>'
                     f'<p class="ok">ReTendo ID created (pid {a.pid}).</p>'
                     f'<p>access token:<br>{tok.access_token}</p>')
    return _page('<h1>Create ReTendo ID</h1>'
                 '<form method="post"><label>User ID</label>'
                 '<input name="user_id"><label>Password</label>'
                 '<input type="password" name="password">'
                 '<label>Email (optional)</label><input name="email">'
                 '<label>Mii name (optional)</label><input name="mii_name">'
                 '<button>Create</button></form>')


@retendo.route("/login", methods=["GET", "POST"])
def login():
    err = ""
    if request.method == "POST":
        a = find_account(request.form.get("user_id", "").strip())
        if a and a.password and check_password(request.form.get("password", ""), a.password):
            tok = _issue_token(a)
            return _page(f'<h1>Signed in as {a.user_id}</h1>'
                         f'<p class="ok">pid {a.pid}</p>'
                         f'<p>access token:<br>{tok.access_token}</p>')
        err = '<div class="err">Invalid user ID or password.</div>'
    return _page('<h1>Sign in to ReTendo</h1>'
                 '<form method="post"><label>User ID</label>'
                 '<input name="user_id"><label>Password</label>'
                 '<input type="password" name="password">'
                 '<button>Sign in</button></form>' + err)


@retendo.route("/v1/api/oauth20/authorize", methods=["GET", "POST"])
def authorize():
    """The console's webview lands here to link an NNID.

    On success we bounce back to redirect_uri with ?code=<access_token>&state=.
    """
    redirect_uri = request.values.get("redirect_uri", "")
    state = request.values.get("state", "")
    if request.method == "POST":
        a = find_account(request.form.get("user_id", "").strip())
        if a and a.password and check_password(request.form.get("password", ""), a.password):
            tok = _issue_token(a)
            if redirect_uri:
                sep = "&" if "?" in redirect_uri else "?"
                return redirect(f"{redirect_uri}{sep}code={tok.access_token}&state={state}")
            return _page(f'<h1>Linked {a.user_id}</h1>'
                         f'<p class="ok">code: {tok.access_token}</p>')
        err = '<div class="err">Invalid user ID or password.</div>'
    else:
        err = ""
    hidden = (f'<input type="hidden" name="redirect_uri" value="{redirect_uri}">'
              f'<input type="hidden" name="state" value="{state}">')
    return _page('<h1>Link this console</h1>'
                 '<form method="post">' + hidden +
                 '<label>User ID</label><input name="user_id">'
                 '<label>Password</label><input type="password" name="password">'
                 '<button>Link</button></form>' +
                 '<p><a href="/signup">Create a new ID</a></p>' + err)
