"""The run pipeline (plan v2 §8.2), with independent stages run concurrently.

Stage order and concurrency:
  2 Resolve (Identify -> Company Enrich [-> S1 fallback])  ||  Mode B URL fetch
  1 Packet (Mode A picks from `news[]`, one fetch request)
  3 Call 1 extract + local validation
  4 Gap resolution: Identify(names) for prior employers and leads (free)  || evidence table
  5 Call 2 assess + local validation
  6 Code gate, then call 3 check
  7 Render and publish (write once, read back, hash, manifest)

Profiles: FULL follows the plan. FAST (D18) runs every stage and keeps the code
gate in full, but uses low effort on all calls, <=2 pages and <=3 claims, and skips
optional extra retrieval. Every output is labelled with its run mode, model
source and profile.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from proofroom import config, exceptions, gate, graph, llm, packet, prompts, render, report, store
from proofroom import equity_report, scoring, signals
from proofroom import crustdata as cd
from proofroom.errors import ConfigError, CrustError, ModelError, ProofroomError, StoreError
from proofroom.models import (AssessResult, AttemptRecord, CaseRecord, CheckResult, Claim,
                              Document, Evidence, ExtractResult, RunInput, TeamRow)

log = logging.getLogger(__name__)

FULL, FAST = "FULL", "FAST"


@dataclass(frozen=True)
class Profile:
    name: str
    max_urls: int
    max_selected: int
    effort_extract: str
    effort_assess: str
    effort_check: str
    retrieval_deadline_s: float  # no new retrieval after this (§9: 55 s)
    hard_stop_s: float


PROFILES = {
    FULL: Profile(FULL, 3, 5, "low", "medium", "low", 55.0, 110.0),
    FAST: Profile(FAST, 2, 3, "low", "low", "low", 30.0, 60.0),
}

# Session-provider calls are answered by an agent, so they get their own timeout.
SESSION_MODEL_TIMEOUT_S = 900.0


@dataclass
class RunRequest:
    domain: str
    input_mode: str = "A"            # A: domain only, B: packet (paste and/or URLs)
    run_mode: str = cd.CACHED        # LIVE | CACHED | FIXTURE
    profile: str = FULL              # FULL | FAST
    provider: str = "auto"           # session | anthropic | fixture | auto
    focus_note: str = ""
    urls: list[str] = field(default_factory=list)
    pasted: list[str] = field(default_factory=list)
    sentence: str = ""               # U5 one-sentence check (implies Mode B)
    fixture: str = ""
    email: bool | None = None        # U8 founder email draft; None = config default (off)
    research: bool = True            # D24 equity-research report (signals + rating + PDF)
    check_size_usd: float = 100_000.0  # the reader's standard ticket, for suggested sizing

    def normalized(self) -> "RunRequest":
        r = RunRequest(**{**self.__dict__})
        r.domain = cd._clean(r.domain)
        r.profile = r.profile.upper()
        r.run_mode = r.run_mode.upper()
        if r.profile not in PROFILES:
            raise ValueError(f"profile must be FULL or FAST, got {self.profile!r}")
        if r.run_mode not in cd.MODES:
            raise ValueError(f"run mode must be one of {cd.MODES}")
        if r.run_mode == cd.FIXTURE and not r.fixture:
            raise ValueError("FIXTURE runs need a fixture name")
        if r.sentence.strip():
            r.input_mode = "B"
            r.pasted = [r.sentence.strip()]
            r.focus_note = r.focus_note or "Check only this one sentence."
        if r.input_mode == "B" and not (r.pasted or r.urls):
            raise ValueError("Mode B needs pasted text or URLs")
        if r.provider == "fixture" and r.run_mode != cd.FIXTURE:
            raise ValueError("the fixture model provider is only for FIXTURE runs")
        return r

    def as_input(self) -> RunInput:
        return RunInput(domain=self.domain, input_mode=self.input_mode,  # type: ignore[arg-type]
                        run_mode=self.run_mode, focus_note=self.focus_note,  # type: ignore[arg-type]
                        urls=list(self.urls), pasted=list(self.pasted), fixture=self.fixture)


@dataclass
class RunOutcome:
    status: str                      # DELIVERED | NARROWED | FAILED
    run_dir: Path | None
    case: CaseRecord | None
    brief: str = ""
    error: str = ""
    seconds: float = 0.0


Progress = Callable[[str, dict], Awaitable[None] | None]


class _Run:
    """State for one run; methods are the stages."""

    def __init__(self, req: RunRequest, st: store.Store, on_progress: Progress | None):
        self.req = req
        self.prof = PROFILES[req.profile]
        self.store = st
        self.on_progress = on_progress
        self.t0 = time.monotonic()
        self.limitations: list[str] = []
        self.not_checked: list[str] = []
        self.questions: list[str] = []
        self.injection_notes: list[str] = []
        self.model_attempts: list[AttemptRecord] = []
        self.log_lines: list[str] = []
        self.client: cd.Crustdata | None = None

    # ---- helpers -----------------------------------------------------------
    def elapsed(self) -> float:
        return round(time.monotonic() - self.t0, 2)

    async def progress(self, stage: str, **payload: Any) -> None:
        self.log_lines.append(f"{self.elapsed():6.2f}s {stage}")
        log.info("stage %s at %.2fs", stage, self.elapsed())
        if self.on_progress:
            res = self.on_progress(stage, {"elapsed": self.elapsed(), **payload})
            if asyncio.iscoroutine(res):
                await res

    def model_timeout(self, provider: Any) -> float:
        if isinstance(provider, llm.SessionProvider):
            return SESSION_MODEL_TIMEOUT_S
        left = self.prof.hard_stop_s - (time.monotonic() - self.t0) - 3
        return max(10.0, left)

    async def call_model(self, provider: Any, name: str, system: str, user: str,
                         schema: type, effort: str) -> Any:
        t_call = time.monotonic()
        try:
            out = await provider.call(name, system, user, schema, effort,
                                      self.model_timeout(provider))
        except ModelError as e:
            self.model_attempts += list(getattr(e, "attempts", None) or [])
            raise
        finally:
            # An agent answering request files is not retrieval time (D15): give the
            # retrieval deadline back what the wait took.
            if isinstance(provider, llm.SessionProvider) and self.client is not None \
                    and self.client.deadline is not None:
                self.client.deadline += time.monotonic() - t_call
        self.model_attempts += list(getattr(out, "attempts", None) or [out.attempt])
        if out.parsed is None:
            raise ModelError(f"{name}: {out.stop_reason or 'no parsed output'}")
        return out.parsed


async def run(req: RunRequest, *, st: store.Store | None = None,
              on_progress: Progress | None = None) -> RunOutcome:
    """Run one request end to end. Never raises for expected failures: a FAILED
    outcome carries the error, and its attempts are kept in `failed.json`."""
    try:
        req = req.normalized()
    except ValueError as e:
        return RunOutcome("FAILED", None, None, error=str(e))
    st = st or store.Store()
    case_id = store.case_id_for(req.domain)
    lock = store.case_lock(case_id)
    if lock.locked():
        return RunOutcome("FAILED", None, None, error=f"a run for {case_id} is already active")
    with lock:
        existing = st.recent_identical(case_id, req.as_input().model_dump())
        if existing and req.run_mode != cd.FIXTURE:  # FIXTURE replays are free; always rerun
            case = CaseRecord.model_validate_json((existing.path / "case.json").read_text())
            return RunOutcome(case.status, existing.path, case,
                              (existing.path / "brief.md").read_text(encoding="utf-8"))
        rd = st.new_run(case_id)
        r = _Run(req, st, on_progress)
        try:
            return await _execute(r, rd)
        except (ProofroomError, OSError) as e:
            log.error("run %s run-%d failed: %s", case_id, rd.run, e)
            _write_failed(rd, r, e)
            return RunOutcome("FAILED", rd.path, None, error=str(e), seconds=r.elapsed())


async def _execute(r: _Run, rd: store.RunDir) -> RunOutcome:
    req, prof = r.req, r.prof
    provider = llm.make_provider(req.provider, rd.path,
                                 config.FIXTURES_DIR / req.fixture / "model" if req.fixture else None)
    model_source = _provider_label(provider)
    deadline = r.t0 + prof.retrieval_deadline_s
    client = cd.Crustdata(req.run_mode, fixture=req.fixture, deadline=deadline,
                          use_cache=req.run_mode != cd.LIVE)
    r.client = client
    async with client:
        await r.progress("start", domain=req.domain, profile=prof.name, mode=req.run_mode,
                         run_dir=str(rd.path), run=rd.run, model_source=model_source)

        # Stage 2 resolve || Mode B fetch (independent).
        mode_b = (packet.assemble_mode_b(client, req.pasted, req.urls, domain=req.domain)
                  if req.input_mode == "B" else _none())
        g, pk_b = await asyncio.gather(graph.resolve(client, req.domain), mode_b)
        r.limitations += g.limitations
        await r.progress("identity", g1=g.g1.as_dict(), team=[t.name for t in g.team])
        # D24: investor signals run in parallel with the packet, call 1 and stage 4.
        sig_task = (asyncio.create_task(_signals(client, g, req, r.limitations))
                    if req.research and g.g1.company_id is not None else None)

        # Stage 1 packet (Mode A needs `news[]` from the enrich record).
        if req.input_mode == "A":
            if g.g1.company_id is None:
                pk = packet.PacketResult(documents=[], picks=[], excluded=[], failed_urls=[],
                                         limitations=["No packet: company identity unresolved"],
                                         injection_notes=[])
            else:
                pk = await packet.assemble_mode_a(client, g.g1, g.news, g.financing,
                                                  max_urls=prof.max_urls)
        else:
            pk = pk_b
        r.limitations += pk.limitations
        r.injection_notes = list(pk.injection_notes)
        docs: list[Document] = pk.documents
        await r.progress("packet", documents=[{"id": d.id, "source": d.source,
                                               "title": d.title} for d in docs],
                         injection_notes=len(r.injection_notes))

        # Stage 3 call 1.
        claims: list[Claim] = []
        if docs:
            ext = await r.call_model(provider, "extract", prompts.SYSTEM_EXTRACT,
                                     prompts.extract_message(g.g1.name or req.domain, req.domain,
                                                             g.g1.company_id, docs, req.focus_note,
                                                             max_selected=prof.max_selected),
                                     ExtractResult, prof.effort_extract)
            ext, lims = llm.local_validate_extract(ext, docs, prof.max_selected)
            r.limitations += lims
            claims = ext.claims
        else:
            r.limitations.append("No source documents: the brief reports Crustdata's record only")
        selected = [c for c in claims if c.selected]
        r.not_checked += _dedupe([f"{c.id}: \"{' '.join(c.quote.split())}\" "
                                  f"({c.exclusion_reason or 'not selected'})"
                                  for c in claims if not c.selected])
        await r.progress("claims", claims=[c.model_dump() for c in claims])

        # Stage 4 gap resolution (free Identify by names) || evidence table.
        names = _prior_employer_names(selected)
        cands_task = (_names_lookup(client, names + _lead_names(selected), r.limitations)
                      if names or _lead_names(selected) else _none({}))
        cands = await cands_task
        for row in g.team:
            row.prior_joins = graph.prior_joins(row, names, cands) if names else []
        evidence = _passage_evidence(docs, selected, req.domain) + graph.graph_evidence(
            g.g1, g.team, g.financing or {"milestones": [], "total_investment_usd": None,
                                          "record_refresh": "unknown", "total_is_capital": False})
        financing_lines = _financing_lines(g, selected, evidence, r.questions)
        sig = await sig_task if sig_task is not None else None

    # Stage 5 call 2 (no more retrieval from here on).
    findings = []
    if selected:
        ass = await r.call_model(provider, "assess", prompts.SYSTEM_ASSESS,
                                 prompts.assess_message(g.g1.name or req.domain, req.domain,
                                                        g.g1.company_id, _today(), selected,
                                                        evidence, _team_matrix(g.team, g.g1)),
                                 AssessResult, prof.effort_assess)
        ass, lims = _validate_assess(ass, selected, evidence)
        r.limitations += lims
        findings = ass.findings
    await r.progress("assessed", findings=len(findings))

    # Stage 6 code gate, then call 3.
    kept, suppressed, lims = gate.gate_findings(findings, evidence)
    r.limitations += lims
    checks = []
    withheld_n = 0
    if kept:
        by_id = {e.id: e for e in evidence}
        items = [(f.claim_id, f.sentence, [by_id[i] for i in f.evidence_ids if i in by_id])
                 for f in kept]
        chk = await r.call_model(provider, "check", prompts.SYSTEM_CHECK,
                                 prompts.check_message(items), CheckResult, prof.effort_check)
        checks = chk.checks
        kept, withheld = _apply_checks(kept, checks, r.limitations)
        withheld_n = len(withheld)
        # A withheld sentence's question survives only if its own numbers pass the gate.
        by_id = {e.id: e for e in evidence}
        for f in withheld:
            if f.question and gate.gate_sentence(f.question, f.evidence_ids, by_id).passed:
                r.questions.append(f.question)
    await r.progress("checked", kept=len(kept), suppressed=len(suppressed))

    # Stage 7 render and publish.
    status = "DELIVERED"
    if g.g1.status != graph.MATCHED or not docs:
        status = "NARROWED"
    credits, unknown = cd.sum_credits(client.attempts)
    case = CaseRecord(
        case_id=rd.case_id, run=rd.run, status=status, run_mode=req.run_mode,  # type: ignore
        input=req.as_input(), reviewed=_today(), g1=g.g1.as_dict(), documents=docs,
        evidence=evidence, claims=claims, findings=kept, checks=checks, team=g.team,
        financing=financing_lines, questions=_dedupe(r.questions), not_checked=_dedupe(r.not_checked),
        limitations=_dedupe(r.limitations),
        attempts=[_crust_attempt(a) for a in client.attempts] + r.model_attempts,
        stats={"profile": prof.name, "model_source": model_source, "seconds": r.elapsed(),
               "crustdata_credits": credits, "credits_unknown_attempts": unknown,
               "input_tokens": sum(a.input_tokens for a in r.model_attempts),
               "output_tokens": sum(a.output_tokens for a in r.model_attempts),
               "sentences_emitted": len(kept), "sentences_suppressed": len(suppressed) + withheld_n,
               "team_rows": len(g.team),
               "id_joins": sum(t.role_join for t in g.team)
               + sum(j.joined for t in g.team for j in t.prior_joins),
               "agent_instructions_ignored": len(r.injection_notes),
               "packet_picks": [p.get("url") for p in pk.picks],
               "excluded_sources": len(pk.excluded),
               "stage_log": r.log_lines})
    desk = exceptions.exception_desk(case)
    case.stats["needs_a_person"] = len(desk)
    case.stats["exceptions"] = [d.as_dict() for d in desk]
    brief = _with_desk(render.brief_md(case, model_source=model_source, profile=prof.name),
                       exceptions.exception_desk_md(desk))
    extra: dict[str, str | bytes] = {"questions.md": render.questions_md(case),
                                     "report.md": report.report_md(case),
                                     "report.html": report.report_html(case)}
    if sig is not None:
        extra.update(_research(case, sig, req, r))
    if req.email if req.email is not None else config.founder_email_enabled():
        extra["founder_email.md"] = exceptions.founder_email_md(case)
    st = r.store
    st.publish(rd, req.as_input().model_dump(), case.model_dump(mode="json"), brief,
               run_status=status, extra=extra)
    await r.progress("published", status=status, run=rd.run)
    return RunOutcome(status, rd.path, case, brief, seconds=r.elapsed())


# ---- stage helpers ------------------------------------------------------------------

async def _none(value: Any = None) -> Any:
    return value


async def _names_lookup(client: cd.Crustdata, names: list[str],
                        limitations: list[str]) -> dict[str, set[int]]:
    try:
        return graph.name_candidates(await client.identify_names(_dedupe(names)))
    except CrustError as e:
        if e.fatal:
            raise
        limitations.append(f"Name lookup for prior employers and leads failed "
                           f"({e.status} {e.type}); those joins are unchecked")
        return {}


_SPLIT = re.compile(r"\s*(?:,|;|&|\band\b)\s*", re.I)


def _prior_employer_names(claims: list[Claim]) -> list[str]:
    names: list[str] = []
    for c in claims:
        if c.predicate == "previously_worked_at" and c.object:
            names += [n.strip(" .") for n in _SPLIT.split(c.object) if n.strip(" .")]
    return _dedupe(names)[:20]


_ROUNDISH = re.compile(r"\b(round|series|seed|funding|financing|tender)\b", re.I)


def _lead_of(c: Claim) -> str:
    """The investor in a led_round claim: `object` by contract, but tolerate a swap."""
    for cand in (c.object, c.subject):
        cand = (cand or "").strip()
        if cand and not _ROUNDISH.search(cand):
            return cand
    return ""


def _lead_names(claims: list[Claim]) -> list[str]:
    return _dedupe([n for n in (_lead_of(c) for c in claims if c.predicate == "led_round")
                    if n])[:5]


def _passage_evidence(docs: list[Document], claims: list[Claim], domain: str) -> list[Evidence]:
    """One E-row per distinct quoted passage, with the surrounding sentence as excerpt."""
    by_doc = {d.id: d for d in docs}
    rows: list[Evidence] = []
    seen: dict[tuple[str, str], str] = {}
    for c in claims:
        d = by_doc.get(c.doc_id)
        if d is None or (c.doc_id, c.quote) in seen:
            continue
        span = llm.quote_span(d.text, c.quote)
        excerpt = _context(d.text, span) if span else c.quote
        eid = f"E{len(rows) + 1}"
        seen[(c.doc_id, c.quote)] = eid
        rows.append(Evidence(
            id=eid, kind="source_passage", source=d.source,
            locator=f"{d.id}[{span[0]}:{span[1]}]" if span else d.id, value=excerpt,
            subject_basis=("domain match" if domain in d.source else
                           "company named in the passage" if d.source != "pasted" else
                           "user-supplied document"),
            origin=d.origin or "unknown", published=d.published, updated=d.updated,
            retrieved=d.retrieved))
    return rows


_SENTENCE_END = re.compile(r"[.!?][\"”’)]?\s+(?=[A-Z\"“])|\n")


def _context(text: str, span: tuple[int, int], width: int = 420) -> str:
    """The quoted span with its sentence: start after the previous sentence end (or a
    word boundary within `width`), end at the next full stop (or `width` past the span)."""
    a, b = span
    lo = max(0, a - width)
    window = text[lo:a]
    ends = list(_SENTENCE_END.finditer(window))  # "Feb. 24" is not a sentence end
    if ends:
        start = lo + ends[-1].end()
    elif lo == 0:
        start = 0
    else:
        sp = window.find(" ")
        start = lo + sp + 1 if sp >= 0 else a
    m = _SENTENCE_END.search(text, b, min(len(text), b + width))
    end = m.start() + 1 if m else min(len(text), b + width)
    return " ".join(text[start:end].split())


def _team_matrix(team: list[TeamRow], g1: graph.G1Result) -> str:
    if not team:
        return "(no people found in Crustdata's graph)"
    lines = []
    for t in team:
        cur = "; ".join(f"{e.employer_name} {e.employer_id} \"{e.title}\" since {e.start or '?'}"
                        for e in t.current_at_subject) or "no current entry at the subject"
        mark = "✔" if t.role_join else "?"
        joins = "; ".join(
            f"{j.employer_name}: {'✔ ID ' + str(j.employer_id) if j.basis == 'id' else '≈ name match ' + str(j.employer_id) if j.basis == 'name_match' else '?'}"
            for j in t.prior_joins) or "none requested"
        past = "; ".join(f"{e.employer_name} ({e.employer_id}) \"{e.title}\" {e.start or '?'}-{e.end or '?'}"
                         for e in t.past[:12])
        lines.append(f"{t.name} (person {t.person_id}, profile updated {t.updated_at or 'unknown'}) | "
                     f"current at {g1.name} {g1.company_id}: {cur} {mark} | prior-employer joins: "
                     f"{joins} | indexed past roles: {past or 'none'}")
    return "\n".join(lines)


def _financing_lines(g: graph.GraphResult, claims: list[Claim], evidence: list[Evidence],
                     questions: list[str]) -> list[dict]:
    """Deterministic G4 lines, each citing graph evidence by ID (§7, PC-2)."""
    fin = g.financing
    if not fin:
        return []
    by_loc = {e.locator: e.id for e in evidence if e.kind == "graph"}
    lines: list[dict] = []
    for c in claims:
        if c.predicate not in ("raised_round", "led_round") or c.family != "F3":
            continue
        rtype = _round_type(c.quote + " " + c.object)
        if not rtype:
            continue
        amounts = [a for a in gate.parse_amounts(c.amount_text or c.quote) if a.currency == "USD"]
        lead = _lead_of(c) if c.predicate == "led_round" else ""
        m = graph.match_round(fin, rtype, amounts[0].value if amounts else None,
                              _iso_from_text(c.date_text), lead)
        if m["status"] == "not_in_record":
            lines.append({"kind": "round_check", "claim_id": c.id, "evidence_ids": [],
                          "line": f"{c.id}: {m['note']}."})
            continue
        ms = m["milestone"]
        eid = by_loc.get(ms["path"])
        verdict = ("consistent with Crustdata's record" if m["status"] == "consistent"
                   else "record differs: " + "; ".join(m["differences"]))
        extra = ""
        if "lead" in m:
            lead_s = m["lead"]
            extra = (f" Lead {lead} is among the record's investors." if lead_s.startswith("found")
                     else f" Lead {lead}: {lead_s}.")
        lines.append({"kind": "round_check", "claim_id": c.id,
                      "evidence_ids": [eid] if eid else [],
                      "line": f"{c.id} ({rtype.replace('_', ' ')}): {verdict}.{extra} "
                              f"[{eid}]" if eid else f"{c.id}: {verdict}.{extra}"})
        if m["status"] == "differs":
            questions.append(f"The announcement and Crustdata's record differ on the "
                             f"{rtype.replace('_', ' ')} ({'; '.join(m['differences'])}). "
                             "Which figure is right?")
    # Other indexed rounds, labelled indexed-only (gap fill, never "independent").
    checked = {ln.get("claim_id") for ln in lines}
    for ms in fin["milestones"]:
        eid = by_loc.get(ms["path"])
        amt = f"${ms['amount_usd']:,.0f}" if ms["amount_usd"] is not None else "no amount recorded"
        lead = ", ".join(ms["lead_investors"]) or "lead not recorded"
        kind = "secondary sale (liquidity, not company capital)" if ms["secondary"] else \
            ms["round_type"].replace("_", " ")
        lines.append({"kind": "indexed_round", "claim_id": "", "evidence_ids": [eid] if eid else [],
                      "line": f"Indexed {kind}: {ms['date'] or 'date unknown'}, {amt}, {lead} "
                              f"(indexed record, Crunchbase-derived). [{eid}]"})
    total = fin.get("total_investment_usd")
    tid = by_loc.get("funding.total_investment_usd")
    if total is not None:
        if fin["total_is_capital"]:
            how = (f" across {fin['num_rounds']} rounds; it equals the sum of the recorded "
                   "round amounts" if fin["total_explained_by_milestones"] else
                   f" across {fin['num_rounds']} rounds")
            lines.append({"kind": "total", "claim_id": "", "evidence_ids": [tid] if tid else [],
                          "line": f"Total raised per Crustdata's record: ${total:,.0f}{how} "
                                  f"(indexed record, Crunchbase-derived). [{tid}]"})
        else:
            lines.append({"kind": "total", "claim_id": "", "evidence_ids": [tid] if tid else [],
                          "line": f"Crustdata's indexed total ${total:,.0f} includes secondary "
                                  f"sales, so it is not capital raised. [{tid}]"})
            rounds = [m for m in fin["milestones"] if not m["secondary"] and m["amount_usd"]]
            ids = [by_loc[m["path"]] for m in rounds if m["path"] in by_loc]
            if rounds and len(ids) == len(rounds):
                calc = sum(m["amount_usd"] for m in rounds)
                lines.append({"kind": "calculation", "claim_id": "", "evidence_ids": ids,
                              "line": f"The recorded rounds not marked as secondary sales sum to "
                                      f"${calc:,.0f} (calculation from the indexed record; a round "
                                      "can still include some secondary shares). "
                                      + "".join(f"[{i}]" for i in ids)})
    del checked
    return lines


_ROUND = re.compile(r"\b(pre[- ]?seed|seed|series\s+([a-h])|secondary|tender)\b", re.I)


def _round_type(text: str) -> str:
    m = _ROUND.search(text or "")
    if not m:
        return ""
    word = m.group(1).lower().replace(" ", "").replace("-", "")
    if word.startswith("series"):
        return f"series_{m.group(2).lower()}"
    if word in ("secondary", "tender"):
        return "secondary_market"
    return "pre_seed" if word == "preseed" else "seed"


_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _iso_from_text(text: str) -> str:
    """Best-effort ISO date from a claim's `date_text` at its precision ("" if relative)."""
    t = (text or "").strip()
    m = re.search(r"\b(\d{4})-(\d{2})(?:-(\d{2}))?\b", t)
    if m:
        return m.group(0)
    m = re.search(r"\b(\d{1,2})?\s*([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2},\s*)?(\d{4})\b", t)
    if m and m.group(2).lower()[:3] in _MONTHS:
        mon = _MONTHS[m.group(2).lower()[:3]]
        day = m.group(1) or (m.group(3) or "").strip(", ")
        return f"{m.group(4)}-{mon:02d}" + (f"-{int(day):02d}" if day else "")
    m = re.search(r"\b(19|20)\d{2}\b", t)
    return m.group(0) if m else ""


