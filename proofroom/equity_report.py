"""Equity-research style PDF report (D24).

`build_html()` turns a verified CaseRecord plus Signals, flags, pillar scores and a
Recommendation into one self-contained A4 HTML document (system fonts, inline SVG,
no network). `render_pdf()` prints it to PDF with Playwright's Chromium through
`proofroom/pdf/render_pdf.js`; when node or Playwright is missing it raises
`PdfRenderError` and the caller serves the HTML instead.

Pages: 1 Investment snapshot · 2 Why this rating · 3 Growth and traction · 4 Team ·
5 Market and competition · 6 Financing and verified claims · 7 Methodology.

Honesty rules: every number shown comes from Signals, the CaseRecord, or a plain
calculation over them (labelled); every run label is printed; text from sources is
HTML-escaped; Crustdata funding is "indexed record (Crunchbase-derived)".
"""
from __future__ import annotations

import functools
import html
import math
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Iterable

from proofroom.errors import ProofroomError
from proofroom.models import CaseRecord, TeamRow
from proofroom.research_models import (Flag, Metric, Pillar, Point, Recommendation, Series,
                                       Signals)

__all__ = ["build_html", "render_pdf", "pdf_available", "PdfRenderError", "svg_line_chart",
           "svg_band_chart", "svg_bar_chart", "svg_donut", "svg_stacked_bar", "svg_gauge",
           "svg_sparkline", "svg_rounds_chart", "DISCLAIMER"]

DISCLAIMER = ("Rules-based signal from public and indexed data; not financial advice. "
              "Proofroom verifies Team & Financing claims and summarises indexed signals; it "
              "does not value the company or assess the product.")

RENDER_JS = Path(__file__).resolve().parent / "pdf" / "render_pdf.js"
PDF_TIMEOUT_S = 60


class PdfRenderError(ProofroomError):
    """The PDF could not be rendered (node/Playwright missing or Chromium failed).

    The caller should fall back to serving the HTML report.
    """


# ---- palette (dataviz reference instance, light print surface) ----------------------
BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, REDS = (
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
CATEGORICAL = [BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, REDS]
GOOD, WARN, SERIOUS, CRIT, CRIT_DARK = "#0ca30c", "#fab219", "#ec835a", "#d03b3b", "#8f1d1d"
GRID, AXIS, MUTED, NAVY = "#e1e0d9", "#c3c2b7", "#6b6a65", "#0f1f3d"

RATING_STYLE = {  # background, text
    "INVEST": ("#0a7d32", "#ffffff"),
    "ACCUMULATE": ("#8fd17a", "#0b2b12"),
    "HOLD": (WARN, "#0b0b0b"),
    "AVOID": (CRIT, "#ffffff"),
}
RATING_INK = {"INVEST": "#0a7d32", "ACCUMULATE": "#2f7a1f", "HOLD": "#8a5a00", "AVOID": "#b42323"}
LEVEL_META = {  # heading, colour, short label
    "critical": ("Critical flags · verification and integrity", CRIT_DARK, "Critical"),
    "red": ("Red flags · business risks", CRIT, "Red"),
    "amber": ("Open points", "#b27a00", "Amber"),
    "green": ("Green flags", "#0a7d32", "Green"),
}
DISPOSITION = {  # label, css class
    "supported": ("Supported", "ok"),
    "supported_corrected": ("Supported, corrected", "warn"),
    "conflicting": ("Conflicting", "bad"),
    "not_established": ("Not established", "muted"),
}
BASIS_LABEL = {
    "company_statement": "company statement",
    "investor_statement": "investor statement",
    "independent_report": "independent report",
    "crustdata_indexed_record": "indexed record (Crunchbase-derived)",
    "calculation": "calculation",
}

_e = functools.partial(html.escape, quote=True)


# ---- formatting -----------------------------------------------------------------------

def _trim(x: float, digits: int = 1) -> str:
    s = f"{x:.{digits}f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def fmt_compact(v: float | None) -> str:
    if v is None:
        return "n/a"
    a, sign = abs(v), "-" if v < 0 else ""
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            return f"{sign}{_trim(a / div)}{suf}"
    return f"{sign}{_trim(a, 1 if a < 10 and a != int(a) else 0)}"


def fmt_usd(v: float | None) -> str:
    if v is None:
        return "n/a"
    return ("-" if v < 0 else "") + "$" + fmt_compact(abs(v))


def fmt_pct(v: float | None, signed: bool = True) -> str:
    if v is None:
        return "n/a"
    return (f"{v:+.1f}%" if signed else f"{v:.1f}%").replace(".0%", "%")


def fmt_value(v: float | None, unit: str = "") -> str:
    u = (unit or "").lower()
    if v is None:
        return "n/a"
    if u in ("usd", "$"):
        return fmt_usd(v)
    if u == "%":
        return fmt_pct(v)
    return fmt_compact(v)


def parse_date(s: str) -> date | None:
    """ISO date at its precision; YYYY and YYYY-01-01 are year-level (CLAUDE.md §3)."""
    m = re.match(r"^\s*(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?", s or "")
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2) or 1), int(m.group(3) or 1))
    except ValueError:
        return None


def _date_label(s: str) -> str:
    d = parse_date(s)
    if d is None:
        return s or "date n/r"
    if re.fullmatch(r"\d{4}", s.strip()) or re.fullmatch(r"\d{4}-01-01", s.strip()):
        return str(d.year)
    if re.fullmatch(r"\d{4}-\d{1,2}", s.strip()):
        return d.strftime("%b %Y")
    return f"{d.day} {d.strftime('%b %Y')}"


def _months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month) - (1 if b.day < a.day else 0)


def _nice_step(span: float, n: int) -> float:
    raw = span / max(n, 1)
    if raw <= 0:
        return 1.0
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def _ticks(lo: float, hi: float, n: int = 4) -> list[float]:
    if hi == lo:
        hi, lo = hi + (abs(hi) or 1) * 0.5, lo - (abs(lo) or 1) * 0.5
    step = _nice_step(hi - lo, n)
    start, end = math.floor(lo / step) * step, math.ceil(hi / step) * step
    out, v = [], start
    while v <= end + step * 1e-9 and len(out) < 12:
        out.append(round(v, 10))
        v += step
    return out


# ---- SVG primitives ---------------------------------------------------------------

_SVG_FONT = "font-family=\"Inter, system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif\""


def _svg_open(w: int, h: int, label: str) -> str:
    return (f'<svg class="chart" viewBox="0 0 {w} {h}" width="100%" role="img" '
            f'aria-label="{_e(label)}" xmlns="http://www.w3.org/2000/svg" {_SVG_FONT} '
            f'font-size="10" style="color:inherit"><title>{_e(label)}</title>')


def _no_data(w: int, h: int, title: str, msg: str = "no data") -> str:
    return (_svg_open(w, h, f"{title}: {msg}")
            + f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="6" fill="none" '
              f'stroke="{GRID}" stroke-dasharray="4 3"/>'
            + f'<text x="{w / 2}" y="{h / 2 + 4}" text-anchor="middle" fill="currentColor" '
              f'fill-opacity="0.55" font-size="11">{_e(msg)}</text></svg>')


def _txt(x: float, y: float, s: str, *, anchor: str = "start", size: float = 10,
         weight: str = "400", opacity: float = 1.0, fill: str = "currentColor") -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" fill-opacity="{opacity}">{_e(s)}</text>')


def _valid_points(s: Series) -> list[tuple[date, float]]:
    pts = []
    for p in s.points:
        d = parse_date(p.date)
        if d is not None and p.value is not None and math.isfinite(p.value):
            pts.append((d, float(p.value)))
    return sorted(pts)


def _x_ticks(d0: date, d1: date, n: int = 4) -> list[tuple[date, str]]:
    span = (d1 - d0).days
    fmt = "%Y" if span > 1100 else "%b '%y"
    out, seen = [], set()
    for i in range(n):
        d = date.fromordinal(d0.toordinal() + round(span * i / max(n - 1, 1)))
        lab = d.strftime(fmt)
        if lab not in seen:
            seen.add(lab)
            out.append((d, lab))
    return out


def svg_line_chart(series: list[Series], *, width: int = 340, height: int = 170, title: str = "",
                   annotation: str = "", colors: list[str] | None = None,
                   zero_based: bool | None = None) -> str:
    """Line chart over dated points. Legend for >=2 series; end-point value labels."""
    title = title or (series[0].label if series else "chart")
    data = [(s, _valid_points(s)) for s in series]
    data = [(s, p) for s, p in data if p]
    if not data:
        return _no_data(width, height, title)
    colors = colors or CATEGORICAL
    unit = data[0][0].unit
    all_pts = [pt for _, ps in data for pt in ps]
    d0, d1 = min(p[0] for p in all_pts), max(p[0] for p in all_pts)
    if d0 == d1:
        d0, d1 = date.fromordinal(d0.toordinal() - 45), date.fromordinal(d1.toordinal() + 45)
    vmin, vmax = min(p[1] for p in all_pts), max(p[1] for p in all_pts)
    if zero_based is None:
        zero_based = vmin >= 0 and vmin < 0.6 * vmax
    lo = 0.0 if zero_based and vmin >= 0 else vmin
    yt = _ticks(lo, vmax if vmax != lo else lo + 1, 4)
    legend_h = 16 if len(data) >= 2 else 0
    ml, mr, mt, mb = 40, 46, 12 + legend_h + (12 if annotation else 0), 22
    pw, ph = width - ml - mr, height - mt - mb
    y_lo, y_hi = yt[0], yt[-1]

    def X(d: date) -> float:
        return ml + pw * (d.toordinal() - d0.toordinal()) / max(d1.toordinal() - d0.toordinal(), 1)

    def Y(v: float) -> float:
        return mt + ph - ph * (v - y_lo) / max(y_hi - y_lo, 1e-12)

    out = [_svg_open(width, height, title)]
    for t in yt:
        y = Y(t)
        out.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{y:.1f}" y2="{y:.1f}" '
                   f'stroke="{AXIS if t == y_lo else GRID}" stroke-width="{1 if t == y_lo else 0.6}"/>')
        out.append(_txt(ml - 5, y + 3.5, fmt_value(t, unit), anchor="end", size=9, opacity=0.6))
    for d, lab in _x_ticks(d0, d1):
        out.append(_txt(X(d), height - 7, lab, anchor="middle", size=9, opacity=0.6))
    if annotation:
        out.append(_txt(ml, 12 + legend_h, annotation, size=10, weight="600"))
    if legend_h:
        x = ml
        for i, (s, _) in enumerate(data):
            c = colors[i % len(colors)]
            out.append(f'<rect x="{x}" y="4" width="10" height="3" rx="1.5" fill="{c}"/>')
            out.append(_txt(x + 14, 9, s.label, size=9, opacity=0.8))
            x += 22 + 5.4 * len(s.label)
    for i, (s, ps) in enumerate(data):
        c = colors[i % len(colors)]
        coords = [(X(d), Y(v)) for d, v in ps]
        if len(coords) == 1:
            cx, cy = coords[0]
            out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="{c}" stroke="#fff" stroke-width="2"/>')
            out.append(_txt(cx, cy - 8, f"{fmt_value(ps[0][1], s.unit)} (one data point)",
                            anchor="middle", size=9, weight="600"))
            continue
        path = " ".join(f"{'M' if j == 0 else 'L'}{x:.1f},{y:.1f}" for j, (x, y) in enumerate(coords))
        if len(data) == 1:
            area = path + f" L{coords[-1][0]:.1f},{Y(y_lo):.1f} L{coords[0][0]:.1f},{Y(y_lo):.1f} Z"
            out.append(f'<path d="{area}" fill="{c}" fill-opacity="0.10"/>')
        out.append(f'<path d="{path}" fill="none" stroke="{c}" stroke-width="2" '
                   f'stroke-linejoin="round" stroke-linecap="round"/>')
        lx, ly = coords[-1]
        out.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.5" fill="{c}" stroke="#fff" stroke-width="2"/>')
        out.append(_txt(lx + 6, ly + 3.5, fmt_value(ps[-1][1], s.unit), size=9.5, weight="600"))
    out.append("</svg>")
    return "".join(out)


