"""What the graph decides (plan v2 §7, §20): G1 subject anchor, and helpers that
unwrap Crustdata's `[].matches[].company_data` responses. G2–G4 build on these."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

MATCHED, NO_MATCH, TIE = "MATCHED", "NO_MATCH", "TIE"


@dataclass
class G1Result:
    """Subject anchor. `status` is MATCHED, NO_MATCH (never "does not exist") or TIE."""

    domain: str
    status: str
    company_id: int | None = None
    name: str = ""
    basis: str = ""
    candidates: list[dict] = field(default_factory=list)
    excluded: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _matches(response: Any) -> list[dict]:
    """Flatten Identify/Enrich responses: a list of `{matched_on, matches: [...]}` blocks.
    Unknown shapes yield no matches rather than raising."""
    blocks = response if isinstance(response, list) else [response] if isinstance(response, dict) else []
    out: list[dict] = []
    for block in blocks:
        if isinstance(block, dict) and isinstance(block.get("matches"), list):
            out.extend(m for m in block["matches"] if isinstance(m, dict))
    return out


def _candidate(match: dict) -> dict | None:
    data = match.get("company_data") or {}
    info = data.get("basic_info") or {}
    cid = data.get("crustdata_company_id") or info.get("crustdata_company_id")
    try:
        cid = int(cid)
    except (TypeError, ValueError):
        return None
    try:
        conf = float(match.get("confidence_score") or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    return {
        "id": cid,
        "name": str(info.get("name") or ""),
        "primary_domain": str(info.get("primary_domain") or "").lower(),
        "all_domains": [str(d).lower() for d in info.get("all_domains") or []],
        "confidence": conf,
    }


def resolve_g1(domain: str, identify_response: Any) -> G1Result:
    """G1 tie rule (§7): prefer the candidate whose `primary_domain` equals the input,
    highest confidence first; otherwise a unique candidate whose `all_domains` contains
    it. Abstain (TIE) only if two distinct IDs tie on both checks."""
    domain = domain.strip().lower()
    cands: dict[int, dict] = {}
    for m in _matches(identify_response):
        c = _candidate(m)
        if c and (c["id"] not in cands or c["confidence"] > cands[c["id"]]["confidence"]):
            cands[c["id"]] = c
    all_cands = sorted(cands.values(), key=lambda c: -c["confidence"])
    res = G1Result(domain, NO_MATCH, candidates=all_cands)
    if not all_cands:
        res.basis = "Identify returned no candidates (not evidence that the company does not exist)"
        return res

    exact = [c for c in all_cands if c["primary_domain"] == domain]
    if exact:
        top = exact[0]["confidence"]
        best = [c for c in exact if c["confidence"] == top]
        if len(best) == 1:
            return _accept(res, best[0], f"primary_domain == {domain}, confidence {top}")
        res.status, res.basis = TIE, f"{len(best)} IDs share primary_domain {domain} at {top}"
        return res

    listed = [c for c in all_cands if domain in c["all_domains"]]
    if len(listed) == 1:
        return _accept(res, listed[0], f"unique candidate listing {domain} in all_domains")
    if len(listed) > 1:
        res.status, res.basis = TIE, f"{len(listed)} IDs list {domain} in all_domains"
        return res
    res.basis = "no candidate has this domain as primary or listed domain"
    res.excluded = all_cands
    return res


def _accept(res: G1Result, chosen: dict, basis: str) -> G1Result:
    res.status, res.company_id, res.name, res.basis = MATCHED, chosen["id"], chosen["name"], basis
    res.excluded = [c for c in res.candidates if c["id"] != chosen["id"]]
    return res


def company_record(enrich_response: Any) -> dict:
    """The first `company_data` of a Company Enrich response, or {} if absent."""
    for m in _matches(enrich_response):
        data = m.get("company_data")
        if isinstance(data, dict):
            return data
    log.warning("company enrich response had no company_data")
    return {}
