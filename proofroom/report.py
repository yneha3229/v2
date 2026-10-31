"""U9 diligence report (D23): a fixed three-page format for every company.

Page 1 Snapshot & flags · Page 2 Team, financing & considerations · Page 3 Methodology.

Flags come from fixed rules over the verified CaseRecord (code, not a model), so
the format and the criteria are identical across companies. Every flag cites the
evidence IDs it rests on. There is deliberately no invest / pass verdict: the
report states facts for the reader's decision (plan §4.5).
"""
from __future__ import annotations

import html
import re
from collections import Counter
from dataclasses import dataclass, field

from proofroom.models import CaseRecord, Finding

GREEN, AMBER, RED = "green", "amber", "red"
LEVEL_LABEL = {GREEN: "Green flag", AMBER: "Open point", RED: "Red flag"}
LEVEL_MARK = {GREEN: "🟢", AMBER: "🟡", RED: "🔴"}

DISCLAIMER = ("Facts for your decision, not a recommendation. Proofroom checks team and "
              "financing claims; it does not assess the market, the product or the price.")

# Rule ID -> (level, condition). Printed on the methodology page so every report
# shows the same criteria.
RULES: dict[str, tuple[str, str]] = {
    "R1 identity": (RED, "The domain did not resolve to exactly one Crustdata company"),
    "R2 conflict": (RED, "A selected claim is Conflicting between comparable sources"),
    "R3 record-differs": (RED, "An announced round differs from Crustdata's indexed record"),
    "R4 founder-no-join": (RED, "A founder listed by Crustdata has no current role at the company"),
    "A1 withheld": (AMBER, "A sentence could not be verified as written and was withheld"),
    "A2 qualified": (AMBER, "A claim holds only with a qualification or rests on one party's word"),
    "A3 corrected": (AMBER, "A claim is true only with a correction (date, scope, title...)"),
    "A4 not-established": (AMBER, "Evidence neither supports nor contradicts a selected claim"),
    "A5 secondary": (AMBER, "The indexed total includes secondary sales (liquidity, not capital)"),
    "A6 retrieval": (AMBER, "A data source failed, so a check is incomplete"),
    "A7 no-sources": (AMBER, "No public source documents were found"),
    "G1 round-confirmed": (GREEN, "An announced round matches Crustdata's indexed record"),
    "G2 independent": (GREEN, "A financing claim is supported by an independent report"),
    "G3 founders-joined": (GREEN, "Every founder Crustdata lists holds a current role at the company "
                                  "(employer-ID join)"),
    "G4 prior-employer": (GREEN, "A prior employer named by a source joins to the person by ID"),
    "G5 total-explained": (GREEN, "The indexed total equals the sum of the recorded rounds"),
}

# What each rule means for the reader's decision (page 2). Fixed text.
CONSIDERATION = {
    "G1 round-confirmed": "The announced rounds match Crustdata's indexed record, so they can "
                          "be cited in a memo together with their sources.",
    "G2 independent": "At least one financing fact is reported by a publisher other than the "
                      "company or its investors.",
    "G3 founders-joined": "The founding team in Crustdata's graph matches the company's current "
                          "roster; reference checks can start from these profiles.",
    "G4 prior-employer": "A prior-employer claim is backed by an ID join, not just a name.",
    "G5 total-explained": "The indexed funding history adds up: the total equals its rounds.",
    "R1 identity": "Identity is not settled; nothing in this report should be relied on until "
                   "it is.",
    "R2 conflict": "Sources disagree; resolve which figure is right before it goes into a memo.",
    "R3 record-differs": "The announcement and the indexed record differ; ask which is right.",
    "R4 founder-no-join": "A listed founder may have left or changed role; confirm the current "
                          "team.",
    "A1 withheld": "A stated figure could not be verified as written; ask for the supporting "
                   "document (for example a cap-table summary).",
    "A2 qualified": "Some facts rest on one party's word; confirm them in the meeting.",
    "A3 corrected": "Some statements needed a correction; use the corrected version.",
    "A4 not-established": "Some claims could not be established either way; treat them as gaps, "
                          "not red flags.",
    "A5 secondary": "Do not read the indexed total as capital in the company; part of it is "
                    "secondary liquidity.",
    "A6 retrieval": "A check is incomplete because a source failed; re-run before relying on it.",
    "A7 no-sources": "Only Crustdata's record was available; there is no public announcement to "
                     "check against.",
}


