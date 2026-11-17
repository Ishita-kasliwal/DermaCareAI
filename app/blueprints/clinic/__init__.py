"""Dermatologist page: appointment requests for the doctor's own clinic (and photos patients chose to share)."""

from flask import Blueprint

bp = Blueprint("clinic", __name__)

from app.blueprints.clinic import routes  # noqa: E402,F401
