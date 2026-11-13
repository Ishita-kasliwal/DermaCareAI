"""Public mode (behind the Cloudflare tunnel): real visitor IPs and secure cookies."""

from app import create_app
from app.config import TestingConfig
from app.extensions import db as _db
from app.services.catalog import seed_disease_classes


def _public_app(monkeypatch, tmp_path, trust=1):
    monkeypatch.setattr(TestingConfig, "TRUST_PROXY", trust)
    monkeypatch.setattr(TestingConfig, "SESSION_COOKIE_SECURE", True)
    monkeypatch.setattr(TestingConfig, "RATELIMIT_ENABLED", True)
    app = create_app("testing")
    app.config["UPLOAD_DIR"] = tmp_path
    return app


def test_rate_limit_is_per_real_visitor_behind_proxy(monkeypatch, tmp_path):
    app = _public_app(monkeypatch, tmp_path)
    with app.app_context():
        _db.create_all()
        seed_disease_classes(_db)
        c = app.test_client()

        def attempt(ip):
            return c.post("/auth/login", data={"email": "x@example.com", "password": "y"},
                          headers={"X-Forwarded-For": ip}).status_code

        first = [attempt("203.0.113.1") for _ in range(6)]
        other = attempt("198.51.100.7")   # a different visitor is NOT blocked by the first one
        _db.drop_all()
    assert first[:5] == [401] * 5 and first[5] == 429
    assert other == 401


def test_secure_cookie_and_https_scheme_in_public_mode(monkeypatch, tmp_path):
    app = _public_app(monkeypatch, tmp_path)
    app.config["WTF_CSRF_ENABLED"] = True  # the login form then stores its CSRF token in the session cookie
    with app.app_context():
        _db.create_all()
        c = app.test_client()
        r = c.get("/auth/login", headers={"X-Forwarded-Proto": "https"})
        _db.drop_all()
    cookie = r.headers.get("Set-Cookie", "")
    assert r.status_code == 200
    assert "Secure" in cookie and "HttpOnly" in cookie


def test_proxy_headers_ignored_when_not_in_public_mode(client):
    # default config: X-Forwarded-For must not be trusted (direct access only)
    r = client.get("/health", headers={"X-Forwarded-For": "1.2.3.4"})
    assert r.status_code == 200
    assert client.application.config["TRUST_PROXY"] == 0
