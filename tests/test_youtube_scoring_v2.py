"""Tests for the refined YouTube candidate scoring (RC11).

Covers:
- Content-type synonym matching (curtain raiser = teaser)
- Reaction/review penalty when user asks for teaser/trailer/song
- Official source preference without hardcoded channels
- Duplicate normalization
- Recency signal
- Discovery vs explicit request distinction
- Rejection preserves semantic intent
"""

from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta

from mini_kio.media.providers.youtube_provider import _score_candidate


# ── Helper ──────────────────────────────────────────────────────────────────

def _ts(days_ago: int = 0) -> str:
    """ISO 8601 timestamp for N days ago."""
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ── 1. Cosmic Samson teaser ────────────────────────────────────────────────

class TestCosmicSamsonTeaser:
    """The core failing case: 'play cosmic samson teaser' must select the
    actual teaser, not a reaction/review."""

    def test_official_teaser_beats_reaction(self):
        """Curtain raiser (official teaser synonym) must beat reaction."""
        official = _score_candidate(
            "Cosmic Samson - Curtain Raiser (Malayalam)",
            "https://www.youtube.com/watch?v=OFFICIAL",
            "cosmic samson teaser",
            channel="Think Music",
            media_type="teaser",
            published_at=_ts(3),
        )
        reaction = _score_candidate(
            "Cosmic Samson Teaser Reaction | OMG What A Trailer!",
            "https://www.youtube.com/watch?v=REACT",
            "cosmic samson teaser",
            channel="Fan Channel",
            media_type="teaser",
            published_at=_ts(5),
        )
        assert official > reaction, (
            f"Official teaser ({official}) must beat reaction ({reaction})"
        )

    def test_official_teaser_beats_review(self):
        """Official teaser must beat a review video."""
        official = _score_candidate(
            "Cosmic Samson - Official Teaser | Malayalam",
            "https://www.youtube.com/watch?v=OFFICIAL",
            "cosmic samson teaser",
            channel="Cosmic Samson Official",
            media_type="teaser",
            published_at=_ts(2),
        )
        review = _score_candidate(
            "Cosmic Samson Teaser Review - Is It Worth The Hype?",
            "https://www.youtube.com/watch?v=REVIEW",
            "cosmic samson teaser",
            channel="Review Channel",
            media_type="teaser",
            published_at=_ts(10),
        )
        assert official > review, (
            f"Official teaser ({official}) must beat review ({review})"
        )

    def test_teaser_in_title_wins(self):
        """A title literally containing 'teaser' should score higher than one
        that doesn't, for a 'teaser' query."""
        has_teaser = _score_candidate(
            "Cosmic Samson Teaser",
            "https://www.youtube.com/watch?v=A",
            "cosmic samson teaser",
            media_type="teaser",
        )
        no_teaser = _score_candidate(
            "Cosmic Samson - Curtain Raiser (Malayalam)",
            "https://www.youtube.com/watch?v=B",
            "cosmic samson teaser",
            media_type="teaser",
        )
        # Both should be high, but 'teaser' in title gets the content-type boost
        assert has_teaser >= no_teaser, (
            f"Title with 'teaser' ({has_teaser}) should be >= curtain raiser ({no_teaser})"
        )

    def test_malayalam_teaser_prefers_malayalam(self):
        """When user says 'teaser Malayalam', prefer Malayalam candidate."""
        mal = _score_candidate(
            "Cosmic Samson - Teaser (Malayalam)",
            "https://www.youtube.com/watch?v=MAL",
            "cosmic samson teaser malayalam",
            media_type="teaser",
        )
        hindi = _score_candidate(
            "Cosmic Samson - Teaser (Hindi)",
            "https://www.youtube.com/watch?v=HIN",
            "cosmic samson teaser malayalam",
            media_type="teaser",
        )
        assert mal > hindi, (
            f"Malayalam teaser ({mal}) must beat Hindi ({hindi})"
        )


# ── 2. Trailer queries ─────────────────────────────────────────────────────

