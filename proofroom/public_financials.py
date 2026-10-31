"""Reported financials for listed companies, from SEC EDGAR XBRL filings (D32).

A model estimate is the wrong tool for a company that files accounts: for NVIDIA the
revenue model gives $12B against $216B reported. When Crustdata marks a company as
public, its ticker is looked up in SEC's ticker map and the latest annual revenue and net
income are read from the company's 10-K / 20-F / 40-F facts (data.sec.gov, no key).

Responses are cached under cache/sec/ so a replay is offline. Anything that fails (not an
SEC filer, network error, no annual revenue fact) returns None with a reason, and the
caller keeps the model estimate, labelled as such.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from . import config

log = logging.getLogger(__name__)

SEC_DIR = config.CACHE_DIR / "sec"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
FILINGS_URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik:010d}&type=10-K"
TICKERS_MAX_AGE_S = 7 * 24 * 3600
TIMEOUT_S = 20.0

ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
# Revenue tags in order of preference; the freshest annual fact across them wins.
REVENUE_TAGS = [
    ("us-gaap", "Revenues"),
    ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
    ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax"),
    ("us-gaap", "SalesRevenueNet"),
    ("ifrs-full", "Revenue"),
    ("ifrs-full", "RevenueFromContractsWithCustomers"),
]
NET_INCOME_TAGS = [("us-gaap", "NetIncomeLoss"), ("ifrs-full", "ProfitLoss"),
                   ("us-gaap", "ProfitLoss")]


class NoUserAgent(Exception):
    """SEC_USER_AGENT is not set, and the answer is not in the cache."""


def user_agent() -> str:
    """SEC's fair-access policy asks every client to declare who it is and a contact
    email ('Name email'), and www.sec.gov refuses requests that don't. Read from .env."""
    return os.environ.get("SEC_USER_AGENT", "").strip()


# ---- which companies qualify ------------------------------------------------------------

def public_markets(rec: dict) -> dict:
    return ((rec or {}).get("revenue") or {}).get("public_markets") or {}


def is_public(rec: dict) -> bool:
    """Crustdata says the company is listed: company_type 'Public Company' or an IPO date.
    A ticker alone is not enough: private records carry made-up symbols ('ATTIO')."""
    bi = (rec or {}).get("basic_info") or {}
    return bi.get("company_type") == "Public Company" or bool(public_markets(rec).get("ipo_date"))


def candidate_tickers(rec: dict) -> list[str]:
    """Crustdata's stock_symbols mixes tickers and names ('NVDA', 'NVIDIA'); every entry
    is tried against SEC's map, in order. 'NASDAQ:NVDA' style prefixes are stripped."""
    out: list[str] = []
    for s in public_markets(rec).get("stock_symbols") or []:
        t = str(s).split(":")[-1].strip().upper().replace(".", "-")
        if t and t not in out:
            out.append(t)
    return out


# ---- parsing XBRL company facts ---------------------------------------------------------

def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def annual_facts(facts: dict, ns: str, tag: str) -> tuple[str, list[dict]]:
    """Full-year values of one tag from annual reports, one per period end (the latest
    filing wins, so restatements replace originals). Prefers USD; else the first unit."""
    units = (((facts.get("facts") or {}).get(ns) or {}).get(tag) or {}).get("units") or {}
    if not units:
        return "", []
    cur = "USD" if "USD" in units else next(iter(units))
    by_end: dict[str, dict] = {}
    for x in units[cur]:
        if x.get("form") not in ANNUAL_FORMS or not x.get("start") or not x.get("end"):
            continue
        if not 330 <= _days(x["start"], x["end"]) <= 400:   # a full year, not a quarter
            continue
        prev = by_end.get(x["end"])
        if prev is None or str(x.get("filed", "")) > str(prev.get("filed", "")):
            by_end[x["end"]] = x
    return cur, sorted(by_end.values(), key=lambda x: x["end"])


def _pick(facts: dict, tags: list[tuple[str, str]]) -> tuple[str, str, list[dict]]:
    """The tag whose latest annual fact is the most recent (ties keep tag order)."""
    best: tuple[str, str, list[dict]] = ("", "", [])
    for ns, tag in tags:
        cur, rows = annual_facts(facts, ns, tag)
        if rows and (not best[2] or rows[-1]["end"] > best[2][-1]["end"]):
            best = (f"{ns}:{tag}", cur, rows)
    return best


