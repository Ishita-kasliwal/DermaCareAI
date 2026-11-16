"""Home-care tips file (app/data/care.json): safety rules and lookups."""

from app.services.care_service import MAX_TIPS, MIN_TIPS, care_for, validate
from skinai_ml.classes import CLASS_INFO

CANCER_CODES = ("mel", "bcc", "akiec")


def test_care_file_follows_the_rules():
    assert validate() == []


def test_skin_cancers_get_no_home_remedies_only_see_a_doctor():
    for code in CANCER_CODES:
        care = care_for(code)
        assert care.urgent and care.home_care == []
        assert "dermatologist" in care.urgent_message and "as soon as possible" in care.urgent_message


def test_every_other_condition_has_3_to_5_tips():
    for code in CLASS_INFO:
        if code in CANCER_CODES or code == "unfamiliar":
            continue
        tips = care_for(code).home_care
        assert MIN_TIPS <= len(tips) <= MAX_TIPS, code


def test_validate_catches_broken_entries():
    data = {"urgent_message": "See a doctor.", "conditions": {
        "mel": {"urgent": True, "home_care": ["apply something"]},
        "acne": {"home_care": ["only one tip"]},
    }}
    problems = validate(data, ["mel", "acne", "eczema"])
    assert any("mel" in p and "must not" in p for p in problems)
    assert any("acne" in p and "3-5" in p for p in problems)
    assert any("eczema" in p and "no entry" in p for p in problems)


def test_no_medicine_doses_in_home_care():
    for code in CLASS_INFO:
        for tip in care_for(code).home_care:
            assert " mg" not in tip and "tablet" not in tip.lower(), (code, tip)


# ------------------------------------------------------------------ over-the-counter medicines (Task 3)
from app.services.care_service import MAX_MEDICINES, PRESCRIPTION_ONLY  # noqa: E402


def test_cancers_list_no_medicines():
    for code in CANCER_CODES:
        assert care_for(code).medicines == []


def test_medicines_are_generic_otc_without_doses():
    for code in CLASS_INFO:
        meds = care_for(code).medicines
        assert len(meds) <= MAX_MEDICINES, code
        for m in meds:
            text = f"{m['name']} {m.get('use', '')}".lower()
            assert not any(ch.isdigit() for ch in text), (code, m)          # no strengths or doses
            assert not any(rx in text for rx in PRESCRIPTION_ONLY), (code, m)


def test_safety_note_wording():
    note = care_for("acne").medicine_note
    assert note == ("These are common options, not a prescription. Please check with a doctor or pharmacist before "
                    "using any medicine, especially for children, pregnant women, or people with allergies.")


def test_validate_rejects_doses_and_prescription_medicines():
    data = {"urgent_message": "x", "medicine_note": "x", "conditions": {
        "acne": {"home_care": ["a", "b", "c"], "medicines": [{"name": "Benzoyl peroxide 5%", "use": "x"}]},
        "eczema": {"home_care": ["a", "b", "c"], "medicines": [{"name": "Hydrocortisone cream", "use": "x"}]},
        "mel": {"urgent": True, "medicines": [{"name": "Sunscreen", "use": "x"}]},
    }}
    problems = validate(data, ["acne", "eczema", "mel"])
    assert any("acne" in p and "number" in p for p in problems)
    assert any("eczema" in p and "prescription" in p for p in problems)
    assert any("mel" in p and "medicines" in p for p in problems)
