import pytest
import time
from mini_kio.core.command_router import handle_command
from mini_kio.core.runtime import bootstrap_runtime, get_runtime
from mini_kio.llm.response_governor import ResponseGovernor
from mini_kio.llm.intent_classifier import IntentClassifier
from mini_kio.llm.conversation_responder import ConversationResponder
from mini_kio.runtime.runtime_contracts import RuntimeHandoffResult, ExecutionClassification, ExecutionAuditMetadata
from mini_kio.llm.conversation_models import OrchestrationResponse, OrchestrationState
from mini_kio.llm.intent_models import IntentType

@pytest.fixture(autouse=True)
def setup_runtime():
    bootstrap_runtime()
    yield

def test_patch1_idle_detection_exact_match():
    governor = ResponseGovernor()
    # "production-ready" should NOT be idle
    assert not governor.is_idle_response("Kubernetes is a production-ready container orchestrator.")
    # "ready" (exact) SHOULD be idle
    assert governor.is_idle_response("ready")
    assert governor.is_idle_response("Ready.")
    # "ok" (exact) SHOULD be idle
    assert governor.is_idle_response("ok")
    # "broken" should NOT be idle (previously matched "ok" substring)
    assert not governor.is_idle_response("The system is broken.")

def test_patch2_uptime_routing():
    # Uptime query
    result = handle_command("How long have you been running?")
    assert result["success"] is True
    assert "Uptime:" in result["message"]
    
    # Verify it's not "done" or generic
    assert "s" in result["message"] or "m" in result["message"]

def test_patch3_achievement_recognition():
    responder = ConversationResponder()
    
    def get_resp(text):
        orchestration = OrchestrationResponse(
            state=OrchestrationState.CONVERSATIONAL,
            response_text=text,
            intent_type=IntentType.CONVERSATIONAL
        )
        audit = ExecutionAuditMetadata(
            intent_origin="test",
            validation_state="validated",
            confirmation_state="none",
            dispatch_eligibility=True
        )
        handoff = RuntimeHandoffResult(
            success=True,
            classification=ExecutionClassification.CONVERSATIONAL_ONLY,
            message=text,
            audit_metadata=audit
        )
        return responder.generate(text, orchestration, handoff)

    # Test exact matches
    assert get_resp("I fixed the bug") in ["Nice. That's progress.", "Good. That closes the issue.", "Clean result.", "Noted. System verified.", "Solid. Moving forward."]
    assert get_resp("it works now") in ["Nice. That's progress.", "Good. That closes the issue.", "Clean result.", "Noted. System verified.", "Solid. Moving forward."]

def test_patch4_ram_metrics_routing():
    result = handle_command("How much RAM are you using?")
    assert result["success"] is True
    assert "RAM usage:" in result["message"]
    assert "MB" in result["message"]

def test_patch5_cpu_metrics_routing():
    result = handle_command("What is your CPU usage?")
    assert result["success"] is True
    assert "CPU metrics are currently unavailable." in result["message"]

    result = handle_command("Processor usage?")
    assert result["success"] is True
    assert "CPU metrics are currently unavailable." in result["message"]

def test_patch1_real_world_kubernetes_interference():
    governor = ResponseGovernor()
    user_text = "What is Kubernetes?"
    valid_summary = "Kubernetes is a production-ready platform for orchestrating containers."
    
    # Previously, "ready" in "production-ready" would trigger mismatch
    # Now, it should NOT be a mismatch
    assert not governor.check_coherence_mismatch(valid_summary, user_text)
