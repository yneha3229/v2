"""Pull the revenue-model training set from Crustdata Company Search and fit the model.

    .venv/bin/python scripts/train_revenue_model.py pull    # CACHED: live only on a miss
    .venv/bin/python scripts/train_revenue_model.py fit     # offline, from training_set.json

Cost (docs.crustdata.com/general/pricing, confirmed by x-credits-used): 0.03 base per
result + 0.2 headcount response + 0.2 funding response = 0.43 per row. basic_info,
revenue and locations are not premium groups; filters used here (company_type, markets,
industries, year_founded, employee_count_range, revenue bound, id exclusion) are free, and
sorting is not billed. 5 strata x 26 rows ~= 56 credits (budget <= 60).
Rows with a null funding group are not billed for it, so the actual cost is lower.
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from proofroom.crustdata import CACHED, Crustdata, sum_credits  # noqa: E402
from proofroom import revenue_model as rm  # noqa: E402

SEARCH = "/company/search"
AS_OF = date(2026, 10, 31)   # pull date; months-since-round is measured from it
STRATA = ("11-50", "51-200", "201-500", "501-1000", "1001-5000")
# (sort field, order, rows) per stratum: most funded, most recently funded, oldest-indexed.
SORTS = (("funding.total_investment_usd", "desc", 9),
         ("funding.last_fundraise_date", "desc", 9),
         ("crustdata_company_id", "asc", 8))
INDUSTRIES = ["Software Development", "Technology, Information and Internet",
              "Financial Services", "IT Services and IT Consulting"]
# Validation companies (and dev companies) are excluded so the 8-company check is held out.
EXCLUDE_IDS = [3718859, 633791, 664000, 1010356, 631347, 633593, 689494, 631990, 6421460]
FIELDS = ["crustdata_company_id", "basic_info", "revenue", "headcount", "funding", "locations"]


def body(stratum: str, sort_field: str, order: str, limit: int) -> dict:
    return {"filters": {"op": "and", "conditions": [
        {"field": "basic_info.company_type", "type": "=", "value": "Privately Held"},
        {"field": "basic_info.markets", "type": "=", "value": "PRIVATE"},
        {"field": "basic_info.year_founded", "type": "=>", "value": 2012},
        {"field": "basic_info.industries", "type": "in", "value": INDUSTRIES},
        {"field": "basic_info.employee_count_range", "type": "=", "value": stratum},
        {"field": "revenue.estimated.upper_bound_usd", "type": ">", "value": 0},
        {"field": "crustdata_company_id", "type": "not_in", "value": EXCLUDE_IDS}]},
        "sorts": [{"field": sort_field, "order": order}],
        "fields": FIELDS, "limit": limit}


async def pull() -> None:
    rows: dict[int, dict] = {}
    log = []
    async with Crustdata(CACHED) as client:
        for stratum in STRATA:
            for field, order, limit in SORTS:
                n0 = len(client.attempts)
                resp = await client.request("POST", SEARCH, body(stratum, field, order, limit))
                a = client.attempts[-1]
                got = 0
                for c in (resp or {}).get("companies") or []:
                    r = rm.row_from_search(c)
                    if r and r["crustdata_company_id"] not in rows:
                        r["stratum"] = stratum
                        r["sort"] = f"{field} {order}"
                        rows[r["crustdata_company_id"]] = r
                        got += 1
                log.append({"stratum": stratum, "sort": f"{field} {order}", "limit": limit,
                            "new_rows": got, "mode": a.mode, "credits_used": a.credits_used,
                            "total_count": (resp or {}).get("total_count")})
                print(f"{stratum:>9} {field:<32} {a.mode:<6} credits={a.credits_used:<6} "
                      f"+{got} (pool {(resp or {}).get('total_count')})")
                del n0
        live, unknown = sum_credits(client.attempts)
    doc = {"pulled_on": AS_OF.isoformat(), "endpoint": SEARCH,
           "filters": "Privately Held, markets PRIVATE, founded >= 2012, industries "
                      + ", ".join(INDUSTRIES) + ", revenue band present; validation ids excluded",
           "credits_used_live": live, "credits_unknown_attempts": unknown,
           "requests": log, "rows": list(rows.values())}
    rm.DATA_DIR.mkdir(parents=True, exist_ok=True)
    rm.TRAINING_PATH.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(rows)} rows -> {rm.TRAINING_PATH} (LIVE credits this run: {live})")


def fit() -> None:
    doc = json.loads(rm.TRAINING_PATH.read_text(encoding="utf-8"))
    rows = doc["rows"]
    model = rm.train(rows, date.fromisoformat(doc.get("pulled_on", AS_OF.isoformat())))
    model["training_set"] = {"path": "proofroom/data/training_set.json", "rows": len(rows),
                             "credits_used": doc.get("credits_used_live")}
    rm.MODEL_PATH.write_text(json.dumps(model, indent=1), encoding="utf-8")
    cv = model["cv"]
    print(f"n={model['n_rows']} method={model['method']} lambda={model['lambda']}")
    for k in ("model", "baseline"):
        print(f"  {k:<8} " + " ".join(f"{m}={v}" for m, v in cv[k].items()))
    print("  coefficients (standardized):")
    for f, w in sorted(zip(model["features"], model["coef_standardized"]), key=lambda x: -abs(x[1])):
        print(f"    {f:<26} {w:+.3f}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "pull":
        asyncio.run(pull())
    elif cmd == "fit":
        fit()
    else:
        print(__doc__)
