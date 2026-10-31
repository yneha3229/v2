"""Economics model (D26): payroll from where staff are and what they do, switch-premium
salary samples, a revenue estimate (revenue_model.py) and a customer profile.

Every figure here is an ESTIMATE built from Crustdata's indexed profiles and a salary
benchmark table. Rules (judgement calls), documented here and in constants:

Region dedupe (`dedupe_regions`). Crustdata's `headcount.by_region_absolute` lists nested
regions side by side ("San Francisco, CA" inside "San Francisco Bay Area" inside
"California, United States" inside "United States"). The rule:
1. Classify each key as a COUNTRY ("United States"), a METRO (matched to a metro cluster in
   `METROS` by keyword: "San Francisco, CA" and "San Francisco Bay Area" are one cluster) or
   a STATE ("<state>, <country>" that is not a metro, e.g. "New York, United States").
2. Overlapping keys inside one metro cluster are not added: the cluster takes their MAX.
3. Per country: people = the country key if present, else max(sum of its states, sum of its
   metros); never less than the sum of its metro clusters. Country minus its metros goes to
   that country's "rest of country" tier (states only refine nothing further).
4. People not placed in any listed country (Crustdata lists only the top regions) are
   spread over the located countries' REST-OF-COUNTRY tiers in proportion to located
   people: any metro bigger than them would have been listed, so they get no metro premium.
5. Unknown keys with no parseable country are ignored and listed in the method notes.

Role mix: `by_role_absolute` functions map to role families (`ROLE_FAMILY`); people not in
any function are spread pro rata. Role mix is assumed independent of location (Crustdata
gives no joint table), so people(role, loc) = people(loc) x share(role).

Salary: blended base = sum people(role, loc) x benchmark(role, loc) / headcount. Benchmarks
come from `proofroom/data/salary_benchmarks.json` when present, else the BUILT-IN FALLBACK
table below (approximate, uncited, same schema). Loaded cost = payroll x 1.3 (documented
range 1.25-1.4: payroll taxes, benefits, equipment). Runway (upper bound) = primary capital
raised / monthly loaded payroll: it ignores capital already spent and non-payroll costs, and
ignores revenue.

Switch-premium samples (`sample_employees`): Person Search for current employees (small n,
experience returned: 0.23 credits/result). Each sampled person's salary = benchmark(role,
location) x employer-tier multiplier of their most recent PAST employer x switch premium
(1.20-1.25, midpoint used); without a past employer, the role x location benchmark.
The blended average is then adjusted: ratio = sum(sample estimates) / sum(their role x
location benchmarks); adjusted = blended x (1 + w (ratio - 1)), w = n / (n + 30), so 15
samples move the average at most a third of the way toward what they imply.

Customer profile (`infer_customers`): keyword and share rules in code; every inference
lists the evidence it rests on.
"""
from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from proofroom.crustdata import FIXTURE, Crustdata, _slug, cache_key
from proofroom.errors import CrustError
from proofroom.research_models import (CustomerProfile, Economics, EmployeeSample,
                                       PayrollEstimate, SalaryBenchmark, Signals)
from proofroom import revenue_model

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "data"
BENCHMARK_PATH = DATA_DIR / "salary_benchmarks.json"
GROUND_TRUTH_PATH = DATA_DIR / "revenue_ground_truth.json"

OVERHEAD_MULTIPLIER = 1.3
OVERHEAD_RANGE = (1.25, 1.4)
SWITCH_PREMIUM = (1.20, 1.25)
BENCHMARK_UNCERTAINTY = 0.15       # +/- on the blended average
SAMPLE_SHRINK_K = 30               # w = n / (n + K)
SAMPLE_N = 15                      # 15 x 0.23 = 3.45 credits (budget <= 4 per company)
PERSON_SEARCH = "/person/search"

# ---- location tiers -------------------------------------------------------------------

