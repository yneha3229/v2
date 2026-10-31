"""Revenue model (D26): a log-linear ridge regression trained on Crustdata Company Search
rows, then used to narrow a company's own Crustdata revenue band.

Everything this module returns is an ESTIMATE. The training target is itself Crustdata's
third-party revenue band (not reported revenue), so the model learns "where inside the
indexed band a company with these signals tends to sit" and is validated against bands
(cross-validation) and, separately, against publicly reported ARR for 8 companies
(docs/economics_results.md).

Training (scripts/train_revenue_model.py):
- Rows: private companies (company_type "Privately Held", markets PRIVATE, founded >= 2012,
  software / internet / financial-services industries) WITH a revenue band, stratified by
  employee_count_range (11-50 ... 1001-5000) and three sort orders per stratum.
- Target: y = log10(band midpoint). The bounds are kept: a row is interval-censored in
  [log10(lower), log10(upper)] (a lower bound of 0 is floored at `MIN_REVENUE_USD`).
- Fit A, "midpoint ridge": ridge on standardized features against the midpoint.
- Fit B, "interval EM" (Tobit-like): start from the midpoint fit; repeat: predict, set each
  row's working target to clamp(prediction, log lower, log upper), refit. At convergence
  the loss is the squared distance from the prediction to the band (zero inside it).
  The working target starts at the midpoint, so the fit stays anchored near it.
- 5-fold CV (fixed seed) for both fits and for the naive baseline
  revenue = headcount x median(revenue per employee of the training fold). The fit with
  the better held-out median |log10 error| is saved (ties broken by band hit rate).
- The ridge penalty is picked from `LAMBDAS` by the same CV (mildly optimistic; noted).

Inference (`estimate_revenue`): features from Signals -> model raw -> clamp into the
company's Crustdata band (the narrowing step) -> point; range = point x/÷ 10^q80 where q80
is the CV 80th-percentile |log10 error|, intersected with the band.
"""
from __future__ import annotations

import json
import math
import re
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from proofroom.research_models import PayrollEstimate, RevenueEstimate, Signals

DATA_DIR = Path(__file__).resolve().parent / "data"
MODEL_PATH = DATA_DIR / "revenue_model.json"
TRAINING_PATH = DATA_DIR / "training_set.json"
MODEL_VERSION = "rev-1"

MIN_REVENUE_USD = 50_000.0     # floor for a band lower bound of $0 (log10 needs > 0)
LAMBDAS = (0.1, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0)
EM_ITERS = 50
CV_FOLDS = 5
CV_SEED = 7
RANGE_QUANTILE = 0.8           # range = point x/÷ 10^(q80 of held-out |log10 error|)

FEATURES: tuple[str, ...] = (
    "log_headcount", "hc_growth_log", "log_funding", "funded", "log_last_round",
    "years_since_round", "age_years", "largest_country_us", "largest_country_high_cost",
    "hq_tier1_metro", "cat_ai", "cat_devtools", "cat_fintech", "cat_consumer", "cat_b2b",
    "log_size_bucket")

# LinkedIn-style employee_count_range buckets (basic_info.employee_count_range) and the
# midpoint used for the `log_size_bucket` feature. Crustdata's revenue band tracks this
# self-reported bucket far more than the indexed headcount (training set: 15 of 23 rows in
# 501-1000 sit in $500M-1B), so training uses the LISTED bucket (what generated the band)
# and inference uses the bucket implied by the CURRENT headcount ("refreshed" band level).
SIZE_BUCKETS: tuple[tuple[str, int, int, float], ...] = (
    ("1", 0, 1, 1.0), ("2-10", 2, 10, 6.0), ("11-50", 11, 50, 30.0),
    ("51-200", 51, 200, 125.0), ("201-500", 201, 500, 350.0), ("501-1000", 501, 1000, 750.0),
    ("1001-5000", 1001, 5000, 3000.0), ("5001-10000", 5001, 10000, 7500.0),
    ("10001+", 10001, 10**9, 15000.0))
_BUCKET_MID = {b[0]: b[3] for b in SIZE_BUCKETS}
_BUCKET_RANK = {b[0]: i for i, b in enumerate(SIZE_BUCKETS)}


def bucket_of(headcount: float) -> str:
    for name, _lo, hi, _mid in SIZE_BUCKETS:
        if headcount <= hi:
            return name
    return SIZE_BUCKETS[-1][0]

