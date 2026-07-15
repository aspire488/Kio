import requests

from mini_kio.knowledge import wikipedia_provider
from mini_kio.llm.conversation_models import OrchestrationResponse, OrchestrationState
from mini_kio.llm.conversation_responder import ConversationResponder
from mini_kio.llm.intent_models import IntentType
from mini_kio.runtime.runtime_contracts import (
    ExecutionAuditMetadata,
    ExecutionClassification,
    RuntimeHandoffResult,
)


FORBIDDEN_PHRASES = (
    "Ready.",
    "Standing by.",
    "Online.",
    "Awaiting input.",
    "Go ahead.",
)


def _mock_orchestration(text: str, intent_type=IntentType.INFORMATIONAL):
    return OrchestrationResponse(
        state=OrchestrationState.CONVERSATIONAL,
        response_text=text,
        pending_action=None,
        intent_type=intent_type,
        metadata={},
    )


def _mock_handoff(message: str):
    audit = ExecutionAuditMetadata(
        intent_origin="test",
        validation_state="SAFE",
        confirmation_state="test",
        dispatch_eligibility=False,
    )
    return RuntimeHandoffResult(
        success=True,
        classification=ExecutionClassification.CONVERSATIONAL_ONLY,
        message=message,
        audit_metadata=audit,
    )


def _assert_no_forbidden_status(reply: str):
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in reply


def test_information_query_uses_wikipedia_when_provider_unavailable(monkeypatch):
    monkeypatch.setattr("mini_kio.llm.conversation_responder._ask_gemini", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "mini_kio.knowledge.retrieval_router.fetch_summary",
        lambda query: "Kubernetes is an open-source container orchestration system.",
    )

    responder = ConversationResponder()
    reply = responder.generate(
        "What is Kubernetes?",
        _mock_orchestration("What is Kubernetes?"),
        _mock_handoff("What is Kubernetes?"),
    )

    assert "Kubernetes" in reply
    _assert_no_forbidden_status(reply)


def test_who_is_query_uses_wikipedia_when_provider_unavailable(monkeypatch):
    monkeypatch.setattr("mini_kio.llm.conversation_responder._ask_gemini", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "mini_kio.knowledge.retrieval_router.fetch_summary",
        lambda query: "Linus Torvalds is the creator of Linux and Git.",
    )

    responder = ConversationResponder()
    reply = responder.generate(
        "Who is Linus Torvalds?",
        _mock_orchestration("Who is Linus Torvalds?"),
        _mock_handoff("Who is Linus Torvalds?"),
    )

    assert "Linus Torvalds" in reply
    _assert_no_forbidden_status(reply)


def test_define_and_how_does_queries_use_same_chain(monkeypatch):
    monkeypatch.setattr("mini_kio.llm.conversation_responder._ask_gemini", lambda *args, **kwargs: None)

    def fake_fetch(query: str):
        if "memoization" in query.lower():
            return "Memoization stores previous results so repeated computations can be reused."
        return "Virtual memory maps addresses so processes can use isolated memory spaces."

    monkeypatch.setattr("mini_kio.knowledge.retrieval_router.fetch_summary", fake_fetch)

    responder = ConversationResponder()
    memo = responder.generate(
        "Define memoization",
        _mock_orchestration("Define memoization"),
        _mock_handoff("Define memoization"),
    )
    vm = responder.generate(
        "How does virtual memory work?",
        _mock_orchestration("How does virtual memory work?"),
        _mock_handoff("How does virtual memory work?"),
    )

    assert "Memoization" in memo
    assert "Virtual memory" in vm
    _assert_no_forbidden_status(memo)
    _assert_no_forbidden_status(vm)


def test_explicit_failure_when_provider_and_wikipedia_fail(monkeypatch):
    monkeypatch.setattr("mini_kio.llm.conversation_responder._ask_gemini", lambda *args, **kwargs: None)
    monkeypatch.setattr("mini_kio.knowledge.retrieval_router.fetch_summary", lambda query: None)

    responder = ConversationResponder()
    reply = responder.generate(
        "What is branch prediction?",
        _mock_orchestration("What is branch prediction?"),
        _mock_handoff("What is branch prediction?"),
    )

    assert reply == "I couldn't retrieve information for that topic right now."
    _assert_no_forbidden_status(reply)


def test_wikipedia_timeout_returns_none(monkeypatch):
    def timeout(*args, **kwargs):
        raise requests.Timeout("timed out")

    monkeypatch.setattr(wikipedia_provider.requests, "get", timeout)
    wikipedia_provider._CACHE.clear()

    assert wikipedia_provider.fetch_summary("What is memoization?") is None


def test_wikipedia_request_failure_returns_none(monkeypatch):
    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(wikipedia_provider.requests, "get", unavailable)
    wikipedia_provider._CACHE.clear()

    assert wikipedia_provider.fetch_summary("Who is Linus Torvalds?") is None


def test_wikipedia_empty_result_returns_none(monkeypatch):
    class FakeResponse:
        def __init__(self, payload, status_code=200):
            self._payload = payload
            self.status_code = status_code

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    calls = {"count": 0}

    def fake_get(url, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return FakeResponse(["q", ["Memoization"], [], []])
        return FakeResponse({"extract": ""})

    monkeypatch.setattr(wikipedia_provider.requests, "get", fake_get)
    wikipedia_provider._CACHE.clear()

    assert wikipedia_provider.fetch_summary("What is memoization?") is None