US, GB, IN = "USA", "GBR", "IND"
# metro cluster -> (country ISO3, tier, keyword patterns)
METROS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "San Francisco Bay Area": (US, "San Francisco Bay Area", (
        "san francisco", "bay area", "palo alto", "san jose", "oakland", "mountain view",
        "menlo park", "sunnyvale", "redwood city", "berkeley", "san mateo", "santa clara",
        "cupertino")),
    "New York City": (US, "New York City", ("new york city", "new york, ny", "nyc", "brooklyn",
                                            "manhattan", "jersey city")),
    "Seattle": (US, "Seattle", ("seattle", "bellevue", "redmond")),
    "Boston": (US, "Boston", ("boston", "cambridge, ma", "cambridge, massachusetts")),
    "Los Angeles": (US, "Los Angeles", ("los angeles", "santa monica")),
    "Austin": (US, "US Other", ("austin",)),
    "Denver": (US, "US Other", ("denver", "boulder")),
    "Chicago": (US, "US Other", ("chicago",)),
    "Washington DC": (US, "US Other", ("washington dc", "washington, dc", "washington d.c")),
    "Miami": (US, "US Other", ("miami",)),
    "Atlanta": (US, "US Other", ("atlanta",)),
    "London": (GB, "London", ("london",)),
    "Manchester": (GB, "UK Other", ("manchester",)),
    "Bangalore": (IN, "India", ("bangalore", "bengaluru")),
    "Mumbai": (IN, "India", ("mumbai", "thane", "navi mumbai")),
    "Delhi NCR": (IN, "India", ("delhi", "gurgaon", "gurugram", "noida")),
    "Hyderabad": (IN, "India", ("hyderabad",)),
    "Pune": (IN, "India", ("pune",)),
    "Chennai": (IN, "India", ("chennai",)),
    "Toronto": ("CAN", "Canada", ("toronto",)),
    "Vancouver": ("CAN", "Canada", ("vancouver",)),
    "Montreal": ("CAN", "Canada", ("montreal", "montréal")),
    "Paris": ("FRA", "Western Europe", ("paris", "île-de-france", "ile-de-france")),
    "Berlin": ("DEU", "Western Europe", ("berlin",)),
    "Munich": ("DEU", "Western Europe", ("munich", "münchen")),
    "Amsterdam": ("NLD", "Western Europe", ("amsterdam",)),
    "Dublin": ("IRL", "Western Europe", ("dublin",)),
    "Stockholm": ("SWE", "Western Europe", ("stockholm",)),
    "Zurich": ("CHE", "Western Europe", ("zurich", "zürich")),
    "Madrid": ("ESP", "Southern Europe", ("madrid",)),
    "Barcelona": ("ESP", "Southern Europe", ("barcelona",)),
    "Lisbon": ("PRT", "Southern Europe", ("lisbon", "lisboa")),
    "Warsaw": ("POL", "Eastern Europe", ("warsaw",)),
    "Sao Paulo": ("BRA", "Latin America", ("são paulo", "sao paulo")),
    "Mexico City": ("MEX", "Latin America", ("mexico city", "ciudad de méxico")),
    "Buenos Aires": ("ARG", "Latin America", ("buenos aires",)),
    "Singapore": ("SGP", "Asia Pacific", ("singapore",)),
    "Sydney": ("AUS", "Asia Pacific", ("sydney",)),
    "Melbourne": ("AUS", "Asia Pacific", ("melbourne",)),
    "Tel Aviv": ("ISR", "Israel", ("tel aviv",)),
}
# country ISO3 -> rest-of-country tier
COUNTRY_TIER: dict[str, str] = {
    US: "US Other", GB: "UK Other", IN: "India", "CAN": "Canada", "ISR": "Israel",
    **{c: "Western Europe" for c in ("DEU", "FRA", "NLD", "IRL", "CHE", "SWE", "DNK", "NOR",
                                    "FIN", "BEL", "AUT", "LUX")},
    **{c: "Southern Europe" for c in ("ESP", "PRT", "ITA", "GRC")},
    **{c: "Eastern Europe" for c in ("POL", "UKR", "ROU", "SRB", "CZE", "EST", "TUR")},
    **{c: "Latin America" for c in ("BRA", "MEX", "ARG", "COL", "CHL")},
    **{c: "Asia Pacific" for c in ("SGP", "AUS", "JPN", "NZL")},
}
DEFAULT_TIER = "Rest of World"
LOCATION_TIERS = ("San Francisco Bay Area", "New York City", "Seattle", "Boston", "Los Angeles",
                  "US Other", "London", "UK Other", "Canada", "Western Europe", "Israel",
                  "Southern Europe", "Eastern Europe", "Latin America", "India", "Asia Pacific",
                  DEFAULT_TIER)
_US_STATES = frozenset(s.casefold() for s in (
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut",
    "Delaware", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa",
    "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan",
    "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire",
    "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio",
    "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington", "West Virginia",
    "Wisconsin", "Wyoming", "District of Columbia"))

# ---- role families --------------------------------------------------------------------

ROLE_FAMILIES = ("Engineering", "Product", "Design", "Data & Research", "Sales", "Marketing",
                 "Customer Success & Support", "Operations", "G&A", "Executive")
ROLE_FAMILY: dict[str, str] = {
    "engineering": "Engineering", "information technology": "Engineering",
    "quality assurance": "Engineering", "product management": "Product",
    "arts and design": "Design", "design": "Design", "research": "Data & Research",
    "data science": "Data & Research", "sales": "Sales", "business development": "Sales",
    "marketing": "Marketing", "media and communication": "Marketing",
    "support": "Customer Success & Support", "customer success and support":
    "Customer Success & Support", "customer success": "Customer Success & Support",
    "operations": "Operations", "program and project management": "Operations",
    "purchasing": "Operations", "consulting": "Operations", "real estate": "Operations",
    "administrative": "G&A", "human resources": "G&A", "finance": "G&A", "accounting": "G&A",
    "legal": "G&A", "entrepreneurship": "Executive",
}
# Title keywords for sampled people (first match wins).
TITLE_ROLE: tuple[tuple[str, str], ...] = (
    (r"\b(founder|co-?founder|ceo|cto|coo|cfo|chief|president)\b", "Executive"),
    (r"\b(product manager|product lead|head of product|\bpm\b|product owner)", "Product"),
    (r"\b(designer|design|ux|ui)\b", "Design"),
    (r"\b(data scientist|data analyst|research|scientist|machine learning|ml engineer|analytics)",
     "Data & Research"),
    (r"\b(engineer|developer|engineering|sre|devops|architect|programmer|technical staff)",
     "Engineering"),
    (r"\b(account executive|sales|sdr|bdr|business development|account manager|partnerships)",
     "Sales"),
    (r"\b(marketing|growth|content|brand|communications|community|seo)\b", "Marketing"),
    (r"\b(support|customer success|solutions|implementation|onboarding|customer experience)",
     "Customer Success & Support"),
    (r"\b(recruit|talent|people|hr|finance|accountant|legal|counsel|controller|payroll)",
     "G&A"),
    (r"\b(operations|ops|program manager|project manager|strategy|chief of staff)", "Operations"),
)

# ---- built-in fallback benchmark table ------------------------------------------------
# BUILT-IN FALLBACK (approximate, uncited): median annual BASE salary in USD for a
# mid-level hire at a venture-backed company. Used only when salary_benchmarks.json is
# absent or lacks a (role, location) pair. Engineering anchor by tier x role factor.
_FALLBACK_ENG = {"San Francisco Bay Area": 185_000, "New York City": 175_000, "Seattle": 175_000,
                 "Boston": 160_000, "Los Angeles": 160_000, "US Other": 145_000,
                 "London": 95_000, "UK Other": 75_000, "Canada": 115_000,
                 "Western Europe": 85_000, "Israel": 110_000, "Southern Europe": 60_000,
                 "Eastern Europe": 55_000, "Latin America": 50_000, "India": 30_000,
                 "Asia Pacific": 100_000, DEFAULT_TIER: 45_000}
_FALLBACK_ROLE = {"Engineering": 1.0, "Product": 1.0, "Design": 0.85, "Data & Research": 0.95,
                  "Sales": 0.80, "Marketing": 0.80, "Customer Success & Support": 0.55,
                  "Operations": 0.70, "G&A": 0.70, "Executive": 1.15}
