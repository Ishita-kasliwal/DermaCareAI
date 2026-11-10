import numpy as np

from app.security.passwords import hash_password, needs_rehash, password_problems, verify_password
from app.security.utils import safe_next_url
from app.services.quality_service import assess


def test_password_hashing_roundtrip():
    h = hash_password("Some-Long-Pass-9")
    assert h.startswith("$argon2id$") and "Some-Long-Pass-9" not in h
    assert verify_password(h, "Some-Long-Pass-9")
    assert not verify_password(h, "some-long-pass-9")
    assert not verify_password(None, "anything-at-all")
    assert not verify_password("garbage", "anything-at-all")
    assert not needs_rehash(h)
    assert hash_password("Some-Long-Pass-9") != h, "salted"


def test_password_policy():
    assert password_problems("Correct-Horse-91") == []
    assert password_problems("short")
    assert password_problems("aaaaaaaaaaaa")
    assert password_problems("alice-secure-pass", email="alice@example.com")
    assert password_problems("x" * 129)


def test_safe_next_url():
    assert safe_next_url("/history/", "/d") == "/history/"
    for bad in ("http://evil", "//evil", "/\\evil", "evil", "javascript:x", None, ""):
        assert safe_next_url(bad, "/d") == "/d"


def _textured(seed=0, sigma=30):
    rng = np.random.default_rng(seed)
    return np.clip(rng.normal(128, sigma, (300, 300, 3)), 0, 255).astype(np.uint8)


def test_quality_good_image():
    r = assess(_textured())
    assert r.ok and not r.rejected and r.blur_score > 40


def test_quality_blank_rejected():
    r = assess(np.full((300, 300, 3), 120, np.uint8))
    assert r.rejected and r.issues[0]["code"] == "blank"


def test_quality_dark_bright_blurry_grey():
    import cv2

    dark = (_textured(sigma=80) * 0.2).astype(np.uint8)  # dim but still textured
    assert "dark" in [i["code"] for i in assess(dark).issues]
    bright = np.clip(_textured().astype(int) + 140, 0, 255).astype(np.uint8)
    assert "overexposed" in [i["code"] for i in assess(bright).issues]
    lesion = np.full((300, 300, 3), (205, 160, 140), np.uint8)  # skin-coloured background
    cv2.circle(lesion, (150, 150), 70, (90, 55, 40), -1)         # dark lesion
    assert "blurry" not in [i["code"] for i in assess(lesion).issues]
    blurry = cv2.GaussianBlur(lesion, (0, 0), 8)
    assert "blurry" in [i["code"] for i in assess(blurry).issues]
    grey = np.repeat(_textured()[..., :1], 3, axis=2)
    assert "greyscale" in [i["code"] for i in assess(grey).issues]
