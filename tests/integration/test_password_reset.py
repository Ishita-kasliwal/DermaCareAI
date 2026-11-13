"""Forgotten password: no account fishing, signed single-use time-limited links, admin-issued links."""

import re
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models import AuditLog, User
from app.services.password_reset import make_token, reset_url
from tests.conftest import PASSWORD, login

NEW = "Fresh-Dermis-Pass-8"


def _token_from(link: str) -> str:
    return re.search(r"/auth/reset/([^\"'\s<]+)", link).group(1)


def test_login_page_links_to_forgot(client):
    assert b"/auth/forgot" in client.get("/auth/login").data


def test_forgot_shows_same_message_for_known_and_unknown_email(client, user):
    a = client.post("/auth/forgot", data={"email": "alice@example.com"})
    b = client.post("/auth/forgot", data={"email": "nobody@example.com"})
    assert a.status_code == b.status_code == 200
    strip = lambda html: re.sub(rb'name="csrf_token"[^>]*>', b"", html)  # noqa: E731
    assert strip(a.data) == strip(b.data), "response must not reveal whether the account exists"
    assert db.session.scalar(db.select(db.func.count(AuditLog.id)).filter_by(
        action="password_reset_requested", user_id=user.id)) == 1


def test_reset_link_changes_password_and_is_single_use(app, client, user):
    other = app.test_client()
    login(other)                                   # a session that must be signed out by the reset
    token = make_token(user, 3600)
    assert client.get(f"/auth/reset/{token}").status_code == 200
    r = client.post(f"/auth/reset/{token}", data={"password": NEW, "confirm": NEW})
    assert r.status_code == 302 and "/auth/login" in r.headers["Location"]
    assert login(client, password=NEW).status_code == 302
    assert login(app.test_client(), password=PASSWORD).status_code == 401
    assert other.get("/dashboard").status_code == 302, "existing sessions are signed out"
    again = client.post(f"/auth/reset/{token}", data={"password": "Another-Pass-99", "confirm": "Another-Pass-99"})
    assert again.status_code == 400 and b"already been used" in again.data


def test_tampered_and_expired_links_rejected(app, client, user, monkeypatch):
    token = make_token(user, 3600)
    bad = client.get(f"/auth/reset/{token[:-3]}xyz")
    assert bad.status_code == 400 and b"isn&#39;t valid" in bad.data
    import itsdangerous.timed as timed

    future = datetime.now(timezone.utc) + timedelta(hours=2)
    monkeypatch.setattr(timed.TimestampSigner, "get_timestamp", lambda self: int(future.timestamp()))
    old = client.get(f"/auth/reset/{token}")
    assert old.status_code == 400 and b"expired" in old.data


def test_reset_enforces_password_policy(client, user):
    token = make_token(user, 3600)
    r = client.post(f"/auth/reset/{token}", data={"password": "short", "confirm": "short"})
    assert r.status_code == 400 and b"at least 10" in r.data
    r = client.post(f"/auth/reset/{token}", data={"password": PASSWORD, "confirm": PASSWORD})
    assert r.status_code == 400 and b"different from your old one" in r.data


def test_reset_unlocks_a_locked_account(client, user):
    for _ in range(5):
        login(client, password="wrong-password-1")
    token = make_token(db.session.get(User, user.id), 3600)
    client.post(f"/auth/reset/{token}", data={"password": NEW, "confirm": NEW})
    assert login(client, password=NEW).status_code == 302


def test_admin_can_issue_link_regular_user_cannot(app, client, user, other_user, admin):
    login(client)
    assert client.post(f"/admin/users/{other_user.public_id}/reset-link").status_code == 403
    c = app.test_client()
    login(c, "admin@example.com")
    client.post("/auth/logout")
    app.test_client().post("/auth/forgot", data={"email": "bob@example.com"})
    assert b"Asked for reset" in c.get("/admin/users").data
    r = c.post(f"/admin/users/{other_user.public_id}/reset-link")
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store"
    token = _token_from(r.data.decode())
    bob = app.test_client()
    assert bob.post(f"/auth/reset/{token}", data={"password": NEW, "confirm": NEW}).status_code == 302
    assert login(bob, "bob@example.com", NEW).status_code == 302
    assert b"Asked for reset" not in c.get("/admin/users").data
    actions = {a for (a,) in db.session.execute(db.select(AuditLog.action))}
    assert {"admin_reset_link_created", "password_reset_done"} <= actions


def test_admin_link_lasts_24h_but_email_link_only_1h(app, user):
    with app.test_request_context():
        assert "/auth/reset/" in reset_url(user)
    import itsdangerous.timed as timed

    real = timed.TimestampSigner.get_timestamp
    short, long_ = make_token(user, 3600), make_token(user, 24 * 3600)
    try:
        timed.TimestampSigner.get_timestamp = lambda self: int(real(self) + 2 * 3600)
        c = app.test_client()
        assert c.get(f"/auth/reset/{short}").status_code == 400
        assert c.get(f"/auth/reset/{long_}").status_code == 200
    finally:
        timed.TimestampSigner.get_timestamp = real
