"""Loads the ACTIVE model version for each checker ("domain") and caches it.

Domains: "lesion" (mole or spot) and "general" (rash or other skin problem). Each has at most one
active model in the model_versions table. TensorFlow is imported lazily.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from flask import current_app

from app.config import ROOT_DIR
from app.extensions import db
from app.models import ModelVersion

DOMAINS = ("lesion", "general")


class ModelUnavailableError(RuntimeError):
    pass


class ModelRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._predictors: dict[str, tuple[tuple[int, str], object]] = {}

    @staticmethod
    def active_version(domain: str = "lesion") -> ModelVersion | None:
        return db.session.scalar(db.select(ModelVersion).filter_by(is_active=True, domain=domain))

    @classmethod
    def active_versions(cls) -> dict[str, ModelVersion | None]:
        return {d: cls.active_version(d) for d in DOMAINS}

    @staticmethod
    def model_dir(mv: ModelVersion) -> Path:
        p = Path(mv.file_path)
        return p if p.is_absolute() else ROOT_DIR / p

    def get_predictor(self, mv: ModelVersion | None = None, domain: str = "lesion"):
        mv = mv or self.active_version(domain)
        if mv is None:
            raise ModelUnavailableError("The AI for this kind of check isn't ready yet.")
        key = (mv.id, mv.file_sha256)
        with self._lock:
            cached = self._predictors.get(mv.domain)
            if cached is not None and cached[0] == key:
                return cached[1]
            from skinai_ml.prediction import SkinLesionPredictor

            directory = self.model_dir(mv)
            manifest_path = directory / "manifest.json"
            if not manifest_path.exists():
                raise ModelUnavailableError(f"The AI files for {mv.version} are missing.")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("model_sha256") != mv.file_sha256:
                raise ModelUnavailableError("Model checksum does not match the registered version.")
            pred = SkinLesionPredictor(directory, confidence_threshold=mv.confidence_threshold)
            self._predictors[mv.domain] = (key, pred)  # one loaded model per domain
            current_app.logger.info("model loaded: %s (%s)", mv.version, mv.domain)
            return pred

    def clear(self) -> None:
        with self._lock:
            self._predictors.clear()


registry = ModelRegistry()
