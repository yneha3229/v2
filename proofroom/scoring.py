"""Investment signal (D24): flags, pillar scores, rating and position sizing.

Everything here is a fixed, published rule over verified evidence (CaseRecord) and
indexed metrics (Signals), so two companies are scored the same way and every
point of the score can be traced to an input. No model is involved.

Flag levels (user decision, 12:40):
- critical: integrity and legal problems: identity, conflicting sources, a record
  that contradicts the announcement, a listed founder with no current role,
  legal-risk news, a company that is not active.
- red: business risks: shrinking team or traffic, crowded market, stale funding,
  underperforming peers, a thin team for the company's age, falling revenue.
- amber: open points that need a person or more data.
- green: verified strengths.

Rating: INVEST / ACCUMULATE / HOLD / AVOID from the weighted pillar score, capped by
critical and red flags; sizing is a share of the reader's standard check, scaled
by confidence (data coverage). It is a rules-based signal, not financial advice.
"""
from __future__ import annotations

from datetime import date

from proofroom import report as verif
from proofroom.models import CaseRecord
from proofroom.research_models import Flag, Pillar, Recommendation, Signals

DISCLAIMER = ("Rules-based signal computed from public sources and Crustdata's indexed data "
              "(including estimates). It is not financial advice and does not replace "
              "diligence, references or legal review. Private-company financial statements "
              "are not public; revenue figures are third-party estimates.")

WEIGHTS = {"Team": 0.25, "Traction": 0.30, "Market": 0.15, "Financing": 0.15,
           "Verification": 0.15}

# rating thresholds on the 0-100 weighted score
THRESHOLDS = [(70.0, "INVEST"), (58.0, "ACCUMULATE"), (45.0, "HOLD"), (0.0, "AVOID")]
SIZING = {"INVEST": 1.0, "ACCUMULATE": 0.5, "HOLD": 0.0, "AVOID": 0.0}
CONFIDENCE_MULT = {"high": 1.0, "medium": 0.75, "low": 0.5}

CROWDED_FUNDED_PEERS = 15      # mirrors signals.py crowding "high"
REGULATED_NAICS_PREFIXES = ("52", "62", "92")  # finance & insurance, health care, public admin

# Rule id -> (level, condition). Printed in the methodology.
RULES: dict[str, tuple[str, str]] = {
    "C1 identity": ("critical", "The domain did not resolve to exactly one Crustdata company"),
    "C2 conflict": ("critical", "Comparable sources contradict each other on a selected claim"),
    "C3 record-differs": ("critical", "An announced round differs from Crustdata's indexed record"),
    "C4 founder-no-role": ("critical", "A founder listed by Crustdata has no current role at the company"),
    "C5 legal-news": ("critical", "Indexed news mentions a lawsuit, fraud, investigation, breach, "
                                  "settlement, regulator probe or bankruptcy"),
    "C6 not-active": ("critical", "Crustdata lists the company as not active"),
    "R1 headcount-decline": ("red", "Headcount fell more than 10% year on year (or 15% in 6 months)"),
    "R2 traffic-decline": ("red", "Web visitors fell more than 30% year on year (or 25% in 3 months)"),
    "R3 crowded-market": ("red", f"{CROWDED_FUNDED_PEERS}+ peers in the same category raised money "
                                 "in the last 24 months"),
    "R4 stale-funding": ("red", "More than 24 months since the last round and the team is not growing"),
    "R5 lagging-peers": ("red", "Headcount growth trails the peer median by more than 30 points"),
    "R6 thin-team": ("red", "Fewer than 5 people more than 2 years after founding"),
    "R7 revenue-down": ("red", "The estimated revenue band moved down over the series"),
    "R8 layoffs-news": ("red", "Indexed news mentions layoffs or a shutdown"),
    "A1 verification-open": ("amber", "A claim is qualified, corrected, not established or withheld"),
    "A2 secondary-total": ("amber", "The indexed total includes secondary sales (liquidity, not capital)"),
    "A3 data-gap": ("amber", "A key data group is missing, so part of the score is a default"),
    "A4 regulated-sector": ("amber", "The company's NAICS code is in a regulated sector"),
    "G1 verified-round": ("green", "An announced round matches the indexed record"),
    "G2 team-joined": ("green", "Every listed founder holds a current role at the company (ID join)"),
    "G3 strong-growth": ("green", "Headcount grew more than 30% year on year"),
    "G4 traffic-growth": ("green", "Web visitors grew more than 30% year on year"),
    "G5 recent-raise": ("green", "Raised in the last 12 months"),
    "G6 notable-founders": ("green", "A founder previously founded a company or worked at a notable "
                                     "tech company or scaleup"),
    "G7 beats-peers": ("green", "Headcount growth beats the peer median by more than 20 points"),
    "G8 audience-growth": ("green", "Followers grew more than 50% year on year"),
}


