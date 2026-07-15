import pytest
from mini_kio.memory.memory_store import MemoryStore
from mini_kio.llm.conversation_responder import ConversationResponder
from mini_kio.llm.intent_models import IntentType
from mini_kio.runtime.runtime_contracts import RuntimeHandoffResult, ExecutionClassification, ExecutionAuditMetadata
from mini_kio.llm.conversation_models import OrchestrationResponse, OrchestrationState

@pytest.fixture
def memory():
    m = MemoryStore(session_id="test_stabilization")
    m.clear()
    yield m
    m.clear()

@pytest.fixture
def responder():
    return ConversationResponder()

@pytest.fixture
def valid_handoff():
    audit = ExecutionAuditMetadata(intent_origin="test", validation_state="valid", confirmation_state="none", dispatch_eligibility=True)
    return RuntimeHandoffResult(success=True, classification=ExecutionClassification.CONVERSATIONAL_ONLY, message="", audit_metadata=audit)

def test_deterministic_fact_extraction(memory, responder, valid_handoff):
    responder._memory = memory
    responder._context.sync_from_memory(memory)
    
    orch = OrchestrationResponse(state=OrchestrationState.CONVERSATIONAL, response_text="")
    responder.generate("I like mangoes", orch, valid_handoff)
    
    assert memory.get_fact("preference_mangoes") == "like"
    
    responder.generate("What fruit do I like?", orch, valid_handoff)
    assert "preference_mangoes" in memory.get_all_facts()

def test_memory_ownership_validation(memory, responder):
    responder._memory = memory
    memory.append("user", "My friend likes mangoes")
    assert memory.get_fact("preference_mangoes") is None

def test_memory_conflict_handling(memory, responder):
    memory.append("user", "I like mangoes")
    assert memory.get_fact("preference_mangoes") == "like"
    
    memory.append("user", "I hate mangoes")
    assert memory.get_fact("preference_mangoes") == "dislike"

def test_memory_recall_same_session(memory, responder, valid_handoff):
    responder._memory = memory
    orch = OrchestrationResponse(state=OrchestrationState.CONVERSATIONAL, response_text="")
    responder.generate("I like mangoes", orch, valid_handoff)
    
    prompt = responder._build_bounded_prompt("test")
    assert "preference_mangoes: like" in prompt
