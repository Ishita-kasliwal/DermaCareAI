"""Find a dermatologist (Task 4): city -> district -> state fallback, distances, errors. Map services are faked."""

import urllib.parse

import pytest

from app.services import doctor_search as ds

PLACES = {  # fake Nominatim: query -> (lat, lon)
    "smalltown, bigdistrict, maharashtra": (18.0, 74.0),
    "bigdistrict district, maharashtra": (18.5, 73.9),
    "maharashtra": (19.6, 75.5),
}


def fake_http(clinics_at):
    """clinics_at: {"city"|"district"|"state": [clinic dicts]} returned for a search inside that place's box."""
    boxes = {}   # west longitude of each place's box -> level

    def _http_json(url, data=None, headers=None):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        if "viewbox" in q:                                        # clinic search inside a box
            west = round(float(q["viewbox"][0].split(",")[0]), 3)
            return [{"name": c["name"], "category": "amenity", "type": "clinic", "lat": c["lat"], "lon": c["lon"],
                     "address": c.get("address", {}), "extratags": c.get("extratags", {})}
                    for c in clinics_at.get(boxes.get(west), [])]
        text = q["q"][0].lower()                                  # place lookup
        if text not in PLACES:
            return []
        lat, lon = PLACES[text]
        boxes[round(lon - 0.5, 3)] = ("city" if text.startswith("smalltown") else
                                      "district" if "district" in text else "state")
        return [{"lat": lat, "lon": lon, "boundingbox": [lat - 0.5, lat + 0.5, lon - 0.5, lon + 0.5],
                 "display_name": text}]
    return _http_json


@pytest.fixture(autouse=True)
def no_cache_no_wait(monkeypatch):
    ds._cache.clear()
    monkeypatch.setattr(ds.time, "sleep", lambda s: None)


def clinic(name, lat, lon, address=None, phone=""):
    return {"name": name, "lat": lat, "lon": lon, "address": address or {},
            "extratags": {"phone": phone} if phone else {}}


def test_city_results_sorted_nearest_first(monkeypatch):
    monkeypatch.setattr(ds, "_http_json", fake_http({"city": [
        clinic("Far Skin Clinic", 18.1, 74.0), clinic("Near Skin Care", 18.01, 74.0, phone="+91 20 1234 5678",
                                                    address={"road": "MG Road", "city": "Smalltown"}),
        clinic("Skin Clinic In Another City", 18.4, 74.0)]}))
    r = ds.search("Smalltown", "Bigdistrict", "Maharashtra")
    assert r.level == "city" and not r.error and r.messages == []
    assert [c.name for c in r.clinics] == ["Near Skin Care", "Far Skin Clinic"]   # 44 km one left out
    assert r.clinics[0].distance_km == pytest.approx(1.1, abs=0.1)
    assert r.clinics[0].address == "MG Road, Smalltown" and r.clinics[0].phone
    assert "dermatologist+in+Smalltown%2C+Bigdistrict%2C+Maharashtra" in r.maps_search_url


def test_falls_back_to_district_with_friendly_message(monkeypatch):
    monkeypatch.setattr(ds, "_http_json", fake_http({"district": [clinic("District Skin Hospital", 18.4, 73.9)]}))
    r = ds.search("Smalltown", "Bigdistrict", "Maharashtra")
    assert r.level == "district" and r.area == "Bigdistrict district"
    assert "couldn't find any dermatologists listed in Smalltown" in r.messages[0]
    assert r.clinics[0].name == "District Skin Hospital"


def test_falls_back_to_state_when_district_has_none(monkeypatch):
    monkeypatch.setattr(ds, "_http_json", fake_http({"state": [clinic("State Skin Centre", 19.0, 75.0)]}))
    r = ds.search("Smalltown", "Bigdistrict", "Maharashtra")
    assert r.level == "state" and r.area == "Maharashtra"
    assert any("district either" in m for m in r.messages)


def test_unknown_city_is_explained_politely(monkeypatch):
    monkeypatch.setattr(ds, "_http_json", fake_http({"state": [clinic("State Skin Centre", 19.0, 75.0)]}))
    r = ds.search("Nowhereville", "", "Maharashtra")
    assert "couldn't find “Nowhereville” on the map" in r.messages[0]
    assert r.level == "state"


def test_nothing_anywhere_points_to_google_maps(monkeypatch):
    monkeypatch.setattr(ds, "_http_json", fake_http({}))
    r = ds.search("Smalltown", "", "Maharashtra")
    assert r.clinics == [] and r.level == "none"
    assert "Google Maps button" in r.messages[-1]


def test_service_down_gives_friendly_error(monkeypatch):
    def broken(*a, **k):
        raise ds.MapServiceError("timeout")
    monkeypatch.setattr(ds, "_http_json", broken)
    r = ds.search("Smalltown", "", "Maharashtra")
    assert r.clinics == [] and "couldn't reach the map service" in r.error
    assert r.maps_search_url.startswith("https://www.google.com/maps/search/")


def test_distance_km():
    assert ds.distance_km(18.52, 73.86, 19.08, 72.88) == pytest.approx(120, abs=5)   # Pune -> Mumbai


def test_same_clinic_listed_twice_is_shown_once(monkeypatch):
    monkeypatch.setattr(ds, "_http_json", fake_http({"city": [
        clinic("Ethereal Skin Clinic", 18.01, 74.0, address={"road": "Service Road"}),
        clinic("Ethereal Skin Clinic", 18.012, 74.001, address={"house_number": "109-C", "road": "Service Road"}),
        clinic("Other Skin Clinic", 18.02, 74.0, address={"road": "MG Road"})]}))
    r = ds.search("Smalltown", "Bigdistrict", "Maharashtra")
    names = [c.name for c in r.clinics]
    assert names.count("Ethereal Skin Clinic") == 1 and "Other Skin Clinic" in names
    assert next(c for c in r.clinics if c.name == "Ethereal Skin Clinic").address.startswith("109-C")  # fuller one kept
