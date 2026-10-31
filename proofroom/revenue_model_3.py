"""Revenue model v3 (ESTIMATE): v1's band-trained ridge plus new signals that target the
errors in docs/revenue_evaluation.md (namesake-inflated headcount, payroll, investor
quality, LinkedIn mentions, market width, hiring intensity). Results and ablations:
docs/revenue_model_3_results.md. Training: scripts/train_revenue_model_3.py.

Signals (each computed offline from recorded Crustdata data; sources in brackets):

1. clean_headcount [Company Enrich headcount.by_region_absolute, by_role_absolute,
   locations]. Region keys are rolled up to countries (economics.classify_region; a
   country's count is its country-level key, else its largest sub-key). Kept countries:
   the HQ country; a country with a listed office (locations.all_office_addresses); a
   `TECH_HUBS` country no larger than the HQ country. Everything else (e.g. Ramp's
   "Brazil" 6,877 against a US HQ with 2,196) is treated as namesake profiles.
   region_share = kept / all located. Functions in `IMPLAUSIBLE_FUNCTIONS` (Education,
   Community and Social Services, Military and Protective Services, Healthcare
   Services, Real Estate) are dropped unless the company description names that domain;
   function_share = 1 - dropped / all with a function. Because the two filters often
   catch the same namesake profiles, clean = headcount x min(region_share,
   function_share) (not the product). When located regions sum past headcount (Ramp
   9,879 vs 3,757) the share rescales them to headcount automatically.
2. loaded_payroll [salary_benchmarks.json via economics.Benchmarks: BLS OEWS / ONS /
   Payscale cells; employer_tiers]. Clean regions -> economics.dedupe_regions, clean
   roles -> economics.role_people, both summing to clean headcount; base = sum
   people(role, location) x benchmark. "Startup pay": tech roles (Engineering, Product,
   Design, Data & Research) outside India are multiplied by the file's employer-tier
   multiplier: `scaleup` 1.21 (BLS NAICS 513200 software publishers / all industries)
   for software/fintech companies with >= $100M indexed funding, `startup` 1.01 (Carta
   H1 2025 new-hire salary / BLS SF) for other funded companies, 1.0 when unfunded.
   Loaded = base x 1.3 (economics.OVERHEAD_MULTIPLIER).
3. payroll-implied revenue = k x loaded payroll; k is the median band-midpoint/payroll
   ratio per stage (early: < $100M funding; late: >= $100M) on the training band data,
   or the median reported-revenue/payroll ratio of the OTHER reported companies (LOO).
4. investor_quality [Company Enrich / Search funding.investors, funding.milestones
   lead_investors]: count of distinct `TOP_TIER_INVESTORS` (list below, chosen before
   looking at results) and whether the latest dated round's lead is top-tier.
5. mentions [POST /social_post/search, limit 0: total_count only, 0 credits]: LinkedIn
   posts by persons (actor.actor_type = person) whose mentions.company_id contains the
   company, all-time and last 12 months; plus the count of those whose text contains
   one of `PARTNER_PHRASES` (case-insensitive exact phrase, `[.]`).
6. market_width [POST /company/search, limit 1, ~0.13 credits each]: total_count of
   companies tagged with the company's first specific taxonomy category
   (signals.candidate_categories), and of those with last_fundraise_date in the last
   24 months (month-anchored); log10(1 + n).
7. hiring_intensity [Company Enrich hiring.openings_count]: openings / clean headcount.

Everything returned is an ESTIMATE, not reported revenue.
"""
from __future__ import annotations

import json
import math
import re
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from proofroom import economics as eco_mod
from proofroom import revenue_model as rm

DATA_DIR = rm.DATA_DIR
MODEL_PATH = DATA_DIR / "revenue_model_3.json"
FEATURES_PATH = DATA_DIR / "model3_features.json"
MODEL_VERSION = "rev-3"
SEARCH = "/company/search"
POSTS = "/social_post/search"

# ---- 1. clean headcount ------------------------------------------------------------------

TECH_HUBS = frozenset(rm.HIGH_COST_COUNTRIES | {"USA", "IND", "POL", "UKR", "ROU", "PRT",
                                                "ESP", "ARG", "BRA", "MEX", "COL", "SRB",
                                                "CZE", "EST"})