@dataclass
class Flag:
    level: str
    rule: str
    title: str
    detail: str
    evidence_ids: list[str] = field(default_factory=list)


def _short(text: str, n: int = 220) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _cites(ids: list[str]) -> str:
    return "".join(f"[{i}]" for i in ids if i)


def flags(case: CaseRecord) -> list[Flag]:
    """Apply the fixed rules. Order: red, amber, green; stable within a level."""
    out: list[Flag] = []
    g1 = case.g1 or {}
    if g1.get("status") != "MATCHED":
        out.append(Flag(RED, "R1 identity", "Company identity not settled",
                        _short(g1.get("basis", "")) or "Identify returned no single match"))

    for f in case.findings:
        if f.disposition == "conflicting":
            out.append(Flag(RED, "R2 conflict", f"{f.claim_id}: sources disagree", _short(f.sentence),
                            list(f.evidence_ids)))
        elif f.disposition == "supported_corrected":
            why = f" ({f.correction_reason})" if f.correction_reason else ""
            out.append(Flag(AMBER, "A3 corrected", f"{f.claim_id}: true only with a correction{why}",
                            _short(f.sentence), list(f.evidence_ids)))
        elif f.disposition == "not_established":
            out.append(Flag(AMBER, "A4 not-established", f"{f.claim_id}: not established",
                            _short(f.sentence), list(f.evidence_ids)))
        elif f.qualified or f.limitation.strip():
            out.append(Flag(AMBER, "A2 qualified", f"{f.claim_id}: holds with a qualification",
                            _short(f.limitation or f.sentence), list(f.evidence_ids)))

    for line in case.financing:
        text = str(line.get("line") or "")
        ids = [i for i in line.get("evidence_ids") or [] if i]
        if line.get("kind") != "round_check":
            continue
        if "record differs" in text:
            out.append(Flag(RED, "R3 record-differs", "Announcement differs from the indexed record",
                            _short(_strip_cites(text)), ids))
        elif "consistent with Crustdata's record" in text:
            if any(f.rule == "G1 round-confirmed" and f.evidence_ids == ids for f in out):
                continue  # one flag per indexed round
            out.append(Flag(GREEN, "G1 round-confirmed", "Round matches the indexed record",
                            _short(_strip_cites(text)), ids))

    for f in case.findings:
        if f.disposition == "supported" and "independent_report" in f.basis and _is_financing(case, f):
            out.append(Flag(GREEN, "G2 independent", f"{f.claim_id}: independently reported",
                            _short(f.sentence), list(f.evidence_ids)))

    listed = [t for t in case.team if t.listed_as_founder or t.source == "people.founders"]
    if listed:
        missing = [t for t in listed if not t.role_join]
        ev = _team_evidence(case)
        if missing:
            out.append(Flag(RED, "R4 founder-no-join", "A listed founder has no current role here",
                            ", ".join(t.name for t in missing)))
        else:
            names = ", ".join(t.name for t in listed)
            out.append(Flag(GREEN, "G3 founders-joined",
                            f"{len(listed)} of {len(listed)} founders ID-joined to the company",
                            names, ev))
    for t in case.team:
        for j in t.prior_joins:
            if j.basis == "id" or j.joined:
                out.append(Flag(GREEN, "G4 prior-employer", f"{t.name} → {j.employer_name}",
                                f"past role joins by ID ({j.employer_id})"))

    total = _line(case, "total")
    if total:
        text = str(total.get("line") or "")
        ids = [i for i in total.get("evidence_ids") or [] if i]
        if "includes secondary" in text:
            out.append(Flag(AMBER, "A5 secondary", "Indexed total includes secondary sales",
                            _short(_strip_cites(text)), ids))
        elif "equals the sum of the recorded round amounts" in text:
            out.append(Flag(GREEN, "G5 total-explained", "Indexed total adds up",
                            _short(_strip_cites(text)), ids))

    for lim in case.limitations:
        low = lim.lower()
        if "suppressed" in low or "withheld" in low:
            out.append(Flag(AMBER, "A1 withheld", "A sentence was withheld", _short(_readable(lim))))
        elif "failed" in low and any(k in low for k in ("fetch", "lookup", "enrich", "discovery")):
            out.append(Flag(AMBER, "A6 retrieval", "A data source failed", _short(lim)))
        elif low.startswith("no source documents") or low.startswith("no packet"):
            out.append(Flag(AMBER, "A7 no-sources", "No public sources found", _short(lim)))

    order = {RED: 0, AMBER: 1, GREEN: 2}
    return sorted(out, key=lambda fl: order[fl.level])


