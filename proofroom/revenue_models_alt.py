"""Revenue-model bake-off (D30 candidate): alternative model families, guardrails and
explanations. Offline, deterministic, numpy only. Model v1 (`proofroom.revenue_model`) is
reused READ-ONLY for its feature extraction, design matrix, targets and CV folds.

Families (all trained on the 126 Crustdata band-labelled rows, `training_set.json`):
- ridge:    v1's midpoint ridge (log10 band midpoint ~ 16 standardized features)
- huber:    the same linear model fitted by IRLS with the Huber loss (robust to outliers)
- tobit:    interval-censored Gaussian regression fitted by EM: each row's target is its
            band [log10 lower, log10 upper] (a lower bound of $0 is left-censored), not the
            midpoint; the M-step is the same ridge
- knn:      k nearest neighbours in standardized feature space; averages the neighbours'
            log10 revenue per employee, then multiplies by the company's headcount
- gbm:      gradient-boosted depth-2 regression trees on log10 revenue per employee
- segment:  median revenue per employee by size bucket x primary category (fallbacks:
            bucket, then global)
- stack:    equal-weight average (in log10) of the six above; no weights are tuned

Hyperparameters (lambda, k, number of trees) are chosen by an INNER 4-fold CV on each
outer training fold, so the outer 5-fold CV (v1's folds, seed 7) never tunes on its test
rows. `ridge_v1` keeps v1's lambda 30, which v1 picked on the same outer CV (optimistic).

Every value here is an ESTIMATE. Crustdata's bands follow a stale self-reported LinkedIn
size bucket and sit well below reported revenue for fast-growing scaleups, so a model that
fits the bands well is biased low; `predict_alt` corrects that with a reported-revenue
factor and then applies `apply_guardrails`.
"""
from __future__ import annotations

import json
import math
import re
import statistics
from datetime import date
from pathlib import Path
from typing import Any, Callable

import numpy as np

from proofroom import revenue_model as rm

ALT_PATH = rm.DATA_DIR / "revenue_models_alt.json"
ALT_VERSION = "rev-alt-1"
LOG2 = math.log10(2.0)
INNER_FOLDS, INNER_SEED = 4, 11
HUBER_C = 1.345

# Guardrail defaults. Public SaaS / fintech leaders report roughly $300K-$1M revenue per
# employee (e.g. large public SaaS companies cluster around $300K-$500K; the most efficient
# software/fintech names approach $1M). $20K/employee is below any functioning venture-backed
# software business that sells anything; $1.5M is above all but a handful of outliers.
RPE_MIN_USD = 20_000.0
RPE_MAX_USD = 1_500_000.0
MAX_OVER_BAND_TOP = 15.0       # cap: <= 15x the band top (scaled for a stale size bucket)
EARLY_STAFF, EARLY_CAPITAL_USD = 50, 20e6   # same early-stage gate as calibration.py

CATEGORY_ORDER = ("cat_fintech", "cat_devtools", "cat_ai", "cat_consumer", "cat_b2b")
_FI = {k: i for i, k in enumerate(rm.FEATURES)}


# ---- data ------------------------------------------------------------------------------

def load_training(path: Path | None = None) -> dict[str, Any]:
    """Design matrices and targets exactly as v1 builds them (listed size bucket for
    training, headcount-implied bucket for held-out scoring)."""
    doc = json.loads((path or rm.TRAINING_PATH).read_text(encoding="utf-8"))
    as_of = date.fromisoformat(str(doc.get("pulled_on") or "2026-10-31")[:10])
    rows, feats, feats_eval = [], [], []
    for r in doc["rows"]:
        f = rm.features_from_row(r, as_of)
        if f is not None:
            rows.append(r)
            feats.append(f)
            feats_eval.append(rm.features_from_row(r, as_of, listed_bucket=False))
    y_mid, y_lo, y_hi = rm.targets(rows)
    lo_open = np.array([float(r["revenue_lower_usd"]) <= 0 for r in rows])
    return {"rows": rows, "as_of": as_of, "X": rm.design(feats), "X_eval": rm.design(feats_eval),
            "y_mid": y_mid, "y_lo": y_lo, "y_hi": y_hi, "lo_open": lo_open,
            "hc": np.array([float(r["headcount"]) for r in rows])}


# ---- shared helpers ----------------------------------------------------------------------