class TestTrailerQueries:

    def test_trailer_beats_reaction(self):
        """'play X trailer' must pick trailer, not reaction."""
        trailer = _score_candidate(
            "Interstellar - Official Trailer",
            "https://www.youtube.com/watch?v=A",
            "interstellar trailer",
            channel="Warner Bros. Pictures",
            media_type="trailer",
        )
        reaction = _score_candidate(
            "Interstellar Trailer Reaction - SO EMOTIONAL",
            "https://www.youtube.com/watch?v=B",
            "interstellar trailer",
            channel="React Channel",
            media_type="trailer",
        )
        assert trailer > reaction

    def test_trailer_beats_review(self):
        trailer = _score_candidate(
            "Batman - Official Trailer",
            "https://www.youtube.com/watch?v=A",
            "batman trailer",
            media_type="trailer",
        )
        review = _score_candidate(
            "Batman Trailer Review - Breakdown",
            "https://www.youtube.com/watch?v=B",
            "batman trailer",
            media_type="trailer",
        )
        assert trailer > review


# ── 3. Song queries ────────────────────────────────────────────────────────

class TestSongQueries:

    def test_music_video_beats_reaction(self):
        """'play shape of you' must pick the actual song, not a reaction."""
        song = _score_candidate(
            "Ed Sheeran - Shape of You (Official Music Video)",
            "https://www.youtube.com/watch?v=A",
            "shape of you",
            channel="Ed Sheeran",
            media_type="music video",
        )
        reaction = _score_candidate(
            "Shape of You - Reaction (AMAZING!!)",
            "https://www.youtube.com/watch?v=B",
            "shape of you",
            channel="Reaction Channel",
            media_type="music video",
        )
        assert song > reaction

    def test_official_music_video_beats_lyrics(self):
        """Official video should beat auto-generated lyrics video."""
        official = _score_candidate(
            "Ed Sheeran - Shape of You (Official Video)",
            "https://www.youtube.com/watch?v=A",
            "shape of you official music video",
            channel="Ed Sheeran",
            media_type="music video",
        )
        lyrics = _score_candidate(
            "Ed Sheeran - Shape of You (Lyrics)",
            "https://www.youtube.com/watch?v=B",
            "shape of you official music video",
            channel="Lyrics Channel",
            media_type="music video",
        )
        assert official > lyrics


# ── 4. Official source detection (no hardcoded channels) ──────────────────

class TestOfficialSourceDetection:

    def test_vevo_channel_bonus(self):
        """VEVO channel gets authority bonus."""
        vevo = _score_candidate(
            "Artist - Song (Official Video)",
            "https://www.youtube.com/watch?v=A",
            "artist song",
            channel="Artist VEVO",
            media_type="music video",
        )
        random_ch = _score_candidate(
            "Artist - Song (Official Video)",
            "https://www.youtube.com/watch?v=B",
            "artist song",
            channel="Random Uploads",
            media_type="music video",
        )
        assert vevo > random_ch

    def test_official_in_title_bonus(self):
        """'official' in title gets bonus."""
        off = _score_candidate(
            "Movie - Official Trailer",
            "https://www.youtube.com/watch?v=A",
            "movie trailer",
            media_type="trailer",
        )
        noff = _score_candidate(
            "Movie - Trailer",
            "https://www.youtube.com/watch?v=B",
            "movie trailer",
            media_type="trailer",
        )
        assert off > noff

    def test_studios_channel_bonus(self):
        """Channel with 'studios' gets authority bonus."""
        studios = _score_candidate(
            "Movie - Official Trailer",
            "https://www.youtube.com/watch?v=A",
            "movie trailer",
            channel="Warner Bros. Studios",
            media_type="trailer",
        )
        no_studios = _score_candidate(
            "Movie - Official Trailer",
            "https://www.youtube.com/watch?v=B",
            "movie trailer",
            channel="Some Random Channel",
            media_type="trailer",
        )
        assert studios > no_studios


# ── 5. Content-type penalties ──────────────────────────────────────────────