_SUPPRESSED = re.compile(r"^(C\d+): suppressed by the sentence check(?: \(unsupported: (.*)\))?$")


def _readable(lim: str) -> str:
    m = _SUPPRESSED.match(lim.strip())
    if not m:
        return lim
    part = f"; the unsupported part was {m.group(2)}" if m.group(2) else ""
    return f"{m.group(1)} could not be verified as written from its cited evidence{part}."


def _is_financing(case: CaseRecord, f: Finding) -> bool:
    claim = next((c for c in case.claims if c.id == f.claim_id), None)
    return claim is None or claim.family == "F3"


def _team_evidence(case: CaseRecord) -> list[str]:
    return [e.id for e in case.evidence
            if e.kind == "graph" and ".employment_details.current" in e.locator]


def _line(case: CaseRecord, kind: str) -> dict | None:
    return next((ln for ln in case.financing if ln.get("kind") == kind), None)


_CITE = re.compile(r"\s*\[(?:E|G)\d+\]")


def _strip_cites(text: str) -> str:
    return _CITE.sub("", text).strip()


def considerations(fl: list[Flag]) -> tuple[list[str], list[str]]:
    """(supports the case, weakens the case until resolved), one line per rule fired."""
    seen: set[str] = set()
    pro, con = [], []
    for f in fl:
        if f.rule in seen:
            continue
        seen.add(f.rule)
        (pro if f.level == GREEN else con).append(CONSIDERATION[f.rule])
    return pro, con


# ---- rendering -------------------------------------------------------------------

def _labels(case: CaseRecord) -> str:
    st = case.stats or {}
    return (f"{case.run_mode} · model: {st.get('model_source', 'unknown')} · profile "
            f"{st.get('profile', 'FULL')} · run {case.run} · reviewed {case.reviewed}")


def _company(case: CaseRecord) -> str:
    return (case.g1 or {}).get("name") or case.input.domain


def _snapshot_rows(case: CaseRecord) -> list[tuple[str, str]]:
    g1 = case.g1 or {}
    founders = ", ".join(t.name for t in case.team if t.role_join) or "none found in the graph"
    rounds = [ln for ln in case.financing if ln.get("kind") == "indexed_round"]
    latest = _strip_cites(str(rounds[0].get("line"))) if rounds else "no indexed rounds"
    total = _line(case, "total")
    return [
        ("Company", f"{_company(case)} ({case.input.domain})"),
        ("Crustdata ID", str(g1.get("company_id") or "unresolved")),
        ("Founders (graph)", founders),
        ("Latest indexed round", latest),
        ("Indexed total", _strip_cites(str(total.get("line"))) if total else "not recorded"),
        ("Sources checked", f"{len(case.documents)} documents, {len(case.evidence)} evidence rows"),
        ("Claims", f"{sum(c.selected for c in case.claims)} checked, "
                   f"{len(case.findings)} sentences emitted, "
                   f"{(case.stats or {}).get('sentences_suppressed', 0)} withheld"),
    ]


