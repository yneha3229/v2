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
location) x employer-tier multiplier of their most recent PAST employer x a LOCATION-SPECIFIC
switch premium from salary_benchmarks.json (midpoint used): US x1.048-1.073 (ADP job-changer
base/gross raise), Canada x1.056 (ADP Canada), India x1.21-1.30 (survey EXPECTATION); other
markets have no figure in the file and use the US one, which each sample's `method` states.
The 1.20-1.25 hypothesis is kept only as the built-in fallback. Without a past employer, the
role x location benchmark.
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
    "Bangalore": (IN, "Bangalore", ("bangalore", "bengaluru")),
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
    "Portland": (US, "US Other", ("portland",)),
    "Brighton": (GB, "UK Other", ("brighton",)),
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
                  "Southern Europe", "Eastern Europe", "Latin America", "Bangalore", "India",
                  "Asia Pacific", DEFAULT_TIER)
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
# Families follow Crustdata's function names (and salary_benchmarks.json roles).

ROLE_FAMILIES = ("Engineering", "Product", "Design", "Data & Research", "Sales",
                 "Business Development", "Marketing", "Customer Success & Support",
                 "Operations", "Finance", "Human Resources", "Legal", "Administrative",
                 "Executive")
ROLE_FAMILY: dict[str, str] = {
    "engineering": "Engineering", "information technology": "Engineering",
    "quality assurance": "Engineering", "product management": "Product",
    "arts and design": "Design", "design": "Design", "research": "Data & Research",
    "data science": "Data & Research", "sales": "Sales",
    "business development": "Business Development",
    "marketing": "Marketing", "media and communication": "Marketing",
    "support": "Customer Success & Support", "customer success and support":
    "Customer Success & Support", "customer success": "Customer Success & Support",
    "operations": "Operations", "program and project management": "Operations",
    "purchasing": "Operations", "consulting": "Operations", "real estate": "Operations",
    "administrative": "Administrative", "human resources": "Human Resources",
    "finance": "Finance", "accounting": "Finance", "legal": "Legal",
    "entrepreneurship": "Executive",
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
    (r"\b(business development|partnerships|\bbd\b|alliances)", "Business Development"),
    (r"\b(account executive|sales|sdr|bdr|account manager|gtm|go-to-market)", "Sales"),
    (r"\b(marketing|growth|content|brand|communications|community|seo)\b", "Marketing"),
    (r"\b(support|customer success|solutions|implementation|onboarding|customer experience)",
     "Customer Success & Support"),
    (r"\b(recruit|talent|people|hr)\b", "Human Resources"),
    (r"\b(finance|accountant|accounting|controller|payroll|fp&a|treasury)", "Finance"),
    (r"\b(legal|counsel|attorney|lawyer|compliance)", "Legal"),
    (r"\b(assistant|administrative|office manager|receptionist)", "Administrative"),
    (r"\b(operations|ops|program manager|project manager|strategy|chief of staff)", "Operations"),
)

# ---- built-in fallback benchmark table ------------------------------------------------
# BUILT-IN FALLBACK (approximate, uncited): median annual BASE salary in USD. Used when
# salary_benchmarks.json is absent, and for (role, tier) cells the file cannot fill
# (Israel, Southern/Eastern Europe, Latin America, Rest of World). Engineering anchor by
# tier x role factor.
_FALLBACK_ENG = {"San Francisco Bay Area": 185_000, "New York City": 175_000, "Seattle": 175_000,
                 "Boston": 160_000, "Los Angeles": 160_000, "US Other": 145_000,
                 "London": 95_000, "UK Other": 75_000, "Canada": 115_000,
                 "Western Europe": 85_000, "Israel": 110_000, "Southern Europe": 60_000,
                 "Eastern Europe": 55_000, "Latin America": 50_000, "Bangalore": 32_000,
                 "India": 25_000, "Asia Pacific": 100_000, DEFAULT_TIER: 45_000}
