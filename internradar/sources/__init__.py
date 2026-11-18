"""Source adapters. Each one turns a company's public job board into RawJob objects."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import RawJob

if TYPE_CHECKING:
    from ..http import Fetcher


class Source:
    """Base class. Subclasses set `ats` and implement `list_jobs()` (and maybe `enrich()`)."""

    ats = "base"
    #: True when list_jobs() returns titles/locations only and enrich() fetches descriptions
    needs_details = False

    def __init__(self, company: dict, spec: dict, fetcher: "Fetcher", settings: dict):
        self.company = company
        self.spec = spec
        self.fetcher = fetcher
        self.settings = settings
        self.name = company["name"]
        self.key = company["key"]

    @property
    def label(self) -> str:
        ident = self.spec.get("slug") or self.spec.get("host") or self.spec.get("url") or ""
        return f"{self.ats}:{ident}" if ident else self.ats

    @property
    def board_url(self) -> str | None:
        """Human-facing URL of the board (shown on the website's source table)."""
        return None

    def job(self, **kw) -> RawJob:
        return RawJob(source=self.ats, company=self.name, company_key=self.key, **kw)

    async def list_jobs(self) -> list[RawJob]:
        raise NotImplementedError

    async def enrich(self, job: RawJob) -> RawJob:
        return job


def registry() -> dict[str, type[Source]]:
    from .amazon import Amazon
    from .adzuna import Adzuna
    from .ashby import Ashby
    from .browser import Browser
    from .greenhouse import Greenhouse
    from .html_links import HtmlLinks
    from .lever import Lever
    from .personio import Personio
    from .recruitee import Recruitee
    from .smartrecruiters import SmartRecruiters
    from .workable import Workable
    from .workday import Workday

    classes = [Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Recruitee, Personio, Workday,
               Amazon, HtmlLinks, Browser, Adzuna]
    return {c.ats: c for c in classes}
