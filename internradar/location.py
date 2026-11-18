"""Decide whether a job is located in Switzerland, and normalise the city name.

Location strings from ATS feeds look like "Zürich, CH", "Lausanne, Vaud, Switzerland",
"CH, ZH, Zurich", "London; Zurich", "Remote - Switzerland", "2 Locations" ...
"""

from __future__ import annotations

import re

from .text import fold

# folded spelling -> display name.  Unambiguous: matching the name alone is enough.
_CITIES: dict[str, str] = {}


def _add(display: str, *spellings: str) -> None:
    for s in (display, *spellings):
        _CITIES[fold(s)] = display


_add("Zürich", "Zurich", "Zuerich", "Zurigo", "Oerlikon", "Altstetten")
_add("Lausanne", "Losanna")
_add("Geneva", "Genève", "Geneve", "Genf", "Ginevra")
_add("Basel", "Bâle", "Bale", "Basilea")
_add("Bern", "Berne", "Berna")
_add("Lugano")
_add("Zug", "Zoug")
_add("Lucerne", "Luzern", "Lucerna")
_add("St. Gallen", "St Gallen", "Sankt Gallen", "Saint-Gall", "St.Gallen")
_add("Winterthur")
_add("Neuchâtel", "Neuchatel", "Neuenburg")
_add("Fribourg")
_add("Sion", "Sitten")
_add("Biel", "Bienne", "Biel/Bienne")
_CITIES[fold("Cham ZG")] = "Cham"
for _c in [
    "Martigny", "Yverdon-les-Bains", "Yverdon", "Vevey", "Montreux", "Nyon", "Rolle", "Morges",
    "Renens", "Ecublens", "Prilly", "Pully", "Lutry", "Gland", "Epalinges",
    "Cheseaux-sur-Lausanne", "Crissier", "Bussigny", "Paudex", "Tolochenaz", "Eysins", "Vernier",
    "Meyrin", "Carouge", "Plan-les-Ouates", "Lancy", "Satigny", "Chur", "Aarau", "Olten",
    "Solothurn", "Thun", "Schlieren", "Dübendorf", "Opfikon", "Kloten", "Glattbrugg",
    "Wallisellen", "Dietikon", "Adliswil", "Thalwil", "Rüschlikon", "Horgen", "Wädenswil",
    "Stäfa", "Uster", "Rapperswil-Jona", "Rapperswil", "Baar", "Steinhausen", "Rotkreuz",
    "Risch-Rotkreuz", "Kaiseraugst", "Allschwil", "Muttenz", "Pratteln", "Liestal", "Villigen",
    "Würenlingen", "Brugg", "Wettingen", "Spreitenbach", "Lenzburg", "Visp", "Schaffhausen",
    "Bulle", "La Chaux-de-Fonds", "Le Locle", "Delémont", "Bellinzona", "Locarno", "Mendrisio",
    "Manno", "Pfäffikon", "Zollikon", "Küsnacht", "Meilen", "Regensdorf", "Bülach", "Hergiswil",
    "Kriens", "Ebikon", "Sursee", "Langenthal", "Zuchwil", "Untersiggenthal", "Lupfig",
    "Monthey", "Sierre", "Payerne", "Echallens", "Préverenges", "Saint-Prex", "Aubonne",
    "Etoy", "Wetzikon", "Volketswil", "Rümlang", "Männedorf", "Neuhausen am Rheinfall",
    "Freienbach", "Schwyz", "Frauenfeld", "Kreuzlingen", "Arbon", "Herisau", "Davos",
    "Gümligen", "Ittigen", "Köniz", "Ostermundigen", "Petit-Lancy", "Grand-Saconnex",
    "Le Grand-Saconnex", "Châtel-Saint-Denis", "Granges-Paccot", "Villars-sur-Glâne", "Bioggio",
    "Stabio", "Chiasso", "Wohlen", "Dättwil", "Baden-Dättwil",
]:
    _add(_c)

# These names also exist outside Switzerland: only count them when a Swiss marker is present.
_AMBIGUOUS = {fold(x): x for x in [
    "Baden", "Freiburg", "Emmen", "Buchs", "Wil", "Reinach", "Rheinfelden", "Neuhausen",
    "Burgdorf", "Birr", "Stans", "Root", "Muri", "Kilchberg", "Arlesheim", "Dornach", "Marly",
    "Altdorf", "Saint-Sulpice", "Cham",
]}

