"""
test_discourse_context_routing.py

Focused tests for the canonical owner of conversational continuity:
"context outranks surface form". The classifier commits to
ENTITY_QUERY/INFORMATION from the latest message alone ("Wbt fight club"
looks like a capitalized proper-noun phrase). Pipeline._apply_discourse_context_override
re-routes such surface-form research decisions back to CONVERSATION when the
message continues the ongoing discussion — while genuine information requests
(release dates, casts, news, verification/currentness frames) are NEVER
re-routed.

General categories covered (no per-entity or abbreviation-dictionary cases):
  - contextual abbreviation ("Wbt X" = "what about X")
  - bare noun phrase inside an active conversational thread
  - callback/comparison morphology ("instead of", "u said", "the one you")
  - previous-KIO-statement callbacks ("you said X earlier")
  - multi-thread referents ("that other one", "going back to that")
  - conversational vs research routing (currentness preserved)

Tests assert ROUTE and CONTEXT, never exact response wording.
"""

import pytest

from mini_kio.core.context_manager import clear_session_context, get_session_context
from mini_kio.core.pipeline import Pipeline
from mini_kio.core.pipeline.types import IntentType


@pytest.fixture(autouse=True)
def _fresh_sessions():
    clear_session_context("discourse_test")
    clear_session_context("research_test")
    clear_session_context("fresh_test")
    yield
    clear_session_context("discourse_test")
    clear_session_context("research_test")
    clear_session_context("fresh_test")


def _run(p: Pipeline, session: str, msg: str):
    """Simulate one full pipeline turn: normalize -> classify -> override,
    then commit the exchange so the next turn sees the history."""
    ctx = get_session_context(session)
    norm = p._normalizer.run(msg, ctx)
    d = p._classifier.classify(norm, msg)
    d = p._apply_discourse_context_override(d, msg, ctx)
    result = {"success": True, "message": "[reply]", "action": d.action, "target": d.target}
    ctx.update(result, norm)
    ctx.append_exchange(norm, result["message"])
    return d


# ── The exact live failure sequence ─────────────────────────────────────────

def test_live_failure_sequence_stays_conversational():
    p = Pipeline()
    sequence = [
        "what movie should I watch tonight",
        "Wbt fight club",
        "No I mean the movie fight club",
        "Wbt watching it tonight instead of arrival u said of",
    ]
    for msg in sequence:
        d = _run(p, "discourse_test", msg)
        assert d.intent_type == IntentType.CONVERSATION, (
            f"{msg!r} must route to CONVERSATION (got {d.intent_type})"
        )


# ── Contextual abbreviation (morphological, never a dictionary) ────────────

@pytest.mark.parametrize("msg", [
    "Wbt fight club", "Wbt Dune?", "Wbu Interstellar", "Wb Arrival",
    "tbh Dune", "Hbu that movie",
])
def test_contextual_abbreviation_routes_conversation(msg):
    p = Pipeline()
    d = _run(p, "discourse_test", msg)
    assert d.intent_type == IntentType.CONVERSATION
    assert d.action == "converse"


def test_allcaps_acronym_is_not_a_discourse_opener():
    # "GTA" / "NBA" are entity names, never compressed discourse words.
    p = Pipeline()
    d = _run(p, "fresh_test", "GTA")
    assert d.intent_type == IntentType.ENTITY_QUERY


# ── Bare noun phrase inside an active conversational thread ─────────────────

def test_bare_noun_phrase_in_thread_is_conversation():
    p = Pipeline()
    _run(p, "discourse_test", "what movie should I watch tonight")
    d = _run(p, "discourse_test", "And Marvel?")
    assert d.intent_type == IntentType.CONVERSATION
    d = _run(p, "discourse_test", "Maybe Dune?")
    assert d.intent_type == IntentType.CONVERSATION


def test_bare_entity_without_thread_stays_entity():
    p = Pipeline()
    d = _run(p, "fresh_test", "Tom Holland")
    assert d.intent_type == IntentType.ENTITY_QUERY


# ── Callback / comparison morphology ────────────────────────────────────────

@pytest.mark.parametrize("msg", [
    "what about Dune instead?",
    "would you pick it over Arrival?",
    "would you choose it over Interstellar?",
    "are they better than the ones you mentioned?",
    "you said Arrival was better earlier though",
    "the second one",
    "what about that other one?",
    "going back to that",
])
def test_callback_and_comparison_frames_are_conversational(msg):
    p = Pipeline()
    d = _run(p, "discourse_test", msg)
    assert d.intent_type == IntentType.CONVERSATION


# ── Previous-KIO-statement callback ─────────────────────────────────────────

def test_previous_kio_statement_callback_is_conversational():
    p = Pipeline()
    _run(p, "discourse_test", "what movie should I watch tonight")
    d = _run(p, "discourse_test", "you said Arrival was better earlier though")
    assert d.intent_type == IntentType.CONVERSATION