def _standardize(X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd = np.where(sd == 0, 1.0, sd)
    return (X - mu) / sd, mu, sd


def _wridge(Z: np.ndarray, y: np.ndarray, lam: float, wt: np.ndarray | None = None
            ) -> tuple[np.ndarray, float]:
    """Weighted ridge on standardized Z with an unpenalized intercept."""
    wt = np.ones(len(y)) if wt is None else wt
    sw = wt.sum()
    zbar, ybar = (wt @ Z) / sw, float(wt @ y / sw)
    Zc = Z - zbar
    A = Zc.T @ (Zc * wt[:, None]) + lam * np.eye(Z.shape[1])
    w = np.linalg.solve(A, Zc.T @ (wt * (y - ybar)))
    return w, ybar - float(zbar @ w)


def _log_hc(X: np.ndarray) -> np.ndarray:
    return X[:, _FI["log_headcount"]]


_erf = np.vectorize(math.erf, otypes=[float])


def _Phi(x: np.ndarray) -> np.ndarray:
    return np.where(np.isneginf(x), 0.0, np.where(np.isposinf(x), 1.0,
                    0.5 * (1.0 + _erf(np.nan_to_num(x, posinf=40, neginf=-40) / math.sqrt(2)))))


def _phi(x: np.ndarray) -> np.ndarray:
    xf = np.nan_to_num(x, posinf=40, neginf=-40)
    return np.where(np.isinf(x), 0.0, np.exp(-0.5 * xf * xf) / math.sqrt(2 * math.pi))


class Linear:
    """log10 revenue = ((x - mu) / sd) . w + b (standardized coefficients)."""
    kind = "linear"

    def __init__(self, w, b, mu, sd, name: str = "linear", **extra):
        self.w, self.b, self.mu, self.sd = (np.asarray(w, float), float(b),
                                            np.asarray(mu, float), np.asarray(sd, float))
        self.name, self.extra = name, extra

    def predict(self, X: np.ndarray) -> np.ndarray:
        return ((X - self.mu) / self.sd) @ self.w + self.b

    def contributions(self, x: np.ndarray) -> dict[str, float]:
        """Per-feature contribution in log10 units; sum + intercept = prediction."""
        z = (np.asarray(x, float) - self.mu) / self.sd
        return {k: float(c) for k, c in zip(rm.FEATURES, z * self.w)}

    def to_doc(self) -> dict:
        return {"kind": "linear", "name": self.name,
                "coef_standardized": [round(float(v), 8) for v in self.w],
                "intercept": round(self.b, 8),
                "feature_means": [round(float(v), 8) for v in self.mu],
                "feature_stds": [round(float(v), 8) for v in self.sd], **self.extra}

    @classmethod
    def from_doc(cls, d: dict) -> "Linear":
        return cls(d["coef_standardized"], d["intercept"], d["feature_means"],
                   d["feature_stds"], d.get("name", "linear"))


# ---- model families ------------------------------------------------------------------------

def fit_ridge(X, y_mid, y_lo=None, y_hi=None, lo_open=None, *, lam: float = 30.0) -> Linear:
    Z, mu, sd = _standardize(X)
    w, b = _wridge(Z, y_mid, lam)
    return Linear(w, b, mu, sd, "ridge", lam=lam)


def fit_huber(X, y_mid, y_lo=None, y_hi=None, lo_open=None, *, lam: float = 30.0,
              c: float = HUBER_C, iters: int = 100) -> Linear:
    """Huber regression by IRLS: weights min(1, c / |r / s|), s = 1.4826 * MAD(r)."""
    Z, mu, sd = _standardize(X)
    w, b = _wridge(Z, y_mid, lam)
    wt = np.ones(len(y_mid))
    for _ in range(iters):
        r = y_mid - (Z @ w + b)
        s = max(1.4826 * float(np.median(np.abs(r - np.median(r)))), 1e-3)
        u = np.abs(r) / s
        wt_new = np.where(u <= c, 1.0, c / np.maximum(u, 1e-12))
        w_new, b_new = _wridge(Z, y_mid, lam, wt_new)
        done = np.max(np.abs(w_new - w)) < 1e-8 and abs(b_new - b) < 1e-8
        w, b, wt = w_new, b_new, wt_new
        if done:
            break
    return Linear(w, b, mu, sd, "huber", lam=lam, c=c,
                  n_downweighted=int((wt < 1).sum()))


def tobit_estep(m: np.ndarray, s: float, lo: np.ndarray, hi: np.ndarray
                ) -> tuple[np.ndarray, np.ndarray]:
    """E[y] and Var[y] of N(m, s^2) truncated to [lo, hi] (lo may be -inf)."""
    a, b = (lo - m) / s, (hi - m) / s
    Zp = _Phi(b) - _Phi(a)
    pa, pb = _phi(a), _phi(b)
    apa = np.where(np.isinf(a), 0.0, np.nan_to_num(a) * pa)
    bpb = np.where(np.isinf(b), 0.0, np.nan_to_num(b) * pb)
    ok = Zp > 1e-10
    Zs = np.where(ok, Zp, 1.0)
    ey = np.where(ok, m + s * (pa - pb) / Zs, np.clip(m, lo, hi))
    var = np.where(ok, s * s * (1 + (apa - bpb) / Zs - ((pa - pb) / Zs) ** 2), 0.0)
    return np.clip(ey, lo, hi), np.maximum(var, 0.0)


def fit_tobit(X, y_mid, y_lo, y_hi, lo_open=None, *, lam: float = 30.0, iters: int = 200
              ) -> Linear:
    """Interval-censored Gaussian (Tobit-style) regression by EM. Each row only says
    'log10 revenue is inside [lo, hi]'; a $0 lower bound is left-censored (-inf)."""
    lo = np.where(lo_open, -np.inf, y_lo) if lo_open is not None else np.asarray(y_lo, float)
    hi = np.asarray(y_hi, float)
    Z, mu, sd = _standardize(X)
    w, b = _wridge(Z, y_mid, lam)
    s = max(float(np.std(y_mid - (Z @ w + b))), 0.05)
    for _ in range(iters):
        ey, var = tobit_estep(Z @ w + b, s, lo, hi)
        w_new, b_new = _wridge(Z, ey, lam)
        s_new = max(math.sqrt(float(np.mean((ey - (Z @ w_new + b_new)) ** 2 + var))), 0.02)
        done = (np.max(np.abs(w_new - w)) < 1e-7 and abs(b_new - b) < 1e-7
                and abs(s_new - s) < 1e-7)
        w, b, s = w_new, b_new, s_new
        if done:
            break
    return Linear(w, b, mu, sd, "tobit", lam=lam, sigma=round(s, 6))


class KNN:
    kind = "knn"

    def __init__(self, Ztr, t, mu, sd, k):
        self.Ztr, self.t, self.mu, self.sd, self.k = Ztr, t, mu, sd, k

    def predict(self, X: np.ndarray) -> np.ndarray:
        Z = (X - self.mu) / self.sd
        d = ((Z[:, None, :] - self.Ztr[None, :, :]) ** 2).sum(-1)
        nn = np.argsort(d, axis=1, kind="stable")[:, :self.k]
        return _log_hc(X) + self.t[nn].mean(axis=1)


def fit_knn(X, y_mid, y_lo=None, y_hi=None, lo_open=None, *, k: int = 8) -> KNN:
    Z, mu, sd = _standardize(X)
    return KNN(Z, y_mid - _log_hc(X), mu, sd, min(k, len(y_mid)))


def _best_split(X, r, idx, min_leaf):
    best = (math.inf, -1, 0.0)
    n = len(idx)
    if n < 2 * min_leaf:
        return best
    tot, tot2 = r[idx].sum(), (r[idx] ** 2).sum()
    for j in range(X.shape[1]):
        order = idx[np.argsort(X[idx, j], kind="stable")]
        xs, rs = X[order, j], r[order]
        cs = np.cumsum(rs)
        i = np.arange(min_leaf, n - min_leaf + 1)
        valid = xs[i - 1] < xs[np.minimum(i, n - 1)]
        if not valid.any():
            continue
        left = cs[i - 1]
        sse = -(left ** 2 / i + (tot - left) ** 2 / (n - i))   # + const (tot2)
        sse = np.where(valid, sse, math.inf)
        m = int(np.argmin(sse))
        if sse[m] + tot2 < best[0]:
            best = (float(sse[m] + tot2), j, float((xs[i[m] - 1] + xs[i[m]]) / 2))
    return best


def _grow(X, r, idx, depth, min_leaf):
    if depth == 0:
        return float(r[idx].mean())
    _sse, j, thr = _best_split(X, r, idx, min_leaf)
    if j < 0:
        return float(r[idx].mean())
    L, R = idx[X[idx, j] <= thr], idx[X[idx, j] > thr]
    return (j, thr, _grow(X, r, L, depth - 1, min_leaf), _grow(X, r, R, depth - 1, min_leaf))


def _tree_predict(node, X):
    if not isinstance(node, tuple):
        return np.full(len(X), node)
    j, thr, left, right = node
    out = np.empty(len(X))
    m = X[:, j] <= thr
    out[m] = _tree_predict(left, X[m]) if m.any() else []
    out[~m] = _tree_predict(right, X[~m]) if (~m).any() else []
    return out


class GBM:
    kind = "gbm"

    def __init__(self, f0, trees, lr):
        self.f0, self.trees, self.lr = f0, trees, lr

    def predict(self, X: np.ndarray) -> np.ndarray:
        f = np.full(len(X), self.f0)
        for t in self.trees:
            f += self.lr * _tree_predict(t, X)
        return _log_hc(X) + f


def fit_gbm(X, y_mid, y_lo=None, y_hi=None, lo_open=None, *, n_trees: int = 100,
            lr: float = 0.1, depth: int = 2, min_leaf: int = 5) -> GBM:
    """Least-squares gradient boosting of depth-2 trees on log10 revenue per employee."""
    t = y_mid - _log_hc(X)
    f0 = float(t.mean())
    f = np.full(len(t), f0)
    idx = np.arange(len(t))
    trees = []
    for _ in range(n_trees):
        tree = _grow(X, t - f, idx, depth, min_leaf)
        trees.append(tree)
        f += lr * _tree_predict(tree, X)
    return GBM(f0, trees, lr)


def primary_category(x: np.ndarray) -> str:
    for k in CATEGORY_ORDER:
        if x[_FI[k]] > 0.5:
            return k[4:]
    return "other"


class Segment:
    kind = "segment"

    def __init__(self, cells, buckets, glob):
        self.cells, self.buckets, self.glob = cells, buckets, glob

    @staticmethod
    def key(x):
        return round(float(x[_FI["log_size_bucket"]]), 3), primary_category(x)

    def predict(self, X: np.ndarray) -> np.ndarray:
        out = []
        for x in X:
            b, c = self.key(x)
            out.append(self.cells.get((b, c), self.buckets.get(b, self.glob)))
        return _log_hc(X) + np.array(out)


def fit_segment(X, y_mid, y_lo=None, y_hi=None, lo_open=None, *, min_cell: int = 5) -> Segment:
    t = y_mid - _log_hc(X)
    groups: dict = {}
    bgroups: dict = {}
    for x, v in zip(X, t):
        b, c = Segment.key(x)
        groups.setdefault((b, c), []).append(v)
        bgroups.setdefault(b, []).append(v)
    cells = {k: float(np.median(v)) for k, v in groups.items() if len(v) >= min_cell}
    buckets = {k: float(np.median(v)) for k, v in bgroups.items() if len(v) >= min_cell}
    return Segment(cells, buckets, float(np.median(t)))


class Baseline:
    kind = "baseline"

    def __init__(self, t):
        self.t = t

    def predict(self, X):
        return _log_hc(X) + self.t


def fit_baseline(X, y_mid, *_a, **_k) -> Baseline:
    """v1's baseline: headcount x median revenue per employee of the training rows."""
    return Baseline(float(np.log10(np.median(10 ** y_mid / 10 ** _log_hc(X)))))


class Stack:
    kind = "stack"

    def __init__(self, members):
        self.members = members

    def predict(self, X):
        return np.mean([m.predict(X) for m in self.members], axis=0)


# name -> (fit function, hyperparameter grid or None for fixed defaults)
FAMILIES: dict[str, tuple[Callable, dict[str, tuple] | None]] = {
    "baseline": (fit_baseline, None),
    "ridge_v1": (lambda *a, **k: fit_ridge(*a, lam=30.0), None),
    "ridge": (fit_ridge, {"lam": rm.LAMBDAS}),
    "huber": (fit_huber, {"lam": rm.LAMBDAS}),
    "tobit": (fit_tobit, {"lam": rm.LAMBDAS}),
    "knn": (fit_knn, {"k": (3, 5, 8, 12, 20, 30)}),
    "gbm": (fit_gbm, {"n_trees": (25, 50, 100, 200)}),
    "segment": (fit_segment, None),
}
STACK_MEMBERS = ("ridge", "huber", "tobit", "knn", "gbm", "segment")


# ---- cross-validation --------------------------------------------------------------------

def _score(pred, y_mid):
    return float(np.median(np.abs(pred - y_mid)))


def _tune(fit, grid, X, Xe, y_mid, y_lo, y_hi, lo_open) -> dict:
    """Inner CV on the given (training) rows only."""
    if not grid:
        return {}
    (name, values), = grid.items()
    best, best_v = math.inf, values[0]
    folds = rm._folds(len(y_mid), INNER_FOLDS, INNER_SEED)
    for v in values:
        pred = np.zeros_like(y_mid)
        for te in folds:
            tr = np.setdiff1d(np.arange(len(y_mid)), te)
            m = fit(X[tr], y_mid[tr], y_lo[tr], y_hi[tr], lo_open[tr], **{name: v})
            pred[te] = m.predict(Xe[te])
        s = _score(pred, y_mid)
        if s < best - 1e-12:
            best, best_v = s, v
    return {name: best_v}


def fit_family(name: str, X, Xe, y_mid, y_lo, y_hi, lo_open, hp: dict | None = None):
    """Fit one family on these rows; hyperparameters by inner CV unless `hp` is given."""
    if name == "stack":
        return Stack([fit_family(m, X, Xe, y_mid, y_lo, y_hi, lo_open) for m in STACK_MEMBERS])
    fit, grid = FAMILIES[name]
    hp = hp if hp is not None else _tune(fit, grid, X, Xe, y_mid, y_lo, y_hi, lo_open)
    model = fit(X, y_mid, y_lo, y_hi, lo_open, **hp)
    model.hp = hp
    return model


def metrics(pred, y_mid, y_lo, y_hi) -> dict:
    m = rm._metrics(pred, y_mid, y_lo, y_hi)
    err = pred - y_mid
    m["max_over_x"] = round(float(10 ** err.max()), 2)
    m["max_under_x"] = round(float(10 ** -err.min()), 2)
    return m


def cross_validate(D: dict, name: str) -> dict:
    X, Xe, y_mid, y_lo, y_hi, lo_open = (D[k] for k in ("X", "X_eval", "y_mid", "y_lo",
                                                         "y_hi", "lo_open"))
    pred = np.zeros_like(y_mid)
    hps = []
    for te in rm._folds(len(y_mid)):
        tr = np.setdiff1d(np.arange(len(y_mid)), te)
        m = fit_family(name, X[tr], Xe[tr], y_mid[tr], y_lo[tr], y_hi[tr], lo_open[tr])
        hps.append(getattr(m, "hp", {}))
        pred[te] = m.predict(Xe[te])
    return {"model": name, **metrics(pred, y_mid, y_lo, y_hi), "fold_hparams": hps,
            "pred": pred}


# ---- guardrails ----------------------------------------------------------------------------

def _bucket_mid(b: str) -> float | None:
    return rm._BUCKET_MID.get(b)


def apply_guardrails(estimate: float, headcount: float | None,
                     band: tuple[float, float] | None = None, *, listed_bucket: str = "",
                     band_trusted: bool | None = None, namesake: bool = False,
                     rpe_min: float = RPE_MIN_USD, rpe_max: float = RPE_MAX_USD,
                     max_over_band_top: float = MAX_OVER_BAND_TOP) -> dict:
    """Clip an estimate to sane bounds and flag every clip.

    1. Band floor: when the band is trusted (listed size bucket == the bucket implied by
       headcount, and no namesake flag), never go below its lower bound.
    2. Band cap: never above `max_over_band_top` x the band top, scaled up by
       (implied bucket midpoint / listed bucket midpoint) when the listed bucket is
       smaller than the company now is (a stale band lags growth; it does not cap it).
    3. Revenue per employee in [rpe_min, rpe_max] (hard bounds, applied last). With a
       namesake-inflated headcount the per-employee FLOOR is skipped (the count is too
       high, so a low per-head figure is expected).
    """
    v = float(estimate)
    flags: list[str] = []
    implied = rm.bucket_of(headcount) if headcount else ""
    if band_trusted is None:
        band_trusted = bool(band and listed_bucket and listed_bucket == implied and not namesake)
    if band and band[1] and band[1] > 0:
        lo, hi = max(float(band[0]), 0.0), float(band[1])
        if band_trusted and lo > 0 and v < lo:
            flags.append(f"raised to the trusted band floor ${lo:,.0f} (was ${v:,.0f})")
            v = lo
        scale = 1.0
        lm, im = _bucket_mid(listed_bucket), _bucket_mid(implied)
        if lm and im and im > lm:
            scale = im / lm
        cap = max_over_band_top * hi * scale
        if v > cap:
            flags.append(f"capped at {max_over_band_top:g}x band top"
                         + (f" x{scale:.1f} stale-bucket scale" if scale > 1 else "")
                         + f" = ${cap:,.0f} (was ${v:,.0f})")
            v = cap
    if headcount and headcount > 0:
        lo_r, hi_r = headcount * rpe_min, headcount * rpe_max
        if v > hi_r:
            flags.append(f"capped at ${rpe_max:,.0f}/employee x {headcount:,.0f} = "
                         f"${hi_r:,.0f} (was ${v:,.0f})")
            v = hi_r
        elif v < lo_r and not namesake:
            flags.append(f"raised to ${rpe_min:,.0f}/employee x {headcount:,.0f} = "
                         f"${lo_r:,.0f} (was ${v:,.0f})")
            v = lo_r
    return {"value_usd": v, "original_usd": float(estimate), "clipped": bool(flags),
            "flags": flags, "band_trusted": band_trusted, "implied_bucket": implied}


# ---- explanation helpers -------------------------------------------------------------------

def top_drivers(contrib: dict[str, float], n: int = 4) -> list[tuple[str, float]]:
    return sorted(contrib.items(), key=lambda kv: -abs(kv[1]))[:n]


def listed_bucket_from_economics(economics: Any) -> str:
    """Recover basic_info.employee_count_range from v1's method notes (stale-band rule)."""
    for line in getattr(getattr(economics, "revenue", None), "method", []) or []:
        m = re.search(r"listed size bucket (\S+) is", line)
        if m:
            return m.group(1)
    return ""


def namesake_flag(economics: Any) -> bool:
    return any("namesake" in str(x).lower() for x in getattr(economics, "limitations", []) or [])


def _metric(signals: Any, k: str) -> float | None:
    m = getattr(signals, "metrics", {}) or {}
    return m[k].value if k in m and m[k].value is not None else None


def reason_line(d: dict) -> str:
    """One plain-English line from the diagnostics dict built by `diagnostics`."""
    parts: list[str] = []
    ratio = d.get("ratio_to_reported")
    if ratio is None:
        head = "No reported revenue to compare"
    elif ratio < 0.77:
        head = f"Underestimated ({ratio:.2f}x reported)"
    elif ratio > 1.3:
        head = f"Overestimated ({ratio:.2f}x reported)"
    else:
        head = f"Close ({ratio:.2f}x reported)"
    rep_rpe, bench = d.get("reported_rpe_usd"), d.get("benchmark_rpe_usd")
    if rep_rpe and bench:
        if rep_rpe > 1.3 * bench:
            why = ("typical of usage-priced infrastructure" if d.get("category") == "devtools"
                   else "typical of interchange/float fintech revenue"
                   if d.get("category") == "fintech" else "unusually efficient")
            parts.append(f"high revenue per employee (${rep_rpe / 1e3:,.0f}K reported vs "
                         f"${bench / 1e3:,.0f}K benchmark), {why}")
        elif rep_rpe < bench / 1.3:
            parts.append(f"low revenue per employee (${rep_rpe / 1e3:,.0f}K reported vs "
                         f"${bench / 1e3:,.0f}K benchmark)")
    if d.get("namesake"):
        parts.append(f"headcount {d['headcount']:,.0f} is inflated by namesake profiles")
    if d.get("band_stale"):
        parts.append(f"band is stale (listed {d['listed_bucket']}, actual "
                     f"{d['headcount']:,.0f})")
    if d.get("early_stage"):
        parts.append("early-stage: no reported-revenue correction; model and band only")
    g = d.get("headcount_yoy_pct")
    if g is not None and g > 60:
        parts.append(f"fast headcount growth ({g:+.0f}% yoy) suggests revenue ahead of the band")
    elif g is not None and g < -5 and not d.get("namesake"):
        parts.append(f"shrinking headcount ({g:+.0f}% yoy)")
    if d.get("guardrail_flags"):
        parts.append("guardrail fired: " + d["guardrail_flags"][0].split(" (was")[0])
    return head + (": " + "; ".join(parts) if parts else "") + "."


# ---- inference -----------------------------------------------------------------------------

class AltModel:
    def __init__(self, doc: dict):
        self.doc = doc
        self.linear = Linear.from_doc(doc["model"])
        self.bias = float(doc["reported_bias_factor"])
        self.bench_rpe = float(doc["benchmark_rpe_usd"])
        self.w_bench = float(doc["weights"]["benchmark"])
        g = doc.get("guardrails", {})
        self.g = {"rpe_min": g.get("rpe_min_usd", RPE_MIN_USD),
                  "rpe_max": g.get("rpe_max_usd", RPE_MAX_USD),
                  "max_over_band_top": g.get("max_over_band_top", MAX_OVER_BAND_TOP)}

    @classmethod
    def load(cls, path: Path | None = None) -> "AltModel | None":
        try:
            return cls(json.loads((path or ALT_PATH).read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError):
            return None


def combine(raw_usd: float, headcount: float, early: bool, bias: float, bench_rpe: float,
            w_bench: float) -> tuple[float, dict[str, float]]:
    """Recommended point before guardrails: geometric blend of the bias-corrected band
    model and the reported revenue-per-employee benchmark (scaleups only)."""
    if early or not headcount:
        return raw_usd, {"model_raw": raw_usd}
    corrected = raw_usd * bias
    bench = headcount * bench_rpe
    point = 10 ** ((1 - w_bench) * math.log10(corrected) + w_bench * math.log10(bench))
    return point, {"model_raw": raw_usd, "model_bias_corrected": corrected, "benchmark": bench}


def predict_alt(signals: Any, economics: Any = None, *, model: AltModel | None = None,
                as_of: date | None = None, largest_country: str = "",
                listed_bucket: str = "") -> dict:
    """Recommended alternative revenue ESTIMATE (inference only, offline, deterministic
    for a fixed `as_of`). Returns point/low/high, components, guardrail flags, the top
    linear drivers and a one-line reason."""
    model = model or AltModel.load()
    out: dict[str, Any] = {"version": ALT_VERSION, "point_usd": None, "label": "ESTIMATE",
                           "flags": [], "drivers": [], "components": {}}
    if model is None:
        out["flags"].append("revenue_models_alt.json not found")
        return out
    feats = rm.features_from_signals(signals, as_of or date.today(), largest_country)
    if feats is None:
        out["flags"].append("no headcount: no estimate")
        return out
    x = np.array([feats[k] for k in rm.FEATURES], float)
    contrib = model.linear.contributions(x)
    log_raw = model.linear.b + sum(contrib.values())
    hc = float(signals.headcount_total)
    prim = _metric(signals, "total_funding_primary_usd") or _metric(signals, "total_funding_usd") or 0
    early = hc < EARLY_STAFF or prim < EARLY_CAPITAL_USD
    point, comps = combine(10 ** log_raw, hc, early, model.bias, model.bench_rpe, model.w_bench)
    listed = listed_bucket or listed_bucket_from_economics(economics)
    namesake = namesake_flag(economics)
    band = signals.revenue_band_usd
    g = apply_guardrails(point, hc, band, listed_bucket=listed, namesake=namesake, **model.g)
    spread = 10 ** float(model.doc.get("spread_log10", 0.3))
    out.update({
        "point_usd": round(g["value_usd"], 0),
        "low_usd": round(g["value_usd"] / spread, 0), "high_usd": round(g["value_usd"] * spread, 0),
        "components": {k: round(v, 0) for k, v in comps.items()},
        "early_stage": early, "namesake": namesake, "listed_bucket": listed,
        "band_usd": band, "band_trusted": g["band_trusted"], "flags": g["flags"],
        "drivers": [{"feature": k, "log10": round(v, 4), "factor": round(10 ** v, 3)}
                    for k, v in top_drivers(contrib)],
        "intercept_log10": round(model.linear.b, 4),
        "revenue_per_employee_usd": round(g["value_usd"] / hc, 0),
        "method": model.doc.get("method", ""),
    })
    out["reason"] = reason_line({
        "ratio_to_reported": None, "namesake": namesake, "headcount": hc,
        "band_stale": bool(listed and listed != rm.bucket_of(hc)), "listed_bucket": listed,
        "early_stage": early, "headcount_yoy_pct": _metric(signals, "headcount_yoy_pct"),
        "guardrail_flags": g["flags"]})
    return out