FALLBACK_SOURCE = "BUILT-IN FALLBACK (approximate, uncited; replace with salary_benchmarks.json)"

# Employer tiers for the prior employer (multiplier on the role x location benchmark).
_FALLBACK_TIERS: dict[str, tuple[float, tuple[str, ...]]] = {
    "big_tech": (1.30, ("google", "alphabet", "meta", "facebook", "apple", "microsoft", "amazon",
                        "aws", "netflix", "nvidia", "linkedin", "youtube", "deepmind",
                        "google deepmind", "instagram")),
    "top_scaleup": (1.15, ("stripe", "airbnb", "uber", "coinbase", "databricks", "snowflake",
                           "openai", "anthropic", "figma", "notion", "datadog", "plaid",
                           "ramp", "brex", "rippling", "doordash", "lyft", "pinterest",
                           "dropbox", "shopify", "atlassian", "palantir", "robinhood",
                           "square", "block", "affirm", "twilio", "slack", "github",
                           "vercel", "linear", "retool", "mercury", "scale ai", "canva")),
    "enterprise_finance": (1.05, ("salesforce", "oracle", "ibm", "sap", "adobe", "cisco",
                                  "intel", "accenture", "deloitte", "mckinsey", "bain",
                                  "boston consulting group", "goldman sachs", "jpmorgan",
                                  "jp morgan", "morgan stanley", "citi", "bank of america",
                                  "pwc", "ey", "kpmg")),
}
DEFAULT_TIER_MULT = 1.0


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9&]+", " ", (s or "").casefold()).strip()


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _usd(v: float | None) -> str:
    if v is None:
        return "n/a"
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(v) >= div:
            return f"${v / div:.1f}{suf}"
    return f"${v:,.0f}"


# ---- benchmark table ------------------------------------------------------------------

def fallback_table() -> dict:
    """The built-in table in the salary_benchmarks.json schema."""
    rows = [{"role": r, "location": loc, "annual_usd": round(_FALLBACK_ENG[loc] * f, -3),
             "source": FALLBACK_SOURCE}
            for loc in LOCATION_TIERS for r, f in _FALLBACK_ROLE.items()]
    return {"version": "builtin-fallback-1", "currency": "USD",
            "basis": "median annual base salary, mid-level, venture-backed employers",
            "benchmarks": rows,
            "switch_premium": {"low": SWITCH_PREMIUM[0], "high": SWITCH_PREMIUM[1],
                               "source": FALLBACK_SOURCE},
            "employer_tiers": {k: {"multiplier": m, "employers": list(e)}
                               for k, (m, e) in _FALLBACK_TIERS.items()},
            "overhead_multiplier": {"default": OVERHEAD_MULTIPLIER, "low": OVERHEAD_RANGE[0],
                                    "high": OVERHEAD_RANGE[1]}}


_ROLE_ALIASES = {
    "engineering": "Engineering", "software engineering": "Engineering",
    "software engineer": "Engineering", "engineer": "Engineering", "it": "Engineering",
    "product": "Product", "product management": "Product", "product manager": "Product",
    "design": "Design", "arts and design": "Design", "designer": "Design",
    "data": "Data & Research", "data & research": "Data & Research", "research": "Data & Research",
    "data science": "Data & Research", "data and research": "Data & Research",
    "sales": "Sales", "business development": "Sales", "sales & bd": "Sales",
    "marketing": "Marketing", "support": "Customer Success & Support",
    "customer support": "Customer Success & Support",
    "customer success": "Customer Success & Support",
    "customer success & support": "Customer Success & Support",
    "customer success and support": "Customer Success & Support",
    "operations": "Operations", "ops": "Operations", "g&a": "G&A", "g a": "G&A",
    "general and administrative": "G&A", "general & administrative": "G&A",
    "admin": "G&A", "administrative": "G&A", "hr": "G&A", "people": "G&A",
    "executive": "Executive", "executives": "Executive", "leadership": "Executive",
    "founder": "Executive", "founders": "Executive", "entrepreneurship": "Executive",
}
_LOC_ALIASES = {
    "san francisco bay area": "San Francisco Bay Area", "sf bay area": "San Francisco Bay Area",
    "san francisco": "San Francisco Bay Area", "bay area": "San Francisco Bay Area",
    "new york city": "New York City", "new york": "New York City", "nyc": "New York City",
    "seattle": "Seattle", "boston": "Boston", "los angeles": "Los Angeles",
    "us other": "US Other", "united states other": "US Other", "united states": "US Other",
    "us": "US Other", "usa": "US Other", "rest of us": "US Other", "us average": "US Other",
    "london": "London", "uk other": "UK Other", "united kingdom": "UK Other",
    "rest of uk": "UK Other", "uk": "UK Other", "canada": "Canada",
    "western europe": "Western Europe", "europe": "Western Europe", "israel": "Israel",
    "southern europe": "Southern Europe", "eastern europe": "Eastern Europe",
    "latin america": "Latin America", "latam": "Latin America", "brazil": "Latin America",
    "india": "India", "bangalore": "India", "bengaluru": "India", "india bangalore": "India",
    "asia pacific": "Asia Pacific", "apac": "Asia Pacific", "rest of world": DEFAULT_TIER,
    "row": DEFAULT_TIER, "global": DEFAULT_TIER, "other": DEFAULT_TIER,
}


def _canon(value: str, aliases: dict[str, str], canon: tuple[str, ...]) -> str:
    n = _norm(value)
    for c in canon:
        if _norm(c) == n:
            return c
    if n in aliases:
        return aliases[n]
    for k in sorted(aliases, key=len, reverse=True):
        if re.search(rf"\b{re.escape(k)}\b", n):
            return aliases[k]
    return ""


