"""Find dermatologists near a place in India: city/town first, then the district, then the whole state.

Where the data comes from
- Default (free, no key): OpenStreetMap through its Nominatim search service. First it finds the place
  (centre + bounding box), then it searches inside that box for clinics, doctors and hospitals with "skin"
  in their name (e.g. "Kimaya Skin Clinic", "Skin & Hair Clinic"). OpenStreetMap is volunteer-made, so small
  towns may have nothing listed. (The Overpass API was tried first but its public servers time out.)
- Optional: set GOOGLE_MAPS_API_KEY to use Google Places (Text Search) for the clinic list instead. It usually
  has more clinics and phone numbers. Nominatim is still used to find the place centre for distances.
- Always: a ready-made Google Maps search link "dermatologist in City, District, State" (needs no key).

Only the place names the person typed are sent to these services, never anything about the person.
Results are cached in memory for a day, and Nominatim calls are spaced 1 second apart (its usage policy).
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

NOMINATIM = "https://nominatim.openstreetmap.org/search"
GOOGLE_TEXT_SEARCH = "https://places.googleapis.com/v1/places:searchText"
USER_AGENT = "DermaCareAI/1.0 (student project; dermatologist finder)"
TIMEOUT = 15
MAX_RESULTS = 10
CITY_RADIUS_KM = 25     # clinics further than this from the town centre don't count as "in" the town
CACHE_SECONDS = 24 * 3600
# OpenStreetMap kinds of place that can be a skin clinic
CLINIC_TYPES = {("amenity", "clinic"), ("amenity", "doctors"), ("amenity", "hospital"),
                ("healthcare", "clinic"), ("healthcare", "doctor"), ("healthcare", "centre"),
                ("healthcare", "hospital")}


class MapServiceError(RuntimeError):
    """The map service could not be reached or answered with an error."""


@dataclass
class Clinic:
    name: str
    address: str
    lat: float
    lon: float
    phone: str = ""
    distance_km: float | None = None

    @property
    def maps_url(self) -> str:
        q = f"{self.name}, {self.address}" if self.address else f"{self.lat},{self.lon}"
        return "https://www.google.com/maps/search/?" + urllib.parse.urlencode({"api": 1, "query": q})

    @property
    def check_url(self) -> str:
        """Google Maps search for this clinic by name and town, to confirm address, hours and reviews."""
        return "https://www.google.com/maps/search/?" + urllib.parse.urlencode(
            {"api": 1, "query": f"{self.name} {self.address}".strip()})

    @property
    def directions_url(self) -> str:
        """Google Maps directions to the clinic (opens in a new tab)."""
        return f"https://www.google.com/maps/dir/?api=1&destination={self.lat:.6f},{self.lon:.6f}"

    @property
    def display_phone(self) -> str:
        """First number only: listings often hold several ("0731...;98...")."""
        first = re.split(r"[;,/]", self.phone or "")[0].strip()
        return first if len(re.sub(r"\D", "", first)) >= 8 else ""

    @property
    def tel_href(self) -> str:
        """tel: link (digits and a leading + only), or "" when there is no usable number."""
        num = self.display_phone
        return "tel:" + ("+" if num.startswith("+") else "") + re.sub(r"\D", "", num) if num else ""


@dataclass
class SearchResult:
    clinics: list[Clinic] = field(default_factory=list)
    level: str = "none"          # "city" | "district" | "state" | "none"
    area: str = ""               # the place the clinics are in, e.g. "Pune district"
    messages: list[str] = field(default_factory=list)   # friendly notes about fallbacks
    maps_search_url: str = ""
    error: str = ""              # set when the map service could not be reached
    source: str = ""             # "OpenStreetMap" or "Google Maps"


# --------------------------------------------------------------------------------------------- helpers
def google_maps_search_url(city: str, district: str, state: str) -> str:
    place = ", ".join(p for p in (city, district, state) if p)
    return "https://www.google.com/maps/search/?" + urllib.parse.urlencode(
        {"api": 1, "query": f"dermatologist in {place}"})


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line (great-circle) distance in km."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


_cache: dict[str, tuple[float, object]] = {}
_cache_lock = threading.Lock()
_nominatim_lock = threading.Lock()
_last_nominatim = [0.0]


def _cached(key: str, fn):
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1]
    value = fn()
    with _cache_lock:
        _cache[key] = (now, value)
    return value


def _http_json(url: str, data: bytes | None = None, headers: dict | None = None) -> object:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 - fixed https hosts above
            return json.loads(r.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - any network/HTTP/JSON problem means "service unavailable"
        raise MapServiceError(str(exc)) from exc


def _nominatim(params: dict) -> list:
    """One Nominatim request (India only), at most one per second as its usage policy asks."""
    with _nominatim_lock:
        wait = 1.05 - (time.time() - _last_nominatim[0])
        if wait > 0:
            time.sleep(wait)
        url = NOMINATIM + "?" + urllib.parse.urlencode({**params, "countrycodes": "in", "format": "jsonv2"})
        try:
            try:
                return _http_json(url) or []
            except MapServiceError:   # the free service sometimes hiccups: wait a moment and try once more
                time.sleep(2)
                return _http_json(url) or []
        finally:
            _last_nominatim[0] = time.time()


# --------------------------------------------------------------------------------------------- geocoding
def geocode(query: str) -> dict | None:
    """Centre and bounding box (south, west, north, east) of a place in India, or None if it can't be found."""
    def run():
        rows = _nominatim({"q": query, "limit": 1})
        if not rows:
            return None
        row = rows[0]
        s, n, w, e = (float(v) for v in row["boundingbox"])
        return {"lat": float(row["lat"]), "lon": float(row["lon"]), "bbox": (s, w, n, e),
                "name": row.get("display_name", query)}
    return _cached("geo:" + query.lower(), run)


