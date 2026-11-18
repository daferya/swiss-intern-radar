"""Optional: Adzuna aggregator API (free developer key, ~1,000 calls/month).

Catches internships at companies that are not in companies.yaml. Enabled only when the
ADZUNA_APP_ID and ADZUNA_APP_KEY environment variables are set (GitHub secrets in CI).
Register at https://developer.adzuna.com/ — no credit card.
"""

from __future__ import annotations

import os

from ..classify import salary_from_struct
from ..models import RawJob, SourceError
from ..text import html_to_text, slugify
from . import Source

DEFAULT_QUERIES = [
    {"what": "machine learning", "what_or": "intern internship praktikum praktikant stagiaire stage"},
    {"what": "data", "what_or": "intern internship praktikum praktikant stagiaire"},
    {"what": "AI", "what_or": "intern internship praktikum praktikant stagiaire"},
    {"what": "data scientist", "what_or": "intern internship praktikum stage"},
]


class Adzuna(Source):
    ats = "adzuna"

    @property
    def label(self) -> str:
        return "adzuna:ch"

    @property
    def board_url(self) -> str:
        return "https://www.adzuna.ch"

    async def list_jobs(self):
        app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
        if not (app_id and app_key):
            raise SourceError("skipped: set ADZUNA_APP_ID / ADZUNA_APP_KEY to enable (free key)")
        seen: dict[str, RawJob] = {}
        for q in self.spec.get("queries") or DEFAULT_QUERIES:
            for page in range(1, int(self.spec.get("pages", 2)) + 1):
                params = {"app_id": app_id, "app_key": app_key, "results_per_page": 50,
                          "max_days_old": self.spec.get("max_days_old", 60), "content-type": "application/json", **q}
                data = await self.fetcher.get_json(f"https://api.adzuna.com/v1/api/jobs/ch/search/{page}", params=params)
                results = data.get("results") or []
                for r in results:
                    rid = str(r.get("id"))
                    if rid in seen:
                        continue
                    comp = ((r.get("company") or {}).get("display_name") or "Unknown").strip()
                    loc = r.get("location") or {}
                    sal = None
                    if str(r.get("salary_is_predicted", "0")) != "1":
                        sal = salary_from_struct(r.get("salary_min"), r.get("salary_max"), "CHF", "year")
                    seen[rid] = RawJob(
                        source="adzuna",
                        company=comp,
                        company_key="adzuna:" + slugify(comp),
                        external_id=rid,
                        title=html_to_text(r.get("title") or ""),
                        url=r.get("redirect_url") or "",
                        locations=[x for x in [loc.get("display_name"), ", ".join(loc.get("area") or [])] if x],
                        country_codes=["ch"],
                        employment_type=r.get("contract_time") or r.get("contract_type"),
                        posted_at=(r.get("created") or "")[:10] or None,
                        description=html_to_text(r.get("description") or ""),
                        salary=sal,
                    )
                if len(results) < 50:
                    break
        return list(seen.values())
