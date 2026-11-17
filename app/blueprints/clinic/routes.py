"""Doctor page.

Who sees what
- Only accounts an admin made "doctor" (with a clinic name) can open these pages.
- A doctor sees only appointment requests for their own clinic (clinic name matched without regard to case).
- The photo and the AI result are shown only when the patient ticked "share my photo" while booking, and only
  while the patient hasn't deleted that check. Every photo view is written to the audit log.
"""

from flask import abort, render_template, request
from flask_login import current_user

from app.blueprints.clinic import bp
from app.extensions import db
from app.models import Appointment
from app.security.decorators import doctor_required
from app.services.audit_service import audit


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


@bp.get("/")
@doctor_required
def appointments():
    page = request.args.get("page", 1, type=int)
    pagination = db.paginate(_my_requests().order_by(Appointment.created_at.desc(), Appointment.id.desc()),
                             page=max(page, 1), per_page=20, error_out=False)
    return render_template("clinic/appointments.html", pagination=pagination, shared=shared_prediction)


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