_FALLBACK_ROLE = {"Engineering": 1.0, "Product": 1.0, "Design": 0.85, "Data & Research": 0.95,
                  "Sales": 0.80, "Business Development": 0.75, "Marketing": 0.80,
                  "Customer Success & Support": 0.55, "Operations": 0.70, "Finance": 0.75,
                  "Human Resources": 0.65, "Legal": 1.0, "Administrative": 0.45,
                  "Executive": 1.15}
FALLBACK_SOURCE = "BUILT-IN FALLBACK (approximate, uncited)"

# Employer tiers for the prior employer: name lists here; multipliers from the file's
# employer_tiers when present (big_tech, scaleup, fintech_incumbent, services/IT), else
# these fallbacks. India uses the file's india_multiplier when given.
_TIER_EMPLOYERS: dict[str, tuple[str, ...]] = {
    "big_tech": ("google", "alphabet", "meta", "facebook", "apple", "microsoft", "amazon",
                 "aws", "amazon web services", "netflix", "nvidia", "linkedin", "youtube",
                 "deepmind", "google deepmind", "instagram"),
    "scaleup": ("stripe", "airbnb", "uber", "coinbase", "databricks", "snowflake", "openai",
                "anthropic", "figma", "notion", "datadog", "plaid", "ramp", "brex", "rippling",
                "doordash", "lyft", "pinterest", "dropbox", "shopify", "atlassian", "palantir",
                "robinhood", "square", "block", "affirm", "twilio", "slack", "github", "vercel",
                "linear", "retool", "mercury", "scale ai", "canva", "airtable", "hashicorp",
                "salesforce", "adobe", "oracle", "sap", "servicenow", "workday", "intuit"),
    "fintech_incumbent": ("jpmorgan", "jp morgan", "jpmorgan chase", "goldman sachs", "hsbc",
                          "visa", "mastercard", "citi", "citibank", "bank of america",
                          "morgan stanley", "capital one", "american express", "barclays",
                          "wells fargo"),
    "services/IT": ("tcs", "tata consultancy services", "infosys", "wipro", "cognizant", "hcl",
                    "hcltech", "accenture", "capgemini", "tech mahindra", "deloitte", "pwc",
                    "ey", "kpmg", "ibm"),
}
_FALLBACK_TIER_MULT = {"big_tech": 1.30, "scaleup": 1.15, "fintech_incumbent": 1.05,
                       "services/IT": 0.95}
DEFAULT_TIER_MULT = 1.0
# Switch premium: the file stores the realised raise for job changers as a FRACTION
# (0.048-0.073 US); a value below 1 is read as 1 + fraction. India uses the file's
# expected-hike range (21-30%, a survey EXPECTATION, flagged).
INDIA_TIERS = frozenset({"Bangalore", "India"})

# Our tier -> the file's location label (proxy noted where not exact).
FILE_LOCATION = {
    "San Francisco Bay Area": "San Francisco Bay Area", "New York City": "New York",
    "Seattle": "Seattle", "Boston": "Los Angeles", "Los Angeles": "Los Angeles",
    "US Other": "Other US", "London": "London",
    "UK Other": "Other UK/EU (Berlin/Paris/Amsterdam)",
    "Western Europe": "Other UK/EU (Berlin/Paris/Amsterdam)", "Canada": "Toronto/Canada",
    "Bangalore": "Bangalore/India", "India": "Other India", "Asia Pacific": "Singapore",
}
FILE_ROLE = {"Engineering": "Engineering", "Product": "Product Management",
             "Design": "Arts and Design", "Data & Research": "Data Science", "Sales": "Sales",
             "Business Development": "Business Development", "Marketing": "Marketing",
             "Customer Success & Support": "Support", "Operations": "Operations",
             "Finance": "Finance", "Human Resources": "Human Resources", "Legal": "Legal",
             "Administrative": "Other", "Executive": "Entrepreneurship"}
