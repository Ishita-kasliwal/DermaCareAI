"""Prediction history."""

from flask import Blueprint

bp = Blueprint("history", __name__)

from app.blueprints.history import routes  # noqa: E402,F401
