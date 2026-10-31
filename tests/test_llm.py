"""Model-call layer: prompts, providers (no real API call), local validation (saf-6)."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from proofroom import llm, prompts
from proofroom.errors import ConfigError, ModelError
from proofroom.models import (AssessResult, Check, CheckResult, Claim, Document, Evidence,
                              ExtractResult, Finding)

THINK = "Think the problem through before you answer."
FORBIDDEN = {"thinking", "temperature", "top_p", "top_k", "tool_choice", "tools", "citations",
             "stop_sequences", "extra_body", "extra_headers"}


def claim(cid="C1", doc="D1", quote="raised a $5M seed", selected=True, **kw) -> Claim:
    base = dict(id=cid, doc_id=doc, quote=quote, family="F3", predicate="raised_round",
                subject="Example Startup", object="", amount_text="$5M", currency_text="$",
                date_text="", title_text="", qualifiers="", materiality="high",
                selected=selected, exclusion_reason="")
    base.update(kw)
    return Claim(**base)


def finding(cid="C1", ev=("E1",)) -> Finding:
    return Finding(claim_id=cid, disposition="supported", qualified=False,
                   basis=["company_statement"], sentence="Example's post says it raised $5M.",
                   evidence_ids=list(ev), as_of="2026-01-15", correction_reason="",
                   limitation="", question="")


CHECKS = CheckResult(checks=[Check(claim_id="C1", entailed=True, missing_qualifier="",
                                   unsupported_fragment="")])


# ---- prompts ----------------------------------------------------------------------

def test_system_prompts_end_with_think_line_and_data_rule():
    for system in (prompts.SYSTEM_EXTRACT, prompts.SYSTEM_ASSESS, prompts.SYSTEM_CHECK):
        assert system.endswith(THINK)
        assert "never" in system and "instruction" in system.lower()
    assert "Absence of a record is never a conflict" in prompts.SYSTEM_ASSESS
    assert "2024-01-01" in prompts.SYSTEM_ASSESS


def test_message_layouts():
    doc = Document(id="D1", source="https://example-startup.test/a", text="Body text.",
                   published="2026-01-15")
    m = prompts.extract_message("Example", "example-startup.test", None, [doc], "")
    assert m.startswith("FOCUS NOTE: none\nSUBJECT: Example (example-startup.test), "
                        "Crustdata company ID unresolved\n")
    assert "DOCUMENT D1\nsource: https://example-startup.test/a   published: 2026-01-15" \
           "   updated: unknown\nBody text." in m
    assert "SELECTION CAP" not in m
    assert "SELECTION CAP: at most 3" in prompts.extract_message("E", "e.test", 1, [doc], "x",
                                                                 max_selected=3)
    ev = [Evidence(id="E1", kind="source_passage", source="u", value="a\nb", origin="O1 (company)"),
          Evidence(id="G4", kind="graph", source="/company/enrich",
                   locator="funding.milestones[1]", value="{amount_usd: 5000000}")]
    a = prompts.assess_message("E", "e.test", 3718859, "2026-10-31",
                               [claim(), claim("C2", selected=False)], ev, "row")
    assert "C1 | F3 | raised_round | quote: \"raised a $5M seed\" | doc D1" in a
    assert "C2 |" not in a
    assert "E1 | source_passage | u | subject: unknown | origin O1 (company) | " \
           "published unknown | updated unknown | retrieved unknown | \"a b\"" in a
    assert "G4 | graph | /company/enrich | funding.milestones[1] = {amount_usd: 5000000} | " \
           "record refresh: unknown | origin: Crustdata indexed record (Crunchbase-derived)" in a
    assert "TEAM MATRIX (computed by code from employer-ID joins)\nrow" in a
    c = prompts.check_message([("C1", "S one.", ev[:1]), ("C2", "S two.", [])])
    assert "SENTENCE FOR C1\nsentence: \"S one.\"\ncited evidence:\nE1 |" in c
    assert "SENTENCE FOR C2\nsentence: \"S two.\"\ncited evidence:\nnone" in c


# ---- AnthropicProvider (fake client; no network) ---------------------------------------

class FakeMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def resp(stop, parsed=None, category=None):
    return SimpleNamespace(stop_reason=stop, parsed_output=parsed,
                           stop_details=SimpleNamespace(category=category) if category else None,
                           usage=SimpleNamespace(input_tokens=11, output_tokens=7), content=[])


def fake_provider(*responses):
    msgs = FakeMessages(responses)
    return llm.AnthropicProvider(client=SimpleNamespace(messages=msgs)), msgs


def test_anthropic_success_sends_only_allowed_params():
    p, msgs = fake_provider(resp("end_turn", CHECKS))
    out = asyncio.run(p.call("check", prompts.SYSTEM_CHECK, "u", CheckResult, "low", 30.0))
    assert out.parsed == CHECKS and out.stop_reason == "end_turn"
    assert out.attempt.status == "ok" and out.attempt.mode == "LIVE"
    assert (out.attempt.input_tokens, out.attempt.output_tokens) == (11, 7)
    kw = msgs.calls[0]
    assert set(kw) == {"model", "max_tokens", "system", "messages", "output_format",
                       "output_config", "timeout"}
    assert not FORBIDDEN & set(kw)
    assert kw["model"] == "claude-sonnet-5-5" and kw["max_tokens"] == 12000
    assert kw["messages"] == [{"role": "user", "content": "u"}]          # no prefill
    assert kw["output_format"] is CheckResult and kw["output_config"] == {"effort": "low"}
    assert isinstance(kw["timeout"], float) and 0 < kw["timeout"] <= 30.0


def test_anthropic_max_tokens_retries_once_then_fails():
    p, msgs = fake_provider(resp("max_tokens", CHECKS), resp("max_tokens", CHECKS))
    with pytest.raises(ModelError) as ei:
        asyncio.run(p.call("check", "s", "u", CheckResult, "low", 30.0))
    assert len(msgs.calls) == 2
    assert [a.status for a in ei.value.attempts] == ["max_tokens", "max_tokens"]


def test_anthropic_max_tokens_then_success():
    p, msgs = fake_provider(resp("max_tokens"), resp("end_turn", CHECKS))
    out = asyncio.run(p.call("check", "s", "u", CheckResult, "low", 30.0))
    assert out.parsed == CHECKS and [a.status for a in out.attempts] == ["max_tokens", "ok"]


def test_anthropic_refusal_is_model_error_with_category():
    p, msgs = fake_provider(resp("refusal", None, category="cyber"))
    with pytest.raises(ModelError) as ei:
        asyncio.run(p.call("check", "s", "u", CheckResult, "low", 30.0))
    assert len(msgs.calls) == 1
    assert ei.value.attempts[0].error == {"type": "refusal", "category": "cyber"}


def test_anthropic_end_turn_without_parse_fails():
    p, _ = fake_provider(resp("end_turn", None))
    with pytest.raises(ModelError):
        asyncio.run(p.call("check", "s", "u", CheckResult, "low", 30.0))


def test_anthropic_needs_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ConfigError):
        asyncio.run(llm.AnthropicProvider().call("check", "s", "u", CheckResult, "low", 1.0))
    with pytest.raises(ConfigError):
        llm.make_provider("anthropic", "x")


# ---- SessionProvider ---------------------------------------------------------------

async def _write_later(path, payload, delay=0.05):
    await asyncio.sleep(delay)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(payload if isinstance(payload, str) else json.dumps(payload))
    tmp.replace(path)


def test_session_round_trip(tmp_path):
    p = llm.SessionProvider(tmp_path, poll_s=0.01)

    async def go():
        writer = asyncio.create_task(_write_later(tmp_path / "check.response.json",
                                                  {"output": CHECKS.model_dump()}))
        out = await p.call("check", prompts.SYSTEM_CHECK, "USER", CheckResult, "low", 2.0)
        await writer
        return out

    out = asyncio.run(go())
    assert out.parsed == CHECKS and out.attempt.mode == "SESSION"
    assert out.attempt.endpoint == "session" and out.attempt.status == "ok"
    req = json.loads((tmp_path / "check.request.json").read_text())
    assert set(req) >= {"name", "system", "user", "schema", "effort", "created_at"}
    assert req["user"] == "USER" and req["schema"]["title"] == "CheckResult"
    assert req["system"].endswith(THINK)


def test_session_bare_object_and_stale_response_removed(tmp_path):
    (tmp_path / "check.response.json").write_text("stale")       # must not be accepted
    p = llm.SessionProvider(tmp_path, poll_s=0.01)

    async def go():
        writer = asyncio.create_task(_write_later(tmp_path / "check.response.json",
                                                  CHECKS.model_dump()))
        out = await p.call("check", "s", "u", CheckResult, "low", 2.0)
        await writer
        return out

    assert asyncio.run(go()).parsed == CHECKS


def test_session_invalid_then_fixed(tmp_path):
    p = llm.SessionProvider(tmp_path, poll_s=0.01)
    resp_path = tmp_path / "check.response.json"

    async def go():
        await_task = asyncio.create_task(
            p.call("check", "s", "u", CheckResult, "low", 2.0))
        await _write_later(resp_path, {"checks": [{"claim_id": "C1"}]}, 0.03)
        for _ in range(100):
            if (tmp_path / "check.error.json").exists():
                break
            await asyncio.sleep(0.01)
        err = json.loads((tmp_path / "check.error.json").read_text())
        await _write_later(resp_path, CHECKS.model_dump(), 0.02)
        return err, await await_task

    err, out = asyncio.run(go())
    assert err["attempt"] == 1 and any("entailed" in e["loc"] for e in err["errors"])
    assert out.parsed == CHECKS
    assert [a.status for a in out.attempts] == ["invalid_output", "ok"]


def test_session_invalid_writes_error_then_times_out(tmp_path):
    p = llm.SessionProvider(tmp_path, poll_s=0.01)

    async def go():
        writer = asyncio.create_task(_write_later(tmp_path / "check.response.json",
                                                  {"checks": "nope"}, 0.02))
        try:
            await p.call("check", "s", "u", CheckResult, "low", 0.3)
        finally:
            await writer

    with pytest.raises(ModelError) as ei:
        asyncio.run(go())
    assert "timed out" in str(ei.value)
    err = json.loads((tmp_path / "check.error.json").read_text())
    assert err["name"] == "check" and err["errors"]
    assert not (tmp_path / "check.response.json").exists()        # bad response removed


def test_session_timeout(tmp_path):
    p = llm.SessionProvider(tmp_path, poll_s=0.01)
    with pytest.raises(ModelError, match="model call timed out") as ei:
        asyncio.run(p.call("assess", "s", "u", AssessResult, "medium", 0.05))
    assert ei.value.attempts[-1].status == "timeout"
    assert (tmp_path / "assess.request.json").exists()


# ---- FixtureProvider and factory ---------------------------------------------------------

def test_fixture_provider(tmp_path):
    (tmp_path / "check.response.json").write_text(json.dumps(CHECKS.model_dump()))
    out = asyncio.run(llm.FixtureProvider(tmp_path).call("check", "s", "u", CheckResult,
                                                         "low", 1.0))
    assert out.parsed == CHECKS and out.attempt.mode == "FIXTURE"
    with pytest.raises(ModelError, match="fixture response missing"):
        asyncio.run(llm.FixtureProvider(tmp_path).call("extract", "s", "u", ExtractResult,
                                                       "low", 1.0))


def test_make_provider(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = llm.make_provider("auto", tmp_path)
    assert isinstance(p, llm.SessionProvider) and p.directory == tmp_path / "model"
    assert isinstance(llm.make_provider("fixture", tmp_path, tmp_path), llm.FixtureProvider)
    with pytest.raises(ConfigError):
        llm.make_provider("fixture", tmp_path, None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-key")
    assert isinstance(llm.make_provider("auto", tmp_path), llm.AnthropicProvider)


def test_warmup_lines(tmp_path):
    ext = ExtractResult(claims=[claim(quote="Example Startup raised a $1M pre-seed round")])
    asr = AssessResult(findings=[finding()])
    for name, obj in (("extract", ext), ("assess", asr), ("check", CHECKS)):
        (tmp_path / f"{name}.response.json").write_text(obj.model_dump_json())
    (tmp_path / "check.response.json").unlink()
    lines = asyncio.run(llm.warmup(llm.FixtureProvider(tmp_path)))
    assert lines[0].startswith("OK extract ") and "in=0 out=0" in lines[0]
    assert lines[1].startswith("OK assess ")
    assert lines[2].startswith("FAILED check ")
    for user in llm.warmup_messages().values():
        assert "example-startup.test" in user or "Example Startup" in user


# ---- local validation ----------------------------------------------------------------------

DOC_TEXT = ("Koah’s founders — Nic and Herrick — said the company "
            "raised a\n  $5M   seed round “to build ads”.")


def test_quote_span_normalizes_quotes_dashes_nbsp_whitespace():
    q = "Koah's founders - Nic and Herrick - said the company raised a $5M seed round \"to build ads\""
    span = llm.quote_span(DOC_TEXT, q)
    assert span is not None
    s, e = span
    assert DOC_TEXT[s:e].startswith("Koah’s") and DOC_TEXT[s:e].endswith("ads”")
    assert llm.quote_span(DOC_TEXT, "raised a $5M seed") == (DOC_TEXT.index("raised"),
                                                            DOC_TEXT.index(" round"))
    assert llm.quote_span(DOC_TEXT, "Raised a $5M seed") is None      # case-sensitive
    assert llm.quote_span(DOC_TEXT, "") is None


def test_local_validate_extract():
    docs = [Document(id="D1", source="pasted", text=DOC_TEXT)]
    res = ExtractResult(claims=[
        claim("C1", quote="raised a $5M seed round “to build ads”"),
        claim("C2", quote="Koah's founders – Nic"),
        claim("C3", quote="raised a $9M seed"),                       # not in the text
        claim("C4", doc="D9", quote="raised a $5M seed"),             # unknown document
        claim("C2", quote="raised a $5M seed"),                       # duplicate id
        claim("C5", quote="the company"),
        claim("C6", quote="Herrick", selected=False),
    ])
    out, lims = llm.local_validate_extract(res, docs, max_selected=2)
    ids = [c.id for c in out.claims]
    assert ids == ["C1", "C2", "C5", "C6"]
    sel = {c.id: (c.selected, c.exclusion_reason) for c in out.claims}
    assert sel["C1"] == (True, "") and sel["C2"] == (True, "")
    assert sel["C5"] == (False, "selection cap")
    assert sel["C6"][0] is False and sel["C6"][1]
    joined = " ".join(lims)
    assert "C3 dropped" in joined and "C4 dropped" in joined and "duplicate" in joined
    assert "selection cap of 2" in joined


def test_local_validate_assess_unknown_evidence():
    claims = [claim("C1"), claim("C2"), claim("C3"), claim("C4", selected=False)]
    res = AssessResult(findings=[
        finding("C2", ("E1", "E99")),
        finding("C1", ("G7",)),          # no valid ID left -> suppressed
        finding("C2", ("E1",)),          # extra
        finding("C9", ("E1",)),          # unknown claim
        finding("C4", ("E1",)),          # not selected
    ])
    v = llm.local_validate_assess(res, claims, {"E1", "G4"})
    assert [f.claim_id for f in v.result.findings] == ["C2"]
    assert v.result.findings[0].evidence_ids == ["E1"]
    assert [f.claim_id for f in v.suppressed] == ["C1"]
    joined = " ".join(v.limitations)
    assert "E99" in joined and "C1 suppressed" in joined and "C3" in joined
    assert "C9" in joined and "C4" in joined and "Extra finding for C2" in joined
