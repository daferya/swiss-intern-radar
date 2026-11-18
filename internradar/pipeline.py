"""Run all sources, classify, filter, merge with the previous run and write the website data."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path

from . import classify as C
from .config import ROOT, browser_enabled
from .http import Fetcher
from .location import analyse_location, location_from_text, swiss_match
from .models import RawJob, SourceError
from .sources import registry
from .text import fold, snippet

log = logging.getLogger("internradar")

SOURCE_PRIORITY = {"html": 2, "browser": 2, "adzuna": 1}
_ALL_KW = " ".join(C._DESC_KW)
_LEGAL = re.compile(
    r"\b(ag|sa|gmbh|ltd|limited|inc|sarl|s\.a\.|llc|plc|group|holding|international|switzerland|"
    r"schweiz|suisse|europe|technologies|technology)\b"
)
_TITLE_NOISE = re.compile(r"\((?:[^)]*(?:m/|f/|w/|/x|/d|gender|alle)[^)]*)\)|\b\d{2,3}\s*(?:[-–]\s*\d{2,3})?\s*%")


_GENDER = re.compile(
    r"\s*[(\[]\s*(?:[fmwdhx*]\s*/\s*){1,4}[fmwdhx*]\s*[)\]]|\s*\((?:all genders|alle geschlechter|tous genres)\)",
    re.I,
)


def clean_title(title: str) -> str:
    """'Data Intern (f/m/d) 80-100%' -> 'Data Intern 80-100%'."""
    t = _GENDER.sub("", title or "")
    return re.sub(r"\s{2,}", " ", t).strip(" -–,") or title


def norm_company(name: str) -> str:
    s = _LEGAL.sub(" ", fold(name).replace("&", " "))
    return re.sub(r"[^a-z0-9]+", "", s)


def norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _TITLE_NOISE.sub(" ", fold(title))).strip()


def job_id(raw: RawJob) -> str:
    return hashlib.sha1(f"{raw.source}|{raw.company_key}|{raw.external_id}".encode()).hexdigest()[:12]


# ------------------------------------------------------------------------------------------
# Profile matching (the website recomputes the same score in JavaScript)
# ------------------------------------------------------------------------------------------

def match_score(rec: dict, profile: dict) -> int:
    s = rec["relevance"] * 0.5
    d = (rec.get("duration") or {}).get("fit")
    st = (rec.get("start") or {}).get("fit")
    s += 20 if d is True else (-30 if d is False else 6)
    s += 20 if st is True else (-15 if st is False else 6)
    if set(rec.get("languages") or []) & set(profile.get("hide_languages") or []):
        s -= 40
    if rec.get("phd_only"):
        s -= 30
    sal_min = profile.get("min_monthly_salary_chf")
    if sal_min and rec.get("salary") and rec["salary"]["max"] < sal_min:
        s -= 40
    return int(max(0, min(100, round(s))))


def fits_profile(rec: dict, profile: dict) -> bool:
    if rec["kind"] not in (profile.get("kinds") or ["internship"]):
        return False
    if profile.get("hide_duration_mismatch", True) and (rec.get("duration") or {}).get("fit") is False:
        return False
    if (rec.get("start") or {}).get("fit") is False and profile.get("target_start"):
        return False
    if profile.get("hide_phd_only", True) and rec.get("phd_only"):
        return False
    if set(rec.get("languages") or []) & set(profile.get("hide_languages") or []):
        return False
    sal_min = profile.get("min_monthly_salary_chf")
    if sal_min and rec.get("salary") and rec["salary"]["max"] < sal_min:
        return False
    return True


# ------------------------------------------------------------------------------------------
# Classification of one posting
# ------------------------------------------------------------------------------------------

def prefilter(raw: RawJob, cfg: dict) -> bool:
    """Cheap checks before fetching job details (saves requests)."""
    swiss, _ = swiss_match(raw.locations, raw.country_codes)
    if swiss is False:
        return False
    kind, _ = C.classify_kind(raw.title, raw.employment_type)
    if kind not in cfg["filters"]["keep_kinds"]:
        return False
    if C.is_excluded(raw.title, cfg["filters"]["exclude_title_keywords"]):
        return False
    best_case, _ = C.relevance(raw.title, raw.department, _ALL_KW)
    return best_case >= cfg["filters"]["min_relevance"]


def build_record(raw: RawJob, company: dict, cfg: dict, today: date) -> dict | None:
    profile = cfg["profile"]
    desc = raw.description or ""
    kind, flags = C.classify_kind(raw.title, raw.employment_type)
    if kind not in cfg["filters"]["keep_kinds"] or C.is_excluded(raw.title, cfg["filters"]["exclude_title_keywords"]):
        return None
    swiss, cities = swiss_match(raw.locations, raw.country_codes)
    if swiss is None and desc:
        loc = location_from_text(desc)
        if loc:
            raw.locations = [loc]
            swiss, cities = swiss_match([loc])
    if not swiss:
        return None
    rel, tracks = C.relevance(raw.title, raw.department, desc)
    if re.search(r"\b(ai|robotics)\b", fold(company.get("sector") or "")) and rel:
        rel = min(100, rel + 10)   # an internship at an AI lab / AI startup is usually AI work
    if rel < cfg["filters"]["min_relevance"]:
        return None
    display_loc = next((l for l in raw.locations if analyse_location(l)[0]), raw.locations[0] if raw.locations else "Switzerland")
    langs, lang = C.languages_required(desc) if desc else ([], "en")
    rec = {
        "id": job_id(raw),
        "title": clean_title(raw.title),
        "company": raw.company,
        "company_key": raw.company_key,
        "sector": company.get("sector") or "",
        "url": raw.url,
        "city": cities[0] if cities else None,
        "cities": cities,
        "location": display_loc,
        "remote": bool(raw.remote) or "remote" in fold(display_loc),
        "kind": kind,
        "flags": flags,
        "tracks": tracks,
        "relevance": rel,
        "duration": C.parse_duration(raw.title, desc, float(profile.get("target_duration_months") or 6)),
        "start": C.parse_start(raw.title, desc, raw.posted_at, profile.get("target_start") or [], today),
        "salary": raw.salary or C.parse_salary(desc) or C.parse_salary(raw.title),
        "languages": langs,
        "lang": lang,
        "phd_only": C.phd_only(raw.title),
        "skills": C.skills(desc),
        "department": raw.department,
        "posted_at": raw.posted_at,
        "source": raw.source,
        "origin": company["key"],
        "snippet": snippet(desc, 380),
        "details": raw.details_loaded,
    }
    rec["match"] = match_score(rec, profile)
    rec["fits"] = fits_profile(rec, profile)
    return rec


# ------------------------------------------------------------------------------------------
# Running sources
# ------------------------------------------------------------------------------------------

AUTO_RETRY_DAYS = 7


async def _auto_resolve(company: dict, spec: dict, fetcher: Fetcher) -> tuple[str, str] | None:
    """Probe the common free job-board APIs for a company whose ATS we don't know yet."""
    from .discover import _probe, slug_variants
    variants: list[str] = list(spec.get("slugs") or [])
    for n in spec.get("names") or [company["name"]]:
        variants += slug_variants(n)[:4]
    variants = list(dict.fromkeys(variants))[:6]
    atss = spec.get("ats_list") or ["greenhouse", "lever", "ashby", "workable", "recruitee", "personio"]
    results = [r for r in await asyncio.gather(*(_probe(fetcher, a, s) for a in atss for s in variants)) if r]
    found = [r for r in results if not r.get("error")]
    if spec.get("require_swiss", True):
        found = [r for r in found if r["swiss"] > 0]   # guards against a same-named company abroad
    if not found:
        if any(r.get("error") for r in results):
            raise SourceError("network errors while probing job boards; will retry next run")
        return None
    best = max(found, key=lambda r: (r["swiss"], r["jobs"]))
    return best["ats"], best["slug"]


