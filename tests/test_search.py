"""End-to-end search over the fixture sites."""
from datetime import date

import pytest

from kira_mcp import search
from kira_mcp.sites.publi24 import parse_date


def urls(res):
    return [r["url"] for r in res["results"]]


def test_search_merges_sites_and_drops_non_rentals():
    res = search.search_rentals("Cluj-Napoca")
    assert res["locality"] == {"name": "Cluj-Napoca", "county": "Cluj", "kind": "municipiu"}
    assert {s["site"]: s["status"] for s in res["sources"]} == {
        "storia": "ok", "publi24": "ok", "lajumate": "ok"
    }
    assert res["dropped_non_rentals"] == {"short-stay": 1, "parking-only": 1}
    # Floresti is a different locality: publi24 fell back to it, we filter it out
    assert not any("x2.html" in u for u in urls(res))
    assert "olx" in res["not_searched"]


def test_cross_posted_flat_is_merged():
    res = search.search_rentals("Cluj-Napoca", rooms=[2])
    assert len(res["results"]) == 1
    only = res["results"][0]
    sites = {only["site"]} | {u.split("/")[2].removeprefix("www.") for u in only["also_listed_on"]}
    assert sites == {"storia", "lajumate.ro"} or sites == {"lajumate", "storia.ro"}


def test_facts_are_extracted_and_contacts_redacted():
    res = search.search_rentals("Cluj-Napoca", sites=["storia"])
    by_title = {r["title"]: r for r in res["results"]}
    zorilor = by_title["Ap 2 camere Zorilor, centrala proprie"]
    assert zorilor["heating"] == "centrala_proprie"
    assert zorilor["parking"] == "included"  # storia PARKING tag
    assert zorilor["owner"] == "private"
    assert "0740" not in zorilor["snippet"]
    marasti = by_title["Garsoniera Marasti"]
    assert marasti["price_eur"] == 300.0  # 1500 RON
    assert marasti["heating"] == "termoficare"


def test_filters():
    res = search.search_rentals("Cluj-Napoca", max_price=400)
    assert all(r["price_eur"] <= 400 for r in res["results"])
    res = search.search_rentals("Cluj-Napoca", heating="termoficare")
    assert [r["title"] for r in res["results"]] == ["Garsoniera Marasti"]
    res = search.search_rentals("Cluj-Napoca", owner_only=True)
    assert all(r.get("owner") == "private" for r in res["results"])
    res = search.search_rentals("Cluj-Napoca", keywords="gheorgheni")
    assert len(res["results"]) == 1 and res["results"][0]["site"] == "publi24"


def test_storia_gets_server_side_filters(offline):
    session, _ = offline
    search.search_rentals("Cluj-Napoca", max_price=500, rooms=[1, 4], sites=["storia"])
    params = session.calls[0][1]
    assert params["priceMax"] == 500
    assert params["roomsNumber"] == "[ONE,FOUR,FIVE,SIX]"


def test_parking_filter_reads_full_ad_of_undecided(offline):
    session, _ = offline
    res = search.search_rentals("Cluj-Napoca", parking=["none"], sites=["publi24"])
    assert [r["parking"] for r in res["results"]] == ["none"]
    res = search.search_rentals("Cluj-Napoca", parking=["included"], sites=["lajumate"])
    # lajumate's flat says nothing about parking -> its full ad was fetched
    assert any("/ad/" in url for url, _ in session.calls)
    assert any("full text" in n for n in res["notes"])


def test_near_sorts_by_walking_distance(offline):
    _, gc = offline
    res = search.search_rentals("Cluj-Napoca", near="UMF", sort="distance")
    located = [r for r in res["results"] if "distance" in r]
    assert located, res
    walks = [r["distance"]["walk_minutes"] for r in located]
    assert walks == sorted(walks)
    assert located[0]["distance"]["precision"] == "street"
    assert "umf" in [q.lower() for q in gc.lookups]


def test_max_walk_drops_far_keeps_unplaceable_last():
    res = search.search_rentals("Cluj-Napoca", near="UMF", max_walk_minutes=25)
    located = [r for r in res["results"] if "distance" in r]
    assert located and all(r["distance"]["walk_minutes"] <= 25 for r in located)
    seen_unlocated = False
    for r in res["results"]:
        seen_unlocated |= "distance" not in r
        assert not (seen_unlocated and "distance" in r), "located listings come first"
    res = search.search_rentals("Cluj-Napoca", near="UMF", max_walk_minutes=1)
    assert all("distance" not in r for r in res["results"])
    assert any("more than 1 minutes" in n for n in res["notes"])


