"""Revenue model v3: fetch inputs, train, evaluate (docs/revenue_model_3_results.md).

    .venv/bin/python scripts/train_revenue_model_3.py fetch   # CACHED (live on a miss)
    .venv/bin/python scripts/train_revenue_model_3.py train   # offline

fetch: a stratified 80 of training_set.json (16 per size stratum, ordered by
sha256('rev3:<id>')) get one Company Enrich (headcount, taxonomy, hiring, funding,
locations; 2 credits each, batched 10 ids per request), free mention counts (Social Post
Search, limit 0) and two market-width counts (Company Search limit 1, ~0.13 each). The 9
study companies reuse their fixture Enrich record (0 credits) and get the same counts;
the count records are copied into fixtures/<name>/crustdata/ (never overwriting).
Stripped inputs go to proofroom/data/model3_features.json.

train: ridge v3 = v1 features + new features, v1's 5-fold CV protocol (seed 7) with v1's
own method and lambda (no tuning on the CV folds), ablations, payroll-implied revenue,
and the reported-revenue comparison (leave-one-out) on the 6 reported companies.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import shutil
import sys
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from proofroom import economics as eco_mod  # noqa: E402
from proofroom import revenue_model as rm  # noqa: E402
from proofroom import revenue_model_3 as m3  # noqa: E402
from proofroom.crustdata import CACHED, FIXTURE, LIVE, Crustdata, _slug, cache_key, sum_credits  # noqa: E402,E501
from proofroom.graph import company_record  # noqa: E402

PER_STRATUM = 16
ENRICH_FIELDS = ["headcount", "taxonomy", "hiring", "funding", "locations"]
BATCH = 10
AS_OF = date(2026, 10, 31)


def training_rows() -> list[dict]:
    return list(rm.iter_rows())


def select(rows: list[dict]) -> list[dict]:
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(r["stratum"], []).append(r)
    out = []
    for s in sorted(by):
        rs = sorted(by[s], key=lambda r: hashlib.sha256(
            f"rev3:{r['crustdata_company_id']}".encode()).hexdigest())
        out += rs[:PER_STRATUM]
    return out


def _records(resp) -> dict[int, dict]:
    out = {}
    for item in resp if isinstance(resp, list) else []:
        for m in (item.get("matches") or [])[:1]:
            cd = m.get("company_data") or {}
            if cd.get("crustdata_company_id"):
                out[int(cd["crustdata_company_id"])] = cd
    return out


async def fetch() -> None:
    # Social Post Search and Company Search have no entry in crustdata.RPM (default 10/min);
    # this batch job raises them to 60/min and relies on the client's 429 handling.
    from proofroom import crustdata as cd
    for ep in (m3.POSTS, m3.SEARCH):
        cd._LIMITERS[ep] = cd.RateLimiter(60)
    rows = select(training_rows())
    doc = {"as_of": AS_OF.isoformat(), "selection": f"{PER_STRATUM} per size stratum of "
           "training_set.json ordered by sha256('rev3:<id>')",
           "sources": {
               "regions/roles/hiring/taxonomy/funding": "POST /company/enrich fields "
               + ", ".join(ENRICH_FIELDS) + " (2 credits per company)",
               "mentions": "POST /social_post/search, mentions.company_id in [id] AND "
               "actor.actor_type = person, limit 0 (total_count only; 0 credits): all-time, "
               "date_posted >= as_of-12m, and text [.] any of " + ", ".join(m3.PARTNER_PHRASES),
               "market_width": "POST /company/search taxonomy.categories = first specific "
               "category (signals.candidate_categories), limit 1 (~0.13 credits): pool and "
               "funding.last_fundraise_date >= as_of-24m (month-anchored)",
               "salary": "proofroom/data/salary_benchmarks.json (BLS OEWS May 2025, ONS ASHE "
               "2025, Payscale; employer_tiers scaleup = BLS NAICS 513200 / all, startup = "
               "Carta H1 2025, https://carta.com/data/startup-compensation-h1-2025/)",
               "web_lookups": "none (no levels.fyi/Glassdoor figures were needed: the file's "
               "employer tiers supply the startup/scaleup pay adjustment)"},
           "training": {}, "study": {}}
    async with Crustdata(LIVE, use_cache=False) as c:
        before = (await c.credits())["account"]["credits"]
    doc["account_credits_before"] = before
    async with Crustdata(CACHED) as client:
        recs: dict[int, dict] = {}
        ids = [int(r["crustdata_company_id"]) for r in rows]
        for i in range(0, len(ids), BATCH):
            body = {"crustdata_company_ids": ids[i:i + BATCH], "fields": ENRICH_FIELDS}
            recs.update(_records(await client.request("POST", "/company/enrich", body)))
        sem = asyncio.Semaphore(4)

        async def one(r: dict) -> None:
            cid = int(r["crustdata_company_id"])
            rec = recs.get(cid) or {}
            inp = m3.inputs_from_record(rec, headcount=r.get("headcount"),
                                        description=r.get("description", ""), hq=r.get("hq", ""),
                                        total_funding_usd=r.get("total_funding_usd"))
            if not inp["investors"]:
                inp["investors"] = []
            inp["category"] = m3.first_category(inp["categories"])
            async with sem:
                inp["counts"] = await m3.fetch_counts(client, cid, inp["category"], AS_OF)
            inp["enriched"] = bool(rec)
            doc["training"][str(cid)] = inp
        await asyncio.gather(*(one(r) for r in rows))
        train_spent, unk = sum_credits(client.attempts)
    doc["credits_training"] = {"spent": train_spent, "unknown_attempts": unk}
    # study companies
    study_spent = 0.0
    for name, cid, domain in eco_mod.COMPANIES:
        sig, eco = await eco_mod.replay(name, cid, domain)
        async with Crustdata(FIXTURE, fixture=name) as fx:
            rec = eco_mod._enrich_record(fx, cid) or {}
            as_of = eco_mod._today(fx)
        tf = sig.metrics.get("total_funding_usd")
        inp = m3.inputs_from_record(rec, headcount=sig.headcount_total,
                                    description=sig.description, hq=sig.hq,
                                    total_funding_usd=tf.value if tf else None)
        inp["category"] = m3.first_category(inp["categories"])
        async with Crustdata(CACHED) as client:
            inp["counts"] = await m3.fetch_counts(client, cid, inp["category"], as_of)
            s, _ = sum_credits(client.attempts)
            study_spent += s
            fdir = ROOT / "fixtures" / name / "crustdata"
            for key, ep, body in ([(k, m3.POSTS, b) for k, b in
                                   m3.mention_bodies(cid, as_of).items()]
                                  + [(k, m3.SEARCH, b) for k, b in
                                     m3.market_bodies(inp["category"], as_of).items()]):
                fname = f"{_slug(ep)}-{cache_key(ep, body)}.json"
                src, dst = client.cache_dir / fname, fdir / fname
                if src.exists() and not dst.exists():
                    shutil.copyfile(src, dst)
        doc["study"][name] = inp
    doc["credits_study"] = study_spent
    async with Crustdata(LIVE, use_cache=False) as c:
        doc["account_credits_after"] = (await c.credits())["account"]["credits"]
    m3.FEATURES_PATH.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    print(f"training rows {len(doc['training'])} (enriched "
          f"{sum(1 for v in doc['training'].values() if v['enriched'])}); spent training "
          f"{train_spent}, study {study_spent}; account {before} -> "
          f"{doc['account_credits_after']}")


# ---- train / evaluate (offline) ---------------------------------------------------------

def _cv_preds(X, X_eval, y_mid, y_lo, y_hi, lam, method):
    pred = np.zeros_like(y_mid)
    for test in rm._folds(len(y_mid)):
        train = np.setdiff1d(np.arange(len(y_mid)), test)
        params = rm.fit(X[train], y_mid[train], y_lo[train], y_hi[train], lam, method)
        pred[test] = rm._predict(params, X_eval[test])
    return pred


def _ratio_cv(y_mid, log_base, groups):
    """Held-out log10(k x base), k = median(10^y / base) of the training fold per group."""
    pred = np.zeros_like(y_mid)
    for test in rm._folds(len(y_mid)):
        train = np.setdiff1d(np.arange(len(y_mid)), test)
        for i in test:
            same = [j for j in train if groups[j] == groups[i]] or list(train)
            pred[i] = log_base[i] + float(np.median(y_mid[same] - log_base[same]))
    return pred


def _sign_test(err_a, err_b):
    """Paired two-sided sign test on |err_a| < |err_b| (ties dropped)."""
    wins = int(np.sum(err_a < err_b - 1e-12))
    losses = int(np.sum(err_a > err_b + 1e-12))
    n = wins + losses
    k = min(wins, losses)
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n) if n else 1.0
    return wins, losses, round(p, 4)


def _pct(est, truth):
    return (est - truth) / truth


def _summ(rows, key):
    errs = [abs(_pct(r[key], r["truth"])) for r in rows if r.get(key)]
    ratios = [r[key] / r["truth"] for r in rows if r.get(key)]
    if not errs:
        return None
    worst_over = max(rows, key=lambda r: (r[key] or 0) / r["truth"])
    worst_under = min(rows, key=lambda r: (r[key] or 1e30) / r["truth"])
    return {"n": len(errs), "median_abs_pct_err": round(float(np.median(errs)), 3),
            "within_30pct": round(float(np.mean([e <= 0.3 for e in errs])), 3),
            "within_2x": round(float(np.mean([0.5 <= x <= 2 for x in ratios])), 3),
            "median_ratio": round(float(np.median(ratios)), 3),
            "worst_over": f"{worst_over['name']} {worst_over[key] / worst_over['truth']:.2f}x",
            "worst_under": f"{worst_under['name']} {worst_under[key] / worst_under['truth']:.2f}x"}


def train() -> None:
    feats_doc = json.loads(m3.FEATURES_PATH.read_text(encoding="utf-8"))
    v1doc = json.loads(rm.MODEL_PATH.read_text(encoding="utf-8"))
    lam, method = float(v1doc["lambda"]), v1doc["method"]
    rows = [r for r in training_rows() if str(r["crustdata_company_id"]) in feats_doc["training"]]
    use, f_tr, f_ev, f_new, inps = [], [], [], [], []
    for r in rows:
        inp = feats_doc["training"][str(r["crustdata_company_id"])]
        a, b = rm.features_from_row(r, AS_OF), rm.features_from_row(r, AS_OF, listed_bucket=False)
        if a is None or not inp.get("enriched"):
            continue
        use.append(r); f_tr.append(a); f_ev.append(b); f_new.append(m3.new_features(inp))
        inps.append(inp)
    y_mid, y_lo, y_hi = rm.targets(use)
    hc = np.array([r["headcount"] for r in use], float)
    n = len(use)

    def design(names):
        Xt = np.array([[{**a, **c}[k] for k in names] for a, c in zip(f_tr, f_new)], float)
        Xe = np.array([[{**a, **c}[k] for k in names] for a, c in zip(f_ev, f_new)], float)
        return Xt, Xe

    variants = {"v1 (16 features, refit on this subset)": list(rm.FEATURES)}
    for g, names in m3.FEATURE_GROUPS.items():
        variants[f"v1 + {g}"] = list(rm.FEATURES) + list(names)
    variants["v3 = v1 + all new"] = list(rm.FEATURES) + list(m3.NEW_FEATURES)
    cv, preds = {}, {}
    for label, names in variants.items():
        Xt, Xe = design(names)
        p = _cv_preds(Xt, Xe, y_mid, y_lo, y_hi, lam, method)
        preds[label] = p
        cv[label] = rm._metrics(p, y_mid, y_lo, y_hi)
    base_v1 = np.abs(preds["v1 (16 features, refit on this subset)"] - y_mid)
    for label in variants:
        cv[label]["vs_v1_sign_test"] = _sign_test(np.abs(preds[label] - y_mid), base_v1)
    # baselines and payroll-implied on band data
    clean_hc = np.array([max(10 ** f["log_clean_headcount"], 1) for f in f_new])
    pay = np.array([10 ** f["log_loaded_payroll"] for f in f_new])
    stages = [m3.stage_of(i.get("total_funding_usd")) for i in inps]
    one = ["all"] * n
    extra = {
        "baseline: raw headcount x median rev/employee": _ratio_cv(y_mid, np.log10(hc), one),
        "baseline: CLEAN headcount x median rev/clean employee": _ratio_cv(
            y_mid, np.log10(clean_hc), one),
        "payroll-implied: k x loaded payroll (k by stage)": _ratio_cv(y_mid, np.log10(pay), stages),
        "payroll-implied: k x loaded payroll (single k)": _ratio_cv(y_mid, np.log10(pay), one),
    }
    for label, p in extra.items():
        cv[label] = rm._metrics(p, y_mid, y_lo, y_hi)
        cv[label]["vs_v1_sign_test"] = _sign_test(np.abs(p - y_mid), base_v1)
    k_band = {s: float(10 ** np.median([y_mid[i] - np.log10(pay[i]) for i in range(n)
                                         if stages[i] == s])) for s in ("early", "late")
              if any(st == s for st in stages)}
    # final fit
    names = list(rm.FEATURES) + list(m3.NEW_FEATURES)
    Xt, Xe = design(names)
    w, b, mu, sd = rm.fit(Xt, y_mid, y_lo, y_hi, lam, method)
    clean_stats = {"rows": n, "rows_cleaned": int(sum(1 for f in f_new if f["clean_share"] < 0.98)),
                   "median_clean_share": round(float(np.median([f["clean_share"] for f in f_new])), 3)}
    doc = {"version": m3.MODEL_VERSION, "trained_on": AS_OF.isoformat(), "n_rows": n,
           "target": v1doc["target"], "method": method, "lambda": lam,
           "lambda_note": "v1's method and lambda reused unchanged (not re-tuned on these folds)",
           "features": names, "coef_standardized": [round(float(x), 6) for x in w],
           "intercept": round(b, 6), "feature_means": [round(float(x), 6) for x in mu],
           "feature_stds": [round(float(x), 6) for x in sd],
           "cv": {"folds": rm.CV_FOLDS, "seed": rm.CV_SEED, "results": cv,
                  "definition": "held-out rows scored with the headcount-implied size bucket "
                                "(as v1); error vs log10 band midpoint"},
           "clean_headcount_training": clean_stats,
           "payroll_k_band": {k: round(v, 4) for k, v in k_band.items()},
           "selection": feats_doc.get("selection")}
    m3.MODEL_PATH.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    reported = asyncio.run(evaluate_reported(feats_doc))
    doc.update(reported["save"])
    doc["reported_eval"] = reported["summary"]
    m3.MODEL_PATH.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    out = {"cv": cv, "k_band": k_band, "clean_stats": clean_stats, **reported}
    (ROOT / "proofroom" / "data" / "revenue_model_3.json").write_text(
        json.dumps(doc, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1, default=str))


async def evaluate_reported(feats_doc: dict) -> dict:
    gt = eco_mod.load_ground_truth()
    rows = []
    for name, cid, domain in eco_mod.COMPANIES:
        sig, eco = await eco_mod.replay(name, cid, domain)
        async with Crustdata(FIXTURE, fixture=name) as fx:
            extra = await m3.model3_features_for(fx, cid, sig, eco)
        p = m3.predict_v3(sig, eco, extra)
        truth = (gt.get(domain) or {}).get("best_estimate_usd")
        flagged = any("namesake" in x for x in eco.limitations)
        iq = m3.investor_quality(extra["inputs"]["investors"], extra["inputs"]["milestones"])
        rows.append({"name": name, "domain": domain, "truth": truth, "flagged": flagged,
                     "v1": eco.revenue.point_usd, "v3": p.get("v3_point_usd"),
                     "v3_raw": p.get("v3_raw_usd"), "raw_hc": p["raw_headcount"],
                     "clean_hc": p["clean_headcount"], "payroll": p["loaded_payroll_usd"],
                     "payroll_band_k": p["payroll_implied_band_k_usd"],
                     "band": sig.revenue_band_usd, "stage": p["stage"],
                     "n_top_tier": iq["n_top_tier"], "lead": iq["last_lead"],
                     "lead_tier": iq["last_lead_tier"],
                     "counts": extra["inputs"]["counts"], "category": extra["inputs"]["category"],
                     "new": p["new_features"],
                     "dropped_countries": m3.clean_headcount(
                         extra["inputs"]["regions"], extra["inputs"]["roles"],
                         extra["inputs"]["headcount"], extra["inputs"]["hq_iso"],
                         extra["inputs"]["description"],
                         set(extra["inputs"]["offices"]))["dropped_countries"],
                     "dropped_functions": m3.clean_headcount(
                         extra["inputs"]["regions"], extra["inputs"]["roles"],
                         extra["inputs"]["headcount"], extra["inputs"]["hq_iso"],
                         extra["inputs"]["description"],
                         set(extra["inputs"]["offices"]))["dropped_functions"]})
    rep = [r for r in rows if r["truth"]]
    tr = [r["truth"] for r in rep]
    pays = [r["payroll"] for r in rep]
    ks = m3.loo_k(tr, pays)
    cl = [r["clean_hc"] for r in rep]
    rpe = [m3.fit_k(tr[:i] + tr[i + 1:], cl[:i] + cl[i + 1:]) for i in range(len(rep))]
    for r, k, q in zip(rep, ks, rpe):
        r["payroll_loo"] = r["payroll"] * k
        r["k_loo"] = k
        r["clean_bench_loo"] = r["clean_hc"] * q
        r["rpe_clean_loo"] = q
        r["ensemble"] = float(np.exp(np.mean(np.log([r["v3"], r["payroll_loo"],
                                                       r["clean_bench_loo"]]))))
        r["ensemble_v1"] = float(np.exp(np.mean(np.log([r["v1"], r["payroll_loo"],
                                                          r["clean_bench_loo"]]))))
    keys = ("v1", "v3", "payroll_band_k", "payroll_loo", "clean_bench_loo", "ensemble",
            "ensemble_v1")
    summary = {"all": {k: _summ(rep, k) for k in keys},
               "unflagged": {k: _summ([r for r in rep if not r["flagged"]], k) for k in keys}}
    save = {"payroll_k_reported": round(m3.fit_k(tr, pays), 4),
            "revenue_per_clean_employee_reported": round(m3.fit_k(tr, cl), 0),
            "reported_companies": [r["domain"] for r in rep]}
    return {"rows": rows, "summary": summary, "save": save}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "train"
    if cmd == "fetch":
        asyncio.run(fetch())
    else:
        train()
