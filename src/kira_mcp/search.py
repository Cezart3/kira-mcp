"""Live search: fetch every source site in parallel, extract facts, filter,
de-duplicate cross-posted ads, optionally measure distance from a place."""
from __future__ import annotations

import logging
import os
import re
from collections import Counter
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from kira_mcp import extract as ex
from kira_mcp.geo import geocoder, haversine_m, maps_link, walk_minutes
from kira_mcp.localities import Locality, resolve
from kira_mcp.sites import SITES, UNSUPPORTED, Filters, RawListing, SiteResult, site_for_url
from kira_mcp.text import fold, redact_personal

log = logging.getLogger(__name__)

RON_PER_EUR = float(os.environ.get("KIRA_RON_PER_EUR", "5.0"))
RENT_MIN_EUR = 80       # below: a parking spot or a room-per-night, not a flat
RENT_MAX_EUR = 15000    # above: a sale price or a parse error
GEOCODE_BUDGET = 20     # new Nominatim lookups per search (cached ones are free)
DETAIL_BUDGET = 24      # full-ad fetches per search when filtering on heating/parking
PARKING_STATUSES = {p.value for p in ex.Parking}
HEATING_VALUES = {ex.Heating.CENTRALA_PROPRIE.value, ex.Heating.TERMOFICARE.value}
SORTS = ("newest", "price_asc", "price_desc", "distance")


@dataclass(slots=True)
class Listing:
    raw: RawListing
    price_eur: float | None
    rooms: int | None
    surface_m2: float | None
    floor: str | None
    heating: str
    parking: str
    parking_confidence: int
    negotiable: bool
    street: str
    distance_m: float | None = None
    geo_precision: str | None = None
    origin: tuple[float, float, str] | None = None
    coords: tuple[float, float] | None = None
    also_on: list[str] = field(default_factory=list)

    def to_dict(self, snippet_len: int = 220) -> dict:
        r = self.raw
        d: dict = {
            "title": redact_personal(r.title),
            "url": r.url,
            "site": r.site,
            "price_eur": self.price_eur,
            "price_original": f"{r.price_value} {r.price_currency}".strip() or None,
            "negotiable": self.negotiable or None,
            "rooms": self.rooms,
            "surface_m2": self.surface_m2,
            "floor": self.floor,
            "heating": self.heating,
            "parking": self.parking,
            "area": r.location_text or None,
            "street": self.street or None,
            "owner": {True: "private", False: "agency"}.get(r.private_owner),  # type: ignore[arg-type]
            "posted": r.posted_at.date().isoformat() if r.posted_at else None,
            "snippet": redact_personal(r.description[:snippet_len]) or None,
            "also_listed_on": self.also_on or None,
        }
        if self.distance_m is not None and self.origin and self.coords:
            d["distance"] = {
                "from": self.origin[2],
                "meters": int(self.distance_m),
                "walk_minutes": walk_minutes(self.distance_m),
                "precision": self.geo_precision,
                "directions": maps_link(
                    self.coords[0], self.coords[1], self.origin[0], self.origin[1], "walking"
                ),
            }
        return {k: v for k, v in d.items() if v is not None}


def full_text(r: RawListing) -> str:
    return " ".join(p for p in (r.title, r.description, r.extra_text, r.location_text) if p)


def normalize(r: RawListing, loc: Locality | None = None) -> Listing:
    """Run every extractor over one ad. Structured site fields win over text."""
    text = full_text(r)
    price = ex.to_eur(r.price_value, r.price_currency, RON_PER_EUR)
    if price is not None and price > RENT_MAX_EUR:
        price = None
    parking, conf = ex.classify_parking(text, r.parking_hint)
    stops = frozenset(fold(loc.name).replace("-", " ").split()) if loc else frozenset()
    street = r.street or ex.extract_street(text, stops)
    return Listing(
        raw=r,
        price_eur=price,
        rooms=r.rooms or ex.extract_rooms(text),
        surface_m2=r.surface_m2 or ex.extract_surface(text),
        floor=r.floor or ex.extract_floor(text),
        heating=ex.classify_heating(text).value,
        parking=parking.value,
        parking_confidence=conf,
        negotiable=bool(ex.NEGOTIABLE.search(fold(text))),
        street=street,
    )


