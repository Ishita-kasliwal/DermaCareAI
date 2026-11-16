"""Safe home-care tips and over-the-counter medicines per condition, from the editable file app/data/care.json.

The file is re-read when it changes on disk, so an edit shows on the next page load without a restart.
Rules (checked by validate() and by the tests):
- every condition the app knows has an entry;
- "urgent" conditions (skin cancer and pre-cancer) have NO home-care tips, only the urgent message;
- every other condition with tips has 3 to 5 of them;
- medicines: at most 4, generic names only, no numbers (so no strengths or doses), nothing prescription-only
  (see PRESCRIPTION_ONLY), and none at all for urgent conditions.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path

CARE_FILE = Path(__file__).resolve().parents[1] / "data" / "care.json"
MIN_TIPS, MAX_TIPS = 3, 5
MAX_MEDICINES = 4
# Medicines that need a doctor's prescription in India (or that are often misused as such). They may be named in a
# warning ("avoid creams containing ..."), but never suggested as a medicine. Lower-case substrings.
PRESCRIPTION_ONLY = (
    "steroid", "hydrocortisone", "clobetasol", "betamethasone", "mometasone", "prednis", "dexamethasone",
    "tretinoin", "adapalene", "isotretinoin", "hydroquinone", "mupirocin", "fusidic", "antibiotic", "doxycycline",
    "minocycline", "clindamycin", "acyclovir", "aciclovir", "valacyclovir", "fluconazole", "itraconazole",
    "ketoconazole tablet", "methotrexate", "tacrolimus", "pimecrolimus", "ivermectin", "permethrin",
)

_lock = threading.Lock()
_cache: dict = {"mtime": None, "data": None}


@dataclass
class Care:
    """What the result page shows under "Home care" for one condition."""

    urgent: bool = False
    urgent_message: str = ""
    doctor_first: str = ""
    home_care: list[str] = field(default_factory=list)
    after_tips: str = ""
    medicines: list[dict] = field(default_factory=list)   # [{"name": ..., "use": ...}]
    medicine_warning: str = ""
    medicine_note: str = ""       # always shown with the medicines section
    no_medicine_text: str = ""    # shown instead of a list when no medicine is usually needed

    @property
    def has_content(self) -> bool:
        return self.urgent or bool(self.home_care)


def _load() -> dict:
    mtime = CARE_FILE.stat().st_mtime
    with _lock:
        if _cache["mtime"] != mtime:
            _cache["data"] = json.loads(CARE_FILE.read_text(encoding="utf-8"))
            _cache["mtime"] = mtime
        return _cache["data"]


def validate(data: dict | None = None, codes: list[str] | None = None) -> list[str]:
    """Return a list of problems with the care file (empty list = all good)."""
    from skinai_ml.classes import CLASS_INFO

    data = data if data is not None else _load()
    codes = codes if codes is not None else list(CLASS_INFO)
    problems = []
    conditions = data.get("conditions", {})
    if not data.get("urgent_message"):
        problems.append("urgent_message is missing")
    for code in codes:
        entry = conditions.get(code)
        if entry is None:
            problems.append(f"{code}: no entry")
            continue
        tips = entry.get("home_care", [])
        if entry.get("urgent"):
            if tips:
                problems.append(f"{code}: urgent conditions must not have home remedies")
        elif tips and not MIN_TIPS <= len(tips) <= MAX_TIPS:
            problems.append(f"{code}: needs {MIN_TIPS}-{MAX_TIPS} tips, has {len(tips)}")
        if any(not isinstance(t, str) or not t.strip() for t in tips):
            problems.append(f"{code}: empty tip")
        meds = entry.get("medicines", [])
        if entry.get("urgent") and meds:
            problems.append(f"{code}: urgent conditions must not list medicines")
        if len(meds) > MAX_MEDICINES:
            problems.append(f"{code}: at most {MAX_MEDICINES} medicines, has {len(meds)}")
        for m in meds:
            name = str(m.get("name", "")) if isinstance(m, dict) else ""
            text = f"{name} {m.get('use', '')}".lower() if isinstance(m, dict) else ""
            if not name.strip():
                problems.append(f"{code}: medicine without a name")
            if any(ch.isdigit() for ch in text):
                problems.append(f"{code}: '{name}' contains a number (no strengths or doses allowed)")
            if any(rx in text for rx in PRESCRIPTION_ONLY):
                problems.append(f"{code}: '{name}' looks prescription-only")
    if not data.get("medicine_note"):
        problems.append("medicine_note is missing")
    return problems


def care_for(code: str) -> Care:
    """Home-care content for one condition code. Unknown codes or a broken file give an empty Care."""
    try:
        data = _load()
    except (OSError, ValueError):  # missing or invalid JSON: show nothing rather than break the result page
        return Care()
    entry = data.get("conditions", {}).get(code) or {}
    if entry.get("urgent"):
        return Care(urgent=True, urgent_message=data.get("urgent_message", ""))
    medicines = [m for m in entry.get("medicines", [])[:MAX_MEDICINES]
                 if isinstance(m, dict) and m.get("name")
                 and not any(rx in f"{m['name']} {m.get('use', '')}".lower() for rx in PRESCRIPTION_ONLY)]
    return Care(
        doctor_first=entry.get("doctor_first", ""),
        home_care=list(entry.get("home_care", []))[:MAX_TIPS],
        after_tips=entry.get("after_tips", ""),
        medicines=medicines,
        medicine_warning=entry.get("medicine_warning", ""),
        medicine_note=data.get("medicine_note", ""),
        no_medicine_text=data.get("no_medicine_text", ""),
    )
