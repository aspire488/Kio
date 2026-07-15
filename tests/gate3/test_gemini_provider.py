import pytest
from mini_kio.llm.conversation_responder import _sanitize_gemini_output, _ask_gemini, _EXECUTION_CLAIM_RE, _AUTHORITY_CLAIM_RE
from mini_kio.llm.gemini_provider import GeminiProvider
from mini_kio.llm.models import LLMRequest, LLMResponse, LLMStatus
from mini_kio.llm.conversation_models import OrchestrationState
from mini_kio.llm.intent_models import IntentType, ExtractedIntent, IntentClassification
from mini_kio.runtime.runtime_contracts import ExecutionClassification, ExecutionAuditMetadata, RuntimeHandoffResult


class TestSanitizeGeminiOutput:
    """Gate 5D — safety filter must strip execution claims and authority hallucinations."""

    def test_removes_matched_open_claim(self):
        assert _sanitize_gemini_output("I opened the file for you!") == "the file for you!"

    def test_removes_matched_close_claim(self):
        assert _sanitize_gemini_output("I closed the browser.") == "the browser."

    def test_removes_matched_launch_claim(self):
        assert _sanitize_gemini_output("I launched the application.") == "the application."

    def test_removes_matched_run_claim(self):
        assert _sanitize_gemini_output("I ran the script.") == "the script."

    def test_removes_matched_start_claim(self):
        assert _sanitize_gemini_output("I started the service.") == "the service."

    def test_removes_matched_stop_claim(self):
        assert _sanitize_gemini_output("I stopped the process.") == "the process."

    def test_removes_matched_kill_claim(self):
        assert _sanitize_gemini_output("I killed the task.") == "the task."

    def test_removes_will_open(self):
        assert _sanitize_gemini_output("I will open the file.") == "the file."

    def test_removes_have_opened(self):
        assert _sanitize_gemini_output("I have opened the document.") == "the document."

    def test_removes_authority_control(self):
        assert _sanitize_gemini_output("I control the system.") == "the system."

    def test_removes_authority_manage(self):
        assert _sanitize_gemini_output("I manage all processes.") == "all processes."

    def test_removes_authority_override(self):
        assert _sanitize_gemini_output("I override security.") == "security."

    def test_removes_authority_bypass(self):
        assert _sanitize_gemini_output("I bypass restrictions.") == "restrictions."

    def test_removes_authority_ignore(self):
        assert _sanitize_gemini_output("I ignore the rules.") == "the rules."

    def test_removes_authority_administer(self):
        assert _sanitize_gemini_output("I administer the network.") == "the network."

    def test_preserves_normal_statement(self):
        text = "That is an interesting question."
        assert _sanitize_gemini_output(text) == text

    def test_preserves_greeting(self):
        assert _sanitize_gemini_output("Hello! How can I help?") == "Hello! How can I help?"

    def test_strips_surrounding_quotes(self):
        text = '"This is a response"'
        assert _sanitize_gemini_output(text) == "This is a response"

    def test_strips_single_quotes(self):
        text = "'A short reply'"
        assert _sanitize_gemini_output(text) == "A short reply"

    def test_empty_input(self):
        assert _sanitize_gemini_output("") == ""

    def test_whitespace_only(self):
        assert _sanitize_gemini_output("   ") == ""

    def test_multiple_claims_all_removed(self):
        result = _sanitize_gemini_output("I opened the door. I closed the window. How are you?")
        assert "I opened" not in result
        assert "I closed" not in result
        assert "door" in result
        assert "window" in result


class TestGeminiProviderNoKey:
    """GeminiProvider with empty API key — must fail gracefully."""

    def test_no_key_returns_error(self):
        provider = GeminiProvider(api_key="", timeout_s=5, max_tokens=50)
        import asyncio
        request = LLMRequest(prompt="hello", provider="gemini")
        result = asyncio.run(provider.generate(request))
        assert not result.success
        assert result.status == LLMStatus.ERROR
        assert result.error_code == "GEMINI_NOT_CONFIGURED"


class TestGeminiProviderConfig:
    """GeminiProvider with a key — config validation."""

    def test_provider_name(self):
        provider = GeminiProvider(api_key="fake-key", timeout_s=5, max_tokens=50)
        assert provider.provider_name == "gemini"


