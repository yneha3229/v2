"""Data contract for the equity-research report (D24).

`signals.py` fills `Signals` from Crustdata; `scoring.py` turns a CaseRecord plus
Signals into flags, pillar scores and a recommendation; `equity_report.py` renders
the PDF. Every number shown carries the endpoint and JSON path it came from.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

FlagLevel = Literal["critical", "red", "amber", "green"]
Rating = Literal["INVEST", "ACCUMULATE", "HOLD", "AVOID"]


class Point(BaseModel):
    date: str            # ISO date (YYYY-MM-DD or YYYY-MM)
    value: float


class Series(BaseModel):
    key: str             # headcount | web_visitors | followers | revenue_low | revenue_high | ...
    label: str
    unit: str            # people | visitors/month | followers | USD
    points: list[Point] = Field(default_factory=list)
    source: str = ""     # e.g. "/company/enrich headcount.timeseries"


class Metric(BaseModel):
    key: str             # e.g. headcount_yoy_pct
    label: str
    value: float | None
    unit: str = ""       # %, people, USD, visitors/month, rating, months
    display: str = ""    # pre-formatted, e.g. "+166.7%"
    period: str = ""     # e.g. "trailing 12 months"
    source: str = ""     # endpoint + JSON path
    as_of: str = ""


class Peer(BaseModel):
    name: str
    domain: str = ""
    company_id: int | None = None
    headcount: float | None = None
    headcount_yoy_pct: float | None = None
    total_funding_usd: float | None = None
    last_round_type: str = ""
    last_round_date: str = ""
    year_founded: int | None = None
    source: str = ""


class Market(BaseModel):
    category: str = ""             # the category used for the peer search
    categories: list[str] = Field(default_factory=list)
    naics: str = ""
    peer_count: int | None = None          # companies found in the same category (search)
    funded_peers_24m: int | None = None    # of those, raised in the last 24 months
    crowding: Literal["low", "medium", "high", "unknown"] = "unknown"
    peers: list[Peer] = Field(default_factory=list)   # top peers for benchmarking (<=8)
    median_peer_headcount_yoy_pct: float | None = None
    seo_competitor_domains: list[str] = Field(default_factory=list)  # raw, noisy
    source: str = ""


class FounderProfile(BaseModel):
    name: str
    person_id: int | None = None
    title: str = ""
    since: str = ""
    prior_employers: list[str] = Field(default_factory=list)
    prior_founder: bool = False            # held a founder title before
    big_tech_or_scaleup: list[str] = Field(default_factory=list)  # notable prior employers
    education: list[str] = Field(default_factory=list)
    years_experience: float | None = None
    source: str = ""


class NewsItem(BaseModel):
    title: str
    url: str
    date: str = ""
    publisher: str = ""
    kind: Literal["funding", "product", "people", "legal_risk", "other"] = "other"


class Signals(BaseModel):
    company: str
    domain: str
    company_id: int | None = None
    logo_url: str = ""
    logo_data_uri: str = ""        # embedded so the PDF renders offline
    description: str = ""
    year_founded: int | None = None
    hq: str = ""
    status: str = ""
    headcount_total: float | None = None
    series: dict[str, Series] = Field(default_factory=dict)
    metrics: dict[str, Metric] = Field(default_factory=dict)
    role_mix: dict[str, float] = Field(default_factory=dict)      # % by function
    region_mix: dict[str, float] = Field(default_factory=dict)
    revenue_band_usd: tuple[float, float] | None = None
    hiring_openings: int | None = None
    employee_rating: float | None = None
    founders: list[FounderProfile] = Field(default_factory=list)
    market: Market = Field(default_factory=Market)
    news: list[NewsItem] = Field(default_factory=list)
    coverage: dict[str, bool] = Field(default_factory=dict)       # field group -> data present
    limitations: list[str] = Field(default_factory=list)
    credits_used: float = 0.0


class Flag(BaseModel):
    level: FlagLevel
    rule: str
    title: str
    detail: str
    evidence: list[str] = Field(default_factory=list)   # E#/G# ids or "metric:<key>"


class Pillar(BaseModel):
    name: Literal["Team", "Traction", "Market", "Financing", "Verification"]
    score: float              # 0-100
    weight: float             # sums to 1 across pillars
    reasons: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    rating: Rating
    score: float                       # 0-100 weighted
    confidence: Literal["low", "medium", "high"]
    check_size_usd: float              # the reader's standard ticket
    suggested_usd: float               # what this signal implies
    sizing_pct: float                  # suggested / check size
    headline: str
    rationale: list[str] = Field(default_factory=list)
    revisit_triggers: list[str] = Field(default_factory=list)
    horizon: str = ""
    disclaimer: str = ""
