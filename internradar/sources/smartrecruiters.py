"""SmartRecruiters public Posting API (no key): https://developers.smartrecruiters.com/docs/posting-api"""

from __future__ import annotations

from ..models import SourceError
from ..text import clean_ws, html_to_text
from . import Source

API = "https://api.smartrecruiters.com/v1/companies"


class SmartRecruiters(Source):
    ats = "smartrecruiters"
    needs_details = True

    @property
    def board_url(self) -> str:
        return f"https://jobs.smartrecruiters.com/{self.spec['slug']}"

    async def list_jobs(self):
        cid = self.spec["slug"]
        out, offset, total = [], 0, None
        max_pages = int(self.settings.get("max_pages", 10))
        for _ in range(max_pages):
            data = await self.fetcher.get_json(f"{API}/{cid}/postings", params={"limit": 100, "offset": offset})
            if not isinstance(data, dict) or "content" not in data:
                raise SourceError("unexpected SmartRecruiters payload")
            total = data.get("totalFound", 0) if total is None else total
            for p in data["content"]:
                loc = p.get("location") or {}
                parts = [loc.get("city"), loc.get("region"), loc.get("country", "").upper() or None]
                loc_s = loc.get("fullLocation") or ", ".join(x for x in parts if x)
                out.append(self.job(
                    external_id=str(p.get("id")),
                    title=(p.get("name") or "").strip(),
                    url=f"https://jobs.smartrecruiters.com/{cid}/{p.get('id')}",
                    locations=[loc_s] if loc_s else [],
                    country_codes=[loc["country"]] if loc.get("country") else [],
                    remote=loc.get("remote"),
                    department=(p.get("department") or {}).get("label"),
                    employment_type=(p.get("typeOfEmployment") or {}).get("label"),
                    posted_at=(p.get("releasedDate") or "")[:10] or None,
                    details_loaded=False,
                ))
            offset += 100
            if offset >= (total or 0) or not data["content"]:
                break
        if total == 0:
            self.empty_hint = "0 postings — company identifier may be wrong (it is case-sensitive)"
        return out

    async def enrich(self, job):
        cid = self.spec["slug"]
        d = await self.fetcher.get_json(f"{API}/{cid}/postings/{job.external_id}")
        sections = ((d.get("jobAd") or {}).get("sections") or {})
        parts = []
        for key in ("jobDescription", "qualifications", "additionalInformation", "companyDescription"):
            sec = sections.get(key) or {}
            if sec.get("text"):
                parts.append(f"{sec.get('title', '')}\n{html_to_text(sec['text'])}")
        job.description = clean_ws("\n\n".join(parts))
        job.url = d.get("postingUrl") or job.url
        job.details_loaded = True
        return job
