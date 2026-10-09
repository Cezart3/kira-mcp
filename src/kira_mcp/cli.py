"""`kira` command: the same search from a terminal, or from any agent that can
run shell commands (add --json for machine-readable output)."""
from __future__ import annotations

import argparse
import json
import logging
import sys

from kira_mcp import __version__, localities
from kira_mcp import search as core


def _print_rentals(res: dict) -> None:
    loc = res["locality"]
    print(f"{loc['name']}, {loc['county']} — {res['matched']} matching, showing {res['returned']}")
    for s in res["sources"]:
        extra = f", {s['total_on_site']} on site" if "total_on_site" in s else ""
        print(f"  {s['site']}: {s['status']} ({s['fetched']} fetched{extra})")
    print()
    for i, r in enumerate(res["results"], 1):
        facts = [
            f"{r['price_eur']:.0f} EUR" if r.get("price_eur") else "price ?",
            f"{r['rooms']} cam" if r.get("rooms") else None,
            f"{r['surface_m2']:.0f} mp" if r.get("surface_m2") else None,
            f"heating: {r['heating']}" if r.get("heating") != "unknown" else None,
            f"parking: {r['parking']}" if r.get("parking") != "unknown" else None,
            f"{r['distance']['walk_minutes']} min walk" if r.get("distance") else None,
        ]
        print(f"{i:>2}. {r['title']}")
        print(f"    {' | '.join(f for f in facts if f)}")
        if r.get("area"):
            print(f"    {r['area']}")
        print(f"    {r['url']}")
    for n in res.get("notes") or []:
        print(f"\nnote: {n}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="kira", description="Search Romanian rentals live.")
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="apartments for rent")
    s.add_argument("city")
    s.add_argument("--county")
    s.add_argument("--min-price", type=float)
    s.add_argument("--max-price", type=float)
    s.add_argument("--rooms", type=int, nargs="+", help="e.g. --rooms 2 3 (4 = 4+)")
    s.add_argument("--heating", choices=sorted(core.HEATING_VALUES))
    s.add_argument("--parking", nargs="+", choices=sorted(core.PARKING_STATUSES))
    s.add_argument("--owner-only", action="store_true")
    s.add_argument("--keywords")
    s.add_argument("--near", help="place to measure walking distance from")
    s.add_argument("--max-walk", type=int, dest="max_walk_minutes")
    s.add_argument("--sort", choices=core.SORTS, default="newest")
    s.add_argument("--limit", type=int, default=15)
    s.add_argument("--pages", type=int, default=2)
    s.add_argument("--json", action="store_true", default=argparse.SUPPRESS)

    d = sub.add_parser("listing", help="full details of one ad")
    d.add_argument("url")
    d.add_argument("--json", action="store_true", default=argparse.SUPPRESS)

    p = sub.add_parser("parking", help="parking spots / garages for rent")
    p.add_argument("city")
    p.add_argument("--county")
    p.add_argument("--max-price", type=float)
    p.add_argument("--limit", type=int, default=15)
    p.add_argument("--json", action="store_true", default=argparse.SUPPRESS)

    f = sub.add_parser("find", help="which localities match a name")
    f.add_argument("name")
    f.add_argument("--json", action="store_true", default=argparse.SUPPRESS)

    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        if a.cmd == "search":
            res = core.search_rentals(
                a.city, a.county, min_price=a.min_price, max_price=a.max_price,
                rooms=a.rooms, heating=a.heating, parking=a.parking,
                owner_only=a.owner_only, keywords=a.keywords, near=a.near,
                max_walk_minutes=a.max_walk_minutes, sort=a.sort, limit=a.limit,
                pages=a.pages,
            )
        elif a.cmd == "listing":
            res = core.get_listing(a.url)
        elif a.cmd == "parking":
            res = core.search_parking(a.city, a.county, max_price=a.max_price, limit=a.limit)
        else:
            hits = localities.find(a.name) or localities.suggest(a.name)
            res = {"localities": [
                {"name": h.name, "county": h.county, "kind": h.kind, "population": h.population}
                for h in hits
            ]}
    except (ValueError, LookupError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if a.json or a.cmd != "search":
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        _print_rentals(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
