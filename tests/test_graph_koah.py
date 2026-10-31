"""S4 on the recorded Koah fixture (P1; Prep_02 answer key), plus T-identity and
T-finance unit cases. FIXTURE mode: no key, no network."""
from __future__ import annotations

import asyncio

import pytest

from proofroom import crustdata as cd
from proofroom import graph
from proofroom.models import TeamRow

NAMES = ["Affirm", "Supermove", "Qualified", "Theory Ventures", "Forerunner"]


@pytest.fixture(scope="module")
def koah(tmp_path_factory):
    async def go():
        c = cd.Crustdata(cd.FIXTURE, fixture="koah")
        res = await graph.resolve(c, "koahlabs.com")
        cands = graph.name_candidates(await c.identify_names(NAMES))
        return res, cands, c.attempts
    return asyncio.run(go())


def test_g1_koah(koah):
    res, _, attempts = koah
    assert res.g1.status == graph.MATCHED and res.g1.company_id == 3718859
    assert all(a.mode == "FIXTURE" for a in attempts)


def test_three_founders_all_current_at_koah(koah):
    res, _, _ = koah
    by = {r.name: r for r in res.team}
    assert set(by) == {"Mike Choi", "Nic Baird", "Herrick Fang"}
    for r in res.team:
        assert r.role_join and r.listed_as_founder
        assert r.current_at_subject[0].title == "Co-Founder"
        assert r.updated_at == "2026-10-23"
    # Nic Baird's concurrent SPC role is allowed (fin-1)
    assert [e.employer_id for e in by["Nic Baird"].other_current] == [820009]


def test_herrick_fang_prior_employer_joins(koah):
    res, cands, _ = koah
    herrick = next(r for r in res.team if r.name == "Herrick Fang")
    joins = {j.employer_name: j for j in graph.prior_joins(herrick, ["Affirm", "Supermove",
                                                                     "Qualified"], cands)}
    assert joins["Affirm"].joined and joins["Affirm"].employer_id == 632082
    assert joins["Supermove"].joined and joins["Supermove"].employer_id == 780882
    assert joins["Affirm"].entry.start == "2019" and joins["Affirm"].entry.start_precision == "year"
    # Real finding: Identify("Qualified") returns 25 candidates, none is 632707
    # ("Qualified (Acquired by Salesforce)"), so the strict §7 rule cannot join it.
    assert not joins["Qualified"].joined
    assert "not a refutation" in joins["Qualified"].note
    assert any(e.employer_id == 632707 for e in herrick.past)


def test_other_founders_do_not_join_affirm(koah):
    res, cands, _ = koah
    for r in res.team:
        if r.name != "Herrick Fang":
            assert not any(j.joined for j in graph.prior_joins(r, ["Affirm", "Supermove"], cands))


def test_g4_koah_financing(koah):
    res, _, _ = koah
    fin = res.financing
    seed = next(m for m in fin["milestones"] if m["round_type"] == "seed")
    assert (seed["amount_usd"], seed["date"], seed["lead_investors"]) == (5e6, "2025-09-07",
                                                                         ["Forerunner"])
    pre = next(m for m in fin["milestones"] if m["round_type"] == "pre_seed")
    assert (pre["date"], pre["date_precision"], pre["amount_usd"]) == ("2024", "year", None)
    assert fin["total_investment_usd"] == 25.5e6 and fin["total_is_capital"]
    assert fin["total_explained_by_milestones"] and fin["record_refresh"] == "unknown"
    m = graph.match_round(fin, "Series A", 20.5e6, "2026-02-24", "Theory Ventures")
    assert m["status"] == "consistent" and m["lead"].startswith("found")


def test_graph_evidence_rows_cite_paths(koah):
    res, _, _ = koah
    ev = graph.graph_evidence(res.g1, res.team, res.financing)
    assert [e.id for e in ev] == [f"G{i}" for i in range(1, len(ev) + 1)]
    assert any(e.locator == "funding.milestones[1]" for e in ev)
    assert all(e.kind == "graph" and e.locator for e in ev)
    assert all("Crunchbase-derived" in e.origin for e in ev if e.locator.startswith("funding"))


# ---- T-identity -------------------------------------------------------------------

def _ident(*cands):
    return [{"matches": [{"confidence_score": conf, "company_data": {
        "crustdata_company_id": cid, "basic_info": {"name": f"Co{cid}", "primary_domain": pd,
                                                    "all_domains": ad}}} for cid, conf, pd, ad
        in cands]}]


@pytest.mark.parametrize("resp", [[{"matches": []}], [], None, {"unexpected": 1}])
def test_id1_no_match_never_says_nonexistent(resp):
    g = graph.resolve_g1("example-startup.test", resp)
    assert g.status == graph.NO_MATCH and "not evidence" in g.basis


def test_id3_exact_domain_beats_higher_confidence():
    g = graph.resolve_g1("example-startup.test", _ident(
        (1, 0.9, "example-startup.test", []), (2, 1.0, "other.test", ["example-startup.test"])))
    assert (g.status, g.company_id) == (graph.MATCHED, 1)


def test_id4_tie_abstains_and_keeps_candidates():
    g = graph.resolve_g1("example-startup.test", _ident(
        (1, 1.0, "example-startup.test", []), (2, 1.0, "example-startup.test", [])))
    assert g.status == graph.TIE and len(g.candidates) == 2 and g.company_id is None


def test_unique_all_domains_candidate_accepted():
    g = graph.resolve_g1("alias.test", _ident((5, 0.7, "main.test", ["main.test", "alias.test"])))
    assert (g.status, g.company_id) == (graph.MATCHED, 5)


