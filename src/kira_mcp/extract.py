"""Facts from Romanian listing text: heating, parking, price, rooms, surface, floor, street.

Ported from KiraImobiliare, where these rules were tuned on real ads. All
matching runs on diacritics-folded lowercase text (see text.fold).
"""
import re
from enum import StrEnum

from kira_mcp.text import fold


class Heating(StrEnum):
    CENTRALA_PROPRIE = "centrala_proprie"  # own gas boiler
    TERMOFICARE = "termoficare"            # district / building-level heating
    UNKNOWN = "unknown"


class Parking(StrEnum):
    INCLUDED = "included"                # parking/garage part of the rental
    LIKELY_INCLUDED = "likely_included"  # parking mentioned, not explicit
    AREA_POSSIBLE = "area_possible"      # street/free parking nearby, or at extra cost
    NONE = "none"                        # explicitly without parking
    UNKNOWN = "unknown"


class SpotKind(StrEnum):
    SUBTERAN = "subteran"
    GARAJ = "garaj"
    EXTERIOR = "exterior"
    UNKNOWN = "unknown"


# --- heating ------------------------------------------------------------------
# 'termoficare generala / pe bloc' is NOT an own boiler.

# phrases where 'central(a)' refers to LOCATION or is ambiguous — removed first
_AMBIGUOUS = re.compile(
    r"zona \w{0,12}\s?centrala|pozitie centrala|amplasament central[a]?|"
    r"ultracentral[a]?|parte centrala|incalzire centrala\b(?!\s*propri)"
)
_TERMOFICARE = re.compile(
    r"termoficare|incalzire centralizat|sistem centralizat|"
    r"centrala (?:termica )?de cartier|punct termic|"
    r"\bradet\b|termoenergetica|\bcolterm\b|\bcet\b|"
    r"(?:incalzire|caldura|agent termic|apa calda)\s+(?:de )?la (?:bloc|oras|retea)|"
    r"centrala (?:pe|de) (?:bloc|scara)|centrala comuna|\bpe bloc\b"
)
_PROPRIE_EXPLICIT = re.compile(
    r"centrala (?:termica )?(?:propri|individual)|ct propri|"
    r"centrala (?:de |pe )?apartament|microcentrala|incalzire individual"
)
_PROPRIE_ANY = re.compile(
    r"centrala (?:termica )?(?:propri|individual)|ct propri|"
    r"centrala (?:de |pe )?apartament|microcentrala|incalzire individual|"
    r"centrala (?:pe|de) gaz|centrala noua|\bcentrala termica\b|\bcentrala\b|\bct\b"
)


def classify_heating(text: str) -> Heating:
    t = fold(" ".join((text or "").split()))
    if not t:
        return Heating.UNKNOWN
    t = _AMBIGUOUS.sub(" ", t)
    if _TERMOFICARE.search(t) and not _PROPRIE_EXPLICIT.search(t):
        return Heating.TERMOFICARE
    if _PROPRIE_ANY.search(t):
        return Heating.CENTRALA_PROPRIE
    return Heating.UNKNOWN


# --- parking ------------------------------------------------------------------

