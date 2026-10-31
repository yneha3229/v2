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


def _run(args: argparse.Namespace) -> int:
    from proofroom import pipeline

    pasted = []
    for path in args.paste or []:
        try:
            with open(path, encoding="utf-8") as f:
                pasted.append(f.read())
        except OSError as e:
            print(f"cannot read {path}: {e}", file=sys.stderr)
            return 2
    mode = "FIXTURE" if args.fixture else args.mode
    req = pipeline.RunRequest(
        domain=args.domain or FIXTURE_DOMAINS.get(args.fixture, ""), input_mode="B" if (pasted or args.url) else "A",
        run_mode=mode, profile="FAST" if args.fast else "FULL",
        provider="fixture" if args.fixture else args.provider, focus_note=args.focus or "",
        urls=args.url or [], pasted=pasted, sentence=args.sentence or "",
        fixture=args.fixture or "", email=True if args.email else None)

    def show(stage: str, payload: dict) -> None:
        print(f"[{payload.get('elapsed', 0):6.2f}s] {stage}", flush=True)
        if stage == "start" and req.provider in ("session", "auto"):
            print("        model calls are answered through request files in the run's model/ "
                  "folder (session provider)", flush=True)

    out = asyncio.run(pipeline.run(req, on_progress=show))
    print(f"{out.status} {out.run_dir or ''} in {out.seconds}s")
    if out.error:
        print(f"error: {out.error}", file=sys.stderr)
    return 0 if out.status in ("DELIVERED", "NARROWED") else 1


FIXTURE_DOMAINS = {"koah": "koahlabs.com", "linear": "linear.app", "attio": "attio.com"}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="proofroom")
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("probe", help="Identify (and optionally enrich) a development company")
    pr.add_argument("domain")
    pr.add_argument("--enrich", action="store_true")
    rn = sub.add_parser("run", help="Produce a Team & Financing brief")
    rn.add_argument("--domain", default="")
    rn.add_argument("--paste", action="append", help="file of pasted text (Mode B); repeatable")
    rn.add_argument("--url", action="append", help="source URL (Mode B); repeatable")
    rn.add_argument("--sentence", help="U5: check one sentence only")
    rn.add_argument("--focus", help="focus note")
    rn.add_argument("--mode", default="CACHED", choices=["LIVE", "CACHED"])
    rn.add_argument("--fixture", choices=sorted(FIXTURE_DOMAINS), help="replay a demo case, no keys")
    rn.add_argument("--fast", action="store_true", help="FAST profile: every step, lighter checks")
    rn.add_argument("--email", action="store_true",
                    help="U8: also write founder_email.md (a draft, never sent)")
    rn.add_argument("--provider", default="auto", choices=["auto", "session", "anthropic"])
    vf = sub.add_parser("verify", help="U1 proof receipt: re-check a published run offline")
    vf.add_argument("run_dir")
    sub.add_parser("warmup", help="send each model schema once with a tiny synthetic input")
    p.add_argument("-v", "--verbose", action="store_true", help="log at INFO")
    args = p.parse_args(argv)
    log.setup("INFO" if args.verbose else None)

    if args.cmd == "run":
        try:
            return _run(args)
        except ProofroomError as e:
            print(f"FAILED: {e}", file=sys.stderr)
            return 1
    if args.cmd == "verify":
        from pathlib import Path

        from proofroom import verify
        receipt = verify.verify_receipt(Path(args.run_dir))
        print(verify.format_receipt(receipt))
        return 0 if receipt.ok else 1
    if args.cmd == "warmup":
        from proofroom import config, llm
        provider = llm.make_provider("auto", config.DATA_DIR / "warmup", None)
        for line in asyncio.run(llm.warmup(provider)):
            print(line)
        return 0
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
