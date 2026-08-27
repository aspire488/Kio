"""Integration tests for IntelligenceV2 — evidence-composition intelligence layer."""

import os
import sys
import pytest
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mini_kio.backend import db as _db
from mini_kio.backend.models import SemanticNodeModel, SemanticLinkModel, Base


@pytest.fixture(autouse=True)
def _seed_db():
    """Seed in-memory DB with archive_v3 data for integration tests."""
    # Force re-init with in-memory DB (KIO_TEST_MODE=1 already set)
    _db.close_db()
    _db.init_db()
    # Seed archive_v3 nodes + links
    with _db.db_session() as sess:
        # User node
        user = SemanticNodeModel(
            session_id="archive_v3", kind="participant", name="Joel",
            key="archive_v3:participant:user:joel", status="active",
            meta_json="{}",
        )
        sess.add(user)
        sess.flush()

        seed_data = [
            ("project", "active", "KIO Bot", "Building KIO Telegram bot with semantic graph memory", 1.0),
            ("project", "active", "ChatGPT Export Analysis", "Analyzing 996 ChatGPT conversations for longitudinal intelligence", 0.95),
            ("emotion", "frustration", "Debugging frustration", "Joel gets frustrated when errors persist across multiple debug attempts", 0.85),
            ("emotion", "excitement", "Project launch excitement", "High energy when a project actually works end-to-end", 0.8),
            ("correction", "style", "Correction: no n8n", "Joel explicitly rejected n8n automation - wants code-first approach only", 0.9),
            ("decision", "architecture", "Architecture over speed", "Joel chose robust architecture over quick hacks even when frustrated", 0.85),
            ("identity", "background", "2007 born CS student", "Born 2007, college student, ChatGPT Plus subscriber, prolific builder", 0.95),
            ("communication", "style", "Direct and impatient", "Joel communicates directly, gets impatient with over-explanation, wants results not plans", 0.9),
        ]
        nodes = []
        for cat, subcat, name, desc, conf in seed_data:
            n = SemanticNodeModel(
                session_id="archive_v3", kind="claim", name=name,
                key=f"archive_v3:{cat}:{subcat}:{name}",
                description=desc, status="active",
                meta_json=json.dumps({"category": cat, "subcategory": subcat, "confidence": conf, "date_range": ["2026-01-01", "2026-08-01"]}),
            )
            sess.add(n)
            sess.flush()
            nodes.append(n)
            # Link to user
            link = SemanticLinkModel(
                session_id="archive_v3", source_id=user.id, target_id=n.id,
                relation="said", attributed_to="participant:user",
                stance="assert", confidence=conf, status="active",
                provenance=f"archive_v3:{cat}:{subcat}",
            )
            sess.add(link)
    yield


@pytest.fixture
def intel():
    from mini_kio.memory.intelligence_v2 import IntelligenceV2
    return IntelligenceV2("test_intelligence_v2_session")


def test_query_identity(intel):
    result = intel.query("what do you know about me?")
    assert isinstance(result, str)
    assert len(result) > 0


def test_query_project(intel):
    result = intel.query("what am I building?")
    assert isinstance(result, str)
    assert len(result) > 0


def test_query_emotion(intel):
    result = intel.query("why was I frustrated?")
    assert isinstance(result, str)
    assert len(result) > 0


def test_record_returns_dict_or_none(intel):
    feedback = intel.record("test message", "test reply", "2026-08-22T00:00:00")
    assert feedback is None or isinstance(feedback, dict)


def test_trajectory_returns_valid_direction(intel):
    result = intel.trajectory("emotion")
    assert isinstance(result, dict)
    assert "direction" in result
    assert result["direction"] in (
        "increasing", "decreasing", "stable", "insufficient_data"
    )


def test_trajectory_project(intel):
    result = intel.trajectory("project")
    assert isinstance(result, dict)
    assert "direction" in result


def test_query_empty_input(intel):
    assert intel.query("") == ""
    assert intel.query("   ") == ""


def test_record_empty_input(intel):
    assert intel.record("", "reply") is None


def test_cache_invalidation(intel):
    intel._get_evidence()
    intel._invalidate_cache()
    assert intel._cache is None
    intel._get_evidence()
    assert intel._cache is not None
