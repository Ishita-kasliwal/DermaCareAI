"""Loads the ACTIVE model version (from the model_versions table) once and caches it.

TensorFlow is imported lazily, so pages that don't need the model stay fast.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from flask import current_app

from app.config import ROOT_DIR
from app.extensions import db
from app.models import ModelVersion


class ModelUnavailableError(RuntimeError):
    pass


class ModelRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._predictors: dict[tuple[int, str], object] = {}

    @staticmethod
    def active_version() -> ModelVersion | None:
        return db.session.scalar(db.select(ModelVersion).filter_by(is_active=True))

    @staticmethod
    def model_dir(mv: ModelVersion) -> Path:
        p = Path(mv.file_path)
        return p if p.is_absolute() else ROOT_DIR / p

    def get_predictor(self, mv: ModelVersion | None = None):
        mv = mv or self.active_version()
        if mv is None:
            raise ModelUnavailableError("The AI isn't ready yet. No trained model has been installed.")
        key = (mv.id, mv.file_sha256)
        with self._lock:
            pred = self._predictors.get(key)
            if pred is not None:
                return pred
            from skinai_ml.prediction import SkinLesionPredictor

            directory = self.model_dir(mv)
            manifest_path = directory / "manifest.json"
            if not manifest_path.exists():
                raise ModelUnavailableError(f"The AI files for {mv.version} are missing.")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("model_sha256") != mv.file_sha256:
                raise ModelUnavailableError("Model checksum does not match the registered version.")
            pred = SkinLesionPredictor(directory, confidence_threshold=mv.confidence_threshold)
            self._predictors = {key: pred}  # keep only the active one in memory
            current_app.logger.info("model loaded: %s", mv.version)
            return pred

    def clear(self) -> None:
        with self._lock:
            self._predictors.clear()


registry = ModelRegistry()
