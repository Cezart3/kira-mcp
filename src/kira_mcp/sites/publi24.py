"""publi24.ro — plain HTML cards (div.article-item); detail pages carry ld+json.

The site ignores its own page parameter (verified: page 2 returns page 1
reshuffled), so one page per search.
"""
from __future__ import annotations

import json
import re
from contextlib import suppress
from datetime import date, datetime, timedelta
from urllib.parse import unquote_plus, urljoin

from bs4 import BeautifulSoup

from kira_mcp.extract import find_price_text
from kira_mcp.http import session
from kira_mcp.localities import Locality
from kira_mcp.sites.base import Filters, RawListing, SiteResult, status_for
from kira_mcp.text import fold, squash_ws

BASE = "https://www.publi24.ro"
_LOCATION_ICON = r'use[href="#svg-icon-location"], use[xlink\:href="#svg-icon-location"]'
_LDJSON_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


_MONTHS = {
    m: i for i, m in enumerate(
        ("ianuarie", "februarie", "martie", "aprilie", "mai", "iunie", "iulie",
         "august", "septembrie", "octombrie", "noiembrie", "decembrie"), 1)
}
_DATE_RE = re.compile(r"(\d{1,2}) ([a-z]+)(?: (\d{4}))?")


def parse_date(text: str, today: date | None = None) -> datetime | None:
    """'azi 10:05', 'ieri 14:03', '4 octombrie', '12 martie 2025' -> datetime."""
    today = today or date.today()
    t = fold(text)
    if t.startswith(("azi", "astazi")):
        return datetime.combine(today, datetime.min.time())
    if t.startswith("ieri"):
        return datetime.combine(today - timedelta(days=1), datetime.min.time())
    m = _DATE_RE.search(t)
    if not m or m.group(2) not in _MONTHS:
        return None
    year = int(m.group(3)) if m.group(3) else today.year
    try:
        d = date(year, _MONTHS[m.group(2)], int(m.group(1)))
    except ValueError:
        return None
    if d > today and not m.group(3):  # '28 decembrie' read in January
        d = d.replace(year=year - 1)
    return datetime.combine(d, datetime.min.time())


def _text(node) -> str:
    return squash_ws(node.get_text(" ")) if node else ""


class Publi24:
    name = "publi24"
    hosts = ("publi24.ro",)

    def parse_card(self, c) -> RawListing | None:
        a = c.select_one("h2 a[href]") or c.find("a", href=True)
        if not a:
            return None
        title = _text(c.select_one("h2, .article-title")) or _text(a)
        price = None
        pnode = c.select_one(".article-price .new-price") or c.select_one(".article-price")
        if pnode:
            price = find_price_text(_text(pnode))
        location = ""
        for p in c.select("p"):
            if p.select_one(_LOCATION_ICON):
                location = unquote_plus(_text(p))
                break
        return RawListing(
            site=self.name,
            url=urljoin(BASE, a["href"]),
            title=title[:160],
            description=_text(c.select_one(".article-description")),
            price_value=price[0] if price else "",
            price_currency=price[1] if price else "",
            location_text=location,
            district=location.split(",")[0].strip() if location.count(",") >= 2 else "",
            posted_at=parse_date(_text(c.select_one(".article-date"))),
        )

    @staticmethod
    def _read_attributes(item: RawListing, html: str) -> None:
        """The ad page's attribute list: 'Incalzire centrala proprie',
        'Locuri parcare 1', 'Numar camere 2 camere'..."""
        attrs = [
            squash_ws(a.get_text(" ", strip=True))
            for a in BeautifulSoup(html, "html.parser").select(".attribute-item")
        ]
        if not attrs:
            return
        item.extra_text = (item.extra_text + " | " + "; ".join(attrs)).strip(" |")
        for a in attrs:
            f = fold(a)
            m = re.match(r"locuri parcare (\d+)", f)
            if m and int(m.group(1)) > 0:
                item.parking_hint = True
            m = re.match(r"numar camere (\d+)", f)
            if m and not item.rooms:
                item.rooms = int(m.group(1))
            m = re.match(r"suprafata utila ([\d.]+)", f)
            if m and not item.surface_m2:
                with suppress(ValueError):
                    item.surface_m2 = float(m.group(1))

    def search_rentals(self, loc: Locality, filters: Filters, pages: int) -> SiteResult:
        url = f"{BASE}/anunturi/imobiliare/de-inchiriat/apartamente/{loc.publi24_path()}/"
        res = SiteResult(site=self.name, url=url)
        status, html = session().fetch(url)
        if status != 200:
            res.status = status_for(status)
            return res
        cards = BeautifulSoup(html, "html.parser").select("div.article-item")
        res.items = [r for r in map(self.parse_card, cards) if r]
        res.keep_local(loc)
        if not res.items and not cards:
            res.status = "not-found"
        return res

    def fetch_detail(self, item: RawListing) -> RawListing:
        html = session().get_text(item.url)
        self._read_attributes(item, html or "")
        m = _LDJSON_RE.search(html or "")
        if not m:
            return item
        try:
            d = json.loads(m.group(1), strict=False)
        except json.JSONDecodeError:
            return item
        if isinstance(d, list):
            d = next((x for x in d if isinstance(x, dict) and x.get("description")), {})
        desc = squash_ws(str(d.get("description") or ""))
        if len(desc) > len(item.description):
            item.description = desc
        if not item.title:
            item.title = squash_ws(str(d.get("name") or ""))
        images = [
            im.get("contentUrl") for im in d.get("image") or [] if isinstance(im, dict)
        ]
        if any(images):
            item.images = [u for u in images if u][:8]
        offers = d.get("offers") or {}
        if not item.price_value and isinstance(offers, dict) and offers.get("price"):
            item.price_value = str(offers["price"])
            item.price_currency = str(offers.get("priceCurrency") or "")
        return item
