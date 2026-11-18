"""Fake job-board responses shaped like the real public APIs, served through httpx.MockTransport."""

from __future__ import annotations

import json
import re

import httpx

GREENHOUSE = {
    "jobs": [
        {"id": 111, "title": "Machine Learning Research Intern", "updated_at": "2026-11-10T10:00:00-05:00",
         "first_published": "2026-11-09T10:00:00-05:00",
         "location": {"name": "Zürich, CH"}, "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/111",
         "departments": [{"id": 1, "name": "Research"}], "offices": [{"id": 9, "name": "Zurich", "location": "Zurich, Switzerland"}],
         "content": "&lt;p&gt;Duration: 6 months. Start date: September 2027.&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Python, PyTorch&lt;/li&gt;&lt;li&gt;Monthly salary CHF 4&#39;000&lt;/li&gt;&lt;/ul&gt;"},
        {"id": 112, "title": "Software Engineer, Infrastructure", "updated_at": "2026-11-10T10:00:00-05:00",
         "location": {"name": "Zürich, CH"}, "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/112",
         "departments": [], "offices": [], "content": "&lt;p&gt;Full-time role.&lt;/p&gt;"},
        {"id": 113, "title": "Research Intern, Pre-training", "updated_at": "2026-11-10T10:00:00-05:00",
         "location": {"name": "San Francisco, CA"}, "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/113",
         "departments": [], "offices": [], "content": "&lt;p&gt;12 weeks&lt;/p&gt;"},
    ],
    "meta": {"total": 3},
}

LEVER = [
    {"id": "aaa-1", "text": "Internship - Reinforcement Learning for Navigation", "hostedUrl": "https://jobs.lever.co/robo/aaa-1",
     "createdAt": 1762300000000, "country": "CH", "workplaceType": "hybrid",
     "categories": {"commitment": "Internship", "department": "Robotics", "team": "Navigation", "location": "Zurich, Switzerland",
                    "allLocations": ["Zurich, Switzerland"]},
     "descriptionPlain": "We are only able to consider Schengen citizens or students enrolled at ETH and EPFL who require a compulsory internship.",
     "lists": [{"text": "Internship Details", "content": "<li>Start date: any time of the year</li><li>Duration: 6 months</li>"}],
     "additionalPlain": "Fair market salary."},
    {"id": "aaa-2", "text": "Talent Operations Internship", "hostedUrl": "https://jobs.lever.co/robo/aaa-2",
     "createdAt": 1762300000000, "categories": {"commitment": "Internship", "location": "Zurich, Switzerland"},
     "descriptionPlain": "HR internship.", "lists": []},
    {"id": "aaa-3", "text": "AI Internship", "hostedUrl": "https://jobs.lever.co/robo/aaa-3",
     "createdAt": 1762300000000, "categories": {"commitment": "Internship", "location": "Zurich, Switzerland"},
     "descriptionPlain": "Deep learning, computer vision, Python, C++. Duration: 12 months. Fluent German is required.", "lists": []},
]

ASHBY = {"apiVersion": "1", "jobs": [
    {"id": "j-1", "title": "Research Engineer Intern, Data", "location": "Zurich, Switzerland", "secondaryLocations": [],
     "employmentType": "Intern", "department": "Research", "team": "Data", "isListed": True, "isRemote": False,
     "publishedAt": "2026-11-12T08:00:00.000+00:00", "jobUrl": "https://jobs.ashbyhq.com/lab/j-1",
     "descriptionPlain": "6-month internship. Start: Fall 2027. LLMs, Python.",
     "compensation": {"compensationTierSummary": "CHF 5K – CHF 6K • Monthly"}},
    {"id": "j-2", "title": "Forward Deployed Engineer - Zurich", "location": "Zurich, Switzerland", "employmentType": "FullTime",
     "isListed": True, "jobUrl": "https://jobs.ashbyhq.com/lab/j-2", "descriptionPlain": "Senior role."},
]}