class TestContentTypePenalties:

    def test_soundtrack_penalized_for_visual_request(self):
        """Soundtrack/theme uploads lose to official trailer."""
        official = _score_candidate(
            "I'M GAME TRAILER (Malayalam) | Dulquer Salmaan | Wayfarer Films Music",
            "https://www.youtube.com/watch?v=A",
            "lm game trailer",
            channel="Wayfarer Films Music",
            media_type="trailer",
        )
        theme = _score_candidate(
            "I'M Game Trailer Theme - Malayalam",
            "https://www.youtube.com/watch?v=B",
            "lm game trailer",
            channel="Jakes Bejoy - Topic",
            media_type="trailer",
        )
        assert official > theme

    def test_emoji_reupload_penalized(self):
        """Emoji in title = clickbait reupload, penalized."""
        clean = _score_candidate(
            "Interstellar - Official Trailer",
            "https://www.youtube.com/watch?v=A",
            "interstellar trailer",
            media_type="trailer",
        )
        emoji = _score_candidate(
            "Interstellar - Trailer 🔥🔥 Latest Update",
            "https://www.youtube.com/watch?v=B",
            "interstellar trailer",
            media_type="trailer",
        )
        assert clean > emoji

    def test_shorts_penalized_for_normal_request(self):
        """Shorts URL penalized unless user asked for shorts."""
        normal = _score_candidate(
            "Cosmic Samson - Teaser",
            "https://www.youtube.com/watch?v=A",
            "cosmic samson teaser",
            media_type="teaser",
        )
        shorts = _score_candidate(
            "Cosmic Samson - Teaser",
            "https://www.youtube.com/shorts/ABC123",
            "cosmic samson teaser",
            media_type="teaser",
        )
        assert normal > shorts

    def test_podcast_not_penalized_for_interview(self):
        """Podcast is a valid interview container — should not be penalized."""
        podcast = _score_candidate(
            "Joe Rogan interviews Elon Musk",
            "https://www.youtube.com/watch?v=A",
            "joe rogan elon musk interview",
            media_type="interview",
        )
        trailer = _score_candidate(
            "Elon Musk - Official Trailer",
            "https://www.youtube.com/watch?v=B",
            "joe rogan elon musk interview",
            media_type="interview",
        )
        assert podcast > trailer


# ── 6. View count is weak signal ───────────────────────────────────────────

class TestViewCountSignal:

    def test_views_never_override_relevance(self):
        """High views on unrelated content must not beat low views on
        semantically relevant content."""
        relevant = _score_candidate(
            "Cosmic Samson - Official Teaser",
            "https://www.youtube.com/watch?v=A",
            "cosmic samson teaser",
            view_count=1000,
            media_type="teaser",
        )
        viral_unrelated = _score_candidate(
            "Best Compilation Ever - Cosmic Moments",
            "https://www.youtube.com/watch?v=B",
            "cosmic samson teaser",
            view_count=100_000_000,
            media_type="teaser",
        )
        assert relevant > viral_unrelated, (
            f"Relevant ({relevant}) must beat viral unrelated ({viral_unrelated})"
        )

    def test_views_are_bounded(self):
        """View bonus should never exceed +5."""
        low = _score_candidate(
            "Test Title",
            "https://www.youtube.com/watch?v=A",
            "test",
            view_count=100,
        )
        mid = _score_candidate(
            "Test Title",
            "https://www.youtube.com/watch?v=B",
            "test",
            view_count=1_000_000,
        )
        high = _score_candidate(
            "Test Title",
            "https://www.youtube.com/watch?v=C",
            "test",
            view_count=100_000_000,
        )
        # All should be similar — views are weak
        assert abs(high - low) <= 6, f"View spread too large: low={low} high={high}"


# ── 7. Recency signal ──────────────────────────────────────────────────────

