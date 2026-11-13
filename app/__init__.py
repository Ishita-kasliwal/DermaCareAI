"""Application factory."""

from __future__ import annotations

import logging
from datetime import timedelta

from flask import Flask, jsonify, render_template, request
from flask_login import current_user
from flask_wtf.csrf import CSRFError

from app.config import get_config
from app.extensions import csrf, db, limiter, login_manager, migrate, talisman

# Strict CSP: same-origin scripts/styles only (Chart.js is vendored in /static). No inline code.
CSP = {
    "default-src": "'self'",
    "img-src": ["'self'", "data:", "blob:"],  # blob: for the local file preview before upload
    "script-src": "'self'",
    "style-src": "'self'",
    "font-src": "'self'",
    "connect-src": "'self'",
    "object-src": "'none'",
    "frame-ancestors": "'none'",
    "base-uri": "'self'",
    "form-action": "'self'",
}

ERROR_TEXT = {
    400: ("Something didn't work", "The form may have expired. Please go back, refresh the page and try again."),
    403: ("Sorry, you can't open this page", "This page is only for certain accounts. If you think this is a mistake, contact the admin."),
    404: ("We can't find that page", "It may have moved, or it isn't available on your account."),
    405: ("That action isn't allowed here", "Please go back and try again from the page."),
    413: ("That file is too big", "Please choose a smaller photo."),
    429: ("Too many tries", "You've tried a lot in a short time. Please wait a minute and try again."),
    500: ("Something went wrong on our side", "We've noted the problem. Please try again in a moment."),
}


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(get_config(config_name))
    app.permanent_session_lifetime = timedelta(seconds=app.config["PERMANENT_SESSION_LIFETIME"])

    if not app.config.get("SECRET_KEY") or app.config["SECRET_KEY"] == "change-me":
        raise RuntimeError("SECRET_KEY is missing. Set it in the project .env file.")
    if not app.debug and not app.testing:
        logging.basicConfig(level=logging.INFO)

    if app.config.get("TRUST_PROXY"):
        # Behind cloudflared: use X-Forwarded-For / -Proto from exactly N trusted proxies, so rate limits,
        # lockouts and audit IP hashes see the real visitor, not 127.0.0.1. The app itself only listens on
        # 127.0.0.1, so these headers can only come from the local tunnel.
        from werkzeug.middleware.proxy_fix import ProxyFix

        n = int(app.config["TRUST_PROXY"])
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n)

    _init_extensions(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_hooks(app)

    from app.cli import register_cli

    register_cli(app)
    return app


def _init_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_message = "Please log in to continue."
    login_manager.login_message_category = "info"
    limiter.init_app(app)
    talisman.init_app(
        app,
        content_security_policy=CSP,
        force_https=app.config["FORCE_HTTPS"],
        strict_transport_security=app.config["FORCE_HTTPS"],
        session_cookie_secure=app.config["SESSION_COOKIE_SECURE"],
        referrer_policy="strict-origin-when-cross-origin",
        permissions_policy={"camera": "()", "geolocation": "()", "microphone": "()"},
    )

    from app.services.auth_service import load_user_from_session

    @login_manager.user_loader
    def load_user(session_id: str):
        return load_user_from_session(session_id)


def _register_blueprints(app: Flask) -> None:
    from app.blueprints.account import bp as account_bp
    from app.blueprints.admin import bp as admin_bp
    from app.blueprints.api import bp as api_bp
    from app.blueprints.api.routes import health
    from app.blueprints.auth import bp as auth_bp
    from app.blueprints.history import bp as history_bp
    from app.blueprints.main import bp as main_bp
    from app.blueprints.predict import bp as predict_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(account_bp, url_prefix="/account")
    app.register_blueprint(predict_bp)
    app.register_blueprint(history_bp, url_prefix="/history")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(api_bp, url_prefix="/api/v1")
    app.add_url_rule("/health", endpoint="health", view_func=health)
    limiter.exempt(health)


def _wants_json() -> bool:
    return request.path.startswith("/api/")


def _register_error_handlers(app: Flask) -> None:
    def render_error(code: int, detail: str | None = None):
        title, text = ERROR_TEXT.get(code, ERROR_TEXT[500])
        if _wants_json():
            return jsonify(error=title), code
        return render_template("error.html", code=code, title=title, text=detail or text), code

    for code in ERROR_TEXT:
        app.register_error_handler(code, lambda e, c=code: render_error(c))

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        return render_error(400, "This page was open for a while, so the form expired. Please refresh the page and try again.")

    @app.errorhandler(413)
    def too_large(e):
        return render_error(413, f"Your photo is bigger than {app.config['MAX_UPLOAD_MB']} MB (the upload limit). Please choose a smaller photo.")


def _register_hooks(app: Flask) -> None:
    @app.after_request
    def no_store_for_private_pages(resp):
        if current_user.is_authenticated and "Cache-Control" not in resp.headers:
            resp.headers["Cache-Control"] = "private, no-store"
        return resp

    @app.context_processor
    def inject_globals():
        from datetime import date

        return {"current_year": date.today().year, "brand": app.config["BRAND_NAME"]}

    def _as_dt(value):
        from datetime import datetime

        if value is None or value == "":
            return None
        return datetime.fromisoformat(value) if isinstance(value, str) else value

    @app.template_filter("datefmt")
    def datefmt(value):
        d = _as_dt(value)
        return f"{d.day} {d:%b %Y}" if d else "—"

    @app.template_filter("datetimefmt")
    def datetimefmt(value):
        d = _as_dt(value)
        return f"{d.day} {d:%b %Y, %H:%M} UTC" if d else "—"

    @app.template_filter("pct")
    def pct(value, digits: int = 0):
        if value is None:
            return "—"
        return f"{float(value) * 100:.{digits}f}%"
