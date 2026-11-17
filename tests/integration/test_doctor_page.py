"""Doctor page: appointment requests for the doctor's own clinic, with photos only when the patient shares."""

import pytest

from app.models import Appointment, AuditLog
from tests.conftest import (
    analyse,
    image_bytes,
    image_id_from,
    login,
    logout,
    make_user,
    prediction_id_from,
    register_model,
    upload,
)
from tests.integration.test_appointments import booking


@pytest.fixture()
def doctor(app):
    d = make_user("doc@example.com", "Dr Rao", role="doctor")
    d.clinic_name = "Well Skin Clinic"
    from app.extensions import db
    db.session.commit()
    return d


def _book(client, db, model_dirs, share, clinic="Well Skin Clinic", name="Asha Verma"):
    """The patient (alice) checks a photo, then books at a clinic with or without sharing it."""
    register_model(model_dirs["general"])
    login(client)
    pid = prediction_id_from(analyse(client, image_id_from(upload(client, image_bytes(seed=33), check="general"))))
    data = booking(patient_name=name, clinic_name=clinic, prediction=pid)
    if share:
        data["share_photo"] = "y"
    r = client.post("/book", data=data)
    assert r.status_code == 302, r.data[:300]
    logout(client)
    return db.session.scalar(db.select(Appointment).filter_by(patient_name=name)), pid


def test_shared_photo_visible_to_that_clinic_only(client, db, user, doctor, model_dirs):
    appt, _ = _book(client, db, model_dirs, share=True)
    assert appt.share_photo is True
    login(client, "doc@example.com")
    html = client.get("/doctor/").data.decode()
    assert "Asha Verma" in html and "AI check:" in html
    photo = client.get(f"/doctor/appointments/{appt.public_id}/photo")
    assert photo.status_code == 200 and photo.mimetype == "image/jpeg"
    assert photo.headers["Cache-Control"] == "private, no-store"
    assert db.session.scalar(db.select(AuditLog).filter_by(action="doctor_photo_view")) is not None


def test_no_photo_when_patient_did_not_share(client, db, user, doctor, model_dirs):
    appt, _ = _book(client, db, model_dirs, share=False)
    login(client, "doc@example.com")
    html = client.get("/doctor/").data.decode()
    assert "Asha Verma" in html and "No photo shared" in html
    assert client.get(f"/doctor/appointments/{appt.public_id}/photo").status_code == 404


def test_other_clinics_requests_are_hidden(client, db, user, doctor, model_dirs):
    appt, _ = _book(client, db, model_dirs, share=True, clinic="Another Skin Clinic", name="Other Patient")
    login(client, "doc@example.com")
    assert "Other Patient" not in client.get("/doctor/").data.decode()
    assert client.get(f"/doctor/appointments/{appt.public_id}/photo").status_code == 404


def test_patient_deleting_the_check_removes_the_photo(client, db, user, doctor, model_dirs):
    appt, pid = _book(client, db, model_dirs, share=True)
    login(client)
    client.post(f"/history/{pid}/delete", data={})
    logout(client)
    login(client, "doc@example.com")
    assert client.get(f"/doctor/appointments/{appt.public_id}/photo").status_code == 404


def test_only_doctors_can_open_the_page(client, db, user, admin):
    login(client)
    assert client.get("/doctor/").status_code == 403
    logout(client)
    login(client, "admin@example.com")
    assert client.get("/doctor/").status_code == 403


def test_admin_makes_a_doctor_only_with_a_clinic(client, db, user, admin):
    login(client, "admin@example.com")
    r = client.post(f"/admin/users/{user.public_id}/role", data={"role": "doctor", "clinic_name": ""})
    assert r.status_code == 302
    db.session.refresh(user)
    assert user.role == "user"
    client.post(f"/admin/users/{user.public_id}/role", data={"role": "doctor", "clinic_name": "Well Skin Clinic"})
    db.session.refresh(user)
    assert user.role == "doctor" and user.clinic_name == "Well Skin Clinic"