HIGH_COST_COUNTRIES = frozenset({"GBR", "CHE", "CAN", "AUS", "DEU", "NLD", "SGP", "ISR", "IRL",
                                 "FRA", "SWE", "DNK", "NOR", "FIN", "BEL", "AUT", "LUX", "NZL",
                                 "JPN"})
COUNTRY_ISO3 = {
    "united states": "USA", "usa": "USA", "us": "USA", "united kingdom": "GBR", "uk": "GBR",
    "england": "GBR", "india": "IND", "canada": "CAN", "germany": "DEU", "france": "FRA",
    "netherlands": "NLD", "ireland": "IRL", "switzerland": "CHE", "australia": "AUS",
    "singapore": "SGP", "israel": "ISR", "sweden": "SWE", "denmark": "DNK", "norway": "NOR",
    "finland": "FIN", "belgium": "BEL", "austria": "AUT", "spain": "ESP", "portugal": "PRT",
    "italy": "ITA", "poland": "POL", "ukraine": "UKR", "romania": "ROU", "brazil": "BRA",
    "mexico": "MEX", "argentina": "ARG", "colombia": "COL", "chile": "CHL", "japan": "JPN",
    "china": "CHN", "new zealand": "NZL", "luxembourg": "LUX", "philippines": "PHL",
    "pakistan": "PAK", "nigeria": "NGA", "kenya": "KEN", "south africa": "ZAF",
    "united arab emirates": "ARE", "serbia": "SRB", "czechia": "CZE", "estonia": "EST",
    "greece": "GRC", "turkey": "TUR", "vietnam": "VNM", "indonesia": "IDN",
}
TIER1_HQ = re.compile(r"san francisco|bay area|palo alto|mountain view|menlo park|redwood city|"
                      r"san mateo|sunnyvale|san jose|oakland|berkeley|new york|brooklyn|"
                      r"manhattan", re.I)

# Category flags from the description (the same text exists in Search and Enrich, so
# training and inference flags are computed identically).
CATEGORY_PATTERNS: dict[str, re.Pattern] = {
    "cat_ai": re.compile(r"\bA\.?I\b|artificial intelligence|machine learning|\bLLMs?\b|"
                         r"generative|\bagents?\b|\bagentic\b", re.I),
    "cat_devtools": re.compile(r"developer|\bAPIs?\b|\bSDKs?\b|devops|open[- ]source|"
                               r"infrastructure|engineering teams|\bcode\b|frontend|deploy", re.I),
    "cat_fintech": re.compile(r"payment|banking|\bbanks?\b|fintech|financial|card|lending|credit|"
                              r"insurance|treasury|expense|accounting|invoic|payroll", re.I),
    "cat_consumer": re.compile(r"\bconsumers?\b|gaming|\bgames?\b|shoppers|\bfans\b|dating|"
                               r"fitness|creators?|mobile app|households|families", re.I),
    "cat_b2b": re.compile(r"\bbusinesses\b|enterprise|\bB2B\b|\bSaaS\b|\bteams\b|companies|"
                          r"organi[sz]ations|workflow|\bCRM\b|sales teams|go-to-market|"
                          r"\bGTM\b", re.I),
}


# ---- feature extraction (shared by training and inference) -----------------------------