# --------------------------------------------------------------------------------------------- clinic sources
def _address(addr: dict) -> str:
    """A postal-style address: "Badgara Crest, 301, LB Dawar Marg, Indore, Madhya Pradesh 452001".

    Uses house number, road and the local area (neighbourhood/suburb), then the town and state with the PIN code.
    Map-only district names such as "Indore City" or "... Tahsil" are left out: they aren't part of a postal address.
    """
    town = addr.get("city") or addr.get("town") or addr.get("village") or ""
    skip = {town.lower(), "", None}
    local = []
    for k in ("house_number", "road", "neighbourhood", "quarter", "suburb"):
        v = (addr.get(k) or "").strip()
        if v and v.lower() not in skip and "tahsil" not in v.lower() and v.lower() != f"{town.lower()} city":
            skip.add(v.lower())
            local.append(v)
    tail = ", ".join(x for x in (town, addr.get("state", "")) if x)
    pin = addr.get("postcode", "")
    return ", ".join(local + ([f"{tail} {pin}".strip()] if tail or pin else []))


def _same_place(a: Clinic, b: Clinic) -> bool:
    """The same clinic entered more than once on the map: same name, within 1.5 km."""
    norm = lambda n: re.sub(r"[^a-z0-9]", "", n.lower())   # noqa: E731
    return norm(a.name) == norm(b.name) and distance_km(a.lat, a.lon, b.lat, b.lon) <= 1.5


def osm_clinics(bbox) -> list[Clinic]:
    """Clinics/doctors/hospitals with "skin" in their name inside a bounding box (south, west, north, east)."""
    s, w, n, e = bbox

    def run():
        rows = _nominatim({"q": "skin", "viewbox": f"{w},{n},{e},{s}", "bounded": 1, "limit": 40,
                           "addressdetails": 1, "extratags": 1})
        out = []
        for r in rows:
            # some listings stuff adverts into the name ("X Skin Clinic | Best Dermatologist in ..."): keep the name
            name = (r.get("name") or "").split(" | ")[0].strip()
            if (r.get("category"), r.get("type")) not in CLINIC_TYPES or "skin" not in name.lower():
                continue
            extra = r.get("extratags") or {}
            out.append(Clinic(name=name, address=_address(r.get("address") or {}), lat=float(r["lat"]),
                              lon=float(r["lon"]), phone=extra.get("phone") or extra.get("contact:phone", "")))
        return out
    return _cached("osm:" + ",".join(f"{v:.3f}" for v in bbox), run)


