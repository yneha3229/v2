"""Signal dashboard: growth signals, revenue estimate and the invest signal for the study
companies (offline replay; no keys).

    .venv/bin/python scripts/signal_dashboard.py         # writes docs/signal_dashboard.md

Revenue uses the bake-off's recommended pipeline (revenue_models_alt.predict_alt). The
invest signal is scoring.assess (fixed rules). Companies with a verification run (Koah,
Linear, Attio) use their verified case; the others have no claims check yet, so their
Verification pillar is set to a neutral 50 and labelled "not verified".
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from proofroom import economics, scoring  # noqa: E402
from proofroom import revenue_models_alt as alt  # noqa: E402
from proofroom.crustdata import FIXTURE, Crustdata  # noqa: E402
from proofroom.models import CaseRecord, RunInput, TeamRow  # noqa: E402

AS_OF = date(2026, 10, 31)
CHECK = 100_000.0
OUT = ROOT / "docs" / "signal_dashboard.md"


def _usd(v):
    if v is None:
        return "–"
    return f"${v / 1e9:,.2f}B" if v >= 1e9 else f"${v / 1e6:,.1f}M" if v >= 1e6 else f"${v / 1e3:,.0f}K"


def _pct(sig, key):
    m = sig.metrics.get(key)
    return "–" if m is None or m.value is None else f"{m.value:+.0f}%"


def _val(sig, key):
    m = sig.metrics.get(key)
    return None if m is None else m.value


def verified_case(domain: str) -> CaseRecord | None:
    d = ROOT / "data" / "cases" / domain.replace(".", "-")
    runs = sorted(d.glob("run-*"), key=lambda p: int(p.name[4:])) if d.is_dir() else []
    for r in reversed(runs):
        p = r / "case.json"
        if p.exists():
            return CaseRecord.model_validate_json(p.read_text())
    return None


def unverified_case(sig, domain: str) -> CaseRecord:
    team = [TeamRow(name=f.name, person_id=f.person_id, role_join=True, listed_as_founder=True)
            for f in sig.founders]
    return CaseRecord(case_id=domain.replace(".", "-"), run=0, status="NARROWED", run_mode="FIXTURE",
                      input=RunInput(domain=domain, input_mode="A", run_mode="FIXTURE"),
                      reviewed=AS_OF.isoformat(),
                      g1={"status": "MATCHED", "name": sig.company, "company_id": sig.company_id},
                      team=team)


async def row_for(name: str, cid: int, domain: str) -> dict:
    sig, eco = await economics.replay(name, cid, domain)
    async with Crustdata(FIXTURE, fixture=name) as c:
        rec = economics._enrich_record(c, cid) or {}
    hc = rec.get("headcount") or {}
    rev = alt.predict_alt(sig, eco, as_of=AS_OF,
                          largest_country=str(hc.get("largest_headcount_country") or ""),
                          listed_bucket=str((rec.get("basic_info") or {}).get("employee_count_range") or ""))
    # score with the calibrated revenue range instead of Crustdata's stale band
    if rev.get("low_usd") and rev.get("high_usd"):
        sig.revenue_band_usd = (rev["low_usd"], rev["high_usd"])
    case = verified_case(domain)
    verified = case is not None
    case = case or unverified_case(sig, domain)
    fl = scoring.flags(case, sig, AS_OF)
    pl = scoring.pillars(case, sig, fl)
    if not verified:
        for p in pl:
            if p.name == "Verification":
                p.score, p.reasons = 50.0, ["claims not verified (no source run yet): neutral 50"]
    rec_ = scoring.recommend(case, sig, fl, pl, CHECK)
    if not verified and rec_.confidence == "high":
        rec_.confidence = "medium"
    hcount = sig.headcount_total
    return {"name": sig.company or name, "domain": domain, "verified": verified, "sig": sig,
            "eco": eco, "rev": rev, "flags": fl, "pillars": pl, "rec": rec_,
            "rpe": rev["point_usd"] / hcount if rev.get("point_usd") and hcount else None}


async def main() -> int:
    rows = [await row_for(*c) for c in economics.COMPANIES]
    L = ["# Signal dashboard (offline replay, as of 2026-10-31)", "",
         "Growth and market signals from Crustdata; revenue = calibrated estimate (bake-off "
         "pipeline, LOO-validated median error 14% on 6 reported companies); signal = fixed "
         "scoring rules (`proofroom/scoring.py`). **Rules-based signal, not financial advice.** "
         "Companies marked *unverified* have no claims check yet (Verification pillar neutral).", "",
         "## Growth signals", "",
         "| Company | Staff | Staff YoY | Web visitors | Visitors YoY | Followers YoY | Last round | Crowding (funded peers 24m) |",
         "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        s = r["sig"]
        mo = _val(s, "months_since_last_round")
        L.append(f"| {r['name']} | {s.headcount_total:,.0f} | {_pct(s, 'headcount_yoy_pct')} | "
                 f"{_val(s, 'web_visitors_latest') or 0:,.0f}/mo | {_pct(s, 'web_visitors_yoy_pct')} | "
                 f"{_pct(s, 'followers_yoy_pct')} | {f'{mo:.0f} mo ago' if mo is not None else '–'} | "
                 f"{s.market.crowding} ({s.market.funded_peers_24m if s.market.funded_peers_24m is not None else '–'}) |")
    L += ["", "## Money signals", "",
          "| Company | Est. revenue (range) | Revenue / employee | Avg salary | Loaded payroll | Primary capital |",
          "|---|---|---|---|---|---|"]
    for r in rows:
        s, e, rev = r["sig"], r["eco"], r["rev"]
        cap = _val(s, "total_funding_primary_usd") or _val(s, "total_funding_usd")
        L.append(f"| {r['name']} | {_usd(rev.get('point_usd'))} ({_usd(rev.get('low_usd'))}–{_usd(rev.get('high_usd'))}) | "
                 f"{_usd(r['rpe'])} | {_usd(e.payroll.avg_salary_usd)} | {_usd(e.payroll.loaded_cost_usd)} | {_usd(cap)} |")
    L += ["", "## Invest signal", "",
          "| Company | Signal | Score | Confidence | Suggested (of $100K) | 🛑/🔴/🟡/🟢 | Strongest / weakest pillar | Key red flag |",
          "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        rec, fl, pl = r["rec"], r["flags"], r["pillars"]
        cnt = {lv: sum(f.level == lv for f in fl) for lv in ("critical", "red", "amber", "green")}
        best, worst = max(pl, key=lambda p: p.score), min(pl, key=lambda p: p.score)
        red = next((f"{f.title}" for f in fl if f.level in ("critical", "red")), "none")
        L.append(f"| {r['name']}{'' if r['verified'] else ' *(unverified)*'} | **{rec.rating}** | {rec.score:.0f} | "
                 f"{rec.confidence} | {_usd(rec.suggested_usd) if rec.suggested_usd else '$0'} | "
                 f"{cnt['critical']}/{cnt['red']}/{cnt['amber']}/{cnt['green']} | "
                 f"{best.name} {best.score:.0f} / {worst.name} {worst.score:.0f} | {red} |")
    L += ["", "## Why each revenue estimate is where it is", ""]
    for r in rows:
        why = (r['rev'].get('reason') or '; '.join(r['rev'].get('flags') or [])).replace('No reported revenue to compare: ', '')
        L.append(f"- **{r['name']}**: {why}")
    OUT.write_text("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