def _m(sig: Signals, key: str) -> float | None:
    met = sig.metrics.get(key)
    return None if met is None or met.value is None else float(met.value)


def _fmt_pct(v: float) -> str:
    return f"{v:+.0f}%"


def flags(case: CaseRecord, sig: Signals, today: date | None = None) -> list[Flag]:
    out: list[Flag] = []
    # --- verification flags, re-levelled: integrity problems are critical ---
    remap = {"R1 identity": "C1 identity", "R2 conflict": "C2 conflict",
             "R3 record-differs": "C3 record-differs", "R4 founder-no-join": "C4 founder-no-role"}
    for f in verif.flags(case):
        if f.level == verif.RED:
            out.append(Flag(level="critical", rule=remap.get(f.rule, f.rule), title=f.title,
                            detail=f.detail, evidence=f.evidence_ids))
        elif f.level == verif.AMBER:
            rule = "A2 secondary-total" if f.rule == "A5 secondary" else (
                "A3 data-gap" if f.rule in ("A6 retrieval", "A7 no-sources") else "A1 verification-open")
            out.append(Flag(level="amber", rule=rule, title=f.title, detail=f.detail,
                            evidence=f.evidence_ids))
        elif f.rule in ("G1 round-confirmed", "G3 founders-joined"):
            rule = "G1 verified-round" if f.rule.startswith("G1") else "G2 team-joined"
            if not any(x.rule == rule and x.detail == f.detail for x in out):
                out.append(Flag(level="green", rule=rule, title=f.title, detail=f.detail,
                                evidence=f.evidence_ids))

    # --- legal / status ---
    for n in sig.news:
        low = n.title.lower()
        if n.kind == "legal_risk":
            if any(k in low for k in ("layoff", "laid off", "shut down", "shuts down")):
                out.append(Flag(level="red", rule="R8 layoffs-news", title="Layoffs or shutdown in the news",
                                detail=f"{n.title} ({n.publisher or n.url}, {n.date or 'date unknown'})",
                                evidence=[n.url]))
            else:
                out.append(Flag(level="critical", rule="C5 legal-news", title="Legal-risk news",
                                detail=f"{n.title} ({n.publisher or n.url}, {n.date or 'date unknown'})",
                                evidence=[n.url]))
    if sig.status and sig.status.lower() not in ("active", "operating", ""):
        out.append(Flag(level="critical", rule="C6 not-active", title="Company not listed as active",
                        detail=f"Crustdata status: {sig.status}", evidence=["metric:status"]))

    # --- business red flags and growth greens ---
    hc_yoy, hc_6m = _m(sig, "headcount_yoy_pct"), _m(sig, "headcount_6m_pct")
    if (hc_yoy is not None and hc_yoy < -10) or (hc_6m is not None and hc_6m < -15):
        out.append(Flag(level="red", rule="R1 headcount-decline", title="Team is shrinking",
                        detail=f"Headcount {_fmt_pct(hc_yoy) if hc_yoy is not None else 'n/a'} YoY, "
                               f"{_fmt_pct(hc_6m) if hc_6m is not None else 'n/a'} over 6 months",
                        evidence=["metric:headcount_yoy_pct"]))
    elif hc_yoy is not None and hc_yoy > 30:
        out.append(Flag(level="green", rule="G3 strong-growth", title="Team growing fast",
                        detail=f"Headcount {_fmt_pct(hc_yoy)} year on year "
                               f"(now {sig.headcount_total:.0f})" if sig.headcount_total else
                               f"Headcount {_fmt_pct(hc_yoy)} year on year",
                        evidence=["metric:headcount_yoy_pct"]))

    tr_yoy, tr_qoq = _m(sig, "web_visitors_yoy_pct"), _m(sig, "web_visitors_qoq_pct")
    if (tr_yoy is not None and tr_yoy < -30) or (tr_qoq is not None and tr_qoq < -25):
        out.append(Flag(level="red", rule="R2 traffic-decline", title="Web traffic falling",
                        detail=f"Visitors {_fmt_pct(tr_yoy) if tr_yoy is not None else 'n/a'} YoY, "
                               f"{_fmt_pct(tr_qoq) if tr_qoq is not None else 'n/a'} over 3 months",
                        evidence=["metric:web_visitors_yoy_pct"]))
    elif tr_yoy is not None and tr_yoy > 30:
        out.append(Flag(level="green", rule="G4 traffic-growth", title="Web traffic growing",
                        detail=f"Visitors {_fmt_pct(tr_yoy)} year on year",
                        evidence=["metric:web_visitors_yoy_pct"]))

    fo_yoy = _m(sig, "followers_yoy_pct")
    if fo_yoy is not None and fo_yoy > 50:
        out.append(Flag(level="green", rule="G8 audience-growth", title="Audience growing",
                        detail=f"Followers {_fmt_pct(fo_yoy)} year on year",
                        evidence=["metric:followers_yoy_pct"]))

    mk = sig.market
    if mk.funded_peers_24m is not None and mk.funded_peers_24m >= CROWDED_FUNDED_PEERS:
        out.append(Flag(level="red", rule="R3 crowded-market", title="Crowded market",
                        detail=f"{mk.funded_peers_24m} peers in '{mk.category}' raised money in the "
                               f"last 24 months (of {mk.peer_count} found)",
                        evidence=["metric:market"]))
    med = mk.median_peer_headcount_yoy_pct
    if med is not None and hc_yoy is not None:
        if hc_yoy < med - 30:
            out.append(Flag(level="red", rule="R5 lagging-peers", title="Growing slower than peers",
                            detail=f"Headcount {_fmt_pct(hc_yoy)} YoY vs peer median {_fmt_pct(med)}",
                            evidence=["metric:market"]))
        elif hc_yoy > med + 20:
            out.append(Flag(level="green", rule="G7 beats-peers", title="Growing faster than peers",
                            detail=f"Headcount {_fmt_pct(hc_yoy)} YoY vs peer median {_fmt_pct(med)}",
                            evidence=["metric:market"]))

    months = _m(sig, "months_since_last_round")
    if months is not None:
        if months > 24 and (hc_yoy is None or hc_yoy <= 0):
            out.append(Flag(level="red", rule="R4 stale-funding", title="Funding is stale",
                            detail=f"{months:.0f} months since the last indexed round and the team "
                                   "is not growing", evidence=["metric:months_since_last_round"]))
        elif months <= 12:
            out.append(Flag(level="green", rule="G5 recent-raise", title="Recently funded",
                            detail=f"Last indexed round {months:.0f} months ago",
                            evidence=["metric:months_since_last_round"]))

    today = today or date.today()
    if sig.year_founded and sig.headcount_total is not None and sig.headcount_total < 5 \
            and today.year - sig.year_founded > 2:
        out.append(Flag(level="red", rule="R6 thin-team", title="Thin team for its age",
                        detail=f"{sig.headcount_total:.0f} people, founded {sig.year_founded}",
                        evidence=["metric:headcount_total"]))

    trend = _m(sig, "revenue_trend")
    if trend is not None and trend < 0:
        out.append(Flag(level="red", rule="R7 revenue-down", title="Revenue estimate falling",
                        detail="The estimated revenue band moved down over the series "
                               "(third-party estimate)", evidence=["metric:revenue_trend"]))

    notable = [f for f in sig.founders if f.prior_founder or f.big_tech_or_scaleup]
    if notable:
        bits = []
        for f in notable[:3]:
            parts = (["previous founder"] if f.prior_founder else []) + f.big_tech_or_scaleup[:3]
            bits.append(f"{f.name} ({', '.join(parts)})")
        out.append(Flag(level="green", rule="G6 notable-founders", title="Experienced founders",
                        detail="; ".join(bits), evidence=["metric:founders"]))

    if mk.naics and mk.naics.startswith(REGULATED_NAICS_PREFIXES):
        out.append(Flag(level="amber", rule="A4 regulated-sector", title="Regulated sector",
                        detail=f"NAICS {mk.naics}: expect licensing and compliance diligence",
                        evidence=["metric:market"]))
    missing = [g for g in ("headcount", "web_traffic", "funding") if sig.coverage.get(g) is False]
    if missing:
        out.append(Flag(level="amber", rule="A3 data-gap", title="Data gaps",
                        detail="No data for: " + ", ".join(missing), evidence=["metric:coverage"]))

    order = {"critical": 0, "red": 1, "amber": 2, "green": 3}
    return sorted(out, key=lambda f: order[f.level])


