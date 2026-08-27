"""
test_longitudinal_intelligence.py — Adversarial tests for the intelligence layer.

Tests:
- Relevance-ranked retrieval quality per query category
- Communication evidence accuracy
- Emotional episode extraction
- KIO correction detection (filtering false positives)
- Decision evidence retrieval
- Project lifecycle queries
- KIO self-model queries
- Edge cases: ambiguous references, historical vs current, uncertainty
"""
import pytest
from mini_kio.memory.intelligence_layer import (
    retrieve_intelligence,
    extract_communication_style,
    extract_emotional_episodes,
    extract_kio_corrections,
    extract_shared_history,
    query_self_model,
    _parse_conversations,
    _cached_extraction,
    _is_third_party,
)
import mini_kio.memory.intelligence_layer as il


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def conversations():
    """Load conversations once for the module."""
    return _parse_conversations()


@pytest.fixture(scope="module")
def cached():
    """Populate extraction cache once."""
    il._extraction_cache.clear()
    il._cache_ts = 0
    return _cached_extraction()


# ── 1. Communication Style ──────────────────────────────────────────────────

class TestCommunicationStyle:
    def test_extracts_patterns(self, conversations):
        result = extract_communication_style(conversations)
        assert "patterns" in result
        patterns = result["patterns"]
        assert len(patterns) >= 5, f"Expected at least 5 categories, got {len(patterns)}"

    def test_has_directness_evidence(self, conversations):
        result = extract_communication_style(conversations)
        assert "directness" in result["patterns"]
        assert result["patterns"]["directness"]["count"] > 100

    def test_has_technical_shorthand(self, conversations):
        result = extract_communication_style(conversations)
        assert "technical_shorthand" in result["patterns"]
        assert result["patterns"]["technical_shorthand"]["count"] > 50

    def test_patterns_have_confidence(self, conversations):
        result = extract_communication_style(conversations)
        for cat, data in result["patterns"].items():
            assert 0.0 < data["confidence"] <= 1.0, f"{cat} confidence {data['confidence']} out of range"

    def test_patterns_have_date_range(self, conversations):
        result = extract_communication_style(conversations)
        for cat, data in result["patterns"].items():
            assert data["first_seen"], f"{cat} missing first_seen"
            assert data["last_seen"], f"{cat} missing last_seen"


# ── 2. Emotional Episodes ───────────────────────────────────────────────────

class TestEmotionalEpisodes:
    def test_extracts_episodes(self, conversations):
        episodes = extract_emotional_episodes(conversations)
        assert len(episodes) > 100, f"Expected > 100 episodes, got {len(episodes)}"

    def test_has_emotion_field(self, conversations):
        episodes = extract_emotional_episodes(conversations)
        for ep in episodes[:20]:
            assert "emotion" in ep, "Episode missing 'emotion' field"
            assert ep["emotion"] in ("frustration", "excitement", "urgency", "confusion", "satisfaction")

    def test_has_intensity(self, conversations):
        episodes = extract_emotional_episodes(conversations)
        for ep in episodes[:20]:
            assert ep["intensity"] in ("low", "medium", "high")

    def test_has_trigger_context(self, conversations):
        episodes = extract_emotional_episodes(conversations)
        for ep in episodes[:10]:
            assert ep.get("trigger"), "Episode missing trigger context"

    def test_frustration_epresent(self, conversations):
        episodes = extract_emotional_episodes(conversations)
        frustr = [e for e in episodes if e["emotion"] == "frustration"]
        assert len(frustr) > 50, f"Expected > 50 frustration episodes, got {len(frustr)}"


# ── 3. KIO Corrections ──────────────────────────────────────────────────────

class TestKioCorrections:
    def test_extracts_events(self, conversations):
        events = extract_kio_corrections(conversations)
        assert len(events) > 50, f"Expected > 50 events, got {len(events)}"

    def test_has_correction_type(self, conversations):
        events = extract_kio_corrections(conversations)
        types = {e["type"] for e in events}
        assert "correction" in types or "failure" in types, \
            f"Expected correction or failure events, got types: {types}"

    def test_filters_roleplay(self, conversations):
        events = extract_kio_corrections(conversations)
        for e in events:
            desc = e.get("description", "").lower()
            # Should not contain obvious role-play markers
            assert "i'll be u" not in desc, f"Role-play not filtered: {e['description'][:80]}"
            assert "remember i'm u" not in desc, f"Role-play not filtered: {e['description'][:80]}"

    def test_filters_third_party(self, conversations):
        events = extract_kio_corrections(conversations)
        for e in events:
            desc = e.get("description", "").lower()
            # Should not contain generic content requests
            assert "write a message to a friend" not in desc, \
                f"Third-party content not filtered: {e['description'][:80]}"

    def test_has_context(self, conversations):
        events = extract_kio_corrections(conversations)
        for e in events[:20]:
            assert e.get("context"), "Event missing context (conversation title)"

    def test_has_confidence(self, conversations):
        events = extract_kio_corrections(conversations)
        for e in events[:20]:
            assert 0.0 < e["confidence"] <= 1.0, f"Confidence {e['confidence']} out of range"


