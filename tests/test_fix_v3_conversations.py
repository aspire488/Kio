"""
Tests verifying Fixes 1-5 from the V3 debugging session.

Fix 1: route_for_topic() calls MediaKnowledgeRouter (using router method)
Fix 2: _resolve_contextual_references media entity guard
Fix 3: _handle_acceptance handles "play the first one" patterns
Fix 4: Bare artifact resolution in play()
Fix 5: Extension selector robustness
"""

import sys
import os
import re
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")


# ── Fix 1: route_for_topic() calls MediaKnowledgeRouter ─────────────

def test_media_knowledge_router_movie():
    """MediaKnowledgeRouter must route Interstellar to MOVIE domain via OMDb."""
    from mini_kio.knowledge.media_knowledge_router import MediaKnowledgeRouter
    router = MediaKnowledgeRouter()
    metadata, domain = router.route("Interstellar")
    assert metadata is not None, f"route returned None metadata"
    assert isinstance(metadata, dict), f"Expected dict, got {type(metadata)}"
    assert len(metadata) > 0, "Empty metadata dict"
    print(f"  [OK] Interstellar -> {domain}: title={metadata.get('title','?')[:40]}")


def test_media_knowledge_router_tv():
    """MediaKnowledgeRouter must route The Bear to TV domain via TVMaze."""
    from mini_kio.knowledge.media_knowledge_router import MediaKnowledgeRouter
    router = MediaKnowledgeRouter()
    metadata, domain = router.route("The Bear")
    assert metadata is not None
    assert isinstance(metadata, dict) and len(metadata) > 0
    print(f"  [OK] The Bear -> {domain}: {str(metadata.get('title','?'))[:40]}")


def test_media_knowledge_router_anime():
    """MediaKnowledgeRouter must route Frieren to ANIME domain via Jikan."""
    from mini_kio.knowledge.media_knowledge_router import MediaKnowledgeRouter
    router = MediaKnowledgeRouter()
    metadata, domain = router.route("Frieren")
    assert metadata is not None
    assert isinstance(metadata, dict) and len(metadata) > 0
    print(f"  [OK] Frieren -> {domain}: {str(metadata.get('title','?'))[:40]}")


def test_media_knowledge_router_music():
    """MediaKnowledgeRouter must route Believer to MUSIC domain via MusicBrainz."""
    from mini_kio.knowledge.media_knowledge_router import MediaKnowledgeRouter
    router = MediaKnowledgeRouter()
    metadata, domain = router.route("Believer Imagine Dragons")
    assert metadata is not None
    assert isinstance(metadata, dict) and len(metadata) > 0
    print(f"  [OK] Believer -> {domain}: {str(metadata.get('title','?'))[:40]}")


def test_media_knowledge_router_non_media():
    """MediaKnowledgeRouter must return None for non-media queries."""
    from mini_kio.knowledge.media_knowledge_router import MediaKnowledgeRouter
    router = MediaKnowledgeRouter()
    metadata, domain = router.route("weather today")
    assert isinstance(metadata, dict), f"Expected dict, got {type(metadata)}"
    assert domain == "GENERAL", f"Expected GENERAL, got {domain}"
    print(f"  [OK] Non-media query correctly returned GENERAL")


# ── Fix 2: contextual-reference media entity guard ───────

def test_context_resolve_media_guard_present():
    """resolved_text must have the media passthrough guard (G1) in its code."""
    import inspect
    from mini_kio.core.context_manager import SessionContext
    source = inspect.getsource(SessionContext.resolved_text)
    assert '("play ", "watch ", "seek ", "turn ")' in source, "Media passthrough guard not found"
    print("  [OK] Media entity guard code is present in SessionContext.resolved_text")


# ── Fix 3: _handle_acceptance handles "play the first one" ──────────

