"""Google sign-in, Excel downloads, the face-photo warning and switching checkers."""

import io

import pytest
from openpyxl import load_workbook

from app.models import AuditLog, User
from app.services import google_auth, quality_service
from tests.conftest import (
    analyse,
    image_bytes,
    image_id_from,
    login,
    make_user,
    prediction_id_from,
    register_model,
    upload,
)


# ----------------------------------------------------------------- Google sign-in
class FakeGoogle:
    def __init__(self, info):
        self.info = info

    def authorize_redirect(self, redirect_uri):
        from flask import redirect

        assert redirect_uri.endswith("/auth/google/callback")
        return redirect("https://accounts.google.com/o/oauth2/v2/auth?fake=1")

    def authorize_access_token(self):
        return {"userinfo": self.info}


@pytest.fixture()
def google_on(app, monkeypatch):
    app.config.update(GOOGLE_CLIENT_ID="test-id.apps.googleusercontent.com", GOOGLE_CLIENT_SECRET="test-secret")
    holder = {"info": {"sub": "g-123", "email": "gita@example.com", "email_verified": True, "name": "Gita Rao"}}
    monkeypatch.setattr(google_auth, "client", lambda: FakeGoogle(holder["info"]))
    return holder


def test_google_button_hidden_when_not_configured(client):
    assert "Continue with Google" not in client.get("/auth/login").data.decode()
    r = client.get("/auth/google")
    assert r.status_code == 302 and r.headers["Location"].endswith("/auth/login")


def test_google_button_shown_when_configured(client, google_on):
    assert "Continue with Google" in client.get("/auth/login").data.decode()
    assert "Sign up with Google" in client.get("/auth/register").data.decode()
    r = client.get("/auth/google")
    assert r.status_code == 302 and r.headers["Location"].startswith("https://accounts.google.com/")


def test_google_creates_new_account_without_password(client, db, google_on):
    r = client.get("/auth/google/callback?code=x&state=y")
    assert r.status_code == 302 and r.headers["Location"].endswith("/dashboard")
    u = db.session.scalar(db.select(User).filter_by(email="gita@example.com"))
    assert u.google_sub == "g-123" and u.full_name == "Gita Rao" and not u.has_password
    assert client.get("/dashboard").status_code == 200
    page = client.get("/account/").data.decode()
    assert "Add a password" in page and "Current password" not in page
    # the account can add a password without knowing an old one
    r = client.post("/account/password", data={"new_password": "Tulsi-Garden-2026", "confirm": "Tulsi-Garden-2026"})
    assert r.status_code == 302
    db.session.expire_all()
    assert db.session.get(User, u.id).has_password


def test_google_links_existing_account_by_verified_email(client, db, google_on):
    u = make_user(email="gita@example.com", name="Gita R")
    client.get("/auth/google/callback?code=x&state=y")
    db.session.expire_all()
    u = db.session.get(User, u.id)
    assert u.google_sub == "g-123" and u.has_password and u.full_name == "Gita R"
    assert db.session.scalar(db.select(AuditLog).filter_by(action="google_linked")) is not None


def test_google_refuses_unverified_email(client, db, google_on):
    google_on["info"] = {"sub": "g-9", "email": "x@example.com", "email_verified": False}
    r = client.get("/auth/google/callback?code=x&state=y", follow_redirects=True)
    assert "isn&#39;t verified" in r.data.decode()
    assert db.session.scalar(db.select(User).filter_by(email="x@example.com")) is None
    assert client.get("/dashboard").status_code == 302


def test_google_refuses_switched_off_account(client, db, google_on):
    u = make_user(email="gita@example.com")
    u.is_active_flag = False
    db.session.commit()
    r = client.get("/auth/google/callback?code=x&state=y", follow_redirects=True)
    assert "switched off" in r.data.decode()
    assert client.get("/dashboard").status_code == 302


def test_google_cancel_goes_back_to_login(client, google_on):
    r = client.get("/auth/google/callback?error=access_denied", follow_redirects=True)
    assert "cancelled" in r.data.decode()


def test_google_only_account_can_delete_without_password(client, db, google_on):
    client.get("/auth/google/callback?code=x&state=y")
    r = client.post("/account/delete", data={"confirm_text": "DELETE"})
    assert r.status_code == 302
    u = db.session.scalar(db.select(User).filter_by(google_sub="g-123"))
    assert u is None  # google link removed on delete


