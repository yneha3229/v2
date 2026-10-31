"""Fixture capture and strip (plan v2 §8.5).

Copies dev-cache records into `fixtures/<name>/crustdata/`, keeping only
allowlisted keys (at any depth), so fixtures carry the fields Proofroom reads and
nothing else. File names keep the cache key, so FIXTURE mode replays by request.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from proofroom import config

log = logging.getLogger(__name__)

ALLOWED_KEYS = frozenset({
    # response wrappers
    "matched_on", "match_type", "match_status", "matches", "confidence_score",
    "company_data", "person_data", "profiles", "total_count", "results", "metadata",
    # company identity
    "crustdata_company_id", "basic_info", "name", "primary_domain", "all_domains", "updated_at",
    # funding fields used by G4
    "funding", "total_investment_usd", "last_round_amount_usd", "last_round_type",
    "last_fundraise_date", "num_funding_rounds", "investors", "milestones", "round_type",
    "date", "funding_date", "amount_usd", "lead_investors", "investors_detailed",
    # people and employment (both key sets)
    "people", "founders", "crustdata_person_id", "basic_profile", "current_title",
    "social_handles", "professional_network_identifier", "profile_url",
    "experience", "employment_details", "current", "past",
    "employer_name", "employer_company_id", "employee_title", "employee_start_date",
    "employee_end_date", "title", "start_date", "end_date",
    # news and web
    "news", "article_url", "article_title", "article_publish_date", "article_publisher_name",
    "publisher_domain", "source", "url", "snippet", "success", "timestamp", "content",
    "position",
})


def strip(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: strip(v) for k, v in obj.items() if k in ALLOWED_KEYS}
    if isinstance(obj, list):
        return [strip(v) for v in obj]
    return obj


def capture(name: str, cache_files: list[Path], fixtures_dir: Path | None = None) -> list[Path]:
    """Strip each cache record and write it under `fixtures/<name>/crustdata/`."""
    out_dir = (fixtures_dir or config.FIXTURES_DIR) / name / "crustdata"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for src in cache_files:
        try:
            rec = json.loads(src.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            log.warning("skipping unreadable cache record %s: %s", src.name, e)
            continue
        fixture = {"endpoint": rec.get("endpoint"), "request": rec.get("request"),
                   "status": rec.get("status", 200), "credits_used": rec.get("credits_used"),
                   "body": strip(rec.get("body"))}
        dst = out_dir / src.name
        dst.write_text(json.dumps(fixture, indent=1, ensure_ascii=False), encoding="utf-8")
        written.append(dst)
    return written
