"""brief.md (§4.3), U6 questions, U3 origin map, U4 four clocks and the U1 proof
receipt, all on a synthetic case (example-startup.test)."""
from __future__ import annotations

import json
import re

from proofroom import render, store, verify
from proofroom.models import (CaseRecord, Claim, Document, Employment, Evidence, Finding,
                              PriorJoin, RunInput, TeamRow)

DOMAIN = "example-startup.test"
CRUNCH = "indexed record (Crunchbase-derived)"


def _claim(cid: str, doc: str, quote: str, selected: bool = True, amount: str = "",
           reason: str = "") -> Claim:
    return Claim(id=cid, doc_id=doc, quote=quote, family="F3", predicate="raised_round",
                 subject="Example Startup", object="", amount_text=amount, currency_text="",
                 date_text="", title_text="", qualifiers="", materiality="high",
                 selected=selected, exclusion_reason=reason)


def _finding(cid: str, disp: str, sentence: str, ids: list[str], basis: list[str], **kw) -> Finding:
    base = dict(qualified=False, as_of="", correction_reason="", limitation="", question="")
    base.update(kw)
    return Finding(claim_id=cid, disposition=disp, basis=basis, sentence=sentence,
                   evidence_ids=ids, **base)


def _emp(name: str, eid: int | None, title: str, start: str = "", prec: str = "unknown",
         current: bool = False) -> Employment:
    return Employment(employer_name=name, employer_id=eid, title=title, start=start, end="",
                      start_precision=prec, current=current)


def sample_case(**over) -> CaseRecord:
    docs = [
        Document(id="D1", source="https://example-startup.test/blog/series-a",
                 title="Example Startup raises $12M Series A", text="We raised $12M.",
                 published="2026-02-24", origin="company", retrieved="2026-10-31T05:00:00Z"),
        Document(id="D2", source="https://example-ventures.test/news/example-startup",
                 title="Why we led Example Startup's Series A", text="Our $12M investment.",
                 published="2026-02-24", updated="2026-03-02", origin="investor"),
        Document(id="D3", source="https://news-a.test/story", title="Example Startup hires a CFO today",
                 text="Hiring news.", origin="independent", published="2026-04-01"),
        Document(id="D4", source="https://news-b.test/copy", title="Example Startup hires a CFO today",
                 text="Hiring news.", origin="independent", published="2026-04-02"),
    ]
    evidence = [
        Evidence(id="E1", kind="source_passage", source=docs[0].source, locator="D1:0-40",
                 value="Example Startup raised a $12M Series A led by Example Ventures.",
                 published="2026-02-24", origin="company"),
        Evidence(id="E2", kind="source_passage", source=docs[1].source, locator="D2:10-60",
                 value="We led the $12M Series A in Example Startup. " + "x" * 300,
                 published="2026-02-24", updated="2026-03-02", origin="investor"),
        Evidence(id="E3", kind="source_passage", source=docs[2].source, locator="D3:0-20",
                 value="The founders worked together at Alpha Corp and Beta Inc.",
                 origin="independent"),
        Evidence(id="E4", kind="source_passage", source=docs[3].source, locator="D4:0-20",
                 value="The founders worked together at Alpha Corp and Beta Inc.",
                 origin="independent"),
        Evidence(id="G1", kind="graph", source="/company/identify", locator="matches[0]",
                 value="Example Startup = 4242", origin="Crustdata identity graph",
                 refreshed="unknown"),
        Evidence(id="G2", kind="graph", source="/company/enrich", locator="funding.milestones[0]",
                 value="series_a, 2026-02-24 (day), $12,000,000, lead Example Ventures",
                 origin=CRUNCH, refreshed="2026-10-20"),
        Evidence(id="G3", kind="graph", source="/company/enrich",
                 locator="funding.total_investment_usd", value="$12,000,000", origin=CRUNCH,
                 refreshed="2026-10-20"),
    ]
    team = [
        TeamRow(name="Ada Example", person_id=11, updated_at="2026-10-20", role_join=True,
                current_at_subject=[_emp("Example Startup", 4242, "Co-Founder", "2024", "year", True)],
                other_current=[_emp("Fellowship Org", 77, "Fellow", current=True)],
                prior_joins=[PriorJoin(employer_name="Alpha Corp", employer_id=500, joined=True,
                                       note="ID join: past entry 'Alpha Corp' = 500"),
                             PriorJoin(employer_name="Beta Inc", employer_id=None, joined=False,
                                       note="name match only: 'Beta, Inc.'")]),
        TeamRow(name="Bo Example", person_id=12, updated_at="2026-10-19", role_join=False,
                prior_joins=[PriorJoin(employer_name="Alpha Corp", employer_id=None, joined=False,
                                       note="none of 2 Identify candidates is in this person's "
                                            "indexed past roles (not a refutation)")]),
    ]
    findings = [
        _finding("C1", "supported", "Example Startup announced a $12M Series A in Feb 2026.",
                 ["E1", "E2"], ["company_statement", "investor_statement"], as_of="2026-02-24"),
        _finding("C2", "not_established", "Example Startup's post names no seed amount.",
                 ["E1"], ["company_statement"]),
        _finding("C3", "supported_corrected",
                 "A news report says the founders worked together at Alpha Corp and Beta Inc.",
                 ["E3", "G2"], ["independent_report", "crustdata_indexed_record"],
                 correction_reason="scope", question="Which founders worked at Beta Inc?"),
        _finding("C4", "conflicting", "The sources disagree on the Series A lead.", ["E2"],
                 ["investor_statement"], limitation="lead named differently"),
    ]
    claims = [_claim("C1", "D1", "We raised a $12M Series A", amount="$12M"),
              _claim("C2", "D2", "Our $12M investment", amount="$12M"),
              _claim("C5", "D1", "We have $3M ARR", selected=False, reason="out of scope (revenue)")]
    financing = [
        {"kind": "meta", "line": "", "evidence_ids": [], "record_refresh": "unknown",
         "total_is_capital": True},
        {"kind": "round", "line": "Series A $12M dated 24 Feb 2026, lead Example Ventures",
         "evidence_ids": ["G2"]},
        {"kind": "total", "line": "$12M across 1 rounds per Crustdata's record", "evidence_ids": ["G3"]},
    ]
    data = dict(case_id="example-startup-test", run=2, status="DELIVERED", run_mode="FIXTURE",
                input=RunInput(domain=DOMAIN, input_mode="A", run_mode="FIXTURE"),
                reviewed="2026-10-31", g1={"status": "MATCHED", "company_id": 4242,
                                           "name": "Example Startup"},
                documents=docs, evidence=evidence, claims=claims, findings=findings, team=team,
                financing=financing, questions=["What made up the earlier rounds?"],
                not_checked=["C6: valuation (not in scope)"], limitations=["Record refresh is unknown."],
                stats={"seconds": 12.5, "crustdata_credits": 6, "stage_log": ["a", "b"] * 80})
    data.update(over)
    return CaseRecord(**data)