def svg_band_chart(low: Series | None, high: Series | None, *, width: int = 340, height: int = 170,
                   title: str = "Revenue estimate band") -> str:
    """Shaded lower/upper band over time (an estimate range, not reported revenue)."""
    lo_pts = dict(_valid_points(low)) if low else {}
    hi_pts = dict(_valid_points(high)) if high else {}
    dates = sorted(set(lo_pts) & set(hi_pts))
    if not dates:
        return _no_data(width, height, title)
    vmax = max(hi_pts[d] for d in dates)
    yt = _ticks(0.0, vmax or 1.0, 4)
    ml, mr, mt, mb = 44, 74, 12, 22
    pw, ph = width - ml - mr, height - mt - mb
    d0, d1 = dates[0], dates[-1]
    if d0 == d1:
        d0, d1 = date.fromordinal(d0.toordinal() - 45), date.fromordinal(d1.toordinal() + 45)

    def X(d: date) -> float:
        return ml + pw * (d.toordinal() - d0.toordinal()) / max(d1.toordinal() - d0.toordinal(), 1)

    def Y(v: float) -> float:
        return mt + ph - ph * v / max(yt[-1], 1e-12)

    out = [_svg_open(width, height, title)]
    for t in yt:
        out.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" '
                   f'stroke="{AXIS if t == 0 else GRID}" stroke-width="{1 if t == 0 else 0.6}"/>')
        out.append(_txt(ml - 5, Y(t) + 3.5, fmt_usd(t), anchor="end", size=9, opacity=0.6))
    for d, lab in _x_ticks(d0, d1):
        out.append(_txt(X(d), height - 7, lab, anchor="middle", size=9, opacity=0.6))
    if len(dates) == 1:
        d = dates[0]
        out.append(f'<rect x="{X(d) - 9:.1f}" y="{Y(hi_pts[d]):.1f}" width="18" '
                   f'height="{max(Y(lo_pts[d]) - Y(hi_pts[d]), 2):.1f}" rx="4" fill="{BLUE}" fill-opacity="0.35"/>')
    else:
        top = " ".join(f"{X(d):.1f},{Y(hi_pts[d]):.1f}" for d in dates)
        bot = " ".join(f"{X(d):.1f},{Y(lo_pts[d]):.1f}" for d in reversed(dates))
        out.append(f'<polygon points="{top} {bot}" fill="{BLUE}" fill-opacity="0.20"/>')
        for pts in (hi_pts, lo_pts):
            p = " ".join(f"{'M' if i == 0 else 'L'}{X(d):.1f},{Y(pts[d]):.1f}" for i, d in enumerate(dates))
            out.append(f'<path d="{p}" fill="none" stroke="{BLUE}" stroke-width="1.5"/>')
    last = dates[-1]
    out.append(_txt(X(last) + 6, Y(hi_pts[last]) + 3, f"high {fmt_usd(hi_pts[last])}", size=9, weight="600"))
    out.append(_txt(X(last) + 6, Y(lo_pts[last]) + 10, f"low {fmt_usd(lo_pts[last])}", size=9, weight="600"))
    out.append("</svg>")
    return "".join(out)


def svg_bar_chart(items: list[tuple[str, float | None]], *, width: int = 340, title: str = "",
                  unit: str = "%", highlight: str | None = None,
                  reference: tuple[str, float] | None = None, color: str = BLUE) -> str:
    """Horizontal bars (handles negatives), value labels, optional dashed reference line."""
    title = title or "bar chart"
    vals = [v for _, v in items if v is not None]
    if not items or not vals:
        return _no_data(width, 90, title)
    row, ml, mr = 20, 116, 52
    mt = 16 if reference else 6
    height = mt + row * len(items) + 8
    refv = [reference[1]] if reference else []
    lo, hi = min([0.0, *vals, *refv]), max([0.0, *vals, *refv])
    if hi == lo:
        hi = lo + 1
    pw = width - ml - mr

    def X(v: float) -> float:
        return ml + pw * (v - lo) / (hi - lo)

    out = [_svg_open(width, height, title)]
    out.append(f'<line x1="{X(0):.1f}" x2="{X(0):.1f}" y1="{mt - 2}" y2="{height - 6}" stroke="{AXIS}"/>')
    for i, (name, v) in enumerate(items):
        y = mt + i * row
        is_hi = highlight is not None and name == highlight
        label = name if len(name) <= 20 else name[:19] + "…"
        out.append(_txt(ml - 6, y + 13, label, anchor="end", size=9.5,
                        weight="700" if is_hi else "400", opacity=1 if is_hi else 0.8))
        if v is None:
            out.append(_txt(X(0) + 4, y + 13, "n/a", size=9, opacity=0.5))
            continue
        x0, x1 = sorted((X(0), X(v)))
        fill = color if is_hi or highlight is None else "#9fb3c8"
        out.append(f'<rect x="{x0:.1f}" y="{y + 4}" width="{max(x1 - x0, 1.5):.1f}" height="{row - 8}" '
                   f'rx="3" fill="{fill}"/>')
        lab = fmt_value(v, unit)
        if v >= 0:
            out.append(_txt(x1 + 4, y + 13, lab, size=9, weight="600" if is_hi else "400"))
        else:
            out.append(_txt(X(0) + 4, y + 13, lab, size=9, weight="600" if is_hi else "400"))
    if reference:
        rx = X(reference[1])
        out.append(f'<line x1="{rx:.1f}" x2="{rx:.1f}" y1="{mt - 4}" y2="{height - 6}" stroke="{NAVY}" '
                   f'stroke-width="1.2" stroke-dasharray="3 2"/>')
        out.append(_txt(rx, 9, f"{reference[0]} {fmt_value(reference[1], unit)}", anchor="middle",
                        size=8.5, weight="600"))
    out.append("</svg>")
    return "".join(out)


def _fold_mix(mix: dict[str, float], keep: int = 6) -> list[tuple[str, float]]:
    items = sorted(((k, float(v)) for k, v in (mix or {}).items() if v is not None and v > 0),
                   key=lambda kv: -kv[1])
    if len(items) > keep:
        other = sum(v for _, v in items[keep - 1:])
        items = items[: keep - 1] + [("Other", other)]
    return items


def svg_donut(mix: dict[str, float], *, width: int = 340, height: int = 150, title: str = "Role mix") -> str:
    """Donut with a legend (shares in %). More than six slices fold into 'Other'."""
    items = _fold_mix(mix)
    total = sum(v for _, v in items)
    if not items or total <= 0:
        return _no_data(width, height, title)
    cx, cy, r, rw = height / 2, height / 2, height / 2 - 8, 18
    out = [_svg_open(width, height, title)]
    a0 = -math.pi / 2
    for i, (name, v) in enumerate(items):
        frac = v / total
        a1 = a0 + frac * 2 * math.pi
        c = CATEGORICAL[i % len(CATEGORICAL)]
        if frac >= 0.9999:
            out.append(f'<circle cx="{cx}" cy="{cy}" r="{r - rw / 2}" fill="none" stroke="{c}" stroke-width="{rw}"/>')
        else:
            large = 1 if a1 - a0 > math.pi else 0
            ro, ri = r, r - rw
            p = (f"M{cx + ro * math.cos(a0):.2f},{cy + ro * math.sin(a0):.2f} "
                 f"A{ro},{ro} 0 {large} 1 {cx + ro * math.cos(a1):.2f},{cy + ro * math.sin(a1):.2f} "
                 f"L{cx + ri * math.cos(a1):.2f},{cy + ri * math.sin(a1):.2f} "
                 f"A{ri},{ri} 0 {large} 0 {cx + ri * math.cos(a0):.2f},{cy + ri * math.sin(a0):.2f} Z")
            out.append(f'<path d="{p}" fill="{c}" stroke="#fff" stroke-width="2"/>')
        a0 = a1
    top = items[0]
    out.append(_txt(cx, cy - 1, fmt_pct(100 * top[1] / total, signed=False), anchor="middle", size=15, weight="700"))
    out.append(_txt(cx, cy + 12, top[0][:14], anchor="middle", size=8.5, opacity=0.65))
    lx = height + 8
    for i, (name, v) in enumerate(items):
        y = 14 + i * 20
        out.append(f'<rect x="{lx}" y="{y - 8}" width="10" height="10" rx="2" fill="{CATEGORICAL[i % 8]}"/>')
        out.append(_txt(lx + 16, y + 1, name[:26], size=9.5))
        out.append(_txt(width - 4, y + 1, fmt_pct(100 * v / total, signed=False), anchor="end", size=9.5, weight="600"))
    out.append("</svg>")
    return "".join(out)


def svg_stacked_bar(mix: dict[str, float], *, width: int = 340, title: str = "Mix") -> str:
    """One 100% horizontal stacked bar with a legend below."""
    items = _fold_mix(mix)
    total = sum(v for _, v in items)
    if not items or total <= 0:
        return _no_data(width, 60, title)
    rows = math.ceil(len(items) / 3)
    height = 30 + rows * 16
    out = [_svg_open(width, height, title)]
    x = 0.0
    for i, (name, v) in enumerate(items):
        w = width * v / total
        out.append(f'<rect x="{x:.1f}" y="2" width="{max(w - 2, 1):.1f}" height="16" rx="3" fill="{CATEGORICAL[i % 8]}"/>')
        x += w
    for i, (name, v) in enumerate(items):
        col, rr = i % 3, i // 3
        lx, ly = col * width / 3, 34 + rr * 16
        out.append(f'<rect x="{lx:.1f}" y="{ly - 8}" width="9" height="9" rx="2" fill="{CATEGORICAL[i % 8]}"/>')
        out.append(_txt(lx + 13, ly, f"{name[:30]} {fmt_pct(100 * v / total, signed=False)}", size=9))
    out.append("</svg>")
    return "".join(out)


def svg_gauge(score: float | None, *, width: int = 200, height: int = 118, color: str = NAVY,
              label: str = "signal score") -> str:
    """Semicircular 0-100 signal meter with a needle."""
    if score is None or not math.isfinite(score):
        return _no_data(width, height, "Signal meter", "no score")
    s = max(0.0, min(100.0, float(score)))
    cx, cy, r, rw = width / 2, height - 22, min(width / 2 - 10, height - 32), 14
    out = [_svg_open(width, height, f"Signal meter: {s:.0f} of 100")]
    segs = [(0, 20, CRIT), (20, 40, SERIOUS), (40, 60, WARN), (60, 80, "#8fd17a"), (80, 100, GOOD)]
    for a, b, c in segs:
        t0, t1 = math.pi * (1 - a / 100), math.pi * (1 - b / 100)
        gap = 0.012
        t0, t1 = t0 - gap, t1 + gap
        p = (f"M{cx + r * math.cos(t0):.2f},{cy - r * math.sin(t0):.2f} "
             f"A{r},{r} 0 0 1 {cx + r * math.cos(t1):.2f},{cy - r * math.sin(t1):.2f}")
        out.append(f'<path d="{p}" fill="none" stroke="{c}" stroke-width="{rw}"/>')
    t = math.pi * (1 - s / 100)
    nx, ny = cx + (r - rw - 4) * math.cos(t), cy - (r - rw - 4) * math.sin(t)
    out.append(f'<line x1="{cx}" y1="{cy}" x2="{nx:.2f}" y2="{ny:.2f}" stroke="{NAVY}" stroke-width="3" stroke-linecap="round"/>')
    out.append(f'<circle cx="{cx}" cy="{cy}" r="5" fill="{NAVY}"/>')
    out.append(_txt(cx - r, cy + 14, "0", anchor="middle", size=8.5, opacity=0.55))
    out.append(_txt(cx + r, cy + 14, "100", anchor="middle", size=8.5, opacity=0.55))
    out.append(_txt(cx, cy - 18, f"{s:.0f}", anchor="middle", size=24, weight="800", fill=color))
    out.append(_txt(cx, cy + 15, label, anchor="middle", size=8.5, opacity=0.65))
    out.append("</svg>")
    return "".join(out)


