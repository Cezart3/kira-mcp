"""storia.ro — search pages server-render the results as __NEXT_DATA__ JSON.

Supports server-side price and room filters, which makes it the most precise
source: a filtered query returns only matching ads.
"""
from __future__ import annotations

import logging
from contextlib import suppress
from datetime import datetime

from kira_mcp.extract import find_price_text
from kira_mcp.http import session
from kira_mcp.localities import Locality
from kira_mcp.sites.base import Filters, RawListing, SiteResult, next_data, status_for
from kira_mcp.text import strip_html

log = logging.getLogger(__name__)

BASE = "https://www.storia.ro"
_ROOMS_WORDS = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5, "SIX": 6}
_ROOMS_ENUM = {1: ["ONE"], 2: ["TWO"], 3: ["THREE"], 4: ["FOUR", "FIVE", "SIX"]}
# reverseGeocoding levels finer than the city itself
_DISTRICT_LEVELS = {"district", "sector", "residential", "neighbourhood", "street"}


def _parse_rooms(value) -> int | None:
    if isinstance(value, int):
        return value if 1 <= value <= 6 else None
    if isinstance(value, str):
        return _ROOMS_WORDS.get(value.upper())
    return None


def _parse_dt(value) -> datetime | None:
    with suppress(ValueError, TypeError):
        return datetime.fromisoformat(str(value).replace(" ", "T").replace("Z", "+00:00"))
    return None


class Storia:
    name = "storia"
    hosts = ("storia.ro",)

    def __init__(self) -> None:
        self._paths: dict[Locality, str] = {}  # locality -> storia path that worked

    def _params(self, filters: Filters, page: int) -> dict:
        p: dict = {"page": page, "by": "LATEST", "direction": "DESC"}
        if filters.min_price_eur:
            p["priceMin"] = int(filters.min_price_eur)
        if filters.max_price_eur:
            p["priceMax"] = int(filters.max_price_eur)
        if filters.rooms:
            words = [w for r in sorted(set(filters.rooms)) for w in _ROOMS_ENUM.get(min(r, 4), [])]
            p["roomsNumber"] = "[" + ",".join(dict.fromkeys(words)) + "]"
        return p

    def _search(self, loc: Locality, kind: str, filters: Filters, pages: int) -> SiteResult:
        res = SiteResult(site=self.name)
        paths = [self._paths[loc]] if loc in self._paths else loc.storia_paths()
        data = None
        for path in paths:
            url = f"{BASE}/ro/rezultate/inchiriere/{kind}/{path}"
            status, html = session().fetch(url, self._params(filters, 1))
            res.url = url
            if status == 200:
                data = next_data(html)
                self._paths[loc] = path
                break
            if status != 404:
                res.status = status_for(status)
                return res
        if data is None:
            res.status = "not-found"
            return res

        page = 1
        while True:
            try:
                sa = data["props"]["pageProps"]["data"]["searchAds"]
            except (KeyError, TypeError):
                break
            pag = sa.get("pagination") or {}
            res.total_available = pag.get("totalItems", res.total_available)
            for it in sa.get("items") or []:
                raw = self._to_raw(it)
                if raw:
                    res.items.append(raw)
            if page >= min(pages, pag.get("totalPages") or 1):
                break
            page += 1
            html = session().get_text(res.url, self._params(filters, page))
            data = next_data(html) if html else None
            if data is None:
                break
        return res

    def _to_raw(self, it: dict) -> RawListing | None:
        slug = it.get("slug") or ""
        href = it.get("href") or ""
        if slug:
            url = f"{BASE}/ro/oferta/{slug}"
        elif href:
            url = BASE + href.replace("[lang]", "ro")
        else:
            return None

        loc = it.get("location") or {}
        names: list[str] = []
        district = ""
        with suppress(AttributeError, TypeError):
            for lv in (loc.get("reverseGeocoding") or {}).get("locations") or []:
                if lv.get("name"):
                    names.append(str(lv["name"]))
                if lv.get("locationLevel") in _DISTRICT_LEVELS and lv.get("name"):
                    district = str(lv["name"])
        street = ""
        with suppress(AttributeError, TypeError):
            street = ((loc.get("address") or {}).get("street") or {}).get("name") or ""

        images = [
            im.get("large") or im.get("medium") or im.get("small")
            for im in it.get("images") or []
            if isinstance(im, dict)
        ]
        tag_text = " ".join(
            str(t.get("value", "")) for t in it.get("tags") or [] if isinstance(t, dict)
        )
        tp = it.get("totalPrice") or {}
        area = it.get("areaInSquareMeters")
        return RawListing(
            site=self.name,
            url=url,
            title=(it.get("title") or "").strip(),
            description=strip_html(it.get("shortDescription") or ""),
            price_value=str(tp.get("value", "")),
            price_currency=str(tp.get("currency", "")),
            location_text=", ".join(reversed(names)),
            district=district,
            street=street,
            images=[u for u in images if u][:8],
            rooms=_parse_rooms(it.get("roomsNumber")),
            surface_m2=area if isinstance(area, int | float) else None,
            posted_at=_parse_dt(it.get("createdAtFirst") or it.get("dateCreated")),
            private_owner=it.get("isPrivateOwner") if isinstance(
                it.get("isPrivateOwner"), bool
            ) else None,
            parking_hint="GARAGE" in tag_text.upper() or "PARKING" in tag_text.upper(),
            extra_text=tag_text,
        )

    # ----- public -------------------------------------------------------------

    def search_rentals(self, loc: Locality, filters: Filters, pages: int) -> SiteResult:
        return self._search(loc, "apartament", filters, pages)

    def search_parking(self, loc: Locality, filters: Filters, pages: int) -> SiteResult:
        return self._search(loc, "garaj", Filters(max_price_eur=filters.max_price_eur), pages)

    def fetch_detail(self, item: RawListing) -> RawListing:
        html = session().get_text(item.url)
        data = next_data(html) if html else None
        try:
            ad = data["props"]["pageProps"]["ad"]  # type: ignore[index]
        except (KeyError, TypeError):
            return item

        desc = strip_html(str(ad.get("description") or ""))
        if len(desc) > len(item.description):
            item.description = desc
        images = [
            im.get("large") or im.get("medium")
            for im in ad.get("images") or []
            if isinstance(im, dict)
        ]
        if any(images):
            item.images = [u for u in images if u][:8]
        if not item.title:
            item.title = str(ad.get("title") or "")
        # structured characteristics (heating, floor...) -> extractor text
        extras: list[str] = []
        for ch in ad.get("characteristics") or []:
            if isinstance(ch, dict):
                lk = ch.get("localizedKey") or ch.get("key")
                lv = ch.get("localizedValue") or ch.get("value")
                if lk and lv:
                    extras.append(f"{lk}: {lv}")
        if extras:
            item.extra_text = (item.extra_text + " | " + "; ".join(extras)).strip(" |")
        with suppress(AttributeError, TypeError):
            street = (((ad.get("location") or {}).get("address") or {}).get("street") or {})
            if street.get("name"):
                item.street = str(street["name"])
        if not item.price_value:
            for ch in ad.get("characteristics") or []:
                if isinstance(ch, dict) and ch.get("key") == "price":
                    found = find_price_text(str(ch.get("localizedValue") or ""))
                    if found:
                        item.price_value, item.price_currency = found
        return item
