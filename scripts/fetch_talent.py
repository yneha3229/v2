"""Fetch talent signals (founder schools + elite-alumni staff counts) for the study companies
and record them as fixtures so reports replay offline.

    .venv/bin/python scripts/fetch_talent.py            # LIVE (needs CRUSTDATA_API_KEY)
    .venv/bin/python scripts/fetch_talent.py --fixture  # offline replay

Each count is one Person Search call with limit 1 (~0.2 credits).
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from proofroom import config, economics, talent  # noqa: E402
from proofroom.crustdata import FIXTURE, LIVE, Crustdata, _slug, cache_key  # noqa: E402

OUT = ROOT / "proofroom" / "data" / "talent.json"


def country_of(rec: dict) -> str:
    hq = (rec.get("locations") or {}).get("country") or (rec.get("basic_info") or {}).get("hq_country")
    return str(hq or (rec.get("headcount") or {}).get("largest_headcount_country") or "")


async def one(name: str, cid: int, domain: str, live: bool) -> dict:
    sig, _ = await economics.replay(name, cid, domain)
    keep = {f.name.lower() for f in sig.founders if f.name}
    async with Crustdata(FIXTURE, fixture=name) as fx:
        rec = economics._enrich_record(fx, cid) or {}
    country = country_of(rec)
    mode = dict(mode=LIVE) if live else dict(mode=FIXTURE, fixture=name)
    async with Crustdata(**mode) as c:
        t = await talent.build_talent(c, cid, rec, country, keep)
    if live:   # copy the fresh cache records next to the other fixtures
        dst = config.FIXTURES_DIR / name / "crustdata"
        bodies = [talent._count_body(cid, None)] + [
            talent._count_body(cid, talent._any_of(talent.EDU_FIELD, v)) for v in talent.COUNT_QUERIES.values()] + [
            talent._count_body(cid, talent._any_of(talent.PAST_EMPLOYER_FIELD, talent.BIG_TECH))]
        for b in bodies:
            fn = f"{_slug('/person/search')}-{cache_key('/person/search', b)}.json"
            src = config.CACHE_DIR / "crustdata" / fn
            if src.exists() and not (dst / fn).exists():
                shutil.copy(src, dst / fn)
    bonus, why = talent.team_bonus(t)
    return {"domain": domain, "country": country, **t.as_dict(), "team_bonus": bonus, "team_bonus_why": why}


async def main() -> int:
    live = "--fixture" not in sys.argv
    out = {}
    for name, cid, domain in economics.COMPANIES:
        r = await one(name, cid, domain, live)
        out[domain] = r
        print(f"{name:11} {r['country']:14} founders elite {r['founders_with_elite']}/{r['founders_total']} "
              f"{[h['label'] for h in r['founder_schools']]} staff {r['indexed_staff']} alumni {r['alumni']} "
              f"bigtech {r['ex_big_tech']} bonus +{r['team_bonus']:.0f}")
    OUT.write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
