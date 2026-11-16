"""Result page "Home care" section (Task 2)."""

from tests.conftest import (
    _export_tiny_model,
    analyse,
    image_bytes,
    image_id_from,
    login,
    prediction_id_from,
    register_model,
    upload,
)


def _result_html(client, check="lesion", seed=80):
    login(client)
    pid = prediction_id_from(analyse(client, image_id_from(upload(client, image_bytes(seed=seed), check=check))))
    return client.get(f"/results/{pid}").data.decode()


def test_confident_result_shows_safe_home_care_tips(client, user, model_dirs):
    register_model(model_dirs["general"])          # favours eczema
    html = _result_html(client, check="general")
    assert "Home care" in html
    assert "fragrance-free cream" in html           # an eczema tip from care.json
    assert "When to see a doctor" in html
    # Task 3: over-the-counter medicines + the safety note that is always shown
    assert "Medicines you can ask a pharmacist about" in html
    assert "fragrance-free emollient cream" in html
    assert "These are common options, not a prescription." in html


def test_unclear_result_shows_no_condition_tips(client, user, model_dirs):
    register_model(model_dirs["uniform"])          # never sure -> inconclusive
    html = _result_html(client)
    assert "The result is unclear" in html
    assert "Home care" not in html


def test_skin_cancer_result_shows_only_see_a_doctor(client, user, tmp_path):
    register_model(_export_tiny_model(tmp_path / "tiny-mel", "tiny-mel", favour="mel"))
    html = _result_html(client)
    assert "Home care" in html
    assert "Please don&#39;t try to treat this at home" in html or "Please don't try to treat this at home" in html
    assert "care-list" not in html                  # no list of remedies at all
    assert "med-list" not in html and "Medicines you can ask" not in html   # and no medicines


def test_result_page_uses_plain_caring_words(client, user, model_dirs):
    register_model(model_dirs["general"])          # favours eczema
    html = _result_html(client, check="general")
    from app.services import tone
    assert any(o.replace("'", "&#39;") in html for o in tone.OPENERS)
    assert any(c.replace("'", "&#39;") in html for c in tone.CLOSING)
    assert "atopic" not in html.lower()            # plain name "Eczema", not "Eczema (atopic dermatitis)"
    assert ">Eczema<" in html


def test_result_page_sections_in_the_right_order(client, user, model_dirs):
    """Task 7: result + top 3, explanation, home care, medicines, dermatologists, disclaimer."""
    register_model(model_dirs["general"])          # favours eczema: every section is shown
    html = _result_html(client, check="general")
    order = ["result-title", "Top 3 possibilities", "What this means", "Home care",
             "Medicines you can ask a pharmacist about", "Find a dermatologist near you",
             "This tool is a student project and not a medical diagnosis. Please consult a qualified dermatologist."]
    positions = [html.index(marker) for marker in order]
    assert positions == sorted(positions), dict(zip(order, positions, strict=True))
