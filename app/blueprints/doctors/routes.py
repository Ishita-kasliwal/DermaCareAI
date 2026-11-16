from flask import abort, current_app, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.blueprints.doctors import bp
from app.extensions import db, limiter
from app.forms import AppointmentForm, DoctorSearchForm
from app.models import Appointment
from app.services.audit_service import audit
from app.services.doctor_search import Clinic, search
from app.services.prediction_service import get_owned_prediction
from skinai_ml.classes import simple_name


@bp.get("/find-a-dermatologist")
@limiter.limit("30 per hour")
def find():
    """Search form + results (Task 4). Results appear only after a valid search (GET, so it can be bookmarked)."""
    form = DoctorSearchForm(request.args)
    result = None
    submitted = "city" in request.args or "state" in request.args
    if submitted and form.validate():
        result = search(form.city.data, form.district.data or "", form.state.data,
                        google_key=current_app.config.get("GOOGLE_MAPS_API_KEY", ""))
    return render_template("doctors/find.html", form=form, result=result, submitted=submitted)


def _float_or_none(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if -180 <= v <= 180 else None


@bp.route("/book", methods=["GET", "POST"])
@login_required
@limiter.limit("20 per hour", methods=["POST"])
def book():
    """Ask for an appointment at a clinic from the search results (Task 5).

    The clinic's details come from the search result (link parameters on GET, hidden fields on POST). The
    request is saved for the admin list; the clinic itself is NOT contacted, which the page says plainly.
    """
    form = AppointmentForm()
    if request.method == "GET":
        form.clinic_name.data = (request.args.get("name") or "").strip()[:160]
        form.clinic_address.data = (request.args.get("address") or "").strip()[:255]
        form.clinic_phone.data = (request.args.get("phone") or "").strip()[:40]
        form.clinic_lat.data = (request.args.get("lat") or "")[:20]
        form.clinic_lon.data = (request.args.get("lon") or "")[:20]
        form.prediction.data = (request.args.get("prediction") or "")[:36]
        form.patient_name.data = current_user.full_name if current_user.full_name != "Deleted user" else ""
    if not form.clinic_name.data:
        abort(404)   # no clinic chosen: nothing to book

    pred = get_owned_prediction(current_user, form.prediction.data) if form.prediction.data else None
    condition = (simple_name(pred.predicted_class.code, pred.predicted_class.name)
                 if pred and pred.status == "confident" and pred.predicted_class.code != "unfamiliar" else None)
    lat, lon = _float_or_none(form.clinic_lat.data), _float_or_none(form.clinic_lon.data)
    clinic = Clinic(form.clinic_name.data, form.clinic_address.data or "", lat or 0.0, lon or 0.0,
                    phone=form.clinic_phone.data or "")

    if form.validate_on_submit():
        appt = Appointment(
            user_id=current_user.id, prediction_id=pred.id if pred else None,
            clinic_name=form.clinic_name.data, clinic_address=form.clinic_address.data or None,
            clinic_phone=clinic.display_phone or None, clinic_lat=lat, clinic_lon=lon,
            patient_name=form.patient_name.data, patient_phone=form.patient_phone.data,
            preferred_date=form.preferred_date.data, time_slot=form.time_slot.data,
            note=form.note.data or None, predicted_condition=condition,
        )
        db.session.add(appt)
        db.session.flush()
        audit("appointment_request", current_user, "appointment", appt.public_id, commit=False)
        db.session.commit()
        return redirect(url_for("doctors.booked", appointment_id=appt.public_id))
    return render_template("doctors/book.html", form=form, clinic=clinic, has_location=lat is not None,
                           condition=condition), (400 if request.method == "POST" else 200)


@bp.get("/book/<appointment_id>")
@login_required
def booked(appointment_id):
    """The friendly "we've saved your request" page. Only the person who made the request can see it."""
    appt = db.session.scalar(db.select(Appointment).filter_by(public_id=appointment_id, user_id=current_user.id))
    if appt is None:
        abort(404)
    clinic = Clinic(appt.clinic_name, appt.clinic_address or "", appt.clinic_lat or 0.0, appt.clinic_lon or 0.0,
                    phone=appt.clinic_phone or "")
    return render_template("doctors/booked.html", appt=appt, clinic=clinic,
                           has_location=appt.clinic_lat is not None)
