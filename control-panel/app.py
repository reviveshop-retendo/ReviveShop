"""ReviveShop Control Panel - a single web app to manage the 3DS, Wii U and Wii
revival servers from one place.

Run:  ./run.sh      (or)   .venv/bin/python control-panel/app.py
Open: http://<this-pc>:5001/
"""
import functools
import os

from flask import (Flask, Response, abort, flash, jsonify, redirect,
                   render_template, request, send_from_directory, session,
                   url_for)

import backends as B

app = Flask(__name__)
app.secret_key = os.environ.get("RS_PANEL_SECRET", "reviveshop-control-panel-dev")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024 * 1024  # 8 GiB CIA uploads
app.jinja_env.filters["human"] = B.human_size


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
def current_user():
    if not B.DJANGO_READY:
        return None
    from django.contrib.auth import get_user_model
    uid = session.get("uid")
    if not uid:
        return None
    try:
        return get_user_model().objects.get(pk=uid)
    except Exception:
        return None


def login_required(view):
    @functools.wraps(view)
    def wrapped(*a, **kw):
        if not session.get("uid"):
            return redirect(url_for("login", next=request.path))
        return view(*a, **kw)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    if not B.DJANGO_READY:
        return render_template("login.html", error="Backend not ready: " + B.DJANGO_ERROR)
    error = None
    if request.method == "POST":
        from django.contrib.auth import authenticate
        user = authenticate(username=request.form.get("username", ""),
                            password=request.form.get("password", ""))
        if user is None:
            error = "Wrong username or password."
        elif not (user.is_staff or user.is_superuser):
            error = "This account is not an administrator."
        else:
            session["uid"] = user.pk
            return redirect(request.args.get("next") or url_for("dashboard"))
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
@app.route("/")
@login_required
def dashboard():
    status = B.all_status()
    ctx = {"status": status, "active": "dashboard"}
    if B.DJANGO_READY:
        ctx["ds"] = B.ds_counts()
    else:
        ctx["ds_error"] = B.DJANGO_ERROR
    try:
        ctx["wiiu_count"] = sum(len(v) for v in B.wiiu_titles().values())
    except Exception:
        ctx["wiiu_count"] = "?"
    ctx["wii_titles"] = len(B.wii_titles()) if B.wii_available() else "?"
    return render_template("dashboard.html", **ctx)


# --------------------------------------------------------------------------- #
# 3DS
# --------------------------------------------------------------------------- #
@app.route("/3ds/news", methods=["GET", "POST"])
@login_required
def ds_news():
    if request.method == "POST":
        B.ds_save_news(None, request.form["title"], request.form["content"],
                       request.form.get("is_banner"), request.form.get("banner_url"),
                       request.form.get("publish_date"), request.form.get("expire_date"))
        flash("Announcement created.", "ok")
        return redirect(url_for("ds_news"))
    return render_template("news.html", items=B.ds_list_news(), active="news")


@app.route("/3ds/news/<int:pk>/edit", methods=["GET", "POST"])
@login_required
def ds_news_edit(pk):
    obj = B.ds_get_news(pk)
    if request.method == "POST":
        B.ds_save_news(pk, request.form["title"], request.form["content"],
                       request.form.get("is_banner"), request.form.get("banner_url"),
                       request.form.get("publish_date"), request.form.get("expire_date"))
        flash("Announcement saved.", "ok")
        return redirect(url_for("ds_news"))
    return render_template("news.html", items=B.ds_list_news(), edit=obj, active="news")


@app.route("/3ds/news/<int:pk>/delete", methods=["POST"])
@login_required
def ds_news_delete(pk):
    B.ds_delete_news(pk)
    flash("Announcement deleted.", "ok")
    return redirect(url_for("ds_news"))


@app.route("/3ds/spotpass", methods=["GET", "POST"])
@login_required
def ds_spotpass():
    if request.method == "POST":
        B.ds_save_spotpass(None, request.form["title"], request.form["message"],
                           request.form.get("image_url"))
        flash("SpotPass notification saved.", "ok")
        return redirect(url_for("ds_spotpass"))
    return render_template("spotpass.html", items=B.ds_list_spotpass(), active="spotpass")


