from flask import abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from app.blueprints.predict import bp
from app.extensions import db, limiter
from app.forms import AnalyzeForm, ConfirmForm, FeedbackForm, UploadForm
from app.ml.registry import ModelUnavailableError, registry
from app.models import DiseaseClass, Feedback
from app.services.analytics_service import class_rows
from app.services.audit_service import audit
from app.services.image_service import (
    ImageValidationError,
    get_owned_image,
    resolve_storage_key,
    store_upload,
    switch_checker,
)
from app.services.prediction_service import get_owned_prediction, inconclusive_reasons, run_prediction


ALT_MIN = 0.05  # only discuss alternatives the model gave a non-trivial score
DOMAIN_LABELS = {"lesion": "A mole or spot", "general": "A rash or other skin problem"}


def _user_key():
    return current_user.get_id() if current_user.is_authenticated else request.remote_addr


@bp.route("/analyze", methods=["GET", "POST"])
@login_required
@limiter.limit(lambda: current_app.config["UPLOAD_RATE_LIMIT"], methods=["POST"], key_func=_user_key)
def upload():
    form = UploadForm()
    models = registry.active_versions()
    if request.method == "GET":
        wanted = request.args.get("check")
        if wanted in models:
            form.check_type.data = wanted
        if models.get(form.check_type.data) is None:  # pre-select a checker that is actually installed
            form.check_type.data = next((d for d, mv in models.items() if mv), form.check_type.data)
    error = None
    if form.validate_on_submit():
        domain = form.check_type.data
        if models.get(domain) is None:
            error = ("The AI for this kind of check isn't installed yet, so we can't check this photo. "
                     "Please try the other option, or come back later.")
        else:
            try:
                image, reused = store_upload(current_user, form.image.data, domain)
            except ImageValidationError as e:
                error = str(e)
            else:
                if reused:
                    flash("You've uploaded this photo before, so we're using the saved copy.", "info")
                return redirect(url_for("predict.preview", image_id=image.public_id))
    elif form.is_submitted():
        error = "; ".join(e for errs in form.errors.values() for e in errs)
    any_model = any(models.values())
    return render_template("predict/upload.html", form=form, models=models, model=any_model, error=error,
                           domain_labels=DOMAIN_LABELS,
                           max_mb=current_app.config["MAX_UPLOAD_MB"],
                           min_side=current_app.config["MIN_IMAGE_SIDE"]), (400 if error else 200)


@bp.get("/analyze/<image_id>")
@login_required
def preview(image_id):
    image = get_owned_image(current_user, image_id) or abort(404)
    other = "general" if image.domain == "lesion" else "lesion"
    return render_template("predict/preview.html", image=image, form=AnalyzeForm(), switch_form=ConfirmForm(),
                           other_available=registry.active_version(other) is not None,
                           model=registry.active_version(image.domain), domain_labels=DOMAIN_LABELS)


@bp.post("/analyze/<image_id>/switch")
@login_required
def switch(image_id):
    """Send an uploaded photo to the other checker without uploading it again."""
    image = get_owned_image(current_user, image_id) or abort(404)
    if not ConfirmForm().validate_on_submit():
        abort(400)
    target = "general" if image.domain == "lesion" else "lesion"
    if registry.active_version(target) is None:
        flash("That checker isn't available yet.", "error")
    else:
        switch_checker(image, target)
        flash(f"Okay! This photo will now be checked as: {DOMAIN_LABELS[target].lower()}.", "success")
    return redirect(url_for("predict.preview", image_id=image.public_id))


@bp.post("/analyze/<image_id>")
@login_required
@limiter.limit(lambda: current_app.config["UPLOAD_RATE_LIMIT"], key_func=_user_key)
def analyze(image_id):
    image = get_owned_image(current_user, image_id) or abort(404)
    form = AnalyzeForm()
    model = registry.active_version(image.domain)
    if not form.validate_on_submit():
        return render_template("predict/preview.html", image=image, form=form, model=model, domain_labels=DOMAIN_LABELS), 400
    try:
        pred = run_prediction(current_user, image)
    except ModelUnavailableError as e:
        return render_template("predict/preview.html", image=image, form=form, model=model, domain_labels=DOMAIN_LABELS,
                               error=str(e)), 503
    except Exception:
        current_app.logger.exception("prediction failed")
        return render_template("predict/preview.html", image=image, form=form, model=model, domain_labels=DOMAIN_LABELS,
                               error="Sorry, something went wrong while checking your photo. "
                                     "Please try again in a moment."), 500
    return redirect(url_for("predict.result", prediction_id=pred.public_id))


@bp.get("/results/<prediction_id>")
@login_required
def result(prediction_id):
    pred = get_owned_prediction(current_user, prediction_id) or abort(404)
    fb_form = FeedbackForm(formdata=None)
    fb_form.suggested_class.choices = [("", "Select a category")] + [(c.code, c.name) for c in class_rows()]
    return render_template(
        "predict/result.html", pred=pred, reasons=inconclusive_reasons(pred),
        alternatives=[s for s in pred.scores[1:3] if s.probability >= ALT_MIN], alt_min=ALT_MIN,
        fb_form=fb_form, delete_form=ConfirmForm(),
    )


@bp.post("/results/<prediction_id>/feedback")
@login_required
def feedback(prediction_id):
    pred = get_owned_prediction(current_user, prediction_id) or abort(404)
    form = FeedbackForm()
    form.suggested_class.choices = [("", "")] + [(c.code, c.name) for c in class_rows()]
    if not form.validate_on_submit():
        flash("Please choose an answer before saving.", "error")
        return redirect(url_for("predict.result", prediction_id=prediction_id))
    fb = pred.feedback or Feedback(prediction_id=pred.id)
    fb.is_correct = {"yes": True, "no": False}.get(form.is_correct.data)
    fb.suggested_class_id = None
    if form.is_correct.data == "no" and form.suggested_class.data:
        dc = db.session.scalar(db.select(DiseaseClass).filter_by(code=form.suggested_class.data))
        fb.suggested_class_id = dc.id if dc else None
    fb.comment = (form.comment.data or "").strip() or None
    db.session.add(fb)
    db.session.commit()
    audit("feedback", current_user, "prediction", pred.public_id)
    flash("Thank you! Your answer helps us see how well the AI works in real life.", "success")
    return redirect(url_for("predict.result", prediction_id=prediction_id))


def _private_file(key: str):
    try:
        path = resolve_storage_key(key)
    except ValueError:
        abort(404)
    if not path.exists():
        abort(404)
    resp = send_file(path, mimetype="image/jpeg", max_age=0, conditional=True)
    resp.headers["Cache-Control"] = "private, no-store"
    resp.headers["Content-Disposition"] = "inline"
    return resp


@bp.get("/media/images/<image_id>")
@login_required
def image_file(image_id):
    image = get_owned_image(current_user, image_id) or abort(404)
    return _private_file(image.storage_key)


@bp.get("/media/explanations/<prediction_id>")
@login_required
def gradcam_file(prediction_id):
    pred = get_owned_prediction(current_user, prediction_id) or abort(404)
    if not pred.gradcam_key:
        abort(404)
    return _private_file(pred.gradcam_key)
