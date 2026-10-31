"""Equity-style report: HTML structure, escaping, SVG charts, PDF render (offline)."""
from __future__ import annotations

import re
import shutil
import subprocess

import pytest

from proofroom import equity_report as er
from proofroom.errors import ProofroomError
from proofroom.models import CaseRecord, Claim, Evidence, Finding, RunInput
from proofroom.research_models import (FounderProfile, Flag, Market, Metric, NewsItem, Peer, Pillar,
                                       Point, Recommendation, Series, Signals)


def _series(key, unit, vals, start=2025):
    pts = [Point(date=f"{start + (i // 12)}-{i % 12 + 1:02d}", value=v) for i, v in enumerate(vals)]
    return Series(key=key, label=key.replace("_", " ").title(), unit=unit, points=pts, source=f"test {key}")


def _case() -> CaseRecord:
    return CaseRecord(
        case_id="acme-test", run=1, status="DELIVERED", run_mode="FIXTURE",
        input=RunInput(domain="acme.test", input_mode="A", run_mode="FIXTURE"), reviewed="2026-10-31",
        g1={"status": "MATCHED", "company_id": 42, "name": "Acme"},
        evidence=[
            Evidence(id="E1", kind="source_passage", source="https://acme.test/news", locator="D1[0:40]",
                     value="Acme raised <b>$10M</b>"),
            Evidence(id="G5", kind="graph", source="/company/enrich", locator="funding.milestones[0]",
                     value="series_a, 2026-02-24 (day), $10,000,000, lead Example Capital"),
            Evidence(id="G6", kind="graph", source="/company/enrich", locator="funding.milestones[1]",
                     value="secondary_sale, 2026-06-01 (day), $3,000,000, lead not recorded"),
            Evidence(id="G7", kind="graph", source="/company/enrich", locator="funding.milestones[2]",
                     value="pre_seed, 2024 (year), amount not recorded, lead not recorded"),
        ],
        claims=[Claim(id="C1", doc_id="D1", quote="Acme raised $10M", family="F3", predicate="raised_round",
                      subject="Acme", object="Series A", amount_text="$10M", currency_text="USD",
                      date_text="", title_text="", qualifiers="", materiality="high", selected=True,
                      exclusion_reason="")],
        findings=[Finding(claim_id="C1", disposition="supported", qualified=False,
                          basis=["company_statement", "crustdata_indexed_record"],
                          sentence="Acme announced a $10M Series A <script>alert(1)</script>.",
                          evidence_ids=["E1", "G5"], as_of="2026-02-24", correction_reason="",
                          limitation="", question="")],
        questions=["Who led the pre-seed?"],
        stats={"model_source": "recorded model responses (FIXTURE)", "profile": "FULL"},
    )


def _signals(empty: bool = False) -> Signals:
    series = {} if empty else {
        "headcount": _series("headcount", "people", [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18]),
        "web_visitors": _series("web_visitors", "visitors/month", [100, 200, 300, 500, 800, 900]),
        "followers": _series("followers", "followers", [10]),
        "revenue_low": _series("revenue_low", "USD", [1e5, 2e5, 4e5]),
        "revenue_high": _series("revenue_high", "USD", [3e5, 6e5, 9e5]),
    }
    return Signals(
        company="Acme", domain="acme.test", description="Widgets <img src=x onerror=alert(1)>",
        year_founded=2023, hq="Testville", series=series,
        metrics={} if empty else {"headcount_yoy_pct": Metric(key="headcount_yoy_pct", label="YoY",
                                                              value=200.0, unit="%")},
        role_mix={} if empty else {"Engineering": 60, "Sales": 25, "Ops": 15},
        revenue_band_usd=None if empty else (4e5, 9e5),
        founders=[] if empty else [FounderProfile(name="Ada Founder", title="CEO", prior_employers=["BigCo"],
                                                  big_tech_or_scaleup=["BigCo"], prior_founder=True)],
        market=Market() if empty else Market(category="Widgets", crowding="high", peer_count=30,
                                             funded_peers_24m=12, median_peer_headcount_yoy_pct=20.0,
                                             peers=[Peer(name="Rival", headcount=40, headcount_yoy_pct=-5.0)],
                                             seo_competitor_domains=["noise.example"]),
        news=[] if empty else [NewsItem(title="Acme sued <x>", url="https://n.test", kind="legal_risk")],
    )


FLAGS = [
    Flag(level="critical", rule="R2 conflict", title="Sources disagree", detail="C9 <b>bad</b>", evidence=["E1"]),
    Flag(level="red", rule="B1 burn", title="Runway risk", detail="Last round 30 months ago", evidence=["G5"]),
    Flag(level="amber", rule="A2 qualified", title="Qualified", detail="one party's word"),
    Flag(level="green", rule="G1 round-confirmed", title="Round matches", detail="ok", evidence=["G5"]),
]
PILLARS = [Pillar(name=n, score=s, weight=w, reasons=[f"{n} reason"]) for n, s, w in
           [("Team", 80, .25), ("Traction", 70, .25), ("Market", 40, .15), ("Financing", 60, .15),
            ("Verification", 50, .20)]]