_TECH_ROLES = frozenset({"Engineering", "Product", "Data & Research", "Design"})
_US_TIERS = frozenset({"San Francisco Bay Area", "New York City", "Seattle", "Boston",
                       "Los Angeles", "US Other"})


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
    """The built-in table in the salary_benchmarks.json schema (file labels)."""
    inv = {}
    for tier, label in FILE_LOCATION.items():
        inv.setdefault(label, tier)
    rows = []
    for tier in LOCATION_TIERS:
        label = FILE_LOCATION.get(tier, tier)
        if inv.get(label, tier) != tier:
            continue
        for fam, f in _FALLBACK_ROLE.items():
            rows.append({"role": FILE_ROLE[fam], "location": label,
                         "annual_usd": round(_FALLBACK_ENG[tier] * f, -3),
                         "source": FALLBACK_SOURCE})
    return {"as_of": "builtin", "version": "builtin-fallback-2", "benchmarks": rows,
            "switch_premium": {"low": SWITCH_PREMIUM[0] - 1, "high": SWITCH_PREMIUM[1] - 1,
                               "source": FALLBACK_SOURCE},
            "employer_tiers": [{"tier": t, "multiplier_vs_market": m}
                               for t, m in _FALLBACK_TIER_MULT.items()]}


def _premium(lo: Any, hi: Any) -> tuple[float, float] | None:
    a, b = _num(lo), _num(hi)
    if a is None or b is None:
        return None
    return (1 + a if a < 1 else a, 1 + b if b < 1 else b)


