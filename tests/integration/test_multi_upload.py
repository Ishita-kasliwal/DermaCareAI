"""Several photos at once, and the "Not sure? Let the AI choose" option."""

import io
import re

import pytest

from app.models import Prediction
from tests.conftest import image_bytes, login, register_model


def _post(client, files, check):
    return client.post("/analyze", data={"image": [(io.BytesIO(b), n) for b, n in files], "check_type": check},
                       content_type="multipart/form-data")


@pytest.fixture()
def both(app, model_dirs):
    return register_model(model_dirs["confident"]), register_model(model_dirs["general"])


def _batch_url(r):
    assert r.status_code == 302, r.data[:300]
    loc = r.headers["Location"]
    assert "/analyze/batch?" in loc
    return loc


def test_several_photos_checked_together(client, db, user, both):
    login(client)
    loc = _batch_url(_post(client, [(image_bytes(seed=i), f"p{i}.jpg") for i in range(3)], "lesion"))
    page = client.get(loc).data.decode()
    assert "Check your 3 photos" in page
    assert client.post(loc, data={}).status_code == 400  # consent required
    r = client.post(loc, data={"consent": "y"})
    assert r.status_code == 302 and "/results/batch?" in r.headers["Location"]
    page = client.get(r.headers["Location"]).data.decode()
    assert page.count("Mole checker says") == 3
    assert db.session.scalar(db.select(db.func.count(Prediction.id))) == 3


def _sorter(monkeypatch, p_mole):
    """Fake the photo sorter's answer (None = no sorter installed)."""
    monkeypatch.setattr("skinai_ml.prediction.SkinLesionPredictor.mole_photo_probability", lambda self, rgb: p_mole)


def test_not_sure_without_sorter_falls_back_to_both(client, db, user, both, monkeypatch):
    _sorter(monkeypatch, None)
    login(client)
    loc = _batch_url(_post(client, [(image_bytes(seed=9), "x.jpg")], "auto"))
    assert "checked by" in client.get(loc).data.decode()
    r = client.post(loc, data={"consent": "y"})
    page = client.get(r.headers["Location"]).data.decode()
    assert "Mole checker says" in page and "Rash checker says" in page
    domains = sorted(p.model_version.domain for p in db.session.scalars(db.select(Prediction)))
    assert domains == ["general", "lesion"]


def test_not_sure_rash_photo_gives_one_rash_answer(client, db, user, both, monkeypatch):
    _sorter(monkeypatch, 0.01)                      # looks like a rash/acne photo
    login(client)
    r = client.post(_batch_url(_post(client, [(image_bytes(seed=9), "x.jpg")], "auto")), data={"consent": "y"})
    assert "/results/" in r.headers["Location"] and "/results/batch" not in r.headers["Location"]  # straight to it
    domains = [p.model_version.domain for p in db.session.scalars(db.select(Prediction))]
    assert domains == ["general"], "no mole/skin-cancer answer next to a rash answer"


def test_not_sure_mole_photo_uses_only_the_mole_checker(client, db, user, both, monkeypatch):
    _sorter(monkeypatch, 0.99)                      # looks like a single mole close-up
    login(client)
    r = client.post(_batch_url(_post(client, [(image_bytes(seed=9), "x.jpg")], "auto")), data={"consent": "y"})
    assert r.status_code == 302
    preds = list(db.session.scalars(db.select(Prediction)))
    assert [p.model_version.domain for p in preds] == ["lesion"]
    assert preds[0].image.domain == "lesion"


def test_upload_page_recommends_letting_the_ai_choose(client, user, both):
    login(client)
    html = client.get("/analyze").data.decode()
    assert "Not sure? Let the AI choose" in html
    assert re.search(r'value="auto"[^>]*checked|checked[^>]*value="auto"', html)


def test_too_many_photos_rejected(client, user, both):
    login(client)
    r = _post(client, [(image_bytes(seed=i), f"p{i}.jpg") for i in range(6)], "lesion")
    assert r.status_code == 400 and "up to 5 photos" in r.data.decode()


def test_bad_file_skipped_when_others_ok(client, user, both):
    login(client)
    r = _post(client, [(image_bytes(seed=1), "ok.jpg"), (b"not an image", "bad.jpg")], "general")
    loc = _batch_url(r)
    assert len(re.search(r"ids=([^&]+)", loc).group(1).split("%2C")) == 1


def test_batch_pages_only_show_own_photos(client, user, other_user, both):
    login(client)
    loc = _batch_url(_post(client, [(image_bytes(seed=1), "a.jpg"), (image_bytes(seed=2), "b.jpg")], "lesion"))
    res = client.post(loc, data={"consent": "y"}).headers["Location"]
    client.post("/auth/logout")
    login(client, email=other_user.email)
    assert client.get(loc).status_code == 404
    assert client.post(loc, data={"consent": "y"}).status_code == 404
    assert client.get(res).status_code == 404


def test_upload_page_offers_the_camera(client, user, both):
    login(client)
    r = client.get("/analyze")
    html = r.data.decode()
    assert "Take a photo" in html and 'capture="environment"' in html and "data-camera-dialog" in html
    policy = r.headers.get("Permissions-Policy", "")
    assert "camera=(self)" in policy and "microphone=()" in policy   # this site only, never the microphone
