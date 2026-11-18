import asyncio
import copy
import json
from datetime import date

from internradar.config import DEFAULTS, _merge
from internradar.pipeline import run

from fake_boards import COMPANIES, make_transport

CFG = _merge(DEFAULTS, {
    "profile": {"target_start": ["2027-08", "2027-09"], "target_duration_months": 6},
    "filters": {"exclude_title_keywords": ["quant", "trading"]},
})
TODAY = date(2026, 11, 18)


def _run(tmp_path, transport, today=TODAY, companies=COMPANIES):
    return asyncio.run(run(copy.deepcopy(CFG), copy.deepcopy(companies), out_dir=tmp_path,
                           transport=transport, today=today, browser=False))


def by_title(payload):
    return {j["title"]: j for j in payload["jobs"]}


def test_end_to_end(tmp_path):
    p = _run(tmp_path, make_transport())
    jobs = by_title(p)
    # Kept: Swiss internships with AI/ML/data relevance
    assert "Machine Learning Research Intern" in jobs                    # greenhouse (2nd slug guess)
    assert "Internship - Reinforcement Learning for Navigation" in jobs  # lever
    assert "Research Engineer Intern, Data" in jobs                      # ashby
    assert "Junior Machine Learning Engineer (Internship)" in jobs       # workable
    assert "ML Internship: Deep Learning for Causal Inference" in jobs   # recruitee
    assert "Machine Learning / AI Internship 80–100%, 6–12 Months" in jobs  # personio (gender tag removed)
    assert "AI Engineer/Researcher Intern" in jobs                       # smartrecruiters (CH only)
    assert "Machine Learning Intern" in jobs                             # workday
    assert "Biostatistics Intern" in jobs                                # workday multi-location
    assert "Applied Scientist Intern" in jobs                            # amazon
    assert "Data Science Intern (6 months)" in jobs                      # html + JSON-LD
    # Dropped: non-intern, US-only, HR/marketing internships, US SmartRecruiters posting
    for t in ["Software Engineer, Infrastructure", "Research Intern, Pre-training", "Talent Operations Internship",
              "Marketing Intern", "AI Engineer Intern", "HR Intern", "Forward Deployed Engineer - Zurich"]:
        assert t not in jobs, t

    ml = jobs["Machine Learning Research Intern"]
    assert ml["city"] == "Zürich" and ml["duration"]["fit"] is True and ml["start"]["label"] == "Sep 2027"
    assert ml["salary"]["min"] == 4000 and ml["fits"] is True
    assert jobs["Research Engineer Intern, Data"]["salary"] == {"min": 5000, "max": 6000, "text": "chf 5k – chf 6k • monthly"} or \
        jobs["Research Engineer Intern, Data"]["salary"]["min"] == 5000
    assert jobs["Research Engineer Intern, Data"]["start"]["label"] == "Fall 2027"
    rl = jobs["Internship - Reinforcement Learning for Navigation"]
    assert rl["start"]["label"] == "Flexible" and rl["start"]["fit"] is True and rl["duration"]["label"] == "6 mo"
    ai = jobs["AI Internship"]
    assert ai["duration"]["fit"] is False and "de" in ai["languages"] and ai["fits"] is False
    wd = jobs["Machine Learning Intern"]
    assert wd["start"]["label"] == "ASAP" and wd["start"]["fit"] is False   # ASAP in Nov 2026 != Aug 2027
    assert wd["url"].startswith("https://pharma.wd3.myworkdayjobs.com/")
    assert jobs["Biostatistics Intern"]["duration"]["fit"] is False
    assert jobs["Junior Machine Learning Engineer (Internship)"]["cities"] == ["Lausanne", "Zürich"]
    assert jobs["Data Science Intern (6 months)"]["posted_at"] == "2026-11-02"

    st = {s["key"]: s for s in p["sources"]}
    assert st["acme"]["status"] == "ok" and st["acme"]["resolved"] == "acme"
    assert st["ghost"]["status"] == "error"
    assert st["pharma"]["kept"] == 2
    assert p["stats"]["new"] == 0          # first run never announces everything as "new"

    data = json.loads((tmp_path / "jobs.json").read_text())
    assert len(data["jobs"]) == len(p["jobs"])
    assert (tmp_path / "jobs.js").read_text().startswith("window.RADAR_DATA = {")