class Benchmarks:
    """Salary lookup over (role family, location tier). Cells come from the file when it
    has them; otherwise the file's fill rule (SF cell x location index; the BLS
    all-occupation index for non-tech roles in US tiers); otherwise the built-in fallback.
    Every SalaryBenchmark carries its source."""

    def __init__(self, doc: dict, source: str):
        self.source = source
        self.version = str(doc.get("version") or doc.get("as_of") or "")
        self.cells: dict[tuple[str, str], tuple[float, str]] = {}
        for r in doc.get("benchmarks") or []:
            if isinstance(r, dict) and _num(r.get("annual_usd")):
                self.cells[(_norm(str(r.get("role"))), _norm(str(r.get("location"))))] = (
                    float(r["annual_usd"]), str(r.get("source") or ""))
        self.loc_index = {_norm(str(x.get("location"))): _num(x.get("multiplier_vs_sf"))
                          for x in doc.get("location_index") or [] if isinstance(x, dict)}
        occ = (doc.get("us_all_occupations_index_vs_sf") or {}).get("values") or {}
        self.occ_index = {_norm(k): _num(v) for k, v in occ.items()}
        sp = doc.get("switch_premium") or {}
        self.switch_premium = _premium(sp.get("low"), sp.get("high")) or SWITCH_PREMIUM
        self.switch_source = str(sp.get("source") or "")
        # market -> (low, high, source); US = the file's top-level low/high (ADP base/gross).
        self.premium_by_market: dict[str, tuple[float, float, str]] = {
            "US": (*self.switch_premium, self.switch_source or source)}
        for m in sp.get("by_market") or []:
            if not isinstance(m, dict):
                continue
            mk, src = str(m.get("market") or ""), str(m.get("source") or "")
            if mk == "India":
                pr = _premium(m.get("job_changer_raise_expected_low"),
                              m.get("job_changer_raise_expected_high"))
                if pr:
                    self.premium_by_market["India"] = (*pr, src + " (survey EXPECTATION)")
            elif mk and mk != "US" and mk not in self.premium_by_market:
                r = _num(m.get("job_changer_raise"))
                if r is not None:
                    self.premium_by_market[mk] = (1 + r, 1 + r, src)
        self.tier_mult: dict[str, tuple[float, float]] = {}
        tiers = doc.get("employer_tiers") or []
        for t in tiers if isinstance(tiers, list) else []:
            m = _num(t.get("multiplier_vs_market")) if isinstance(t, dict) else None
            if m:
                self.tier_mult[str(t.get("tier"))] = (m, _num(t.get("india_multiplier")) or m)
        for k, m in _FALLBACK_TIER_MULT.items():
            self.tier_mult.setdefault(k, (m, m))
        self.sourced: Counter = Counter()
        self._cache: dict[tuple[str, str], SalaryBenchmark] = {}

    @classmethod
    def load(cls, path: Path | None = None) -> "Benchmarks":
        p = path or BENCHMARK_PATH
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(doc, dict) and doc.get("benchmarks"):
                return cls(doc, f"file:{p.name}")
            log.warning("salary benchmark file %s has no benchmarks; using fallback", p.name)
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            log.warning("salary benchmark file unreadable (%s); using fallback", e)
        return cls(fallback_table(), "BUILT-IN FALLBACK")

    @property
    def is_fallback(self) -> bool:
        return self.source == "BUILT-IN FALLBACK"

    def _cell(self, role: str, label: str) -> tuple[float, str] | None:
        return self.cells.get((_norm(FILE_ROLE[role]), _norm(label)))

    def get(self, role: str, location: str) -> SalaryBenchmark:
        role = role if role in ROLE_FAMILIES else "Operations"
        location = location if location in LOCATION_TIERS else DEFAULT_TIER
        key = (role, location)
        if key in self._cache:
            return self._cache[key]
        label = FILE_LOCATION.get(location, "")
        value, src, how = None, "", ""
        if label:
            hit = self._cell(role, label)
            if hit:
                value, src, how = hit[0], hit[1], "file cell"
            else:
                sf = self._cell(role, "San Francisco Bay Area")
                idx = None
                if location in _US_TIERS and role not in _TECH_ROLES:
                    idx = self.occ_index.get(_norm(label))
                idx = idx or self.loc_index.get(_norm(label))
                if sf and idx:
                    value, src = sf[0] * idx, f"{sf[1]} x location index {idx:.3f}"
                    how = "file fill rule"
        if value is None:
            value = round(_FALLBACK_ENG[location] * _FALLBACK_ROLE[role], -3)
            src, how = FALLBACK_SOURCE, "built-in fallback"
        if location == "Boston" and how != "built-in fallback":
            src += " (Boston priced at the Los Angeles cell as a proxy)"
        self.sourced[how] += 1
        b = SalaryBenchmark(role=role, location=location, annual_usd=round(value, 0),
                            source=f"{how}: {src}")
        self._cache[key] = b
        return b

    def premium_for(self, location: str) -> tuple[float, float, str]:
        """(low, high, note) switch premium for a location tier, per the file's markets:
        India and Canada have their own figures; the US figure is used for the US and,
        stated in the note, for every other market (the file has none for them)."""
        market = ("India" if location in INDIA_TIERS else "Canada" if location == "Canada"
                  else "US" if location in _US_TIERS else "")
        if market and market in self.premium_by_market:
            lo, hi, src = self.premium_by_market[market]
            return lo, hi, f"{market} x{lo:.3f}-{hi:.3f} ({src})"
        lo, hi, src = self.premium_by_market["US"]
        return lo, hi, (f"no {location or 'location'} figure in the file: US x{lo:.3f}-{hi:.3f} "
                        f"used ({src})")

    def employer_multiplier(self, employer: str, location: str = "") -> tuple[float, str]:
        n = _norm(re.sub(r"\(.*?\)", "", employer or ""))
        if not n:
            return DEFAULT_TIER_MULT, "unknown"
        for tier, names in _TIER_EMPLOYERS.items():
            for name in names:
                nn = _norm(name)
                if n == nn or (len(nn) > 4 and n.startswith(nn + " ")):
                    us, india = self.tier_mult.get(tier, (DEFAULT_TIER_MULT, DEFAULT_TIER_MULT))
                    return (india if location in INDIA_TIERS else us), tier
        return DEFAULT_TIER_MULT, "other"


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

# Functions a software / fintech startup rarely staffs: a visible share of them suggests
# profiles of namesake employers ("Clay", "Ramp", "Mercury" are common words).
OFF_PROFILE_FUNCTIONS = frozenset({"education", "community and social services",
                                   "military and protective services", "healthcare services",
                                   "real estate"})
