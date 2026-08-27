"""Focused tests: proactive-intelligence orchestration + presentation contract.

Three systemic owners fixed:
  1. The proactive opportunity loop was DEAD CODE (offer_media never called).
     It is now wired after topic answers with restraint rules.
  2. The opportunity model fired on ANY "what is X" question (educational
     video offer after general-knowledge queries) — the keywords now require
     media-SEEKING intent.
  3. Verification synthesis was instructed to literally start with
     "Bottom line:" — the report-template contamination. The prompt now
     requires a natural verdict with no fixed label.
"""
import logging
import sys

logging.basicConfig(level=logging.CRITICAL)

sys.path.insert(0, ".")
from mini_kio.media import media_discovery as md
from mini_kio.media.media_discovery import MediaDiscovery


def test_opportunity_fires_on_media_seeking_query():
    d = MediaDiscovery()
    o = d.detect_opportunity("what's the latest on the new Marvel movie")
    assert o is not None
    assert o["media_type"] in ("movie_trailer", "news")
    o2 = d.detect_opportunity("show me the new trailer")
    assert o2 is not None


def test_opportunity_restrained_on_general_questions():
    """'what is the capital of France' must NOT offer a video — the bare
    educational openers were the over-eagerness source."""
    d = MediaDiscovery()
    assert d.detect_opportunity("what is the capital of France") is None
    assert d.detect_opportunity("what is a black hole") is None
    assert d.detect_opportunity("explain how the economy works") is None
    assert d.detect_opportunity("I've been watching The Big Bang Theory again") is None


def test_opportunity_fires_on_current_news():
    d = MediaDiscovery()
    o = d.detect_opportunity("latest news on the new sequel")
    assert o is not None


def test_offer_templates_are_kio_voiced():
    """No robotic search-bot phrasing ('I found the official trailer. Would
    you like me to play it?') — offers read like KIO conversation."""
    for tpl in md._MEDIA_OFFER_TEMPLATES.values():
        assert "I found the official trailer" not in tpl
        assert "Want me to play it?" not in tpl
        assert "Would you like me to play it" not in tpl
        assert tpl.strip()


def test_opportunity_keywords_require_media_intent():
    """The keyword list must not contain bare general-question openers that
    pair with EDUCATIONAL to fire on any question."""
    kws = " ".join(md._OPPORTUNITY_KEYWORDS)
    for bare in ("what is", "tell me about", " explain ", "why is"):
        assert bare not in f" {kws} ", bare


def test_verification_prompt_no_bottom_line_label():
    """The synthesis prompt must not INSTRUCT the literal 'Bottom line:'
    label — that instruction was the report-template contamination source.
    (The prompt may name the label as a forbidden example; what matters is
    it must not tell the model to START with it.)"""
    import inspect
    # The prompt lives in the adapter module, so check the adapter source.
    from mini_kio.media.intelligence import integration_adapter as ia
    asrc = inspect.getsource(ia)
    # The old instruction that made the model mirror the label is gone.
    assert "Start with the bottom line" not in asrc
    # The replacement requires a natural, label-free verdict up front.
    assert "NOT as a fixed label" in asrc
    assert "report-style" in asrc
