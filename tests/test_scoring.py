"""D24 investment signal: flag taxonomy, pillars, rating caps, sizing (SYNTHETIC data)."""
from datetime import date

from proofroom import scoring
from proofroom.models import CaseRecord, Finding, RunInput, TeamRow
from proofroom.research_models import FounderProfile, Market, Metric, NewsItem, Signals

TODAY = date(2026, 10, 31)


def case(findings=3, team_ok=True, **kw):
    fs = [Finding(claim_id=f"C{i}", disposition="supported", qualified=False,
                  basis=["company_statement"], sentence=f"S{i}.", evidence_ids=["E1"], as_of="",
                  correction_reason="", limitation="", question="") for i in range(findings)]
    base = dict(case_id="example-startup-test", run=1, status="DELIVERED", run_mode="FIXTURE",
                input=RunInput(domain="example-startup.test", input_mode="A", run_mode="FIXTURE"),
                reviewed="2026-10-31", g1={"status": "MATCHED", "name": "Example", "company_id": 9},
                findings=fs,
                team=[TeamRow(name="A", person_id=1, role_join=team_ok, listed_as_founder=True),
                      TeamRow(name="B", person_id=2, role_join=True, listed_as_founder=True)])
    base.update(kw)
    return CaseRecord(**base)


def sig(**metrics):
    s = Signals(company="Example", domain="example-startup.test", company_id=9, status="active",
                headcount_total=40, year_founded=2022,
                coverage={"headcount": True, "web_traffic": True, "funding": True},
                market=Market(category="AI", crowding="low", funded_peers_24m=2, peer_count=10,
                              median_peer_headcount_yoy_pct=20),
                founders=[FounderProfile(name="A", prior_founder=True, big_tech_or_scaleup=["Google"])])
    s.series["headcount"] = __import__("proofroom.research_models", fromlist=["Series"]).Series(
        key="headcount", label="Headcount", unit="people")
    for k, v in metrics.items():
        s.metrics[k] = Metric(key=k, label=k, value=v)
    return s


def test_strong_company_gets_invest_and_full_size():
    s = sig(headcount_yoy_pct=120, web_visitors_yoy_pct=80, followers_yoy_pct=150,
            months_since_last_round=6, num_rounds=3)
    fl, pl, rec = scoring.assess(case(), s, 200_000, TODAY)
    assert rec.rating == "INVEST" and rec.confidence in ("high", "medium")
    assert rec.suggested_usd > 0 and rec.suggested_usd <= 200_000
    rules = {f.rule for f in fl}
    assert {"G3 strong-growth", "G4 traffic-growth", "G5 recent-raise", "G6 notable-founders",
            "G7 beats-peers"} <= rules
    assert abs(sum(p.weight for p in pl) - 1.0) < 1e-9


def test_business_red_flags_cap_the_rating():
    s = sig(headcount_yoy_pct=-25, web_visitors_yoy_pct=-45, months_since_last_round=30)
    s.market.funded_peers_24m, s.market.crowding = 22, "high"
    fl, pl, rec = scoring.assess(case(), s, 100_000, TODAY)
    reds = {f.rule for f in fl if f.level == "red"}
    assert {"R1 headcount-decline", "R2 traffic-decline", "R3 crowded-market",
            "R4 stale-funding", "R5 lagging-peers"} <= reds
    assert rec.rating in ("HOLD", "AVOID") and rec.suggested_usd == 0


def test_integrity_problems_are_critical_and_force_avoid():
    s = sig(headcount_yoy_pct=150, months_since_last_round=3)
    s.news = [NewsItem(title="Example sued by former partner", url="https://n.test/1",
                       kind="legal_risk")]
    c = case(team_ok=False, findings=0, g1={"status": "MATCHED", "name": "Example"})
    c.findings = [Finding(claim_id="C1", disposition="conflicting", qualified=False,
                          basis=["company_statement"], sentence="x.", evidence_ids=["E1"],
                          as_of="", correction_reason="", limitation="", question="")]
    fl, pl, rec = scoring.assess(c, s, 100_000, TODAY)
    crit = {f.rule for f in fl if f.level == "critical"}
    assert {"C2 conflict", "C4 founder-no-role", "C5 legal-news"} <= crit
    assert rec.rating == "AVOID" and rec.suggested_usd == 0


def test_layoffs_are_red_not_critical_and_thin_team_rule():
    s = sig(headcount_yoy_pct=5)
    s.headcount_total, s.year_founded = 3, 2020
    s.news = [NewsItem(title="Example lays off staff; laid off 10", url="u", kind="legal_risk")]
    fl = scoring.flags(case(), s, TODAY)
    rules = {f.rule: f.level for f in fl}
    assert rules["R8 layoffs-news"] == "red" and rules["R6 thin-team"] == "red"
    assert "C5 legal-news" not in rules


def test_low_coverage_lowers_confidence_and_size():
    s = sig(headcount_yoy_pct=150, months_since_last_round=3)
    s.coverage = {"headcount": False, "web_traffic": False, "funding": True}
    s.series.clear(); s.founders = []; s.market.crowding = "unknown"
    rec = scoring.assess(case(findings=1), s, 100_000, TODAY)[2]
    assert rec.confidence == "low" and rec.rating != "INVEST"
    assert rec.suggested_usd <= 50_000


def test_every_rule_fired_is_documented_and_disclaimer_present():
    s = sig(headcount_yoy_pct=-40, months_since_last_round=40, revenue_trend=-1)
    s.market.naics = "524114"
    fl, _, rec = scoring.assess(case(), s, 100_000, TODAY)
    assert all(f.rule in scoring.RULES for f in fl)
    assert "not financial advice" in rec.disclaimer and rec.revisit_triggers