WORKABLE = {"name": "Visium", "jobs": [
    {"title": "Junior Machine Learning Engineer (Internship)", "shortcode": "ABC123", "employment_type": "Other",
     "telecommuting": False, "department": "Engineering", "url": "https://apply.workable.com/j/ABC123",
     "published_on": "2026-11-01", "country": "Switzerland", "city": "Lausanne", "state": "Vaud",
     "locations": [{"country": "Switzerland", "countryCode": "CH", "city": "Lausanne", "region": "Vaud", "hidden": False},
                   {"country": "Switzerland", "countryCode": "CH", "city": "Zürich", "region": "Zurich", "hidden": False}],
     "description": "<p>Start Date: September 2027</p><p>Duration: 6-months</p><p>EPFL or ETH Student</p>"},
]}

RECRUITEE = {"offers": [
    {"id": 77, "slug": "ml-internship", "title": "ML Internship: Deep Learning for Causal Inference",
     "careers_url": "https://ethon.recruitee.com/o/ml-internship", "location": "Zürich, Switzerland", "city": "Zürich",
     "country_code": "CH", "published_at": "2026-10-20 10:00:00 UTC", "employment_type_code": "internship",
     "description": "<p>Time-series, PyTorch, causal inference.</p>", "requirements": "<p>Master student.</p>"},
]}

PERSONIO = """<?xml version="1.0" encoding="UTF-8"?>
<workzag-jobs>
  <position>
    <id>2131495</id><office>Zürich (Birmensdorferstrasse)</office><department>Data</department>
    <name>Machine Learning / AI Internship (f/m/x) 80–100%, 6–12 Months</name>
    <jobDescriptions><jobDescription><name>What you will do</name><value><![CDATA[<p>Generative AI, Python.</p>]]></value></jobDescription></jobDescriptions>
    <employmentType>intern</employmentType><createdAt>2026-08-06T10:00:00+00:00</createdAt>
  </position>
  <position>
    <id>2131496</id><office>Zürich</office><name>Marketing Intern</name>
    <employmentType>intern</employmentType><createdAt>2026-08-06T10:00:00+00:00</createdAt>
  </position>
</workzag-jobs>"""

SR_LIST = {"offset": 0, "limit": 100, "totalFound": 2, "content": [
    {"id": "744000001", "name": "AI Engineer/Researcher Intern", "releasedDate": "2026-11-05T12:00:00.000Z",
     "location": {"city": "Lausanne", "region": "VD", "country": "ch", "remote": False},
     "typeOfEmployment": {"label": "Internship"}, "department": {"label": "R&D"}},
    {"id": "744000002", "name": "AI Engineer Intern", "releasedDate": "2026-11-05T12:00:00.000Z",
     "location": {"city": "Boston", "region": "MA", "country": "us"}, "typeOfEmployment": {"label": "Internship"}},
]}
SR_DETAIL = {"id": "744000001", "postingUrl": "https://jobs.smartrecruiters.com/Nexthink/744000001-ai-engineer",
             "jobAd": {"sections": {"jobDescription": {"title": "Job Description", "text": "<p>LLM experiments, Python, SQL. Internship of 6 months starting August 2027.</p>"},
                                    "qualifications": {"title": "Qualifications", "text": "<p>MSc in Data Science</p>"}}}}

