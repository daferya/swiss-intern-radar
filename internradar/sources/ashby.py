"""Ashby public job posting API (no key): https://developers.ashbyhq.com/docs/public-job-posting-api"""

from __future__ import annotations

from ..classify import parse_salary
from ..models import SourceError
from ..text import html_to_text
from . import Source


class Ashby(Source):
    ats = "ashby"

    @property
    def board_url(self) -> str:
        return f"https://jobs.ashbyhq.com/{self.spec['slug']}"

    async def list_jobs(self):
        slug = self.spec["slug"]
        data = await self.fetcher.get_json(
            f"https://api.ashbyhq.com/posting-api/job-board/{slug}", params={"includeCompensation": "true"}
        )
        if not isinstance(data, dict) or "jobs" not in data:
            raise SourceError("unexpected Ashby payload (wrong board name?)", not_found=True)
        out = []
        for j in data["jobs"]:
            if j.get("isListed") is False:
                continue
            locs = [j.get("location") or ""]
            for sec in j.get("secondaryLocations") or []:
                locs.append(sec.get("location") or "")
            addr = ((j.get("address") or {}).get("postalAddress") or {})
            if addr:
                locs.append(", ".join(x for x in [addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")] if x))
            comp = j.get("compensation") or {}
            comp_text = comp.get("scrapeableCompensationSalarySummary") or comp.get("compensationTierSummary") or ""
            out.append(self.job(
                external_id=str(j.get("id")),
                title=(j.get("title") or "").strip(),
                url=j.get("jobUrl") or f"{self.board_url}/{j.get('id')}",
                locations=[x for x in locs if x],
                remote=j.get("isRemote"),
                department=" / ".join(x for x in [j.get("department"), j.get("team")] if x) or None,
                employment_type=j.get("employmentType"),
                posted_at=(j.get("publishedAt") or "")[:10] or None,
                description=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml")),
                salary=parse_salary(comp_text) if comp_text else None,
            ))
        return out
