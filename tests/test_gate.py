"""Code gate (plan v2 §5.4) on synthetic evidence: T-finance fin-3/4/10, date
precision in both directions, unknown IDs, clause drop vs suppression."""
from __future__ import annotations

import pytest

from proofroom import gate
from proofroom.models import Evidence, Finding


def ev(id_: str, value: str, kind: str = "source_passage", **kw) -> Evidence:
    return Evidence(id=id_, kind=kind, source=kw.pop("source", "https://example-startup.test/blog"),
                    value=value, **kw)


def E(*rows: Evidence) -> dict[str, Evidence]:
    return {r.id: r for r in rows}


def finding(cid: str, sentence: str, ids: list[str]) -> Finding:
    return Finding(claim_id=cid, disposition="supported", qualified=False,
                   basis=["company_statement"], sentence=sentence, evidence_ids=ids, as_of="",
                   correction_reason="", limitation="", question="")


# ---- parsing ---------------------------------------------------------------------

@pytest.mark.parametrize("text,value,currency,unit", [
    ("$20.5M", 20_500_000, "USD", 1e5),
    ("$20.5 million", 20_500_000, "USD", 1e5),
    ("US$5m", 5_000_000, "USD", 1e6),
    ("$52,020,932", 52_020_932, "USD", 1),
    ("£40m", 40_000_000, "GBP", 1e6),
    ("€44M", 44_000_000, "EUR", 1e6),
    ("₹50 crore", 500_000_000, "INR", 1e7),           # fin-3
    ("Rs 2 lakh", 200_000, "INR", 1e5),
    ("$1.25B", 1_250_000_000, "USD", 1e7),
    ("$1.25 billion", 1_250_000_000, "USD", 1e7),
    ("$116 million to date", 116_000_000, "USD", 1e6),
    ("20.5 million dollars", 20_500_000, "USD", 1e5),
    ("¥300M", 300_000_000, "unknown", 1e6),            # fin-4
    ("A$5M", 5_000_000, "unknown", 1e6),
])
def test_parse_amounts(text, value, currency, unit):
    [a] = gate.parse_amounts(f"It raised {text} last year.")
    assert (a.value, a.currency, a.unit) == (value, currency, unit)


def test_crore_is_never_converted():
    [a] = gate.parse_amounts("Example Startup raised ₹50 crore")
    assert a.currency == "INR" and a.value == 500_000_000
    facts = gate.evidence_facts([ev("E1", "raised $6M")])
    assert not any(gate.amount_matches(a, x) for x in facts.amounts)


def test_bare_numbers_and_years_are_not_money():
    assert [x.raw for x in gate.parse_amounts("in 2025 USD 5M, with 40 staff")] == ["USD 5M"]
    assert gate.parse_amounts("3 founders and 12 investors") == []


def test_parse_dates_and_years():
    got = [(d.iso, d.precision) for d in gate.parse_full_dates(
        "2026-02-24; 24/02/2026; 24 Feb 2026; Feb 24, 2026; Feb 2026; Aug '25; 2026-03")]
    assert got == [("2026-02-24", "day")] * 4 + [("2026-02", "month"), ("2025-08", "month"),
                                                 ("2026-03", "month")]
    years = [y.value for y in gate.parse_years("Founded in 2023, the seed closed on 7 Sep 2025.")]
    assert years == [2023]
    assert [p.value for p in gate.parse_percentages("a 12% stake and 4.5 percent")] == [12.0, 4.5]


def test_evidence_padded_dates_are_coarse():
    [d] = gate.parse_full_dates("pre_seed, 2024-01-01", evidence=True)
    assert (d.iso, d.precision) == ("2024", "year")
    [d] = gate.parse_full_dates("seed, 2025-09-07 (month)", evidence=True)
    assert (d.iso, d.precision) == ("2025-09", "month")


def test_normalize():
    assert gate.normalize("Koah’s “Series A” — done\n ok") == \
        'Koah\'s "Series A" - done ok'


# ---- the gate --------------------------------------------------------------------

GRAPH_A = ev("G5", "series_a, 2026-02-24 (day), $20,500,000, lead Example Ventures", kind="graph",
             source="/company/enrich", origin="indexed record (Crunchbase-derived)")


def test_fin10_rounded_sentence_passes_against_exact_record():
    evs = E(ev("G1", "series_b, 2025-08-12 (day), $52,020,932, lead Example Capital", kind="graph"))
    r = gate.gate_sentence("The record lists a $52M Series B.", ["G1"], evs)
    assert r.clean and r.counts["amounts"] == [1, 1]


def test_exact_sentence_fails_against_rounded_evidence():
    evs = E(ev("E1", "Example Startup raised $52M in its Series B."))
    r = gate.gate_sentence("Example Startup raised $52,020,932 in its Series B.", ["E1"], evs)
    assert r.suppressed and not r.passed
    assert "52,020,932" in r.failures[0]


def test_amount_value_and_currency_must_match():
    evs = E(GRAPH_A)
    assert gate.gate_sentence("Example Startup raised a $20.5M Series A.", ["G5"], evs).clean
    assert gate.gate_sentence("Example Startup raised a $21M Series A.", ["G5"], evs).suppressed
    assert gate.gate_sentence("Example Startup raised a $20M Series A.", ["G5"], evs).suppressed
    assert gate.gate_sentence("Example Startup raised a £20.5M Series A.", ["G5"], evs).suppressed


