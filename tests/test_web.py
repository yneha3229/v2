"""S10: web UI (plan v2 §8.2 progressive UI, §8.5 "Load demo case (no keys)").
Fast, no network: the pipeline is monkeypatched and run folders live in tmp_path."""
from __future__ import annotations

import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from proofroom import config, pipeline, store, web
from proofroom.models import (CaseRecord, Claim, Document, Employment, Evidence, Finding,
                              RunInput, TeamRow)

DOMAIN = "example-startup.test"
CASE_ID = "example-startup-test"


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return tmp_path


@pytest.fixture()
def client(data_dir):
    with TestClient(web.app) as c:
        yield c


def sample_case(run: int = 1, run_mode: str = "FIXTURE") -> CaseRecord:
    doc = Document(id="D1", source="https://example-startup.test/blog/seed",
                   title="Example raises <b>$5M</b>", text="Example raised $5M in seed funding.",
                   published="2025-09-07", origin="company", retrieved="2026-10-31T05:00:00Z")
    claim = Claim(id="C1", doc_id="D1", quote="Example raised $5M <script>x()</script>",
                  family="F3", predicate="raised_round", subject="Example", object="",
                  amount_text="$5M", currency_text="$", date_text="", title_text="",
                  qualifiers="", materiality="high", selected=True, exclusion_reason="")
    finding = Finding(claim_id="C1", disposition="supported", qualified=False,
                      basis=["company_statement", "crustdata_indexed_record"],
                      sentence="Example raised $5M in seed funding.", evidence_ids=["E1", "G1"],
                      as_of="2025-09-07", correction_reason="", limitation="", question="")
    ev = [Evidence(id="E1", kind="source_passage", source=doc.source, locator="D1[0:34]",
                   value="Example raised $5M in seed funding.", origin="company",
                   published="2025-09-07", retrieved="2026-10-31T05:00:00Z"),
          Evidence(id="G1", kind="graph", source="POST /company/enrich",
                   locator="funding.milestones[0]", value='{"amount_usd": 5000000}',
                   origin="Crustdata indexed record (Crunchbase-derived)", refreshed="2026-10-01")]
    team = [TeamRow(name="Ada Founder", person_id=42, role_join=True, listed_as_founder=True,
                    current_at_subject=[Employment(employer_name="Example", employer_id=7,
                                                   title="CEO", start="2024-01-01", end="",
                                                   start_precision="year", current=True)])]
    return CaseRecord(case_id=CASE_ID, run=run, status="DELIVERED", run_mode=run_mode,
                      input=RunInput(domain=DOMAIN, input_mode="A", run_mode=run_mode),
                      reviewed="2026-10-31",
                      g1={"domain": DOMAIN, "status": "MATCHED", "company_id": 7,
                          "name": "Example", "basis": "primary domain match",
                          "excluded": [{"id": 9, "name": "Example GmbH"}], "candidates": []},
                      documents=[doc], evidence=ev, claims=[claim], findings=[finding],
                      team=team, stats={"profile": "FAST", "model_source": "recorded model "
                                        "responses (FIXTURE)", "stage_log": ["0.10s start"]})


def publish(root, case: CaseRecord | None = None, email: bool = False) -> store.RunDir:
    case = case or sample_case()
    st = store.Store(root)
    rd = st.new_run(case.case_id)
    case = case.model_copy(update={"run": rd.run})
    brief = ("# Example (example-startup.test): Team & Financing\n\n"
             "## From the sources\n\n1. **Supported**: Example raised $5M. [E1][G1]\n\n"
             "<script>alert('x')</script>\n")
    extra = {"questions.md": "# Questions\n\n- Who led the seed? [G1]\n"}
    if email:
        extra["founder_email.md"] = "<!-- DRAFT -->\n**Subject:** Hello\n\nHi Ada,\n"
    st.publish(rd, case.input.model_dump(), case.model_dump(mode="json"), brief, extra=extra)
    return rd


# ---- markdown and escaping ------------------------------------------------------------

def test_markdown_escapes_script_and_renders_subset():
    out = web.md_to_html("# Title\n\n<script>alert(1)</script> **bold** [E1]\n\n"
                         "| a | b |\n|---|---|\n| <img src=x onerror=y> | [G2] |\n\n"
                         "- [ok](https://x.test/a?b=1&c=2)\n- [bad](javascript:alert(1))\n")
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert "<img" not in out and "&lt;img" in out
    assert "<h1>Title</h1>" in out and "<strong>bold</strong>" in out
    assert 'data-ev="E1"' in out and 'data-ev="G2"' in out and "<table>" in out
    assert 'href="https://x.test/a?b=1&amp;c=2"' in out
    assert "javascript:" not in out.split("href=")[-1].split(">")[0]
    assert 'href="javascript' not in out


def test_cite_filter_escapes():
    out = str(web.cite_html('<b onclick="x">hi</b> [E3]'))
    assert "<b" not in out and 'data-ev="E3"' in out


