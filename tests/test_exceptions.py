"""U7 exception desk and U8 founder email draft (SYNTHETIC data)."""
from __future__ import annotations

from proofroom import config, exceptions
from proofroom.models import CaseRecord, Finding, RunInput, TeamRow


def case(**kw) -> CaseRecord:
    base = dict(case_id="example-startup-test", run=1, status="DELIVERED", run_mode="FIXTURE",
                input=RunInput(domain="example-startup.test", input_mode="A", run_mode="FIXTURE"),
                reviewed="2026-10-31", g1={"status": "MATCHED", "name": "Example", "id": 1})
    base.update(kw)
    return CaseRecord(**base)


def finding(cid: str, disp: str) -> Finding:
    return Finding(claim_id=cid, disposition=disp, qualified=False, basis=["company_statement"],
                   sentence=f"Sentence {cid}.", evidence_ids=["E1"], as_of="",
                   correction_reason="", limitation="", question="")


def test_clean_run_needs_no_person():
    items = exceptions.exception_desk(case(findings=[finding("C1", "supported")]))
    assert items == [] and "Needs a person: 0" in exceptions.exception_desk_md(items)


def test_exceptions_listed_most_urgent_first():
    c = case(g1={"status": "TIE", "basis": "2 IDs share primary_domain",
                 "candidates": [{"name": "A", "id": 1}, {"name": "B", "id": 2}]},
             findings=[finding("C2", "conflicting")],
             limitations=["C3: suppressed by the sentence check",
                          "Prior-employer lookup failed (502 http_502); joins unchecked",
                          "Founder discovery failed (402 x)"])
    kinds = [i.kind for i in exceptions.exception_desk(c)]
    assert kinds[0] == "identity" and kinds[1] == "conflict"
    assert {"suppressed", "check_incomplete", "retrieval"} <= set(kinds)
    md = exceptions.exception_desk_md(exceptions.exception_desk(c))
    assert md.startswith("**Needs a person: 5**") and "[E1]" in md


def test_founder_email_is_a_draft_with_questions():
    c = case(team=[TeamRow(name="Synthetic Founder", person_id=1, role_join=True)],
             questions=["Which founders worked at Acme?", "Which founders worked at Acme?"])
    md = exceptions.founder_email_md(c)
    assert "DRAFT" in md and "Not sent" in md and "Hi Synthetic," in md
    assert md.count("Which founders worked at Acme?") == 1


def test_founder_email_flag_off_by_default(monkeypatch):
    monkeypatch.delenv("PROOFROOM_FOUNDER_EMAIL", raising=False)
    assert not config.founder_email_enabled()
    monkeypatch.setenv("PROOFROOM_FOUNDER_EMAIL", "yes")
    assert config.founder_email_enabled()
