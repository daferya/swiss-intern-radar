"""Polite async HTTP client: global + per-host concurrency limits, retries with backoff."""

from __future__ import annotations

import asyncio
import json
import random
from collections import defaultdict
from urllib.parse import urlparse

import httpx

from .models import SourceError

DEFAULT_UA = "Mozilla/5.0 (compatible; internradar/1.0; personal internship search, low volume)"
RETRY_STATUS = {429, 500, 502, 503, 504}


class Fetcher:
    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        concurrency: int = 8,
        per_host: int = 2,
        timeout: float = 25.0,
        retries: int = 2,
        user_agent: str = DEFAULT_UA,
    ) -> None:
        self.client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
            headers={"User-Agent": user_agent, "Accept-Language": "en-US,en;q=0.8,de;q=0.6,fr;q=0.6"},
        )
        self._sem = asyncio.Semaphore(concurrency)
        self._host_sems: dict[str, asyncio.Semaphore] = defaultdict(lambda: asyncio.Semaphore(per_host))
        self.retries = retries
        self.requests = 0

    async def close(self) -> None:
        await self.client.aclose()

    async def request(self, method: str, url: str, **kw) -> httpx.Response:
        host = urlparse(url).netloc
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            async with self._sem, self._host_sems[host]:
                try:
                    self.requests += 1
                    resp = await self.client.request(method, url, **kw)
                except httpx.TransportError as e:  # DNS, connection reset, timeout ...
                    last_exc = e
                    resp = None
            if resp is not None:
                if resp.status_code in RETRY_STATUS and attempt < self.retries:
                    delay = _retry_after(resp) or (1.5 * (attempt + 1) + random.random())
                    await asyncio.sleep(min(delay, 20))
                    continue
                if resp.status_code >= 400:
                    raise SourceError(
                        f"HTTP {resp.status_code} for {url}",
                        status=resp.status_code,
                        not_found=resp.status_code in (404, 410, 422),
                    )
                return resp
            if attempt < self.retries:
                await asyncio.sleep(1.5 * (attempt + 1) + random.random())
        raise SourceError(f"network error for {url}: {last_exc!r}")

    async def get_json(self, url: str, **kw):
        resp = await self.request("GET", url, headers={"Accept": "application/json", **kw.pop("headers", {})}, **kw)
        return _json(resp, url)

    async def post_json(self, url: str, payload: dict, **kw):
        resp = await self.request(
            "POST", url, json=payload,
            headers={"Accept": "application/json", "Content-Type": "application/json", **kw.pop("headers", {})},
            **kw,
        )
        return _json(resp, url)

    async def get_text(self, url: str, **kw) -> str:
        resp = await self.request("GET", url, **kw)
        return resp.text

    async def get_final_url(self, url: str) -> str:
        resp = await self.request("GET", url)
        return str(resp.url)


def _json(resp: httpx.Response, url: str):
    try:
        return resp.json()
    except (json.JSONDecodeError, ValueError):
        raise SourceError(f"not JSON from {url} (got {resp.headers.get('content-type', '?')})")


def _retry_after(resp: httpx.Response) -> float | None:
    v = resp.headers.get("Retry-After")
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None