def _f(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _iso3(country: str) -> str:
    c = (country or "").strip()
    if len(c) == 3 and c.isupper():
        return c
    return COUNTRY_ISO3.get(c.casefold(), "")


def category_flags(text: str) -> dict[str, float]:
    return {k: 1.0 if p.search(text or "") else 0.0 for k, p in CATEGORY_PATTERNS.items()}


def make_features(*, headcount: float | None, growth_yoy_pct: float | None,
                  total_funding_usd: float | None, last_round_usd: float | None,
                  months_since_round: float | None, year_founded: int | None,
                  largest_country: str, hq: str, description: str,
                  as_of: date, size_bucket: str = "") -> dict[str, float] | None:
    """One feature dict; None when headcount is unknown (the model needs it). An empty or
    unknown `size_bucket` uses the bucket implied by `headcount`."""
    if not headcount or headcount <= 0:
        return None
    g = growth_yoy_pct if growth_yoy_pct is not None else 0.0
    funding = max(total_funding_usd or 0.0, 0.0)
    years = (min(max(months_since_round, 0.0) / 12.0, 10.0)
             if months_since_round is not None else 10.0)
    age = min(max(as_of.year - year_founded, 0), 15) if year_founded else 8.0
    iso = _iso3(largest_country)
    feats = {
        "log_headcount": math.log10(headcount),
        "hc_growth_log": max(-1.0, min(1.5, math.log1p(max(g, -90.0) / 100.0))),
        "log_funding": math.log10(1.0 + funding),
        "funded": 1.0 if funding > 0 else 0.0,
        "log_last_round": math.log10(1.0 + max(last_round_usd or 0.0, 0.0)),
        "years_since_round": years,
        "age_years": float(age),
        "largest_country_us": 1.0 if iso == "USA" else 0.0,
        "largest_country_high_cost": 1.0 if iso in HIGH_COST_COUNTRIES else 0.0,
        "hq_tier1_metro": 1.0 if TIER1_HQ.search(hq or "") else 0.0,
    }
    feats.update(category_flags(description))
    bucket = size_bucket if size_bucket in _BUCKET_MID else bucket_of(headcount)
    feats["log_size_bucket"] = math.log10(_BUCKET_MID[bucket])
    return feats


def _months(since: str, as_of: date) -> float | None:
    s = str(since or "")[:10]
    try:
        d = date.fromisoformat(s)
    except ValueError:
        return None
    return (as_of - d).days / 30.4375


def row_from_search(c: dict) -> dict | None:
    """A stripped training row (no contact fields) from one Company Search result."""
    info = c.get("basic_info") or {}
    est = ((c.get("revenue") or {}).get("estimated")) or {}
    hc = c.get("headcount") or {}
    fu = c.get("funding") or {}
    loc = c.get("locations") or {}
    lo, hi = _f(est.get("lower_bound_usd")), _f(est.get("upper_bound_usd"))
    if hi is None or hi <= 0 or lo is None:
        return None
    gp = hc.get("growth_percent") or {}
    return {
        "crustdata_company_id": c.get("crustdata_company_id"),
        "name": str(info.get("name") or ""),
        "domain": str(info.get("primary_domain") or ""),
        "year_founded": info.get("year_founded"),
        "employee_count_range": str(info.get("employee_count_range") or ""),
        "description": str(info.get("description") or "")[:500],
        "revenue_lower_usd": lo, "revenue_upper_usd": hi,
        "headcount": _f(hc.get("total")),
        "headcount_growth_12m_pct": _f(gp.get("12m")),
        "largest_headcount_country": str(hc.get("largest_headcount_country") or ""),
        "total_funding_usd": _f(fu.get("total_investment_usd")),
        "last_round_usd": _f(fu.get("last_round_amount_usd")),
        "last_fundraise_date": str(fu.get("last_fundraise_date") or "")[:10],
        "last_round_type": str(fu.get("last_round_type") or ""),
        "hq": str(loc.get("headquarters") or ""),
        "country": str(loc.get("country") or ""),
    }


def features_from_row(row: dict, as_of: date, listed_bucket: bool = True
                      ) -> dict[str, float] | None:
    """Training features. `listed_bucket` uses the row's employee_count_range (what the
    band was generated from); False uses the headcount-implied bucket, as inference does."""
    yf = _f(row.get("year_founded"))
    return make_features(
        headcount=_f(row.get("headcount")), growth_yoy_pct=_f(row.get("headcount_growth_12m_pct")),
        total_funding_usd=_f(row.get("total_funding_usd")), last_round_usd=_f(row.get("last_round_usd")),
        months_since_round=_months(row.get("last_fundraise_date", ""), as_of),
        year_founded=int(yf) if yf else None, largest_country=row.get("largest_headcount_country", ""),
        hq=row.get("hq", ""), description=row.get("description", ""), as_of=as_of,
        size_bucket=row.get("employee_count_range", "") if listed_bucket else "")


def largest_country_from_mix(region_mix: dict[str, float]) -> str:
    """ISO3 of the largest country-level key in a Crustdata region mix ("United States")."""
    best, best_v = "", -1.0
    for k, v in (region_mix or {}).items():
        iso = COUNTRY_ISO3.get(str(k).strip().casefold(), "")
        if iso and (_f(v) or 0) > best_v:
            best, best_v = iso, float(v)
    return best


def features_from_signals(sig: Signals, as_of: date | None = None,
                          largest_country: str = "") -> dict[str, float] | None:
    m = sig.metrics
    def val(k: str) -> float | None:
        return m[k].value if k in m else None
    as_of = as_of or date.today()
    country = largest_country or largest_country_from_mix(sig.region_mix)
    if not country:
        country = _iso3(sig.hq.rsplit(",", 1)[-1]) if sig.hq else ""
    return make_features(
        headcount=sig.headcount_total, growth_yoy_pct=val("headcount_yoy_pct"),
        total_funding_usd=val("total_funding_usd"), last_round_usd=val("last_round"),
        months_since_round=val("months_since_last_round"), year_founded=sig.year_founded,
        largest_country=country, hq=sig.hq, description=sig.description, as_of=as_of)


# ---- fitting --------------------------------------------------------------------------

def targets(rows: list[dict]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    lo = np.array([max(r["revenue_lower_usd"], MIN_REVENUE_USD) for r in rows], float)
    hi = np.array([max(r["revenue_upper_usd"], MIN_REVENUE_USD * 1.0001) for r in rows], float)
    mid = np.array([(max(r["revenue_lower_usd"], 0) + r["revenue_upper_usd"]) / 2 for r in rows])
    mid = np.maximum(mid, MIN_REVENUE_USD)
    return np.log10(mid), np.log10(lo), np.log10(hi)


def design(feats: list[dict[str, float]]) -> np.ndarray:
    return np.array([[f[k] for k in FEATURES] for f in feats], float)


def _ridge(X: np.ndarray, y: np.ndarray, lam: float) -> tuple[np.ndarray, float, np.ndarray,
                                                                np.ndarray]:
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd
    ym = y.mean()
    A = Z.T @ Z + lam * np.eye(Z.shape[1])
    w = np.linalg.solve(A, Z.T @ (y - ym))
    return w, float(ym), mu, sd


def _predict(params: tuple, X: np.ndarray) -> np.ndarray:
    w, b, mu, sd = params
    return ((X - mu) / sd) @ w + b


def fit(X: np.ndarray, y_mid: np.ndarray, y_lo: np.ndarray, y_hi: np.ndarray, lam: float,
        method: str = "midpoint") -> tuple:
    params = _ridge(X, y_mid, lam)
    if method == "interval_em":
        y = y_mid.copy()
        for _ in range(EM_ITERS):
            y_new = np.clip(_predict(params, X), y_lo, y_hi)
            if np.max(np.abs(y_new - y)) < 1e-6:
                break
            y = y_new
            params = _ridge(X, y, lam)
    return params


def _folds(n: int, k: int = CV_FOLDS, seed: int = CV_SEED) -> list[np.ndarray]:
    idx = np.random.default_rng(seed).permutation(n)
    return [idx[i::k] for i in range(k)]


def _metrics(pred: np.ndarray, y_mid: np.ndarray, y_lo: np.ndarray, y_hi: np.ndarray) -> dict:
    err = np.abs(pred - y_mid)
    hit = (pred >= y_lo - 1e-9) & (pred <= y_hi + 1e-9)
    return {"band_hit_rate": round(float(hit.mean()), 4),
            "median_abs_log10_error": round(float(np.median(err)), 4),
            "mean_abs_log10_error": round(float(err.mean()), 4),
            "q80_abs_log10_error": round(float(np.quantile(err, RANGE_QUANTILE)), 4),
            "within_2x_rate": round(float((err <= math.log10(2)).mean()), 4)}


def cross_validate(X: np.ndarray, y_mid: np.ndarray, y_lo: np.ndarray, y_hi: np.ndarray,
                   headcount: np.ndarray, lam: float, method: str,
                   X_eval: np.ndarray | None = None) -> dict:
    """Held-out metrics. Training folds use X; held-out rows are scored on X_eval (the
    inference-time features: headcount-implied size bucket) when given."""
    X_eval = X if X_eval is None else X_eval
    pred = np.zeros_like(y_mid)
    base = np.zeros_like(y_mid)
    for test in _folds(len(y_mid)):
        train = np.setdiff1d(np.arange(len(y_mid)), test)
        params = fit(X[train], y_mid[train], y_lo[train], y_hi[train], lam, method)
        pred[test] = _predict(params, X_eval[test])
        rpe = np.median(10 ** y_mid[train] / headcount[train])
        base[test] = np.log10(headcount[test] * rpe)
    return {"model": _metrics(pred, y_mid, y_lo, y_hi),
            "baseline": _metrics(base, y_mid, y_lo, y_hi)}


def train(rows: list[dict], as_of: date) -> dict:
    """Fit, cross-validate and return the JSON-able model document."""
    usable, feats, feats_eval = [], [], []
    for r in rows:
        f = features_from_row(r, as_of)
        if f is not None:
            usable.append(r)
            feats.append(f)
            feats_eval.append(features_from_row(r, as_of, listed_bucket=False))
    X = design(feats)
    X_eval = design(feats_eval)
    y_mid, y_lo, y_hi = targets(usable)
    hc = np.array([r["headcount"] for r in usable], float)
    trials = []
    for method in ("midpoint", "interval_em"):
        for lam in LAMBDAS:
            cv = cross_validate(X, y_mid, y_lo, y_hi, hc, lam, method, X_eval)
            listed = cross_validate(X, y_mid, y_lo, y_hi, hc, lam, method)["model"]
            trials.append({"method": method, "lambda": lam, **cv, "model_listed_bucket": listed})
    best = min(trials, key=lambda t: (t["model"]["median_abs_log10_error"],
                                      -t["model"]["band_hit_rate"]))
    params = fit(X, y_mid, y_lo, y_hi, best["lambda"], best["method"])
    w, b, mu, sd = params
    train_pred = _predict(params, X)
    rpe_all = float(np.median(10 ** y_mid / hc))
    bucket_mismatch = sum(1 for r in usable
                          if r.get("employee_count_range") != bucket_of(r["headcount"]))
    return {
        "version": MODEL_VERSION,
        "trained_on": as_of.isoformat(),
        "n_rows": len(usable),
        "target": "log10(Crustdata revenue band midpoint), interval-censored in "
                  "[log10 lower, log10 upper]",
        "method": best["method"], "lambda": best["lambda"],
        "features": list(FEATURES),
        "coef_standardized": [round(float(x), 6) for x in w],
        "intercept": round(b, 6),
        "feature_means": [round(float(x), 6) for x in mu],
        "feature_stds": [round(float(x), 6) for x in sd],
        "cv": {"folds": CV_FOLDS, "seed": CV_SEED, "model": best["model"],
               "model_definition": "held-out rows scored with the headcount-implied size "
                                   "bucket, as at inference",
               "model_listed_bucket": best["model_listed_bucket"],
               "baseline": best["baseline"],
               "baseline_definition": "revenue = headcount x median revenue-per-employee "
                                      "(band midpoint) of the training fold"},
        "cv_trials": trials,
        "train_fit": _metrics(train_pred, y_mid, y_lo, y_hi),
        "median_revenue_per_employee_usd": round(rpe_all, 2),
        "notes": [
            "Target is Crustdata's own third-party revenue band, not reported revenue.",
            "Search rows carry no web traffic, followers or role/region breakdown "
            "(not returned, or premium-billed), so those are not model features.",
            "Lambda and fit method were chosen by the same 5-fold CV that is reported "
            "(mildly optimistic).",
            "Crustdata's band tracks the listed employee_count_range bucket; "
            f"{bucket_mismatch} of {len(usable)} rows list a bucket other than the one their "
            "indexed headcount implies.",
        ],
    }


# ---- inference ------------------------------------------------------------------------

class RevenueModel:
    def __init__(self, doc: dict):
        self.doc = doc
        self.features = list(doc["features"])
        self.w = np.array(doc["coef_standardized"], float)
        self.b = float(doc["intercept"])
        self.mu = np.array(doc["feature_means"], float)
        self.sd = np.array(doc["feature_stds"], float)
        self.sd[self.sd == 0] = 1.0
        cv = doc.get("cv", {}).get("model", {})
        self.q80 = float(cv.get("q80_abs_log10_error", 0.5))
        self.cv = cv

    @classmethod
    def load(cls, path: Path | None = None) -> "RevenueModel | None":
        try:
            return cls(json.loads((path or MODEL_PATH).read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError):
            return None

    def predict_log10(self, feats: dict[str, float]) -> float:
        x = np.array([feats[k] for k in self.features], float)
        return float(((x - self.mu) / self.sd) @ self.w + self.b)

    def describe(self) -> str:
        d = self.doc
        kind = "interval-censored EM ridge" if d.get("method") == "interval_em" else "ridge"
        return (f"log-linear {kind} (lambda {d.get('lambda')}) on {d.get('n_rows')} Crustdata "
                f"Company Search companies, {d.get('version')} trained {d.get('trained_on')}")


def clamp_to_band(value: float, band: tuple[float, float] | None) -> tuple[float, bool]:
    """Clamp a USD value into [lower, upper]; returns (value, was_clamped)."""
    if not band:
        return value, False
    lo, hi = band
    if value < lo:
        return float(lo), True
    if value > hi:
        return float(hi), True
    return value, False


def _usd(v: float) -> str:
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(v) >= div:
            return f"${v / div:.1f}{suf}"
    return f"${v:,.0f}"


def estimate_revenue(signals: Signals, payroll: PayrollEstimate | None = None, *,
                     model: RevenueModel | None = None, as_of: date | None = None,
                     largest_country: str = "") -> RevenueEstimate:
    """Model estimate narrowed into the company's Crustdata band. Always an estimate."""
    est = RevenueEstimate(crustdata_band_usd=signals.revenue_band_usd)
    est.method.append("ESTIMATE, not reported revenue: model output narrowed into Crustdata's "
                      "third-party revenue band.")
    model = model or RevenueModel.load()
    feats = features_from_signals(signals, as_of, largest_country)
    band = signals.revenue_band_usd
    if band is not None:
        band = (max(float(band[0]), 0.0), float(band[1]))
        if band[1] <= 0:
            band = None
    if model is None or feats is None:
        est.method.append("No model or no headcount: falling back to the band midpoint."
                          if band else "No model, headcount or band: no revenue estimate.")
        if band:
            est.point_usd = (band[0] + band[1]) / 2
            est.low_usd, est.high_usd = band
        return _finish(est, signals, payroll)
    est.features = {k: round(v, 4) for k, v in feats.items()}
    est.model = model.describe()
    est.cv_band_hit_rate = model.cv.get("band_hit_rate")
    est.cv_median_abs_log_error = model.cv.get("median_abs_log10_error")
    log_raw = model.predict_log10(feats)
    raw = 10 ** log_raw
    est.model_raw_usd = round(raw, 0)
    point, clamped = clamp_to_band(raw, band)
    est.point_usd = round(point, 0)
    spread = 10 ** model.q80
    low, high = point / spread, point * spread
    if band:
        low, high = max(low, band[0]), min(high, band[1])
    est.low_usd, est.high_usd = round(low, 0), round(high, 0)
    est.method.append(f"Model raw {_usd(raw)} from {est.model}; held-out CV band hit rate "
                      f"{est.cv_band_hit_rate:.0%}, median |log10 error| "
                      f"{est.cv_median_abs_log_error:.2f} (x{10 ** est.cv_median_abs_log_error:.1f}).")
    if band:
        est.method.append(
            f"Clamped into the Crustdata band {_usd(band[0])}–{_usd(band[1])}"
            + (" (raw prediction was outside it)." if clamped else " (raw prediction inside it).")
        )
    else:
        est.method.append("No Crustdata band: the point is the unclamped model output.")
    est.method.append(f"Range = point x/÷ {spread:.2f} (CV 80th-percentile |log10 error| "
                      f"{model.q80:.2f})" + (", intersected with the band." if band else "."))
    return _finish(est, signals, payroll)


def _finish(est: RevenueEstimate, sig: Signals, payroll: PayrollEstimate | None) -> RevenueEstimate:
    if est.point_usd and sig.headcount_total:
        est.revenue_per_employee_usd = round(est.point_usd / sig.headcount_total, 0)
    if est.point_usd and payroll and payroll.loaded_cost_usd:
        ratio = est.point_usd / payroll.loaded_cost_usd
        est.method.append(f"Estimated revenue is {ratio:.2f}x the estimated loaded payroll "
                          f"({_usd(payroll.loaded_cost_usd)}/yr)"
                          + ("; below 1x means the company likely burns cash on payroll alone."
                             if ratio < 1 else "."))
    return est


def iter_rows(path: Path | None = None) -> Iterable[dict]:
    doc = json.loads((path or TRAINING_PATH).read_text(encoding="utf-8"))
    return doc.get("rows", doc) if isinstance(doc, dict) else doc
