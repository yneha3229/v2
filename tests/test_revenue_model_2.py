"""Offline tests for revenue model 2 (social-post features on top of rev-1)."""
import asyncio
import json
import math
from datetime import date

import pytest

from proofroom import revenue_model as rm
from proofroom import revenue_model_2 as rm2
from proofroom.errors import CrustError
from proofroom.research_models import Signals

AS_OF = date(2026, 10, 31)


def post(day: str, text: str = "", reactions: int = 0, comments: int = 0, shares: int = 0,
         video: bool = False, kind: str = "original", url: str = "") -> dict:
    return {"share_url": url or f"https://example.test/{day}/{abs(hash(text)) % 10**6}",
            "text": text, "date_posted": f"{day}T10:00:00Z", "post_type": kind,
            "has_video": video, "content_types": [],
            "engagement": {"total_reactions": reactions, "total_comments": comments,
                           "num_shares": shares}}


def test_cadence_recency_and_engagement():
    posts = [post("2026-10-21", reactions=10, comments=2, shares=1),
             post("2026-10-11", reactions=4),
             post("2026-09-21", reactions=100, video=True)]
    f = rm2.extract_social_features(posts, AS_OF, total_posts=40)
    assert f["has_posts"] == 1.0 and f["n_posts"] == 3
    assert f["days_since_last_post"] == 10
    assert f["posts_per_30d"] == pytest.approx(3.0)          # 3 posts over a 30-day span
    assert f["median_engagement"] == 13 and f["mean_engagement"] == pytest.approx(39.0)
    assert f["log_median_engagement"] == pytest.approx(math.log10(14))
    assert f["video_share"] == pytest.approx(1 / 3)
    assert f["log_total_posts"] == pytest.approx(math.log10(41))


def test_cadence_uses_span_with_30_day_floor():
    posts = [post("2026-10-01"), post("2026-07-03")]           # 90-day span
    assert rm2.extract_social_features(posts, AS_OF)["posts_per_30d"] == pytest.approx(2 / 90 * 30)
    one = rm2.extract_social_features([post("2026-10-30")], AS_OF)
    assert one["posts_per_30d"] == pytest.approx(1.0)


def test_topic_shares_and_reaction_fallback():
    posts = [post("2026-10-20", "We're hiring! Join our team of engineers."),
             post("2026-10-19", "Introducing our new feature, now available in beta"),
             post("2026-10-18", "Excited to have raised our Series A from great investors"),
             post("2026-10-17", "Case study: how a customer cut costs. Join our webinar."),
             {"text": "New integration partnership", "date_posted": "2026-10-16",
              "engagement": {"reactions_by_type": {"LIKE": 3, "PRAISE": 2}}}]
    f = rm2.extract_social_features(posts, AS_OF)
    assert f["topic_hiring"] == pytest.approx(0.2)
    assert f["topic_launches"] == pytest.approx(0.2)
    assert f["topic_funding"] == pytest.approx(0.2)
    assert f["topic_customers"] == pytest.approx(0.2)
    assert f["topic_events"] == pytest.approx(0.2)
    assert f["topic_partnerships"] == pytest.approx(0.2)
    assert f["original_share"] == pytest.approx(0.8)
    assert sorted(rm2.post_engagement(p) for p in posts)[0] == 0
    assert rm2.post_engagement(posts[-1]) == 5


def test_no_posts_is_all_zero_with_indicator():
    f = rm2.extract_social_features([], AS_OF)
    assert f["has_posts"] == 0.0
    assert all(f[k] == 0.0 for k in rm2.SOCIAL_FEATURES)
    assert set(rm2.SOCIAL_FEATURES) <= set(f)


def test_duplicate_posts_counted_once():
    p = post("2026-10-20", "same", url="https://example.test/x")
    assert rm2.extract_social_features([p, dict(p)], AS_OF)["n_posts"] == 1


def test_posts_body_is_fixed():
    b = rm2.posts_body(3718859)
    assert b == rm2.posts_body(3718859)
    assert b["limit"] == 10 and b["filters"]["conditions"][0]["value"] == 3718859


