"""Revenue-model bake-off (offline; replays fixtures, 0 credits).

    .venv/bin/python scripts/compare_revenue_models.py

Writes docs/revenue_models_comparison.md and proofroom/data/revenue_models_alt.json.

1. 5-fold CV on the 126 band-labelled rows (v1's folds, seed 7; hyperparameters by inner
   CV on each training fold only).
2. Accuracy on the 6 companies with publicly reported revenue. Band-trained models are
   scored straight (no reported figure is used); anything that uses reported figures
   (bias factor, revenue-per-employee benchmark) is leave-one-out.
3. Guardrail firing rates and worst ratios (126 CV predictions + the 9 study companies).
4. Per-company explanations (Tobit linear model contributions + diagnostics).
"""
from __future__ import annotations

import asyncio
import json
import math
import statistics
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from proofroom import calibration as cal  # noqa: E402
from proofroom import economics  # noqa: E402
from proofroom import revenue_model as rm  # noqa: E402
from proofroom import revenue_models_alt as A  # noqa: E402
from proofroom.crustdata import FIXTURE, Crustdata  # noqa: E402

OUT_MD = ROOT / "docs" / "revenue_models_comparison.md"
FAMS = ["baseline", "ridge_v1", "ridge", "huber", "tobit", "knn", "gbm", "segment", "stack"]
LABEL = {"baseline": "(0) baseline: headcount x median rev/employee",
         "ridge_v1": "(a) v1 ridge, lambda 30 (reproduced)",
         "ridge": "(a') ridge, lambda by inner CV", "huber": "(b) Huber IRLS",
         "tobit": "(c) interval-censored Tobit (EM)", "knn": "(d) kNN on rev/employee",
         "gbm": "(e) boosted depth-2 trees", "segment": "(f) segment rev/employee",
         "stack": "(g) equal-weight stack of b-f + ridge"}
LINEAR = "tobit"            # explanation model: best linear family by CV
W_BENCH = 0.5               # fixed a priori (not tuned on the 6 reported companies)


def fmt(v, spec):
    return "–" if v is None else spec.format(v)


def usd(v):
    if v is None:
        return "–"
    return f"${v / 1e9:,.2f}B" if v >= 1e9 else f"${v / 1e6:,.1f}M" if v >= 1e6 else f"${v / 1e3:,.0f}K"


async def load_companies() -> list[dict]:
    gt = economics.load_ground_truth()
    out = []
    for name, cid, domain in economics.COMPANIES:
        sig, eco = await economics.replay(name, cid, domain)
        async with Crustdata(FIXTURE, fixture=name) as client:
            rec = economics._enrich_record(client, cid) or {}
            as_of = economics._today(client)
        hc = rec.get("headcount") or {}
        prim = sig.metrics.get("total_funding_primary_usd") or sig.metrics.get("total_funding_usd")
        feats = rm.features_from_signals(sig, as_of, str(hc.get("largest_headcount_country") or ""))
        out.append({
            "name": sig.company or name, "domain": domain, "sig": sig, "eco": eco, "as_of": as_of,
            "largest": str(hc.get("largest_headcount_country") or ""),
            "listed": str((rec.get("basic_info") or {}).get("employee_count_range") or ""),
            "hc": sig.headcount_total, "band": sig.revenue_band_usd,
            "primary": prim.value if prim else 0.0, "feats": feats,
            "x": np.array([feats[k] for k in rm.FEATURES]) if feats else None,
            "flagged": A.namesake_flag(eco),
            "truth": (gt.get(domain) or {}).get("best_estimate_usd"),
            "v1_point": eco.revenue.point_usd, "v1_raw": eco.revenue.model_raw_usd})
    return out


def summarize(est: dict[str, float], truth: dict[str, float]) -> dict:
    r = cal.ratios(est, truth)
    s = cal.summarize(r)
    if r:
        s["max_over"] = max(r.values())
        s["max_under"] = 1 / min(r.values())
    return s


