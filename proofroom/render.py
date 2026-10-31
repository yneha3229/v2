"""Brief rendering (plan v2 §4.3) plus the U3 origin map, U4 four clocks and U6
founder-meeting question sheet. Pure functions of a CaseRecord: no I/O, no network.

`case.financing` line-dict format (built by `financing_lines` from
graph.financing_summary, or by the caller directly):

    {"kind": "meta", "line": "", "evidence_ids": [],
     "record_refresh": "2026-10-23" | "unknown", "total_is_capital": bool, "basis": str}
    {"kind": "round" | "total" | "comparison" | "calculation" | "question" | "note",
     "line": "Seed $5M dated 7 Sep 2025 (day), lead Forerunner", "evidence_ids": ["G7"],
     "total_is_capital": bool  # optional, "total" lines; falls back to the meta value}

Other kinds (e.g. the pipeline's "round_check", "indexed_round") render as plain lines.
Every non-meta line is rendered with its [G#]/[E#] citations (not duplicated when the
line already carries them). When total_is_capital is known (line or meta), a "total"
line is prefixed "Total raised" only if it is True, else "Indexed total, not capital
raised"; without it the line text must label itself. Crustdata funding data is always
labelled "indexed record (Crunchbase-derived)".
"""
from __future__ import annotations

import re
from html import escape as _xml
from urllib.parse import urlparse

from proofroom.gate import CITE_RE, normalize, parse_amounts, parse_full_dates
from proofroom.graph import G4_BASIS, date_and_precision
from proofroom.models import CaseRecord, Document, Evidence, Finding, TeamRow

INDEXED = "indexed record (Crunchbase-derived)"

DISPOSITION = {"supported": "Supported", "supported_corrected": "Supported, corrected",
               "conflicting": "Conflicting", "not_established": "Not established"}
BASIS = {"company_statement": "company statement", "investor_statement": "investor statement",
         "independent_report": "independent report", "calculation": "calculation",
         "crustdata_indexed_record": "Crustdata indexed record"}
# Crustdata last, so "independent" never sits next to a Crustdata label.
_BASIS_ORDER = ["company_statement", "investor_statement", "independent_report", "calculation",
                "crustdata_indexed_record"]
_RANK = {"conflicting": 0, "supported_corrected": 1, "not_established": 2}
_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ---- Small helpers ------------------------------------------------------------------

def cites(ids: list[str], sentence: str = "") -> str:
    present = set(CITE_RE.findall(sentence))
    return "".join(f"[{i}]" for i in ids if i and i not in present)


def status_label(f: Finding) -> str:
    label = DISPOSITION.get(f.disposition, f.disposition)
    if f.disposition == "supported_corrected" and f.correction_reason:
        label += f" ({f.correction_reason})"
    if f.qualified and f.disposition != "supported_corrected":
        label += " (qualified)"
    return label


def basis_chip(basis: list[str]) -> str:
    keys = [b for b in _BASIS_ORDER if b in basis] + [b for b in basis if b not in _BASIS_ORDER]
    if "company_statement" in keys and "investor_statement" in keys:
        rest = [BASIS.get(b, b) for b in keys if b not in ("company_statement", "investor_statement")]
        return " · ".join(["company and investor statements, one announcement"] + rest)
    if keys == ["company_statement"]:
        return "company statement only"
    return " · ".join(BASIS.get(b, b) for b in keys) or "no basis recorded"


def human_date(iso: str, precision: str = "") -> str:
    """2025-09-07 -> "7 Sep 2025"; 2025-09 -> "Sep 2025"; 2024 -> "2024"."""
    if not precision:
        iso, precision = date_and_precision(iso)
    try:
        if precision == "day":
            y, m, d = iso[:10].split("-")
            return f"{int(d)} {_MON[int(m) - 1]} {y}"
        if precision == "month":
            y, m = iso[:7].split("-")
            return f"{_MON[int(m) - 1]} {y}"
        if precision == "year":
            return iso[:4]
    except (ValueError, IndexError):
        pass
    return "date not recorded"


def money(value: float | None) -> str:
    """USD in a form the gate reads back exactly: 5e6 -> "$5M", 52,020,932 -> "$52,020,932"."""
    if value is None:
        return "amount not recorded"
    if value >= 1e9 and value % 1e7 == 0:
        return f"${value / 1e9:.2f}".rstrip("0").rstrip(".") + "B"
    if value >= 1e6 and value % 1e5 == 0:
        return f"${value / 1e6:.1f}".rstrip("0").rstrip(".") + "M"
    return f"${value:,.0f}"


