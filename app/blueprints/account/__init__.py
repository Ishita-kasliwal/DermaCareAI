"""Profile management, password change, account deletion."""

from flask import Blueprint

bp = Blueprint("account", __name__)

from app.blueprints.account import routes  # noqa: E402,F401
