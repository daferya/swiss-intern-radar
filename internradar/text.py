"""Small text helpers: HTML -> plain text, accent folding, snippets."""

from __future__ import annotations

import html
import re
import unicodedata
from html.parser import HTMLParser

_BLOCK_TAGS = {
    "p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
    "tr", "table", "section", "article", "header", "footer", "blockquote", "pre",
}
_SKIP_TAGS = {"script", "style", "noscript", "svg", "head"}


class _Stripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag == "li":
            self.parts.append("\n• ")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(raw: str | None) -> str:
    """Convert an HTML fragment (possibly entity-escaped, as Greenhouse returns it) to text."""
    if not raw:
        return ""
    s = raw
    # Greenhouse returns HTML that is itself HTML-escaped ("&lt;p&gt;...").
    if "&lt;" in s and "<" not in s[:200]:
        s = html.unescape(s)
    if "<" not in s:
        return clean_ws(html.unescape(s))
    p = _Stripper()
    try:
        p.feed(s)
        p.close()
    except Exception:  # malformed HTML: fall back to a regex strip
        return clean_ws(html.unescape(re.sub(r"<[^>]+>", " ", s)))
    return clean_ws("".join(p.parts))


def clean_ws(s: str) -> str:
    s = s.replace("\xa0", " ").replace("​", "")
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def fold(s: str | None) -> str:
    """Lower-case and strip accents: 'Zürich Genève' -> 'zurich geneve'."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.replace("ß", "ss").casefold()


def snippet(text: str, n: int = 420) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    if len(t) <= n:
        return t
    cut = t[:n]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > n * 0.6 else cut) + "…"


def slugify(s: str) -> str:
    s = fold(s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "x"