# Function -> description pattern that makes it plausible for this company.
IMPLAUSIBLE_FUNCTIONS: dict[str, re.Pattern] = {
    "education": re.compile(r"educat|school|learn|teach|tutor|student|universit|course", re.I),
    "community and social services": re.compile(r"nonprofit|non-profit|charit|social impact|"
                                                r"communit", re.I),
    "military and protective services": re.compile(r"defen[cs]e|military|public safety|"
                                                   r"law enforcement|security", re.I),
    "healthcare services": re.compile(r"health|medic|clinic|patient|hospital|care\b", re.I),
    "real estate": re.compile(r"real estate|property|properties|housing|mortgage|rental|"
                              r"proptech", re.I),
}


def _num(v: Any) -> float | None:
    return rm._f(v)


def country_counts(regions: dict[str, Any] | None) -> dict[str, float]:
    """Country ISO3 -> people. Country-level key when present, else the largest sub-key
    (metro/state keys overlap, so they are not summed)."""
    country: dict[str, float] = {}
    sub: dict[str, float] = {}
    for key, raw in (regions or {}).items():
        v = _num(raw)
        if not v or v <= 0:
            continue
        level, iso, _cluster = eco_mod.classify_region(str(key))
        if not iso:
            continue
        if level == "country":
            country[iso] = max(country.get(iso, 0.0), v)
        else:
            sub[iso] = max(sub.get(iso, 0.0), v)
    for iso, v in sub.items():
        country.setdefault(iso, v)
    return country


def hq_country(hq: str) -> str:
    for part in reversed([x.strip() for x in (hq or "").split(",") if x.strip()]):
        iso = rm._iso3(part)
        if iso:
            return iso
    return ""


def office_countries(addresses: list[str] | None) -> set[str]:
    out = set()
    for a in addresses or []:
        parts = [p.strip() for p in str(a).split(",") if p.strip()]
        if parts:
            last = parts[-1]
            iso = "USA" if last.upper() == "US" else rm._iso3(last)
            if iso:
                out.add(iso)
    return out


def clean_headcount(regions: dict[str, Any] | None, roles: dict[str, Any] | None,
                    headcount: float | None, hq_iso: str = "", description: str = "",
                    offices: set[str] | frozenset = frozenset()) -> dict:
    """Namesake-cleaned headcount (rule in the module doc). Deterministic, offline."""
    raw = float(headcount or 0.0)
    out: dict[str, Any] = {"raw": raw, "clean": raw, "region_share": 1.0,
                           "function_share": 1.0, "kept_countries": [],
                           "dropped_countries": {}, "dropped_functions": {}, "notes": []}
    if raw <= 0:
        return out
    cc = country_counts(regions)
    located = sum(cc.values())
    hq = hq_iso or (max(cc, key=cc.get) if cc else "")
    hq_n = cc.get(hq, 0.0)
    if cc and hq_n > 0:
        kept = {}
        for iso, n in cc.items():
            if iso == hq or iso in offices or (iso in TECH_HUBS and n <= hq_n):
                kept[iso] = n
            else:
                out["dropped_countries"][iso] = n
        out["region_share"] = sum(kept.values()) / located
        out["kept_countries"] = sorted(kept, key=lambda k: -kept[k])
        if located > raw * eco_mod.REGION_EXCESS:
            out["notes"].append(f"located regions sum to {located:,.0f} > headcount "
                                f"{raw:,.0f}: kept share rescaled to headcount")
    elif cc:
        out["kept_countries"] = sorted(cc)
        out["notes"].append(f"HQ country {hq or '?'} absent from region data: regions kept")
    total_roles = sum(_num(v) or 0 for v in (roles or {}).values())
    if total_roles > 0:
        dropped = {}
        for k, v in (roles or {}).items():
            pat = IMPLAUSIBLE_FUNCTIONS.get(str(k).strip().casefold())
            if pat is not None and not pat.search(description or ""):
                dropped[str(k)] = _num(v) or 0.0
        out["dropped_functions"] = dropped
        out["function_share"] = 1.0 - sum(dropped.values()) / total_roles
    share = min(out["region_share"], out["function_share"])
    out["clean"] = round(raw * share, 1)
    out["region_share"] = round(out["region_share"], 4)
    out["function_share"] = round(out["function_share"], 4)
    return out


