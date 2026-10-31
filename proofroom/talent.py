"""Talent signals: founders' schools (tiered by region) and how many staff come from elite
schools or big tech (D31).

Founder education comes from Company Enrich `people.founders[].education.schools` (already in
the record). Staff counts come from Person Search `total_count` with the company-ID filter
plus an education or past-employer filter (`limit 1`, so each count costs one result).

Tiers are a coarse, stated prior, not a quality judgement on any person:
- india_elite: IITs, IISc, IIMs, BITS Pilani (national entrance-exam institutes)
- global_elite: Ivy League + Stanford, MIT, Caltech, Berkeley, CMU, Oxford, Cambridge
A top-tier school counts more when it matches the company's home market (IIT for an
Indian company, Stanford/Ivy for a US one), as the user asked (31 Oct).
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .errors import CrustError

log = logging.getLogger(__name__)

INDIA_ELITE = {
    "IIT": r"Indian Institute of Technology|\bIIT\b",
    "IISc": r"Indian Institute of Science\b",
    "IIM": r"Indian Institute of Management|\bIIM\b",
    "BITS Pilani": r"Birla Institute of Technology and Science|BITS,? Pilani",
}
GLOBAL_ELITE = {
    "Stanford": r"^Stanford University",
    "Harvard": r"^Harvard (University|Business School|College|Law School)",
    "MIT": r"Massachusetts Institute of Technology|^MIT\b",
    "Yale": r"^Yale University",
    "Princeton": r"^Princeton University",
    "Columbia": r"^Columbia (University|Business School)",
    "Penn": r"^University of Pennsylvania|^The Wharton School|^Wharton",
    "Brown": r"^Brown University",
    "Cornell": r"^Cornell University",
    "Dartmouth": r"^Dartmouth College",
    "Berkeley": r"University of California,? Berkeley|^UC Berkeley",
    "Carnegie Mellon": r"^Carnegie Mellon University",
    "Caltech": r"California Institute of Technology|^Caltech",
    "Oxford": r"^University of Oxford",
    "Cambridge": r"^University of Cambridge",
}
# Person Search substring values (the API's `(.)` operator) for the staff counts
COUNT_QUERIES = {
    "IIT": ["Indian Institute of Technology"],
    "IIM / IISc / BITS": ["Indian Institute of Management", "Indian Institute of Science",
                          "Birla Institute of Technology and Science"],
    "Stanford / MIT / Harvard": ["Stanford University", "Massachusetts Institute of Technology",
                                 "Harvard University"],
    "Other Ivy + Berkeley/CMU/Oxbridge": [
        "Yale University", "Princeton University", "Columbia University",
        "University of Pennsylvania", "Brown University", "Cornell University",
        "Dartmouth College", "University of California, Berkeley", "Carnegie Mellon University",
        "University of Oxford", "University of Cambridge"],
}
BIG_TECH = ["Google", "Microsoft", "Amazon", "Meta", "Apple", "Stripe", "Uber", "Flipkart"]
NON_DEGREE = re.compile(r"auditor|visiting|exchange|certificate|citation|summer|online|"
                        r"high school|igcse|a levels|baccalaureate", re.I)
EDU_FIELD = "education.schools.school"
PAST_EMPLOYER_FIELD = "experience.employment_details.past.company_name"
CURRENT_FIELD = "experience.employment_details.current.company_id"


@dataclass
class SchoolHit:
    person: str
    school: str
    degree: str
    tier: str            # india_elite | global_elite
    label: str           # e.g. IIT, Stanford
    home_market: bool    # tier matches the company's home market


@dataclass
class Talent:
    founder_schools: list[SchoolHit] = field(default_factory=list)
    founders_with_elite: int = 0
    founders_total: int = 0
    indexed_staff: int | None = None
    alumni: dict[str, int] = field(default_factory=dict)      # group -> staff count
    ex_big_tech: int | None = None
    staff: list["PersonHistory"] = field(default_factory=list)   # sampled staff work history
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def elite_staff(self) -> int:
        return sum(self.alumni.values())


def classify_school(school: str, degree: str = "") -> tuple[str, str] | None:
    """(tier, label) for a degree at an elite school, else None. Non-degree entries
    (auditor, visiting scholar, certificates, high school) never count."""
    if not school or NON_DEGREE.search(f"{school} {degree}"):
        return None
    for tier, table in (("india_elite", INDIA_ELITE), ("global_elite", GLOBAL_ELITE)):
        for label, pat in table.items():
            if re.search(pat, school, re.I):
                return tier, label
    return None


def home_tier(country: str) -> str:
    return "india_elite" if (country or "").strip().lower() in {"india", "ind", "in"} else "global_elite"


def founder_schools(founders: list[dict], country: str) -> tuple[list[SchoolHit], int, int]:
    """founders: [{"name", "schools": [{"school", "degree"}]}] -> hits, founders with an
    elite degree, founders with any education listed."""
    home = home_tier(country)
    hits, with_elite, listed = [], 0, 0
    for f in founders:
        schools = f.get("schools") or []
        listed += bool(schools)
        mine = []
        for s in schools:
            c = classify_school(str(s.get("school") or ""), str(s.get("degree") or ""))
            if c and not any(h.label == c[1] for h in mine):
                mine.append(SchoolHit(str(f.get("name") or ""), str(s.get("school")),
                                      str(s.get("degree") or ""), c[0], c[1], c[0] == home))
        with_elite += bool(mine)
        hits += mine
    return hits, with_elite, listed


def founders_from_enrich(rec: dict, keep_names: set[str] | None = None) -> list[dict]:
    """Founders and their schools from a Company Enrich record. `keep_names` restricts to
    the founders the pipeline already accepted (drops namesake noise)."""
    out = []
    for p in ((rec.get("people") or {}).get("founders")) or []:
        if not isinstance(p, dict):
            continue
        name = str((p.get("basic_profile") or {}).get("name") or "").strip()
        if not name or (keep_names is not None and name.lower() not in keep_names):
            continue
        schools = [{"school": s.get("school"), "degree": s.get("degree") or ""}
                   for s in ((p.get("education") or {}).get("schools")) or []
                   if isinstance(s, dict) and s.get("school")]
        out.append({"name": name, "schools": schools})
    return out


def _count_body(cid: int, extra: dict | None) -> dict:
    conds: list[dict] = [{"field": CURRENT_FIELD, "type": "=", "value": int(cid)}]
    if extra:
        conds.append(extra)
    return {"filters": {"op": "and", "conditions": conds},
            "fields": ["crustdata_person_id"], "limit": 1}


def _any_of(field_name: str, values: list[str]) -> dict:
    if len(values) == 1:
        return {"field": field_name, "type": "(.)", "value": values[0]}
    return {"op": "or", "conditions": [{"field": field_name, "type": "(.)", "value": v}
                                       for v in values]}


async def _total(client: Any, body: dict) -> int | None:
    try:
        r = await client.request("POST", "/person/search", body)
    except CrustError as e:
        log.warning("talent count failed: %s", e)
        return None
    t = r.get("total_count") if isinstance(r, dict) else None
    return int(t) if isinstance(t, (int, float)) else None


async def staff_counts(client: Any, cid: int, talent: Talent) -> Talent:
    """Fill indexed_staff, alumni and ex_big_tech from Person Search total_count."""
    talent.indexed_staff = await _total(client, _count_body(cid, None))
    for group, values in COUNT_QUERIES.items():
        n = await _total(client, _count_body(cid, _any_of(EDU_FIELD, values)))
        if n is not None:
            talent.alumni[group] = n
    talent.ex_big_tech = await _total(client, _count_body(cid, _any_of(PAST_EMPLOYER_FIELD, BIG_TECH)))
    if talent.ex_big_tech is None:
        talent.notes.append("ex-big-tech count unavailable")
    talent.notes.append("staff counts are indexed LinkedIn profiles currently at the company "
                        "(Crustdata Person Search); profiles without education listed are not counted")
    return talent


async def build_talent(client: Any, cid: int, rec: dict, country: str,
                       keep_names: set[str] | None = None, *, counts: bool = True) -> Talent:
    fs = founders_from_enrich(rec, keep_names)
    hits, with_elite, _ = founder_schools(fs, country)
    t = Talent(founder_schools=hits, founders_with_elite=with_elite, founders_total=len(fs))
    if counts:
        await staff_counts(client, cid, t)
    return t


def team_bonus(t: Talent | None) -> tuple[float, str]:
    """Team-pillar points for founder pedigree: +10 for a home-market elite degree, +6 for
    an elite degree elsewhere, and +4 more when >= 20% of indexed staff (and >= 3 people)
    are elite-school alumni. Capped at +14."""
    if t is None:
        return 0.0, ""
    pts, why = 0.0, []
    if any(h.home_market for h in t.founder_schools):
        h = next(h for h in t.founder_schools if h.home_market)
        pts += 10
        why.append(f"founder {h.person} studied at {h.label} (top tier for the home market)")
    elif t.founder_schools:
        h = t.founder_schools[0]
        pts += 6
        why.append(f"founder {h.person} studied at {h.label}")
    if t.indexed_staff and t.elite_staff >= 3 and t.elite_staff / t.indexed_staff >= 0.20:
        pts += 4
        why.append(f"{t.elite_staff} of {t.indexed_staff} indexed staff are elite-school alumni")
    return min(pts, 14.0), "; ".join(why)


_FOUNDER_TITLE = re.compile(r"\bco-?founder\b|\bfounder\b", re.I)
_NOT_FOUNDER = re.compile(r"assistant|\bto (the )?co-?founder|office of", re.I)


def credible_founders(founders: list, founded_year: int | None, slack_years: int = 4) -> list:
    """Drop founder rows that are namesake noise: no name, a title like 'Assistant to the
    Co-Founder', or no start date / a start more than `slack_years` after founding (common
    company names pick up unrelated 'Founder' profiles). Dedupes by name, keeping the row
    with the most prior employers."""
    best: dict[str, Any] = {}
    for f in founders:
        name = str(getattr(f, "name", "") or "").strip()
        title = str(getattr(f, "title", "") or "")
        since = str(getattr(f, "since", "") or "")
        if not name or _NOT_FOUNDER.search(title) or not _FOUNDER_TITLE.search(title):
            continue
        if founded_year and (not since[:4].isdigit() or int(since[:4]) > founded_year + slack_years):
            continue
        k = name.lower()
        if k not in best or len(f.prior_employers) > len(best[k].prior_employers):
            best[k] = f
    return list(best.values())


# ---- staff work history (D31b) -------------------------------------------------------
# Prestige employers beyond signals.NOTABLE_EMPLOYERS (big tech/scaleups): quant trading,
# banks/payments, consulting, and large R&D labs. Highlighted in the report only; the Team
# pillar keeps its own notable-employer rule.
PRESTIGE = {
    "quant": r"quadeye|tower research|jane street|citadel|two sigma|d\.? ?e\.? shaw|optiver|"
             r"hudson river|jump trading|graviton|alphagrep|squarepoint|millennium|worldquant|imc trading",
    "finance": r"goldman sachs|j\.?p\.? ?morgan|morgan stanley|visa\b|mastercard|american express|"
               r"blackrock|bank of america|barclays|deutsche bank",
    "consulting": r"mckinsey|boston consulting|\bbcg\b|bain & company|\bbain\b",
    "big tech / R&D": r"google|microsoft|amazon|meta\b|facebook|apple\b|samsung r&d|nvidia|adobe|"
                      r"qualcomm|intel\b|oracle|uber|flipkart|stripe|openai|deepmind",
}
_INTERN = re.compile(r"\bintern(ship)?\b|trainee|summer analyst", re.I)


@dataclass
class Role:
    title: str
    company: str
    start: str = ""
    end: str = ""
    intern: bool = False
    prestige: str = ""        # category from PRESTIGE, else ""


@dataclass
class PersonHistory:
    name: str
    current_title: str
    past: list[Role] = field(default_factory=list)

    @property
    def highlights(self) -> list[Role]:
        return [r for r in self.past if r.prestige]


def prestige_of(company: str) -> str:
    for cat, pat in PRESTIGE.items():
        if re.search(pat, company or "", re.I):
            return cat
    return ""


def _ym(s: Any) -> str:
    return str(s or "")[:7]


def staff_history(resp: Any, company_id: int, limit: int = 15) -> list[PersonHistory]:
    """Work history of sampled staff from a Person Search response that requested
    `experience.employment_details.past` (economics.sample_body). Internships are kept and
    labelled: they show where people were selected, which matters for early teams."""
    profiles = resp.get("profiles") if isinstance(resp, dict) else resp
    out = []
    for p in (profiles or [])[:limit]:
        if not isinstance(p, dict):
            continue
        det = ((p.get("experience") or {}).get("employment_details")) or {}
        cur = [e for e in det.get("current") or [] if isinstance(e, dict)]
        here = next((e for e in cur if e.get("company_id") == company_id), cur[0] if cur else {})
        roles = []
        for e in det.get("past") or []:
            if not isinstance(e, dict):
                continue
            co = str(e.get("company_name") or e.get("name") or "").strip()
            title = str(e.get("title") or "").strip()
            if not co:
                continue
            roles.append(Role(title, co, _ym(e.get("start_date")), _ym(e.get("end_date")),
                              bool(_INTERN.search(title)), prestige_of(co)))
        roles.sort(key=lambda r: r.start, reverse=True)
        out.append(PersonHistory(str((p.get("basic_profile") or {}).get("name") or ""),
                                 str(here.get("title") or ""), roles))
    return out