@app.route("/3ds/spotpass/<int:pk>/edit", methods=["GET", "POST"])
@login_required
def ds_spotpass_edit(pk):
    obj = B.ds_get_spotpass(pk)
    if request.method == "POST":
        B.ds_save_spotpass(pk, request.form["title"], request.form["message"],
                           request.form.get("image_url"))
        flash("SpotPass notification saved.", "ok")
        return redirect(url_for("ds_spotpass"))
    return render_template("spotpass.html", items=B.ds_list_spotpass(), edit=obj,
                           active="spotpass")


@app.route("/3ds/spotpass/<int:pk>/publish", methods=["POST"])
@login_required
def ds_spotpass_publish(pk):
    B.ds_publish_spotpass(pk)
    flash("Published to SpotPass. The console picks it up on its next BOSS cycle.", "ok")
    return redirect(url_for("ds_spotpass"))


@app.route("/3ds/spotpass/unpublish", methods=["POST"])
@login_required
def ds_spotpass_unpublish():
    B.ds_unpublish_spotpass()
    flash("SpotPass notification unpublished.", "ok")
    return redirect(url_for("ds_spotpass"))


@app.route("/3ds/spotpass/<int:pk>/delete", methods=["POST"])
@login_required
def ds_spotpass_delete(pk):
    B.ds_delete_spotpass(pk)
    flash("SpotPass notification deleted.", "ok")
    return redirect(url_for("ds_spotpass"))


@app.route("/3ds/videos", methods=["GET", "POST"])
@login_required
def ds_videos():
    if request.method == "POST":
        B.ds_save_movie(None, request.form)
        flash("Video created.", "ok")
        return redirect(url_for("ds_videos"))
    return render_template("movies.html", items=B.ds_list_movies(),
                           cats=B.ds_list_lookup("category"), active="videos",
                           prefill={"name": request.args.get("name", ""),
                                    "moflex_url": request.args.get("moflex_url", ""),
                                    "time_in_sec": request.args.get("time_in_sec", "")})


@app.route("/3ds/videos/<int:pk>/edit", methods=["GET", "POST"])
@login_required
def ds_video_edit(pk):
    obj = B.ds_get_movie(pk)
    if request.method == "POST":
        B.ds_save_movie(pk, request.form)
        flash("Video saved.", "ok")
        return redirect(url_for("ds_videos"))
    return render_template("movies.html", items=B.ds_list_movies(),
                           cats=B.ds_list_lookup("category"), edit=obj, active="videos")


@app.route("/3ds/videos/<int:pk>/delete", methods=["POST"])
@login_required
def ds_video_delete(pk):
    B.ds_delete_movie(pk)
    flash("Video deleted.", "ok")
    return redirect(url_for("ds_videos"))


@app.route("/3ds/titles")
@login_required
def ds_titles():
    return render_template("titles.html", items=B.ds_list_titles(),
                           owned=B.ds_owned_map(), active="titles")


@app.route("/3ds/owned", methods=["GET", "POST"])
@login_required
def ds_owned():
    consoles = B.ds_list_consoles()
    if request.method == "POST":
        pk = request.form.get("title")
        target = request.form.get("console") or "all"
        grant = request.form.get("action") == "grant"
        B.ds_set_title_owned(pk, target, grant)
        flash(("Ownership granted." if grant else "Ownership revoked.")
              + ("" if target == "all" else " for console %s." % target), "ok")
        return redirect(url_for("ds_owned"))
    return render_template("owned.html", titles=B.ds_list_titles(),
                           consoles=consoles, owned=B.ds_owned_map(),
                           active="owned")


@app.route("/3ds/titles/<int:pk>/owned", methods=["POST"])
@login_required
def ds_title_owned(pk):
    target = request.form.get("console") or "all"
    grant = request.form.get("grant") == "1"
    B.ds_set_title_owned(pk, target, grant)
    flash(("“%s” is now owned." if grant else "“%s” is no longer owned.")
          % B.ds_get_title(pk).name, "ok")
    return redirect(request.form.get("next") or url_for("ds_owned"))


def _title_form_ctx(edit=None):
    return {
        "edit": edit,
        "pubs": B.ds_list_lookup("publisher"),
        "genres": B.ds_list_lookup("genre"),
        "platforms": B.ds_list_lookup("platform"),
        "cats": B.ds_list_lookup("category"),
        "cias": B.cia_list(),
        "attached": B.cdn_state_for_tid(edit.tid) if edit else None,
        "active": "titles",
    }


