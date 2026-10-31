"""Evaluate revenue estimators against reported revenue (D29). Offline: replays fixtures.

    .venv/bin/python scripts/evaluate_revenue.py            # writes docs/revenue_evaluation.md

Every company is scored leave-one-out: its own reported figure is never in the benchmark
that estimates it. Model 2 (social posts) joins the ensemble only if its own
cross-validation beat v1 on the same companies, and then with a low weight.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from proofroom import calibration as cal  # noqa: E402
from proofroom import economics  # noqa: E402

OUT = ROOT / "docs" / "revenue_evaluation.md"
V2_MODEL = ROOT / "proofroom" / "data" / "revenue_model_2.json"
V2_RESULTS = ROOT / "proofroom" / "data" / "revenue_model_2_results.json"


def _usd(v: float | None) -> str:
    if v is None:
        return "–"
    return f"${v / 1e9:,.2f}B" if v >= 1e9 else f"${v / 1e6:,.1f}M" if v >= 1e6 else f"${v / 1e3:,.0f}K"


def _pct(v: float | None) -> str:
    return "–" if v is None else f"{v:+.0%}"


def v2_status() -> tuple[bool, dict]:
    """(model 2 beat v1 in its own CV on the same companies, model 2 JSON) — rev-2 stores
    its scores under cv.model (v2) and cv.v1_same_subset."""
    try:
        m = json.loads(V2_MODEL.read_text())
    except (OSError, ValueError):
        return False, {}
    cv = m.get("cv") or {}
    v2, v1 = cv.get("model") or {}, cv.get("v1_same_subset") or {}
    ok = bool(v1 and v2 and v2.get("median_abs_log10_error", 9) < v1.get("median_abs_log10_error", 9))
    return ok, m


async def v2_point(name: str, cid: int, sig) -> float | None:
    """Model 2 estimate for one study company, offline from its social-post fixture."""
    try:
        from proofroom import revenue_model_2 as rm2
        from proofroom.crustdata import FIXTURE, Crustdata
        async with Crustdata(FIXTURE, fixture=name) as c:
            soc = await rm2.social_features_for(c, cid, rm2.AS_OF)
            rec = economics._enrich_record(c, cid) or {}
        hc = rec.get("headcount") or {}
        # same inputs as v1 (largest country, listed size bucket) so the stale-band rule applies
        return rm2.estimate_revenue_v2(
            sig, soc["features"], as_of=rm2.AS_OF,
            largest_country=str(hc.get("largest_headcount_country") or ""),
            listed_bucket=str((rec.get("basic_info") or {}).get("employee_count_range") or ""))["point_usd"]
    except Exception as e:  # noqa: BLE001 - a missing fixture just leaves v2 out
        print(f"  v2 unavailable for {name}: {type(e).__name__}: {e}"[:160])
        return None


async def main() -> int:
    gt = economics.load_ground_truth()
    rows = []
    for name, cid, domain in economics.COMPANIES:
        sig, eco = await economics.replay(name, cid, domain)
        flagged = any("namesake" in lim.lower() for lim in eco.limitations)
        primary = (sig.metrics.get("total_funding_primary_usd") or sig.metrics.get("total_funding_usd"))
        rows.append({"name": sig.company or name, "domain": domain, "headcount": sig.headcount_total,
                     "primary": primary.value if primary else None,
                     "v1": eco.revenue.point_usd, "v1_raw": eco.revenue.model_raw_usd,
                     "band": eco.revenue.crustdata_band_usd, "flagged": flagged,
                     "truth": (gt.get(domain) or {}).get("best_estimate_usd"),
                     "reliability": (((gt.get(domain) or {}).get("reported") or [{}])[0] or {}).get("reliability", "")})
    refs = [cal.RefCompany(r["domain"], r["headcount"], r["truth"], r["flagged"], r["reliability"])
            for r in rows if r["truth"] and r["headcount"]]
    v2_ok, v2_doc = v2_status()
    v2_pts: dict[str, float] = {}
    for (name, cid, domain), r in zip(economics.COMPANIES, rows):
        sig, _ = await economics.replay(name, cid, domain)
        pt = await v2_point(name, cid, sig)
        if pt:
            v2_pts[domain] = pt
    for r in rows:
        c = cal.calibrate(r["domain"], r["headcount"], r["primary"], r["v1"], refs,
                          v2_usd=v2_pts.get(r["domain"]), band=r["band"], v2_ok=v2_ok)
        r["cal"] = c
        r["benchmark"] = c.components.get("benchmark")
        r["band_mid"] = sum(r["band"]) / 2 if r["band"] else None

    truth = {r["domain"]: r["truth"] for r in rows if r["truth"]}
    est = {k: {r["domain"]: r[k] if k != "ensemble" else r["cal"].point_usd for r in rows}
           for k in ("band_mid", "v1", "benchmark", "ensemble")}
    if v2_pts:
        est["v2"] = dict(v2_pts)
    summary = {k: cal.summarize(cal.ratios(v, truth)) for k, v in est.items()}
    clean = {d: t for d, t in truth.items() if not next(r for r in rows if r["domain"] == d)["flagged"]}
    summary_clean = {k: cal.summarize(cal.ratios(v, clean)) for k, v in est.items()}

    L = ["# Revenue model evaluation (D29)", "",
         "Scored against publicly reported revenue/ARR (`proofroom/data/revenue_ground_truth.json`, "
         "cited). **Leave-one-out:** a company's own reported figure is never in the benchmark "
         "that estimates it. Offline replay of recorded Crustdata data.", "",
         f"Ensemble weights: benchmark {cal.WEIGHTS['benchmark']:.0%}, v1 {cal.WEIGHTS['v1']:.0%}, "
         f"v2 (social posts) {cal.WEIGHTS['v2']:.0%} — v2 used: **{'yes' if v2_ok else 'no'}** "
         f"({'it beat v1 in cross-validation on the same 80 companies (median |log10 err| ' + str((v2_doc.get('cv') or {}).get('model', {}).get('median_abs_log10_error')) + ' vs ' + str((v2_doc.get('cv') or {}).get('v1_same_subset', {}).get('median_abs_log10_error')) + '); the paired test is not significant, so its weight stays low' if v2_ok else 'not available or did not beat v1 in cross-validation'}).",
         "", "## Accuracy against reported revenue", "",
         "| Estimator | n | Median error | Within 30% | Within 2x | Median estimate/reported |",
         "|---|---|---|---|---|---|"]
    label = {"band_mid": "Crustdata band midpoint", "v1": "Model v1 (band-trained regression)",
             "benchmark": "Reported-revenue benchmark (LOO)", "v2": "Model v2 (v1 + social posts)",
             "ensemble": "**Calibrated ensemble**"}
    for k, s in summary.items():
        if s.get("n"):
            L.append(f"| {label[k]} | {s['n']} | {s['median_abs_pct_error']:.0%} | {s['within_30pct']:.0%} | "
                     f"{s['within_2x']:.0%} | {s['median_ratio']:.2f} |")
    L += ["", "Same, excluding companies whose headcount is flagged as inflated by namesake profiles:", "",
          "| Estimator | n | Median error | Within 30% | Within 2x | Median estimate/reported |",
          "|---|---|---|---|---|---|"]
    for k, s in summary_clean.items():
        if s.get("n"):
            L.append(f"| {label[k]} | {s['n']} | {s['median_abs_pct_error']:.0%} | {s['within_30pct']:.0%} | "
                     f"{s['within_2x']:.0%} | {s['median_ratio']:.2f} |")
    L += ["", "## Per company", "",
          "| Company | Staff | Crustdata band | v1 | v2 (social) | Benchmark (LOO) | Ensemble (range) | Reported | Ensemble error | v1 error |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        c = r["cal"]
        band = f"{_usd(r['band'][0])}–{_usd(r['band'][1])}" if r["band"] else "–"
        rng = f" ({_usd(c.low_usd)}–{_usd(c.high_usd)})" if c.low_usd else ""
        e_ens = c.point_usd / r["truth"] - 1 if r["truth"] and c.point_usd else None
        e_v1 = r["v1"] / r["truth"] - 1 if r["truth"] and r["v1"] else None
        staff = f"{r['headcount']:,.0f}" + (" ⚠️" if r["flagged"] else "")
        L.append(f"| {r['name']} | {staff} | {band} | {_usd(r['v1'])} | {_usd(v2_pts.get(r['domain']))} | {_usd(r['benchmark'])} | "
                 f"{_usd(c.point_usd)}{rng} | {_usd(r['truth'])} | {_pct(e_ens)} | {_pct(e_v1)} |")
    L += ["", "⚠️ headcount flagged as inflated by namesake profiles (excluded from the benchmark's "
          "reference set; their estimates are less reliable).", "",
          "## Notes per company", ""]
    for r in rows:
        L.append(f"- **{r['name']}**: " + "; ".join(r["cal"].notes))
    L += ["", "## Caveats", "",
          "- Only 6 companies have a reported figure (5 company/press, 1 third-party estimate); "
          "results are indicative, not statistically strong.",
          "- Reported figures mix ARR, run-rate and 'passed $X' lower bounds, at different dates.",
          "- The benchmark is built from well-known venture-backed scaleups; it does not apply to "
          "early-stage companies (Koah, TerraStack keep model v1).", ""]
    OUT.write_text("\n".join(L))
    print("\n".join(L[:30]))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
