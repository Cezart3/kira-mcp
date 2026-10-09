"""Extractor rules, ported with their tests from KiraImobiliare."""
from kira_mcp.extract import (
    Heating,
    Parking,
    SpotKind,
    classify_heating,
    classify_parking,
    classify_parking_spot,
    drop_reason,
    extract_floor,
    extract_rooms,
    extract_street,
    extract_surface,
    find_price_text,
    has_house_number,
    looks_like_parking_only,
    to_eur,
)

# --- parking --------------------------------------------------------------------


def test_parking_included():
    s, c = classify_parking("Apartament cu loc de parcare inclus în preț")
    assert s == Parking.INCLUDED and c == 3


def test_parking_included_subteran():
    assert classify_parking("2 camere, parcare subterană")[0] == Parking.INCLUDED


def test_parking_area_possible():
    assert classify_parking("Posibilitate de parcare în zonă")[0] == Parking.AREA_POSSIBLE


def test_parking_area_free_unmarked():
    s, _ = classify_parking("parcare la liber, locuri nemarcate în fața blocului")
    assert s == Parking.AREA_POSSIBLE


def test_parking_extra_cost_is_area():
    s, _ = classify_parking("loc de parcare contra cost în subteran")
    assert s == Parking.AREA_POSSIBLE


def test_parking_none():
    assert classify_parking("apartament fără loc de parcare")[0] == Parking.NONE


def test_parking_both_options_ad_is_area():
    s, _ = classify_parking(
        "chirie 400 eur (fără loc de parcare). chirie 450 eur (cu loc de parcare inclus)"
    )
    assert s == Parking.AREA_POSSIBLE
    s, _ = classify_parking("2500 lei cu parcare supraterană inclusă, 2300 lei fără parcare")
    assert s == Parking.AREA_POSSIBLE


def test_parking_no_own_spot_stays_none():
    assert classify_parking("apartamentul nu dispune de loc de parcare propriu")[0] == Parking.NONE
    assert classify_parking("prețul nu include locul de parcare")[0] == Parking.NONE


def test_parking_unknown():
    s, c = classify_parking("Apartament 2 camere lângă parc")  # 'parc' != 'parcare'
    assert s == Parking.UNKNOWN and c == 0


def test_parking_structured_hint_upgrades():
    s, c = classify_parking("Apartament frumos", structured_hint=True)
    assert s == Parking.INCLUDED and c >= 2


def test_parking_include_multiword_gap():
    s, _ = classify_parking("Pretul include si un loc de parcare in fata blocului")
    assert s == Parking.INCLUDED


def test_parking_dispune_de_loc():
    s, _ = classify_parking("Apartamentul dispune de un loc de parcare langa bloc")
    assert s == Parking.INCLUDED


def test_parking_area_plus_no_own_spot_stays_area():
    s, _ = classify_parking(
        "Exista posibilitate de parcare in zona, insa apartamentul nu dispune "
        "de loc propriu de parcare"
    )
    assert s == Parking.AREA_POSSIBLE


def test_parking_spot_kind():
    kind, numbered = classify_parking_spot("Închiriez loc parcare subteran nr. 24")
    assert kind == SpotKind.SUBTERAN and numbered


def test_parking_only_title():
    assert looks_like_parking_only("Închiriez loc de parcare Mărăști")
    assert not looks_like_parking_only("Apartament 2 camere cu loc de parcare")


# --- heating --------------------------------------------------------------------


def test_heating_proprie():
    assert classify_heating("centrală termică proprie") == Heating.CENTRALA_PROPRIE


def test_heating_termoficare():
    assert classify_heating("încălzire prin termoficare") == Heating.TERMOFICARE


def test_heating_pe_bloc():
    assert classify_heating("căldură de la bloc, apă caldă") == Heating.TERMOFICARE


def test_heating_centralizat():
    assert classify_heating("încălzire centralizată RADET") == Heating.TERMOFICARE


def test_heating_zona_centrala_not_heating():
    assert classify_heating("apartament în zonă centrală, lângă parc") == Heating.UNKNOWN


def test_heating_ultracentral_with_centrala():
    assert classify_heating("ultracentral, cu centrală proprie") == Heating.CENTRALA_PROPRIE


def test_heating_bare_centrala():
    assert classify_heating("mobilat, utilat, centrală, AC") == Heating.CENTRALA_PROPRIE


def test_heating_unknown():
    assert classify_heating("apartament luminos cu balcon") == Heating.UNKNOWN


# --- price ----------------------------------------------------------------------


def test_price_basic():
    assert to_eur("450 €") == 450.0
    assert to_eur("2.500 lei", ron_per_eur=5.0) == 500.0
    assert to_eur("1500", currency_hint="RON", ron_per_eur=5.0) == 300.0
    assert to_eur("1.200 EUR") == 1200.0
    assert to_eur("la cerere") is None


def test_price_separators():
    assert to_eur("906.29 EUR") == 906.3
    assert to_eur("1,000", "EUR") == 1000
    assert to_eur("906,29 eur") == 906.3
    assert to_eur("1.234.567 eur") == 1234567
    assert to_eur("2 000 lei") == 400


def test_find_price_text_ignores_glued_counters():
    def parse(s):
        f = find_price_text(s)
        return to_eur(f[0], f[1]) if f else None

    assert parse("04 1 500 EUR") == 1500
    assert parse("05 250 EUR") == 250
    assert parse("Promovat 3 24 Apartament 2 cam 550 EUR") == 550
    assert parse("fara pret") is None


# --- rooms / surface / floor / street ------------------------------------------


def test_rooms_surface_floor():
    assert extract_rooms("Apartament 2 camere decomandat") == 2
    assert extract_rooms("Garsonieră confort 1") == 1
    assert extract_rooms("apartament cu doua camere") == 2
    assert extract_surface("suprafață 54 mp utili") == 54.0
    assert extract_surface("5 mp") is None
    assert extract_floor("etaj 3 din 4") == "3"


def test_street():
    s = extract_street("Inchiriez apartament str. Fabricii nr. 105, zona Iris")
    assert "fabricii" in s.lower() and has_house_number(s)
    assert extract_street("strada Memorandumului compus din 2 camere").lower() == (
        "strada memorandumului"
    )
    assert extract_street("apartament frumos in cartier linistit") == ""


# --- ad type --------------------------------------------------------------------


def test_drop_reason():
    assert drop_reason("Inchiriez loc de parcare", "") == "parking-only"
    assert drop_reason("De vanzare apartament 2 camere", "") == "sale-ad"
    assert drop_reason("Apartament centru", "regim hotelier, 150 lei pe noapte") == "short-stay"
    assert drop_reason("Apartament 2 camere", "contract minim 1 an") is None
