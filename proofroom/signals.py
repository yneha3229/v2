"""Investor signals from Crustdata (D24): fill `research_models.Signals`.

One Company Enrich call with every useful field group, plus Company Search for the
peer set and a zero-row Job Search count. Every number carries the endpoint and
JSON path it came from. Crustdata funding numbers are an indexed record
(Crunchbase-derived), never "independent" (CLAUDE.md §3). Missing groups never
crash: coverage[group] = False and a limitation is written instead.

Rules that are judgement calls, documented here and in code constants:

- Monthly series keep the LAST value seen in each calendar month (`YYYY-MM`).
- Rounds: `secondary_market` milestones (tenders) are not primary raises. Round
  count, cadence and months-since-last-round use primary rounds; `total_funding_usd`
  is the indexed total (which may include secondaries) and, when a secondary
  exists, `total_funding_primary_usd` sums the primary milestone amounts.
  Year-precision dates (`YYYY-01-01`) are not used for cadence gaps.
- Notable employers: `NOTABLE_EMPLOYERS` below (well-known big tech and scaleups).
  A past employer matches when its normalized name equals an alias, or starts with
  it as whole words (short ambiguous aliases need an exact match).
- Prior founder: a PAST title containing founder / co-founder / cofounder, but not
  programme titles such as "Founder Fellow" or "Founder in Residence".
- Peers (Company Search): candidate categories are the company's taxonomy
  categories minus `GENERIC_CATEGORIES` (at most 4); each is counted (limit 1,
  ~0.13 credits) among companies founded in the window. The niche is the smallest
  pool with >= `MIN_PEER_POOL` companies AND-ed with the next smallest (or with an
  AI tag the company carries); the pair is kept only if its pool is also
  >= `MIN_PEER_POOL`. Founded window: year_founded >= min(today.year - 6,
  company's year - 2). Peers = niche + window + last_fundraise_date within 24
  months (month-anchored), sorted by total funding desc, limit 8, self excluded;
  that call's total_count is funded_peers_24m.
- Crowding: funded_peers_24m >= 100 high, 30-99 medium, < 30 low (`CROWDING_*`). Crustdata
  categories are broad (pools of 1-2k companies), so the thresholds are set on that scale (D25).
  Broad categories saturate at "high"; report the count, not just the level.
- News kinds are a title-keyword heuristic. When the company name is not in the
  title the item is "other", so namesake news (e.g. "linear TV networks") and
  round-ups are never flagged as the company's legal risk or funding.
- Public market: a ticker in `revenue.public_markets.stock_symbols` without an
  `ipo_date` is treated as a namesake; the company stays private.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import statistics
import sys
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import httpx

from proofroom import config
from proofroom.crustdata import FIXTURE, LIVE, Crustdata, _slug, sum_credits
from proofroom.errors import CrustError
from proofroom.graph import company_record, date_and_precision, normalize_employment
from proofroom.research_models import (FounderProfile, Metric, NewsItem, Peer, Point,
                                       Series, Signals)

log = logging.getLogger(__name__)

ENRICH = "/company/enrich"
SEARCH = "/company/search"
JOBS = "/job/search"
FUNDING_LABEL = "indexed record (Crunchbase-derived)"

# All useful groups. Not requested by default: technographics (+2 credits),
# social_posts (+5), social_profiles (crunchbase sub-fields are disabled on the
# event key, so the group would be denied).
ENRICH_FIELDS: tuple[str, ...] = (
    "basic_info", "funding", "people", "news", "headcount", "revenue", "hiring",
    "followers", "web_traffic", "competitors", "taxonomy", "employee_reviews", "seo",
    "locations", "software_reviews", "public_launches", "market_intel", "metadata")
# Groups whose absence is worth a limitation line in the report.
CORE_GROUPS = ("basic_info", "funding", "people", "headcount", "revenue", "followers",
               "web_traffic", "taxonomy", "news")

CROWDING_HIGH = 100     # funded peers in 24 months -> "high" (scoring.CROWDED_FUNDED_PEERS)
CROWDING_MEDIUM = 30    # 30-99 -> "medium"; below 30 -> "low"
PEER_LIMIT = 8
MAX_CATEGORY_PROBES = 4
MIN_PEER_POOL = 10
FOUNDED_WINDOW_YEARS = 6
FUNDED_WINDOW_MONTHS = 24
JOB_WINDOW_MONTHS = 3
LOGO_MAX_BYTES = 500_000
LOGO_TIMEOUT_S = 10.0

GENERIC_CATEGORIES = frozenset(c.casefold() for c in (
    "Artificial Intelligence (AI)", "Artificial Intelligence", "Software", "SaaS",
    "Information Technology", "Internet", "Computer", "Sales", "Marketing", "Advertising",
    "Enterprise Software", "Machine Learning", "Generative AI", "Analytics", "Mobile",
    "Apps", "Consumer", "B2B", "Technology", "Web Development", "Big Data", "Cloud Computing",
    "Consulting", "Professional Services", "Finance", "Financial Services", "Health Care",
))

# Well-known big tech companies and scaleups, matched against past employer names.
NOTABLE_EMPLOYERS: dict[str, tuple[str, ...]] = {
    "Google": ("google", "alphabet", "google deepmind", "deepmind", "youtube"),
    "Apple": ("apple",),
    "Meta": ("meta", "facebook", "instagram", "whatsapp"),
    "Microsoft": ("microsoft",),
    "Amazon": ("amazon", "amazon web services", "aws"),
    "Twitter/X": ("twitter", "x corp"),
    "Stripe": ("stripe",),
    "Airbnb": ("airbnb",),
    "Uber": ("uber",),
    "Coinbase": ("coinbase",),
    "Affirm": ("affirm",),
    "Salesforce": ("salesforce",),
    "Netflix": ("netflix",),
    "LinkedIn": ("linkedin",),
    "Dropbox": ("dropbox",),
    "Square/Block": ("square", "block"),
    "Shopify": ("shopify",),
    "Atlassian": ("atlassian",),
    "Palantir": ("palantir", "palantir technologies"),
    "OpenAI": ("openai",),
    "Anthropic": ("anthropic",),
    "Figma": ("figma",),
    "Notion": ("notion", "notion labs"),
    "Snowflake": ("snowflake",),
    "Databricks": ("databricks",),
}
# Aliases that are common words: only an exact employer name counts.
_EXACT_ONLY = frozenset({"square", "block", "meta", "notion", "x corp", "apple", "amazon"})

_FOUNDER_RE = re.compile(r"\b(co[\s-]?founder|founder|cofounder)\b", re.I)
_NOT_FOUNDER_RE = re.compile(r"\b(fellow|in residence|program|programme|scout)\b", re.I)

NEWS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "legal_risk": ("lawsuit", "sued", "sues", "fraud", "investigation", "layoffs", "laid off",
                   "shut down", "shuts down", "breach", "settlement", "sec", "probe",
                   "bankruptcy"),
    "funding": ("raise", "raises", "raised", "raising", "funding", "series a", "series b",
                "series c", "series d", "series e", "seed", "pre-seed", "round", "valuation",
                "tender", "investment", "invests", "backed", "funding rounds"),
    "people": ("hires", "hired", "appoints", "appointed", "names", "joins", "ceo", "cto",
               "cfo", "coo", "chief", "steps down", "departs", "executive", "promoted"),
    "product": ("launch", "launches", "launched", "unveils", "introduces", "releases",
                "release", "announces", "new feature", "product", "platform", "integration",
                "partners", "partnership", "expands", "acquires", "acquired", "rolls out"),
}


# ---- small helpers ------------------------------------------------------------------

def _num(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # NaN -> None


def _has_data(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, dict):
        return any(_has_data(x) for x in v.values())
    if isinstance(v, (list, tuple, str)):
        return len(v) > 0
    return True


def _pct(v: float | None, digits: int = 1) -> str:
    return "n/a" if v is None else f"{v:+.{digits}f}%"


def _usd(v: float | None) -> str:
    if v is None:
        return "n/a"
    a = abs(v)
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            s = f"{v / div:.1f}".rstrip("0").rstrip(".")
            return f"${s}{suf}"
    return f"${v:,.0f}"


def _int_str(v: float | None) -> str:
    return "n/a" if v is None else f"{v:,.0f}"


def _month(raw: Any) -> str:
    s = str(raw or "").strip()[:10]
    if len(s) >= 7 and s[:4].isdigit() and s[5:7].isdigit() and not s.startswith("1970-01"):
        return s[:7]
    return ""


def _iso_day(raw: Any) -> date | None:
    s = str(raw or "").strip()[:10]
    try:
        d = date.fromisoformat(s)
    except ValueError:
        return None
    return None if d.year <= 1970 else d


def _months_between(a: date, b: date) -> float:
    return (b - a).days / 30.4375


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    return date(d.year + y, m + 1, 1)


def _norm(name: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", (name or "").casefold()).split())


def monthly(points: Iterable[dict], value_key: str) -> list[Point]:
    """Weekly/daily `[{date, <value_key>}]` -> last value per calendar month, sorted."""
    by_month: dict[str, tuple[str, float]] = {}
    for p in points or []:
        if not isinstance(p, dict):
            continue
        m, v = _month(p.get("date")), _num(p.get(value_key))
        if not m or v is None:
            continue
        stamp = str(p.get("date"))[:10]
        if m not in by_month or stamp >= by_month[m][0]:
            by_month[m] = (stamp, v)
    return [Point(date=m, value=by_month[m][1]) for m in sorted(by_month)]


def change_pct(points: list[Point], months: int) -> float | None:
    """% change from the point `months` before the last one to the last one."""
    if not points:
        return None
    last = points[-1]
    y, m = int(last.date[:4]), int(last.date[5:7])
    back = _add_months(date(y, m, 1), -months).isoformat()[:7]
    prev = next((p for p in points if p.date == back), None)
    if prev is None or not prev.value:
        return None
    return (last.value / prev.value - 1) * 100


def cagr_pct(points: list[Point]) -> tuple[float | None, int]:
    """Annualised growth from the first positive monthly point to the last (>=12 months)."""
    pos = [p for p in points if p.value > 0]
    if len(pos) < 2:
        return None, 0
    a, b = pos[0], pos[-1]
    months = (int(b.date[:4]) - int(a.date[:4])) * 12 + int(b.date[5:7]) - int(a.date[5:7])
    if months < 12:
        return None, months
    return ((b.value / a.value) ** (12 / months) - 1) * 100, months


def crowding_level(funded_peers_24m: int | None) -> str:
    if funded_peers_24m is None:
        return "unknown"
    if funded_peers_24m >= CROWDING_HIGH:
        return "high"
    if funded_peers_24m >= CROWDING_MEDIUM:
        return "medium"
    return "low"


def public_listing(record: dict) -> tuple[bool, str]:
    """Public only when an IPO date is indexed; a bare ticker is treated as a namesake."""
    pm = ((record.get("revenue") or {}).get("public_markets")) or {}
    ipo = str(pm.get("ipo_date") or "").strip()
    symbols = [str(s) for s in pm.get("stock_symbols") or [] if s]
    if ipo:
        return True, f"public: IPO {ipo[:10]}" + (f", tickers {', '.join(symbols)}" if symbols else "")
    if symbols:
        return False, (f"private: ticker {', '.join(symbols)} in the index has no IPO date "
                       "(treated as a namesake)")
    return False, "private: no IPO date indexed"


def classify_news(title: str, company: str = "") -> str:
    """Heuristic title-keyword class. When `company` is given, a title that does not
    name the company is "other" (namesakes and round-ups are not attributed)."""
    t = f" {_norm(title)} "
    named = bool(company) and f" {_norm(company)} " in t

    def hit(kind: str) -> bool:
        return any(f" {_norm(k)} " in t for k in NEWS_KEYWORDS[kind])
    if company and not named:
        return "other"
    for kind in ("legal_risk", "funding", "people", "product"):
        if hit(kind):
            return kind
    return "other"


def notable_employers(names: Iterable[str]) -> list[str]:
    out: list[str] = []
    for raw in names:
        n = _norm(raw)
        if not n:
            continue
        for label, aliases in NOTABLE_EMPLOYERS.items():
            for a in aliases:
                if n == a or (a not in _EXACT_ONLY and n.startswith(a + " ")):
                    if label not in out:
                        out.append(label)
                    break
    return out


def is_founder_title(title: str) -> bool:
    return bool(_FOUNDER_RE.search(title or "")) and not _NOT_FOUNDER_RE.search(title or "")


# ---- metric builders ------------------------------------------------------------------

class _Builder:
    def __init__(self, sig: Signals):
        self.sig = sig

    def metric(self, key: str, label: str, value: float | None, unit: str = "",
               display: str = "", period: str = "", source: str = "", as_of: str = "") -> None:
        if value is None and not display:
            return
        self.sig.metrics[key] = Metric(key=key, label=label, value=value, unit=unit,
                                       display=display or ("n/a" if value is None else str(value)),
                                       period=period, source=source, as_of=as_of)

    def series(self, key: str, label: str, unit: str, points: list[Point], source: str) -> None:
        if points:
            self.sig.series[key] = Series(key=key, label=label, unit=unit, points=points,
                                          source=source)

    def limit(self, text: str) -> None:
        if text not in self.sig.limitations:
            self.sig.limitations.append(text)


def _headcount(b: _Builder, rec: dict) -> None:
    hc = rec.get("headcount") or {}
    total = _num(hc.get("total"))
    b.sig.headcount_total = total
    pts = monthly(hc.get("timeseries") or [], "employee_count")
    src = f"{ENRICH} headcount.timeseries"
    b.series("headcount", "Employees (indexed profiles)", "people", pts, src)
    as_of = pts[-1].date if pts else ""
    b.metric("headcount_total", "Headcount", total, "people", _int_str(total),
             "current", f"{ENRICH} headcount.total", as_of)
    gp = hc.get("growth_percent") or {}
    for key, api_key, months, label in (("mom", "mom", 1, "1 month"), ("qoq", "qoq", 3, "3 months"),
                                        ("6m", "six_months", 6, "6 months"),
                                        ("yoy", "yoy", 12, "12 months"),
                                        ("2y", "two_years", 24, "24 months")):
        v, src_k = _num(gp.get(api_key)), f"{ENRICH} headcount.growth_percent.{api_key}"
        if v is None:
            v, src_k = change_pct(pts, months), f"computed from {ENRICH} headcount.timeseries"
        b.metric(f"headcount_{key}_pct", f"Headcount growth ({label})", v, "%", _pct(v),
                 f"trailing {label}", src_k, as_of)
    cagr, months = cagr_pct(pts)
    if cagr is not None:
        b.metric("headcount_cagr", "Headcount CAGR", cagr, "%", _pct(cagr),
                 f"annualised over {months} months", f"computed from {src}", as_of)
    roles = {str(k): round(float(v), 1) for k, v in (hc.get("by_role_percent") or {}).items()
             if _num(v) is not None}
    b.sig.role_mix = dict(sorted(roles.items(), key=lambda kv: -kv[1]))
    regions = {str(k): round(float(v), 1) for k, v in (hc.get("by_region_percent") or {}).items()
               if _num(v) is not None}
    b.sig.region_mix = dict(sorted(regions.items(), key=lambda kv: -kv[1])[:10])
    eng = roles.get("Engineering")
    if eng is not None:
        b.metric("engineering_share_pct", "Engineering share of headcount", eng, "%",
                 f"{eng:.1f}%", "current", f"{ENRICH} headcount.by_role_percent.Engineering", as_of)
    # Per-function series for the three largest current functions.
    fn_ts = ((hc.get("by_function_timeseries") or {}).get("CURRENT_FUNCTION")) or {}
    absolute = hc.get("by_role_absolute") or {}
    ranked = sorted(fn_ts, key=lambda f: -(_num(absolute.get(f)) or
                                            _num((fn_ts[f] or [{}])[-1].get("employee_count")) or 0))
    for fn in ranked[:3]:
        slug = re.sub(r"[^a-z0-9]+", "_", fn.casefold()).strip("_")
        b.series(f"headcount_{slug}", f"{fn} headcount", "people",
                 monthly(fn_ts[fn] or [], "employee_count"),
                 f"{ENRICH} headcount.by_function_timeseries.CURRENT_FUNCTION.{fn}")


def _web(b: _Builder, rec: dict, domain: str) -> None:
    traffic = ((rec.get("web_traffic") or {}).get("domain_traffic")) or {}
    if not isinstance(traffic, dict) or not traffic:
        return
    primary = str((rec.get("basic_info") or {}).get("primary_domain") or domain).lower()
    key = primary if primary in traffic else domain if domain in traffic else max(
        traffic, key=lambda d: _num((traffic[d] or {}).get("monthly_visitors")) or 0)
    t = traffic.get(key) or {}
    base = f"{ENRICH} web_traffic.domain_traffic['{key}']"
    pts = monthly(t.get("monthly_visitors_timeseries") or [], "monthly_visitors")
    b.series("web_visitors", f"Monthly web visitors ({key})", "visitors/month", pts,
             f"{base}.monthly_visitors_timeseries")
    as_of = pts[-1].date if pts else ""
    latest = _num(t.get("monthly_visitors"))
    if latest is None and pts:
        latest = pts[-1].value
    b.metric("web_visitors_latest", "Monthly web visitors", latest, "visitors/month",
             _int_str(latest), "latest month", f"{base}.monthly_visitors", as_of)
    qoq, src = _num(t.get("qoq_pct")), f"{base}.qoq_pct"
    if qoq is None:
        qoq, src = change_pct(pts, 3), f"computed from {base}.monthly_visitors_timeseries"
    b.metric("web_visitors_qoq_pct", "Web visitors growth (3 months)", qoq, "%", _pct(qoq),
             "trailing 3 months", src, as_of)
    yoy = change_pct(pts, 12)
    b.metric("web_visitors_yoy_pct", "Web visitors growth (12 months)", yoy, "%", _pct(yoy),
             "trailing 12 months", f"computed from {base}.monthly_visitors_timeseries", as_of)
    if yoy is None and pts:
        b.limit("Web visitors YoY not computable (no non-zero month 12 months before the latest).")


def _followers(b: _Builder, rec: dict) -> None:
    fo = rec.get("followers") or {}
    pts = monthly(fo.get("timeseries") or [], "follower_count")
    b.series("followers", "Company page followers", "followers", pts,
             f"{ENRICH} followers.timeseries")
    as_of = pts[-1].date if pts else ""
    count = _num(fo.get("count"))
    b.metric("followers_count", "Followers", count, "followers", _int_str(count), "current",
             f"{ENRICH} followers.count", as_of)
    yoy, src = _num(fo.get("yoy_percent")), f"{ENRICH} followers.yoy_percent"
    if yoy is None:
        yoy, src = change_pct(pts, 12), f"computed from {ENRICH} followers.timeseries"
    b.metric("followers_yoy_pct", "Follower growth (12 months)", yoy, "%", _pct(yoy),
             "trailing 12 months", src, as_of)


def _revenue(b: _Builder, rec: dict) -> None:
    est = ((rec.get("revenue") or {}).get("estimated")) or {}
    ts = est.get("timeseries") or []
    low = monthly(ts, "revenue_lower_bound_usd")
    high = monthly(ts, "revenue_upper_bound_usd")
    src = f"{ENRICH} revenue.estimated.timeseries"
    b.series("revenue_low", "Estimated revenue, lower bound", "USD", low, src)
    b.series("revenue_high", "Estimated revenue, upper bound", "USD", high, src)
    lo, hi = _num(est.get("lower_bound_usd")), _num(est.get("upper_bound_usd"))
    if lo is None and low:
        lo = low[-1].value
    if hi is None and high:
        hi = high[-1].value
    as_of = high[-1].date if high else ""
    if lo is not None and hi is not None:
        b.sig.revenue_band_usd = (lo, hi)
        b.metric("revenue_band", "Estimated revenue band", hi, "USD",
                 f"{_usd(lo)}–{_usd(hi)} (third-party estimate)", "latest estimate",
                 f"{ENRICH} revenue.estimated.lower_bound_usd/upper_bound_usd", as_of)
    if len(low) >= 2 and len(high) >= 2:
        first = (low[0].value + high[0].value) / 2
        last = (low[-1].value + high[-1].value) / 2
        trend = 0.0 if first == last else ((last / first - 1) * 100 if first else 100.0)
        if trend == 0:
            disp = f"flat ({_usd(low[-1].value)}–{_usd(high[-1].value)} since {low[0].date})"
        else:
            disp = (f"{_pct(trend)} band midpoint ({_usd(low[0].value)}–{_usd(high[0].value)} "
                    f"in {low[0].date} → {_usd(low[-1].value)}–{_usd(high[-1].value)})")
        b.metric("revenue_trend", "Revenue band movement", trend, "%", disp,
                 f"{low[0].date} to {low[-1].date}", f"computed from {src}", low[-1].date)


def _hiring_reviews_seo(b: _Builder, rec: dict) -> None:
    hiring = rec.get("hiring") or {}
    openings = _num(hiring.get("openings_count"))
    if openings is not None:
        b.sig.hiring_openings = int(openings)
        b.metric("hiring_openings", "Open roles", openings, "roles", _int_str(openings),
                 "current", f"{ENRICH} hiring.openings_count")
    rating = (rec.get("employee_reviews") or {}).get("overall_rating") or {}
    r, n = _num(rating.get("rating")), _num(rating.get("total_count"))
    if r is not None:
        b.sig.employee_rating = r
        b.metric("employee_rating", "Employee review rating", r, "rating",
                 f"{r:.1f}/5" + (f" ({n:.0f} reviews)" if n else ""), "all time",
                 f"{ENRICH} employee_reviews.overall_rating.rating")
    sw = rec.get("software_reviews") or {}
    sr, sn = _num(sw.get("average_rating")), _num(sw.get("review_count"))
    if sr is not None:
        b.metric("software_rating", "Software review rating", sr, "rating",
                 f"{sr:.2f}" + (f" ({sn:.0f} reviews; scale as indexed)" if sn else ""),
                 "all time", f"{ENRICH} software_reviews.average_rating")
    clicks = _num((rec.get("seo") or {}).get("monthly_organic_clicks"))
    b.metric("seo_organic_clicks", "Monthly organic search clicks", clicks, "clicks/month",
             _int_str(clicks), "latest month", f"{ENRICH} seo.monthly_organic_clicks")
    launches = [x for x in ((rec.get("public_launches") or {}).get("launches") or [])
                if isinstance(x, dict)]
    if launches:
        ups = sum(_num(x.get("num_upvotes")) or 0 for x in launches)
        b.metric("public_launches", "Public product launches", float(len(launches)), "launches",
                 f"{len(launches)} launches, {ups:,.0f} upvotes (may include namesakes)",
                 "all time", f"{ENRICH} public_launches.launches")


def _primary_rounds(rec: dict) -> tuple[list[dict], list[dict]]:
    ms = [m for m in ((rec.get("funding") or {}).get("milestones") or []) if isinstance(m, dict)]
    secondary = [m for m in ms if "secondary" in str(m.get("round_type") or "").casefold()]
    primary = [m for m in ms if m not in secondary and not m.get("is_fund")]
    return primary, secondary


def _round_date(m: dict) -> tuple[date | None, str]:
    raw = m.get("funding_date") or m.get("date")
    _, prec = date_and_precision(raw)
    return _iso_day(raw), prec


def _funding(b: _Builder, rec: dict, today: date) -> None:
    fu = rec.get("funding") or {}
    src = f"{ENRICH} funding"
    primary, secondary = _primary_rounds(rec)
    total = _num(fu.get("total_investment_usd"))
    b.metric("total_funding_usd", "Total funding", total, "USD",
             f"{_usd(total)} ({FUNDING_LABEL})", "all time", f"{src}.total_investment_usd")
    if secondary:
        p_sum = sum(_num(m.get("amount_usd")) or 0 for m in primary)
        s_sum = sum(_num(m.get("amount_usd")) or 0 for m in secondary)
        b.metric("total_funding_primary_usd", "Primary funding (excl. secondary sales)", p_sum,
                 "USD", f"{_usd(p_sum)} ({FUNDING_LABEL}; excludes {_usd(s_sum)} in "
                 f"{len(secondary)} secondary-market entries)", "all time",
                 f"computed from {src}.milestones[].amount_usd")
        b.limit(f"Indexed total funding includes {len(secondary)} secondary-market "
                f"(tender) entries; primary-only sum shown separately.")
    dated = []
    for m in primary:
        d, prec = _round_date(m)
        if d:
            dated.append((d, prec, m))
    dated.sort(key=lambda x: x[0])
    if primary:
        n = float(len(primary))
        b.metric("num_rounds", "Primary funding rounds", n, "rounds",
                 f"{n:.0f}" + (f" (+{len(secondary)} secondary)" if secondary else ""),
                 "all time", f"{src}.milestones ({FUNDING_LABEL})")
    elif _num(fu.get("num_funding_rounds")) is not None:
        n = _num(fu.get("num_funding_rounds"))
        b.metric("num_rounds", "Funding rounds", n, "rounds", f"{n:.0f}", "all time",
                 f"{src}.num_funding_rounds ({FUNDING_LABEL})")
    precise = [x for x in dated if x[1] in ("day", "month")]
    gaps = [_months_between(a[0], c[0]) for a, c in zip(precise, precise[1:])]
    if gaps:
        med = statistics.median(gaps)
        b.metric("round_cadence_months", "Median months between rounds", med, "months",
                 f"{med:.1f} months", f"{len(gaps)} gaps between dated primary rounds",
                 f"computed from {src}.milestones[].funding_date ({FUNDING_LABEL})")
    last_date, basis = None, ""
    if dated:
        last_date, prec, m = dated[-1]
        basis = f"{m.get('round_type') or 'round'} on {last_date.isoformat()}" + (
            " (year precision)" if prec == "year" else "")
        amt = _num(m.get("amount_usd"))
        b.metric("last_round", "Last primary round", amt, "USD",
                 f"{str(m.get('round_type') or 'round').replace('_', ' ')} "
                 f"{_usd(amt) if amt else '(undisclosed)'} on {last_date.isoformat()}"
                 f" ({FUNDING_LABEL})", "", f"{src}.milestones", last_date.isoformat())
    elif _iso_day(fu.get("last_fundraise_date")):
        last_date = _iso_day(fu.get("last_fundraise_date"))
        basis = f"{fu.get('last_round_type') or 'round'} on {last_date.isoformat()}"
    if last_date:
        months = round(_months_between(last_date, today), 1)
        b.metric("months_since_last_round", "Months since last primary round", months, "months",
                 f"{months:.1f} months", f"since {basis}",
                 f"computed from {src}.milestones ({FUNDING_LABEL}) vs {today.isoformat()}",
                 today.isoformat())
    if secondary:
        sd = max((d for d in (_round_date(m)[0] for m in secondary) if d), default=None)
        if sd:
            b.metric("last_secondary_date", "Last secondary-market entry", None, "",
                     f"{sd.isoformat()} ({FUNDING_LABEL})", "", f"{src}.milestones",
                     sd.isoformat())
    hc = b.sig.headcount_total
    base = b.sig.metrics.get("total_funding_primary_usd") or b.sig.metrics.get("total_funding_usd")
    if hc and base and base.value:
        v = base.value / hc
        b.metric("funding_per_employee_usd", "Funding per employee", v, "USD",
                 f"{_usd(v)} ({FUNDING_LABEL})", "current", f"computed: {base.key} / headcount_total")


# ---- founders -----------------------------------------------------------------------

def _get(obj: Any, key: str, default: Any = None) -> Any:
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def _start_date(raw: Any) -> date | None:
    s = str(raw or "").strip()
    return _iso_day({4: s + "-01-01", 7: s + "-01"}.get(len(s), s))


def _founder_from_parts(name: str, person_id: int | None, title: str, since: str,
                        past: list, current: list, education: list[str], today: date,
                        source: str) -> FounderProfile:
    def start_key(e: Any) -> str:
        return str(_get(e, "start") or "")
    past_sorted = sorted(past, key=start_key, reverse=True)
    employers: list[str] = []
    for e in past_sorted:
        n = str(_get(e, "employer_name") or "").strip()
        if n and n not in employers:
            employers.append(n)
    starts = [d for d in (_start_date(_get(e, "start")) for e in list(past) + list(current)) if d]
    years = round((today - min(starts)).days / 365.25, 1) if starts else None
    return FounderProfile(
        name=name, person_id=person_id, title=title, since=since, prior_employers=employers,
        prior_founder=any(is_founder_title(str(_get(e, "title") or "")) for e in past),
        big_tech_or_scaleup=notable_employers(employers), education=education,
        years_experience=years, source=source)


def founders_from_record(rec: dict, company_id: int | None, today: date) -> list[FounderProfile]:
    out = []
    for p in ((rec.get("people") or {}).get("founders")) or []:
        if not isinstance(p, dict):
            continue
        prof = p.get("basic_profile") or {}
        details = ((p.get("experience") or {}).get("employment_details")) or {}
        cur = [normalize_employment(e, True) for e in details.get("current") or []
               if isinstance(e, dict)]
        past = [normalize_employment(e, False) for e in details.get("past") or []
                if isinstance(e, dict)]
        past = [e for e in past if company_id is None or e.employer_id != company_id]
        at = [e for e in cur if company_id is not None and e.employer_id == company_id]
        title = (at[0].title if at else "") or str(prof.get("current_title") or "")
        since = at[0].start if at else ""
        edu = []
        for s in ((p.get("education") or {}).get("schools")) or []:
            if not isinstance(s, dict) or not s.get("school"):
                continue
            extra = ", ".join(str(x) for x in (s.get("degree"), s.get("field_of_study")) if x)
            edu.append(f"{s['school']}" + (f" — {extra}" if extra else ""))
        try:
            pid = int(p.get("crustdata_person_id"))
        except (TypeError, ValueError):
            pid = None
        out.append(_founder_from_parts(str(prof.get("name") or ""), pid, title, since, past, cur,
                                       edu, today, f"{ENRICH} people.founders"))
    return out


def merge_team(founders: list[FounderProfile], team: list | None, company_id: int | None,
               today: date) -> list[FounderProfile]:
    """Union TeamRow-like objects (name, person_id, past, current_at_subject) into the list."""
    for row in team or []:
        name = str(_get(row, "name") or "")
        pid = _get(row, "person_id")
        if not name:
            continue
        past = [e for e in (_get(row, "past") or [])
                if company_id is None or _get(e, "employer_id") != company_id]
        cur = list(_get(row, "current_at_subject") or []) + list(_get(row, "other_current") or [])
        match = next((f for f in founders if (pid is not None and f.person_id == pid)
                      or _norm(f.name) == _norm(name)), None)
        extra = _founder_from_parts(name, pid, str(_get(cur[0], "title") or "") if cur else "",
                                    str(_get(cur[0], "start") or "") if cur else "", past, cur, [],
                                    today, str(_get(row, "source") or "team"))
        if match is None:
            founders.append(extra)
            continue
        for n in extra.prior_employers:
            if n not in match.prior_employers:
                match.prior_employers.append(n)
        match.prior_founder = match.prior_founder or extra.prior_founder
        match.big_tech_or_scaleup = notable_employers(match.prior_employers)
        if match.years_experience is None:
            match.years_experience = extra.years_experience
    return founders


# ---- news ------------------------------------------------------------------------------

def news_items(rec: dict, company: str, max_items: int = 25) -> list[NewsItem]:
    seen, out = set(), []
    for n in rec.get("news") or []:
        if not isinstance(n, dict):
            continue
        title = str(n.get("article_title") or "").strip()
        url = str(n.get("article_url") or "").strip()
        if not title or _norm(title) in seen:
            continue
        seen.add(_norm(title))
        d = _iso_day(n.get("article_publish_date"))
        out.append(NewsItem(title=title, url=url, date=d.isoformat() if d else "",
                            publisher=str(n.get("article_publisher_name") or ""),
                            kind=classify_news(title, company)))
    out.sort(key=lambda x: x.date or "0000", reverse=True)
    return out[:max_items]


# ---- market (Company Search) ------------------------------------------------------------

def candidate_categories(rec: dict) -> list[str]:
    cats = [str(c) for c in ((rec.get("taxonomy") or {}).get("categories") or []) if c]
    specific = [c for c in cats if c.casefold() not in GENERIC_CATEGORIES]
    return specific[:MAX_CATEGORY_PROBES]


def _founded_floor(rec: dict, today: date) -> int:
    yf = _num((rec.get("basic_info") or {}).get("year_founded"))
    floor = today.year - FOUNDED_WINDOW_YEARS
    return min(floor, int(yf) - 2) if yf else floor


def _window_conds(categories: list[str], founded_floor: int, company_id: int) -> list[dict]:
    return ([{"field": "taxonomy.categories", "type": "=", "value": c} for c in categories]
            + [{"field": "basic_info.year_founded", "type": "=>", "value": founded_floor},
               {"field": "crustdata_company_id", "type": "!=", "value": int(company_id)}])


def count_body(categories: str | list[str], founded_floor: int, company_id: int) -> dict:
    """Pool size probe: limit 1, id only (base 0.03 + taxonomy filter 0.1 credits)."""
    cats = [categories] if isinstance(categories, str) else list(categories)
    return {"filters": {"op": "and", "conditions": _window_conds(cats, founded_floor, company_id)},
            "fields": ["crustdata_company_id"], "limit": 1}


PEER_FIELDS = ["crustdata_company_id", "basic_info.name", "basic_info.primary_domain",
               "basic_info.year_founded", "headcount.total", "headcount.growth_percent",
               "funding.total_investment_usd", "funding.last_round_type",
               "funding.last_fundraise_date"]


def peers_body(categories: str | list[str], founded_floor: int, company_id: int,
               funded_since: str) -> dict:
    cats = [categories] if isinstance(categories, str) else list(categories)
    conds = _window_conds(cats, founded_floor, company_id) + [
        {"field": "funding.last_fundraise_date", "type": "=>", "value": funded_since}]
    return {"filters": {"op": "and", "conditions": conds},
            "sorts": [{"field": "funding.total_investment_usd", "order": "desc"}],
            "fields": PEER_FIELDS, "limit": PEER_LIMIT}


def peer_from_search(c: dict) -> Peer | None:
    info = c.get("basic_info") or {}
    hc = c.get("headcount") or {}
    fu = c.get("funding") or {}
    name = str(info.get("name") or "")
    if not name:
        return None
    gp = hc.get("growth_percent") or {}
    yoy = _num(gp.get("12m", gp.get("yoy")))
    try:
        cid = int(c.get("crustdata_company_id"))
    except (TypeError, ValueError):
        cid = None
    yf = _num(info.get("year_founded"))
    return Peer(name=name, domain=str(info.get("primary_domain") or ""), company_id=cid,
                headcount=_num(hc.get("total")), headcount_yoy_pct=yoy,
                total_funding_usd=_num(fu.get("total_investment_usd")),
                last_round_type=str(fu.get("last_round_type") or ""),
                last_round_date=str(fu.get("last_fundraise_date") or "")[:10],
                year_founded=int(yf) if yf else None, source=SEARCH)


def _total(resp: Any) -> int | None:
    t = resp.get("total_count") if isinstance(resp, dict) else None
    return int(t) if isinstance(t, (int, float)) and not isinstance(t, bool) else None


# Last-round types that are not venture equity: such results stay in the funded count
# (the search cannot exclude them without a new request) but not in the peer table.
NON_EQUITY_ROUNDS = frozenset({"grant", "debt_financing", "non_equity_assistance",
                               "equity_crowdfunding", "product_crowdfunding", "secondary_market",
                               "post_ipo_equity", "post_ipo_debt", "post_ipo_secondary",
                               "initial_coin_offering"})

# A generic tag that still narrows a niche when paired with a specific category.
PAIRING_TAGS = ("Artificial Intelligence (AI)", "Generative AI")


def choose_niche(cands: list[str], counts: dict[str, int], all_categories: list[str]
                 ) -> list[str]:
    """Smallest specific pool with >= MIN_PEER_POOL companies, paired with the next
    smallest (or an AI tag the company carries) for a narrower niche. The pair is
    kept only if its own pool is >= MIN_PEER_POOL (checked by the caller)."""
    ranked = sorted((c for c in cands if counts.get(c, -1) >= MIN_PEER_POOL),
                    key=lambda c: (counts[c], cands.index(c)))
    if not ranked:
        known = [c for c in cands if c in counts]
        return [max(known, key=lambda c: counts[c])] if known else cands[:1]
    if len(ranked) >= 2:
        return ranked[:2]
    tag = next((t for t in PAIRING_TAGS if t in all_categories and t != ranked[0]), None)
    return [ranked[0], tag] if tag else ranked[:1]


async def _probe(client: Crustdata, groups: list[list[str]], floor: int,
                 company_id: int) -> dict[tuple, int | str | None]:
    """Pool size per category group: an int, None (no total_count) or an error string."""
    resps = await asyncio.gather(*(client.request("POST", SEARCH, count_body(g, floor, company_id))
                                   for g in groups), return_exceptions=True)
    out: dict[tuple, int | str | None] = {}
    for g, r in zip(groups, resps):
        out[tuple(g)] = (f"{' + '.join(g)}: {getattr(r, 'type', type(r).__name__)}"
                         if isinstance(r, BaseException) else _total(r))
    return out


async def _market(b: _Builder, client: Crustdata, rec: dict, company_id: int,
                  today: date) -> None:
    tax = rec.get("taxonomy") or {}
    mk = b.sig.market
    mk.categories = [str(c) for c in tax.get("categories") or [] if c]
    naics = tax.get("primary_naics_detail") or {}
    if naics.get("naics_code"):
        mk.naics = f"{naics.get('naics_code')} {naics.get('industry') or ''}".strip()
    comp = rec.get("competitors") or {}
    raw = [str(d).strip() for d in (comp.get("paid_seo") or []) + (comp.get("organic_seo") or [])]
    mk.seo_competitor_domains = list(dict.fromkeys(d for d in raw if d))[:15]
    cands = candidate_categories(rec) or mk.categories[:1]
    if not cands:
        b.limit("No taxonomy category indexed: peer search skipped, crowding unknown.")
        return
    floor = _founded_floor(rec, today)
    counts = await _probe(client, [[c] for c in cands], floor, company_id)
    known = {k: n for k, n in counts.items() if isinstance(n, int)}
    if not known and any(isinstance(n, str) for n in counts.values()):
        b.limit(f"Company Search failed ({'; '.join(str(n) for n in counts.values())[:160]}):"
                " crowding unknown.")
        return
    niche = choose_niche(cands, {k[0]: n for k, n in known.items()}, mk.categories)
    if len(niche) == 2:
        pair = await _probe(client, [niche], floor, company_id)
        counts.update(pair)
        n2 = pair.get(tuple(niche))
        if not isinstance(n2, int) or n2 < MIN_PEER_POOL:
            niche = niche[:1]
    chosen = list(niche)
    mk.category = " + ".join(chosen)
    pc = counts.get(tuple(chosen))
    mk.peer_count = pc if isinstance(pc, int) else None
    funded_since = _add_months(today.replace(day=1), -FUNDED_WINDOW_MONTHS).isoformat()
    probes = ", ".join(f"{' + '.join(k)}={n if isinstance(n, int) else 'n/a'}"
                       for k, n in counts.items())
    mk.source = (f"{SEARCH} taxonomy.categories = {' AND '.join(repr(c) for c in chosen)}, "
                 f"basic_info.year_founded >= {floor}; funded = funding.last_fundraise_date >= "
                 f"{funded_since} (pool probes: {probes})")
    try:
        resp = await client.request("POST", SEARCH, peers_body(chosen, floor, company_id,
                                                               funded_since))
    except CrustError as e:
        b.limit(f"Company Search peer list failed ({e.type}): crowding unknown.")
        return
    companies = [c for c in (resp.get("companies") if isinstance(resp, dict) else []) or []
                 if isinstance(c, dict)]
    found = [p for p in (peer_from_search(c) for c in companies) if p and p.company_id != company_id]
    peers = [p for p in found if p.last_round_type not in NON_EQUITY_ROUNDS][:PEER_LIMIT]
    if len(peers) < len(found):
        b.limit(f"{len(found) - len(peers)} search result(s) whose last round was a grant, debt or "
                "crowdfunding were left out of the peer table (still in the funded count).")
    mk.peers = peers
    total = _total(resp)
    if total is None:
        total = len(peers)
        if len(companies) >= PEER_LIMIT:
            b.limit(f"Company Search gave no total_count: funded peers is a lower bound "
                    f"(>= {total}).")
    mk.funded_peers_24m = total
    mk.crowding = crowding_level(total)
    yoys = [p.headcount_yoy_pct for p in peers if p.headcount_yoy_pct is not None]
    if yoys:
        mk.median_peer_headcount_yoy_pct = round(statistics.median(yoys), 1)
    b.limit(f"Peers are companies tagged {mk.category!r} (Crustdata taxonomy), founded {floor} or "
            "later; the category match is coarse and is not a verified competitor set.")


async def _jobs(b: _Builder, client: Crustdata, company_id: int, today: date) -> None:
    since = _add_months(today.replace(day=1), -JOB_WINDOW_MONTHS).isoformat()
    body = {"filters": {"op": "and", "conditions": [
        {"field": "company.basic_info.company_id", "type": "=", "value": int(company_id)},
        {"field": "metadata.date_added", "type": "=>", "value": since}]},
        "limit": 0,
        "aggregations": [{"type": "count"},
                         {"type": "group_by", "field": "job_details.category", "agg": "count",
                          "size": 10}]}
    try:
        resp = await client.request("POST", JOBS, body)
    except CrustError as e:
        b.limit(f"Job Search unavailable ({e.type}): no job-listing count.")
        b.sig.coverage["job_search"] = False
        return
    aggs = resp.get("aggregations") if isinstance(resp, dict) else None
    count, cats = None, {}
    for a in aggs or []:
        if not isinstance(a, dict):
            continue
        if a.get("type") == "count":
            count = _num(a.get("value"))
        elif a.get("type") == "group_by":
            cats = {str(x.get("key")): int(_num(x.get("count")) or 0)
                    for x in a.get("buckets") or [] if isinstance(x, dict)}
    if count is None:
        count = _num(_total(resp))
    b.sig.coverage["job_search"] = bool(count)
    if count is None:
        return
    if not count:
        b.metric("job_postings_90d", "Job listings posted (last ~3 months)", 0.0, "listings",
                 "0 indexed (absence of indexed listings is not evidence of no hiring)",
                 f"posted since {since}", f"{JOBS} aggregations.count", today.isoformat())
        b.limit("No job listings indexed for this company in the last ~3 months; hiring "
                "activity is unknown, not zero.")
        return
    mix = ", ".join(f"{k} {v}" for k, v in sorted(cats.items(), key=lambda kv: -kv[1])[:4])
    b.metric("job_postings_90d", "Job listings posted (last ~3 months)", count, "listings",
             f"{count:.0f}" + (f" ({mix})" if mix else ""), f"posted since {since}",
             f"{JOBS} aggregations.count (company.basic_info.company_id = {company_id})",
             today.isoformat())
    if b.sig.hiring_openings is None:
        b.sig.hiring_openings = int(count)
        b.metric("hiring_openings", "Open roles (proxy)", count, "listings", f"{count:.0f}",
                 f"job listings posted since {since}; closed listings may remain indexed",
                 f"{JOBS} aggregations.count", today.isoformat())


# ---- logo ---------------------------------------------------------------------------------

_EXT = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png", "image/gif": "gif",
        "image/webp": "webp", "image/svg+xml": "svg"}
_MIME = {v: k for k, v in _EXT.items()} | {"jpg": "image/jpeg"}


def _logo_cache_dir() -> Path:
    return config.CACHE_DIR / "logos"


def _find_logo(directory: Path, stem: str) -> Path | None:
    for ext in ("jpg", "png", "gif", "webp", "svg"):
        p = directory / f"{stem}.{ext}"
        if p.is_file():
            return p
    return None


def _data_uri(path: Path) -> str:
    mime = _MIME.get(path.suffix.lstrip(".").lower(), "image/png")
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


async def download_logo(url: str, transport: httpx.AsyncBaseTransport | None = None
                        ) -> tuple[bytes, str]:
    """Return (bytes, extension). Raises ValueError on a non-image or oversized body."""
    async with httpx.AsyncClient(timeout=LOGO_TIMEOUT_S, follow_redirects=True,
                                 transport=transport) as http:
        async with http.stream("GET", url) as resp:
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
            if not ctype.startswith("image/") and ctype not in _GENERIC_TYPES:
                raise ValueError(f"not an image ({ctype})")
            buf = bytearray()
            async for chunk in resp.aiter_bytes():
                buf.extend(chunk)
                if len(buf) > LOGO_MAX_BYTES:
                    raise ValueError("logo larger than 500 KB")
    data = bytes(buf)
    if ctype.startswith("image/"):
        return data, _EXT.get(ctype, sniff_image(data) or "png")
    ext = sniff_image(data)  # S3 serves Crustdata logos as binary/octet-stream
    if not ext:
        raise ValueError(f"not an image ({ctype or 'no content-type'}, unknown bytes)")
    return data, ext


_GENERIC_TYPES = frozenset({"", "binary/octet-stream", "application/octet-stream"})


def sniff_image(data: bytes) -> str:
    """Image extension from magic bytes, or "" when the bytes are not a known image."""
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    head = data[:256].lstrip().lower()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in data[:1024].lower()):
        return "svg"
    return ""


async def _logo(b: _Builder, client: Crustdata, company_id: int) -> None:
    url = b.sig.logo_url
    if client.mode == FIXTURE:
        p = _find_logo(client.fixture_dir, "logo")
        if p:
            b.sig.logo_data_uri = _data_uri(p)
        elif url:
            b.limit("Logo not in the fixture: rendered without it.")
        b.sig.coverage["logo"] = bool(p)
        return
    if not url:
        b.sig.coverage["logo"] = False
        return
    cached = _find_logo(_logo_cache_dir(), str(company_id)) if client.mode != LIVE else None
    if cached:
        b.sig.logo_data_uri = _data_uri(cached)
        b.sig.coverage["logo"] = True
        return
    try:
        data, ext = await download_logo(url)
    except (httpx.HTTPError, ValueError) as e:
        b.limit(f"Logo download failed ({type(e).__name__}): rendered without it.")
        b.sig.coverage["logo"] = False
        return
    try:
        d = _logo_cache_dir()
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{company_id}.{ext}").write_bytes(data)
    except OSError as e:
        log.warning("logo cache write failed: %s", e)
    b.sig.logo_data_uri = f"data:{_MIME.get(ext, 'image/png')};base64,{base64.b64encode(data).decode()}"
    b.sig.coverage["logo"] = True


# ---- main entry ---------------------------------------------------------------------------

def _fixture_as_of(client: Crustdata) -> date | None:
    if client.mode != FIXTURE:
        return None
    try:
        meta = json.loads((client.fixture_dir / "signals_meta.json").read_text(encoding="utf-8"))
        return date.fromisoformat(meta["as_of"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _has_groups(record: dict | None) -> bool:
    return isinstance(record, dict) and all(g in record for g in ENRICH_FIELDS)


async def fetch_signals(client: Crustdata, company_id: int, domain: str,
                        record: dict | None = None, founders: list | None = None, *,
                        today: date | None = None, search: bool = True, jobs: bool = True,
                        logo: bool = True) -> Signals:
    """Fetch and normalize every investor signal for one company. Never raises on
    missing data: it records coverage and limitations instead. In FIXTURE mode the
    default `today` is the fixture's capture date so replays are deterministic."""
    today = today or _fixture_as_of(client) or date.today()
    start = len(client.attempts)
    domain = (domain or "").strip().lower()
    sig = Signals(company="", domain=domain, company_id=company_id)
    b = _Builder(sig)

    rec: dict = record if _has_groups(record) else {}
    if not rec:
        try:
            rec = company_record(await client.company_enrich(company_id, ENRICH_FIELDS))
        except CrustError as e:
            b.limit(f"Company Enrich failed ({e.type}): signals limited to what was passed in.")
            rec = record if isinstance(record, dict) else {}
    for g in ENRICH_FIELDS:
        present = _has_data(rec.get(g))
        sig.coverage[g] = present
        if not present and g in CORE_GROUPS:
            b.limit(f"No '{g}' data indexed for this company.")

    info = rec.get("basic_info") or {}
    sig.company = str(info.get("name") or domain)
    sig.logo_url = str(info.get("logo_permalink") or "")
    sig.description = str(info.get("description") or "")
    yf = _num(info.get("year_founded"))
    sig.year_founded = int(yf) if yf else None
    sig.status = str(info.get("status") or "")
    sig.hq = str((rec.get("locations") or {}).get("headquarters") or "")

    _headcount(b, rec)
    _web(b, rec, domain)
    _followers(b, rec)
    _revenue(b, rec)
    _hiring_reviews_seo(b, rec)
    _funding(b, rec, today)
    if sig.coverage.get("funding"):
        b.limit(f"Funding figures are an {FUNDING_LABEL}, not independent confirmation.")
    is_pub, why = public_listing(rec)
    b.metric("public_listing", "Public listing", 1.0 if is_pub else 0.0, "",
             why, "", f"{ENRICH} revenue.public_markets")
    if not is_pub and "ticker" in why:
        b.limit(f"Index lists a stock ticker without an IPO date; treated as private ({why}).")
    if sig.revenue_band_usd:
        b.limit("Revenue band and web traffic are third-party estimates, not reported figures.")

    sig.founders = merge_team(founders_from_record(rec, company_id, today), founders,
                              company_id, today)
    if not sig.founders:
        b.limit("No founders indexed in people.founders.")
    sig.news = news_items(rec, sig.company)
    if sig.news:
        b.limit("News kinds are a title-keyword heuristic; indexed news can include namesakes.")
    tasks = []
    if search:
        tasks.append(_market(b, client, rec, company_id, today))
    else:
        sig.market.categories = [str(c) for c in ((rec.get("taxonomy") or {}).get("categories")
                                                  or []) if c]
    if jobs:
        tasks.append(_jobs(b, client, company_id, today))
    if logo:
        tasks.append(_logo(b, client, company_id))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, BaseException):
            log.warning("signals sub-task failed: %r", r)
            b.limit(f"A signals sub-step failed ({type(r).__name__}); output is partial.")
    sig.coverage["company_search"] = sig.market.crowding != "unknown"
    if sig.market.seo_competitor_domains:
        b.limit("SEO competitor domains are raw keyword overlaps (often namesakes), not a "
                "verified competitor list.")
    sig.credits_used, _ = sum_credits(client.attempts[start:])
    return sig


