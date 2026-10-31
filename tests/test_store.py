"""S3: models and the run store, including saf-4 and saf-5 (Prep_02 T-safety)."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from proofroom import models, store
from proofroom.errors import StoreError


def sample_case() -> dict:
    claim = models.Claim(id="C1", doc_id="D1", quote="raised $1M", family="F3",
                         predicate="raised_round", subject="Example", object="", amount_text="$1M",
                         currency_text="$", date_text="", title_text="", qualifiers="",
                         materiality="high", selected=True, exclusion_reason="")
    rec = models.CaseRecord(
        case_id="example-startup-test", run=1, status="DELIVERED", run_mode="FIXTURE",
        input=models.RunInput(domain="example-startup.test", input_mode="B", run_mode="FIXTURE"),
        reviewed="2026-10-31", g1={"status": "MATCHED", "company_id": 1}, claims=[claim])
    return rec.model_dump()


def test_round_trip_writes_reads_back_and_delivers(tmp_path):
    s = store.Store(tmp_path)
    rd = s.new_run("example-startup-test")
    inp = {"domain": "example-startup.test"}
    case = sample_case()
    man = s.publish(rd, inp, case, "# Brief\n[E1] ₹50 crore\n")
    assert man["delivery"] == "DELIVERED" and rd.run == 1
    assert set(man["files"]) == {"input.json", "case.json", "brief.md"}
    assert store.verify_run(rd)
    back = models.CaseRecord.model_validate_json((rd.path / "case.json").read_text())
    assert back.model_dump() == case
    assert (rd.path / "brief.md").read_text(encoding="utf-8").endswith("₹50 crore\n")


def test_runs_are_numbered_and_write_once(tmp_path):
    s = store.Store(tmp_path)
    a, b = s.new_run("c"), s.new_run("c")
    assert (a.run, b.run) == (1, 2)
    s.publish(a, {}, {}, "x")
    with pytest.raises(StoreError):
        s.publish(a, {}, {}, "y")


def test_saf4_write_failure_leaves_no_manifest(tmp_path):
    s = store.Store(tmp_path)
    rd = s.new_run("c")
    (rd.path / "case.json").write_text("pre-existing")  # exclusive create will fail
    with pytest.raises(StoreError, match="write failed"):
        s.publish(rd, {}, {}, "brief")
    assert not rd.manifest_path.exists() and not store.verify_run(rd)


def test_saf5_readback_mismatch_leaves_no_manifest(tmp_path, monkeypatch):
    s = store.Store(tmp_path)
    rd = s.new_run("c")
    real = store.sha256_bytes
    calls = {"n": 0}

    def flaky(data: bytes) -> str:
        calls["n"] += 1
        return "0" * 64 if calls["n"] == 5 else real(data)  # 5th hash = 2nd read-back

    monkeypatch.setattr(store, "sha256_bytes", flaky)
    with pytest.raises(StoreError, match="mismatch"):
        s.publish(rd, {}, {}, "brief")
    assert not rd.manifest_path.exists()


def test_tampered_file_fails_verification(tmp_path):
    s = store.Store(tmp_path)
    rd = s.new_run("c")
    s.publish(rd, {}, {}, "brief")
    (rd.path / "brief.md").write_text("edited later")
    assert not store.verify_run(rd)


def test_identical_request_within_window_returns_existing(tmp_path):
    now = [1000.0]
    s = store.Store(tmp_path, clock=lambda: now[0])
    rd = s.new_run("c")
    s.publish(rd, {"domain": "a"}, {}, "b")
    assert s.recent_identical("c", {"domain": "a"}).run == 1
    assert s.recent_identical("c", {"domain": "other"}) is None
    now[0] += store.DEDUP_WINDOW_S + 1
    assert s.recent_identical("c", {"domain": "a"}) is None


def test_corrupt_manifest_is_not_delivered(tmp_path):
    s = store.Store(tmp_path)
    rd = s.new_run("c")
    rd.manifest_path.write_text("{oops")
    assert store.read_manifest(rd) is None and not store.verify_run(rd)


def test_case_id_and_lock():
    assert store.case_id_for(" KoahLabs.com ") == "koahlabs-com"
    with pytest.raises(ValueError):
        store.case_id_for("...")
    assert store.case_lock("x") is store.case_lock("x")


def test_model_schemas_are_strict_and_flat():
    with pytest.raises(ValidationError):
        models.Check(claim_id="C1", entailed=True, missing_qualifier="")  # field missing
    with pytest.raises(ValidationError):
        models.Check(claim_id="C1", entailed=True, missing_qualifier="",
                     unsupported_fragment="", extra="no")
    for schema in (models.ExtractResult, models.AssessResult, models.CheckResult):
        js = json.dumps(schema.model_json_schema())
        assert '"additionalProperties": false' in js
        assert "anyOf" not in js  # no nullable/union fields in model-call schemas
        for d in schema.model_json_schema().get("$defs", {}).values():
            assert set(d["required"]) == set(d["properties"])


def test_extra_files_are_hashed_and_verified(tmp_path):
    s = store.Store(tmp_path)
    rd = s.new_run("c")
    man = s.publish(rd, {}, {}, "brief", extra={"questions.md": "# Q"})
    assert "questions.md" in man["files"] and store.verify_run(rd)
    (rd.path / "questions.md").write_text("changed")
    assert not store.verify_run(rd)
    with pytest.raises(StoreError):
        s.publish(s.new_run("c"), {}, {}, "b", extra={"../x": "no"})


def test_binary_extra_file_is_hashed(tmp_path):
    s = store.Store(tmp_path)
    rd = s.new_run("c")
    pdf = b"%PDF-1.7 synthetic"
    man = s.publish(rd, {}, {}, "brief", extra={"equity_report.pdf": pdf})
    assert (rd.path / "equity_report.pdf").read_bytes() == pdf and store.verify_run(rd)
    assert man["files"]["equity_report.pdf"] == store.sha256_bytes(pdf)
