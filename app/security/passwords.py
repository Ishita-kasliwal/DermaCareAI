"""Password hashing (Argon2id) and policy validation. Plaintext passwords are never stored or logged."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()  # Argon2id with library defaults (RFC 9106 low-memory profile)

# Hash of a random value, used to equalise timing when the account does not exist.
_DUMMY_HASH = _hasher.hash("timing-equaliser-not-a-real-password")

MIN_LENGTH = 10
MAX_LENGTH = 128

# Small deny-list of the most common passwords (>= MIN_LENGTH chars).
COMMON = {
    "1234567890", "12345678910", "123456789a", "qwertyuiop", "password12", "password123",
    "password1234", "iloveyou12", "qwerty1234", "1q2w3e4r5t", "abcdefghij", "0987654321",
    "1111111111", "aaaaaaaaaa", "letmein123", "welcome123", "adminadmin", "administrator",
    "passw0rd123", "football123", "sunshine123", "princess123", "qwertyuiop1", "zaq12wsxcde",
}


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(stored_hash or _DUMMY_HASH, password) and stored_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return True


def password_problems(password: str, email: str = "", name: str = "") -> list[str]:
    problems = []
    if len(password) < MIN_LENGTH:
        problems.append(f"Please use at least {MIN_LENGTH} characters.")
    if len(password) > MAX_LENGTH:
        problems.append(f"Please use no more than {MAX_LENGTH} characters.")
    lowered = password.lower()
    if lowered in COMMON or len(set(password)) < 4:
        problems.append("This password is too easy to guess. Please pick something less common.")
    local = email.split("@")[0].lower() if email else ""
    if local and len(local) >= 4 and local in lowered:
        problems.append("Please don't use your email in your password.")
    if name and len(name) >= 4 and name.lower().replace(" ", "") in lowered.replace(" ", ""):
        problems.append("Please don't use your name in your password.")
    return problems
