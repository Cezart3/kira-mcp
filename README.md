# kira-mcp

<!-- mcp-name: io.github.Cezart3/kira-mcp -->

[![ci](https://github.com/Cezart3/kira-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/Cezart3/kira-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/kira-rentals-mcp)](https://pypi.org/project/kira-rentals-mcp/)
[![MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/Cezart3/kira-mcp/blob/main/LICENSE)
![python](https://img.shields.io/badge/python-3.11%2B-blue)
![MCP](https://img.shields.io/badge/MCP-server-8A2BE2)

**Ask your AI to find you a flat to rent in Romania — any city, town or commune.**

![Demo: asking Claude Code for a flat, kira-mcp searches the sites live](https://raw.githubusercontent.com/Cezart3/kira-mcp/main/docs/demo.svg)

An [MCP](https://modelcontextprotocol.io) server (and a CLI) that searches
**storia.ro, publi24.ro and lajumate.ro live**, merges the results, removes
duplicates and non-rentals, and reads the ad text for the things the site
filters don't give you: **heating type, parking, private owner vs agency, and
walking distance** to a place you care about.

Works with Claude (Code & Desktop), Cursor, VS Code, Windsurf, Gemini CLI,
Codex and any other MCP client. Also usable as a plain CLI.

🇷🇴 [Ghid în română](https://github.com/Cezart3/kira-mcp/blob/main/README.ro.md)

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

## Quick start (5 minutes)

### Step 1 — install uv (once)

kira-mcp runs through [uv](https://docs.astral.sh/uv/), which downloads it
and its Python on first use. Nothing else to install.

- **Windows** (PowerShell):
  `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
- **macOS / Linux**:
  `curl -LsSf https://astral.sh/uv/install.sh | sh`

Close and reopen the terminal, then check: `uvx --version`.

### Step 2 — connect it to your AI

<details open>
<summary><b>Claude Code</b></summary>

```bash
claude mcp add kira -s user -- uvx kira-rentals-mcp
```

Check with `claude mcp list` → `kira: ... ✓ Connected`.
</details>

<details>
<summary><b>Claude Desktop</b></summary>

1. Settings → Developer → **Edit Config** (opens `claude_desktop_config.json`).
2. Paste (merge with what is there):

```json
{
  "mcpServers": {
    "kira": {
      "command": "uvx",
      "args": ["kira-rentals-mcp"]
    }
  }
}
```

3. Quit Claude Desktop completely (tray icon → Quit) and start it again.
   "kira" appears under the tools/connectors menu.

If it says the server failed, use the full path of uvx as `command`
(`where uvx` on Windows, `which uvx` on macOS — e.g.
`C:\Users\you\.local\bin\uvx.exe`).
</details>

<details>
<summary><b>Cursor / Windsurf / Gemini CLI</b></summary>

Same JSON as Claude Desktop, in `~/.cursor/mcp.json`,
`~/.codeium/windsurf/mcp_config.json` or `~/.gemini/settings.json`.
</details>

<details>
<summary><b>VS Code (Copilot agent mode)</b></summary>

`.vscode/mcp.json` in your workspace:

```json
{
  "servers": {
    "kira": {
      "type": "stdio",
      "command": "uvx",
      "args": ["kira-rentals-mcp"]
    }
  }
}
```
</details>

<details>
<summary><b>Codex CLI</b></summary>

`~/.codex/config.toml`:

```toml
[mcp_servers.kira]
command = "uvx"
args = ["kira-rentals-mcp"]
```
</details>

<details>
<summary><b>Other / remote clients (HTTP)</b></summary>

```bash
uvx kira-rentals-mcp --transport streamable-http --port 8000
```

serves MCP at `http://localhost:8000/mcp`.
</details>

### Step 3 — ask

Just talk to it, in English or Romanian:

- *"Caută-mi o garsonieră în Sibiu sub 350 €, cu centrală proprie."*
- *"2-room flat in Timișoara, max 500 €, private owner, sorted by price."*
- *"Apartamente cu 2 camere în Cluj la max 20 de minute pe jos de UMF."*
- *"Is parking included in this one? <link>"*
- *"Loc de parcare de închiriat în Brașov sub 60 €."*

The first call takes a few extra seconds while uv downloads the package.

### No MCP? Use the agent skill or the CLI

- **Agent skill**: copy [`skills/romania-rentals/`](https://github.com/Cezart3/kira-mcp/blob/main/skills/romania-rentals/SKILL.md)
  into your skills folder (e.g. `~/.claude/skills/`). It teaches the agent
  when to search and how to read the results, via the MCP tools or the CLI.
- **CLI**: see [below](#cli).

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
uvx --from kira-rentals-mcp kira search "Cluj-Napoca" --rooms 2 --max-price 500 --near UMF --max-walk 20 --sort distance
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

Distances are estimates (straight line × 1.3, walking 4.7 km/h). They use the
location the poster entered; an ad with only a neighbourhood gets a
`district`-precision distance, an ad with neither is listed without one.

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

[MIT](https://github.com/Cezart3/kira-mcp/blob/main/LICENSE) © 2026 Cezar Tocaciu
