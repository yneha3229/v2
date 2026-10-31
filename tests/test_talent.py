"""Talent signals (D31): school tiers, founder filter, staff counts, Team bonus."""
import asyncio
from types import SimpleNamespace as NS

from proofroom import scoring, talent
from proofroom.errors import CrustError
from proofroom.research_models import Flag, Pillar


def test_classify_school_tiers_and_non_degree():
    assert talent.classify_school("Indian Institute of Technology, Bombay", "BTech") == ("india_elite", "IIT")
    assert talent.classify_school("Harvard University", "A.B.") == ("global_elite", "Harvard")
    assert talent.classify_school("Harvard Beijing Academy", "Citation") is None
    assert talent.classify_school("Stanford University Graduate School of Business", "Auditor") is None
    assert talent.classify_school("University of Colorado Boulder", "BBA") is None
    assert talent.classify_school("Y Combinator", "S15") is None


def test_home_market_flag():
    fs = [{"name": "A", "schools": [{"school": "Indian Institute of Technology, Bombay", "degree": "BTech"}]},
          {"name": "B", "schools": [{"school": "Stanford University", "degree": "MS"}]}]
    hits, elite, listed = talent.founder_schools(fs, "IND")
    assert (elite, listed) == (2, 2)
    assert {h.person: h.home_market for h in hits} == {"A": True, "B": False}
    hits, _, _ = talent.founder_schools(fs, "USA")
    assert {h.person: h.home_market for h in hits} == {"A": False, "B": True}


def _f(name, title, since, prior=0):
    return NS(name=name, title=title, since=since, prior_employers=["x"] * prior)


def test_credible_founders_drops_namesake_noise():
    rows = [_f("Eric", "Co-Founder, Co-CEO", "2019-03", 9),
            _f("Reece", "Executive Assistant to Co-Founder/Co-CEO", "2025-12", 4),
            _f("adita", "Founder", ""), _f("", "Founder", "2019"),
            _f("Late", "Co-founder", "2026-09"), _f("Eric", "Co-Founder", "2019-03", 1)]
    out = talent.credible_founders(rows, 2019)
    assert [f.name for f in out] == ["Eric"] and len(out[0].prior_employers) == 9


class FakeClient:
    def __init__(self, totals):
        self.totals, self.calls = totals, []

    async def request(self, method, endpoint, body):
        self.calls.append(body)
        conds = body["filters"]["conditions"]
        if len(conds) == 1:
            return {"total_count": self.totals["all"]}
        extra = conds[1]
        field = extra.get("field") or extra["conditions"][0]["field"]
        if field == talent.PAST_EMPLOYER_FIELD:
            raise CrustError(400, "invalid_request", "unsupported field")
        return {"total_count": self.totals["edu"], "profiles": [{}]}


def test_staff_counts_and_graceful_failure():
    t = asyncio.run(talent.staff_counts(FakeClient({"all": 10, "edu": 2}), 1, talent.Talent()))
    assert t.indexed_staff == 10 and set(t.alumni.values()) == {2}
    assert t.ex_big_tech is None and any("unavailable" in n for n in t.notes)
    assert all(b["limit"] == 1 for b in FakeClient({"all": 1, "edu": 0}).calls or [{"limit": 1}])


def test_team_bonus_and_apply_talent():
    hit = talent.SchoolHit("Aaryan", "Indian Institute of Technology, Bombay", "BTech", "india_elite", "IIT", True)
    t = talent.Talent(founder_schools=[hit], founders_with_elite=1, founders_total=1, indexed_staff=6,
                      alumni={"IIT": 5})
    assert talent.team_bonus(t)[0] == 14
    other = talent.Talent(founder_schools=[talent.SchoolHit("B", "Stanford University", "MS", "global_elite",
                                                            "Stanford", False)], indexed_staff=100, alumni={"x": 5})
    assert talent.team_bonus(other)[0] == 6
    assert talent.team_bonus(None) == (0.0, "")
    pl = [Pillar(name="Team", score=90, weight=0.25, reasons=[])]
    fl: list[Flag] = []
    scoring.apply_talent(fl, pl, t)
    assert pl[0].score == 100 and fl[0].rule == "G9 elite-founder"
    assert "G9 elite-founder" in scoring.RULES


def test_staff_history_flags_interns_and_prestige():
    resp = {"profiles": [{"basic_profile": {"name": "A"}, "experience": {"employment_details": {
        "current": [{"company_id": 7, "title": "CEO"}],
        "past": [{"title": "Quantitative Strategist", "company_name": "Quadeye", "start_date": "2024-05-01T00:00:00"},
                 {"title": "Software Intern", "company_name": "Samsung R&D Institute India - Bangalore",
                  "start_date": "2023-05-01"},
                 {"title": "Analyst", "company_name": "Local Co", "start_date": "2025-01-01"},
                 {"title": "x", "company_name": ""}]}}}]}
    [p] = talent.staff_history(resp, 7)
    assert p.current_title == "CEO" and [r.company for r in p.past][0] == "Local Co"
    assert {r.company: (r.prestige, r.intern) for r in p.past}["Quadeye"] == ("quant", False)
    assert {r.company: r.intern for r in p.past}["Samsung R&D Institute India - Bangalore"] is True
    assert len(p.highlights) == 2 and talent.prestige_of("Visa Inc.") == "finance"