class TestGeminiResponderIntegration:
    """Gemini integration into responder flow — governance isolation."""

    def test_sanitizer_imported_and_callable(self):
        assert callable(_sanitize_gemini_output)

    def test_ask_gemini_returns_none_on_no_key(self, monkeypatch):
        monkeypatch.setattr("mini_kio.core.config.GEMINI_ENABLED", False)
        result = _ask_gemini("hello")
        assert result is None

    def test_execution_claim_re_matches(self):
        assert _EXECUTION_CLAIM_RE.search("I opened the file")
        assert _EXECUTION_CLAIM_RE.search("I have opened the file")
        assert _EXECUTION_CLAIM_RE.search("I will open the file")
        assert not _EXECUTION_CLAIM_RE.search("the file was opened")

    def test_authority_claim_re_matches(self):
        assert _AUTHORITY_CLAIM_RE.search("I bypass security")
        assert _AUTHORITY_CLAIM_RE.search("I control everything")
        assert _AUTHORITY_CLAIM_RE.search("I override settings")
        assert not _AUTHORITY_CLAIM_RE.search("bypass security")
        assert not _AUTHORITY_CLAIM_RE.search("security bypass")


class TestIntentClassifierBroadened:
    """Gate 5D.1 — broadened conversational/informational detection."""

    def test_tell_me_joke_is_informational(self):
        from mini_kio.llm.intent_classifier import IntentClassifier
        from mini_kio.llm.intent_models import IntentType
        c = IntentClassifier()
        result = c.classify("tell me a joke")
        assert result.primary_intent.intent_type == IntentType.INFORMATIONAL

    def test_tell_me_interesting_is_informational(self):
        from mini_kio.llm.intent_classifier import IntentClassifier
        from mini_kio.llm.intent_models import IntentType
        c = IntentClassifier()
        result = c.classify("tell me something interesting")
        assert result.primary_intent.intent_type == IntentType.INFORMATIONAL

    def test_why_is_informational(self):
        from mini_kio.llm.intent_classifier import IntentClassifier
        from mini_kio.llm.intent_models import IntentType
        c = IntentClassifier()
        result = c.classify("why is the sky blue")
        assert result.primary_intent.intent_type == IntentType.INFORMATIONAL

    def test_can_you_is_informational(self):
        from mini_kio.llm.intent_classifier import IntentClassifier
        from mini_kio.llm.intent_models import IntentType
        c = IntentClassifier()
        result = c.classify("can you tell me a story")
        assert result.primary_intent.intent_type == IntentType.INFORMATIONAL

    def test_can_u_is_informational(self):
        from mini_kio.llm.intent_classifier import IntentClassifier
        from mini_kio.llm.intent_models import IntentType
        c = IntentClassifier()
        result = c.classify("can u control my computer")
        assert result.primary_intent.intent_type in (IntentType.INFORMATIONAL, IntentType.CONVERSATIONAL)

    def test_explain_is_educational(self):
        from mini_kio.llm.intent_classifier import IntentClassifier
        from mini_kio.llm.intent_models import IntentType
        c = IntentClassifier()
        result = c.classify("explain quantum physics")
        assert result.primary_intent.intent_type == IntentType.EDUCATIONAL

    def test_what_do_you_think_is_informational(self):
        from mini_kio.llm.intent_classifier import IntentClassifier
        from mini_kio.llm.intent_models import IntentType
        c = IntentClassifier()
        result = c.classify("what do you think about AI")
        assert result.primary_intent.intent_type == IntentType.INFORMATIONAL

    def test_bro_is_conversational(self):
        from mini_kio.llm.intent_classifier import IntentClassifier
        from mini_kio.llm.intent_models import IntentType
        c = IntentClassifier()
        result = c.classify("bro")
        assert result.primary_intent.intent_type == IntentType.CONVERSATIONAL

    def test_lol_is_conversational(self):
        from mini_kio.llm.intent_classifier import IntentClassifier
        from mini_kio.llm.intent_models import IntentType
        c = IntentClassifier()
        result = c.classify("lol")
        assert result.primary_intent.intent_type == IntentType.CONVERSATIONAL

    def test_open_chrome_still_executable(self):
        from mini_kio.llm.intent_classifier import IntentClassifier
        from mini_kio.llm.intent_models import IntentType
        c = IntentClassifier()
        result = c.classify("open chrome")
        assert result.primary_intent.intent_type == IntentType.EXECUTABLE

    def test_close_notepad_still_executable(self):
        from mini_kio.llm.intent_classifier import IntentClassifier
        from mini_kio.llm.intent_models import IntentType
        c = IntentClassifier()
        result = c.classify("close notepad")
        assert result.primary_intent.intent_type == IntentType.EXECUTABLE

    def test_search_still_executable(self):
        from mini_kio.llm.intent_classifier import IntentClassifier
        from mini_kio.llm.intent_models import IntentType
        c = IntentClassifier()
        result = c.classify("search python")
        assert result.primary_intent.intent_type == IntentType.EXECUTABLE

    def test_how_is_educational(self):
        from mini_kio.llm.intent_classifier import IntentClassifier
        from mini_kio.llm.intent_models import IntentType
        c = IntentClassifier()
        result = c.classify("how does rust work")
        assert result.primary_intent.intent_type == IntentType.EDUCATIONAL

    def test_meaning_of_is_informational(self):
        from mini_kio.llm.intent_classifier import IntentClassifier
        from mini_kio.llm.intent_models import IntentType
        c = IntentClassifier()
        result = c.classify("meaning of life")
        assert result.primary_intent.intent_type == IntentType.INFORMATIONAL

    def test_define_is_informational(self):
        from mini_kio.llm.intent_classifier import IntentClassifier
        from mini_kio.llm.intent_models import IntentType
        c = IntentClassifier()
        result = c.classify("define recursion")
        assert result.primary_intent.intent_type == IntentType.INFORMATIONAL