def kept_regions(regions: dict[str, Any] | None, kept_countries: list[str]) -> dict[str, float]:
    keep = set(kept_countries)
    out = {}
    for k, v in (regions or {}).items():
        iso = eco_mod.classify_region(str(k))[1]
        if (not keep or iso in keep) and (_num(v) or 0) > 0:
            out[str(k)] = float(_num(v))
    return out


def kept_roles(roles: dict[str, Any] | None, dropped: dict[str, float]) -> dict[str, float]:
    return {str(k): float(_num(v)) for k, v in (roles or {}).items()
            if str(k) not in dropped and (_num(v) or 0) > 0}


# ---- 2. loaded payroll -------------------------------------------------------------------

_TIER_CACHE: dict[str, float] = {}


def employer_tier_multipliers() -> dict[str, float]:
    if not _TIER_CACHE:
        doc = json.loads(eco_mod.BENCHMARK_PATH.read_text(encoding="utf-8"))
        for t in doc.get("employer_tiers") or []:
            m = _num(t.get("multiplier_vs_market"))
            if m:
                _TIER_CACHE[str(t.get("tier"))] = m
    return _TIER_CACHE


def pay_tier(total_funding_usd: float | None, software_or_fintech: bool) -> str:
    f = total_funding_usd or 0.0
    if f >= 100e6 and software_or_fintech:
        return "scaleup"
    return "startup" if f > 0 else "market"


def loaded_payroll(clean: dict, regions: dict[str, Any] | None, roles: dict[str, Any] | None,
                   *, tier: str = "market", bm: "eco_mod.Benchmarks | None" = None) -> dict:
    """Loaded payroll on CLEAN headcount (module doc, signal 2)."""
    bm = bm or eco_mod.Benchmarks.load()
    hc = clean.get("clean") or 0.0
    if hc <= 0:
        return {"base_usd": None, "loaded_usd": None, "per_head_usd": None, "tier": tier}
    locs, _ = eco_mod.dedupe_regions(kept_regions(regions, clean.get("kept_countries") or []), hc)
    if not locs:
        locs = {eco_mod.DEFAULT_TIER: hc}
    fam, _ = eco_mod.role_people(kept_roles(roles, clean.get("dropped_functions") or {}), hc)
    if not fam:
        fam = {"Engineering": hc * 0.4, "Sales": hc * 0.2, "Operations": hc * 0.4}
    mult = employer_tier_multipliers().get(tier, 1.0) if tier != "market" else 1.0
    rt, lt = sum(fam.values()), sum(locs.values())
    base = 0.0
    for loc, n_loc in locs.items():
        for role, n_role in fam.items():
            m = mult if (role in eco_mod._TECH_ROLES and loc not in eco_mod.INDIA_TIERS) else 1.0
            base += n_loc * (n_role / rt) * bm.get(role, loc).annual_usd * m
    base *= hc / lt
    loaded = base * eco_mod.OVERHEAD_MULTIPLIER
    return {"base_usd": round(base, 0), "loaded_usd": round(loaded, 0),
            "per_head_usd": round(loaded / hc, 0), "tier": tier, "tier_multiplier": mult,
            "by_location": locs}


# ---- 3. payroll-implied revenue ------------------------------------------------------------

LATE_STAGE_FUNDING = 100e6


def stage_of(total_funding_usd: float | None) -> str:
    return "late" if (total_funding_usd or 0) >= LATE_STAGE_FUNDING else "early"


def fit_k(revenues: list[float], payrolls: list[float]) -> float:
    """Median revenue / loaded-payroll ratio (geometric-median-like, robust)."""
    r = [a / b for a, b in zip(revenues, payrolls) if a and b and a > 0 and b > 0]
    return float(np.median(r)) if r else float("nan")


