"""Security checks: CSRF, SQL injection, headers, secrets, password exposure, error handling."""

import re
import subprocess
from pathlib import Path

import pytest

from app.extensions import db
from app.models import User
from tests.conftest import PASSWORD, image_bytes, login

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def csrf_app(app):
    app.config["WTF_CSRF_ENABLED"] = True
    return app


def _token(html: bytes) -> str:
    m = re.search(rb'name="csrf_token" type="hidden" value="([^"]+)"', html) or \
        re.search(rb'name="csrf_token" value="([^"]+)"', html)
    assert m, "csrf token not rendered"
    return m.group(1).decode()


def test_csrf_enforced_on_state_changing_forms(csrf_app, user, active_model):
    c = csrf_app.test_client()
    assert c.post("/auth/login", data={"email": "alice@example.com", "password": PASSWORD}).status_code == 400
    assert c.post("/auth/register", data={"email": "z@example.com"}).status_code == 400
    token = _token(c.get("/auth/login").data)
    assert c.post("/auth/login", data={"email": "alice@example.com", "password": PASSWORD,
                                       "csrf_token": token}).status_code == 302
    # logged in now: every mutating endpoint refuses requests without a token
    for path, data in [("/auth/logout", {}), ("/account/", {"full_name": "Hacked"}),
                       ("/account/password", {}), ("/account/delete", {"password": PASSWORD, "confirm_text": "DELETE"}),
                       ("/analyze", {}), ("/history/abc/delete", {})]:
        r = c.post(path, data=data)
        assert r.status_code == 400, path
    db.session.refresh(user)
    assert user.full_name == "Alice Walker" and user.deleted_at is None
    assert c.get("/dashboard").status_code == 200, "logout without token did not log out"


def test_sql_injection_attempts_are_harmless(client, user):
    payloads = ["' OR '1'='1", "alice@example.com' --", "\" OR 1=1; DROP TABLE users; --", "%' OR 1=1 --"]
    for p in payloads:
        r = client.post("/auth/login", data={"email": p, "password": p})
        assert r.status_code in (400, 401), p
    assert client.get("/dashboard").status_code == 302
    login(client)
    for p in payloads:
        for q in (f"/history/?category={p}", f"/history/?status={p}", f"/history/?date_from={p}",
                  f"/results/{p}", f"/media/images/{p}"):
            assert client.get(q).status_code in (200, 404), q
    assert db.session.scalar(db.select(db.func.count(User.id))) == 1  # table intact


def test_security_headers(client):
    r = client.get("/")
    csp = r.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp and "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert "unsafe-inline" not in csp
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert "strict-origin" in r.headers["Referrer-Policy"]


def test_session_cookie_flags(client, user):
    r = login(client)
    cookie = r.headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie


def test_private_pages_not_cached(client, user):
    login(client)
    for path in ("/dashboard", "/history/", "/account/"):
        assert "no-store" in client.get(path).headers["Cache-Control"], path


def test_no_inline_scripts_or_styles_in_templates():
    for tpl in (ROOT / "app" / "templates").rglob("*.html"):
        text = tpl.read_text(encoding="utf-8")
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", text), f"inline <script> in {tpl.name}"
        assert " style=" not in text and "<style" not in text, f"inline style in {tpl.name}"
        assert not re.search(r"\son[a-z]+=", text), f"inline event handler in {tpl.name}"


def test_password_hash_never_rendered(client, user, admin):
    login(client, "admin@example.com")
    pages = [client.get(p).data for p in ("/admin/users", "/admin/", "/account/", "/admin/audit")]
    for html in pages:
        assert b"$argon2" not in html and PASSWORD.encode() not in html


def test_errors_do_not_leak_tracebacks(app, client):
    @app.get("/__boom")
    def boom():
        raise RuntimeError("secret internal detail")

    app.config["PROPAGATE_EXCEPTIONS"] = False
    r = client.get("/__boom")
    assert r.status_code == 500
    assert b"secret internal detail" not in r.data and b"Traceback" not in r.data
    assert b"Something went wrong" in r.data


def test_rate_limit_on_login(monkeypatch, tmp_path):
    """Build a separate app with rate limiting ON (it is off for the rest of the suite)."""
    from app import create_app
    from app.config import TestingConfig
    from app.extensions import db as _db
    from app.services.catalog import seed_disease_classes

    monkeypatch.setattr(TestingConfig, "RATELIMIT_ENABLED", True)
    rl_app = create_app("testing")
    rl_app.config["UPLOAD_DIR"] = tmp_path
    with rl_app.app_context():
        _db.create_all()
        seed_disease_classes(_db)
        c = rl_app.test_client()
        codes = [c.post("/auth/login", data={"email": "x@example.com", "password": "y"}).status_code
                 for _ in range(7)]
        _db.drop_all()
    assert codes[:5] == [401] * 5
    assert codes[5:] == [429, 429]


def test_secret_key_not_in_tracked_files():
    env = ROOT / ".env"
    if not env.exists():
        pytest.skip(".env not present")
    secret = next((ln.split("=", 1)[1].strip() for ln in env.read_text().splitlines()
                   if ln.startswith("SECRET_KEY=")), "")
    assert len(secret) >= 32, "SECRET_KEY should be long and random"
    skip_dirs = {".venv", ".git", "instance", "run", "ml/data", "ml/artifacts", "__pycache__", ".pytest_cache"}
    for p in ROOT.rglob("*"):
        rel = p.relative_to(ROOT).as_posix()
        if p.is_dir() or rel == ".env" or any(rel == d or rel.startswith(d + "/") for d in skip_dirs):
            continue
        if p.stat().st_size > 2_000_000:
            continue
        try:
            assert secret not in p.read_text(encoding="utf-8", errors="ignore"), rel
        except OSError:
            continue


def test_env_and_private_dirs_are_git_ignored():
    ignore = (ROOT / ".gitignore").read_text()
    for pattern in (".env", ".venv/", "instance/", "run/", "ml/data/*", "ml/artifacts/*", "*.keras" if "*.keras" in ignore else "*.pt"):
        assert pattern in ignore, pattern
    try:
        out = subprocess.run(["git", "check-ignore", ".env", "instance/uploads/x.jpg", "ml/data/raw/a.jpg"],
                             cwd=ROOT, capture_output=True, text=True)
    except FileNotFoundError:
        pytest.skip("git not available")
    if out.returncode == 128:
        pytest.skip("not a git repository yet")
    assert out.stdout.count("\n") == 3, out.stdout


def test_upload_rate_limit_key_is_per_user(client, user, active_model):
    login(client)
    r = client.post("/analyze", data={"image": (__import__("io").BytesIO(image_bytes()), "a.jpg"), "check_type": "lesion"},
                    content_type="multipart/form-data")
    assert r.status_code == 302