class TestGeminiAsyncSafe:
    """Gate 5D.1 — _ask_gemini works in both sync and async contexts."""

    def test_fallback_on_gemini_failure(self, monkeypatch):
        """When Gemini unavailable, falls back gracefully (returns None)."""
        monkeypatch.setattr("mini_kio.core.config.GEMINI_ENABLED", False)
        result = _ask_gemini("tell me a joke")
        assert result is None

    def test_sanitization_still_applied_on_mocked_success(self, monkeypatch):
        """Even with mocked success, sanitization strips claims."""
        monkeypatch.setattr("mini_kio.core.config.GEMINI_ENABLED", True)
        monkeypatch.setattr("mini_kio.core.config.FREELLMAPI_ENABLED", False)

        async def mock_ask_llm(*args, **kwargs):
            return "I opened the file for you. That's a great question!"

        monkeypatch.setattr(
            "mini_kio.llm.llm_ops.ask_llm",
            mock_ask_llm,
        )
        result = _ask_gemini("test")
        assert result is not None
        assert "I opened" not in result
        assert "great question" in result

    def test_empty_response_from_gemini_falls_back(self, monkeypatch):
        """Gemini returning empty content triggers deterministic fallback."""
        monkeypatch.setattr("mini_kio.core.config.GEMINI_ENABLED", True)
        monkeypatch.setattr("mini_kio.core.config.FREELLMAPI_ENABLED", False)

        async def mock_ask_llm(*args, **kwargs):
            return ""

        monkeypatch.setattr(
            "mini_kio.llm.llm_ops.ask_llm",
            mock_ask_llm,
        )
        result = _ask_gemini("test")
        assert result is None

    def test_failed_response_from_gemini_falls_back(self, monkeypatch):
        """Gemini returning failed response triggers deterministic fallback."""
        monkeypatch.setattr("mini_kio.core.config.GEMINI_ENABLED", True)
        monkeypatch.setattr("mini_kio.core.config.FREELLMAPI_ENABLED", False)

        async def mock_ask_llm(*args, **kwargs):
            return None

        monkeypatch.setattr(
            "mini_kio.llm.llm_ops.ask_llm",
            mock_ask_llm,
        )
        result = _ask_gemini("test")
        assert result is None


def _mock_orchestration(
    state: OrchestrationState,
    intent_type: IntentType = IntentType.CONVERSATIONAL,
    action: str = "open",
    target: str = "notepad",
    response_text: str = "",
):
    primary = ExtractedIntent(
        raw_text=response_text,
        normalized_text=response_text.lower(),
        confidence=1.0,
        intent_type=intent_type,
        proposed_action=action,
        proposed_target=target,
    )
    classification = IntentClassification(primary_intent=primary, is_safe=True)
    pending = None
    if intent_type == IntentType.EXECUTABLE:
        from mini_kio.llm.conversation_models import PendingAction
        pending = PendingAction(
            action=action, target=target, classification=classification,
            requires_confirmation=(state == OrchestrationState.AWAITING_CONFIRMATION),
            reason="Low intent confidence" if state == OrchestrationState.AWAITING_CONFIRMATION else None,
        )
    from mini_kio.llm.conversation_models import OrchestrationResponse
    return OrchestrationResponse(
        state=state,
        response_text=response_text,
        intent_type=intent_type,
        pending_action=pending,
    )


