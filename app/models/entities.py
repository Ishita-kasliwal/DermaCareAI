"""Database schema (see docs/ARCHITECTURE.md section 5)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import sqlalchemy as sa
from flask_login import UserMixin
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # stored as naive UTC


def new_uuid() -> str:
    return str(uuid.uuid4())


ROLE_ENUM = sa.Enum("user", "admin", name="user_role")
RISK_ENUM = sa.Enum("high", "medium", "low", name="risk_level")
STATUS_ENUM = sa.Enum("confident", "inconclusive", name="prediction_status")
SEX_ENUM = sa.Enum("female", "male", "other", "prefer_not", name="sex")
PROB = sa.Numeric(7, 6, asdecimal=False)
METRIC = sa.Numeric(6, 4, asdecimal=False)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(sa.String(36), unique=True, default=new_uuid)
    email: Mapped[str] = mapped_column(sa.String(254), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(sa.String(120))
    password_hash: Mapped[str] = mapped_column(sa.String(255))  # "!google" = signs in with Google only
    google_sub: Mapped[str | None] = mapped_column(sa.String(255), unique=True)  # Google account id
    role: Mapped[str] = mapped_column(ROLE_ENUM, default="user")
    is_active_flag: Mapped[bool] = mapped_column("is_active", sa.Boolean, default=True)
    # optional profile data (minimal; all optional)
    birth_year: Mapped[int | None] = mapped_column(sa.SmallInteger)
    sex: Mapped[str | None] = mapped_column(SEX_ENUM)
    skin_type: Mapped[int | None] = mapped_column(sa.SmallInteger)  # Fitzpatrick I-VI as 1-6
    # security
    auth_version: Mapped[int] = mapped_column(sa.Integer, default=1)  # bump => invalidates sessions
    failed_logins: Mapped[int] = mapped_column(sa.Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(sa.DateTime)
    last_login_at: Mapped[datetime | None] = mapped_column(sa.DateTime)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime)

    images: Mapped[list[Image]] = relationship(back_populates="user")
    predictions: Mapped[list[Prediction]] = relationship(back_populates="user")

    # Flask-Login: session id includes auth_version so password changes log out other sessions
    def get_id(self) -> str:
        return f"{self.public_id}.{self.auth_version}"

    @property
    def is_active(self) -> bool:  # Flask-Login hook
        return bool(self.is_active_flag) and self.deleted_at is None

    @property
    def has_password(self) -> bool:
        return bool(self.password_hash) and not self.password_hash.startswith("!")

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def first_name(self) -> str:
        return (self.full_name or "").split(" ")[0]

    def __repr__(self) -> str:  # never include email/hash in logs
        return f"<User {self.public_id} role={self.role}>"


class DiseaseClass(db.Model):
    __tablename__ = "disease_classes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(sa.String(32), unique=True)
    name: Mapped[str] = mapped_column(sa.String(120))
    description: Mapped[str] = mapped_column(sa.Text, default="")
    risk_level: Mapped[str] = mapped_column(RISK_ENUM)
    domain: Mapped[str] = mapped_column(sa.String(16), default="lesion", server_default="lesion", index=True)
    advice: Mapped[str] = mapped_column(sa.Text, default="")
    display_order: Mapped[int] = mapped_column(sa.Integer, default=0)


class ModelVersion(db.Model):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(sa.String(80), unique=True)
    domain: Mapped[str] = mapped_column(sa.String(16), default="lesion", server_default="lesion", index=True)
    architecture: Mapped[str] = mapped_column(sa.String(40))
    file_path: Mapped[str] = mapped_column(sa.String(255))  # directory, relative to project root
    file_sha256: Mapped[str] = mapped_column(sa.String(64))
    input_size: Mapped[int] = mapped_column(sa.Integer)
    accuracy: Mapped[float | None] = mapped_column(METRIC)
    balanced_accuracy: Mapped[float | None] = mapped_column(METRIC)
    macro_f1: Mapped[float | None] = mapped_column(METRIC)
    confidence_threshold: Mapped[float] = mapped_column(METRIC, default=0.5)
    metrics: Mapped[dict | None] = mapped_column(sa.JSON)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=False, index=True)
    trained_at: Mapped[datetime | None] = mapped_column(sa.DateTime)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow)


class Image(db.Model):
    __tablename__ = "images"
    __table_args__ = (sa.Index("ix_images_user_sha", "user_id", "sha256"),)

    id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True)
    public_id: Mapped[str] = mapped_column(sa.String(36), unique=True, default=new_uuid)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    storage_key: Mapped[str] = mapped_column(sa.String(255), unique=True)  # relative path under UPLOAD_DIR
    sha256: Mapped[str] = mapped_column(sa.String(64))
    mime_type: Mapped[str] = mapped_column(sa.String(40), default="image/jpeg")
    domain: Mapped[str] = mapped_column(sa.String(16), default="lesion", server_default="lesion")
    width: Mapped[int] = mapped_column(sa.Integer)
    height: Mapped[int] = mapped_column(sa.Integer)
    size_bytes: Mapped[int] = mapped_column(sa.Integer)
    blur_score: Mapped[float | None] = mapped_column(sa.Float)
    brightness: Mapped[float | None] = mapped_column(sa.Float)
    contrast: Mapped[float | None] = mapped_column(sa.Float)
    quality_ok: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    quality_issues: Mapped[list | None] = mapped_column(sa.JSON)
    uploaded_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime)

    user: Mapped[User] = relationship(back_populates="images")
    predictions: Mapped[list[Prediction]] = relationship(back_populates="image")


class Prediction(db.Model):
    __tablename__ = "predictions"
    __table_args__ = (
        sa.Index("ix_pred_user_created", "user_id", "created_at"),
        sa.Index("ix_pred_class_created", "predicted_class_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True)
    public_id: Mapped[str] = mapped_column(sa.String(36), unique=True, default=new_uuid)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="RESTRICT"))
    image_id: Mapped[int] = mapped_column(sa.ForeignKey("images.id", ondelete="RESTRICT"), index=True)
    model_version_id: Mapped[int] = mapped_column(sa.ForeignKey("model_versions.id", ondelete="RESTRICT"))
    predicted_class_id: Mapped[int] = mapped_column(sa.ForeignKey("disease_classes.id", ondelete="RESTRICT"))
    confidence: Mapped[float] = mapped_column(PROB)
    status: Mapped[str] = mapped_column(STATUS_ENUM)
    inference_ms: Mapped[int] = mapped_column(sa.Integer)
    gradcam_key: Mapped[str | None] = mapped_column(sa.String(255))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime)

    user: Mapped[User] = relationship(back_populates="predictions")
    image: Mapped[Image] = relationship(back_populates="predictions")
    model_version: Mapped[ModelVersion] = relationship()
    predicted_class: Mapped[DiseaseClass] = relationship()
    scores: Mapped[list[PredictionScore]] = relationship(
        back_populates="prediction", cascade="all, delete-orphan",
        order_by="desc(PredictionScore.probability)",
    )
    feedback: Mapped[Feedback | None] = relationship(back_populates="prediction", uselist=False)


class PredictionScore(db.Model):
    __tablename__ = "prediction_scores"

    prediction_id: Mapped[int] = mapped_column(
        sa.BigInteger().with_variant(sa.Integer, "sqlite"),
        sa.ForeignKey("predictions.id", ondelete="CASCADE"), primary_key=True,
    )
    class_id: Mapped[int] = mapped_column(sa.ForeignKey("disease_classes.id", ondelete="RESTRICT"),
                                          primary_key=True)
    probability: Mapped[float] = mapped_column(PROB)

    prediction: Mapped[Prediction] = relationship(back_populates="scores")
    disease_class: Mapped[DiseaseClass] = relationship()


class Feedback(db.Model):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    prediction_id: Mapped[int] = mapped_column(
        sa.BigInteger().with_variant(sa.Integer, "sqlite"),
        sa.ForeignKey("predictions.id", ondelete="CASCADE"), unique=True,
    )
    is_correct: Mapped[bool | None] = mapped_column(sa.Boolean)
    suggested_class_id: Mapped[int | None] = mapped_column(sa.ForeignKey("disease_classes.id"))
    comment: Mapped[str | None] = mapped_column(sa.String(500))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow)

    prediction: Mapped[Prediction] = relationship(back_populates="feedback")
    suggested_class: Mapped[DiseaseClass | None] = relationship()


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(sa.ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(sa.String(60), index=True)
    target_type: Mapped[str | None] = mapped_column(sa.String(40))
    target_id: Mapped[str | None] = mapped_column(sa.String(64))
    ip_hash: Mapped[str | None] = mapped_column(sa.String(64))
    details: Mapped[dict | None] = mapped_column(sa.JSON)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, index=True)

    user: Mapped[User | None] = relationship()


TIME_SLOTS = ("morning", "afternoon", "evening")


class Appointment(db.Model):
    """An appointment REQUEST made from a clinic card ("Book"). The clinic is not contacted automatically:
    the request is stored here and listed for admins at /admin/appointments."""

    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(sa.String(36), unique=True, default=new_uuid)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"), index=True)
    prediction_id: Mapped[int | None] = mapped_column(
        sa.BigInteger().with_variant(sa.Integer, "sqlite"),
        sa.ForeignKey("predictions.id", ondelete="SET NULL"))
    clinic_name: Mapped[str] = mapped_column(sa.String(160))
    clinic_address: Mapped[str | None] = mapped_column(sa.String(255))
    clinic_phone: Mapped[str | None] = mapped_column(sa.String(40))
    clinic_lat: Mapped[float | None] = mapped_column(sa.Float)
    clinic_lon: Mapped[float | None] = mapped_column(sa.Float)
    patient_name: Mapped[str] = mapped_column(sa.String(80))
    patient_phone: Mapped[str] = mapped_column(sa.String(10))
    preferred_date: Mapped[date] = mapped_column(sa.Date)
    time_slot: Mapped[str] = mapped_column(sa.String(10))      # morning | afternoon | evening
    note: Mapped[str | None] = mapped_column(sa.String(500))
    predicted_condition: Mapped[str | None] = mapped_column(sa.String(120))   # snapshot of the check's answer
    status: Mapped[str] = mapped_column(sa.String(16), default="requested")
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, index=True)

    user: Mapped[User] = relationship()
    prediction: Mapped[Prediction | None] = relationship()
