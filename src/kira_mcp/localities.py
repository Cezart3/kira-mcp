"""Every Romanian municipiu, oraș and comună (Wikidata), with name resolution
and the URL slugs each source site uses for it."""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from kira_mcp.text import fold, slugify

# what people type -> official name
_ALIASES = {
    "cluj": "Cluj-Napoca",
    "bucharest": "București",
    "buc": "București",
    "tg mures": "Târgu Mureș",
    "tg. mures": "Târgu Mureș",
    "tirgu mures": "Târgu Mureș",
    "tg jiu": "Târgu Jiu",
    "tirgu jiu": "Târgu Jiu",
    "sf gheorghe": "Sfântu Gheorghe",
    "dr tr severin": "Drobeta-Turnu Severin",
    "drobeta": "Drobeta-Turnu Severin",
    "turnu severin": "Drobeta-Turnu Severin",
    "piatra-neamt": "Piatra Neamț",
}
_SPLIT = re.compile(r"\s*[,(]\s*|\s*\)\s*$")


@dataclass(frozen=True, slots=True)
class Locality:
    name: str
    county: str
    kind: str  # municipiu | oras | comuna
    lat: float
    lon: float
    population: int

    @property
    def label(self) -> str:
        return self.name if self.name == self.county else f"{self.name}, {self.county}"

    @property
    def is_bucharest(self) -> bool:
        return self.county == "București"

    # ----- site slugs ---------------------------------------------------------

    def storia_paths(self) -> list[str]:
        """Candidate storia location paths, most likely first. storia writes a
        hyphen inside a name as '--' and a space as '-' ('cluj/cluj--napoca',
        'mures/targu-mures'), but its spelling of a name doesn't always match the
        official one ('neamt/piatra--neamt'), hence the fallbacks."""
        if self.is_bucharest:
            return ["bucuresti"]

        def storia(s: str) -> str:
            return "--".join(slugify(part) for part in fold(s).split("-"))

        county, name = storia(self.county), storia(self.name)
        cands = [
            f"{county}/{name}",
            f"{county}/{slugify(self.name, '--')}",
            f"{slugify(self.county)}/{slugify(self.name)}",
        ]
        return list(dict.fromkeys(cands))

    def publi24_path(self) -> str:
        if self.is_bucharest:
            return "bucuresti/bucuresti"
        return f"{slugify(self.county)}/{slugify(self.name)}"

    def lajumate_path(self) -> str:
        county = "bucuresti-ilfov" if self.county in ("București", "Ilfov") else slugify(
            self.county
        )
        return f"{county}/{slugify(self.name)}"

    def matches(self, location_text: str) -> bool:
        """Whether a site's location string names this locality."""
        # 'Piatra-Neamț' vs 'Piatra Neamt': compare on space-separated slugs
        return f" {slugify(self.name, ' ')} " in f" {slugify(location_text, ' ')} "


@lru_cache(maxsize=1)
def all_localities() -> tuple[Locality, ...]:
    raw = json.loads(
        resources.files("kira_mcp").joinpath("data/localities.json").read_text("utf-8")
    )
    return tuple(Locality(*row) for row in raw["rows"])


@lru_cache(maxsize=1)
def _by_name() -> dict[str, list[Locality]]:
    idx: dict[str, list[Locality]] = {}
    for loc in all_localities():  # data is sorted by population, desc
        idx.setdefault(fold(loc.name), []).append(loc)
        idx.setdefault(slugify(loc.name, " "), []).append(loc)
    return {k: list(dict.fromkeys(v)) for k, v in idx.items()}


class LocalityNotFound(ValueError):
    def __init__(self, query: str, suggestions: list[Locality]):
        self.query = query
        self.suggestions = suggestions
        msg = f"No Romanian locality named {query!r}."
        if suggestions:
            msg += " Did you mean: " + "; ".join(s.label for s in suggestions) + "?"
        else:
            msg += " Use find_locality, or give the name of the city/town/commune in Romanian."
        super().__init__(msg)


def _norm(s: str) -> str:
    return " ".join(slugify(s, " ").split())


def find(query: str, county: str | None = None) -> list[Locality]:
    """All localities matching a name, largest first. Accepts 'Florești, Cluj'
    or 'Florești (Prahova)' as well as a separate county."""
    parts = [p for p in _SPLIT.split(query.strip()) if p]
    if not parts:
        return []
    name = parts[0]
    if county is None and len(parts) > 1:
        county = parts[1]
    key = _norm(name)
    name = _ALIASES.get(key, _ALIASES.get(fold(name).strip(), name))
    hits = list(_by_name().get(_norm(name), []))
    if county:
        ck = _norm(county.removeprefix("judetul ").removeprefix("județul "))
        hits = [h for h in hits if _norm(h.county) == ck]
    return hits


def resolve(query: str, county: str | None = None) -> Locality:
    """The locality a person most likely means: the most populous one with that
    name (Florești -> Florești, Cluj), unless a county narrows it."""
    hits = find(query, county)
    if hits:
        return hits[0]
    raise LocalityNotFound(query, suggest(query))


def suggest(query: str, n: int = 5) -> list[Locality]:
    names = difflib.get_close_matches(_norm(query), list(_by_name()), n=n, cutoff=0.7)
    out: list[Locality] = []
    for k in names:
        out.extend(_by_name()[k][:2])
    return list(dict.fromkeys(out))[:n]
