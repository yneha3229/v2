"""Deterministic code gate (plan v2 §5.4).

Blocking code checks on every emitted sentence:

- every cited evidence ID exists in this run;
- every money amount, percentage, 4-digit year and full date written in digits
  matches its cited evidence after normalization, at the sentence's precision.

On failure the gate drops the failing clause if the remainder still passes and is
still a sentence; otherwise it suppresses the sentence. Every failure becomes a
limitation string. There is no model repair. Currencies are never converted.

Evidence text used for matching is the evidence value plus its published / updated /
refreshed dates (see `evidence_text`). Fetched text is data, never instructions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date as _date
from typing import Iterable, Mapping

from proofroom.graph import amounts_match, date_and_precision
from proofroom.models import Evidence, Finding

# ---- Normalization ---------------------------------------------------------------

_QUOTES = {ord(c): "'" for c in "‘’‚‛′ʼ`"}
_QUOTES.update({ord(c): '"' for c in "“”„‟″«»"})
_DASHES = {ord(c): "-" for c in "‐‑‒–—―−﹘﹣－"}
_SPACES = {ord(c): " " for c in "          　"}
_ZERO = {ord(c): None for c in "​‌‍⁠﻿­"}
_TABLE = {**_QUOTES, **_DASHES, **_SPACES, **_ZERO, ord("…"): "..."}


def normalize(text: str) -> str:
    """Unicode quotes -> ASCII quotes, dashes -> '-', NBSP/thin spaces -> ' ',
    zero-width characters removed, whitespace collapsed."""
    return re.sub(r"\s+", " ", str(text or "").translate(_TABLE)).strip()


# ---- Parsed tokens ------------------------------------------------------------------

@dataclass(frozen=True)
class Amount:
    value: float              # in units of `currency` (never converted)
    currency: str             # USD | INR | GBP | EUR | unknown
    unit: float               # precision the text implies: "$20.5M" -> 100000
    raw: str
    span: tuple[int, int]
    symbol: str = ""          # the currency token as written ("$", "US$", "A$", "¥", "rupees")


@dataclass(frozen=True)
class Percent:
    value: float
    raw: str
    span: tuple[int, int]


@dataclass(frozen=True)
class Year:
    value: int
    raw: str
    span: tuple[int, int]
    precision: str = "year"


@dataclass(frozen=True)
class FullDate:
    iso: str                  # YYYY-MM-DD (day) or YYYY-MM (month) or YYYY (year)
    precision: str            # day | month | year
    raw: str
    span: tuple[int, int]


# ---- Amounts ------------------------------------------------------------------------

_NUM = r"(?P<num>\d+(?:,\d+)*(?:\.\d+)?)"
_SCALE = (r"(?:\s?(?P<scale>(?i:lakh\s+crores?|thousand|million|billion|trillion|lakhs?|lacs?"
          r"|crores?|mn|mm|bn|tn|cr|k|m|b))(?![A-Za-z]))")
_SUFCUR = (r"(?P<sc>(?i:us\s+dollars|dollars|usd|rupees|inr|pounds\s+sterling|pounds|gbp"
           r"|euros?|eur))(?![A-Za-z])")
_UNKNOWN_SYMBOLS = "¥₩₽₺₦₱฿₫₴₪¤₿₡₲₵₸"
_PREFIX = (r"(?P<pc>US\$|(?<![A-Za-z])[A-Z]{1,3}\$|\$|(?<![A-Za-z])(?:USD|INR|GBP|EUR|Rs\.?)"
           r"|[£€₹" + _UNKNOWN_SYMBOLS + r"])")
_AMOUNT_PREFIX_RE = re.compile(_PREFIX + r"\s?" + _NUM + _SCALE + r"?(?:\s" + _SUFCUR + r")?")
_AMOUNT_SUFFIX_RE = re.compile(r"(?<![\w.,$£€₹])" + _NUM + _SCALE + r"?\s?" + _SUFCUR)

_SCALES = {"thousand": 1e3, "k": 1e3, "million": 1e6, "mn": 1e6, "mm": 1e6, "m": 1e6,
           "billion": 1e9, "bn": 1e9, "b": 1e9, "trillion": 1e12, "tn": 1e12,
           "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5,
           "crore": 1e7, "crores": 1e7, "cr": 1e7}
_CUR = {"$": "USD", "us$": "USD", "usd": "USD", "dollars": "USD", "us dollars": "USD",
        "₹": "INR", "inr": "INR", "rs": "INR", "rs.": "INR", "rupees": "INR",
        "£": "GBP", "gbp": "GBP", "pounds": "GBP", "pounds sterling": "GBP",
        "€": "EUR", "eur": "EUR", "euro": "EUR", "euros": "EUR"}


def _scale(word: str | None) -> float:
    if not word:
        return 1.0
    w = re.sub(r"\s+", " ", word.lower())
    if w.startswith("lakh crore"):
        return 1e12
    return _SCALES[w]


def _currency(token: str | None) -> str | None:
    if not token:
        return None
    return _CUR.get(re.sub(r"\s+", " ", token.strip().lower()), "unknown")


def _make_amount(m: re.Match, text: str) -> Amount | None:
    num = m.group("num")
    pc = m.groupdict().get("pc")
    sc = m.groupdict().get("sc")
    scale_word = m.group("scale")
    if not pc and not scale_word and sc and sc.lower() in {"usd", "inr", "gbp", "eur"} \
            and "," not in num:
        return None  # "2025 USD" is more likely a year than money
    cp, cs = _currency(pc), _currency(sc)
    if cp and cs and cp != cs:
        currency = "unknown"
    else:
        currency = cp or cs or "unknown"
    digits = num.replace(",", "")
    decimals = len(digits.split(".")[1]) if "." in digits else 0
    scale = _scale(scale_word)
    value = float(digits) * scale
    unit = scale * 10 ** (-decimals)
    symbol = (pc or sc or "").strip()
    return Amount(round(value, 6), currency, unit, m.group(0).strip(), (m.start(), m.end()), symbol)


def parse_amounts(text: str) -> list[Amount]:
    """Money amounts with a currency marker. "₹50 crore" = 500,000,000 INR; an
    unrecognized currency symbol gives currency "unknown" (fin-4). No FX conversion."""
    text = str(text or "")
    out: list[Amount] = []
    masked = text
    for rx in (_AMOUNT_PREFIX_RE, _AMOUNT_SUFFIX_RE):
        for m in rx.finditer(masked):
            a = _make_amount(m, masked)
            if a:
                out.append(Amount(a.value, a.currency, a.unit, text[m.start():m.end()].strip(),
                                  a.span, a.symbol))
        masked = _mask(masked, [a.span for a in out])
    return sorted(out, key=lambda a: a.span)


# ---- Percentages and years ----------------------------------------------------------

_PCT_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s?(?:%|(?i:percent|per\s+cent|pct)(?![A-Za-z]))")
_YEAR_RE = re.compile(r"(?<!\d,)(?<![\d.$£€₹])((?:19|20)\d{2})(?!\d|,\d|%|\.\d)")


def parse_percentages(text: str) -> list[Percent]:
    return [Percent(float(m.group(1)), m.group(0), m.span()) for m in _PCT_RE.finditer(str(text or ""))]


def parse_years(text: str) -> list[Year]:
    """Standalone 4-digit years 1900-2099 (not part of a date, amount or percentage)."""
    text = str(text or "")
    taken = [d.span for d in parse_full_dates(text)] + [a.span for a in parse_amounts(text)]
    taken += [p.span for p in parse_percentages(text)]
    masked = _mask(text, taken)
    return [Year(int(m.group(1)), m.group(1), m.span()) for m in _YEAR_RE.finditer(masked)]


# ---- Dates --------------------------------------------------------------------------

_MONTH = (r"(?P<mon>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?"
          r"|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)(?![a-z])")
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_ORD = r"(?:st|nd|rd|th)?"
_PREC_NOTE = re.compile(r"\s*\((day|month|year)\)")

_DATE_RES: list[tuple[str, re.Pattern]] = [
    ("iso", re.compile(r"(?<![\d-])(?P<y>\d{4})[-/](?P<m>\d{2})[-/](?P<d>\d{2})(?!\d)")),
    ("dmy_num", re.compile(r"(?<![\d/.-])(?P<d>\d{1,2})[/.](?P<m>\d{1,2})[/.](?P<y>\d{4})(?![\d/])")),
    ("dmy", re.compile(r"(?<!\d)(?P<d>\d{1,2})" + _ORD + r"\s+(?:of\s+)?" + _MONTH
                       + r"\.?,?\s+(?P<y>\d{4})(?!\d)")),
    ("mdy", re.compile(r"\b" + _MONTH + r"\.?\s+(?P<d>\d{1,2})" + _ORD + r",?\s+(?P<y>\d{4})(?!\d)")),
    ("my", re.compile(r"\b" + _MONTH + r"\.?,?\s+(?:(?P<y>\d{4})|'(?P<yy>\d{2}))(?![\d'])")),
    ("iso_month", re.compile(r"(?<![\d-])(?P<y>\d{4})-(?P<m>\d{2})(?![\d-])")),
]


def _valid(y: int, m: int, d: int = 1) -> bool:
    try:
        _date(y, m, d)
    except ValueError:
        return False
    return 1900 <= y <= 2099


def parse_full_dates(text: str, *, evidence: bool = False) -> list[FullDate]:
    """Dates written with digits: ISO (day or month), DD/MM/YYYY (day-first; read as
    MM/DD only when the second number exceeds 12), "24 Feb 2026", "Feb 24, 2026" (day)
    and "Feb 2026" / "Aug '25" (month).

    With `evidence=True`, ISO dates follow the project rule (`YYYY-01-01` -> year,
    `YYYY-MM-01` -> month, via graph.date_and_precision) and an explicit "(day)",
    "(month)" or "(year)" right after the date (graph evidence rows) overrides that."""
    text = str(text or "")
    out: list[FullDate] = []
    masked = text
    for kind, rx in _DATE_RES:
        found: list[FullDate] = []
        for m in rx.finditer(masked):
            g = m.groupdict()
            if "mon" in g and g["mon"]:
                mon = _MONTHS[g["mon"][:3].lower()]
            else:
                mon = int(g.get("m") or 0)
            y = int(g["y"]) if g.get("y") else 2000 + int(g["yy"])
            if kind == "dmy_num":
                d, mon2 = int(g["d"]), int(g["m"])
                if mon2 > 12 and d <= 12:      # month-first (US) when unambiguous
                    d, mon2 = mon2, d
                mon = mon2
            else:
                d = int(g["d"]) if g.get("d") else 0
            if not _valid(y, mon, d or 1):
                continue
            if d:
                iso, prec = f"{y:04d}-{mon:02d}-{d:02d}", "day"
            else:
                iso, prec = f"{y:04d}-{mon:02d}", "month"
            if evidence and kind in ("iso", "iso_month"):
                iso, prec = date_and_precision(iso)
                if prec == "unknown":
                    continue
            if evidence:
                note = _PREC_NOTE.match(masked, m.end())
                if note:
                    want = note.group(1)
                    if _RANK[want] < _RANK[prec]:
                        iso, prec = iso[:_LEN[want]], want
            found.append(FullDate(iso, prec, text[m.start():m.end()], m.span()))
        out.extend(found)
        masked = _mask(masked, [f.span for f in found])
    return sorted(out, key=lambda f: f.span)


_RANK = {"year": 0, "month": 1, "day": 2}
_LEN = {"year": 4, "month": 7, "day": 10}


def date_matches(stated: FullDate, record: FullDate) -> bool:
    """A stated date matches only evidence at least as precise, equal at the stated
    precision: "Feb 2026" matches 2026-02-24; "24 Feb 2026" does not match "Feb 2026"."""
    if _RANK[record.precision] < _RANK[stated.precision]:
        return False
    n = _LEN[stated.precision]
    return record.iso[:n] == stated.iso[:n]


def amount_matches(stated: Amount, record: Amount) -> bool:
    """Same currency (an unknown currency matches only the same symbol), the record at
    least as precise as the sentence, and the values equal at the sentence's precision
    (graph.amounts_match). An exact half-unit tie is ambiguous rounding and fails, so
    neither "$20M" nor "$21M" passes for 20.5M; the sentence must say "$20.5M"."""
    if stated.currency != record.currency:
        return False
    if stated.currency == "unknown" and stated.symbol != record.symbol:
        return False
    if record.unit > stated.unit * (1 + 1e-9):
        return False
    if not amounts_match(stated.value, record.value, stated.unit):
        return False
    diff = abs(record.value - stated.value)
    return not (diff > 0 and abs(diff - stated.unit / 2) <= stated.unit * 1e-9)


# ---- Evidence facts -------------------------------------------------------------------

@dataclass
class EvidenceFacts:
    amounts: list[Amount] = field(default_factory=list)
    percents: list[Percent] = field(default_factory=list)
    years: set[int] = field(default_factory=set)
    dates: list[FullDate] = field(default_factory=list)


def evidence_text(ev: Evidence) -> str:
    """The text a citation can support: the value plus its published / updated /
    refreshed dates (the four clocks are evidence metadata, §5.2)."""
    parts = [ev.value]
    for v in (ev.published, ev.updated, ev.refreshed):
        if v and v != "unknown":
            parts.append(str(v))
    return normalize(" | ".join(parts))


def evidence_facts(evs: Iterable[Evidence]) -> EvidenceFacts:
    facts = EvidenceFacts()
    for ev in evs:
        t = evidence_text(ev)
        facts.amounts += parse_amounts(t)
        facts.percents += parse_percentages(t)
        facts.dates += parse_full_dates(t, evidence=True)
        facts.years |= {int(y) for y in re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", t)}
        facts.years |= {int(d.iso[:4]) for d in facts.dates}
    return facts


# ---- The gate -------------------------------------------------------------------------

CITE_RE = re.compile(r"\[([EG]\d+)\]")
_SEP_RE = re.compile(r";\s|,\s+with\s|,\s+and\s|\s+and\s")
KINDS = ("amounts", "percentages", "years", "dates")


@dataclass
class Token:
    kind: str                 # amounts | percentages | years | dates
    raw: str
    span: tuple[int, int]
    ok: bool
    detail: str = ""


@dataclass
class GateResult:
    """`passed`: the returned `sentence` (possibly with a clause dropped) is kept and
    passes every check. `suppressed`: the sentence must not be emitted. `failures` are
    limitation strings (non-empty also when a clause was dropped or an unknown ID was
    removed). `counts` maps each kind to [ok, total] for the original sentence."""

    passed: bool
    sentence: str
    dropped_clauses: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    suppressed: bool = False
    evidence_ids: list[str] = field(default_factory=list)
    counts: dict[str, list[int]] = field(default_factory=dict)

    @property
    def clean(self) -> bool:
        return self.passed and not self.failures and not self.dropped_clauses


def check_tokens(text: str, facts: EvidenceFacts) -> list[Token]:
    """Every amount, percentage, year and date in `text`, each checked against `facts`."""
    text = CITE_RE.sub(lambda m: " " * len(m.group(0)), text)
    tokens: list[Token] = []
    dates = parse_full_dates(text)
    for d in dates:
        ok = any(date_matches(d, e) for e in facts.dates)
        tokens.append(Token("dates", d.raw, d.span, ok, f"{d.iso} ({d.precision})"))
    masked = _mask(text, [d.span for d in dates])
    amounts = parse_amounts(masked)
    for a in amounts:
        ok = any(amount_matches(a, e) for e in facts.amounts)
        tokens.append(Token("amounts", text[a.span[0]:a.span[1]].strip(), a.span, ok,
                            f"{a.value:,.0f} {a.currency} at {a.unit:,.0f} precision"))
    masked = _mask(masked, [a.span for a in amounts])
    pcts = parse_percentages(masked)
    for p in pcts:
        ok = any(abs(p.value - e.value) < 1e-9 for e in facts.percents)
        tokens.append(Token("percentages", p.raw, p.span, ok, f"{p.value:g}%"))
    masked = _mask(masked, [p.span for p in pcts])
    for m in _YEAR_RE.finditer(masked):
        y = int(m.group(1))
        tokens.append(Token("years", m.group(1), m.span(), y in facts.years, str(y)))
    return sorted(tokens, key=lambda t: t.span)


def _counts(tokens: list[Token]) -> dict[str, list[int]]:
    out = {k: [0, 0] for k in KINDS}
    for t in tokens:
        out[t.kind][1] += 1
        out[t.kind][0] += int(t.ok)
    return out


def _segments(text: str) -> list[tuple[int, int]]:
    """Clause segments: segment i>0 starts at its separator ("; ", ", with ",
    ", and ", " and ") and runs to the next separator."""
    starts = [0] + [m.start() for m in _SEP_RE.finditer(text)]
    ends = starts[1:] + [len(text)]
    return list(zip(starts, ends))


def _words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9$£€₹]+", CITE_RE.sub(" ", text)))


def gate_sentence(sentence: str, evidence_ids: Iterable[str],
                  evidence_by_id: Mapping[str, Evidence]) -> GateResult:
    text = normalize(sentence)
    failures: list[str] = []
    ids: list[str] = []
    for i in list(evidence_ids) + CITE_RE.findall(text):
        if i and i not in ids:
            ids.append(i)
    valid = [i for i in ids if i in evidence_by_id]
    for bad in (i for i in ids if i not in evidence_by_id):
        failures.append(f"cited evidence {bad} does not exist in this run")
    if not text:
        return GateResult(False, "", failures=failures + ["empty sentence; suppressed"],
                          suppressed=True, evidence_ids=valid)
    if not valid:
        failures.append("no valid evidence cited; sentence suppressed")
        return GateResult(False, text, failures=failures, suppressed=True, evidence_ids=[])

    facts = evidence_facts(evidence_by_id[i] for i in valid)
    tokens = check_tokens(text, facts)
    counts = _counts(tokens)
    bad = [t for t in tokens if not t.ok]
    cited = ", ".join(valid)
    if not bad:
        return GateResult(True, text, failures=failures, evidence_ids=valid, counts=counts)

    def why(t: Token) -> str:
        return (f"{t.kind[:-1]} '{t.raw}' ({t.detail}) not found in cited evidence {cited} "
                f"at the sentence's precision")

    segs = _segments(text)
    bad_segs = sorted({next(i for i, (s, e) in enumerate(segs) if s <= t.span[0] < e) for t in bad})
    if bad_segs and 0 not in bad_segs:
        kept = "".join(text[s:e] for i, (s, e) in enumerate(segs) if i not in bad_segs).rstrip(" ,;")
        if text[-1] in ".!?" and kept and kept[-1] not in ".!?":
            kept += text[-1]
        dropped = [_SEP_RE.sub("", text[s:e], count=1).strip(" ,;.") for i, (s, e) in enumerate(segs)
                   if i in bad_segs]
        if _words(kept) >= 5 and all(t.ok for t in check_tokens(kept, facts)):
            for t in bad:
                failures.append(why(t) + f"; clause dropped: '{_clause_of(t, segs, text)}'")
            return GateResult(True, kept, dropped_clauses=dropped, failures=failures,
                              evidence_ids=valid, counts=counts)
    for t in bad:
        failures.append(why(t) + "; sentence suppressed")
    return GateResult(False, text, failures=failures, suppressed=True, evidence_ids=valid,
                      counts=counts)


def _clause_of(t: Token, segs: list[tuple[int, int]], text: str) -> str:
    for s, e in segs:
        if s <= t.span[0] < e:
            return _SEP_RE.sub("", text[s:e], count=1).strip(" ,;.")
    return t.raw


def gate_findings(findings: Iterable[Finding], evidence: Iterable[Evidence] | Mapping[str, Evidence]
                  ) -> tuple[list[Finding], list[tuple[Finding, str]], list[str]]:
    """Gate every finding. Kept findings carry the (possibly reduced) sentence and only
    valid evidence IDs. Returns (kept, [(suppressed finding, reason)], limitations)."""
    by_id = dict(evidence) if isinstance(evidence, Mapping) else {e.id: e for e in evidence}
    kept: list[Finding] = []
    suppressed: list[tuple[Finding, str]] = []
    limitations: list[str] = []
    for f in findings:
        r = gate_sentence(f.sentence, f.evidence_ids, by_id)
        if r.suppressed:
            reason = "; ".join(r.failures)
            suppressed.append((f, reason))
            limitations.append(f"{f.claim_id}: sentence withheld by the code gate ({reason})")
            continue
        kept.append(f.model_copy(update={"sentence": r.sentence, "evidence_ids": r.evidence_ids}))
        limitations += [f"{f.claim_id}: {msg}" for msg in r.failures]
    return kept, suppressed, limitations


def _mask(text: str, spans: Iterable[tuple[int, int]]) -> str:
    chars = list(text)
    for s, e in spans:
        for i in range(s, min(e, len(chars))):
            chars[i] = " "
    return "".join(chars)
