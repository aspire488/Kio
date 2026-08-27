"""Focused tests: action-intent routing + answer-depth/relevance mechanisms.

Systemic owners fixed this session:
  1. Action requests (\"show me the trailer\", \"show the highlights\") fell to
     the conversational LLM, which HALLUCINATED a fake resource URL
     (youtube.com/watch?v=example-trailer-id). They now route to the
     accept_offer/play action path that only ever returns real provider
     results, and the converse prompt forbids inventing URLs.
  2. Simple factual questions (\"what's the capital of Japan\") produced
     tourism paragraphs instead of answering first. The composer prompt now
     requires answering the ACTUAL question directly, with the question text
     included in the prompt.
  3. Role questions (\"who wrote Dune\") hit RELEVANCE_REJECT because the
     role-stem bypass missed inflected forms (\"wrote\" vs \"writ\") — the
     correctly retrieved author page was rejected and the answer fell to
     \"I don't have information.\"
"""
import logging
import sys

logging.basicConfig(level=logging.CRITICAL)

sys.path.insert(0, ".")
from mini_kio.core.runtime import bootstrap_runtime
bootstrap_runtime()

from mini_kio.core.pipeline import Pipeline
from mini_kio.core.context_manager import get_session_context
from mini_kio.media.intelligence.integration_adapter import MediaIntelligenceAdapter


def _route(q):
    p = Pipeline()
    ctx = get_session_context("act_depth")
    norm = p._normalizer.run(q, ctx)
    d = p._classifier.classify(norm, q)
    return d.intent_type.value, d.action


def test_show_media_noun_routes_to_accept_offer():
    for q in ("show me the trailer", "show the trailer", "show me the highlights",
              "show me the latest trailer", "show me the interview", "show me the clip"):
        intent, action = _route(q)
        assert action == "accept_offer", (q, action)
        assert intent == "conversation"


def test_show_nonmedia_stays_conversational():
    intent, action = _route("show me how that works")
    assert action == "converse", (intent, action)


def test_play_trailer_routes_to_media_play():
    intent, action = _route("play the trailer")
    assert action == "play"


def test_factual_questions_unchanged():
    intent, action = _route("why is the sky blue")
    assert action == "information_query"


def test_converse_prompt_forbids_fabricated_resources():
    import inspect
    from mini_kio.core.pipeline import _ExecutionCoordinator
    src = inspect.getsource(_ExecutionCoordinator._chat_converse)
    assert "NEVER invent URLs" in src
    assert "fabricate" in src.lower()
    # The guard must tell the model a fake link is worse than fetching one.
    assert "never fabricate one" in src


def test_answer_composer_answers_actual_question():
    import inspect
    from mini_kio.media.intelligence.answer_composer import AnswerComposer
    src = inspect.getsource(AnswerComposer._summarize_with_llm)
    assert "The user's question was:" in src
    assert "Answer THAT question" in src
    assert "DIRECTLY first" in src


def test_role_stem_relevance_covers_inflected_forms():
    """'who wrote the book Dune' must NOT be RELEVANCE_REJECTed — the role
    stem bypass previously missed the inflected 'wrote' and the correctly
    retrieved author page was thrown away."""
    adapter = object.__new__(MediaIntelligenceAdapter)
    raw = "Frank Herbert's Dune " + "x" * 200
    assert adapter._is_relevant(raw, "who wrote the book Dune", "book Dune") is True
    assert adapter._is_relevant(raw, "who directed inception", "inception") is True
    assert adapter._is_relevant(raw, "who composed the soundtrack", "soundtrack") is True