async def _run_auto(company, spec, fetcher, settings, cfg, resolved, today):
    cached = resolved.get(f"{company['key']}|auto") or ""
    status = {"company": company["name"], "key": company["key"], "ats": "auto", "status": "error",
              "listed": 0, "kept": 0, "error": None, "label": "auto", "url": None, "ms": 0}
    if cached.startswith("none:"):
        try:
            last = date.fromisoformat(cached.split(":", 1)[1])
            if (today - last).days < AUTO_RETRY_DAYS:
                status.update(status="skipped", auto=cached,
                              error=f"skipped: no public board found on {last} (retries weekly; run `discover`)")
                return status, []
        except ValueError:
            pass
    found = tuple(cached.split(":", 1)) if cached and not cached.startswith("none:") else None
    if not found:
        try:
            found = await _auto_resolve(company, spec, fetcher)
        except SourceError as e:
            status["error"] = str(e)
            return status, []
    if not found:
        status.update(auto=f"none:{today.isoformat()}",
                      error="no Swiss postings found on Greenhouse/Lever/Ashby/Workable/Recruitee/Personio")
        return status, []
    ats, slug = found
    st, cands = await _run_one(company, {"ats": ats, "slug": slug}, fetcher, settings, cfg, resolved)
    st["auto"] = f"{ats}:{slug}"
    if st["status"] == "error":
        st["auto"] = None   # resolved board stopped working: probe again next run
    return st, cands