@app.route("/3ds/attach", methods=["POST"])
@login_required
def ds_title_attach():
    """Attach a stored (or freshly uploaded) CIA to a title, from the title form."""
    pk = request.form.get("pk") or ""
    name = request.form.get("name") or ""
    try:
        if not name:
            f = request.files.get("cia")
            if not f or not f.filename:
                flash("Pick a stored CIA or upload one first.", "err")
                return redirect(url_for("ds_title_new") if not pk
                                else url_for("ds_title_edit", pk=pk))
            name = os.path.basename(B.cia_store(f.stream, os.path.basename(f.filename)))
        rep = B.cia_attach(name, title_pk=pk or None)
    except Exception as e:
        flash("Attach failed: %s" % e, "err")
        return redirect(url_for("ds_title_new") if not pk
                        else url_for("ds_title_edit", pk=pk))

    note = ("rebuilt a stale TMD for %s" % ", ".join(rep["stale"])
            if rep["stale"] else "TMD already matched")
    flash("Attached “%s” to %s - %s, %s, %s (%s)." % (
        name, rep["tid"], rep["title"], rep["human"], note,
        "verified" if rep["verified"] else "NOT VERIFIED"), "ok")
    obj = B.m.Title.objects.filter(tid__iexact=rep["tid"]).first()
    if obj is not None:
        return redirect(url_for("ds_title_edit", pk=obj.pk))
    return redirect(url_for("ds_titles"))


@app.route("/3ds/titles/new", methods=["GET", "POST"])
@login_required
def ds_title_new():
    if request.method == "POST":
        B.ds_save_title(None, request.form)
        flash("Title created.", "ok")
        return redirect(url_for("ds_titles"))
    return render_template("title_edit.html", **_title_form_ctx())


@app.route("/3ds/titles/<int:pk>/edit", methods=["GET", "POST"])
@login_required
def ds_title_edit(pk):
    if request.method == "POST":
        B.ds_save_title(pk, request.form)
        flash("Title saved.", "ok")
        return redirect(url_for("ds_titles"))
    return render_template("title_edit.html", **_title_form_ctx(B.ds_get_title(pk)))


@app.route("/3ds/titles/<int:pk>/delete", methods=["POST"])
@login_required
def ds_title_delete(pk):
    B.ds_delete_title(pk)
    flash("Title deleted.", "ok")
    return redirect(url_for("ds_titles"))


@app.route("/3ds/cias", methods=["GET", "POST"])
@login_required
def cia_library():
    if request.method == "POST":
        f = request.files.get("cia")
        if not f or not f.filename:
            flash("Choose a .cia file first.", "err")
        else:
            try:
                dest = B.cia_store(f.stream, os.path.basename(f.filename))
                flash("Stored %s." % dest.name, "ok")
            except Exception as e:
                flash("Upload failed: %s" % e, "err")
        return redirect(url_for("cia_library"))
    return render_template("cias.html", cias=B.cia_list(),
                           report=None, verify=None, active="cias")


@app.route("/3ds/cias/attach", methods=["POST"])
@login_required
def cia_do_attach():
    name = request.form.get("name") or ""
    try:
        rep = B.cia_attach(name)
    except Exception as e:
        flash("Attach failed: %s" % e, "err")
        return redirect(url_for("cia_library"))
    note = ("rebuilt a stale TMD" if rep["stale"] else "TMD already matched")
    flash("Attached %s - %s, %s, %s (%s)." % (
        rep["tid"], rep["title"], rep["human"], note,
        "verified" if rep["verified"] else "NOT VERIFIED"), "ok")
    return render_template("cias.html", cias=B.cia_list(), report=rep,
                           verify=None, active="cias")


@app.route("/3ds/cias/verify", methods=["POST"])
@login_required
def cia_do_verify():
    name = request.form.get("name") or ""
    try:
        verify = B.cia_verify(name)
    except Exception as e:
        flash("Verify failed: %s" % e, "err")
        return redirect(url_for("cia_library"))
    if verify["ok"]:
        flash("%s: TMD matches its content." % verify["name"], "ok")
    else:
        bad = ", ".join(r["id"] for r in verify["contents"] if not r["match"])
        flash("%s: TMD does NOT match content for %s. Attaching will rebuild it."
              % (verify["name"], bad), "err")
    return render_template("cias.html", cias=B.cia_list(), report=None,
                           verify=verify, active="cias")