SECTIONS = ["## From the sources", "## From Crustdata's graph", "## Questions", "## Not checked",
            "## Limitations", "## Evidence", "## Run statistics"]


# ---- brief.md ----------------------------------------------------------------------

def test_brief_section_order_and_header():
    md = render.brief_md(sample_case(), model_source="session", profile="FULL")
    pos = [md.index(s) for s in SECTIONS]
    assert pos == sorted(pos)
    head = md.split("## From the sources")[0]
    for bit in ("Example Startup (example-startup.test)", "Crustdata company ID 4242",
                "reviewed 2026-10-31", "run 2", "Mode A", "FIXTURE", "model: session", "profile FULL"):
        assert bit in head
    assert "reduced checking" not in md


def test_fast_profile_is_labelled():
    md = render.brief_md(sample_case(), model_source="session", profile="FAST")
    assert "profile FAST (reduced checking)" in md.split("\n## ")[0]


def test_source_sentences_keep_status_basis_and_citations():
    md = render.brief_md(sample_case(), model_source="session", profile="FULL")
    src = md.split("## From the sources")[1].split("## From Crustdata's graph")[0]
    assert ("1. **Supported** · company and investor statements, one announcement: "
            "Example Startup announced a $12M Series A in Feb 2026. [E1][E2]") in src
    assert "**Not established** · company statement only:" in src
    assert "**Supported, corrected (scope)**" in src and "[E3][G2]" in src
    assert "**Conflicting**" in src
    for f in sample_case().findings:
        assert f.sentence in src


def test_team_table_marks():
    md = render.brief_md(sample_case(), model_source="session", profile="FULL")
    assert ("| Founder | Person ID | Current role at Example Startup (employer-ID join) "
            "| Prior employers matched by ID |") in md
    ada = next(ln for ln in md.splitlines() if ln.startswith("| Ada Example"))
    assert "Co-Founder, since 2024 ✔" in ada and "also current: Fellowship Org" in ada
    assert "Alpha Corp ✔" in ada and "Beta Inc ≈" in ada
    bo = next(ln for ln in md.splitlines() if ln.startswith("| Bo Example"))
    assert "? no current entry with employer ID 4242" in bo and "Alpha Corp ?" in bo
    assert "profiles are self-maintained" in md


