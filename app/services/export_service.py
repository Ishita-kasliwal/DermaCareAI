"""Power BI-friendly CSV exports (star schema). UTF-8 with BOM, ISO-8601 dates, '.' decimals.

Exports contain no names, emails, images or raw IDs: users appear as a keyed pseudonym.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator

from app.extensions import db
from app.models import DiseaseClass, Feedback, Image, ModelVersion, Prediction, PredictionScore, User
from app.security.utils import pseudonymous_key

BOM = "﻿"


def _stream(header: list[str], rows) -> Iterator[str]:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(header)
    yield BOM + buf.getvalue()
    for row in rows:
        buf.seek(0)
        buf.truncate(0)
        writer.writerow([_cell(v) for v in row])
        yield buf.getvalue()


def _cell(v):
    if v is None:
        return ""
    if hasattr(v, "isoformat"):
        return v.isoformat(timespec="seconds")
    if isinstance(v, float):
        return f"{v:.6f}"
    s = str(v)
    # neutralise spreadsheet formula injection
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


def _pred_query(user: User | None):
    q = (db.select(Prediction, DiseaseClass.code, ModelVersion.version, Image.quality_ok, User.public_id)
         .join(DiseaseClass, Prediction.predicted_class_id == DiseaseClass.id)
         .join(ModelVersion, Prediction.model_version_id == ModelVersion.id)
         .join(Image, Prediction.image_id == Image.id)
         .join(User, Prediction.user_id == User.id)
         .where(Prediction.deleted_at.is_(None))
         .order_by(Prediction.created_at))
    if user is not None:
        q = q.where(Prediction.user_id == user.id)
    return q


def fact_predictions(user: User | None = None) -> Iterator[str]:
    def rows():
        for pred, code, version, q_ok, upid in db.session.execute(_pred_query(user)).yield_per(500):
            yield [pred.public_id, pseudonymous_key(upid), pred.created_at, version, code,
                   float(pred.confidence), pred.status, int(bool(q_ok)), pred.inference_ms]

    return _stream(["prediction_id", "user_key", "created_at", "model_version", "predicted_class_code",
                    "confidence", "status", "quality_ok", "inference_ms"], rows())


def fact_prediction_scores(user: User | None = None) -> Iterator[str]:
    def rows():
        q = (db.select(Prediction.public_id, DiseaseClass.code, PredictionScore.probability)
             .join(PredictionScore, PredictionScore.prediction_id == Prediction.id)
             .join(DiseaseClass, PredictionScore.class_id == DiseaseClass.id)
             .where(Prediction.deleted_at.is_(None))
             .order_by(Prediction.id, DiseaseClass.display_order))
        if user is not None:
            q = q.where(Prediction.user_id == user.id)
        for pid, code, p in db.session.execute(q).yield_per(1000):
            yield [pid, code, float(p)]

    return _stream(["prediction_id", "class_code", "probability"], rows())


def dim_disease_classes() -> Iterator[str]:
    rows = ([c.code, c.name, c.domain, c.risk_level, c.display_order]
            for c in db.session.scalars(db.select(DiseaseClass).order_by(DiseaseClass.display_order)))
    return _stream(["class_code", "name", "checker", "risk_level", "display_order"], rows)


def dim_model_versions() -> Iterator[str]:
    rows = ([m.version, m.architecture, m.input_size, m.accuracy, m.balanced_accuracy, m.macro_f1,
             m.confidence_threshold, int(m.is_active), m.trained_at, m.created_at]
            for m in db.session.scalars(db.select(ModelVersion).order_by(ModelVersion.created_at)))
    return _stream(["model_version", "architecture", "input_size", "test_accuracy",
                    "test_balanced_accuracy", "test_macro_f1", "confidence_threshold", "is_active",
                    "trained_at", "registered_at"], rows)


def fact_feedback() -> Iterator[str]:
    def rows():
        q = (db.select(Prediction.public_id, Feedback.is_correct, DiseaseClass.code, Feedback.created_at)
             .join(Prediction, Feedback.prediction_id == Prediction.id)
             .outerjoin(DiseaseClass, Feedback.suggested_class_id == DiseaseClass.id)
             .where(Prediction.deleted_at.is_(None)))
        for pid, ok, code, created in db.session.execute(q):
            yield [pid, "" if ok is None else int(ok), code, created]

    return _stream(["prediction_id", "is_correct", "suggested_class_code", "created_at"], rows())


ADMIN_EXPORTS = {
    "fact_predictions": fact_predictions,
    "fact_prediction_scores": fact_prediction_scores,
    "dim_disease_classes": dim_disease_classes,
    "dim_model_versions": dim_model_versions,
    "fact_feedback": fact_feedback,
}
