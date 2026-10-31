"""Pydantic records (plan v2 §8.3, §8.4; Prep_01).

Model-call schemas are flat, forbid extra keys (`additionalProperties: false`),
and make every field required, using "" or [] for "none" (§8.3 schema rules).
Internal records (evidence, team rows, attempts, the case) are what case.json holds.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---- Call 1: extract and select ---------------------------------------------

Family = Literal["F1", "F2", "F3"]
Predicate = Literal["raised_round", "led_round", "participated_in_round", "total_raised",
                    "valuation", "secondary_sale", "founded_by", "holds_title",
                    "previously_worked_at", "backed_company", "other"]
Materiality = Literal["high", "medium", "low"]


class Claim(Strict):
    id: str
    doc_id: str
    quote: str
    family: Family
    predicate: Predicate
    subject: str
    object: str
    amount_text: str
    currency_text: str
    date_text: str
    title_text: str
    qualifiers: str
    materiality: Materiality
    selected: bool
    exclusion_reason: str


class ExtractResult(Strict):
    claims: list[Claim]


# ---- Call 2: assess -----------------------------------------------------------

Disposition = Literal["supported", "supported_corrected", "conflicting", "not_established"]
Basis = Literal["company_statement", "investor_statement", "independent_report",
                "crustdata_indexed_record", "calculation"]
CorrectionReason = Literal["", "date", "definition", "attribution", "title", "entity", "scope"]


class Finding(Strict):
    claim_id: str
    disposition: Disposition
    qualified: bool
    basis: list[Basis]
    sentence: str
    evidence_ids: list[str]
    as_of: str
    correction_reason: CorrectionReason
    limitation: str
    question: str


class AssessResult(Strict):
    findings: list[Finding]


# ---- Call 3: check ------------------------------------------------------------

class Check(Strict):
    claim_id: str
    entailed: bool
    missing_qualifier: str
    unsupported_fragment: str


class CheckResult(Strict):
    checks: list[Check]


# ---- Internal records -----------------------------------------------------------

RunMode = Literal["LIVE", "CACHED", "FIXTURE"]
AttemptMode = Literal["LIVE", "CACHED", "FIXTURE", "SESSION"]  # SESSION: answered by an agent (D15)
InputMode = Literal["A", "B"]
RunStatus = Literal["DELIVERED", "NARROWED", "FAILED"]


class Document(BaseModel):
    """One packet document. `text` is data, never instructions (CLAUDE.md §3)."""

    id: str                        # D1, D2, ...
    source: str                    # URL or "pasted"
    title: str = ""
    text: str
    published: str = ""            # ISO date at its precision, or ""
    updated: str = ""
    retrieved: str = ""            # ISO timestamp
    sha256: str = ""               # hash of the exact representation fetched (§5.3)
    origin: str = ""               # company | investor | independent | unknown
    picked_because: str = ""


class Evidence(BaseModel):
    """One row of the evidence table. `kind` is source_passage or graph."""

    id: str                        # E1.. for passages, G1.. for graph values
    kind: Literal["source_passage", "graph"]
    source: str                    # URL, or endpoint for graph rows
    locator: str = ""              # document ID + span, or JSON path
    value: str                     # excerpt, or rendered JSON value
    subject_basis: str = ""        # how this evidence maps to the subject (§5.2)
    origin: str = ""               # origin group or "Crustdata indexed record (Crunchbase-derived)"
    published: str = ""
    updated: str = ""
    refreshed: str = ""            # provider updated_at, or "unknown"
    retrieved: str = ""


class Employment(BaseModel):
    """One employment entry after normalizing both key sets (§20.2 item 3)."""

    employer_name: str
    employer_id: int | None
    title: str
    start: str                     # as given, "" when absent
    end: str
    start_precision: Literal["day", "month", "year", "unknown"]
    current: bool


class PriorJoin(BaseModel):
    employer_name: str             # as named by a source
    employer_id: int | None        # Identify(names) result
    joined: bool                   # exactly one matching past entry for this person (ID join)
    entry: Employment | None = None
    note: str = ""
    basis: Literal["id", "name_match", "none"] = "none"  # name_match is shown as "≈" (D14)


class TeamRow(BaseModel):
    name: str
    person_id: int | None
    profile_url: str = ""
    updated_at: str = ""
    current_at_subject: list[Employment] = Field(default_factory=list)
    role_join: bool = False        # a current entry's employer_id == G1
    listed_as_founder: bool = False
    other_current: list[Employment] = Field(default_factory=list)
    past: list[Employment] = Field(default_factory=list)
    prior_joins: list[PriorJoin] = Field(default_factory=list)
    source: str = ""               # people.founders | person_search | person_enrich


class AttemptRecord(BaseModel):
    """A Crustdata or model attempt; failures are kept (CLAUDE.md §3 honesty)."""

    stage: str
    endpoint: str
    mode: AttemptMode
    status: str
    seconds: float
    credits_used: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    error: dict | None = None


class RunInput(BaseModel):
    domain: str
    input_mode: InputMode
    run_mode: RunMode
    focus_note: str = ""
    urls: list[str] = Field(default_factory=list)
    pasted: list[str] = Field(default_factory=list)
    fixture: str = ""


class CaseRecord(BaseModel):
    """Everything case.json holds for one run."""

    case_id: str
    run: int
    status: RunStatus
    run_mode: RunMode
    input: RunInput
    reviewed: str
    g1: dict
    documents: list[Document] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    checks: list[Check] = Field(default_factory=list)
    team: list[TeamRow] = Field(default_factory=list)
    financing: list[dict] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    not_checked: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    attempts: list[AttemptRecord] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)