class TestRecencySignal:

    def test_recentGetsBonus(self):
        """Recent upload gets small bonus."""
        recent = _score_candidate(
            "Same Title",
            "https://www.youtube.com/watch?v=A",
            "same title",
            published_at=_ts(2),
        )
        old = _score_candidate(
            "Same Title",
            "https://www.youtube.com/watch?v=B",
            "same title",
            published_at=_ts(400),
        )
        assert recent > old, f"Recent ({recent}) should beat old ({old})"

    def test_recency_is_weak(self):
        """Recency bonus (max +3) must not override strong relevance signals."""
        recent_unrelated = _score_candidate(
            "Completely Different Video",
            "https://www.youtube.com/watch?v=A",
            "cosmic samson teaser",
            published_at=_ts(1),
            media_type="teaser",
        )
        old_relevant = _score_candidate(
            "Cosmic Samson - Official Teaser",
            "https://www.youtube.com/watch?v=B",
            "cosmic samson teaser",
            published_at=_ts(400),
            media_type="teaser",
        )
        assert old_relevant > recent_unrelated, (
            f"Old relevant ({old_relevant}) must beat recent unrelated ({recent_unrelated})"
        )


# ── 8. Exact entity match ─────────────────────────────────────────────────

class TestExactEntityMatch:

    def test_exact_entity_in_title_wins(self):
        """'Cosmic Samson' should match the entity, not a vague result."""
        exact = _score_candidate(
            "Cosmic Samson",
            "https://www.youtube.com/watch?v=A",
            "cosmic samson",
        )
        vague = _score_candidate(
            "Samson - A Cosmic Journey Documentary",
            "https://www.youtube.com/watch?v=B",
            "cosmic samson",
        )
        assert exact > vague


# ── 9. Phrase position ─────────────────────────────────────────────────────

class TestPhrasePosition:

    def test_leading_phrase_beats_buried(self):
        """Query at start of title wins over buried at end."""
        leading = _score_candidate(
            "Cosmic Samson - Teaser",
            "https://www.youtube.com/watch?v=A",
            "cosmic samson teaser",
            media_type="teaser",
        )
        buried = _score_candidate(
            "Latest Updates - Cosmic Samson Teaser Reaction Breakdown",
            "https://www.youtube.com/watch?v=B",
            "cosmic samson teaser",
            media_type="teaser",
        )
        assert leading > buried


# ── 10. Aggregation/mashup penalty ────────────────────────────────────────

class TestAggregationPenalty:

    def test_dash_chain_penalized(self):
        """Multi-dash compilation titles penalized."""
        clean = _score_candidate(
            "Cosmic Samson - Official Teaser",
            "https://www.youtube.com/watch?v=A",
            "cosmic samson teaser",
            media_type="teaser",
        )
        mashup = _score_candidate(
            "Cosmic Samson - Spiderman - Venom - Best Moments",
            "https://www.youtube.com/watch?v=B",
            "cosmic samson teaser",
            media_type="teaser",
        )
        assert clean > mashup

    def test_vs_mashup_penalized(self):
        """'A vs B' mashup penalized when user didn't ask for vs."""
        clean = _score_candidate(
            "Cosmic Samson - Official Teaser",
            "https://www.youtube.com/watch?v=A",
            "cosmic samson teaser",
            media_type="teaser",
        )
        vs = _score_candidate(
            "Cosmic Samson vs Superman - Who Would Win?",
            "https://www.youtube.com/watch?v=B",
            "cosmic samson teaser",
            media_type="teaser",
        )
        assert clean > vs


# ── 11. Discovery vs explicit distinction ─────────────────────────────────

class TestDiscoveryVsExplicit:

    def test_discovery_bare_phrase_has_no_content_type(self):
        """Discovery queries ('play something funny') should not trigger
        content-type penalties — they have no media_type."""
        # Without media_type, no content-type mismatch penalty applies
        result = _score_candidate(
            "Funny Cat Compilation",
            "https://www.youtube.com/watch?v=A",
            "play something funny",
        )
        # Should have some score (not -100 for unrelated)
        assert result > -100

    def test_explicit_teaser_query_has_strong_content_type_signal(self):
        """Explicit 'teaser' query has content-type validation active."""
        has_teaser = _score_candidate(
            "Movie - Teaser",
            "https://www.youtube.com/watch?v=A",
            "movie teaser",
            media_type="teaser",
        )
        no_teaser = _score_candidate(
            "Movie - Official Trailer",
            "https://www.youtube.com/watch?v=B",
            "movie teaser",
            media_type="teaser",
        )
        # Both are valid but 'teaser' in title gets content-type boost
        assert has_teaser >= no_teaser