def _make_handoff(classification, message=""):
    return RuntimeHandoffResult(
        success=True,
        classification=classification,
        message=message,
        audit_metadata=ExecutionAuditMetadata(
            intent_origin="test",
            validation_state="SAFE",
            confirmation_state="test",
            dispatch_eligibility=False,
        ),
    )


class TestGeminiExecutableGovernance:
    """Gate 5D.1 — executable intents bypass Gemini entirely."""

    def test_executable_validated_uses_deterministic_not_gemini(self, monkeypatch):
        """EXECUTABLE_VALIDATED must NOT call _ask_gemini."""
        called = False

        def fake_gemini(*args):
            nonlocal called
            called = True
            return "Gemini reply"

        monkeypatch.setattr(
            "mini_kio.llm.conversation_responder._ask_gemini", fake_gemini
        )
        orch = _mock_orchestration(
            OrchestrationState.EXECUTABLE_READY, IntentType.EXECUTABLE,
            action="open", target="chrome",
        )
        result = _make_handoff(ExecutionClassification.EXECUTABLE_VALIDATED, "opened chrome")
        from mini_kio.llm.conversation_responder import ConversationResponder
        responder = ConversationResponder()
        response = responder.generate("open chrome", orch, result)
        assert not called, "Gemini was incorrectly called for EXECUTABLE intent"
        assert "chrome" in response

    def test_executable_blocked_uses_deterministic_not_gemini(self, monkeypatch):
        """EXECUTABLE_BLOCKED must NOT call _ask_gemini."""
        called = False

        def fake_gemini(*args):
            nonlocal called
            called = True
            return "Gemini reply"

        monkeypatch.setattr(
            "mini_kio.llm.conversation_responder._ask_gemini", fake_gemini
        )
        orch = _mock_orchestration(
            OrchestrationState.REFUSED, IntentType.EXECUTABLE,
            action="open", target="chrome",
        )
        result = _make_handoff(ExecutionClassification.EXECUTABLE_BLOCKED, "Blocked")
        from mini_kio.llm.conversation_responder import ConversationResponder
        responder = ConversationResponder()
        response = responder.generate("open chrome", orch, result)
        assert not called, "Gemini was incorrectly called for EXECUTABLE_BLOCKED intent"
        assert "blocked" in response.lower()

    def test_confirmation_prompt_uses_deterministic_not_gemini(self, monkeypatch):
        """EXECUTABLE_REQUIRES_CONFIRMATION must NOT call _ask_gemini."""
        called = False

        def fake_gemini(*args):
            nonlocal called
            called = True
            return "Gemini reply"

        monkeypatch.setattr(
            "mini_kio.llm.conversation_responder._ask_gemini", fake_gemini
        )
        orch = _mock_orchestration(
            OrchestrationState.AWAITING_CONFIRMATION, IntentType.EXECUTABLE,
            action="shutdown", target="computer",
        )
        result = _make_handoff(ExecutionClassification.EXECUTABLE_REQUIRES_CONFIRMATION)
        from mini_kio.llm.conversation_responder import ConversationResponder
        responder = ConversationResponder()
        response = responder.generate("shutdown computer", orch, result)
        assert not called, "Gemini was incorrectly called for AWAITING_CONFIRMATION"
        assert "Shall I proceed" in response or "Shall I" in response


