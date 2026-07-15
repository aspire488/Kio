import pytest
from mini_kio.llm.conversation_responder import ConversationResponder
from mini_kio.llm.conversation_models import OrchestrationResponse, OrchestrationState
from mini_kio.llm.intent_models import IntentType
from mini_kio.runtime.runtime_contracts import ExecutionClassification, RuntimeHandoffResult, ExecutionAuditMetadata

@pytest.fixture
def responder():
    return ConversationResponder()

@pytest.fixture
def audit():
    return ExecutionAuditMetadata("test", "validated", "not_required", True)

def test_case_a_single_turn_educational(responder, audit):
    """Input: teach me python
    Expected: provider/wiki answer or truthful explicit failure
    Must NOT contain: 'Say "next" for more.'
    """
    orch = OrchestrationResponse(state=OrchestrationState.CONVERSATIONAL, response_text="teach me python", intent_type=IntentType.EDUCATIONAL)
    handoff = RuntimeHandoffResult(True, ExecutionClassification.CONVERSATIONAL_ONLY, "OK", audit)
    
    response = responder.generate("teach me python", orch, handoff)
    assert len(response) > 50
    assert "Python" in response or "couldn't retrieve information" in response
    assert 'Say "next" for more.' not in response
    assert "next" not in response.lower() or "keyword" in response.lower() or "language" in response.lower()
    # Specifically check it doesn't suggest continuation
    assert "say 'next'" not in response.lower()

def test_case_b_next_not_active(responder, audit):
    """Input: next
    Expected: 'Nothing is currently active to continue.'
    """
    orch = OrchestrationResponse(state=OrchestrationState.CONVERSATIONAL, response_text="next", intent_type=IntentType.CONVERSATIONAL)
    handoff = RuntimeHandoffResult(True, ExecutionClassification.CONVERSATIONAL_ONLY, "next", audit)
    
    response = responder.generate("next", orch, handoff)
    assert response == "Nothing is currently active to continue."

def test_case_c_compare_intent_no_lesson(responder, audit):
    """Input: compare python vs rust
    Expected: comparison response
    Must NOT start lesson mode.
    """
    orch = OrchestrationResponse(state=OrchestrationState.CONVERSATIONAL, response_text="compare python vs rust", intent_type=IntentType.EDUCATIONAL)
    handoff = RuntimeHandoffResult(True, ExecutionClassification.CONVERSATIONAL_ONLY, "comparison", audit)
    
    response = responder.generate("compare python vs rust", orch, handoff)
    assert "Python" in response or "Rust" in response or "comparison" in response.lower()
    assert "Lesson 1" not in response
    assert "next" not in response.lower()

def test_case_d_interrupted_educational(responder, audit):
    """Input: teach me python, then hello
    Expected: normal conversational response
    No educational ownership retained.
    """
    # 1. First turn: teach me python
    orch1 = OrchestrationResponse(state=OrchestrationState.CONVERSATIONAL, response_text="teach me python", intent_type=IntentType.EDUCATIONAL)
    handoff1 = RuntimeHandoffResult(True, ExecutionClassification.CONVERSATIONAL_ONLY, "OK", audit)
    responder.generate("teach me python", orch1, handoff1)
    
    # 2. Second turn: hello
    orch2 = OrchestrationResponse(state=OrchestrationState.CONVERSATIONAL, response_text="hello", intent_type=IntentType.CONVERSATIONAL)
    handoff2 = RuntimeHandoffResult(True, ExecutionClassification.CONVERSATIONAL_ONLY, "hello", audit)
    response2 = responder.generate("hello", orch2, handoff2)
    
    assert isinstance(response2, str)
    assert len(response2.strip()) > 0
    
    # Verify no lesson state leaked into greeting
    assert "python" not in response2.lower()
    assert "lesson" not in response2.lower()
    assert "next" not in response2.lower()

def test_case_e_what_is_machine_learning(responder, audit):
    """Input: what is machine learning
    Expected: single-turn explanation
    No lesson progression markers.
    """
    orch = OrchestrationResponse(state=OrchestrationState.CONVERSATIONAL, response_text="what is machine learning", intent_type=IntentType.EDUCATIONAL)
    handoff = RuntimeHandoffResult(True, ExecutionClassification.CONVERSATIONAL_ONLY, "OK", audit)
    
    response = responder.generate("what is machine learning", orch, handoff)
    assert "Machine learning" in response or "ML" in response or "couldn't retrieve information" in response
    assert "Lesson 1" not in response
    assert "next" not in response.lower()
