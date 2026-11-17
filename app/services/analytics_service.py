"""Aggregations for dashboards and analytics. Every value comes from database records."""

from __future__ import annotations

import json
from collections import Counter, OrderedDict
from datetime import date, datetime, timedelta

import sqlalchemy as sa

from skinai_ml.classes import simple_name

from app.extensions import db
from app.models import DiseaseClass, Feedback, Image, ModelVersion, Prediction, User
from app.models.entities import utcnow


def _live_predictions():
    return db.select(Prediction).where(Prediction.deleted_at.is_(None))


def class_rows() -> list[DiseaseClass]:
    return list(db.session.scalars(db.select(DiseaseClass).order_by(DiseaseClass.display_order)))


def model_codes(mv) -> set[str] | None:
    """Condition codes an installed model can actually name (from its labels.json); None if unknown."""
    if mv is None:
        return None
    from app.ml.registry import registry

    try:
        labels = json.loads((registry.model_dir(mv) / "labels.json").read_text(encoding="utf-8"))
        return {item["code"] for item in labels}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def known_class_rows(extra_ids=()) -> list[DiseaseClass]:
    """Conditions the installed checkers can name, plus any whose id is in `extra_ids`.

    Conditions from older models stay in the database (past results point to them) but are not offered
    as choices. A checker that isn't installed, or whose labels can't be read, keeps all its rows.
    """
    from app.ml.registry import registry

    models = registry.active_versions()
    codes = {d: model_codes(models.get(d)) for d in ("lesion", "general")}
    extra = set(extra_ids)
    return [c for c in class_rows()
            if c.id in extra or codes.get(c.domain) is None or c.code in codes[c.domain]]


def _class_distribution(where) -> list[dict]:
    rows = db.session.execute(
        db.select(DiseaseClass.code, DiseaseClass.name, DiseaseClass.risk_level,
                  sa.func.count(Prediction.id))
        .select_from(DiseaseClass)
        .outerjoin(Prediction, sa.and_(Prediction.predicted_class_id == DiseaseClass.id, *where))
        .group_by(DiseaseClass.id)
        .order_by(DiseaseClass.display_order)
    ).all()
    return [{"code": c, "name": n, "simple_name": simple_name(c, n), "risk_level": r, "count": int(k)}
            for c, n, r, k in rows]


def _status_split(where) -> dict:
    rows = db.session.execute(
        db.select(Prediction.status, sa.func.count()).where(*where).group_by(Prediction.status)
    ).all()
    out = {"confident": 0, "inconclusive": 0}
    out.update({s: int(n) for s, n in rows})
    return out


def _monthly(where, months: int = 12) -> list[dict]:
    today = utcnow().date().replace(day=1)
    keys = []
    y, m = today.year, today.month
    for _ in range(months):
        keys.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    keys.reverse()
    start = datetime(int(keys[0][:4]), int(keys[0][5:]), 1)
    stamps = db.session.scalars(
        db.select(Prediction.created_at).where(*where, Prediction.created_at >= start)
    ).all()
    counts = Counter(f"{t:%Y-%m}" for t in stamps)
    return [{"month": k, "count": counts.get(k, 0)} for k in keys]


def user_stats(user: User) -> dict:
    where = [Prediction.user_id == user.id, Prediction.deleted_at.is_(None)]
    total = db.session.scalar(db.select(sa.func.count(Prediction.id)).where(*where)) or 0
    last = db.session.scalar(db.select(sa.func.max(Prediction.created_at)).where(*where))
    high = db.session.scalar(
        db.select(sa.func.count(Prediction.id))
        .join(DiseaseClass, Prediction.predicted_class_id == DiseaseClass.id)
        .where(*where, DiseaseClass.risk_level == "high", Prediction.status == "confident")
    ) or 0
    return {
        "total": int(total),
        "last_at": last.isoformat() if last else None,
        "high_risk_confident": int(high),
        "status": _status_split(where),
        "by_class": _class_distribution(where),
        "monthly": _monthly(where),
    }


def recent_predictions(user: User, limit: int = 5) -> list[Prediction]:
    return list(db.session.scalars(
        _live_predictions().filter_by(user_id=user.id).order_by(Prediction.created_at.desc()).limit(limit)
    ))