async def _run_one(company: dict, spec: dict, fetcher: Fetcher, settings: dict, cfg: dict,
                   resolved: dict) -> tuple[dict, list[RawJob]]:
    reg = registry()
    ats = spec.get("ats")
    if ats == "auto":
        return await _run_auto(company, spec, fetcher, settings, cfg, resolved, settings["today"])
    cls = reg.get(ats)
    status = {"company": company["name"], "key": company["key"], "ats": ats, "status": "error",
              "listed": 0, "kept": 0, "error": None, "label": ats, "url": None, "ms": 0}
    if cls is None:
        status["error"] = f"unknown ats '{ats}'"
        return status, []
    slugs = spec.get("slug")
    candidates = slugs if isinstance(slugs, list) else [slugs]
    prev = resolved.get(f"{company['key']}|{ats}")
    if prev in candidates:
        candidates = [prev] + [c for c in candidates if c != prev]

    t0 = time.monotonic()
    for i, slug in enumerate(candidates):
        s = dict(spec, slug=slug) if slug is not None else dict(spec)
        src = cls(company, s, fetcher, settings)
        status["label"] = src.label
        try:
            raws = await src.list_jobs()
        except SourceError as e:
            if e.not_found and i + 1 < len(candidates):
                continue
            msg = str(e)
            if e.not_found and ats not in ("html", "browser"):
                ident = slug or spec.get("host") or ""
                msg = f"not found: no {ats} board '{ident}' (check the slug, or run `discover`)"
            status["status"] = "skipped" if msg.startswith("skipped") else "error"
            status["error"] = msg[:300]
            status["url"] = src.board_url
            status["ms"] = int((time.monotonic() - t0) * 1000)
            return status, []
        except Exception as e:  # a bug in one adapter must not kill the run
            log.exception("source crashed: %s %s", company["name"], src.label)
            status["error"] = f"crash: {e!r}"[:300]
            status["ms"] = int((time.monotonic() - t0) * 1000)
            return status, []

        cands = [r for r in raws if prefilter(r, cfg)]
        if src.needs_details:
            limit = int(cfg["scraper"]["max_details_per_source"])
            todo = [r for r in cands if not r.details_loaded][:limit]

            async def _enrich(r):
                try:
                    await src.enrich(r)
                except Exception as e:  # keep the posting with what we know
                    log.debug("enrich failed for %s: %r", r.url, e)
            await asyncio.gather(*(_enrich(r) for r in todo))
        status.update(status="ok" if raws else "empty", listed=len(raws), url=src.board_url, label=src.label,
                      ms=int((time.monotonic() - t0) * 1000), resolved=slug if isinstance(slugs, list) else None)
        if getattr(src, "empty_hint", None) and not raws:
            status["error"] = src.empty_hint
        if ats == "workday" and getattr(src, "facet_used", None) is False:
            status["note"] = "no Switzerland facet; filtered by location text"
        return status, cands
    status["error"] = "no candidate slug worked"
    return status, []


