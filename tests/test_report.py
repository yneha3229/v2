"""U9 diligence report: fixed format, rule-derived flags, no verdict (SYNTHETIC data)."""
from proofroom import report
from proofroom.models import CaseRecord, Evidence, Finding, RunInput, TeamRow, Employment


def emp(cid):
    return Employment(employer_name="Example", employer_id=cid, title="Co-Founder", start="2024",
                      end="", start_precision="year", current=True)


def finding(cid, disp, basis=("company_statement",), qualified=False, lim=""):
    return Finding(claim_id=cid, disposition=disp, qualified=qualified, basis=list(basis),
                   sentence=f"Sentence {cid}.", evidence_ids=["E1"], as_of="",
                   correction_reason="", limitation=lim, question="")


def case(**kw):
    base = dict(case_id="example-startup-test", run=1, status="DELIVERED", run_mode="FIXTURE",
                input=RunInput(domain="example-startup.test", input_mode="A", run_mode="FIXTURE"),
                reviewed="2026-10-31", g1={"status": "MATCHED", "name": "Example", "company_id": 9},
                evidence=[Evidence(id="E1", kind="source_passage", source="https://x.test", value="v"),
                          Evidence(id="G2", kind="graph", source="/company/enrich",
                                   locator="people.founders[A].experience.employment_details.current",
                                   value="v")])
    base.update(kw)
    return CaseRecord(**base)


def test_flags_follow_the_fixed_rules():
    c = case(findings=[finding("C1", "conflicting"), finding("C2", "supported", qualified=True,
                                                             lim="Title rests on the company only."),
                       finding("C3", "supported", basis=("independent_report",))],
             team=[TeamRow(name="A", person_id=1, role_join=True, listed_as_founder=True,
                           current_at_subject=[emp(9)])],
             financing=[{"kind": "round_check", "line": "C3 (seed): consistent with Crustdata's record. [G6]",
                         "evidence_ids": ["G6"]},
                        {"kind": "round_check", "line": "C5 (seed): consistent with Crustdata's record. [G6]",
                         "evidence_ids": ["G6"]},
                        {"kind": "total", "line": "Crustdata's indexed total $9 includes secondary sales",
                         "evidence_ids": ["G8"]}],
             limitations=["C4: suppressed by the sentence check (unsupported: \"x\")"])
    fl = report.flags(c)
    rules = [f.rule for f in fl]
    assert rules[0] == "R2 conflict"                       # red first
    assert {"A2 qualified", "A1 withheld", "A5 secondary"} <= set(rules)
    assert rules.count("G1 round-confirmed") == 1          # one flag per indexed round
    assert "G3 founders-joined" in rules and "G2 independent" in rules
    assert all(r in report.RULES for r in rules)
    withheld = next(f for f in fl if f.rule == "A1 withheld")
    assert withheld.detail.startswith("C4 could not be verified as written")


def test_report_has_three_pages_methodology_and_no_verdict():
    c = case(findings=[finding("C1", "supported")])
    md = report.report_md(c)
    for heading in ("## Page 1 · Snapshot and flags", "## Page 2 · Team, financing and considerations",
                    "## Page 3 · Methodology", "### Flag rules (identical for every company)"):
        assert heading in md
    low = md.lower()
    assert report.DISCLAIMER in md
    for verdict in ("we recommend", "you should invest", "do not invest", "buy", "pass on"):
        assert verdict not in low
    assert "FIXTURE" in md                                  # honest label


def test_red_flags_for_identity_and_founder_without_join():
    c = case(g1={"status": "TIE", "basis": "2 IDs tie"},
             team=[TeamRow(name="B", person_id=2, role_join=False, listed_as_founder=True)])
    rules = [f.rule for f in report.flags(c)]
    assert "R1 identity" in rules and "R4 founder-no-join" in rules


def test_html_escapes_source_text():
    c = case(findings=[finding("C1", "conflicting")])
    c.findings[0].sentence = "<script>alert(1)</script>"
    h = report.report_html(c)
    assert "<script>alert" not in h and "&lt;script&gt;" in h
    assert h.count('class="page"') == 3