def payroll_implied(loaded_usd: float | None, k: float) -> float | None:
    if not loaded_usd or not k or not math.isfinite(k):
        return None
    return float(loaded_usd) * k


def loo_k(revenues: list[float], payrolls: list[float]) -> list[float]:
    """Leave-one-out k for each company: median ratio of the others."""
    return [fit_k(revenues[:i] + revenues[i + 1:], payrolls[:i] + payrolls[i + 1:])
            for i in range(len(revenues))]


# ---- 4. investor quality -------------------------------------------------------------------

# Documented list (fixed before results were looked at; task brief + common VC rankings).
TOP_TIER_INVESTORS: dict[str, tuple[str, ...]] = {
    "Sequoia": ("sequoia", "sequoia capital"),
    "Andreessen Horowitz": ("andreessen horowitz", "a16z"),
    "Accel": ("accel",),
    "Founders Fund": ("founders fund",),
    "Benchmark": ("benchmark", "benchmark capital"),
    "Greylock": ("greylock", "greylock partners"),
    "Index Ventures": ("index ventures",),
    "Lightspeed": ("lightspeed", "lightspeed venture partners"),
    "Kleiner Perkins": ("kleiner perkins", "kpcb"),
    "General Catalyst": ("general catalyst",),
    "Thrive Capital": ("thrive", "thrive capital"),
    "Tiger Global": ("tiger global", "tiger global management"),
    "Coatue": ("coatue", "coatue management"),
    "Insight Partners": ("insight partners", "insight venture partners"),
    "GV": ("gv", "google ventures"),
    "Khosla Ventures": ("khosla ventures",),
    "Bessemer": ("bessemer venture partners", "bessemer"),
    "IVP": ("ivp", "institutional venture partners"),
    "ICONIQ": ("iconiq", "iconiq growth", "iconiq capital"),
    "Redpoint": ("redpoint", "redpoint ventures"),
    "First Round": ("first round", "first round capital"),
    "Y Combinator": ("y combinator", "ycombinator", "yc"),
}
_NORM = re.compile(r"[^a-z0-9 ]+")


def _norm_name(s: str) -> str:
    return " ".join(_NORM.sub(" ", str(s or "").casefold()).split())


def top_tier_of(name: str) -> str:
    """Canonical top-tier firm for an investor name, or "". Matches an alias exactly or as
    the leading words ("Sequoia Capital India" -> Sequoia); "Accel-KKR" does not match."""
    n = _norm_name(name)
    if not n or str(name).casefold().startswith("accel-kkr"):
        return ""
    for canon, aliases in TOP_TIER_INVESTORS.items():
        for a in aliases:
            if n == a or (len(a) > 3 and n.startswith(a + " ")):
                return canon
    return ""


def _split(v: Any) -> list[str]:
    if isinstance(v, list):
        return [str(x.get("name") if isinstance(x, dict) else x) for x in v if x]
    if isinstance(v, str):
        return [p.strip() for p in v.split(",") if p.strip()]
    return []


def investor_quality(investors: Any, milestones: list[dict] | None = None) -> dict:
    """Top-tier count over all indexed investors plus the latest dated round's lead tier
    (2 = top-tier lead, 1 = other named lead, 0 = no lead indexed)."""
    names = set(_split(investors))
    ms = [m for m in (milestones or []) if isinstance(m, dict)]
    for m in ms:
        names.update(_split(m.get("investors")) + _split(m.get("lead_investors")))
    top = sorted({t for t in (top_tier_of(n) for n in names) if t})
    dated = sorted((m for m in ms if (m.get("funding_date") or m.get("date"))
                    and "secondary" not in str(m.get("round_type") or "")),
                   key=lambda m: str(m.get("funding_date") or m.get("date")), reverse=True)
    lead_tier, lead = 0, ""
    for m in dated[:1]:
        leads = _split(m.get("lead_investors"))
        if leads:
            lead = ", ".join(leads)
            lead_tier = 2 if any(top_tier_of(x) for x in leads) else 1
    return {"n_top_tier": len(top), "top_tier": top, "last_lead": lead,
            "last_lead_tier": lead_tier, "n_investors": len(names)}


