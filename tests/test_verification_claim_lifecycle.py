"""Focused tests: verification claim-store LIFECYCLE.

The pending-proposition store (last_verif_claims) must be:
  1. session-scoped  — user A's claim is never reclaimable by user B;
  2. consumed on topic move — a bare probe refers to the IMMEDIATELY
     preceding proposition, so once the user moves to a new topic a later
     "is that true?" must NOT resurrect the old conversation's claim
     (live failure: a Kawhi-trade claim from an earlier session answered a
     "Did that actually happen?" in an unrelated sports thread);
  3. replaced by a NEW assertion within the same session;
  4. gated against degenerate LLM synthesis ("It's 2:52 AM." must never be
     accepted as an evidence-grounded answer).
"""
import logging
import sys

logging.basicConfig(level=logging.CRITICAL)

sys.path.insert(0, ".")
from mini_kio.media.intelligence import integration_adapter as ia


def _tokens(text):
    return ia._meaningful_tokens(text)


def test_degenerate_synthesis_rejected_by_empty_tokens():
    """'It's 2:52 AM.' carries no content tokens — the grounding gate must
    reject it regardless of any referential token overlap with evidence."""
    query = "I heard SpaceX launched a new rocket and Messi announced he's retiring"
    ground = _tokens(query)
    # The degenerate answer that actually leaked live:
    bad = "It's 2:52 AM."
    at = _tokens(bad)
    assert not at, f"expected empty content tokens, got {at}"
    # Gate contract (mirrors the adapter's check): empty -> REJECT.
    if not at:
        rejected = True
    elif ground and not (at & ground):
        rejected = True
    else:
        rejected = False
    assert rejected


def test_real_synthesis_accepted_by_grounding_gate():
    """A grounded synthesis shares content tokens with the claim and passes."""
    query = "I heard SpaceX launched a new rocket and Messi announced he's retiring"
    ground = _tokens(query)
    good = "Bottom line: the Messi news checks out, SpaceX launch still scheduled"
    at = _tokens(good)
    assert at
    if not at:
        rejected = True
    elif ground and not (at & ground):
        rejected = True
    else:
        rejected = False
    assert not rejected


def test_contracted_referential_forms_are_stopwords():
    """Contracted referential forms ('it's', 'that's') are stopwords — they are
    the semantic class that let a degenerate answer sneak through the gate."""
    assert "it's" in ia._EVIDENCE_STOPWORDS
    assert "that's" in ia._EVIDENCE_STOPWORDS
    assert "there's" in ia._EVIDENCE_STOPWORDS
    assert _tokens("It's 2:52 AM.") == set()


def test_session_scoped_claim_keys():
    """register_user_assertion + has_pending_verif_claims must key by session:
    a claim registered for sess_a is invisible to sess_b."""
    adapter = MediaIntelligenceAdapterStub()
    adapter.register_user_assertion("Ronaldo got married too", session_id="sess_a")
    assert adapter.has_pending_verif_claims("sess_a") is True
    assert adapter.has_pending_verif_claims("sess_b") is False
    assert adapter.has_pending_verif_claims("") is False


def test_clear_user_claims_consumes_only_that_session():
    adapter = MediaIntelligenceAdapterStub()
    adapter.register_user_assertion("Ronaldo got married too", session_id="sess_a")
    adapter.register_user_assertion("The Warriors won last night", session_id="sess_b")
    adapter.clear_user_claims("sess_a")
    assert adapter.has_pending_verif_claims("sess_a") is False
    assert adapter.has_pending_verif_claims("sess_b") is True


def test_new_assertion_replaces_old_in_same_session():
    adapter = MediaIntelligenceAdapterStub()
    adapter.register_user_assertion("Ronaldo got married too", session_id="s1")
    adapter.register_user_assertion("The Warriors won last night", session_id="s1")
    key = adapter._claims_key("s1")
    entry = adapter._ctx.get(key)
    assert entry is not None
    claims = entry.value
    assert any("warriors" in c.lower() for c in claims)
    assert not any("ronaldo" in c.lower() for c in claims)


def test_split_claims_handles_two_propositions():
    """A multi-proposition message splits into independent claims (SpaceX /
    Messi) — evidence stays aligned per proposition."""
    adapter = MediaIntelligenceAdapterStub()
    claims = adapter._split_claims(
        "I heard SpaceX launched a new rocket and Messi announced he's retiring"
    )
    joined = " | ".join(claims).lower()
    assert "spacex" in joined
    assert "messi" in joined
    assert len(claims) >= 2


class MediaIntelligenceAdapterStub:
    """Thin adapter exercising ONLY the claim-store lifecycle methods (no
    providers, no LLM, no websocket)."""

    def __init__(self):
        from mini_kio.media.intelligence.context_store import ContextStore
        self._ctx = ContextStore(max_entries=50)

    @staticmethod
    def _claims_key(session_id):
        return ia.MediaIntelligenceAdapter._claims_key(
            object.__new__(ia.MediaIntelligenceAdapter), session_id
        )

    @staticmethod
    def _split_claims(query):
        return ia.MediaIntelligenceAdapter._split_claims(query)

    def register_user_assertion(self, text, session_id=""):
        ia.MediaIntelligenceAdapter.register_user_assertion(self, text, session_id)

    def has_pending_verif_claims(self, session_id=""):
        return ia.MediaIntelligenceAdapter.has_pending_verif_claims(self, session_id)

    def clear_user_claims(self, session_id=""):
        ia.MediaIntelligenceAdapter.clear_user_claims(self, session_id)