def test_second_run_new_and_stale(tmp_path):
    _run(tmp_path, make_transport())
    # Day 2: Lever is down, one Greenhouse job disappeared, nothing else changed
    from fake_boards import GREENHOUSE
    saved = copy.deepcopy(GREENHOUSE["jobs"])
    GREENHOUSE["jobs"] = [j for j in GREENHOUSE["jobs"] if j["id"] != 111]
    GREENHOUSE["jobs"].append({**saved[0], "id": 999, "title": "Computer Vision Intern",
                               "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/999"})
    try:
        p2 = _run(tmp_path, make_transport(fail={"api.lever.co"}), today=date(2026, 11, 19))
    finally:
        GREENHOUSE["jobs"] = saved
    jobs = by_title(p2)
    assert "Machine Learning Research Intern" not in jobs           # closed posting removed
    assert jobs["Computer Vision Intern"]["first_seen"] == "2026-11-19"
    assert [j["title"] for j in p2["_new_jobs"]] == ["Computer Vision Intern"]
    rl = jobs["Internship - Reinforcement Learning for Navigation"]  # Lever failed: kept, marked stale
    assert rl["stale"] is True and rl["first_seen"] == "2026-11-18"
    assert jobs["Junior Machine Learning Engineer (Internship)"]["first_seen"] == "2026-11-18"


def test_partial_run_keeps_other_companies(tmp_path):
    _run(tmp_path, make_transport())
    p = asyncio.run(run(copy.deepcopy(CFG), copy.deepcopy(COMPANIES), out_dir=tmp_path, transport=make_transport(),
                        today=TODAY, browser=False, only_keys=["visium"]))
    titles = by_title(p)
    assert "Machine Learning Research Intern" in titles and "Junior Machine Learning Engineer (Internship)" in titles


def test_notify(tmp_path, monkeypatch):
    from internradar.notify import write_new_jobs
    _run(tmp_path, make_transport())
    from fake_boards import GREENHOUSE
    saved = copy.deepcopy(GREENHOUSE["jobs"])
    GREENHOUSE["jobs"].append({**saved[0], "id": 555, "title": "NLP Intern",
                               "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/555"})
    try:
        p2 = _run(tmp_path, make_transport(), today=date(2026, 11, 19))
    finally:
        GREENHOUSE["jobs"] = saved
    gh_out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_out))
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    n = write_new_jobs(p2, CFG, tmp_path / "out")
    assert n == 1
    md = (tmp_path / "out" / "new_jobs.md").read_text()
    assert "NLP Intern" in md and "Acme AI" in md
    assert "new_count=1" in gh_out.read_text()


def test_auto_detect_and_workday_site_discovery(tmp_path):
    companies = [
        {"name": "Robo", "key": "robo", "sector": "Robotics", "sources": [{"ats": "auto", "slugs": ["robo"]}]},
        {"name": "Nowhere", "key": "nowhere", "sector": "AI startup", "sources": [{"ats": "auto"}]},
        {"name": "Pharma", "key": "pharma", "sector": "Pharma & health",
         "sources": [{"ats": "workday", "host": "pharma.wd3.myworkdayjobs.com"}]},   # no site: discovered
    ]
    p1 = _run(tmp_path, make_transport(), companies=companies)
    st = {s["key"]: s for s in p1["sources"]}
    assert st["robo"]["auto"] == "lever:robo" and st["robo"]["status"] == "ok"
    assert st["nowhere"]["auto"].startswith("none:")
    assert st["pharma"]["status"] == "ok" and "Careers" in st["pharma"]["label"]
    titles = {j["title"] for j in p1["jobs"]}
    assert "Internship - Reinforcement Learning for Navigation" in titles and "Machine Learning Intern" in titles

    # Second run: the detected board is reused, "nowhere" is not probed again this week
    calls = []
    inner = make_transport()

    def spy(request):
        calls.append(str(request.url))
        return inner.handle_request(request)
    import httpx
    p2 = _run(tmp_path, httpx.MockTransport(spy), today=date(2026, 11, 19), companies=companies)
    st2 = {s["key"]: s for s in p2["sources"]}
    assert st2["robo"]["auto"] == "lever:robo"
    assert st2["nowhere"]["status"] == "skipped"
    assert not any("greenhouse" in c for c in calls)      # no probing on the second run
