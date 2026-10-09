# kira-mcp

**Ask your AI to find you a flat to rent in Romania — any city, town or commune.**

An [MCP](https://modelcontextprotocol.io) server (and a CLI) that searches
**storia.ro, publi24.ro and lajumate.ro live**, merges the results, removes
duplicates and non-rentals, and reads the ad text for the things the site
filters don't give you: **heating type, parking, private owner vs agency, and
walking distance** to a place you care about.

Works with Claude, ChatGPT, Cursor, VS Code, Gemini CLI, Codex and any other
MCP client.

> "Find me a 2-room flat in Cluj under 500 €, own boiler, with parking,
> max 20 minutes on foot from UMF."

```text
$ kira search Brasov --rooms 2 --max-price 500 --heating centrala_proprie --limit 3
Brașov, Brașov — 10 matching, showing 3
  storia: ok (74 fetched, 374 on site)
  publi24: ok (24 fetched)
  lajumate: ok (56 fetched, 382 on site)

 1. Studio Maurer Villas partial mobilat
    500 EUR | 2 cam | 45 mp | heating: centrala_proprie | parking: included
    Tractorul, Brasov, Brasov
    https://www.storia.ro/ro/oferta/studio-maurer-villas-partial-mobilat-IDIPoX
 2. Apartament pe 2 niveluri, 62 mp, zona Faget-Tractorul
    400 EUR | 2 cam | 62 mp | heating: centrala_proprie
    ...
```

## Why

Romanian rental sites each cover part of the market, their filters are thin,
and the details that decide a viewing — *centrală proprie or termoficare? is
the parking spot included or "posibilitate de parcare în zonă"?* — live in
free text. kira-mcp does the tab-juggling and the reading, so an agent can
answer the question you actually asked.

## Features

- **All of Romania**: 3,181 localities (municipii, orașe, comune) from
  Wikidata. Diacritics optional, common shortcuts understood (`cluj`,
  `tg mures`, `buc`), ambiguous names resolved (`Floresti, Prahova`).
- **3 sites in parallel**, deduplicated across sites (the same flat posted on
  two sites shows once, with `also_listed_on`).
- **Filters**: price (EUR; RON converted), rooms, heating, parking,
  private owner, keywords.
- **Text extraction** tuned on real Romanian ads: heating
  (`centrala_proprie` / `termoficare`), parking (`included`,
  `likely_included`, `area_possible`, `none`), rooms, surface, floor, street.
  When a filter needs it, the full ad is read, not just the snippet.
- **Walking distance** from any place (`near="UMF"`), geocoded with
  OpenStreetMap, with a Google Maps directions link.
- **Drops non-rentals**: sale ads, parking-only ads, hotel-style short stays.
- **Parking spots** search (`search_parking`).
- **Privacy**: phone numbers and e-mails are redacted from returned text.
  The user contacts the owner on the original site.

## Install

You need [uv](https://docs.astral.sh/uv/getting-started/installation/).
Nothing else — `uvx` fetches and runs it.

**Claude Code**

```bash
claude mcp add kira -- uvx --from git+https://github.com/Cezart3/kira-mcp kira-mcp
```

**Claude Desktop, Cursor, Windsurf, Gemini CLI** — add to the client's MCP
config (`claude_desktop_config.json`, `~/.cursor/mcp.json`,
`~/.gemini/settings.json`, ...):

```json
{
  "mcpServers": {
    "kira": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Cezart3/kira-mcp", "kira-mcp"]
    }
  }
}
```

**VS Code** (`.vscode/mcp.json`):

```json
{
  "servers": {
    "kira": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Cezart3/kira-mcp", "kira-mcp"]
    }
  }
}
```

**Codex** (`~/.codex/config.toml`):

```toml
[mcp_servers.kira]
command = "uvx"
args = ["--from", "git+https://github.com/Cezart3/kira-mcp", "kira-mcp"]
```

**Remote / HTTP clients**: `kira-mcp --transport streamable-http --port 8000`
serves MCP at `http://localhost:8000/mcp`.

**Agent skill**: [`skills/romania-rentals/SKILL.md`](skills/romania-rentals/SKILL.md)
teaches agents that support skills (Claude Code, Codex, ...) when and how to
use it — through the MCP tools, or through the CLI if no MCP server is set up.
Copy the folder into your skills directory (e.g. `~/.claude/skills/`).

## Tools

| Tool | What it does |
|---|---|
| `search_rentals` | Search one locality. Filters: `min_price`, `max_price` (EUR/month), `rooms`, `heating`, `parking`, `owner_only`, `keywords`, `near` + `max_walk_minutes`, `sort` (`newest`, `price_asc`, `price_desc`, `distance`), `limit`. |
| `get_listing_details` | Full description, photos, heating/parking with confidence, for one ad URL. |
| `search_parking` | Parking spots / garages for rent in a locality. |
| `find_locality` | Resolve an ambiguous or misspelled place name; lists candidates with county. |

All tools are read-only. Every result carries the original ad URL.

## CLI

```bash
uvx --from git+https://github.com/Cezart3/kira-mcp kira search "Cluj-Napoca" --rooms 2 --max-price 500 --near UMF --max-walk 20 --sort distance
kira search Iasi --heating centrala_proprie --parking included likely_included
kira listing https://www.storia.ro/ro/oferta/...
kira parking Brasov --max-price 80
kira find Floresti
kira --json search Sibiu        # machine-readable
```

## Configuration

| Env var | Default | |
|---|---|---|
| `KIRA_RON_PER_EUR` | `5.0` | Exchange rate for RON prices. |
| `KIRA_REQUEST_DELAY` | `1.2` | Seconds between requests to the same site. |
| `KIRA_USER_AGENT` | `kira-mcp/<version> (+repo url)` | |
| `KIRA_CACHE_DIR` | OS cache dir | Where geocoding results are cached. |

## Sources and limits

| Site | Status |
|---|---|
| storia.ro | ✅ server-side price/room filters, pagination |
| publi24.ro | ✅ newest page per search |
| lajumate.ro | ✅ pagination |
| olx.ro | ❌ blocks automated access (HTTP 403) |
| imobiliare.ro | ❌ blocks automated access (HTTP 403) |

kira-mcp does not try to get around a site that blocks it. Results are
therefore a large share of the market, not all of it — the tool says so in
every response.

**Be a good citizen.** kira-mcp identifies itself, waits between requests,
caches pages for 10 minutes, fetches only what one search needs and returns
links back to the sites. It is meant for personal flat-hunting, not bulk
harvesting. Check each site's terms before using it for anything else.

Distances are estimates (straight line × 1.3, walking 4.7 km/h). An ad with
only a neighbourhood gets an `area`-precision distance.

## Development

```bash
git clone https://github.com/Cezart3/kira-mcp && cd kira-mcp
uv sync --group dev
uv run pytest            # offline, against synthetic fixtures
KIRA_LIVE=1 uv run pytest -m live   # against the real sites
uv run ruff check .
```

The locality list is rebuilt with `uv run python scripts/build_localities.py`.

Site parsers live in `src/kira_mcp/sites/`. Adding a site = one class with
`search_rentals` and `fetch_detail`; see `sites/base.py`.

## Credits

- Locality data: [Wikidata](https://www.wikidata.org) (CC0).
- Geocoding: [Nominatim](https://nominatim.org) / © OpenStreetMap
  contributors (ODbL), at ≤1 request/second, cached.
- Extraction rules grew out of *Kira*, a personal flat-hunting bot.

## License

[MIT](LICENSE) © 2026 Cezar Tocaciu
