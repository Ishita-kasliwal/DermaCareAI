import sqlalchemy as sa
from flask import Response, abort, flash, redirect, render_template, request, stream_with_context, url_for
from flask_login import current_user

from app.blueprints.admin import bp
from app.extensions import db
from app.forms import ClassEditForm, ConfirmForm, RoleForm, UserSearchForm
from app.ml.registry import registry
from app.models import AuditLog, DiseaseClass, ModelVersion, Prediction, User
from app.security.decorators import admin_required
from app.services import export_service
from app.services.analytics_service import admin_overview, parse_range
from app.services.audit_service import audit


@bp.before_request
@admin_required
def _guard():
    """Every route in this blueprint requires an authenticated administrator."""
    return None


def _user_or_404(public_id: str) -> User:
    user = db.session.scalar(db.select(User).filter_by(public_id=public_id).where(User.deleted_at.is_(None)))
    return user or abort(404)


def _active_admin_count() -> int:
    return db.session.scalar(db.select(sa.func.count(User.id)).where(
        User.role == "admin", User.is_active_flag.is_(True), User.deleted_at.is_(None))) or 0


@bp.get("/")
def dashboard():
    recent = list(db.session.scalars(db.select(AuditLog).order_by(AuditLog.created_at.desc()).limit(8)))
    return render_template("admin/dashboard.html", o=admin_overview(), recent=recent)


@bp.get("/users")
def users():
    form = UserSearchForm(request.args)
    form.validate()
    q = db.select(User).where(User.deleted_at.is_(None))
    if form.q.data:
        like = f"%{form.q.data.strip().lower()}%"  # bound parameter; never string-built SQL
        q = q.where(sa.or_(sa.func.lower(User.email).like(like), sa.func.lower(User.full_name).like(like)))
    if form.role.data:
        q = q.where(User.role == form.role.data)
    if form.state.data == "active":
        q = q.where(User.is_active_flag.is_(True))
    elif form.state.data == "inactive":
        q = q.where(User.is_active_flag.is_(False))
    page = request.args.get("page", 1, type=int)
    pagination = db.paginate(q.order_by(User.created_at.desc()), page=max(page, 1), per_page=20,
                             error_out=False)
    counts = dict(db.session.execute(
        db.select(Prediction.user_id, sa.func.count()).where(Prediction.deleted_at.is_(None))
        .group_by(Prediction.user_id)).all())
    filters = {k: v for k, v in request.args.items() if k != "page" and v}
    return render_template("admin/users.html", form=form, pagination=pagination, counts=counts,
                           filters=filters, confirm=ConfirmForm(), role_form=RoleForm())


@bp.post("/users/<public_id>/active")
def toggle_active(public_id):
    if not ConfirmForm().validate_on_submit():
        abort(400)
    user = _user_or_404(public_id)
    if user.id == current_user.id:
        flash("You can't deactivate your own account.", "error")
        return redirect(url_for("admin.users"))
    if user.is_active_flag and user.role == "admin" and _active_admin_count() <= 1:
        flash("At least one active administrator is required.", "error")
        return redirect(url_for("admin.users"))
    user.is_active_flag = not user.is_active_flag
    user.auth_version += 1  # end their sessions immediately
    db.session.commit()
    audit("admin_user_active" if user.is_active_flag else "admin_user_deactivate", current_user,
          "user", user.public_id)
    flash(f"{user.full_name} has been {'reactivated' if user.is_active_flag else 'deactivated'}.", "success")
    return redirect(request.referrer if request.referrer and "/admin/users" in request.referrer
                    else url_for("admin.users"))


@bp.post("/users/<public_id>/role")
def change_role(public_id):
    form = RoleForm()
    if not form.validate_on_submit():
        abort(400)
    user = _user_or_404(public_id)
    if user.id == current_user.id:
        flash("You can't change your own role.", "error")
        return redirect(url_for("admin.users"))
    if user.role == "admin" and form.role.data != "admin" and _active_admin_count() <= 1:
        flash("At least one active administrator is required.", "error")
        return redirect(url_for("admin.users"))
    old = user.role
    user.role = form.role.data
    user.auth_version += 1
    db.session.commit()
    audit("admin_role_change", current_user, "user", user.public_id, details={"from": old, "to": user.role})
    flash(f"{user.full_name} is now {'an administrator' if user.role == 'admin' else 'a standard user'}.", "success")
    return redirect(url_for("admin.users"))


@bp.get("/models")
def models():
    versions = list(db.session.scalars(db.select(ModelVersion).order_by(ModelVersion.created_at.desc())))
    usage = dict(db.session.execute(db.select(Prediction.model_version_id, sa.func.count())
                                    .group_by(Prediction.model_version_id)).all())
    return render_template("admin/models.html", versions=versions, usage=usage, confirm=ConfirmForm())


@bp.post("/models/<int:model_id>/activate")
def activate_model(model_id):
    if not ConfirmForm().validate_on_submit():
        abort(400)
    mv = db.session.get(ModelVersion, model_id) or abort(404)
    if not registry.model_dir(mv).joinpath("manifest.json").exists():
        flash("The files for this model version are missing on disk, so it can't be activated.", "error")
        return redirect(url_for("admin.models"))
    db.session.execute(sa.update(ModelVersion).values(is_active=False))
    mv.is_active = True
    db.session.commit()
    registry.clear()
    audit("admin_model_activate", current_user, "model_version", mv.version)
    flash(f"Model {mv.version} is now active for new analyses.", "success")
    return redirect(url_for("admin.models"))


@bp.get("/categories")
def categories():
    rows = list(db.session.scalars(db.select(DiseaseClass).order_by(DiseaseClass.display_order)))
    return render_template("admin/categories.html", rows=rows)


@bp.route("/categories/<code>", methods=["GET", "POST"])
def edit_category(code):
    dc = db.session.scalar(db.select(DiseaseClass).filter_by(code=code)) or abort(404)
    form = ClassEditForm(obj=dc)
    if form.validate_on_submit():
        dc.description = form.description.data.strip()
        dc.advice = form.advice.data.strip()
        db.session.commit()
        audit("admin_category_edit", current_user, "disease_class", dc.code)
        flash(f"Updated the text for {dc.name}.", "success")
        return redirect(url_for("admin.categories"))
    return render_template("admin/category_edit.html", dc=dc, form=form), (400 if form.errors else 200)


@bp.get("/analytics")
def analytics():
    start, end = parse_range(request.args.get("from"), request.args.get("to"))
    return render_template("admin/analytics.html", start=start, end=end)


@bp.get("/audit")
def audit_log():
    action = (request.args.get("action") or "").strip()[:60]
    q = db.select(AuditLog)
    if action:
        q = q.where(AuditLog.action == action)
    page = request.args.get("page", 1, type=int)
    pagination = db.paginate(q.order_by(AuditLog.created_at.desc()), page=max(page, 1), per_page=30,
                             error_out=False)
    actions = [a for (a,) in db.session.execute(db.select(AuditLog.action).distinct().order_by(AuditLog.action))]
    return render_template("admin/audit.html", pagination=pagination, actions=actions, action=action)


@bp.get("/exports")
def exports():
    return render_template("admin/exports.html", names=list(export_service.ADMIN_EXPORTS))


@bp.get("/exports/<name>.csv")
def export_file(name):
    fn = export_service.ADMIN_EXPORTS.get(name) or abort(404)
    audit("admin_export", current_user, "export", name)
    return Response(stream_with_context(fn()), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={name}.csv",
                             "Cache-Control": "private, no-store"})
