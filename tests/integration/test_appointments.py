"""Clinic card buttons and appointment requests (Task 5)."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.models import Appointment, AuditLog
from app.services import doctor_search as ds
from tests.conftest import login, logout

IST = timezone(timedelta(hours=5, minutes=30))


def today_ist():
    return datetime.now(UTC).astimezone(IST).date()


CLINIC = {"name": "Well Skin Clinic", "address": "Sapna Sangeeta Road, Indore", "phone": "9713193581",
          "lat": "22.705800", "lon": "75.867700"}


def booking(**over):
    data = {"patient_name": "Asha Verma", "patient_phone": "98765 43210",
            "preferred_date": (today_ist() + timedelta(days=2)).isoformat(), "time_slot": "morning",
            "note": "Itchy rash on arm", "clinic_name": CLINIC["name"], "clinic_address": CLINIC["address"],
            "clinic_phone": CLINIC["phone"], "clinic_lat": CLINIC["lat"], "clinic_lon": CLINIC["lon"]}
    data.update(over)
    return data


# ---------------------------------------------------------------- clinic card links
def test_clinic_links():
    c = ds.Clinic("X Skin Clinic", "Road", 22.7058, 75.8677, phone="07312547200;8982693241")
    assert c.directions_url == "https://www.google.com/maps/dir/?api=1&destination=22.705800,75.867700"
    assert c.display_phone == "07312547200" and c.tel_href == "tel:07312547200"
    assert ds.Clinic("Y", "", 1, 2, phone="+91 98765 43210").tel_href == "tel:+919876543210"
    assert ds.Clinic("Z", "", 1, 2, phone="").tel_href == ""


def test_cards_show_call_directions_book(client, monkeypatch):
    def fake_search(city, district, state, google_key=""):
        r = ds.SearchResult(level="city", area="Indore", source="OpenStreetMap",
                            maps_search_url=ds.google_maps_search_url(city, district, state))
        r.clinics = [ds.Clinic("Near Skin Clinic", "MG Road", 22.70, 75.86, phone="9713193581", distance_km=1.2),
                     ds.Clinic("No Phone Skin Clinic", "AB Road", 22.72, 75.88, distance_km=3.4)]
        return r
    import app.blueprints.doctors.routes as routes
    monkeypatch.setattr(routes, "search", fake_search)
    html = client.get("/find-a-dermatologist?city=Indore&state=Madhya+Pradesh&prediction=abc").data.decode()
    assert html.index("Near Skin Clinic") < html.index("No Phone Skin Clinic")         # nearest first
    assert 'href="tel:9713193581"' in html and "Phone number not available" in html
    assert "google.com/maps/dir/?api=1&amp;destination=22.700000,75.860000" in html
    assert 'target="_blank"' in html
    assert "/book?name=Near+Skin+Clinic" in html and "prediction=abc" in html


# ---------------------------------------------------------------- booking
def test_booking_needs_login(client):
    r = client.get("/book?name=Well+Skin+Clinic")
    assert r.status_code == 302 and "/auth/login" in r.headers["Location"]


def test_booking_form_prefilled(client, user):
    login(client)
    html = client.get("/book?" + "&".join(f"{k}={v}" for k, v in CLINIC.items())).data.decode()
    assert "Ask for an appointment" in html and "Well Skin Clinic" in html
    assert "does\n      <strong>not</strong> get a message from us" in html or "not</strong> get a message" in html
    assert 'href="tel:9713193581"' in html


def test_booking_saved_with_friendly_message(client, db, user):
    login(client)
    r = client.post("/book", data=booking())
    assert r.status_code == 302 and "/book/" in r.headers["Location"]
    appt = db.session.scalar(db.select(Appointment))
    assert appt.patient_phone == "9876543210" and appt.time_slot == "morning"
    assert appt.clinic_name == "Well Skin Clinic" and appt.status == "requested"
    assert db.session.scalar(db.select(AuditLog).filter_by(action="appointment_request")) is not None
    page = client.get(r.headers["Location"]).data.decode()
    assert "Thank you, Asha Verma! Your request is saved." in page
    assert "the clinic hasn" in page          # honest: the clinic is not told automatically


@pytest.mark.parametrize(("field", "value", "message"), [
    ("patient_name", "", "Please tell us your name."),
    ("patient_phone", "12345", "Please type a 10-digit mobile number"),
    ("patient_phone", "1234567890", "Please type a 10-digit mobile number"),
    ("preferred_date", "2020-01-01", "Please choose today or a later date."),
    ("time_slot", "", "Please choose a time of day."),
])
def test_booking_polite_validation(client, db, user, field, value, message):
    login(client)
    r = client.post("/book", data=booking(**{field: value}))
    assert r.status_code == 400 and message in r.data.decode().replace("&#39;", "'")
    assert db.session.scalar(db.select(db.func.count(Appointment.id))) == 0


def test_confirmation_only_visible_to_its_owner(client, db, user, admin):
    login(client)
    loc = client.post("/book", data=booking()).headers["Location"]
    logout(client)
    login(client, "admin@example.com")
    assert client.get(loc).status_code == 404


# ---------------------------------------------------------------- admin list
def test_admin_list_newest_first(client, db, user, admin):
    login(client)
    client.post("/book", data=booking(patient_name="First Person"))
    client.post("/book", data=booking(patient_name="Second Person"))
    assert client.get("/admin/appointments").status_code in (302, 403, 404)   # not for normal users
    logout(client)
    login(client, "admin@example.com")
    html = client.get("/admin/appointments").data.decode()
    assert "Appointment requests" in html
    assert html.index("Second Person") < html.index("First Person")
    assert "9876543210" in html and "Well Skin Clinic" in html


def test_account_delete_removes_appointments(client, db, user):
    login(client)
    client.post("/book", data=booking())
    assert db.session.scalar(db.select(db.func.count(Appointment.id))) == 1
    from app.services.auth_service import delete_account
    from tests.conftest import PASSWORD
    delete_account(user, PASSWORD)
    assert db.session.scalar(db.select(db.func.count(Appointment.id))) == 0
