import pytest
from mini_kio.llm.identity_guard import IdentityGuard

@pytest.fixture
def guard():
    return IdentityGuard()

def test_surgical_rewrite_identity(guard):
    # Case: Mixture of valid and violating sentences
    # "I can help with that. I am a large language model trained by Google."
    # The second sentence should be rewritten, the first should stay.
    
    response = "I can help with that. I am a large language model trained by Google."
    rewritten, violations = guard.check_and_rewrite(response, "who are you")
    
    assert "I can help with that" in rewritten
    assert "large language model" not in rewritten
    assert "KIO" in rewritten
    assert len(violations) > 0

def test_surgical_rewrite_emotions(guard):
    # "I can help with that. I feel sad that you are leaving."
    # The second sentence should be rewritten.
    
    response = "I can help with that. I feel sad that you are leaving."
    rewritten, violations = guard.check_and_rewrite(response, "bye")
    
    assert "help with that" in rewritten
    assert "feel sad" not in rewritten
    assert "KIO does not have feelings" in rewritten or "emotions" in rewritten
    assert len(violations) > 0