_NEG = r"nu (?:are|exista|include|detine|dispune de|beneficiaza de)"
_NONE = [
    r"fara (?:loc de )?parcare",
    rf"{_NEG} (?:un )?(?:loc(?:ul)? (?:de |propriu )?)?parcare",
    rf"{_NEG} loc (?:propriu )?(?:de )?parcare",
    r"nu (?:are|detine) (?:loc de )?parcare propri",
]
_EXTRA_COST = [
    r"parcare contra cost",
    r"parcare cu plata",
    r"parcare optionala?",
    r"(?:loc de )?parcare .{0,14}(?:cost suplimentar|extra cost|se plateste)",
]
_STRONG = [
    r"(?:loc(?:ul)? de )?parcare inclus",
    r"garaj inclus",
    r"loc de parcare propriu",
    r"parcare propri[ea]",
    r"includ[ae].{0,30}parcare",
    r"pretul include.{0,30}(?:loc de )?parcare",
    r"(?:loc de )?parcare.{0,20}inclus(?:a|e)?\b",
    r"(?:dispune de|are|beneficiaza de|cu propriul?).{0,20}(?:loc de parcare|garaj)",
    r"cu loc de parcare",
    r"cu garaj",
    r"loc (?:de )?parcare subteran",
    r"parcare subteran",
    r"(?:loc de )?parcare (?:in|la) pret",
]
_AREA = [
    r"posibilitat\w* (?:de )?parcare",
    r"posibiliate de parcare",  # common misspelling seen in real ads
    r"parcare (?:in|prin) zona",
    r"parcare pe strada",
    r"parcare stradala",
    r"parcare la liber",
    r"locuri? nemarcat",
    r"parcare nemarcat",
    r"se gaseste parcare",
    r"parcare gratuita in zona",
]
_WEAK = [r"loc de parcare", r"\bgaraj\b", r"parcare\s*\+"]
_ANY = re.compile(r"parcare|garaj")
_INCLUS = re.compile(r"inclus")
# a genuine, non-negated "parcare ... inclus(a)" — catches two-tier ads
# ("2500 lei cu parcare inclusa / 2300 lei fara"): parking obtainable, not in base price
_INCL_PHRASE = re.compile(
    r"(?<!fara )(?<!include )(?:loc(?:ul)? de )?parcare\w* "
    r"(?:supraterana |subterana )?inclus(?:a|e)?"
)

_NONE_RE = [re.compile(p) for p in _NONE]
_EXTRA_RE = [re.compile(p) for p in _EXTRA_COST]
_STRONG_RE = [re.compile(p) for p in _STRONG]
_AREA_RE = [re.compile(p) for p in _AREA]
_WEAK_RE = [re.compile(p) for p in _WEAK]


def classify_parking(text: str, structured_hint: bool = False) -> tuple[Parking, int]:
    """Return (status, confidence 0-3). structured_hint: the site tagged the ad
    with a GARAGE/PARKING attribute."""
    t = fold(" ".join((text or "").split()))
    has_area = any(r.search(t) for r in _AREA_RE)
    both_options = any(r.search(t) for r in _NONE_RE) and _INCL_PHRASE.search(t) is not None
    if not t:
        status, conf = Parking.UNKNOWN, 0
    elif both_options:
        status, conf = Parking.AREA_POSSIBLE, 2
    elif any(r.search(t) for r in _NONE_RE) and not has_area:
        status, conf = Parking.NONE, 3
    elif any(r.search(t) for r in _EXTRA_RE) and not _INCLUS.search(t):
        status, conf = Parking.AREA_POSSIBLE, 2
    elif any(r.search(t) for r in _STRONG_RE):
        status, conf = Parking.INCLUDED, 3
    elif has_area:
        status, conf = Parking.AREA_POSSIBLE, 2
    elif any(r.search(t) for r in _WEAK_RE):
        status, conf = Parking.LIKELY_INCLUDED, 2
    elif _ANY.search(t):
        status, conf = Parking.LIKELY_INCLUDED, 1
    else:
        status, conf = Parking.UNKNOWN, 0

    if structured_hint and status in (
        Parking.UNKNOWN, Parking.LIKELY_INCLUDED, Parking.AREA_POSSIBLE
    ):
        status, conf = Parking.INCLUDED, max(conf, 2)
    return status, conf


_KIND_SUBTERAN = re.compile(r"subteran|demisol|subsol")
_KIND_GARAJ = re.compile(r"\bgaraj\b")
_KIND_EXTERIOR = re.compile(r"exterior|suprateran|aer liber|in curte|curte interioara")
_NUMBERED = re.compile(r"(?:loc(?:ul)?|parcare)\D{0,12}nr\.?\s*\d+|loc(?:ul)? \d+|numerotat")

PARKING_ONLY_TITLE = re.compile(
    r"(?:inchiriez|ofer|dau spre inchiriere)?\s*(?:loc(?:ul)? de parcare|loc parcare|"
    r"parcare subterana|garaj)\b"
)
APARTMENT_WORDS = re.compile(r"apartament|garsonier|\bcamere\b|\bcasa\b|\bvila\b|penthouse")


