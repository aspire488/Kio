"""
KIO identity / operational routing regression tests — 2026-08-10 batch.

Covers the root mechanisms behind the live failures:
1.  KIO-as-self wins over general knowledge (health/status/uptime families
    route deterministically — never the LLM).
2.  Typo/contraction/punctuation/casual-language tolerant canonicalization
    ("Kio heath", "how's kio's health", "u good kio?", "KIO status?").
3.  KIO-as-assistant vs KIO-as-external-entity boundary
    ("Tell me about KIO Systems" stays knowledge, "What is KIO?" is identity).
4.  Anti-fabrication guard: the LLM may never address the user by an invented
    name, and conversation prompts forbid it.
5.  No regression to existing deterministic families (desktop state, open,
    greetings).

Classification assertions are intent/action-level (deterministic contract),
never output-phrase-level.
"""

import os

os.environ.setdefault("KIO_TEST_MODE", "1")

from mini_kio.core.pipeline import Pipeline, _sanitize_llm_name_address
from mini_kio.core.pipeline.types import IntentType

p = Pipeline()


def classify(text: str):
    return p._classifier.classify(text, text)


# ---------------------------------------------------------------------------
# 1. KIO-self health/status/uptime family (all variants, never LLM)
# ---------------------------------------------------------------------------

HEALTH_PROBES = [
    "KIO health",
    "kio health",
    "Kio heath",                      # typo
    "KIO's health",
    "How's Kio's health",
    "how's KIO health",
    "how is KIO doing",
    "KIO ok?",
    "kio okay",
    "u good KIO?",
    "you good?",
    "hey kio, you alright?",
    "KIO still running?",
    "kio still up",
    "how's your health, KIO?",
    "are you okay",
    "are you ok",
    "is everything ok",
    "everything ok?",
    "KIO running?",
]

STATUS_PROBES = [
    "KIO status?",
    "kio status",
    "KIO's status",
    "kio state",
    "are you there",
]

UPTIME_PROBES = [
    "KIO uptime",
    "kio's uptime",
    "how long have you been running",
]


def _assert_operational(text: str, action: str):
    d = classify(text)
    assert d.intent_type == IntentType.OPERATIONAL, f"{text!r} -> {d.intent_type}"
    assert d.action == action, f"{text!r} -> action {d.action!r} != {action!r}"


def test_health_family_routes_deterministically():
    for probe in HEALTH_PROBES:
        _assert_operational(probe, "health")


def test_status_family_routes_deterministically():
    for probe in STATUS_PROBES:
        _assert_operational(probe, "status")


def test_uptime_family_routes_deterministically():
    for probe in UPTIME_PROBES:
        _assert_operational(probe, "uptime")


def test_kio_self_responses_are_state_grounded_not_llm():
    """Full pipeline: health probes produce a deterministic operational
    message (truthful state), never an LLM-generated 'I'm doing great'."""
    for probe in ("kio heath", "How's Kio's health", "KIO ok?"):
        r = p.run(probe, session_id="local_0")
        assert r.get("success") is True
        msg = str(r.get("message") or "")
        assert "KIO is" in msg or "Uptime" in msg, f"{probe!r} -> {msg!r}"


# ---------------------------------------------------------------------------
# 2. KIO conversational identity (deterministic, never fabricated biography)
# ---------------------------------------------------------------------------

GREETING_PROBES = [
    "how are you",
    "how're you",
    "How are you, KIO?",
    "hey KIO",
    "hey kio, what's up",
    "what's up",
    "whats up",
    "how's it going",
    "how is it going",
    "you there?",
]


def test_greeting_family_routes_to_greeting():
    for probe in GREETING_PROBES:
        d = classify(probe)
        assert d.intent_type in (IntentType.GREETING, IntentType.SOCIAL), (
            f"{probe!r} -> {d.intent_type}"
        )


# ---------------------------------------------------------------------------
# 3. KIO-as-assistant vs KIO-as-external-entity
# ---------------------------------------------------------------------------

def test_what_is_kio_is_identity():
    for probe in ("What is KIO?", "who is kio", "what's kio"):
        d = classify(probe)
        assert d.intent_type == IntentType.IDENTITY, f"{probe!r} -> {d.intent_type}"


def test_kio_external_entity_stays_knowledge():
    """'Tell me about KIO Systems' is an external-entity query, never
    self-identity."""
    for probe in (
        "Tell me about KIO Systems",
        "tell me about kio corporation",
        "what is kio technologies",
    ):
        d = classify(probe)
        assert d.intent_type != IntentType.IDENTITY, f"{probe!r} -> identity"
        assert d.intent_type in (
            IntentType.INFORMATION,
            IntentType.ENTITY_QUERY,
            IntentType.CONVERSATION,
        ), f"{probe!r} -> {d.intent_type}"


# ---------------------------------------------------------------------------
# 4. Anti-fabrication guard
# ---------------------------------------------------------------------------

def test_sanitize_strips_invented_name_fragment():
    out = _sanitize_llm_name_address("Hey, it sounds pretty serious. Peter")
    assert "Peter" not in out
    assert "serious" in out


def test_sanitize_rewrites_greeting_name_address():
    out = _sanitize_llm_name_address("Hey, Peter, how can I help?")
    assert "Peter" not in out
    assert out.startswith("Hey")


def test_sanitize_keeps_single_sentence_proper_nouns():
    assert _sanitize_llm_name_address("The company is OpenAI.") == "The company is OpenAI."


def test_sanitize_keeps_known_names():
    assert "Joel" in _sanitize_llm_name_address("Hi Joel, everything ready.")


def test_conversation_prompt_forbids_name_invention():
    """The LLM system prompt must forbid inventing user identity."""
    from mini_kio.core.pipeline import _ExecutionCoordinator
    import inspect

    src = inspect.getsource(_ExecutionCoordinator._chat_converse)
    assert "NEVER invent the user's name" in src
    assert "Never address the user by any name" in src


# ---------------------------------------------------------------------------
# 5. No regression to existing deterministic families
# ---------------------------------------------------------------------------

def test_existing_deterministic_families_unchanged():
    cases = [
        ("what's open", IntentType.BROWSER_TABS),
        ("KIO what's open", IntentType.BROWSER_TABS),
        ("which apps are open", IntentType.BROWSER_TABS),
        ("open chrome", IntentType.DESKTOP_OPEN),
        ("open chatgpt in chrome", IntentType.BROWSER_NAVIGATE),
        ("close chrome", IntentType.DESKTOP_CLOSE),
        ("hey KIO", IntentType.GREETING),
        ("play messi highlights", IntentType.MEDIA_PLAY),
        ("search python tutorial", IntentType.SEARCH),
        # knowledge, not operational — INFORMATION/CONVERSATION both OK
        ("what is uptime", (IntentType.INFORMATION, IntentType.CONVERSATION)),
    ]
    for text, expected in cases:
        d = classify(text)
        expected_set = expected if isinstance(expected, tuple) else (expected,)
        assert d.intent_type in expected_set, f"{text!r} -> {d.intent_type} != {expected_set}"


def test_knowledge_query_sharing_words_stays_knowledge():
    """A knowledge question that merely shares words with an operational
    family must NOT become an operational response."""
    for probe in ("what is open source", "what is running time", "what is uptime"):
        d = classify(probe)
        assert d.intent_type != IntentType.OPERATIONAL, f"{probe!r} -> operational"


def test_typo_correction_is_bounded():
    """'help' is far enough from 'health' that knowledge intent stays intact."""
    d = classify("help")
    assert d.intent_type in (IntentType.CONVERSATION, IntentType.SOCIAL, IntentType.UNKNOWN)
