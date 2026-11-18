"""Lever postings API (public, no key): https://github.com/lever/postings-api"""

from __future__ import annotations

from datetime import datetime, timezone

from ..classify import salary_from_struct
from ..models import SourceError
from ..text import clean_ws, html_to_text
from . import Source

HOSTS = {"global": "https://api.lever.co", "eu": "https://api.eu.lever.co"}


class Lever(Source):
    ats = "lever"

    @property
    def board_url(self) -> str:
        eu = ".eu" if getattr(self, "_region", self.spec.get("region")) == "eu" else ""
        return f"https://jobs{eu}.lever.co/{self.spec['slug']}"

    async def list_jobs(self):
        slug = self.spec["slug"]
        regions = [self.spec["region"]] if self.spec.get("region") else ["global", "eu"]
        data, last = None, None
        for region in regions:
            try:
                data = await self.fetcher.get_json(f"{HOSTS[region]}/v0/postings/{slug}", params={"mode": "json"})
                if isinstance(data, dict) and data.get("ok") is False:
                    raise SourceError(str(data.get("error")), not_found=True)
                self._region = region
                break
            except SourceError as e:
                last = e
                data = None
                if not e.not_found:
                    raise
        if data is None:
            raise last or SourceError("site not found", not_found=True)
        if not isinstance(data, list):
            raise SourceError("unexpected Lever payload")

        out = []
        for p in data:
            cats = p.get("categories") or {}
            locs = cats.get("allLocations") or ([cats["location"]] if cats.get("location") else [])
            parts = [p.get("descriptionPlain") or html_to_text(p.get("description"))]
            for lst in p.get("lists") or []:
                parts.append(f"{lst.get('text', '')}\n{html_to_text(lst.get('content'))}")
            parts.append(p.get("additionalPlain") or html_to_text(p.get("additional")))
            created = p.get("createdAt")
            posted = (datetime.fromtimestamp(created / 1000, tz=timezone.utc).date().isoformat()
                      if isinstance(created, (int, float)) else None)
            sr = p.get("salaryRange") or {}
            out.append(self.job(
                external_id=str(p.get("id")),
                title=(p.get("text") or "").strip(),
                url=p.get("hostedUrl") or f"{self.board_url}/{p.get('id')}",
                locations=locs,
                country_codes=[p["country"]] if p.get("country") else [],
                remote=(p.get("workplaceType") == "remote") if p.get("workplaceType") else None,
                department=" / ".join(x for x in [cats.get("department"), cats.get("team")] if x) or None,
                employment_type=cats.get("commitment"),
                posted_at=posted,
                description=clean_ws("\n\n".join(x for x in parts if x)),
                salary=salary_from_struct(sr.get("min"), sr.get("max"), sr.get("currency"), sr.get("interval")) if sr else None,
            ))
        return out