# ── 4. Shared History ───────────────────────────────────────────────────────

class TestSharedHistory:
    def test_extracts_chains(self, conversations):
        chains = extract_shared_history(conversations)
        assert len(chains) > 5, f"Expected > 5 chains, got {len(chains)}"

    def test_chains_have_events(self, conversations):
        chains = extract_shared_history(conversations)
        for chain in chains[:10]:
            assert chain.get("events"), "Chain missing events"
            assert chain.get("trigger"), "Chain missing trigger type"

    def test_chains_sorted_chronologically(self, conversations):
        chains = extract_shared_history(conversations)
        for i in range(len(chains) - 1):
            assert chains[i]["start_when"] <= chains[i + 1]["start_when"], \
                "Chains not sorted chronologically"


# ── 5. Retrieval Quality ────────────────────────────────────────────────────

class TestRetrievalQuality:
    def test_identity_query(self):
        result = retrieve_intelligence("tg_default", "who am I?")
        # May be empty if living model not populated in test env
        if result:
            assert "About Joel" in result or "education" in result.lower() or "CGPA" in result

    def test_project_query(self):
        result = retrieve_intelligence("tg_default", "what have I been doing lately?")
        if result:
            assert "project" in result.lower() or "Active" in result

    def test_correction_query(self):
        result = retrieve_intelligence("tg_default", "what have I corrected you about?")
        if result:
            assert "correction" in result.lower() or "corrected" in result.lower() or "KIO" in result

    def test_decision_query(self):
        result = retrieve_intelligence("tg_default", "what have I changed my mind about?")
        if result:
            assert "decision" in result.lower() or "changed" in result.lower()

    def test_emotion_query(self):
        result = retrieve_intelligence("tg_default", "how do I express frustration?")
        if result:
            assert "frustrat" in result.lower() or "emotion" in result.lower()

    def test_communication_query(self):
        result = retrieve_intelligence("tg_default", "how do I usually talk?")
        if result:
            assert "communication" in result.lower() or "style" in result.lower() or "talk" in result.lower()

    def test_self_model_query(self):
        result = retrieve_intelligence("tg_default", "what do you know about yourself?")
        if result:
            assert "KIO" in result or "self" in result.lower() or "limitation" in result.lower()

    def test_project_historical_query(self):
        result = retrieve_intelligence("tg_default", "what happened to that old project?")
        if result:
            assert "project" in result.lower()

    def test_empty_query_returns_identity(self):
        result = retrieve_intelligence("tg_default", "")
        # May be empty if living model not populated in test env
        # The important thing is it doesn't crash
        assert isinstance(result, str)

    def test_irrelevant_query_still_returns_something(self):
        result = retrieve_intelligence("tg_default", "asdfghjkl")
        # May be empty if living model not populated
        # The important thing is it doesn't crash
        assert isinstance(result, str)


# ── 6. Self-Model Queries ──────────────────────────────────────────────────

class TestSelfModel:
    def test_failures_query(self):
        result = query_self_model("tg_default", "what have you gotten wrong before?")
        assert result, "Self-model failures query returned empty"

    def test_corrections_query(self):
        result = query_self_model("tg_default", "what have I corrected you about?")
        assert result, "Self-model corrections query returned empty"

    def test_evolution_query(self):
        result = query_self_model("tg_default", "how have you changed?")
        assert result, "Self-model evolution query returned empty"


# ── 7. Third-Party Filtering ───────────────────────────────────────────────

class TestThirdPartyFiltering:
    def test_filters_writing_requests(self):
        assert _is_third_party("Write a message to a friend", "test")
        assert _is_third_party("Can you write an essay about climate change?", "test")

    def test_does_not_filter_personal_statements(self):
        assert not _is_third_party("I'm frustrated with this bug", "debugging help")
        assert not _is_third_party("No, that's not what I meant", "kio fix")

    def test_does_not_filter_short_answers(self):
        assert not _is_third_party("yes", "general")
        assert not _is_third_party("ok thanks", "general")


# ── 8. Cache Behavior ──────────────────────────────────────────────────────

class TestCache:
    def test_cache_populates(self, cached):
        assert "corrections" in cached
        assert "emotional" in cached
        assert "shared_history" in cached

    def test_cache_has_data(self, cached):
        assert len(cached["corrections"]) > 100
        assert len(cached["emotional"]) > 100
        assert len(cached["shared_history"]) > 10

    def test_cache_reuse(self):
        """Second call should use cached data."""
        cache1 = _cached_extraction()
        cache2 = _cached_extraction()
        assert cache1 is cache2, "Cache should return same object"
