"""WSGI entry point used by Waitress (scripts/start.ps1)."""

from app import create_app

app = create_app()
