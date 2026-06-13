
import pytest
import asyncio
from unittest.mock import MagicMock, patch
from mini_kio.llm.conversation_responder import ConversationResponder, _sanitize_gemini_output, _ask_gemini
from mini_kio.llm.models import LLMResponse, LLMStatus, LLMRequest
from mini_kio.llm.conversation_models import OrchestrationResponse, OrchestrationState
from mini_kio.runtime.runtime_contracts import RuntimeHandoffResult, ExecutionClassification
from mini_kio.llm.gemini_provider import GeminiProvider

def _return_and_close(value):
    def _wrap(coro):
        coro.close()
        return value
    return _wrap

def test_sanitize_gemini_output():
    # Safe response survives
    assert _sanitize_gemini_output("Hello there!") == "Hello there!"
    
    # Partial stripping preserves safe remainder
    assert _sanitize_gemini_output("I will open Chrome for you.") == "Chrome for you."
    assert _sanitize_gemini_output("Sure! I've opened the file.") == "Sure! the file."
    
    # Authority claim stripping
    assert _sanitize_gemini_output("I control the system.") == "the system."
    
    # Multiple claims
    assert _sanitize_gemini_output("I opened Chrome and I will close it.") == "Chrome and it."
    
    # Empty after sanitize
    assert _sanitize_gemini_output("I will open ") == ""

@patch("mini_kio.llm.conversation_responder.asyncio.get_running_loop")
@patch("mini_kio.llm.conversation_responder.asyncio.run")
@patch("mini_kio.core.llm_router.ask_llm")
@patch("mini_kio.core.config.GEMINI_ENABLED", True)
def test_ask_gemini_logic(mock_ask_llm, mock_asyncio_run, mock_get_loop):
    # Mock ask_llm to return a valid response
    mock_ask_llm.return_value = "Hello! I am KIO."
    # Simulate synchronous context (no running loop)
    mock_get_loop.side_effect = RuntimeError("No loop")
    mock_asyncio_run.side_effect = _return_and_close("Hello! I am KIO.")
    
    res = _ask_gemini("hi")
    assert res == "Hello! I am KIO."
    
    # Mock fully stripped response
    mock_ask_llm.return_value = "I will open "
    mock_asyncio_run.side_effect = _return_and_close("I will open ")
    res = _ask_gemini("hi")
    assert res is None # Should trigger fallback
    
    # Mock failed LLM
    mock_ask_llm.return_value = None
    mock_asyncio_run.side_effect = _return_and_close(None)
    res = _ask_gemini("hi")
    assert res is None

def test_responder_bypasses_fallback_on_valid_gemini():
    from mini_kio.runtime.runtime_contracts import ExecutionAuditMetadata
    responder = ConversationResponder()
    orchestration = OrchestrationResponse(state=OrchestrationState.CONVERSATIONAL, response_text="")
    
    audit = ExecutionAuditMetadata(
        intent_origin="test",
        validation_state="test",
        confirmation_state="test",
        dispatch_eligibility=True
    )
    handoff_result = RuntimeHandoffResult(
        success=True,
        classification=ExecutionClassification.CONVERSATIONAL_ONLY,
        message="",
        audit_metadata=audit
    )
    
    with patch("mini_kio.llm.conversation_responder._ask_gemini") as mock_ask:
        mock_ask.return_value = "This is a real Gemini response."
        resp = responder.generate("hello", orchestration, handoff_result)
        assert resp != "This is a real Gemini response."
        assert resp
        mock_ask.assert_not_called()
        
        mock_ask.return_value = None # Fallback triggered
        resp = responder.generate("hello", orchestration, handoff_result)
        assert resp != "This is a real Gemini response."
        assert resp

