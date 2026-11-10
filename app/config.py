"""Configuration classes.

Values come ONLY from this project's .env file (loaded into this process at
startup). Nothing is written to user- or system-level environment variables.
"""

import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env", override=False)


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


def _mysql_uri() -> str:
    """App connections use the least-privilege DML account. Schema migrations set
    SKINAI_DB_ROLE=migrate (only inside scripts/db_upgrade.ps1) to use the DDL account."""
    if _env("DATABASE_URL"):
        return _env("DATABASE_URL")
    if _env("SKINAI_DB_ROLE") == "migrate":
        user = quote_plus(_env("DB_MIGRATE_USER", "skin_ai_migrate"))
        pwd = quote_plus(_env("DB_MIGRATE_PASSWORD", ""))
    else:
        user = quote_plus(_env("DB_USER", "skin_ai_app"))
        pwd = quote_plus(_env("DB_PASSWORD", ""))
    host = _env("DB_HOST", "127.0.0.1")
    port = _env("DB_PORT", "3306")
    name = _env("DB_NAME", "skin_ai_db")
    return f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{name}?charset=utf8mb4"


class BaseConfig:
    APP_NAME = _env("APP_NAME", "AI Skin Disease Detection")
    BRAND_NAME = _env("BRAND_NAME", "DermaCareAI")
    SECRET_KEY = _env("SECRET_KEY")

    SQLALCHEMY_DATABASE_URI = _mysql_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 1800}

    # Uploads
    MAX_UPLOAD_MB = int(_env("MAX_UPLOAD_MB", "8"))
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024
    UPLOAD_DIR = ROOT_DIR / _env("UPLOAD_DIR", "instance/uploads")
    ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}
    MIN_IMAGE_SIDE = int(_env("MIN_IMAGE_SIDE", "224"))
    MAX_IMAGE_SIDE = int(_env("MAX_IMAGE_SIDE", "4000"))  # larger images are downscaled
    MAX_IMAGE_PIXELS = 40_000_000                          # decompression-bomb guard

    # ML
    MODEL_DIR = ROOT_DIR / _env("MODEL_DIR", "ml/artifacts")
    CONFIDENCE_THRESHOLD = float(_env("CONFIDENCE_THRESHOLD", "0.50"))
    INCONCLUSIVE_MARGIN = float(_env("INCONCLUSIVE_MARGIN", "0.10"))
    ENABLE_GRADCAM = _env("ENABLE_GRADCAM", "true").lower() == "true"

    # Rate limits (per client)
    LOGIN_RATE_LIMIT = "5 per minute"
    REGISTER_RATE_LIMIT = "10 per hour"
    UPLOAD_RATE_LIMIT = "30 per hour"

    # Privacy
    RETENTION_DAYS = int(_env("RETENTION_DAYS", "30"))

    # Sessions / cookies
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    PERMANENT_SESSION_LIFETIME = 30 * 60  # 30-minute idle timeout
    REMEMBER_COOKIE_HTTPONLY = True

    # Rate limiting
    RATELIMIT_STORAGE_URI = "memory://"
    RATELIMIT_DEFAULT = "200 per hour"

    FORCE_HTTPS = False


class DevelopmentConfig(BaseConfig):
    DEBUG = False  # never enable the Werkzeug debugger on a served app


class TestingConfig(BaseConfig):
    TESTING = True
    SECRET_KEY = "test-only-not-secret"
    SQLALCHEMY_DATABASE_URI = _env("TEST_DATABASE_URL", "sqlite://")
    SQLALCHEMY_ENGINE_OPTIONS: dict = {}
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    ENABLE_GRADCAM = True


class ProductionConfig(BaseConfig):
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    FORCE_HTTPS = True


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None) -> type[BaseConfig]:
    return CONFIGS[(name or _env("APP_ENV", "development")).lower()]
