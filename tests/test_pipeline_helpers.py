"""Pipeline helpers: excerpt boundaries, exception-desk placement, round parsing."""
from proofroom import pipeline


def test_context_starts_at_a_real_sentence_boundary():
    text = ("Intro line. SAN FRANCISCO, Feb. 24, 2026 /PRNewswire/ -- Koah today announced "
            "a $20.5 million Series A. Next sentence.")
    a = text.index("today announced")
    out = pipeline._context(text, (a, a + 15))
    assert out.startswith("SAN FRANCISCO, Feb. 24, 2026") and out.endswith("Series A.")


def test_desk_goes_before_the_first_section():
    brief = "# Title\n\nheader line\n\n## From the sources\n\n1. x\n"
    out = pipeline._with_desk(brief, "**Needs a person: 0.**\n")
    assert out.index("header line") < out.index("## Needs a person") < out.index("## From the sources")


def test_round_type_and_date_parsing():
    assert pipeline._round_type("a $20.5 million Series A funding round") == "series_a"
    assert pipeline._round_type("pre-seed") == "pre_seed"
    assert pipeline._round_type("a $99M tender offer") == "secondary_market"
    assert pipeline._iso_from_text("today (Feb. 24, 2026)") == "2026-02-24"
    assert pipeline._iso_from_text("September 2025") == "2025-09"
    assert pipeline._iso_from_text("recently") == ""


def test_prior_employer_names_split_collective_claims():
    from proofroom.models import Claim
    c = Claim(id="C1", doc_id="D1", quote="q", family="F2", predicate="previously_worked_at",
              subject="the founders", object="Affirm, Supermove, & Qualified", amount_text="",
              currency_text="", date_text="", title_text="", qualifiers="", materiality="high",
              selected=True, exclusion_reason="")
    assert pipeline._prior_employer_names([c]) == ["Affirm", "Supermove", "Qualified"]