def _validate_assess(ass: AssessResult, claims: list[Claim],
                     evidence: list[Evidence]) -> tuple[AssessResult, list[str]]:
    out = llm.local_validate_assess(ass, claims, {e.id for e in evidence})
    if isinstance(out, tuple):
        result, lims = out[0], list(out[1])
        return result, lims
    lims = list(out.limitations)
    for item in getattr(out, "suppressed", None) or []:
        lims.append(f"suppressed before the gate: {item}")
    return out.result, lims  # AssessValidation


def _apply_checks(findings: list, checks: list, limitations: list[str]) -> list:
    """Call 3: a sentence that is not entailed is withheld; a missing qualifier is
    recorded. There is no repair call (§5.4). Returns (kept, withheld)."""
    by = {c.claim_id: c for c in checks}
    kept, withheld = [], []
    for f in findings:
        c = by.get(f.claim_id)
        if c is None:
            limitations.append(f"{f.claim_id}: sentence check incomplete; kept with code gate only")
            kept.append(f)
            continue
        if not c.entailed:
            limitations.append(f"{f.claim_id}: suppressed by the sentence check"
                               + (f" (unsupported: \"{c.unsupported_fragment}\")"
                                  if c.unsupported_fragment else ""))
            withheld.append(f)
            continue
        if c.missing_qualifier:
            limitations.append(f"{f.claim_id}: the evidence carries a qualifier the sentence "
                               f"omits: \"{c.missing_qualifier}\"")
        kept.append(f)
    return kept, withheld


