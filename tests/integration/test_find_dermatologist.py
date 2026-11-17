"""Find a dermatologist page (Task 4): form validation, results and the link from the result page."""

from app.services import doctor_search as ds


def test_page_shows_form_with_all_states_and_uts(client):
    html = client.get("/find-a-dermatologist").data.decode()
    assert "Find a dermatologist near you" in html
    for name in ("Maharashtra", "Tamil Nadu", "Delhi (UT)", "Ladakh (UT)", "Lakshadweep (UT)"):
        assert name in html
    assert html.count("<option") == 1 + 28 + 8


def test_polite_validation_messages(client, monkeypatch):
    monkeypatch.setattr(ds, "search", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not search")))
    html = client.get("/find-a-dermatologist?city=&district=&state=").data.decode()
    assert "Please type your city or town" in html
    assert "Please choose your state or union territory" in html
    html = client.get("/find-a-dermatologist?city=Pune123&state=Maharashtra").data.decode()
    assert "only letters and spaces in the city name" in html


def test_results_and_fallback_message_shown(client, monkeypatch):
    def fake_search(city, district, state, google_key=""):
        r = ds.SearchResult(level="district", area="Pune district", source="OpenStreetMap",
                            maps_search_url=ds.google_maps_search_url(city, district, state),
                            messages=["We couldn't find any dermatologists listed in Smalltown, so we looked in the wider district."])
        r.clinics = [ds.Clinic("Skin Care Clinic", "FC Road, Pune", 18.52, 73.84, distance_km=3.2)]
        return r
    import app.blueprints.doctors.routes as routes
    monkeypatch.setattr(routes, "search", fake_search)
    html = client.get("/find-a-dermatologist?city=Smalltown&district=Pune&state=Maharashtra").data.decode()
    assert "Skin Care Clinic" in html and "3.2 km" in html
    assert "FC Road, Pune" not in html      # addresses are not shown (open-map addresses can be wrong)
    assert "looked in the wider district" in html
    assert "across Pune district" in html
    assert "google.com/maps/search/" in html and "dermatologist+in+Smalltown" in html


def test_result_page_links_to_search(client, user, model_dirs):
    from tests.conftest import (
        analyse,
        image_id_from,
        login,
        prediction_id_from,
        register_model,
    )

    register_model(model_dirs["confident"])
    login(client)
    pid = prediction_id_from(analyse(client, image_id_from(upload_one(client))))
    html = client.get(f"/results/{pid}").data.decode()
    assert "Find a dermatologist near you" in html and 'action="/find-a-dermatologist"' in html
    assert f'name="prediction" value="{pid}"' in html


def upload_one(client):
    from tests.conftest import image_bytes, upload
    return upload(client, image_bytes(seed=91))


def test_district_list_covers_every_state_and_ut(client):
    from app.data.india import ALL
    data = client.get("/static/data/india_districts.json").get_json()
    assert set(data["states"]) == set(ALL)
    assert "Indore" in data["states"]["Madhya Pradesh"] and "Leh" in data["states"]["Ladakh"]


def test_search_form_asks_state_first(client):
    html = client.get("/find-a-dermatologist").data.decode()
    assert html.index('name="state"') < html.index('name="district"') < html.index('name="city"')
