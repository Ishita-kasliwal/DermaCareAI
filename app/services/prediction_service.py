"""Runs real model inference on a stored image and persists the result.

No prediction or confidence value is ever produced here except by the trained model's output.
"""

from __future__ import annotations

import io
import time
import uuid

from flask import current_app
from PIL import Image as PILImage

from app.extensions import db
from app.ml.registry import ModelUnavailableError, registry
from app.models import DiseaseClass, Image, Prediction, PredictionScore, User
from app.models.entities import utcnow
from app.services.audit_service import audit
from app.services.image_service import delete_file, resolve_storage_key

__all__ = ["ModelUnavailableError", "run_prediction", "get_owned_prediction", "inconclusive_reasons",
           "soft_delete_prediction"]


def _status(confidence: float, second: float, threshold: float, margin: float) -> str:
    if confidence < threshold or (confidence - second) < margin:
        return "inconclusive"
    return "confident"


def inconclusive_reasons(pred: Prediction) -> list[str]:
    """Human-readable reasons, derived from the stored scores (not re-computed by the model)."""
    reasons = []
    threshold = float(pred.model_version.confidence_threshold)
    margin = current_app.config["INCONCLUSIVE_MARGIN"]
    probs = sorted((s.probability for s in pred.scores), reverse=True)
    if probs and probs[0] < threshold:
        reasons.append(
            f"The closest match only reached {probs[0]:.0%}. We like to be at least {threshold:.0%} sure "
            "before naming anything."
        )
    if len(probs) > 1 and probs[0] - probs[1] < margin:
        reasons.append("The top two answers were very close, so the AI couldn't choose between them.")
    if pred.image.quality_issues:
        reasons.append("The photo isn't very clear, which makes it harder to read.")
    return reasons


def run_prediction(user: User, image: Image, domain: str | None = None) -> Prediction:
    """Check one photo. `domain` picks the checker ("lesion" or "general"); default: the photo's own."""
    if image.user_id != user.id or image.deleted_at is not None:
        raise PermissionError("image not owned by user")
    domain = domain or image.domain or "lesion"
    if domain not in ("lesion", "general"):
        raise ValueError("unknown checker")
    mv = registry.active_version(domain)
    if mv is None:
        raise ModelUnavailableError("The AI for this kind of check isn't ready yet.")
    predictor = registry.get_predictor(mv)

    path = resolve_storage_key(image.storage_key)
    from skinai_ml.prediction import load_rgb_image

    rgb = load_rgb_image(path)
    t0 = time.perf_counter()
    result = predictor.predict_array(rgb)
    inference_ms = int((time.perf_counter() - t0) * 1000)

    classes = {c.code: c for c in db.session.scalars(db.select(DiseaseClass))}
    missing = [c for c in result.probabilities if c not in classes]
    if missing:
        raise RuntimeError(f"model classes not in database: {missing}")

    ordered = sorted(result.probabilities.items(), key=lambda kv: kv[1], reverse=True)
    top_code, top_p = ordered[0]
    second_p = ordered[1][1] if len(ordered) > 1 else 0.0
    status = _status(top_p, second_p, float(mv.confidence_threshold),
                     current_app.config["INCONCLUSIVE_MARGIN"])

    pred = Prediction(
        user_id=user.id, image_id=image.id, model_version_id=mv.id,
        predicted_class_id=classes[top_code].id, confidence=float(top_p), status=status,
        inference_ms=inference_ms,
    )
    pred.scores = [PredictionScore(class_id=classes[c].id, probability=float(p)) for c, p in ordered]
    db.session.add(pred)
    db.session.flush()

    # Heatmaps need a convolutional model; models that say "gradcam": false (e.g. CLIP-based) skip them.
    if current_app.config["ENABLE_GRADCAM"] and predictor.manifest.get("gradcam", True)             and result.code != "unfamiliar":
        try:
            pred.gradcam_key = _save_gradcam(predictor, rgb, result, image, user)
        except Exception as exc:  # explanation is optional; never fail the prediction for it
            current_app.logger.warning("Grad-CAM failed: %s", exc)

    db.session.commit()
    audit("prediction_create", user, "prediction", pred.public_id,
          details={"model": mv.version, "status": status})
    return pred


def _save_gradcam(predictor, rgb, result, image: Image, user: User) -> str:
    from skinai_ml.gradcam import compute_heatmap, overlay
    from skinai_ml.preprocess import preprocess_image, to_model_input

    model = predictor._load()
    prepared = preprocess_image(rgb, predictor.preprocess_cfg)
    x = to_model_input(prepared)[None, ...]
    idx = predictor.class_codes.index(result.code)
    heat = compute_heatmap(model, x, idx)
    blended = overlay(prepared.numpy(), heat)
    now = utcnow()
    key = f"{user.public_id}/{now:%Y}/{now:%m}/cam_{uuid.uuid4().hex}.jpg"
    path = resolve_storage_key(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    PILImage.fromarray(blended).save(buf, format="JPEG", quality=90)
    path.write_bytes(buf.getvalue())
    return key


def get_owned_prediction(user: User, public_id: str) -> Prediction | None:
    """Ownership is part of the query: other users' records are indistinguishable from missing."""
    return db.session.scalar(
        db.select(Prediction)
        .filter_by(public_id=public_id, user_id=user.id)
        .where(Prediction.deleted_at.is_(None))
    )


def soft_delete_prediction(user: User, pred: Prediction) -> None:
    now = utcnow()
    pred.deleted_at = now
    delete_file(pred.gradcam_key)
    image = pred.image
    still_used = any(p.deleted_at is None for p in image.predictions if p.id != pred.id)
    if not still_used:
        delete_file(image.storage_key)
        image.deleted_at = now
    db.session.commit()
    audit("prediction_delete", user, "prediction", pred.public_id)