class Benchmarks:
    """Salary benchmark lookup: the JSON file when present, else the built-in fallback.
    A (role, location) pair missing from the file falls back to the built-in value."""

    def __init__(self, doc: dict, source: str):
        self.source = source
        self.version = str(doc.get("version", "")) if isinstance(doc, dict) else ""
        rows = doc.get("benchmarks", doc.get("rows", [])) if isinstance(doc, dict) else doc
        self.table: dict[tuple[str, str], SalaryBenchmark] = {}
        for r in rows or []:
            if not isinstance(r, dict):
                continue
            role = _canon(str(r.get("role", "")), _ROLE_ALIASES, ROLE_FAMILIES)
            loc = _canon(str(r.get("location", "")), _LOC_ALIASES, LOCATION_TIERS)
            usd = _num(r.get("annual_usd", r.get("median_usd", r.get("base_usd"))))
            if role and loc and usd and (role, loc) not in self.table:
                self.table[(role, loc)] = SalaryBenchmark(
                    role=role, location=loc, annual_usd=usd, source=str(r.get("source", "")))
        self.switch_premium = _pair(doc.get("switch_premium") if isinstance(doc, dict) else None,
                                    SWITCH_PREMIUM)
        self.tiers = _tiers(doc.get("employer_tiers") if isinstance(doc, dict) else None)
        self.missing: set[tuple[str, str]] = set()
        self._fallback: dict[tuple[str, str], SalaryBenchmark] | None = None

    @classmethod
    def load(cls, path: Path | None = None) -> "Benchmarks":
        p = path or BENCHMARK_PATH
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            b = cls(doc, f"file:{p.name}")
            if b.table:
                return b
            log.warning("salary benchmark file %s has no usable rows; using fallback", p.name)
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            log.warning("salary benchmark file unreadable (%s); using fallback", e)
        return cls(fallback_table(), "BUILT-IN FALLBACK")

    @property
    def is_fallback(self) -> bool:
        return self.source == "BUILT-IN FALLBACK"

    def get(self, role: str, location: str) -> SalaryBenchmark:
        role = role if role in ROLE_FAMILIES else "Operations"
        location = location if location in LOCATION_TIERS else DEFAULT_TIER
        hit = self.table.get((role, location))
        if hit:
            return hit
        self.missing.add((role, location))
        if self._fallback is None:
            self._fallback = Benchmarks(fallback_table(), "BUILT-IN FALLBACK").table
        return self._fallback[(role, location)]

    def employer_multiplier(self, employer: str) -> tuple[float, str]:
        n = _norm(employer)
        if not n:
            return DEFAULT_TIER_MULT, "unknown"
        for tier, (mult, names) in self.tiers.items():
            for name in names:
                nn = _norm(name)
                if n == nn or (len(nn) > 4 and n.startswith(nn + " ")):
                    return mult, tier
        return DEFAULT_TIER_MULT, "other"


def _pair(v: Any, default: tuple[float, float]) -> tuple[float, float]:
    if isinstance(v, dict):
        lo, hi = _num(v.get("low", v.get("min"))), _num(v.get("high", v.get("max")))
        if lo and hi:
            return (lo, hi)
        mid = _num(v.get("value", v.get("default")))
        return (mid, mid) if mid else default
    if isinstance(v, (list, tuple)) and len(v) == 2 and all(_num(x) for x in v):
        return (float(v[0]), float(v[1]))
    if _num(v):
        return (float(v), float(v))
    return default


def _tiers(v: Any) -> dict[str, tuple[float, tuple[str, ...]]]:
    out: dict[str, tuple[float, tuple[str, ...]]] = {}
    if isinstance(v, dict):
        for k, t in v.items():
            if isinstance(t, dict) and _num(t.get("multiplier")):
                names = tuple(str(x) for x in t.get("employers") or t.get("companies") or [])
                out[str(k)] = (float(t["multiplier"]), names)
    return out or dict(_FALLBACK_TIERS)


# ---- regions --------------------------------------------------------------------------

def _country_of(name: str) -> str:
    return revenue_model.COUNTRY_ISO3.get(_norm(name), "")


def classify_region(key: str) -> tuple[str, str, str]:
    """(level, country ISO3, cluster): level is country | metro | state | unknown."""
    n = key.strip().casefold()
    iso = _country_of(key)
    if iso:
        return "country", iso, ""
    for cluster, (c_iso, _tier, pats) in METROS.items():
        if any(p in n for p in pats):
            return "metro", c_iso, cluster
    parts = [p.strip() for p in key.split(",")]
    if len(parts) >= 2:
        suffix_iso = _country_of(parts[-1])
        if suffix_iso and len(parts) == 2:
            return "state", suffix_iso, ""
        if suffix_iso:
            return "metro", suffix_iso, ""        # "City, State, Country": an unlisted metro
        if parts[-1].strip().upper() in {"CA", "NY", "WA", "MA", "TX", "IL", "CO"} or \
                parts[-1].strip().casefold() in _US_STATES:
            return "metro", US, ""
    if n in _US_STATES:
        return "state", US, ""
    return "unknown", "", ""


