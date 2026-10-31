"""Revenue-model bake-off: every family fits synthetic data, Huber resists an outlier, Tobit
respects intervals, guardrails clip and flag, linear explanations are exactly additive."""
import math
from datetime import date
from types import SimpleNamespace

import numpy as np
import pytest

from proofroom import revenue_model as rm
from proofroom import revenue_models_alt as A

FI = {k: i for i, k in enumerate(rm.FEATURES)}


def synth(n=90, seed=0, noise=0.1):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, len(rm.FEATURES)))
    lh = rng.uniform(1.0, 3.5, n)
    X[:, FI["log_headcount"]] = lh
    X[:, FI["log_size_bucket"]] = [math.log10(rm._BUCKET_MID[rm.bucket_of(10 ** v)]) for v in lh]
    for k in A.CATEGORY_ORDER:
        X[:, FI[k]] = rng.random(n) < 0.3
    y = 5.0 + 0.9 * lh + 0.3 * X[:, FI["hc_growth_log"]] + rng.normal(0, noise, n)
    return X, y


@pytest.mark.parametrize("name", list(A.FAMILIES) + ["stack"])
def test_every_family_fits_and_predicts(name):
    X, y = synth()
    m = A.fit_family(name, X, X, y, y - 0.15, y + 0.15, np.zeros(len(y), bool))
    p = m.predict(X)
    assert p.shape == y.shape and np.all(np.isfinite(p))
    assert np.median(np.abs(p - y)) < (0.6 if name in ("baseline", "segment") else 0.35)


def test_huber_is_robust_to_an_outlier():
    X, y = synth(noise=0.02)
    y_bad = y.copy()
    i = int(np.argmax(X[:, FI["hc_growth_log"]]))      # high-leverage row
    y_bad[i] += 4.0
    clean = A.fit_ridge(X, y, lam=0.1)
    ridge = A.fit_ridge(X, y_bad, lam=0.1)
    huber = A.fit_huber(X, y_bad, lam=0.1)
    others = np.arange(len(y)) != i
    err = lambda m: np.median(np.abs(m.predict(X)[others] - clean.predict(X)[others]))  # noqa: E731
    assert err(huber) < err(ridge) / 3
    assert huber.extra["n_downweighted"] >= 1


def test_tobit_respects_intervals():
    X, y = synth(noise=0.05)
    lo, hi = np.floor(y * 2) / 2, np.floor(y * 2) / 2 + 0.5     # coarse half-dex bands
    lo_open = np.zeros(len(y), bool)
    lo_open[:5] = True                                            # left-censored rows
    t = A.fit_tobit(X, (lo + hi) / 2, lo, hi, lo_open, lam=0.1)
    p = t.predict(X)
    hit = np.mean((p >= np.where(lo_open, -np.inf, lo) - 1e-9) & (p <= hi + 1e-9))
    assert hit >= 0.8
    assert np.median(np.abs(p - y)) < 0.12            # recovers the latent value, not just the band
    assert t.extra["sigma"] < 0.3
    ey, var = A.tobit_estep(np.array([0.0, 5.0, -3.0]), 1.0, np.array([-np.inf, 1.0, 1.0]),
                            np.array([2.0, 2.0, 2.0]))
    assert np.all(ey <= 2.0) and ey[1] >= 1.0 and ey[2] >= 1.0 and np.all(var >= 0)


def test_guardrails_clip_and_flag():
    ok = A.apply_guardrails(30e6, 100, (10e6, 50e6), listed_bucket="51-200")
    assert not ok["clipped"] and ok["value_usd"] == 30e6 and ok["band_trusted"]
    cap = A.apply_guardrails(1e9, 100, None)                      # $10M per employee
    assert cap["value_usd"] == 100 * A.RPE_MAX_USD and cap["clipped"] and cap["flags"]
    floor = A.apply_guardrails(1e5, 100, None)                    # $1K per employee
    assert floor["value_usd"] == 100 * A.RPE_MIN_USD and "raised" in floor["flags"][0]
    trusted = A.apply_guardrails(3e6, 100, (10e6, 20e6), listed_bucket="51-200")
    assert trusted["value_usd"] == 10e6 and "band floor" in trusted["flags"][0]
    stale = A.apply_guardrails(9e6, 400, (10e6, 20e6), listed_bucket="51-200")
    assert stale["value_usd"] == 9e6 and not stale["band_trusted"]   # stale band: no floor
    over = A.apply_guardrails(500e6, 400, (1e6, 2e6), listed_bucket="201-500")
    assert over["value_usd"] == 15 * 2e6 and "band top" in over["flags"][0]
    scaled = A.apply_guardrails(500e6, 400, (1e6, 2e6), listed_bucket="51-200")
    assert scaled["value_usd"] == pytest.approx(15 * 2e6 * 350 / 125)
    ns = A.apply_guardrails(1e5, 1000, None, namesake=True)
    assert ns["value_usd"] == 1e5 and not ns["clipped"]           # inflated count: no floor


def test_linear_explanations_sum_to_prediction():
    X, y = synth()
    for m in (A.fit_ridge(X, y), A.fit_huber(X, y), A.fit_tobit(X, y, y - .2, y + .2)):
        for x in X[:5]:
            c = m.contributions(x)
            assert set(c) == set(rm.FEATURES)
            assert abs(m.b + sum(c.values()) - float(m.predict(x[None, :])[0])) < 1e-9
        back = A.Linear.from_doc(m.to_doc())
        assert np.allclose(back.predict(X), m.predict(X), atol=1e-6)


def _sig(hc=300, band=(10e6, 20e6), funding=150e6):
    metric = lambda v: SimpleNamespace(value=v)  # noqa: E731
    return SimpleNamespace(
        headcount_total=hc, revenue_band_usd=band, year_founded=2019,
        hq="San Francisco, California, United States", description="developer platform for teams",
        region_mix={"United States": 80.0},
        metrics={"headcount_yoy_pct": metric(40.0), "total_funding_usd": metric(funding),
                 "last_round": metric(50e6), "months_since_last_round": metric(12.0)})


def test_predict_alt_is_deterministic_and_bounded():
    model = A.AltModel.load()
    assert model is not None
    eco = SimpleNamespace(limitations=[], revenue=SimpleNamespace(method=[]))
    a = A.predict_alt(_sig(), eco, model=model, as_of=date(2026, 10, 31))
    b = A.predict_alt(_sig(), eco, model=model, as_of=date(2026, 10, 31))
    assert a == b and a["label"] == "ESTIMATE" and len(a["drivers"]) == 4
    assert 300 * A.RPE_MIN_USD <= a["point_usd"] <= 300 * A.RPE_MAX_USD
    assert "benchmark" in a["components"] and not a["early_stage"]
    tiny = A.predict_alt(_sig(hc=8, band=(0, 5e5), funding=2e6), eco, model=model,
                         as_of=date(2026, 10, 31))
    assert tiny["early_stage"] and "benchmark" not in tiny["components"]