def svg_sparkline(series: Series | None, *, width: int = 120, height: int = 28, color: str = BLUE) -> str:
    pts = _valid_points(series) if series else []
    if len(pts) < 2:
        return ""
    vs = [v for _, v in pts]
    lo, hi = min(vs), max(vs)
    o0, o1 = pts[0][0].toordinal(), pts[-1][0].toordinal()
    coords = [(2 + (width - 6) * (d.toordinal() - o0) / max(o1 - o0, 1),
               height - 3 - (height - 6) * ((v - lo) / (hi - lo) if hi > lo else 0.5)) for d, v in pts]
    p = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(coords))
    lx, ly = coords[-1]
    return (f'<svg class="spark" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
            f'aria-hidden="true" xmlns="http://www.w3.org/2000/svg"><path d="{p}" fill="none" '
            f'stroke="{color}" stroke-width="1.6" stroke-linejoin="round"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.4" fill="{color}"/></svg>')


def svg_rounds_chart(rounds: list[dict], *, width: int = 688, height: int = 190,
                     title: str = "Funding rounds (indexed record)") -> str:
    """Rounds in date order as columns: amount bars, secondary sales hatched (liquidity).

    Columns are evenly spaced; the gap in months between rounds is written between them.
    Rounds with no recorded amount appear as a hollow marker on the baseline.
    """
    rs = sorted([r for r in rounds if parse_date(r.get("date", ""))], key=lambda r: parse_date(r["date"]))
    rs += [r for r in rounds if not parse_date(r.get("date", ""))]
    if not rs:
        return _no_data(width, 110, title)
    amts = [r["amount"] for r in rs if r.get("amount")]
    vmax = max(amts) if amts else 1.0
    ml, mr, mt, mb = 16, 16, 24, 40
    pw, ph = width - ml - mr, height - mt - mb
    col = pw / len(rs)
    bw = min(56, col * 0.42)
    base = mt + ph
    out = [_svg_open(width, height, title),
           '<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" '
           f'patternTransform="rotate(45)"><rect width="6" height="6" fill="#eef0f3"/>'
           f'<line x1="0" y1="0" x2="0" y2="6" stroke="{MUTED}" stroke-width="2"/></pattern></defs>',
           f'<line x1="{ml}" x2="{ml + pw}" y1="{base}" y2="{base}" stroke="{AXIS}"/>']
    prev = None
    for i, r in enumerate(rs):
        cx = ml + col * (i + 0.5)
        amt = r.get("amount")
        sec = bool(r.get("secondary"))
        if amt:
            h = max(ph * amt / vmax, 3)
            fill = "url(#hatch)" if sec else NAVY if i == len(rs) - 1 else BLUE
            out.append(f'<rect x="{cx - bw / 2:.1f}" y="{base - h:.1f}" width="{bw:.1f}" height="{h:.1f}" '
                       f'rx="4" fill="{fill}" stroke="{MUTED if sec else "none"}"/>')
            out.append(_txt(cx, base - h - 6, fmt_usd(amt), anchor="middle", size=11, weight="700"))
        else:
            out.append(f'<circle cx="{cx:.1f}" cy="{base - 6}" r="5" fill="#fff" stroke="{MUTED}" stroke-width="1.5"/>')
            out.append(_txt(cx, base - 16, "amount not recorded", anchor="middle", size=8.5, opacity=0.6))
        kind = r.get("type", "round") + (" · liquidity" if sec else "")
        out.append(_txt(cx, base + 14, kind, anchor="middle", size=10, weight="600"))
        sub = _date_label(r.get("date", "")) + (f" · {r['lead']}" if r.get("lead") else "")
        out.append(_txt(cx, base + 27, sub[:44], anchor="middle", size=8.5, opacity=0.65))
        d = parse_date(r.get("date", ""))
        if prev and d:
            gap = _months_between(prev, d)
            out.append(_txt(cx - col / 2, base - 4, f"+{gap} mo", anchor="middle", size=8.5, opacity=0.55))
        prev = d or prev
    out.append("</svg>")
    return "".join(out)


# ---- data helpers -----------------------------------------------------------------

def _metric(signals: Signals, *keys: str) -> Metric | None:
    for k in keys:
        m = signals.metrics.get(k)
        if m is not None and m.value is not None:
            return m
    return None


def _series(signals: Signals, *keys: str) -> Series | None:
    for k in keys:
        s = signals.series.get(k)
        if s is not None and _valid_points(s):
            return s
    return None


def _yoy(s: Series | None) -> float | None:
    """Last value vs the value nearest 12 months earlier (needs >= 10 months of history)."""
    pts = _valid_points(s) if s else []
    if len(pts) < 2:
        return None
    d1, v1 = pts[-1]
    target = d1.toordinal() - 365
    d0, v0 = min(pts, key=lambda p: abs(p[0].toordinal() - target))
    if (d1 - d0).days < 300 or v0 == 0:
        return None
    return 100.0 * (v1 - v0) / v0


def _change(s: Series | None) -> tuple[float, int] | None:
    """(% change first->last, months spanned)."""
    pts = _valid_points(s) if s else []
    if len(pts) < 2 or pts[0][1] == 0:
        return None
    return 100.0 * (pts[-1][1] - pts[0][1]) / pts[0][1], _months_between(pts[0][0], pts[-1][0])


_ROUND_EV = re.compile(r"^\s*(?P<type>[A-Za-z_ ]+?),\s*(?P<date>\d{4}(?:-\d{2}(?:-\d{2})?)?)"
                       r"(?:\s*\((?P<prec>\w+)\))?,\s*(?P<amt>\$[\d,\.]+|amount not recorded)"
                       r"(?:,\s*lead\s+(?P<lead>.*))?$")
_ROUND_LINE = re.compile(r"^Indexed (?P<type>[^:]+):\s*(?P<date>\d{4}(?:-\d{2}(?:-\d{2})?)?),\s*"
                         r"(?P<amt>\$[\d,\.]+|no amount recorded),\s*(?P<lead>[^(\[]*)")


def _usd(text: str) -> float | None:
    m = re.search(r"\$([\d,]+(?:\.\d+)?)", text or "")
    return float(m.group(1).replace(",", "")) if m else None


def _pretty_round(t: str) -> str:
    t = t.replace("_", " ").strip()
    if t.lower() in ("series unknown", "unknown"):
        return "Undisclosed round"
    return " ".join(w.upper() if len(w) == 1 else w.capitalize() for w in t.split())


def funding_rounds(case: CaseRecord) -> list[dict]:
    """Rounds from the graph evidence (funding.milestones), else the indexed financing lines."""
    out: list[dict] = []
    for ev in case.evidence:
        if ev.kind == "graph" and "milestones" in ev.locator:
            m = _ROUND_EV.match(ev.value or "")
            if m:
                lead = (m.group("lead") or "").strip()
                d = m.group("date")
                if m.group("prec") == "year":
                    d = d[:4]
                out.append({"type": _pretty_round(m.group("type")), "date": d,
                            "amount": _usd(m.group("amt")), "lead": "" if lead == "not recorded" else lead,
                            "secondary": "secondary" in m.group("type").lower(), "evidence": ev.id})
    if out:
        return out
    for ln in case.financing:
        if ln.get("kind") != "indexed_round":
            continue
        m = _ROUND_LINE.match(str(ln.get("line") or ""))
        if m:
            lead = m.group("lead").strip()
            out.append({"type": _pretty_round(m.group("type")), "date": m.group("date"),
                        "amount": _usd(m.group("amt")), "lead": "" if "not recorded" in lead else lead,
                        "secondary": "secondary" in m.group("type").lower(),
                        "evidence": ",".join(ln.get("evidence_ids") or [])})
    return out


def _indexed_total(case: CaseRecord) -> tuple[float | None, str]:
    for ev in case.evidence:
        if ev.kind == "graph" and "total_investment" in ev.locator:
            return _usd(ev.value), ev.id
    for ln in case.financing:
        if ln.get("kind") == "total":
            return _usd(str(ln.get("line"))), ",".join(ln.get("evidence_ids") or [])
    return None, ""


def _company(case: CaseRecord, signals: Signals) -> str:
    return signals.company or (case.g1 or {}).get("name") or case.input.domain


def run_labels(case: CaseRecord) -> list[str]:
    st = case.stats or {}
    return [case.run_mode, f"model: {st.get('model_source', 'unknown')}",
            f"profile {st.get('profile', 'FULL')}", f"run {case.run}", f"reviewed {case.reviewed}"]


def _cites(ids: Iterable[str]) -> str:
    chips = "".join(f'<span class="cite">{_e(i)}</span>' for i in ids if i)
    return f'<span class="cites">{chips}</span>' if chips else ""