WD_FACETS = {"total": 5000, "jobPostings": [{"title": "x", "externalPath": "/job/x", "locationsText": "Basel"}], "facets": [
    {"facetParameter": "jobFamilyGroup", "values": [{"descriptor": "Research", "id": "f1", "count": 10}]},
    {"facetParameter": "locationMainGroup", "values": [
        {"facetParameter": "locationCountry", "descriptor": "Country", "values": [
            {"descriptor": "Switzerland", "id": "ch-id-123", "count": 800},
            {"descriptor": "United States of America", "id": "us-id", "count": 3000}]}]},
]}
WD_SEARCH = {"total": 2, "jobPostings": [
    {"title": "Machine Learning Intern", "externalPath": "/job/Basel-City/Machine-Learning-Intern_REQ-1",
     "locationsText": "Basel (City)", "postedOn": "Posted 3 Days Ago"},
    {"title": "Biostatistics Intern", "externalPath": "/job/Basel-City/Biostatistics-Intern_REQ-2",
     "locationsText": "2 Locations", "postedOn": "Posted Today"},
]}
WD_DETAIL = {
    "/job/Basel-City/Machine-Learning-Intern_REQ-1": {"jobPostingInfo": {
        "title": "Machine Learning Intern", "location": "Basel (City)", "country": {"descriptor": "Switzerland"},
        "jobDescription": "<p>Duration: 6 months. Start: as soon as possible.</p><p>Python, deep learning.</p>",
        "startDate": "2026-11-15", "externalUrl": "https://pharma.wd3.myworkdayjobs.com/Careers/job/Basel-City/Machine-Learning-Intern_REQ-1"}},
    "/job/Basel-City/Biostatistics-Intern_REQ-2": {"jobPostingInfo": {
        "title": "Biostatistics Intern", "location": "Basel (City)", "additionalLocations": ["Kaiseraugst"],
        "country": {"descriptor": "Switzerland"},
        "jobDescription": "<p>Statistics, R, Python. 12 months internship.</p>", "startDate": "2026-11-18"}},
}

AMAZON = {"hits": 1, "jobs": [
    {"id_icims": "3100001", "title": "Applied Scientist Intern", "location": "CH, ZH, Zurich", "country_code": "CHE",
     "job_path": "/en/jobs/3100001/applied-scientist-intern", "posted_date": "November 3, 2026",
     "description": "Machine learning research internship. Duration 6 months.", "basic_qualifications": "MSc student"},
]}

HTML_LIST = """<html><body><table>
<tr><td><a class="jobTitle-link" href="/job/Zurich-Data-Science-Intern-%286-months%29/1234501/">Data Science Intern (6 months)</a></td></tr>
<tr><td><a class="jobTitle-link" href="/job/Zurich-HR-Intern/1234502/">HR Intern</a></td></tr>
<tr><td><a href="/about">About</a></td></tr></table></body></html>"""
HTML_DETAIL = """<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@type":"JobPosting","title":"Data Science Intern (6 months)",
 "datePosted":"2026-11-02","employmentType":"INTERN",
 "jobLocation":{"@type":"Place","address":{"@type":"PostalAddress","addressLocality":"Zurich","addressCountry":"CH"}},
 "description":"&lt;p&gt;Analytics and machine learning on insurance data. Python, SQL. Start: August 2027.&lt;/p&gt;"}
</script></head><body>...</body></html>"""