# ---- fixtures -------------------------------------------------------------------------------

# Bulky keys signals.py never reads, dropped at any depth.
DROP_KEYS = frozenset({
    "employer_linkedin_description", "employee_description", "employer_logo_url",
    "employer_logo_permalink", "summary", "profile_picture_url", "profile_picture_permalink",
    "professional_network", "skills", "crunchbase_profile_url", "uuid", "permalink",
    "employee_location", "employee_position_id", "by_skill_absolute", "by_skill_percent",
    "GEO_REGION", "decision_makers", "cxos", "makers", "reviews", "content", "about", "raw",
    "source_search_pct_timeseries", "source_direct_pct_timeseries",
    "source_social_pct_timeseries", "source_paid_referral_pct_timeseries",
    "source_referral_pct_timeseries", "activities", "categories_detailed",
})
_LAUNCH_KEYS = ("name", "launched_at", "num_upvotes", "tagline", "slug")


def strip_signals(obj: Any, parent: str = "") -> Any:
    if isinstance(obj, dict):
        if parent == "launches":
            return {k: obj.get(k) for k in _LAUNCH_KEYS if k in obj}
        return {k: strip_signals(v, k) for k, v in obj.items() if k not in DROP_KEYS}
    if isinstance(obj, list):
        return [strip_signals(v, parent) for v in obj]
    return obj