# ---- 5/6. request bodies (mentions are free with limit 0) -----------------------------------

PARTNER_PHRASES = ("sponsored", "partnered with", "powered by", "in partnership")


def mention_bodies(company_id: int, as_of: date) -> dict[str, dict]:
    base = [{"field": "mentions.company_id", "type": "in", "value": [int(company_id)]},
            {"field": "actor.actor_type", "type": "=", "value": "person"}]
    since = date(as_of.year - 1, as_of.month, min(as_of.day, 28)).isoformat()
    partner = {"op": "or", "conditions": [{"field": "text", "type": "[.]", "value": p}
                                          for p in PARTNER_PHRASES]}
    return {
        "mentions_all": {"filters": {"op": "and", "conditions": base}, "limit": 0},
        "mentions_12m": {"filters": {"op": "and", "conditions": base + [
            {"field": "date_posted", "type": "=>", "value": since}]}, "limit": 0},
        "mentions_partner": {"filters": {"op": "and", "conditions": base + [partner]},
                             "limit": 0},
    }


def market_bodies(category: str, as_of: date) -> dict[str, dict]:
    cond = {"field": "taxonomy.categories", "type": "=", "value": category}
    since = date(as_of.year - 2, as_of.month, 1).isoformat()   # month-anchored, 24 months
    return {
        "market_pool": {"filters": {"op": "and", "conditions": [cond]},
                        "fields": ["crustdata_company_id"], "limit": 1},
        "market_funded_24m": {"filters": {"op": "and", "conditions": [cond, {
            "field": "funding.last_fundraise_date", "type": "=>", "value": since}]},
            "fields": ["crustdata_company_id"], "limit": 1},
    }


def first_category(categories: list[str] | None) -> str:
    from proofroom.signals import candidate_categories
    c = candidate_categories({"taxonomy": {"categories": list(categories or [])}})
    return c[0] if c else ((categories or [""])[0] or "")


def _total(resp: Any) -> int | None:
    t = resp.get("total_count") if isinstance(resp, dict) else None
    return int(t) if isinstance(t, (int, float)) and not isinstance(t, bool) else None


async def fetch_counts(client: Any, company_id: int, category: str, as_of: date,
                       market: bool = True) -> dict[str, int | None]:
    """Mentions (free) and market-width (~0.26 credits) counts. Errors -> None."""
    from proofroom.errors import CrustError
    bodies = [(k, POSTS, b) for k, b in mention_bodies(company_id, as_of).items()]
    if market and category:
        bodies += [(k, SEARCH, b) for k, b in market_bodies(category, as_of).items()]
    out: dict[str, int | None] = {}
    for key, ep, body in bodies:
        try:
            out[key] = _total(await client.request("POST", ep, body))
        except (CrustError, OSError, ValueError):
            out[key] = None
    return out


# ---- inputs -> features ---------------------------------------------------------------------

def is_software_or_fintech(description: str, naics: str = "") -> bool:
    f = rm.category_flags(description)
    return bool(f["cat_devtools"] or f["cat_fintech"] or f["cat_b2b"] or f["cat_ai"]
                or str(naics)[:2] in {"51", "52", "54"})


def new_features(inp: dict) -> dict[str, float]:
    """The v3 additions from one raw input record (see `inputs_from_record`)."""
    raw_hc = _num(inp.get("headcount")) or 0.0
    desc = inp.get("description", "")
    clean = clean_headcount(inp.get("regions"), inp.get("roles"), raw_hc,
                            inp.get("hq_iso", ""), desc, set(inp.get("offices") or []))
    hc = max(clean["clean"], 1.0)
    funding = _num(inp.get("total_funding_usd"))
    tier = pay_tier(funding, is_software_or_fintech(desc, inp.get("naics", "")))
    pay = loaded_payroll(clean, inp.get("regions"), inp.get("roles"), tier=tier)
    iq = investor_quality(inp.get("investors"), inp.get("milestones"))
    c = inp.get("counts") or {}
    openings = _num(inp.get("openings")) or 0.0

    def lg(k: str) -> float:
        return math.log10(1.0 + max(_num(c.get(k)) or 0.0, 0.0))
    return {
        "log_clean_headcount": math.log10(hc),
        "clean_share": clean["clean"] / raw_hc if raw_hc else 1.0,
        "log_loaded_payroll": math.log10(max(pay["loaded_usd"] or 1.0, 1.0)),
        "log_payroll_per_head": math.log10(max(pay["per_head_usd"] or 1.0, 1.0)),
        "n_top_tier": float(min(iq["n_top_tier"], 8)),
        "last_lead_top_tier": 1.0 if iq["last_lead_tier"] == 2 else 0.0,
        "log_mentions": lg("mentions_all"),
        "log_mentions_12m": lg("mentions_12m"),
        "log_partner_posts": lg("mentions_partner"),
        "log_market_pool": lg("market_pool"),
        "log_market_funded_24m": lg("market_funded_24m"),
        "openings_per_head": min(openings / hc, 1.0),
    }


