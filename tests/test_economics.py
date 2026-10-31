"""Economics model (D26): offline and fast. No network; FIXTURE replays only."""
import asyncio
import json
import math
from datetime import date

import pytest

from proofroom import economics as e
from proofroom import revenue_model as rm
from proofroom.research_models import EmployeeSample, Market, Metric, Signals

FALLBACK = e.Benchmarks.load(e.DATA_DIR / "does-not-exist.json")


def _sig(**kw) -> Signals:
    base = dict(company="Synth", domain="synth.example", company_id=1, headcount_total=10.0)
    base.update(kw)
    return Signals(**base)


# ---- region dedupe ---------------------------------------------------------------------

def test_region_dedupe_nested_keys():
    regions = {"San Francisco Bay Area": 35, "San Francisco, CA": 26,
               "California, United States": 51, "Los Angeles Metropolitan Area": 9,
               "New York City Metropolitan Area": 26, "New York, NY": 14,
               "New York, United States": 24, "United States": 135,
               "Greater London": 12, "London Area, United Kingdom": 15,
               "England, United Kingdom": 29, "United Kingdom": 35, "India": 9, "Brazil": 20}
    tiers, notes = e.dedupe_regions(regions, 199)
    assert tiers["San Francisco Bay Area"] == 35           # max of the SF cluster, not 61
    assert tiers["New York City"] == 26                    # NYC cluster max; NY state ignored
    assert tiers["London"] == 15
    assert tiers["US Other"] == pytest.approx(135 - 35 - 26 - 9)
    assert tiers["UK Other"] == pytest.approx(35 - 15)
    assert tiers["Latin America"] == 20 and tiers["India"] == 9
    assert sum(tiers.values()) == pytest.approx(199)
    assert not notes


def test_region_dedupe_spreads_unplaced_to_rest_of_country():
    tiers, notes = e.dedupe_regions({"United States": 50, "San Francisco Bay Area": 30}, 100)
    assert sum(tiers.values()) == pytest.approx(100)
    assert tiers["San Francisco Bay Area"] == 30           # no metro premium for unplaced
    assert tiers["US Other"] == pytest.approx(70)
    assert "no listed region" in notes[0]


def test_region_dedupe_scales_down_overcounted():
    tiers, notes = e.dedupe_regions({"Brazil": 300, "United States": 100}, 200)
    assert sum(tiers.values()) == pytest.approx(200)
    assert "scaled" in notes[0]


def test_classify_region_levels():
    assert e.classify_region("United States")[0] == "country"
    assert e.classify_region("New York, United States")[0] == "state"
    assert e.classify_region("New York, NY")[2] == "New York City"
    assert e.classify_region("London Area, United Kingdom")[2] == "London"
    assert e.classify_region("Bangalore Urban")[2] == "Bangalore"


# ---- payroll math (synthetic) ----------------------------------------------------------

def test_payroll_math_synthetic():
    sig = _sig(headcount_total=10.0, metrics={"total_funding_usd": Metric(
        key="total_funding_usd", label="Total funding", value=12_000_000.0)})
    p = e.estimate_payroll(sig, regions={"United States": 10, "San Francisco Bay Area": 6},
                           roles={"Engineering": 5, "Sales": 5}, benchmarks=FALLBACK)
    eng_sf = FALLBACK.get("Engineering", "San Francisco Bay Area").annual_usd
    eng_us = FALLBACK.get("Engineering", "US Other").annual_usd
    sal_sf = FALLBACK.get("Sales", "San Francisco Bay Area").annual_usd
    sal_us = FALLBACK.get("Sales", "US Other").annual_usd
    expected = (6 * 0.5 * (eng_sf + sal_sf) + 4 * 0.5 * (eng_us + sal_us)) / 10
    assert p.avg_salary_usd == pytest.approx(expected, abs=1)
    assert p.annual_payroll_usd == pytest.approx(expected * 10, abs=10)
    assert p.loaded_cost_usd == pytest.approx(p.annual_payroll_usd * 1.3, abs=10)
    assert p.est_runway_months == pytest.approx(12e6 / (p.loaded_cost_usd / 12), abs=0.1)
    lo, hi = p.avg_salary_range_usd
    assert lo == pytest.approx(expected * 0.85, abs=1) and hi == pytest.approx(expected * 1.15, abs=1)
    assert any("ESTIMATE" in m for m in p.method)