# ── Conversational vs research routing (currentness preserved) ──────────────

@pytest.mark.parametrize("msg", [
    "What's the latest on Messi?",
    "did Tom Holland actually say he is taking a break",
    "is it true that the new iPhone got delayed",
    "Is the new Marvel trailer out?",
    "Wbt the latest on Messi",
    "Wbu the new iPhone release date?",
])
def test_currentness_requests_stay_on_research_path(msg):
    p = Pipeline()
    # Run inside an active conversational thread — currentness must NOT be
    # swallowed by the discourse override.
    _run(p, "research_test", "what movie should I watch tonight")
    d = _run(p, "research_test", msg)
    assert d.intent_type in (IntentType.INFORMATION, IntentType.ENTITY_QUERY)
    assert d.action == "information_query"


@pytest.mark.parametrize("msg", [
    "Fight Club cast",
    "Spider-Man 4 release date",
    "Interstellar cast",
])
def test_entity_lookups_stay_entity_even_in_thread(msg):
    p = Pipeline()
    _run(p, "research_test", "what movie should I watch tonight")
    d = _run(p, "research_test", msg)
    assert d.intent_type == IntentType.ENTITY_QUERY


# ── Multi-thread referents ──────────────────────────────────────────────────

def test_multi_thread_referent_resolution_routes_conversation():
    p = Pipeline()
    # Thread A: football -> Thread B: movies. A referent continuation after
    # the movie thread must stay CONVERSATION (the generator resolves it with
    # the full history; routing must not send "that other one" to retrieval).
    _run(p, "discourse_test", "what about the Messi transfer rumors")
    _run(p, "discourse_test", "And Marvel?")
    d = _run(p, "discourse_test", "what about that other one?")
    assert d.intent_type == IntentType.CONVERSATION


# ── Command thread does not open conversational override ────────────────────

def test_command_thread_does_not_swallow_entity_queries():
    p = Pipeline()
    _run(p, "discourse_test", "open chrome")
    # A bare entity after a COMMAND thread is a fresh lookup, not a topic
    # mention — the override must not fire.
    d = _run(p, "discourse_test", "Tom Holland")
    assert d.intent_type == IntentType.ENTITY_QUERY


# ── Session identity survives the discourse override ───────────────────────
# Live bug: the override built a FRESH RoutingDecision whose session_id
# defaulted to "local_0", so the conversational generator read an EMPTY
# session context — history missing, generic "we haven't discussed that"
# answers. run() sets session_id/channel/user_id between classify() and the
# override, so the replacement decision must carry them forward.

def _run_with_identity(p: Pipeline, session: str, msg: str, channel="telegram", user_id=777):
    """Mirror run(): set session identity on the decision BEFORE the
    discourse override, then apply the override — exactly what run() does."""
    ctx = get_session_context(session)
    norm = p._normalizer.run(msg, ctx)
    d = p._classifier.classify(norm, msg)
    d.session_id = session
    d.channel = channel
    d.user_id = user_id
    d = p._apply_discourse_context_override(d, msg, ctx)
    return d


def test_override_preserves_session_identity():
    p = Pipeline()
    # Open a conversational thread so the bare-noun override fires.
    ctx = get_session_context("session_preserve_test")
    ctx.append_exchange("what movie should I watch tonight", "I'd go with Arrival.")
    d = _run_with_identity(p, "session_preserve_test", "why did you prefer that one")
    assert d.intent_type == IntentType.CONVERSATION
    # The replacement decision MUST keep the caller's session identity — a
    # fresh default would be "local_0"/unknown and the generator would read
    # the wrong (empty) context.
    assert d.session_id == "session_preserve_test", (
        f"override dropped session_id -> {d.session_id!r}"
    )
    assert d.channel == "telegram"
    assert d.user_id == 777


def test_override_history_reaches_conversational_prompt(monkeypatch):
    """End-to-end: the overridden decision must let _chat_converse build a
    prompt that contains the seeded history (the Arrival recommendation)."""
    import mini_kio.llm.llm_ops as llm_ops

    captured = {}

    def spy(text, system_prompt=None, **kw):
        captured["prompt"] = system_prompt
        captured["text"] = text
        raise RuntimeError("_stop")

    monkeypatch.setattr(llm_ops, "ask_llm_sync", spy)
    p = Pipeline()
    ctx = get_session_context("session_preserve_test")
    ctx.append_exchange("6!", "720")
    ctx.append_exchange(
        "what movie should I watch tonight",
        "I'd go with Arrival — it mixes thoughtful sci-fi premises.",
    )
    try:
        p.run(
            "why did you prefer that one",
            session_id="session_preserve_test",
            channel="telegram",
            user_id=777,
        )
    except RuntimeError:
        pass
    prompt = captured.get("prompt") or ""
    assert "Recent conversation" in prompt, "history section missing from prompt"
    assert "Arrival" in prompt, "the recommendation must be in the prompt history"
