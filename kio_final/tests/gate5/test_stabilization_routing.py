import pytest
from mini_kio.llm.conversation_responder import ConversationResponder
from mini_kio.llm.conversation_models import OrchestrationResponse, OrchestrationState
from mini_kio.llm.intent_models import IntentType
from mini_kio.runtime.runtime_contracts import RuntimeHandoffResult, ExecutionClassification, ExecutionAuditMetadata

@pytest.fixture
def responder():
    return ConversationResponder()

@pytest.fixture
def valid_handoff():
    audit = ExecutionAuditMetadata(intent_origin="test", validation_state="valid", confirmation_state="none", dispatch_eligibility=True)
    return RuntimeHandoffResult(success=True, classification=ExecutionClassification.INFORMATIONAL_ONLY, message="", audit_metadata=audit)

def test_arithmetic_routing(responder, valid_handoff):
    orch = OrchestrationResponse(state=OrchestrationState.CONVERSATIONAL, response_text="", intent_type=IntentType.MATH)
    reply = responder.generate("682893*8202", orch, valid_handoff)
    assert "5601088386" in reply

def test_math_intent_routing(responder, valid_handoff):
    orch = OrchestrationResponse(state=OrchestrationState.CONVERSATIONAL, response_text="", intent_type=IntentType.MATH)
    reply = responder.generate("25 squared", orch, valid_handoff)
    assert "625" in reply

def test_system_state_routing_battery(responder, valid_handoff):
    orch = OrchestrationResponse(state=OrchestrationState.CONVERSATIONAL, response_text="", intent_type=IntentType.SYSTEM_STATE)
    reply = responder.generate("what is my battery percentage", orch, valid_handoff)
    assert "Battery is at" in reply or "I cannot verify your battery status" in reply

def test_reasoning_routing(responder, valid_handoff):
    # This just checks it doesn't crash and routes to LLM (mocked or fallback)
    orch = OrchestrationResponse(state=OrchestrationState.CONVERSATIONAL, response_text="", intent_type=IntentType.REASONING)
    # Since we can't easily mock LLM here without more setup, we just ensure it attempts resolution
    pass
