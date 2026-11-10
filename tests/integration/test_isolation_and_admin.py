"""Authorization: record isolation between users and admin-only areas."""

import csv
import io

import pytest

from app.extensions import db
from app.models import AuditLog, DiseaseClass, Prediction, User
from tests.conftest import PASSWORD, login, logout, register_model

PROTECTED_GET = ["/dashboard", "/analyze", "/history/", "/history/export.csv", "/account/"]
ADMIN_GET = ["/admin/", "/admin/users", "/admin/models", "/admin/categories", "/admin/categories/mel",
             "/admin/analytics", "/admin/audit", "/admin/exports", "/admin/exports/fact_predictions.csv"]


@pytest.mark.parametrize("path", PROTECTED_GET + ADMIN_GET)
def test_anonymous_is_redirected_to_login(client, path):
    r = client.get(path)
    assert r.status_code == 302 and "/auth/login" in r.headers["Location"]


@pytest.mark.parametrize("path", ["/api/v1/me/stats", "/api/v1/admin/analytics", "/api/v1/admin/overview"])
def test_api_requires_auth(client, path):
    r = client.get(path)
    assert r.status_code == 401 and r.is_json


def test_regular_user_gets_403_on_admin(client, user):
    login(client)
    for path in ADMIN_GET:
        assert client.get(path).status_code == 403, path
    for path in ["/api/v1/admin/analytics", "/api/v1/admin/overview"]:
        assert client.get(path).status_code == 403, path
    target = db.session.scalar(db.select(User).filter_by(email="alice@example.com"))
    for path in [f"/admin/users/{target.public_id}/active", f"/admin/users/{target.public_id}/role",
                 "/admin/models/1/activate", "/admin/categories/mel"]:
        assert client.post(path, data={"role": "admin"}).status_code == 403, path
    db.session.refresh(target)
    assert target.role == "user"


def test_users_cannot_access_each_others_records(app, analysed, other_user):
    iid, pid = analysed
    pred = db.session.scalar(db.select(Prediction).filter_by(public_id=pid))
    intruder = app.test_client()
    login(intruder, "bob@example.com")
    for path in [f"/results/{pid}", f"/media/images/{iid}", f"/media/explanations/{pid}", f"/analyze/{iid}"]:
        assert intruder.get(path).status_code == 404, path
    assert intruder.post(f"/analyze/{iid}", data={"consent": "y"}).status_code == 404
    assert intruder.post(f"/history/{pid}/delete").status_code == 404
    assert intruder.post(f"/results/{pid}/feedback", data={"is_correct": "yes"}).status_code == 404
    assert b'href="/results/' not in intruder.get("/history/").data
    assert intruder.get("/api/v1/me/stats").get_json()["total"] == 0
    rows = list(csv.reader(io.StringIO(intruder.get("/history/export.csv").data.decode("utf-8-sig"))))
    assert len(rows) == 1  # header only
    db.session.refresh(pred)
    assert pred.deleted_at is None and pred.feedback is None


def test_admin_cannot_view_user_images(app, analysed, admin):
    iid, pid = analysed
    c = app.test_client()
    login(c, "admin@example.com")
    assert c.get(f"/media/images/{iid}").status_code == 404
    assert c.get(f"/results/{pid}").status_code == 404


def test_admin_pages_render_with_real_numbers(client, analysed, admin):
    logout(client)
    login(client, "admin@example.com")
    html = client.get("/admin/").data.decode()
    assert '<div class="value">1</div><div class="label">Analyses stored</div>' in html
    for path in ADMIN_GET:
        assert client.get(path).status_code == 200, path
    data = client.get("/api/v1/admin/analytics").get_json()
    assert data["total"] == 1 and sum(r["count"] for r in data["daily"]) == 1
    assert sum(r["count"] for r in data["confidence_histogram"]) == 1
    ov = client.get("/api/v1/admin/overview").get_json()
    assert ov["predictions"] == 1 and ov["users"] == 2


