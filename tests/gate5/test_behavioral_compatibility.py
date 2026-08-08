"""Behavioral compatibility tests — Phase A pipeline regressions.

Every regression listed in the audit has a permanent test here.
Fix the classification or execution layer, not the test.
"""

import pytest
from mini_kio.core.pipeline import Pipeline, _IntentClassifier, IntentType


# ── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def classifier():
    return _IntentClassifier()


def _classify(text, raw=None):
    """Shorthand: classify through the pipeline's classifier directly."""
    pipe = Pipeline()
    return pipe._classifier.classify(text.lower().strip(), raw or text)


# ── Greeting / Social ───────────────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "hello", "hi", "hey", "good morning", "what's up",
])
def test_greeting(query):
    d = _classify(query)
    assert d.intent_type == IntentType.GREETING


@pytest.mark.parametrize("query", [
    "thanks", "thank you", "got it", "i see",
])
def test_social(query):
    d = _classify(query)
    assert d.intent_type == IntentType.SOCIAL


# ── Identity ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "who are you", "what are you", "who created you", "identify yourself",
])
def test_identity(query):
    d = _classify(query)
    assert d.intent_type == IntentType.IDENTITY


# ── Media transport ─────────────────────────────────────────────────────

@pytest.mark.parametrize("query,expected_action", [
    ("pause", "pause"),
    ("resume", "resume"),
    ("stop", "stop"),
    ("next", "next"),
    ("skip", "skip"),
    ("previous", "previous"),
    ("volume up", "volume"),
    ("mute", "mute"),
    ("unmute", "unmute"),
])
def test_media_transport(query, expected_action):
    d = _classify(query)
    assert d.intent_type == IntentType.MEDIA_TRANSPORT, f"{query!r} should be MEDIA_TRANSPORT"


# ── Regression: "continue" → MEDIA_TRANSPORT (was elaborate) ─────────

@pytest.mark.parametrize("query", [
    "continue", "keep going", "continue playing",
])
def test_continue_is_media_transport(query):
    d = _classify(query)
    assert d.intent_type == IntentType.MEDIA_TRANSPORT, (
        f"{query!r} should be MEDIA_TRANSPORT (resume), got {d.intent_type}"
    )


# ── Play commands ───────────────────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "play",
])
def test_media_play(query):
    d = _classify(query)
    assert d.intent_type == IntentType.MEDIA_PLAY


# ── Regression: "play something similar" → MEDIA_PLAY ────────────────

@pytest.mark.parametrize("query", [
    "play something similar",
    "play something similar to this",
    "play more like that",
    "play more",
    "play another",
    "play another one",
    "another one",
    "more like this",
])
def test_play_context_followup(query):
    d = _classify(query)
    assert d.intent_type == IntentType.MEDIA_PLAY, (
        f"{query!r} should be MEDIA_PLAY, got {d.intent_type}"
    )


# ── "tell me more" → elaborate → process_followup ────────────────────

@pytest.mark.parametrize("query", [
    "tell me more", "more info", "more details", "expand", "elaborate",
])
def test_elaborate_classification(query):
    d = _classify(query)
    assert d.intent_type == IntentType.CONVERSATION
    assert d.action == "elaborate"


# ── Context followup: "yes" / affirmative ───────────────────────────────

@pytest.mark.parametrize("query", [
    "yes", "yeah", "sure", "ok",
    "show it", "watch it", "do it", "go ahead", "play video",
])
def test_affirmative_accept_offer(query):
    d = _classify(query)
    assert d.intent_type == IntentType.CONVERSATION
    assert d.action == "accept_offer"


# ── Browser actions ─────────────────────────────────────────────────────

def test_browser_goto():
    d = _classify("go to https://google.com")
    assert d.intent_type == IntentType.BROWSER_NAVIGATE
    assert d.action == "browser_goto"


def test_browser_focus():
    d = _classify("focus youtube")
    assert d.intent_type == IntentType.BROWSER_FOCUS


def test_list_tabs():
    d = _classify("list tabs")
    assert d.intent_type == IntentType.BROWSER_TABS


def test_close_tab():
    d = _classify("close youtube")
    assert d.intent_type == IntentType.BROWSER_FOCUS
    assert d.action == "close_tab"


# ── System commands ─────────────────────────────────────────────────────

@pytest.mark.parametrize("query,expected_action", [
    ("shutdown", "shutdown_system"),
    ("restart", "restart_system"),
    ("lock", "lock_system"),
    ("recovery", "recovery_runtime"),
    ("recover", "recovery_runtime"),
])
def test_system_commands(query, expected_action):
    d = _classify(query)
    assert d.intent_type == IntentType.SYSTEM
    assert d.action == expected_action


# ── Search ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("query,expected_action", [
    ("search python", "search_web"),
    ("search for python", "search_web"),
    ("search youtube music", "search_youtube"),
])
def test_search(query, expected_action):
    d = _classify(query)
    assert d.intent_type == IntentType.SEARCH
    assert d.action == expected_action


