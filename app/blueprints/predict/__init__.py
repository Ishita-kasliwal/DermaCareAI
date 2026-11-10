"""Upload -> preview -> analyse -> result."""

from flask import Blueprint

bp = Blueprint("predict", __name__)

from app.blueprints.predict import routes  # noqa: E402,F401
