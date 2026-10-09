"""The MCP surface, through a real in-process MCP client."""
import json

import anyio
from mcp import Client

from kira_mcp.server import mcp


def call(name: str, args: dict):
    async def go():
        async with Client(mcp) as c:
            return await c.call_tool(name, args)

    return anyio.run(go)


def test_tools_are_listed_read_only():
    async def go():
        async with Client(mcp) as c:
            return (await c.list_tools()).tools

    tools = {t.name: t for t in anyio.run(go)}
    assert set(tools) == {
        "search_rentals", "get_listing_details", "search_parking", "find_locality"
    }
    assert all(t.annotations and t.annotations.read_only_hint for t in tools.values())


def test_search_tool_returns_results():
    r = call("search_rentals", {"city": "Cluj", "rooms": [1]})
    assert not r.is_error
    data = json.loads(r.content[0].text)
    assert data["locality"]["name"] == "Cluj-Napoca"
    assert data["results"][0]["title"] == "Garsoniera Marasti"


def test_errors_reach_the_agent_with_suggestions():
    r = call("search_rentals", {"city": "Brasovv"})
    assert r.is_error
    assert "Brașov" in r.content[0].text


def test_find_locality_tool():
    r = call("find_locality", {"name": "Floresti"})
    data = json.loads(r.content[0].text)
    assert data["exact"] and data["localities"][0]["county"] == "Cluj"


def test_stdio_entry_point_starts():
    """The installed `kira-mcp` command speaks MCP over stdio."""
    import sys

    from mcp import StdioServerParameters
    from mcp.client.session import ClientSession
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=sys.executable, args=["-m", "kira_mcp.server"])

    async def go():
        async with stdio_client(params) as (read, write), ClientSession(read, write) as s:
            init = await s.initialize()
            tools = (await s.list_tools()).tools
            return init.server_info.name, {t.name for t in tools}

    name, tools = anyio.run(go)
    assert name == "kira" and "search_rentals" in tools