# ── 12. Rejection preserves intent ────────────────────────────────────────

class TestRejectionIntentPreservation:

    def test_different_candidate_same_entity(self):
        """After rejection, a different Cosmic Samson teaser should still
        score well — rejection doesn't destroy relevance."""
        # Both are valid teasers — rejection of one shouldn't penalize the other
        a = _score_candidate(
            "Cosmic Samson - Teaser (Malayalam)",
            "https://www.youtube.com/watch?v=A",
            "cosmic samson teaser",
            media_type="teaser",
        )
        b = _score_candidate(
            "Cosmic Samson - Official Teaser",
            "https://www.youtube.com/watch?v=B",
            "cosmic samson teaser",
            media_type="teaser",
        )
        # Both should score positively and similarly
        assert a > 0 and b > 0, f"Both should be positive: A={a}, B={b}"
        assert abs(a - b) < 20, f"Scores too different: A={a}, B={b}"


# ── 13. Duplicate normalization ───────────────────────────────────────────

class TestDuplicateNormalization:
    """These test the scoring, not the dedup logic (which is in
    _select_best_candidate). Two candidates with same title but different
    URL params should score identically."""

    def test_same_video_different_params_same_score(self):
        """Same title + video, different URL params → same score."""
        s1 = _score_candidate(
            "Cosmic Samson - Teaser",
            "https://www.youtube.com/watch?v=ABC123",
            "cosmic samson teaser",
            media_type="teaser",
        )
        s2 = _score_candidate(
            "Cosmic Samson - Teaser",
            "https://www.youtube.com/watch?v=ABC123&list=PLxyz",
            "cosmic samson teaser",
            media_type="teaser",
        )
        assert s1 == s2, f"Same video should score identically: {s1} vs {s2}"


# ── 14. Negative framing signals ──────────────────────────────────────────

class TestNegativeFraming:

    def test_reaction_penalty_scales_with_type_request(self):
        """Reaction gets stronger penalty when user asks for teaser/trailer."""
        # User asked for teaser — reaction gets extra penalty
        reaction_teaser = _score_candidate(
            "Cosmic Samson Teaser Reaction",
            "https://www.youtube.com/watch?v=A",
            "cosmic samson teaser",
            media_type="teaser",
        )
        # User didn't ask for teaser explicitly — reaction gets normal penalty
        reaction_plain = _score_candidate(
            "Cosmic Samson Teaser Reaction",
            "https://www.youtube.com/watch?v=B",
            "cosmic samson",
        )
        # Both penalized, but teaser query should penalize harder
        assert reaction_teaser <= reaction_plain, (
            f"Reaction with teaser query ({reaction_teaser}) should be <= plain ({reaction_plain})"
        )

    def test_breakdown_penalized_for_trailer(self):
        """'breakdown' penalized when user asks for trailer."""
        trailer = _score_candidate(
            "Movie - Official Trailer",
            "https://www.youtube.com/watch?v=A",
            "movie trailer",
            media_type="trailer",
        )
        breakdown = _score_candidate(
            "Movie Trailer Breakdown - Every Detail Explained",
            "https://www.youtube.com/watch?v=B",
            "movie trailer",
            media_type="trailer",
        )
        assert trailer > breakdown

    def test_explained_penalized(self):
        """'explained' penalized when user asks for teaser."""
        teaser = _score_candidate(
            "Movie - Teaser",
            "https://www.youtube.com/watch?v=A",
            "movie teaser",
            media_type="teaser",
        )
        explained = _score_candidate(
            "Movie Teaser Ending Explained",
            "https://www.youtube.com/watch?v=B",
            "movie teaser",
            media_type="teaser",
        )
        assert teaser > explained


# ── 15. Live/shorts/video type distinctions ────────────────────────────────

