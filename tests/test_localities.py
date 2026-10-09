import pytest

from kira_mcp.localities import LocalityNotFound, all_localities, find, resolve
from kira_mcp.text import redact_personal, slugify


def test_dataset_covers_romania():
    locs = all_localities()
    assert len(locs) > 3000
    assert len({loc.county for loc in locs}) == 42  # 41 counties + București
    assert {loc.kind for loc in locs} == {"municipiu", "oras", "comuna"}


def test_resolve_diacritics_and_aliases():
    assert resolve("Iasi").name == "Iași"
    assert resolve("targu mures").name == "Târgu Mureș"
    assert resolve("Tg. Mures").name == "Târgu Mureș"
    assert resolve("cluj").name == "Cluj-Napoca"
    assert resolve("Bucharest").name == "București"


def test_ambiguous_name_prefers_largest_unless_county_given():
    assert resolve("Florești").county == "Cluj"
    assert resolve("Floresti", county="Prahova").county == "Prahova"
    assert resolve("Floresti, Prahova").county == "Prahova"
    assert resolve("Floresti (judetul Prahova)").county == "Prahova"
    assert len(find("Floresti")) >= 3


def test_unknown_suggests():
    with pytest.raises(LocalityNotFound) as e:
        resolve("Brasovv")
    assert any(s.name == "Brașov" for s in e.value.suggestions)


def test_site_paths():
    cj = resolve("Cluj-Napoca")
    assert cj.storia_paths()[0] == "cluj/cluj--napoca"
    assert cj.publi24_path() == "cluj/cluj-napoca"
    assert cj.lajumate_path() == "cluj/cluj-napoca"
    assert resolve("Targu Mures").storia_paths()[0] == "mures/targu-mures"
    assert resolve("Bistrita").storia_paths()[0] == "bistrita--nasaud/bistrita"
    assert resolve("Drobeta-Turnu Severin").storia_paths()[0] == "mehedinti/drobeta--turnu-severin"
    assert "neamt/piatra--neamt" in resolve("Piatra Neamt").storia_paths()
    b = resolve("Bucuresti")
    assert b.storia_paths() == ["bucuresti"]
    assert b.publi24_path() == "bucuresti/bucuresti"
    assert b.lajumate_path() == "bucuresti-ilfov/bucuresti"
    assert resolve("Voluntari").lajumate_path() == "bucuresti-ilfov/voluntari"


def test_location_matching_ignores_hyphens_and_diacritics():
    pn = resolve("Piatra Neamt")
    assert pn.matches("Centru, Piatra Neamt, Neamt")
    assert resolve("Cluj-Napoca").matches("Manastur, Cluj-Napoca, Cluj")
    assert not resolve("Cluj-Napoca").matches("Floresti, Cluj")


def test_text_helpers():
    assert slugify("Târgu Mureș") == "targu-mures"
    out = redact_personal("Sunati la 0740 123 456 sau +40 264 123 456, mail a.b@x.ro")
    assert "0740" not in out and "264" not in out and "@" not in out