def test_password_account_still_needs_password_to_delete(client, user):
    login(client)
    r = client.post("/account/delete", data={"confirm_text": "DELETE"})
    assert r.status_code == 400 and "Please enter your password to confirm." in r.data.decode()
    r = client.post("/account/password", data={"new_password": "Another-Pass-77", "confirm": "Another-Pass-77"})
    assert r.status_code == 400 and "Please enter your current password." in r.data.decode()


# ----------------------------------------------------------------- Excel downloads
def test_user_excel_has_only_own_rows(client, analysed, user, other_user):
    r = client.get("/history/export.xlsx")
    assert r.status_code == 200 and r.mimetype.endswith("spreadsheetml.sheet")
    wb = load_workbook(io.BytesIO(r.data))
    ws = wb["My checks"]
    rows = list(ws.iter_rows(values_only=True))
    assert rows[0][:3] == ("Date (UTC)", "What I checked", "Closest match")
    assert len(rows) == 2 and 0 <= rows[1][3] <= 1
    assert "Please read" in wb.sheetnames
    text = " ".join(str(c) for row in rows for c in row)
    assert user.email not in text


def test_excel_formula_injection_guard():
    from app.services.export_service import _xl_cell

    assert _xl_cell("=HYPERLINK(\"x\")") == "'=HYPERLINK(\"x\")"
    assert _xl_cell("@SUM(A1)").startswith("'") and _xl_cell("Eczema") == "Eczema" and _xl_cell(0.5) == 0.5


def test_admin_excel_workbook(client, analysed, admin):
    client.post("/auth/logout")
    login(client, email=admin.email)
    r = client.get("/admin/exports/dermacareai_data.xlsx")
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.data))
    assert set(wb.sheetnames) == {"fact_predictions", "fact_prediction_scores", "dim_disease_classes",
                                  "dim_model_versions", "fact_feedback"}
    preds = list(wb["fact_predictions"].iter_rows(values_only=True))
    assert len(preds) == 2 and isinstance(preds[1][5], float)


def test_excel_requires_login_and_admin(client, user):
    assert client.get("/history/export.xlsx").status_code == 302
    login(client)
    assert client.get("/admin/exports/dermacareai_data.xlsx").status_code in (403, 404)


# ----------------------------------------------------------------- face warning + switch checker
@pytest.fixture()
def both_models(app, model_dirs):
    return register_model(model_dirs["confident"]), register_model(model_dirs["general"])


def test_face_photo_warns_and_can_switch_to_rash_checker(client, db, user, both_models, monkeypatch):
    monkeypatch.setattr(quality_service, "detect_face", lambda rgb: True)
    login(client)
    iid = image_id_from(upload(client, image_bytes(seed=4), check="lesion"))
    page = client.get(f"/analyze/{iid}").data.decode()
    assert "This looks like a photo of a face." in page and "Switch to the rash checker" in page

    r = client.post(f"/analyze/{iid}/switch")
    assert r.status_code == 302
    page = client.get(f"/analyze/{iid}").data.decode()
    assert "This looks like a photo of a face." not in page
    assert "A rash or other skin problem" in page
    pid = prediction_id_from(analyse(client, iid))
    assert client.get(f"/results/{pid}").status_code == 200


def test_face_warning_not_added_for_rash_checker(client, user, both_models, monkeypatch):
    monkeypatch.setattr(quality_service, "detect_face", lambda rgb: True)
    login(client)
    iid = image_id_from(upload(client, image_bytes(seed=5), check="general"))
    assert "This looks like a photo of a face." not in client.get(f"/analyze/{iid}").data.decode()


def test_switch_needs_owner(client, user, other_user, both_models):
    login(client)
    iid = image_id_from(upload(client, image_bytes(seed=6)))
    client.post("/auth/logout")
    login(client, email=other_user.email)
    assert client.post(f"/analyze/{iid}/switch").status_code == 404


def test_detect_face_false_on_skin_texture():
    import numpy as np

    rng = np.random.default_rng(0)
    rgb = np.clip(rng.normal(150, 30, (300, 300, 3)), 0, 255).astype(np.uint8)
    assert quality_service.detect_face(rgb) is False
