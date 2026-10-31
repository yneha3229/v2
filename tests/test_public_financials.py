"""Reported financials for listed companies (D32): who qualifies, XBRL parsing, offline cache."""
import asyncio
import json

from proofroom import public_financials as pf


def _fact(start, end, val, form="10-K", filed="2026-03-01", fy=2025):
    return {"start": start, "end": end, "val": val, "form": form, "filed": filed, "fy": fy, "accn": "0001"}


def _facts(**tags):
    out = {"entityName": "NVIDIA CORP", "facts": {}}
    for key, rows in tags.items():
        ns, tag = key.split("__")
        out["facts"].setdefault(ns, {})[tag] = {"units": {"USD": rows}}
    return out


def _rec(company_type="Public Company", symbols=("NVDA", "NVIDIA"), ipo="1999-01-22"):
    return {"basic_info": {"company_type": company_type},
            "revenue": {"public_markets": {"ipo_date": ipo, "stock_symbols": list(symbols)}}}


def test_only_listed_companies_qualify():
    assert pf.is_public(_rec())
    assert pf.is_public(_rec(company_type="", ipo="2004-08-19"))
    # a private record with a made-up ticker (Attio carries "ATTIO") is not public
    assert not pf.is_public(_rec(company_type="Privately Held", symbols=("ATTIO",), ipo=None))


def test_candidate_tickers_strip_exchange_and_dedupe():
    assert pf.candidate_tickers(_rec(symbols=("NASDAQ:NVDA", "nvda", "BRK.B"))) == ["NVDA", "BRK-B"]


def test_summary_takes_latest_full_year_and_skips_quarters():
    facts = _facts(**{
        "us-gaap__Revenues": [
            _fact("2024-01-29", "2025-01-26", 130.5e9, filed="2025-02-26", fy=2024),
            _fact("2025-01-27", "2026-01-25", 215.9e9, fy=2025),
            _fact("2026-01-26", "2026-04-26", 70e9, form="10-Q"),           # a quarter
        ],
        "us-gaap__NetIncomeLoss": [_fact("2025-01-27", "2026-01-25", 120e9)],
    })
    s = pf.summarize(facts)
    assert s["revenue"] == 215.9e9 and s["fiscal_year_end"] == "2026-01-25"
    assert s["prior_revenue"] == 130.5e9
    assert round(s["revenue_yoy_pct"], 1) == 65.4
    assert s["net_income"] == 120e9 and round(s["net_margin_pct"]) == 56
    assert s["tag"] == "us-gaap:Revenues"


def test_restatement_replaces_original_and_freshest_tag_wins():
    facts = _facts(**{
        "us-gaap__Revenues": [_fact("2020-01-01", "2020-12-31", 10e9, filed="2021-02-01")],
        "us-gaap__RevenueFromContractWithCustomerExcludingAssessedTax": [
            _fact("2024-01-01", "2024-12-31", 50e9, filed="2025-02-01"),
            _fact("2024-01-01", "2024-12-31", 51e9, form="10-K/A", filed="2025-06-01"),
        ],
    })
    s = pf.summarize(facts)
    assert s["revenue"] == 51e9 and s["form"] == "10-K/A"
    assert s["tag"] == "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"


def test_no_annual_revenue_gives_none():
    assert pf.summarize(_facts(**{"us-gaap__Revenues": [_fact("2026-01-01", "2026-03-31", 1e9, form="10-Q")]})) is None


def test_reported_financials_reads_cache_offline(tmp_path):
    (tmp_path / "company_tickers.json").write_text(json.dumps(
        {"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"}}), encoding="utf-8")
    (tmp_path / "CIK0001045810.json").write_text(json.dumps(_facts(**{
        "us-gaap__Revenues": [_fact("2025-01-27", "2026-01-25", 215.9e9)]})), encoding="utf-8")
    fin, note = asyncio.run(pf.reported_financials(_rec(), cache_dir=tmp_path))
    assert note == "" and fin["ticker"] == "NVDA" and fin["cik"] == 1045810
    assert fin["revenue"] == 215.9e9 and fin["source"] == "SEC EDGAR, 10-K filed 2026-03-01"
    rev = pf.as_revenue(fin, {"point_usd": 12.4e9}, 52_000)
    assert rev["label"] == "REPORTED" and rev["point_usd"] == rev["low_usd"] == rev["high_usd"] == 215.9e9
    assert rev["model_estimate_usd"] == 12.4e9 and rev["revenue_per_employee_usd"] == round(215.9e9 / 52_000)


def test_no_network_without_a_declared_user_agent(tmp_path, monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    fin, note = asyncio.run(pf.reported_financials(_rec(), cache_dir=tmp_path))
    assert fin is None and "SEC_USER_AGENT is not set" in note


def test_listed_but_not_an_sec_filer(tmp_path):
    (tmp_path / "company_tickers.json").write_text(json.dumps(
        {"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"}}), encoding="utf-8")
    fin, note = asyncio.run(pf.reported_financials(_rec(symbols=("RELIANCE",)), cache_dir=tmp_path))
    assert fin is None and "not an SEC filer" in note
    fin, note = asyncio.run(pf.reported_financials(_rec(company_type="Privately Held", ipo=None)))
    assert fin is None and note.startswith("private company")
