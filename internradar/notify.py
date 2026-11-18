"""New-internship alerts: a markdown file (turned into a GitHub issue by the workflow) and,
optionally, a push notification through ntfy.sh (free, no account: pick a secret topic name)."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import httpx

from .pipeline import site_url


def _row(j: dict) -> str:
    dur = (j.get("duration") or {}).get("label") or "–"
    start = (j.get("start") or {}).get("label") or "–"
    where = j.get("city") or j.get("location") or ""
    title = j["title"].replace("|", "/")
    star = "⭐" if j.get("fits") else ""
    langs = " ".join(f"`{l.upper()}`" for l in j.get("languages") or [])
    return f"| {star} | [{title}]({j['url']}) | {j['company']} | {where} | {dur} | {start} | {langs} |"


def write_new_jobs(payload: dict, cfg: dict, out_dir: Path) -> int:
    """Write out/new_jobs.md + out/new_jobs_title.txt. Returns the number of jobs announced."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in ("new_jobs.md", "new_jobs_title.txt"):
        (out_dir / f).unlink(missing_ok=True)
    new = payload.get("_new_jobs") or []
    if cfg["notify"].get("only_matching", True):
        new = [j for j in new if j.get("fits")]
    new.sort(key=lambda j: j.get("match", 0), reverse=True)
    n = len(new)
    _github_output("new_count", str(n))
    if not n:
        return 0
    shown = new[: int(cfg["notify"].get("max_items", 40))]
    url = site_url(cfg)
    lines = [
        f"**{n} new internship{'s' if n != 1 else ''}** matching your profile ({date.today().isoformat()}).",
        "",
        "| | Role | Company | Where | Duration | Start | Lang |",
        "|---|---|---|---|---|---|---|",
        *(_row(j) for j in shown),
    ]
    if n > len(shown):
        lines.append(f"\n…and {n - len(shown)} more.")
    if url:
        lines.append(f"\nBrowse and filter everything: {url}")
    (out_dir / "new_jobs.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out_dir / "new_jobs_title.txt").write_text(
        f"🆕 {n} new internship{'s' if n != 1 else ''} · {date.today().isoformat()}\n", encoding="utf-8")
    _ntfy(new, url)
    return n


def _github_output(key: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


def _ntfy(jobs: list[dict], url: str) -> None:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic or not jobs:
        return
    body = "\n".join(f"• {j['title']} — {j['company']} ({j.get('city') or ''})" for j in jobs[:6])
    if len(jobs) > 6:
        body += f"\n…+{len(jobs) - 6} more"
    headers = {"Title": f"{len(jobs)} new internship(s)", "Tags": "briefcase"}
    if url:
        headers["Click"] = url
    try:
        httpx.post(f"https://ntfy.sh/{topic}", content=body.encode("utf-8"), headers=headers, timeout=15)
    except httpx.HTTPError:
        pass