def _dedup(listings: list[Listing]) -> list[Listing]:
    """The same flat is often posted on several sites: same rooms, surface and
    (rounded) price. Keep the richest copy, remember where else it is."""
    groups: dict[tuple, Listing] = {}
    out: list[Listing] = []
    for li in listings:
        if not (li.rooms and li.surface_m2 and li.price_eur):
            out.append(li)
            continue
        key = (li.rooms, round(li.surface_m2), round(li.price_eur / 10))
        kept = groups.get(key)
        if kept is None:
            groups[key] = li
            out.append(li)
        elif kept.raw.site != li.raw.site:
            kept.also_on.append(li.raw.url)
        else:
            out.append(li)  # same site, same numbers: two flats in one building
    return out


def _fetch_all(
    loc: Locality, filters: Filters, pages: int, sites: Iterable[str], parking: bool = False
) -> list[SiteResult]:
    def run(name: str) -> SiteResult:
        site = SITES[name]
        try:
            if parking:
                return site.search_parking(loc, filters, pages)  # type: ignore[attr-defined]
            return site.search_rentals(loc, filters, pages)
        except Exception as e:  # one broken site must not sink the search
            log.exception("%s failed", name)
            return SiteResult(site=name, status="error", error=f"{type(e).__name__}: {e}")

    names = list(sites)
    with ThreadPoolExecutor(max_workers=len(names) or 1) as pool:
        return list(pool.map(run, names))


def _enrich(items: list[Listing], loc: Locality) -> None:
    """Fetch each ad's full page (sites in parallel, politely in turn per site)
    and re-run the extractors on the complete text."""
    by_site: dict[str, list[Listing]] = {}
    for li in items:
        by_site.setdefault(li.raw.site, []).append(li)

    def run(group: list[Listing]) -> None:
        for li in group:
            try:
                SITES[li.raw.site].fetch_detail(li.raw)
            except Exception:  # keep what the result card gave us
                log.exception("detail fetch failed: %s", li.raw.url)
                continue
            fresh = normalize(li.raw, loc)
            for name in ("price_eur", "rooms", "surface_m2", "floor", "heating",
                         "parking", "parking_confidence", "negotiable", "street"):
                setattr(li, name, getattr(fresh, name) or getattr(li, name))
            li.heating, li.parking = fresh.heating, fresh.parking

    with ThreadPoolExecutor(max_workers=len(by_site) or 1) as pool:
        list(pool.map(run, by_site.values()))


def _place_by_text(items: list[Listing], known: Iterable[str]) -> None:
    """Neighbourhood names the sites use for this locality (storia gives one for
    most ads) are matched against the ads' own words:
    - an ad pinned to the default spot ('Centru, Piata Unirii') whose title says
      'Marasti' is moved to Marasti;
    - an ad with no location data that says 'zona Marasti' gets one.
    `known`: every district seen in this search, before filtering."""
    names = {fold(d): d for d in known if d and len(d) >= 4}
    if not names:
        return
    alts = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    in_title = re.compile(rf"\b({alts})\b")
    in_text = re.compile(rf"\b(?:zona|cartier(?:ul)?|in)\s+({alts})\b")
    for li in items:
        own = fold(li.raw.district) if li.raw.district else ""
        hits = [m.group(1) for m in in_title.finditer(fold(li.raw.title))]
        if not hits and not own:
            hits = [m.group(1) for m in in_text.finditer(fold(li.raw.description))]
        if not hits or own in hits:
            continue
        li.raw.district = names[hits[0]]
        if li.street and li.street == li.raw.street:  # the site's pin, as wrong as its district
            li.street = ""


def _locate(
    items: list[Listing], loc: Locality, origin: tuple[float, float, str], budget: int
) -> None:
    """Coordinates for each listing from its street (or else its district), then
    distance to the origin. Cached places are free; new lookups spend the budget,
    on the places that cover the most listings first (a district is shared by
    many ads, a street by few)."""
    gc = geocoder()

    def candidates(li: Listing):
        return [(q, p) for q, p in ((li.street, "street"), (li.raw.district, "district")) if q]

    wanted: Counter[str] = Counter()
    for li in items:
        for q, _ in candidates(li):
            if not gc.cached(q, loc)[0]:
                wanted[q] += 1
    for q, _ in wanted.most_common(budget):
        gc.geocode(q, loc)

    for li in items:
        for q, precision in candidates(li):
            known, coords = gc.cached(q, loc)
            if known and coords:
                li.coords, li.geo_precision, li.origin = coords, precision, origin
                li.distance_m = haversine_m(coords[0], coords[1], origin[0], origin[1])
                break


