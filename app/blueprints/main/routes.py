from pathlib import Path

from flask import current_app, render_template
from flask_login import current_user, login_required

from app.blueprints.main import bp
from app.ml.registry import registry
from app.services.analytics_service import known_class_rows, recent_predictions, user_stats

CHECKERS = [
    {"domain": "lesion", "title": "Moles and spots",
     "intro": "Close-up photos of a single mole or spot, ideally taken with a skin magnifier (dermatoscope)."},
    {"domain": "general", "title": "Rashes and other skin problems",
     "intro": "Everyday phone photos of rashes, bumps, patches and other common skin problems."},
]


# Home page "What you can check" list. A photo is shown only when a file with a clear licence exists in
# app/static/img/conditions/<key>.jpg (otherwise a plain tile). Add the credit here when you add a photo.
CHECK_ITEMS = [
    {"key": "acne", "title": "Pimples and acne", "icon": "chat",
     "desc": "Whiteheads, blackheads and red, sometimes painful spots, usually on the face, chest or back.",
     "credit": "Photo: mehak mehla / Unsplash"},
    {"key": "eczema", "title": "Rashes and eczema", "icon": "sun",
     "desc": "Itchy, red or dry patches that can come and go, often in skin folds or where something touched the skin.",
     "credit": ""},
    {"key": "ringworm", "title": "Ringworm", "icon": "focus",
     "desc": "A round, red, scaly and itchy patch, often with a clearer middle. It's a fungus, not a worm.",
     "credit": ""},
    {"key": "dark_spots", "title": "Dark spots and redness", "icon": "eye",
     "desc": "Brown patches or spots from sun, old pimples or melasma, and flushed red cheeks.",
     "credit": "Photo: sun spots seen through a skin magnifier. HAM10000, ViDIR Group, Medical University of Vienna, CC BY-NC 4.0."},
    {"key": "scratches", "title": "Scratches and small cuts", "icon": "doctor",
     "desc": "Scrapes and small cuts: how to clean them and when a doctor should look at them.",
     "credit": "Photo: Diana Polekhina / Unsplash"},
    {"key": "moles", "title": "Moles and spots", "icon": "question",
     "desc": "A single mole or spot: whether it shows signs a doctor should check, like an uneven edge or several colours.",
     "credit": "Photo: a common mole seen through a skin magnifier. HAM10000, ViDIR Group, Medical University of Vienna, CC BY-NC 4.0."},
]


def _check_items():
    folder = Path(current_app.static_folder) / "img" / "conditions"
    return [{**i, "image": f"img/conditions/{i['key']}.jpg" if (folder / f"{i['key']}.jpg").exists() else None}
            for i in CHECK_ITEMS]


def _classes_by_domain():
    rows = known_class_rows()
    return {c["domain"]: [r for r in rows if r.domain == c["domain"]] for c in CHECKERS}


@bp.get("/")
def index():
    models = registry.active_versions()
    return render_template("main/index.html", classes=known_class_rows(), by_domain=_classes_by_domain(),
                           checkers=CHECKERS, models=models, model=any(models.values()), check_items=_check_items())


@bp.get("/about-model")
def about_model():
    models = registry.active_versions()
    return render_template("main/about_model.html", checkers=CHECKERS, models=models,
                           by_domain=_classes_by_domain(),
                           classes=[c for c in known_class_rows() if c.code != "unfamiliar"])


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
