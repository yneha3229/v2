"""Demo dashboard backend: one JSON payload per company for the /demo page, and the PDF
report on demand.

Recorded companies replay from fixtures (instant, 0 credits). A new company is identified
live and analysed the same way (Crustdata only; claims are not verified, so Verification is
a neutral 50 and confidence is capped at medium). Every payload carries its run mode.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

from . import config, economics, equity_report, public_financials, scoring, talent
from . import revenue_models_alt as alt
from .crustdata import CACHED, Crustdata
from .errors import CrustError, ProofroomError
from .research_models import Metric
from .signals import fetch_signals

log = logging.getLogger(__name__)
AS_OF = date.today()
CHECK = 100_000.0
REPORT_DIR = config.ROOT / "data" / "demo_reports"
KNOWN = {d: (n, cid) for n, cid, d in economics.COMPANIES}
_CACHE: dict[str, dict] = {}
_OBJ: dict[str, tuple] = {}
INR = equity_report.INR_PER_USD


def _clean_domain(q: str) -> str:
    q = q.strip().lower()
    q = re.sub(r"^https?://", "", q).split("/")[0]
    return q.removeprefix("www.")


def search_known(q: str) -> list[dict]:
    q = q.strip().lower()
    out = []
    for d, (n, cid) in KNOWN.items():
        if not q or q in d or q in n:
            out.append({"name": n.title() if n != "koah" else "Koah", "domain": d, "recorded": True})
    return out


async def identify(q: str) -> list[dict]:
    """Live Crustdata identify by domain (if it looks like one) or by name."""
    async with Crustdata(CACHED) as c:
        resp = await (c.identify_domain(_clean_domain(q)) if "." in q else c.identify_names([q]))
    out = []
    for block in resp or []:
        for m in (block.get("matches") or [])[:5]:
            bi = (m.get("company_data") or {}).get("basic_info") or {}
            if bi.get("primary_domain"):
                out.append({"name": bi.get("name"), "domain": bi.get("primary_domain"),
                            "cid": bi.get("crustdata_company_id"), "recorded": False,
                            "confidence": m.get("confidence_score")})
    return out


async def _bundle(domain: str, cid: int | None = None) -> tuple:
    domain = _clean_domain(domain)
    if domain in KNOWN:
        name, cid = KNOWN[domain]
        cache_dir, mode_label = config.FIXTURES_DIR / name / "crustdata", "REPLAY (recorded Crustdata data)"
    else:
        cache_dir, mode_label = config.CACHE_DIR / "crustdata", "LIVE (Crustdata, claims not verified)"
        if cid is None:
            hits = await identify(domain)
            if not hits:
                raise ProofroomError(f"No Crustdata company found for {domain!r}")
            cid = int(hits[0]["cid"])
    async with Crustdata(CACHED, cache_dir=cache_dir) as c:
        sig = await fetch_signals(c, int(cid), domain, today=AS_OF, search=True, jobs=True, logo=True)
        eco = await economics.build_economics(c, sig, int(cid))
        rec = economics._enrich_record(c, int(cid)) or {}
        hc = rec.get("headcount") or {}
        rev = alt.predict_alt(sig, eco, as_of=AS_OF,
                              largest_country=str(hc.get("largest_headcount_country") or ""),
                              listed_bucket=str((rec.get("basic_info") or {}).get("employee_count_range") or ""))
        founded = (rec.get("basic_info") or {}).get("year_founded")
        sig.founders = talent.credible_founders(sig.founders, int(founded) if founded else None) or sig.founders
        country = str((rec.get("locations") or {}).get("country") or "")
        tal = await talent.build_talent(c, int(cid), rec, country, {f.name.lower() for f in sig.founders})
        try:
            staff = await c.request("POST", economics.PERSON_SEARCH, economics.sample_body(int(cid), economics.SAMPLE_N))
            tal.staff = talent.staff_history(staff, int(cid))
        except CrustError as e:
            log.warning("staff sample failed: %s", e)
    # D32: a listed company's filed accounts replace the model estimate
    fin, note = await public_financials.reported_financials(rec)
    if fin and fin["currency"] != "USD":
        fin, note = None, f"{fin['ticker']} reports in {fin['currency']}; revenue is a model estimate"
    if fin:
        rev = public_financials.as_revenue(fin, rev, sig.headcount_total)
    elif public_financials.is_public(rec):
        rev["public_note"] = note
        sig.limitations.append(f"Listed company, but {note}: revenue is a model estimate")
    if rev.get("low_usd") and rev.get("high_usd"):
        sig.revenue_band_usd = (rev["low_usd"], rev["high_usd"])
    if rev.get("point_usd"):
        sig.metrics["revenue_estimate_usd"] = Metric(
            key="revenue_estimate_usd",
            label=f"Revenue (reported, FY ending {fin['fiscal_year_end']})" if fin else "Revenue estimate",
            value=rev["point_usd"], unit="USD", display=equity_report.fmt_usd(rev["point_usd"]),
            source=fin["source"] if fin else "revenue_models_alt")
    import sys
    sys.path.insert(0, str(config.ROOT / "scripts"))
    import signal_dashboard as sd  # verified case lookup + unverified stub
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
    r = scoring.recommend(case, sig, fl, pl, CHECK)
    if not verified and r.confidence == "high":
        r.confidence = "medium"
    return domain, sig, eco, rev, tal, case, fl, pl, r, verified, mode_label, rec


def _series(sig, key: str) -> list[list]:
    s = sig.series.get(key)
    pts = getattr(s, "points", None) or []
    return [[p.date, p.value] for p in pts if p.value is not None]


def _m(sig, key: str):
    m = sig.metrics.get(key)
    return None if m is None else m.value


def _payload(b: tuple) -> dict:
    domain, sig, eco, rev, tal, case, fl, pl, r, verified, mode, rec = b
    pay = eco.payroll
    market = "india" if any("india" in k.lower() for k in (pay.by_location or {})) and \
        max(pay.by_location, key=pay.by_location.get, default="").lower().find("india") >= 0 else "us"
    ctx = [{"label": k, "usd": v} for k, v in equity_report.PAY_CONTEXT[market]]
    bm = economics.Benchmarks.load() if hasattr(economics, "Benchmarks") else None
    sf = None
    try:
        import json
        cells = {(x["role"], x["location"]): x["annual_usd"] for x in json.loads(
            (config.ROOT / "proofroom/data/salary_benchmarks.json").read_text(encoding="utf-8"))["benchmarks"]}
        rmap = {"Data & Research": "Data Science"}
        sf = sum(n * (cells.get((rmap.get(k, k), "San Francisco Bay Area")) or cells[("Other", "San Francisco Bay Area")])
                 for k, n in (pay.by_role or {}).items()) * pay.overhead_multiplier
    except Exception:  # noqa: BLE001 - optional comparison
        sf = None
    prim = _m(sig, "total_funding_primary_usd") or _m(sig, "total_funding_usd")
    mk = sig.market
    rounds = equity_report.funding_rounds(case)
    checklist = equity_report._red_flag_checklist(case, sig, fl)
    return {
        "domain": domain, "mode": mode, "verified": verified, "as_of": AS_OF.isoformat(),
        "company": {"name": sig.company, "description": sig.description, "founded": sig.year_founded,
                    "hq": sig.hq, "status": sig.status, "logo": sig.logo_data_uri if sig.logo_data_uri.startswith("data:image/") else "",
                    "cid": sig.company_id},
        "rec": {"rating": r.rating, "score": r.score, "confidence": r.confidence, "suggested": r.suggested_usd,
                "check": r.check_size_usd, "headline": r.headline, "rationale": r.rationale,
                "horizon": r.horizon, "triggers": r.revisit_triggers, "disclaimer": r.disclaimer},
        "pillars": [{"name": p.name, "score": p.score, "weight": p.weight, "reasons": p.reasons} for p in pl],
        "flags": [{"level": f.level, "rule": f.rule, "title": f.title, "detail": f.detail} for f in fl],
        "rules": {k: v[1] if isinstance(v, tuple) else v for k, v in scoring.RULES.items()},
        "thresholds": [[t, n] for t, n in scoring.THRESHOLDS],
        "kpi": {"headcount": sig.headcount_total, "headcount_yoy": _m(sig, "headcount_yoy_pct"),
                "headcount_6m": _m(sig, "headcount_6m_pct"), "web": _m(sig, "web_visitors_latest"),
                "web_yoy": _m(sig, "web_visitors_yoy_pct"), "web_qoq": _m(sig, "web_visitors_qoq_pct"),
                "followers": _m(sig, "followers_count"), "followers_yoy": _m(sig, "followers_yoy_pct"),
                "months_since_round": _m(sig, "months_since_last_round"), "capital": prim,
                "eng_share": _m(sig, "engineering_share_pct"), "jobs": _m(sig, "job_postings_90d")},
        "series": {k: _series(sig, k) for k in ("headcount", "web_visitors", "followers")},
        "revenue": {k: rev.get(k) for k in ("point_usd", "low_usd", "high_usd", "drivers", "components",
                                            "band_usd", "band_trusted", "early_stage", "namesake",
                                            "intercept_log10", "revenue_per_employee_usd", "method",
                                            "reason", "flags", "listed_bucket", "label", "reported",
                                            "model_estimate_usd", "public_note")},
        "payroll": {"avg": pay.avg_salary_usd, "avg_range": pay.avg_salary_range_usd,
                    "base": pay.annual_payroll_usd, "loaded": pay.loaded_cost_usd,
                    "overhead": pay.overhead_multiplier, "switch": pay.switch_premium,
                    "by_location": pay.by_location, "by_role": pay.by_role, "market": market,
                    "context": ctx, "inr_per_usd": INR, "sf_equivalent": sf,
                    "runway_months": (prim / (pay.loaded_cost_usd / 12)) if prim and pay.loaded_cost_usd else None,
                    "samples": [{"title": s.title, "location": s.location, "prior": s.prior_employer,
                                 "est": s.est_salary_usd, "method": s.method} for s in pay.samples[:8]]},
        "customers": {"model": eco.customers.business_model, "targets": eco.customers.target_customers,
                      "use_cases": eco.customers.use_cases},
        "talent": {"founders_total": tal.founders_total, "founders_elite": tal.founders_with_elite,
                   "schools": [{"person": h.person, "school": h.school, "degree": h.degree, "label": h.label,
                                "home": h.home_market} for h in tal.founder_schools],
                   "staff_indexed": tal.indexed_staff, "alumni": tal.alumni, "ex_big_tech": tal.ex_big_tech,
                   "history": [{"name": p.name, "title": p.current_title,
                                "past": [{"title": x.title, "company": x.company, "start": x.start,
                                          "intern": x.intern, "prestige": x.prestige} for x in p.past[:4]]}
                               for p in sorted(tal.staff, key=lambda p: -len(p.highlights))[:8]]},
        "founders": [{"name": f.name, "title": f.title, "since": f.since, "prior": f.prior_employers[:6],
                      "prior_founder": f.prior_founder, "notable": f.big_tech_or_scaleup} for f in sig.founders],
        "market": {"category": mk.category, "primary": (mk.category or "").split(" + ")[0] or
                   equity_report._primary_category(mk.categories), "categories": mk.categories,
                   "crowding": mk.crowding, "pool": mk.peer_count, "funded_24m": mk.funded_peers_24m,
                   "median_peer_yoy": mk.median_peer_headcount_yoy_pct,
                   "peers": [{"name": p.name, "domain": p.domain, "founded": p.year_founded, "headcount": p.headcount,
                              "yoy": p.headcount_yoy_pct, "funding": p.total_funding_usd,
                              "round": p.last_round_type, "round_date": p.last_round_date} for p in mk.peers[:8]]},
        "financing": {"rounds": rounds, "findings": [{"claim": f.claim_id, "disposition": f.disposition,
                                                      "sentence": f.sentence} for f in case.findings],
                      "questions": case.questions[:5]},
        "checklist": [{"item": i, "result": res, "detail": d} for i, res, d in checklist],
        "coverage": [{"section": s, "status": st, "note": n} for s, st, n in equity_report.COVERAGE],
        "limitations": (sig.limitations + eco.limitations)[:12],
    }


async def analyze(domain: str, cid: int | None = None) -> dict:
    key = _clean_domain(domain)
    if key not in _CACHE:
        b = await _bundle(key, cid)
        _OBJ[key] = b
        _CACHE[key] = _payload(b)
    return _CACHE[key]


async def report_pdf(domain: str) -> Path:
    key = _clean_domain(domain)
    if key not in _OBJ:
        await analyze(key)
    d, sig, eco, rev, tal, case, fl, pl, r, verified, mode, rec = _OBJ[key]
    html = equity_report.build_html(case, sig, fl, pl, r, rules=scoring.RULES, talent=tal,
                                    economics=eco, revenue=rev)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / f"{key.replace('.', '-')}-report.pdf"
    await asyncio.to_thread(equity_report.render_pdf, html, out)
    return out
