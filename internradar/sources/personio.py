"""Personio public XML feed (no key): https://{slug}.jobs.personio.de/xml"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from ..models import SourceError
from ..text import html_to_text
from . import Source


class Personio(Source):
    ats = "personio"

    @property
    def board_url(self) -> str:
        return f"https://{self.spec['slug']}.jobs.personio.{getattr(self, '_tld', 'de')}"

    async def list_jobs(self):
        slug = self.spec["slug"]
        xml, last = None, None
        for tld in ([self.spec["tld"]] if self.spec.get("tld") else ["de", "com"]):
            try:
                xml = await self.fetcher.get_text(f"https://{slug}.jobs.personio.{tld}/xml", params={"language": "en"})
                self._tld = tld
                break
            except SourceError as e:
                last = e
                if not e.not_found:
                    raise
        if xml is None:
            raise last or SourceError("feed not found", not_found=True)
        try:
            root = ET.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
        except ET.ParseError:
            raise SourceError("Personio feed is not valid XML (wrong company name?)", not_found=True)

        out = []
        for pos in root.iter("position"):
            def t(tag):
                el = pos.find(tag)
                return (el.text or "").strip() if el is not None and el.text else ""
            jid = t("id")
            offices = [t("office")] + [(o.text or "").strip() for o in pos.findall("additionalOffices/office")]
            descs = []
            for jd in pos.findall("jobDescriptions/jobDescription"):
                name = (jd.findtext("name") or "").strip()
                val = html_to_text(jd.findtext("value") or "")
                descs.append(f"{name}\n{val}" if name else val)
            out.append(self.job(
                external_id=jid,
                title=t("name"),
                url=f"{self.board_url}/job/{jid}?language=en",
                locations=[o for o in offices if o],
                department=t("department") or None,
                employment_type=t("employmentType") or None,
                posted_at=t("createdAt")[:10] or None,
                description="\n\n".join(d for d in descs if d),
            ))
        return out
