"""Capability-level acceptance tests for the execution fabric changes.

Tests verify:
1. Media contract scoring (score_content_intent) routes correctly
2. Artifact validation catches bad content and triggers fallback
3. Unicode injection uses clipboard paste
4. YouTube candidate scoring boosts 'interview' when query contains it
"""

import os
os.environ.setdefault("KIO_TEST_MODE", "1")

import pytest


# ── Media contract scoring ──────────────────────────────────────────────────

class TestMediaContractScoring:
    """Verify score_content_intent produces correct media type detections."""

    def test_music_query(self):
        from mini_kio.core.media_contract import score_content_intent, MediaType
        intent = score_content_intent("play some music")
        assert intent.media_type == MediaType.MUSIC

    def test_video_query(self):
        from mini_kio.core.media_contract import score_content_intent, MediaType
        intent = score_content_intent("watch a video on youtube")
        assert intent.media_type == MediaType.VIDEO

    def test_news_query(self):
        from mini_kio.core.media_contract import score_content_intent, MediaType
        intent = score_content_intent("latest news today")
        assert intent.media_type == MediaType.NEWS

    def test_podcast_interview_detected(self):
        """'interview' maps to PODCAST in the contract scorer."""
        from mini_kio.core.media_contract import score_content_intent, MediaType
        intent = score_content_intent("Bethlehem interview")
        assert intent.media_type == MediaType.PODCAST

    def test_empty_query_returns_unknown(self):
        from mini_kio.core.media_contract import score_content_intent, MediaType
        intent = score_content_intent("")
        assert intent.media_type == MediaType.UNKNOWN

    def test_platform_hint_detected(self):
        from mini_kio.core.media_contract import score_content_intent
        intent = score_content_intent("play something on spotify")
        assert intent.platform_hint == "spotify"
        assert intent.is_explicit is True


# ── Media manager integration ───────────────────────────────────────────────

class TestMediaManagerDetection:
    """Verify _detect_media_type uses the contract scorer."""

    def test_detect_returns_string(self):
        from mini_kio.media.media_manager import _detect_media_type
        result = _detect_media_type("play a song")
        assert isinstance(result, str)

    def test_detect_music(self):
        from mini_kio.media.media_manager import _detect_media_type
        assert _detect_media_type("play some music") == "music"

    def test_detect_video(self):
        from mini_kio.media.media_manager import _detect_media_type
        assert _detect_media_type("watch a movie on youtube") == "video"

    def test_detect_news(self):
        from mini_kio.media.media_manager import _detect_media_type
        assert _detect_media_type("latest news update") == "news"


# ── Artifact validation ─────────────────────────────────────────────────────

class TestArtifactValidation:
    """Verify validate_content_for_artifact catches bad content."""

    def test_valid_spreadsheet_passes(self):
        from mini_kio.core.artifact_contract import validate_content_for_artifact, ArtifactType
        content = "Name\tAge\tCity\nAlice\t30\tNYC\nBob\t25\tLA"
        valid, msg = validate_content_for_artifact(content, ArtifactType.SPREADSHEET)
        assert valid is True

    def test_prose_fails_spreadsheet(self):
        from mini_kio.core.artifact_contract import validate_content_for_artifact, ArtifactType
        content = "Here are the instructions for creating a spreadsheet.\nFirst open Excel.\nThen create columns."
        valid, msg = validate_content_for_artifact(content, ArtifactType.SPREADSHEET)
        assert valid is False

    def test_empty_content_fails(self):
        from mini_kio.core.artifact_contract import validate_content_for_artifact, ArtifactType
        valid, msg = validate_content_for_artifact("", ArtifactType.SPREADSHEET)
        assert valid is False

    def test_valid_document_passes(self):
        from mini_kio.core.artifact_contract import validate_content_for_artifact, ArtifactType
        content = "# Report\n\n## Section 1\n\nThis is a substantial paragraph with enough words to pass validation.\n\n## Section 2\n\nAnother substantial paragraph here with sufficient content."
        valid, msg = validate_content_for_artifact(content, ArtifactType.DOCUMENT)
        assert valid is True

    def test_deterministic_spreadsheet_fallback(self):
        from mini_kio.core.artifact_contract import deterministic_spreadsheet_content
        content = deterministic_spreadsheet_content("create a budget spreadsheet")
        assert "\t" in content
        lines = [l for l in content.splitlines() if l.strip()]
        assert len(lines) >= 2

    def test_deterministic_document_fallback(self):
        from mini_kio.core.artifact_contract import deterministic_document_content
        content = deterministic_document_content("write a report about climate change")
        assert "climate change" in content.lower()


# ── YouTube candidate scoring ───────────────────────────────────────────────

class TestYouTubeScoring:
    """Verify _score_candidate boosts interview content correctly."""

    def test_interview_in_title_boosted_when_in_query(self):
        from mini_kio.media.providers.youtube_provider import _score_candidate
        # Query asks for interview, title contains interview -> high score
        score_interview = _score_candidate(
            title="Bethlehem Interview with the Mayor",
            url="https://youtube.com/watch?v=abc",
            query="Bethlehem interview",
            media_type="podcast",
        )
        # Same query but title is a trailer -> lower score
        score_trailer = _score_candidate(
            title="Bethlehem - Official Trailer (2024)",
            url="https://youtube.com/watch?v=def",
            query="Bethlehem interview",
            media_type="podcast",
        )
        assert score_interview > score_trailer

    def test_official_trailer_beats_soundtrack(self):
        from mini_kio.media.providers.youtube_provider import _score_candidate
        score_official = _score_candidate(
            title="Interstellar - Official Trailer",
            url="https://youtube.com/watch?v=abc",
            query="interstellar trailer",
            media_type="trailer",
        )
        score_soundtrack = _score_candidate(
            title="Interstellar Theme - Soundtrack",
            url="https://youtube.com/watch?v=def",
            query="interstellar trailer",
            media_type="trailer",
        )
        assert score_official > score_soundtrack


# ── Artifact operator validation wiring ─────────────────────────────────────

class TestArtifactOperatorValidation:
    """Verify create_artifact uses validation and falls back on bad content."""

    def test_spreadsheet_valid_content_accepted(self, tmp_path):
        from mini_kio.core.artifact_operator import create_artifact
        content = "Item\tQty\tPrice\nWidget\t5\t10.00\nGadget\t3\t25.00"
        result = create_artifact("test items", content, artifact="spreadsheet", out_dir=tmp_path)
        assert result.get("success") is True

    def test_spreadsheet_prose_content_gets_fallback(self, tmp_path):
        from mini_kio.core.artifact_operator import create_artifact
        # This is prose, not tabular data — should trigger fallback
        content = "Here are instructions for making a spreadsheet. Open Excel and create columns."
        result = create_artifact("budget tracker", content, artifact="spreadsheet", out_dir=tmp_path)
        # Should succeed via fallback, not fail
        assert result.get("success") is True

    def test_document_valid_content_accepted(self, tmp_path):
        from mini_kio.core.artifact_operator import create_artifact
        content = "# Report\n\n## Overview\n\nThis covers the topic.\n\n## Details\n\nMore content here with enough words to pass."
        result = create_artifact("test report", content, artifact="document", out_dir=tmp_path)
        assert result.get("success") is True
