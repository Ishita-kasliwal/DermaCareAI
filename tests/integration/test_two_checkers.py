"""The two checkers ("mole or spot" and "rash or other skin problem") route to their own models."""

from app.extensions import db
from app.models import DiseaseClass, ModelVersion, Prediction
from tests.conftest import (
    GENERAL_CLASSES,
    analyse,
    image_bytes,
    image_id_from,
    login,
    prediction_id_from,
    register_model,
    upload,
)


def _pred(pid) -> Prediction:
    return db.session.scalar(db.select(Prediction).filter_by(public_id=pid))


def test_all_19_conditions_seeded_with_checker(app):
    rows = list(db.session.scalars(db.select(DiseaseClass)))
    assert len(rows) == 19
    assert sorted(r.code for r in rows if r.domain == "general") == sorted(GENERAL_CLASSES + ["dermatitis", "ringworm"])
    assert len([r for r in rows if r.domain == "lesion"]) == 7
    assert all(r.description and r.advice for r in rows)


def test_rash_photo_uses_rash_model_and_only_its_conditions(client, user, model_dirs):
    register_model(model_dirs["confident"])   # lesion model
    register_model(model_dirs["general"])     # general model (both active: one per checker)
    assert db.session.scalar(db.select(db.func.count(ModelVersion.id)).filter_by(is_active=True)) == 2
    login(client)
    iid = image_id_from(upload(client, image_bytes(seed=60), check="general"))
    pred = _pred(prediction_id_from(analyse(client, iid)))
    assert pred.model_version.domain == "general"
    codes = {s.disease_class.code for s in pred.scores}
    assert codes == set(GENERAL_CLASSES), "rash results only list rash conditions"
    assert pred.predicted_class.code == "eczema"
    html = client.get(f"/results/{pred.public_id}").data.decode()
    assert "How your photo matched all 10 types" in html
    assert "Eczema (atopic dermatitis)" in html
    assert "Good to know." in html and "only knows 10 conditions" in html, "rash results carry the limits warning"

    # the mole checker still uses the mole model
    iid2 = image_id_from(upload(client, image_bytes(seed=61), check="lesion"))
    pred2 = _pred(prediction_id_from(analyse(client, iid2)))
    assert pred2.model_version.domain == "lesion" and len(pred2.scores) == 7


def test_missing_checker_model_is_reported_not_faked(client, user, model_dirs):
    register_model(model_dirs["confident"])  # only the mole model is installed
    login(client)
    page = client.get("/analyze").data.decode()
    assert "Not available yet" in page
    r = upload(client, image_bytes(seed=62), check="general")
    assert r.status_code == 400 and b"isn&#39;t installed yet" in r.data
    assert db.session.scalar(db.select(db.func.count(Prediction.id))) == 0


def test_invalid_checker_value_rejected(client, user, active_model):
    login(client)
    r = upload(client, image_bytes(seed=63), check="tattoo")
    assert r.status_code == 400


def test_activating_one_checker_keeps_the_other(client, admin, model_dirs):
    a = register_model(model_dirs["confident"])
    g = register_model(model_dirs["general"])
    u = register_model(model_dirs["uniform"], active=False)
    login(client, "admin@example.com")
    client.post(f"/admin/models/{u.id}/activate")
    for m in (a, g, u):
        db.session.refresh(m)
    assert u.is_active and not a.is_active and g.is_active