def test_geocode_budget_goes_to_shared_places_first(offline, monkeypatch):
    _, gc = offline
    monkeypatch.setattr(search, "GEOCODE_BUDGET", 1)
    search.search_rentals("Cluj-Napoca", near="UMF", sort="distance")
    # 'umf' for the origin, then a single lookup for listings
    assert len(gc.lookups) == 2


def test_unknown_near_is_reported():
    res = search.search_rentals("Cluj-Napoca", near="Atlantida")
    assert any("Could not place" in n for n in res["notes"])


def test_locality_without_ads_reports_not_found():
    res = search.search_rentals("Sibiu")
    assert res["matched"] == 0
    assert {s["status"] for s in res["sources"]} == {"not-found"}


def test_bad_arguments():
    with pytest.raises(ValueError):
        search.search_rentals("Cluj-Napoca", heating="lemne")
    with pytest.raises(ValueError):
        search.search_rentals("Cluj-Napoca", parking=["maybe"])
    with pytest.raises(ValueError, match="No Romanian locality"):
        search.search_rentals("Atlantida")


def test_get_listing_reads_full_ad():
    d = search.get_listing("https://www.storia.ro/ro/oferta/ap-2-camere-zorilor-test-ID1")
    assert d["parking"] == "included"
    assert d["heating"] == "centrala_proprie"
    assert d["price_eur"] == 450.0
    assert len(d["images"]) == 2
    assert "0740" not in d["description"]
    with pytest.raises(ValueError):
        search.get_listing("https://www.olx.ro/d/oferta/x")


def test_publi24_dates():
    today = date(2026, 1, 10)
    assert parse_date("azi 10:05", today).date() == today
    assert parse_date("ieri 14:03", today).date() == date(2026, 1, 9)
    assert parse_date("4 ianuarie", today).date() == date(2026, 1, 4)
    assert parse_date("28 decembrie", today).date() == date(2025, 12, 28)
    assert parse_date("12 martie 2024", today).date() == date(2024, 3, 12)
    assert parse_date("", today) is None


def test_ads_from_neighbouring_localities_are_skipped():
    from kira_mcp.localities import resolve
    from kira_mcp.sites.base import RawListing, SiteResult

    res = SiteResult(site="storia", items=[
        RawListing(site="storia", url="a", title="", location_text="Hipodrom, Sibiu, Sibiu"),
        RawListing(site="storia", url="b", title="", location_text="Selimbar, Sibiu"),
        RawListing(site="storia", url="c", title="", location_text=""),
    ])
    res.keep_local(resolve("Selimbar"))
    assert [r.url for r in res.items] == ["b", "c"] and res.elsewhere == 1


def test_title_neighbourhood_beats_default_pin():
    from kira_mcp.sites.base import RawListing

    def li(title, district="", street="", desc=""):
        raw = RawListing(site="storia", url=title, title=title, district=district,
                         street=street, description=desc)
        return search.normalize(raw)

    pinned = li("Studio bloc nou Marasti", "Centru", "Piata Unirii")
    right = li("Ap 2 camere Zorilor", "Zorilor", "Strada Lunii")
    bare = li("Apartament 2 camere", desc="situat in zona Marasti, aproape de piata")
    others = [li("x", "Marasti"), li("y", "Centru")]
    items = [pinned, right, bare, *others]
    search._place_by_text(items, {li.raw.district for li in items})
    assert (pinned.raw.district, pinned.street) == ("Marasti", "")
    assert (right.raw.district, right.street) == ("Zorilor", "Strada Lunii")
    assert bare.raw.district == "Marasti"


def test_full_text_can_reveal_a_sale_ad(monkeypatch):
    from kira_mcp.sites import SITES

    def detail(item):
        item.description = "Apartament de 2 camere, de vanzare. Pret: 74.999 EUR"
        return item

    monkeypatch.setattr(SITES["lajumate"], "fetch_detail", detail)
    res = search.search_rentals("Cluj-Napoca", heating="centrala_proprie", sites=["lajumate"])
    assert res["results"] == []
    assert res["dropped_non_rentals"].get("sale-ad") == 1
