"""Several photos at once, and the "Not sure? Check with both" option."""

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


def test_not_sure_checks_with_both(client, db, user, both):
    login(client)
    loc = _batch_url(_post(client, [(image_bytes(seed=9), "x.jpg")], "auto"))
    assert "checked by" in client.get(loc).data.decode()
    r = client.post(loc, data={"consent": "y"})
    page = client.get(r.headers["Location"]).data.decode()
    assert "Mole checker says" in page and "Rash checker says" in page
    assert "Which answer should I look at?" in page
    domains = sorted(p.model_version.domain for p in db.session.scalars(db.select(Prediction)))
    assert domains == ["general", "lesion"]


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
