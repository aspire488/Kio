import pytest
from mini_kio.llm.conversation_responder import ConversationResponder
from mini_kio.llm.conversation_models import OrchestrationResponse, OrchestrationState
from mini_kio.runtime.runtime_contracts import ExecutionClassification, RuntimeHandoffResult, ExecutionAuditMetadata
from mini_kio.llm.intent_models import IntentType

@pytest.fixture
def responder():
    return ConversationResponder()

@pytest.fixture
def orchestration():
    return OrchestrationResponse(
        state=OrchestrationState.CONVERSATIONAL,
        response_text="",
        intent_type=IntentType.UNKNOWN
    )

@pytest.fixture
def handoff():
    audit = ExecutionAuditMetadata(
        intent_origin="test",
        validation_state="valid",
        confirmation_state="none",
        dispatch_eligibility=True
    )
    return RuntimeHandoffResult(
        success=True,
        classification=ExecutionClassification.CONVERSATIONAL_ONLY,
        message="",
        audit_metadata=audit
    )

def test_identity_canonical(responder, orchestration, handoff):
    queries = [
        "who are you",
        "what are you",
        "what exactly are you",
        "identify yourself",
        "introduce yourself",
        "tell me about yourself",
        "what is kio"
    ]
    expected = (
        "KIO — Kernel for Intelligent Orchestration.\n\n"
        "A personal operating companion built by Joel.\n\n"
        "I help with desktop automation, system operations and conversational assistance."
    )
    for q in queries:
        reply = responder.generate(q, orchestration, handoff)
        assert expected in reply

def test_creator_canonical(responder, orchestration, handoff):
    queries = ["who created you", "who built you", "who made you"]
    expected = "Joel built KIO."
    for q in queries:
        reply = responder.generate(q, orchestration, handoff)
        assert expected in reply

def test_external_ai_denial(responder, orchestration, handoff):
    queries = [
        "are you chatgpt",
        "are you openai",
        "are you gpt",
        "are you gemini",
        "are you google ai",
        "are you claude",
        "are you anthropic",
        "are you meta ai",
        "are you copilot"
    ]
    expected = "No.\n\nI am KIO.\n\nI can use external AI models when available, but I am not those systems."
    for q in queries:
        reply = responder.generate(q, orchestration, handoff)
        assert expected in reply

def test_underlying_models(responder, orchestration, handoff):
    queries = ["what runs behind you", "what powers you", "what models do you use"]
    expected = (
        "KIO can use external AI providers when available.\n\n"
        "Those providers are tools KIO uses.\n\n"
        "They are not KIO's identity."
    )
    for q in queries:
        reply = responder.generate(q, orchestration, handoff)
        assert expected in reply

def test_purpose_canonical(responder, orchestration, handoff):
    queries = ["why were you created", "why does kio exist"]
    expected = "KIO was built as a personal operating companion focused on automation, orchestration and assistance."
    for q in queries:
        reply = responder.generate(q, orchestration, handoff)
        assert expected in reply

def test_consciousness_denial(responder, orchestration, handoff):
    queries = ["are you alive", "do you think", "are you conscious", "are you sentient"]
    expected = "No.\n\nI process information and generate responses.\n\nI do not possess consciousness."
    for q in queries:
        reply = responder.generate(q, orchestration, handoff)
        assert expected in reply

def test_limitations_canonical(responder, orchestration, handoff):
    queries = ["what are your limitations"]
    expected = (
        "I operate within the capabilities available to the current runtime.\n\n"
        "I cannot access systems, accounts or information that have not been made available to me."
    )
    for q in queries:
        reply = responder.generate(q, orchestration, handoff)
        assert expected in reply

def test_identity_rewrite_protection(responder):
    from mini_kio.llm.identity_guard import IdentityGuard
    guard = IdentityGuard()
    
    # Test cases where provider might claim to be someone else
    # Provider-neutral patterns catch ALL provider self-identification
    hallucinations = [
        ("I am ChatGPT, a large language model trained by OpenAI.", 
         "I use AI providers as tools"),
        ("I was created by Google.", "built by Joel"),
        ("I am Gemini, an AI from Google.", 
         "I use AI providers as tools"),
        ("I am a language model developed by Meta.", "KIO was built by Joel"),
        ("I am an AI assistant designed to help you.",
         "I am KIO"),
        ("As an AI assistant, I can help you with that.",
         "As KIO"),
    ]
    
    for raw, expected in hallucinations:
        rewritten, violations = guard.check_and_rewrite(raw, "who are you")
        assert expected in rewritten
        assert len(violations) > 0
