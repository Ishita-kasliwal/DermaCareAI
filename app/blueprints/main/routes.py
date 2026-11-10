from flask import render_template
from flask_login import current_user, login_required

from app.blueprints.main import bp
from app.ml.registry import registry
from app.services.analytics_service import class_rows, recent_predictions, user_stats


@bp.get("/")
def index():
    return render_template("main/index.html", classes=class_rows(),
                           model=registry.active_version())


@bp.get("/about-model")
def about_model():
    mv = registry.active_version()
    metrics = (mv.metrics or {}) if mv else {}
    return render_template("main/about_model.html", model=mv, metrics=metrics, classes=class_rows())


@bp.get("/dashboard")
@login_required
def dashboard():
    return render_template(
        "main/dashboard.html",
        stats=user_stats(current_user),
        recent=recent_predictions(current_user),
        model=registry.active_version(),
    )
