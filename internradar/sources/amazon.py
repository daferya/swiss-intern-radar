"""amazon.jobs public search JSON (no key)."""

from __future__ import annotations

from datetime import datetime

from ..models import SourceError
from ..text import html_to_text
from . import Source


class Amazon(Source):
    ats = "amazon"

    @property
    def label(self) -> str:
        return "amazon:jobs"

    @property
    def board_url(self) -> str:
        return "https://www.amazon.jobs/en/locations/switzerland"

    async def list_jobs(self):
        seen = {}
        for q in self.spec.get("queries") or ["intern", "internship", "student"]:
            data = await self.fetcher.get_json(
                "https://www.amazon.jobs/en/search.json",
                params={"base_query": q, "loc_query": self.spec.get("country", "Switzerland"),
                        "result_limit": 100, "offset": 0, "sort": "recent"},
            )
            if not isinstance(data, dict) or "jobs" not in data:
                raise SourceError("unexpected amazon.jobs payload")
            for j in data["jobs"]:
                jid = str(j.get("id_icims") or j.get("id") or j.get("job_path"))
                if jid in seen:
                    continue
                posted = None
                try:
                    posted = datetime.strptime(j.get("posted_date", ""), "%B %d, %Y").date().isoformat()
                except ValueError:
                    pass
                desc = "\n\n".join(html_to_text(j.get(k)) for k in ("description", "basic_qualifications", "preferred_qualifications") if j.get(k))
                seen[jid] = self.job(
                    external_id=jid,
                    title=(j.get("title") or "").strip(),
                    url="https://www.amazon.jobs" + (j.get("job_path") or ""),
                    locations=[x for x in [j.get("location"), j.get("normalized_location")] if x],
                    country_codes=[j["country_code"]] if j.get("country_code") else [],
                    department=j.get("job_category") or None,
                    employment_type=j.get("job_schedule_type"),
                    posted_at=posted,
                    description=desc,
                )
        return list(seen.values())