def test_gateway_json_validation_relaxed():
    from mini_kio.llm.llm_gateway import LLMGateway
    gateway = LLMGateway()
    
    # Response with braces but NOT an intent should pass
    resp = LLMResponse(success=True, status=LLMStatus.SUCCESS, content="Hello {world}")
    status, error = gateway._validate_response(resp)
    assert status == LLMStatus.SUCCESS
    assert error is None
    
    # Response with intent_type MUST be valid JSON
    resp_intent = LLMResponse(success=True, status=LLMStatus.SUCCESS, content='{"intent_type": "invalid"}')
    status, error = gateway._validate_response(resp_intent)
    assert status == LLMStatus.SUCCESS
    
    # Test MISSING_JSON_BRACES
    resp_no_close = LLMResponse(success=True, status=LLMStatus.SUCCESS, content='{"intent_type": "broken"')
    status, error = gateway._validate_response(resp_no_close)
    assert status == LLMStatus.MALFORMED
    assert error == "MISSING_JSON_BRACES"

    # Test INVALID_JSON_STRUCTURE (has braces but invalid content)
    resp_bad_json = LLMResponse(success=True, status=LLMStatus.SUCCESS, content='{"intent_type": "broken", }')
    status, error = gateway._validate_response(resp_bad_json)
    assert status == LLMStatus.MALFORMED
    assert error == "INVALID_JSON_STRUCTURE"


class TestGeminiProviderFixes:
    """Tests for Gate 5D.1 — robust Gemini response extraction."""

    def test_extraction_success(self):
        async def _test():
            with patch("mini_kio.llm.gemini_provider.genai") as mock_genai:
                provider = GeminiProvider(api_key="test-key")
                mock_model = MagicMock()
                provider._model = mock_model
                
                mock_result = MagicMock()
                mock_result.text = "Hello world"
                mock_model.generate_content.return_value = mock_result
                
                request = LLMRequest(prompt="hi", provider="gemini")
                response = await provider.generate(request)
                
                assert response.success
                assert response.content == "Hello world"
        asyncio.run(_test())

    def test_extraction_value_error_fallback(self):
        """Test fallback when result.text raises ValueError."""
        async def _test():
            with patch("mini_kio.llm.gemini_provider.genai") as mock_genai:
                provider = GeminiProvider(api_key="test-key")
                mock_model = MagicMock()
                provider._model = mock_model
                
                mock_result = MagicMock()
                # Simulate result.text raising ValueError (common for blocked responses)
                type(mock_result).text = property(lambda x: (_ for _ in ()).throw(ValueError("Quick extraction failed")))
                
                # Setup fallback candidates
                mock_candidate = MagicMock()
                mock_candidate.content.parts = [MagicMock(text="Fallback text")]
                mock_result.candidates = [mock_candidate]
                
                mock_model.generate_content.return_value = mock_result
                
                request = LLMRequest(prompt="hi", provider="gemini")
                response = await provider.generate(request)
                
                # Before fix, this might fail or return ""
                # After fix, it should return "Fallback text"
                assert response.success
                assert response.content == "Fallback text"
        asyncio.run(_test())

    def test_extraction_blocked_response(self):
        """Test handling when response is blocked (no candidates, text raises)."""
        async def _test():
            with patch("mini_kio.llm.gemini_provider.genai") as mock_genai:
                provider = GeminiProvider(api_key="test-key")
                provider._fallback_model = None  # prevent fallback activation
                mock_model = MagicMock()
                provider._model = mock_model
                
                mock_result = MagicMock()
                type(mock_result).text = property(lambda x: (_ for _ in ()).throw(ValueError("Blocked")))
                mock_result.candidates = []
                mock_result.prompt_feedback = MagicMock()
                
                mock_model.generate_content.return_value = mock_result
                
                request = LLMRequest(prompt="hi", provider="gemini")
                response = await provider.generate(request)
                
                assert not response.success
                assert response.error_code in ("GEMINI_EMPTY_RESPONSE", "GEMINI_ERROR")
        asyncio.run(_test())

    def test_extraction_empty_result(self):
        async def _test():
            with patch("mini_kio.llm.gemini_provider.genai") as mock_genai:
                provider = GeminiProvider(api_key="test-key")
                provider._fallback_model = None  # prevent fallback activation
                mock_model = MagicMock()
                provider._model = mock_model
                
                mock_model.generate_content.return_value = None
                
                request = LLMRequest(prompt="hi", provider="gemini")
                response = await provider.generate(request)
                
                assert not response.success
                assert response.error_code == "GEMINI_EMPTY_RESPONSE"
        asyncio.run(_test())