# ---- index and demo selector ----------------------------------------------------------

def test_index_renders_with_demo_selector_and_recent_runs(client, data_dir):
    publish(data_dir)
    r = client.get("/")
    assert r.status_code == 200
    body = r.text
    assert "Load demo case (no keys)" in body
    for key in ("koah", "linear", "attio"):
        assert f'value="{key}"' in body
    assert "every step, lighter checks" in body and "Draft founder email" in body
    assert f"/runs/{CASE_ID}/1" in body and "FIXTURE" in body


def test_build_request_demo_and_validation():
    req = web.build_request({"demo": "koah"})
    assert (req.run_mode, req.provider, req.fixture, req.domain) == \
        ("FIXTURE", "fixture", "koah", "koahlabs.com")
    req = web.build_request({"domain": "example.com", "urls": ["https://a.test/x"],
                             "profile": "fast"})
    assert req.input_mode == "B" and req.profile == "FAST"
    from fastapi import HTTPException
    for bad in ({"domain": ""}, {"domain": "a.test", "run_mode": "FIXTURE"},
                {"domain": "a.test", "urls": ["javascript:alert(1)"]},
                {"domain": "a.test", "urls": ["https://a.test/1"] * 4}, {"demo": "nope"},
                {"domain": "a.test", "provider": "fixture"}):
        with pytest.raises(HTTPException):
            web.build_request(bad)


# ---- POST /api/runs + polling ------------------------------------------------------------

def _poll(client, token, until=lambda j: j["status"] != "RUNNING", timeout=5.0):
    t0 = time.monotonic()
    while True:
        j = client.get(f"/api/runs/{token}").json()
        if until(j) or time.monotonic() - t0 > timeout:
            return j
        time.sleep(0.02)


def test_post_run_polls_events_and_result(client, data_dir, monkeypatch):
    seen = {}

    async def fake_run(req, *, st=None, on_progress=None):
        seen["req"] = req
        rd = publish(data_dir, email=True)
        await on_progress("start", {"elapsed": 0.1, "run_dir": str(rd.path), "run": rd.run,
                                    "model_source": "x", "profile": "FULL", "mode": "FIXTURE"})
        await on_progress("identity", {"elapsed": 0.2, "g1": {"name": "Example",
                                                             "company_id": 7}, "team": ["Ada"]})
        await asyncio.sleep(0.01)
        await on_progress("claims", {"elapsed": 0.3, "claims": []})
        await on_progress("published", {"elapsed": 0.4, "status": "DELIVERED", "run": rd.run})
        case = CaseRecord.model_validate_json((rd.path / "case.json").read_text())
        return pipeline.RunOutcome("DELIVERED", rd.path, case,
                                   (rd.path / "brief.md").read_text(), seconds=0.4)

    monkeypatch.setattr(pipeline, "run", fake_run)
    r = client.post("/api/runs", json={"demo": "koah"})
    assert r.status_code == 200
    j = _poll(client, r.json()["token"])
    assert j["status"] == "DELIVERED", j
    assert [e["stage"] for e in j["events"]] == ["start", "identity", "claims", "published"]
    assert j["events"][1]["g1"]["company_id"] == 7
    res = j["result"]
    assert "Example raised $5M" in res["brief_md"] and "&lt;script&gt;" in res["brief_html"]
    assert res["case"]["case_id"] == CASE_ID and res["questions_md"].startswith("# Questions")
    assert res["founder_email_md"] and isinstance(res["exceptions"], list)
    assert {e["id"] for e in res["evidence"]} == {"E1", "G1"}
    assert res["run_url"] == f"/runs/{CASE_ID}/1" and j["waiting_for_model"] is None
    assert seen["req"].run_mode == "FIXTURE" and seen["req"].provider == "fixture"


def test_form_post_and_pipeline_crash_is_failed_not_500(client, monkeypatch):
    async def boom(req, *, st=None, on_progress=None):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(pipeline, "run", boom)
    r = client.post("/api/runs", data={"domain": "example.com", "run_mode": "CACHED",
                                       "profile": "FULL"})
    assert r.status_code == 200
    j = _poll(client, r.json()["token"])
    assert j["status"] == "FAILED" and "kaboom" in j["error"] and j["result"] is None


def test_failed_outcome_shows_error(client, monkeypatch):
    async def failed(req, *, st=None, on_progress=None):
        return pipeline.RunOutcome("FAILED", None, None, error="a run for x is already active")

    monkeypatch.setattr(pipeline, "run", failed)
    token = client.post("/api/runs", json={"domain": "example.com"}).json()["token"]
    j = _poll(client, token)
    assert j["status"] == "FAILED" and "already active" in j["error"]


def test_bad_input_and_unknown_token(client):
    assert client.post("/api/runs", json={"domain": "not a domain"}).status_code == 422
    assert client.post("/api/runs", json=["x"]).status_code == 422
    assert client.get("/api/runs/nope").status_code == 404