def _crust_attempt(a: cd.Attempt) -> AttemptRecord:
    return AttemptRecord(stage="crustdata", endpoint=a.endpoint, mode=a.mode,  # type: ignore
                         status=str(a.status), seconds=a.seconds, credits_used=a.credits_used,
                         error=a.error)


def _write_failed(rd: store.RunDir, r: _Run, err: Exception) -> None:
    import json
    try:
        (rd.path / "failed.json").write_text(json.dumps({
            "error": str(err), "type": type(err).__name__, "seconds": r.elapsed(),
            "limitations": r.limitations, "stage_log": r.log_lines,
            "model_attempts": [a.model_dump() for a in r.model_attempts]}, indent=2))
    except OSError as e:
        log.error("could not write failed.json: %s", e)


async def _signals(client: cd.Crustdata, g: graph.GraphResult, req: RunRequest,
                   limitations: list[str]) -> Any:
    """Investor signals; a failure narrows the research report, never the brief."""
    try:
        return await signals.fetch_signals(client, g.g1.company_id, req.domain, founders=g.team)
    except CrustError as e:
        if e.fatal:
            raise
        limitations.append(f"Investor signals unavailable ({e.status} {e.type})")
    except Exception as e:  # noqa: BLE001 - research data must never fail the brief
        log.exception("signals failed")
        limitations.append(f"Investor signals unavailable ({type(e).__name__})")
    return None


