import pytest
from mini_kio.llm.intent_classifier import IntentClassifier
from mini_kio.llm.intent_models import IntentType, ExtractedIntent
from mini_kio.llm.conversation_responder import ConversationResponder
from mini_kio.llm.conversation_models import OrchestrationResponse, OrchestrationState
from mini_kio.runtime.runtime_contracts import ExecutionClassification, RuntimeHandoffResult
from mini_kio.core.routing_utils import get_browser_routing
from mini_kio.core.config import DEFAULT_BROWSER

@pytest.fixture
def classifier():
    return IntentClassifier()

@pytest.fixture
def responder():
    return ConversationResponder()

def test_educational_classification(classifier):
    """Verify educational intent detection."""
    texts = [
        "teach me python",
        "explain recursion",
        "python syntax tutorial",
        "beginner guide to coding",
        "learn javascript",
        "how does ai work"
    ]
    for t in texts:
        classification = classifier.classify(t)
        assert classification.primary_intent.intent_type == IntentType.EDUCATIONAL, f"Failed for: {t}"

def test_browser_fallback_routing():
    """Verify routing: Native -> Browser fallback."""
    # 1. Native app (chrome is in registry)
    route = get_browser_routing("chrome")
    assert route["route_type"] == "native"
    assert route["action"] == "open_app"
    
    # 2. Browser fallback (youtube is a web app)
    route = get_browser_routing("youtube")
    assert route["route_type"] == "browser_fallback"
    assert "open_url" in route["target"]
    assert DEFAULT_BROWSER in route["target"]
    
    # 3. Search fallback
    route = get_browser_routing("some unknown thing")
    assert route["route_type"] == "search_fallback"
    assert route["action"] == "search_web"

def test_typo_normalization(responder):
    """Verify typo normalization in responder."""
    orch = OrchestrationResponse(state=OrchestrationState.CONVERSATIONAL, response_text="hellp", intent_type=IntentType.CONVERSATIONAL)
    handoff = RuntimeHandoffResult(success=True, classification=ExecutionClassification.CONVERSATIONAL_ONLY, message="OK", audit_metadata={})
    
    responder.generate("hellp", orch, handoff)
    diag = responder.get_context_diagnostics()
    assert diag.get("typo_normalization_applied", 0) > 0

def test_semantic_hardening(responder):
    """Verify educational intents don't get idle responses."""
    orch = OrchestrationResponse(state=OrchestrationState.CONVERSATIONAL, response_text="teach me python", intent_type=IntentType.EDUCATIONAL)
    handoff = RuntimeHandoffResult(success=True, classification=ExecutionClassification.CONVERSATIONAL_ONLY, message="OK", audit_metadata={})
    
    reply = responder.generate("teach me python", orch, handoff)
    # Generic idle responses are like "Alright. Let me know how I can help."
    assert reply == "I couldn't retrieve information for that topic right now." or "Python" in reply
    assert "Alright" not in reply

def test_degraded_survivability(responder):
    """Verify degraded fallback behavior."""
    handoff = RuntimeHandoffResult(success=False, classification=ExecutionClassification.DEGRADED_BLOCK, message="DEGRADED", audit_metadata={})
    orch = OrchestrationResponse(state=OrchestrationState.DEGRADED, response_text="error")
    
    reply = responder.generate("hello", orch, handoff)
    assert "offline" in reply.lower() or "exhausted" in reply.lower()