def _methodology(case: CaseRecord) -> dict:
    st = case.stats or {}
    endpoints = Counter(a.endpoint for a in case.attempts if a.stage == "crustdata")
    failed = [a for a in case.attempts if a.error]
    return {
        "sources": [(d.id, d.source, d.origin or "unknown", d.published or "unknown")
                    for d in case.documents],
        "excluded": st.get("excluded_sources", 0),
        "endpoints": sorted(endpoints.items()),
        "credits": st.get("crustdata_credits", 0),
        "model_calls": [a for a in case.attempts if a.stage.startswith("model")],
        "failed_attempts": len(failed),
        "seconds": st.get("seconds", 0),
        "agent_instructions_ignored": st.get("agent_instructions_ignored", 0),
        "not_checked": len(case.not_checked),
    }


METHOD_STEPS = [
    "Identity: the domain is resolved to one Crustdata company ID (exact primary domain first; "
    "a tie abstains).",
    "Sources: the funding announcement and coverage are picked from Crustdata's news index "
    "within ±7 days of a recorded round date, one per publisher, then fetched; text addressed "
    "to AI agents is treated as data and ignored.",
    "Claims: up to 5 material Team & Financing claims are quoted verbatim from the sources.",
    "Graph: founders' current roles and named prior employers are joined by employer ID; funding "
    "rounds are type-matched against the indexed record (Crunchbase-derived, never treated as "
    "independent).",
    "Assessment: each claim gets a status and basis under fixed rules (four clocks, one origin "
    "per announcement, secondary sales are not capital, aliases only when a source states them).",
    "Gate: code checks every amount, percentage, year and date against the cited evidence; a "
    "separate check confirms each sentence is entailed by only its cited evidence. A failure "
    "drops the clause or withholds the sentence; there is no repair.",
    "Delivery: files are written once, read back and SHA-256-hashed into a manifest; "
    "`python -m proofroom verify <run folder>` re-checks every number offline.",
]


def report_md(case: CaseRecord) -> str:
    fl = flags(case)
    pro, con = considerations(fl)
    m = _methodology(case)
    out = [f"# {_company(case)}: Diligence report (Team & Financing)", "", f"*{_labels(case)}*",
           "", f"> {DISCLAIMER}", "", "## Page 1 · Snapshot and flags", "",
           "| | |", "|---|---|"]
    out += [f"| {k} | {v} |" for k, v in _snapshot_rows(case)]
    for level, heading in ((RED, "Red flags"), (AMBER, "Open points"), (GREEN, "Green flags")):
        items = [f for f in fl if f.level == level]
        out += ["", f"### {LEVEL_MARK[level]} {heading} ({len(items)})", ""]
        out += [f"- **{f.title}**: {f.detail} {_cites(f.evidence_ids)} `{f.rule}`".rstrip()
                for f in items] or ["- None found by the rules."]

    out += ["", "## Page 2 · Team, financing and considerations", "", "### Team (Crustdata graph)",
            "", "| Founder | Current role (ID join) | Prior employers named by sources |",
            "|---|---|---|"]
    for t in case.team:
        role = "; ".join(f"{e.title} since {e.start or '?'}" for e in t.current_at_subject)
        mark = "✔" if t.role_join else "?"
        prior = ", ".join(f"{j.employer_name} {'✔' if j.basis == 'id' else '≈' if j.basis == 'name_match' else '?'}"
                          for j in t.prior_joins) or "none named"
        out.append(f"| {t.name} | {role or 'no current entry'} {mark} | {prior} |")
    if not case.team:
        out.append("| none found | | |")
    out += ["", "### Financing", ""]
    out += [f"- {ln.get('line')}" for ln in case.financing if ln.get("line")] or ["- No record."]
    out += ["", "### Considerations for the investment decision", "", f"*{DISCLAIMER}*", "",
            "**What supports the case**", ""]
    out += [f"- {c}" for c in pro] or ["- Nothing the rules could confirm."]
    out += ["", "**What weakens the case until resolved**", ""]
    out += [f"- {c}" for c in con] or ["- Nothing the rules flagged."]
    if case.questions:
        out += ["", "**Ask the founders**", ""] + [f"- {q}" for q in case.questions]

    out += ["", "## Page 3 · Methodology", "", *[f"{i}. {s}" for i, s in enumerate(METHOD_STEPS, 1)],
            "", "### This run", "",
            f"- Sources used: {len(m['sources'])} (excluded during selection: {m['excluded']})"]
    out += [f"  - {d}: {src} · origin {org} · published {pub}" for d, src, org, pub in m["sources"]]
    out += [f"- Crustdata calls: " + (", ".join(f"{e} ×{n}" for e, n in m["endpoints"]) or "none")
            + f" · credits {m['credits']}",
            f"- Model calls: {len(m['model_calls'])} · failed attempts kept: {m['failed_attempts']}",
            f"- Agent-directed instructions found in sources and ignored: "
            f"{m['agent_instructions_ignored']}",
            f"- Claims not checked (listed in the brief): {m['not_checked']}",
            f"- Run time: {m['seconds']} s", "", "### Flag rules (identical for every company)", "",
            "| Rule | Level | Fires when |", "|---|---|---|"]
    out += [f"| `{r}` | {LEVEL_LABEL[lv]} | {cond} |" for r, (lv, cond) in RULES.items()]
    out += ["", "Evidence IDs refer to the evidence list in `brief.md` (E = source passage, "
            "G = Crustdata graph value).", ""]
    return "\n".join(out)


