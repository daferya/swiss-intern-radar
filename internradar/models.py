from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RawJob:
    """A posting as returned by one source, before classification."""

    source: str                 # "greenhouse", "workday", ...
    company: str                # display name
    company_key: str            # key from companies.yaml
    external_id: str            # id unique within the source
    title: str
    url: str
    locations: list[str] = field(default_factory=list)
    country_codes: list[str] = field(default_factory=list)
    remote: bool | None = None
    department: str | None = None
    employment_type: str | None = None
    posted_at: str | None = None        # ISO date (YYYY-MM-DD) when known
    description: str = ""               # plain text; may be filled later by Source.enrich()
    salary: dict | None = None          # structured salary when the source exposes one
    details_loaded: bool = True         # False when enrich() should fetch the full posting
    extra: dict = field(default_factory=dict)


class SourceError(Exception):
    """Raised by a source when its board cannot be read (bad slug, HTTP error, bad payload)."""

    def __init__(self, message: str, status: int | None = None, not_found: bool = False):
        super().__init__(message)
        self.status = status
        self.not_found = not_found
