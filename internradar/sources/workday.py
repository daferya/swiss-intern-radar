"""Workday career sites via their public CXS JSON API (the same calls the career page makes).

List : POST https://{host}/wday/cxs/{tenant}/{site}/jobs  {"appliedFacets":{}, "limit":20, "offset":0, "searchText":"intern"}
Job  : GET  https://{host}/wday/cxs/{tenant}/{site}{externalPath}
Workday rejects limit > 20, so we page by 20. Big employers (Roche, Novartis) have thousands
of postings, so we search for internship keywords and apply the site's own "Switzerland"
facet when it has one.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from ..location import analyse_location, is_multi_placeholder
from ..models import SourceError
from ..text import clean_ws, fold, html_to_text
from . import Source

DEFAULT_SEARCH = ["intern", "internship", "praktikum", "praktikant", "stage", "stagiaire", "student", "thesis"]
_POSTED = re.compile(r"posted\s+(today|yesterday|(\d+)\+?\s+days?\s+ago)", re.I)


def find_swiss_facet(facets: list) -> tuple[str, list[str]] | None:
    """Find the facet values meaning "Switzerland" in a Workday facets tree."""
    exact_country, exact_any, cities = None, None, {}

    def walk(items, parent_param=None):
        nonlocal exact_country, exact_any
        for f in items or []:
            param = f.get("facetParameter") or parent_param
            for v in f.get("values") or []:
                if v.get("values"):          # nested group (e.g. locationMainGroup -> locationCountry)
                    walk([v], v.get("facetParameter") or param)
                    continue
                desc = fold(v.get("descriptor") or "")
                vid = v.get("id")
                if not vid:
                    continue
                if desc in ("switzerland", "schweiz", "suisse", "svizzera", "ch"):
                    if "country" in (param or "").lower() and exact_country is None:
                        exact_country = (param, [vid])
                    elif exact_any is None:
                        exact_any = (param, [vid])
                elif analyse_location(v.get("descriptor") or "")[0]:
                    cities.setdefault(param, []).append(vid)

    walk(facets)
    if exact_country:
        return exact_country
    if exact_any:
        return exact_any
    if cities:
        param = max(cities, key=lambda k: len(cities[k]))
        return param, cities[param]
    return None


def _posted_date(text: str | None, today: date) -> str | None:
    if not text:
        return None
    m = _POSTED.search(text)
    if not m:
        return None
    if m.group(1).lower() == "today":
        return today.isoformat()
    if m.group(1).lower() == "yesterday":
        return (today - timedelta(days=1)).isoformat()
    return (today - timedelta(days=int(m.group(2)))).isoformat()


class Workday(Source):
    ats = "workday"
    needs_details = True

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.host = self.spec["host"].replace("https://", "").strip("/")
        self.tenant = self.spec.get("tenant") or self.host.split(".")[0]
        self.site = self.spec.get("site")

    @property
    def label(self) -> str:
        return f"workday:{self.host}/{self.site or '?'}"

    @property
    def board_url(self) -> str:
        return f"https://{self.host}/{self.site or ''}"

    @property
    def api(self) -> str:
        return f"https://{self.host}/wday/cxs/{self.tenant}/{self.site}"

    async def discover_site(self) -> str:
        """Bare tenant URLs usually redirect to the default external career site."""
        final = await self.fetcher.get_final_url(f"https://{self.host}/")
        m = re.search(r"myworkday(?:jobs|site)\.com/(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_\-]+)", final)
        if not m or m.group(1).lower() in ("wday", "en-us"):
            raise SourceError(f"could not discover Workday site name for {self.host} (set `site:`)")
        return m.group(1)

    async def _post(self, payload: dict) -> dict:
        data = await self.fetcher.post_json(f"{self.api}/jobs", payload)
        if not isinstance(data, dict) or "jobPostings" not in data:
            raise SourceError("unexpected Workday payload")
        return data

    async def list_jobs(self):
        if not self.site:
            self.site = await self.discover_site()
        try:
            first = await self._post({"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""})
        except SourceError as e:
            if not e.not_found or self.spec.get("site") is None:
                raise
            self.site = await self.discover_site()   # configured site moved: try the default one
            first = await self._post({"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""})

        facet = find_swiss_facet(first.get("facets") or [])
        applied = {facet[0]: facet[1]} if facet else {}
        self.facet_used = bool(facet)
        today = self.settings.get("today") or date.today()
        terms = self.spec.get("search") or self.settings.get("workday_search") or DEFAULT_SEARCH
        max_pages = int(self.settings.get("max_pages", 10))

        seen: dict[str, object] = {}
        for term in terms:
            total = None
            for page in range(max_pages):
                data = await self._post({"appliedFacets": applied, "limit": 20, "offset": page * 20, "searchText": term})
                posts = data.get("jobPostings") or []
                if total is None:
                    total = data.get("total") or 0   # later pages may report 0; trust the first
                for p in posts:
                    path = p.get("externalPath")
                    if not path or path in seen:
                        continue
                    loc = p.get("locationsText") or ""
                    if not facet and loc and not is_multi_placeholder(loc) and not analyse_location(loc)[0]:
                        continue  # no Switzerland facet on this site: filter by location text
                    seen[path] = self.job(
                        external_id=path,
                        title=(p.get("title") or "").strip(),
                        url=f"https://{self.host}/en-US/{self.site}{path}",
                        locations=[loc] if loc else [],
                        posted_at=_posted_date(p.get("postedOn"), today),
                        details_loaded=False,
                    )
                if len(posts) < 20 or (page + 1) * 20 >= total:
                    break
        return list(seen.values())

    async def enrich(self, job):
        d = await self.fetcher.get_json(f"{self.api}{job.external_id}")
        info = d.get("jobPostingInfo") or {}
        locs = [info.get("location") or ""] + list(info.get("additionalLocations") or [])
        country = (info.get("country") or {}).get("descriptor")
        if country:
            locs.append(country)
        locs = [x for x in locs if x]
        if locs:
            job.locations = locs
        job.title = (info.get("title") or job.title).strip()
        job.description = clean_ws(html_to_text(info.get("jobDescription")))
        job.employment_type = info.get("timeType") or job.employment_type
        if info.get("startDate"):
            job.posted_at = info["startDate"][:10]
        job.url = info.get("externalUrl") or job.url
        job.details_loaded = True
        return job