def report_html(case: CaseRecord) -> str:
    """Printable three-page HTML (print to PDF from the browser). All text escaped."""
    e = html.escape
    fl = flags(case)
    pro, con = considerations(fl)
    m = _methodology(case)

    def flag_list(level: str) -> str:
        items = [f for f in fl if f.level == level]
        if not items:
            return "<p class='none'>None found by the rules.</p>"
        return "<ul>" + "".join(
            f"<li><b>{e(f.title)}</b>: {e(f.detail)} <span class='cite'>{e(_cites(f.evidence_ids))}</span>"
            f" <code>{e(f.rule)}</code></li>" for f in items) + "</ul>"

    snap = "".join(f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in _snapshot_rows(case))
    team = "".join(
        f"<tr><td>{e(t.name)}</td><td>{e('; '.join(f'{x.title} since {x.start or chr(63)}' for x in t.current_at_subject) or 'no current entry')} "
        f"{'✔' if t.role_join else '?'}</td><td>{e(', '.join(j.employer_name + (' ✔' if j.basis == 'id' else ' ≈' if j.basis == 'name_match' else ' ?') for j in t.prior_joins) or 'none named')}</td></tr>"
        for t in case.team) or "<tr><td colspan=3>none found</td></tr>"
    fin = "".join(f"<li>{e(str(ln.get('line')))}</li>" for ln in case.financing if ln.get("line"))
    rules = "".join(f"<tr><td><code>{e(r)}</code></td><td>{e(LEVEL_LABEL[lv])}</td><td>{e(c)}</td></tr>"
                    for r, (lv, c) in RULES.items())
    srcs = "".join(f"<li>{e(d)}: {e(s)} · origin {e(o)} · published {e(p)}</li>"
                   for d, s, o, p in m["sources"])
    steps = "".join(f"<li>{e(s)}</li>" for s in METHOD_STEPS)
    qs = "".join(f"<li>{e(q)}</li>" for q in case.questions)
    lst = lambda xs, empty: "".join(f"<li>{e(x)}</li>" for x in xs) or f"<li>{e(empty)}</li>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(_company(case))} diligence report</title>