FEATURE_GROUPS: dict[str, tuple[str, ...]] = {
    "clean_headcount": ("log_clean_headcount", "clean_share"),
    "loaded_payroll": ("log_loaded_payroll", "log_payroll_per_head"),
    "investor_quality": ("n_top_tier", "last_lead_top_tier"),
    "mentions": ("log_mentions", "log_mentions_12m", "log_partner_posts"),
    "market_width": ("log_market_pool", "log_market_funded_24m"),
    "hiring_intensity": ("openings_per_head",),
}
NEW_FEATURES: tuple[str, ...] = tuple(f for g in FEATURE_GROUPS.values() for f in g)


def inputs_from_record(rec: dict, *, headcount: float | None = None, description: str = "",
                       hq: str = "", total_funding_usd: float | None = None) -> dict:
    """Stripped raw inputs (no contact fields) from a Company Enrich record."""
    hc = rec.get("headcount") or {}
    tax = rec.get("taxonomy") or {}
    fu = rec.get("funding") or {}
    loc = rec.get("locations") or {}
    info = rec.get("basic_info") or {}
    nd = tax.get("primary_naics_detail") or {}
    hq = hq or str(loc.get("headquarters") or "")
    ms = [{k: m.get(k) for k in ("round_type", "date", "funding_date", "amount_usd",
                                 "investors", "lead_investors")}
          for m in (fu.get("milestones") or []) if isinstance(m, dict)]
    return {
        "headcount": headcount if headcount is not None else _num(hc.get("total")),
        "regions": hc.get("by_region_absolute") or {},
        "roles": hc.get("by_role_absolute") or {},
        "hq": hq, "hq_iso": hq_country(hq) or rm._iso3(str(loc.get("country") or "")),
        "offices": sorted(office_countries(loc.get("all_office_addresses"))),
        "description": (description or str(info.get("description") or ""))[:500],
        "categories": [str(c) for c in tax.get("categories") or [] if c],
        "naics": str(nd.get("naics_code") or ""),
        "investors": list(fu.get("investors") or []),
        "milestones": ms,
        "total_funding_usd": (total_funding_usd if total_funding_usd is not None
                              else _num(fu.get("total_investment_usd"))),
        "openings": _num((rec.get("hiring") or {}).get("openings_count")),
    }


# ---- model ---------------------------------------------------------------------------------

