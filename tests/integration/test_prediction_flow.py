"""End-to-end: login -> upload -> preview -> analyse -> result -> history -> delete."""

import csv
import io

import numpy as np

from app.extensions import db
from app.models import Image as ImageRow
from app.models import Prediction
from app.services.image_service import resolve_storage_key
from app.services.prediction_service import _status
from skinai_ml.prediction import SkinLesionPredictor, load_rgb_image
from tests.conftest import (
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


def test_consent_is_required(client, user, active_model):
    login(client)
    iid = image_id_from(upload(client, image_bytes()))
    r = analyse(client, iid, consent=False)
    assert r.status_code == 400 and b"tick the box to continue" in r.data
    assert db.session.scalar(db.select(db.func.count(Prediction.id))) == 0


def test_full_flow_stores_real_model_output(client, user, active_model, model_dirs):
    login(client)
    iid = image_id_from(upload(client, image_bytes(seed=3)))
    pid = prediction_id_from(analyse(client, iid))
    pred = _pred(pid)

    # 7 scores stored, summing to 1, ordered, top == predicted class
    probs = {s.disease_class.code: s.probability for s in pred.scores}
    assert len(probs) == 7 and abs(sum(probs.values()) - 1) < 1e-4
    assert pred.predicted_class.code == max(probs, key=probs.get)
    assert pred.model_version_id == active_model.id and pred.inference_ms >= 0

    # stored values equal an independent run of the exported model on the stored image
    direct = SkinLesionPredictor(model_dirs["confident"]).predict_array(
        load_rgb_image(resolve_storage_key(pred.image.storage_key)))
    for code, p in direct.probabilities.items():
        assert abs(probs[code] - p) < 1e-5
    assert pred.status == "confident" and pred.predicted_class.code == "nv"

    page = client.get(f"/results/{pid}")
    assert page.status_code == 200
    html = page.data.decode()
    assert ">Common mole<" in html
    assert "This tool is a student project and not a medical diagnosis. Please consult a qualified dermatologist." in html
    assert "Please consult a qualified dermatologist" in html
    assert "Top 3 possibilities" in html
    assert "It could also be" in html
    assert f"<strong>{probs['nv'] * 100:.1f}%</strong> match" in html

    # Grad-CAM explanation produced and served privately
    assert pred.gradcam_key and resolve_storage_key(pred.gradcam_key).exists()
    assert client.get(f"/media/explanations/{pid}").status_code == 200


def test_inconclusive_when_model_is_unsure(client, user, model_dirs):
    register_model(model_dirs["uniform"])  # near-uniform outputs (~14% each)
    login(client)
    pid = prediction_id_from(analyse(client, image_id_from(upload(client, image_bytes(seed=5)))))
    pred = _pred(pid)
    assert pred.status == "inconclusive"
    html = client.get(f"/results/{pid}").data.decode()
    assert "The result is unclear" in html and "not enough to be sure" in html
    assert "We like to be at least 50% sure" in html
    assert "please see a dermatologist" in html


def test_status_rule():
    assert _status(0.9, 0.05, 0.5, 0.1) == "confident"
    assert _status(0.45, 0.3, 0.5, 0.1) == "inconclusive"   # below threshold
    assert _status(0.55, 0.50, 0.5, 0.1) == "inconclusive"  # too close to runner-up
    assert _status(0.50, 0.30, 0.5, 0.1) == "confident"     # threshold inclusive


def test_same_image_gives_identical_scores(client, user, active_model):
    login(client)
    iid = image_id_from(upload(client, image_bytes(seed=8)))
    a = _pred(prediction_id_from(analyse(client, iid)))
    b = _pred(prediction_id_from(analyse(client, iid)))
    assert [(s.class_id, s.probability) for s in a.scores] == [(s.class_id, s.probability) for s in b.scores]


def test_history_list_filters_and_pagination(client, user, active_model, model_dirs):
    login(client)
    for seed in range(3):
        analyse(client, image_id_from(upload(client, image_bytes(seed=20 + seed))))
    register_model(model_dirs["uniform"])
    analyse(client, image_id_from(upload(client, image_bytes(seed=30))))

    page = client.get("/history/").data.decode()
    assert page.count('href="/results/') == 4
    assert client.get("/history/?status=inconclusive").data.decode().count('href="/results/') == 1
    assert client.get("/history/?category=nv&status=confident").data.decode().count('href="/results/') == 3
    assert client.get("/history/?risk=high").data.decode().count('href="/results/') == 0
    assert b"No checks match" in client.get("/history/?risk=high").data
    assert b"weren" in client.get("/history/?date_from=not-a-date").data  # invalid filter warned, ignored
    assert client.get("/history/?date_from=2000-01-01&date_to=2000-01-02").data.decode().count('href="/results/') == 0
    assert client.get("/history/?page=999").status_code == 200


def test_delete_removes_record_and_files(client, analysed):
    iid, pid = analysed
    pred = _pred(pid)
    img_path = resolve_storage_key(pred.image.storage_key)
    cam_path = resolve_storage_key(pred.gradcam_key)
    r = client.post(f"/history/{pid}/delete")
    assert r.status_code == 302
    assert not img_path.exists() and not cam_path.exists()
    assert client.get(f"/results/{pid}").status_code == 404
    assert client.get(f"/media/images/{iid}").status_code == 404
    assert b'href="/results/' not in client.get("/history/").data
    assert client.get("/history/x/delete").status_code == 405  # GET is not allowed


def test_feedback_saved_and_validated(client, analysed):
    _, pid = analysed
    assert client.post(f"/results/{pid}/feedback", data={"is_correct": "maybe"}).status_code == 302
    assert _pred(pid).feedback is None
    client.post(f"/results/{pid}/feedback", data={"is_correct": "no", "suggested_class": "mel", "comment": "biopsy"})
    fb = _pred(pid).feedback
    assert fb.is_correct is False and fb.suggested_class.code == "mel" and fb.comment == "biopsy"
    client.post(f"/results/{pid}/feedback", data={"is_correct": "yes", "suggested_class": "mel"})
    fb = _pred(pid).feedback
    assert fb.is_correct is True and fb.suggested_class_id is None


def test_user_export_csv_contains_only_own_rows_and_no_pii(client, analysed, user):
    r = client.get("/history/export.csv")
    assert r.status_code == 200 and r.mimetype == "text/csv"
    text = r.data.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    assert len(rows) == 1
    assert user.email not in text and user.full_name not in text and user.public_id not in text
    assert 0 <= float(rows[0]["confidence"]) <= 1


def test_dashboard_reflects_database(client, analysed):
    html = client.get("/dashboard").data.decode()
    assert '<div class="value">1</div><div class="label">Checks done</div>' in html
    stats = client.get("/api/v1/me/stats").get_json()
    assert stats["total"] == 1
    assert sum(c["count"] for c in stats["by_class"]) == 1
    assert stats["status"]["confident"] + stats["status"]["inconclusive"] == 1


def test_model_files_missing_or_tampered_is_handled(client, user, model_dirs, tmp_path):
    import shutil

    bad_dir = tmp_path / "tampered"
    shutil.copytree(model_dirs["confident"], bad_dir)
    with open(bad_dir / "model.keras", "ab") as f:
        f.write(b"x")
    mv = register_model(bad_dir)
    mv.version = "tampered"
    db.session.commit()
    login(client)
    iid = image_id_from(upload(client, image_bytes(seed=40)))
    r = analyse(client, iid)
    assert r.status_code == 500 and b"something went wrong while checking your photo" in r.data
    assert db.session.scalar(db.select(db.func.count(Prediction.id))) == 0
    assert db.session.scalar(db.select(db.func.count(ImageRow.id))) == 1  # image kept for retry


def test_no_randomness_in_prediction_service():
    import inspect

    import app.services.prediction_service as ps

    src = inspect.getsource(ps)
    assert "random" not in src and "np.random" not in src
    assert np is not None