def dedupe_regions(by_region_absolute: dict[str, Any], headcount: float | None
                   ) -> tuple[dict[str, float], list[str]]:
    """People per location tier from nested Crustdata region keys (rule in module doc).
    Returns (tiers, notes); tiers sum to headcount when headcount is known."""
    countries: dict[str, float] = {}
    states: dict[str, float] = Counter()
    clusters: dict[str, float] = {}
    unlisted_metros: dict[str, float] = Counter()
    ignored = []
    for key, raw in (by_region_absolute or {}).items():
        v = _num(raw)
        if not v or v <= 0:
            continue
        level, iso, cluster = classify_region(str(key))
        if level == "country":
            countries[iso] = max(countries.get(iso, 0.0), v)
        elif level == "metro" and cluster:
            clusters[cluster] = max(clusters.get(cluster, 0.0), v)
        elif level == "metro":
            unlisted_metros[iso] += v
        elif level == "state":
            states[iso] += v
        else:
            ignored.append(str(key))
    metro_sum: dict[str, float] = Counter()
    for cl, v in clusters.items():
        metro_sum[METROS[cl][0]] += v
    for iso in set(states) | set(metro_sum) | set(unlisted_metros):
        if iso not in countries:
            countries[iso] = max(states.get(iso, 0.0), metro_sum.get(iso, 0.0)
                                 + unlisted_metros.get(iso, 0.0))
    tiers: dict[str, float] = Counter()
    rest: dict[str, float] = Counter()
    for cl, v in clusters.items():
        tiers[METROS[cl][1]] += v
    for iso, total in countries.items():
        r = max(total - metro_sum.get(iso, 0.0), 0.0)
        rest[COUNTRY_TIER.get(iso, DEFAULT_TIER)] += r
    for t, v in rest.items():
        tiers[t] += v
    located = sum(tiers.values())
    notes = []
    if headcount and headcount > located:
        unplaced = headcount - located
        rest_total = sum(rest.values())
        if rest_total > 0:
            for t, v in rest.items():
                tiers[t] += unplaced * v / rest_total
        elif located > 0:
            for t in list(tiers):
                tiers[t] += unplaced * tiers[t] / located
        else:
            tiers[DEFAULT_TIER] += unplaced
        notes.append(f"{unplaced:.0f} of {headcount:.0f} people are in no listed region; spread "
                     "over the located countries' rest-of-country tiers pro rata.")
    elif headcount and located > headcount:
        scale = headcount / located
        tiers = Counter({t: v * scale for t, v in tiers.items()})
        notes.append(f"Deduped regions sum to {located:.0f} > headcount {headcount:.0f}; scaled "
                     "to headcount.")
    if ignored:
        notes.append("Region keys not placed: " + ", ".join(ignored[:6]))
    out = {t: round(v, 2) for t, v in sorted(tiers.items(), key=lambda kv: -kv[1]) if v > 0}
    return out, notes


def role_people(by_role_absolute: dict[str, Any], headcount: float | None
                ) -> tuple[dict[str, float], list[str]]:
    fam: dict[str, float] = Counter()
    unmapped = []
    for k, raw in (by_role_absolute or {}).items():
        v = _num(raw)
        if not v or v <= 0:
            continue
        f = ROLE_FAMILY.get(str(k).strip().casefold())
        if not f:
            unmapped.append(str(k))
            f = "Operations"
        fam[f] += v
    notes = []
    total = sum(fam.values())
    if headcount and total and headcount != total:
        notes.append(f"{total:.0f} of {headcount:.0f} people have an indexed function; role mix "
                     "scaled to headcount pro rata.")
        fam = Counter({f: v * headcount / total for f, v in fam.items()})
    if unmapped:
        notes.append("Functions mapped to Operations: " + ", ".join(unmapped[:6]))
    return {f: round(v, 2) for f, v in sorted(fam.items(), key=lambda kv: -kv[1])}, notes


# ---- payroll --------------------------------------------------------------------------

def _primary_capital(sig: Signals) -> float | None:
    for k in ("total_funding_primary_usd", "total_funding_usd"):
        m = sig.metrics.get(k)
        if m and m.value:
            return float(m.value)
    return None


def estimate_payroll(signals: Signals, samples: list[EmployeeSample] | None = None, *,
                     regions: dict[str, Any] | None = None, roles: dict[str, Any] | None = None,
                     benchmarks: Benchmarks | None = None) -> PayrollEstimate:
    """Blended salary and loaded payroll. `regions`/`roles` are the raw
    by_region_absolute / by_role_absolute maps; without them the Signals mixes (percent of
    headcount; regions top-10 only) are used."""
    bm = benchmarks or Benchmarks.load()
    hc = signals.headcount_total
    p = PayrollEstimate(headcount=hc, overhead_multiplier=OVERHEAD_MULTIPLIER,
                        switch_premium=bm.switch_premium, samples=list(samples or []))
    p.method.append("ESTIMATE from indexed profiles x salary benchmarks; not reported payroll.")
    p.method.append(f"Benchmarks: {bm.source}" + (f" ({bm.version})" if bm.version else "")
                    + (" — approximate built-in table, not cited." if bm.is_fallback else "."))
    if not hc:
        p.method.append("No headcount indexed: payroll not estimated.")
        return p
    if regions is None:
        regions = {k: v * hc / 100 for k, v in (signals.region_mix or {}).items()}
        p.method.append("Regions from the Signals mix (top 10 keys, percent of headcount).")
    if roles is None:
        roles = {k: v * hc / 100 for k, v in (signals.role_mix or {}).items()}
    p.by_location, notes = dedupe_regions(regions, hc)
    p.method += notes
    if not p.by_location:
        p.by_location = {DEFAULT_TIER: hc}
        p.method.append("No region data: all staff priced at the Rest of World tier.")
    p.by_role, notes = role_people(roles, hc)
    p.method += notes
    if not p.by_role:
        p.by_role = {"Engineering": hc * 0.4, "Sales": hc * 0.2, "Operations": hc * 0.4}
        p.method.append("No role data: assumed 40% Engineering, 20% Sales, 40% Operations.")
    role_total = sum(p.by_role.values())
    loc_total = sum(p.by_location.values())
    payroll = 0.0
    for loc, n_loc in p.by_location.items():
        for role, n_role in p.by_role.items():
            payroll += n_loc * (n_role / role_total) * bm.get(role, loc).annual_usd
    payroll *= hc / loc_total
    blended = payroll / hc
    p.method.append(f"Blended base {_usd(blended)} = sum people(role, location) x benchmark / "
                    "headcount; role mix assumed independent of location.")
    adjusted = blended
    est = [s for s in p.samples if s.est_salary_usd and s.role and s.location]
    if est:
        bench_sum = sum(bm.get(s.role, s.location).annual_usd for s in est)
        ratio = sum(s.est_salary_usd for s in est) / bench_sum if bench_sum else 1.0
        w = len(est) / (len(est) + SAMPLE_SHRINK_K)
        adjusted = blended * (1 + w * (ratio - 1))
        n_sw = sum(1 for s in est if s.method == "switch-premium")
        p.method.append(f"Switch-premium samples: {len(est)} people ({n_sw} priced from a prior "
                        f"employer x {bm.switch_premium[0]:.2f}-{bm.switch_premium[1]:.2f}); they "
                        f"imply {ratio:.2f}x benchmark; blended moved by weight "
                        f"{w:.2f} -> {_usd(adjusted)}.")
    p.avg_salary_usd = round(adjusted, 0)
    lo = min(blended, adjusted) * (1 - BENCHMARK_UNCERTAINTY)
    hi = max(blended, adjusted) * (1 + BENCHMARK_UNCERTAINTY)
    p.avg_salary_range_usd = (round(lo, 0), round(hi, 0))
    p.annual_payroll_usd = round(adjusted * hc, 0)
    p.loaded_cost_usd = round(p.annual_payroll_usd * OVERHEAD_MULTIPLIER, 0)
    p.method.append(f"Loaded cost = base payroll x {OVERHEAD_MULTIPLIER} (range "
                    f"{OVERHEAD_RANGE[0]}-{OVERHEAD_RANGE[1]}: taxes, benefits, equipment); "
                    f"salary range = +/-{BENCHMARK_UNCERTAINTY:.0%} benchmark uncertainty.")
    cap = _primary_capital(signals)
    if cap and p.loaded_cost_usd:
        p.est_runway_months = round(cap / (p.loaded_cost_usd / 12), 1)
        p.method.append(f"Runway upper bound {p.est_runway_months:.0f} months = primary capital "
                        f"{_usd(cap)} (indexed record, Crunchbase-derived) / monthly loaded "
                        "payroll; ignores capital already spent, non-payroll costs and revenue.")
    if bm.missing:
        p.method.append(f"{len(bm.missing)} (role, location) pairs not in the benchmark file "
                        "used the built-in fallback.")
    return p


