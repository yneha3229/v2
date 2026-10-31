"""Packet intake (plan v2 §4.2, §5.2, §5.3, §20.2 item 2; Day-check PC-4).

Mode A picks <=3 funding URLs from Company Enrich `news[]` (Web Search is the one
fallback), fetches them in ONE Web Fetch request and turns the raw HTML into
`Document`s. Mode B takes pasted text plus <=3 URLs. Both modes:

- read published and updated dates separately (an update never re-dates an event);
- hash the exact representation fetched;
- cap the packet at 6,000 words in total;
- scan for text addressed to AI agents (U2). Such text is DATA and never followed.

Date strings are ISO at their precision: "2025", "2025-08" or "2025-08-26"; the
string's length is its precision (`precision_of`). "" means unknown.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from proofroom.crustdata import match_fetch_results
from proofroom.errors import CrustError
from proofroom.graph import date_and_precision
from proofroom.models import Document

log = logging.getLogger(__name__)

MAX_WORDS = 6000
THIN_WORDS = 200
PROXIMITY_DAYS = 7
SNIPPET_CHARS = 160

# ---- dates ----------------------------------------------------------------------

_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
           "sep": 9, "oct": 10, "nov": 11, "dec": 12}
_MON = (r"(?P<mon>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|"
        r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?")
_DATE_FORMS = [  # most specific first; each is matched at the start of the remaining text
    re.compile(_MON + r"\s+(?P<d>\d{1,2})(?:st|nd|rd|th)?,?\s+(?P<y>\d{4})\b", re.I),
    re.compile(r"(?P<d>\d{1,2})(?:st|nd|rd|th)?\s+" + _MON + r",?\s+(?P<y>\d{4})\b", re.I),
    re.compile(r"(?P<y>\d{4})[-/.](?P<m>\d{1,2})[-/.](?P<d>\d{1,2})\b"),
    re.compile(_MON + r",?\s+(?P<y>\d{4})\b", re.I),
    re.compile(_MON + r"\s*['‘’ʼ`](?P<yy>\d{2})\b", re.I),
    re.compile(r"(?P<y>\d{4})[-/](?P<m>\d{1,2})\b(?![-/]\d)"),
]
_LABEL = re.compile(
    r"\b(?P<label>date\s+published|first\s+published|originally\s+published|published|posted|"
    r"released|publish\s+date|last\s+updated|updated|last\s+modified|date\s+modified|modified)"
    r"\b(?:\s+(?:on|at))?\s*[:\-–—]?\s*", re.I)


def precision_of(iso: str) -> str:
    """Precision of an ISO string produced by this module."""
    return {4: "year", 7: "month", 10: "day"}.get(len(iso or ""), "unknown")


def _iso(y: int, m: int | None = None, d: int | None = None) -> str:
    """Validated ISO at the given precision, or "" if the parts are not a real date."""
    try:
        if m is None:
            return f"{y:04d}" if 1971 <= y <= 2100 else ""
        if d is None:
            date(y, m, 1)
            return f"{y:04d}-{m:02d}" if 1971 <= y <= 2100 else ""
        date(y, m, d)
        return f"{y:04d}-{m:02d}-{d:02d}" if 1971 <= y <= 2100 else ""
    except ValueError:
        return ""


def parse_date_text(s: str) -> str:
    """Parse a human date at the START of `s` ("Aug '25", "August 26, 2025",
    "26 Aug 2025", "2025-08-26", "Aug 2025"). A stated day keeps day precision."""
    s = (s or "").strip()
    for rx in _DATE_FORMS:
        m = rx.match(s)
        if not m:
            continue
        g = m.groupdict()
        mon = _MONTHS.get((g.get("mon") or "")[:3].lower()) if g.get("mon") else None
        month = mon or (int(g["m"]) if g.get("m") else None)
        if g.get("yy"):
            year = 2000 + int(g["yy"])
        else:
            year = int(g["y"])
        day = int(g["d"]) if g.get("d") else None
        out = _iso(year, month, day)
        if out:
            return out
    return ""


def machine_date(raw: object) -> str:
    """Normalize a machine date (meta, JSON-LD, <time datetime>). Padded dates follow
    the graph rule (`YYYY-01-01` -> year, `YYYY-MM-01` -> month) unless a non-midnight
    time shows the day is real. `1970-01-01` is unknown."""
    s = str(raw or "").strip()
    if not s:
        return ""
    m = re.match(r"^(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?(?:[T ](\d{1,2}):(\d{2}))?", s)
    if m:
        y, mo, d, hh, mm = m.groups()
        if d and hh is not None and (int(hh), int(mm)) != (0, 0):
            return _iso(int(y), int(mo), int(d))
        if d:
            iso, _ = date_and_precision(f"{y}-{int(mo):02d}-{int(d):02d}")
            return iso
        if mo:
            iso, _ = date_and_precision(f"{y}-{int(mo):02d}")
            return iso
        return _iso(int(y))
    try:
        dt = parsedate_to_datetime(s)
        return _iso(dt.year, dt.month, dt.day)
    except (TypeError, ValueError, IndexError):
        pass
    return parse_date_text(s)


def labeled_dates(text: str) -> tuple[str, str]:
    """First "Published ..." and first "Updated ..." date in visible text."""
    published = updated = ""
    for m in _LABEL.finditer(text or ""):
        label = m.group("label").lower()
        value = parse_date_text(text[m.end():m.end() + 40])
        if not value:
            continue
        if any(w in label for w in ("updated", "modified")):
            updated = updated or value
        else:
            published = published or value
        if published and updated:
            break
    return published, updated


# ---- relative dates (§5.3) --------------------------------------------------------

_NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
            "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
            "a couple of": 2, "a couple": 2, "couple of": 2}
_AGO = re.compile(r"\b(?P<n>\d{1,3}|a couple of|a couple|couple of|an?|one|two|three|four|five|"
                  r"six|seven|eight|nine|ten|eleven|twelve)\s+(?P<unit>day|week|month|year)s?"
                  r"\s+(?:ago|back|earlier|before)\b", re.I)
_APPROX_WORDS = re.compile(r"\b(weeks?|months?|years?|last|earlier|recently|ago)\b", re.I)


def is_approximate(phrase: str) -> bool:
    """True when an anchored phrase gives only an approximate date. Approximate
    relative dates never create a conflict (§5.3)."""
    p = (phrase or "").lower().strip()
    if p in ("today", "this week", "this month", "this year", "yesterday"):
        return False
    m = _AGO.search(p)
    if m and m.group("unit").lower() == "day":
        return False
    return bool(_APPROX_WORDS.search(p)) or not p


def _parts(iso: str) -> tuple[int | None, int | None, int | None]:
    nums = [int(x) for x in iso.split("-")] if iso else []
    nums += [None] * (3 - len(nums))  # type: ignore[list-item]
    return nums[0], nums[1], nums[2]


def _shift_months(y: int, m: int, n: int) -> tuple[int, int]:
    k = y * 12 + (m - 1) - n
    return k // 12, k % 12 + 1


def anchor_relative(phrase: str, published: str) -> tuple[str, str]:
    """Anchor a relative date phrase to a publication date (§5.3, fin-5).

    Returns (iso, precision) with precision "day" | "month" | "year" | "unknown".
    "today"/"this week" -> the published date at its precision. "N weeks/months ago",
    "last month" -> month precision; "N years ago", "last year" -> year precision.
    Use `is_approximate(phrase)` to flag the result as approximate."""
    pub = published if precision_of(published) != "unknown" else machine_date(published)
    pprec = precision_of(pub)
    if pprec == "unknown":
        return "", "unknown"
    y, m, d = _parts(pub)
    assert y is not None
    p = re.sub(r"\s+", " ", (phrase or "").lower()).strip()

    def as_month(yy: int, mm: int) -> tuple[str, str]:
        return _iso(yy, mm), "month"

    if p in ("today", "this week", "now", "currently"):
        return pub, pprec
    if p == "this month":
        return (pub[:7], "month") if pprec != "year" else (pub, "year")
    if p in ("this year", "earlier this year", "later this year"):
        return pub[:4], "year"
    if p == "yesterday":
        if pprec == "day":
            return (date(y, m, d) - timedelta(days=1)).isoformat(), "day"  # type: ignore[arg-type]
        return pub, pprec
    if p in ("last week", "a week ago"):
        p = "1 week ago"
    if p in ("last month", "a month ago"):
        p = "1 month ago"
    if p in ("last year", "a year ago"):
        return str(y - 1), "year"

    match = _AGO.search(p)
    if not match:
        return "", "unknown"
    raw_n = match.group("n").lower()
    n = int(raw_n) if raw_n.isdigit() else _NUMBERS.get(raw_n, 0)
    unit = match.group("unit").lower()
    if n <= 0:
        return "", "unknown"
    if unit == "year":
        return str(y - n), "year"
    if pprec == "year":
        return "", "unknown"  # months/weeks before an unknown month cannot be placed
    if unit == "month":
        return as_month(*_shift_months(y, m, n))  # type: ignore[arg-type]
    base = date(y, m, d if d else 15)  # type: ignore[arg-type]
    shifted = base - timedelta(days=n * (7 if unit == "week" else 1))
    if unit == "day" and pprec == "day":
        return shifted.isoformat(), "day"
    return as_month(shifted.year, shifted.month)


# ---- HTML -> text -------------------------------------------------------------------

@dataclass
class PageText:
    title: str
    text: str
    published: str
    updated: str
    words: int


_HTML_HINT = re.compile(r"<\s*(?:!doctype|html|head|body|div|p|span|meta|article|main|section|"
                        r"h[1-6]|a|br|title|script)\b", re.I)
_BLOCKS = ("p", "div", "section", "article", "main", "h1", "h2", "h3", "h4", "h5", "h6", "li",
           "ul", "ol", "tr", "table", "blockquote", "pre", "dd", "dt", "dl", "figcaption",
           "header", "aside", "time")
_DROP = ("script", "style", "noscript", "svg", "nav", "footer", "form", "iframe", "template",
         "button", "select", "canvas")


def looks_like_html(s: str) -> bool:
    return bool(_HTML_HINT.search((s or "")[:20000]))


def _clean_lines(raw: str) -> str:
    lines = (re.sub(r"[ \t\r\f\v ​]+", " ", ln).strip() for ln in raw.split("\n"))
    out: list[str] = []
    for ln in lines:
        if ln:
            out.append(ln)
    return "\n".join(out)


def _meta(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        for attr in ("property", "name", "itemprop"):
            tag = soup.find("meta", attrs={attr: name})
            if isinstance(tag, Tag) and tag.get("content"):
                return str(tag.get("content")).strip()
    return ""


def _json_ld_dates(soup: BeautifulSoup) -> tuple[str, str]:
    found: list[tuple[bool, str, str]] = []

    def walk(obj: Any, depth: int = 0) -> None:
        if depth > 8:
            return
        if isinstance(obj, list):
            for o in obj:
                walk(o, depth + 1)
        elif isinstance(obj, dict):
            if "datePublished" in obj or "dateModified" in obj:
                kind = obj.get("@type")
                kinds = " ".join(kind) if isinstance(kind, list) else str(kind or "")
                articleish = bool(re.search(r"article|posting|report|release", kinds, re.I))
                found.append((articleish, str(obj.get("datePublished") or ""),
                              str(obj.get("dateModified") or "")))
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    walk(v, depth + 1)

    for tag in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = (tag.string or tag.get_text() or "").strip()
        raw = re.sub(r"^\s*(<!--|<!\[CDATA\[)|(-->|\]\]>)\s*$", "", raw)
        data = None
        for candidate in (raw, re.sub(r",\s*([}\]])", r"\1", raw)):
            try:
                data = json.loads(candidate, strict=False)
                break
            except ValueError:
                continue
        if data is None:
            log.debug("ignoring unparseable JSON-LD block (%d chars)", len(raw))
            continue
        walk(data)
    found.sort(key=lambda t: not t[0])  # article-like types first, stable otherwise
    pub = next((machine_date(p) for _, p, _ in found if machine_date(p)), "")
    upd = next((machine_date(u) for _, _, u in found if machine_date(u)), "")
    return pub, upd


def _time_dates(soup: BeautifulSoup) -> tuple[str, str]:
    pub = upd = ""
    for t in soup.find_all("time"):
        if not isinstance(t, Tag):
            continue
        value = machine_date(t.get("datetime") or "") or parse_date_text(t.get_text(" "))
        if not value:
            continue
        hint = " ".join([str(t.get("itemprop") or ""), " ".join(t.get("class") or [])]).lower()
        if any(w in hint for w in ("modified", "updated")):
            upd = upd or value
        else:
            pub = pub or value
    return pub, upd


def _title(soup: BeautifulSoup) -> str:
    og = _meta(soup, "og:title", "twitter:title")
    if og:
        return re.sub(r"\s+", " ", og).strip()
    if soup.title and soup.title.get_text(strip=True):
        return re.sub(r"\s+", " ", soup.title.get_text(" ")).strip()
    h1 = soup.find("h1")
    return re.sub(r"\s+", " ", h1.get_text(" ")).strip() if isinstance(h1, Tag) else ""


def _plain_text(s: str) -> PageText:
    text = _clean_lines(s.replace("\r\n", "\n"))
    title = ""
    for ln in text.split("\n")[:15]:
        m = re.match(r"^(?:#\s+|title:\s*)(.+)$", ln, re.I)
        if m:
            title = m.group(1).strip()
            break
    if not title and text:
        title = text.split("\n", 1)[0][:200]
    pub, upd = labeled_dates(text)
    return PageText(title, text, pub, upd, len(text.split()))


def extract_text(html: str) -> PageText:
    """Visible text, title and published/updated dates from raw HTML (or plain text).

    Date priority: meta (`article:published_time` / `article:modified_time`) >
    JSON-LD (`datePublished` / `dateModified`) > visible "Published ... · Updated ..."
    text > `<time datetime>`. Each date is chosen separately, so an update date never
    replaces the published date. Never raises on odd input."""
    s = html if isinstance(html, str) else ("" if html is None else str(html))
    if not s.strip():
        return PageText("", "", "", "", 0)
    if not looks_like_html(s):
        return _plain_text(s)
    try:
        soup = BeautifulSoup(s, "html.parser")
    except Exception as e:  # noqa: BLE001 - html.parser is lenient, but never crash here
        log.warning("HTML parse failed (%s); treating as plain text", type(e).__name__)
        return _plain_text(re.sub(r"<[^>]+>", " ", s))

    title = _title(soup)
    meta_pub = machine_date(_meta(soup, "article:published_time", "og:published_time",
                                  "datePublished", "publish-date", "pubdate", "date",
                                  "parsely-pub-date", "sailthru.date", "dc.date"))
    meta_upd = machine_date(_meta(soup, "article:modified_time", "og:updated_time",
                                  "dateModified", "last-modified"))
    ld_pub, ld_upd = _json_ld_dates(soup)
    time_pub, time_upd = _time_dates(soup)

    for c in soup.find_all(string=lambda x: isinstance(x, Comment)):
        c.extract()
    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for tag in soup.find_all(_BLOCKS):
        tag.insert_before(NavigableString("\n"))
        tag.append(NavigableString("\n"))
    full_text = _clean_lines(soup.get_text())
    text_pub, text_upd = labeled_dates(full_text)

    for tag in soup(list(_DROP)):
        tag.decompose()
    for header in soup.find_all("header"):
        if not header.find_parent(["article", "main"]):
            header.decompose()
    body = soup.body or soup
    candidates = [t for t in soup.find_all(["main", "article"]) if isinstance(t, Tag)]
    best = max(candidates, key=lambda t: len(t.get_text(" ").split()), default=None)
    if best is not None and len(best.get_text(" ").split()) >= 150:
        body = best
    text = _clean_lines(body.get_text())

    published = meta_pub or ld_pub or text_pub or time_pub
    updated = meta_upd or ld_upd or text_upd or time_upd
    if updated and updated == published:
        updated = ""  # an identical "update" adds nothing
    return PageText(title, text, published, updated, len(text.split()))


# ---- U2: text addressed to AI agents ------------------------------------------------

_AGENT_PATTERNS = [re.compile(p, re.I) for p in (
    r"\bfor\s+(?:ai\s+|llm\s+|coding\s+)?agents\s*[:,\-–—]",
    r"\b(?:ignore|disregard|forget|override)\s+(?:all\s+|any\s+)?(?:the\s+|your\s+)?"
    r"(?:previous|prior|above|earlier|preceding|original)\s+(?:instructions|prompts?|rules|directions)",
    r"\b(?:ai|llm)\s+(?:agents?|assistants?|models?|crawlers?|systems?)\s+(?:should|must|shall|"
    r"need\s+to|are\s+(?:instructed|required|asked))\b",
    r"\b(?:language\s+models?|chatbots?|assistants?)\s+(?:reading|parsing|processing)\s+this\b",
    r"\bif\s+you\s+are\s+an?\s+(?:ai|llm|language\s+model|agent|assistant|bot)\b",
    r"\bnote\s+to\s+(?:ai|llms?|agents?|assistants?|language\s+models?)\b",
    r"\b(?:your|the|reveal|print|override|ignore|new)\s+(?:the\s+)?system\s+prompt\b",
    r"\bmark\s+(?:all|every|each)\s+(?:the\s+)?claims?\s+(?:as\s+)?(?:supported|verified|true)\b",
    r"\bas\s+an\s+ai\s+language\s+model\b",
    r"\byou\s+are\s+now\s+(?:an?\s+|the\s+)?(?:ai|assistant|agent|chatbot|dan)\b",
    r"\bconnect\s+to\s+the\s+[\w .\-]{1,40}\s+mcp\s+server\b",
)]


def find_agent_instructions(text: str) -> list[str]:
    """Snippets (<=160 chars) of text addressed to AI agents/LLMs. These are DATA and
    are never followed; the run log only counts them (saf-2, saf-3)."""
    s = text if isinstance(text, str) else ""
    spans: list[tuple[int, int]] = []
    for rx in _AGENT_PATTERNS:
        for m in rx.finditer(s):
            spans.append((m.start(), m.end()))
    spans.sort()
    out: list[str] = []
    last_end = -1
    for start, end in spans:
        if start < last_end:
            continue  # overlaps a snippet already taken
        lo = max(s.rfind("\n", 0, start), s.rfind(". ", 0, start) + 1, start - 60, 0)
        snippet = re.sub(r"\s+", " ", s[lo:lo + SNIPPET_CHARS]).strip()
        hi = lo + SNIPPET_CHARS
        out.append(snippet[:SNIPPET_CHARS])
        last_end = max(end, hi)
    return out


# ---- URL helpers ----------------------------------------------------------------------

def host_of(url: str) -> str:
    try:
        host = (urlsplit(url.strip()).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _on_domain(url: str, domain: str) -> bool:
    h, d = host_of(url), (domain or "").lower().strip().removeprefix("www.")
    return bool(h and d) and (h == d or h.endswith("." + d))


def _site_of(host: str) -> str:
    """Registrable-ish site for "one result per publisher" (news.x.com -> x.com)."""
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "net", "ac", "gov") \
            and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def unwrap_redirect(url: str) -> tuple[str, bool]:
    """(url, ok). Google redirect links are unwrapped from `url=`/`q=`; ones that cannot
    be unwrapped (news.google.com/rss/articles/...) return ok=False."""
    host = host_of(url)
    if not (host == "google.com" or host.startswith("google.") or host.endswith(".google.com")):
        return url, True
    try:
        qs = parse_qs(urlsplit(url).query)
    except ValueError:
        return url, False
    for key in ("url", "q", "u"):
        for v in qs.get(key, []):
            if v.startswith(("http://", "https://")) and "google." not in host_of(v):
                return v, True
    return url, False


# ---- Mode A picking (§20.2 item 2, PC-4) ------------------------------------------------

_FUNDING = re.compile(r"\b(raises?|raised|raising|funding|funded|series\s+[a-h]\b|seed|pre-seed|"
                      r"round|led\s+by|investment|invests?|backed|secures?|bags|closes?|"
                      r"financing|venture)\b", re.I)
_WIRES = ("prnewswire.com", "businesswire.com", "globenewswire.com", "newswire.com",
          "accesswire.com", "einpresswire.com")
_MAJOR_OUTLETS = ("techcrunch.com", "reuters.com", "bloomberg.com", "wsj.com", "ft.com",
                  "axios.com", "forbes.com", "businessinsider.com", "theinformation.com",
                  "venturebeat.com", "fortune.com", "cnbc.com", "nytimes.com", "theverge.com",
                  "economictimes.indiatimes.com", "inc42.com", "yourstory.com", "sifted.eu")
_ENTITY_NOUNS = {
    "trail", "trails", "park", "road", "street", "avenue", "highway", "bridge", "creek", "river",
    "lake", "county", "village", "town", "school", "church", "hospital", "museum", "library",
    "stadium", "mall", "station", "railway", "rail", "walking", "bike", "path", "greenway",
    "algebra", "regression", "equation", "equations", "programming", "accelerator", "motor",
    "motors", "actuator", "amplifier", "polarizer", "polarization", "function", "functions",
    "growth", "scale", "fit", "model", "models", "time", "foot", "feet", "mile", "miles",
}
_ROUND_WORDS = {"pre_seed": r"pre-?seed", "seed": r"(?<!pre-)(?<!pre )seed",
                "series_a": r"series\s+a\b", "series_b": r"series\s+b\b",
                "series_c": r"series\s+c\b", "series_d": r"series\s+d\b",
                "series_e": r"series\s+e\b"}


def _name_rx(name: str) -> re.Pattern[str] | None:
    core = re.sub(r"[,\s]+(inc\.?|llc|ltd\.?|labs?|corp\.?|co\.?|gmbh|technologies|ai)$", "",
                  (name or "").strip(), flags=re.I).strip() or (name or "").strip()
    if len(core) < 2:
        return None
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(core) + r"(?![A-Za-z0-9])", re.I)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


def _mentions(text: str, url: str, name_rx: re.Pattern[str] | None, name: str,
              domain: str) -> bool:
    d = (domain or "").lower()
    if d and (d in (text or "").lower() or _on_domain(url, d) or d in (url or "").lower()):
        return True
    if name_rx and name_rx.search(text or ""):
        return True
    slug = _slug(name)
    path = urlsplit(url).path.lower() if url else ""
    return bool(slug and len(slug) >= 3 and re.search(r"(?<![a-z0-9])" + re.escape(slug)
                                                       + r"(?![a-z0-9])", path))


def _namesake(title: str, name: str, name_rx: re.Pattern[str] | None) -> str:
    """A reason string when the title uses the name for a different entity, else ""."""
    if not name_rx or not title:
        return ""
    words = re.findall(r"[A-Za-z][A-Za-z'\-]*", title)
    hits = list(name_rx.finditer(title))
    if not hits:
        return ""
    if any(c.isupper() for c in name) and all(
            not any(c.isupper() for c in h.group(0)) for h in hits):
        return f"subject mismatch: '{hits[0].group(0)}' used as a common word"
    lowered = [w.lower() for w in words]
    target = name.split()[0].lower() if name.split() else ""
    for i, w in enumerate(lowered):
        if w != target:
            continue
        # stop at the first verb-like word after the name ("Linear raises ... model")
        after = []
        for nxt in lowered[i + 1:i + 4]:
            if _FUNDING.fullmatch(nxt) or nxt in ("is", "launches", "announces", "unveils"):
                break
            after.append(nxt)
        window = lowered[max(0, i - 2):i] + after
        noun = next((x for x in window if x in _ENTITY_NOUNS), "")
        if noun:
            return f"subject mismatch: '{name}' here names a different entity ('{noun}')"
    return ""


def _parse_day(iso: str) -> date | None:
    try:
        return date.fromisoformat(iso) if len(iso) == 10 else None
    except ValueError:
        return None


def _nearest_milestone(pub: str, pub_prec: str, milestones: list[dict]) -> tuple[dict | None, int]:
    """(milestone, distance in days) for the closest milestone the publish date matches:
    within ±7 days for day precision, same month/year at month/year precision."""
    best: tuple[dict | None, int] = (None, 10**6)
    pday = _parse_day(pub) if pub_prec == "day" else None
    for m in milestones or []:
        if not isinstance(m, dict):
            continue
        mdate, mprec = str(m.get("date") or ""), str(m.get("date_precision") or "")
        if not mdate or mprec not in ("day", "month", "year"):
            mdate, mprec = date_and_precision(mdate)
            if mprec == "unknown":
                continue
        dist = 10**6
        if mprec == "day" and pday is not None:
            md = _parse_day(mdate)
            if md is not None:
                dist = abs((pday - md).days)
                if dist > PROXIMITY_DAYS:
                    continue
            else:
                continue
        elif mprec == "day" and pub_prec == "month":
            if pub != mdate[:7]:
                continue
            dist = 15
        elif mprec == "month":
            if pub[:7] != mdate[:7] or pub_prec == "year":
                continue
            dist = 20
        elif mprec == "year":
            if pub[:4] != mdate[:4]:
                continue
            dist = 200
        else:
            continue
        if dist < best[1] or (dist == best[1] and best[0] is not None
                              and str(m.get("date")) > str(best[0].get("date"))):
            best = (m, dist)
    return best


def _round_bonus(title: str, milestone: dict | None) -> int:
    if not milestone:
        return 0
    rx = _ROUND_WORDS.get(str(milestone.get("round_type") or ""))
    return 5 if rx and re.search(rx, title or "", re.I) else 0


def _score(own: bool, fwords: list[str], title: str, host: str,
           name_rx: re.Pattern[str] | None) -> int:
    """Fixed, documented ranking: own page > funding words > the company leads the title >
    wire press release or a major outlet > a stated amount."""
    score = 100 if own else 0
    score += (10 + 2 * min(len(fwords) - 1, 2)) if fwords else 0
    score += 8 if name_rx and name_rx.match(title or "") else 0
    score += 4 if _on_any(host, _WIRES) else 0
    score += 6 if _on_any(host, _MAJOR_OUTLETS) else 0
    score += 3 if re.search(r"[$€£₹]\s?\d", title or "") else 0
    return score


def _on_any(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def _item(url: str, title: str, publisher: str, publish_date: str, reason: str,
          **extra: Any) -> dict:
    return {"url": url, "title": title, "publisher": publisher, "publish_date": publish_date,
            "reason": reason, **extra}


def pick_news(news: list[dict], company_name: str, domain: str, milestones: list[dict],
              max_urls: int = 3) -> tuple[list[dict], list[dict]]:
    """Pick <=max_urls funding articles from Company Enrich `news[]` (PC-4 rules).

    Returns (picks, excluded); every item has url, title, publisher, publish_date and
    reason. A pick names the company (word boundary) or its domain in title/URL, has a
    publish date matching a milestone (±7 days at day precision) and either funding
    words or the company's own domain. One per publisher; the company's own pages
    first; syndicated copies (same title) count once. Deterministic."""
    name_rx = _name_rx(company_name)
    eligible: list[dict] = []
    excluded: list[dict] = []
    seen_urls: set[str] = set()
    for raw in news if isinstance(news, list) else []:
        if not isinstance(raw, dict):
            continue
        url = str(raw.get("article_url") or raw.get("url") or "").strip()
        title = re.sub(r"\s+", " ", str(raw.get("article_title") or raw.get("title") or "")).strip()
        publisher = str(raw.get("article_publisher_name") or raw.get("publisher_domain")
                        or host_of(url) or "")
        pub, pprec = date_and_precision(raw.get("article_publish_date"))
        base = dict(url=url, title=title, publisher=publisher, publish_date=pub)
        if not url or not url.startswith(("http://", "https://")):
            excluded.append(_item(**base, reason="no usable URL"))
            continue
        url, ok = unwrap_redirect(url)
        base["url"] = url
        if not ok:
            excluded.append(_item(**base, reason="unresolvable Google redirect link"))
            continue
        if url.lower() in seen_urls:
            excluded.append(_item(**base, reason="duplicate URL"))
            continue
        seen_urls.add(url.lower())
        own = _on_domain(url, domain)
        if not own and not _mentions(title, url, name_rx, company_name, domain):
            excluded.append(_item(**base, reason="subject mismatch: company name and domain "
                                                 "absent from title and URL"))
            continue
        namesake = "" if own else _namesake(title, company_name, name_rx)
        if namesake:
            excluded.append(_item(**base, reason=namesake))
            continue
        fwords = sorted({w.lower() for w in _FUNDING.findall(title)})
        milestone, dist = (None, 10**6) if pprec == "unknown" else \
            _nearest_milestone(pub, pprec, milestones)
        if not fwords and not own and milestone is None:
            excluded.append(_item(**base, reason="subject mismatch: no funding words and no "
                                                 f"milestone within ±{PROXIMITY_DAYS} days"))
            continue
        if pprec == "unknown":
            excluded.append(_item(**base, reason="publish date unknown (missing or "
                                                 "1970-01-01 sentinel)"))
            continue
        if milestone is None:
            excluded.append(_item(**base, reason=f"no funding milestone within "
                                                 f"±{PROXIMITY_DAYS} days of {pub}"))
            continue
        if not fwords and not own:
            excluded.append(_item(**base, reason="no funding words in title"))
            continue
        host = host_of(url)
        score = _score(own, fwords, title, host, name_rx) + _round_bonus(title, milestone)
        ms_label = f"{milestone.get('round_type', 'unknown')} {milestone.get('date', '')}"
        why = ("company's own page; " if own else "") + \
            (f"funding words: {', '.join(fwords)}; " if fwords else "") + \
            (f"published {pub}, {dist} days from milestone {ms_label}" if dist <= PROXIMITY_DAYS
             else f"published {pub}, matches milestone {ms_label} at "
                  f"{milestone.get('date_precision', '')} precision")
        eligible.append(_item(**base, reason=why, own=own, score=score, distance=dist,
                              milestone=ms_label, milestone_date=str(milestone.get("date", "")),
                              site=_site_of(host)))

    eligible.sort(key=lambda e: (not e["own"], -e["score"], e["distance"],
                                 _neg(e["milestone_date"]), _neg(e["publish_date"]), e["url"]))
    picks: list[dict] = []
    used_sites: set[str] = set()
    used_titles: set[str] = set()

    def norm_title(t: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()

    def take(e: dict) -> bool:
        if e["site"] in used_sites or norm_title(e["title"]) in used_titles:
            return False
        picks.append(e)
        used_sites.add(e["site"])
        used_titles.add(norm_title(e["title"]))
        return True

    limit = max(0, int(max_urls))
    for e in [e for e in eligible if e["own"]]:  # own pages first
        if len(picks) < limit:
            take(e)
    # one article per milestone, latest round first, leaving one slot to corroborate
    rounds = sorted({e["milestone_date"] for e in eligible}, key=_neg)
    for mdate in rounds[:max(1, limit - 1)]:
        if len(picks) >= limit:
            break
        if any(p["milestone_date"] == mdate for p in picks):
            continue
        for e in eligible:
            if e["milestone_date"] == mdate and not any(p is e for p in picks) and take(e):
                break
    for e in eligible:
        if len(picks) >= limit:
            break
        if not any(p is e for p in picks):
            take(e)

    for e in eligible:
        if any(p is e for p in picks):
            continue
        if norm_title(e["title"]) in used_titles:
            reason = "duplicate title (syndicated copy; one origin)"
        elif e["site"] in used_sites:
            reason = "publisher already picked"
        else:
            reason = f"lower rank (limit {limit})"
        excluded.append(_public(e, reason))
    return [_public(p, p["reason"]) for p in picks], excluded


def _neg(iso: str) -> str:
    """Sort key that orders ISO strings descending inside an ascending sort."""
    return "".join(chr(0x10FFFF - ord(c)) for c in (iso or ""))


def _public(e: dict, reason: str) -> dict:
    return _item(e["url"], e["title"], e["publisher"], e["publish_date"], reason,
                 milestone=e.get("milestone", ""), score=e.get("score", 0))


def pick_search_results(results: Any, company_name: str, domain: str,
                        max_urls: int = 3) -> tuple[list[dict], list[dict]]:
    """Pick from Web Search results (no dates available): the name or domain must appear
    in the URL, title or snippet; funding words required unless it is the company's own
    site; one per site; own site first; Google redirects unwrapped or skipped."""
    items = _search_items(results)
    name_rx = _name_rx(company_name)
    eligible: list[dict] = []
    excluded: list[dict] = []
    for idx, r in enumerate(items):
        url = str(r.get("url") or r.get("link") or "").strip()
        title = re.sub(r"\s+", " ", str(r.get("title") or "")).strip()
        snippet = re.sub(r"\s+", " ", str(r.get("snippet") or "")).strip()
        publisher = str(r.get("source") or host_of(url) or "")
        base = dict(url=url, title=title, publisher=publisher, publish_date="")
        if not url.startswith(("http://", "https://")):
            excluded.append(_item(**base, reason="no usable URL"))
            continue
        url, ok = unwrap_redirect(url)
        base["url"] = url
        if not ok:
            excluded.append(_item(**base, reason="unresolvable Google redirect link"))
            continue
        own = _on_domain(url, domain)
        if not own and not _mentions(f"{title} {snippet}", url, name_rx, company_name, domain):
            excluded.append(_item(**base, reason="subject mismatch: company name and domain "
                                                 "absent from title, snippet and URL"))
            continue
        namesake = "" if own else _namesake(title, company_name, name_rx)
        if namesake:
            excluded.append(_item(**base, reason=namesake))
            continue
        fwords = sorted({w.lower() for w in _FUNDING.findall(f"{title} {snippet}")})
        if not fwords and not own:
            excluded.append(_item(**base, reason="subject mismatch: no funding words"))
            continue
        try:
            pos = int(r.get("position") or idx + 1)
        except (TypeError, ValueError):
            pos = idx + 1
        host = host_of(url)
        score = _score(own, fwords, title, host, name_rx)
        why = ("company's own site; " if own else "") + \
            (f"funding words: {', '.join(fwords)}; " if fwords else "") + \
            f"search position {pos}; publish date not given by search"
        eligible.append(dict(**base, reason=why, own=own, score=score, pos=pos,
                             site=_site_of(host)))
    eligible.sort(key=lambda e: (not e["own"], -e["score"], e["pos"], e["url"]))
    picks: list[dict] = []
    sites: set[str] = set()
    for e in eligible:
        if e["site"] in sites:
            excluded.append(_item(e["url"], e["title"], e["publisher"], "", "site already picked"))
        elif len(picks) >= max(0, int(max_urls)):
            excluded.append(_item(e["url"], e["title"], e["publisher"], "",
                                  f"lower rank (limit {max_urls})"))
        else:
            sites.add(e["site"])
            picks.append(_item(e["url"], e["title"], e["publisher"], "", e["reason"],
                               score=e["score"]))
    return picks, excluded


def _search_items(results: Any) -> list[dict]:
    if isinstance(results, dict):
        for key in ("results", "data", "items", "news"):
            if isinstance(results.get(key), list):
                return _search_items(results[key])
        return []
    if isinstance(results, list):
        out: list[dict] = []
        for r in results:
            if isinstance(r, dict) and (r.get("url") or r.get("link")):
                out.append(r)
            elif isinstance(r, dict):
                out.extend(_search_items(r))
        return out
    return []


# ---- assembly ----------------------------------------------------------------------------

@dataclass
class PacketResult:
    documents: list[Document] = field(default_factory=list)
    picks: list[dict] = field(default_factory=list)
    excluded: list[dict] = field(default_factory=list)
    failed_urls: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    injection_notes: list[str] = field(default_factory=list)
    attempts_note: str = ""

    @property
    def injection_count(self) -> int:
        return len(self.injection_notes)

    def injection_summary(self) -> str:
        return f"{self.injection_count} agent-directed instructions found and ignored"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8", errors="surrogatepass")).hexdigest()


def _g1_fields(g1: Any) -> tuple[str, str]:
    get = (lambda k: g1.get(k)) if isinstance(g1, dict) else (lambda k: getattr(g1, k, ""))
    domain = str(get("domain") or "").strip().lower().removeprefix("www.")
    name = str(get("name") or "").strip()
    if not name and domain:
        name = domain.split(".")[0]
    return name, domain


def _make_doc(doc_id: str, source: str, content: str, *, title_hint: str, subject_domain: str,
              picked_because: str, retrieved: str, res: PacketResult) -> Document:
    page = extract_text(content)
    origin = "company" if source != "pasted" and _on_domain(source, subject_domain) else "unknown"
    doc = Document(id=doc_id, source=source, title=page.title or title_hint, text=page.text,
                   published=page.published, updated=page.updated, retrieved=retrieved,
                   sha256=_sha(content), origin=origin, picked_because=picked_because)
    if page.words < THIN_WORDS:
        res.limitations.append(f"{doc_id} thin page ({page.words} words): {source}")
    found = find_agent_instructions(page.text)
    if looks_like_html(content):
        try:
            soup = BeautifulSoup(content, "html.parser")
            hidden = " \n".join(str(c) for c in soup.find_all(string=lambda x: isinstance(x, Comment)))
            found += [f for f in find_agent_instructions(hidden) if f not in found]
        except Exception:  # noqa: BLE001 - the scan is best effort
            pass
    for snippet in found:
        res.injection_notes.append(f"{doc_id}: {snippet}")
    if found:
        log.warning("%s: %d agent-directed instructions found and ignored", doc_id, len(found))
    return doc


def _cap_words(docs: list[Document], res: PacketResult, limit: int = MAX_WORDS) -> None:
    """Truncate the longest documents so the packet holds <= limit words in total."""
    counts = [len(d.text.split()) for d in docs]
    if sum(counts) <= limit:
        return
    lo, hi = 0, max(counts)
    while lo < hi:  # largest cap c with sum(min(w, c)) <= limit
        mid = (lo + hi + 1) // 2
        if sum(min(w, mid) for w in counts) <= limit:
            lo = mid
        else:
            hi = mid - 1
    for d, w in zip(docs, counts):
        if w > lo:
            spans = list(re.finditer(r"\S+", d.text))
            d.text = d.text[:spans[lo - 1].end()] if lo > 0 else ""
            res.limitations.append(f"{d.id} truncated from {w} to {lo} words "
                                   f"(packet limit {limit} words)")


async def _fetch_into(client: Any, targets: list[dict], subject_domain: str, res: PacketResult,
                      start_index: int) -> int:
    """ONE Web Fetch request for <=3 targets ({url, title, reason}). Returns docs added."""
    targets = targets[:3]
    urls = [t["url"] for t in targets]
    if not urls:
        return 0
    try:
        results = await client.web_fetch(urls)
    except CrustError as e:
        if e.fatal:
            raise
        res.failed_urls.extend(urls)
        res.limitations.append(f"Web Fetch failed ({e.status} {e.type}); "
                               f"{len(urls)} URL(s) not retrieved")
        res.attempts_note += f"web_fetch: 1 request, {len(urls)} URLs, failed {e.type}. "
        return 0
    ok, failed = match_fetch_results(urls, results)
    res.failed_urls.extend(failed)
    for u in failed:
        res.limitations.append(f"Web Fetch did not retrieve {u} (attempt kept, not evidence)")
    res.attempts_note += f"web_fetch: 1 request, {len(urls)} URLs, {len(ok)} succeeded. "
    retrieved = _now()
    added = 0
    for t in targets:
        item = ok.get(t["url"])
        if item is None:
            continue
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            res.failed_urls.append(t["url"])
            res.limitations.append(f"Web Fetch returned no content for {t['url']}")
            continue
        added += 1
        doc_id = f"D{start_index + added}"
        ts = item.get("timestamp")
        stamp = retrieved
        if isinstance(ts, (int, float)) and ts > 0:
            stamp = datetime.fromtimestamp(ts / (1000 if ts > 1e11 else 1), timezone.utc) \
                .replace(microsecond=0).isoformat().replace("+00:00", "Z")
        elif isinstance(ts, str) and ts.strip():
            stamp = ts.strip()
        res.documents.append(_make_doc(doc_id, t["url"], content,
                                       title_hint=str(item.get("title") or t.get("title") or ""),
                                       subject_domain=subject_domain,
                                       picked_because=str(t.get("reason") or ""),
                                       retrieved=stamp, res=res))
    return added


def _finish(res: PacketResult) -> PacketResult:
    _cap_words(res.documents, res)
    if res.injection_notes:
        res.limitations.append(res.injection_summary())
    log.info("packet: %d documents, %d failed URLs, %s", len(res.documents),
             len(res.failed_urls), res.injection_summary())
    return res


async def assemble_mode_a(client: Any, g1: Any, news: list[dict], financing: dict, *,
                          max_urls: int = 3) -> PacketResult:
    """Mode A (§4.2, §20.2 item 2): pick from `news[]`; if nothing qualifies, ONE Web
    Search "<name> raises" (news); then ONE Web Fetch for the picks."""
    name, domain = _g1_fields(g1)
    res = PacketResult()
    ms = (financing or {}).get("milestones") or [] if isinstance(financing, dict) else []
    picks, excluded = pick_news(news or [], name, domain, ms, max_urls)
    res.excluded.extend(excluded)
    res.attempts_note = f"news[]: {len(news or [])} items, {len(picks)} picked. "
    if not picks:
        res.limitations.append("No news[] item passed the subject, funding-word and ±7-day "
                               "milestone checks; one Web Search fallback was used")
        try:
            found = await client.web_search(f"{name} raises", sources=("news",))
            picks, excluded = pick_search_results(found, name, domain, max_urls)
            res.excluded.extend(excluded)
            res.attempts_note += f"web_search: 1 request, {len(picks)} picked. "
        except CrustError as e:
            if e.fatal:
                raise
            res.limitations.append(f"Web Search fallback failed ({e.status} {e.type})")
            res.attempts_note += f"web_search: 1 request, failed {e.type}. "
    res.picks = picks
    if not picks:
        res.limitations.append("No funding source found to fetch; the brief relies on the "
                               "indexed record only")
        return _finish(res)
    await _fetch_into(client, picks, domain, res, 0)
    return _finish(res)


async def assemble_mode_b(client: Any, pasted: list[str], urls: list[str], *,
                          domain: str = "") -> PacketResult:
    """Mode B (§4.2): pasted texts become documents (source "pasted"); URLs (<=3) are
    fetched in ONE Web Fetch request. `domain` (optional) sets origin "company"."""
    res = PacketResult()
    retrieved = _now()
    n = 0
    for text in pasted or []:
        if not isinstance(text, str) or not text.strip():
            continue
        n += 1
        res.documents.append(_make_doc(f"D{n}", "pasted", text, title_hint="Pasted text",
                                       subject_domain=domain, picked_because="pasted by user",
                                       retrieved=retrieved, res=res))
    targets: list[dict] = []
    for u in urls or []:
        u = str(u or "").strip()
        if not u:
            continue
        if not u.startswith(("http://", "https://")):
            u = "https://" + u
        unwrapped, ok = unwrap_redirect(u)
        if not ok:
            res.failed_urls.append(u)
            res.limitations.append(f"Skipped unresolvable Google redirect link {u}")
            continue
        if any(t["url"] == unwrapped for t in targets):
            continue
        targets.append({"url": unwrapped, "title": "", "reason": "supplied by user"})
    if len(targets) > 3:
        for t in targets[3:]:
            res.limitations.append(f"Only 3 URLs are fetched; skipped {t['url']}")
        targets = targets[:3]
    res.picks = [_item(t["url"], "", host_of(t["url"]), "", t["reason"]) for t in targets]
    res.attempts_note = f"pasted: {n} documents. "
    if targets:
        await _fetch_into(client, targets, domain, res, n)
    return _finish(res)