@app.route("/3ds/cias/delete", methods=["POST"])
@login_required
def cia_do_delete():
    name = request.form.get("name") or ""
    try:
        B.cia_delete(name)
        flash("Deleted %s." % name, "ok")
    except Exception as e:
        flash("Delete failed: %s" % e, "err")
    return redirect(url_for("cia_library"))


@app.route("/3ds/import", methods=["GET", "POST"])
@login_required
def ds_import():
    report = None
    if request.method == "POST":
        f = request.files.get("cia")
        if not f or not f.filename:
            flash("Choose a .cia file first.", "err")
        else:
            try:
                obj, report = B.ds_import_cia(f.stream, os.path.basename(f.filename))
                rep = report
                extra = ("rebuilt a stale TMD for %s" % ", ".join(rep["stale"])
                         if rep.get("stale") else "TMD already matched")
                flash(f"Imported {rep['tid']} ({len(rep['contents'])} contents, "
                      f"{rep['human']}, {extra}, kept as “{rep['stored']}”).", "ok")
            except Exception as e:
                flash(f"Import failed: {e}", "err")
    return render_template("import.html", report=report, cdn=B.ds_cdn_titles(), active="import")


@app.route("/3ds/cdn")
@login_required
def ds_cdn():
    return render_template("cdn.html", folders=B.ds_cdn_titles(), active="cdn")


META_SPECS = {
    "category": [("id", "ID", "int"), ("index", "Home index", "int"), ("name", "Name", "text"),
                 ("standard", "Standard", "bool"), ("icon_url", "Icon URL", "text"),
                 ("banner_url", "Banner URL", "text"), ("new", "New", "bool"),
                 ("order", "Order", "int")],
    "genre": [("id", "ID", "int"), ("name", "Name", "text")],
    "publisher": [("id", "ID", "int"), ("publisher_name", "Publisher", "text")],
    "platform": [("id", "ID", "int"), ("name", "Name", "text")],
    "motd": [("id", "ID", "int"), ("order", "Order", "int"), ("content", "Text", "text")],
}


def _coerce(spec, form):
    val = form.get(spec[0])
    if spec[2] == "bool":
        return spec[0] in form
    if val in (None, ""):
        return None if spec[2] == "int" else ""
    if spec[2] == "int":
        return int(val)
    return val


@app.route("/3ds/meta/<model_name>", methods=["GET", "POST"])
@login_required
def ds_meta(model_name):
    if model_name not in META_SPECS:
        abort(404)
    specs = META_SPECS[model_name]
    if request.method == "POST":
        pk = request.form.get("id") or None
        data = {s[0]: _coerce(s, request.form) for s in specs}
        B.ds_save_lookup(model_name, pk, data)
        flash(f"{model_name.title()} saved.", "ok")
        return redirect(url_for("ds_meta", model_name=model_name))
    rows = B.ds_rows(model_name, [s[0] for s in specs])
    return render_template("meta.html", model_name=model_name, specs=specs,
                           rows=rows, active=("ticker" if model_name == "motd" else "meta"))


@app.route("/3ds/meta/<model_name>/<pk>/delete", methods=["POST"])
@login_required
def ds_meta_delete(model_name, pk):
    if model_name not in META_SPECS:
        abort(404)
    B.ds_delete_lookup(model_name, pk)
    flash("Deleted.", "ok")
    return redirect(url_for("ds_meta", model_name=model_name))


@app.route("/3ds/consoles")
@login_required
def ds_consoles():
    return render_template("consoles.html", rows=B.ds_list_consoles(), active="consoles")


@app.route("/3ds/account")
@login_required
def ds_account():
    return render_template("account.html", consoles=B.ds_list_consoles(),
                           cards=B.ds_list_cards(), titles=B.ds_list_titles(),
                           title_names=B.ds_title_names_by_tid(),
                           web_base=B.web_base_url(), active="account")


@app.route("/3ds/account/<int:pk>/funds", methods=["POST"])
@login_required
def ds_account_funds(pk):
    try:
        amount = int(request.form.get("amount") or 0)
    except ValueError:
        amount = 0
    mode = "set" if request.form.get("mode") == "set" else "add"
    obj = B.ds_fund_console(pk, amount, mode)
    flash(f"{obj.consoleid}: balance is now {obj.balance} Credit.", "ok")
    return redirect(url_for("ds_account"))


