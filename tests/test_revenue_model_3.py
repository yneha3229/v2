"""Offline, fast tests for revenue model v3 (proofroom/revenue_model_3.py)."""
import math

import pytest

from proofroom import revenue_model_3 as m3


def test_clean_headcount_rescales_ramp_like_inflation():
    regions = {"Brazil": 6877, "São Paulo, Brazil": 1446, "United States": 2196,
               "New York, NY": 681, "India": 395, "Italy": 411}
    roles = {"Engineering": 1748, "Sales": 895}
    c = m3.clean_headcount(regions, roles, 3757, "USA", "corporate cards for businesses")
    # located = 6877 + 2196 + 395 + 411 = 9879; kept US + India (hub, smaller than HQ)
    assert c["dropped_countries"] == {"BRA": 6877.0, "ITA": 411.0}
    assert c["region_share"] == pytest.approx((2196 + 395) / 9879, abs=1e-4)
    assert c["clean"] == pytest.approx(3757 * (2196 + 395) / 9879, abs=0.2)
    assert c["clean"] < c["raw"] and any("rescaled" in n for n in c["notes"])


def test_clean_headcount_keeps_office_country_and_clean_company():
    regions = {"United States": 100, "Germany": 30}
    c = m3.clean_headcount(regions, {"Engineering": 120}, 130, "USA", "developer tools")
    assert c["clean"] == 130 and c["dropped_countries"] == {}
    # a large non-hub country is kept when the company lists an office there
    regions = {"United States": 100, "Philippines": 150}
    c2 = m3.clean_headcount(regions, {}, 250, "USA", "", offices={"PHL"})
    assert c2["clean"] == 250
    c3 = m3.clean_headcount(regions, {}, 250, "USA", "")
    assert c3["clean"] == pytest.approx(100.0)


def test_clean_headcount_drops_implausible_functions_unless_described():
    roles = {"Engineering": 800, "Education": 150, "Community and Social Services": 50}
    c = m3.clean_headcount({"United States": 1000}, roles, 1000, "USA", "GTM data platform")
    assert set(c["dropped_functions"]) == {"Education", "Community and Social Services"}
    assert c["clean"] == pytest.approx(800.0)
    edtech = m3.clean_headcount({"United States": 1000}, roles, 1000, "USA",
                                "online learning for students")
    assert "Education" not in edtech["dropped_functions"]
    assert edtech["clean"] == pytest.approx(950.0)


def test_clean_headcount_uses_min_not_product_of_filters():
    regions = {"United States": 50, "Brazil": 50}
    roles = {"Engineering": 50, "Education": 50}
    c = m3.clean_headcount(regions, roles, 100, "USA", "")
    assert c["clean"] == pytest.approx(50.0)     # min(0.5, 0.5), not 0.25


def test_investor_tier_counting():
    inv = ["Sequoia Capital", "Sequoia Capital India", "a16z", "Andreessen Horowitz",
           "Accel-KKR", "Some Angel", "GV", "Thrive Capital"]
    ms = [{"round_type": "series_b", "funding_date": "2024-05-01",
           "lead_investors": "Founders Fund"},
          {"round_type": "series_c", "funding_date": "2025-06-01", "lead_investors": "Acme VC"},
          {"round_type": "secondary_market", "funding_date": "2026-01-01",
           "lead_investors": "Accel"}]
    q = m3.investor_quality(inv, ms)
    assert q["top_tier"] == sorted(["Sequoia", "Andreessen Horowitz", "GV", "Thrive Capital",
                                    "Founders Fund", "Accel"])
    assert q["n_top_tier"] == 6
    assert q["last_lead"] == "Acme VC" and q["last_lead_tier"] == 1   # secondary ignored
    assert m3.top_tier_of("Accel-KKR") == "" and m3.top_tier_of("Benchmark Capital")
    assert m3.investor_quality([], [])["last_lead_tier"] == 0


def test_payroll_implied_math_and_loo():
    rev = [100e6, 200e6, 600e6]
    pay = [50e6, 100e6, 150e6]          # ratios 2, 2, 4
    assert m3.fit_k(rev, pay) == pytest.approx(2.0)
    assert m3.payroll_implied(30e6, 2.0) == pytest.approx(60e6)
    assert m3.payroll_implied(None, 2.0) is None
    assert m3.loo_k(rev, pay) == pytest.approx([3.0, 3.0, 2.0])
    assert m3.stage_of(150e6) == "late" and m3.stage_of(5e6) == "early"


def test_loaded_payroll_scales_with_clean_headcount_and_tier():
    clean = {"clean": 100.0, "kept_countries": ["USA"], "dropped_functions": {}}
    regions = {"United States": 100}
    roles = {"Engineering": 60, "Sales": 40}
    mkt = m3.loaded_payroll(clean, regions, roles, tier="market")
    up = m3.loaded_payroll(clean, regions, roles, tier="scaleup")
    assert mkt["loaded_usd"] == pytest.approx(mkt["base_usd"] * 1.3, rel=1e-6)
    assert up["loaded_usd"] > mkt["loaded_usd"]
    half = m3.loaded_payroll({**clean, "clean": 50.0}, regions, roles, tier="market")
    assert half["loaded_usd"] == pytest.approx(mkt["loaded_usd"] / 2, rel=1e-3)


def test_request_bodies_are_free_counts():
    from datetime import date
    b = m3.mention_bodies(42, date(2026, 10, 31))
    assert all(x["limit"] == 0 for x in b.values())
    assert b["mentions_12m"]["filters"]["conditions"][-1]["value"] == "2025-10-28"
    mk = m3.market_bodies("CRM", date(2026, 10, 31))
    assert mk["market_funded_24m"]["filters"]["conditions"][1]["value"] == "2024-10-01"


def test_model_and_features_load():
    model = m3.Model3.load()
    assert model is not None
    assert set(m3.NEW_FEATURES) <= set(model.features)
    assert len(model.w) == len(model.features) and all(math.isfinite(x) for x in model.w)
    import json
    doc = json.loads(m3.FEATURES_PATH.read_text(encoding="utf-8"))
    assert len(doc["training"]) >= 60 and "ramp" in doc["study"]
    f = m3.new_features(doc["study"]["ramp"])
    assert f["clean_share"] < 0.5           # Brazil namesakes removed
