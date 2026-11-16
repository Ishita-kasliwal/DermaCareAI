"""Find a dermatologist near me (Task 4)."""

from flask import Blueprint

bp = Blueprint("doctors", __name__)

from app.blueprints.doctors import routes  # noqa: E402,F401