def make_transport(fail: set[str] | None = None) -> httpx.MockTransport:
    """`fail` = hostnames that should return HTTP 500 (to test carry-over of stale postings)."""
    fail = fail or set()

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        host = request.url.host
        if host in fail:
            return httpx.Response(500, text="boom")
        if host == "boards-api.greenhouse.io":
            if "/boards/acme/" in url:
                return httpx.Response(200, json=GREENHOUSE)
            return httpx.Response(404, json={"status": 404, "error": "Job not found"})
        if host == "boards-api.eu.greenhouse.io":
            return httpx.Response(404, json={"status": 404})
        if host == "api.lever.co":
            if "/postings/robo" in url:
                return httpx.Response(200, json=LEVER)
            return httpx.Response(404, json={"ok": False, "error": "Document not found"})
        if host == "api.eu.lever.co":
            return httpx.Response(404, json={"ok": False, "error": "Document not found"})
        if host == "api.ashbyhq.com":
            if url.split("?")[0].endswith("/job-board/lab"):
                return httpx.Response(200, json=ASHBY)
            return httpx.Response(404, json={"success": False})
        if host == "apply.workable.com":
            if "/accounts/visium" in url:
                return httpx.Response(200, json=WORKABLE)
            return httpx.Response(404, json={"error": "not found"})
        if host.endswith(".recruitee.com"):
            if host.startswith("ethon."):
                return httpx.Response(200, json=RECRUITEE)
            return httpx.Response(404, json={"error": "not found"})
        if host.endswith("jobs.personio.de") or host.endswith("jobs.personio.com"):
            if host.startswith("comparis."):
                return httpx.Response(200, text=PERSONIO, headers={"content-type": "application/xml"})
            return httpx.Response(404, text="<html>not found</html>")
        if host == "api.smartrecruiters.com":
            if url.endswith("/postings/744000001"):
                return httpx.Response(200, json=SR_DETAIL)
            if "/companies/Nexthink/postings" in url:
                return httpx.Response(200, json=SR_LIST)
            return httpx.Response(200, json={"offset": 0, "limit": 100, "totalFound": 0, "content": []})
        if host == "pharma.wd3.myworkdayjobs.com":
            path = request.url.path
            if request.method == "GET" and path == "/":
                return httpx.Response(302, headers={"Location": "https://pharma.wd3.myworkdayjobs.com/en-US/Careers"})
            if request.method == "GET" and path == "/en-US/Careers":
                return httpx.Response(200, text="<html>careers</html>")
            if request.method == "POST" and path.endswith("/jobs"):
                body = json.loads(request.content or b"{}")
                if body.get("limit") == 1:
                    return httpx.Response(200, json=WD_FACETS)
                assert body["appliedFacets"] == {"locationCountry": ["ch-id-123"]}, body
                if body.get("searchText") == "intern" and body.get("offset") == 0:
                    return httpx.Response(200, json=WD_SEARCH)
                return httpx.Response(200, json={"total": 0, "jobPostings": []})
            m = re.search(r"/wday/cxs/pharma/Careers(/job/.+)$", path)
            if m and m.group(1) in WD_DETAIL:
                return httpx.Response(200, json=WD_DETAIL[m.group(1)])
            return httpx.Response(404, json={})
        if host == "www.amazon.jobs":
            return httpx.Response(200, json=AMAZON)
        if host == "careers.insure.example":
            if request.url.path.startswith("/search"):
                return httpx.Response(200, text=HTML_LIST)
            return httpx.Response(200, text=HTML_DETAIL)
        return httpx.Response(404, text="unknown host in test")

    return httpx.MockTransport(handler)


COMPANIES = [
    {"name": "Acme AI", "key": "acme", "sector": "AI lab", "sources": [{"ats": "greenhouse", "slug": ["acme-typo", "acme"]}]},
    {"name": "Robo AG", "key": "robo", "sector": "Robotics", "sources": [{"ats": "lever", "slug": "robo"}]},
    {"name": "Lab", "key": "lab", "sector": "AI lab", "sources": [{"ats": "ashby", "slug": "lab"}]},
    {"name": "Visium", "key": "visium", "sector": "AI consulting", "sources": [{"ats": "workable", "slug": "visium"}]},
    {"name": "Ethon", "key": "ethon", "sector": "AI startup", "sources": [{"ats": "recruitee", "slug": "ethon"}]},
    {"name": "Comparis", "key": "comparis", "sector": "Tech", "sources": [{"ats": "personio", "slug": "comparis"}]},
    {"name": "Nexthink", "key": "nexthink", "sector": "Tech", "sources": [{"ats": "smartrecruiters", "slug": "Nexthink"}]},
    {"name": "Pharma", "key": "pharma", "sector": "Pharma & health",
     "sources": [{"ats": "workday", "host": "pharma.wd3.myworkdayjobs.com", "site": "Careers"}]},
    {"name": "Amazon", "key": "amazon", "sector": "Big tech", "sources": [{"ats": "amazon"}]},
    {"name": "Insure", "key": "insure", "sector": "Insurance & finance",
     "sources": [{"ats": "html", "urls": ["https://careers.insure.example/search/?q=intern"],
                  "link_pattern": "/job/[^/?#]+/\\d+/?$", "fetch_details": True}]},
    {"name": "Ghost", "key": "ghost", "sector": "AI startup", "sources": [{"ats": "lever", "slug": "ghost"}]},
]
