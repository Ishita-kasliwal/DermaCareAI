"""Management commands:  .\\.venv\\Scripts\\flask.exe --app wsgi <command>

  init-db         create tables (development convenience; production uses `flask db upgrade`)
  seed-classes    insert/update the 7 HAM10000 categories
  create-admin    create an administrator (prompts for the password; never pass it as an argument)
  register-model  register an exported model directory (optionally activate it)
  purge           hard-delete soft-deleted data older than RETENTION_DAYS and orphaned uploads
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import click
from flask import current_app

from app.config import ROOT_DIR
from app.extensions import db


def register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Create all tables and seed categories."""
        from app.services.catalog import seed_disease_classes

        db.create_all()
        n = seed_disease_classes(db)
        click.echo(f"Tables ready. Categories created: {n}")

    @app.cli.command("seed-classes")
    @click.option("--refresh-text", is_flag=True, help="Also reset descriptions/advice to the defaults.")
    def seed_classes(refresh_text: bool):
        from app.services.catalog import seed_disease_classes

        click.echo(f"Categories created: {seed_disease_classes(db, update_text=refresh_text)}")

    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--name", prompt="Full name")
    def create_admin(email, name):
        """Create an administrator account. The password is read from a hidden prompt."""
        from app.services.auth_service import AuthError, register_user

        password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
        try:
            user = register_user(email, name, password, role="admin")
        except AuthError as e:
            raise click.ClickException(e.message) from None
        click.echo(f"Administrator created: {user.public_id}")

    @app.cli.command("register-model")
    @click.argument("model_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
    @click.option("--activate", is_flag=True, help="Make this the active model.")
    def register_model(model_dir: Path, activate: bool):
        """Register an exported model directory (from ml/src/export.py)."""
        import sqlalchemy as sa

        from app.ml.registry import registry
        from app.models import ModelVersion
        from app.utils_files import sha256_file

        manifest = json.loads((model_dir / "manifest.json").read_text(encoding="utf-8"))
        metrics = json.loads((model_dir / "metrics.json").read_text(encoding="utf-8"))
        actual = sha256_file(model_dir / manifest["model_file"])
        if actual != manifest["model_sha256"]:
            raise click.ClickException("model.keras checksum does not match manifest.json")
        test = metrics.get("test", {})
        try:
            rel = model_dir.resolve().relative_to(ROOT_DIR)
        except ValueError:
            rel = model_dir.resolve()
        mv = db.session.scalar(db.select(ModelVersion).filter_by(version=manifest["version"]))
        if mv is None:
            mv = ModelVersion(version=manifest["version"])
            db.session.add(mv)
        mv.architecture = manifest["architecture"]
        mv.file_path = str(rel).replace("\\", "/")
        mv.file_sha256 = manifest["model_sha256"]
        mv.input_size = manifest["image_size"]
        mv.accuracy = test.get("accuracy")
        mv.balanced_accuracy = test.get("balanced_accuracy")
        mv.macro_f1 = test.get("macro_f1")
        mv.confidence_threshold = manifest.get("confidence_threshold", current_app.config["CONFIDENCE_THRESHOLD"])
        mv.metrics = {"validation": _summary(metrics.get("validation", {})), "test": _summary(test),
                      "dataset": manifest.get("dataset"), "group_column": manifest.get("group_column"),
                      "splits_fingerprint": manifest.get("splits_fingerprint"),
                      "environment": manifest.get("environment")}
        ts = manifest.get("environment", {}).get("timestamp_utc")
        mv.trained_at = datetime.fromisoformat(ts).replace(tzinfo=None) if ts else None
        if activate:
            db.session.execute(sa.update(ModelVersion).values(is_active=False))
            mv.is_active = True
        db.session.commit()
        registry.clear()
        click.echo(f"Registered {mv.version}{' (active)' if mv.is_active else ''}")

    @app.cli.command("purge")
    @click.option("--dry-run", is_flag=True)
    def purge(dry_run: bool):
        """Permanently remove data that was deleted more than RETENTION_DAYS ago."""
        from app.models import Image, Prediction
        from app.models.entities import utcnow
        from app.services.image_service import delete_file

        cutoff = utcnow() - timedelta(days=current_app.config["RETENTION_DAYS"])
        orphan_cutoff = utcnow() - timedelta(hours=24)
        preds = list(db.session.scalars(db.select(Prediction).where(Prediction.deleted_at < cutoff)))
        images = list(db.session.scalars(db.select(Image).where(Image.deleted_at < cutoff)))
        orphans = [i for i in db.session.scalars(
            db.select(Image).where(Image.deleted_at.is_(None), Image.uploaded_at < orphan_cutoff))
            if not i.predictions]
        click.echo(f"predictions: {len(preds)}, deleted images: {len(images)}, orphan uploads: {len(orphans)}")
        if dry_run:
            return
        for p in preds:
            delete_file(p.gradcam_key)
            db.session.delete(p)
        db.session.flush()
        for i in images + orphans:
            delete_file(i.storage_key)
            if not any(p for p in i.predictions if p not in preds):
                db.session.delete(i)
        db.session.commit()
        click.echo("Purge complete.")


def _summary(m: dict) -> dict:
    """Keep the headline and per-class numbers needed by the About page (drop large arrays)."""
    if not m:
        return {}
    keep = ("n_images", "accuracy", "balanced_accuracy", "macro_f1", "weighted_f1", "macro_roc_auc_ovr",
            "malignant_vs_benign", "confusion_matrix", "confidence_thresholds")
    out = {k: m.get(k) for k in keep}
    out["per_class"] = {c: {k: v.get(k) for k in ("support", "precision", "recall_sensitivity",
                                                   "specificity", "f1", "roc_auc_ovr")}
                        for c, v in (m.get("per_class") or {}).items()}
    return out
