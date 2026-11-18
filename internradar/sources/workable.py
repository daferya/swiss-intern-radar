"""Workable public widget API (no key): apply.workable.com/api/v1/widget/accounts/{slug}?details=true"""

from __future__ import annotations

from ..models import SourceError
from ..text import html_to_text
from . import Source


class Workable(Source):
    ats = "workable"

    @property
    def board_url(self) -> str:
        return f"https://apply.workable.com/{self.spec['slug']}/"

    async def list_jobs(self):
        slug = self.spec["slug"]
        data = await self.fetcher.get_json(
            f"https://apply.workable.com/api/v1/widget/accounts/{slug}", params={"details": "true"}
        )
        if not isinstance(data, dict) or "jobs" not in data:
            raise SourceError("unexpected Workable payload")
        out = []
        for j in data["jobs"]:
            locs, ccs = [], []
            main = ", ".join(x for x in [j.get("city"), j.get("state"), j.get("country")] if x)
            if main:
                locs.append(main)
            for loc in j.get("locations") or []:
                if loc.get("hidden"):
                    continue
                s = ", ".join(x for x in [loc.get("city"), loc.get("region"), loc.get("country")] if x)
                if s and s not in locs:
                    locs.append(s)
                if loc.get("countryCode"):
                    ccs.append(loc["countryCode"])
            shortcode = j.get("shortcode") or j.get("code") or ""
            desc = "\n\n".join(html_to_text(j.get(k)) for k in ("description", "requirements", "benefits") if j.get(k))
            out.append(self.job(
                external_id=str(shortcode or j.get("url")),
                title=(j.get("title") or "").strip(),
                url=j.get("url") or j.get("shortlink") or f"https://apply.workable.com/{slug}/j/{shortcode}/",
                locations=locs,
                country_codes=ccs,
                remote=j.get("telecommuting"),
                department=j.get("department") or j.get("function") or None,
                employment_type=j.get("employment_type"),
                posted_at=(j.get("published_on") or j.get("created_at") or "")[:10] or None,
                description=desc,
            ))
        return out
