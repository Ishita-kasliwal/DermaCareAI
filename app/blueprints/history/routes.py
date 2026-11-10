from datetime import datetime, time, timedelta

from flask import Response, abort, flash, redirect, render_template, request, stream_with_context, url_for
from flask_login import current_user, login_required

from app.blueprints.history import bp
from app.extensions import db
from app.forms import ConfirmForm, HistoryFilterForm
from app.models import DiseaseClass, Prediction
from app.services import export_service
from app.services.analytics_service import class_rows
from app.services.prediction_service import get_owned_prediction, soft_delete_prediction

PER_PAGE = 15


@bp.get("/")
@login_required
def index():
    classes = class_rows()
    form = HistoryFilterForm(request.args)
    form.category.choices = [("", "All categories")] + [(c.code, c.name) for c in classes]
    valid = form.validate()

    q = (db.select(Prediction)
         .join(DiseaseClass, Prediction.predicted_class_id == DiseaseClass.id)
         .where(Prediction.user_id == current_user.id, Prediction.deleted_at.is_(None)))
    if valid:
        if form.category.data:
            q = q.where(DiseaseClass.code == form.category.data)
        if form.status.data:
            q = q.where(Prediction.status == form.status.data)
        if form.risk.data:
            q = q.where(DiseaseClass.risk_level == form.risk.data)
        if form.date_from.data:
            q = q.where(Prediction.created_at >= datetime.combine(form.date_from.data, time.min))
        if form.date_to.data:
            q = q.where(Prediction.created_at < datetime.combine(form.date_to.data + timedelta(days=1), time.min))
    page = request.args.get("page", 1, type=int)
    pagination = db.paginate(q.order_by(Prediction.created_at.desc()), page=max(page, 1),
                             per_page=PER_PAGE, error_out=False)
    filters = {k: v for k, v in request.args.items() if k != "page" and v}
    return render_template("history/index.html", form=form, pagination=pagination,
                           filters=filters, filtered=bool(filters), delete_form=ConfirmForm(),
                           invalid=not valid)


@bp.post("/<prediction_id>/delete")
@login_required
def delete(prediction_id):
    form = ConfirmForm()
    if not form.validate_on_submit():
        abort(400)
    pred = get_owned_prediction(current_user, prediction_id) or abort(404)
    soft_delete_prediction(current_user, pred)
    flash("Done. The check and its photo were deleted.", "info")
    return redirect(url_for("history.index"))


@bp.get("/export.csv")
@login_required
def export():
    stream = export_service.fact_predictions(current_user)
    return Response(stream_with_context(stream), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=my_skin_analyses.csv",
                             "Cache-Control": "private, no-store"})