def summarize(facts: dict) -> dict | None:
    """Latest fiscal-year revenue, the prior year and growth, and net income for the same
    year. None when the filer reports no annual revenue."""
    tag, cur, rows = _pick(facts, REVENUE_TAGS)
    if not rows:
        return None
    last = rows[-1]
    prior = next((x for x in reversed(rows[:-1]) if 330 <= _days(x["end"], last["end"]) <= 400), None)
    ni_tag, ni_cur, ni_rows = _pick(facts, NET_INCOME_TAGS)
    ni = next((x for x in ni_rows if x["end"] == last["end"]), None) if ni_cur == cur else None
    rev = float(last["val"])
    return {
        "entity": facts.get("entityName", ""),
        "currency": cur,
        "revenue": rev,
        "fiscal_year_end": last["end"],
        "fiscal_year": last.get("fy"),
        "form": last.get("form", ""),
        "filed": last.get("filed", ""),
        "accession": last.get("accn", ""),
        "tag": tag,
        "prior_revenue": float(prior["val"]) if prior else None,
        "revenue_yoy_pct": (100.0 * (rev / float(prior["val"]) - 1)) if prior and prior["val"] else None,
        "net_income": float(ni["val"]) if ni else None,
        "net_margin_pct": (100.0 * float(ni["val"]) / rev) if ni and rev else None,
        "history": [{"end": x["end"], "value": float(x["val"])} for x in rows[-6:]],
    }


# ---- fetching (cached) ------------------------------------------------------------------

async def _get_json(client: httpx.AsyncClient, url: str, path: Path, max_age_s: float | None) -> Any:
    if path.exists() and (max_age_s is None or time.time() - path.stat().st_mtime < max_age_s):
        return json.loads(path.read_text(encoding="utf-8"))
    if not client.headers.get("User-Agent"):
        raise NoUserAgent
    r = await client.get(url)
    r.raise_for_status()
    data = r.json()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


async def reported_financials(rec: dict, *, cache_dir: Path | None = None) -> tuple[dict | None, str]:
    """(financials, note). financials is None when there is nothing reported to use; the
    note says why, for the page and the limitations list."""
    if not is_public(rec):
        return None, "private company: no filed accounts"
    tickers = candidate_tickers(rec)
    if not tickers:
        return None, "listed, but Crustdata has no ticker to look up"
    folder = cache_dir or SEC_DIR
    try:
        async with httpx.AsyncClient(headers={"User-Agent": user_agent()}, timeout=TIMEOUT_S,
                                     follow_redirects=True) as client:
            tmap = await _get_json(client, TICKERS_URL, folder / "company_tickers.json", TICKERS_MAX_AGE_S)
            by_ticker = {str(v.get("ticker", "")).upper(): v for v in tmap.values()}
            hit = next(((t, by_ticker[t]) for t in tickers if t in by_ticker), None)
            if hit is None:
                return None, f"listed ({', '.join(tickers[:3])}), but not an SEC filer"
            ticker, row = hit
            cik = int(row["cik_str"])
            facts = await _get_json(client, FACTS_URL.format(cik=cik), folder / f"CIK{cik:010d}.json", None)
    except NoUserAgent:
        return None, "SEC_USER_AGENT is not set, so filed accounts could not be fetched"
    except (httpx.HTTPError, ValueError, OSError) as e:
        log.warning("SEC lookup failed: %s", e)
        return None, f"SEC lookup failed ({type(e).__name__})"
    out = summarize(facts)
    if out is None:
        return None, f"{ticker} files with the SEC, but reports no annual revenue fact"
    out.update({"ticker": ticker, "cik": cik, "source_url": FILINGS_URL.format(cik=cik),
                "source": f"SEC EDGAR, {out['form']} filed {out['filed']}"})
    return out, ""


def as_revenue(fin: dict, model_estimate: dict, headcount: float | None) -> dict:
    """The revenue payload with reported figures in place of the estimate. The model's own
    number is kept alongside for comparison, never shown as the revenue."""
    v = fin["revenue"]
    return {
        "label": "REPORTED",
        "point_usd": v, "low_usd": v, "high_usd": v,
        "revenue_per_employee_usd": round(v / headcount, 0) if headcount else None,
        "reported": fin,
        "model_estimate_usd": model_estimate.get("point_usd"),
        "method": f"Reported revenue from {fin['source']} ({fin['tag']})",
        "reason": "Listed company: filed accounts are used instead of the model.",
        "drivers": [], "components": {}, "flags": [], "band_usd": model_estimate.get("band_usd"),
        "band_trusted": False, "early_stage": False, "namesake": model_estimate.get("namesake"),
        "listed_bucket": model_estimate.get("listed_bucket"),
    }
