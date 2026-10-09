"""Polite HTTP: identifiable User-Agent, per-host delay, no retry on non-200,
and a short in-memory cache so repeated questions don't re-fetch pages."""
from __future__ import annotations

import logging
import os
import threading
import time
from urllib.parse import urlsplit

import requests

from kira_mcp import __version__

log = logging.getLogger(__name__)

# a browser token (many CDNs reject bare client UAs) + an honest self-identification
UA = os.environ.get("KIRA_USER_AGENT") or (
    f"Mozilla/5.0 (compatible; kira-mcp/{__version__}; +https://github.com/Cezart3/kira-mcp) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
DELAY_S = float(os.environ.get("KIRA_REQUEST_DELAY", "1.2"))
TIMEOUT_S = 25
CACHE_TTL_S = 600


class PoliteSession:
    def __init__(self, delay_s: float = DELAY_S):
        self.delay = delay_s
        self.sess = requests.Session()
        self.sess.headers.update(HEADERS)
        self._last: dict[str, float] = {}
        self._cache: dict[str, tuple[float, int, str]] = {}
        self._lock = threading.Lock()

    def _throttle(self, url: str) -> None:
        host = urlsplit(url).netloc
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._last.get(host, 0.0) + self.delay)
            self._last[host] = slot
        if slot > now:
            time.sleep(slot - now)

    def fetch(self, url: str, params: dict | None = None) -> tuple[int, str]:
        """GET -> (status, body). status 0 = network error. Never retries: a
        non-200 answer is respected, not hammered."""
        key = requests.Request("GET", url, params=params).prepare().url or url
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
            return hit[1], hit[2]
        self._throttle(url)
        try:
            r = self.sess.get(url, params=params, timeout=TIMEOUT_S)
        except requests.RequestException as e:
            log.warning("GET %s failed: %s", key, e)
            return 0, ""
        if r.status_code != 200:
            log.info("GET %s -> HTTP %s", key, r.status_code)
        self._cache[key] = (time.monotonic(), r.status_code, r.text)
        return r.status_code, r.text

    def get_text(self, url: str, params: dict | None = None) -> str | None:
        status, body = self.fetch(url, params)
        return body if status == 200 else None


_session: PoliteSession | None = None


def session() -> PoliteSession:
    """One shared session per process, so the per-host delay holds across sites' threads."""
    global _session
    if _session is None:
        _session = PoliteSession()
    return _session