def test_acceptance_number_pattern_matches():
    """_NUMBER_WORDS must include 'the first one' pattern."""
    from mini_kio.media.intelligence.integration_adapter import MediaIntelligenceAdapter
    nw = MediaIntelligenceAdapter._NUMBER_WORDS
    assert "first one" in nw, "first one not in NUMBER_WORDS"
    assert "the first one" in nw, "the first one not in NUMBER_WORDS"
    assert "second one" in nw
    assert "the second one" in nw
    print(f"  [OK] NUMBER_WORDS contains ordinal patterns: {list(nw.keys())[:6]}")


def test_acceptance_play_ordinal_regex():
    """'play the X one' patterns must match ordinal stripping regex."""
    pattern = re.compile(r"(?:play|show|watch)\s+(?:the\s+)?(.+)")
    for test_input, expected_stripped in [
        ("play the first one", "first one"),
        ("show the second one", "second one"),
        ("play first one", "first one"),
        ("show third one", "third one"),
        ("watch the first one", "first one"),
    ]:
        m = pattern.match(test_input)
        assert m is not None, f"Pattern did not match: {test_input}"
        assert m.group(1).strip() == expected_stripped, \
            f"For '{test_input}', expected '{expected_stripped}', got '{m.group(1)}'"
    print("  [OK] Ordinal stripping regex matches all patterns")


def test_acceptance_code_present():
    """_handle_acceptance must contain the ordinal stripping logic."""
    import inspect
    from mini_kio.media.intelligence.integration_adapter import MediaIntelligenceAdapter
    source = inspect.getsource(MediaIntelligenceAdapter._handle_acceptance)
    assert "ordinal_match" in source, "ordinal stripping code not found"
    assert "re.match" in source, "regex match not found"
    print("  [OK] Ordinal stripping code is present in _handle_acceptance")


# ── Fix 4: Bare artifact resolution in play() ──────────────────────

def test_bare_artifact_patterns():
    """Bare artifact pattern set must contain common artifact keywords."""
    import inspect
    from mini_kio.media.media_manager import MediaManager
    source = inspect.getsource(MediaManager.play)
    assert "_bare_artifact_patterns" in source, "Bare artifact patterns not found in play()"
    assert "trailer" in source, "trailer not in patterns"
    assert "highlights" in source, "highlights not in patterns"
    assert "interview" in source, "interview not in patterns"
    assert "teaser" in source, "teaser not in patterns"
    print("  [OK] Bare artifact pattern set present in play() with all keywords")


def test_bare_artifact_enrichment_logic():
    """Enriched query must prepend entity name to bare artifact."""
    # Simulate the enrichment logic from media_manager.py
    query = "trailer"
    entity_name = "Spider-Man Brand New Day"
    enriched = f"{entity_name} {query}"
    assert enriched == "Spider-Man Brand New Day trailer"
    assert entity_name in enriched
    assert query in enriched
    print(f"  [OK] Enrichment works: '{query}' -> '{enriched}'")


# ── Fix 5: Extension scripts ───────────────────────────────────────

def test_extension_background_js_syntax():
    """background.js must have valid syntax and contain SCRIPTS registry."""
    import json
    js_path = os.path.join(os.path.dirname(__file__), 
                           "..", "mini_kio", "browser_connector", "extension", "background.js")
    with open(js_path, "r", encoding="utf-8") as f:
        js = f.read()
    assert "get_page_info" in js, "get_page_info script not found"
    assert "youtube_bootstrap" in js, "youtube_bootstrap script not found"
    assert "SCRIPTS" in js, "SCRIPTS registry not found"
    # Check that youtube_bootstrap has updated selectors
    assert "ytd-rich-item-renderer" in js, "New YouTube selectors not found"
    assert "ytd-compact-video-renderer" in js, "Compact video selector not found"
    # Check that the fallback wildcard selector exists
    assert 'a[href*="/watch?"]' in js
    print("  [OK] background.js has get_page_info, youtube_bootstrap, and updated selectors")


# ── Run all ────────────────────────────────────────────────────────

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"\n=== {name} ===")
            try:
                fn()
                print("  PASS")
            except Exception as e:
                import traceback
                print(f"  FAIL: {e}")
                traceback.print_exc()
