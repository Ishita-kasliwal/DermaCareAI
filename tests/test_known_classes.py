"""Conditions from older models stay in the database but are not offered as choices."""

from tests.conftest import (analyse, image_bytes, image_id_from, login, prediction_id_from, register_model,
                            upload)


def _option_codes(html: str, select_name: str) -> set[str]:
    import re

    block = re.search(rf'<select[^>]*name="{select_name}"[^>]*>(.*?)</select>', html, re.S).group(1)
    return set(re.findall(r'<option[^>]*value="([^"]+)"', block))


def test_feedback_and_history_lists_only_offer_current_conditions(client, user, model_dirs):
    register_model(model_dirs["confident"])
    register_model(model_dirs["general"])          # knows only the conftest GENERAL_CLASSES
    login(client)
    pid = prediction_id_from(analyse(client, image_id_from(upload(client, image_bytes()))))

    feedback = _option_codes(client.get(f"/results/{pid}").get_data(as_text=True), "suggested_class")
    assert "ringworm" not in feedback and "dark_spots" not in feedback   # seeded, but this model can't name them
    assert {"mel", "nv", "eczema", "cold_sores"} <= feedback

    history = _option_codes(client.get("/history/").get_data(as_text=True), "category")
    assert "ringworm" not in history and "nv" in history


def test_about_page_counts_only_current_conditions(client, model_dirs):
    register_model(model_dirs["confident"])
    register_model(model_dirs["general"])
    html = client.get("/about-model").get_data(as_text=True)
    assert "It knows 17 common conditions" in html   # 7 mole types + 10 rash answers in the test models