class TestMediaTypeDistinctions:

    def test_live_penalized_when_not_asked(self):
        """'live' penalized when user didn't ask for live content."""
        normal = _score_candidate(
            "Artist - Song (Official Video)",
            "https://www.youtube.com/watch?v=A",
            "artist song",
            media_type="music video",
        )
        live = _score_candidate(
            "Artist - Song (Live Performance)",
            "https://www.youtube.com/watch?v=B",
            "artist song",
            media_type="music video",
        )
        assert normal > live

    def test_live_not_penalized_when_asked(self):
        """'live' NOT penalized when user asked for live."""
        live_asked = _score_candidate(
            "Artist - Song (Live Performance)",
            "https://www.youtube.com/watch?v=A",
            "artist song live",
            media_type="live",
        )
        normal = _score_candidate(
            "Artist - Song (Official Video)",
            "https://www.youtube.com/watch?v=B",
            "artist song live",
            media_type="live",
        )
        # Live should be boosted when user asks for live
        assert live_asked >= normal


# ── 16. Coverage gate ─────────────────────────────────────────────────────

class TestCoverageGate:

    def test_low_coverage_penalized(self):
        """Missing >50% of query terms → strong penalty."""
        full = _score_candidate(
            "Cosmic Samson - Official Teaser",
            "https://www.youtube.com/watch?v=A",
            "cosmic samson teaser",
            media_type="teaser",
        )
        partial = _score_candidate(
            "Samson - Action Movie",
            "https://www.youtube.com/watch?v=B",
            "cosmic samson teaser",
            media_type="teaser",
        )
        assert full > partial


# ── 17. Long title penalty ─────────────────────────────────────────────────

class TestLongTitlePenalty:

    def test_long_title_penalized(self):
        """Titles >90 chars get penalty."""
        short = _score_candidate(
            "Cosmic Samson - Teaser",
            "https://www.youtube.com/watch?v=A",
            "cosmic samson teaser",
            media_type="teaser",
        )
        long_title = _score_candidate(
            "Cosmic Samson - Teaser Official Malayalam Movie 2024 Dulquer Salmaan Latest Release Announcement",
            "https://www.youtube.com/watch?v=B",
            "cosmic samson teaser",
            media_type="teaser",
        )
        assert short >= long_title


# ── 18. Tie-breaking ──────────────────────────────────────────────────────

class TestTieBreaking:

    def test_shorter_title_wins_on_tie(self):
        """When scores are equal, shorter title wins (more canonical)."""
        s1 = _score_candidate(
            "Cosmic Samson - Teaser",
            "https://www.youtube.com/watch?v=A",
            "cosmic samson teaser",
            media_type="teaser",
        )
        s2 = _score_candidate(
            "Cosmic Samson - Teaser - Official - Malayalam - 2024",
            "https://www.youtube.com/watch?v=B",
            "cosmic samson teaser",
            media_type="teaser",
        )
        # If scores are tied, shorter title should be preferred
        # (tested by tie-breaking key, but verify scores are at least equal)
        assert s1 >= s2 - 2, f"Shorter title should be competitive: {s1} vs {s2}"


# ── 19. Karikku/FilterCopy NOT hardcoded ──────────────────────────────────

class TestNoHardcodedChannels:

    def test_karikku_comedy_not_hardcoded(self):
        """'play a Karikku comedy' should work via channel name match, not
        hardcoded rules."""
        karikku = _score_candidate(
            "Karikku - Office Romance",
            "https://www.youtube.com/watch?v=A",
            "karikku comedy",
            channel="Karikku",
        )
        other = _score_candidate(
            "Random Comedy - Funny Skit",
            "https://www.youtube.com/watch?v=B",
            "karikku comedy",
            channel="Random Channel",
        )
        assert karikku > other

    def test_filtercopy_not_hardcoded(self):
        """FilterCopy works via channel name match."""
        fc = _score_candidate(
            "FilterCopy - Things Indian Moms Say",
            "https://www.youtube.com/watch?v=A",
            "filtercopy",
            channel="FilterCopy",
        )
        other = _score_candidate(
            "Things Indian Moms Say - reaction",
            "https://www.youtube.com/watch?v=B",
            "filtercopy",
            channel="Reaction Channel",
        )
        assert fc > other


