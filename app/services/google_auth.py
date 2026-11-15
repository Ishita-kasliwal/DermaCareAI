"""Optional "Continue with Google" sign-in (OpenID Connect via Authlib).

Turned on only when GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are set. We ask Google only for the
person's name and email (scopes: openid email profile) and accept only emails Google has verified.
"""

from __future__ import annotations

from authlib.integrations.flask_client import OAuth
from flask import Flask, current_app

from app.extensions import db
from app.models import User
from app.models.entities import utcnow
from app.services.audit_service import audit
from app.services.auth_service import AuthError, normalise_email

GOOGLE_METADATA = "https://accounts.google.com/.well-known/openid-configuration"
NO_PASSWORD = "!google"  # marker: this account has no password (signs in with Google only)

oauth = OAuth()


def google_configured(app: Flask | None = None) -> bool:
    cfg = (app or current_app).config
    return bool(cfg.get("GOOGLE_CLIENT_ID") and cfg.get("GOOGLE_CLIENT_SECRET"))


def init_google(app: Flask) -> None:
    oauth.init_app(app)
    if google_configured(app):
        oauth.register(
            name="google",
            client_id=app.config["GOOGLE_CLIENT_ID"],
            client_secret=app.config["GOOGLE_CLIENT_SECRET"],
            server_metadata_url=GOOGLE_METADATA,
            client_kwargs={"scope": "openid email profile"},
        )


def client():
    return oauth.create_client("google")


def user_from_google(info: dict) -> User:
    """Find or create the account for a Google profile. Raises AuthError with a friendly message."""
    sub = str(info.get("sub") or "")
    email = normalise_email(info.get("email") or "")
    if not sub or not email:
        raise AuthError("Google didn't share your email with us, so we couldn't log you in.")
    if info.get("email_verified") is not True:
        raise AuthError("Your Google email isn't verified yet. Please verify it with Google, then try again.")

    user = db.session.scalar(db.select(User).filter_by(google_sub=sub))
    if user is None:
        user = db.session.scalar(db.select(User).filter_by(email=email))
        if user is not None and user.google_sub and user.google_sub != sub:
            raise AuthError("This email is already linked to a different Google account.")
    if user is not None and (user.deleted_at is not None or not user.is_active_flag):
        raise AuthError("This account is switched off. Please contact the site admin.")

    if user is None:
        name = " ".join(str(info.get("name") or email.split("@")[0]).split())[:120]
        user = User(email=email, full_name=name, password_hash=NO_PASSWORD, google_sub=sub)
        db.session.add(user)
        db.session.commit()
        audit("register", user, "user", user.public_id, details={"method": "google"})
    elif not user.google_sub:
        user.google_sub = sub  # same verified email: link Google to the existing account
        db.session.commit()
        audit("google_linked", user, "user", user.public_id)

    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = utcnow()
    db.session.commit()
    audit("login_ok", user, "user", user.public_id, details={"method": "google"})
    return user