def _cell(text: str) -> str:
    return normalize(text).replace("|", "\\|")


def _company(case: CaseRecord) -> str:
    return str(case.g1.get("name") or case.input.domain)


def _excerpt(value: str, n: int = 200) -> str:
    v = normalize(value)
    return v if len(v) <= n else v[: n - 1].rstrip() + "…"


def _host(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


# ---- G4 financing lines -------------------------------------------------------------

def _round_label(rtype: str) -> str:
    if rtype == "secondary_market":
        return "Secondary sale (liquidity, not company capital)"
    if rtype == "pre_seed":
        return "Pre-seed"
    words = rtype.replace("_", " ").split()
    if words[:1] == ["series"] and len(words) > 1:
        return "Series " + " ".join(w.upper() if len(w) == 1 else w for w in words[1:])
    return " ".join(words).capitalize() or "Round"


def financing_lines(summary: dict, evidence: list[Evidence]) -> list[dict]:
    """case.financing lines from graph.financing_summary, citing the G rows that
    graph.graph_evidence created (matched by JSON path)."""
    if not summary:
        return []
    by_loc = {e.locator: e.id for e in evidence if e.kind == "graph"}
    out: list[dict] = [{"kind": "meta", "line": "", "evidence_ids": [],
                        "record_refresh": summary.get("record_refresh") or "unknown",
                        "total_is_capital": bool(summary.get("total_is_capital")),
                        "basis": summary.get("basis") or G4_BASIS}]
    ms_ids = []
    for m in summary.get("milestones") or []:
        gid = by_loc.get(m.get("path", ""))
        ms_ids += [gid] if gid else []
        lead = ", ".join(m.get("lead_investors") or []) or "not recorded"
        when = human_date(m.get("date") or "", m.get("date_precision") or "unknown")
        line = f"{_round_label(m.get('round_type') or '')} {money(m.get('amount_usd'))}"
        line += f" dated {when}" if when != "date not recorded" else ", date not recorded"
        line += f", lead {lead}"
        out.append({"kind": "round", "line": line, "evidence_ids": [gid] if gid else []})
    total = summary.get("total_investment_usd")
    if total is not None:
        tid = by_loc.get("funding.total_investment_usd")
        n = summary.get("num_rounds") or 0
        if summary.get("total_is_capital"):
            line = f"{money(total)} across {n} rounds per Crustdata's record"
        else:
            line = f"{money(total)} indexed total, which includes secondary sales"
        out.append({"kind": "total", "line": line, "evidence_ids": [tid] if tid else [],
                    "total_is_capital": bool(summary.get("total_is_capital"))})
        if not summary.get("total_is_capital") and summary.get("primary_sum_usd") is not None:
            out.append({"kind": "calculation", "evidence_ids": ms_ids,
                        "line": f"Primary rounds sum to {money(summary['primary_sum_usd'])} "
                                "(calculation from Crustdata's indexed record)"})
    return out


def _meta(case: CaseRecord) -> dict:
    return next((d for d in case.financing if d.get("kind") == "meta"), {})


# ---- brief.md -----------------------------------------------------------------------

def brief_md(case: CaseRecord, *, model_source: str, profile: str) -> str:
    company = _company(case)
    prof = profile.upper()
    prof_text = f"{prof} (reduced checking)" if prof == "FAST" else prof
    out: list[str] = []
    out.append(f"# {company} ({case.input.domain}): Team & Financing")
    out.append("")
    head = [f"Crustdata company ID {case.g1.get('company_id') or 'not resolved'}",
            f"reviewed {case.reviewed}", f"run {case.run}", f"Mode {case.input.input_mode}",
            case.run_mode, f"model: {model_source}", f"profile {prof_text}"]
    if case.status != "DELIVERED":
        head.append(f"status {case.status}")
    out.append(" · ".join(head))
    out.append("")

    out.append("## From the sources")
    out.append("")
    if case.findings:
        for n, f in enumerate(case.findings, 1):
            sent = f.sentence.strip()
            out.append(f"{n}. **{status_label(f)}** · {basis_chip(list(f.basis))}: "
                       f"{sent} {cites(f.evidence_ids, sent)}".rstrip())
    else:
        out.append("No source sentence passed the checks in this run.")
    out.append("")

    out.append("## From Crustdata's graph")
    out.append("")
    out += _team_section(case)
    out.append("")
    out += _funding_section(case)
    out.append("")

    out.append("## Questions")
    out.append("")
    qs = _questions(case)
    out += [f"- {q} {cites(ids, q)}".rstrip() for q, ids, _ in qs] or ["- None raised."]
    out.append("")

    out.append("## Not checked")
    out.append("")
    out += [f"- {x}" for x in _not_checked(case)] or ["- Nothing was left unchecked."]
    out.append("")

    out.append("## Limitations")
    out.append("")
    lims = list(dict.fromkeys(
        list(case.limitations) + [f"{f.claim_id}: {f.limitation}" for f in case.findings if f.limitation]))
    out += [f"- {x}" for x in lims] or ["- None recorded."]
    out.append("")

    out.append("## Evidence")
    out.append("")
    out += [_evidence_line(e) for e in case.evidence] or ["- No evidence rows."]
    out.append("")

    out.append("## Run statistics")
    out.append("")
    out += _stats(case)
    return "\n".join(out).rstrip() + "\n"


def _team_section(case: CaseRecord) -> list[str]:
    company = _company(case)
    gid = case.g1.get("company_id")
    if not case.team:
        return [f"No founder records were found in Crustdata's graph for company ID "
                f"{gid or 'not resolved'}; roles stay attributed to the sources (see Limitations)."]
    dates = sorted({t.updated_at for t in case.team if t.updated_at})
    when = ", ".join(human_date(d) for d in dates) or "unknown dates"
    out = [f"Team (profiles are self-maintained; values as indexed on {when})", "",
           f"| Founder | Person ID | Current role at {_cell(company)} (employer-ID join) "
           "| Prior employers matched by ID |",
           "|---|---|---|---|"]
    for t in case.team:
        out.append(f"| {_cell(t.name)} | {t.person_id if t.person_id is not None else '?'} "
                   f"| {_role_cell(t, gid)} | {_prior_cell(t)} |")
    out.append("")
    out.append("✔ employer-ID join · ≈ name match only (no ID join) · ? no join found "
               "(absence is not a refutation)")
    return out


def _role_cell(t: TeamRow, gid: object) -> str:
    if t.role_join and t.current_at_subject:
        parts = []
        for e in t.current_at_subject:
            since = f", since {human_date(e.start, e.start_precision)}" if e.start else ""
            parts.append(f"{_cell(e.title or 'role not stated')}{since} ✔")
        cell = "; ".join(parts)
    else:
        cell = f"? no current entry with employer ID {gid or 'unknown'}"
    others = [e.employer_name for e in t.other_current if e.employer_name]
    if others:
        cell += f" (also current: {_cell(', '.join(others))})"
    return cell


def join_mark(j) -> str:
    if (j.note or "").strip().lower().startswith("name match"):
        return "≈"
    return "✔" if j.joined else "?"


def _prior_cell(t: TeamRow) -> str:
    if not t.prior_joins:
        return "none named by the sources"
    return " · ".join(f"{_cell(j.employer_name)} {join_mark(j)}" for j in t.prior_joins)


def record_refresh(case: CaseRecord) -> str:
    """The meta line's record_refresh, else the indexed graph rows' refresh, else unknown."""
    meta = _meta(case)
    if meta.get("record_refresh"):
        return str(meta["record_refresh"])
    for e in case.evidence:
        if e.kind == "graph" and "crunchbase" in (e.origin or "").lower() and e.refreshed:
            return e.refreshed
    return "unknown"


def _funding_section(case: CaseRecord) -> list[str]:
    meta = _meta(case)
    refresh = record_refresh(case)
    lines = [d for d in case.financing if d.get("kind") != "meta"]
    out = [f"Funding record: {INDEXED}; record refresh: {refresh}", ""]
    if not lines:
        out.append("- No funding record lines in this run.")
        return out
    for d in lines:
        text = str(d.get("line") or "").strip()
        kind = d.get("kind")
        if kind == "total" and ("total_is_capital" in d or "total_is_capital" in meta):
            capital = d.get("total_is_capital", meta.get("total_is_capital"))
            prefix = "Total raised" if capital is True else "Indexed total, not capital raised"
            text = f"{prefix}: {text}"
        elif kind == "calculation" and "calculation" not in text.lower():
            text += " (calculation from Crustdata's indexed record)"
        elif kind == "question":
            text = f"Question: {text}"
        out.append(f"- {text} {cites(list(d.get('evidence_ids') or []), text)}".rstrip())
    return out


def _not_checked(case: CaseRecord) -> list[str]:
    items = list(case.not_checked)
    for c in case.claims:
        if not c.selected:
            reason = c.exclusion_reason or "not selected"
            items.append(f'{c.id}: "{_excerpt(c.quote, 160)}" ({reason})')
    return list(dict.fromkeys(items))


def _evidence_line(e: Evidence) -> str:
    clocks = []
    for name in ("published", "updated", "refreshed", "retrieved"):
        v = getattr(e, name)
        if v:
            clocks.append(f"{name} {v}")
    loc = f" · {e.locator}" if e.locator else ""
    origin = f" · {e.origin}" if e.origin else ""
    tail = f" · {' · '.join(clocks)}" if clocks else ""
    return f'- **{e.id}** · {e.source}{loc}{origin} · "{_excerpt(e.value)}"{tail}'


def _stat(v: object) -> str:
    if isinstance(v, (list, tuple)):
        if all(isinstance(x, (str, int, float)) for x in v) and len(", ".join(map(str, v))) <= 120:
            return ", ".join(map(str, v)) or "none"
        return f"{len(v)} entries"
    if isinstance(v, dict):
        return f"{len(v)} entries"
    return str(v)


def _stats(case: CaseRecord) -> list[str]:
    rows = [(str(k), _stat(v)) for k, v in case.stats.items()]
    if case.attempts:
        failed = sum(1 for a in case.attempts if a.status not in ("ok", "OK", "200"))
        rows.append(("attempts", f"{len(case.attempts)} ({failed} not ok)"))
    if not rows:
        return ["No statistics recorded."]
    return ["| Metric | Value |", "|---|---|"] + [f"| {_cell(k)} | {_cell(v)} |" for k, v in rows]


# ---- U6: questions for the founder meeting -------------------------------------------

def _claim_text(case: CaseRecord, f: Finding) -> str:
    c = next((c for c in case.claims if c.id == f.claim_id), None)
    return normalize(c.quote) if c and c.quote else normalize(f.sentence)


def _generated_question(case: CaseRecord, f: Finding) -> str:
    said = _excerpt(_claim_text(case, f), 180)
    if f.disposition == "conflicting":
        return (f'The sources disagree on this point: "{said}" Could you tell us which version '
                "is correct, and share a document that shows it?")
    if f.disposition == "supported_corrected":
        why = f" ({f.correction_reason})" if f.correction_reason else ""
        return (f'We needed to correct this statement{why}: "{said}" Could you confirm the '
                "accurate version and who it applies to?")
    if f.disposition == "not_established":
        return (f'We could not establish this from public sources or Crustdata\'s graph: "{said}" '
                "Could you point us to a source that documents it?")
    return (f'This holds only with a qualification: "{said}" Could you walk us through the '
            "details behind it?")


def _questions(case: CaseRecord) -> list[tuple[str, list[str], int]]:
    """(question, evidence IDs, rank), ranked conflicting > corrected > not established
    > other; stable within a rank."""
    items: list[tuple[str, list[str], int]] = []
    for f in case.findings:
        rank = _RANK.get(f.disposition, 3)
        if f.question.strip():
            items.append((f.question.strip(), list(f.evidence_ids), rank))
        elif f.disposition in _RANK or f.qualified:
            items.append((_generated_question(case, f), list(f.evidence_ids), rank))
    for d in case.financing:
        if d.get("kind") == "question" and str(d.get("line") or "").strip():
            items.append((str(d["line"]).strip(), list(d.get("evidence_ids") or []), 3))
    for q in case.questions:
        if q.strip():
            items.append((q.strip(), [], 3))
    seen: set[str] = set()
    uniq = []
    for q, ids, r in items:
        key = normalize(CITE_RE.sub("", q)).casefold()
        if key not in seen:
            seen.add(key)
            uniq.append((q, ids, r))
    return sorted(uniq, key=lambda x: x[2])


def questions_md(case: CaseRecord) -> str:
    ev = {e.id: e for e in case.evidence}
    out = ["# Questions for the founder meeting", "",
           f"{_company(case)} ({case.input.domain}) · reviewed {case.reviewed} · run {case.run} · "
           f"{case.run_mode}", ""]
    qs = _questions(case)
    if not qs:
        out.append("No open questions from this run.")
    for n, (q, ids, _) in enumerate(qs, 1):
        out.append(f"{n}. {q}")
        for i in ids:
            e = ev.get(i)
            if e:
                out.append(f'   - [{i}] {e.source}: "{_excerpt(e.value, 160)}"')
    return "\n".join(out).rstrip() + "\n"


# ---- U3: origin map ---------------------------------------------------------------------

_DOC_RE = re.compile(r"^(D\d+)\b")
_ROUND_PREDICATES = {"raised_round", "led_round", "participated_in_round"}
_PLAIN_ORIGINS = {"", "company", "investor", "independent", "unknown"}


def _norm_title(title: str) -> str:
    t = normalize(title).casefold()
    t = re.split(r"\s+[|\-]\s+", t)[0]          # drop " | Site name" / " - Site" suffixes
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _doc_for(e: Evidence, docs: list[Document]) -> Document | None:
    m = _DOC_RE.match(e.locator or "")
    if m:
        d = next((d for d in docs if d.id == m.group(1)), None)
        if d:
            return d
    return next((d for d in docs if d.source == e.source), None)


def _round_keys(case: CaseRecord, doc: Document) -> set[tuple[str, float]]:
    keys: set[tuple[str, float]] = set()
    for c in case.claims:
        if c.doc_id == doc.id and (c.family == "F3" or c.predicate in _ROUND_PREDICATES):
            for a in parse_amounts(c.amount_text or c.quote):
                keys.add((a.currency, a.value))
    if not keys:
        for a in parse_amounts(f"{doc.title} {doc.text[:4000]}"):
            keys.add((a.currency, a.value))
    return keys


def origin_map(case: CaseRecord) -> dict:
    """Group sources by origin: the same normalized title on different hosts is one
    origin (syndication); a company post and an investor post about the same round
    (a shared amount) are one announcement. Crustdata rows form their own groups and
    never count as an independent origin."""
    docs = list(case.documents)
    parent = {d.id: d.id for d in docs}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        parent[find(a)] = find(b)

    explicit: dict[str, str] = {}
    for e in case.evidence:
        d = _doc_for(e, docs) if e.kind == "source_passage" else None
        if d and e.origin not in _PLAIN_ORIGINS:
            if e.origin in explicit:
                union(d.id, explicit[e.origin])
            explicit[e.origin] = d.id
    by_title: dict[str, str] = {}
    for d in docs:
        t = _norm_title(d.title)
        if t and len(t.split()) >= 3:
            if t in by_title:
                union(d.id, by_title[t])
            else:
                by_title[t] = d.id
    rounds = {d.id: _round_keys(case, d) for d in docs}
    for a in docs:
        for b in docs:
            if a.id < b.id and {a.origin, b.origin} == {"company", "investor"} \
                    and rounds[a.id] & rounds[b.id]:
                union(a.id, b.id)

    groups: dict[str, dict] = {}
    order: list[str] = []

    def group(key: str, label: str, kind: str) -> dict:
        if key not in groups:
            groups[key] = {"id": f"O{len(groups) + 1}", "label": label, "kind": kind, "members": []}
            order.append(key)
        return groups[key]

    root_docs: dict[str, list[Document]] = {}
    for d in docs:
        root_docs.setdefault(find(d.id), []).append(d)
    for root, members in root_docs.items():
        origins = {m.origin for m in members}
        hosts = sorted({_host(m.source) or m.source for m in members})
        if len(members) > 1 and {"company", "investor"} <= origins:
            kind, label = "announcement", f"One announcement: company + investor ({', '.join(hosts)})"
        elif len(members) > 1:
            kind = "syndication"
            label = f"One origin, {len(members)} copies: {members[0].title or hosts[0]}"
        else:
            m = members[0]
            kind = m.origin or "unknown"
            label = f"{kind} · {_host(m.source) or m.source}"
        group(root, label, kind)

    seen_docs: set[str] = set()
    for e in case.evidence:
        if e.kind == "graph":
            indexed = "crunchbase" in (e.origin or "").lower()
            g = group("indexed" if indexed else "graph",
                      f"Crustdata {INDEXED}" if indexed else "Crustdata identity graph",
                      "indexed_record" if indexed else "graph")
        else:
            d = _doc_for(e, docs)
            if d:
                seen_docs.add(d.id)
                g = groups[find(d.id)]
            else:
                g = group(f"src:{e.source}", f"{e.origin or 'unknown'} · {_host(e.source) or e.source}",
                          e.origin if e.origin in _PLAIN_ORIGINS and e.origin else "unknown")
        g["members"].append({"evidence_id": e.id, "source": e.source})
    for d in docs:
        if d.id not in seen_docs:
            groups[find(d.id)]["members"].append({"evidence_id": "", "source": d.source, "doc_id": d.id})

    out_groups = [groups[k] for k in order]
    independent = sum(1 for g in out_groups if g["kind"] not in ("graph", "indexed_record"))
    return {"groups": out_groups, "independent_origin_count": independent}


def origin_map_svg(data: dict) -> str:
    """Inline SVG, one box per origin group with its members; currentColor only."""
    width, pad, line_h = 640, 12, 18
    y = pad
    parts = []
    head = f"Distinct source origins: {data.get('independent_origin_count', 0)}"
    parts.append(f'<text x="{pad}" y="{y + 14}" font-weight="600">{_xml(head)}</text>')
    y += 30
    for g in data.get("groups", []):
        members = g.get("members") or []
        h = pad * 2 + line_h * (1 + max(1, len(members)))
        dash = ' stroke-dasharray="4 3"' if g.get("kind") in ("graph", "indexed_record") else ""
        parts.append(f'<rect x="{pad}" y="{y}" width="{width - 2 * pad}" height="{h}" rx="6" '
                     f'fill="none" stroke="currentColor"{dash}/>')
        ty = y + pad + 13
        parts.append(f'<text x="{pad * 2}" y="{ty}" font-weight="600">'
                     f'{_xml(g.get("id", ""))} · {_xml(_excerpt(g.get("label", ""), 80))}</text>')
        for m in members or [{"evidence_id": "", "source": "no evidence rows"}]:
            ty += line_h
            label = f"{m.get('evidence_id') or m.get('doc_id') or '–'}  {m.get('source', '')}"
            parts.append(f'<text x="{pad * 3}" y="{ty}">{_xml(_excerpt(label, 90))}</text>')
        y += h + pad
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {y}" width="100%" '
            f'role="img" aria-label="Origin map" fill="currentColor" stroke="none" '
            f'font-family="system-ui, sans-serif" font-size="13">' + "".join(parts) + "</svg>")