def _clip(text: str, n: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _short_source(src: str) -> str:
    m = re.match(r"^https?://(?:www\.)?([^/]+)(/.*)?$", src or "")
    if not m:
        return src
    path = m.group(2) or ""
    return m.group(1) + (path if len(path) <= 18 else path[:17] + "…")


def _initials(name: str) -> str:
    parts = [p for p in re.split(r"\W+", name) if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


def _icon(level: str) -> str:
    c = LEVEL_META[level][1]
    shapes = {
        "critical": f'<polygon points="4,0 10,0 14,4 14,10 10,14 4,14 0,10 0,4" fill="{c}"/>'
                    '<rect x="6.2" y="3" width="1.6" height="5.2" fill="#fff"/><rect x="6.2" y="9.4" width="1.6" height="1.6" fill="#fff"/>',
        "red": f'<circle cx="7" cy="7" r="7" fill="{c}"/><rect x="6.2" y="3" width="1.6" height="5.2" fill="#fff"/>'
               '<rect x="6.2" y="9.4" width="1.6" height="1.6" fill="#fff"/>',
        "amber": f'<polygon points="7,0.5 13.8,13.3 0.2,13.3" fill="{WARN}"/><rect x="6.3" y="5" width="1.4" height="4.4" fill="#0b0b0b"/>'
                 '<rect x="6.3" y="10.3" width="1.4" height="1.4" fill="#0b0b0b"/>',
        "green": f'<circle cx="7" cy="7" r="7" fill="{GOOD}"/><path d="M3.6,7.2 L6,9.6 L10.6,4.6" fill="none" stroke="#fff" stroke-width="1.8"/>',
    }
    return f'<svg class="ico" viewBox="0 0 14 14" width="13" height="13" aria-hidden="true">{shapes[level]}</svg>'


# ---- page builders ----------------------------------------------------------------

def _page(n: int, title: str, company: str, body: str, kicker: str = "") -> str:
    return (f'<section class="page" id="p{n}"><div class="strip"><span>PROOFROOM · SIGNAL REPORT · '
            f'{_e(company)}</span><span>{n} / 7</span></div>'
            f'<h2 class="ph"><span class="pn">{n}</span>{_e(title)}</h2>'
            + (f'<p class="kicker">{_e(kicker)}</p>' if kicker else "") + body + "</section>")


def _tile(label: str, value: str, sub: str = "", tone: str = "neutral", spark: str = "", src: str = "") -> str:
    small = " t-text" if len(value) > 12 else ""
    return (f'<div class="tile t-{tone}{small}"><div class="t-label">{_e(label)}</div>'
            f'<div class="t-value">{_e(value)}</div><div class="t-sub">{sub}</div>{spark}'
            + (f'<div class="t-src">{_e(src)}</div>' if src else "") + "</div>")


def _delta(v: float | None, suffix: str) -> str:
    if v is None:
        return f'<span class="muted">{_e(suffix.strip() or "trend n/a")} n/a</span>'
    cls, arrow = ("up", "▲") if v > 0 else ("down", "▼") if v < 0 else ("flat", "■")
    return f'<span class="delta {cls}">{arrow} {_e(fmt_pct(v))}{_e(suffix)}</span>'


def _kpis(case: CaseRecord, s: Signals, flags: list[Flag]) -> str:
    tiles = []
    hc_s = _series(s, "headcount")
    hc_last = _valid_points(hc_s)[-1][1] if hc_s else None
    hc = s.headcount_total if s.headcount_total is not None else hc_last
    m = _metric(s, "headcount_yoy_pct", "headcount_growth_yoy_pct")
    yoy = m.value if m else _yoy(hc_s)
    tone = "neutral" if yoy is None else "good" if yoy > 0 else "bad" if yoy < 0 else "neutral"
    tiles.append(_tile("Headcount", fmt_compact(hc) if hc is not None else "n/a",
                       _delta(yoy, " YoY" + ("" if m else " (from series)" if yoy is not None else "")),
                       tone, svg_sparkline(hc_s, color=BLUE), (hc_s.source if hc_s else "")))
    wv = _series(s, "web_visitors", "web_traffic", "monthly_visitors")
    wm = _metric(s, "web_visitors_latest")
    wv_last = wm.value if wm else _valid_points(wv)[-1][1] if wv else None
    m = _metric(s, "web_visitors_yoy_pct", "web_visitors_qoq_pct", "web_visitors_change_pct")
    if m:
        wsub, wchg = _delta(m.value, f" {m.period}" if m.period else ""), m.value
    else:
        ch = _change(wv)
        wchg = ch[0] if ch else None
        wsub = _delta(wchg, f" over {ch[1]} mo" if ch else " trend")
    tiles.append(_tile("Web visitors / month", fmt_compact(wv_last) if wv_last is not None else "n/a", wsub,
                       "neutral" if wchg is None else "good" if wchg > 0 else "bad",
                       svg_sparkline(wv, color=AQUA), wv.source if wv else ""))
    rounds = funding_rounds(case)
    tm = _metric(s, "total_funding_usd", "total_investment_usd")
    total, tsrc = (tm.value, tm.source) if tm else _indexed_total(case)
    dated = [r for r in rounds if parse_date(r["date"])]
    last = max(dated, key=lambda r: parse_date(r["date"])) if dated else None
    lr = _metric(s, "last_round")
    lsub = (f'Last: {_e(last["type"])} · {_e(_date_label(last["date"]))}'
            + (f' · {_e(fmt_usd(last["amount"]))}' if last.get("amount") else "")) if last else \
        (f"Last: {_e(lr.display)}" if lr else "no indexed rounds")
    prim = _metric(s, "total_funding_primary_usd")
    if prim:
        lsub += f'<br><span class="muted">Primary only (excl. secondary): {_e(fmt_usd(prim.value))}</span>'
    tiles.append(_tile("Total indexed funding", fmt_usd(total) if total else "n/a", lsub, "neutral", "",
                       f"indexed record (Crunchbase-derived) {tsrc}".strip()))
    band = s.revenue_band_usd
    rm = _metric(s, "revenue_estimate_usd")
    rv = f"{fmt_usd(band[0])}–{fmt_usd(band[1])}" if band else fmt_usd(rm.value) if rm else "n/a"
    rb, rt = _metric(s, "revenue_band"), s.metrics.get("revenue_trend")
    rsub = '<span class="muted">Estimate band, not reported revenue</span>'
    if rt and rt.value is not None:
        rsub = _delta(rt.value, " band midpoint") + "<br>" + rsub
    rsrc = (rb or rm).source if (rb or rm) else ("Signals revenue band" if band else "")
    tiles.append(_tile("Revenue estimate", rv, rsub, "neutral",
                       svg_sparkline(_series(s, "revenue_high"), color=BLUE), rsrc))
    mm = _metric(s, "months_since_last_round")
    if mm:
        months, msrc = mm.value, mm.source
    else:
        rd = parse_date(case.reviewed)
        months = _months_between(parse_date(last["date"]), rd) if last and rd else None
        msrc = "calculated: reviewed date − last indexed round" if months is not None else ""
    mtone = "neutral" if months is None else "good" if months <= 12 else "warn" if months <= 24 else "bad"
    tiles.append(_tile("Months since last round", fmt_compact(months) if months is not None else "n/a",
                       f'<span class="muted">{_e(last["type"] + " · " + _date_label(last["date"])) if last else "no dated round"}</span>',
                       mtone, "", msrc))
    cnt = Counter(f.level for f in flags)
    chips = "".join(f'<span class="fc fc-{lv}">{_icon(lv)}<b>{cnt.get(lv, 0)}</b> {LEVEL_META[lv][2]}</span>'
                    for lv in ("critical", "red", "amber", "green"))
    ftone = "bad" if cnt.get("critical") or cnt.get("red") else "warn" if cnt.get("amber") else "good"
    tiles.append(f'<div class="tile t-{ftone}"><div class="t-label">Flags raised by the rules</div>'
                 f'<div class="t-value">{len(flags)}</div><div class="fcs">{chips}</div>'
                 f'<div class="t-src">fixed rules, identical for every company (page 7)</div></div>')
    return '<div class="tiles">' + "".join(tiles) + "</div>"


def _founder_line(case: CaseRecord, s: Signals) -> list[tuple[str, str]]:
    if s.founders:
        return [(f.name, f.title) for f in s.founders]
    return [(t.name, "; ".join(e.title for e in t.current_at_subject)) for t in case.team
            if t.role_join or t.listed_as_founder]


def _page1(case: CaseRecord, s: Signals, flags: list[Flag], rec: Recommendation, sample: bool) -> str:
    company = _company(case, s)
    logo = (f'<img class="logo" src="{_e(s.logo_data_uri)}" alt="">' if s.logo_data_uri.startswith("data:image/")
            else f'<div class="logo initials">{_e(_initials(company))}</div>')
    facts = [s.domain or case.input.domain]
    if s.year_founded:
        facts.append(f"Founded {s.year_founded}")
    if s.hq:
        facts.append(s.hq)
    if s.status:
        facts.append(s.status)
    cid = s.company_id or (case.g1 or {}).get("company_id")
    if cid:
        facts.append(f"Crustdata ID {cid}")
    labels = "".join(f'<span class="lab{" lab-mode" if i == 0 else ""}">{_e(x)}</span>'
                     for i, x in enumerate(run_labels(case)))
    if sample:
        labels += '<span class="lab lab-sample">SIGNALS: SAMPLE</span>'
    bg, fg = RATING_STYLE.get(rec.rating, (NAVY, "#fff"))
    founders = _founder_line(case, s)
    fl = "".join(f"<li><b>{_e(n)}</b>{(' · ' + _e(t)) if t else ''}</li>" for n, t in founders) or \
        "<li class='muted'>No founders found in the graph</li>"
    rationale = "".join(f"<li>{_e(r)}</li>" for r in rec.rationale[:5]) or "<li class='muted'>No rationale given</li>"
    pct = max(0.0, min(100.0, rec.sizing_pct if rec.sizing_pct > 1 else rec.sizing_pct * 100))
    sample_banner = ('<div class="sample-banner"><b>SAMPLE DATA.</b> Growth, market, founder-profile values, '
                     'the scores and the recommendation on these pages are placeholders for layout review, '
                     'not Crustdata output. Verified claims, evidence and funding come from a recorded '
                     f'{_e(case.run_mode)} run.</div>') if sample else ""
    body = f"""
<header class="band">
  {logo}
  <div class="band-main"><div class="kick">Investment snapshot · Team &amp; Financing verified</div>
    <h1>{_e(company)}</h1><div class="facts">{" · ".join(_e(f) for f in facts)}</div>
    <p class="desc">{_e(_clip(s.description, 230)) if s.description else ''}</p></div>
  <div class="band-side"><div class="kick">Run labels</div><div class="labs">{labels}</div></div>
</header>
{sample_banner}
<div class="hero">
  <div class="card rating">
    <div class="r-left"><div class="kick dark">Signal rating</div>
      <div class="badge" style="background:{bg};color:{fg}">{_e(rec.rating)}</div>
      <div class="chips"><span class="chip conf-{_e(rec.confidence)}">Confidence: {_e(rec.confidence)}</span>
      {f'<span class="chip">Horizon: {_e(rec.horizon)}</span>' if rec.horizon else ''}</div></div>
    <div class="r-gauge">{svg_gauge(rec.score, color=RATING_INK.get(rec.rating, NAVY))}</div>
  </div>
  <div class="card alloc"><div class="kick dark">Suggested allocation</div>
    <div class="alloc-line"><span class="big">{_e(fmt_usd(rec.suggested_usd))}</span>
    <span class="of">of your {_e(fmt_usd(rec.check_size_usd))} standard check ({_e(_trim(pct))}%)</span></div>
    <div class="meter"><div class="meter-fill" style="width:{pct:.1f}%;background:{bg}"></div></div>
    <div class="meter-ax"><span>$0</span><span>{_e(fmt_usd(rec.check_size_usd))}</span></div>
  </div>
</div>
<div class="headline"><div class="kick dark">Headline finding</div><p>{_e(rec.headline)}</p></div>
{_kpis(case, s, flags)}
<div class="two">
  <div><h3>Why, in brief</h3><ul class="bul">{rationale}</ul></div>
  <div><h3>Founders</h3><ul class="plain">{fl}</ul></div>
</div>
<p class="disc"><b>{_e(rec.disclaimer or DISCLAIMER)}</b> Every figure carries its source; verified claims cite
evidence IDs (E = source passage, G = Crustdata graph value) listed on page 7. Crustdata funding data is an
indexed record (Crunchbase-derived), not an independent source.</p>"""
    return (f'<section class="page" id="p1"><div class="strip"><span>PROOFROOM · SIGNAL REPORT</span>'
            f'<span>1 / 7</span></div>{body}</section>')


def _flag_block(level: str, items: list[Flag], empty: str) -> str:
    head, color, _ = LEVEL_META[level]
    lis = "".join(
        f'<li>{_icon(level)}<div><b>{_e(f.title)}</b> <span class="detail">{_e(f.detail)}</span> '
        f'{_cites(f.evidence)} <code>{_e(f.rule)}</code></div></li>' for f in items)
    return (f'<div class="flags fl-{level}"><h3 style="color:{color}">{_e(head)} '
            f'<span class="count">{len(items)}</span></h3>'
            + (f'<ul class="fl">{lis}</ul>' if items else f'<p class="muted none">{_e(empty)}</p>') + "</div>")


def _score_color(v: float) -> str:
    return GOOD if v >= 70 else "#8fd17a" if v >= 55 else WARN if v >= 40 else CRIT


def _page2(company: str, flags: list[Flag], pillars: list[Pillar], rec: Recommendation) -> str:
    rows = []
    for p in pillars:
        rs = "".join(f"<li>{_e(r)}</li>" for r in p.reasons) or "<li class='muted'>no reasons recorded</li>"
        sc = max(0.0, min(100.0, p.score))
        rows.append(f'<tr><td class="pname"><b>{_e(p.name)}</b><div class="muted small">weight '
                    f'{_e(_trim(p.weight * 100))}%</div></td><td class="pbar"><div class="bar">'
                    f'<div style="width:{sc:.1f}%;background:{_score_color(sc)}"></div></div>'
                    f'<span class="pscore">{sc:.0f}</span></td><td><ul class="tight">{rs}</ul></td></tr>')
    total_w = sum(p.weight for p in pillars)
    table = (f'<table class="pillars"><thead><tr><th>Pillar</th><th>Score (0–100)</th><th>Reasons</th></tr></thead>'
             f'<tbody>{"".join(rows) or "<tr><td colspan=3 class=muted>No pillar scores</td></tr>"}</tbody>'
             f'<tfoot><tr><td><b>Weighted score</b><div class="muted small">weights sum {_e(_trim(total_w * 100))}%</div></td>'
             f'<td class="pbar"><div class="bar"><div style="width:{max(0, min(100, rec.score)):.1f}%;background:{NAVY}"></div></div>'
             f'<span class="pscore">{rec.score:.0f}</span></td><td>Rating <b>{_e(rec.rating)}</b> · confidence '
             f'{_e(rec.confidence)}</td></tr></tfoot></table>')
    by = {lv: [f for f in flags if f.level == lv] for lv in LEVEL_META}
    trig = "".join(f"<li>{_e(t)}</li>" for t in rec.revisit_triggers) or "<li class='muted'>None listed</li>"
    body = (table
            + '<div class="two">'
            + _flag_block("critical", by["critical"], "No verification or integrity problems found by the rules.")
            + _flag_block("red", by["red"], "No business-risk red flags fired.") + "</div>"
            + '<div class="two">' + _flag_block("amber", by["amber"], "No open points.")
            + _flag_block("green", by["green"], "No green flags fired.") + "</div>"
            + f'<div class="callout"><h3>What would change the rating</h3><ul class="bul">{trig}</ul></div>')
    return _page(2, "Why this rating", company, body,
                 "Five pillars, fixed weights, fixed rules. Critical flags are about whether the facts hold; "
                 "red flags are about the business.")


def _chart_card(title: str, svg: str, note: str = "") -> str:
    return (f'<figure class="cc"><figcaption>{_e(title)}</figcaption>{svg}'
            + (f'<div class="src">{_e(note)}</div>' if note else "") + "</figure>")


def _traction_bullets(s: Signals) -> list[str]:
    out = []
    hc = _series(s, "headcount")
    if hc:
        pts = _valid_points(hc)
        y = _yoy(hc)
        txt = (f"Headcount moved from {fmt_compact(pts[0][1])} ({pts[0][0]:%b %Y}) to "
               f"{fmt_compact(pts[-1][1])} ({pts[-1][0]:%b %Y})")
        out.append(txt + (f", {fmt_pct(y)} year on year." if y is not None else "."))
    wv = _series(s, "web_visitors", "web_traffic", "monthly_visitors")
    if wv:
        pts = _valid_points(wv)
        peak = max(pts, key=lambda p: p[1])
        out.append(f"Web visitors: latest {fmt_compact(pts[-1][1])}/month ({pts[-1][0]:%b %Y}); "
                   f"peak {fmt_compact(peak[1])} in {peak[0]:%b %Y}.")
    fo = _series(s, "followers", "linkedin_followers")
    ch = _change(fo)
    fy = _metric(s, "followers_yoy_pct")
    if fo and fy:
        out.append(f"Followers: {fmt_compact(_valid_points(fo)[-1][1])}, {fmt_pct(fy.value)} over 12 months.")
    elif fo and ch:
        out.append(f"Followers changed {fmt_pct(ch[0])} over {ch[1]} months to "
                   f"{fmt_compact(_valid_points(fo)[-1][1])}.")
    if s.revenue_band_usd:
        out.append(f"Revenue estimate band: {fmt_usd(s.revenue_band_usd[0])}–{fmt_usd(s.revenue_band_usd[1])} "
                   "(an estimate range, not reported revenue).")
    mix = _fold_mix(s.role_mix)
    if mix:
        tot = sum(v for _, v in mix)
        out.append(f"Largest function: {mix[0][0]} at {fmt_pct(100 * mix[0][1] / tot, signed=False)} of staff.")
    if s.hiring_openings is not None:
        out.append(f"Open roles listed: {s.hiring_openings}.")
    return out or ["No growth or traction series were available for this company."]


def _page3(company: str, s: Signals) -> str:
    hc = _series(s, "headcount")
    y = _metric(s, "headcount_yoy_pct")
    yv = y.value if y else _yoy(hc)
    ann = f"{fmt_pct(yv)} YoY" if yv is not None else ""
    wv = _series(s, "web_visitors", "web_traffic", "monthly_visitors")
    fo = _series(s, "followers", "linkedin_followers")
    lo, hi = s.series.get("revenue_low"), s.series.get("revenue_high")
    openings = _series(s, "job_openings", "hiring_openings", "open_roles")
    if openings:
        hire = svg_line_chart([openings], title="Open roles over time", colors=[ORANGE])
    elif s.hiring_openings is not None:
        hire = svg_bar_chart([("Open roles now", float(s.hiring_openings))], unit="", title="Open roles",
                             color=ORANGE)
    else:
        hire = _no_data(340, 150, "Open roles")
    src = lambda x: x.source if x else ""
    charts = [
        _chart_card("Headcount", svg_line_chart([hc] if hc else [], title="Headcount", annotation=ann), src(hc)),
        _chart_card("Web visitors per month", svg_line_chart([wv] if wv else [], title="Web visitors",
                                                             colors=[AQUA]), src(wv)),
        _chart_card("Followers", svg_line_chart([fo] if fo else [], title="Followers", colors=[VIOLET]), src(fo)),
        _chart_card("Revenue estimate band (USD)", svg_band_chart(lo, hi), src(hi) or src(lo)),
        _chart_card("Role mix (% of staff)", svg_donut(s.role_mix), "Signals role_mix"),
        _chart_card("Hiring", hire, src(openings)),
    ]
    region = (_chart_card("Region mix (% of staff)", svg_stacked_bar(s.region_mix, width=688, title="Region mix"))
              if s.region_mix else "")
    bullets = "".join(f"<li>{_e(b)}</li>" for b in _traction_bullets(s))
    body = (f'<div class="callout insights"><h3>What the charts say</h3><ul class="bul">{bullets}</ul></div>'
            f'<div class="grid2">{"".join(charts)}</div>{region}')
    return _page(3, "Growth and traction", company, body,
                 "Indexed signals over time. Values are as reported by the data provider; derived figures are "
                 "plain calculations over the plotted points.")


def _mark(basis: str) -> str:
    return {"id": '<span class="mk ok" title="ID join">✔</span>',
            "name_match": '<span class="mk warn" title="name match">≈</span>'}.get(
        basis, '<span class="mk muted" title="not joined">?</span>')


def _role_basis(t: TeamRow) -> str:
    return "id" if t.role_join else "name_match" if (t.current_at_subject or t.listed_as_founder) else "none"


def _page4(company: str, case: CaseRecord, s: Signals) -> str:
    frows = []
    for f in s.founders:
        notable = set(f.big_tech_or_scaleup)
        emps = ", ".join(f'<span class="pill">{_e(x)}</span>' if x in notable else _e(x)
                         for x in f.prior_employers) or '<span class="muted">none indexed</span>'
        extra = [x for x in notable if x not in f.prior_employers]
        emps += "".join(f' <span class="pill">{_e(x)}</span>' for x in extra)
        frows.append(f"<tr><td><b>{_e(f.name)}</b><div class='muted small'>{_e(f.title)}</div></td>"
                     f"<td>{_e(_date_label(f.since)) if f.since else '—'}</td><td>{emps}</td>"
                     f"<td class='c'>{'<span class=\"mk ok\">✔</span>' if f.prior_founder else '—'}</td>"
                     f"<td>{_e('; '.join(f.education)) or '—'}</td>"
                     f"<td class='num'>{_e(_trim(f.years_experience)) if f.years_experience is not None else '—'}</td></tr>")
    founders = ("<table class='data'><thead><tr><th>Founder</th><th>Since</th><th>Prior employers "
                "(notable highlighted)</th><th class='c'>Prior founder</th><th>Education</th>"
                "<th class='num'>Yrs exp.</th></tr></thead><tbody>"
                + ("".join(frows) or "<tr><td colspan=6 class='muted'>No founder profiles in Signals</td></tr>")
                + "</tbody></table>")
    trows = []
    for t in case.team:
        role = "; ".join(f"{e.title} since {e.start or '?'}" for e in t.current_at_subject) or "no current entry"
        prior = ", ".join(f"{_e(j.employer_name)} {_mark(j.basis if j.basis != 'none' or not j.joined else 'id')}"
                          for j in t.prior_joins) or '<span class="muted">none named by sources</span>'
        trows.append(f"<tr><td><b>{_e(t.name)}</b><div class='muted small'>person {_e(str(t.person_id or '—'))}</div></td>"
                     f"<td>{_mark(_role_basis(t))} {_e(role)}</td><td>{prior}</td><td class='muted small'>{_e(t.source)}</td></tr>")
    team = ("<table class='data'><thead><tr><th>Person</th><th>Current role at the company</th>"
            "<th>Prior employers named by sources</th><th>Source</th></tr></thead><tbody>"
            + ("".join(trows) or "<tr><td colspan=4 class='muted'>No team rows</td></tr>") + "</tbody></table>")
    ev = [e.id for e in case.evidence if e.kind == "graph" and "employment_details" in e.locator]
    body = (f"<h3>Founder profiles</h3>{founders}"
            f"<h3>Verified team (Crustdata identity graph) {_cites(ev)}</h3>{team}"
            '<p class="legend"><span class="mk ok">✔</span> ID join: the employer ID on the person\'s record '
            'equals the company ID · <span class="mk warn">≈</span> name match only · '
            '<span class="mk muted">?</span> not joined</p>')
    return _page(4, "Team", company, body,
                 "Who runs the company, and whether the graph confirms they are where the sources say.")


def _page5(company: str, s: Signals) -> str:
    mk = s.market
    crowd_tone = {"low": "good", "medium": "warn", "high": "bad"}.get(mk.crowding, "neutral")
    tiles = ('<div class="tiles t4">'
             + _tile("Category", mk.category or "n/a", " ".join(f'<span class="pill">{_e(c)}</span>'
                                                               for c in mk.categories[:5]))
             + _tile("NAICS", mk.naics or "n/a")
             + _tile("Crowding", mk.crowding.upper(), f'<span class="muted">{_e(str(mk.peer_count)) if mk.peer_count is not None else "n/a"} '
                     "companies in category</span>", crowd_tone)
             + _tile("Funded in 24 months", fmt_compact(mk.funded_peers_24m) if mk.funded_peers_24m is not None else "n/a",
                     '<span class="muted">peers that raised recently</span>')
             + "</div>")
    rows = "".join(
        f"<tr><td><b>{_e(p.name)}</b><div class='muted small'>{_e(p.domain)}</div></td>"
        f"<td class='num'>{_e(str(p.year_founded or '—'))}</td><td class='num'>{_e(fmt_compact(p.headcount)) if p.headcount is not None else '—'}</td>"
        f"<td class='num'>{_e(fmt_pct(p.headcount_yoy_pct)) if p.headcount_yoy_pct is not None else '—'}</td>"
        f"<td class='num'>{_e(fmt_usd(p.total_funding_usd)) if p.total_funding_usd else '—'}</td>"
        f"<td>{_e(_pretty_round(p.last_round_type)) if p.last_round_type else '—'}"
        f"<span class='muted small'> {_e(_date_label(p.last_round_date)) if p.last_round_date else ''}</span></td></tr>"
        for p in mk.peers[:8])
    hc_yoy = _metric(s, "headcount_yoy_pct")
    own = hc_yoy.value if hc_yoy else _yoy(_series(s, "headcount"))
    items = [(company, own)] + [(p.name, p.headcount_yoy_pct) for p in mk.peers[:8]]
    ref = ("peer median", mk.median_peer_headcount_yoy_pct) if mk.median_peer_headcount_yoy_pct is not None else None
    chart = svg_bar_chart(items, width=688, title="Headcount growth YoY vs peers", highlight=company, reference=ref)
    seo = (f'<p class="foot-note">SEO overlap domains (noisy: keyword overlap, not verified competitors): '
           f'{_e(", ".join(mk.seo_competitor_domains[:12]))}</p>') if mk.seo_competitor_domains else ""
    body = (tiles
            + "<h3>Peer benchmark</h3><table class='data'><thead><tr><th>Company</th><th class='num'>Founded</th>"
              "<th class='num'>Headcount</th><th class='num'>Headcount YoY</th><th class='num'>Total funding</th>"
              "<th>Last round</th></tr></thead><tbody>"
            + (rows or "<tr><td colspan=6 class='muted'>No peers found</td></tr>") + "</tbody></table>"
            + _chart_card("Headcount growth YoY: company vs peers", chart, mk.source)
            + seo)
    return _page(5, "Market and competition", company, body,
                 "How crowded the category is, and how the company's growth compares with funded peers.")


def _page6(company: str, case: CaseRecord, s: Signals) -> str:
    rounds = funding_rounds(case)
    lines = "".join(f"<li>{_e(str(ln.get('line')))}</li>" for ln in case.financing
                    if ln.get("line") and ln.get("kind") in ("indexed_round", "total"))
    claims = {c.id: c for c in case.claims}
    frows = []
    for f in case.findings:
        lab, cls = DISPOSITION.get(f.disposition, (f.disposition, "muted"))
        basis = ", ".join(BASIS_LABEL.get(b, b) for b in f.basis)
        q = " · qualified" if f.qualified else ""
        corr = f" · correction: {f.correction_reason}" if f.correction_reason else ""
        fam = claims[f.claim_id].family if f.claim_id in claims else ""
        frows.append(f'<li><div class="fhead"><span class="cid">{_e(f.claim_id)}</span>'
                     f'<span class="st st-{cls}">{_e(lab)}</span><span class="muted small">{_e(fam)} · basis: '
                     f'{_e(basis)}{_e(q)}{_e(corr)}{(" · as of " + _e(f.as_of)) if f.as_of else ""}</span></div>'
                     f'<p>{_e(f.sentence)} {_cites(f.evidence_ids)}</p>'
                     + (f'<p class="muted small">Limitation: {_e(f.limitation)}</p>' if f.limitation else "")
                     + "</li>")
    withheld = [x for x in case.limitations if "suppressed" in x.lower() or "withheld" in x.lower()]
    frows += [f'<li><div class="fhead"><span class="st st-bad">Withheld</span></div><p class="muted">{_e(w)}</p></li>'
              for w in withheld]
    qs = "".join(f"<li>{_e(q)}</li>" for q in case.questions) or "<li class='muted'>No open questions</li>"
    news = [n for n in s.news if n.kind in ("funding", "legal_risk")][:5]
    newsh = ("<h3>Indexed news</h3><ul class='plain small'>" + "".join(
        f"<li><span class='st st-{'bad' if n.kind == 'legal_risk' else 'muted'}'>{_e(n.kind.replace('_', ' '))}</span> "
        f"{_e(n.title)} <span class='muted'>· {_e(n.publisher)} {_e(n.date)}</span></li>" for n in news)
             + "</ul>") if news else ""
    body = (_chart_card("Funding rounds by date (indexed record, Crunchbase-derived)", svg_rounds_chart(rounds),
                        "Hatched bars are secondary sales: liquidity for existing holders, not capital in the "
                        "company. Year-only dates are shown at year precision.")
            + f"<ul class='plain small fin'>{lines}</ul>"
            + f"<h3>Verified claims</h3><ul class='findings'>{''.join(frows) or '<li class=muted>No findings</li>'}</ul>"
            + f'<div class="callout"><h3>Questions for the founders</h3><ul class="bul">{qs}</ul></div>' + newsh)
    return _page(6, "Financing and verified claims", company, body,
                 "Each sentence below passed the code check (every number against its cited evidence) and the "
                 "entailment check.")


def _rules_rows(flags: list[Flag], rules: dict | None) -> str:
    desc: dict[str, tuple[str, str]] = {}
    for k, v in (rules or {}).items():
        if isinstance(v, (tuple, list)) and len(v) >= 2:
            desc[k] = (str(v[0]), str(v[1]))
        else:
            desc[k] = ("", str(v))
    fired = Counter(f.rule for f in flags)
    for f in flags:
        lv, d = desc.get(f.rule, ("", ""))
        desc[f.rule] = (lv or f.level, d or f.title)
    order = {"critical": 0, "red": 1, "amber": 2, "green": 3}
    rows = sorted(desc.items(), key=lambda kv: (order.get(kv[1][0], 9), kv[0]))
    return "".join(
        f"<li class='{'fired' if fired.get(r) else ''}'><span class='lv lv-{_e(lv)}'>"
        f"{_e(LEVEL_META.get(lv, (None, None, lv or '—'))[2])}</span> <code>{_e(r)}</code> {_e(d)}"
        f"{(' <b>×' + str(fired[r]) + '</b>') if fired.get(r) else ''}</li>" for r, (lv, d) in rows)


def _page7(company: str, case: CaseRecord, s: Signals, flags: list[Flag], pillars: list[Pillar],
           rec: Recommendation, rules: dict | None, sample: bool) -> str:
    fby = {f.claim_id: f for f in case.findings}
    withheld = {m.group(1) for x in case.limitations for m in [re.match(r"^(C\d+):", x.strip())] if m}
    crow = []
    for c in case.claims:
        if c.id in fby:
            st = DISPOSITION.get(fby[c.id].disposition, (fby[c.id].disposition, "muted"))
            status = f'<span class="st st-{st[1]}">{_e(st[0])}</span>'
        elif c.id in withheld:
            status = '<span class="st st-bad">Withheld</span>'
        elif not c.selected:
            status = f'<span class="muted small">not checked: {_e(c.exclusion_reason)}</span>'
        else:
            status = '<span class="muted small">no sentence emitted</span>'
        crow.append(f"<tr><td class='nw'><b>{_e(c.id)}</b> <span class='muted'>{_e(c.doc_id)} · {_e(c.family)}</span></td>"
                    f"<td>“{_e(_clip(c.quote, 150))}” <span class='muted'>· {_e(c.predicate.replace('_', ' '))}</span></td>"
                    f"<td>{status}</td></tr>")
    eps = Counter((a.endpoint, a.mode, a.status) for a in case.attempts if a.stage == "crustdata")
    ep_rows = "".join(f"<tr><td><code>{_e(ep)}</code></td><td>{_e(m)}</td><td>{_e(st)}</td><td class='num'>{n}</td></tr>"
                      for (ep, m, st), n in sorted(eps.items()))
    sig_src = sorted({x for x in ([se.source for se in s.series.values()] + [m.source for m in s.metrics.values()]
                                  + [s.market.source] + [f.source for f in s.founders]) if x})
    docs = "".join(f"<tr><td><b>{_e(d.id)}</b></td><td class='url'>{_e(d.source)}</td><td>{_e(d.origin or 'unknown')}</td>"
                   f"<td>{_e(d.published or '—')}</td><td>{_e(d.updated or '—')}</td><td>{_e(d.retrieved[:10] or '—')}</td></tr>"
                   for d in case.documents)
    weights = "".join(f"<span class='pill'>{_e(p.name)} {_e(_trim(p.weight * 100))}%</span>" for p in pillars)
    ev = "".join(f"<tr><td><b>{_e(e.id)}</b></td><td class='evsrc'>{_e(_short_source(e.source))}"
                 f"<br><code>{_e(e.locator)}</code></td>"
                 f"<td>{_e(_clip(e.value, 170))}{(' <span class=muted>· ' + _e(e.origin) + '</span>') if e.origin else ''}</td></tr>"
                 for e in case.evidence)
    gaps = [f"No data for field group: {k}" for k, v in s.coverage.items() if not v]
    lims = "".join(f"<li>{_e(x)}</li>" for x in [*case.limitations, *s.limitations, *gaps])
    if sample:
        lims += "<li><b>SAMPLE:</b> Signals, pillars, flags derived from Signals, and the recommendation in this " \
                "document are placeholders for layout review.</li>"
    st = case.stats or {}
    body = f"""
<div class="two">
<div><h3>Pipeline</h3><ol class="tight small">
<li>Identity: the domain resolves to one Crustdata company ID (a tie abstains).</li>
<li>Sources: the funding announcement and coverage are fetched; text addressed to AI agents is data, ignored.</li>
<li>Claims C1, C2…: material Team &amp; Financing statements quoted verbatim from those sources.</li>
<li>Graph: founders' roles and prior employers joined by employer ID; rounds matched to the indexed record.</li>
<li>Gate: code checks every amount, percentage, year and date against cited evidence; an entailment check confirms each sentence. Failures are withheld, never repaired.</li>
<li>Signals and scoring: indexed growth, market and founder data feed five pillars and fixed flag rules.</li>
</ol></div>
<div><h3>Scoring model</h3><p class="small">Pillar weights: {weights or '<span class="muted">n/a</span>'}</p>
<p class="small">Weighted score {rec.score:.0f}/100 → rating <b>{_e(rec.rating)}</b>; confidence {_e(rec.confidence)}.
Suggested allocation = standard check × sizing ({_e(fmt_usd(rec.check_size_usd))} × {_e(_trim(rec.sizing_pct if rec.sizing_pct > 1 else rec.sizing_pct * 100))}% = {_e(fmt_usd(rec.suggested_usd))}).</p>
<p class="small muted">This run: {len(case.documents)} documents, {len(case.evidence)} evidence rows, {len(case.claims)} claims,
{st.get('sentences_emitted', len(case.findings))} sentences emitted, {st.get('sentences_suppressed', 0)} withheld,
Crustdata credits {_e(str(st.get('crustdata_credits', 0)))} + signals {_e(_trim(s.credits_used))}.</p></div>
</div>
<p class="disc"><b>{_e(rec.disclaimer or DISCLAIMER)}</b></p>
<h3>Claims extracted</h3><table class="data small"><thead><tr><th>ID</th><th>Quote</th><th>Status</th></tr></thead>
<tbody>{''.join(crow) or "<tr><td colspan=3 class='muted'>No claims</td></tr>"}</tbody></table>
<h3>Flag rules <span class="muted small">(identical for every company; ×n = fired in this run)</span></h3>
<ul class="rules">{_rules_rows(flags, rules) or "<li class='muted'>No rules</li>"}</ul>
<h3>Data sources</h3><table class="data small"><thead><tr><th>Crustdata endpoint</th><th>Mode</th><th>Status</th><th class="num">Calls</th></tr></thead>
<tbody>{ep_rows or "<tr><td colspan=4 class='muted'>No Crustdata calls recorded</td></tr>"}</tbody></table>
{('<p class="small"><b>Signal fields:</b> ' + ', '.join(f'<code>{_e(x)}</code>' for x in sig_src) + '</p>') if sig_src else ''}
<table class="data small"><thead><tr><th>Doc</th><th>Web Fetch source</th><th>Origin</th><th>Published</th><th>Updated</th><th>Retrieved</th></tr></thead>
<tbody>{docs or "<tr><td colspan=6 class='muted'>No source documents</td></tr>"}</tbody></table>
<h3>Evidence</h3><table class="data small ev"><thead><tr><th>ID</th><th>Source · locator</th><th>Value</th></tr></thead>
<tbody>{ev or "<tr><td colspan=3 class='muted'>No evidence</td></tr>"}</tbody></table>
<h3>Limitations</h3><ul class="tight small">{lims or "<li class='muted'>None recorded</li>"}</ul>"""
    return _page(7, "Methodology", company, body, "How every number and status in this report was produced.")


# ---- stylesheet ------------------------------------------------------------------

CSS = """
@page { size: A4; margin: 14mm; }
* { box-sizing: border-box; }
:root { --navy:#0f1f3d; --navy2:#1c3566; --ink:#0b0b0b; --ink2:#52514e; --muted:#6b6a65; --line:#e1e0d9;
  --axis:#c3c2b7; --plane:#f6f6f3; --blue:#2a78d6; --good:#0ca30c; --goodtext:#006300; --warn:#fab219;
  --warntext:#8a5a00; --crit:#d03b3b; --critdark:#8f1d1d; color-scheme: light; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin:0; background:#e8e8e4; color:var(--ink);
  font: 9.4pt/1.42 Inter, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
.page { width:182mm; margin:16px auto; background:#fff; padding:0; position:relative; }
@media screen { .page { padding:12mm; width:calc(182mm + 24mm); box-shadow:0 1px 6px rgba(0,0,0,.15); } }
@media print { body { background:#fff; } .page { margin:0; box-shadow:none; } .page + .page { break-before: page; } }
.strip { display:flex; justify-content:space-between; font-size:7pt; letter-spacing:.08em; color:var(--muted);
  border-bottom:1px solid var(--line); padding-bottom:3px; margin-bottom:8px; }
h1 { font-size:23pt; line-height:1.05; margin:0; letter-spacing:-.01em; }
h2.ph { font-size:16pt; margin:2px 0 2px; color:var(--navy); display:flex; align-items:center; gap:8px; }
.pn { display:inline-flex; width:22px; height:22px; border-radius:5px; background:var(--navy); color:#fff;
  font-size:10pt; align-items:center; justify-content:center; }
h3 { font-size:10.5pt; margin:12px 0 5px; color:var(--navy); }
.kicker { color:var(--ink2); margin:0 0 8px; }
.kick { font-size:7pt; text-transform:uppercase; letter-spacing:.12em; color:#a9bbdb; font-weight:600; }
.kick.dark { color:var(--muted); }
.muted { color:var(--muted); } .small { font-size:8pt; } .none { margin:2px 0 6px; }
.num { text-align:right; font-variant-numeric: tabular-nums; white-space:nowrap; } .c { text-align:center; }
code { font-family:"JetBrains Mono", ui-monospace, Menlo, Consolas, monospace; font-size:7.4pt; color:var(--muted); }
.band { background:linear-gradient(120deg, var(--navy) 0%, var(--navy2) 100%); color:#fff; border-radius:8px;
  padding:14px 16px; display:grid; grid-template-columns:58px 1fr 172px; gap:14px; align-items:start; }
.logo { width:58px; height:58px; border-radius:12px; background:#fff; object-fit:contain; }
.logo.initials { display:flex; align-items:center; justify-content:center; font-weight:800; font-size:20pt;
  color:var(--navy); }
.facts { color:#d5def0; margin-top:4px; font-size:8.6pt; }
.desc { margin:6px 0 0; color:#eef2fa; font-size:9pt; }
.band-side .labs { display:flex; flex-wrap:wrap; gap:4px; margin-top:5px; }
.lab { font-size:7pt; padding:2px 6px; border-radius:4px; background:rgba(255,255,255,.12); color:#e6ecf7;
  border:1px solid rgba(255,255,255,.18); }
.lab-mode { background:#fff; color:var(--navy); font-weight:800; }
.lab-sample { background:var(--crit); border-color:var(--crit); color:#fff; font-weight:800; }
.sample-banner { margin:8px 0 0; padding:6px 10px; border:1.5px dashed var(--crit); border-radius:6px;
  color:var(--critdark); background:#fdf1f1; font-size:8pt; }
.hero { display:grid; grid-template-columns:minmax(0, 1.35fr) minmax(0, 1fr); gap:10px; margin-top:10px; }
.card { border:1px solid var(--line); border-radius:8px; padding:10px 12px; background:#fff; }
.rating { display:grid; grid-template-columns:minmax(0, 1fr) 150px; align-items:center; gap:6px; }
.badge { display:inline-block; font-size:19pt; font-weight:900; letter-spacing:.03em; padding:4px 12px;
  border-radius:7px; margin:5px 0 7px; }
.chips { display:flex; gap:5px; flex-wrap:wrap; }
.chip { font-size:7.6pt; padding:2px 7px; border-radius:999px; background:var(--plane); border:1px solid var(--line); }
.conf-high { background:#e6f5e6; border-color:#b7e0b7; } .conf-low { background:#fdecec; border-color:#f3c4c4; }
.conf-medium { background:#fff6de; border-color:#f4dc9c; }
.alloc .big { font-size:28pt; font-weight:900; color:var(--navy); letter-spacing:-.02em; line-height:1.05; }
.alloc-line { margin:6px 0 8px; } .alloc .of { display:block; font-size:10pt; color:var(--ink2); margin-top:2px; }
.meter { height:10px; border-radius:6px; background:var(--plane); border:1px solid var(--line); overflow:hidden; }
.meter-fill { height:100%; border-radius:6px; }
.meter-ax { display:flex; justify-content:space-between; font-size:7pt; color:var(--muted); margin-top:2px; }
.headline { margin-top:10px; border-left:4px solid var(--navy); padding:4px 12px; background:var(--plane); border-radius:0 6px 6px 0; }
.headline p { margin:2px 0 3px; font-size:12pt; font-weight:700; line-height:1.3; color:var(--navy); }
.tiles { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:8px; margin-top:10px; }
.tiles.t4 { grid-template-columns:repeat(4, minmax(0, 1fr)); }
.tile, .two > *, .grid2 > *, .hero > *, .band > * { min-width:0; }
.tile { border-radius:8px; padding:8px 10px 7px; position:relative; border:1px solid transparent; min-height:84px;
  break-inside:avoid; }
.t-neutral { background:#eef3fb; border-color:#d6e2f4; } .t-good { background:#eaf6ea; border-color:#c7e6c7; }
.t-bad { background:#fbeceb; border-color:#f1cccc; } .t-warn { background:#fff6df; border-color:#f3e0a8; }
.t-label { font-size:7.4pt; text-transform:uppercase; letter-spacing:.07em; color:var(--ink2); font-weight:600; }
.t-value { font-size:19pt; font-weight:800; line-height:1.15; color:var(--navy); margin-top:2px; }
.t-good .t-value { color:var(--goodtext); } .t-bad .t-value { color:#a52020; } .t-warn .t-value { color:var(--warntext); }
.t-sub { font-size:8pt; margin-top:1px; }
.t-src { font-size:6.6pt; color:var(--muted); margin-top:3px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.spark { position:absolute; right:8px; top:10px; width:76px; height:24px; }
.delta { font-weight:700; } .delta.up { color:var(--goodtext); } .delta.down { color:#a52020; } .delta.flat { color:var(--muted); }
.fcs { display:flex; flex-wrap:wrap; gap:4px 8px; margin-top:3px; font-size:7.8pt; }
.fc { display:inline-flex; align-items:center; gap:3px; } .ico { flex:none; vertical-align:-2px; }
.two { display:grid; grid-template-columns:minmax(0, 1fr) minmax(0, 1fr); gap:14px; }
.bul { margin:0; padding-left:16px; } .bul li { margin:2px 0; }
.plain { list-style:none; margin:0; padding:0; } .plain li { margin:2px 0; }
.tight { margin:0; padding-left:15px; } .tight li { margin:1px 0; }
.disc { font-size:7.4pt; color:var(--muted); border-top:1px solid var(--line); padding-top:6px; margin-top:12px; }
table { border-collapse:collapse; width:100%; }
th { text-align:left; font-size:7.4pt; text-transform:uppercase; letter-spacing:.06em; color:var(--muted);
  font-weight:600; border-bottom:1.5px solid var(--navy); padding:4px 6px; }
td { padding:5px 6px; border-bottom:1px solid var(--line); vertical-align:top; }
tr { break-inside:avoid; }
table.small td { font-size:7.6pt; padding:2px 5px; line-height:1.3; }
td.nw { white-space:nowrap; }
.ev code { font-size:6.8pt; word-break:break-all; }
td.url { word-break:break-all; max-width:220px; }
.ev td.evsrc { width:42%; }
#p7 h3 { margin:7px 0 3px; } #p7 .disc { margin-top:6px; } #p7 .two h3 { margin-top:2px; }
.pillars td { vertical-align:middle; } .pillars .pname { width:110px; }
.pbar { width:190px; white-space:nowrap; } .pbar .bar { display:inline-block; width:140px; height:10px;
  background:var(--plane); border-radius:5px; overflow:hidden; vertical-align:middle; border:1px solid var(--line); }
.pbar .bar div { height:100%; border-radius:5px; }
.pscore { display:inline-block; width:30px; text-align:right; font-weight:800; font-variant-numeric:tabular-nums; font-size:11pt; }
.pillars tfoot td { border-top:1.5px solid var(--navy); border-bottom:none; background:var(--plane); }
.flags { margin-top:4px; }
.fl li { font-size:8.3pt; line-height:1.35; }
.pillars td { padding:3px 6px; }
.rules { columns:2; column-gap:16px; list-style:none; padding:0; margin:0; font-size:7.4pt; line-height:1.3; }
.rules li { break-inside:avoid; padding:2px 0; border-bottom:1px solid var(--line); color:var(--ink2); }
.rules li.fired { color:var(--ink); }
.lv { display:inline-block; width:44px; font-weight:700; font-size:6.8pt; text-transform:uppercase; }
.lv-critical { color:var(--critdark); } .lv-red { color:var(--crit); } .lv-amber { color:var(--warntext); } .lv-green { color:var(--goodtext); }
.t-text .t-value { font-size:12pt; line-height:1.2; margin:3px 0 2px; }
.flags h3 { display:flex; align-items:center; gap:6px; }
.count { font-size:8pt; background:var(--plane); border:1px solid var(--line); border-radius:999px; padding:0 7px; color:var(--ink2); }
.fl { list-style:none; padding:0; margin:0; } .fl li { display:flex; gap:7px; padding:4px 0; border-bottom:1px solid var(--line); }
.fl li .ico { margin-top:2px; }
.fl-critical .fl li { background:#fbf0f0; padding:5px 6px; border-radius:5px; border:1px solid #efcfcf; margin-bottom:3px; }
.detail { color:var(--ink2); }
.cites { white-space:nowrap; } .cite { display:inline-block; font-size:7pt; font-weight:700; color:var(--navy);
  background:#e7eef9; border-radius:3px; padding:0 3px; margin-left:2px; font-variant-numeric:tabular-nums; }
.callout { margin-top:10px; padding:8px 12px; border-radius:8px; background:var(--plane); border:1px solid var(--line); break-inside:avoid; }
.callout h3 { margin-top:0; }
.insights { background:#eef3fb; border-color:#d6e2f4; }
.grid2 { display:grid; grid-template-columns:minmax(0, 1fr) minmax(0, 1fr); gap:8px 14px; margin-top:8px; }
figure.cc { margin:8px 0 0; break-inside:avoid; }
figcaption { font-weight:700; font-size:9pt; color:var(--navy); margin-bottom:2px; }
.src { font-size:6.8pt; color:var(--muted); }
.chart { display:block; }
.pill { display:inline-block; font-size:7.4pt; padding:0 6px; border-radius:999px; background:#e7eef9; color:var(--navy);
  font-weight:600; margin:1px 1px; }
.mk { font-weight:800; } .mk.ok { color:var(--goodtext); } .mk.warn { color:var(--warntext); } .mk.muted { color:var(--muted); }
.legend { font-size:7.6pt; color:var(--muted); }
.foot-note { font-size:7.2pt; color:var(--muted); margin-top:10px; font-style:italic; }
.findings { list-style:none; margin:0; padding:0; } .findings li { padding:5px 0; border-bottom:1px solid var(--line); break-inside:avoid; }
.findings p { margin:2px 0; }
.fhead { display:flex; gap:6px; align-items:center; flex-wrap:wrap; }
.cid { font-weight:800; color:var(--navy); }
.st { font-size:7pt; font-weight:700; text-transform:uppercase; letter-spacing:.05em; padding:1px 6px; border-radius:4px; }
.st-ok { background:#e2f3e2; color:var(--goodtext); } .st-warn { background:#fff1cc; color:var(--warntext); }
.st-bad { background:#fbe1e1; color:#a52020; } .st-muted { background:#eceae4; color:var(--ink2); }
.fin { margin-top:4px; color:var(--ink2); }
.watermark { position:fixed; top:42%; left:-10%; right:-10%; text-align:center; transform:rotate(-28deg);
  font-size:86pt; font-weight:900; letter-spacing:.08em; color:rgba(208,59,59,.09); z-index:10; pointer-events:none; }
"""


# ---- public API ----------------------------------------------------------------

def build_html(case: CaseRecord, signals: Signals, flags: list[Flag], pillars: list[Pillar],
               rec: Recommendation, *, rules: dict | None = None, sample: bool = False) -> str:
    """Self-contained A4 HTML report (7 sections). All source text is HTML-escaped.

    `rules` maps rule id -> (level, condition) or -> condition, printed on page 7.
    `sample=True` adds a SAMPLE DATA watermark and banner (placeholder Signals).
    """
    company = _company(case, signals)
    footer = f"Proofroom · {company} · {' · '.join(run_labels(case))}" + (" · SAMPLE DATA" if sample else "")
    pages = [
        _page1(case, signals, flags, rec, sample),
        _page2(company, flags, pillars, rec),
        _page3(company, signals),
        _page4(company, case, signals),
        _page5(company, signals),
        _page6(company, case, signals),
        _page7(company, case, signals, flags, pillars, rec, rules, sample),
    ]
    wm = '<div class="watermark" aria-hidden="true">SAMPLE DATA</div>' if sample else ""
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="proofroom-footer" content="{_e(footer)}">'
            f'<title>{_e(company)} signal report</title><style>{CSS}</style></head><body>'
            f'{wm}{"".join(pages)}</body></html>')


@functools.lru_cache(maxsize=1)
def _node_env() -> tuple[str | None, str]:
    """(node binary, NODE_PATH) with the global module dirs added so require('playwright') resolves."""
    node = shutil.which("node")
    paths = [p for p in os.environ.get("NODE_PATH", "").split(os.pathsep) if p]
    npm = shutil.which("npm")
    if npm:
        try:
            root = subprocess.run([npm, "root", "-g"], capture_output=True, text=True, timeout=15).stdout.strip()
            if root:
                paths.append(root)
        except (OSError, subprocess.SubprocessError):
            pass
    for extra in ("/opt/node-tools/node_modules", "/usr/local/lib/node_modules", "/usr/lib/node_modules"):
        if os.path.isdir(extra):
            paths.append(extra)
    seen: list[str] = []
    for p in paths:
        if p not in seen:
            seen.append(p)
    return node, os.pathsep.join(seen)


def pdf_available() -> bool:
    """True when node can load Playwright (used by tests and callers to choose PDF vs HTML)."""
    node, node_path = _node_env()
    if not node or not RENDER_JS.exists():
        return False
    try:
        r = subprocess.run([node, "-e", "require('playwright')"], capture_output=True, timeout=20,
                           env={**os.environ, "NODE_PATH": node_path})
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


def render_pdf(html_text: str, out_path: Path, *, timeout: float = PDF_TIMEOUT_S) -> Path:
    """Print `html_text` to an A4 PDF at `out_path` via node + Playwright Chromium.

    Raises PdfRenderError when node/Playwright is missing or rendering fails.
    """
    node, node_path = _node_env()
    if not node:
        raise PdfRenderError("node is not installed; serve the HTML report instead")
    if not RENDER_JS.exists():
        raise PdfRenderError(f"renderer script missing: {RENDER_JS}")
    out_path = Path(out_path)
    with tempfile.TemporaryDirectory(prefix="proofroom-pdf-") as tmp:
        src, dst = Path(tmp) / "report.html", Path(tmp) / "report.pdf"
        src.write_text(html_text, encoding="utf-8")
        try:
            r = subprocess.run([node, str(RENDER_JS), str(src), str(dst)], capture_output=True, text=True,
                               timeout=timeout, env={**os.environ, "NODE_PATH": node_path})
        except subprocess.TimeoutExpired as exc:
            raise PdfRenderError(f"PDF render timed out after {timeout:.0f} s") from exc
        except OSError as exc:
            raise PdfRenderError(f"could not start node: {exc}") from exc
        if r.returncode == 3 or "PROOFROOM_NO_PLAYWRIGHT" in r.stderr:
            raise PdfRenderError("Playwright is not available to node (require('playwright') failed); "
                                 "serve the HTML report instead")
        if r.returncode != 0 or not dst.exists():
            tail = (r.stderr or r.stdout).strip().splitlines()[-3:]
            raise PdfRenderError("PDF render failed: " + " | ".join(tail))
        data = dst.read_bytes()
        if not data.startswith(b"%PDF"):
            raise PdfRenderError("renderer produced a file that is not a PDF")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)
    return out_path