def test_funding_labels_and_no_independent_next_to_crustdata():
    md = render.brief_md(sample_case(), model_source="session", profile="FULL")
    graph = md.split("## From Crustdata's graph")[1].split("## Questions")[0]
    assert "Funding record: indexed record (Crunchbase-derived); record refresh: unknown" in graph
    assert "- Series A $12M dated 24 Feb 2026, lead Example Ventures [G2]" in graph
    assert "- Total raised: $12M across 1 rounds per Crustdata's record [G3]" in graph
    assert "independent" not in graph.lower()
    assert not re.search(r"\bindependent\s+(?:\w+\s+)?\(?(?:Crustdata|Crunchbase)", md, re.I)
    assert not re.search(r"(?:Crustdata|Crunchbase)[^\n·|:]{0,60}\bindependent", md, re.I)


def test_total_not_capital_when_secondary():
    fin = [{"kind": "total", "line": "$181M indexed total, which includes secondary sales",
            "evidence_ids": ["G3"], "total_is_capital": False}]
    md = render.brief_md(sample_case(financing=fin), model_source="session", profile="FULL")
    assert "Indexed total, not capital raised: $181M" in md and "Total raised" not in md
    # refresh falls back to the indexed graph rows when there is no meta line
    assert "record refresh: 2026-10-20" in md


def test_financing_lines_from_summary():
    summary = {"basis": "x", "record_refresh": "unknown", "total_is_capital": False,
               "num_rounds": 2, "total_investment_usd": 181e6, "primary_sum_usd": 82e6,
               "milestones": [
                   {"path": "funding.milestones[0]", "round_type": "series_c", "date": "2024",
                    "date_precision": "year", "amount_usd": 82e6, "lead_investors": []},
                   {"path": "funding.milestones[1]", "round_type": "secondary_market",
                    "date": "2025-09-07", "date_precision": "day", "amount_usd": 99e6,
                    "lead_investors": ["Buyer Fund"]}]}
    evs = [Evidence(id="G2", kind="graph", source="/company/enrich", locator="funding.milestones[0]",
                    value="series_c, 2024 (year), $82,000,000, lead not recorded", origin=CRUNCH),
           Evidence(id="G3", kind="graph", source="/company/enrich", locator="funding.milestones[1]",
                    value="secondary_market, 2025-09-07 (day), $99,000,000, lead Buyer Fund", origin=CRUNCH),
           Evidence(id="G4", kind="graph", source="/company/enrich",
                    locator="funding.total_investment_usd",
                    value="$181,000,000 (includes secondary sales)", origin=CRUNCH)]
    lines = render.financing_lines(summary, evs)
    assert lines[0]["kind"] == "meta" and lines[0]["total_is_capital"] is False
    assert lines[1] == {"kind": "round", "line": "Series C $82M dated 2024, lead not recorded",
                        "evidence_ids": ["G2"]}
    assert lines[2]["line"].startswith("Secondary sale (liquidity, not company capital) $99M dated 7 Sep 2025")
    assert lines[3]["kind"] == "total" and lines[3]["evidence_ids"] == ["G4"]
    assert lines[4]["kind"] == "calculation" and "calculation from Crustdata's indexed record" in lines[4]["line"]
    from proofroom import gate
    ev = {e.id: e for e in evs}
    for d in lines[1:4]:
        assert gate.gate_sentence(d["line"], d["evidence_ids"], ev).clean, d


def test_not_checked_limitations_evidence_and_stats():
    md = render.brief_md(sample_case(), model_source="session", profile="FULL")
    nc = md.split("## Not checked")[1].split("## Limitations")[0]
    assert "C6: valuation (not in scope)" in nc and 'C5: "We have $3M ARR" (out of scope (revenue))' in nc
    lim = md.split("## Limitations")[1].split("## Evidence")[0]
    assert "Record refresh is unknown." in lim and "C4: lead named differently" in lim
    evl = md.split("## Evidence")[1].split("## Run statistics")[0]
    e2 = next(ln for ln in evl.splitlines() if ln.startswith("- **E2**"))
    assert "published 2026-02-24 · updated 2026-03-02" in e2
    assert len(re.search(r'"([^"]*)"', e2).group(1)) <= 200
    stats = md.split("## Run statistics")[1]
    assert "| crustdata_credits | 6 |" in stats and "| stage_log | 160 entries |" in stats


def test_empty_graph_states_why():
    md = render.brief_md(sample_case(team=[], financing=[]), model_source="session", profile="FULL")
    assert "No founder records were found in Crustdata's graph for company ID 4242" in md


# ---- U6 questions ------------------------------------------------------------------

def test_questions_ranked_with_evidence():
    q = render.questions_md(sample_case())
    assert q.startswith("# Questions for the founder meeting")
    items = re.findall(r"^\d+\. (.*)$", q, re.M)
    assert "sources disagree" in items[0]                       # conflicting first
    assert items[1] == "Which founders worked at Beta Inc?"     # then corrected (own question)
    assert "could not establish" in items[2] and "\"Our $12M investment\"" in items[2]
    assert items[-1] == "What made up the earlier rounds?"
    assert "   - [E3] https://news-a.test/story:" in q
    assert len(items) == 4


