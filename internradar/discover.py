"""Find which free job-board API a company uses, by probing likely slugs.

    python -m internradar discover "Lakera" "DeepJudge" "Gravis Robotics"

Prints the boards that answer, how many postings they have (and how many in Switzerland),
plus a YAML snippet to paste into companies.yaml.
"""

from __future__ import annotations

import asyncio
import re

from .http import Fetcher
from .location import swiss_match
from .models import SourceError
from .sources import registry
from .text import fold

PROBE_ATS = ["greenhouse", "lever", "ashby", "workable", "recruitee", "personio", "smartrecruiters"]


def slug_variants(name: str) -> list[str]:
    base = re.sub(r"[^a-z0-9]+", "", fold(name))
    hyph = re.sub(r"[^a-z0-9]+", "-", fold(name)).strip("-")
    stripped = re.sub(r"\b(ag|sa|gmbh|ai|inc|ltd|technologies|robotics|labs?)\b", "", fold(name))
    short = re.sub(r"[^a-z0-9]+", "", stripped)
    out = []
    for s in [base, hyph, short, base + "ag", base + "sa", base + "ai", base + "hq", base + "jobs",
              base + "careers", hyph + "-ag", hyph + "-sa", hyph + "-ch", base + "ch"]:
        if s and s not in out:
            out.append(s)
    return out


async def _probe(fetcher, ats: str, slug: str) -> dict | None:
    cls = registry()[ats]
    company = {"name": slug, "key": slug, "sources": []}
    src = cls(company, {"ats": ats, "slug": slug}, fetcher, {"max_pages": 3})
    try:
        jobs = await src.list_jobs()
    except SourceError as e:
        return None if e.not_found else {"error": str(e)}
    except Exception as e:
        return {"error": repr(e)}
    if ats == "smartrecruiters" and not jobs:
        return None  # SmartRecruiters answers 200 with 0 postings for unknown companies
    swiss = sum(1 for j in jobs if swiss_match(j.locations, j.country_codes)[0])
    return {"ats": ats, "slug": slug, "jobs": len(jobs), "swiss": swiss, "url": src.board_url}


async def discover(names: list[str]) -> list[tuple[str, list[dict]]]:
    fetcher = Fetcher(concurrency=10, per_host=3, retries=0, timeout=15)
    results = []
    try:
        for name in names:
            variants = slug_variants(name)
            # SmartRecruiters identifiers are case-sensitive: also try the name as written
            sr = list(dict.fromkeys([re.sub(r"\s+", "", name), re.sub(r"\s+", "", name.title()), *variants]))
            tasks = []
            for ats in PROBE_ATS:
                for slug in (sr if ats == "smartrecruiters" else variants):
                    tasks.append(_probe(fetcher, ats, slug))
            found = [r for r in await asyncio.gather(*tasks) if r and not r.get("error")]
            results.append((name, found))
    finally:
        await fetcher.close()
    return results


def print_report(results) -> None:
    for name, found in results:
        print(f"\n## {name}")
        if not found:
            print("  nothing found on Greenhouse/Lever/Ashby/Workable/Recruitee/Personio/SmartRecruiters.")
            print("  → open their careers page and look where the 'Apply' links point (Workday? custom site?).")
            continue
        for r in sorted(found, key=lambda r: (-r["swiss"], -r["jobs"])):
            print(f"  ✓ {r['ats']:<16} slug={r['slug']:<24} {r['jobs']:>4} postings, {r['swiss']:>3} in CH   {r['url']}")
        best = max(found, key=lambda r: (r["swiss"], r["jobs"]))
        print("\n  companies.yaml snippet:")
        print(f"  - name: {name}\n    sector: AI startup\n    sources:\n      - {{ats: {best['ats']}, slug: {best['slug']}}}")