# ---- switch-premium samples -----------------------------------------------------------

def role_from_title(title: str) -> str:
    t = (title or "").casefold()
    for pat, role in TITLE_ROLE:
        if re.search(pat, t):
            return role
    return "Operations" if t else ""


def location_tier(loc: Any) -> str:
    """Tier for a person's location (string or {city,state,country,full_location})."""
    if isinstance(loc, dict):
        text = ", ".join(str(loc.get(k) or "") for k in ("full_location", "city", "state",
                                                         "country") if loc.get(k))
        country = str(loc.get("country") or "")
    else:
        text, country = str(loc or ""), ""
    n = text.casefold()
    for cluster, (_iso, tier, pats) in METROS.items():
        if any(p in n for p in pats):
            return tier
    iso = _country_of(country)
    if not iso:
        for part in reversed([x.strip() for x in text.split(",") if x.strip()]):
            iso = _country_of(part)
            if iso:
                break
            if part.casefold() in _US_STATES:
                iso = US
                break
    if not iso:
        return ""
    return COUNTRY_TIER.get(iso, DEFAULT_TIER)


def sample_body(company_id: int, n: int = SAMPLE_N) -> dict:
    return {"filters": {"op": "and", "conditions": [
        {"field": "experience.employment_details.current.company_id", "type": "=",
         "value": int(company_id)}]},
        "fields": ["crustdata_person_id", "basic_profile",
                   "experience.employment_details.current",
                   "experience.employment_details.past"],
        "limit": int(n)}


def _most_recent_past(past: list[dict], company_id: int) -> dict | None:
    def key(e: dict) -> str:
        return str(e.get("end_date") or e.get("start_date") or "")
    items = [e for e in past or [] if isinstance(e, dict) and e.get("name")
             and e.get("crustdata_company_id") != company_id]
    return max(items, key=key) if items else None


def sample_from_profile(person: dict, company_id: int, bm: Benchmarks) -> EmployeeSample:
    bp = person.get("basic_profile") or {}
    emp = ((person.get("experience") or {}).get("employment_details")) or {}
    current = [e for e in emp.get("current") or [] if isinstance(e, dict)]
    here = next((e for e in current if e.get("crustdata_company_id") == company_id), None)
    title = str((here or {}).get("title") or bp.get("current_title") or "")
    role = role_from_title(title) or "Operations"
    loc = location_tier(bp.get("location")) or ""
    s = EmployeeSample(title=title, role=role, location=loc)
    bench = bm.get(role, loc or DEFAULT_TIER).annual_usd
    prior = _most_recent_past(emp.get("past") or [], company_id)
    if prior:
        mult, _tier = bm.employer_multiplier(str(prior.get("name")))
        s.prior_employer = str(prior.get("name"))
        s.prior_salary_usd = round(bench * mult, 0)
        s.est_salary_usd = round(s.prior_salary_usd * sum(bm.switch_premium) / 2, 0)
        s.method = "switch-premium"
    else:
        s.est_salary_usd = round(bench, 0)
        s.method = "role-location benchmark"
    if not loc:
        s.location = DEFAULT_TIER
    return s


async def sample_employees(client: Crustdata, company_id: int, n: int = SAMPLE_N, *,
                           benchmarks: Benchmarks | None = None) -> list[EmployeeSample]:
    """Person Search for current employees (0.23 credits/result with experience)."""
    bm = benchmarks or Benchmarks.load()
    resp = await client.request("POST", PERSON_SEARCH, sample_body(company_id, n))
    profiles = resp.get("profiles") if isinstance(resp, dict) else resp
    return [sample_from_profile(p, int(company_id), bm)
            for p in profiles or [] if isinstance(p, dict)]


# ---- customers ------------------------------------------------------------------------