# ---- U3 origin map -----------------------------------------------------------------

def test_origin_map_groups_announcement_and_syndication():
    data = render.origin_map(sample_case())
    kinds = {g["kind"]: g for g in data["groups"]}
    ann = kinds["announcement"]
    assert {m["evidence_id"] for m in ann["members"]} == {"E1", "E2"}
    syn = kinds["syndication"]
    assert {m["evidence_id"] for m in syn["members"]} == {"E3", "E4"}
    assert {"graph", "indexed_record"} <= set(kinds)
    assert data["independent_origin_count"] == 2
    svg = render.origin_map_svg(data)
    assert svg.startswith("<svg") and "currentColor" in svg and "E3" in svg and "http://www.w3.org" in svg
    assert "<script" not in svg


def test_origin_map_different_rounds_stay_separate():
    case = sample_case()
    case.documents[1].text = "Our $7M investment."
    case.documents[1].title = "Why we backed Example Startup"
    case.claims = []
    case.documents[0].text = "We raised $12M."
    data = render.origin_map(case)
    assert "announcement" not in {g["kind"] for g in data["groups"]}
    assert data["independent_origin_count"] == 3


# ---- U4 four clocks ----------------------------------------------------------------

def test_four_clocks():
    rows = {r["claim_id"]: r for r in render.four_clocks(sample_case())}
    c1 = rows["C1"]
    assert c1["event"] == {"value": "2026-02-24", "precision": "day"}
    assert c1["published"] == [{"evidence_id": "E1", "value": "2026-02-24", "precision": "day"},
                               {"evidence_id": "E2", "value": "2026-02-24", "precision": "day"}]
    assert c1["updated"] == [{"evidence_id": "E2", "value": "2026-03-02", "precision": "day"}]
    assert c1["retrieved"] == [{"evidence_id": "E1", "value": "2026-10-31T05:00:00Z",
                                "precision": "timestamp"}]
    c3 = rows["C3"]
    assert c3["refreshed"] == [{"evidence_id": "G2", "value": "2026-10-20", "precision": "day"}]
    assert rows["C2"]["event"]["precision"] == "unknown"
    assert render.clock_value("2024-01-01") == {"value": "2024", "precision": "year"}
    assert render.clock_value("Feb 2026") == {"value": "2026-02", "precision": "month"}


# ---- U1 proof receipt ----------------------------------------------------------------

def _publish(tmp_path, case: CaseRecord):
    s = store.Store(tmp_path)
    rd = s.new_run(case.case_id)
    brief = render.brief_md(case, model_source="session", profile="FULL")
    s.publish(rd, case.input.model_dump(), case.model_dump(mode="json"), brief)
    return rd


def test_receipt_ok_on_published_run(tmp_path):
    rd = _publish(tmp_path, sample_case())
    r = verify.verify_receipt(rd.path)
    text = verify.format_receipt(r)
    assert r.ok, text
    assert "PASS sha256 brief.md" in text and "PASS case.json loads as CaseRecord" in text
    assert "PASS C1 amounts 1/1 dates 1/1" in text
    assert "PASS financing[1] amounts 1/1 dates 1/1" in text
    assert text.rstrip().endswith("RECEIPT OK")


def test_receipt_fails_after_brief_tamper(tmp_path):
    rd = _publish(tmp_path, sample_case())
    p = rd.path / "brief.md"
    p.write_text(p.read_text(encoding="utf-8").replace("$12M Series A in Feb", "$15M Series A in Feb")
                 + "\nSee [E77].\n", encoding="utf-8")
    text = verify.format_receipt(verify.verify_receipt(rd.path))
    assert "FAIL sha256 brief.md (mismatch)" in text
    assert "FAIL C1" in text and "not found in brief.md" in text
    assert "FAIL citations in brief.md: unknown E77" in text
    assert re.search(r"RECEIPT FAILED \(\d+\)\n$", text)


def test_receipt_fails_after_evidence_number_edit(tmp_path):
    rd = _publish(tmp_path, sample_case())
    p = rd.path / "case.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    for e in data["evidence"]:
        if e["id"] in ("E1", "E2"):
            e["value"] = e["value"].replace("$12M", "$13M")
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    r = verify.verify_receipt(rd.path)
    text = verify.format_receipt(r)
    assert not r.ok
    assert "FAIL sha256 case.json (mismatch)" in text
    assert re.search(r"^FAIL C1 amounts 0/1", text, re.M)
    assert "RECEIPT FAILED (2)" in text


def test_receipt_without_manifest(tmp_path):
    r = verify.verify_receipt(tmp_path)
    assert not r.ok and verify.format_receipt(r).endswith("RECEIPT FAILED (1)\n")