# ---- pillars ---------------------------------------------------------------------

def _interp(x: float, pts: list[tuple[float, float]]) -> float:
    """Piecewise-linear map, clamped at the ends."""
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def pillars(case: CaseRecord, sig: Signals, fl: list[Flag]) -> list[Pillar]:
    rules = [f.rule for f in fl]
    out: list[Pillar] = []

    # Team
    team, why = 45.0, []
    listed = [t for t in case.team if t.listed_as_founder or t.source == "people.founders"]
    if listed:
        joined = sum(t.role_join for t in listed)
        team += 15 * joined / len(listed)
        why.append(f"{joined}/{len(listed)} listed founders ID-joined to the company")
    if len({t.name for t in case.team if t.role_join}) >= 2:
        team += 10
        why.append("more than one founder")
    if any(f.prior_founder for f in sig.founders):
        team += 15
        why.append("a founder has founded before")
    if any(f.big_tech_or_scaleup for f in sig.founders):
        team += 10
        why.append("notable prior employers")
    if "C4 founder-no-role" in rules:
        team -= 25
        why.append("a listed founder has no current role")
    out.append(Pillar(name="Team", score=_clamp(team), weight=WEIGHTS["Team"], reasons=why))

    # Traction
    why = []
    hc_yoy = _m(sig, "headcount_yoy_pct")
    if hc_yoy is None:
        trac = 45.0
        why.append("no headcount trend (default)")
    else:
        trac = _interp(hc_yoy, [(-30, 10), (0, 40), (30, 62), (100, 82), (250, 95)])
        why.append(f"headcount {_fmt_pct(hc_yoy)} YoY")
    tr = _m(sig, "web_visitors_yoy_pct")
    if tr is not None:
        adj = _interp(tr, [(-50, -12), (0, 0), (50, 6), (200, 10)])
        trac += adj
        why.append(f"web visitors {_fmt_pct(tr)} YoY")
    fo = _m(sig, "followers_yoy_pct")
    if fo is not None:
        trac += _interp(fo, [(-20, -4), (0, 0), (100, 4), (400, 6)])
        why.append(f"followers {_fmt_pct(fo)} YoY")
    if "R7 revenue-down" in rules:
        trac -= 10
        why.append("revenue estimate falling")
    out.append(Pillar(name="Traction", score=_clamp(trac), weight=WEIGHTS["Traction"], reasons=why))

    # Market
    mk, why = sig.market, []
    mkt = {"low": 75.0, "medium": 55.0, "high": 30.0}.get(mk.crowding, 50.0)
    why.append(f"crowding {mk.crowding}" + (f" ({mk.funded_peers_24m} funded peers in 24 months)"
                                            if mk.funded_peers_24m is not None else ""))
    if "G7 beats-peers" in rules:
        mkt += 12
        why.append("growing faster than peers")
    if "R5 lagging-peers" in rules:
        mkt -= 12
        why.append("growing slower than peers")
    if "A4 regulated-sector" in rules:
        mkt -= 5
        why.append("regulated sector")
    out.append(Pillar(name="Market", score=_clamp(mkt), weight=WEIGHTS["Market"], reasons=why))

    # Financing
    why = []
    months = _m(sig, "months_since_last_round")
    if months is None:
        fin = 35.0
        why.append("no dated round in the record")
    else:
        fin = _interp(months, [(0, 85), (12, 72), (24, 55), (36, 35), (60, 20)])
        why.append(f"last round {months:.0f} months ago")
    rounds = _m(sig, "num_rounds")
    if rounds and rounds >= 3:
        fin += 5
        why.append(f"{rounds:.0f} indexed rounds")
    if "G1 verified-round" in rules:
        fin += 5
        why.append("announced round verified against the record")
    if "R4 stale-funding" in rules:
        fin -= 10
    out.append(Pillar(name="Financing", score=_clamp(fin), weight=WEIGHTS["Financing"], reasons=why))

    # Verification
    crit = sum(f.level == "critical" for f in fl)
    open_n = sum(f.rule == "A1 verification-open" for f in fl)
    emitted = len(case.findings)
    ver = 100.0 - 30 * crit - 6 * open_n - (20 if emitted < 3 else 0)
    why = [f"{emitted} verified sentences", f"{crit} critical flags", f"{open_n} open points"]
    out.append(Pillar(name="Verification", score=_clamp(ver), weight=WEIGHTS["Verification"],
                      reasons=why))
    return out