_CUSTOMER_RULES: tuple[tuple[str, str], ...] = (
    (r"\bstartups?\b|founders|venture-backed", "Startups and venture-backed companies"),
    (r"developers?|engineering teams|engineers\b|frontend|\bAPIs?\b|\bSDK", "Software developers and engineering teams"),
    (r"product teams|product development|software teams|issue track", "Product and software teams"),
    (r"sales teams|go-to-market|\bGTM\b|revenue teams|sales reps|outbound|prospect", "Sales and go-to-market teams"),
    (r"finance teams|\bCFOs?\b|controllers|accounts payable|expense|spend management|bookkeep", "Finance teams (CFOs, controllers)"),
    (r"enterprises?\b|fortune 500|large companies", "Enterprises"),
    (r"small business|\bSMBs?\b|small and medium|small to medium", "Small and medium businesses"),
    (r"advertis|\bbrands\b|monetiz|publishers", "Advertisers, brands and publishers"),
    (r"\bAI (apps|applications|assistants|chatbots)|LLM apps|chatbots?|conversational AI", "AI application builders"),
    (r"marketers|marketing teams", "Marketing teams"),
    (r"merchants|e-?commerce|online stores|retailers", "Online merchants and retailers"),
    (r"\bconsumers?\b|individuals|households", "Consumers"),
)
_USE_CASE_RULES: tuple[tuple[str, str], ...] = (
    (r"issue track|project management|roadmap|sprint", "Issue tracking and project management"),
    (r"\bCRM\b|customer relationship|relationship management", "CRM / customer relationship management"),
    (r"deploy|hosting|frontend cloud|serverless|preview", "Web app hosting and deployment"),
    (r"internal tools|admin panels|dashboards for", "Building internal tools"),
    (r"corporate cards?|expense|spend management|bill pay", "Corporate cards and spend management"),
    (r"\bbanking\b|bank accounts?|treasury", "Business banking and treasury"),
    (r"enrich|prospect|lead (data|list)|outbound", "Prospect data enrichment and outbound"),
    (r"advertis|\bads\b|sponsored|monetiz", "Advertising and monetization"),
    (r"payments?|payouts|invoic", "Payments and invoicing"),
    (r"accounting|bookkeep|close the books", "Accounting automation"),
    (r"workflow|automat", "Workflow automation"),
    (r"analytics|reporting|insights", "Analytics and reporting"),
    (r"collaborat|knowledge|documentation|docs\b", "Team collaboration and documentation"),
)
_B2B_CATEGORIES = re.compile(r"crm|developer|saas|enterprise|b2b|sales|marketing automation|"
                             r"productivity|project management|lead|fintech|payments|"
                             r"advertising platforms|cloud|devops|infrastructure", re.I)
_B2C_CATEGORIES = re.compile(r"consumer|e-commerce|gaming|social|dating|fitness|personal "
                             r"finance|music|video streaming", re.I)
_MARKETPLACE = re.compile(r"marketplace|connects (buyers|sellers|.* with)|two-sided", re.I)
_EMBEDDED = re.compile(r"embedded|white-label|banking-as-a-service|\bBaaS\b|for platforms", re.I)
_SECTOR_EMPLOYERS: dict[str, tuple[str, ...]] = {
    "fintech / financial services": ("stripe", "brex", "plaid", "square", "block", "affirm",
                                     "chime", "robinhood", "coinbase", "jpmorgan", "goldman",
                                     "capital one", "american express", "visa", "mastercard",
                                     "paypal", "bank", "capital", "financial", "ramp",
                                     "mercury", "wise", "revolut", "monzo"),
    "developer tools / cloud": ("github", "atlassian", "gitlab", "heroku", "datadog",
                                "hashicorp", "vercel", "aws", "amazon web services",
                                "cloudflare", "netlify", "twilio", "mongodb", "docker"),
    "sales / marketing software": ("salesforce", "hubspot", "zoominfo", "outreach", "gong",
                                   "marketo", "apollo", "linkedin", "intercom"),
    "advertising / media": ("google", "meta", "facebook", "the trade desk", "criteo",
                            "taboola", "outbrain", "pinterest", "snap", "tiktok"),
}


def _hits(rules: tuple[tuple[str, str], ...], text: str) -> list[tuple[str, str]]:
    out = []
    for pat, label in rules:
        m = re.search(pat, text, re.I)
        if m and label not in [x[0] for x in out]:
            out.append((label, m.group(0)))
    return out


