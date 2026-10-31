"""Calibrated revenue estimate (D29): model v1 + a reported-revenue benchmark (+ v2, low weight).

Why: model v1 learns Crustdata's revenue bands, which lag reality for fast-growing
venture-backed companies (Linear's band is $10-20M; Linear reports $100M+ ARR). A
benchmark built from *reported* revenue per employee of comparable companies corrects
that bias. To keep the test honest, every company is scored leave-one-out: its own
reported figure is never part of the benchmark used to estimate it.

Estimators compared:
- band:      midpoint of Crustdata's revenue band
- v1:        the regression (proofroom.revenue_model), Crustdata-band trained
- benchmark: headcount x median reported revenue per employee of the reference set
- v2:        v1 features + social posts (proofroom.revenue_model_2), when available
- ensemble:  weighted geometric mean of benchmark, v1 and (low weight) v2

Reference set: companies with a reported figure whose headcount is NOT flagged as
inflated by namesake profiles (common-word names such as Clay or Ramp mix in other
companies' staff, which would corrupt revenue per employee). The benchmark applies only
to venture-backed companies past the early stage (>= 50 staff and >= $20M primary
capital); smaller companies keep the v1 estimate.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass, field

WEIGHTS = {"benchmark": 0.60, "v1": 0.25, "v2": 0.15}   # v2 deliberately low (user, 13:15)
MIN_STAFF, MIN_CAPITAL_USD = 50, 20e6


@dataclass
class RefCompany:
    domain: str
    headcount: float
    reported_usd: float
    flagged: bool = False          # headcount inflated by namesake profiles
    reliability: str = ""

    @property
    def rev_per_employee(self) -> float:
        return self.reported_usd / self.headcount


@dataclass
class Calibrated:
    domain: str
    applied: bool
    point_usd: float | None
    low_usd: float | None = None
    high_usd: float | None = None
    components: dict[str, float] = field(default_factory=dict)   # estimator -> USD
    weights: dict[str, float] = field(default_factory=dict)
    benchmark_rev_per_employee: float | None = None
    n_reference: int = 0
    band_usd: tuple[float, float] | None = None
    band_stale: bool = False
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def benchmark_rpe(refs: list[RefCompany], exclude: str = "") -> tuple[float | None, int]:
    """Median reported revenue per employee over unflagged references, minus `exclude`."""
    vals = [r.rev_per_employee for r in refs if not r.flagged and r.domain != exclude]
    return (statistics.median(vals), len(vals)) if vals else (None, 0)


def _geo_blend(parts: dict[str, float], weights: dict[str, float]) -> tuple[float, dict[str, float]]:
    use = {k: v for k, v in parts.items() if v and v > 0 and weights.get(k, 0) > 0}
    total = sum(weights[k] for k in use)
    w = {k: weights[k] / total for k in use}
    return math.exp(sum(w[k] * math.log(use[k]) for k in use)), w


def calibrate(domain: str, headcount: float | None, primary_capital_usd: float | None,
              v1_usd: float | None, refs: list[RefCompany], *, v2_usd: float | None = None,
              band: tuple[float, float] | None = None, v2_ok: bool = False,
              weights: dict[str, float] | None = None) -> Calibrated:
    """One company's calibrated estimate. `v2_ok` is True only if model 2 beat v1 in CV."""
    weights = dict(weights or WEIGHTS)
    out = Calibrated(domain=domain, applied=False, point_usd=v1_usd, band_usd=band)
    if v1_usd:
        out.components["v1"] = v1_usd
    if v2_usd and v2_ok:
        out.components["v2"] = v2_usd
    elif v2_usd:
        out.notes.append("model 2 (social posts) excluded: it did not beat v1 in cross-validation")
    early = (headcount or 0) < MIN_STAFF or (primary_capital_usd or 0) < MIN_CAPITAL_USD
    rpe, n = benchmark_rpe(refs, exclude=domain)
    out.benchmark_rev_per_employee, out.n_reference = rpe, n
    if early or not rpe or not headcount:
        out.notes.append("early-stage company (<50 staff or <$20M primary capital): the "
                         "scaleup revenue-per-employee benchmark does not apply; v1 kept")
        if "v2" in out.components and v1_usd:
            out.point_usd, out.weights = _geo_blend(out.components, {"v1": 0.85, "v2": 0.15})
        return out
    out.components["benchmark"] = headcount * rpe
    out.point_usd, out.weights = _geo_blend(out.components, weights)
    out.applied = True
    lo, hi = min(out.components.values()), max(out.components.values())
    out.low_usd, out.high_usd = lo * 0.8, hi * 1.25
    if band and band[1] and out.point_usd > band[1]:
        out.band_stale = True
        out.notes.append(f"estimate is above Crustdata's band (${band[1] / 1e6:,.1f}M top): the "
                         "band is treated as stale (it tracks a self-reported size bucket)")
    out.notes.append(f"benchmark: {n} reference companies, median reported revenue per "
                     f"employee ${rpe / 1e3:,.0f}K (leave-one-out)")
    return out


# ---- evaluation ---------------------------------------------------------------------

def ratios(est: dict[str, float | None], truth: dict[str, float]) -> dict[str, float]:
    """estimate / reported, per company with both."""
    return {d: e / truth[d] for d, e in est.items() if e and d in truth and truth[d]}


def summarize(r: dict[str, float]) -> dict[str, float | int]:
    """Accuracy of one estimator from its estimate/reported ratios."""
    if not r:
        return {"n": 0}
    err = [abs(x - 1) for x in r.values()]
    return {"n": len(r),
            "median_abs_pct_error": statistics.median(err),
            "mean_abs_pct_error": sum(err) / len(err),
            "within_30pct": sum(e <= 0.30 for e in err) / len(r),
            "within_2x": sum(0.5 <= x <= 2.0 for x in r.values()) / len(r),
            "median_ratio": statistics.median(r.values())}   # <1 means biased low