def test_fin4_unknown_currency_matches_only_same_symbol():
    evs = E(ev("E1", "The company raised ¤12M from angels."))
    assert gate.gate_sentence("The company raised ¤12M from angels.", ["E1"], evs).clean
    assert gate.gate_sentence("The company raised $12M from angels.", ["E1"], evs).suppressed


def test_fin3_crore_sentence_against_crore_and_digit_evidence():
    evs = E(ev("E1", "Example Startup has raised ₹50 crore (₹500,000,000) in a seed round."))
    assert gate.gate_sentence("Example Startup raised ₹50 crore in seed funding.", ["E1"], evs).clean
    assert gate.gate_sentence("Example Startup raised Rs 500,000,000 in seed funding.", ["E1"], evs).clean
    assert gate.gate_sentence("Example Startup raised $6M in seed funding.", ["E1"], evs).suppressed


def test_month_sentence_matches_day_evidence():
    r = gate.gate_sentence("Example Startup announced its Series A in Feb 2026.", ["G5"], E(GRAPH_A))
    assert r.clean and r.counts["dates"] == [1, 1]


def test_day_sentence_does_not_match_month_evidence():
    evs = E(ev("E1", "In Feb 2026 Example Startup announced a Series A."))
    r = gate.gate_sentence("Example Startup announced a Series A on 24 Feb 2026.", ["E1"], evs)
    assert r.suppressed
    r = gate.gate_sentence("Example Startup announced a Series A on 2026-02-24.", ["E1"], evs)
    assert r.suppressed


def test_padded_record_date_is_year_only():
    evs = E(ev("G2", "pre_seed, 2024 (year), $1,000,000, lead not recorded", kind="graph"))
    assert gate.gate_sentence("The record lists a $1M pre-seed in 2024.", ["G2"], evs).clean
    assert gate.gate_sentence("The record lists a $1M pre-seed on 1 Jan 2024.", ["G2"], evs).suppressed


def test_year_must_appear_in_cited_evidence_or_its_dates():
    evs = E(ev("E1", "We started building in 2023.", published="2026-02-24"))
    assert gate.gate_sentence("The founders started building in 2023.", ["E1"], evs).clean
    assert gate.gate_sentence("The post was published in 2026 by the company.", ["E1"], evs).clean
    assert gate.gate_sentence("The founders started building in 2021.", ["E1"], evs).suppressed


def test_percentages_exact():
    evs = E(ev("E1", "Investors hold a 12.5% stake."))
    assert gate.gate_sentence("Investors hold a 12.5% stake in the company.", ["E1"], evs).clean
    assert gate.gate_sentence("Investors hold a 13% stake in the company.", ["E1"], evs).suppressed


def test_unknown_evidence_id_is_a_failure_and_removed():
    r = gate.gate_sentence("Example Startup raised a $20.5M Series A.", ["G5", "E99"], E(GRAPH_A))
    assert r.passed and not r.suppressed and r.evidence_ids == ["G5"]
    assert any("E99" in f for f in r.failures)


def test_only_unknown_ids_suppresses():
    r = gate.gate_sentence("Example Startup raised a Series A.", ["E99"], E(GRAPH_A))
    assert r.suppressed and any("E99" in f for f in r.failures)
    assert gate.gate_sentence("Example Startup raised a Series A.", [], E(GRAPH_A)).suppressed


def test_inline_citations_are_checked_too():
    r = gate.gate_sentence("Example Startup raised a $20.5M Series A [G5][E42].", [], E(GRAPH_A))
    assert r.passed and r.evidence_ids == ["G5"] and any("E42" in f for f in r.failures)


def test_failing_trailing_clause_is_dropped():
    s = ("Example Startup raised a $20.5M Series A led by Example Ventures on 24 Feb 2026, "
         "with Second Fund participating on 3 Mar 2026.")
    r = gate.gate_sentence(s, ["G5"], E(GRAPH_A))
    assert r.passed and not r.suppressed
    assert r.sentence == "Example Startup raised a $20.5M Series A led by Example Ventures on 24 Feb 2026."
    assert r.dropped_clauses == ["Second Fund participating on 3 Mar 2026"]
    assert r.failures and "clause dropped" in r.failures[0]


def test_failure_in_main_clause_suppresses():
    s = "Example Startup raised a $25M Series A, with Second Fund participating."
    r = gate.gate_sentence(s, ["G5"], E(GRAPH_A))
    assert r.suppressed and "suppressed" in r.failures[0]


def test_short_remainder_is_suppressed_not_kept():
    r = gate.gate_sentence("It raised $20.5M; and $9M in 2019.", ["G5"], E(GRAPH_A))
    assert r.suppressed


def test_gate_findings_splits_kept_and_suppressed():
    fs = [finding("C1", "Example Startup raised a $20.5M Series A in Feb 2026.", ["G5"]),
          finding("C2", "Example Startup raised a $30M Series A.", ["G5"]),
          finding("C3", "Example Startup raised a $20.5M Series A.", ["G5", "E7"])]
    kept, suppressed, lims = gate.gate_findings(fs, [GRAPH_A])
    assert [f.claim_id for f in kept] == ["C1", "C3"]
    assert kept[1].evidence_ids == ["G5"]
    assert [f.claim_id for f, _ in suppressed] == ["C2"]
    assert any(x.startswith("C2:") and "withheld" in x for x in lims)
    assert any(x.startswith("C3:") and "E7" in x for x in lims)