OFF_PROFILE_SHARE = 0.02
OFF_PROFILE_MIN = 10          # people; tiny teams are not flagged on one odd profile
REGION_EXCESS = 1.25


def data_quality_flags(regions: dict[str, Any] | None, roles: dict[str, Any] | None,
                       headcount: float | None, largest_country: str, hq: str) -> list[str]:
    """Warnings that indexed staff may include namesake profiles. Estimates are not changed;
    the flags travel as limitations."""
    flags = []
    if regions and headcount:
        located = sum(_num(v) or 0 for k, v in regions.items()
                      if classify_region(str(k))[0] == "country")
        if located > REGION_EXCESS * headcount:
            flags.append(f"Country-level region counts sum to {located:,.0f}, more than "
                         f"headcount {headcount:,.0f}: the index likely mixes in profiles of "
                         "namesake companies; location mix and payroll are unreliable.")
    if roles:
        total = sum(_num(v) or 0 for v in roles.values()) or 1
        off = {k: v for k, v in roles.items() if str(k).casefold() in OFF_PROFILE_FUNCTIONS}
        n_off = sum(_num(v) or 0 for v in off.values())
        share = n_off / total
        if share >= OFF_PROFILE_SHARE and n_off >= OFF_PROFILE_MIN:
            flags.append(f"{share:.0%} of indexed staff are in functions unusual for this kind of "
                         f"company ({', '.join(off)}): possible namesake profiles; headcount may "
                         "be overstated.")
    hq_iso = ""
    for part in reversed([x.strip() for x in (hq or "").split(",") if x.strip()]):
        hq_iso = revenue_model.COUNTRY_ISO3.get(part.casefold(), "")
        if hq_iso:
            break
    if largest_country and hq_iso and largest_country != hq_iso:
        flags.append(f"Largest staff country {largest_country} differs from the HQ country "
                     f"{hq_iso}: check for namesake profiles before trusting the location mix.")
    return flags


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
        n_sw = sum(1 for s in est if s.method.startswith("switch-premium"))
        p.method.append(f"Switch-premium samples: {len(est)} people ({n_sw} priced from a prior "
                        "employer x employer tier x location-specific switch premium); they "
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
    if bm.sourced:
        p.method.append("Benchmark cells used: " + ", ".join(f"{k} {v}" for k, v in
                                                             bm.sourced.most_common()) + ".")
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
        tier_loc = loc or DEFAULT_TIER
        mult, tier = bm.employer_multiplier(str(prior.get("name")), tier_loc)
        lo, hi, note = bm.premium_for(tier_loc)
        s.prior_employer = str(prior.get("name"))
        s.prior_salary_usd = round(bench * mult, 0)
        s.est_salary_usd = round(s.prior_salary_usd * (lo + hi) / 2, 0)
        s.method = (f"switch-premium: benchmark x {tier} tier {mult:.2f} x premium "
                    f"{(lo + hi) / 2:.3f}; {note}")
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
    (r"sales teams|go-to-market|\bGTM\b|revenue teams|sales reps|outbound|prospect|pipeline", "Sales and go-to-market teams"),
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


def infer_customers(signals: Signals, samples: list[EmployeeSample] | None = None, *,
                    naics: str = "") -> CustomerProfile:
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
    naics = naics or signals.market.naics
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
        n_priors = sum(priors.values())
        for sector, c in sectors.most_common(2):
            if c >= max(4, 0.3 * n_priors):
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
    eco.limitations += data_quality_flags(regions, roles, signals.headcount_total, largest,
                                          signals.hq)
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
    nd = ((rec.get("taxonomy") or {}).get("primary_naics_detail")) or {}
    naics = f"{nd.get('naics_code') or ''} {nd.get('industry') or ''}".strip()
    eco.customers = infer_customers(signals, samples, naics=naics)
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


# ---- 8-company validation run (python -m proofroom.economics record|results) ----------

COMPANIES: tuple[tuple[str, int, str], ...] = (
    ("koah", 3718859, "koahlabs.com"), ("linear", 633791, "linear.app"),
    ("attio", 664000, "attio.com"), ("clay", 1010356, "clay.com"),
    ("vercel", 631347, "vercel.com"), ("retool", 633593, "retool.com"),
    ("ramp", 689494, "ramp.com"), ("mercury", 631990, "mercury.com"),
    ("terrastack", 6421460, "terrastack.in"))
NEW_FIXTURES = frozenset({"clay", "vercel", "retool", "ramp", "mercury", "terrastack"})


async def _signals(client: Crustdata, cid: int, domain: str, today: date | None = None
                   ) -> Signals:
    from proofroom.signals import fetch_signals
    # search=False: economics needs no peer set (saves ~6.5 credits per new company).
    return await fetch_signals(client, cid, domain, today=today, search=False, jobs=True,
                               logo=False)


async def record(name: str, cid: int, domain: str) -> float:
    """CACHED run (live on a miss) of what economics needs, captured as FIXTURE files.
    Existing signals fixtures are reused; only missing requests go live."""
    from proofroom.crustdata import CACHED, sum_credits
    from proofroom.signals import cache_files_for, capture_signals
    today = date.today()
    async with Crustdata(CACHED) as client:
        if name in NEW_FIXTURES:
            await client.identify_domain(domain)
            await _signals(client, cid, domain, today)
        await sample_employees(client, cid, SAMPLE_N)
        files = cache_files_for(client)
        spent, _ = sum_credits(client.attempts)
    capture_signals(name, files, as_of=today if name in NEW_FIXTURES else None)
    return spent


async def replay(name: str, cid: int, domain: str) -> tuple[Signals, Economics]:
    async with Crustdata(FIXTURE, fixture=name) as client:
        sig = await _signals(client, cid, domain)
        eco = await build_economics(client, sig, cid)
    return sig, eco


def _top_locations(p: PayrollEstimate, k: int = 3) -> str:
    hc = p.headcount or sum(p.by_location.values()) or 1
    return ", ".join(f"{t} {v / hc:.0%}" for t, v in list(p.by_location.items())[:k])


def _truth_source(t: dict) -> str:
    """Short source label for a ground-truth entry: host of the reported figure matching
    best_estimate_usd (else the latest reported entry), plus its as-of date."""
    from urllib.parse import urlparse
    rep = [r for r in t.get("reported") or [] if isinstance(r, dict)]
    best = _num(t.get("best_estimate_usd"))
    pick = next((r for r in rep if _num(r.get("value_usd")) == best), rep[-1] if rep else {})
    url = str(pick.get("source") or t.get("source") or "")
    host = urlparse(url).netloc.replace("www.", "") if url.startswith("http") else url[:40]
    exact = _num(pick.get("value_usd")) == best
    return (f"{host}, {t.get('best_as_of') or pick.get('as_of') or ''}"
            + ("" if exact else "; best estimate differs from the cited figure")).strip(", ")


def _pct_err(est: float | None, truth: float | None) -> float | None:
    if not est or not truth:
        return None
    return (est - truth) / truth * 100


def results_markdown(rows: list[tuple[str, Signals, Economics]],
                     truth: dict[str, dict]) -> str:
    model = revenue_model.RevenueModel.load()
    doc = model.doc if model else {}
    cv = doc.get("cv", {})
    m, b, ml = cv.get("model", {}), cv.get("baseline", {}), cv.get("model_listed_bucket", {})
    out = ["# Economics model results (D26)", "",
           "All figures are ESTIMATES from Crustdata indexed data (FIXTURE replay of captured "
           "responses), not company-reported numbers. Reported ARR comes from "
           "`proofroom/data/revenue_ground_truth.json` (press / company statements).", "",
           "## Revenue model cross-validation", "",
           f"Model: {model.describe() if model else 'n/a'}. Features: "
           + ", ".join(f"`{f}`" for f in doc.get("features", [])) + ".", "",
           "| 5-fold CV (held-out) | Band hit rate | Median abs log10 err | Mean abs log10 err "
           "| Within 2x of midpoint |", "|---|---|---|---|---|"]
    for label, x in (("Model (headcount-implied size bucket, as at inference)", m),
                     ("Model (listed size bucket: reproduces Crustdata's band)", ml),
                     ("Naive baseline: headcount x median revenue/employee", b)):
        if x:
            out.append(f"| {label} | {x['band_hit_rate']:.0%} | {x['median_abs_log10_error']:.3f} "
                       f"(x{10 ** x['median_abs_log10_error']:.2f}) | "
                       f"{x['mean_abs_log10_error']:.3f} | {x['within_2x_rate']:.0%} |")
    out += ["", "Target = Crustdata's own revenue band midpoint (interval-censored); the "
            "training set is " + str(doc.get("n_rows", "?")) + " private companies from "
            "Company Search. " + " ".join(doc.get("notes", [])), "",
            f"## {len(rows)} companies", "",
            "| Company | Headcount | Top locations | Avg salary (range) | Loaded payroll | "
            "Runway bound | Crustdata band | Model raw | Our estimate (range) | Reported ARR "
            "(source) | Error | In our range | In band |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    errs = []
    for name, sig, eco in rows:
        p, r = eco.payroll, eco.revenue
        t = truth.get(sig.domain.casefold()) or {}
        tv = _num(t.get("best_estimate_usd"))
        err = _pct_err(r.point_usd, tv)
        raw_err = _pct_err(r.model_raw_usd, tv)
        if err is not None:
            errs.append((name, err, raw_err, tv, r, sig))
        band = (f"{_usd(r.crustdata_band_usd[0])}–{_usd(r.crustdata_band_usd[1])}"
                if r.crustdata_band_usd else "none")
        rng = p.avg_salary_range_usd
        in_range = (tv is not None and r.low_usd is not None
                    and r.low_usd <= tv <= r.high_usd)
        in_band = (tv is not None and r.crustdata_band_usd is not None
                   and r.crustdata_band_usd[0] <= tv <= r.crustdata_band_usd[1])
        src = _truth_source(t)
        out.append(
            f"| {sig.company} | {p.headcount or 0:,.0f} | {_top_locations(p)} | "
            f"{_usd(p.avg_salary_usd)} ({_usd(rng[0]) if rng else '?'}–"
            f"{_usd(rng[1]) if rng else '?'}) | {_usd(p.loaded_cost_usd)} | "
            f"{(str(round(p.est_runway_months)) + ' mo') if p.est_runway_months else 'n/a'} | "
            f"{band} | {_usd(r.model_raw_usd)} | {_usd(r.point_usd)} ({_usd(r.low_usd)}–"
            f"{_usd(r.high_usd)}) | {(_usd(tv) + ' (' + src + ')') if tv else 'n/a'} | "
            f"{(f'{err:+.0f}%') if err is not None else 'n/a'} | "
            f"{('yes' if in_range else 'no') if tv else 'n/a'} | "
            f"{('yes' if in_band else 'no') if tv else 'n/a'} |")
    if errs:
        abs_e = sorted(abs(e[1]) for e in errs)
        raw_e = sorted(abs(e[2]) for e in errs if e[2] is not None)
        mid = [abs(_pct_err((x[4].crustdata_band_usd[0] + x[4].crustdata_band_usd[1]) / 2, x[3]))
               for x in errs if x[4].crustdata_band_usd]
        med = lambda v: sorted(v)[len(v) // 2] if len(v) % 2 else (sorted(v)[len(v) // 2 - 1] + sorted(v)[len(v) // 2]) / 2  # noqa: E731
        out += ["", f"Median absolute error vs reported ARR over {len(errs)} companies: "
                f"our point {med(abs_e):.0f}%, model raw {med(raw_e):.0f}%"
                + (f", Crustdata band midpoint {med(mid):.0f}%" if mid else "") + ". "
                f"Reported ARR inside our range: {sum(1 for e in errs if e[4].low_usd and e[4].low_usd <= e[3] <= e[4].high_usd)}"
                f"/{len(errs)}; inside Crustdata's band: "
                f"{sum(1 for e in errs if e[4].crustdata_band_usd and e[4].crustdata_band_usd[0] <= e[3] <= e[4].crustdata_band_usd[1])}"
                f"/{len(errs)}."]
    flagged = [(sig.company, [x for x in eco.limitations if "namesake" in x]) for _, sig, eco in rows]
    flagged = [(c, f) for c, f in flagged if f]
    if flagged:
        out += ["", "### Data-quality flags (possible namesake profiles in the index)", ""]
        out += [f"- **{c}**: " + " ".join(f) for c, f in flagged]
    if errs:
        under = [e for e in errs if e[1] < 0]
        out += ["", "### Findings", "",
                f"- {len(under)} of {len(errs)} point estimates are BELOW the reported figure. The "
                "model learns Crustdata's own band (the only revenue label available at scale), and "
                "those bands sit far below reported ARR for fast-growing venture-backed companies "
                "(see the 'In band' column), so the model inherits that downward bias. It is "
                "validated against bands, not against reported revenue.",
                "- Crustdata's band follows the LISTED employee_count_range bucket, which is often "
                "stale; the stale-band rule (band = floor only when the indexed headcount implies a "
                "bigger bucket) is what lets the estimate leave a band that is too low.",
                "- Clay and Ramp headcounts are inflated by namesake profiles (common-word names), so "
                "their payroll and model inputs are unreliable; Clay's 'hit' is partly luck from an "
                "overstated headcount.",
                "- Reported figures are themselves mixed (run-rate, ARR, 'passed $X' lower bounds, "
                "third-party estimates); see revenue_ground_truth.json notes."]
    out += ["", "## Customer profiles", "",
            "| Company | Model | Target customers | Use cases | Talent sources (sampled staff) |",
            "|---|---|---|---|---|"]
    for name, sig, eco in rows:
        c = eco.customers
        out.append(f"| {sig.company} | {c.business_model} | {'; '.join(c.target_customers[:4])} | "
                   f"{'; '.join(c.use_cases[:3])} | {', '.join(c.talent_sources[:4])} |")
    out += ["", "## Method notes per company", ""]
    for name, sig, eco in rows:
        out.append(f"**{sig.company}** — payroll: " + " ".join(eco.payroll.method[2:6])
                   + " Revenue: " + " ".join(eco.revenue.method[1:4]))
        out.append("")
    return "\n".join(out)


if __name__ == "__main__":  # python -m proofroom.economics record [name] | results
    import asyncio
    import sys
    logging.basicConfig(level=logging.WARNING)
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "record":
        names = set(sys.argv[2:])
        total = 0.0
        for n, cid, dom in COMPANIES:
            if names and n not in names:
                continue
            spent = asyncio.run(record(n, cid, dom))
            total += spent
            print(f"{n}: LIVE credits {spent}")
        print(f"total LIVE credits {round(total, 2)}")
    elif cmd == "results":
        rows = []
        for n, cid, dom in COMPANIES:
            sig, eco = asyncio.run(replay(n, cid, dom))
            rows.append((n, sig, eco))
            r, p = eco.revenue, eco.payroll
            print(f"{sig.company:<8} hc={p.headcount} avg={_usd(p.avg_salary_usd)} "
                  f"loaded={_usd(p.loaded_cost_usd)} band={r.crustdata_band_usd} "
                  f"raw={_usd(r.model_raw_usd)} point={_usd(r.point_usd)} "
                  f"[{_usd(r.low_usd)}-{_usd(r.high_usd)}] {eco.customers.business_model}")
        md = results_markdown(rows, load_ground_truth())
        outp = Path(__file__).resolve().parent.parent / "docs" / "economics_results.md"
        outp.write_text(md, encoding="utf-8")
        print(f"wrote {outp}")
    else:
        print("usage: python -m proofroom.economics record [name ...] | results")
