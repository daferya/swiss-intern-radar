"""Career pages that only render with JavaScript (Google, Apple, Meta, Microsoft...).

Uses Playwright (free, open source) to load the listing page in headless Chromium, then reuses
the html_links logic. Optional: install with `pip install -r requirements-browser.txt` and
`python -m playwright install chromium`. Big-tech sites change their markup from time to time,
so treat these as best-effort; the source table on the website tells you when one breaks.
"""

from __future__ import annotations

import asyncio
import os

from ..models import SourceError
from .html_links import HtmlLinks, enrich_from_page, filter_links

_LOCK: asyncio.Lock | None = None  # one Chromium at a time keeps memory low on the free CI runner


class Browser(HtmlLinks):
    ats = "browser"

    @property
    def label(self) -> str:
        return "browser:" + self.spec["urls"][0].split("/")[2]

    async def list_jobs(self):
        if not self.settings.get("browser_enabled"):
            raise SourceError("skipped: browser sources disabled (install Playwright or set RADAR_BROWSER=1)")
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise SourceError("skipped: Playwright not installed (pip install -r requirements-browser.txt)")

        global _LOCK
        if _LOCK is None:
            _LOCK = asyncio.Lock()   # created inside the running event loop
        pairs: list[tuple[str, str]] = []
        async with _LOCK, async_playwright() as p:
            channel = os.environ.get("RADAR_BROWSER_CHANNEL") or None   # e.g. "chrome" to use local Chrome
            browser = await p.chromium.launch(headless=True, channel=channel)
            try:
                page = await browser.new_page(locale="en-US")
                for url in self.spec["urls"]:
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    except Exception as e:  # DNS / timeout / blocked: report it, don't crash the run
                        raise SourceError(f"could not load {url}: {str(e).splitlines()[0][:160]}")
                    try:
                        await page.wait_for_load_state("networkidle", timeout=20000)
                    except Exception:
                        pass
                    if self.spec.get("wait_for"):
                        try:
                            await page.wait_for_selector(self.spec["wait_for"], timeout=20000)
                        except Exception:
                            pass
                    for _ in range(int(self.spec.get("scrolls", 3))):
                        await page.mouse.wheel(0, 5000)
                        await page.wait_for_timeout(800)
                    anchors = await page.eval_on_selector_all(
                        "a[href]",
                        "els => els.map(e => [e.href, (e.innerText || e.getAttribute('aria-label') || e.title || '')])",
                    )
                    pairs += filter_links(anchors, self.spec["link_pattern"], self.spec.get("exclude_pattern"))
            finally:
                await browser.close()
        if not pairs:
            raise SourceError("no job links found (site layout may have changed; update link_pattern)")
        return self.make_jobs(dict(pairs).items())

    async def enrich(self, job):
        return await enrich_from_page(self.fetcher, job)
