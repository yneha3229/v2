"""Revenue model 2 (rev-2): social-post features on top of rev-1. Separate from rev-1.

    .venv/bin/python scripts/train_revenue_model_2.py select   # print the subset (offline)
    .venv/bin/python scripts/train_revenue_model_2.py count    # free limit-0 post counts
    .venv/bin/python scripts/train_revenue_model_2.py pull     # CACHED: live only on a miss
    .venv/bin/python scripts/train_revenue_model_2.py fit      # offline
    .venv/bin/python scripts/train_revenue_model_2.py apply    # 9 study companies (CACHED,
                                                               # captures fixtures)
    .venv/bin/python scripts/train_revenue_model_2.py apply --offline   # FIXTURE replay

Subset (deterministic): from proofroom/data/training_set.json, rows with a usable rev-1
feature vector, grouped by their size stratum (employee_count_range); inside each stratum
rows are ordered by sha256("rev2:<crustdata_company_id>") and the first PER_STRATUM are
taken (5 strata x 16 = 80). The hash order is unrelated to size, funding or revenue.

Cost: Social Post Search bills 0.5 credits per post returned (<= 10 per company, so <= 5);
limit-0 counts and empty results are free. `pull` stops before the task budget is crossed.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from proofroom import config  # noqa: E402
from proofroom import revenue_model as rm  # noqa: E402
from proofroom import revenue_model_2 as rm2  # noqa: E402
from proofroom.crustdata import CACHED, FIXTURE, Crustdata, cache_key, sum_credits  # noqa: E402
from proofroom.errors import CrustError  # noqa: E402

PER_STRATUM = 16
BUDGET = 450.0          # task cap on Crustdata credits (all calls in this task)
SPENT_BEFORE = 3.5      # the koahlabs.com probe (7 posts x 0.5) made before `pull`
GT_PATH = rm.DATA_DIR / "revenue_ground_truth.json"

STUDY: tuple[tuple[str, str, int | None], ...] = (
    ("koah", "koahlabs.com", 3718859), ("linear", "linear.app", 633791),
    ("attio", "attio.com", 664000), ("clay", "clay.com", None),
    ("vercel", "vercel.com", None), ("retool", "retool.com", None),
    ("ramp", "ramp.com", None), ("mercury", "mercury.com", None),
    ("terrastack", "terrastack.in", 6421460))


def _h(cid: int) -> str:
    return hashlib.sha256(f"rev2:{cid}".encode()).hexdigest()


def select_rows() -> list[dict]:
    rows = list(rm.iter_rows())
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if rm.features_from_row(r, rm2.AS_OF) is not None:
            by[r.get("stratum") or r.get("employee_count_range") or ""].append(r)
    out = []
    for stratum in sorted(by, key=lambda s: rm._BUCKET_RANK.get(s, 99)):
        out += sorted(by[stratum], key=lambda r: _h(int(r["crustdata_company_id"])))[:PER_STRATUM]
    return out


async def count() -> None:
    sel = select_rows()
    proj = 0.0
    async with Crustdata(CACHED) as c:
        for r in sel:
            resp = await c.request("POST", rm2.POSTS_ENDPOINT,
                                   rm2.posts_body(r["crustdata_company_id"], 0))
            t = int((resp or {}).get("total_count") or 0)
            proj += 0.5 * min(t, rm2.POST_LIMIT)
        spent, _ = sum_credits(c.attempts)
    print(f"{len(sel)} companies; projected pull cost {proj:.1f} credits; this step {spent}")


async def pull() -> None:
    sel = select_rows()
    prev = {}
    if rm2.SOCIAL_TRAINING_PATH.exists():
        prev = json.loads(rm2.SOCIAL_TRAINING_PATH.read_text(encoding="utf-8"))
    companies, stopped = [], ""
    async with Crustdata(CACHED) as c:
        before = (await c.credits())["account"]["credits"]
        for r in sel:
            cid = int(r["crustdata_company_id"])
            spent, _ = sum_credits(c.attempts)
            if SPENT_BEFORE + spent + 5.0 > BUDGET - 50.0:   # keep ~50 for the study companies
                stopped = f"budget guard hit before id {cid}"
                break
            s = await rm2.social_features_for(c, cid, rm2.AS_OF)
            s.update(name=r["name"], stratum=r.get("stratum", ""))
            companies.append(s)
            print(f"{r['stratum']:>9} {cid:>8} {r['name'][:28]:<28} {s['mode']:<6} "
                  f"credits={s['credits_used']:<5} posts={s['n_posts']:<2} "
                  f"total={s['total_count']} {s['error']}")
        spent, unknown = sum_credits(c.attempts)
        after = (await c.credits())["account"]["credits"]
    doc = {"as_of": rm2.AS_OF.isoformat(),
           "source": f"POST {rm2.POSTS_ENDPOINT} (actor.crustdata_entity_id = company id, "
                     f"actor_type company, newest first, limit {rm2.POST_LIMIT})",
           "why_not_enrich": "Company Enrich field group social_posts returned 403 "
                             "permission_error (field not enabled on the event key).",
           "selection": f"{PER_STRATUM} per size stratum of training_set.json, ordered by "
                        "sha256('rev2:<id>')",
           "features": list(rm2.SOCIAL_FEATURES + rm2.INFO_FEATURES),
           "snippets_note": "first 200 characters of up to 3 newest posts, for audit only",
           "credits_used_live_this_pull": spent, "credits_unknown_attempts": unknown,
           "account_credits_before_pull": before, "account_credits_after_pull": after,
           "account_credits_note": "account balance is shared with other concurrent work; "
                                   "credits_used_live_this_pull is this script's own spend "
                                   "(sum of x-credits-used)",
           "stopped": stopped, "companies": companies}
    if prev.get("account_credits_before_pull") and not spent:
        doc["account_credits_before_pull"] = prev["account_credits_before_pull"]
        doc["credits_used_live_this_pull"] = prev.get("credits_used_live_this_pull", 0)
    rm2.SOCIAL_TRAINING_PATH.write_text(json.dumps(doc, indent=1, ensure_ascii=False),
                                        encoding="utf-8")
    print(f"{len(companies)} companies -> {rm2.SOCIAL_TRAINING_PATH}; live credits {spent}; "
          f"account {before} -> {after}")


def _social_map() -> dict[int, dict]:
    doc = json.loads(rm2.SOCIAL_TRAINING_PATH.read_text(encoding="utf-8"))
    return {int(s["company_id"]): s for s in doc["companies"] if not s.get("error")}


def fit() -> dict:
    social = _social_map()
    mat = rm2.training_matrix(select_rows(), social)
    v1 = tuple(rm.FEATURES)
    volume = ("has_posts", "log_total_posts")
    activity = ("posts_per_30d", "days_since_last_post", "log_median_engagement",
                "log_mean_engagement", "video_share", "original_share")
    sets = {"v1": v1, "v2": rm2.FEATURES, "v1+volume": v1 + volume,
            "v1+volume+activity": v1 + volume + activity, "v1+topics": v1 + ("has_posts",)
            + rm2.TOPICS}
    ev = rm2.evaluate(mat, sets)
    y = mat["y_mid"]
    pair = rm2.paired(ev["v1"]["pred"], ev["v2"]["pred"], y)
    pair_base = rm2.paired(ev["baseline"]["pred"], ev["v2"]["pred"], y)
    summary = {k: {"method": v["method"], "lambda": v["lambda"], **v["metrics"]}
               for k, v in ev.items()}
    n_posts = sum(1 for f in mat["f_train"] if f["has_posts"])
    extra = {
        "training_set": {"rows_path": "proofroom/data/training_set.json",
                         "social_path": "proofroom/data/social_posts_training.json",
                         "n_selected": len(select_rows()), "n_used": len(mat["rows"]),
                         "n_with_posts": n_posts, "selection": __doc__.split("Subset")[1]
                         .split("Cost:")[0].strip()},
        "cv_same_subset": summary,
        "cv_definition": "5-fold CV (rev-1 folds, seed 7) on the same rows for every model; "
                         "each model's method and lambda tuned by that CV (rev-1 rule, mildly "
                         "optimistic); held-out rows scored with the headcount-implied size "
                         "bucket, as at inference",
        "paired_v2_vs_v1": pair, "paired_v2_vs_baseline": pair_base,
    }
    doc = rm2.fit_document(mat, ev["v2"], {"v1_same_subset": ev["v1"]["metrics"],
                                           "baseline": ev["baseline"]["metrics"]}, extra)
    soc = [(f, w) for f, w in zip(doc["features"], doc["coef_standardized"])
           if f in rm2.SOCIAL_FEATURES]
    doc["top_social_coefficients"] = [{"feature": f, "coef_standardized": w}
                                      for f, w in sorted(soc, key=lambda x: -abs(x[1]))]
    doc["social_feature_means_with_posts"] = {
        k: round(float(np.mean([f[k] for f in mat["f_train"] if f["has_posts"]] or [0])), 4)
        for k in rm2.SOCIAL_FEATURES}
    doc["notes"] = [
        "ESTIMATE model; the target is Crustdata's third-party revenue band, not reported "
        "revenue.",
        "Social features come from at most the 10 most recent company posts (Social Post "
        "Search); Company Enrich social_posts was 403 on this key.",
        "Topic shares are keyword rules over post text; posts are what a company chooses "
        "to publish.",
    ]
    if rm2.MODEL_PATH.exists():
        old = json.loads(rm2.MODEL_PATH.read_text(encoding="utf-8"))
        if "study_companies" in old:
            doc["study_companies"] = old["study_companies"]
    rm2.MODEL_PATH.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"n={len(mat['rows'])} (with posts {n_posts})")
    for k, v in summary.items():
        print(f"  {k:<20} " + " ".join(f"{m}={x}" for m, x in v.items()))
    print("  paired v2 vs v1:", pair)
    print("  paired v2 vs baseline:", pair_base)
    print("  social coefficients:")
    for t in doc["top_social_coefficients"]:
        print(f"    {t['feature']:<24} {t['coef_standardized']:+.4f}")
    return doc


# ---- 9 study companies ----------------------------------------------------------------

def _copy_fixture(src: Path, name: str, strip: bool) -> str:
    out = config.FIXTURES_DIR / name / "crustdata" / src.name
    if out.exists():
        return "kept"
    rec = json.loads(src.read_text(encoding="utf-8"))
    if strip:
        from proofroom.signals import strip_signals
        rec = {"endpoint": rec.get("endpoint"), "request": rec.get("request"),
               "status": rec.get("status", 200), "credits_used": rec.get("credits_used"),
               "body": strip_signals(rec.get("body"))}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
    return "written"


def _record_path(client: Crustdata, endpoint: str, body: dict) -> Path:
    key = cache_key(endpoint, body)
    folder = client.fixture_dir if client.mode == FIXTURE else client.cache_dir
    return folder / f"{endpoint.strip('/').replace('/', '_')}-{key}.json"


async def apply(offline: bool = False) -> None:
    from proofroom.graph import company_record
    from proofroom.signals import ENRICH_FIELDS, fetch_signals
    model = rm2.RevenueModel2.load()
    v1_model = rm.RevenueModel.load()
    truth = {}
    try:
        from proofroom.economics import load_ground_truth
        truth = load_ground_truth(GT_PATH)
    except Exception:  # noqa: BLE001 - another agent owns economics.py
        truth = {}
    results, spent_total = [], 0.0
    for name, domain, cid in STUDY:
        mode = FIXTURE if offline else CACHED
        async with Crustdata(mode, fixture=name if offline else "") as c:
            row = {"name": name, "domain": domain, "company_id": cid, "mode": mode}
            try:
                if cid is None:
                    resp = await c.identify_domain(domain)
                    cid = _identify_id(resp)
                    row["company_id"] = cid
                sig = await fetch_signals(c, cid, domain, today=rm2.AS_OF, search=False,
                                          jobs=False, logo=False)
                body = {"crustdata_company_ids": [int(cid)], "fields": list(ENRICH_FIELDS)}
                rp = _record_path(c, "/company/enrich", body)
                rec = company_record(json.loads(rp.read_text(encoding="utf-8"))["body"]) \
                    if rp.exists() else {}
                hc = rec.get("headcount") or {}
                largest = str(hc.get("largest_headcount_country") or "")
                listed = str((rec.get("basic_info") or {}).get("employee_count_range") or "")
                v1 = rm.estimate_revenue(sig, model=v1_model, as_of=rm2.AS_OF,
                                         largest_country=largest, listed_bucket=listed)
                soc = await rm2.social_features_for(c, cid, rm2.AS_OF)
                v2 = rm2.estimate_revenue_v2(sig, soc["features"], model=model,
                                             as_of=rm2.AS_OF, largest_country=largest,
                                             listed_bucket=listed)
                row.update(headcount=sig.headcount_total, listed_bucket=listed,
                           band=sig.revenue_band_usd, v1_point=v1.point_usd,
                           v1_raw=v1.model_raw_usd, v2_point=v2["point_usd"],
                           v2_raw=v2["model_raw_usd"], v2_low=v2["low_usd"],
                           v2_high=v2["high_usd"], n_posts=soc["n_posts"],
                           total_posts=soc["total_count"], social_error=soc["error"],
                           social=soc["features"])
            except (CrustError, OSError, ValueError, KeyError) as e:
                row["error"] = f"{type(e).__name__}: {e}"[:200]
            spent, _ = sum_credits(c.attempts)
            spent_total += spent
            if not offline:
                files = []
                for a in c.attempts:
                    p = c.cache_dir / f"{a.endpoint.strip('/').replace('/', '_')}-{a.cache_key}.json"
                    if not a.error and p.is_file() and p not in files:
                        files.append(p)
                row["fixtures"] = {p.name: _copy_fixture(p, name, strip=p.name.startswith(
                    "company_enrich")) for p in files}
        gt = truth.get(domain, {})
        rev = gt.get("best_estimate_usd") or gt.get("reported_arr_usd")
        row["reported_usd"] = rev
        for k in ("v1_point", "v2_point"):
            row[k.replace("point", "pct_err")] = (round((row[k] - rev) / rev * 100, 1)
                                                  if rev and row.get(k) else None)
        results.append(row)
        print(f"{name:<11} id={row.get('company_id')} hc={row.get('headcount')} "
              f"band={row.get('band')} v1={row.get('v1_point')} v2={row.get('v2_point')} "
              f"posts={row.get('n_posts')}/{row.get('total_posts')} rep={rev} "
              f"{row.get('error', '')}")
    print(f"live credits this step: {spent_total}")
    if not offline and rm2.MODEL_PATH.exists():
        doc = json.loads(rm2.MODEL_PATH.read_text(encoding="utf-8"))
        doc["study_companies"] = [{k: v for k, v in r.items() if k != "fixtures"}
                                  for r in results]
        doc["study_credits_live"] = spent_total
        rm2.MODEL_PATH.write_text(json.dumps(doc, indent=1), encoding="utf-8")


def _identify_id(resp) -> int:
    items = resp if isinstance(resp, list) else (resp or {}).get("results") or []
    for it in items:
        for m in (it.get("matches") or []) if isinstance(it, dict) else []:
            cd = m.get("company_data") or {}
            cid = cd.get("crustdata_company_id") or m.get("crustdata_company_id")
            if cid:
                return int(cid)
    raise ValueError("identify returned no company id")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "select":
        for r in select_rows():
            print(r["stratum"], r["crustdata_company_id"], r["name"])
    elif cmd == "count":
        asyncio.run(count())
    elif cmd == "pull":
        asyncio.run(pull())
    elif cmd == "fit":
        fit()
    elif cmd == "apply":
        asyncio.run(apply(offline="--offline" in sys.argv))
    else:
        print(__doc__)