class Model3:
    def __init__(self, doc: dict):
        self.doc = doc
        self.features = list(doc["features"])
        self.w = np.array(doc["coef_standardized"], float)
        self.b = float(doc["intercept"])
        self.mu = np.array(doc["feature_means"], float)
        self.sd = np.array(doc["feature_stds"], float)
        self.sd[self.sd == 0] = 1.0

    @classmethod
    def load(cls, path: Path | None = None) -> "Model3 | None":
        try:
            return cls(json.loads((path or MODEL_PATH).read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError):
            return None

    def predict_log10(self, feats: dict[str, float]) -> float:
        x = np.array([feats[k] for k in self.features], float)
        return float(((x - self.mu) / self.sd) @ self.w + self.b)


def predict_v3(signals: Any, economics: Any, extra_features: dict) -> dict:
    """Offline, deterministic v3 estimate. `extra_features` is model3_features_for()'s
    output (raw inputs + counts). Returns v1 point, v3 raw/point, payroll-implied (k
    from the 6 reported companies and from band data), clean-headcount benchmark and an
    ensemble (geometric mean of v3 point, payroll-implied and clean benchmark)."""
    doc = Model3.load()
    as_of = date.fromisoformat(extra_features.get("as_of") or date.today().isoformat())
    inp = extra_features.get("inputs") or {}
    v1 = rm.features_from_signals(signals, as_of, extra_features.get("largest_country", ""))
    new = new_features(inp)
    out: dict[str, Any] = {"label": "ESTIMATE (not reported revenue)", "version": MODEL_VERSION,
                           "new_features": {k: round(v, 4) for k, v in new.items()}}
    v1_point = getattr(getattr(economics, "revenue", None), "point_usd", None)
    out["v1_point_usd"] = v1_point
    band = signals.revenue_band_usd
    if band is not None:
        band = (max(float(band[0]), 0.0), float(band[1]))
    clamp_band, _ = rm.effective_band(band, extra_features.get("listed_bucket", ""),
                                      signals.headcount_total)
    if doc and v1 is not None:
        raw = 10 ** doc.predict_log10({**v1, **new})
        out["v3_raw_usd"] = round(raw, 0)
        out["v3_point_usd"] = round(rm.clamp_to_band(raw, clamp_band)[0], 0)
    clean = clean_headcount(inp.get("regions"), inp.get("roles"), inp.get("headcount"),
                            inp.get("hq_iso", ""), inp.get("description", ""),
                            set(inp.get("offices") or []))
    out["clean_headcount"] = clean["clean"]
    out["raw_headcount"] = clean["raw"]
    pay_loaded = 10 ** new["log_loaded_payroll"] if new["log_loaded_payroll"] > 0 else None
    out["loaded_payroll_usd"] = round(pay_loaded, 0) if pay_loaded else None
    d = doc.doc if doc else {}
    stage = stage_of(inp.get("total_funding_usd"))
    k_band = (d.get("payroll_k_band") or {}).get(stage)
    k_rep = d.get("payroll_k_reported")
    out["payroll_implied_band_k_usd"] = payroll_implied(pay_loaded, k_band) if k_band else None
    out["payroll_implied_reported_k_usd"] = payroll_implied(pay_loaded, k_rep) if k_rep else None
    rpe = d.get("revenue_per_clean_employee_reported")
    out["clean_benchmark_usd"] = clean["clean"] * rpe if rpe and stage == "late" else None
    parts = [v for v in (out.get("v3_point_usd"), out["payroll_implied_reported_k_usd"]
                         if stage == "late" else None, out["clean_benchmark_usd"]) if v]
    out["ensemble_usd"] = round(float(np.exp(np.mean(np.log(parts)))), 0) if parts else None
    out["stage"] = stage
    if stage == "early":
        out["note"] = ("early-stage (< $100M indexed funding): reported-company k and the "
                       "clean benchmark come from scaleups and are not used in the ensemble")
    return out


async def model3_features_for(client: Any, company_id: int, signals: Any,
                              economics: Any = None) -> dict:
    """Raw v3 inputs for one company: the full Company Enrich record already on disk
    (0 credits), plus mentions (free) and market-width counts (~0.26 credits) through
    `client` (FIXTURE mode replays them)."""
    rec = eco_mod._enrich_record(client, company_id) or {}
    as_of = eco_mod._today(client)
    tf = signals.metrics.get("total_funding_usd") if getattr(signals, "metrics", None) else None
    inp = inputs_from_record(rec, headcount=signals.headcount_total,
                             description=signals.description, hq=signals.hq,
                             total_funding_usd=tf.value if tf else None)
    cat = first_category(inp["categories"])
    inp["counts"] = await fetch_counts(client, company_id, cat, as_of)
    inp["category"] = cat
    hc = rec.get("headcount") or {}
    return {"as_of": as_of.isoformat(), "inputs": inp,
            "largest_country": str(hc.get("largest_headcount_country") or ""),
            "listed_bucket": str((rec.get("basic_info") or {}).get("employee_count_range") or "")}
