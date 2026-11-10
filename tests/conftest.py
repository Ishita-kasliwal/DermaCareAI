"""Shared fixtures for the web application tests.

Database: SQLite in memory by default (set TEST_DATABASE_URL to run the same suite on MySQL).
Model: a tiny CNN is built and exported in the REAL export format. Its outputs come from actual
Keras inference; the bias of its last layer is set so that tests can exercise both the
"confident" and the "inconclusive" path deterministically. It is not a skin-lesion model.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app import create_app
from app.extensions import db as _db
from app.ml.registry import registry
from app.models import ModelVersion, User
from app.security.passwords import hash_password
from app.services.catalog import seed_disease_classes

CLASSES = ["akiec", "bcc", "bkl", "df", "mel", "nv", "vasc"]
PASSWORD = "Correct-Horse-91"


# ----------------------------------------------------------------- tiny real model
def _export_tiny_model(directory: Path, version: str, favour: str | None) -> Path:
    import keras

    keras.utils.set_random_seed(0)
    inputs = keras.Input((64, 64, 3), dtype="float32")
    x = keras.layers.Rescaling(1 / 255.0)(inputs)
    x = keras.layers.Conv2D(8, 3, activation="relu", name="conv_a")(x)
    x = keras.layers.Conv2D(8, 3, activation="relu", name="conv_b")(x)
    x = keras.layers.GlobalAveragePooling2D()(x)
    dense = keras.layers.Dense(7, activation="softmax", name="probs")
    out = dense(x)
    model = keras.Model(inputs, out)
    w, b = dense.get_weights()
    w[:] = w * 0.01
    b[:] = 0.0
    if favour:
        b[CLASSES.index(favour)] = 6.0
    dense.set_weights([w, b])

    directory.mkdir(parents=True, exist_ok=True)
    model.save(directory / "model.keras")
    sha = hashlib.sha256((directory / "model.keras").read_bytes()).hexdigest()
    (directory / "labels.json").write_text(json.dumps(
        [{"index": i, "code": c, "name": c, "risk_level": "low"} for i, c in enumerate(CLASSES)]))
    (directory / "preprocess_config.json").write_text(json.dumps(
        {"image_size": 64, "crop": "center_square", "resize_method": "bilinear", "antialias": True}))
    (directory / "manifest.json").write_text(json.dumps({
        "version": version, "architecture": "tinycnn-test", "model_file": "model.keras",
        "model_sha256": sha, "num_classes": 7, "classes": CLASSES, "image_size": 64,
        "confidence_threshold": 0.5, "environment": {"timestamp_utc": "2026-11-10T00:00:00+00:00"}}))
    (directory / "metrics.json").write_text(json.dumps({"validation": {}, "test": {}}))
    return directory


@pytest.fixture(scope="session")
def model_dirs(tmp_path_factory):
    root = tmp_path_factory.mktemp("models")
    return {
        "confident": _export_tiny_model(root / "tiny-confident", "tiny-confident", favour="nv"),
        "uniform": _export_tiny_model(root / "tiny-uniform", "tiny-uniform", favour=None),
    }


# ----------------------------------------------------------------- app / db
@pytest.fixture()
def app(tmp_path):
    app = create_app("testing")
    app.config.update(UPLOAD_DIR=tmp_path / "uploads", SERVER_NAME="localhost")

    # The fixture keeps one app context pushed (so tests can use db.session directly). Flask would
    # then reuse it for every test request, sharing `g` (Flask-Login's cached user) and the ORM
    # identity map across requests and clients. Reset both so each request behaves like production.
    @app.before_request
    def _fresh_request_state():
        from flask import g

        g.pop("_login_user", None)
        _db.session.expire_all()

    with app.app_context():
        _db.create_all()
        seed_disease_classes(_db)
        registry.clear()
        yield app
        _db.session.remove()
        _db.drop_all()
        registry.clear()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(app):
    return _db


def make_user(email="alice@example.com", name="Alice Walker", role="user", password=PASSWORD) -> User:
    u = User(email=email, full_name=name, role=role, password_hash=hash_password(password))
    _db.session.add(u)
    _db.session.commit()
    return u


@pytest.fixture()
def user(app):
    return make_user()


@pytest.fixture()
def other_user(app):
    return make_user("bob@example.com", "Bob Stone")


@pytest.fixture()
def admin(app):
    return make_user("admin@example.com", "Ada Admin", role="admin")


def login(client, email="alice@example.com", password=PASSWORD):
    return client.post("/auth/login", data={"email": email, "password": password})


def logout(client):
    return client.post("/auth/logout")


def register_model(directory: Path, active=True) -> ModelVersion:
    manifest = json.loads((directory / "manifest.json").read_text())
    if active:
        _db.session.execute(_db.update(ModelVersion).values(is_active=False))
    mv = ModelVersion(version=manifest["version"], architecture=manifest["architecture"],
                      file_path=str(directory), file_sha256=manifest["model_sha256"],
                      input_size=64, confidence_threshold=0.5, is_active=active)
    _db.session.add(mv)
    _db.session.commit()
    registry.clear()
    return mv


@pytest.fixture()
def active_model(app, model_dirs):
    return register_model(model_dirs["confident"])


# ----------------------------------------------------------------- images
def image_bytes(fmt="JPEG", size=(320, 260), mode="RGB", seed=1, exif=None, colour=True) -> bytes:
    rng = np.random.default_rng(seed)
    h, w = size[1], size[0]
    yy, xx = np.mgrid[0:h, 0:w]
    base = np.stack([150 + 40 * np.sin(xx / 9), 110 + 30 * np.cos(yy / 7), 90 + 20 * np.sin((xx + yy) / 11)], -1)
    arr = np.clip(base + rng.normal(0, 25, base.shape), 0, 255).astype(np.uint8)
    if not colour:
        arr = np.repeat(arr.mean(-1, keepdims=True), 3, -1).astype(np.uint8)
    img = Image.fromarray(arr).convert(mode)
    buf = io.BytesIO()
    kwargs = {"exif": exif} if exif is not None else {}
    img.save(buf, format=fmt, **kwargs)
    return buf.getvalue()


def upload(client, data: bytes, filename="lesion.jpg"):
    return client.post("/analyze", data={"image": (io.BytesIO(data), filename)},
                       content_type="multipart/form-data")


def image_id_from(resp) -> str:
    m = re.search(r"/analyze/([0-9a-f-]{36})", resp.headers.get("Location", ""))
    assert m, f"no preview redirect: {resp.status_code}"
    return m.group(1)


def analyse(client, image_id, consent=True):
    data = {"consent": "y"} if consent else {}
    return client.post(f"/analyze/{image_id}", data=data)


def prediction_id_from(resp) -> str:
    m = re.search(r"/results/([0-9a-f-]{36})", resp.headers.get("Location", ""))
    assert m, f"no result redirect: {resp.status_code}"
    return m.group(1)


@pytest.fixture()
def analysed(client, user, active_model):
    """A logged-in user with one completed analysis. Returns (image_id, prediction_id)."""
    login(client)
    iid = image_id_from(upload(client, image_bytes()))
    pid = prediction_id_from(analyse(client, iid))
    return iid, pid
