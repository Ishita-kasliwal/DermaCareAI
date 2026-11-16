from flask import current_app, render_template, request
from flask_login import current_user

from app.blueprints.doctors import bp
from app.extensions import limiter
from app.forms import DoctorSearchForm
from app.services.doctor_search import search


@bp.get("/find-a-dermatologist")
@limiter.limit("30 per hour")
def find():
    """Search form + results. Results appear only after a valid search (GET, so the page can be bookmarked)."""
    form = DoctorSearchForm(request.args)
    result = None
    submitted = "city" in request.args or "state" in request.args
    if submitted and form.validate():
        result = search(form.city.data, form.district.data or "", form.state.data,
                        google_key=current_app.config.get("GOOGLE_MAPS_API_KEY", ""))
    if not submitted and current_user.is_authenticated and not form.state.data:
        form.state.data = ""   # no state stored on profiles yet; the person chooses it
    return render_template("doctors/find.html", form=form, result=result, submitted=submitted)
