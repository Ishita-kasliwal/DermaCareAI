"""Audit trail for security-relevant events. Never records passwords, tokens or raw IPs."""

from __future__ import annotations

from flask import has_request_context

from app.extensions import db
from app.models import AuditLog
from app.security.utils import ip_hash


def audit(action: str, user=None, target_type: str | None = None, target_id: str | None = None,
          details: dict | None = None, commit: bool = True) -> None:
    entry = AuditLog(
        user_id=getattr(user, "id", None),
        action=action[:60],
        target_type=target_type,
        target_id=str(target_id)[:64] if target_id is not None else None,
        ip_hash=ip_hash() if has_request_context() else None,
        details=details or None,
    )
    db.session.add(entry)
    if commit:
        db.session.commit()