# ---- U4: four clocks ---------------------------------------------------------------------

def clock_value(value: str) -> dict:
    """{"value", "precision"}: ISO dates use the project rule (YYYY-01-01 = year), a
    timestamp keeps "timestamp", free text dates are parsed ("Feb 2026" = month)."""
    v = normalize(value)
    if not v or v.lower() == "unknown":
        return {"value": v or "", "precision": "unknown"}
    if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", v):
        return {"value": v, "precision": "timestamp"}
    if re.match(r"^\d{4}(-\d{2}){0,2}$", v):
        iso, prec = date_and_precision(v)
        return {"value": iso or v, "precision": prec}
    dates = parse_full_dates(v)
    if dates:
        return {"value": dates[0].iso, "precision": dates[0].precision}
    m = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", v)
    if m:
        return {"value": m.group(1), "precision": "year"}
    return {"value": v, "precision": "unknown"}


def four_clocks(case: CaseRecord) -> list[dict]:
    """Per finding: the event date (as_of) and, from each cited evidence row, its
    published, updated, provider-refresh and retrieved times, each with its precision.
    Source-passage rows fall back to their document's published/updated/retrieved."""
    ev = {e.id: e for e in case.evidence}
    docs = list(case.documents)
    out = []
    for f in case.findings:
        row: dict = {"claim_id": f.claim_id, "evidence_ids": list(f.evidence_ids),
                     "event": clock_value(f.as_of),
                     "published": [], "updated": [], "refreshed": [], "retrieved": []}
        for i in f.evidence_ids:
            e = ev.get(i)
            if not e:
                continue
            d = _doc_for(e, docs) if e.kind == "source_passage" else None
            for clock in ("published", "updated", "refreshed", "retrieved"):
                v = getattr(e, clock) or (getattr(d, clock, "") if d and clock != "refreshed" else "")
                if v:
                    row[clock].append({"evidence_id": i, **clock_value(v)})
        out.append(row)
    return out