# ---- sample (layout review only; values are placeholders) -------------------------

def _sample_inputs(case: CaseRecord) -> tuple[Signals, list[Flag], list[Pillar], Recommendation, dict]:
    """Placeholder Signals etc. for a real case. Flags for verification come from the case's rules."""
    from proofroom import report as base

    def ser(key: str, label: str, unit: str, vals: list[tuple[str, float]], src: str = "SAMPLE") -> Series:
        return Series(key=key, label=label, unit=unit, points=[Point(date=d, value=v) for d, v in vals], source=src)

    months = [f"{y}-{m:02d}" for y in (2024, 2025, 2026) for m in range(1, 13)][9:34]  # 2024-10 .. 2026-10
    hc = [3, 3, 4, 4, 5, 5, 6, 6, 7, 8, 8, 9, 10, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21]
    wv = [800, 950, 1200, 1500, 2100, 2600, 3300, 3900, 4800, 6200, 7400, 8100, 9900, 12500, 14200, 16900,
          18800, 22400, 26100, 24700, 28800, 31900, 35500, 39800, 43100]
    fo = [120, 150, 180, 230, 290, 360, 450, 520, 640, 900, 1150, 1300, 1480, 1900, 2350, 2800, 3200, 3700,
          4300, 4600, 5100, 5600, 6300, 6900, 7400]
    q = months[::3]
    signals = Signals(
        company=(case.g1 or {}).get("name") or case.input.domain, domain=case.input.domain,
        company_id=(case.g1 or {}).get("company_id"),
        description="SAMPLE description: contextual advertising native to AI assistants and search apps.",
        year_founded=2024, hq="San Francisco, CA (SAMPLE)", status="Private",
        series={
            "headcount": ser("headcount", "Headcount", "people", list(zip(months, hc)), "SAMPLE headcount.timeseries"),
            "web_visitors": ser("web_visitors", "Web visitors", "visitors/month", list(zip(months, wv)),
                                "SAMPLE web_traffic.monthly_visitors"),
            "followers": ser("followers", "Followers", "followers", list(zip(months, fo)), "SAMPLE linkedin followers"),
            "revenue_low": ser("revenue_low", "Revenue low", "USD",
                               list(zip(q, [0, 0.1e6, 0.25e6, 0.5e6, 0.8e6, 1.0e6, 1.5e6, 2.0e6, 2.5e6])),
                               "SAMPLE revenue estimate"),
            "revenue_high": ser("revenue_high", "Revenue high", "USD",
                                list(zip(q, [0.1e6, 0.4e6, 0.8e6, 1.2e6, 1.8e6, 2.5e6, 3.5e6, 4.2e6, 5.0e6])),
                                "SAMPLE revenue estimate"),
            "job_openings": ser("job_openings", "Open roles", "roles",
                                list(zip(months[12:], [2, 2, 3, 3, 4, 5, 4, 6, 7, 6, 8, 9, 9])), "SAMPLE job openings"),
        },
        metrics={"headcount_yoy_pct": Metric(key="headcount_yoy_pct", label="Headcount YoY", value=110.0,
                                             unit="%", display="+110%", period="trailing 12 months",
                                             source="SAMPLE headcount.growth_yoy")},
        role_mix={"Engineering": 48, "Sales": 19, "Product": 10, "Marketing": 9, "Operations": 8, "Design": 6},
        region_mix={"United States": 81, "Canada": 10, "India": 9},
        revenue_band_usd=(2.5e6, 5.0e6), hiring_openings=9,
        founders=[
            FounderProfileSample(name="Nic Baird", title="Co-Founder & CEO", since="2024",
                                 prior_employers=["Affirm", "Two Sigma"], big_tech_or_scaleup=["Affirm"],
                                 education=["SAMPLE University, BS"], years_experience=9),
            FounderProfileSample(name="Mike Choi", title="Co-Founder", since="2024-08",
                                 prior_employers=["Google", "Stealth startup (founder)"], prior_founder=True,
                                 big_tech_or_scaleup=["Google"], education=["SAMPLE University, MS"],
                                 years_experience=11),
            FounderProfileSample(name="Herrick Fang", title="Co-Founder", since="2024",
                                 prior_employers=["Affirm", "Supermove", "Qualified"],
                                 big_tech_or_scaleup=["Affirm"], education=["SAMPLE University, BS"],
                                 years_experience=8),
        ],
        market={"category": "Advertising technology", "categories": ["AdTech", "Generative AI", "Monetization"],
                "naics": "541810", "peer_count": 64, "funded_peers_24m": 17, "crowding": "medium",
                "median_peer_headcount_yoy_pct": 34.0,
                "peers": [{"name": f"Peer {c} (SAMPLE)", "domain": f"peer-{c.lower()}.example", "year_founded": y,
                           "headcount": h, "headcount_yoy_pct": g, "total_funding_usd": f,
                           "last_round_type": t, "last_round_date": d}
                          for c, y, h, g, f, t, d in [("A", 2021, 85, 41.0, 48e6, "series_b", "2025-11"),
                                                      ("B", 2023, 22, 57.0, 12e6, "seed", "2025-06"),
                                                      ("C", 2019, 140, 12.0, 95e6, "series_c", "2024-09"),
                                                      ("D", 2022, 35, 34.0, 18e6, "series_a", "2026-01"),
                                                      ("E", 2020, 60, -8.0, 30e6, "series_a", "2023-12")]],
                "seo_competitor_domains": ["example-ads.com", "example-search.net", "example-ai.io"],
                "source": "SAMPLE /company/search category peers"},
        news=[], coverage={"headcount": True, "web_traffic": True, "glassdoor": False},
        limitations=["SAMPLE: employee-rating field group not covered for this company."],
        credits_used=0.0,
    )
    flags: list[Flag] = []
    for f in base.flags(case):
        level = "critical" if f.level == "red" else f.level
        flags.append(Flag(level=level, rule=f.rule, title=f.title, detail=f.detail, evidence=list(f.evidence_ids)))
    flags += [
        Flag(level="amber", rule="M2 crowded", title="Category moderately crowded (SAMPLE value)",
             detail="17 of 64 peers raised in the last 24 months.", evidence=["metric:market.funded_peers_24m"]),
        Flag(level="green", rule="T1 headcount-growth", title="Headcount growing faster than peers (SAMPLE value)",
             detail="+110% YoY vs a peer median of +34%.", evidence=["metric:headcount_yoy_pct"]),
    ]
    pillars = [
        Pillar(name="Team", score=78, weight=0.25, reasons=["3 of 3 founders ID-joined (real)",
                                                             "SAMPLE: prior founder on the team"]),
        Pillar(name="Traction", score=72, weight=0.25, reasons=["SAMPLE: headcount +110% YoY",
                                                                 "SAMPLE: web visitors rising"]),
        Pillar(name="Market", score=55, weight=0.15, reasons=["SAMPLE: medium crowding, 17 funded peers"]),
        Pillar(name="Financing", score=74, weight=0.15, reasons=["Series A 8 months ago (indexed record)",
                                                                  "Indexed total equals the sum of rounds"]),
        Pillar(name="Verification", score=82, weight=0.20, reasons=["4 sentences verified, 1 withheld (real)"]),
    ]
    score = sum(p.score * p.weight for p in pillars)
    rec = Recommendation(
        rating="ACCUMULATE", score=round(score, 1), confidence="medium", check_size_usd=250_000,
        suggested_usd=150_000, sizing_pct=60.0, horizon="12–18 months",
        headline="SAMPLE: Verified Series A and a fully joined founding team; growth signals are strong but "
                 "the pre-seed amount is unrecorded and the claimed total is withheld.",
        rationale=["Announced Series A and seed match Crustdata's indexed record (real, page 6).",
                   "All three founders hold current roles at the company by employer-ID join (real, page 4).",
                   "SAMPLE: headcount growth well above the peer median.",
                   "Open point: the release's 'more than $26 million' total could not be verified (real)."],
        revisit_triggers=["The pre-seed amount is documented (closes the $26M vs $25.5M gap).",
                          "SAMPLE: headcount growth falls below the peer median for two quarters.",
                          "A new round or secondary sale appears in the indexed record."],
        disclaimer=DISCLAIMER,
    )
    rules = {r: ("critical" if lv == "red" else lv, cond) for r, (lv, cond) in base.RULES.items()}
    rules.update({"M2 crowded": ("amber", "More than 20% of category peers raised in the last 24 months"),
                  "T1 headcount-growth": ("green", "Headcount YoY exceeds the peer median")})
    return signals, flags, pillars, rec, rules


