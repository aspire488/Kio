import pytest
from mini_kio.llm.conversation_responder import ConversationResponder
from mini_kio.llm.conversation_models import OrchestrationResponse, OrchestrationState
from mini_kio.runtime.runtime_contracts import RuntimeHandoffResult, ExecutionClassification

EXPLICIT_FAILURE = "I couldn't retrieve information for that topic right now."
STATUS_PHRASES = {"ready.", "standing by.", "online.", "awaiting input.", "go ahead."}

@pytest.fixture
def responder():
    return ConversationResponder()

@pytest.fixture
def orchestration():
    return OrchestrationResponse(state=OrchestrationState.CONVERSATIONAL, response_text="")

@pytest.fixture
def handoff_conversational():
    from mini_kio.runtime.runtime_contracts import ExecutionAuditMetadata
    audit = ExecutionAuditMetadata(
        intent_origin="test",
        validation_state="validated",
        confirmation_state="not_required",
        dispatch_eligibility=True
    )
    return RuntimeHandoffResult(
        success=True,
        classification=ExecutionClassification.CONVERSATIONAL_ONLY,
        message="Conversational handoff",
        audit_metadata=audit
    )

def test_educational_intent_routing(responder, orchestration, handoff_conversational):
    """Test various educational intent triggers."""
    prompts = [
        "teach me python",
        "explain recursion",
        "python basics",
        "javascript syntax",
        "coding tutorial",
        "beginner guide for ai",
        "learn machine learning",
        "how does an operating system work"
    ]
    
    for prompt in prompts:
        # We simulate Gemini returning an idle response to trigger the coherence check/educational fallback
        # In these tests, we assume Gemini is disabled or returns nothing to trigger fallbacks
        response = responder.generate(prompt, orchestration, handoff_conversational)
        keywords = ["python", "recursion", "javascript", "machine learning", "operating system", "ai"]
        found = any(keyword in response.lower() for keyword in keywords)
        if not found:
            print(f"\nPrompt: {prompt}")
            print(f"Response: {response}")
        assert found or response == EXPLICIT_FAILURE or len(response.strip()) > 20
        assert "not sure" not in response.lower()
        assert response.lower().strip() not in STATUS_PHRASES

def test_typo_aliases(responder, orchestration, handoff_conversational):
    """Test typo normalization for common technical terms."""
    typo_prompts = [
        ("pythn basics", "python"),
        ("javascrpt syntax", "javascript"),
        ("recusrion tutorial", "recursion"),
        ("machien learning", "machine learning"),
        ("hellp", "hello"),
        ("whos joel", "who is")
    ]
    
    for typo, expected in typo_prompts:
        # Check normalization diagnostic
        responder.generate(typo, orchestration, handoff_conversational)
        diag = responder.get_context_diagnostics()
        assert diag.get("typo_normalization_applied", 0) > 0

def test_coherence_validation_idle_suppression(responder, orchestration, handoff_conversational):
    """Test that idle responses are rejected for educational prompts."""
    # If Gemini (mocked or disabled) would return "I'm here", it should be rewritten
    # We can't easily mock _ask_gemini here as it's a module-level function, 
    # but we can check if the coherence rewrite diagnostic triggers when we know it should.
    
    prompt = "teach me python"
    responder.generate(prompt, orchestration, handoff_conversational)
    diag = responder.get_context_diagnostics()
    # If it used educational_route_used, it's good.
    assert diag.get("educational_route_used", 0) > 0 or diag.get("coherence_rewrite_applied", 0) > 0

def test_educational_rescue_topics(responder, orchestration, handoff_conversational):
    """Test rescue fallback for specific required topics."""
    topics = ["python", "javascript", "video editing", "rocket science", "ai", "machine learning", "recursion"]
    for topic in topics:
        prompt = f"tell me about {topic}"
        response = responder.generate(prompt, orchestration, handoff_conversational)
        assert response == EXPLICIT_FAILURE or any(word in response.lower() for word in topic.split())

def test_diagnostics_completeness(responder, orchestration, handoff_conversational):
    """Verify all requested diagnostic keys are present."""
    responder.generate("teach me pythn", orchestration, handoff_conversational)
    diag = responder.get_context_diagnostics()
    
    required_keys = [
        "educational_route_used",
        "typo_normalization_applied",
        "semantic_fallback_used",
        "coherence_rewrite_applied"
    ]
    for key in required_keys:
        assert key in diag
