"""Load config.yaml (your preferences) and companies.yaml (where to look)."""

from __future__ import annotations

import copy
import os
from pathlib import Path

import yaml

from .text import slugify

ROOT = Path(__file__).resolve().parent.parent

DEFAULTS = {
    "profile": {
        "target_start": [],
        "target_duration_months": 6,
        "hide_duration_mismatch": True,
        "hide_phd_only": True,
        "hide_languages": [],
        "min_monthly_salary_chf": None,
        "kinds": ["internship"],
    },
    "filters": {
        "min_relevance": 35,
        "keep_kinds": ["internship", "thesis", "working_student"],
        "exclude_title_keywords": [],
        "drop_stale_after_days": 10,
    },
    "scraper": {
        "concurrency": 8,
        "per_host": 2,
        "timeout": 25,
        "max_details_per_source": 40,
        "max_pages": 10,
        "workday_search": ["intern", "internship", "praktikum", "praktikant", "stage", "stagiaire", "student", "thesis"],
        "browser": "auto",
    },
    "notify": {"only_matching": True, "max_items": 40},
    "site": {"title": "Swiss AI Internship Radar", "repo_url": ""},
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | os.PathLike | None = None) -> dict:
    p = Path(path) if path else ROOT / "config.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    return _merge(DEFAULTS, data or {})


def load_companies(path: str | os.PathLike | None = None) -> list[dict]:
    p = Path(path) if path else ROOT / "companies.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    out, keys = [], set()
    for c in data.get("companies", []):
        if c.get("enabled") is False:
            continue
        c = dict(c)
        c["key"] = c.get("key") or slugify(c["name"])
        if c["key"] in keys:
            raise ValueError(f"duplicate company key in companies.yaml: {c['key']}")
        keys.add(c["key"])
        c["sources"] = [s for s in c.get("sources", []) if s.get("enabled", True)]
        out.append(c)
    return out


def browser_enabled(cfg: dict) -> bool:
    env = os.environ.get("RADAR_BROWSER")
    if env is not None:
        return env.strip().lower() in ("1", "true", "yes", "on")
    mode = str(cfg["scraper"].get("browser", "auto")).lower()
    if mode in ("false", "off", "no", "0"):
        return False
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False
    return True