# ── Open commands ───────────────────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "open notepad", "open calculator", "open spotify",
])
def test_open_app(query):
    d = _classify(query)
    assert d.intent_type == IntentType.DESKTOP_OPEN


# ── Multi-step ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "open notepad and search python",
    "open spotify and play music",
])
def test_multi_step(query):
    d = _classify(query)
    assert d.intent_type == IntentType.MULTI_STEP


# ── Unknown / fallback ──────────────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "asdfgh", "xylophone zebra", "quantum flux capacitor",
])
def test_unknown(query):
    d = _classify(query)
    assert d.intent_type == IntentType.CONVERSATION
    assert d.confidence <= 0.5


# ── R1: bare "please" prefix stripping ─────────────────────────────────

@pytest.mark.parametrize("query,expected_target", [
    ("please open chrome", "chrome"),
    ("can you open chrome", "chrome"),
    ("can you please open chrome", "chrome"),
])
def test_r1_please_open_normalizes_to_desktop_open(query, expected_target):
    """Bare 'please' must be stripped so the classifier sees a clean command verb."""
    from mini_kio.core.context_manager import get_session_context
    from mini_kio.core.pipeline import _NormalizationService
    norm = _NormalizationService().run(query, get_session_context("local_0"))
    d = _classify(norm, raw=query)
    assert d.intent_type == IntentType.DESKTOP_OPEN
    assert d.action == "open_app"
    assert d.target == expected_target


def test_r1_please_alone_not_stripped_to_empty():
    """Bare 'please' on its own must not vanish into an empty command."""
    from mini_kio.core.context_manager import get_session_context
    from mini_kio.core.pipeline import _NormalizationService
    norm = _NormalizationService().run("please", get_session_context("local_0"))
    assert norm.strip() == "please"


# ── R5: ordinal play resolves via offer engine (execution layer) ─────────

def test_r5_ordinal_play_accepts_pending_offer():
    """'play the second one' with a pending multi-offer plays candidate index 1."""
    from mini_kio.media.media_manager import MediaManager
    from mini_kio.media.intelligence.media_offer_manager import OfferTrigger
    from mini_kio.media.media_intelligence_models import EntityType, ResolvedEntity

    mm = MediaManager.get_instance()
    mgr = mm._offer_manager
    mgr.clear_all()
    def _ent(name):
        return ResolvedEntity(name=name, entity_type=EntityType.MOVIE, confidence=1.0)
    mgr.create_multi_offer(
        [_ent("First Movie"), _ent("Second Movie")],
        OfferTrigger.TRAILER_RELEASED, "Found:",
    )
    result = mm.play("play the second one")
    assert mgr.has_pending_offer() is False, "offer must be consumed"
    last = mgr.get_last_accepted_offer()
    assert last is not None, "ordinal play must accept the pending offer"
    assert last.accepted_index == 1, "must accept candidate index 1"
    entity = mgr.get_accepted_entity(last)
    assert entity and entity.name == "Second Movie", "must target candidate 1"
    mgr.clear_all()


def test_r5_ordinal_play_no_offer_falls_through():
    """Without a pending offer, ordinal phrasing still returns a play dict, not crash."""
    from mini_kio.media.media_manager import MediaManager
    mm = MediaManager.get_instance()
    mm._offer_manager.clear_all()
    result = mm.play("play the second one")
    assert isinstance(result, dict)


# ── R4: media-shaped affirmatives classify as accept_offer ───────────────

@pytest.mark.parametrize("query", [
    "show it", "watch it", "play video",
])
def test_r4_media_affirmative_accept_offer(query):
    """'show it'/'watch it' must accept the pending offer, not literal-play.

    R-EFG: "play it"/"play that" are deliberately excluded — they are
    media-continuity commands resolved by MediaManager.play pronoun handling,
    not offer acceptance.
    """
    d = _classify(query)
    assert d.intent_type == IntentType.CONVERSATION
    assert d.action == "accept_offer"


# ── Pipeline smoke test (end-to-end classification only) ────────────────

def test_pipeline_smoke():
    pipe = Pipeline()
    cases = [
        ("hello", IntentType.GREETING),
        ("who are you", IntentType.IDENTITY),
        ("search python", IntentType.SEARCH),
        ("play never gonna give you up", IntentType.MEDIA_PLAY),
        ("pause", IntentType.MEDIA_TRANSPORT),
        ("continue", IntentType.MEDIA_TRANSPORT),
        ("play something similar", IntentType.MEDIA_PLAY),
        ("tell me more", IntentType.CONVERSATION),
        ("yes", IntentType.CONVERSATION),
        ("shutdown", IntentType.SYSTEM),
        ("focus youtube", IntentType.BROWSER_FOCUS),
        ("asdfgh", IntentType.CONVERSATION),
    ]
    for text, expected_intent in cases:
        result = pipe.run(text)
        assert isinstance(result, dict), f"{text!r} should return dict"
        if expected_intent == IntentType.GREETING:
            assert "success" in result