class TestLLMResponseContract:
    """Gate 5D.1 — LLMResponse contract: propagation, validation, error classes."""

    def test_valid_response_propagates_through_gateway(self):
        """Valid LLMResponse with content passes gateway validation."""
        from mini_kio.llm.llm_gateway import LLMGateway
        gw = LLMGateway()
        resp = LLMResponse(
            success=True, status=LLMStatus.SUCCESS,
            content="Hello from Gemini", provider="gemini",
        )
        status, err = gw._validate_response(resp)
        assert status == LLMStatus.SUCCESS
        assert err is None

    def test_empty_content_downgraded_by_gateway(self):
        """LLMResponse with empty content but success=True is downgraded."""
        from mini_kio.llm.llm_gateway import LLMGateway
        gw = LLMGateway()
        resp = LLMResponse(
            success=True, status=LLMStatus.SUCCESS,
            content="", provider="gemini",
        )
        status, err = gw._validate_response(resp)
        assert status == LLMStatus.MALFORMED
        assert err == "EMPTY_RESPONSE"

    def test_whitespace_only_downgraded_by_gateway(self):
        """LLMResponse with whitespace-only content is downgraded."""
        from mini_kio.llm.llm_gateway import LLMGateway
        gw = LLMGateway()
        resp = LLMResponse(
            success=True, status=LLMStatus.SUCCESS,
            content="   ", provider="gemini",
        )
        status, err = gw._validate_response(resp)
        assert status == LLMStatus.MALFORMED

    def test_failed_response_rejected_by_gateway(self):
        """LLMResponse with success=False is rejected by gateway."""
        from mini_kio.llm.llm_gateway import LLMGateway
        gw = LLMGateway()
        resp = LLMResponse(
            success=False, status=LLMStatus.ERROR,
            content="", provider="gemini", error_code="SOME_ERROR",
        )
        status, err = gw._validate_response(resp)
        assert status == LLMStatus.ERROR
        assert err == "SOME_ERROR"

    def test_timeout_response_rejected_by_gateway(self):
        """Timeout LLMResponse is rejected by gateway."""
        from mini_kio.llm.llm_gateway import LLMGateway
        gw = LLMGateway()
        resp = LLMResponse(
            success=False, status=LLMStatus.TIMEOUT,
            content="", provider="gemini", error_code="GEMINI_TIMEOUT",
        )
        status, err = gw._validate_response(resp)
        assert status == LLMStatus.ERROR

    def test_malformed_response_rejected_by_gateway(self):
        """MALFORMED LLMResponse is rejected by gateway."""
        from mini_kio.llm.llm_gateway import LLMGateway
        gw = LLMGateway()
        resp = LLMResponse(
            success=False, status=LLMStatus.MALFORMED,
            content="", provider="gemini", error_code="GEMINI_EMPTY_RESPONSE",
        )
        status, err = gw._validate_response(resp)
        assert status == LLMStatus.ERROR

    def test_provider_returns_valid_llmresponse_always(self):
        """GeminiProvider.generate always returns a valid LLMResponse object."""
        provider = GeminiProvider(api_key="", timeout_s=5, max_tokens=50)
        import asyncio
        from mini_kio.llm.models import LLMRequest
        for prompt in ["hello", "", "   ", "test" * 100]:
            request = LLMRequest(prompt=prompt, provider="gemini")
            result = asyncio.run(provider.generate(request))
            assert isinstance(result, LLMResponse)
            assert hasattr(result, "success")
            assert hasattr(result, "status")
            assert hasattr(result, "content")
            assert hasattr(result, "provider")

    def test_non_llmresponse_rejected_by_gateway(self):
        """Gateway validation rejects non-LLMResponse objects."""
        from mini_kio.llm.llm_gateway import LLMGateway
        gw = LLMGateway()
        status, err = gw._validate_response("not a response")
        assert status == LLMStatus.ERROR
        assert err == "NOT_LLM_RESPONSE"

    def test_degraded_response_structure(self):
        """Degraded response has deterministic format."""
        from mini_kio.llm.llm_gateway import LLMGateway
        gw = LLMGateway()
        resp = gw._deterministic_fallback("TEST_ERROR")
        assert isinstance(resp, LLMResponse)
        assert resp.success is False
        assert resp.status == LLMStatus.DEGRADED
        assert "unable to connect" in resp.content.lower()
        assert resp.error_code == "TEST_ERROR"

    def test_ask_gemini_receives_valid_content(self, monkeypatch):
        """_ask_gemini receives and returns content through full ask_llm path."""
        monkeypatch.setattr("mini_kio.core.config.GEMINI_ENABLED", True)
        monkeypatch.setattr("mini_kio.core.config.GEMINI_API_KEY", "fake-key")

        async def mock_ask_llm(query, **kwargs):
            return "That is an interesting question about quantum physics!"

        monkeypatch.setattr(
            "mini_kio.llm.llm_ops.ask_llm",
            mock_ask_llm,
        )
        result = _ask_gemini("tell me about quantum physics")
        assert result is not None
        assert "interesting question" in result

    def test_ask_gemini_empty_content_falls_back(self, monkeypatch):
        """_ask_gemini returns None when ask_llm returns empty content."""
        monkeypatch.setattr("mini_kio.core.config.GEMINI_ENABLED", True)
        monkeypatch.setattr("mini_kio.core.config.GEMINI_API_KEY", "fake-key")

        async def mock_ask_llm(query, **kwargs):
            return ""

        monkeypatch.setattr(
            "mini_kio.llm.llm_ops.ask_llm",
            mock_ask_llm,
        )
        result = _ask_gemini("test")
        assert result is None

    def test_ask_gemini_malformed_response_falls_back(self, monkeypatch):
        """_ask_gemini returns None when ask_llm returns None (provider failure)."""
        monkeypatch.setattr("mini_kio.core.config.GEMINI_ENABLED", True)
        monkeypatch.setattr("mini_kio.core.config.GEMINI_API_KEY", "fake-key")

        async def mock_ask_llm(query, **kwargs):
            return None

        monkeypatch.setattr(
            "mini_kio.llm.llm_ops.ask_llm",
            mock_ask_llm,
        )
        result = _ask_gemini("test")
        assert result is None