def _source_report(results: list[SiteResult]) -> list[dict]:
    out = []
    for r in results:
        d = {"site": r.site, "status": r.status, "fetched": len(r.items), "url": r.url}
        if r.total_available is not None:
            d["total_on_site"] = r.total_available
        if r.elsewhere:
            d["skipped_other_localities"] = r.elsewhere
        if r.error:
            d["error"] = r.error
        out.append(d)
    return out


def search_rentals(
    city: str,
    county: str | None = None,
    *,
    min_price: float | None = None,
    max_price: float | None = None,
    rooms: list[int] | None = None,
    heating: str | None = None,
    parking: list[str] | None = None,
    owner_only: bool = False,
    keywords: str | None = None,
    near: str | None = None,
    max_walk_minutes: int | None = None,
    sort: str = "newest",
    limit: int = 15,
    pages: int = 2,
    sites: list[str] | None = None,
) -> dict:
    """Search apartment rentals live in any Romanian locality. See server.py for
    the parameter documentation agents read."""
    loc = resolve(city, county)
    if heating and heating not in HEATING_VALUES:
        raise ValueError(f"heating must be one of {sorted(HEATING_VALUES)}")
    bad = set(parking or ()) - PARKING_STATUSES
    if bad:
        raise ValueError(f"unknown parking value(s) {sorted(bad)}; use {sorted(PARKING_STATUSES)}")
    if sort not in SORTS:
        raise ValueError(f"sort must be one of {SORTS}")
    names = [s for s in (sites or SITES) if s in SITES]
    if not names:
        raise ValueError(f"no supported site in {sites}; supported: {sorted(SITES)}")
    limit = max(1, min(limit, 50))
    pages = max(1, min(pages, 5))
    wanted_rooms = {min(r, 4) for r in rooms or ()}

    results = _fetch_all(
        loc, Filters(min_price, max_price, tuple(sorted(wanted_rooms))), pages, names
    )

    notes: list[str] = []
    dropped: dict[str, int] = {}
    listings: list[Listing] = []
    seen: set[str] = set()
    for res in results:
        for raw in res.items:
            if raw.url in seen:
                continue
            seen.add(raw.url)
            reason = ex.drop_reason(raw.title, full_text(raw))
            li = normalize(raw, loc)
            if reason is None and li.price_eur is not None and li.price_eur < RENT_MIN_EUR:
                reason = "below-min-price"
            if reason:
                dropped[reason] = dropped.get(reason, 0) + 1
                continue
            listings.append(li)

    kw = [fold(k) for k in (keywords or "").split() if k.strip()]

    def keep_basic(li: Listing) -> bool:
        if min_price is not None and (li.price_eur is None or li.price_eur < min_price):
            return False
        if max_price is not None and (li.price_eur is None or li.price_eur > max_price):
            return False
        if wanted_rooms and (li.rooms is None or min(li.rooms, 4) not in wanted_rooms):
            return False
        if owner_only and li.raw.private_owner is not True:
            return False
        return not kw or all(k in fold(full_text(li.raw)) for k in kw)

    def keep_facts(li: Listing) -> bool:
        if heating and li.heating != heating:
            return False
        return not parking or li.parking in parking

    def newest(li: Listing) -> float:
        return li.raw.posted_at.timestamp() if li.raw.posted_at else 0.0

    basic = [li for li in listings if keep_basic(li)]
    if sort == "price_asc":
        basic.sort(key=lambda li: (li.price_eur is None, li.price_eur or 0))
    elif sort == "price_desc":
        basic.sort(key=lambda li: li.price_eur or 0, reverse=True)
    else:
        basic.sort(key=newest, reverse=True)

    # result cards carry a snippet; heating and parking are usually further down
    # the ad. When filtering on them, read the full ad of the undecided ones.
    undecided = [
        li for li in basic
        if (heating and li.heating == ex.Heating.UNKNOWN)
        or (parking and li.parking in (ex.Parking.UNKNOWN, ex.Parking.LIKELY_INCLUDED))
    ][:DETAIL_BUDGET]
    if undecided:
        _enrich(undecided, loc)
        # the full text can reveal what the snippet hid (a sale ad, a hotel-style let)
        late = set()
        for li in undecided:
            reason = ex.drop_reason(li.raw.title, full_text(li.raw))
            if reason:
                late.add(id(li))
                dropped[reason] = dropped.get(reason, 0) + 1
        basic = [li for li in basic if id(li) not in late]
        notes.append(
            f"Read the full text of {len(undecided)} ad(s) to check heating/parking "
            "(result pages only show a snippet)."
        )

    matched = _dedup([li for li in basic if keep_facts(li)])

    if near:
        o = geocoder().geocode_place(near, loc)
        if o is None:
            notes.append(f"Could not place {near!r} in {loc.label}; no distances computed.")
        else:
            origin = (o[0], o[1], near)
            # distance-sorted / filtered results need every candidate located;
            # otherwise only the ones we will return
            pool = matched if (sort == "distance" or max_walk_minutes) else matched[:limit]
            _place_by_text(matched, {li.raw.district for li in listings})
            _locate(pool, loc, origin, GEOCODE_BUDGET)
            unlocated = sum(1 for li in pool if li.distance_m is None)
            if max_walk_minutes:
                far = {
                    id(li) for li in matched
                    if li.distance_m is not None
                    and walk_minutes(li.distance_m) > max_walk_minutes
                }
                matched = [li for li in matched if id(li) not in far]
                notes.append(
                    f"{len(far)} listing(s) dropped as more than {max_walk_minutes} minutes "
                    "on foot away."
                )
            if sort == "distance" or max_walk_minutes:
                if sort == "distance":
                    matched.sort(key=lambda li: li.distance_m or 0)
                matched.sort(key=lambda li: li.distance_m is None)  # stable: located first
            if unlocated:
                notes.append(
                    f"{unlocated} listing(s) could not be placed (no usable street or "
                    "district); they come after the located ones, without a distance."
                )
            notes.append(
                "Distances are straight-line x1.3 at 4.7 km/h, from the location the "
                "poster entered; 'district' precision = measured from the "
                "neighbourhood centre."
            )
    elif sort == "distance" or max_walk_minutes:
        notes.append("Distance sort/filter needs `near`; ignored.")

    for r in results:
        if r.status == "blocked":
            notes.append(f"{r.site} refused the request (HTTP 403/429); try again later.")
    return {
        "locality": {"name": loc.name, "county": loc.county, "kind": loc.kind},
        "sources": _source_report(results),
        "not_searched": UNSUPPORTED,
        "dropped_non_rentals": dropped or None,
        "matched": len(matched),
        "returned": min(limit, len(matched)),
        "results": [li.to_dict() for li in matched[:limit]],
        "notes": notes or None,
    }