def classify_parking_spot(text: str) -> tuple[SpotKind, bool]:
    """For a standalone parking listing: (kind, is_numbered)."""
    t = fold(" ".join((text or "").split()))
    if _KIND_SUBTERAN.search(t):
        kind = SpotKind.SUBTERAN
    elif _KIND_GARAJ.search(t):
        kind = SpotKind.GARAJ
    elif _KIND_EXTERIOR.search(t):
        kind = SpotKind.EXTERIOR
    else:
        kind = SpotKind.UNKNOWN
    return kind, bool(_NUMBERED.search(t))


def looks_like_parking_only(title: str) -> bool:
    """True when a title is a standalone parking/garage rental (not an apartment)."""
    t = fold(title or "")
    return bool(PARKING_ONLY_TITLE.search(t)) and not APARTMENT_WORDS.search(t)


# --- price --------------------------------------------------------------------

_NUM_CLEAN_RE = re.compile(r"[^\d,\.]")
# Anchored: thousands groups are exactly 3 digits and the number can't start
# with 0, so badge counters glued in front of a price aren't swallowed
# ("4 1 500 EUR" -> 1500, not 41500).
PRICE_TEXT_RE = re.compile(
    r"(?<![\d.,])([1-9]\d{0,2}(?:[ .]\d{3})+|[1-9]\d*)\s*(€|(?:eur(?:o)?|lei|ron)\b)",
    re.I,
)


def find_price_text(text: str) -> tuple[str, str] | None:
    """Extract (value, currency) from free text, or None."""
    m = PRICE_TEXT_RE.search(text or "")
    if not m:
        return None
    return m.group(1).strip(), m.group(2)


def _normalize_number(num: str) -> str:
    """'1.500'/'1,000' are thousands (3-digit group), '906.29'/'906,29' decimals."""
    if "," in num and "." in num:
        if num.rfind(",") > num.rfind("."):
            return num.replace(".", "").replace(",", ".")
        return num.replace(",", "")
    for sep in (",", "."):
        if sep in num:
            int_part, _, frac = num.rpartition(sep)
            if len(frac) == 3 and int_part:
                return num.replace(sep, "")
            return int_part.replace(sep, "") + "." + frac
    return num


def to_eur(raw: str | None, currency_hint: str = "", ron_per_eur: float = 5.0) -> float | None:
    """Parse a price string ('1.500 lei', '906.29 EUR', '450 €') into EUR."""
    if raw is None:
        return None
    s = str(raw).lower().replace("\xa0", " ")
    num = _NUM_CLEAN_RE.sub("", s)
    if not num:
        return None
    try:
        val = float(_normalize_number(num))
    except ValueError:
        return None

    is_ron = ("lei" in s or "ron" in s) and "eur" not in s and "€" not in s
    hint = (currency_hint or "").upper()
    if hint in ("RON", "LEI"):
        is_ron = True
    if hint == "EUR" or "€" in s or "eur" in s:
        is_ron = False
    if is_ron:
        val = val / ron_per_eur
    return round(val, 1)


# --- rooms / surface / floor ----------------------------------------------------

_GARSONIERA = re.compile(r"\bgarsonier")
_N_CAMERE = re.compile(r"\b(\d)\s*(?:camere|camera|cam\b)")
_WORD_CAMERE = [
    (re.compile(r"\bo camera\b"), 1),
    (re.compile(r"\bdoua camere\b"), 2),
    (re.compile(r"\btrei camere\b"), 3),
    (re.compile(r"\bpatru camere\b"), 4),
]
_SURFACE = re.compile(r"(\d{2,3}(?:[.,]\d)?)\s*(?:mp\b|m2\b|m²|metri patrati)")
_FLOOR = re.compile(r"etaj(?:ul)?\s*:?\s*(parter|demisol|mansarda|\d{1,2})")


def extract_rooms(text: str) -> int | None:
    t = fold(text)
    if _GARSONIERA.search(t):
        return 1
    m = _N_CAMERE.search(t)
    if m and 1 <= int(m.group(1)) <= 6:
        return int(m.group(1))
    for rx, n in _WORD_CAMERE:
        if rx.search(t):
            return n
    return None


