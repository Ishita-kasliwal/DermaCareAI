"""Password reset: signed, time-limited, single-use links + optional email delivery.

Token = itsdangerous signature over {user public_id, auth_version, fingerprint of the current password hash}.
- time-limited: max_age (1 h for self-service email links, 24 h for admin-issued links)
- single-use: a successful reset changes the hash and bumps auth_version, so the old token stops matching
- revoked automatically by any other password change or account (de)activation
No token is stored in the database. Plaintext passwords and tokens are never logged.
"""

from __future__ import annotations

import hashlib
import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.extensions import db
from app.models import User
from app.security.passwords import hash_password, password_problems, verify_password
from app.services.audit_service import audit

SALT = "dermacareai-password-reset-v1"
SELF_SERVICE_MAX_AGE = 60 * 60          # 1 hour
ADMIN_LINK_MAX_AGE = 24 * 60 * 60       # 24 hours


class ResetError(Exception):
    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.field = field


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=SALT)


def _fingerprint(user: User) -> str:
    return hashlib.sha256((user.password_hash or "").encode()).hexdigest()[:16]


def make_token(user: User, max_age: int) -> str:
    return _serializer().dumps({"u": user.public_id, "v": user.auth_version, "h": _fingerprint(user), "m": max_age})


def reset_url(user: User, max_age: int = SELF_SERVICE_MAX_AGE) -> str:
    return url_for("auth.reset_password", token=make_token(user, max_age), _external=True)


def user_from_token(token: str) -> User:
    """Return the user for a valid token, or raise ResetError with a friendly message."""
    s = _serializer()
    try:
        # outer bound = the longest allowed lifetime; the per-token limit ("m") is checked below
        data, ts = s.loads(token, max_age=ADMIN_LINK_MAX_AGE, return_timestamp=True)
    except SignatureExpired:
        raise ResetError("This reset link has expired. Please ask for a new one.") from None
    except BadSignature:
        raise ResetError("This reset link isn't valid. Please ask for a new one.") from None
    # measure age with the same clock the signature check uses (one source of truth for "now")
    age = s.make_signer().get_timestamp() - ts.timestamp()
    if age > int(data.get("m", SELF_SERVICE_MAX_AGE)):
        raise ResetError("This reset link has expired. Please ask for a new one.")
    user = db.session.scalar(db.select(User).filter_by(public_id=data.get("u")).where(User.deleted_at.is_(None)))
    if user is None or not user.is_active or user.auth_version != data.get("v") or _fingerprint(user) != data.get("h"):
        raise ResetError("This reset link has already been used or is no longer valid. Please ask for a new one.")
    return user


def reset_password(token: str, new_password: str) -> User:
    user = user_from_token(token)
    problems = password_problems(new_password, user.email, user.full_name)
    if problems:
        raise ResetError(" ".join(problems), field="password")
    if verify_password(user.password_hash, new_password):
        raise ResetError("Please choose a password that's different from your old one.", field="password")
    user.password_hash = hash_password(new_password)
    user.auth_version += 1          # invalidates this link and signs out every session
    user.failed_logins = 0
    user.locked_until = None
    db.session.commit()
    audit("password_reset_done", user, "user", user.public_id)
    return user


# ---------------------------------------------------------------- email (optional)
def mail_configured() -> bool:
    c = current_app.config
    return bool(c.get("MAIL_SERVER") and c.get("MAIL_FROM"))


def send_reset_email(user: User) -> bool:
    """Send the reset link by email if SMTP is configured. Never raises to the caller."""
    if not mail_configured():
        return False
    c = current_app.config
    brand = c.get("BRAND_NAME", "DermaCareAI")
    msg = EmailMessage()
    msg["Subject"] = f"Reset your {brand} password"
    msg["From"] = c["MAIL_FROM"]
    msg["To"] = user.email
    msg.set_content(
        f"Hi {user.first_name},\n\n"
        f"Someone (hopefully you) asked to reset your {brand} password.\n"
        f"Open this link within 1 hour to choose a new password:\n\n{reset_url(user)}\n\n"
        "If you didn't ask for this, you can ignore this email. Your password won't change.\n"
    )
    try:
        port = int(c.get("MAIL_PORT") or 587)
        if c.get("MAIL_USE_SSL"):
            server = smtplib.SMTP_SSL(c["MAIL_SERVER"], port, context=ssl.create_default_context(), timeout=20)
        else:
            server = smtplib.SMTP(c["MAIL_SERVER"], port, timeout=20)
            server.starttls(context=ssl.create_default_context())
        with server:
            if c.get("MAIL_USERNAME"):
                server.login(c["MAIL_USERNAME"], c.get("MAIL_PASSWORD") or "")
            server.send_message(msg)
        return True
    except Exception as exc:  # noqa: BLE001 - never reveal mail errors to the visitor
        current_app.logger.warning("password reset email failed: %s", exc.__class__.__name__)
        return False
