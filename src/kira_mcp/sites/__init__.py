"""Source sites. OLX and imobiliare.ro are not here on purpose: both refuse
automated requests (HTTP 403), and kira-mcp respects that instead of evading it."""
from urllib.parse import urlsplit

from kira_mcp.sites.base import Filters, RawListing, Site, SiteResult
from kira_mcp.sites.lajumate import Lajumate
from kira_mcp.sites.publi24 import Publi24
from kira_mcp.sites.storia import Storia

SITES: dict[str, Site] = {s.name: s for s in (Storia(), Publi24(), Lajumate())}
UNSUPPORTED = {
    "olx": "OLX blocks automated requests (HTTP 403)",
    "imobiliare": "imobiliare.ro blocks automated requests (HTTP 403)",
}


def site_for_url(url: str) -> Site | None:
    host = urlsplit(url).netloc.lower()
    for site in SITES.values():
        if any(host == h or host.endswith("." + h) for h in site.hosts):
            return site
    return None


__all__ = ["SITES", "UNSUPPORTED", "Filters", "RawListing", "Site", "SiteResult", "site_for_url"]
