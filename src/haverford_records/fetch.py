"""Polite fetching with an immutable raw store.

Two rules this module exists to enforce:

1. We never hit a host faster than SCRAPER_DELAY, and we say who we are in the
   User-Agent. This is a department-sanctioned tool reading its own
   institution's site; it should be identifiable and unobtrusive.

2. Every response body is kept, keyed by (url, sha256). Parsers WILL have bugs,
   and reprocessing two seasons of history must never mean re-crawling. It also
   means an amended result -- a DQ applied days later, a corrected wind reading
   -- lands as a new row we can diff against the old one rather than silently
   overwriting what we thought we knew.
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx


@dataclass(frozen=True)
class Fetched:
    url: str
    status: int
    body: str
    content_hash: str

    @property
    def ok(self) -> bool:
        return self.status == 200 and bool(self.body)


class PoliteFetcher:
    def __init__(
        self,
        *,
        contact: str | None = None,
        delay: float | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.contact = contact or os.getenv("SCRAPER_CONTACT", "unset@example.edu")
        self.delay = delay if delay is not None else float(os.getenv("SCRAPER_DELAY", "2.0"))
        self._last_hit: dict[str, float] = {}
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    f"haverford-records/0.1 (athletics communications committee; {self.contact})"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )

    def _wait(self, host: str) -> None:
        elapsed = time.monotonic() - self._last_hit.get(host, 0.0)
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_hit[host] = time.monotonic()

    def get(self, url: str) -> Fetched:
        host = urlparse(url).netloc
        self._wait(host)
        resp = self._client.get(url)
        body = resp.text if resp.status_code == 200 else ""
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        return Fetched(url=url, status=resp.status_code, body=body, content_hash=digest)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "PoliteFetcher":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
