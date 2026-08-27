"""Focused tests: verification follow-ups that name the SAME entity as the
stored claims ("what exactly did Messi say?") must reclaim the prior claims
instead of being searched as a bare fresh phrase (live failure: the follow-up
returned an unrelated World Cup quote)."""
import logging
import sys
from types import SimpleNamespace

logging.basicConfig(level=logging.CRITICAL)

sys.path.insert(0, ".")
from mini_kio.media.intelligence import integration_adapter as ia
from mini_kio.media.intelligence.integration_adapter import MediaIntelligenceAdapter


def _make_adapter(last_claims):
    adapter = MediaIntelligenceAdapter.__new__(MediaIntelligenceAdapter)
    store = {"last_verif_claims": last_claims}
    ctx = SimpleNamespace(
        get=lambda k: (SimpleNamespace(value=store[k]) if k in store else None),
        put=lambda k, v, **kw: store.__setitem__(k, v),
    )
    adapter._ctx = ctx
    # After the first verification the adapter registers the resolved entity
    # ("Messi") in memory; the follow-up resolves referents against it.
    _last_entity = SimpleNamespace(name="Messi", entity_type="MOVIE")
    adapter._mem = SimpleNamespace(get_last_entity=lambda: _last_entity)
    # Stub the heavy pieces so the test exercises ONLY the reclaim logic.
    adapter._retrieve_evidence = lambda *a, **k: []
    adapter._filter_claim_evidence = lambda *a, **k: []
    adapter._llm_fn = lambda *a, **k: None
    adapter._verify_llm_fn = None
    adapter._register_entity = lambda *a, **k: None
    adapter._split_claims = ia.MediaIntelligenceAdapter._split_claims
    adapter._is_verification_query = lambda *a, **k: True
    return adapter, store


def test_entity_named_elaboration_reclaims():
    """'what exactly did Messi say' after a Messi verification must reuse the
    stored claims (never search the bare phrase)."""
    adapter, store = _make_adapter(
        ["Messi's father passed away", "he said he can't play long anymore"]
    )
    calls = {}

    def fake_retrieve(cq, topic, n=2):
        calls["query"] = cq
        return []  # no live evidence in unit test; we assert the QUERY shape

    adapter._retrieve_evidence = fake_retrieve
    result = adapter._handle_verification("what exactly did Messi say")
    # No evidence and no LLM -> returns None (caller falls back), but the
    # retrieved query MUST carry the reclaimed claim content, proving the
    # bare "Messi say" phrase was NOT searched.
    assert "say" not in (calls.get("query") or "").lower() or "long" in (calls.get("query") or "").lower(), calls
    assert "play" in (calls.get("query") or "").lower(), calls
    assert result is None or result.response_text


def test_new_state_verb_stays_fresh_claim():
    """'did Messi retire' introduces a NEW state verb (retire) — it must NOT
    reclaim; it is a fresh claim to verify."""
    adapter, store = _make_adapter(
        ["Messi's father passed away", "he said he can't play long anymore"]
    )
    calls = {}

    def fake_retrieve(cq, topic, n=2):
        calls["query"] = cq
        return []

    adapter._retrieve_evidence = fake_retrieve
    adapter._handle_verification("did Messi retire")
    q = (calls.get("query") or "").lower()
    assert "retire" in q, q  # searched the new predicate, not the old claim
    assert "father" not in q, q


def test_elaboration_gate_routes_to_verification():
    """The context-aware gate: entity-named elaboration follow-ups reach the
    verification path (and reclaim); fresh topics / new predicates do not."""
    adapter, store = _make_adapter(
        ["Messi's father passed away", "he said he can't play long anymore"]
    )
    assert adapter._is_verif_elaboration_followup("what exactly did Messi say")
    assert adapter._is_verif_elaboration_followup("when did that happen")
    assert adapter._is_verif_elaboration_followup("what did Messi announce")
    # New state verb / fresh topic — never an elaboration of the prior claim.
    assert not adapter._is_verif_elaboration_followup("did Messi retire")
    assert not adapter._is_verif_elaboration_followup(
        "how are the premier league standings looking"
    )


def test_generic_followup_reclaims():
    """'is that actually true' still reclaims via the generic path."""
    adapter, store = _make_adapter(
        ["Messi's father passed away", "he said he can't play long anymore"]
    )
    calls = {"queries": []}

    def fake_retrieve(cq, topic, n=2):
        calls["queries"].append(cq)
        return []

    adapter._retrieve_evidence = fake_retrieve
    adapter._handle_verification("is that actually true")
    # The FIRST (anchored) query for the reclaimed claim must carry the
    # stored claim content ("father passed away"), never the bare follow-up
    # words. The recorded queries are anchored attempts + fallbacks.
    assert any("father" in (q or "").lower() for q in calls["queries"]), calls
    assert any("play" in (q or "").lower() for q in calls["queries"]), calls


if __name__ == "__main__":
    test_entity_named_elaboration_reclaims()
    print("ok: entity-named elaboration reclaims")
    test_new_state_verb_stays_fresh_claim()
    print("ok: new state verb stays fresh")
    test_generic_followup_reclaims()
    print("ok: generic followup reclaims")