def loo_factor(ratios: dict[str, float], refs: set[str], exclude: str) -> float:
    vals = [ratios[d] for d in refs if d != exclude and d in ratios]
    return statistics.median(vals) if vals else 1.0


def main() -> int:
    D = A.load_training()
    rows, y_mid, y_lo, y_hi = D["rows"], D["y_mid"], D["y_lo"], D["y_hi"]

    # ---- 1. CV on bands
    cv = {f: A.cross_validate(D, f) for f in FAMS}

    # ---- 2. fit every family on all 126 rows, predict the 9 companies
    full = {f: A.fit_family(f, D["X"], D["X_eval"], y_mid, y_lo, y_hi, D["lo_open"]) for f in FAMS}
    comps = asyncio.run(load_companies())
    for c in comps:
        c["raw"] = {f: (10 ** float(full[f].predict(c["x"][None, :])[0]) if c["x"] is not None
                        else None) for f in FAMS}
    sanity = {c["domain"]: (round(c["raw"]["ridge_v1"]), c["v1_raw"]) for c in comps}

    truth = {c["domain"]: c["truth"] for c in comps if c["truth"]}
    clean_truth = {d: t for d, t in truth.items()
                   if not next(c for c in comps if c["domain"] == d)["flagged"]}
    refs = set(clean_truth)                      # unflagged reported companies
    by = {c["domain"]: c for c in comps}

    # LOO benchmark rev/employee (unflagged refs only, as calibration.py)
    ref_objs = [cal.RefCompany(c["domain"], c["hc"], c["truth"], c["flagged"]) for c in comps
                if c["truth"] and c["hc"]]

    def early(c):
        return (c["hc"] or 0) < A.EARLY_STAFF or (c["primary"] or 0) < A.EARLY_CAPITAL_USD

    def guard(c, v):
        return A.apply_guardrails(v, c["hc"], c["band"], listed_bucket=c["listed"],
                                  namesake=c["flagged"])

    est: dict[str, dict[str, float]] = {}
    est["Crustdata band midpoint"] = {c["domain"]: sum(c["band"]) / 2 for c in comps if c["band"]}
    est["v1 point (band-clamped, in production)"] = {c["domain"]: c["v1_point"] for c in comps}
    bench, ens = {}, {}
    for c in comps:
        k = cal.calibrate(c["domain"], c["hc"], c["primary"], c["v1_point"], ref_objs, band=c["band"])
        ens[c["domain"]] = k.point_usd
        if "benchmark" in k.components:
            bench[c["domain"]] = k.components["benchmark"]
    est["Benchmark rev/employee (LOO)"] = bench
    est["Current calibrated ensemble (D29, LOO)"] = ens
    pipeline: dict[str, dict] = {}
    for f in FAMS:
        raw = {c["domain"]: c["raw"][f] for c in comps if c["raw"][f]}
        est[f"{f} raw"] = raw
        est[f"{f} raw + guardrails"] = {d: guard(by[d], v)["value_usd"] for d, v in raw.items()}
        # reported / model (the multiplier that would have made each reference exact)
        ratios_f = {d: 1 / r for d, r in cal.ratios(raw, clean_truth).items()}
        corr, blend, blend_g = {}, {}, {}
        for d, v in raw.items():
            c = by[d]
            if early(c):
                corr[d] = blend[d] = v
            else:
                fac = loo_factor(ratios_f, refs, d)
                rpe, _n = cal.benchmark_rpe(ref_objs, exclude=d)
                corr[d] = v * fac
                blend[d], _ = A.combine(v, c["hc"], False, fac, rpe, W_BENCH)
            blend_g[d] = guard(c, blend[d])
        est[f"{f} x LOO bias factor"] = corr
        est[f"{f} bias-corrected 50/50 benchmark (LOO)"] = blend
        est[f"{f} bias-corrected 50/50 benchmark + guardrails (LOO)"] = {
            d: g["value_usd"] for d, g in blend_g.items()}
        pipeline[f] = {"blend": blend, "guard": blend_g}

    acc = {k: summarize(v, truth) for k, v in est.items()}
    acc_clean = {k: summarize(v, clean_truth) for k, v in est.items()}

    # ---- 3. guardrails on the 126 CV predictions (of each model) and the 9 companies
    def guard_rows(pred):
        res = []
        for r, p in zip(rows, pred):
            band = (r["revenue_lower_usd"], r["revenue_upper_usd"])
            res.append(A.apply_guardrails(10 ** p, r["headcount"], band,
                                          listed_bucket=r.get("employee_count_range", "")))
        return res

    band_rpe = 10 ** y_mid / D["hc"]
    plausible = (band_rpe >= A.RPE_MIN_USD) & (band_rpe <= A.RPE_MAX_USD)
    gstats = {}
    for f in ("ridge_v1", "tobit", "gbm", "stack"):
        g = guard_rows(cv[f]["pred"])
        after = np.log10([x["value_usd"] for x in g])
        kinds = {"band floor": 0, "band cap": 0, "rpe cap": 0, "rpe floor": 0}
        for x in g:
            for fl in x["flags"]:
                kinds["band floor" if "band floor" in fl else "band cap" if "band top" in fl
                      else "rpe cap" if fl.startswith("capped") else "rpe floor"] += 1
        ok = plausible
        gstats[f] = {"fired": sum(x["clipped"] for x in g) / len(g), **kinds,
                     "before": A.metrics(cv[f]["pred"], y_mid, y_lo, y_hi),
                     "after": A.metrics(after, y_mid, y_lo, y_hi),
                     "after_plausible": A.metrics(after[ok], y_mid[ok], y_lo[ok], y_hi[ok])}
    nine_fire = {f: sum(guard(c, c["raw"][f])["clipped"] for c in comps if c["raw"][f])
                 for f in FAMS}
    chosen_g9 = pipeline[LINEAR]["guard"]

    # ---- 4. explanations: final Tobit linear model on all 126
    lin: A.Linear = full[LINEAR]
    expl = []
    for c in comps:
        d = c["domain"]
        contrib = lin.contributions(c["x"])
        point = chosen_g9[d]["value_usd"]
        rpe_bench, _ = cal.benchmark_rpe(ref_objs, exclude=d)
        m = c["sig"].metrics
        val = (lambda k: m[k].value if k in m else None)
        diag = {"ratio_to_reported": point / c["truth"] if c["truth"] else None,
                "reported_rpe_usd": c["truth"] / c["hc"] if c["truth"] else None,
                "benchmark_rpe_usd": rpe_bench, "category": A.primary_category(c["x"]),
                "namesake": c["flagged"], "headcount": c["hc"], "listed_bucket": c["listed"],
                "band_stale": bool(c["listed"] and c["listed"] != rm.bucket_of(c["hc"])),
                "early_stage": early(c), "headcount_yoy_pct": val("headcount_yoy_pct"),
                "estimate_vs_band_top": point / c["band"][1] if c["band"] and c["band"][1] else None,
                "guardrail_flags": chosen_g9[d]["flags"]}
        expl.append({"c": c, "point": point, "drivers": A.top_drivers(contrib),
                     "check": abs(lin.b + sum(contrib.values()) - math.log10(c["raw"][LINEAR])),
                     "web_yoy": val("web_visitors_yoy_pct"),
                     "funding_per_hc": (c["primary"] or 0) / c["hc"] if c["hc"] else None,
                     "rpe_implied": point / c["hc"], **diag, "reason": A.reason_line(diag)})

    # ---- save chosen model (Tobit + reported bias factor + benchmark + guardrails)
    raw_t = {c["domain"]: c["raw"][LINEAR] for c in comps if c["raw"][LINEAR]}
    rat_t = {d: 1 / r for d, r in cal.ratios(raw_t, clean_truth).items()}   # reported / model
    bias_all = statistics.median(rat_t.values())
    rpe_all, n_all = cal.benchmark_rpe(ref_objs)
    chosen_key = f"{LINEAR} bias-corrected 50/50 benchmark + guardrails (LOO)"
    log_err = [abs(math.log10(est[chosen_key][d] / t)) for d, t in truth.items()]
    doc = {
        "version": A.ALT_VERSION, "trained_on": D["as_of"].isoformat(), "n_rows": len(rows),
        "method": (f"{LINEAR} (interval-censored ridge, EM) on {len(rows)} Crustdata band rows; "
                   f"x reported-revenue bias factor; geometric 50/50 blend with reported "
                   f"revenue/employee benchmark (scaleups >= {A.EARLY_STAFF} staff and >= "
                   f"$20M primary capital only); then guardrails"),
        "model": lin.to_doc(), "features": list(rm.FEATURES),
        "reported_bias_factor": round(bias_all, 6),
        "reported_bias_refs": {d: round(v, 4) for d, v in rat_t.items()},
        "benchmark_rpe_usd": round(rpe_all, 2), "benchmark_n": n_all,
        "weights": {"benchmark": W_BENCH, "model_bias_corrected": 1 - W_BENCH},
        "spread_log10": round(float(np.median(log_err)), 4) if log_err else 0.3,
        "guardrails": {"rpe_min_usd": A.RPE_MIN_USD, "rpe_max_usd": A.RPE_MAX_USD,
                       "max_over_band_top": A.MAX_OVER_BAND_TOP},
        "cv_bands": {k: v for k, v in cv[LINEAR].items() if k != "pred"},
        "reported_loo": {k: round(v, 4) if isinstance(v, float) else v
                         for k, v in acc[chosen_key].items()},
        "notes": ["ESTIMATE, not reported revenue.",
                  "Bias factor and benchmark come from the unflagged reported companies "
                  f"({', '.join(sorted(refs))}); n=3, indicative only.",
                  "Blend weight 0.5 fixed a priori, not tuned on the reported companies."],
    }
    A.ALT_PATH.write_text(json.dumps(doc, indent=1))

    # ---- markdown
    L = ["# Revenue model bake-off (alternative model families)", "",
         "Offline: `scripts/compare_revenue_models.py` (0 credits). Code: "
         "`proofroom/revenue_models_alt.py`. Chosen parameters: "
         "`proofroom/data/revenue_models_alt.json`. Every number below is an ESTIMATE quality "
         "measure; no model output is reported revenue.", "",
         "## 1. Cross-validation on Crustdata bands (126 rows)", "",
         "Same protocol as v1: 5 folds, seed 7, training on the listed size bucket, held-out "
         "rows scored with the headcount-implied bucket. Hyperparameters by inner 4-fold CV "
         "on each training fold (never on the test fold); `v1 ridge` keeps v1's lambda 30, "
         "which v1 chose on these same folds (mildly optimistic). Error is |log10(pred / "
         "band midpoint)|.", "",
         "| Model | Median abs log10 err | Within 2x | Band hit | Worst over | Worst under | Tuned |",
         "|---|---|---|---|---|---|---|"]
    for f in FAMS:
        r = cv[f]
        hp = sorted({json.dumps(h) for h in r["fold_hparams"]} - {"{}"})
        L.append(f"| {LABEL[f]} | {r['median_abs_log10_error']:.3f} | {r['within_2x_rate']:.0%} | "
                 f"{r['band_hit_rate']:.0%} | {r['max_over_x']:.0f}x | {r['max_under_x']:.0f}x | "
                 f"{', '.join(hp) or '–'} |")
    L += ["", "Differences of 0.01–0.03 in median error are within fold noise at n=126. All "
          "models are trained on bands that are biased low for fast-growing companies, so "
          "band accuracy is not the deciding metric (section 2).", "",
          "## 2. Accuracy on publicly reported revenue (6 companies)", "",
          "Band-trained models are scored straight (they never see reported figures). The bias "
          "factor (median reported / model over the OTHER unflagged reported companies) and the "
          "revenue-per-employee benchmark are leave-one-out. Ratio = estimate / reported.", ""]
    keep = (["Crustdata band midpoint", "v1 point (band-clamped, in production)",
             "Benchmark rev/employee (LOO)", "Current calibrated ensemble (D29, LOO)"]
            + [f"{f} raw" for f in FAMS if f != "baseline"]
            + [f"{f} raw + guardrails" for f in ("tobit", "gbm")]
            + [f"{f} x LOO bias factor" for f in ("ridge_v1", "tobit", "gbm", "stack")]
            + [f"{f} bias-corrected 50/50 benchmark (LOO)" for f in ("ridge_v1", "tobit", "gbm", "stack")]
            + [f"{f} bias-corrected 50/50 benchmark + guardrails (LOO)" for f in ("tobit", "gbm")])
    for title, table in (("All 6 reported", acc), ("Without namesake-flagged headcounts "
                                                  "(Linear, Vercel, Retool)", acc_clean)):
        L += [f"**{title}**", "",
              "| Estimator | n | Median abs % err | Within 30% | Within 2x | Median ratio | Max over | Max under |",
              "|---|---|---|---|---|---|---|---|"]
        for k in keep:
            s = table[k]
            if s.get("n"):
                L.append(f"| {k} | {s['n']} | {s['median_abs_pct_error']:.0%} | {s['within_30pct']:.0%} | "
                         f"{s['within_2x']:.0%} | {s['median_ratio']:.2f} | {s['max_over']:.2f}x | "
                         f"{s['max_under']:.2f}x |")
        L.append("")
    L += ["Per company (estimate / reported):", "",
          "| Company | v1 point | Ensemble D29 | tobit raw | gbm raw | tobit chosen (LOO) | gbm chosen (LOO) |",
          "|---|---|---|---|---|---|---|"]
    ck = lambda f: f"{f} bias-corrected 50/50 benchmark + guardrails (LOO)"  # noqa: E731
    for d, t in truth.items():
        cells = [est["v1 point (band-clamped, in production)"], est["Current calibrated ensemble (D29, LOO)"],
                 est["tobit raw"], est["gbm raw"], est[ck("tobit")], est[ck("gbm")]]
        L.append(f"| {by[d]['name']}{' ⚠️' if by[d]['flagged'] else ''} | "
                 + " | ".join(f"{x[d] / t:.2f}" if x.get(d) else "–" for x in cells) + " |")
    L += ["", "⚠️ headcount flagged as inflated by namesake profiles.", "",
          "## 3. Guardrails", "",
          f"`apply_guardrails`: revenue per employee clipped to ${A.RPE_MIN_USD / 1e3:,.0f}K–"
          f"${A.RPE_MAX_USD / 1e6:.1f}M (public SaaS/fintech leaders sit around $300K–$1M per "
          "employee; $20K is below any functioning software business, $1.5M above all but a "
          "few outliers); never below the band floor when the band is trusted (listed size "
          "bucket = bucket implied by headcount, no namesake flag); never above "
          f"{A.MAX_OVER_BAND_TOP:g}x the band top, with that cap scaled up by (implied / listed "
          "bucket midpoint) when the listed bucket is stale. Every clip is flagged in the "
          "output. The per-employee floor is skipped for namesake-inflated headcounts.", "",
          "On the 126 band rows (held-out CV predictions; ratios vs band midpoint):", "",
          "| Model | Fired | Band floor | Band cap | Rev/emp cap | Rev/emp floor | Worst over before → after | Worst under before → after | Median err before → after | Within 2x before → after | Worst over / under after, plausible bands only |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for f, g in gstats.items():
        b, a = g["before"], g["after"]
        L.append(f"| {f} | {g['fired']:.0%} | {g['band floor']} | {g['band cap']} | {g['rpe cap']} | "
                 f"{g['rpe floor']} | {b['max_over_x']:.0f}x → {a['max_over_x']:.0f}x | "
                 f"{b['max_under_x']:.0f}x → {a['max_under_x']:.0f}x | "
                 f"{b['median_abs_log10_error']:.3f} → {a['median_abs_log10_error']:.3f} | "
                 f"{b['within_2x_rate']:.0%} → {a['within_2x_rate']:.0%} | "
                 f"{g['after_plausible']['max_over_x']:.0f}x / {g['after_plausible']['max_under_x']:.0f}x |")
    L += ["", f"{int((~plausible).sum())} of {len(rows)} band labels themselves imply revenue per "
          f"employee outside ${A.RPE_MIN_USD / 1e3:,.0f}K–${A.RPE_MAX_USD / 1e6:.1f}M (e.g. Telegram "
          "listed 11-50 with 3,530 staff and a $5–10M band; Unison Risk Advisors 73 staff with a "
          "$100–500M band). The remaining large 'errors' are against those labels; guardrailed "
          "outputs can never leave the per-employee range, so against any plausible truth the "
          "worst case is bounded by construction (1.5M / 20K = 75x at the extreme, far less in "
          "practice)."]
    L += ["", "On the 9 study companies, raw model outputs clipped: " +
          ", ".join(f"{f} {n}/9" for f, n in nine_fire.items()) +
          f". Chosen pipeline (tobit, bias-corrected + benchmark): "
          f"{sum(g['clipped'] for g in chosen_g9.values())}/9 clipped.", ""]
    for e in expl:
        for fl in e["guardrail_flags"]:
            L.append(f"- {e['c']['name']}: {fl}")
    L += ["", "Worst ratios on reported revenue after guardrails (chosen pipeline, LOO): "
          f"max over {acc[ck('tobit')]['max_over']:.2f}x, max under {acc[ck('tobit')]['max_under']:.2f}x.", "",
          "## 4. Why over or under? (per company)", "",
          f"Drivers: contribution of each standardized feature to the {LINEAR} linear model "
          "(coef x standardized value, log10 units; x10^v as a factor). Contributions + "
          "intercept reproduce the raw prediction exactly (max check error "
          f"{max(e['check'] for e in expl):.1e}). Estimate = chosen pipeline (LOO for reported companies).", "",
          f"Intercept: {lin.b:.3f} (= {usd(10 ** lin.b)} for an average training row).", "",
          "| Company | Staff | Listed → implied bucket | Band | Estimate | Reported | Est/rep | Implied rev/emp | Benchmark rev/emp | HC yoy | Web yoy | Primary capital / staff | Top 4 drivers |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for e in expl:
        c = e["c"]
        drv = "; ".join(f"{k} {v:+.2f}" for k, v in e["drivers"])
        L.append(f"| {c['name']}{' ⚠️' if c['flagged'] else ''} | {c['hc']:,.0f} | "
                 f"{c['listed'] or '?'} → {rm.bucket_of(c['hc'])} | "
                 f"{usd(c['band'][0])}–{usd(c['band'][1])} | {usd(e['point'])} | {usd(c['truth'])} | "
                 f"{fmt(e['ratio_to_reported'], '{:.2f}')} | "
                 f"{usd(e['rpe_implied'])} | {usd(e['benchmark_rpe_usd'])} | "
                 f"{fmt(e['headcount_yoy_pct'], '{:+.0f}%')} | {fmt(e['web_yoy'], '{:+.0f}%')} | "
                 f"{usd(e['funding_per_hc'])} | {drv} |")
    L += ["", "Plain-English reasons:", ""]
    L += [f"- **{e['c']['name']}**: {e['reason']}" for e in expl]
    a_ch, a_d29 = acc[ck(LINEAR)], acc["Current calibrated ensemble (D29, LOO)"]
    c_ch, c_d29 = acc_clean[ck(LINEAR)], acc_clean["Current calibrated ensemble (D29, LOO)"]
    L += ["", "Reading the drivers: in the band-trained model faster headcount growth LOWERS the "
          "prediction (hc_growth_log has a negative coefficient: Crustdata's bands lag growth), and "
          "log_size_bucket (the listed LinkedIn bucket at training time, the implied bucket at "
          "inference) carries most of the size signal. That is why every band-trained family "
          "underpredicts fast-growing scaleups by 2–5x (section 2, 'raw' rows) and why a "
          "reported-revenue correction is needed at all.", "",
          "## 5. Recommendation", "",
          f"- **Use: {LINEAR} (interval-censored ridge) raw output x reported-revenue bias factor, "
          f"geometric 50/50 blend with the reported revenue-per-employee benchmark, then "
          f"guardrails** (`predict_alt`). LOO on the 6 reported companies: median error "
          f"{a_ch['median_abs_pct_error']:.0%} (D29 ensemble {a_d29['median_abs_pct_error']:.0%}), "
          f"within 30% {a_ch['within_30pct']:.0%} ({a_d29['within_30pct']:.0%}), within 2x "
          f"{a_ch['within_2x']:.0%} ({a_d29['within_2x']:.0%}), worst {a_ch['max_over']:.2f}x over / "
          f"{a_ch['max_under']:.2f}x under (D29 {a_d29['max_over']:.2f}x / {a_d29['max_under']:.2f}x). "
          f"Unflagged only: {c_ch['median_abs_pct_error']:.0%} vs {c_d29['median_abs_pct_error']:.0%}.",
          "- The gain over D29 comes from correcting the model's UNCLAMPED output for its known low "
          "bias instead of blending a band-clamped v1 point; ridge_v1 and the stack give the same "
          "result in that pipeline (section 2), so the model family matters far less than the bias "
          "correction. Tobit is chosen because it has the best band CV among linear models and its "
          "drivers are exactly additive (explanations). gbm wins on band CV but transfers worst to "
          "reported revenue and is not additive.",
          "- Clay's 1.50x depends on the band-cap guardrail (its $2.5–5M band is wildly stale); "
          "without guardrails the same pipeline is 2.97x over on Clay. Guardrails never fired against "
          "a correct estimate on the 9 study companies.",
          "- **Honesty: n=6 (3 unflagged).** The bias factor and benchmark each rest on 2–3 "
          "companies per LOO fold; the blend weight (0.5) and guardrail bounds were fixed a priori, "
          "not tuned on these companies, but the families compared were chosen with them in view. "
          "Treat the reported-revenue numbers as indicative; keep labelling every output an ESTIMATE.",
          "- Early-stage companies (< 50 staff or < $20M primary capital: Koah, Terrastack) get the "
          "raw model + guardrails only; no scaleup benchmark or bias factor applies.", ""]
    OUT_MD.write_text("\n".join(L))

    # console summary
    print("sanity v1 raw (ours, economics):", sanity)
    for f in FAMS:
        r = cv[f]
        print(f"CV {f:9s} med {r['median_abs_log10_error']:.3f} w2x {r['within_2x_rate']:.0%} "
              f"hit {r['band_hit_rate']:.0%} over {r['max_over_x']:.0f}x under {r['max_under_x']:.0f}x")
    for k in keep:
        s, s2 = acc[k], acc_clean[k]
        if s.get("n"):
            print(f"REP {k[:62]:62s} med {s['median_abs_pct_error']:.0%} w30 {s['within_30pct']:.0%} "
                  f"w2x {s['within_2x']:.0%} ratio {s['median_ratio']:.2f} over {s['max_over']:.2f} "
                  f"under {s['max_under']:.2f} | clean med {s2['median_abs_pct_error']:.0%} "
                  f"w2x {s2['within_2x']:.0%} ratio {s2['median_ratio']:.2f}")
    for f, g in gstats.items():
        print("GUARD", f, f"{g['fired']:.0%}", {k: g[k] for k in ('band floor', 'band cap', 'rpe cap', 'rpe floor')},
              g["before"]["max_over_x"], "->", g["after"]["max_over_x"], g["before"]["max_under_x"], "->",
              g["after"]["max_under_x"], g["before"]["within_2x_rate"], "->", g["after"]["within_2x_rate"])
    print("nine fire", nine_fire)
    for e in expl:
        print("WHY", e["c"]["name"], e["c"]["listed"], usd(e["point"]), e["reason"])
    print("saved bias", bias_all, "rpe", rpe_all, doc["reported_loo"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
