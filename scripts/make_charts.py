"""Render the signal charts (PNG) for the report preview: TerraStack growth, pay context,
pillars; invest scores for all study companies; revenue-model accuracy.

    .venv/bin/python scripts/make_charts.py      # writes docs/charts/*.png (offline replay)

Static images (no hover layer); every bar carries a direct value label.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import signal_dashboard as sd  # noqa: E402
from proofroom import economics  # noqa: E402

OUT = ROOT / "docs" / "charts"
INR_PER_USD = 94.955          # ECB cross rate 2026-10-30, as in salary_benchmarks.json
W, H = 760, 380
CSS = """
:root{--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#8a8984;--grid:#e6e5e0;
--s1:#2a78d6;--s2:#eb6834;--good:#0ca30c;--warn:#fab219;--serious:#ec835a;--crit:#d03b3b;--neutral:#b9b8b2}
body{margin:0;background:var(--surface);font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink)}
.chart{width:%dpx;padding:20px 24px 16px;box-sizing:border-box;background:var(--surface)}
h2{font-size:17px;margin:0 0 4px;font-weight:650}
p.sub{font-size:12.5px;color:var(--ink2);margin:0 0 10px}
p.src{font-size:10.5px;color:var(--muted);margin:6px 0 0}
svg text{font-family:inherit}
""" % W


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def frame(cid: str, title: str, sub: str, svg: str, src: str) -> str:
    return (f'<div class="chart" id="{cid}"><h2>{_esc(title)}</h2><p class="sub">{_esc(sub)}</p>'
            f'{svg}<p class="src">{_esc(src)}</p></div>')


def hbars(rows, *, vmax, fmt, ref=None, width=W - 48, label_w=230, bar_h=22, gap=10):
    """rows: (label, value, color). Horizontal bars from a zero baseline, value labelled."""
    h = len(rows) * (bar_h + gap) + 24 + (12 if ref else 0)
    plot = width - label_w - 70
    out = [f'<svg width="{width}" height="{h}" viewBox="0 0 {width} {h}">']
    for frac in (0, .25, .5, .75, 1):
        x = label_w + plot * frac
        out.append(f'<line x1="{x:.1f}" y1="0" x2="{x:.1f}" y2="{h - 20}" stroke="var(--grid)"/>'
                   f'<text x="{x:.1f}" y="{h - 6}" font-size="10.5" fill="var(--muted)" text-anchor="middle">{fmt(vmax * frac)}</text>')
    for val, txt in (ref or []):
        x = label_w + plot * val / vmax
        out.append(f'<line x1="{x:.1f}" y1="0" x2="{x:.1f}" y2="{h - 20}" stroke="var(--muted)" stroke-dasharray="3 3"/>'
                   f'<text x="{x:.1f}" y="10" font-size="10" fill="var(--ink2)" text-anchor="middle">{_esc(txt)}</text>')
    top = 16 if ref else 4
    for i, (lab, v, col) in enumerate(rows):
        y = i * (bar_h + gap) + top
        bw = max(plot * v / vmax, 2)
        out.append(f'<text x="{label_w - 10}" y="{y + bar_h * .68:.1f}" font-size="12.5" fill="var(--ink)" text-anchor="end">{_esc(lab)}</text>'
                   f'<rect x="{label_w}" y="{y}" width="{bw:.1f}" height="{bar_h}" rx="4" fill="{col}"/>'
                   f'<text x="{label_w + bw + 6:.1f}" y="{y + bar_h * .68:.1f}" font-size="12" fill="var(--ink2)" font-weight="600">{fmt(v)}</text>')
    return "".join(out) + "</svg>"


def line(points, *, fmt, color="var(--s1)", width=W - 48, height=230, annotate=None, bars=False):
    """points: [(label 'YYYY-MM', value)]. Single series, zero baseline."""
    pl, pr, pt, pb = 46, 16, 14, 30
    vmax = max(v for _, v in points) * 1.15 or 1
    n = len(points)
    xs = [pl + (width - pl - pr) * (i / max(n - 1, 1) if not bars else (i + .5) / n) for i in range(n)]
    ys = [pt + (height - pt - pb) * (1 - v / vmax) for _, v in points]
    base = height - pb
    out = [f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">']
    for frac in (0, .5, 1):
        y = pt + (height - pt - pb) * (1 - frac)
        out.append(f'<line x1="{pl}" y1="{y:.1f}" x2="{width - pr}" y2="{y:.1f}" stroke="var(--grid)"/>'
                   f'<text x="{pl - 6}" y="{y + 4:.1f}" font-size="10.5" fill="var(--muted)" text-anchor="end">{fmt(vmax * frac)}</text>')
    step = max(1, n // 8)
    for i, (lab, _) in enumerate(points):
        if (i % step == 0 and n - 1 - i >= step / 2) or i == n - 1:
            out.append(f'<text x="{xs[i]:.1f}" y="{height - 10}" font-size="10.5" fill="var(--muted)" text-anchor="middle">{lab}</text>')
    if bars:
        bw = (width - pl - pr) / n * .6
        for x, y, (_, v) in zip(xs, ys, points):
            out.append(f'<rect x="{x - bw / 2:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{base - y:.1f}" rx="4" fill="{color}"/>'
                       f'<text x="{x:.1f}" y="{y - 5:.1f}" font-size="11" fill="var(--ink2)" text-anchor="middle" font-weight="600">{fmt(v)}</text>')
    else:
        d = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(zip(xs, ys)))
        out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.25" stroke-linejoin="round"/>')
        for i in {n - 1, max(range(n), key=lambda k: points[k][1])}:
            out.append(f'<circle cx="{xs[i]:.1f}" cy="{ys[i]:.1f}" r="4.5" fill="{color}" stroke="var(--surface)" stroke-width="2"/>'
                       f'<text x="{xs[i]:.1f}" y="{ys[i] - 10:.1f}" font-size="11.5" fill="var(--ink)" text-anchor="middle" font-weight="600">{fmt(points[i][1])}</text>')
    for lab, txt in (annotate or []):
        i = next((k for k, (l, _) in enumerate(points) if l == lab), None)
        if i is not None:
            out.append(f'<line x1="{xs[i]:.1f}" y1="{pt}" x2="{xs[i]:.1f}" y2="{base}" stroke="var(--ink2)" stroke-dasharray="4 3"/>'
                       f'<text x="{xs[i] + 5:.1f}" y="{pt + 10}" font-size="10.5" fill="var(--ink2)">{_esc(txt)}</text>')
    return "".join(out) + "</svg>"


def _k(v):
    return f"{v / 1e3:,.1f}K" if 1e3 <= v < 1e4 else f"{v / 1e3:,.0f}K" if v >= 1e4 else f"{v:,.0f}"


def _lpa(v):
    return f"₹{v:,.1f}L"


RATING_COLOR = {"INVEST": "var(--good)", "ACCUMULATE": "var(--warn)", "HOLD": "var(--serious)", "AVOID": "var(--crit)"}


async def build() -> str:
    rows = [await sd.row_for(*c) for c in economics.COMPANIES]
    ts = next(r for r in rows if "terra" in r["domain"])
    sig, eco = ts["sig"], ts["eco"]
    S = {k: [(p.date, p.value) for p in s.points] if hasattr(s, "points") else [(p.date, p.value) for p in s]
         for k, s in sig.series.items()}
    charts = []

    hc = S["headcount"]
    charts.append(frame("ts_headcount", "TerraStack: headcount over time",
                        f"Grew from 1 to a peak of {max(v for _, v in hc):.0f}; now {hc[-1][1]:.0f} (-22% over 6 months, +133% over 2 years)",
                        line(hc, fmt=lambda v: f"{v:.0f}", annotate=[("2026-04", "6 months ago")]),
                        "Source: Crustdata Company Enrich, headcount timeseries (monthly). Indexed LinkedIn profiles."))
    wv = S["web_visitors"]
    charts.append(frame("ts_web", "TerraStack: monthly website visitors",
                        "Latest month 7.7K, about 4x the prior peak (+338% quarter on quarter)",
                        line(wv, fmt=_k, bars=True),
                        "Source: Crustdata Company Enrich, web traffic (monthly visitors)."))
    fo = S["followers"]
    charts.append(frame("ts_followers", "TerraStack: LinkedIn followers",
                        "766 followers, +64% year on year",
                        line(fo, fmt=lambda v: f"{v:.0f}", color="var(--s2)"),
                        "Source: Crustdata Company Enrich, follower timeseries."))

    pl = ts["pillars"]
    charts.append(frame("ts_pillars", "TerraStack: score by pillar (0-100)",
                        f"Overall {ts['rec'].score:.0f}/100 -> {ts['rec'].rating}; Traction is the weak spot",
                        hbars([(f"{p.name}", p.score, "var(--s1)") for p in sorted(pl, key=lambda p: -p.score)],
                              vmax=100, fmt=lambda v: f"{v:.0f}", ref=[(70, "INVEST line 70")], label_w=130),
                        "Weights: Team 25%, Traction 30%, Market 15%, Financing 15%, Verification 15%. Market and Verification are neutral 50 (not yet measured)."))

    # pay context (annual, ₹ lakh)
    bm = {(b["role"], b["location"]): b for b in json.loads((ROOT / "proofroom/data/salary_benchmarks.json").read_text())["benchmarks"]}
    ts_avg = eco.payroll.avg_salary_usd * INR_PER_USD / 1e5
    pay = [("India avg salaried worker (PLFS 2025)", 24217 * 12 / 1e5, "var(--neutral)"),
           ("TCS avg (Payscale)", 7.59, "var(--neutral)"),
           ("TerraStack est. avg (7 staff)", ts_avg, "var(--s1)"),
           ("India software engineer avg", bm[("Engineering", "Other India")]["local_amount"] / 1e5, "var(--neutral)"),
           ("Infosys avg (Payscale)", 8.50, "var(--neutral)"),
           ("Bangalore software engineer avg", bm[("Engineering", "Bangalore/India")]["local_amount"] / 1e5, "var(--neutral)")]
    pay.sort(key=lambda r: r[1])
    charts.append(frame("ts_pay", "TerraStack pay vs India benchmarks (annual, ₹ lakh)",
                        f"Est. ₹{ts_avg:.1f} lakh average: ~{ts_avg / (24217 * 12 / 1e5):.1f}x India's average salaried wage, on par with IT-services majors",
                        hbars(pay, vmax=12, fmt=_lpa, label_w=260),
                        "TerraStack figure is a model estimate (benchmarks x role mix x 1.21-1.30 switch premium), not reported pay. PLFS 2025 male regular-wage avg ₹24,217/mo; Payscale India; ₹94.955/USD."))

    # same team, other city
    mix = eco.payroll.by_role
    role_map = {"Data & Research": "Data Science"}
    sf = sum(n * bm[(role_map.get(r, r), "San Francisco Bay Area")]["annual_usd"] for r, n in mix.items()) * 1.3
    charts.append(frame("ts_team_cost", "Cost of TerraStack's 7-person team per year (loaded)",
                        f"Mumbai ~${eco.payroll.loaded_cost_usd / 1e3:,.0f}K vs ~${sf / 1e6:,.2f}M for the same roles in San Francisco: ~{sf / eco.payroll.loaded_cost_usd:.0f}x longer runway per dollar",
                        hbars([("TerraStack, Mumbai (est.)", eco.payroll.loaded_cost_usd, "var(--s1)"),
                               ("Same roles, San Francisco", sf, "var(--neutral)")],
                              vmax=1.6e6, fmt=lambda v: f"${v / 1e6:,.2f}M" if v >= 1e6 else f"${v / 1e3:,.0f}K", label_w=210),
                        "Loaded = salary x 1.3 (benefits, taxes, overhead). SF from BLS OEWS May 2025 cells in salary_benchmarks.json."))

    inv = sorted(rows, key=lambda r: -r["rec"].score)
    charts.append(frame("invest_scores", "Invest signal: all 9 companies (score 0-100)",
                        "INVEST >= 70, ACCUMULATE >= 58, HOLD >= 45, else AVOID (caps apply for red/critical flags)",
                        hbars([(f"{'TerraStack' if 'terra' in r['domain'] else r['name']}{'' if r['verified'] else ' *'}  ·  {r['rec'].rating}", r["rec"].score,
                                RATING_COLOR[r["rec"].rating]) for r in inv],
                              vmax=100, fmt=lambda v: f"{v:.0f}", ref=[(70, "70"), (58, "58"), (45, "45")], label_w=230),
                        "* not yet claims-verified (Verification neutral 50). Ramp is held down by a namesake headcount artifact. Rules-based, not advice."))

    acc = [("Crustdata band midpoint", 78), ("Model 3 (ridge, new signals)", 79), ("Model v1", 57), ("Model v2 (+ social posts)", 57),
           ("Reported-revenue benchmark", 42), ("Payroll x multiplier (model 3)", 34), ("Calibrated ensemble (D29)", 31),
           ("Bake-off pipeline (in use)", 14)]
    charts.append(frame("revenue_accuracy", "Revenue models: median error vs reported revenue",
                        "Lower is better; 6 companies with public revenue, leave-one-out",
                        hbars([(l, v, "var(--s1)" if "in use" in l else "var(--neutral)") for l, v in acc],
                              vmax=100, fmt=lambda v: f"{v:.0f}%", label_w=250),
                        "Small sample (n=6): directional, not statistically strong. Details: docs/revenue_evaluation.md, docs/revenue_model_3_results.md."))
    return f"<!doctype html><html><head><meta charset=utf-8><style>{CSS}</style></head><body>{''.join(charts)}</body></html>"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    html = OUT / "_charts.html"
    html.write_text(asyncio.run(build()))
    js = OUT / "_shot.js"
    js.write_text("""const {chromium}=require('playwright');(async()=>{const b=await chromium.launch();
const p=await b.newPage({deviceScaleFactor:2});await p.goto('file://'+process.argv[2]);
for(const el of await p.$$('.chart')){const id=await el.getAttribute('id');await el.screenshot({path:process.argv[3]+'/'+id+'.png'});console.log(id);}
await b.close();})();""")
    npm_root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip()
    subprocess.run(["node", str(js), str(html), str(OUT)], check=True, env={**os.environ, "NODE_PATH": npm_root})
    js.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
