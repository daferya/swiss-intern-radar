"""Rule-based classification of job postings (EN / FR / DE / IT).

Everything here is deterministic and free: no LLM calls. Each function works on titles and
plain-text descriptions and returns small JSON-serialisable values.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from .text import fold

# --------------------------------------------------------------------------------------------
# Kind of position: internship / thesis / working student / graduate / apprenticeship / other
# --------------------------------------------------------------------------------------------

_APPRENTICE = re.compile(
    r"\b(apprenti\w*|apprentice\w*|lehrstelle\w*|lehrling\w*|lernende\w*|berufslehre|efz|cfc|"
    r"apprendista|azubi|ausbildung)\b"
)
_INTERN = re.compile(
    r"\b(intern|interns|internship|internships|internee|"
    r"\w*praktik(?:um|a|ant|antin|anten|antinnen|antenstelle)|"
    r"stagiaire\w*|stagista|stagisti|tirocin\w*|summer student|student researcher|"
    r"research student|co-op|industrial placement|placement student|off-cycle)\b"
)
_STAGE = re.compile(r"(?:^|[\s(\[/|,:–-])stages?(?=$|[\s:)\]/|,–-])")
_STAGE_NEG = re.compile(
    r"\b(early|late|multi|growth|seed|series|next|clinical|pre|post|final|first|second|third|"
    r"one|two|three|single|back|front|on|center|centre)[\s-]+stages?\b"
)
_THESIS = re.compile(
    r"\b(masters?'? thesis|master'?s thesis|masterarbeit\w*|masters? project|master'?s project|"
    r"semester project|bachelor'?s? thesis|bachelorarbeit\w*|thesis|these de master|"
    r"travail de master|projet de master|tesi(?: di laurea)?|diplomarbeit\w*|pfe|"
    r"projet de fin d'etudes)\b"
)
_WORKING = re.compile(
    r"\b(werkstudent\w*|working students?|student assistants?|studentische\w* "
    r"(?:hilfskraft|mitarbeiter\w*|aushilfe)|student jobs?|job etudiant|hilfsassistent\w*|"
    r"student workers?|part-time students?)\b"
)
_GRADUATE = re.compile(
    r"\b(graduate program\w*|graduate programme|trainee\w*|graduate trainee|new grad\w*|"
    r"university grad\w*|young graduate|rotational program\w*)\b"
)


def classify_kind(title: str, employment_type: str | None = None) -> tuple[str, list[str]]:
    t = fold(title)
    et = fold(employment_type or "")
    flags: list[str] = []
    if _THESIS.search(t):
        flags.append("thesis")
    if _WORKING.search(t):
        flags.append("working_student")
    if _APPRENTICE.search(t):
        return "apprenticeship", flags
    stage = bool(_STAGE.search(t)) and not _STAGE_NEG.search(t)
    if _INTERN.search(t) or stage or _INTERN.search(et) or et in ("stage", "stagiaire"):
        return "internship", flags
    if "thesis" in flags:
        return "thesis", flags
    if "working_student" in flags:
        return "working_student", flags
    if _GRADUATE.search(t):
        return "graduate", flags
    return "other", flags


# --------------------------------------------------------------------------------------------
# Relevance to AI / ML / data science
# --------------------------------------------------------------------------------------------

def _rx(words: list[str]) -> list[re.Pattern]:
    return [re.compile(w) for w in words]


_AI = _rx([
    r"machine learning", r"\bml\b", r"deep learning", r"artificial intelligence", r"\bai\b",
    r"\bgen ?ai\b", r"generative", r"\bllms?\b", r"large language", r"computer vision",
    r"\bnlp\b", r"natural language", r"reinforcement learning", r"\brl\b", r"foundation model",
    r"neural", r"perception", r"mlops", r"data scien", r"applied scien", r"research scien",
    r"research engineer", r"speech", r"recommend", r"robot learning", r"autonom", r"\bki\b",
    r"\bia\b", r"apprentissage automatique", r"maschinell\w* lernen", r"intelligence artificielle",
    r"intelligenza artificiale", r"kunstliche\w* intelligenz", r"3d reconstruction", r"\bvision\b",
    r"agentic", r"\bai agents?\b",
])
_DATA = _rx([
    r"\bdata\b", r"analytic", r"statistic", r"bioinformatic", r"computational", r"algorithm",
    r"optimi[sz]ation", r"operations research", r"business intelligence", r"\bbi\b", r"donnees",
    r"\bdaten", r"\bdati\b", r"forecast", r"simulation", r"modell?ing", r"insight", r"geospatial",
    r"quantitative",
])
_TECH = _rx([
    r"software", r"engineer", r"developer", r"research", r"robotic", r"scien", r"\bit\b",
    r"informati", r"cloud", r"backend", r"full[- ]?stack", r"devops", r"\bhpc\b", r"compiler",
    r"cuda", r"\bgpu", r"platform", r"technolog", r"digital", r"automation", r"programm",
])
_NONTECH = _rx([
    r"marketing", r"\bsales\b", r"accounting", r"accountant", r"\bfinance\b",
    r"financial (planning|reporting|controlling)", r"controlling", r"treasury", r"\baudit",
    r"\btax\b", r"legal", r"\blaw\b", r"compliance", r"human resources", r"\bhr\b", r"recruit",
    r"talent", r"people (?!analytics)", r"communication", r"\bbrand", r"\bevents?\b",
    r"\boffice\b", r"reception", r"procurement", r"purchas", r"supply chain", r"logistic",
    r"customer (success|service|support)", r"business development", r"copywrit", r"content",
    r"social media", r"public relations", r"graphic design", r"facility", r"administrat",
    r"executive assistant", r"\bcook\b", r"workplace", r"employer branding", r"go-to-market",
    r"growth intern", r"outbound", r"partnerships",
])
_DESC_KW = [
    "python", "pytorch", "tensorflow", " jax", "scikit", "sklearn", "pandas", "numpy", " sql",
    "spark", "hugging face", "transformer", " llm", "machine learning", "deep learning",
    "neural network", "statistic", "computer vision", " nlp", "data science",
    "reinforcement learning", "kubernetes", "cuda", "matlab", "airflow", "mlflow", "langchain",
    "retrieval", "diffusion", "time series", "bayesian", "causal", "model training", "embedding",
]


def relevance(title: str, department: str | None = None, description: str = "") -> tuple[int, list[str]]:
    """Score 0-100: how much this looks like an AI / ML / data role, plus topic tags."""
    t = fold(title)
    d = fold(department or "")
    desc = " " + fold(description[:8000])
    ai = sum(1 for r in _AI if r.search(t))
    data = sum(1 for r in _DATA if r.search(t))
    tech = sum(1 for r in _TECH if r.search(t))
    neg = sum(1 for r in _NONTECH if r.search(t))
    score = 0
    if ai:
        score += 45 + 8 * (ai - 1)
    if data:
        score += 30 + 4 * (data - 1)
    if tech:
        score += 14 + 2 * (tech - 1)
    if not (ai or data or tech):
        # Look at the department when the title is generic ("Intern", "Praktikant")
        if any(r.search(d) for r in _AI):
            score += 30
        elif any(r.search(d) for r in _DATA + _TECH):
            score += 18
    if neg:
        score -= 22 if ai else 45
    hits = sum(1 for k in _DESC_KW if k in desc)
    generic_title = not (ai or data or tech)
    score += min(50, 6 * hits) if generic_title else min(30, 3 * hits)
    score = max(0, min(100, score))

    tracks: list[str] = []
    if ai or (hits >= 4 and (data or tech)) or (generic_title and hits >= 5):
        tracks.append("ML/AI")
    if re.search(r"data scien|statistic|analytic|insight", t):
        tracks.append("Data Science")
    if re.search(r"data engineer|data platform|\betl\b|data pipeline|analytics engineer", t):
        tracks.append("Data Eng")
    if re.search(r"research|scientist|\bphd\b", t):
        tracks.append("Research")
    if re.search(r"\bvision\b|perception|\b3d\b|\bimag|graphics", t):
        tracks.append("Vision")
    if re.search(r"\bnlp\b|\bllms?\b|language|speech|genai|gen ai|generative|agent", t):
        tracks.append("NLP/LLM")
    if re.search(r"robot|autonom|locomotion|manipulation|navigation|drone", t):
        tracks.append("Robotics")
    if re.search(r"software|developer|full[- ]?stack|backend|frontend|platform|devops|cloud", t):
        tracks.append("Software")
    if re.search(r"bio|pharma|clinical|health|genom|drug|molecul|protein|medic", t):
        tracks.append("Bio/Health")
    return score, tracks


def is_excluded(title: str, exclude_keywords: list[str]) -> bool:
    t = fold(title)
    return any(re.search(r"\b" + re.escape(fold(k)) + r"\b", t) for k in exclude_keywords or [])


# --------------------------------------------------------------------------------------------
# Duration ("6 months", "6–12 Monate", "durée : 6 mois", "13-17 weeks", "12-month internship")
# --------------------------------------------------------------------------------------------

_NUMWORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "eighteen": 18,
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "sept": 7, "huit": 8,
    "neuf": 9, "dix": 10, "onze": 11, "douze": 12,
    "ein": 1, "eine": 1, "einen": 1, "zwei": 2, "drei": 3, "vier": 4, "funf": 5, "sechs": 6,
    "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "elf": 11, "zwolf": 12,
    "uno": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6, "sette": 7,
    "otto": 8, "nove": 9, "dieci": 10, "undici": 11, "dodici": 12,
}
_NUM = r"(\d{1,2}(?:[.,]5)?|" + "|".join(sorted(_NUMWORDS, key=len, reverse=True)) + r")"
_MON = r"(?:months?|monate?n?|monats|mois|mesi|mese)\b"
_WK = r"(?:weeks?|wochen|semaines?|settimane?)\b"
_SEP = r"\s*(?:-|–|—|to|bis|a|or|oder|ou|o)\s*"
_RANGE_M = re.compile(r"\b" + _NUM + _SEP + _NUM + r"\+?[\s-]*" + _MON)
_SINGLE_M = re.compile(r"\b" + _NUM + r"(\+)?[\s-]*" + _MON)
_RANGE_W = re.compile(r"\b" + _NUM + _SEP + _NUM + r"[\s-]*" + _WK)
_SINGLE_W = re.compile(r"\b" + _NUM + r"[\s-]*" + _WK)
_YEAR = re.compile(r"\b(?:one|1|un|une|ein|eine|einem|uno)[\s-]*(?:year|jahr|jahres|an|annee|anno)\b")
_BEFORE_BAD = re.compile(
    r"(within|innerhalb|in the last|in the past|graduat|completed|abgeschlossen|dans les|entro|"
    r"older than|not older|ago|since|seit|every|each|alle)\W*$"
)
_AFTER_BAD = re.compile(
    r"^\W*(of (?:relevant |professional |work |industry )?experience|experience|berufserfahrung|"
    r"erfahrung|d'experience|di esperienza|ago|after|nach dem|nach abschluss|apres|post|"
    r"since|notice|kundigung|probation|probezeit|of (?:your )?(?:studies|study)|remaining|left|"
    r"before|prior|old)"
)
_MIN_WORDS = re.compile(r"(minimum|min\.|at least|mindestens|au moins|al meno|no less than|ideally at least)(?:\s+(?:of|von|de|di))?\W*$")
_MAX_WORDS = re.compile(r"(up to|bis zu|jusqu'a|max\.?|maximum|fino a|not more than)\W*$")


def _num(tok: str) -> float | None:
    tok = tok.strip()
    if tok in _NUMWORDS:
        return float(_NUMWORDS[tok])
    try:
        return float(tok.replace(",", "."))
    except ValueError:
        return None


def _half(x: float) -> float:
    return round(x * 2) / 2


def _scan_duration(text: str) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    taken: list[tuple[int, int]] = []

    def ok_context(m) -> bool:
        before = text[max(0, m.start() - 40):m.start()]
        after = text[m.end():m.end() + 40]
        return not (_BEFORE_BAD.search(before) or _AFTER_BAD.search(after))

    def overlaps(m) -> bool:
        return any(not (m.end() <= a or m.start() >= b) for a, b in taken)

    for rx, factor in ((_RANGE_M, 1.0), (_RANGE_W, 1 / 4.33)):
        for m in rx.finditer(text):
            a, b = _num(m.group(1)), _num(m.group(2))
            if a is None or b is None or not ok_context(m):
                continue
            a, b = sorted((_half(a * factor), _half(b * factor)))
            if 0.5 <= a <= 24 and b <= 36:
                out.append((a, b))
                taken.append((m.start(), m.end()))
    for rx, factor in ((_SINGLE_M, 1.0), (_SINGLE_W, 1 / 4.33)):
        for m in rx.finditer(text):
            if overlaps(m) or not ok_context(m):
                continue
            n = _num(m.group(1))
            if n is None:
                continue
            n = _half(n * factor)
            if not (0.5 <= n <= 24):
                continue
            before = text[max(0, m.start() - 25):m.start()]
            plus = rx is _SINGLE_M and m.group(2)
            if plus or _MIN_WORDS.search(before):
                out.append((n, max(n, 12.0)))
            elif _MAX_WORDS.search(before):
                out.append((min(3.0, n), n))
            else:
                out.append((n, n))
            taken.append((m.start(), m.end()))
    for m in _YEAR.finditer(text):
        if not overlaps(m) and ok_context(m):
            out.append((12.0, 12.0))
    return out


def parse_duration(title: str, description: str = "", target: float = 6.0) -> dict | None:
    """Return {"min","max","label","fit"} or None when no duration is stated."""
    found = _scan_duration(fold(title))
    if not found:
        found = _scan_duration(fold(description[:6000]))
    if not found:
        return None
    lo = min(a for a, _ in found)
    hi = max(b for _, b in found)
    label = f"{lo:g} mo" if lo == hi else f"{lo:g}–{hi:g} mo"
    fit = lo <= target + 0.5 and hi >= target - 0.5
    return {"min": lo, "max": hi, "label": label, "fit": fit}


# --------------------------------------------------------------------------------------------
# Start date
# --------------------------------------------------------------------------------------------

_MONTHS = {
    "january": 1, "jan": 1, "janvier": 1, "januar": 1, "janner": 1, "gennaio": 1,
    "february": 2, "feb": 2, "fevrier": 2, "februar": 2, "febbraio": 2,
    "march": 3, "mar": 3, "mars": 3, "marz": 3, "maerz": 3, "marzo": 3,
    "april": 4, "apr": 4, "avril": 4, "aprile": 4,
    "may": 5, "mai": 5, "maggio": 5,
    "june": 6, "jun": 6, "juin": 6, "juni": 6, "giugno": 6,
    "july": 7, "jul": 7, "juillet": 7, "juli": 7, "luglio": 7,
    "august": 8, "aug": 8, "aout": 8, "agosto": 8,
    "september": 9, "sep": 9, "sept": 9, "septembre": 9, "settembre": 9,
    "october": 10, "oct": 10, "octobre": 10, "oktober": 10, "ottobre": 10,
    "november": 11, "nov": 11, "novembre": 11,
    "december": 12, "dec": 12, "decembre": 12, "dezember": 12, "dicembre": 12,
}
_SEASONS = {
    "spring": (3, 5), "fruhling": (3, 5), "fruhjahr": (3, 5), "printemps": (3, 5), "primavera": (3, 5),
    "summer": (6, 8), "sommer": (6, 8), "ete": (6, 8), "estate": (6, 8),
    "fall": (9, 11), "autumn": (9, 11), "herbst": (9, 11), "automne": (9, 11), "autunno": (9, 11),
    "winter": (12, 2), "hiver": (12, 2), "inverno": (12, 2),
}
_SEASON_EN = {
    "spring": "Spring", "fruhling": "Spring", "fruhjahr": "Spring", "printemps": "Spring", "primavera": "Spring",
    "summer": "Summer", "sommer": "Summer", "ete": "Summer", "estate": "Summer",
    "fall": "Fall", "autumn": "Fall", "herbst": "Fall", "automne": "Fall", "autunno": "Fall",
    "winter": "Winter", "hiver": "Winter", "inverno": "Winter",
}
_MONTH_NAMES = "|".join(sorted(_MONTHS, key=len, reverse=True))
_SEASON_NAMES = "|".join(sorted(_SEASONS, key=len, reverse=True))
_START_KW = re.compile(
    r"\b(start(?:ing)?(?: date)?|starts|start date|begin(?:ning|s)?|beginn|eintritt(?:sdatum)?|"
    r"stellenantritt|arbeitsbeginn|starttermin|antritt|date de debut|debut|entree en fonction|"
    r"des le|a partir d[eu]|a compter d[eu]|inizio|data di inizio|available from|commencing|"
    r"commence|from|ab)\b"
)
_NEAR_START = re.compile(
    r"(start|begin|from|\bab\b|a partir|a compter|\bdes\b|debut|beginn|eintritt|inizio|\bdal?\b|"
    r"commenc|available|internship|intern\b|stage|praktik|program)"
)
_AMBIG_MONTH_TOKENS = {"may", "mar", "jan", "feb", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec", "mai"}
_ASAP = re.compile(
    r"\b(as soon as possible|asap|immediately|immediate start|ab sofort|per sofort|sofort|"
    r"des que possible|au plus vite|tout de suite|immediatement|subito|il prima possibile|"
    r"al piu presto)\b"
)
_FLEX = re.compile(
    r"\b(flexible|by arrangement|by agreement|upon agreement|on agreement|to be agreed|"
    r"to be discussed|negotiable|nach vereinbarung|nach absprache|a convenir|a definir|"
    r"any ?time|jederzeit|rolling|da concordare|year-round|throughout the year)\b"
)
_DATE_NUM = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](20\d\d)\b|\b(20\d\d)-(\d{2})-(\d{2})\b|\b(\d{1,2})[./](20\d\d)\b")
_MONTH_YEAR = re.compile(r"\b(?:\d{1,2}\.?\s*)?(" + _MONTH_NAMES + r")\.?\s*(?:\d{1,2}(?:st|nd|rd|th)?,?\s*)?(20\d\d)?\b")
_SEASON_YEAR = re.compile(r"\b(" + _SEASON_NAMES + r")(?:\s+(?:of\s+)?(20\d\d))?\b")
_ANY_MONTH_YEAR = re.compile(r"\b(" + _MONTH_NAMES + r")\.?\s+(20\d\d)\b")
_ANY_SEASON_YEAR = re.compile(r"\b(" + _SEASON_NAMES + r")\s+(20\d\d)\b|\b(20\d\d)\s+(" + _SEASON_NAMES + r")\b")
_TITLE_YEAR = re.compile(r"\b(202\d|203\d)\b")

_MONTH_LABEL = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _infer_year(month: int, ref: date) -> int:
    return ref.year + 1 if month < ref.month - 1 else ref.year


def _ym(y: int, m: int) -> int:
    return y * 12 + (m - 1)


def _start_from_window(win: str, ref: date) -> dict | None:
    m = _DATE_NUM.search(win)
    if m:
        if m.group(3):
            mo, y = int(m.group(2)), int(m.group(3))
        elif m.group(4):
            y, mo = int(m.group(4)), int(m.group(5))
        else:
            mo, y = int(m.group(7)), int(m.group(8))
        if 1 <= mo <= 12:
            return {"months": [(y, mo)], "label": f"{_MONTH_LABEL[mo]} {y}"}
    m = _SEASON_YEAR.search(win)
    if m and (m.group(2) or m.start() < 12):
        a, b = _SEASONS[m.group(1)]
        y = int(m.group(2)) if m.group(2) else _infer_year(a, ref)
        months = [(y, a), (y, (a % 12) + 1), (y if b > a else y + 1, b)]
        return {"months": months, "label": f"{_SEASON_EN[m.group(1)]} {y}"}
    for m in _MONTH_YEAR.finditer(win):
        tok = m.group(1)
        has_day = bool(re.match(r"\d", m.group(0)))
        if not m.group(2):
            # "may", "sep" ... without a year are too ambiguous ("start date may vary")
            if m.start() >= 12 or (tok in _AMBIG_MONTH_TOKENS and not has_day):
                continue
        mo = _MONTHS[tok]
        y = int(m.group(2)) if m.group(2) else _infer_year(mo, ref)
        return {"months": [(y, mo)], "label": f"{_MONTH_LABEL[mo]} {y}"}
    if _ASAP.search(win):
        return {"months": [(ref.year, ref.month)], "label": "ASAP", "asap": True}
    if _FLEX.search(win):
        return {"months": None, "label": "Flexible", "flexible": True}
    return None


def parse_start(title: str, description: str, posted: str | None, target_months: list[str],
                today: date | None = None) -> dict | None:
    """Return {"label","month","fit"}; month is "YYYY-MM" when known."""
    ref = today or date.today()
    if posted:
        try:
            ref = datetime.fromisoformat(posted[:10]).date()
        except ValueError:
            pass
    t = fold(title)
    d = fold(description[:7000])
    found = None
    # 1) "(Fall 2027)" / "September 2027" in the title
    m = _ANY_SEASON_YEAR.search(t)
    if m:
        name = m.group(1) or m.group(4)
        y = int(m.group(2) or m.group(3))
        a, b = _SEASONS[name]
        found = {"months": [(y, a), (y, (a % 12) + 1), (y if b > a else y + 1, b)], "label": f"{_SEASON_EN[name]} {y}"}
    if not found:
        m = _ANY_MONTH_YEAR.search(t)
        if m:
            mo = _MONTHS[m.group(1)]
            found = {"months": [(int(m.group(2)), mo)], "label": f"{_MONTH_LABEL[mo]} {m.group(2)}"}
    # 2) "Start date: ...", "Eintritt: 01.08.2027", "dès septembre 2027" in the description
    if not found:
        for km in _START_KW.finditer(d):
            win = d[km.end():km.end() + 60]
            res = _start_from_window(win, ref)
            if res:
                found = res
                break
    # 3) Any "Month 2027" in the description right after start-ish words (intern, stage, from...)
    if not found:
        for m in _ANY_MONTH_YEAR.finditer(d):
            if _NEAR_START.search(d[max(0, m.start() - 45):m.start()]):
                mo = _MONTHS[m.group(1)]
                found = {"months": [(int(m.group(2)), mo)], "label": f"{_MONTH_LABEL[mo]} {m.group(2)}"}
                break
    year_only = None
    if not found:
        m = _TITLE_YEAR.search(t)
        if m:
            year_only = int(m.group(1))
            found = {"months": None, "label": str(year_only)}
    if not found:
        return None

    fit = None
    targets = []
    for tm in target_months or []:
        try:
            y, mo = tm.split("-")
            targets.append(_ym(int(y), int(mo)))
        except ValueError:
            continue
    if targets:
        lo, hi = min(targets) - 1, max(targets) + 1  # one month of tolerance each side
        if found.get("flexible"):
            fit = True
        elif found.get("asap"):
            # ASAP means "around the posting date": a fit only if the ad appears close to your start.
            fit = (min(targets) - 3) <= _ym(ref.year, ref.month) <= hi
        elif found.get("months"):
            fit = any(lo <= _ym(y, mo) <= hi for y, mo in found["months"])
        elif year_only:
            ty = min(targets) // 12
            fit = None if year_only == ty else (False if year_only < ty else None)
    month = None
    if found.get("months") and len(found["months"]) == 1:
        y, mo = found["months"][0]
        month = f"{y}-{mo:02d}"
    elif found.get("months"):
        y, mo = found["months"][0]
        month = f"{y}-{mo:02d}"
    return {"label": found["label"], "month": month, "fit": fit}


# --------------------------------------------------------------------------------------------
# Salary (only when stated; never guessed)
# --------------------------------------------------------------------------------------------

_AMT = r"(\d{1,3}(?:[’'’ .,]\d{3})+|\d+(?:[.,]\d+)?)\s*(k)?"
_CUR = r"(?:chf|sfr\.?|fr\.)"
_PER = (
    r"(?:\s*(?:/|per|pro|par|a|al|each|every)?\s*(month|monat|mois|mese|monthly|monatlich|"
    r"mensuel(?:le)?|mensile|year|yr|jahr|annum|annee|anno|annual|annually|yearly|jahrlich|"
    r"annuel(?:le)?|hour|hr|stunde|heure|ora)\b)?"
)
_GROSS = r"(?:\s*(?:gross|brutto|brut|lordo|net|netto))?"
_SAL1 = re.compile(_CUR + r"\s*" + _AMT + r"(?:\s*(?:-|–|—|to|bis|a)\s*(?:" + _CUR + r"\s*)?" + _AMT + r")?" + _GROSS + _PER)
_SAL2 = re.compile(_AMT + r"(?:\s*(?:-|–|—|to|bis|a)\s*" + _AMT + r")?\s*" + _CUR + _GROSS + _PER)


def _amount(num: str | None, k: str | None) -> float | None:
    if not num:
        return None
    s = num.replace("’", "'").replace("’", "'")
    if k:
        try:
            return float(s.replace("'", "").replace(" ", "").replace(",", ".")) * 1000
        except ValueError:
            return None
    s = s.replace("'", "").replace(" ", "")
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", s):
        s = re.sub(r"[.,]", "", s)
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _to_monthly(v: float, period: str | None) -> float | None:
    p = (period or "")
    if p.startswith(("hour", "hr", "stunde", "heure", "ora")):
        return None
    if p.startswith(("year", "yr", "jahr", "annum", "annee", "anno", "annual", "yearly", "jahrlich", "annuel")):
        return v / 12
    if p:
        return v
    if v >= 15000:
        return v / 12
    if 500 <= v < 15000:
        return v
    return None


def parse_salary(text: str) -> dict | None:
    t = fold(text or "")
    for rx in (_SAL1, _SAL2):
        for m in rx.finditer(t):
            a = _amount(m.group(1), m.group(2))
            b = _amount(m.group(3), m.group(4))
            period = m.group(5)
            if a is None:
                continue
            lo = _to_monthly(a, period)
            hi = _to_monthly(b, period) if b else lo
            if lo is None or hi is None:
                continue
            lo, hi = sorted((lo, hi))
            if 500 <= lo <= 25000 and hi <= 30000:
                return {"min": int(round(lo, -1)), "max": int(round(hi, -1)), "text": m.group(0).strip()}
    return None


def salary_from_struct(min_v, max_v, currency: str | None, interval: str | None) -> dict | None:
    if (currency or "").upper() not in ("CHF", ""):
        return None
    if min_v is None and max_v is None:
        return None
    iv = fold(interval or "")
    period = "year" if ("year" in iv or "annual" in iv) else "month" if "month" in iv else ("hour" if "hour" in iv else None)
    lo = _to_monthly(float(min_v or max_v), period)
    hi = _to_monthly(float(max_v or min_v), period)
    if lo is None or hi is None:
        return None
    if not (500 <= lo <= 25000):
        return None
    return {"min": int(round(lo, -1)), "max": int(round(hi, -1)), "text": f"CHF {min_v}–{max_v} {interval or ''}".strip()}


# --------------------------------------------------------------------------------------------
# Language requirements, PhD-only, skills
# --------------------------------------------------------------------------------------------

_PLUS = re.compile(
    r"(\bplus\b|advantage|asset|nice to have|nice-to-have|desirable|beneficial|bonus|preferred|"
    r"von vorteil|wunschenswert|ein plus|un plus|un atout|atout|souhaite|apprezzat|vantaggio|helpful|"
    r"is a benefit|would be great|ideally)"
)
_LANG_PATTERNS = {
    "de": [
        r"(fluent|fluency|excellent|very good|good|strong|business[- ]fluent|business[- ]level|native|"
        r"proficien\w*|working knowledge|command)\W+(?:\w+\W+){0,4}?german\b",
        r"german\b\W+(?:\w+\W+){0,3}?(fluent|fluency|required|mandatory|must|essential|native|c1|c2|b2|proficien\w*)",
        r"deutschkenntnisse", r"deutsch\w*\W+(?:\w+\W+){0,2}?(fliessend|verhandlungssicher|muttersprache|stilsicher|c1|c2|b2|in wort und schrift)",
        r"(sehr )?gute\w* deutsch", r"(maitrise|connaissance\w*|excellente?s?|bonne?s?)\W+(?:\w+\W+){0,3}?allemand",
        r"allemand\W+(courant|indispensable|requis|exige|obligatoire|c1|c2|b2)", r"tedesco\W+(fluente|richiesto|c1|c2)",
    ],
    "fr": [
        r"(fluent|fluency|excellent|very good|good|strong|business[- ]fluent|business[- ]level|native|"
        r"proficien\w*|working knowledge|command)\W+(?:\w+\W+){0,4}?french\b",
        r"french\b\W+(?:\w+\W+){0,3}?(fluent|fluency|required|mandatory|must|essential|native|c1|c2|b2|proficien\w*)",
        r"franzosischkenntnisse", r"(maitrise|excellente?s?|tres bonne?s?|bonne?s?)\W+(?:\w+\W+){0,2}?(du |de la )?(langue )?francais\w*",
        r"francais\W+(courant|indispensable|requis|exige|obligatoire|c1|c2|b2|langue maternelle)",
    ],
}
_LANG_RX = {k: [re.compile(p) for p in v] for k, v in _LANG_PATTERNS.items()}
_STOP = {
    "de": {"der", "die", "das", "und", "mit", "fur", "wir", "sie", "ist", "bei", "eine", "von", "zu", "auf", "im", "unsere", "deine", "ihre", "du", "als"},
    "fr": {"le", "la", "les", "et", "des", "pour", "nous", "vous", "avec", "une", "du", "est", "sur", "dans", "votre", "au", "en"},
    "en": {"the", "and", "with", "for", "we", "you", "our", "are", "is", "to", "of", "in", "your", "will", "be", "an"},
}


def posting_language(text: str) -> str:
    words = re.findall(r"[a-z]+", fold(text[:2500]))
    if len(words) < 25:
        return "en"
    counts = {k: sum(1 for w in words if w in s) for k, s in _STOP.items()}
    return max(counts, key=counts.get)


def languages_required(text: str) -> tuple[list[str], str]:
    """Return (languages required beyond English, language the ad is written in)."""
    t = fold(text[:10000])
    lang = posting_language(text)
    req: list[str] = []
    for code, rxs in _LANG_RX.items():
        for rx in rxs:
            for m in rx.finditer(t):
                s = t.rfind(".", 0, m.start())
                e = t.find(".", m.end())
                sentence = t[s + 1: e if e != -1 else len(t)]
                if not _PLUS.search(sentence):
                    if code not in req:
                        req.append(code)
                    break
            if code in req:
                break
    if lang in ("de", "fr") and lang not in req:
        req.append(lang)
    return req, lang


_PHD_TITLE = re.compile(r"\b(ph\.?\s?d|doctoral|doktorand\w*)\b")
_MSC = re.compile(r"\b(ms|msc|m\.sc|master'?s?|bachelor'?s?|bs|bsc|undergrad\w*)\b")


def phd_only(title: str) -> bool:
    t = fold(title)
    return bool(_PHD_TITLE.search(t)) and not _MSC.search(_PHD_TITLE.sub("", t))


_SKILLS = [
    ("Python", r"\bpython\b"), ("PyTorch", r"pytorch"), ("TensorFlow", r"tensorflow"), ("JAX", r"\bjax\b"),
    ("scikit-learn", r"scikit|sklearn"), ("SQL", r"\bsql\b"), ("Spark", r"\bspark\b|pyspark"),
    ("C++", r"c\+\+"), ("Java", r"\bjava\b"), ("Scala", r"\bscala\b"), ("Rust", r"\brust\b"),
    ("CUDA", r"\bcuda\b"), ("Kubernetes", r"kubernetes|\bk8s\b"), ("Docker", r"\bdocker\b"),
    ("AWS", r"\baws\b"), ("GCP", r"\bgcp\b|google cloud"), ("Azure", r"\bazure\b"),
    ("LLMs", r"\bllms?\b|large language"), ("RAG", r"\brag\b|retrieval[- ]augmented"),
    ("Computer vision", r"computer vision"), ("NLP", r"\bnlp\b|natural language"),
    ("Reinforcement learning", r"reinforcement learning"), ("Statistics", r"statistic"),
    ("Time series", r"time[- ]series"), ("Causal inference", r"causal"), ("ROS", r"\bros2?\b"),
    ("MATLAB", r"matlab"), ("Tableau", r"tableau"), ("Power BI", r"power ?bi"), ("Git", r"\bgit\b"),
]
_SKILL_RX = [(n, re.compile(p)) for n, p in _SKILLS]


def skills(text: str, limit: int = 8) -> list[str]:
    t = fold(text[:12000])
    return [n for n, rx in _SKILL_RX if rx.search(t)][:limit]
