"""MCP server: exposes the live search as tools any MCP client can call
(Claude, ChatGPT, Cursor, VS Code, Gemini CLI, Codex...)."""
from __future__ import annotations

import argparse
import functools
import logging
import sys
from typing import Annotated, Literal

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from kira_mcp import __version__, localities
from kira_mcp import search as core

INSTRUCTIONS = """\
Live search of apartment rentals in Romania, in any city, town or commune
(3,100+ localities), across storia.ro, publi24.ro and lajumate.ro.

- Prices are monthly rent in EUR (RON converted at ~5 RON/EUR).
- `heating`: 'centrala_proprie' = own gas boiler (Romanians usually prefer it),
  'termoficare' = district or shared building heating (not the flat's own boiler).
- `parking` statuses: included, likely_included, area_possible (street/free
  parking nearby, or at extra cost), none, unknown.
- Every result links to the original ad; contact details are on that page only.
- Searches hit the sites live and take ~5-20 s. Prefer one well-filtered search
  over many broad ones.
- Reply to the user in their language; ad text is Romanian.
"""

mcp = MCPServer(
    name="kira",
    title="Kira — Romanian rentals",
    instructions=INSTRUCTIONS,
    website_url="https://github.com/Cezart3/kira-mcp",
    version=__version__,
)
_READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True, idempotent_hint=True)

Parking = Literal["included", "likely_included", "area_possible", "none", "unknown"]


async def _run(fn, /, *args, **kwargs):
    """Run blocking search code off the event loop; turn expected failures
    (unknown city, bad filter, unreadable ad) into messages the agent can act on."""
    try:
        return await anyio.to_thread.run_sync(functools.partial(fn, *args, **kwargs))
    except (ValueError, LookupError) as e:
        raise ToolError(str(e)) from e


@mcp.tool(annotations=_READ_ONLY)
async def search_rentals(
    city: Annotated[str, Field(description="Romanian locality, diacritics optional: 'Cluj-Napoca', 'Iasi', 'Floresti', 'Brasov'. 'Floresti, Prahova' disambiguates.")],
    county: Annotated[str | None, Field(description="County (județ) when the name is ambiguous, e.g. 'Prahova'.")] = None,
    max_price: Annotated[float | None, Field(description="Max monthly rent, EUR.")] = None,
    min_price: Annotated[float | None, Field(description="Min monthly rent, EUR.")] = None,
    rooms: Annotated[list[int] | None, Field(description="Room counts; 1 = garsonieră/studio, 4 means 4+. E.g. [2, 3].")] = None,
    heating: Annotated[Literal["centrala_proprie", "termoficare"] | None, Field(description="centrala_proprie = own gas boiler; termoficare = district or shared building heating.")] = None,
    parking: Annotated[list[Parking] | None, Field(description="Keep only these parking statuses, e.g. ['included'] or ['included', 'likely_included'].")] = None,
    owner_only: Annotated[bool, Field(description="Only ads posted by private owners (no agency). Only storia reports this; other sites' ads are then excluded.")] = False,
    keywords: Annotated[str | None, Field(description="Words that must all appear in the ad, e.g. 'balcon mobilat' or 'pet'.")] = None,
    near: Annotated[str | None, Field(description="A place in the same locality to measure walking distance from: 'UMF', 'Piata Unirii', 'Iulius Mall', 'strada Observatorului 34'.")] = None,
    max_walk_minutes: Annotated[int | None, Field(description="With `near`: drop listings farther than this many minutes on foot.")] = None,
    sort: Annotated[Literal["newest", "price_asc", "price_desc", "distance"], Field(description="'distance' needs `near`.")] = "newest",
    limit: Annotated[int, Field(ge=1, le=50, description="How many results to return.")] = 15,
    pages: Annotated[int, Field(ge=1, le=5, description="Result pages fetched per site; more = slower but wider.")] = 2,
) -> dict:
    """Search apartments for rent in a Romanian locality, live, across storia.ro,
    publi24.ro and lajumate.ro. Returns de-duplicated listings with extracted
    facts (price in EUR, rooms, surface, heating type, parking) and links to the
    original ads, plus per-site status."""
    return await _run(
        core.search_rentals, city, county,
        min_price=min_price, max_price=max_price, rooms=rooms, heating=heating,
        parking=parking, owner_only=owner_only, keywords=keywords, near=near,
        max_walk_minutes=max_walk_minutes, sort=sort, limit=limit, pages=pages,
    )


@mcp.tool(annotations=_READ_ONLY)
async def get_listing_details(
    url: Annotated[str, Field(description="URL of an ad on storia.ro, publi24.ro or lajumate.ro (e.g. from search_rentals).")],
) -> dict:
    """Full description, photos and extracted facts for one ad. Use it before
    recommending a listing: heating and parking are often only in the full text."""
    return await _run(core.get_listing, url)


@mcp.tool(annotations=_READ_ONLY)
async def search_parking(
    city: Annotated[str, Field(description="Romanian locality.")],
    county: Annotated[str | None, Field(description="County when the name is ambiguous.")] = None,
    max_price: Annotated[float | None, Field(description="Max monthly rent, EUR.")] = None,
    limit: Annotated[int, Field(ge=1, le=50)] = 15,
) -> dict:
    """Parking spots and garages for rent in a Romanian locality (storia.ro)."""
    return await _run(core.search_parking, city, county, max_price=max_price, limit=limit)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True))
def find_locality(
    name: Annotated[str, Field(description="Locality name, diacritics optional.")],
) -> dict:
    """Which Romanian localities match a name (with county, type and population).
    Use it when a name is ambiguous — there are e.g. several 'Florești'."""
    hits = localities.find(name)
    rows = hits or localities.suggest(name)
    return {
        "exact": bool(hits),
        "localities": [
            {"name": h.name, "county": h.county, "kind": h.kind, "population": h.population}
            for h in rows[:15]
        ],
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="kira-mcp", description="Kira MCP server")
    ap.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    ap.add_argument("--port", type=int, default=8000, help="for streamable-http")
    ap.add_argument("--version", action="version", version=__version__)
    args = ap.parse_args(argv)
    # stdout belongs to the protocol on stdio: log to stderr only
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    if args.transport == "stdio":
        mcp.run()
    else:
        mcp.run(transport="streamable-http", port=args.port)


if __name__ == "__main__":
    main()
