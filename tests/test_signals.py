"""Investor signals (signals.py): offline, on recorded fixtures and synthetic records."""
from __future__ import annotations

import asyncio
from datetime import date

import httpx
import pytest

from proofroom import signals
from proofroom.crustdata import FIXTURE, Crustdata
from proofroom.models import Employment, TeamRow

KOAH, LINEAR, ATTIO = 3718859, 633791, 664000


def _fixture_run(name: str, cid: int, domain: str, **kw):
    async def go():
        async with Crustdata(FIXTURE, fixture=name) as c:
            return await signals.fetch_signals(c, cid, domain, **kw)
    return asyncio.run(go())


def _offline(tmp_path, record, **kw):
    """FIXTURE client over an empty fixture dir: every request is `fixture_missing`."""
    async def go():
        async with Crustdata(FIXTURE, fixture="none", fixtures_dir=tmp_path) as c:
            return await signals.fetch_signals(c, 1, "example-startup.test", record=record,
                                               logo=False, **kw)
    return asyncio.run(go())


@pytest.fixture(scope="module")
def koah():
    return _fixture_run("koah", KOAH, "koahlabs.com")


# ---- recorded fixtures --------------------------------------------------------------

def test_koah_headcount_and_growth(koah):
    assert koah.company == "Koah" and koah.headcount_total == 24
    m = koah.metrics
    assert m["headcount_total"].value == 24
    assert m["headcount_yoy_pct"].value == pytest.approx(166.67, abs=0.01)
    assert m["headcount_yoy_pct"].display == "+166.7%"
    assert "headcount.growth_percent.yoy" in m["headcount_yoy_pct"].source
    pts = koah.series["headcount"].points
    months = [p.date for p in pts]
    assert months == sorted(set(months)) and all(len(d) == 7 for d in months)
    assert pts[-1].value == 24
    assert m["engineering_share_pct"].value == pytest.approx(29.2, abs=0.1)
    assert any(k.startswith("headcount_") and k != "headcount" for k in koah.series)


def test_koah_traffic_followers_revenue(koah):
    web = koah.series["web_visitors"]
    assert len(web.points) >= 12 and web.unit == "visitors/month"
    assert koah.metrics["web_visitors_latest"].value == 17228
    assert "web_visitors_yoy_pct" in koah.metrics
    assert koah.metrics["followers_yoy_pct"].value == pytest.approx(733.7, abs=0.1)
    assert koah.revenue_band_usd == (0, 500000)
    assert koah.metrics["revenue_trend"].value == 0
    assert "revenue_low" in koah.series and "revenue_high" in koah.series


def test_koah_funding_labels_and_timing(koah):
    m = koah.metrics
    assert "indexed record (Crunchbase-derived)" in m["total_funding_usd"].display
    assert m["total_funding_usd"].value == 25_500_000
    # FIXTURE replays use the capture date (2026-10-31) as today.
    assert m["months_since_last_round"].value == pytest.approx(8.2, abs=0.05)
    assert m["round_cadence_months"].value == pytest.approx(5.6, abs=0.1)  # year-only pre-seed skipped
    assert m["num_rounds"].value == 3
    assert m["funding_per_employee_usd"].value == pytest.approx(25_500_000 / 24)


def test_koah_founders(koah):
    assert len(koah.founders) == 3
    by = {f.name: f for f in koah.founders}
    assert all(f.prior_employers for f in koah.founders)
    assert "Affirm" in by["Herrick Fang"].big_tech_or_scaleup
    assert "Google" in by["Mike Choi"].big_tech_or_scaleup
    assert by["Mike Choi"].education and by["Mike Choi"].years_experience > 5
    assert "Koah" not in by["Herrick Fang"].prior_employers


def test_koah_coverage_market_logo(koah):
    assert koah.coverage["headcount"] and koah.coverage["web_traffic"] and koah.coverage["funding"]
    assert koah.coverage["employee_reviews"] is False
    assert koah.metrics["public_listing"].value == 0  # ticker KOAH is a namesake
    mk = koah.market
    # 72 funded peers in 24 months: "medium" on the D25 scale (100+ = high)
    assert mk.crowding == "medium" and signals.CROWDING_MEDIUM <= mk.funded_peers_24m < signals.CROWDING_HIGH
    assert 0 < len(mk.peers) <= 8 and all(p.company_id != KOAH for p in mk.peers)
    assert mk.median_peer_headcount_yoy_pct is not None and mk.peer_count
    assert koah.logo_data_uri.startswith("data:image/jpeg;base64,")
    assert koah.credits_used == 0
    assert koah.hiring_openings == 7


