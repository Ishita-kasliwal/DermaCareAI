"""Secure image intake: validate -> sanitise (re-encode, strip metadata) -> store privately.

Files are written under UPLOAD_DIR (instance/uploads), never under /static, with server-generated
names. They are served only through ownership-checked routes.
"""

from __future__ import annotations

import hashlib
import io
import uuid
import warnings
from pathlib import Path

import numpy as np
from flask import current_app
from PIL import Image as PILImage
from PIL import ImageOps, UnidentifiedImageError

from app.extensions import db
from app.models import Image, User
from app.models.entities import utcnow
from app.services import quality_service

ALLOWED_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png"}
JPEG_QUALITY = 92


class ImageValidationError(ValueError):
    pass


def upload_root() -> Path:
    root = Path(current_app.config["UPLOAD_DIR"])
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_storage_key(key: str) -> Path:
    """Map a stored key to a path, refusing anything that escapes the upload root."""
    root = upload_root().resolve()
    path = (root / key).resolve()
    if root not in path.parents:
        raise ValueError("invalid storage key")
    return path


def _extension_ok(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config["ALLOWED_EXTENSIONS"]


def decode_and_sanitise(data: bytes) -> tuple[np.ndarray, bytes]:
    """Validate real content and re-encode to a clean JPEG. Returns (rgb array, jpeg bytes)."""
    cfg = current_app.config
    if not data:
        raise ImageValidationError("This file is empty. Please choose a photo.")
    max_bytes = cfg["MAX_CONTENT_LENGTH"]
    if len(data) > max_bytes:
        raise ImageValidationError(f"This photo is bigger than {cfg['MAX_UPLOAD_MB']} MB. Please choose a smaller one.")

    with warnings.catch_warnings():
        warnings.simplefilter("error", PILImage.DecompressionBombWarning)
        try:
            probe = PILImage.open(io.BytesIO(data))
            fmt = probe.format
            w, h = probe.size
            if fmt not in ALLOWED_FORMATS:
                raise ImageValidationError("Please upload a JPG or PNG photo.")
            if w * h > cfg["MAX_IMAGE_PIXELS"]:
                raise ImageValidationError("This photo is too large (too many pixels). Please use a smaller photo.")
            probe.verify()  # structural integrity check
            img = PILImage.open(io.BytesIO(data))
            img.load()
        except ImageValidationError:
            raise
        except (PILImage.DecompressionBombError, PILImage.DecompressionBombWarning):
            raise ImageValidationError("This photo is too large (too many pixels). Please use a smaller photo.") from None
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
            raise ImageValidationError(
                "We couldn't open this file. Please upload a JPG or PNG photo that isn't damaged."
            ) from None

    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = PILImage.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")

    min_side = cfg["MIN_IMAGE_SIDE"]
    if min(img.size) < min_side:
        raise ImageValidationError(
            f"This photo is too small ({img.width} × {img.height} pixels). Please use one that's at least {min_side} pixels on each side."
        )
    if max(img.size) > cfg["MAX_IMAGE_SIDE"]:
        img.thumbnail((cfg["MAX_IMAGE_SIDE"], cfg["MAX_IMAGE_SIDE"]))

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)  # no EXIF/ICC/GPS copied
    return np.asarray(img, dtype=np.uint8), out.getvalue()


def store_upload(user: User, file_storage, domain: str = "lesion") -> tuple[Image, bool]:
    """Validate and store an uploaded file for `user`. Returns (image, reused_existing).
    `domain` is the checker the user chose: "lesion" (mole or spot) or "general" (rash or other)."""
    if domain not in ("lesion", "general"):
        raise ImageValidationError("Please choose what you are checking.")
    if file_storage is None or not file_storage.filename:
        raise ImageValidationError("Please choose a photo to upload.")
    if not _extension_ok(file_storage.filename):
        raise ImageValidationError("Please upload a JPG or PNG photo (.jpg, .jpeg or .png).")

    data = file_storage.stream.read(current_app.config["MAX_CONTENT_LENGTH"] + 1)
    rgb, jpeg = decode_and_sanitise(data)
    report = quality_service.assess(rgb)
    if domain != "lesion":  # face photos are fine for the rash checker
        report.issues = [i for i in report.issues if i["code"] != "face"]
    if report.rejected:
        raise ImageValidationError(report.issues[0]["message"])

    digest = hashlib.sha256(jpeg).hexdigest()
    existing = db.session.scalar(
        db.select(Image).filter_by(user_id=user.id, sha256=digest).where(Image.deleted_at.is_(None))
    )
    if existing is not None and resolve_storage_key(existing.storage_key).exists():
        if existing.domain != domain:
            existing.domain = domain
            db.session.commit()
        return existing, True

    now = utcnow()
    key = f"{user.public_id}/{now:%Y}/{now:%m}/{uuid.uuid4().hex}.jpg"
    path = resolve_storage_key(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(jpeg)

    image = Image(
        user_id=user.id, storage_key=key, sha256=digest, mime_type="image/jpeg", domain=domain,
        width=int(rgb.shape[1]), height=int(rgb.shape[0]), size_bytes=len(jpeg),
        blur_score=report.blur_score, brightness=report.brightness, contrast=report.contrast,
        quality_ok=report.ok, quality_issues=report.issues,
    )
    db.session.add(image)
    db.session.commit()
    return image, False


def switch_checker(image: Image, domain: str) -> None:
    """Move an uploaded photo to the other checker (e.g. a face photo sent to the mole checker)."""
    if domain not in ("lesion", "general"):
        raise ImageValidationError("Please choose what you are checking.")
    image.domain = domain
    issues = [i for i in (image.quality_issues or []) if not (domain != "lesion" and i.get("code") == "face")]
    image.quality_issues = issues
    image.quality_ok = not any(i.get("severity") in ("warning", "error") for i in issues)
    db.session.commit()


def get_owned_image(user: User, public_id: str) -> Image | None:
    return db.session.scalar(
        db.select(Image).filter_by(public_id=public_id, user_id=user.id).where(Image.deleted_at.is_(None))
    )


def delete_file(key: str | None) -> None:
    if not key:
        return
    try:
        resolve_storage_key(key).unlink(missing_ok=True)
    except ValueError:
        pass


def delete_image_files(image: Image) -> None:
    delete_file(image.storage_key)
    for pred in image.predictions:
        delete_file(pred.gradcam_key)