def test_id6_redacted_person_is_skipped():
    resp = [{"matched_on": "u1", "match_status": "redacted", "matches": []},
            {"matched_on": "u2", "match_status": "matched",
             "matches": [{"person_data": {"basic_profile": {"name": "Synthetic Person"}}}]}]
    assert [p["basic_profile"]["name"] for p in graph.persons_from_enrich(resp)] == [
        "Synthetic Person"]


def test_id7_both_employment_key_sets_normalize():
    a = graph.normalize_employment({"employer_name": "Koah", "employer_company_id": ["3718859"],
                                    "employee_title": "Co-Founder",
                                    "employee_start_date": "2024-08-01T00:00:00.000Z"}, True)
    b = graph.normalize_employment({"name": "Koah", "crustdata_company_id": 3718859,
                                    "title": "Co-Founder",
                                    "start_date": "2024-08-01T00:00:00+00:00"}, True)
    assert a.employer_id == b.employer_id == 3718859
    assert (a.start, a.start_precision) == ("2024-08", "month") == (b.start, b.start_precision)


def test_employer_id_list_with_conflicting_ids_is_none():
    e = graph.normalize_employment({"employer_name": "X", "employer_company_id": ["1", "2"]}, False)
    assert e.employer_id is None


# ---- T-finance ----------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("2024-01-01", ("2024", "year")), ("2025-09-01", ("2025-09", "month")),
    ("2025-09-07T00:00:00Z", ("2025-09-07", "day")), ("1970-01-01", ("", "unknown")),
    (None, ("", "unknown")), ("garbage", ("", "unknown")), ("2025-13", ("", "unknown")), ("2025-02-30", ("", "unknown")),
])
def test_fin8_fin9_date_precision(raw, expected):
    assert graph.date_and_precision(raw) == expected


def test_fin7_secondary_total_is_not_capital():
    rec = {"funding": {"total_investment_usd": 181e6, "milestones": [
        {"round_type": "secondary_market", "date": "2026-08-26", "amount_usd": 99e6},
        {"round_type": "series_c", "date": "2025-06-10", "amount_usd": 82e6,
         "lead_investors": "Accel"}]}}
    fin = graph.financing_summary(rec)
    assert not fin["total_is_capital"] and fin["has_secondary"]
    assert fin["primary_sum_usd"] == 82e6 and not fin["total_explained_by_milestones"]
    # type-matched: a "Series C" announcement matches series_c, not the last (secondary) round
    m = graph.match_round(fin, "Series C", 82e6, "2025-06", "Accel")
    assert m["status"] == "consistent" and m["milestone"]["round_type"] == "series_c"


def test_fin10_and_pc6_amount_precision_and_aliases():
    rec = {"funding": {"milestones": [{"round_type": "series_b", "date": "2025-08-26",
                                       "amount_usd": 52020932, "lead_investors": "Google Ventures"}]}}
    fin = graph.financing_summary(rec)
    m = graph.match_round(fin, "series_b", 52e6, "2025-08", "GV")
    assert m["status"] == "consistent" and m["lead"] == "not matched (not a conflict)"
    m2 = graph.match_round(fin, "series_b", 52e6, "2025-08", "GV", {"GV": "Google Ventures"})
    assert m2["lead"].startswith("found via source-stated alias")
    assert graph.match_round(fin, "series_b", 60e6)["status"] == "differs"
    assert graph.match_round(fin, "series_d")["status"] == "not_in_record"


def test_investor_name_normalization():
    assert graph.norm_investor("Theory Ventures") == graph.norm_investor("theory")
    assert graph.norm_investor("Forerunner Ventures, LLC") == "forerunner"
    assert graph.norm_investor("GV") != graph.norm_investor("Google Ventures")


def test_s1_fallback_when_no_founders(tmp_path):
    class Fake:
        async def identify_domain(self, d):
            return _ident((9, 1.0, "example-startup.test", []))

        async def company_enrich(self, cid, fields=None):
            return [{"matches": [{"company_data": {"crustdata_company_id": 9, "people": {}}}]}]

        async def founder_search(self, cid):
            return {"profiles": [{"crustdata_person_id": 1, "social_handles": {
                "professional_network_identifier": {"profile_url": "https://x.test/in/a"}}}]}

        async def person_enrich(self, urls):
            return [{"match_status": "matched", "matches": [{"person_data": {
                "crustdata_person_id": 1, "basic_profile": {"name": "Synthetic Founder"},
                "experience": {"employment_details": {"current": [
                    {"name": "Example", "crustdata_company_id": 9, "title": "CEO, Cofounder"}]}}}}]}]

    res = asyncio.run(graph.resolve(Fake(), "example-startup.test"))
    assert [r.name for r in res.team] == ["Synthetic Founder"]
    assert res.team[0].role_join and res.team[0].source == "person_enrich"
    assert isinstance(res.team[0], TeamRow)


def test_enrich_failure_narrows_but_401_propagates():
    from proofroom.errors import CrustError

    class Fake:
        def __init__(self, status):
            self.status = status

        async def identify_domain(self, d):
            return _ident((9, 1.0, "example-startup.test", []))

        async def company_enrich(self, cid, fields=None):
            raise CrustError(self.status, "x", "y")

    res = asyncio.run(graph.resolve(Fake(402), "example-startup.test"))
    assert res.team == [] and "narrowed" in res.limitations[0]
    with pytest.raises(CrustError):
        asyncio.run(graph.resolve(Fake(401), "example-startup.test"))