def test_linear_secondary_split():
    s = _fixture_run("linear", LINEAR, "linear.app")
    m = s.metrics
    assert m["total_funding_usd"].value == pytest.approx(233.2e6)
    assert m["total_funding_primary_usd"].value == pytest.approx(134.2e6)
    assert m["num_rounds"].value == 4
    assert "series c" in m["last_round"].display
    assert s.hiring_openings is None  # zero indexed listings is not "no hiring"
    assert any("secondary" in x for x in s.limitations)


# ---- synthetic metric math --------------------------------------------------------

def _weekly(start_count: int, end_count: int, months: int) -> list[dict]:
    out = []
    for i in range(months + 1):
        y, mth = divmod(i, 12)
        v = start_count + (end_count - start_count) * i / months
        out.append({"date": f"{2024 + y}-{mth + 1:02d}-07", "employee_count": round(v) + 5})
        out.append({"date": f"{2024 + y}-{mth + 1:02d}-21", "employee_count": round(v)})
    return out


def _record(**groups):
    rec = {g: None for g in signals.ENRICH_FIELDS}
    rec["basic_info"] = {"name": "Example", "primary_domain": "example-startup.test",
                         "year_founded": 2022, "status": "active"}
    rec.update(groups)
    return rec


def test_declining_headcount_gives_negative_yoy(tmp_path):
    rec = _record(headcount={"total": 60, "timeseries": _weekly(100, 60, 18)})
    s = _offline(tmp_path, rec, today=date(2026, 1, 1), search=False, jobs=False)
    pts = s.series["headcount"].points
    assert pts[0].value == 100  # last weekly value of the month, not the first
    assert s.metrics["headcount_yoy_pct"].value < 0
    assert s.metrics["headcount_yoy_pct"].display.startswith("-")
    assert "computed" in s.metrics["headcount_yoy_pct"].source
    assert s.metrics["headcount_cagr"].value < 0


def test_cadence_and_months_since_last_round(tmp_path):
    ms = [{"round_type": "pre_seed", "date": "2020-01-01"},       # year precision: no gap
          {"round_type": "seed", "date": "2021-03-15", "amount_usd": 3e6},
          {"round_type": "series_a", "date": "2022-03-15", "amount_usd": 10e6},
          {"round_type": "series_b", "date": "2024-03-15", "amount_usd": 30e6}]
    rec = _record(funding={"total_investment_usd": 43e6, "milestones": ms})
    s = _offline(tmp_path, rec, today=date(2025, 3, 15), search=False, jobs=False)
    m = s.metrics
    assert m["round_cadence_months"].value == pytest.approx(18.0, abs=0.2)  # median(12, 24)
    assert m["months_since_last_round"].value == pytest.approx(12.0, abs=0.1)
    assert m["num_rounds"].value == 4
    assert "total_funding_primary_usd" not in m  # no secondary entries


def test_missing_groups_do_not_crash(tmp_path):
    s = _offline(tmp_path, {"basic_info": {"name": "Example"}}, today=date(2026, 1, 1))
    assert s.company == "Example"
    assert s.coverage["headcount"] is False and s.coverage["funding"] is False
    assert any("Company Enrich failed" in x for x in s.limitations)
    assert any("'headcount'" in x for x in s.limitations)
    assert s.market.crowding == "unknown" and not s.series and s.founders == []


def test_search_failure_sets_crowding_unknown(tmp_path):
    rec = _record(taxonomy={"categories": ["Widget Platforms", "Software"]})
    s = _offline(tmp_path, rec, today=date(2026, 1, 1))
    assert s.market.crowding == "unknown" and s.market.categories
    assert any("Company Search failed" in x for x in s.limitations)
    assert s.coverage["company_search"] is False


def test_merge_team_rows(tmp_path):
    row = TeamRow(name="Ada Example", person_id=7, source="person_search", past=[
        Employment(employer_name="Stripe", employer_id=99, title="Co-founder", start="2015-01",
                   end="2018-01", start_precision="month", current=False)])
    s = _offline(tmp_path, _record(), today=date(2026, 1, 1), search=False, jobs=False,
                 founders=[row])
    (f,) = s.founders
    assert f.prior_founder and f.big_tech_or_scaleup == ["Stripe"]
    assert f.years_experience == pytest.approx(11.0, abs=0.1)


# ---- heuristics -------------------------------------------------------------------

def test_legal_risk_classification():
    assert signals.classify_news("Koah sued over ad fraud claims", "Koah") == "legal_risk"
    assert signals.classify_news("Koah announces layoffs", "Koah") == "legal_risk"
    assert signals.classify_news("SEC probe widens", "") == "legal_risk"
    # Namesake or round-up titles that do not name the company are never attributed.
    assert signals.classify_news("Networks face lawsuit over linear TV", "Attio") == "other"
    assert signals.classify_news("Koah Raises $20.5M Series A", "Koah") == "funding"
    assert signals.classify_news("Koah launches publisher SDK", "Koah") == "product"
    assert signals.classify_news("Settlementsville weather", "") == "other"  # whole words only