def google_clinics(text: str, key: str) -> list[Clinic]:
    def run():
        data = _http_json(GOOGLE_TEXT_SEARCH, data=json.dumps({"textQuery": text, "regionCode": "IN"}).encode(),
                          headers={"Content-Type": "application/json", "X-Goog-Api-Key": key,
                                   "X-Goog-FieldMask": "places.displayName,places.formattedAddress,"
                                                       "places.location,places.nationalPhoneNumber"})
        out = []
        for p in data.get("places", []):
            loc = p.get("location") or {}
            if "latitude" not in loc:
                continue
            out.append(Clinic(name=(p.get("displayName") or {}).get("text", "Clinic"),
                              address=p.get("formattedAddress", ""), lat=loc["latitude"], lon=loc["longitude"],
                              phone=p.get("nationalPhoneNumber", "")))
        return out
    return _cached("google:" + text.lower(), run)


# --------------------------------------------------------------------------------------------- main search
def search(city: str, district: str, state: str, google_key: str = "") -> SearchResult:
    """City first; if nothing is listed there, the district (if given); then the whole state.

    Places are looked up only when needed, so a city with clinics needs just two quick requests.
    """
    # "indore" -> "Indore" for display (names typed with capitals are kept as they are)
    city, district, state = (v.strip().title() if v.strip().islower() else v.strip() for v in (city, district, state))
    res = SearchResult(maps_search_url=google_maps_search_url(city, district, state),
                       source="Google Maps" if google_key else "OpenStreetMap")
    try:
        city_geo = geocode(", ".join(p for p in (city, district, state) if p))
        if city_geo is None and district:
            city_geo = geocode(f"{city}, {state}")
        if city_geo is None:
            res.messages.append(f"We couldn't find “{city}” on the map. Please check the spelling, "
                                "or try the nearest bigger town.")
        centre = city_geo

        steps = [("city", city, lambda: city_geo)]
        if district:
            steps.append(("district", f"{district} district", lambda: geocode(f"{district} district, {state}")))
        steps.append(("state", state, lambda: geocode(state)))

        for level, label, get_geo in steps:
            geo = get_geo()
            if geo is None:
                continue
            centre = centre or geo
            if google_key:
                place = {"city": ", ".join(p for p in (city, district, state) if p),
                         "district": f"{district} district, {state}", "state": state}[level]
                found = google_clinics(f"dermatologist in {place}", google_key)
            else:
                found = osm_clinics(geo["bbox"])
            if level == "city" and centre:
                # a town's map box can cover nearby cities: only count clinics really near the town
                found = [c for c in found
                         if distance_km(centre["lat"], centre["lon"], c.lat, c.lon) <= CITY_RADIUS_KM]
            if found:
                res.level, res.area, res.clinics = level, label, found
                break
            if level == "city":
                res.messages.append(f"We couldn't find any dermatologists listed in {city}, so we looked in the "
                                    + ("wider district." if district else "rest of the state."))
            elif level == "district":
                res.messages.append(f"There were none listed in {district} district either, "
                                    "so here are some from across the state.")
        if not res.clinics:
            res.messages.append("We couldn't find any dermatologists listed online for this area. "
                                "The Google Maps button below may still find some near you.")
        if centre:
            for c in res.clinics:
                c.distance_km = round(distance_km(centre["lat"], centre["lon"], c.lat, c.lon), 1)
            res.clinics.sort(key=lambda c: c.distance_km)
        # the same clinic is often on the map several times: keep one (the one with the fullest address)
        unique: list[Clinic] = []
        for c in res.clinics:
            twin = next((u for u in unique if _same_place(u, c)), None)
            if twin is None:
                unique.append(c)
            elif len(c.address) > len(twin.address):
                unique[unique.index(twin)] = c
        res.clinics = unique[:MAX_RESULTS]
    except MapServiceError:
        res.error = ("We couldn't reach the map service just now. Please try again in a minute, "
                     "or use the Google Maps button below.")
        res.clinics, res.level = [], "none"
    return res