async def collect(companies: list[dict], cfg: dict, fetcher: Fetcher, settings: dict,
                  resolved: dict) -> tuple[list[tuple[dict, RawJob]], list[dict]]:
    tasks = []
    for c in companies:
        for spec in c["sources"]:
            tasks.append((c, _run_one(c, spec, fetcher, settings, cfg, resolved)))
    results = await asyncio.gather(*(t for _, t in tasks))
    raws, statuses = [], []
    for (c, _), (status, rs) in zip(tasks, results):
        statuses.append(status)
        raws += [(c, r) for r in rs]
    return raws, statuses


def _attach_known_company(raw: RawJob, known: dict[str, dict]) -> dict | None:
    """Map an aggregator posting ("Scandit AG") onto a company from companies.yaml."""
    n = norm_company(raw.company)
    for k, c in known.items():
        if n and (n == k or (len(k) >= 5 and n.startswith(k))):
            return c
    return None


def dedupe(records: list[dict]) -> list[dict]:
    best: dict[tuple, dict] = {}
    for r in records:
        key = (norm_company(r["company"]), norm_title(r["title"]), r.get("city") or "")
        cur = best.get(key)
        if cur is None:
            best[key] = r
            continue
        pr = (SOURCE_PRIORITY.get(r["source"], 3), len(r.get("snippet") or ""))
        pc = (SOURCE_PRIORITY.get(cur["source"], 3), len(cur.get("snippet") or ""))
        if pr > pc:
            best[key] = r
    return list(best.values())


# ------------------------------------------------------------------------------------------
# Output
# ------------------------------------------------------------------------------------------

def load_previous(out_dir: Path) -> dict:
    p = out_dir / "jobs.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _dump_jobs_json(payload: dict) -> str:
    """One job per line: readable git diffs when the workflow commits new data."""
    head = {k: v for k, v in payload.items() if k != "jobs"}
    lines = [json.dumps(j, ensure_ascii=False, sort_keys=True) for j in payload["jobs"]]
    body = json.dumps(head, ensure_ascii=False, indent=1, sort_keys=True)[:-1].rstrip()
    return body + ',\n "jobs": [\n' + ",\n".join(lines) + "\n ]\n}\n"


def site_url(cfg: dict) -> str:
    if cfg["site"].get("url"):
        return cfg["site"]["url"]
    repo = os.environ.get("GITHUB_REPOSITORY")
    if repo and "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner.lower()}.github.io/{name}/"
    return ""


def write_outputs(payload: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "jobs.json").write_text(_dump_jobs_json(payload), encoding="utf-8")
    js = "window.RADAR_DATA = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n"
    (out_dir / "jobs.js").write_text(js, encoding="utf-8")