@app.route("/3ds/account/card", methods=["POST"])
@login_required
def ds_account_card():
    code = (request.form.get("code") or "").strip().upper()
    if not code:
        code = B.gen_card_code()
    is_money = request.form.get("card_type") != "application"
    if is_money:
        content = request.form.get("amount") or 0
    else:
        content = (request.form.get("title_tid") or "").strip()
    try:
        card = B.ds_create_card(code, content, is_money)
        if card.is_money:
            flash(f"Money card {card.code} created for {card.content} Credit.", "ok")
        else:
            name = B.ds_title_names_by_tid().get(card.content, card.content)
            flash(f"Download code {card.code} created for \"{name}\".", "ok")
    except Exception as e:
        flash(f"Could not create card: {e}", "err")
    return redirect(url_for("ds_account"))


@app.route("/3ds/account/card/<int:pk>/qr.png")
@login_required
def ds_account_card_qr(pk):
    card = B.ds_get_card(pk)
    png = B.qr_png(B.redeem_code_url(card.code))
    headers = {"Cache-Control": "no-store"}
    if request.args.get("dl"):
        headers["Content-Disposition"] = f'attachment; filename="{card.code}.png"'
    return Response(png, mimetype="image/png", headers=headers)


@app.route("/3ds/codes")
@login_required
def ds_codes():
    cards = B.ds_list_cards()
    esh_links = {c.content: B.ds_esh_link(c.content) for c in cards if not c.is_money}
    return render_template("codes.html", cards=cards,
                           titles=B.ds_list_titles(),
                           title_names=B.ds_title_names_by_tid(),
                           esh_links=esh_links,
                           web_base=B.web_base_url(), active="codes")


@app.route("/3ds/qr.png")
@login_required
def ds_qr():
    data = request.args.get("data") or ""
    if not data:
        abort(400)
    png = B.qr_png(data)
    headers = {"Cache-Control": "no-store"}
    if request.args.get("dl"):
        base = "".join(ch for ch in data if ch.isalnum())[:24] or "qr"
        headers["Content-Disposition"] = f'attachment; filename="{base}.png"'
    return Response(png, mimetype="image/png", headers=headers)


@app.route("/3ds/account/card/<int:pk>/delete", methods=["POST"])
@login_required
def ds_account_card_delete(pk):
    B.ds_delete_card(pk)
    flash("Card deleted.", "ok")
    return redirect(url_for("ds_account"))


# --------------------------------------------------------------------------- #
# Ratings
# --------------------------------------------------------------------------- #
@app.route("/3ds/ratings")
@login_required
def ds_ratings():
    rows = B.ds_rating_rows()
    return render_template("ratings.html", rows=rows,
                           total_votes=sum(r["count"] for r in rows),
                           active="ratings")


@app.route("/3ds/ratings/vote/<int:pk>/delete", methods=["POST"])
@login_required
def ds_rating_vote_delete(pk):
    B.ds_delete_vote(pk)
    flash("Vote deleted.", "ok")
    return redirect(url_for("ds_ratings"))


@app.route("/3ds/ratings/title/<int:pk>/clear", methods=["POST"])
@login_required
def ds_ratings_clear(pk):
    n = B.ds_clear_title_votes(pk)
    flash(f"Cleared {n} vote{'s' if n != 1 else ''}.", "ok")
    return redirect(url_for("ds_ratings"))


@app.route("/3ds/ratings/clear", methods=["POST"])
@login_required
def ds_ratings_clear_all():
    n = B.ds_clear_all_votes()
    flash(f"Cleared {n} vote{'s' if n != 1 else ''}.", "ok")
    return redirect(url_for("ds_ratings"))


# --------------------------------------------------------------------------- #
# Title images (top image + upper/lower screenshots on the title detail page)
# --------------------------------------------------------------------------- #
@app.route("/3ds/images")
@login_required
def ds_images():
    pk = request.args.get("t", type=int)
    if pk:
        img = B.ds_title_images(pk)
        return render_template("title_images_edit.html", img=img, active="images")
    return render_template("title_images.html",
                           titles=B.ds_list_titles(),
                           counts=B.ds_titles_image_counts(),
                           active="images")


