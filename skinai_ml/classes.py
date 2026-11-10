"""The 7 HAM10000 skin-lesion categories (single source of truth for names and risk levels)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LesionClass:
    code: str
    name: str
    risk_level: str  # "high" | "medium" | "low"


CLASS_INFO: dict[str, LesionClass] = {
    c.code: c
    for c in (
        LesionClass("akiec", "Sun-damage patch (actinic keratosis)", "medium"),
        LesionClass("bcc", "Basal cell carcinoma (a skin cancer)", "high"),
        LesionClass("bkl", "Harmless age spot (benign keratosis)", "low"),
        LesionClass("df", "Harmless firm bump (dermatofibroma)", "low"),
        LesionClass("mel", "Melanoma (a skin cancer)", "high"),
        LesionClass("nv", "Common mole (melanocytic nevus)", "low"),
        LesionClass("vasc", "Blood-vessel spot (vascular lesion)", "low"),
    )
}

# Codes treated as "malignant or pre-malignant" for the grouped sensitivity/specificity metric.
MALIGNANT_CODES = ("akiec", "bcc", "mel")