<style>
:root {{ --fg:#1b1f24; --muted:#5b6470; --bg:#fff; --line:#d8dde3; --g:#1a7f37; --a:#9a6700; --r:#cf222e; }}
@media (prefers-color-scheme: dark) {{ :root {{ --fg:#e6edf3; --muted:#9aa4af; --bg:#0d1117; --line:#30363d; --g:#3fb950; --a:#d29922; --r:#f85149; }} }}
body {{ font: 15px/1.5 system-ui, -apple-system, Segoe UI, sans-serif; color:var(--fg); background:var(--bg); margin:0; }}
.page {{ max-width: 820px; margin: 0 auto; padding: 28px 16px; border-bottom: 1px solid var(--line); }}
h1 {{ font-size: 24px; margin: 0 0 4px; }} h2 {{ font-size: 18px; margin: 0 0 12px; }} h3 {{ font-size: 15px; margin: 18px 0 6px; }}
.labels, .none, .disc {{ color: var(--muted); }} .disc {{ border-left: 3px solid var(--line); padding-left: 10px; }}
table {{ border-collapse: collapse; width: 100%; }} th, td {{ text-align:left; vertical-align: top; padding: 5px 8px; border-bottom: 1px solid var(--line); }}
th {{ width: 30%; color: var(--muted); font-weight: 600; }} .cite {{ color: var(--muted); font-size: 13px; }}
h3.red {{ color: var(--r); }} h3.amber {{ color: var(--a); }} h3.green {{ color: var(--g); }}
code {{ font-size: 12px; color: var(--muted); }} ul {{ padding-left: 20px; }}
@media print {{ .page {{ page-break-after: always; border: 0; }} body {{ font-size: 12px; }} }}
</style></head><body>
<section class="page"><h1>{e(_company(case))}: Diligence report</h1>
<div class="labels">{e(_labels(case))}</div><p class="disc">{e(DISCLAIMER)}</p>
<h2>Page 1 · Snapshot and flags</h2><table>{snap}</table>
<h3 class="red">🔴 Red flags</h3>{flag_list(RED)}
<h3 class="amber">🟡 Open points</h3>{flag_list(AMBER)}
<h3 class="green">🟢 Green flags</h3>{flag_list(GREEN)}</section>
<section class="page"><h2>Page 2 · Team, financing and considerations</h2>
<h3>Team (Crustdata graph)</h3><table><tr><th>Founder</th><th>Current role (ID join)</th><th>Prior employers named by sources</th></tr>{team}</table>
<h3>Financing</h3><ul>{fin or '<li>No record.</li>'}</ul>
<h3>Considerations for the investment decision</h3><p class="disc">{e(DISCLAIMER)}</p>
<p><b>What supports the case</b></p><ul>{lst(pro, 'Nothing the rules could confirm.')}</ul>
<p><b>What weakens the case until resolved</b></p><ul>{lst(con, 'Nothing the rules flagged.')}</ul>
{f'<p><b>Ask the founders</b></p><ul>{qs}</ul>' if qs else ''}</section>
<section class="page"><h2>Page 3 · Methodology</h2><ol>{steps}</ol>
<h3>This run</h3><ul><li>Sources used: {len(m['sources'])} (excluded during selection: {e(str(m['excluded']))})<ul>{srcs}</ul></li>
<li>Crustdata calls: {e(', '.join(f'{k} ×{n}' for k, n in m['endpoints']) or 'none')} · credits {e(str(m['credits']))}</li>
<li>Model calls: {len(m['model_calls'])} · failed attempts kept: {m['failed_attempts']}</li>
<li>Agent-directed instructions found and ignored: {e(str(m['agent_instructions_ignored']))}</li>
<li>Claims not checked: {m['not_checked']} · run time {e(str(m['seconds']))} s</li></ul>
<h3>Flag rules (identical for every company)</h3><table><tr><th>Rule</th><th>Level</th><th>Fires when</th></tr>{rules}</table>
<p class="labels">Evidence IDs refer to the evidence list in brief.md (E = source passage, G = Crustdata graph value).</p></section>
</body></html>
"""
