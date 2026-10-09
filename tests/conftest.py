"""Offline test harness: the sites are served from synthetic fixtures (invented
ads with the real page structure), geocoding from a small table."""
from pathlib import Path

import pytest

from kira_mcp import geo, http
from kira_mcp.localities import Locality

FIXTURES = Path(__file__).parent / "fixtures"

ROUTES = {
    "storia.ro/ro/rezultate/inchiriere/apartament/cluj/cluj--napoca": "storia_search.html",
    "storia.ro/ro/oferta/": "storia_ad.html",
    "publi24.ro/anunturi/imobiliare/de-inchiriat/apartamente/cluj/cluj-napoca/": (
        "publi24_search.html"
    ),
    "lajumate.ro/anunturi/imobiliare/apartamente-de-inchiriat/in/cluj/cluj-napoca": (
        "lajumate_search.html"
    ),
}


class FakeSession:
    def __init__(self):
        self.calls: list[tuple[str, dict | None]] = []

    def fetch(self, url: str, params: dict | None = None) -> tuple[int, str]:
        self.calls.append((url, params))
        for key, name in ROUTES.items():
            if key in url:
                return 200, (FIXTURES / name).read_text("utf-8")
        return 404, ""

    def get_text(self, url: str, params: dict | None = None) -> str | None:
        status, body = self.fetch(url, params)
        return body if status == 200 else None


PLACES = {
    "umf": (46.7663, 23.5855),
    "strada lunii": (46.7550, 23.5800),   # ~1.3 km from umf
    "marasti": (46.7800, 23.6150),        # ~2.8 km
    "gheorgheni": (46.7700, 23.6250),
}


class FakeGeocoder:
    def __init__(self):
        self.lookups: list[str] = []
        self.cache: dict[str, tuple[float, float] | None] = {}

    def cached(self, query: str, loc: Locality):
        q = query.strip().lower()
        return q in self.cache, self.cache.get(q)

    def geocode(self, query: str, loc: Locality):
        self.lookups.append(query)
        q = query.strip().lower()
        self.cache[q] = PLACES.get(q)
        return self.cache[q]

    geocode_place = geocode


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    fake = FakeSession()
    monkeypatch.setattr(http, "_session", fake)
    gc = FakeGeocoder()
    monkeypatch.setattr(geo, "_geocoder", gc)
    # storia remembers which path worked per locality; start clean
    from kira_mcp.sites import SITES

    SITES["storia"]._paths.clear()  # type: ignore[attr-defined]
    return fake, gc
