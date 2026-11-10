"""JSON endpoints for Chart.js. Read-only (GET), session-authenticated, same-origin."""

from functools import wraps

from flask import current_app, jsonify, request
from flask_login import current_user

from app.blueprints.api import bp
from app.services.analytics_service import admin_analytics, admin_overview, parse_range, user_stats


def api_auth(admin: bool = False):
    def deco(view):
        @wraps(view)
        def wrapped(*a, **kw):
            if not current_user.is_authenticated:
                return jsonify(error="authentication required"), 401
            if admin and not current_user.is_admin:
                return jsonify(error="forbidden"), 403
            return view(*a, **kw)
        return wrapped
    return deco


@bp.get("/health")
def health():
    """Liveness probe used by scripts/status.ps1. Does not touch the DB or model."""
    return jsonify(status="ok", app=current_app.config["APP_NAME"])


@bp.get("/me/stats")
@api_auth()
def my_stats():
    return jsonify(user_stats(current_user))


@bp.get("/admin/overview")
@api_auth(admin=True)
def overview():
    o = admin_overview()
    mv = o.pop("active_model")
    o["active_model"] = mv.version if mv else None
    return jsonify(o)


@bp.get("/admin/analytics")
@api_auth(admin=True)
def analytics():
    start, end = parse_range(request.args.get("from"), request.args.get("to"))
    return jsonify(admin_analytics(start, end))
