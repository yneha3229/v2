"""D29 calibrated revenue: leave-one-out benchmark, early-stage guard, v2 low weight, band staleness."""
import math

from proofroom import calibration as cal

REFS = [cal.RefCompany("a.test", 100, 30e6), cal.RefCompany("b.test", 200, 80e6),
        cal.RefCompany("c.test", 400, 120e6), cal.RefCompany("x.test", 1000, 50e6, flagged=True)]


def test_benchmark_is_leave_one_out_and_skips_flagged():
    rpe, n = cal.benchmark_rpe(REFS, exclude="a.test")
    assert n == 2 and rpe == (400e3 + 300e3) / 2      # b and c only; x is flagged
    rpe_all, n_all = cal.benchmark_rpe(REFS)
    assert n_all == 3 and rpe_all == 300e3


def test_calibrated_blend_is_weighted_geometric_mean():
    c = cal.calibrate("new.test", 300, 100e6, 20e6, REFS, band=(10e6, 20e6))
    bench = 300 * 300e3
    expect = math.exp((0.60 * math.log(bench) + 0.25 * math.log(20e6)) / 0.85)
    assert c.applied and abs(c.point_usd - expect) < 1 and c.band_stale
    assert c.low_usd < c.point_usd < c.high_usd


def test_early_stage_keeps_v1():
    c = cal.calibrate("tiny.test", 7, 0, 450e3, REFS)
    assert not c.applied and c.point_usd == 450e3 and "early-stage" in c.notes[0]


def test_v2_used_only_if_it_beat_v1_and_with_low_weight():
    off = cal.calibrate("new.test", 300, 100e6, 20e6, REFS, v2_usd=40e6, v2_ok=False)
    assert "v2" not in off.components and any("excluded" in n for n in off.notes)
    on = cal.calibrate("new.test", 300, 100e6, 20e6, REFS, v2_usd=40e6, v2_ok=True)
    assert on.weights["v2"] < on.weights["v1"] < on.weights["benchmark"]
    assert abs(sum(on.weights.values()) - 1) < 1e-9


def test_summary_metrics():
    s = cal.summarize(cal.ratios({"a": 50, "b": 110, "c": 300}, {"a": 100, "b": 100, "c": 100}))
    assert s["n"] == 3 and s["within_2x"] == 2 / 3 and abs(s["median_abs_pct_error"] - 0.5) < 1e-9
    assert s["median_ratio"] == 1.1
