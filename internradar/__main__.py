"""Command line:

    python -m internradar scrape              # fetch everything, write docs/data/, print a report
    python -m internradar scrape --notify     # ...and write out/new_jobs.md (+ ntfy push if NTFY_TOPIC set)
    python -m internradar check               # test every source without writing anything
    python -m internradar list                # print current matches in the terminal
    python -m internradar discover "Lakera"   # find a company's job-board API + slug
    python -m internradar serve               # open the website locally on http://localhost:8000
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import http.server
import json
import logging
import sys
import webbrowser
from pathlib import Path

from .config import ROOT, load_companies, load_config


def _report(payload: dict) -> None:
    st = payload["stats"]
    print(f"\n{st['jobs']} internships kept ({st['fits']} match your profile, {st['new']} new) — "
          f"{st['sources_ok']} sources OK, {st['sources_error']} failing, {st['sources_skipped']} skipped — "
          f"{st['requests']} requests in {st['seconds']}s\n")
    w = max([len(s["company"]) for s in payload["sources"]] + [8])
    for s in payload["sources"]:
        mark = {"ok": "✓", "empty": "·", "error": "✗", "skipped": "–"}.get(s["status"], "?")
        extra = s.get("error") or s.get("note") or ""
        print(f" {mark} {s['company']:<{w}}  {s['label'][:46]:<46} listed {s['listed']:>4}  kept {s['kept']:>3}  {extra[:90]}")


def _print_jobs(payload: dict, only_fits: bool) -> None:
    jobs = [j for j in payload.get("jobs", []) if j.get("fits") or not only_fits]
    jobs.sort(key=lambda j: j.get("match", 0), reverse=True)
    for j in jobs:
        dur = (j.get("duration") or {}).get("label") or "?"
        start = (j.get("start") or {}).get("label") or "?"
        langs = ",".join(j.get("languages") or []) or "-"
        print(f"{j.get('match', 0):>3}  {j['title'][:60]:<60} {j['company'][:22]:<22} {(j.get('city') or '')[:12]:<12} "
              f"{dur:<9} {start:<10} {langs:<5} {j['url']}")
    print(f"\n{len(jobs)} postings")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="internradar", description="Free Swiss AI/ML internship radar")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--config", default=None, help="path to config.yaml")
    ap.add_argument("--companies", default=None, help="path to companies.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name in ("scrape", "check"):
        p = sub.add_parser(name)
        p.add_argument("--only", help="comma-separated ATS types, e.g. greenhouse,lever")
        p.add_argument("--company", help="comma-separated company keys from companies.yaml")
        p.add_argument("--no-browser", action="store_true", help="skip Playwright sources")
        p.add_argument("--out", default=None, help="output folder (default docs/data)")
        if name == "scrape":
            p.add_argument("--notify", action="store_true", help="write out/new_jobs.md and send ntfy push")

    p = sub.add_parser("list")
    p.add_argument("--all", action="store_true", help="show everything, not only profile matches")
    p = sub.add_parser("discover")
    p.add_argument("names", nargs="+")
    p = sub.add_parser("serve")
    p.add_argument("--port", type=int, default=8000)

    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    cfg = load_config(a.config)

    if a.cmd in ("scrape", "check"):
        from .pipeline import run
        companies = load_companies(a.companies)
        payload = asyncio.run(run(
            cfg, companies,
            out_dir=Path(a.out) if a.out else None,
            only_ats=a.only.split(",") if a.only else None,
            only_keys=a.company.split(",") if a.company else None,
            write=(a.cmd == "scrape"),
            browser=False if a.no_browser else None,
        ))
        _report(payload)
        if a.cmd == "scrape" and getattr(a, "notify", False):
            from .notify import write_new_jobs
            n = write_new_jobs(payload, cfg, ROOT / "out")
            print(f"\nnotification: {n} new matching internship(s)" + (" (first run: nothing announced)" if payload["_first_run"] else ""))
        return 0

    if a.cmd == "list":
        p = ROOT / "docs" / "data" / "jobs.json"
        if not p.exists():
            print("no data yet: run `python -m internradar scrape` first")
            return 1
        _print_jobs(json.loads(p.read_text(encoding="utf-8")), only_fits=not a.all)
        return 0

    if a.cmd == "discover":
        from .discover import discover, print_report
        print_report(asyncio.run(discover(a.names)))
        return 0

    if a.cmd == "serve":
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / "docs"))
        url = f"http://localhost:{a.port}/"
        print(f"serving {ROOT / 'docs'} at {url}  (Ctrl+C to stop)")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        with http.server.ThreadingHTTPServer(("127.0.0.1", a.port), handler) as srv:
            try:
                srv.serve_forever()
            except KeyboardInterrupt:
                pass
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