def get_listing(url: str) -> dict:
    """Full details of one ad from a supported site."""
    site = site_for_url(url)
    if site is None:
        raise ValueError(f"unsupported site: {url} (supported: {sorted(SITES)})")
    raw = site.fetch_detail(RawListing(site=site.name, url=url))
    if not (raw.title or raw.description):
        raise LookupError(f"could not read {url} (removed, or the site refused the request)")
    li = normalize(raw)
    d = li.to_dict(snippet_len=0)
    d.pop("snippet", None)
    d["description"] = redact_personal(raw.description[:6000])
    d["images"] = raw.images
    d["parking_confidence"] = li.parking_confidence
    d["not_a_rental"] = ex.drop_reason(raw.title, full_text(raw))
    return {k: v for k, v in d.items() if v not in (None, [], "")}


def search_parking(
    city: str,
    county: str | None = None,
    *,
    max_price: float | None = None,
    limit: int = 15,
    pages: int = 1,
) -> dict:
    """Parking spots and garages for rent (storia's garage category)."""
    loc = resolve(city, county)
    names = [n for n, s in SITES.items() if hasattr(s, "search_parking")]
    results = _fetch_all(loc, Filters(max_price_eur=max_price), max(1, min(pages, 3)),
                         names, parking=True)
    spots = []
    seen: set[str] = set()
    for res in results:
        for raw in res.items:
            if raw.url in seen or ex.APARTMENT_WORDS.search(fold(raw.title)):
                continue
            seen.add(raw.url)
            price = ex.to_eur(raw.price_value, raw.price_currency, RON_PER_EUR)
            if max_price is not None and (price is None or price > max_price):
                continue
            kind, numbered = ex.classify_parking_spot(full_text(raw))
            spot = {
                "title": redact_personal(raw.title),
                "url": raw.url,
                "price_eur": price,
                "kind": kind.value,
                "numbered_spot": numbered or None,
                "area": raw.location_text or None,
                "street": raw.street or None,
            }
            spots.append({k: v for k, v in spot.items() if v is not None})
    spots.sort(key=lambda s: s.get("price_eur") or float("inf"))
    return {
        "locality": {"name": loc.name, "county": loc.county, "kind": loc.kind},
        "sources": _source_report(results),
        "matched": len(spots),
        "results": spots[: max(1, min(limit, 50))],
    }