def _research(case: CaseRecord, sig: Any, req: RunRequest, r: _Run) -> dict[str, str | bytes]:
    """D24: score, rate, size, and render the equity-research report (PDF when possible)."""
    fl, pl, rec = scoring.assess(case, sig, req.check_size_usd)
    case.stats.update({"rating": rec.rating, "signal_score": rec.score,
                       "confidence": rec.confidence, "suggested_usd": rec.suggested_usd,
                       "check_size_usd": rec.check_size_usd,
                       "flags": {lv: sum(f.level == lv for f in fl)
                                 for lv in ("critical", "red", "amber", "green")},
                       "signals_credits": sig.credits_used})
    html = equity_report.build_html(case, sig, fl, pl, rec, rules=scoring.RULES)
    out: dict[str, str | bytes] = {"equity_report.html": html,
                                   "signals.json": sig.model_dump_json(indent=2)}
    try:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            pdf = equity_report.render_pdf(html, Path(tmp) / "equity_report.pdf")
            out["equity_report.pdf"] = pdf.read_bytes()
    except ProofroomError as e:
        r.limitations.append(f"PDF rendering unavailable ({e}); the HTML report is included")
    return out


def _with_desk(brief: str, desk_md: str) -> str:
    """U7: the exception desk goes after the header, before the first section."""
    section = "\n## "
    i = brief.find(section)
    if i < 0:
        return brief.rstrip() + "\n\n## Needs a person\n\n" + desk_md
    return brief[:i] + "\n## Needs a person\n\n" + desk_md + brief[i:]


def _provider_label(provider: Any) -> str:
    if isinstance(provider, llm.AnthropicProvider):
        return f"{provider.model} (Anthropic API)"
    if isinstance(provider, llm.SessionProvider):
        return "agent session (request files, D15)"
    if isinstance(provider, llm.FixtureProvider):
        return "recorded model responses (FIXTURE)"
    return type(provider).__name__


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    return [x for x in items if not (x in seen or seen.add(x))]


__all__ = ["RunRequest", "RunOutcome", "run", "PROFILES", "FULL", "FAST", "ConfigError",
           "StoreError"]