def test_samples_adjust_blended_with_shrinkage():
    sig = _sig(headcount_total=10.0)
    bench = FALLBACK.get("Engineering", "US Other").annual_usd
    samples = [EmployeeSample(title="Engineer", role="Engineering", location="US Other",
                              est_salary_usd=bench * 2, method="switch-premium")] * 10
    p = e.estimate_payroll(sig, samples, regions={"United States": 10},
                           roles={"Engineering": 10}, benchmarks=FALLBACK)
    w = 10 / (10 + e.SAMPLE_SHRINK_K)
    assert p.avg_salary_usd == pytest.approx(bench * (1 + w), abs=1)


# ---- switch premium --------------------------------------------------------------------

def _person(title: str, loc: dict, past: str | None) -> dict:
    emp = {"current": [{"crustdata_company_id": 1, "name": "Synth", "title": title}],
           "past": ([{"crustdata_company_id": 99, "name": past, "title": "Engineer",
                      "end_date": "2024-01-01T00:00:00+00:00"}] if past else [])}
    return {"basic_profile": {"current_title": title, "location": loc},
            "experience": {"employment_details": emp}}


def test_switch_premium_applied_us_big_tech():
    bm = e.Benchmarks.load()      # real file when present, fallback otherwise
    s = e.sample_from_profile(_person("Software Engineer", {"city": "San Francisco",
                                                             "country": "United States"},
                                      "Google"), 1, bm)
    bench = bm.get("Engineering", "San Francisco Bay Area").annual_usd
    mult, tier = bm.employer_multiplier("Google", "San Francisco Bay Area")
    lo, hi, note = bm.premium_for("San Francisco Bay Area")
    assert tier == "big_tech" and mult > 1
    assert s.prior_salary_usd == pytest.approx(bench * mult, abs=1)
    assert s.est_salary_usd == pytest.approx(bench * mult * (lo + hi) / 2, abs=1)
    assert s.method.startswith("switch-premium") and "US" in note


def test_switch_premium_is_location_specific():
    bm = e.Benchmarks.load()
    us = bm.premium_for("US Other")
    india = bm.premium_for("Bangalore")
    uk = bm.premium_for("London")
    if not bm.is_fallback:
        assert 1.04 <= us[0] <= us[1] <= 1.08         # ADP job-changer raise
        assert india[0] >= 1.2                          # survey expectation
        assert "US" in uk[2] and "no London figure" in uk[2]


def test_no_prior_employer_uses_benchmark():
    s = e.sample_from_profile(_person("Account Executive", {"country": "India"}, None), 1,
                              FALLBACK)
    assert s.role == "Sales" and s.location == "India"
    assert s.est_salary_usd == FALLBACK.get("Sales", "India").annual_usd
    assert s.method == "role-location benchmark"


def test_benchmark_fallback_and_file_fill_rule(tmp_path):
    assert FALLBACK.is_fallback
    doc = {"benchmarks": [{"role": "Support", "location": "San Francisco Bay Area",
                           "annual_usd": 100000, "source": "x"}],
           "location_index": [{"location": "London", "multiplier_vs_sf": 0.5}],
           "switch_premium": {"low": 0.05, "high": 0.07}}
    f = tmp_path / "b.json"
    f.write_text(json.dumps(doc))
    bm = e.Benchmarks.load(f)
    assert not bm.is_fallback
    assert bm.get("Customer Success & Support", "London").annual_usd == 50000
    assert bm.get("Customer Success & Support", "Latin America").source.startswith("built-in")
    assert bm.switch_premium == pytest.approx((1.05, 1.07))


# ---- revenue ---------------------------------------------------------------------------

def _tiny_model(intercept: float) -> rm.RevenueModel:
    n = len(rm.FEATURES)
    return rm.RevenueModel({"version": "t", "trained_on": "2026-10-31", "n_rows": 1,
                            "method": "midpoint", "lambda": 1, "features": list(rm.FEATURES),
                            "coef_standardized": [0.0] * n, "intercept": intercept,
                            "feature_means": [0.0] * n, "feature_stds": [1.0] * n,
                            "cv": {"model": {"band_hit_rate": 0.3, "median_abs_log10_error": 0.3,
                                             "q80_abs_log10_error": 0.6}}})


def test_revenue_clamped_into_band():
    sig = _sig(headcount_total=100.0, revenue_band_usd=(10e6, 20e6))
    r = rm.estimate_revenue(sig, model=_tiny_model(8.0), as_of=date(2026, 10, 31))  # raw $100M
    assert r.model_raw_usd == pytest.approx(1e8, rel=1e-6)
    assert r.point_usd == 20e6
    assert r.low_usd == pytest.approx(20e6 / 10 ** 0.3, rel=1e-3) and r.high_usd == 20e6
    assert r.revenue_per_employee_usd == 200_000
    assert "ESTIMATE" in r.method[0]
    inside = rm.estimate_revenue(sig, model=_tiny_model(math.log10(15e6)))
    assert inside.point_usd == pytest.approx(15e6, rel=1e-6)


