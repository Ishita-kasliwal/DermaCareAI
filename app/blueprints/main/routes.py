import json

from flask import render_template
from flask_login import current_user, login_required

from app.blueprints.main import bp
from app.ml.registry import registry
from app.services.analytics_service import class_rows, recent_predictions, user_stats

CHECKERS = [
    {"domain": "lesion", "title": "Moles and spots",
     "intro": "Close-up photos of a single mole or spot, ideally taken with a skin magnifier (dermatoscope)."},
    {"domain": "general", "title": "Rashes and other skin problems",
     "intro": "Everyday phone photos of rashes, bumps, patches and other common skin problems."},
]


def _model_codes(mv) -> set[str] | None:
    """Category codes the installed model can actually name (from its labels.json)."""
    if mv is None:
        return None
    try:
        labels = json.loads((registry.model_dir(mv) / "labels.json").read_text(encoding="utf-8"))
        return {item["code"] for item in labels}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _classes_by_domain():
    rows = class_rows()
    models = registry.active_versions()
    out = {}
    for c in CHECKERS:
        codes = _model_codes(models.get(c["domain"]))
        out[c["domain"]] = [r for r in rows if r.domain == c["domain"] and (codes is None or r.code in codes)]
    return out


@bp.get("/")
def index():
    models = registry.active_versions()
    return render_template("main/index.html", classes=class_rows(), by_domain=_classes_by_domain(),
                           checkers=CHECKERS, models=models, model=any(models.values()))


@bp.get("/about-model")
def about_model():
    models = registry.active_versions()
    return render_template("main/about_model.html", checkers=CHECKERS, models=models,
                           by_domain=_classes_by_domain(), classes=class_rows())


@bp.get("/dashboard")
@login_required
def dashboard():
    models = registry.active_versions()
    return render_template(
        "main/dashboard.html",
        stats=user_stats(current_user),
        recent=recent_predictions(current_user),
        models=models,
        model=any(models.values()),
    )