def FounderProfileSample(**kw):  # noqa: N802 - small factory for the sample only
    from proofroom.research_models import FounderProfile
    return FounderProfile(source="SAMPLE founder profile", **kw)


def _latest_case(case_dir: Path) -> Path:
    runs = sorted(case_dir.glob("run-*/case.json"), key=lambda p: int(p.parent.name.split("-")[1]))
    if not runs:
        raise FileNotFoundError(f"no case.json under {case_dir}")
    return runs[-1]


def main(argv: list[str] | None = None) -> int:
    """python -m proofroom.equity_report [case_dir] [out.pdf]: render the SAMPLE report."""
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    root = Path(__file__).resolve().parent.parent
    case_dir = Path(args[0]) if args else root / "data" / "cases" / "koahlabs-com"
    out = Path(args[1]) if len(args) > 1 else root / "docs" / "reports" / "sample-equity-report.pdf"
    case = CaseRecord.model_validate_json(_latest_case(case_dir).read_text(encoding="utf-8"))
    sig, fl, pil, rec, rules = _sample_inputs(case)
    doc = build_html(case, sig, fl, pil, rec, rules=rules, sample=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".html").write_text(doc, encoding="utf-8")
    try:
        render_pdf(doc, out)
    except PdfRenderError as exc:
        print(f"PDF unavailable ({exc}); HTML written to {out.with_suffix('.html')}")
        return 1
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
