"""Rebuild src/kira_mcp/data/localities.json from Wikidata (CC0).

Every municipiu, oraș and comună in Romania, with county, coordinates and
population. Run rarely — localities don't move:

    python scripts/build_localities.py
"""
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "src" / "kira_mcp" / "data" / "localities.json"

QUERY = """
SELECT ?x ?name ?kind ?countyName ?coord (MAX(?pop) AS ?population) WHERE {
  VALUES (?cls ?kind) {
    (wd:Q640364 "municipiu") (wd:Q16858213 "oras") (wd:Q659103 "comuna")
  }
  ?x wdt:P31 ?cls; rdfs:label ?name. FILTER(LANG(?name) = "ro")
  OPTIONAL {
    ?x wdt:P131 ?county. ?county wdt:P31 wd:Q1776764; rdfs:label ?countyName.
    FILTER(LANG(?countyName) = "ro")
  }
  OPTIONAL { ?x wdt:P625 ?coord }
  OPTIONAL { ?x wdt:P1082 ?pop }
} GROUP BY ?x ?name ?kind ?countyName ?coord
"""

_POINT = re.compile(r"Point\(([-\d.]+) ([-\d.]+)\)")


def main() -> None:
    url = "https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(QUERY)
    req = urllib.request.Request(
        url, headers={"User-Agent": "kira-mcp-build (https://github.com/Cezart3/kira-mcp)"}
    )
    rows = json.load(urllib.request.urlopen(req, timeout=180))["results"]["bindings"]

    seen: dict[str, list] = {}
    for b in rows:
        v = {k: x["value"] for k, x in b.items()}
        if v["x"] in seen:  # several coordinates on one item: keep the first
            continue
        county = v.get("countyName") or ("București" if v["name"] == "București" else None)
        m = _POINT.match(v.get("coord", ""))
        if not county or not m:
            continue
        lon, lat = float(m.group(1)), float(m.group(2))
        seen[v["x"]] = [
            v["name"], county, v["kind"], round(lat, 5), round(lon, 5),
            int(float(v.get("population") or 0)),
        ]

    data = sorted(seen.values(), key=lambda r: (-r[5], r[0]))
    OUT.write_text(
        json.dumps(
            {
                "source": "Wikidata (CC0), built by scripts/build_localities.py",
                "fields": ["name", "county", "kind", "lat", "lon", "population"],
                "rows": data,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    print(f"{len(data)} localities -> {OUT}")


if __name__ == "__main__":
    main()
