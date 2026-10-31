"""What the graph decides (plan v2 §7, §20): G1 subject anchor, and helpers that
unwrap Crustdata's `[].matches[].company_data` responses. G2–G4 build on these."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from proofroom.errors import CrustError
from proofroom.models import Employment, Evidence, PriorJoin, TeamRow

log = logging.getLogger(__name__)

MATCHED, NO_MATCH, TIE = "MATCHED", "NO_MATCH", "TIE"


@dataclass
class G1Result:
    """Subject anchor. `status` is MATCHED, NO_MATCH (never "does not exist") or TIE."""

    domain: str
    status: str
    company_id: int | None = None
    name: str = ""
    basis: str = ""
    candidates: list[dict] = field(default_factory=list)
    excluded: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _matches(response: Any) -> list[dict]:
    """Flatten Identify/Enrich responses: a list of `{matched_on, matches: [...]}` blocks.
    Unknown shapes yield no matches rather than raising."""
    blocks = response if isinstance(response, list) else [response] if isinstance(response, dict) else []
    out: list[dict] = []
    for block in blocks:
        if isinstance(block, dict) and isinstance(block.get("matches"), list):
            out.extend(m for m in block["matches"] if isinstance(m, dict))
    return out


def _candidate(match: dict) -> dict | None:
    data = match.get("company_data") or {}
    info = data.get("basic_info") or {}
    cid = data.get("crustdata_company_id") or info.get("crustdata_company_id")
    try:
        cid = int(cid)
    except (TypeError, ValueError):
        return None
    try:
        conf = float(match.get("confidence_score") or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    return {
        "id": cid,
        "name": str(info.get("name") or ""),
        "primary_domain": str(info.get("primary_domain") or "").lower(),
        "all_domains": [str(d).lower() for d in info.get("all_domains") or []],
        "confidence": conf,
    }


def resolve_g1(domain: str, identify_response: Any) -> G1Result:
    """G1 tie rule (§7): prefer the candidate whose `primary_domain` equals the input,
    highest confidence first; otherwise a unique candidate whose `all_domains` contains
    it. Abstain (TIE) only if two distinct IDs tie on both checks."""
    domain = domain.strip().lower()
    cands: dict[int, dict] = {}
    for m in _matches(identify_response):
        c = _candidate(m)
        if c and (c["id"] not in cands or c["confidence"] > cands[c["id"]]["confidence"]):
            cands[c["id"]] = c
    all_cands = sorted(cands.values(), key=lambda c: -c["confidence"])
    res = G1Result(domain, NO_MATCH, candidates=all_cands)
    if not all_cands:
        res.basis = "Identify returned no candidates (not evidence that the company does not exist)"
        return res

    exact = [c for c in all_cands if c["primary_domain"] == domain]
    if exact:
        top = exact[0]["confidence"]
        best = [c for c in exact if c["confidence"] == top]
        if len(best) == 1:
            return _accept(res, best[0], f"primary_domain == {domain}, confidence {top}")
        res.status, res.basis = TIE, f"{len(best)} IDs share primary_domain {domain} at {top}"
        return res

    listed = [c for c in all_cands if domain in c["all_domains"]]
    if len(listed) == 1:
        return _accept(res, listed[0], f"unique candidate listing {domain} in all_domains")
    if len(listed) > 1:
        res.status, res.basis = TIE, f"{len(listed)} IDs list {domain} in all_domains"
        return res
    res.basis = "no candidate has this domain as primary or listed domain"
    res.excluded = all_cands
    return res


def _accept(res: G1Result, chosen: dict, basis: str) -> G1Result:
    res.status, res.company_id, res.name, res.basis = MATCHED, chosen["id"], chosen["name"], basis
    res.excluded = [c for c in res.candidates if c["id"] != chosen["id"]]
    return res


def company_record(enrich_response: Any) -> dict:
    """The first `company_data` of a Company Enrich response, or {} if absent."""
    for m in _matches(enrich_response):
        data = m.get("company_data")
        if isinstance(data, dict):
            return data
    log.warning("company enrich response had no company_data")
    return {}


# ---- Dates and the employment normalizer (§20.2 items 3–4) --------------------

def date_and_precision(raw: object) -> tuple[str, str]:
    """`YYYY-01-01` -> year precision, `YYYY-MM-01` -> month, else day. `1970-01-01`
    (epoch sentinel, PC-4) and unparseable values -> unknown. Time parts are dropped."""
    s = str(raw or "").strip()[:10]
    if len(s) < 4 or not s[:4].isdigit():
        return "", "unknown"
    if s.startswith("1970-01-01"):
        return "", "unknown"
    from datetime import date as _date
    try:
        _date.fromisoformat({4: s + "-01-01", 7: s + "-01"}.get(len(s), s))
    except ValueError:
        return "", "unknown"
    if len(s) == 4:
        return s, "year"
    if len(s) == 7:
        return s, "month"
    if s.endswith("-01-01"):
        return s[:4], "year"
    if s.endswith("-01"):
        return s[:7], "month"
    return s, "day"


def _to_int(value: object) -> int | None:
    if isinstance(value, list):
        ids = {i for i in (_to_int(v) for v in value) if i is not None}
        return ids.pop() if len(ids) == 1 else None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def normalize_employment(entry: dict, current: bool) -> Employment:
    """Accept both key sets: Company Enrich founders (`employer_name`,
    `employer_company_id` as a list of strings, `employee_title`, `employee_*_date`)
    and Person Enrich (`name`, `crustdata_company_id`, `title`, `start_date`)."""
    name = entry.get("employer_name") or entry.get("name") or ""
    raw_id = entry.get("employer_company_id", entry.get("crustdata_company_id"))
    start, prec = date_and_precision(entry.get("employee_start_date") or entry.get("start_date"))
    end, _ = date_and_precision(entry.get("employee_end_date") or entry.get("end_date"))
    return Employment(employer_name=str(name), employer_id=_to_int(raw_id),
                      title=str(entry.get("employee_title") or entry.get("title") or ""),
                      start=start, end=end, start_precision=prec, current=current)


def _employment(person: dict) -> tuple[list[Employment], list[Employment]]:
    details = ((person.get("experience") or {}).get("employment_details") or {})
    cur = [normalize_employment(e, True) for e in details.get("current") or [] if isinstance(e, dict)]
    past = [normalize_employment(e, False) for e in details.get("past") or [] if isinstance(e, dict)]
    return cur, past


def _profile_url(person: dict) -> str:
    handles = person.get("social_handles") or {}
    return str(((handles.get("professional_network_identifier") or {}).get("profile_url")) or "")


# ---- G2 team matrix and G3 roster -------------------------------------------------

def team_row(person: dict, subject_id: int | None, source: str) -> TeamRow:
    profile = person.get("basic_profile") or {}
    cur, past = _employment(person)
    at_subject = [e for e in cur if subject_id is not None and e.employer_id == subject_id]
    return TeamRow(
        name=str(profile.get("name") or ""),
        person_id=_to_int(person.get("crustdata_person_id")),
        profile_url=_profile_url(person),
        updated_at=str(person.get("updated_at") or "")[:10],
        current_at_subject=at_subject,
        role_join=bool(at_subject),
        listed_as_founder=source == "people.founders",
        other_current=[e for e in cur if e not in at_subject],
        past=past,
        source=source,
    )


def team_from_record(record: dict, subject_id: int | None) -> list[TeamRow]:
    founders = ((record.get("people") or {}).get("founders")) or []
    return [team_row(p, subject_id, "people.founders") for p in founders if isinstance(p, dict)]


def persons_from_enrich(response: Any) -> list[dict]:
    """`[].matches[].person_data` from Person Enrich, skipping not_found/redacted
    blocks (id-6: a redacted profile is respected, with no alternative lookups)."""
    out = []
    for block in response if isinstance(response, list) else []:
        if not isinstance(block, dict):
            continue
        status = str(block.get("match_status") or "matched")
        if status != "matched":
            log.info("person %s: %s", block.get("matched_on"), status)
            continue
        for m in block.get("matches") or []:
            if isinstance(m, dict) and isinstance(m.get("person_data"), dict):
                out.append(m["person_data"])
    return out


def search_profiles(response: Any) -> list[dict]:
    profiles = response.get("profiles") if isinstance(response, dict) else None
    return [p for p in profiles or [] if isinstance(p, dict)]


# ---- Prior-employer joins (§7 G2) ---------------------------------------------------

def name_candidates(identify_response: Any) -> dict[str, set[int]]:
    """Identify(names) -> {queried name (casefolded): candidate IDs}."""
    out: dict[str, set[int]] = {}
    blocks = identify_response if isinstance(identify_response, list) else []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        key = str(block.get("matched_on") or "").casefold().strip()
        ids = {c["id"] for c in (_candidate(m) for m in block.get("matches") or []
                                 if isinstance(m, dict)) if c}
        out.setdefault(key, set()).update(ids)
    return out


def prior_joins(row: TeamRow, names: list[str], candidates: dict[str, set[int]]) -> list[PriorJoin]:
    """Accept a prior-employer join only when exactly one Identify candidate ID appears
    in this person's past entries (strict §7 rule). Otherwise `joined` is False and the
    note says why; absence is never a refutation (§5.2)."""
    past_ids = {e.employer_id for e in row.past if e.employer_id is not None}
    joins = []
    for name in names:
        cands = candidates.get(name.casefold().strip(), set())
        hits = cands & past_ids
        if len(hits) == 1:
            cid = hits.pop()
            entry = next(e for e in row.past if e.employer_id == cid)
            joins.append(PriorJoin(employer_name=name, employer_id=cid, joined=True, entry=entry,
                                   note=f"ID join: past entry '{entry.employer_name}' = {cid}"))
        elif len(hits) > 1:
            joins.append(PriorJoin(employer_name=name, employer_id=None, joined=False,
                                   note=f"ambiguous: {len(hits)} candidate IDs in past entries"))
        elif not cands:
            joins.append(PriorJoin(employer_name=name, employer_id=None, joined=False,
                                   note="Identify returned no candidates for this name"))
        else:
            joins.append(PriorJoin(employer_name=name, employer_id=None, joined=False,
                                   note=f"none of {len(cands)} Identify candidates is in this "
                                        "person's indexed past roles (not a refutation)"))
    return joins


# ---- G4 financing cross-check (§7, PC-2, PC-5, PC-6) ------------------------------------

G4_BASIS = "Crustdata funding record (Crunchbase-derived)"
_SUFFIXES = {"ventures", "venture", "capital", "partners", "vc", "llc", "inc", "fund", "management"}


def norm_investor(name: str) -> str:
    """Casefold, drop punctuation and generic suffixes. Aliases such as GV / Google
    Ventures are NOT normalization: they match only when a source states them (PC-6)."""
    words = re.sub(r"[^a-z0-9 ]+", " ", (name or "").casefold()).split()
    while len(words) > 1 and words[-1] in _SUFFIXES:
        words.pop()
    return " ".join(words)


def _split_names(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return []


def milestones(record: dict) -> list[dict]:
    funding = record.get("funding") or {}
    out = []
    for i, m in enumerate(funding.get("milestones") or []):
        if not isinstance(m, dict):
            continue
        date, prec = date_and_precision(m.get("funding_date") or m.get("date"))
        amount = m.get("amount_usd")
        out.append({
            "index": i,
            "path": f"funding.milestones[{i}]",
            "round_type": str(m.get("round_type") or "unknown"),
            "date": date,
            "date_precision": prec,
            "amount_usd": float(amount) if isinstance(amount, (int, float)) else None,
            "lead_investors": _split_names(m.get("lead_investors")),
            "investors": [str(d.get("name")) for d in m.get("investors_detailed") or []
                          if isinstance(d, dict) and d.get("name")],
            "secondary": str(m.get("round_type") or "") == "secondary_market",
        })
    return out


def financing_summary(record: dict) -> dict:
    """Deterministic G4 facts. The total is never presented as capital raised when any
    milestone is a secondary sale (PC-2); the primary sum is then a labeled calculation."""
    funding = record.get("funding") or {}
    ms = milestones(record)
    total = funding.get("total_investment_usd")
    total = float(total) if isinstance(total, (int, float)) else None
    has_secondary = any(m["secondary"] for m in ms)
    primary = [m for m in ms if not m["secondary"] and m["amount_usd"] is not None]
    primary_sum = sum(m["amount_usd"] for m in primary) if primary else None
    explained = (total is not None and primary_sum is not None and not has_secondary
                 and abs(total - primary_sum) < 1)
    return {
        "basis": G4_BASIS,
        "record_refresh": str(record.get("updated_at") or "")[:10] or "unknown",
        "milestones": ms,
        "total_investment_usd": total,
        "total_is_capital": total is not None and not has_secondary,
        "has_secondary": has_secondary,
        "primary_sum_usd": primary_sum,
        "total_explained_by_milestones": explained,
        "num_rounds": len(ms),
        "investors": _split_names(funding.get("investors")),
        "last_round": {"type": funding.get("last_round_type"),
                       "amount_usd": funding.get("last_round_amount_usd"),
                       "date": funding.get("last_fundraise_date")},
    }


def match_round(summary: dict, round_type: str, amount_usd: float | None = None,
                date: str = "", lead: str = "", stated_aliases: dict[str, str] | None = None) -> dict:
    """Compare one announced round with the record: type-matched (never just "last
    round"), amount at the announcement's precision, date within ±7 days or at the
    shared precision, lead by normalized name or a source-stated alias."""
    rtype = round_type.strip().lower().replace(" ", "_").replace("-", "_")
    cands = [m for m in summary["milestones"] if m["round_type"] == rtype]
    if not cands:
        return {"status": "not_in_record", "round_type": rtype,
                "note": f"no '{rtype}' milestone in the indexed record (not a refutation)"}
    if date and len(cands) > 1:
        cands.sort(key=lambda m: abs(_days_between(m["date"], date) or 10**6))
    m = cands[0]
    out: dict[str, Any] = {"status": "consistent", "milestone": m, "differences": []}
    if amount_usd is not None and m["amount_usd"] is not None:
        if not amounts_match(amount_usd, m["amount_usd"]):
            out["differences"].append(f"amount {amount_usd:,.0f} vs record {m['amount_usd']:,.0f}")
    if date and m["date"]:
        gap = _days_between(m["date"], date)
        if gap is not None and gap > 7 and not _same_at_precision(m["date"], date):
            out["differences"].append(f"date {date} vs record {m['date']}")
    if lead:
        out["lead"] = lead_status(lead, m["lead_investors"] + m["investors"], stated_aliases)
    if out["differences"]:
        out["status"] = "differs"
    return out


def lead_status(name: str, record_names: list[str], stated_aliases: dict[str, str] | None) -> str:
    target = norm_investor(name)
    normed = {norm_investor(n): n for n in record_names}
    if target in normed:
        return f"found: {normed[target]}"
    for alias, full in (stated_aliases or {}).items():
        if norm_investor(alias) == target and norm_investor(full) in normed:
            return f"found via source-stated alias: {normed[norm_investor(full)]}"
    return "not matched (not a conflict)"


def amounts_match(stated: float, record: float, unit: float | None = None) -> bool:
    """Compare at the stated figure's precision (PC-5): "$52M" matches 52,020,932.

    `unit` is the precision the text implies (1e6 for "$52M", 1e5 for "$20.5M"). Without
    it, it is the stated value's last significant digit, comparing at least two
    significant digits so "$50M" is not read as "anything from 45M to 55M"."""
    if stated <= 0 or record < 0:
        return stated == record
    if unit is None:
        digits = len(str(int(stated)))
        trailing = digits - len(str(int(stated)).rstrip("0"))
        unit = 10 ** min(trailing, max(0, digits - 2))
    return abs(record - stated) <= unit / 2


def _days_between(a: str, b: str) -> int | None:
    from datetime import date as _d
    try:
        da = _d.fromisoformat(_pad(a))
        db = _d.fromisoformat(_pad(b))
    except ValueError:
        return None
    return abs((da - db).days)


def _pad(s: str) -> str:
    return s if len(s) == 10 else s + "-01" if len(s) == 7 else s + "-01-01"


def _same_at_precision(a: str, b: str) -> bool:
    n = min(len(a), len(b))
    return n >= 4 and a[:n] == b[:n]


# ---- Graph evidence rows (cited by JSON path) ---------------------------------------

def graph_evidence(g1: G1Result, team: list[TeamRow], fin: dict) -> list[Evidence]:
    rows: list[Evidence] = []

    def add(source: str, locator: str, value: str, refreshed: str) -> None:
        rows.append(Evidence(id=f"G{len(rows) + 1}", kind="graph", source=source,
                             locator=locator, value=value,
                             subject_basis=f"Crustdata company ID {g1.company_id}",
                             origin="Crustdata identity graph", refreshed=refreshed))

    if g1.company_id:
        add("/company/identify", "matches[0].company_data.crustdata_company_id",
            f"{g1.name} = {g1.company_id} ({g1.basis})", "unknown")
    for r in team:
        for e in r.current_at_subject:
            add("/company/enrich" if r.source == "people.founders" else "/person/enrich",
                f"{r.source}[{r.name}].experience.employment_details.current",
                f"{r.name} (person {r.person_id}): {e.title} at {e.employer_name} "
                f"{e.employer_id}, since {e.start or 'unknown'}", r.updated_at or "unknown")
        for j in r.prior_joins:
            if j.joined and j.entry:
                add("/company/enrich" if r.source == "people.founders" else "/person/enrich",
                    f"{r.source}[{r.name}].experience.employment_details.past",
                    f"{r.name}: {j.entry.title} at {j.entry.employer_name} {j.employer_id}, "
                    f"{j.entry.start or '?'} to {j.entry.end or '?'}", r.updated_at or "unknown")
    for m in fin["milestones"]:
        amt = f"${m['amount_usd']:,.0f}" if m["amount_usd"] is not None else "amount not recorded"
        rows.append(Evidence(
            id=f"G{len(rows) + 1}", kind="graph", source="/company/enrich", locator=m["path"],
            value=f"{m['round_type']}, {m['date'] or 'date unknown'} ({m['date_precision']}), "
                  f"{amt}, lead {', '.join(m['lead_investors']) or 'not recorded'}",
            subject_basis=f"Crustdata company ID {g1.company_id}",
            origin="indexed record (Crunchbase-derived)", refreshed=fin["record_refresh"]))
    if fin["total_investment_usd"] is not None:
        rows.append(Evidence(
            id=f"G{len(rows) + 1}", kind="graph", source="/company/enrich",
            locator="funding.total_investment_usd",
            value=f"${fin['total_investment_usd']:,.0f}"
                  + ("" if fin["total_is_capital"] else " (includes secondary sales)"),
            subject_basis=f"Crustdata company ID {g1.company_id}",
            origin="indexed record (Crunchbase-derived)", refreshed=fin["record_refresh"]))
    return rows


# ---- Orchestration (stage 2) ---------------------------------------------------------

@dataclass
class GraphResult:
    g1: G1Result
    record: dict = field(default_factory=dict)
    team: list[TeamRow] = field(default_factory=list)
    financing: dict = field(default_factory=dict)
    news: list[dict] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


async def resolve(client: Any, domain: str) -> GraphResult:
    """G1 -> Company Enrich -> team (founders, else S1 search + enrich). Recoverable
    failures narrow the result and add a limitation; a 401 propagates (run FAILED)."""
    g1 = resolve_g1(domain, await _soft(client.identify_domain(domain), [], 404))
    res = GraphResult(g1)
    if g1.status != MATCHED or g1.company_id is None:
        res.limitations.append(f"Company identity not resolved: {g1.basis}")
        return res
    try:
        res.record = company_record(await client.company_enrich(g1.company_id))
    except CrustError as e:
        if e.status == 403 and "news" in e.denied_fields:
            res.limitations.append("Crustdata denied the optional `news` field; retried without it")
            res.record = company_record(await client.company_enrich(
                g1.company_id, ("basic_info", "funding", "people")))
        elif e.fatal:
            raise
        else:
            res.limitations.append(f"Company Enrich failed ({e.status} {e.type}); graph narrowed")
            return res
    res.financing = financing_summary(res.record)
    res.news = [n for n in res.record.get("news") or [] if isinstance(n, dict)]
    res.team = team_from_record(res.record, g1.company_id)
    if not res.team:
        res.team = await _s1_fallback(client, g1.company_id, res.limitations)
    return res


async def _s1_fallback(client: Any, company_id: int, limitations: list[str]) -> list[TeamRow]:
    try:
        profiles = search_profiles(await client.founder_search(company_id))
        urls = [u for u in (_profile_url(p) for p in profiles) if u][:3]
        persons = persons_from_enrich(await client.person_enrich(urls)) if urls else []
    except CrustError as e:
        if e.fatal:
            raise
        limitations.append(f"Founder discovery failed ({e.status} {e.type})")
        return []
    if not persons:
        limitations.append("No founders found in Crustdata's graph; roles stay attributed to sources")
    return [team_row(p, company_id, "person_enrich") for p in persons]


async def _soft(coro: Any, default: Any, *ok_statuses: int) -> Any:
    """Await; map the given statuses (e.g. Identify 404 = no match) to `default`."""
    try:
        return await coro
    except CrustError as e:
        if e.status in ok_statuses:
            return default
        raise