def extract_surface(text: str) -> float | None:
    m = _SURFACE.search(fold(text))
    if not m:
        return None
    val = float(m.group(1).replace(",", "."))
    return val if 10 <= val <= 400 else None


def extract_floor(text: str) -> str | None:
    m = _FLOOR.search(fold(text))
    return m.group(1) if m else None


# --- street -------------------------------------------------------------------

STREET_RE = re.compile(
    r"\b(?:str\.?|strada|b-?dul|bulevardul|bd\.?|calea|aleea|pia[țt]a|splaiul|"
    r"[șs]oseaua|[șs]os\.)\s+"
    r"([\wăâîșțĂÂÎȘȚ\.\-]+(?:\s+[\wăâîșțĂÂÎȘȚ0-9\.\-]+){0,2})",
    re.UNICODE | re.IGNORECASE,
)
# tokens that signal the street name ended (verbs / filler leaking into the match)
_STOPWORDS = {
    "inchiriez", "inchiriere", "salut", "se", "va", "oferim", "ofer", "compus",
    "este", "aproape", "nou", "pf", "proprietar", "recomandat", "pentru",
    "apartamentul", "caut", "coleg", "colega", "face", "in", "din", "zona",
    "cartier", "cartierul", "pret", "mobilat", "modern", "garsoniera",
    "apartament", "ap", "bloc", "etaj", "situat", "situata", "chiar", "foarte",
    "complet", "decomandat", "semidecomandat", "renovat", "lux", "superb",
}


def _clean_street(s: str, extra_stops: frozenset[str]) -> str:
    toks = s.strip().rstrip(".,;:- ").split()
    out: list[str] = []
    i = 0
    while i < len(toks):
        base = fold(toks[i].strip(".,;:"))
        if base in ("nr", "numar", "numarul"):
            # keep the house number itself ('str. Fabricii nr. 105' -> '... 105')
            nxt = toks[i + 1].strip(".,;:") if i + 1 < len(toks) else ""
            if nxt and nxt[0].isdigit():
                out.append(nxt)
                i += 2
                continue
            break
        if base in _STOPWORDS or base in extra_stops:
            break
        out.append(toks[i])
        i += 1
    return " ".join(out).rstrip(".,;:- ")


def extract_street(text: str, extra_stops: frozenset[str] = frozenset()) -> str:
    """Return a 'strada X [nr]' fragment, or ''."""
    if not text:
        return ""
    m = STREET_RE.search(" ".join(text.split()))
    if not m:
        return ""
    street = _clean_street(m.group(0), extra_stops)
    return street if len(street.split()) >= 2 else ""


def has_house_number(street: str) -> bool:
    return bool(re.search(r"\d", street or ""))


# --- ad type ------------------------------------------------------------------

_SHORT_STAY = re.compile(
    r"regim hotelier|pe noapte|/\s*noapte|/\s*zi\b|pe zi\b|nightly|"
    r"cazare (?:muncitori|in regim)|pe termen scurt|"
    # 'zilnic' alone is agency boilerplate ("oferte noi zilnic"); needs a rental word
    r"(?:inchiri\w*|chiri\w*|regim|tarif\w*) (?:zilnic|saptamanal)"
)
# "regim hotelier sau pe termen lung", "se poate inchiria si in regim hotelier"
_ALSO_LONG_TERM = re.compile(
    r"(?:termen|durata|perioada) (?:lung|indelungat)|pe termen nedeterminat|"
    r"si (?:in )?regim hotelier|(?:sau|cat si) (?:pe )?(?:termen lung|luna|lunar)"
)
_SALE_AD = re.compile(r"\bde vanzare\b|\bvand\b|\bvindem\b")
NEGOTIABLE = re.compile(r"\bnegocia")  # \b keeps "nenegociabil" out


def drop_reason(title: str, full_text: str) -> str | None:
    """Why an ad from a rental feed is not a long-term apartment rental, or None."""
    if looks_like_parking_only(title):
        return "parking-only"
    if _SALE_AD.search(fold(title)):
        return "sale-ad"
    text = fold(full_text)
    if _SHORT_STAY.search(text) and not _ALSO_LONG_TERM.search(text):
        return "short-stay"
    return None