def infer_customers(signals: Signals, samples: list[EmployeeSample] | None = None
                    ) -> CustomerProfile:
    """Business model, target customers, use cases and talent sources, each with evidence."""
    cp = CustomerProfile()
    samples = samples or []
    desc = signals.description or ""
    cats = list(signals.market.categories or [])
    text = desc + " " + " ".join(cats)
    b2b, b2c = 0.0, 0.0
    b2b_cats = [c for c in cats if _B2B_CATEGORIES.search(c)]
    b2c_cats = [c for c in cats if _B2C_CATEGORIES.search(c)]
    if b2b_cats:
        b2b += 1.0
        cp.evidence.append("B2B: taxonomy categories " + ", ".join(b2b_cats[:4]))
    if b2c_cats:
        b2c += 1.0
        cp.evidence.append("B2C: taxonomy categories " + ", ".join(b2c_cats[:4]))
    fl = revenue_model.category_flags(desc)
    if fl.get("cat_b2b"):
        b2b += 1.0
        m = revenue_model.CATEGORY_PATTERNS["cat_b2b"].search(desc)
        cp.evidence.append(f"B2B: description mentions '{m.group(0) if m else 'business'}'")
    if fl.get("cat_consumer"):
        b2c += 1.0
        m = revenue_model.CATEGORY_PATTERNS["cat_consumer"].search(desc)
        cp.evidence.append(f"B2C: description mentions '{m.group(0) if m else 'consumer'}'")
    naics = signals.market.naics
    if naics.startswith(("5112", "5132", "5415", "5182", "5416")):
        b2b += 0.5
        cp.evidence.append(f"B2B: NAICS {naics} (software / IT services)")
    elif naics.startswith(("44", "45", "7225", "7139")):
        b2c += 0.5
        cp.evidence.append(f"B2C: NAICS {naics} (retail / consumer services)")
    sales_pct = sum(v for k, v in (signals.role_mix or {}).items()
                    if k in ("Sales", "Business Development"))
    ae = [s.title for s in samples if re.search(r"account executive|\bsdr\b|\bbdr\b|"
                                                r"account manager|sales", s.title or "", re.I)]
    if sales_pct >= 10 or len(ae) >= 2:
        b2b += 1.0
        cp.evidence.append(f"Sales-led B2B motion: Sales + Business Development = "
                           f"{sales_pct:.1f}% of staff" + (f"; {len(ae)} sampled sales titles "
                                                           f"({', '.join(ae[:3])})" if ae else ""))
    if _MARKETPLACE.search(desc):
        cp.business_model = "marketplace"
        cp.evidence.append("Marketplace: description describes a two-sided market")
    elif b2b == 0 and b2c == 0:
        cp.business_model = "unknown"
    elif b2b > 0 and b2c > 0 and (abs(b2b - b2c) <= 0.5 or _EMBEDDED.search(desc)):
        cp.business_model = "B2B2C"
    else:
        cp.business_model = "B2B" if b2b >= b2c else "B2C"
    if _EMBEDDED.search(desc) and cp.business_model == "B2B":
        cp.evidence.append("Embedded / platform language: sells through other businesses")
    cp.evidence.append(f"Business model scores: B2B {b2b:.1f}, B2C {b2c:.1f}")
    for label, hit in _hits(_CUSTOMER_RULES, text):
        cp.target_customers.append(label)
        cp.evidence.append(f"Customer '{label}': text '{hit}'")
    for label, hit in _hits(_USE_CASE_RULES, text):
        cp.use_cases.append(label)
        cp.evidence.append(f"Use case '{label}': text '{hit}'")
    specific = [c for c in cats if c.casefold() not in {
        "software", "information technology", "artificial intelligence (ai)", "computer",
        "internet", "saas", "finance", "financial services"}]
    if specific and len(cp.use_cases) < 2:
        cp.use_cases += [f"{c} (taxonomy category)" for c in specific[:3]]
        cp.evidence.append("Use cases from taxonomy: " + ", ".join(specific[:3]))
    priors = Counter(s.prior_employer for s in samples if s.prior_employer)
    cp.talent_sources = [f"{n} ({c})" if c > 1 else n for n, c in priors.most_common(6)]
    if priors:
        cp.evidence.append(f"Talent sources: prior employers of {sum(priors.values())} sampled staff")
        sectors: Counter = Counter()
        for name, c in priors.items():
            nn = _norm(name)
            for sector, keys in _SECTOR_EMPLOYERS.items():
                if any(re.search(rf"\b{re.escape(k)}\b", nn) for k in keys):
                    sectors[sector] += c
                    break
        for sector, c in sectors.most_common(2):
            if c >= 3 or (c >= 2 and c / max(len(samples), 1) >= 0.25):
                cp.evidence.append(f"{c} sampled staff came from {sector} employers: domain "
                                   f"expertise suggests {sector} customers or integrations")
                hint = {"fintech / financial services": "Finance teams (CFOs, controllers)",
                        "developer tools / cloud": "Software developers and engineering teams",
                        "sales / marketing software": "Sales and go-to-market teams",
                        "advertising / media": "Advertisers, brands and publishers"}[sector]
                if hint not in cp.target_customers:
                    cp.target_customers.append(f"{hint} (from talent sources)")
    if not cp.target_customers:
        cp.evidence.append("No customer keyword matched; target customers unknown")
    return cp


# ---- orchestration --------------------------------------------------------------------

def _enrich_record(client: Crustdata, company_id: int) -> dict | None:
    """The full Company Enrich record signals.py fetched, read from the fixture or dev
    cache WITHOUT a new request (0 credits). None when not on disk."""
    from proofroom.graph import company_record
    from proofroom.signals import ENRICH_FIELDS
    endpoint = "/company/enrich"
    body = {"crustdata_company_ids": [int(company_id)], "fields": list(ENRICH_FIELDS)}
    name = f"{_slug(endpoint)}-{cache_key(endpoint, body)}.json"
    folder = client.fixture_dir if client.mode == FIXTURE else client.cache_dir
    rec = client._read_record(folder / name)
    return company_record(rec["body"]) if rec else None


def _today(client: Crustdata) -> date:
    from proofroom.signals import _fixture_as_of
    return _fixture_as_of(client) or date.today()


async def build_economics(client: Crustdata, signals: Signals, company_id: int, *,
                          n_samples: int = SAMPLE_N) -> Economics:
    """Payroll (with switch-premium samples), revenue estimate and customer profile."""
    eco = Economics()
    bm = Benchmarks.load()
    if bm.is_fallback:
        eco.limitations.append("Salary benchmarks: BUILT-IN FALLBACK table (approximate, "
                               "uncited); salary_benchmarks.json not found.")
    rec = _enrich_record(client, company_id) or {}
    hc = rec.get("headcount") or {}
    regions = hc.get("by_region_absolute") or None
    roles = hc.get("by_role_absolute") or None
    listed_bucket = str((rec.get("basic_info") or {}).get("employee_count_range") or "")
    largest = str(hc.get("largest_headcount_country") or "")
    if not rec:
        eco.limitations.append("Full Company Enrich record not on disk: regions limited to the "
                               "top-10 Signals mix.")
    samples: list[EmployeeSample] = []
    if n_samples > 0:
        try:
            samples = await sample_employees(client, company_id, n_samples, benchmarks=bm)
        except CrustError as e:
            eco.limitations.append(f"Employee sample (Person Search) failed ({e.type}): "
                                   "payroll uses benchmarks only.")
    eco.payroll = estimate_payroll(signals, samples, regions=regions, roles=roles, benchmarks=bm)
    eco.revenue = revenue_model.estimate_revenue(
        signals, eco.payroll, as_of=_today(client), largest_country=largest,
        listed_bucket=listed_bucket)
    eco.customers = infer_customers(signals, samples)
    eco.limitations.append("Payroll, revenue and customer profile are model estimates from "
                           "indexed data, not company-reported figures.")
    if samples:
        eco.limitations.append(f"{len(samples)} sampled employees are not a random sample "
                               "(Person Search default order).")
    return eco


def load_ground_truth(path: Path | None = None) -> dict[str, dict]:
    """revenue_ground_truth.json keyed by domain (accepts a list or a dict)."""
    try:
        doc = json.loads((path or GROUND_TRUTH_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    items = doc.get("companies", doc) if isinstance(doc, dict) else doc
    out: dict[str, dict] = {}
    if isinstance(items, dict):
        for k, v in items.items():
            if isinstance(v, dict):
                out[str(v.get("domain") or k).casefold()] = v
    elif isinstance(items, list):
        for v in items:
            if isinstance(v, dict) and (v.get("domain") or v.get("company")):
                out[str(v.get("domain") or v.get("company")).casefold()] = v
    return out
