"""All skin conditions DermaCareAI knows about (single source of truth for names, risk and checker).

Two checkers ("domains"), each with its own trained model:
  lesion  - "Check a mole or spot": 7 HAM10000 types, close-up/dermoscopic photos
  general - "Check a rash or other skin problem": 10 SCIN condition groups, everyday phone photos
"""

from dataclasses import dataclass

DOMAINS = {
    "lesion": "Mole or spot",
    "general": "Rash or other skin problem",
}


@dataclass(frozen=True)
class LesionClass:
    code: str
    name: str
    risk_level: str  # "high" | "medium" | "low"
    domain: str = "lesion"


_ALL = (
    # --- lesion (HAM10000)
    LesionClass("akiec", "Sun-damage patch (actinic keratosis)", "medium"),
    LesionClass("bcc", "Basal cell carcinoma (a skin cancer)", "high"),
    LesionClass("bkl", "Harmless age spot (benign keratosis)", "low"),
    LesionClass("df", "Harmless firm bump (dermatofibroma)", "low"),
    LesionClass("mel", "Melanoma (a skin cancer)", "high"),
    LesionClass("nv", "Common mole (melanocytic nevus)", "low"),
    LesionClass("vasc", "Blood-vessel spot (vascular lesion)", "low"),
    # --- general (SCIN)
    LesionClass("eczema", "Eczema (atopic dermatitis)", "low", "general"),
    LesionClass("contact_dermatitis", "Contact dermatitis (skin reaction)", "low", "general"),
    LesionClass("urticaria", "Hives (urticaria)", "low", "general"),
    LesionClass("insect_bite", "Insect bite", "low", "general"),
    LesionClass("folliculitis", "Folliculitis (inflamed hair follicles)", "low", "general"),
    LesionClass("fungal", "Fungal skin infection (tinea)", "low", "general"),
    LesionClass("acne", "Acne or rosacea", "low", "general"),
    LesionClass("psoriasis", "Psoriasis", "medium", "general"),
    LesionClass("shingles", "Shingles (herpes zoster)", "high", "general"),
    LesionClass("cold_sores", "Cold sores (herpes simplex)", "low", "general"),
    # --- general (user-provided rash dataset, used by the current rash checker)
    LesionClass("dermatitis", "Skin irritation (dermatitis)", "low", "general"),
    LesionClass("ringworm", "Ringworm (fungal infection)", "low", "general"),
    # --- general (Roboflow Universe sets, CC BY 4.0, added 2026-11-16)
    LesionClass("dark_spots", "Dark spots and pigmentation", "low", "general"),
    LesionClass("redness", "Skin redness", "low", "general"),
    LesionClass("scratches", "Scratches and small cuts", "low", "general"),
    LesionClass("healthy", "Healthy-looking skin", "low", "general"),
    LesionClass("unfamiliar", "Not a skin problem the AI knows", "low", "general"),
)

CLASS_INFO: dict[str, LesionClass] = {c.code: c for c in _ALL}

# Codes treated as "malignant or pre-malignant" for the grouped sensitivity/specificity metric.
MALIGNANT_CODES = ("akiec", "bcc", "mel")


def codes_for(domain: str) -> list[str]:
    return [c.code for c in _ALL if c.domain == domain]


# Everyday names for charts and short labels (no medical words).
SIMPLE_NAMES = {
    "akiec": "Sun-damage patch", "bcc": "Skin cancer (BCC)", "bkl": "Harmless age spot",
    "df": "Harmless firm bump", "mel": "Skin cancer (melanoma)", "nv": "Common mole",
    "vasc": "Blood-vessel spot", "eczema": "Eczema", "contact_dermatitis": "Skin reaction",
    "urticaria": "Hives", "insect_bite": "Insect bite", "folliculitis": "Hair-root bumps",
    "fungal": "Fungal infection", "acne": "Acne / pimples", "psoriasis": "Psoriasis",
    "shingles": "Shingles", "cold_sores": "Cold sores", "dermatitis": "Skin irritation",
    "ringworm": "Ringworm", "dark_spots": "Dark spots", "redness": "Skin redness",
    "scratches": "Scratches & cuts", "healthy": "Healthy skin", "unfamiliar": "Not a known skin problem",
}


def simple_name(code: str, fallback: str = "") -> str:
    return SIMPLE_NAMES.get(code, fallback or code)
