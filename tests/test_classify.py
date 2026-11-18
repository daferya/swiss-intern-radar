from datetime import date

import pytest

from internradar import classify as C
from internradar.location import analyse_location, swiss_match

T = ["2027-08", "2027-09"]
D = date(2026, 11, 18)


@pytest.mark.parametrize("title,kind", [
    ("Machine Learning Intern 2027 (Zurich)", "internship"),
    ("Pflichtpraktikum Data Analytics", "internship"),
    ("Stage - Data Scientist (6 mois)", "internship"),
    ("Stagiaire Data Engineer", "internship"),
    ("Tirocinio Data Science", "internship"),
    ("Student Researcher 2027", "internship"),
    ("Werkstudent Data Science", "working_student"),
    ("Masterarbeit: LLM evaluation", "thesis"),
    ("Trainee Program IT", "graduate"),
    ("Apprentissage informaticien CFC", "apprenticeship"),
    ("Early-stage startup ML engineer", "other"),
    ("Coop Data Scientist", "other"),
])
def test_kind(title, kind):
    assert C.classify_kind(title)[0] == kind


def test_kind_from_employment_type():
    assert C.classify_kind("Junior ML Engineer", "Intern")[0] == "internship"


@pytest.mark.parametrize("title,low,high", [
    ("Machine Learning Intern", 40, 100),
    ("Computer Vision/Machine Learning Intern", 50, 100),
    ("People Analytics & AI Intern", 35, 100),
    ("Marketing Intern", 0, 10),
    ("Internal Revision Intern", 0, 10),
    ("Finance Intern - Personal Workspace", 0, 10),
])
def test_relevance(title, low, high):
    assert low <= C.relevance(title)[0] <= high


@pytest.mark.parametrize("text,label,fit", [
    ("Duration: 6 months. Start: September 2027.", "6 mo", True),
    ("You graduated within 12 months. The internship lasts 6 months.", "6 mo", True),
    ("Duration: Minimum 6 months; ideally 9–12 months", "6–12 mo", True),
    ("12 months internship starting January 2027", "12 mo", False),
    ("Ability to complete a 13-17 week full-time internship", "3–4 mo", False),
    ("Dauer: sechs Monate, Eintritt nach Vereinbarung", "6 mo", True),
    ("durée : 6 mois, dès septembre 2027", "6 mo", True),
    ("one-year internship", "12 mo", False),
    ("The internship lasts 4-6 months", "4–6 mo", True),
])
def test_duration(text, label, fit):
    d = C.parse_duration("Intern", text)
    assert d["label"] == label and d["fit"] is fit


def test_duration_ignores_experience():
    assert C.parse_duration("Intern", "at least 6 months of experience in Python") is None


@pytest.mark.parametrize("title,text,posted,label,fit", [
    ("X", "Start date: September 2027", None, "Sep 2027", True),
    ("Fall 2027 ML Intern", "", None, "Fall 2027", True),
    ("X", "Eintritt: 01.08.2027", None, "Aug 2027", True),
    ("X", "dès septembre 2027 pour 6 mois", None, "Sep 2027", True),
    ("X", "Start: as soon as possible", "2026-11-10", "ASAP", False),
    ("X", "Start date: any time of the year", None, "Flexible", True),
    ("X", "We are looking for an intern starting in March 2027", "2026-11-01", "Mar 2027", False),
    ("X", "Start: September", "2026-11-15", "Sep 2027", True),
])
def test_start(title, text, posted, label, fit):
    s = C.parse_start(title, text, posted, T, today=D)
    assert s["label"] == label and s["fit"] is fit


def test_start_ambiguous_may():
    assert C.parse_start("X", "The start date may vary", "2026-11-01", T, today=D) is None


@pytest.mark.parametrize("text,lo,hi", [
    ("CHF 3'500 per month", 3500, 3500),
    ("CHF 62'000 - 94'000 gross per year", 5170, 7830),
    ("Monthly salary of 4,200 CHF", 4200, 4200),
    ("CHF 4K – CHF 5K • Monthly", 4000, 5000),
])
def test_salary(text, lo, hi):
    s = C.parse_salary(text)
    assert (s["min"], s["max"]) == (lo, hi)


def test_salary_ignores_nonsense():
    assert C.parse_salary("CHF 1 billion revenue") is None
    assert C.parse_salary("CHF 25 per hour") is None


@pytest.mark.parametrize("text,req", [
    ("Fluent German is required.", ["de"]),
    ("German is a plus.", []),
    ("Very good German skills as well as good English skills", ["de"]),
    ("Maîtrise du français indispensable.", ["fr"]),
    ("Experience working with teams in Germany is excellent.", []),
])
def test_languages(text, req):
    assert C.languages_required(text)[0] == req


def test_phd():
    assert C.phd_only("Research Scientist Intern (PhD)")
    assert not C.phd_only("MS/PhD Machine Learning Intern")
    assert not C.phd_only("Data Science Intern")


@pytest.mark.parametrize("loc,ok", [
    ("Zürich, CH", True), ("CH, ZH, Zurich", True), ("London; Zurich", True), ("Remote - Switzerland", True),
    ("Geneva, IL, United States", False), ("Baden-Baden, Germany", False), ("Baden, AG, Switzerland", True),
    ("Freiburg im Breisgau", False), ("Marly-le-Roi, France", False), ("CHENNAI, INDIA", False),
    ("Rüschlikon", True), ("Remote (EMEA)", False),
])
def test_location(loc, ok):
    assert analyse_location(loc)[0] is ok


def test_swiss_match_unknown():
    assert swiss_match(["3 Locations"]) == (None, [])
    assert swiss_match([], ["ch"])[0] is True
