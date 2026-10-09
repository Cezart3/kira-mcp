"""Structured fields on the ad pages, beyond the free text."""
import json

from kira_mcp import http
from kira_mcp.extract import Heating, classify_heating
from kira_mcp.sites.base import RawListing
from kira_mcp.sites.lajumate import Lajumate
from kira_mcp.sites.publi24 import Publi24
from kira_mcp.sites.storia import Storia


class OnePage:
    def __init__(self, html: str):
        self.html = html

    def fetch(self, url, params=None):
        return 200, self.html

    def get_text(self, url, params=None):
        return self.html


def test_storia_heating_enum_without_label(monkeypatch):
    ad = {"props": {"pageProps": {"ad": {
        "description": "Apartament luminos.",
        "characteristics": [{"key": "heating", "value": "urban", "localizedValue": ""}],
    }}}}
    html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(ad)}</script>'
    monkeypatch.setattr(http, "_session", OnePage(html))
    item = Storia().fetch_detail(RawListing(site="storia", url="u"))
    assert classify_heating(item.extra_text) == Heating.TERMOFICARE


def test_publi24_attribute_list(monkeypatch):
    html = """<ul>
      <li class="attribute-item">Numar camere 2 camere</li>
      <li class="attribute-item">Suprafata utila 58.6 m 2</li>
      <li class="attribute-item">Incalzire centrala proprie</li>
      <li class="attribute-item">Locuri parcare 1</li>
    </ul>"""
    monkeypatch.setattr(http, "_session", OnePage(html))
    item = Publi24().fetch_detail(RawListing(site="publi24", url="u"))
    assert item.rooms == 2 and item.surface_m2 == 58.6
    assert item.parking_hint
    assert classify_heating(item.extra_text) == Heating.CENTRALA_PROPRIE


def test_lajumate_seller_type():
    ad = {"id": 1, "title": "Ap 2 camere", "fields": [
        {"name": "person_type", "field_key": "Tip Vanzator", "value": "Persoană fizică"}
    ]}
    assert Lajumate().to_raw(ad).private_owner is True
    ad["fields"][0]["value"] = "Persoană juridică"
    assert Lajumate().to_raw(ad).private_owner is False