# ── 20. Edge cases ─────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_empty_query(self):
        """Empty query returns 0."""
        assert _score_candidate("title", "url", "") == 0

    def test_no_match(self):
        """Completely unrelated title returns -100."""
        assert _score_candidate(
            "Random Unrelated Video",
            "https://www.youtube.com/watch?v=A",
            "cosmic samson teaser",
        ) == -100

    def test_exact_title_match(self):
        """Title == query gets +20 bonus."""
        s = _score_candidate(
            "cosmic samson teaser",
            "https://www.youtube.com/watch?v=A",
            "cosmic samson teaser",
        )
        assert s > 30  # strong match

    def test_description_corroboration(self):
        """Description containing query terms gives bonus."""
        with_desc = _score_candidate(
            "Cosmic Samson",
            "https://www.youtube.com/watch?v=A",
            "cosmic samson teaser",
            description="Watch the official Cosmic Samson teaser here",
            media_type="teaser",
        )
        without_desc = _score_candidate(
            "Cosmic Samson",
            "https://www.youtube.com/watch?v=B",
            "cosmic samson teaser",
            description="",
            media_type="teaser",
        )
        assert with_desc >= without_desc


# ── 21. Audio-only channel penalized ───────────────────────────────────────

class TestAudioOnlyPenalty:

    def test_topic_channel_penalized_for_visual(self):
        """'- Topic' channel penalized when visual type requested."""
        visual = _score_candidate(
            "Movie - Official Trailer",
            "https://www.youtube.com/watch?v=A",
            "movie trailer",
            channel="Studio Pictures",
            media_type="trailer",
        )
        topic = _score_candidate(
            "Movie - Official Trailer",
            "https://www.youtube.com/watch?v=B",
            "movie trailer",
            channel="Soundtrack - Topic",
            media_type="trailer",
        )
        assert visual > topic


# ── 22. RC13: content-type detection from query (not pipeline media_type) ────

class TestRC13ContentTypeDetection:

    def test_teaser_query_overrides_music_media_type(self):
        """When pipeline sends media_type='music' but query says 'teaser',
        the content-type boost must still fire from query detection."""
        official = _score_candidate(
            "Cosmic Samson - Curtain Raiser (Hindi)",
            "https://www.youtube.com/watch?v=A",
            "play cosmic samson teaser",
            channel="",
            description="",
            media_type="music",  # pipeline sends music — the RC13 bug
        )
        reaction = _score_candidate(
            "Cosmic Samson Teaser Reaction Curtain Raiser | Entertainment Kizhi",
            "https://www.youtube.com/watch?v=B",
            "play cosmic samson teaser",
            channel="",
            description="",
            media_type="music",
        )
        assert official > reaction

    def test_trailer_query_overrides_music_media_type(self):
        """'play X trailer' with media_type='music' still gets trailer boost."""
        official = _score_candidate(
            "Spider-Man - Official Trailer",
            "https://www.youtube.com/watch?v=A",
            "play spider-man official trailer",
            channel="Marvel",
            media_type="music",
        )
        reaction = _score_candidate(
            "Spider-Man Trailer Reaction Breakdown",
            "https://www.youtube.com/watch?v=B",
            "play spider-man official trailer",
            channel="",
            media_type="music",
        )
        assert official > reaction

    def test_content_type_detected_from_query_not_media_type(self):
        """'teaser' in query triggers boost even when media_type is unrelated."""
        teaser = _score_candidate(
            "Movie - Official Teaser",
            "https://www.youtube.com/watch?v=A",
            "play movie teaser",
            media_type="music",
        )
        non_teaser = _score_candidate(
            "Movie - Official Teaser",
            "https://www.youtube.com/watch?v=A",
            "play movie teaser",
            media_type="trailer",
        )
        # Both should get the same boost regardless of media_type param
        assert teaser == non_teaser

    def test_no_content_type_in_query_uses_media_type_fallback(self):
        """When query has no content-type word, falls back to media_type."""
        with_teaser = _score_candidate(
            "Movie - Official Trailer",
            "https://www.youtube.com/watch?v=A",
            "movie trailer",
            media_type="trailer",
        )
        without_type = _score_candidate(
            "Movie - Official Trailer",
            "https://www.youtube.com/watch?v=A",
            "movie trailer",
            media_type="",
        )
        assert with_teaser >= without_type