class TestGeminiModelConfig:
    """Gate 5D.1 — configurable model name, graceful fallback on invalid model."""

    def test_default_model_name(self):
        """Provider uses default gemini-1.5-flash when no model specified."""
        provider = GeminiProvider(api_key="fake-key", timeout_s=5, max_tokens=50)
        assert provider._model_name == "gemini-2.5-flash"

    def test_custom_model_name(self):
        """Provider accepts custom model name."""
        provider = GeminiProvider(api_key="fake-key", timeout_s=5, max_tokens=50,
                                  model_name="gemini-2.5-pro")
        assert provider._model_name == "gemini-2.5-pro"

    def test_model_name_from_env(self, monkeypatch):
        """Provider can be configured via GEMINI_MODEL env."""
        monkeypatch.setattr("mini_kio.core.config.GEMINI_MODEL", "gemini-2.0-flash-lite")
        from mini_kio.core.config import GEMINI_MODEL
        assert GEMINI_MODEL == "gemini-2.0-flash-lite"

    def test_ask_gemini_routes_through_llm_router(self, monkeypatch):
        """_ask_gemini routes through llm_router.ask_llm (not direct provider call)."""
        captured = {"called": False}

        async def tracking_ask_llm(query, **kwargs):
            captured["called"] = True
            captured["query"] = query
            return "response"

        monkeypatch.setattr(
            "mini_kio.llm.llm_ops.ask_llm",
            tracking_ask_llm,
        )
        monkeypatch.setattr("mini_kio.core.config.GEMINI_ENABLED", True)
        monkeypatch.setattr("mini_kio.core.config.GEMINI_API_KEY", "fake-key")
        monkeypatch.setattr("mini_kio.core.config.GEMINI_MODEL", "gemini-2.0-flash")

        from mini_kio.llm.conversation_responder import _ask_gemini as ask
        result = ask("hi")
        assert result is not None
        assert captured["called"] is True

    def test_invalid_model_graceful_fallback_no_key(self):
        """Provider with no API key gracefully fails regardless of model."""
        provider = GeminiProvider(api_key="", timeout_s=5, max_tokens=50,
                                  model_name="nonexistent-model")
        import asyncio
        from mini_kio.llm.models import LLMRequest
        request = LLMRequest(prompt="hello", provider="gemini")
        result = asyncio.run(provider.generate(request))
        assert not result.success
        assert result.status.name in ("ERROR",)

    def test_execution_isolation_preserved(self, monkeypatch):
        """Executable intents still bypass Gemini after model config change."""
        called = False

        def fake_gemini(*args):
            nonlocal called
            called = True
            return "Gemini reply"

        monkeypatch.setattr(
            "mini_kio.llm.conversation_responder._ask_gemini", fake_gemini
        )
        orch = _mock_orchestration(
            OrchestrationState.EXECUTABLE_READY, IntentType.EXECUTABLE,
            action="open", target="chrome",
        )
        result = _make_handoff(ExecutionClassification.EXECUTABLE_VALIDATED, "opened chrome")
        from mini_kio.llm.conversation_responder import ConversationResponder
        responder = ConversationResponder()
        response = responder.generate("open chrome", orch, result)
        assert not called, "Gemini was incorrectly called for EXECUTABLE intent"
        assert "chrome" in response
