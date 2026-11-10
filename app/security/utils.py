"""Small security helpers."""

from __future__ import annotations

import hashlib
import hmac
from urllib.parse import urlsplit

from flask import current_app, request


def safe_next_url(target: str | None, default: str) -> str:
    """Only allow same-site relative redirects (prevents open redirects)."""
    if not target:
        return default
    target = target.strip().replace("\\", "/")
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not target.startswith("/") or target.startswith("//"):
        return default
    return target


def ip_hash() -> str | None:
    """Keyed hash of the client IP: lets us correlate abuse without storing raw IPs."""
    ip = request.remote_addr if request else None
    if not ip:
        return None
    key = (current_app.config["SECRET_KEY"] + "|ip").encode()
    return hmac.new(key, ip.encode(), hashlib.sha256).hexdigest()


def pseudonymous_key(value: str) -> str:
    key = (current_app.config["SECRET_KEY"] + "|export").encode()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()[:16]
