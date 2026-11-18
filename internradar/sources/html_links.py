"""Generic scraper for server-rendered career pages (no JavaScript needed).

Fetches one or more listing URLs, keeps the links that match `link_pattern`, then (optionally)
opens each job page and reads the schema.org JobPosting JSON-LD most career sites embed for
Google Jobs. Works for SAP SuccessFactors career sites, many custom sites, etc.

    - type: html
      urls: ["https://careers.example.com/search/?q=intern&locationsearch=Switzerland"]
      link_pattern: "/job/[^/]+/\\d+/"
      assume_country: ch        # the listing URL is already filtered to Switzerland
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from ..location import location_from_text
from ..models import RawJob, SourceError
from ..text import clean_ws, html_to_text
from . import Source


class _Anchors(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._stack: list[list] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            self._stack.append([href, []])
        elif tag in ("br", "p", "div", "li", "span") and self._stack:
            self._stack[-1][1].append("\n")

    def handle_endtag(self, tag):
        if tag == "a" and self._stack:
            href, parts = self._stack.pop()
            if href:
                self.links.append((href, "".join(parts)))

    def handle_data(self, data):
        if self._stack:
            self._stack[-1][1].append(data)


def extract_anchors(html: str, base_url: str) -> list[tuple[str, str]]:
    p = _Anchors()
    try:
        p.feed(html)
    except Exception:
        pass
    return [(urljoin(base_url, h.strip()), t) for h, t in p.links if h and not h.startswith(("#", "mailto:", "javascript:"))]


def title_from(text: str, href: str) -> tuple[str, list[str]]:
    """First non-empty line is the title; the other lines may hold a location."""
    lines = [clean_ws(x) for x in re.split(r"[\n\r]+", text or "") if clean_ws(x)]
    if lines and len(lines[0]) >= 4:
        return lines[0][:200], lines[1:6]
    seg = [s for s in urlparse(href).path.split("/") if s and not s.isdigit()]
    slug = seg[-1] if seg else href
    return re.sub(r"[-_]+", " ", slug).strip().title()[:200], lines


def filter_links(anchors, link_pattern: str, exclude: str | None = None):
    rx = re.compile(link_pattern)
    ex = re.compile(exclude) if exclude else None
    seen = {}
    for href, text in anchors:
        if not rx.search(href) or (ex and ex.search(href)):
            continue
        key = href.split("#")[0]
        if key not in seen or len(text.strip()) > len(seen[key].strip()):
            seen[key] = text
    return list(seen.items())


def jsonld_jobposting(html: str) -> dict | None:
    for m in re.finditer(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", html, re.S | re.I):
        raw = m.group(1).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            try:
                data = json.loads(re.sub(r"[\x00-\x1f]", " ", raw))
            except json.JSONDecodeError:
                continue
        stack = [data]
        while stack:
            d = stack.pop()
            if isinstance(d, list):
                stack.extend(d)
            elif isinstance(d, dict):
                t = d.get("@type")
                if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
                    return d
                if "@graph" in d:
                    stack.append(d["@graph"])
    return None


def jsonld_locations(jp: dict) -> tuple[list[str], list[str]]:
    locs, ccs = [], []
    jl = jp.get("jobLocation") or []
    for loc in jl if isinstance(jl, list) else [jl]:
        addr = (loc or {}).get("address") or {}
        if isinstance(addr, str):
            locs.append(addr)
            continue
        country = addr.get("addressCountry")
        if isinstance(country, dict):
            country = country.get("name")
        s = ", ".join(x for x in [addr.get("addressLocality"), addr.get("addressRegion"), country] if isinstance(x, str) and x)
        if s:
            locs.append(s)
        if isinstance(country, str) and len(country) in (2, 3):
            ccs.append(country)
    if jp.get("jobLocationType") == "TELECOMMUTE":
        req = jp.get("applicantLocationRequirements") or {}
        for r in req if isinstance(req, list) else [req]:
            if isinstance(r, dict) and r.get("name"):
                locs.append(f"Remote - {r['name']}")
    return locs, ccs


async def enrich_from_page(fetcher, job: RawJob) -> RawJob:
    html = await fetcher.get_text(job.url)
    jp = jsonld_jobposting(html)
    if jp:
        if jp.get("title") and len(job.title) < 6:
            job.title = clean_ws(str(jp["title"]))
        job.description = html_to_text(jp.get("description") or "")
        locs, ccs = jsonld_locations(jp)
        if locs:
            job.locations = locs
        job.country_codes = list(dict.fromkeys(job.country_codes + ccs))
        et = jp.get("employmentType")
        job.employment_type = ", ".join(et) if isinstance(et, list) else (et or job.employment_type)
        if jp.get("datePosted"):
            job.posted_at = str(jp["datePosted"])[:10]
    else:
        body = re.search(r"<main[^>]*>(.*?)</main>", html, re.S | re.I)
        job.description = html_to_text(body.group(1) if body else html)[:15000]
    if not job.locations:
        loc = location_from_text(job.description)
        if loc:
            job.locations = [loc]
    job.details_loaded = True
    return job


class HtmlLinks(Source):
    ats = "html"

    @property
    def needs_details(self) -> bool:
        return bool(self.spec.get("fetch_details", True))

    @property
    def label(self) -> str:
        return f"html:{urlparse(self.spec['urls'][0]).netloc}"

    @property
    def board_url(self) -> str:
        return self.spec["urls"][0]

    def make_jobs(self, pairs) -> list[RawJob]:
        out = []
        assume = self.spec.get("assume_country")
        for href, text in pairs:
            title, rest = title_from(text, href)
            locs = [self.spec["location"]] if self.spec.get("location") else []
            for line in rest:
                if location_from_text(line):
                    locs.append(line)
                    break
            out.append(self.job(
                external_id=href,
                title=title,
                url=href,
                locations=locs,
                country_codes=[assume] if assume else [],
                details_loaded=not self.needs_details,
            ))
        return out

    async def list_jobs(self):
        pairs = []
        for url in self.spec["urls"]:
            html = await self.fetcher.get_text(url)
            pairs += filter_links(extract_anchors(html, url), self.spec["link_pattern"], self.spec.get("exclude_pattern"))
        if not pairs:
            raise SourceError("no job links matched link_pattern (page layout changed or needs JavaScript?)")
        return self.make_jobs(dict(pairs).items())

    async def enrich(self, job):
        return await enrich_from_page(self.fetcher, job)