# ---- recommendation ------------------------------------------------------------------

def confidence(case: CaseRecord, sig: Signals) -> str:
    checks = [
        sig.coverage.get("headcount", False) and "headcount" in sig.series,
        sig.coverage.get("web_traffic", False),
        sig.coverage.get("funding", True) and _m(sig, "months_since_last_round") is not None,
        bool(sig.founders),
        sig.market.crowding != "unknown",
        len(case.findings) >= 3,
        (case.g1 or {}).get("status") == "MATCHED",
    ]
    share = sum(bool(c) for c in checks) / len(checks)
    return "high" if share >= 0.85 else "medium" if share >= 0.6 else "low"


def recommend(case: CaseRecord, sig: Signals, fl: list[Flag], pl: list[Pillar],
              check_size_usd: float = 100_000.0) -> Recommendation:
    score = round(sum(p.score * p.weight for p in pl), 1)
    rating = next(r for t, r in THRESHOLDS if score >= t)
    crit = sum(f.level == "critical" for f in fl)
    red = sum(f.level == "red" for f in fl)
    caps = []
    if crit >= 2:
        rating, caps = "AVOID", caps + [f"{crit} critical flags force AVOID"]
    elif crit == 1 and rating in ("INVEST", "ACCUMULATE"):
        rating, caps = "HOLD", caps + ["a critical flag caps the rating at HOLD"]
    if red >= 3 and rating in ("INVEST", "ACCUMULATE"):
        rating, caps = "HOLD", caps + [f"{red} red flags cap the rating at HOLD"]
    elif red >= 1 and rating == "INVEST":
        rating, caps = "ACCUMULATE", caps + ["red flags cap the rating at ACCUMULATE"]
    conf = confidence(case, sig)
    if conf == "low" and rating == "INVEST":
        rating, caps = "ACCUMULATE", caps + ["low data coverage caps the rating at ACCUMULATE"]

    pct = SIZING[rating] * CONFIDENCE_MULT[conf]
    suggested = round(check_size_usd * pct / 5_000) * 5_000 if pct else 0.0
    best = sorted(pl, key=lambda p: -p.score)
    worst = sorted(pl, key=lambda p: p.score)
    rationale = [f"Score {score:.0f}/100 · strongest: {best[0].name} ({best[0].score:.0f}) — "
                 f"{'; '.join(best[0].reasons[:2])}",
                 f"Weakest: {worst[0].name} ({worst[0].score:.0f}) — {'; '.join(worst[0].reasons[:2])}"]
    for f in fl:
        if f.level in ("critical", "red") and len(rationale) < 5:
            rationale.append(f"{'Critical' if f.level == 'critical' else 'Red flag'}: {f.title} — {f.detail}")
    rationale += caps
    for f in fl:
        if f.level == "green" and len(rationale) < 6:
            rationale.append(f"Strength: {f.title} — {f.detail}")

    triggers = []
    if any(f.rule == "R1 headcount-decline" for f in fl):
        triggers.append("Headcount returns to growth for two consecutive quarters")
    if any(f.level == "critical" for f in fl):
        triggers.append("Every critical flag is resolved with a document")
    if any(f.rule == "R3 crowded-market" for f in fl):
        triggers.append("Evidence of a defensible wedge versus funded peers")
    triggers += [f"Answer: {q}" for q in case.questions[:2]]
    triggers.append("A new round, a founder change or a status change in Crustdata's record")

    horizon = {"INVEST": "Proceed now, subject to standard legal diligence",
               "ACCUMULATE": "Commit a first tranche now; the rest after the next milestone",
               "HOLD": "Do not commit yet; re-check in 3–6 months",
               "AVOID": "Do not proceed on current evidence"}[rating]
    reason = (worst[0].name if rating in ("HOLD", "AVOID") else best[0].name).lower()
    headline = {"INVEST": f"Strong {reason} signal with verified facts",
                "ACCUMULATE": f"Positive, led by {reason}; size down until open points close",
                "HOLD": f"Wait: {reason} does not yet support a commitment",
                "AVOID": f"Evidence does not support investing ({reason})"}[rating]
    return Recommendation(rating=rating, score=score, confidence=conf,
                          check_size_usd=check_size_usd, suggested_usd=float(suggested),
                          sizing_pct=round(pct * 100, 1), headline=headline,
                          rationale=rationale, revisit_triggers=triggers, horizon=horizon,
                          disclaimer=DISCLAIMER)


def assess(case: CaseRecord, sig: Signals, check_size_usd: float = 100_000.0,
           today: date | None = None) -> tuple[list[Flag], list[Pillar], Recommendation]:
    fl = flags(case, sig, today)
    pl = pillars(case, sig, fl)
    return fl, pl, recommend(case, sig, fl, pl, check_size_usd)