@app.route("/3ds/images/save", methods=["POST"])
@login_required
def ds_images_save():
    pk = request.form.get("t", type=int)
    B.ds_save_title_images(pk, request.form.get("top_image_url"),
                           request.form.get("upper_urls"),
                           request.form.get("lower_urls"))
    flash("Title images saved.", "ok")
    return redirect(url_for("ds_images", t=pk))


@app.route("/3ds/retendo")
@login_required
def ds_retendo():
    return render_template("retendo.html", accounts=B.ds_list_accounts(),
                           links=B.ds_list_links(),
                           consoles=B.ds_list_consoles(), active="retendo")


@app.route("/3ds/retendo/new", methods=["POST"])
@login_required
def ds_retendo_new():
    try:
        a = B.ds_create_account(request.form.get("user_id"),
                                request.form.get("password"),
                                email=request.form.get("email", ""),
                                mii_name=request.form.get("mii_name", ""))
        flash(f"ReTendo ID {a.user_id} created (pid {a.pid}).", "ok")
    except Exception as e:
        flash(f"Could not create account: {e}", "err")
    return redirect(url_for("ds_retendo"))


@app.route("/3ds/retendo/<int:pk>/password", methods=["POST"])
@login_required
def ds_retendo_password(pk):
    try:
        B.ds_set_account_password(pk, request.form.get("password"))
        flash("Password updated.", "ok")
    except Exception as e:
        flash(f"Could not update password: {e}", "err")
    return redirect(url_for("ds_retendo"))


@app.route("/3ds/retendo/<int:pk>/link", methods=["POST"])
@login_required
def ds_retendo_link(pk):
    try:
        B.ds_link_console(pk, request.form.get("console_pk"))
        flash("Console linked.", "ok")
    except Exception as e:
        flash(f"Could not link console: {e}", "err")
    return redirect(url_for("ds_retendo"))


@app.route("/3ds/retendo/link/<int:pk>/delete", methods=["POST"])
@login_required
def ds_retendo_unlink(pk):
    B.ds_delete_link(pk)
    flash("Link removed.", "ok")
    return redirect(url_for("ds_retendo"))


@app.route("/3ds/retendo/<int:pk>/delete", methods=["POST"])
@login_required
def ds_retendo_delete(pk):
    B.ds_delete_account(pk)
    flash("ReTendo account deleted.", "ok")
    return redirect(url_for("ds_retendo"))


# --------------------------------------------------------------------------- #
# Wii U
# --------------------------------------------------------------------------- #
@app.route("/wiiu")
@login_required
def wiiu():
    return render_template("wiiu.html", titles=B.wiiu_titles(), catalog=B.wiiu_catalog(),
                           status=B.all_status()["wiiu"], active="wiiu")


@app.route("/wiiu/title/new", methods=["POST"])
@login_required
def wiiu_title_new():
    try:
        B.wiiu_create_title(request.form["kind"], request.form["tid"])
        flash("Title folder created.", "ok")
    except Exception as e:
        flash(f"Error: {e}", "err")
    return redirect(url_for("wiiu"))


@app.route("/wiiu/title/<kind>/<tid>", methods=["GET", "POST"])
@login_required
def wiiu_title(kind, tid):
    if kind not in B.WIIU_KINDS:
        abort(404)
    if request.method == "POST":
        saved = B.wiiu_save_upload(kind, tid, request.files.getlist("files"))
        flash("Uploaded: " + ", ".join(saved) if saved else "No files selected.", "ok" if saved else "err")
        return redirect(url_for("wiiu_title", kind=kind, tid=tid))
    detail = B.wiiu_title_detail(kind, tid)
    if not detail:
        abort(404)
    return render_template("wiiu_title.html", d=detail, active="wiiu")


@app.route("/wiiu/title/<kind>/<tid>/delete", methods=["POST"])
@login_required
def wiiu_title_delete(kind, tid):
    B.wiiu_delete_title(kind, tid)
    flash("Title folder deleted.", "ok")
    return redirect(url_for("wiiu"))


@app.route("/wiiu/file/delete", methods=["POST"])
@login_required
def wiiu_file_delete():
    B.wiiu_delete_file(request.form["kind"], request.form["tid"], request.form["name"])
    flash("File deleted.", "ok")
    return redirect(url_for("wiiu_title", kind=request.form["kind"], tid=request.form["tid"]))