def test_stale_bucket_band_is_floor_only():
    sig = _sig(headcount_total=300.0, revenue_band_usd=(10e6, 20e6))
    r = rm.estimate_revenue(sig, model=_tiny_model(8.0), listed_bucket="51-200")
    assert r.point_usd == pytest.approx(1e8, rel=1e-6)
    assert any("floor only" in m for m in r.method)
    band, note = rm.effective_band((10e6, 20e6), "1001-5000", 300)
    assert band == (0.0, 20e6) and "cap only" in note


def test_model_loads_from_json():
    m = rm.RevenueModel.load()
    assert m is not None
    doc = json.loads(rm.MODEL_PATH.read_text())
    assert doc["features"] == list(rm.FEATURES)
    assert len(doc["coef_standardized"]) == len(rm.FEATURES)
    for k in ("band_hit_rate", "median_abs_log10_error"):
        assert k in doc["cv"]["model"] and k in doc["cv"]["baseline"]
    assert doc["n_rows"] >= 100 and doc["version"] and doc["trained_on"]
    feats = rm.make_features(headcount=100, growth_yoy_pct=50, total_funding_usd=5e7,
                             last_round_usd=2e7, months_since_round=12, year_founded=2019,
                             largest_country="USA", hq="San Francisco, CA",
                             description="AI platform for developers", as_of=date(2026, 10, 31))
    assert 1e5 < 10 ** m.predict_log10(feats) < 1e10


def test_training_rows_have_no_contact_fields():
    rows = list(rm.iter_rows())
    assert rows and all("contact_email" not in r and "phone_number" not in r for r in rows)


# ---- customers -------------------------------------------------------------------------

def test_customer_rules_b2b_sales_led():
    sig = _sig(description="Ramp is a financial operations platform for businesses: corporate "
                           "cards, expense management and bill payments for finance teams.",
               role_mix={"Sales": 14.0, "Engineering": 40.0},
               market=Market(categories=["FinTech", "Payments"]))
    samples = [EmployeeSample(title="Account Executive", prior_employer="Brex"),
               EmployeeSample(title="Senior Account Executive", prior_employer="Brex")]
    cp = e.infer_customers(sig, samples)
    assert cp.business_model == "B2B"
    assert "Finance teams (CFOs, controllers)" in cp.target_customers
    assert "Corporate cards and spend management" in cp.use_cases
    assert cp.talent_sources[0] == "Brex (2)"
    assert any("Sales-led" in x for x in cp.evidence)


def test_customer_rules_consumer_and_marketplace():
    c = e.infer_customers(_sig(description="A mobile app for consumers to track fitness."))
    assert c.business_model == "B2C" and "Consumers" in c.target_customers
    m = e.infer_customers(_sig(description="A marketplace that connects buyers with sellers."))
    assert m.business_model == "marketplace"
    u = e.infer_customers(_sig(description=""))
    assert u.business_model == "unknown"


def test_data_quality_flags():
    flags = e.data_quality_flags({"Brazil": 900, "United States": 300}, {"Engineering": 100},
                                 400, "BRA", "New York, New York, United States")
    assert len(flags) == 2
    assert not e.data_quality_flags({"United States": 10}, {"Education": 1, "Engineering": 9},
                                    10, "USA", "San Francisco, California, United States")


# ---- FIXTURE replay --------------------------------------------------------------------

def test_fixture_koah_reproduces_numbers():
    sig, eco = asyncio.run(e.replay("koah", 3718859, "koahlabs.com"))
    p, r = eco.payroll, eco.revenue
    assert p.headcount == 24 and len(p.samples) == 15
    assert sum(p.by_location.values()) == pytest.approx(24)
    assert p.by_location["San Francisco Bay Area"] == 10
    assert r.crustdata_band_usd == (0.0, 500000.0)
    assert r.model_raw_usd == pytest.approx(539_725, rel=0.01)
    assert r.point_usd == r.model_raw_usd               # stale 2-10 bucket: band is a floor
    if not e.Benchmarks.load().is_fallback:
        assert p.avg_salary_usd == pytest.approx(130_069, rel=0.01)
        assert p.loaded_cost_usd == pytest.approx(4_058_144, rel=0.01)
    assert eco.customers.business_model == "B2B"
    assert "Advertisers, brands and publishers" in eco.customers.target_customers