def capture_signals(name: str, cache_files: list[Path], *, fixtures_dir: Path | None = None,
                    logo_file: Path | None = None, as_of: date | None = None,
                    overwrite: bool = False) -> list[Path]:
    """Write signals fixtures to `fixtures/<name>/crustdata/`: stripped cache records
    (file names keep the cache key), the logo as `logo.<ext>`, and `signals_meta.json`
    with the capture date. Existing files are kept unless `overwrite`."""
    out_dir = (fixtures_dir or config.FIXTURES_DIR) / name / "crustdata"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for src in cache_files:
        dst = out_dir / src.name
        if dst.exists() and not overwrite:
            log.info("keeping existing fixture %s", dst.name)
            continue
        try:
            rec = json.loads(src.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            log.warning("skipping unreadable cache record %s: %s", src.name, e)
            continue
        fixture = {"endpoint": rec.get("endpoint"), "request": rec.get("request"),
                   "status": rec.get("status", 200), "credits_used": rec.get("credits_used"),
                   "body": strip_signals(rec.get("body"))}
        dst.write_text(json.dumps(fixture, indent=1, ensure_ascii=False), encoding="utf-8")
        written.append(dst)
    if logo_file and logo_file.is_file():
        dst = out_dir / f"logo{logo_file.suffix}"
        if overwrite or not dst.exists():
            dst.write_bytes(logo_file.read_bytes())
            written.append(dst)
    meta = out_dir / "signals_meta.json"
    if as_of and (overwrite or not meta.exists()):
        meta.write_text(json.dumps({"as_of": as_of.isoformat(),
                                    "note": "capture date; FIXTURE replays use it as 'today'"}),
                        encoding="utf-8")
        written.append(meta)
    return written


def cache_files_for(client: Crustdata, start: int = 0) -> list[Path]:
    """Dev-cache files behind the client's successful attempts since `start`."""
    files = []
    for a in client.attempts[start:]:
        if a.error:
            continue
        p = client.cache_dir / f"{_slug(a.endpoint)}-{a.cache_key}.json"
        if p.is_file() and p not in files:
            files.append(p)
    return files


async def record_fixture(name: str, company_id: int, domain: str,
                         today: date | None = None) -> Signals:
    """CACHED run (live on a miss), then capture fixtures for FIXTURE replays."""
    from proofroom.crustdata import CACHED
    today = today or date.today()
    async with Crustdata(CACHED) as client:
        sig = await fetch_signals(client, company_id, domain, today=today)
        files = cache_files_for(client)
    capture_signals(name, files, logo_file=_find_logo(_logo_cache_dir(), str(company_id)),
                    as_of=today)
    return sig


def _summary(sig: Signals) -> str:
    m = sig.metrics
    def d(k: str) -> str:
        return m[k].display if k in m else "n/a"
    lines = [f"{sig.company} ({sig.domain}, id {sig.company_id}) credits={sig.credits_used}",
             f"  headcount {d('headcount_total')} yoy {d('headcount_yoy_pct')} | web "
             f"{d('web_visitors_latest')} qoq {d('web_visitors_qoq_pct')} yoy "
             f"{d('web_visitors_yoy_pct')} | followers yoy {d('followers_yoy_pct')}",
             f"  revenue {d('revenue_band')} trend {d('revenue_trend')} | last round "
             f"{d('last_round')} | months since {d('months_since_last_round')} | cadence "
             f"{d('round_cadence_months')}",
             f"  market '{sig.market.category}' peers={sig.market.peer_count} funded24m="
             f"{sig.market.funded_peers_24m} crowding={sig.market.crowding} median peer yoy="
             f"{sig.market.median_peer_headcount_yoy_pct} peers: "
             + ", ".join(p.name for p in sig.market.peers[:5]),
             "  founders: " + "; ".join(f"{f.name} (prior founder={f.prior_founder}, notable="
                                        f"{f.big_tech_or_scaleup}, {f.years_experience}y)"
                                        for f in sig.founders),
             f"  hiring {d('hiring_openings')} | jobs {d('job_postings_90d')} | logo "
             f"{'yes' if sig.logo_data_uri else 'no'}",
             "  coverage missing: " + ", ".join(k for k, v in sig.coverage.items() if not v)]
    return "\n".join(lines)


if __name__ == "__main__":  # python -m proofroom.signals record <fixture> <id> <domain>
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) == 5 and sys.argv[1] == "record":
        s = asyncio.run(record_fixture(sys.argv[2], int(sys.argv[3]), sys.argv[4]))
        print(_summary(s))
    elif len(sys.argv) == 4 and sys.argv[1] == "fixture":
        async def _replay() -> Signals:
            async with Crustdata(FIXTURE, fixture=sys.argv[2]) as c:
                return await fetch_signals(c, int(sys.argv[3]), "")
        print(_summary(asyncio.run(_replay())))
    else:
        print("usage: python -m proofroom.signals record|fixture <name> <id> [domain]")
