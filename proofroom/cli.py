"""Command line: `python -m proofroom <probe|warmup|run> ...`."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from proofroom import crustdata as cd
from proofroom import graph, log
from proofroom.errors import ProofroomError

DEV_DOMAINS = {"koahlabs.com", "linear.app", "attio.com"}


async def _probe(domain: str, enrich: bool) -> int:
    async with cd.Crustdata(cd.CACHED) as c:
        ident = await c.identify_domain(domain)
        g1 = graph.resolve_g1(domain, ident)
        print(f"G1 {domain}: {g1.status} id={g1.company_id} basis={g1.basis}")
        for cand in g1.candidates:
            print(f"  candidate {cand['id']} {cand['name']!r} {cand['primary_domain']} "
                  f"conf={cand['confidence']}")
        if enrich and g1.company_id:
            rec = graph.company_record(await c.company_enrich(g1.company_id))
            fund = rec.get("funding") or {}
            print(f"  funding total={fund.get('total_investment_usd')} "
                  f"last={fund.get('last_round_type')} {fund.get('last_round_amount_usd')}")
            print(f"  founders={len((rec.get('people') or {}).get('founders') or [])} "
                  f"news={len(rec.get('news') or [])}")
        for a in c.attempts:
            print(f"  attempt {a.endpoint} {a.mode} {a.status} {a.seconds}s credits={a.credits_used}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="proofroom")
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("probe", help="Identify (and optionally enrich) a development company")
    pr.add_argument("domain")
    pr.add_argument("--enrich", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true", help="log at INFO")
    args = p.parse_args(argv)
    log.setup("INFO" if args.verbose else None)

    if args.cmd == "probe":
        if args.domain not in DEV_DOMAINS:
            print(f"refusing: probe only development companies {sorted(DEV_DOMAINS)}",
                  file=sys.stderr)
            return 2
        try:
            return asyncio.run(_probe(args.domain, args.enrich))
        except ProofroomError as e:
            detail = e.as_dict() if hasattr(e, "as_dict") else str(e)
            print(f"FAILED: {json.dumps(detail)}", file=sys.stderr)
            return 1
    return 2