def admin_overview() -> dict:
    live = [Prediction.deleted_at.is_(None)]
    week_ago = utcnow() - timedelta(days=7)
    n_users = db.session.scalar(db.select(sa.func.count(User.id)).where(User.deleted_at.is_(None))) or 0
    n_active = db.session.scalar(
        db.select(sa.func.count(User.id)).where(User.deleted_at.is_(None), User.is_active_flag.is_(True))
    ) or 0
    n_admins = db.session.scalar(
        db.select(sa.func.count(User.id)).where(User.deleted_at.is_(None), User.role == "admin")
    ) or 0
    total = db.session.scalar(db.select(sa.func.count(Prediction.id)).where(*live)) or 0
    week = db.session.scalar(
        db.select(sa.func.count(Prediction.id)).where(*live, Prediction.created_at >= week_ago)
    ) or 0
    status = _status_split(live)
    fb_total = db.session.scalar(
        db.select(sa.func.count(Feedback.id)).where(Feedback.is_correct.is_not(None))
    ) or 0
    fb_correct = db.session.scalar(
        db.select(sa.func.count(Feedback.id)).where(Feedback.is_correct.is_(True))
    ) or 0
    return {
        "users": int(n_users), "active_users": int(n_active), "admins": int(n_admins),
        "predictions": int(total), "predictions_7d": int(week),
        "inconclusive_rate": (status["inconclusive"] / total) if total else None,
        "feedback_total": int(fb_total),
        "feedback_agreement": (fb_correct / fb_total) if fb_total else None,
        "active_models": {d: db.session.scalar(db.select(ModelVersion).filter_by(is_active=True, domain=d))
                          for d in ("lesion", "general")},
    }


def parse_range(date_from: str | None, date_to: str | None, default_days: int = 90):
    today = utcnow().date()
    try:
        end = date.fromisoformat(date_to) if date_to else today
    except ValueError:
        end = today
    try:
        start = date.fromisoformat(date_from) if date_from else end - timedelta(days=default_days - 1)
    except ValueError:
        start = end - timedelta(days=default_days - 1)
    if start > end:
        start, end = end, start
    if (end - start).days > 3660:
        start = end - timedelta(days=3660)
    return start, end


def admin_analytics(start: date, end: date) -> dict:
    lo = datetime.combine(start, datetime.min.time())
    hi = datetime.combine(end + timedelta(days=1), datetime.min.time())
    where = [Prediction.deleted_at.is_(None), Prediction.created_at >= lo, Prediction.created_at < hi]

    rows = db.session.execute(
        db.select(Prediction.created_at, Prediction.confidence, ModelVersion.version, Image.quality_ok)
        .join(ModelVersion, Prediction.model_version_id == ModelVersion.id)
        .join(Image, Prediction.image_id == Image.id)
        .where(*where)
    ).all()

    daily = OrderedDict(((start + timedelta(days=i)).isoformat(), 0)
                        for i in range((end - start).days + 1))
    hist = [0] * 10
    per_model = Counter()
    quality_issues = 0
    for created, conf, version, q_ok in rows:
        key = created.date().isoformat()
        if key in daily:
            daily[key] += 1
        hist[min(int(float(conf) * 10), 9)] += 1
        per_model[version] += 1
        quality_issues += 0 if q_ok else 1

    fb_rows = db.session.execute(
        db.select(DiseaseClass.code, Feedback.is_correct, sa.func.count())
        .join(Prediction, Feedback.prediction_id == Prediction.id)
        .join(DiseaseClass, Prediction.predicted_class_id == DiseaseClass.id)
        .where(*where, Feedback.is_correct.is_not(None))
        .group_by(DiseaseClass.code, Feedback.is_correct)
    ).all()
    fb = {}
    for code, ok, n in fb_rows:
        fb.setdefault(code, {"agree": 0, "disagree": 0})["agree" if ok else "disagree"] += int(n)

    total = len(rows)
    return {
        "range": {"from": start.isoformat(), "to": end.isoformat()},
        "total": total,
        "daily": [{"date": d, "count": c} for d, c in daily.items()],
        "by_class": _class_distribution(where),
        "status": _status_split(where),
        "confidence_histogram": [{"bin": f"{i * 10}-{i * 10 + 10}%", "count": c}
                                 for i, c in enumerate(hist)],
        "by_model": [{"version": v, "count": c} for v, c in per_model.most_common()],
        "quality_issue_rate": (quality_issues / total) if total else None,
        "feedback_by_class": fb,
    }
