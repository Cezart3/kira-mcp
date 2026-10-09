"""Distances + geocoding through OpenStreetMap Nominatim.

Nominatim is a shared community service: we stay at 1 request/second, identify
ourselves, cache every answer on disk, and cap new lookups per search.
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from pathlib import Path

import requests

from kira_mcp.http import UA
from kira_mcp.localities import Locality

log = logging.getLogger(__name__)

NOMINATIM_URL = os.environ.get("KIRA_NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
WALK_KMH = 4.7
DETOUR = 1.3  # straight line -> on-foot distance


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def walk_minutes(distance_m: float) -> int:
    return round(distance_m * DETOUR / 1000 / WALK_KMH * 60)


def maps_link(olat: float, olon: float, dlat: float, dlon: float, mode: str = "walking") -> str:
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={olat},{olon}&destination={dlat},{dlon}&travelmode={mode}"
    )


def _cache_dir() -> Path:
    base = os.environ.get("KIRA_CACHE_DIR")
    if base:
        return Path(base)
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "kira-mcp"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "kira-mcp"


class Geocoder:
    """Nominatim with a persistent JSON cache (misses are cached too)."""

    def __init__(self, cache_file: Path | None = None):
        self.path = cache_file or _cache_dir() / "geocode.json"
        self._lock = threading.Lock()
        self._last = 0.0
        try:
            self._cache: dict[str, list[float] | None] = json.loads(
                self.path.read_text("utf-8")
            )
        except (OSError, ValueError):
            self._cache = {}

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._cache, ensure_ascii=False), "utf-8")
        except OSError as e:
            log.debug("geocode cache not saved: %s", e)

    @staticmethod
    def _key(query: str, loc: Locality) -> str:
        return f"{' '.join(query.split()).lower()}|{loc.label}"

    def cached(self, query: str, loc: Locality) -> tuple[bool, tuple[float, float] | None]:
        key = self._key(query, loc)
        if key in self._cache:
            hit = self._cache[key]
            return True, (hit[0], hit[1]) if hit else None
        return False, None

    def geocode_place(self, query: str, loc: Locality) -> tuple[float, float] | None:
        """Like geocode, for what a person types ('UMF Iuliu Hatieganu'): OSM may
        not know the abbreviation, so retry without leading words."""
        words = query.split()
        for i in range(min(3, len(words))):
            found = self.geocode(" ".join(words[i:]), loc)
            if found or len(words) - i <= 1:
                return found
        return None

    def geocode(self, query: str, loc: Locality) -> tuple[float, float] | None:
        """Coordinates for a place inside a locality, or None."""
        query = " ".join(query.split())
        if not query:
            return None
        known, coords = self.cached(query, loc)
        if known:
            return coords
        with self._lock:
            wait = 1.1 - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            radius_km = 15 if loc.kind == "municipiu" else 8
            dlat = radius_km / 111.0
            dlon = radius_km / (111.0 * math.cos(math.radians(loc.lat)))
            params = {
                "q": f"{query}, {loc.name}",  # county/country words make OSM miss POIs
                "format": "json",
                "limit": 1,
                "countrycodes": "ro",
                "viewbox": f"{loc.lon - dlon},{loc.lat + dlat},{loc.lon + dlon},{loc.lat - dlat}",
                "bounded": 1,
            }
            try:
                r = requests.get(NOMINATIM_URL, params=params, timeout=20,
                                 headers={"User-Agent": UA})
                r.raise_for_status()
                data = r.json()
            except (requests.RequestException, ValueError) as e:
                log.warning("geocode failed for %r: %s", query, e)
                return None  # transient: don't cache
            found = (float(data[0]["lat"]), float(data[0]["lon"])) if data else None
            self._cache[self._key(query, loc)] = list(found) if found else None
            self._save()
            return found


_geocoder: Geocoder | None = None


def geocoder() -> Geocoder:
    global _geocoder
    if _geocoder is None:
        _geocoder = Geocoder()
    return _geocoder