def test_public_market_namesake_not_public():
    pub, why = signals.public_listing({"revenue": {"public_markets": {
        "stock_symbols": ["KOAH"], "ipo_date": None}}})
    assert pub is False and "namesake" in why
    pub, _ = signals.public_listing({"revenue": {"public_markets": {
        "stock_symbols": ["XYZ"], "ipo_date": "2021-05-01"}}})
    assert pub is True
    assert signals.public_listing({})[0] is False


@pytest.mark.parametrize("n,level", [(None, "unknown"), (0, "low"), (29, "low"), (30, "medium"),
                                     (99, "medium"), (100, "high"), (126, "high")])
def test_crowding_thresholds(n, level):
    assert signals.crowding_level(n) == level


def test_notable_employers_and_founder_titles():
    assert signals.notable_employers(["Google DeepMind", "Square Enix", "Meta Platforms",
                                      "Qualified (Acquired by Salesforce)", "Affirm"]) == \
        ["Google", "Affirm"]
    assert signals.notable_employers(["Square", "Meta"]) == ["Square/Block", "Meta"]
    assert signals.is_founder_title("Co-Founder & CTO")
    assert signals.is_founder_title("cofounder")
    assert not signals.is_founder_title("Founder Fellow")
    assert not signals.is_founder_title("Founding Engineer")


def test_monthly_and_change_helpers():
    pts = signals.monthly([{"date": "2025-01-05", "v": 1}, {"date": "2025-01-28", "v": 3},
                           {"date": "1970-01-01", "v": 9}, {"date": "2026-01-02", "v": 6}], "v")
    assert [(p.date, p.value) for p in pts] == [("2025-01", 3), ("2026-01", 6)]
    assert signals.change_pct(pts, 12) == pytest.approx(100.0)
    assert signals.cagr_pct(pts)[0] == pytest.approx(100.0)


def test_choose_niche():
    cands = ["A", "B", "C"]
    assert signals.choose_niche(cands, {"A": 500, "B": 50, "C": 5}, cands) == ["B", "A"]
    assert signals.choose_niche(["A"], {"A": 40}, ["A", "Artificial Intelligence (AI)"]) == \
        ["A", "Artificial Intelligence (AI)"]
    assert signals.choose_niche(["A", "B"], {"A": 3, "B": 7}, ["A", "B"]) == ["B"]
    assert signals.choose_niche(["A"], {}, ["A"]) == ["A"]


def test_news_dedup_and_epoch_date():
    rec = {"news": [{"article_title": "Koah Raises $5M", "article_url": "u1",
                     "article_publish_date": "1970-01-01"},
                    {"article_title": "Koah raises $5M", "article_url": "u2",
                     "article_publish_date": "2025-09-10"}]}
    (n,) = signals.news_items(rec, "Koah")
    assert n.date == "" and n.kind == "funding"


# ---- logo -------------------------------------------------------------------------

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100


def _logo(body: bytes, ctype: str):
    transport = httpx.MockTransport(lambda req: httpx.Response(
        200, content=body, headers={"content-type": ctype}))
    return asyncio.run(signals.download_logo("https://logo.test/x", transport=transport))


def test_logo_download_rules():
    assert _logo(JPEG, "binary/octet-stream") == (JPEG, "jpg")   # S3 generic type, sniffed
    assert _logo(b"\x89PNG\r\n\x1a\n" + b"0" * 10, "image/png")[1] == "png"
    with pytest.raises(ValueError):
        _logo(b"<html>no</html>", "text/html")
    with pytest.raises(ValueError):
        _logo(b"plain bytes", "application/octet-stream")
    with pytest.raises(ValueError):
        _logo(JPEG + b"0" * signals.LOGO_MAX_BYTES, "image/jpeg")


def test_strip_signals_drops_bulky_keys():
    rec = {"people": {"founders": [{"basic_profile": {"name": "A", "summary": "long"},
                                    "experience": {"employment_details": {"past": [
                                        {"employer_name": "X",
                                         "employer_linkedin_description": "long"}]}}}],
                      "decision_makers": [{"x": 1}]},
           "public_launches": {"launches": [{"name": "L", "num_upvotes": 3, "description": "d"}]}}
    out = signals.strip_signals(rec)
    f = out["people"]["founders"][0]
    assert f["basic_profile"] == {"name": "A"}
    assert f["experience"]["employment_details"]["past"][0] == {"employer_name": "X"}
    assert "decision_makers" not in out["people"]
    assert out["public_launches"]["launches"][0] == {"name": "L", "num_upvotes": 3}