REC = Recommendation(rating="HOLD", score=62.5, confidence="medium", check_size_usd=250_000,
                     suggested_usd=100_000, sizing_pct=40.0, headline="Solid team, unresolved conflict",
                     rationale=["Reason one", "Reason two"], revisit_triggers=["Conflict resolved"],
                     horizon="12 months", disclaimer=er.DISCLAIMER)


@pytest.fixture(scope="module")
def doc() -> str:
    return er.build_html(_case(), _signals(), FLAGS, PILLARS, REC,
                         rules={"R2 conflict": ("critical", "Sources conflict"), "X9 unused": "never fires"})


def test_pages_and_headline_content(doc):
    for heading in ("Investment snapshot", "Why this rating", "Growth and traction", "Team",
                    "Market and competition", "Financing and verified claims", "Methodology"):
        assert heading in doc
    assert doc.count('class="page"') == 7
    assert ">HOLD<" in doc
    assert "$100K" in doc and "of your $250K standard check (40%)" in doc
    assert "not financial advice" in doc
    assert "FIXTURE" in doc and "recorded model responses" in doc
    assert "@page { size: A4; margin: 14mm; }" in doc
    assert 'name="proofroom-footer"' in doc and "Proofroom · Acme · FIXTURE" in doc


def test_all_source_text_escaped(doc):
    assert "<script>alert(1)</script>" not in doc
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in doc
    assert "<img src=x" not in doc and "<b>bad</b>" not in doc and "<b>$10M</b>" not in doc
    assert "Acme sued &lt;x&gt;" in doc


def test_flags_rules_and_citations(doc):
    assert "Critical flags" in doc and "Red flags" in doc and "Open points" in doc and "Green flags" in doc
    assert '<span class="cite">G5</span>' in doc
    assert "Sources conflict" in doc and "never fires" in doc and "B1 burn" in doc
    assert "Conflict resolved" in doc


def test_charts_and_rounds(doc):
    assert doc.count("<svg") >= 8
    assert "+200% YoY" in doc
    assert "liquidity" in doc  # secondary sale shown as liquidity
    assert "amount not recorded" in doc
    assert "indexed record (Crunchbase-derived)" in doc
    assert "noisy" in doc and "noise.example" in doc
    assert "Who led the pre-seed?" in doc
    assert "one data point" in doc  # followers has a single point


def test_no_external_resources(doc):
    assert not re.search(r"""(src|href)=["']https?://""", doc)
    assert "@import" not in doc and "fonts.googleapis" not in doc


def test_empty_signals_render_no_data():
    html = er.build_html(_case(), _signals(empty=True), [], [], REC)
    assert html.count("no data") >= 4
    assert "n/a" in html
    assert "No pillar scores" in html


def test_svg_helpers_empty_and_values():
    assert "no data" in er.svg_line_chart([])
    assert "no data" in er.svg_line_chart([Series(key="x", label="X", unit="people")])
    assert "no data" in er.svg_band_chart(None, None)
    assert "no data" in er.svg_bar_chart([])
    assert "no data" in er.svg_donut({})
    assert "no data" in er.svg_stacked_bar({})
    assert "no data" in er.svg_rounds_chart([])
    assert "no score" in er.svg_gauge(None)
    assert er.svg_sparkline(None) == ""
    s = _series("headcount", "people", [1, 2, 3])
    out = er.svg_line_chart([s, _series("web", "people", [3, 2, 1])])
    assert out.startswith("<svg") and out.endswith("</svg>") and "Headcount" in out
    assert "&lt;evil&gt;" in er.svg_bar_chart([("<evil>", 5.0), ("b", None)], unit="%")
    assert ">73<" in er.svg_gauge(73)


def test_formatting():
    assert er.fmt_usd(25_500_000) == "$25.5M"
    assert er.fmt_usd(150_000) == "$150K"
    assert er.fmt_pct(12.0) == "+12%"
    assert er.fmt_compact(1234) == "1.2K"
    assert er._date_label("2024") == "2024" and er._date_label("2024-01-01") == "2024"


def test_render_pdf_without_node_raises(monkeypatch, tmp_path):
    er._node_env.cache_clear()
    monkeypatch.setattr(er.shutil, "which", lambda name: None)
    try:
        with pytest.raises(er.PdfRenderError) as exc:
            er.render_pdf("<html></html>", tmp_path / "x.pdf")
        assert isinstance(exc.value, ProofroomError)
    finally:
        er._node_env.cache_clear()


@pytest.mark.skipif(not er.pdf_available(), reason="node or Playwright not available")
def test_render_pdf(doc, tmp_path):
    out = er.render_pdf(doc, tmp_path / "report.pdf")
    data = out.read_bytes()
    assert data.startswith(b"%PDF") and len(data) > 10_000
    if shutil.which("pdfinfo"):
        info = subprocess.run(["pdfinfo", str(out)], capture_output=True, text=True).stdout
        pages = int(re.search(r"Pages:\s+(\d+)", info).group(1))
        assert pages >= 5
