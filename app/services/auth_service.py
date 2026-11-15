"""Registration, authentication, profile and account lifecycle."""

from __future__ import annotations

from datetime import timedelta

from flask import current_app

from app.extensions import db
from app.models import User
from app.models.entities import utcnow
from app.security.passwords import hash_password, needs_rehash, password_problems, verify_password
from app.services.audit_service import audit

MAX_FAILED = 5
LOCK_MINUTES = 15


class AuthError(Exception):
    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.field = field


def normalise_email(email: str) -> str:
    return (email or "").strip().lower()


def get_user_by_email(email: str) -> User | None:
    return db.session.scalar(
        db.select(User).filter_by(email=normalise_email(email)).where(User.deleted_at.is_(None))
    )


def register_user(email: str, full_name: str, password: str, role: str = "user") -> User:
    email = normalise_email(email)
    full_name = " ".join((full_name or "").split())
    problems = password_problems(password, email, full_name)
    if problems:
        raise AuthError(" ".join(problems), field="password")
    if db.session.scalar(db.select(User.id).filter_by(email=email)) is not None:
        # Same wording whether or not the account is deleted; avoids revealing account state.
        raise AuthError("There's already an account with this email. Try logging in instead.",
                        field="email")
    user = User(email=email, full_name=full_name, password_hash=hash_password(password), role=role)
    db.session.add(user)
    db.session.commit()
    audit("register", user, "user", user.public_id)
    return user


def authenticate(email: str, password: str) -> User:
    """Returns the user or raises AuthError with a deliberately generic message."""
    generic = AuthError("That email or password isn't right. Please try again.")
    user = get_user_by_email(email)
    now = utcnow()

    if user is None:
        verify_password(None, password)  # equalise timing
        audit("login_fail", None, details={"reason": "unknown_email"})
        raise generic
    if user.locked_until and user.locked_until > now:
        audit("login_blocked_locked", user, "user", user.public_id)
        raise AuthError(f"Too many wrong tries. Please wait {LOCK_MINUTES} minutes and try again.")
    if not verify_password(user.password_hash, password):
        user.failed_logins = (user.failed_logins or 0) + 1
        if user.failed_logins >= MAX_FAILED:
            user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
            user.failed_logins = 0
            audit("account_locked", user, "user", user.public_id, commit=False)
        audit("login_fail", user, "user", user.public_id, details={"reason": "bad_password"})
        raise generic
    if not user.is_active:
        audit("login_blocked_inactive", user, "user", user.public_id)
        raise AuthError("This account has been switched off. Please contact the admin.")

    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    audit("login_ok", user, "user", user.public_id)
    return user


def load_user_from_session(session_id: str) -> User | None:
    try:
        public_id, version = session_id.rsplit(".", 1)
        version = int(version)
    except (ValueError, AttributeError):
        return None
    user = db.session.scalar(db.select(User).filter_by(public_id=public_id))
    if user is None or user.auth_version != version or not user.is_active:
        return None
    return user


def update_profile(user: User, full_name: str, birth_year: int | None, sex: str | None,
                   skin_type: int | None) -> None:
    user.full_name = " ".join(full_name.split())
    user.birth_year = birth_year
    user.sex = sex or None
    user.skin_type = skin_type
    db.session.commit()
    audit("profile_update", user, "user", user.public_id)


def change_password(user: User, current: str | None, new: str) -> None:
    """Change (or, for a Google-only account, set) the password."""
    if user.has_password:
        if not current:
            raise AuthError("Please enter your current password.", field="current_password")
        if not verify_password(user.password_hash, current):
            raise AuthError("Your current password isn't right.", field="current_password")
    problems = password_problems(new, user.email, user.full_name)
    if problems:
        raise AuthError(" ".join(problems), field="new_password")
    if verify_password(user.password_hash, new):
        raise AuthError("Please choose a password that's different from your current one.", field="new_password")
    user.password_hash = hash_password(new)
    user.auth_version += 1  # signs out every other session
    db.session.commit()
    audit("password_change", user, "user", user.public_id)


def delete_account(user: User, password: str) -> None:
    """Deletes the user's images from disk immediately and anonymises the account row."""
    from app.services.image_service import delete_image_files

    if user.has_password:  # Google-only accounts confirm by typing DELETE (they're already logged in)
        if not password:
            raise AuthError("Please enter your password to confirm.", field="password")
        if not verify_password(user.password_hash, password):
            raise AuthError("That password isn't right.", field="password")
    now = utcnow()
    for image in user.images:
        delete_image_files(image)
        image.deleted_at = image.deleted_at or now
    for pred in user.predictions:
        pred.deleted_at = pred.deleted_at or now
    audit("account_delete", user, "user", user.public_id, commit=False)
    user.deleted_at = now
    user.is_active_flag = False
    user.email = f"deleted-{user.public_id}@invalid.local"
    user.full_name = "Deleted user"
    user.birth_year = user.sex = user.skin_type = None
    user.password_hash = "!deleted"
    user.google_sub = None
    user.auth_version += 1
    db.session.commit()
    current_app.logger.info("account deleted: %s", user.public_id)