_COUNTRY_WORDS = re.compile(
    r"\b(switzerland|schweiz|suisse|svizzera|svizra|helvetia|confoederatio helvetica)\b"
)
# Upper-case ISO codes, matched on the *original* string so "ch" inside words never matches.
_COUNTRY_CODES = re.compile(r"(?<![A-Za-z])(CH|CHE)(?![A-Za-z])")
_OTHER_COUNTRY = re.compile(
    r"\b(united states|usa|u\.s\.a?\.?|united kingdom|uk|england|scotland|ireland|germany|deutschland|"
    r"france|italy|italia|austria|osterreich|netherlands|spain|espana|poland|portugal|belgium|"
    r"luxembourg|denmark|sweden|norway|finland|czech|romania|greece|hungary|india|canada|israel|"
    r"japan|china|singapore|korea|taiwan|australia|brazil|mexico|united arab emirates|uae)\b"
)
_US_STATE = re.compile(
    r",\s*(AL|AK|AZ|CA|CO|CT|DC|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|MA|MD|ME|MI|MN|MO|MS|MT|NC|ND|NH|NJ|NM|"
    r"NV|NY|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VA|VT|WA|WI|WV|WY)\b"
)
_MULTI = re.compile(r"^\s*\d+\s+(locations|standorte|sites|lieux|sedi)\s*$", re.I)
_SPLIT = re.compile(r"\s*(?:;|\||/|\n|\s+or\s+|\s+oder\s+|\s+ou\s+|\s+&\s+)\s*", re.I)


def _city_regex(names) -> re.Pattern:
    alts = sorted((re.escape(n) for n in names), key=len, reverse=True)
    return re.compile(r"(?<![a-z0-9])(" + "|".join(alts) + r")(?![a-z0-9])")


_CITY_RE = _city_regex(_CITIES)
_AMBIG_RE = _city_regex(_AMBIGUOUS)


def is_multi_placeholder(loc: str) -> bool:
    """Workday shows '3 Locations' when a job has several sites."""
    return bool(_MULTI.match(loc or ""))


def _analyse_part(part: str) -> tuple[bool, list[str]]:
    f = fold(part)
    has_country = bool(_COUNTRY_WORDS.search(f) or _COUNTRY_CODES.search(part))
    if not has_country and (_OTHER_COUNTRY.search(f) or _US_STATE.search(part)):
        return False, []  # e.g. "Geneva, IL" or "Lucerne, United States"
    cities: list[str] = []
    for m in _CITY_RE.finditer(f):
        name = _CITIES[m.group(1)]
        if name not in cities:
            cities.append(name)
    if has_country:
        for m in _AMBIG_RE.finditer(f):
            name = _AMBIGUOUS[m.group(1)]
            if name not in cities:
                cities.append(name)
    return (has_country or bool(cities)), cities


def analyse_location(loc: str) -> tuple[bool, list[str]]:
    """Return (is_swiss, cities) for one location string (which may list several places)."""
    if not loc:
        return False, []
    swiss, cities = False, []
    parts = [p for p in _SPLIT.split(loc) if p.strip()] or [loc]
    whole_ok, whole_cities = _analyse_part(loc)
    for part in parts:
        ok, cs = _analyse_part(part)
        if ok:
            swiss = True
            cities += [c for c in cs if c not in cities]
    if not swiss and whole_ok:
        # "Basel" + "Switzerland" may sit in different split parts ("Basel / Switzerland").
        swiss, cities = True, whole_cities
    return swiss, cities


def swiss_match(locations: list[str] | None, country_codes: list[str] | None = None) -> tuple[bool | None, list[str]]:
    """Decide for a job with possibly several locations.

    Returns (True, cities) if any location is in Switzerland, (False, []) if locations are
    known and none is Swiss, (None, []) if there is no usable location information.
    """
    cities: list[str] = []
    swiss = False
    known = False
    for cc in country_codes or []:
        if not cc:
            continue
        known = True
        if cc.strip().lower() in ("ch", "che", "switzerland"):
            swiss = True
    for loc in locations or []:
        if not loc or is_multi_placeholder(loc):
            continue
        known = True
        ok, cs = analyse_location(loc)
        if ok:
            swiss = True
            cities += [c for c in cs if c not in cities]
    if swiss:
        return True, cities
    return (False if known else None), []


_LOC_LINE = re.compile(
    r"(?:^|\n)\s*(?:location|locations|standort|arbeitsort|einsatzort|lieu(?: de travail)?|"
    r"luogo(?: di lavoro)?|place of work|based in|workplace)\s*[:\-–]\s*([^\n]{2,120})",
    re.I,
)


def location_from_text(text: str) -> str | None:
    """Best-effort location extraction from a free-text job page."""
    if not text:
        return None
    m = _LOC_LINE.search(text[:6000])
    if m:
        return m.group(1).strip()
    head = text[:2500]
    ok, cities = analyse_location(head)
    if cities:
        return ", ".join(cities[:3]) + ", Switzerland"
    if ok:
        return "Switzerland"
    return None
