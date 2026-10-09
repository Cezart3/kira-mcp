"""Against the real sites. Skipped unless KIRA_LIVE=1 — run before a release,
and whenever a site may have changed its pages."""
import os

import pytest

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("KIRA_LIVE") != "1", reason="set KIRA_LIVE=1"),
]


@pytest.fixture(autouse=True)
def offline():  # override conftest: hit the network
    from kira_mcp.sites import SITES

    SITES["storia"]._paths.clear()  # type: ignore[attr-defined]


@pytest.mark.parametrize("city", ["Cluj-Napoca", "Bucuresti", "Piatra Neamt", "Floresti"])
def test_every_site_answers(city):
    from kira_mcp.search import search_rentals

    res = search_rentals(city, pages=1, limit=5)
    by_site = {s["site"]: s for s in res["sources"]}
    assert by_site["storia"]["status"] == "ok" and by_site["storia"]["fetched"] > 0
    assert sum(s["fetched"] for s in res["sources"]) > 10
    assert res["results"], res


def test_detail_pages_parse():
    from kira_mcp.search import get_listing, search_rentals

    for site in ("storia", "publi24", "lajumate"):
        res = search_rentals("Cluj-Napoca", pages=1, limit=5, sites=[site])
        assert res["results"], site
        d = get_listing(res["results"][0]["url"])
        assert d["title"] and d["description"], (site, d)
