"""Site adapter contract. An adapter turns one source site's pages into RawListings."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar, Protocol

from kira_mcp.localities import Locality

_NEXT_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def next_data(html: str) -> dict | None:
    """The JSON a Next.js page server-renders into __NEXT_DATA__."""
    m = _NEXT_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


@dataclass(slots=True)
class RawListing:
    site: str
    url: str
    title: str = ""
    description: str = ""
    price_value: str = ""       # as found on the site
    price_currency: str = ""
    location_text: str = ""     # site-provided location ('Gruia, Cluj-Napoca, Cluj')
    district: str = ""          # neighbourhood / sector, when the site gives one
    street: str = ""            # structured street, when the site gives one
    images: list[str] = field(default_factory=list)
    rooms: int | None = None
    surface_m2: float | None = None
    floor: str | None = None
    posted_at: datetime | None = None
    private_owner: bool | None = None  # True = owner, False = agency, None = unknown
    parking_hint: bool = False         # structured parking/garage tag from the site
    extra_text: str = ""               # tags/attributes fed to the extractors


@dataclass(frozen=True, slots=True)
class Filters:
    """Filters a site may apply server-side (the rest are applied after fetching)."""
    min_price_eur: float | None = None
    max_price_eur: float | None = None
    rooms: tuple[int, ...] = ()


@dataclass(slots=True)
class SiteResult:
    site: str
    status: str = "ok"  # ok | not-found | blocked | error
    url: str = ""
    items: list[RawListing] = field(default_factory=list)
    total_available: int | None = None  # how many the site says match, when it says
    error: str = ""


class Site(Protocol):
    name: ClassVar[str]
    hosts: ClassVar[tuple[str, ...]]

    def search_rentals(self, loc: Locality, filters: Filters, pages: int) -> SiteResult: ...

    def fetch_detail(self, item: RawListing) -> RawListing: ...


def status_for(http_status: int) -> str:
    if http_status == 404:
        return "not-found"
    if http_status in (401, 403, 429):
        return "blocked"
    return "error"