def test_waiting_for_model_detected(client, data_dir, monkeypatch):
    gate = {}

    async def slow(req, *, st=None, on_progress=None):
        rd = data_dir / "cases" / CASE_ID / "run-1"
        (rd / "model").mkdir(parents=True)
        await on_progress("start", {"elapsed": 0.0, "run_dir": str(rd)})
        (rd / "model" / "extract.request.json").write_text("{}")
        gate["ev"] = asyncio.Event()
        await gate["ev"].wait()
        return pipeline.RunOutcome("FAILED", rd, None, error="stopped")

    monkeypatch.setattr(pipeline, "run", slow)
    token = client.post("/api/runs", json={"domain": "example.com",
                                           "provider": "session"}).json()["token"]
    j = _poll(client, token, until=lambda j: j["waiting_for_model"])
    assert j["status"] == "RUNNING" and j["waiting_for_model"] == "extract"
    rd = data_dir / "cases" / CASE_ID / "run-1"
    (rd / "model" / "extract.response.json").write_text("{}")
    assert client.get(f"/api/runs/{token}").json()["waiting_for_model"] is None
    (rd / "model" / "assess.request.json").write_text("{}")
    assert web.waiting_for_model(rd) == "assess"
    web.RUNS[token].task.cancel()


def test_waiting_for_model_unit(tmp_path):
    assert web.waiting_for_model(None) is None
    assert web.waiting_for_model(tmp_path) is None
    (tmp_path / "model").mkdir()
    (tmp_path / "model" / "check.request.json").write_text("{}")
    assert web.waiting_for_model(tmp_path) == "check"


# ---- run page, receipt, traversal ---------------------------------------------------------

def test_published_run_page_renders_from_folder(client, data_dir):
    publish(data_dir, email=True)
    r = client.get(f"/runs/{CASE_ID}/1")
    assert r.status_code == 200
    b = r.text
    for text in ("FIXTURE", "reduced checking", "Verified ✔", "Identity", "Example GmbH",
                 "Needs a person", "Claims", "Brief", "Team", "Ada Founder", "Evidence",
                 "Questions", "DRAFT — not sent", "Run log", "Proof receipt", "Four clocks"):
        assert text in b, text
    assert "<script>alert" not in b and "<script>x()" not in b and "<b>$5M</b>" not in b
    assert 'id="ev-E1"' in b and 'data-ev="G1"' in b
    data = b.split('id="evidence-data">', 1)[1].split("</script>", 1)[0]
    assert {e["id"] for e in json.loads(data)} == {"E1", "G1"}


def test_tampered_run_is_not_delivered(client, data_dir):
    rd = publish(data_dir)
    (rd.path / "brief.md").write_text("tampered", encoding="utf-8")
    b = client.get(f"/runs/{CASE_ID}/1").text
    assert "Not delivered" in b and "Verified ✔" not in b
    j = client.get(f"/api/verify/{CASE_ID}/1").json()
    assert j["ok"] is False and any(l.startswith("FAIL") for l in j["lines"])


def test_verify_endpoint_ok(client, data_dir):
    publish(data_dir)
    j = client.get(f"/api/verify/{CASE_ID}/1").json()
    assert j["lines"] and isinstance(j["ok"], bool)
    assert any("sha256 brief.md" in l for l in j["lines"])


def test_unpublished_run_without_manifest(client, data_dir):
    rd = store.Store(data_dir).new_run(CASE_ID)
    (rd.path / "failed.json").write_text(json.dumps({"error": "model call timed out <x>",
                                                     "stage_log": ["1.0s start"]}))
    b = client.get(f"/runs/{CASE_ID}/1").text
    assert "Not delivered" in b and "model call timed out &lt;x&gt;" in b


@pytest.mark.parametrize("path", ["/runs/..%2F..%2Fetc/1", "/runs/../1", "/runs/Bad_ID/1",
                                  f"/runs/{CASE_ID}/abc", f"/runs/{CASE_ID}/-1",
                                  "/runs/nope/1", "/api/verify/..%2Fx/1", "/api/verify/a.b/1"])
def test_path_traversal_rejected(client, data_dir, path):
    publish(data_dir)
    assert client.get(path).status_code in (404, 422)


def test_timeline_positions():
    rows = [{"claim_id": "C1", "event": {"value": "2025-09-07", "precision": "day"},
             "published": [{"evidence_id": "E1", "value": "2025-09-07", "precision": "day"}],
             "updated": [], "refreshed": [], "retrieved": [{"evidence_id": "E1",
                                                            "value": "2026-10-31T05:00:00Z",
                                                            "precision": "timestamp"}]}]
    tl = web.timeline(rows)
    pts = tl[0]["rows"][0]["points"]
    assert [p["clock"] for p in pts] == ["event", "published", "retrieved"]
    assert pts[0]["left"] == 4.0 and pts[-1]["left"] == 96.0
    assert web.timeline([]) == []