@app.route("/wiiu/catalog/add", methods=["POST"])
@login_required
def wiiu_catalog_add():
    B.wiiu_catalog_add(request.form["tid"], request.form["name"])
    flash("Catalog entry saved.", "ok")
    return redirect(url_for("wiiu"))


@app.route("/wiiu/catalog/remove", methods=["POST"])
@login_required
def wiiu_catalog_remove():
    B.wiiu_catalog_remove(request.form["tid"])
    flash("Catalog entry removed.", "ok")
    return redirect(url_for("wiiu"))


@app.route("/wiiu/control/<action>", methods=["POST"])
@login_required
def wiiu_control(action):
    ok, out = B.wiiu_control(action)
    flash(("OK: " if ok else "Failed: ") + out.strip()[-300:], "ok" if ok else "err")
    return redirect(url_for("wiiu"))


# --------------------------------------------------------------------------- #
# Wii
# --------------------------------------------------------------------------- #
@app.route("/wii")
@login_required
def wii():
    if not B.wii_available():
        flash("WiiMart Postgres (:5432) is not reachable — start the containers.", "err")
    return render_template("wii.html", titles=B.wii_titles(), accounts=B.wii_accounts(),
                           owned=B.wii_owned(), containers=B.wii_containers(), active="wii")


@app.route("/wii/titles/save", methods=["POST"])
@login_required
def wii_title_save():
    ok, out = B.wii_save_title(request.form.get("item_id"), request.form["price_code"],
                               request.form["price"], request.form["title_id"],
                               request.form.get("reference_id", ""))
    flash(("Saved." if ok else "Failed: " + out[-200:]), "ok" if ok else "err")
    return redirect(url_for("wii"))


@app.route("/wii/titles/<item_id>/delete", methods=["POST"])
@login_required
def wii_title_delete(item_id):
    ok, out = B.wii_delete_title(item_id)
    flash(("Deleted." if ok else "Failed: " + out[-200:]), "ok" if ok else "err")
    return redirect(url_for("wii"))


@app.route("/wii/control/<action>", methods=["POST"])
@login_required
def wii_control(action):
    ok, out = B.wii_control(action)
    flash(("OK: " if ok else "Failed: ") + out.strip()[-300:], "ok" if ok else "err")
    return redirect(url_for("wii"))


# --------------------------------------------------------------------------- #
# Services
# --------------------------------------------------------------------------- #
@app.route("/services")
@login_required
def services():
    return render_template("services.html", status=B.all_status(), logs=B.logs(), active="services")


@app.route("/services/<stack>/<action>", methods=["POST"])
@login_required
def service_control(stack, action):
    ok, out = B.stack_control(stack, action)
    flash(("OK: " if ok else "Failed: ") + (out or "").strip()[-400:], "ok" if ok else "err")
    return redirect(url_for("services"))


# --------------------------------------------------------------------------- #
# Maintenance
# --------------------------------------------------------------------------- #
@app.route("/maintenance", methods=["GET", "POST"])
@login_required
def maintenance():
    if request.method == "POST":
        enabled = request.form.get("enabled") == "1"
        ok, out = B.set_maintenance(enabled)
        flash(("OK: " if ok else "Failed: ") + out, "ok" if ok else "err")
        return redirect(url_for("maintenance"))
    return render_template("maintenance.html",
                           on=B.maintenance_status(), active="maintenance")


# --------------------------------------------------------------------------- #
# Image / asset hosting
# --------------------------------------------------------------------------- #
@app.route("/assets")
@login_required
def assets():
    return render_template("assets.html", items=B.list_assets(), base=B.asset_base_url(),
                           active="assets")


@app.route("/assets/upload", methods=["POST"])
@login_required
def asset_upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify(ok=False, error="no file supplied"), 400
    preset = request.form.get("preset") or ""
    if preset in B.IMAGE_PRESETS:
        w, h, _label = B.IMAGE_PRESETS[preset]
        try:
            info = B.resize_image(f.stream, f.filename, w, h, "cover", "#000000", "jpg", 92)
        except Exception as e:
            return jsonify(ok=False, error=str(e)), 400
        return jsonify(ok=True, name=info["name"], url=info["url"],
                       preview=url_for("asset_media", name=info["name"]),
                       resized=info["size"])
    try:
        name, url = B.save_asset(f.stream, f.filename)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400
    return jsonify(ok=True, name=name, url=url, preview=url_for("asset_media", name=name))