async def run(cfg: dict, companies: list[dict], *, out_dir: Path | None = None, only_ats: list[str] | None = None,
              only_keys: list[str] | None = None, transport=None, today: date | None = None,
              write: bool = True, browser: bool | None = None) -> dict:
    today = today or date.today()
    out_dir = Path(out_dir) if out_dir else ROOT / "docs" / "data"
    prev = load_previous(out_dir)
    first_run = not prev.get("generated_at")
    resolved = {}
    for s in prev.get("sources", []):
        if s.get("resolved"):
            resolved[f"{s.get('key')}|{s.get('ats')}"] = s["resolved"]
        if s.get("auto"):
            resolved[f"{s.get('key')}|auto"] = s["auto"]

    selected = []
    for c in companies:
        if only_keys and c["key"] not in only_keys:
            continue
        specs = [s for s in c["sources"] if not only_ats or s.get("ats") in only_ats]
        if specs:
            selected.append({**c, "sources": specs})

    sc = cfg["scraper"]
    settings = {
        "workday_search": sc["workday_search"], "max_pages": sc["max_pages"], "today": today,
        "browser_enabled": browser_enabled(cfg) if browser is None else browser,
    }
    fetcher = Fetcher(transport=transport, concurrency=int(sc["concurrency"]), per_host=int(sc["per_host"]),
                      timeout=float(sc["timeout"]))
    t0 = time.monotonic()
    try:
        raws, statuses = await collect(selected, cfg, fetcher, settings, resolved)
    finally:
        await fetcher.close()

    known = {norm_company(c["name"]): c for c in companies}
    records = []
    for company, raw in raws:
        if raw.source == "adzuna":
            match = _attach_known_company(raw, known)
            if match:
                raw.company, raw.company_key = match["name"], match["key"]
                company = {**match, "key": company["key"]}
        rec = build_record(raw, company, cfg, today)
        if rec:
            records.append(rec)
    records = dedupe(records)
    kept_by_label = {}
    for r in records:
        kept_by_label[(r["origin"], r["source"])] = kept_by_label.get((r["origin"], r["source"]), 0) + 1
    for s in statuses:
        s["kept"] = kept_by_label.get((s["key"], s["ats"]), 0)

    # ---- merge with the previous run -------------------------------------------------------
    t_iso = today.isoformat()
    prev_jobs = {j["id"]: j for j in prev.get("jobs", [])}
    ran = {c["key"] for c in selected}
    failed = {s["key"] for s in statuses if s["status"] == "error"}
    ok_somewhere = {s["key"] for s in statuses if s["status"] in ("ok", "empty")}
    failed -= ok_somewhere   # a company with one working source is not "failed"
    current_ids = {r["id"] for r in records}
    new_jobs = []
    for r in records:
        p = prev_jobs.get(r["id"])
        r["first_seen"] = p["first_seen"] if p else t_iso
        r["last_seen"] = t_iso
        r["stale"] = False
        if p is None and not first_run:
            new_jobs.append(r)
    carried = 0
    for j in prev_jobs.values():
        if j["id"] in current_ids:
            continue
        origin = j.get("origin", j.get("company_key"))
        keep = origin not in ran  # partial run (--company / --only): leave others untouched
        if origin in failed:
            age = (today - date.fromisoformat(j.get("last_seen", t_iso))).days
            keep = age <= int(cfg["filters"]["drop_stale_after_days"])
            j["stale"] = True
        if keep:
            j["match"] = match_score(j, cfg["profile"])
            j["fits"] = fits_profile(j, cfg["profile"])
            records.append(j)
            carried += 1

    records.sort(key=lambda r: (r.get("first_seen") or "", r.get("match", 0)), reverse=True)
    n_ok = sum(1 for s in statuses if s["status"] in ("ok", "empty"))
    payload = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "site": {"title": cfg["site"].get("title"), "repo_url": cfg["site"].get("repo_url") or "", "url": site_url(cfg)},
        "profile": cfg["profile"],
        "min_relevance": cfg["filters"]["min_relevance"],
        "stats": {
            "jobs": len(records), "new": len(new_jobs), "fits": sum(1 for r in records if r.get("fits")),
            "companies": len({s["key"] for s in statuses}), "sources_ok": n_ok,
            "sources_error": sum(1 for s in statuses if s["status"] == "error"),
            "sources_skipped": sum(1 for s in statuses if s["status"] == "skipped"),
            "requests": fetcher.requests, "seconds": round(time.monotonic() - t0, 1), "carried": carried,
        },
        "sources": sorted(statuses, key=lambda s: (s["status"] != "error", s["company"].lower())),
        "jobs": records,
    }
    if write:
        write_outputs(payload, out_dir)
    payload["_new_jobs"] = new_jobs
    payload["_first_run"] = first_run
    return payload
