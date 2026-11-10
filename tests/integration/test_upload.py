import io

import numpy as np
from PIL import Image

from app.extensions import db
from app.models import Image as ImageRow
from app.services.image_service import resolve_storage_key
from tests.conftest import image_bytes, image_id_from, login, upload


def _stored(iid) -> ImageRow:
    return db.session.scalar(db.select(ImageRow).filter_by(public_id=iid))


def test_upload_requires_login(client):
    r = upload(client, image_bytes())
    assert r.status_code == 302 and "/auth/login" in r.headers["Location"]


def test_upload_blocked_when_no_model(client, user):
    login(client)
    r = client.get("/analyze")
    assert b"The AI isn" in r.data and b"t ready yet" in r.data
    r = upload(client, image_bytes())
    assert r.status_code == 400 and b"the AI isn&#39;t installed" in r.data
    assert db.session.scalar(db.select(db.func.count(ImageRow.id))) == 0


def test_valid_jpeg_is_sanitised_and_stored_privately(client, user, active_model, app):
    login(client)
    exif = Image.Exif()
    exif[0x010F] = "SecretCameraMaker"  # Make
    exif[0x8825] = {2: (51.0, 30.0, 0.0)}  # GPS IFD
    r = upload(client, image_bytes(exif=exif), filename="../../etc/passwd.jpg")
    iid = image_id_from(r)
    row = _stored(iid)
    path = resolve_storage_key(row.storage_key)
    assert path.exists()
    upload_root = app.config["UPLOAD_DIR"].resolve()
    assert upload_root in path.resolve().parents, "stored under the private upload dir"
    assert "static" not in str(path).lower()
    assert "passwd" not in row.storage_key and ".." not in row.storage_key
    stored = Image.open(path)
    assert stored.format == "JPEG"
    assert not stored.getexif(), "EXIF (incl. GPS) removed"
    assert b"SecretCameraMaker" not in path.read_bytes()
    # preview page renders and serves the image only via the authenticated route
    assert client.get(f"/analyze/{iid}").status_code == 200
    img = client.get(f"/media/images/{iid}")
    assert img.status_code == 200 and img.mimetype == "image/jpeg"
    assert "no-store" in img.headers["Cache-Control"]


def test_png_with_alpha_accepted(client, user, active_model):
    login(client)
    r = upload(client, image_bytes(fmt="PNG", mode="RGBA"), filename="x.png")
    assert r.status_code == 302


def test_rejects_unsupported_and_malicious_files(client, user, active_model):
    login(client)
    gif = io.BytesIO()
    Image.fromarray(np.zeros((300, 300, 3), np.uint8) + 120).save(gif, format="GIF")
    cases = [
        (b"<?php system($_GET['c']); ?>", "shell.jpg", b"couldn&#39;t open this file"),
        (b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>", "x.svg", b"(.jpg, .jpeg or .png)"),
        (gif.getvalue(), "anim.jpg", b"Please upload a JPG or PNG photo."),
        (image_bytes(), "lesion.exe", b"(.jpg, .jpeg or .png)"),
        (image_bytes()[:400], "truncated.jpg", b"couldn&#39;t open this file"),
        (b"", "empty.jpg", b"empty"),
        (image_bytes(size=(150, 120)), "tiny.jpg", b"too small"),
    ]
    for data, name, msg in cases:
        r = upload(client, data, filename=name)
        assert r.status_code == 400, name
        assert msg in r.data, (name, r.data[:2000])
    assert db.session.scalar(db.select(db.func.count(ImageRow.id))) == 0


def test_polyglot_jpeg_with_appended_payload_is_reencoded(client, user, active_model):
    login(client)
    payload = b"<script>alert(1)</script>"
    iid = image_id_from(upload(client, image_bytes() + payload))
    path = resolve_storage_key(_stored(iid).storage_key)
    assert payload not in path.read_bytes()


def test_decompression_bomb_rejected(client, user, active_model):
    login(client)
    buf = io.BytesIO()
    Image.new("1", (12000, 12000)).save(buf, format="PNG")  # 144 MP, tiny file
    r = upload(client, buf.getvalue(), filename="bomb.png")
    assert r.status_code == 400 and b"too large" in r.data


def test_oversized_upload_rejected_with_413(client, user, active_model, app):
    login(client)
    big = b"\xff\xd8" + b"0" * (app.config["MAX_CONTENT_LENGTH"] + 10)
    r = upload(client, big)
    assert r.status_code == 413 and b"upload limit" in r.data


def test_blank_image_rejected_and_greyscale_warned(client, user, active_model):
    login(client)
    blank = io.BytesIO()
    Image.new("RGB", (300, 300), (200, 180, 170)).save(blank, format="JPEG")
    r = upload(client, blank.getvalue())
    assert r.status_code == 400 and b"almost blank" in r.data
    iid = image_id_from(upload(client, image_bytes(colour=False, seed=4)))
    row = _stored(iid)
    assert not row.quality_ok and "greyscale" in [i["code"] for i in row.quality_issues]
    assert b"black-and-white" in client.get(f"/analyze/{iid}").data


def test_duplicate_upload_reuses_image(client, user, active_model):
    login(client)
    data = image_bytes(seed=9)
    a = image_id_from(upload(client, data))
    b = image_id_from(upload(client, data))
    assert a == b
    assert db.session.scalar(db.select(db.func.count(ImageRow.id))) == 1


def test_missing_file_field(client, user, active_model):
    login(client)
    r = client.post("/analyze", data={}, content_type="multipart/form-data")
    assert r.status_code == 400 and b"choose a photo to upload" in r.data
