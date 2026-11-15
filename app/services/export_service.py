"""Power BI-friendly CSV exports (star schema). UTF-8 with BOM, ISO-8601 dates, '.' decimals.

Exports contain no names, emails, images or raw IDs: users appear as a keyed pseudonym.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator

from app.extensions import db
from app.models import DiseaseClass, Feedback, Image, ModelVersion, Prediction, PredictionScore, User
from app.security.utils import pseudonymous_key

BOM = "﻿"


def _stream(header: list[str], rows) -> Iterator[str]:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(header)
    yield BOM + buf.getvalue()
    for row in rows:
        buf.seek(0)
        buf.truncate(0)
        writer.writerow([_cell(v) for v in row])
        yield buf.getvalue()


def _cell(v):
    if v is None:
        return ""
    if hasattr(v, "isoformat"):
        return v.isoformat(timespec="seconds")
    if isinstance(v, float):
        return f"{v:.6f}"
    s = str(v)
    # neutralise spreadsheet formula injection
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


def _pred_query(user: User | None):
    q = (db.select(Prediction, DiseaseClass.code, ModelVersion.version, Image.quality_ok, User.public_id)
         .join(DiseaseClass, Prediction.predicted_class_id == DiseaseClass.id)
         .join(ModelVersion, Prediction.model_version_id == ModelVersion.id)
         .join(Image, Prediction.image_id == Image.id)
         .join(User, Prediction.user_id == User.id)
         .where(Prediction.deleted_at.is_(None))
         .order_by(Prediction.created_at))
    if user is not None:
        q = q.where(Prediction.user_id == user.id)
    return q


def fact_predictions(user: User | None = None) -> Iterator[str]:
    def rows():
        for pred, code, version, q_ok, upid in db.session.execute(_pred_query(user)).yield_per(500):
            yield [pred.public_id, pseudonymous_key(upid), pred.created_at, version, code,
                   float(pred.confidence), pred.status, int(bool(q_ok)), pred.inference_ms]

    return _stream(["prediction_id", "user_key", "created_at", "model_version", "predicted_class_code",
                    "confidence", "status", "quality_ok", "inference_ms"], rows())


def fact_prediction_scores(user: User | None = None) -> Iterator[str]:
    def rows():
        q = (db.select(Prediction.public_id, DiseaseClass.code, PredictionScore.probability)
             .join(PredictionScore, PredictionScore.prediction_id == Prediction.id)
             .join(DiseaseClass, PredictionScore.class_id == DiseaseClass.id)
             .where(Prediction.deleted_at.is_(None))
             .order_by(Prediction.id, DiseaseClass.display_order))
        if user is not None:
            q = q.where(Prediction.user_id == user.id)
        for pid, code, p in db.session.execute(q).yield_per(1000):
            yield [pid, code, float(p)]

    return _stream(["prediction_id", "class_code", "probability"], rows())


def dim_disease_classes() -> Iterator[str]:
    rows = ([c.code, c.name, c.domain, c.risk_level, c.display_order]
            for c in db.session.scalars(db.select(DiseaseClass).order_by(DiseaseClass.display_order)))
    return _stream(["class_code", "name", "checker", "risk_level", "display_order"], rows)


def dim_model_versions() -> Iterator[str]:
    rows = ([m.version, m.architecture, m.input_size, m.accuracy, m.balanced_accuracy, m.macro_f1,
             m.confidence_threshold, int(m.is_active), m.trained_at, m.created_at]
            for m in db.session.scalars(db.select(ModelVersion).order_by(ModelVersion.created_at)))
    return _stream(["model_version", "architecture", "input_size", "test_accuracy",
                    "test_balanced_accuracy", "test_macro_f1", "confidence_threshold", "is_active",
                    "trained_at", "registered_at"], rows)


def fact_feedback() -> Iterator[str]:
    def rows():
        q = (db.select(Prediction.public_id, Feedback.is_correct, DiseaseClass.code, Feedback.created_at)
             .join(Prediction, Feedback.prediction_id == Prediction.id)
             .outerjoin(DiseaseClass, Feedback.suggested_class_id == DiseaseClass.id)
             .where(Prediction.deleted_at.is_(None)))
        for pid, ok, code, created in db.session.execute(q):
            yield [pid, "" if ok is None else int(ok), code, created]

    return _stream(["prediction_id", "is_correct", "suggested_class_code", "created_at"], rows())


ADMIN_EXPORTS = {
    "fact_predictions": fact_predictions,
    "fact_prediction_scores": fact_prediction_scores,
    "dim_disease_classes": dim_disease_classes,
    "dim_model_versions": dim_model_versions,
    "fact_feedback": fact_feedback,
}


# ---------------------------------------------------------------- Excel (.xlsx)

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOMAIN_NAMES = {"lesion": "Mole or spot", "general": "Rash or other skin problem"}
STATUS_NAMES = {"confident": "AI was sure", "inconclusive": "AI was not sure"}
_NUMERIC = {"confidence", "probability", "quality_ok", "inference_ms", "input_size", "test_accuracy",
            "test_balanced_accuracy", "test_macro_f1", "confidence_threshold", "is_active",
            "display_order", "is_correct"}


def _xl_cell(v):
    """Keep numbers and dates as real Excel values; guard text against formula injection."""
    if v is None:
        return None
    if getattr(v, "tzinfo", None) is not None:
        v = v.replace(tzinfo=None)  # Excel has no time zones (stored times are UTC)
    if isinstance(v, (int, float)) or hasattr(v, "isoformat"):
        return v
    s = str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def _add_sheet(wb, title: str, header: list[str], rows, widths: dict[int, int] | None = None,
               formats: dict[int, str] | None = None) -> None:
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    ws = wb.create_sheet(title=title[:31])
    ws.append(header)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="0F766E")
    for row in rows:
        ws.append([_xl_cell(v) for v in row])
    ws.freeze_panes = "A2"
    if ws.max_row > 1:
        ws.auto_filter.ref = ws.dimensions
    for i, name in enumerate(header, start=1):
        ws.column_dimensions[get_column_letter(i)].width = (widths or {}).get(i, max(14, len(name) + 4))
    for i, fmt in (formats or {}).items():
        for (cell,) in ws.iter_rows(min_row=2, min_col=i, max_col=i):
            cell.number_format = fmt


def _workbook_bytes(wb) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def user_history_xlsx(user: User) -> bytes:
    """A simple, readable Excel file of one person's own checks (no other users' data)."""
    from openpyxl import Workbook

    q = (db.select(Prediction, DiseaseClass.name, DiseaseClass.domain, Image.quality_ok)
         .join(DiseaseClass, Prediction.predicted_class_id == DiseaseClass.id)
         .join(Image, Prediction.image_id == Image.id)
         .where(Prediction.user_id == user.id, Prediction.deleted_at.is_(None))
         .order_by(Prediction.created_at.desc()))
    rows = [[pred.created_at, DOMAIN_NAMES.get(domain, domain), name, float(pred.confidence),
             STATUS_NAMES.get(pred.status, pred.status), "Good" if q_ok else "Could be better"]
            for pred, name, domain, q_ok in db.session.execute(q)]
    wb = Workbook()
    wb.remove(wb.active)
    _add_sheet(wb, "My checks", ["Date (UTC)", "What I checked", "Closest match", "How sure", "Result",
                                 "Photo quality"], rows,
               widths={1: 20, 2: 28, 3: 34, 4: 11, 5: 18, 6: 16},
               formats={1: "yyyy-mm-dd hh:mm", 4: "0%"})
    notes = wb.create_sheet("Please read")
    for line in ["This is not a medical diagnosis.",
                 "The AI compares your photo with photos it learned from. It can be wrong.",
                 "If a spot changes, bleeds, itches or worries you, please see a doctor."]:
        notes.append([line])
    notes.column_dimensions["A"].width = 80
    return _workbook_bytes(wb)


def _typed(header: list[str], rows: list[list[str]]) -> list[list]:
    num_idx = {i for i, h in enumerate(header) if h in _NUMERIC}
    out = []
    for r in rows:
        row = []
        for i, v in enumerate(r):
            if v.startswith("'"):  # undo the CSV guard; _xl_cell applies its own
                v = v[1:]
            if i in num_idx and v != "":
                try:
                    v = float(v) if "." in v else int(v)
                except ValueError:
                    pass
            row.append(None if v == "" else v)
        out.append(row)
    return out


def admin_workbook_xlsx() -> bytes:
    """All Power BI tables in one Excel workbook, one sheet per table (same columns as the CSV files)."""
    from openpyxl import Workbook

    wb = Workbook()
    wb.remove(wb.active)
    for name, fn in ADMIN_EXPORTS.items():
        table = list(csv.reader(io.StringIO("".join(fn()).lstrip(BOM))))
        header, rows = table[0], table[1:]
        _add_sheet(wb, name, header, _typed(header, rows))
    return _workbook_bytes(wb)
