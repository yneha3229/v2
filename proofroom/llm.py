"""Model providers and local validation for the three calls (plan v2 §8.3, Prep_01, D15).

Providers share one interface, `Provider.call(...) -> ModelOutcome`:

- AnthropicProvider: the official SDK, `messages.parse()` with the §8.3 settings (LIVE).
- SessionProvider: writes `<name>.request.json` and waits for `<name>.response.json`, written by
  an agent session acting as the model (D15). Label SESSION.
- FixtureProvider: reads `<name>.response.json` at once (FIXTURE runs and tests).

Every failure raises `ModelCallError` (a `ModelError`) that carries the attempt records, so
failed attempts are kept (CLAUDE.md §3 honesty).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from proofroom import config
from proofroom.errors import ConfigError, ModelError
from proofroom.log import redact
from proofroom.models import (AssessResult, AttemptRecord, CheckResult, Claim, Document,
                              Evidence, ExtractResult, Finding)
from proofroom import prompts

log = logging.getLogger(__name__)

CALLS: dict[str, tuple[str, type[BaseModel], str]] = {
    "extract": (prompts.SYSTEM_EXTRACT, ExtractResult, "low"),
    "assess": (prompts.SYSTEM_ASSESS, AssessResult, "medium"),
    "check": (prompts.SYSTEM_CHECK, CheckResult, "low"),
}


# ---- outcomes and errors -----------------------------------------------------------

@dataclass
class ModelOutcome:
    parsed: BaseModel | None
    attempt: AttemptRecord                      # the last attempt
    stop_reason: str = ""
    attempts: list[AttemptRecord] = field(default_factory=list)   # all, failed ones included


class ModelCallError(ModelError):
    """A failed model stage, carrying every attempt made (kept in case.json)."""

    def __init__(self, message: str, attempts: list[AttemptRecord] | None = None,
                 stop_reason: str = ""):
        super().__init__(message)
        self.attempts = list(attempts or [])
        self.stop_reason = stop_reason


def make_attempt(stage: str, endpoint: str, mode: str, status: str, seconds: float,
                 input_tokens: int = 0, output_tokens: int = 0,
                 error: dict | None = None) -> AttemptRecord:
    """Build an AttemptRecord. "SESSION" is not yet in models.RunMode, so it bypasses validation."""
    data = dict(stage=stage, endpoint=endpoint, mode=mode, status=status,
                seconds=round(seconds, 3), credits_used="", input_tokens=int(input_tokens or 0),
                output_tokens=int(output_tokens or 0), error=error)
    try:
        return AttemptRecord(**data)
    except ValidationError:
        return AttemptRecord.model_construct(**data)


class Provider(Protocol):
    async def call(self, name: str, system: str, user: str, schema: type[BaseModel],
                   effort: str, timeout: float) -> ModelOutcome: ...


# ---- Anthropic SDK ---------------------------------------------------------------------

def _sdk_errors() -> tuple[Any, Any, Any]:
    """SDK exception classes, without importing the SDK when only a test client is in use."""
    sdk = sys.modules.get("anthropic")
    if sdk is None:
        return (), (), ()                       # `except ()` matches nothing
    return sdk.APITimeoutError, sdk.APIStatusError, sdk.APIConnectionError


class AnthropicProvider:
    """`client.messages.parse()` with the v2 §8.3 settings and nothing else.

    Never sends thinking, temperature, top_p, top_k, tool_choice, a prefill or citations.
    """

    mode = "LIVE"

    def __init__(self, model: str = config.MODEL, max_tokens: int = 12000, client: Any = None):
        self.model = model
        self.max_tokens = max_tokens
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            key = config.anthropic_key()
            if not key:
                raise ConfigError("ANTHROPIC_API_KEY is not set")
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=key, max_retries=0)
        return self._client

    async def call(self, name: str, system: str, user: str, schema: type[BaseModel],
                   effort: str, timeout: float) -> ModelOutcome:
        client = self._get_client()
        timeout_err, status_err, conn_err = _sdk_errors()
        stage = f"model:{name}"
        deadline = time.monotonic() + timeout
        attempts: list[AttemptRecord] = []
        last_stop = ""
        last_elapsed = 0.0
        for try_no in (1, 2):
            remaining = deadline - time.monotonic()
            if try_no == 2 and (remaining < 1.0 or remaining < last_elapsed):
                break                                       # no budget for the one retry
            t0 = time.monotonic()
            kwargs = dict(model=self.model, max_tokens=self.max_tokens, system=system,
                          messages=[{"role": "user", "content": user}],
                          output_format=schema, output_config={"effort": effort},
                          timeout=float(max(remaining, 0.001)))
            try:
                resp = await client.messages.parse(**kwargs)
            except timeout_err:
                attempts.append(make_attempt(stage, self.model, self.mode, "timeout",
                                             time.monotonic() - t0,
                                             error={"type": "timeout", "message": "model call timed out"}))
                raise ModelCallError("model call timed out", attempts)
            except status_err as exc:
                msg = redact(str(getattr(exc, "message", "") or exc))[:500]
                attempts.append(make_attempt(stage, self.model, self.mode, "error",
                                             time.monotonic() - t0,
                                             error={"type": "api_status",
                                                    "status": getattr(exc, "status_code", 0),
                                                    "message": msg}))
                raise ModelCallError(f"model API error {getattr(exc, 'status_code', '?')}: {msg}",
                                     attempts)
            except conn_err as exc:
                attempts.append(make_attempt(stage, self.model, self.mode, "error",
                                             time.monotonic() - t0,
                                             error={"type": "network",
                                                    "message": redact(str(exc))[:500]}))
                raise ModelCallError("model API connection failed", attempts)
            except (ValidationError, ValueError) as exc:     # truncated or invalid JSON
                last_elapsed = time.monotonic() - t0
                attempts.append(make_attempt(stage, self.model, self.mode, "invalid_output",
                                             last_elapsed,
                                             error={"type": "invalid_output",
                                                    "message": redact(str(exc))[:500]}))
                continue

            last_elapsed = time.monotonic() - t0
            last_stop = str(getattr(resp, "stop_reason", "") or "")
            usage = getattr(resp, "usage", None)
            tin = getattr(usage, "input_tokens", 0) or 0
            tout = getattr(usage, "output_tokens", 0) or 0
            parsed = getattr(resp, "parsed_output", None)

            if last_stop == "refusal":
                details = getattr(resp, "stop_details", None)
                category = (details.get("category") if isinstance(details, dict)
                            else getattr(details, "category", None))
                attempts.append(make_attempt(stage, self.model, self.mode, "refusal", last_elapsed,
                                             tin, tout, error={"type": "refusal",
                                                               "category": category or ""}))
                raise ModelCallError(f"model refused ({category or 'no category'})", attempts,
                                     last_stop)
            if last_stop == "end_turn" and parsed is not None:
                attempt = make_attempt(stage, self.model, self.mode, "ok", last_elapsed, tin, tout)
                attempts.append(attempt)
                return ModelOutcome(parsed, attempt, last_stop, attempts)
            if last_stop == "max_tokens":
                attempts.append(make_attempt(stage, self.model, self.mode, "max_tokens",
                                             last_elapsed, tin, tout,
                                             error={"type": "max_tokens",
                                                    "message": "stopped at max_tokens"}))
                continue                                    # one retry if budget allows
            attempts.append(make_attempt(stage, self.model, self.mode, "failed", last_elapsed,
                                         tin, tout, error={"type": "bad_stop",
                                                           "stop_reason": last_stop,
                                                           "parsed": parsed is not None}))
            raise ModelCallError(f"model call failed (stop_reason={last_stop or 'none'})",
                                 attempts, last_stop)
        raise ModelCallError(f"model call failed after {len(attempts)} attempt(s): "
                             f"{attempts[-1].status if attempts else 'no attempt'}",
                             attempts, last_stop)


# ---- file-based providers (session and fixture) ------------------------------------------

def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def parse_response(raw: str, schema: type[BaseModel]) -> BaseModel:
    """Parse a response file: the bare schema object, or {"output": {...}}.

    Raises ValueError (bad JSON) or ValidationError (schema mismatch).
    """
    data = json.loads(raw)
    if (isinstance(data, dict) and set(data) == {"output"}
            and "output" not in schema.model_fields):
        data = data["output"]
    return schema.model_validate(data)


def _describe_errors(exc: Exception) -> list[dict]:
    if isinstance(exc, ValidationError):
        return [{"loc": ".".join(str(p) for p in e["loc"]), "msg": e["msg"], "type": e["type"]}
                for e in exc.errors()]
    return [{"loc": "", "msg": str(exc), "type": "json_invalid"}]


class SessionProvider:
    """The model is an agent session answering request files (D15)."""

    mode = "SESSION"

    def __init__(self, directory: Path, poll_s: float = 1.0):
        self.directory = Path(directory)
        self.poll_s = poll_s

    def paths(self, name: str) -> tuple[Path, Path, Path]:
        d = self.directory
        return (d / f"{name}.request.json", d / f"{name}.response.json", d / f"{name}.error.json")

    async def call(self, name: str, system: str, user: str, schema: type[BaseModel],
                   effort: str, timeout: float) -> ModelOutcome:
        req_path, resp_path, err_path = self.paths(name)
        stage = f"model:{name}"
        for stale in (resp_path, err_path):         # an answer must be to this request
            stale.unlink(missing_ok=True)
        now = datetime.now(timezone.utc)
        _atomic_write_json(req_path, {
            "name": name, "system": system, "user": user,
            "schema": schema.model_json_schema(), "effort": effort,
            "created_at": now.isoformat(timespec="seconds"),
            "timeout_s": timeout,
            "response_file": resp_path.name,
            "response_format": "the JSON object matching `schema`, or {\"output\": <that object>}",
        })
        t0 = time.monotonic()
        deadline = t0 + timeout
        attempts: list[AttemptRecord] = []
        invalid_seen = 0
        while True:
            if resp_path.exists():
                try:
                    raw = resp_path.read_text(encoding="utf-8")
                    parsed = parse_response(raw, schema)
                except FileNotFoundError:
                    parsed = None
                except (ValueError, ValidationError) as exc:
                    if not isinstance(exc, ValidationError) and self._maybe_writing(resp_path):
                        parsed = None                       # still being written; look again
                    else:
                        invalid_seen += 1
                        errors = _describe_errors(exc)
                        attempts.append(make_attempt(stage, "session", self.mode, "invalid_output",
                                                     time.monotonic() - t0,
                                                     error={"type": "invalid_output",
                                                            "errors": errors[:50]}))
                        _atomic_write_json(err_path, {
                            "name": name, "attempt": invalid_seen,
                            "message": (f"{resp_path.name} did not validate against the "
                                        f"{schema.__name__} schema in {req_path.name}. "
                                        + ("Fix it and write the file again before the timeout."
                                           if invalid_seen == 1 else "No more attempts.")),
                            "errors": errors,
                            "written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        })
                        if invalid_seen >= 2:
                            raise ModelCallError(
                                f"session response for {name} is invalid twice: "
                                f"{len(errors)} error(s), see {err_path.name}", attempts)
                        resp_path.unlink(missing_ok=True)
                        parsed = None
                else:
                    attempt = make_attempt(stage, "session", self.mode, "ok",
                                           time.monotonic() - t0)
                    attempts.append(attempt)
                    return ModelOutcome(parsed, attempt, "end_turn", attempts)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                attempts.append(make_attempt(stage, "session", self.mode, "timeout",
                                             time.monotonic() - t0,
                                             error={"type": "timeout",
                                                    "message": "model call timed out",
                                                    "invalid_responses": invalid_seen}))
                msg = "model call timed out"
                if invalid_seen:
                    msg += f" (after an invalid response, see {err_path.name})"
                raise ModelCallError(msg, attempts)
            await asyncio.sleep(min(self.poll_s, remaining))

    def _maybe_writing(self, path: Path) -> bool:
        """True if the file changed within the last two poll intervals (a partial write)."""
        try:
            age = time.time() - path.stat().st_mtime
        except FileNotFoundError:
            return True
        return age < 2 * self.poll_s


class FixtureProvider:
    """Replays `<dir>/<name>.response.json` at once. Label FIXTURE."""

    mode = "FIXTURE"

    def __init__(self, directory: Path):
        self.directory = Path(directory)

    async def call(self, name: str, system: str, user: str, schema: type[BaseModel],
                   effort: str, timeout: float) -> ModelOutcome:
        path = self.directory / f"{name}.response.json"
        stage = f"model:{name}"
        t0 = time.monotonic()
        try:
            parsed = parse_response(path.read_text(encoding="utf-8"), schema)
        except FileNotFoundError:
            att = make_attempt(stage, "fixture", self.mode, "missing", time.monotonic() - t0,
                               error={"type": "fixture_missing", "message": str(path.name)})
            raise ModelCallError(f"fixture response missing: {path}", [att])
        except (ValueError, ValidationError) as exc:
            att = make_attempt(stage, "fixture", self.mode, "invalid_output",
                               time.monotonic() - t0,
                               error={"type": "invalid_output", "errors": _describe_errors(exc)[:50]})
            raise ModelCallError(f"fixture response invalid: {path.name}", [att])
        att = make_attempt(stage, "fixture", self.mode, "ok", time.monotonic() - t0)
        return ModelOutcome(parsed, att, "end_turn", [att])


def make_provider(kind: str, run_dir: Path, fixture_dir: Path | None = None) -> Provider:
    """kind: session | anthropic | fixture | auto (anthropic if a key is set, else session).

    The session provider uses `<run_dir>/model/`; the fixture provider reads `fixture_dir`.
    """
    kind = (kind or "auto").lower()
    if kind == "auto":
        kind = "anthropic" if config.anthropic_key() else "session"
    if kind == "anthropic":
        if not config.anthropic_key():
            raise ConfigError("ANTHROPIC_API_KEY is not set")
        return AnthropicProvider()
    if kind == "session":
        return SessionProvider(Path(run_dir) / "model")
    if kind == "fixture":
        if fixture_dir is None:
            raise ConfigError("fixture provider needs a fixture directory")
        return FixtureProvider(Path(fixture_dir))
    raise ConfigError(f"unknown model provider: {kind}")


async def run_call(provider: Provider, name: str, user: str, timeout: float,
                   effort: str | None = None) -> ModelOutcome:
    """Call `name` with its system prompt, schema and default effort (CALLS)."""
    system, schema, default_effort = CALLS[name]
    return await provider.call(name, system, user, schema, effort or default_effort, timeout)


# ---- local validation (Prep_01) ---------------------------------------------------------

_CHAR_MAP = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-",
    "−": "-",
    "…": "...",
}
_DROP = {"​", "‌", "‍", "⁠", "﻿", "­"}


def _normalize_map(text: str) -> tuple[str, list[int]]:
    """Normalized text and, per normalized char, its index in the original text.

    Unicode quotes and dashes become ASCII, NBSP and every whitespace run become one space,
    zero-width characters are removed. Case is kept.
    """
    out: list[str] = []
    idx: list[int] = []
    in_space = False
    for i, ch in enumerate(text):
        if ch in _DROP:
            continue
        if ch.isspace():                        # includes NBSP, U+202F, U+2009
            if not in_space:
                out.append(" ")
                idx.append(i)
                in_space = True
            continue
        in_space = False
        rep = _CHAR_MAP.get(ch, ch)
        for r in rep:
            out.append(r)
            idx.append(i)
    return "".join(out), idx


def normalize_text(text: str) -> str:
    return _normalize_map(text)[0].strip()


def quote_span(doc_text: str, quote: str) -> tuple[int, int] | None:
    """(start, end) of `quote` in the ORIGINAL `doc_text`, matched after normalization."""
    needle = normalize_text(quote)
    if not needle:
        return None
    hay, idx = _normalize_map(doc_text)
    pos = hay.find(needle)
    if pos < 0:
        return None
    return idx[pos], idx[pos + len(needle) - 1] + 1


def local_validate_extract(result: ExtractResult, documents: list[Document],
                           max_selected: int = prompts.DEFAULT_MAX_SELECTED
                           ) -> tuple[ExtractResult, list[str]]:
    """Prep_01 call-1 checks. Returns the cleaned result and limitation strings."""
    docs = {d.id: d for d in documents}
    limitations: list[str] = []
    seen: set[str] = set()
    kept: list[Claim] = []
    for claim in result.claims:
        if claim.id in seen:
            limitations.append(f"Claim {claim.id} dropped: duplicate claim ID.")
            continue
        seen.add(claim.id)
        doc = docs.get(claim.doc_id)
        if doc is None:
            limitations.append(f"Claim {claim.id} dropped: document {claim.doc_id!r} "
                               "is not in the packet.")
            continue
        if quote_span(doc.text, claim.quote) is None:
            limitations.append(f"Claim {claim.id} dropped: its quote is not a verbatim passage "
                               f"of {claim.doc_id}.")
            continue
        kept.append(claim)

    out: list[Claim] = []
    n_selected = 0
    for claim in kept:
        if claim.selected:
            if n_selected < max_selected:
                n_selected += 1
                out.append(claim.model_copy(update={"exclusion_reason": ""}))
            else:
                out.append(claim.model_copy(update={"selected": False,
                                                    "exclusion_reason": "selection cap"}))
        else:
            reason = claim.exclusion_reason.strip() or "not selected (no reason given)"
            out.append(claim.model_copy(update={"exclusion_reason": reason}))
    demoted = sum(1 for c in kept if c.selected) - n_selected
    if demoted:
        limitations.append(f"{demoted} selected claim(s) moved to Not checked by the "
                           f"selection cap of {max_selected}.")
    return ExtractResult(claims=out), limitations


@dataclass
class AssessValidation:
    result: AssessResult                  # findings that passed, in claim order
    limitations: list[str]
    suppressed: list[Finding]             # findings left with no valid evidence ID


def local_validate_assess(result: AssessResult, claims: list[Claim],
                          evidence_ids: set[str] | list[str]) -> AssessValidation:
    """Prep_01 call-2 checks: one finding per selected claim; cited evidence IDs must exist."""
    order = [c.id for c in claims if c.selected]
    wanted = set(order)
    known = set(evidence_ids)
    limitations: list[str] = []
    suppressed: list[Finding] = []
    by_claim: dict[str, Finding] = {}
    for f in result.findings:
        if f.claim_id not in wanted:
            limitations.append(f"Finding for {f.claim_id!r} dropped: not a selected claim.")
            continue
        if f.claim_id in by_claim:
            limitations.append(f"Extra finding for {f.claim_id} dropped: one finding per claim.")
            continue
        unknown = [e for e in f.evidence_ids if e not in known]
        valid = [e for e in dict.fromkeys(f.evidence_ids) if e in known]
        if unknown:
            limitations.append(f"Finding {f.claim_id}: unknown evidence ID(s) "
                               f"{', '.join(unknown)} removed.")
        if not valid:
            limitations.append(f"Finding {f.claim_id} suppressed: it cites no evidence "
                               "that exists in this run.")
            suppressed.append(f)
            by_claim[f.claim_id] = None  # type: ignore[assignment]  # counted, not kept
            continue
        by_claim[f.claim_id] = f.model_copy(update={"evidence_ids": valid})
    for cid in order:
        if cid not in by_claim:
            limitations.append(f"Claim {cid}: the assessment returned no finding.")
    findings = [by_claim[c] for c in order if by_claim.get(c) is not None]
    return AssessValidation(AssessResult(findings=findings), limitations, suppressed)


# ---- warm-up ---------------------------------------------------------------------------

_WARM_DOC = Document(
    id="D1", source="https://example-startup.test/blog/pre-seed", published="2026-01-15",
    text=("Example Startup raised a $1M pre-seed round led by Example Ventures, "
          "the company said. Alex Example, CEO & Co-founder, wrote the post."))
_WARM_CLAIM = Claim(
    id="C1", doc_id="D1", quote="Example Startup raised a $1M pre-seed round", family="F3",
    predicate="raised_round", subject="Example Startup", object="", amount_text="$1M",
    currency_text="$", date_text="", title_text="", qualifiers="", materiality="high",
    selected=True, exclusion_reason="")
_WARM_EVIDENCE = Evidence(
    id="E1", kind="source_passage", source=_WARM_DOC.source, locator="D1:0-43",
    value="Example Startup raised a $1M pre-seed round led by Example Ventures",
    subject_basis="domain match", origin="O1 (company)", published="2026-01-15")


def warmup_messages() -> dict[str, str]:
    """Tiny SYNTHETIC inputs (never a real or unseen company) for each call."""
    return {
        "extract": prompts.extract_message("Example Startup", "example-startup.test", "",
                                           [_WARM_DOC], ""),
        "assess": prompts.assess_message("Example Startup", "example-startup.test", "",
                                         "2026-10-31", [_WARM_CLAIM], [_WARM_EVIDENCE], ""),
        "check": prompts.check_message([("C1", "Example Startup's post says it raised a $1M "
                                         "pre-seed round.", [_WARM_EVIDENCE])]),
    }


async def warmup(provider: Provider, timeout: float = 180.0) -> list[str]:
    """Send each schema once; return print-ready OK/FAILED lines."""
    lines: list[str] = []
    for name, user in warmup_messages().items():
        try:
            out = await run_call(provider, name, user, timeout)
        except ModelError as exc:
            lines.append(f"FAILED {name} {redact(str(exc))}")
            continue
        a = out.attempt
        lines.append(f"OK {name} {a.seconds:.1f}s in={a.input_tokens} out={a.output_tokens}")
    return lines
