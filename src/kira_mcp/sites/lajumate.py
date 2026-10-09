"""lajumate.ro — search pages server-render ads as __NEXT_DATA__ JSON
(props.pageProps.adsServer + paginationServer). Structured fields (rooms,
surface, floor) come in ad_fields."""
from __future__ import annotations

from contextlib import suppress
from datetime import datetime

from kira_mcp.http import session
from kira_mcp.localities import Locality
from kira_mcp.sites.base import Filters, RawListing, SiteResult, next_data, status_for
from kira_mcp.text import strip_html

BASE = "https://lajumate.ro"
IMG_BASE = "https://api-preprod.lajumate.ro/opt-image"
SEARCH_PATH = "/anunturi/imobiliare/apartamente-de-inchiriat/in"


def _num(v) -> float | None:
    with suppress(TypeError, ValueError):
        return float(str(v).replace(",", "."))
    return None


class Lajumate:
    name = "lajumate"
    hosts = ("lajumate.ro",)

    def to_raw(self, ad: dict) -> RawListing | None:
        ad_id, title = ad.get("id"), (ad.get("title") or "").strip()
        if not ad_id or not title:
            return None
        slug = ad.get("slug") or ""
        fields = {
            f.get("name"): f
            for f in ad.get("ad_fields") or ad.get("fields") or []  # search page / ad page
            if isinstance(f, dict) and f.get("name")
        }

        def val(name: str):
            return (fields.get(name) or {}).get("value")

        rooms = _num(val("rooms"))
        surface = _num(val("real_estate_dimensions"))
        floor = val("real_estate_floor")
        city = ad.get("city") or {}
        location = ", ".join(
            p for p in (city.get("name"), (city.get("county") or {}).get("name")) if p
        )
        posted = None
        with suppress(ValueError, TypeError):
            posted = datetime.fromisoformat(str(ad.get("listed_at")).replace(" ", "T"))
        return RawListing(
            site=self.name,
            url=f"{BASE}/ad/{slug}-{ad_id}" if slug else f"{BASE}/ad/{ad_id}",
            title=title,
            description=strip_html(ad.get("description") or ""),
            price_value=str(ad.get("price") or ""),
            price_currency=str(ad.get("currency") or ""),
            location_text=location,
            images=[
                f"{IMG_BASE}/{im['path'].lstrip('/')}?w=800"
                for im in ad.get("images") or []
                if isinstance(im, dict) and im.get("path")
            ][:8],
            rooms=int(rooms) if rooms and 1 <= rooms <= 6 else None,
            surface_m2=surface if surface and 10 <= surface <= 400 else None,
            floor=str(floor) if floor not in (None, "") else None,
            posted_at=posted,
            extra_text="; ".join(
                f"{f.get('field_key')}: {f.get('value')}" for f in fields.values()
            ),
        )

    def search_rentals(self, loc: Locality, filters: Filters, pages: int) -> SiteResult:
        url = f"{BASE}{SEARCH_PATH}/{loc.lajumate_path()}"
        res = SiteResult(site=self.name, url=url)
        page = 1
        while page <= pages:
            status, html = session().fetch(url, {"page": page} if page > 1 else None)
            if status != 200:
                if page == 1:
                    res.status = status_for(status)
                break
            data = next_data(html)
            try:
                pp = data["props"]["pageProps"]  # type: ignore[index]
            except (KeyError, TypeError):
                break
            ads = pp.get("adsServer") or []
            pag = pp.get("paginationServer") or {}
            if page == 1:
                res.total_available = pag.get("totalAds")
            res.items.extend(r for r in map(self.to_raw, ads) if r)
            if not ads or page >= (pag.get("totalPages") or 1):
                break
            page += 1
        res.items = [r for r in res.items if not r.location_text or loc.matches(r.location_text)]
        return res

    def fetch_detail(self, item: RawListing) -> RawListing:
        html = session().get_text(item.url)
        data = next_data(html) if html else None
        with suppress(KeyError, TypeError):
            pp = data["props"]["pageProps"]  # type: ignore[index]
            ad = pp.get("adData") or {}
            if isinstance(ad, dict) and ad.get("id"):
                full = self.to_raw(ad)
                if full:
                    if len(full.description) > len(item.description):
                        item.description = full.description
                    item.images = full.images or item.images
                    item.extra_text = full.extra_text or item.extra_text
                    item.title = item.title or full.title
                    item.price_value = item.price_value or full.price_value
                    item.price_currency = item.price_currency or full.price_currency
        return item