def test_admin_user_management_rules(client, admin, user):
    login(client, "admin@example.com")
    # cannot deactivate or demote self; cannot remove the last admin
    assert client.post(f"/admin/users/{admin.public_id}/active").status_code == 302
    db.session.refresh(admin)
    assert admin.is_active_flag
    client.post(f"/admin/users/{admin.public_id}/role", data={"role": "user"})
    db.session.refresh(admin)
    assert admin.role == "admin"

    # deactivating a user ends their session immediately
    victim = app_client = client.application.test_client()
    login(app_client)
    assert victim.get("/dashboard").status_code == 200
    client.post(f"/admin/users/{user.public_id}/active")
    db.session.refresh(user)
    assert user.is_active_flag is False
    assert victim.get("/dashboard").status_code == 302
    client.post(f"/admin/users/{user.public_id}/active")  # reactivate
    db.session.refresh(user)
    assert user.is_active_flag is True

    # promote, and invalid role value rejected
    assert client.post(f"/admin/users/{user.public_id}/role", data={"role": "superuser"}).status_code == 400
    client.post(f"/admin/users/{user.public_id}/role", data={"role": "admin"})
    db.session.refresh(user)
    assert user.role == "admin"
    assert client.post("/admin/users/00000000-0000-0000-0000-000000000000/active").status_code == 404
    actions = {a for (a,) in db.session.execute(db.select(AuditLog.action))}
    assert {"admin_user_deactivate", "admin_user_active", "admin_role_change"} <= actions


def test_admin_user_search_is_parameterised(client, admin, user):
    login(client, "admin@example.com")
    r = client.get("/admin/users?q=%27%20OR%201%3D1%20--")
    assert r.status_code == 200 and b"No users found" in r.data
    assert b"alice@example.com" in client.get("/admin/users?q=ALICE").data


def test_admin_activate_model_and_edit_category(client, admin, model_dirs):
    a = register_model(model_dirs["confident"])
    b = register_model(model_dirs["uniform"], active=False)
    login(client, "admin@example.com")
    client.post(f"/admin/models/{b.id}/activate")
    db.session.refresh(a)
    db.session.refresh(b)
    assert b.is_active and not a.is_active
    assert client.post("/admin/models/9999/activate").status_code == 404

    assert client.post("/admin/categories/mel", data={"description": "short", "advice": "x"}).status_code == 400
    ok = client.post("/admin/categories/mel", data={"description": "A pigment-cell cancer, described here.",
                                                    "advice": "See a dermatologist promptly please."})
    assert ok.status_code == 302
    assert db.session.scalar(db.select(DiseaseClass).filter_by(code="mel")).advice.startswith("See a dermatologist")
    assert client.get("/admin/categories/nope").status_code == 404


def test_admin_exports_are_pseudonymous(client, analysed, admin, user):
    logout(client)
    login(client, "admin@example.com")
    for name in ("fact_predictions", "fact_prediction_scores", "dim_disease_classes", "dim_model_versions",
                 "fact_feedback"):
        r = client.get(f"/admin/exports/{name}.csv")
        assert r.status_code == 200, name
        text = r.data.decode("utf-8")
        assert text.startswith("﻿"), "UTF-8 BOM for Power BI/Excel"
        assert user.email not in text and user.full_name not in text and user.public_id not in text
    scores = list(csv.DictReader(io.StringIO(client.get("/admin/exports/fact_prediction_scores.csv").data.decode("utf-8-sig"))))
    assert len(scores) == 7
    assert client.get("/admin/exports/users.csv").status_code == 404


def test_formula_injection_neutralised_in_exports(app):
    from app.services.export_service import _cell

    assert _cell("=HYPERLINK(\"http://x\")").startswith("'")
    assert _cell("+1") == "'+1" and _cell("@SUM") == "'@SUM"
    assert _cell(0.5) == "0.500000"


def test_deleted_users_password_is_unusable(client, user):
    login(client)
    client.post("/account/delete", data={"password": PASSWORD, "confirm_text": "DELETE"})
    db.session.refresh(user)
    assert user.password_hash == "!deleted"
