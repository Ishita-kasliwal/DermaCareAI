"""Doctor page.

Who sees what
- Only accounts an admin made "doctor" (with a clinic name) can open these pages.
- A doctor sees only appointment requests for their own clinic (clinic name matched without regard to case).
- The photo and the AI result are shown only when the patient ticked "share my photo" while booking, and only
  while the patient hasn't deleted that check. Every photo view is written to the audit log.
- After the visit the doctor deletes the request ("Visit done, delete"). Requests are also deleted automatically
  KEEP_DAYS after the appointment date, so names and phone numbers don't pile up.
"""

from datetime import date, timedelta

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.blueprints.clinic import bp
from app.extensions import db
from app.forms import ConfirmForm
from app.models import Appointment
from app.security.decorators import doctor_required
from app.services.audit_service import audit

KEEP_DAYS = 7   # days after the appointment date before a request is deleted automatically


def _my_requests():
    name = (current_user.clinic_name or "").strip().lower()
    if not name:
        return db.select(Appointment).where(db.false())
    return db.select(Appointment).where(db.func.lower(db.func.trim(Appointment.clinic_name)) == name)


def shared_prediction(appt):
    """The check the patient shared with this clinic, or None (not shared, or since deleted by the patient)."""
    p = appt.prediction
    if not appt.share_photo or p is None or p.deleted_at is not None or p.image is None or p.image.deleted_at:
        return None
    return p


def delete_expired() -> int:
    """Delete requests whose appointment date is more than KEEP_DAYS in the past. Returns how many."""
    cutoff = date.today() - timedelta(days=KEEP_DAYS)
    n = db.session.execute(db.delete(Appointment).where(Appointment.preferred_date < cutoff)).rowcount or 0
    if n:
        db.session.commit()
    return n


def patient_details(appt, pred) -> dict:
    """What the doctor may see when the patient shared: never the email or password."""
    u = appt.user
    age = (date.today().year - u.birth_year) if u and u.birth_year else None
    skin = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI"}.get(u.skin_type) if u else None
    sex = {"female": "Female", "male": "Male", "other": "Other"}.get(u.sex) if u else None
    return {"age": age, "sex": sex, "skin_type": skin, "checked_on": pred.created_at,
            "checker": "Rash checker" if pred.model_version.domain == "general" else "Mole checker",
            "quality_ok": pred.image.quality_ok, "top3": pred.scores[:3]}


@bp.get("/")
@doctor_required
def appointments():
    delete_expired()
    page = request.args.get("page", 1, type=int)
    pagination = db.paginate(_my_requests().order_by(Appointment.created_at.desc(), Appointment.id.desc()),
                             page=max(page, 1), per_page=20, error_out=False)
    return render_template("clinic/appointments.html", pagination=pagination, shared=shared_prediction,
                           details=patient_details, delete_form=ConfirmForm(), keep_days=KEEP_DAYS)


@bp.post("/appointments/<appointment_id>/delete")
@doctor_required
def delete(appointment_id):
    """After the visit: remove the request (name, phone, photo link) for good."""
    if not ConfirmForm().validate_on_submit():
        abort(400)
    appt = db.session.scalar(_my_requests().filter_by(public_id=appointment_id))
    if appt is None:
        abort(404)
    audit("doctor_appointment_delete", current_user, "appointment", appt.public_id, commit=False)
    db.session.delete(appt)
    db.session.commit()
    flash(f"Done. The request from {appt.patient_name} was deleted.", "info")
    return redirect(url_for("clinic.appointments"))


@bp.get("/appointments/<appointment_id>/photo")
@doctor_required
def photo(appointment_id):
    appt = db.session.scalar(_my_requests().filter_by(public_id=appointment_id))
    pred = shared_prediction(appt) if appt else None
    if pred is None:
        abort(404)
    audit("doctor_photo_view", current_user, "appointment", appt.public_id)
    from app.blueprints.predict.routes import _private_file

    return _private_file(pred.image.storage_key)