def test_v1_features_reused_unchanged():
    assert rm2.FEATURES[:len(rm.FEATURES)] == tuple(rm.FEATURES)
    assert rm2.FEATURES[len(rm.FEATURES):] == rm2.SOCIAL_FEATURES
    row = {"headcount": 120, "headcount_growth_12m_pct": 20, "total_funding_usd": 3e7,
           "last_round_usd": 2e7, "last_fundraise_date": "2025-10-31", "year_founded": 2019,
           "largest_headcount_country": "USA", "hq": "San Francisco, California",
           "description": "AI platform for sales teams", "employee_count_range": "51-200"}
    social = {"features": rm2.extract_social_features([post("2026-10-01")], AS_OF)}
    mat = rm2.training_matrix([{**row, "crustdata_company_id": 1, "revenue_lower_usd": 1e6,
                                "revenue_upper_usd": 1e7}], {1: social}, AS_OF)
    v1 = rm.features_from_row(row, AS_OF)
    assert {k: mat["f_train"][0][k] for k in rm.FEATURES} == v1


def _synthetic_model(tmp_path):
    n = len(rm2.FEATURES)
    doc = {"version": "rev-2", "features": list(rm2.FEATURES),
           "coef_standardized": [0.0] * n, "intercept": 7.0,          # raw = $10M
           "feature_means": [0.0] * n, "feature_stds": [1.0] * n,
           "cv": {"model": {"median_abs_log10_error": 0.3, "q80_abs_log10_error": 0.7}}}
    p = tmp_path / "m.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def test_model_loads_from_json_and_clamps_into_band(tmp_path):
    model = rm2.RevenueModel2.load(_synthetic_model(tmp_path))
    assert model is not None and model.features == list(rm2.FEATURES)
    sig = Signals(company="X", domain="x.test", headcount_total=40,
                  revenue_band_usd=(1e6, 2.5e6), description="AI for teams")
    out = rm2.estimate_revenue_v2(sig, rm2.extract_social_features([], AS_OF), model=model,
                                  as_of=AS_OF)
    assert out["model_raw_usd"] == pytest.approx(1e7)
    assert out["point_usd"] == 2.5e6 and out["clamped"] is True
    assert 1e6 <= out["low_usd"] <= out["point_usd"] <= out["high_usd"] <= 2.5e6
    assert out["model_version"] == "rev-2" and out["label"] == "ESTIMATE"
    assert out["cv"]["median_abs_log10_error"] == 0.3
    free = rm2.estimate_revenue_v2(sig.model_copy(update={"revenue_band_usd": None}), {},
                                   model=model, as_of=AS_OF)
    assert free["point_usd"] == pytest.approx(1e7) and not free["clamped"]
    assert free["high_usd"] == pytest.approx(1e7 * 10 ** 0.3, rel=1e-6)


def test_missing_model_file_returns_none(tmp_path):
    assert rm2.RevenueModel2.load(tmp_path / "missing.json") is None


class _FakeClient:
    mode = "FIXTURE"

    def __init__(self, resp=None, err=None):
        self.resp, self.err, self.attempts, self.bodies = resp, err, [], []

    async def request(self, method, endpoint, body=None):
        self.bodies.append((method, endpoint, body))
        if self.err:
            raise self.err
        return self.resp


def test_social_features_for_success_and_error():
    resp = {"posts": [post("2026-10-21", "x" * 300, reactions=5)], "total_count": 12,
            "next_cursor": None}
    out = asyncio.run(rm2.social_features_for(_FakeClient(resp), 42, AS_OF))
    assert out["n_posts"] == 1 and out["total_count"] == 12 and out["error"] == ""
    assert len(out["snippets"][0]["text"]) == 200
    bad = _FakeClient(err=CrustError(403, "permission_error", "denied"))
    out = asyncio.run(rm2.social_features_for(bad, 42, AS_OF))
    assert out["error"] == "permission_error" and out["features"]["has_posts"] == 0.0


def test_posts_from_enrich_record_shape():
    rec = {"basic_info": {}, "social_posts": [post("2026-10-21")]}
    posts, total = rm2.posts_from_response(rec)
    assert len(posts) == 1 and total is None


def test_shipped_model_json_is_consistent():
    model = rm2.RevenueModel2.load()
    if model is None:
        pytest.skip("revenue_model_2.json not trained")
    assert model.features == list(rm2.FEATURES)
    assert len(model.w) == len(model.mu) == len(model.sd) == len(rm2.FEATURES)
