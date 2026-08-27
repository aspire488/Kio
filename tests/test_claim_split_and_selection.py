"""Focused tests: arbitrary-N claim decomposition and claim-selection referents.

Covers the canonical owners changed for universal proposition handling:
- _split_claims must decompose comma-separated independent clauses (including
  lowercase subjects like "spotify bought...") into one claim each, never
  collapse them into a single claim that makes synthesis wander into evidence.
- Verification tails ("which of those is actually true", "what's true") are
  ASKS, never claims.
- Relative-clause commas ("which released in 2024", "who is known for")
  never split.
- _is_claim_selection_referent recognizes "the second one" / "which part is
  true" so they route to verification (reclaim) instead of artifact selection
  or the conversational LLM (which contradicted verified evidence from memory).
"""
import logging
import sys

logging.basicConfig(level=logging.CRITICAL)

sys.path.insert(0, ".")
from mini_kio.media.intelligence.integration_adapter import (
    MediaIntelligenceAdapter,
    _is_claim_selection_referent,
)


def _split(q):
    return MediaIntelligenceAdapter._split_claims(q)


# ── arbitrary-N claim decomposition ─────────────────────────────────────────
def test_three_propositions_with_capitalized_subjects():
    claims = _split(
        "I heard SpaceX launched a new rocket, Spotify bought a podcast "
        "company, and the new season of Stranger Things got delayed. "
        "Which of those is actually true?"
    )
    assert claims == [
        "SpaceX launched a new rocket",
        "Spotify bought a podcast company",
        "the new season of Stranger Things got delayed",
    ]


def test_three_propositions_with_lowercase_subject():
    """A lowercase entity after a comma (\"spotify bought...\") must still
    split — the fragment is an independent clause with an event verb, not a
    relative-clause continuation."""
    claims = _split(
        "I heard SpaceX launched a new rocket, spotify bought a podcast "
        "company, and the new season of Stranger Things got delayed. "
        "Which of those is actually true?"
    )
    assert claims == [
        "SpaceX launched a new rocket",
        "spotify bought a podcast company",
        "the new season of Stranger Things got delayed",
    ]


def test_four_propositions_nested_clause():
    """Verb sits 6 words after the comma (\"the director of the new Avengers
    movie quit\") — the bounded event-verb lookahead must still fire."""
    claims = _split(
        "I heard Nintendo announced a new console, the director of the new "
        "Avengers movie quit, and a legendary actor passed away. "
        "Which of those is actually true?"
    )
    assert claims == [
        "Nintendo announced a new console",
        "the director of the new Avengers movie quit",
        "a legendary actor passed away",
    ]


def test_single_letter_labels():
    claims = _split(
        "I heard A happened, B got cancelled, C left the company and D is "
        "coming back. What is actually true?"
    )
    assert claims == [
        "A happened",
        "B got cancelled",
        "C left the company",
        "D is coming back",
    ]


def test_relative_clause_commas_never_split():
    claims = _split(
        "The movie, which released in 2024, was directed by Nolan, who is "
        "known for Inception"
    )
    assert len(claims) == 1


def test_two_proposition_conjunction():
    claims = _split(
        "Messi father passed away and he said he cannot play long anymore"
    )
    assert claims == [
        "Messi father passed away",
        "he said he cannot play long anymore",
    ]


def test_verification_tail_not_a_claim():
    claims = _split("Is it true that Messi is retiring?")
    assert claims == ["Messi is retiring"]


def test_selection_tail_not_a_claim():
    """'Which of those is actually true?' is the ASK, never a claim — it must
    not occupy a claim slot (it would corrupt the ordinal index of a later
    'the second one')."""
    claims = _split(
        "I heard A happened, B got cancelled. Which of those is actually true?"
    )
    assert "which of those is actually true" not in [c.lower() for c in claims]
    assert claims == ["A happened", "B got cancelled"]


# ── claim-selection referents ───────────────────────────────────────────────
def test_selection_referent_recognized():
    for q in [
        "which part is true",
        "the second one",
        "the first one",
        "which one",
        "which of those is real",
        "what's actually true",
    ]:
        assert _is_claim_selection_referent(q), q


def test_non_selection_not_misrouted():
    for q in [
        "which movie is better",
        "the second half was great",
        "which part of the movie did you like",
        "what's the latest on the new iPhone",
    ]:
        assert not _is_claim_selection_referent(q), q
