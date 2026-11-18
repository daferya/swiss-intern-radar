"""Recruitee careers-site API (public, no key): https://{slug}.recruitee.com/api/offers/"""

from __future__ import annotations

from ..classify import salary_from_struct
from ..models import SourceError
from ..text import html_to_text
from . import Source


class Recruitee(Source):
    ats = "recruitee"

    @property
    def base(self) -> str:
        host = self.spec.get("host") or f"{self.spec['slug']}.recruitee.com"
        return f"https://{host}"

    @property
    def board_url(self) -> str:
        return self.base

    async def list_jobs(self):
        data = await self.fetcher.get_json(f"{self.base}/api/offers/")
        if not isinstance(data, dict) or "offers" not in data:
            raise SourceError("unexpected Recruitee payload")
        out = []
        for o in data["offers"]:
            locs, ccs = [], []
            if o.get("location"):
                locs.append(o["location"])
            for loc in o.get("locations") or []:
                s = ", ".join(x for x in [loc.get("city"), loc.get("state"), loc.get("country")] if x)
                if s and s not in locs:
                    locs.append(s)
                if loc.get("country_code"):
                    ccs.append(loc["country_code"])
            if o.get("country_code"):
                ccs.append(o["country_code"])
            sal = o.get("salary") or {}
            desc = "\n\n".join(html_to_text(o.get(k)) for k in ("description", "requirements") if o.get(k))
            out.append(self.job(
                external_id=str(o.get("id")),
                title=(o.get("title") or "").strip(),
                url=o.get("careers_url") or f"{self.base}/o/{o.get('slug')}",
                locations=locs,
                country_codes=ccs,
                remote=o.get("remote"),
                department=o.get("department"),
                employment_type=o.get("employment_type_code"),
                posted_at=(o.get("published_at") or o.get("created_at") or "")[:10] or None,
                description=desc,
                salary=salary_from_struct(sal.get("min"), sal.get("max"), sal.get("currency"), sal.get("period")) if sal else None,
            ))
        return out