@app.route("/media/<path:name>")
@login_required
def asset_media(name):
    return send_from_directory(str(B.ASSET_DIR), os.path.basename(name))


@app.route("/assets/delete", methods=["POST"])
@login_required
def asset_delete():
    if B.delete_asset(request.form["name"]):
        flash("Asset deleted.", "ok")
    else:
        flash("Asset not found.", "err")
    return redirect(url_for("assets"))


@app.route("/3ds/videos/upload", methods=["POST"])
@login_required
def video_upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify(ok=False, error="no file supplied"), 400
    try:
        info = B.save_video(f.stream, f.filename)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400
    info["ok"] = True
    info["preview"] = url_for("asset_media", name=info["name"])
    return jsonify(**info)


@app.route("/3ds/videos/prepare", methods=["POST"])
@login_required
def video_prepare():
    try:
        name, human = B.prepare_video(request.form["name"], request.form.get("is_3d") == "on")
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400
    return jsonify(ok=True, name=name, human=human, url=B.asset_base_url() + name)


@app.route("/3ds/convert")
@login_required
def convert_page():
    return render_template("convert.html", layouts=B.MOFLEX_LAYOUTS,
                           available=B.moflex_available(), active="convert")


@app.route("/3ds/convert/start", methods=["POST"])
@login_required
def convert_start():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify(ok=False, error="no file supplied"), 400
    try:
        job = B.start_moflex_job(f.stream, f.filename,
                                 request.form.get("layout", "2d"),
                                 request.form.get("quality", "normal"))
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400
    return jsonify(ok=True, id=job["id"])


@app.route("/3ds/convert/status/<job_id>")
@login_required
def convert_status(job_id):
    job = B.get_moflex_job(job_id)
    if not job:
        return jsonify(ok=False, error="unknown job"), 404
    return jsonify(ok=True, **{k: job.get(k) for k in
             ("status", "message", "name", "url", "duration", "human",
              "error", "started", "finished")})


@app.route("/assets/resize")
@login_required
def assets_resize():
    return render_template("resize.html", presets=B.IMAGE_PRESETS, active="resize")


@app.route("/assets/resize/upload", methods=["POST"])
@login_required
def assets_resize_upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify(ok=False, error="no file supplied"), 400
    try:
        info = B.resize_image(f.stream, f.filename,
                              request.form.get("width") or 128,
                              request.form.get("height") or 96,
                              request.form.get("mode", "cover"),
                              request.form.get("bg", "#000000"),
                              request.form.get("fmt", "png"),
                              request.form.get("quality", 90))
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400
    info["ok"] = True
    info["preview"] = url_for("asset_media", name=info["name"])
    return jsonify(**info)


@app.route("/3ds/music")
@login_required
def ds_music():
    return render_template("music.html", items=B.bgm_list(),
                           available=B.bgm_available(), active="music")


@app.route("/3ds/music/upload", methods=["POST"])
@login_required
def ds_music_upload():
    f = request.files.get("file")
    if not f or not f.filename:
        flash("Choose an audio file first.", "err")
        return redirect(url_for("ds_music"))
    try:
        e = B.bgm_add(f.stream, os.path.basename(f.filename),
                      request.form.get("name", ""), request.form.get("begin", ""))
        flash(f"Added '{e['name']}' (begins {e['begin']}).", "ok")
    except Exception as e:
        flash(f"Upload failed: {e}", "err")
    return redirect(url_for("ds_music"))


@app.route("/3ds/music/<file>/save", methods=["POST"])
@login_required
def ds_music_save(file):
    try:
        B.bgm_save(file, request.form.get("name", ""), request.form.get("begin", ""))
        flash("Track saved.", "ok")
    except Exception as e:
        flash(f"Save failed: {e}", "err")
    return redirect(url_for("ds_music"))


@app.route("/3ds/music/<file>/delete", methods=["POST"])
@login_required
def ds_music_delete(file):
    if B.bgm_delete(file):
        flash("Track deleted.", "ok")
    else:
        flash("Track not found.", "err")
    return redirect(url_for("ds_music"))


if __name__ == "__main__":
    port = int(os.environ.get("RS_PANEL_PORT", "5001"))
    print(f"ReviveShop Control Panel on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
