"""Greenhouse Job Board API (public, no key): https://developers.greenhouse.io/job-board.html"""

from __future__ import annotations

from ..models import SourceError
from ..text import html_to_text
from . import Source

HOSTS = {"us": "https://boards-api.greenhouse.io", "eu": "https://boards-api.eu.greenhouse.io"}


class Greenhouse(Source):
    ats = "greenhouse"

    @property
    def board_url(self) -> str:
        eu = ".eu" if getattr(self, "_region", self.spec.get("region")) == "eu" else ""
        return f"https://job-boards{eu}.greenhouse.io/{self.spec['slug']}"

    async def list_jobs(self):
        slug = self.spec["slug"]
        # Boards live in one of two regions and the slug does not say which: try both.
        regions = [self.spec["region"]] if self.spec.get("region") else ["us", "eu"]
        data, last = None, None
        for region in regions:
            try:
                data = await self.fetcher.get_json(f"{HOSTS[region]}/v1/boards/{slug}/jobs", params={"content": "true"})
                self._region = region
                break
            except SourceError as e:
                last = e
                if not e.not_found:
                    raise
        if data is None:
            raise last or SourceError("board not found", not_found=True)
        if not isinstance(data, dict) or "jobs" not in data:
            raise SourceError("unexpected Greenhouse payload")

        out = []
        for j in data["jobs"]:
            loc = ((j.get("location") or {}).get("name") or "").strip()
            offices = [(o.get("location") or o.get("name") or "").strip() for o in j.get("offices") or []]
            locs = [x for x in [loc, *offices] if x]
            depts = ", ".join(d["name"] for d in j.get("departments") or [] if d.get("name"))
            posted = (j.get("first_published") or j.get("updated_at") or "")[:10] or None
            out.append(self.job(
                external_id=str(j["id"]),
                title=(j.get("title") or "").strip(),
                url=j.get("absolute_url") or f"{self.board_url}/jobs/{j['id']}",
                locations=list(dict.fromkeys(locs)),
                department=depts or None,
                posted_at=posted,
                description=html_to_text(j.get("content")),
            ))
        return out
