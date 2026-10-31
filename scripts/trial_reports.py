"""Trial equity reports (PDF) for one company per rating, with the talent and economics pages.

    .venv/bin/python scripts/trial_reports.py [domain ...]   # writes docs/reports/trial/*.pdf

Offline replay of recorded Crustdata data. Verified cases (claims checked) are used when a
run exists in data/cases; otherwise Verification is a neutral 50 and confidence is capped at
medium, as in the signal dashboard.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import signal_dashboard as sd  # noqa: E402
from proofroom import economics, equity_report, scoring, talent  # noqa: E402
from proofroom import revenue_models_alt as alt  # noqa: E402
from proofroom.crustdata import FIXTURE, Crustdata  # noqa: E402
from proofroom.research_models import Metric  # noqa: E402

AS_OF = date(2026, 10, 31)
OUT = ROOT / "docs" / "reports" / "trial"
DEFAULT = ["linear.app", "terrastack.in", "ramp.com", "retool.com"]


async def report(name: str, cid: int, domain: str) -> dict:
    sig, eco = await economics.replay(name, cid, domain)
    async with Crustdata(FIXTURE, fixture=name) as c:
        rec = economics._enrich_record(c, cid) or {}
        hc = rec.get("headcount") or {}
        rev = alt.predict_alt(sig, eco, as_of=AS_OF,
                              largest_country=str(hc.get("largest_headcount_country") or ""),
                              listed_bucket=str((rec.get("basic_info") or {}).get("employee_count_range") or ""))
        founded = (rec.get("basic_info") or {}).get("year_founded")
        sig.founders = talent.credible_founders(sig.founders, int(founded) if founded else None) or sig.founders
        country = str((rec.get("locations") or {}).get("country") or "")
        tal = await talent.build_talent(c, cid, rec, country, {f.name.lower() for f in sig.founders})
    if rev.get("low_usd") and rev.get("high_usd"):
        sig.revenue_band_usd = (rev["low_usd"], rev["high_usd"])
    if rev.get("point_usd"):
        sig.metrics["revenue_estimate_usd"] = Metric(
            key="revenue_estimate_usd", label="Revenue estimate", value=rev["point_usd"], unit="USD",
            display=equity_report.fmt_usd(rev["point_usd"]), source="revenue_models_alt (bake-off pipeline)")
    case = sd.verified_case(domain)
    verified = case is not None
    case = case or sd.unverified_case(sig, domain)
    fl = scoring.flags(case, sig, AS_OF)
    pl = scoring.pillars(case, sig, fl)
    if not verified:
        for p in pl:
            if p.name == "Verification":
                p.score, p.reasons = 50.0, ["claims not verified (no source run yet): neutral 50"]
    scoring.apply_talent(fl, pl, tal)
    r = scoring.recommend(case, sig, fl, pl, 100_000.0)
    if not verified and r.confidence == "high":
        r.confidence = "medium"
    html = equity_report.build_html(case, sig, fl, pl, r, rules=scoring.RULES,
                                    talent=tal, economics=eco, revenue=rev)
    OUT.mkdir(parents=True, exist_ok=True)
    slug = domain.split(".")[0]
    (OUT / f"{slug}.html").write_text(html)
    equity_report.render_pdf(html, OUT / f"{slug}.pdf")
    return {"name": sig.company or name, "rating": r.rating, "score": r.score, "conf": r.confidence,
            "suggested": r.suggested_usd, "verified": verified,
            "team": next(p.score for p in pl if p.name == "Team"),
            "founders": [f.name for f in sig.founders], "schools": [h.label for h in tal.founder_schools],
            "alumni": tal.alumni, "staff": tal.indexed_staff}


async def main() -> int:
    want = sys.argv[1:] or DEFAULT
    for name, cid, domain in economics.COMPANIES:
        if domain in want:
            r = await report(name, cid, domain)
            print(f"{r['name']:11} {r['rating']:10} {r['score']:5.1f} {r['conf']:6} ${r['suggested']:,.0f} "
                  f"verified={r['verified']} team={r['team']:.0f} founders={r['founders']} schools={r['schools']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
