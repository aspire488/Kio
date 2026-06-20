"""
Tests for OllamaProvider — local LLM fallback via Ollama API.
"""

import asyncio
import json
import httpx
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from mini_kio.llm.ollama_provider import OllamaProvider
from mini_kio.llm.models import LLMRequest, LLMResponse, LLMStatus
from mini_kio.llm.provider_registry import ProviderPriority
from mini_kio.llm.llm_gateway import LLMGateway


@pytest.fixture
def provider():
    return OllamaProvider(
        base_url="http://localhost:11434",
        model="qwen3:8b",
        timeout_s=5.0,
        max_tokens=128,
    )


@pytest.fixture
def request_obj():
    return LLMRequest(
        prompt="What is the capital of France?",
        max_tokens=64,
        timeout_s=5.0,
        provider="ollama",
    )


def _mock_response(status_code=200, json_data=None):
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = json_data or {}
    return m


def _patch_ollama(mock_response=None, side_effect=None):
    """Patch httpx.AsyncClient to return a controlled mock response."""
    mock_client = AsyncMock()
    if side_effect:
        mock_client.post.side_effect = side_effect
    else:
        mock_client.post.return_value = mock_response or _mock_response()
    return patch("httpx.AsyncClient", return_value=mock_client)


class TestProviderIdentity:
    def test_provider_name(self, provider):
        assert provider.provider_name == "ollama"

    def test_provider_priority(self):
        assert ProviderPriority.OLLAMA.value == 8


class TestSuccessfulGeneration:
    @pytest.mark.asyncio
    async def test_success_response(self, provider, request_obj):
        mock_json = {"message": {"content": "The capital of France is Paris."}}
        mock_resp = _mock_response(json_data=mock_json)

        with _patch_ollama(mock_response=mock_resp):
            result = await provider.generate(request_obj)

            assert result.success is True
            assert result.status == LLMStatus.SUCCESS
            assert "capital" in result.content
            assert "Paris" in result.content
            assert result.provider == "ollama"
            assert result.latency_ms > 0

    @pytest.mark.asyncio
    async def test_success_long_response(self, provider):
        mock_json = {
            "message": {
                "content": (
                    "The Eiffel Tower is located in Paris, France. "
                    "It was constructed between 1887 and 1889. "
                    "It stands 330 meters tall."
                )
            }
        }
        mock_resp = _mock_response(json_data=mock_json)
        req = LLMRequest(prompt="Tell me about the Eiffel Tower", max_tokens=256, timeout_s=10.0)

        with _patch_ollama(mock_response=mock_resp):
            result = await provider.generate(req)

            assert result.success is True
            assert len(result.content) > 50
            assert "Eiffel Tower" in result.content


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_connection_refused(self, provider, request_obj):
        with _patch_ollama(side_effect=httpx.ConnectError("Connection refused")):
            result = await provider.generate(request_obj)

            assert result.success is False
            assert result.status == LLMStatus.ERROR
            assert result.error_code == "OLLAMA_UNREACHABLE"
            assert result.provider == "ollama"

    @pytest.mark.asyncio
    async def test_timeout(self, provider, request_obj):
        with _patch_ollama(side_effect=asyncio.TimeoutError(" simulated")):
            result = await provider.generate(request_obj)

            assert result.success is False
            assert result.status == LLMStatus.TIMEOUT
            assert result.error_code == "OLLAMA_TIMEOUT"
            assert result.provider == "ollama"

    @pytest.mark.asyncio
    async def test_http_500_error(self, provider, request_obj):
        mock_resp = _mock_response(status_code=500)
        mock_resp.text = "Internal Server Error"

        with _patch_ollama(mock_response=mock_resp):
            result = await provider.generate(request_obj)

            assert result.success is False
            assert result.status == LLMStatus.MALFORMED
            assert result.error_code == "OLLAMA_EMPTY_RESPONSE"

    @pytest.mark.asyncio
    async def test_malformed_json_response(self, provider, request_obj):
        mock_resp = _mock_response()
        mock_resp.json.side_effect = json.JSONDecodeError("msg", "doc", 0)

        with _patch_ollama(mock_response=mock_resp):
            result = await provider.generate(request_obj)

            assert result.success is False
            assert result.status == LLMStatus.MALFORMED
            assert result.error_code == "OLLAMA_EMPTY_RESPONSE"

    @pytest.mark.asyncio
    async def test_empty_content_in_response(self, provider, request_obj):
        mock_resp = _mock_response(json_data={"message": {"content": ""}})

        with _patch_ollama(mock_response=mock_resp):
            result = await provider.generate(request_obj)

            assert result.success is False
            assert result.status == LLMStatus.MALFORMED
            assert result.error_code == "OLLAMA_EMPTY_RESPONSE"

    @pytest.mark.asyncio
    async def test_missing_message_key(self, provider, request_obj):
        mock_resp = _mock_response(json_data={"done": True, "error": "model not found"})

        with _patch_ollama(mock_response=mock_resp):
            result = await provider.generate(request_obj)

            assert result.success is False
            assert result.error_code == "OLLAMA_EMPTY_RESPONSE"

    @pytest.mark.asyncio
    async def test_thinking_field_fallback(self, provider, request_obj):
        """When content is empty but thinking field has content, use thinking."""
        mock_json = {
            "message": {
                "content": "",
                "thinking": "The capital of France is Paris. I am sure about this.",
            }
        }
        mock_resp = _mock_response(json_data=mock_json)

        with _patch_ollama(mock_response=mock_resp):
            result = await provider.generate(request_obj)

            assert result.success is True
            assert result.status == LLMStatus.SUCCESS
            assert "capital" in result.content
            assert "Paris" in result.content


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_online(self, provider):
        mock_resp = _mock_response(json_data={"message": {"content": "pong"}})

        with _patch_ollama(mock_response=mock_resp):
            healthy = await provider.health_check()
            assert healthy is True

    @pytest.mark.asyncio
    async def test_health_check_offline(self, provider):
        with _patch_ollama(side_effect=httpx.ConnectError("Connection refused")):
            healthy = await provider.health_check()
            assert healthy is False


class TestGatewayIntegration:
    @pytest.mark.asyncio
    async def test_ollama_registered_in_gateway(self):
        gateway = LLMGateway()
        provider = OllamaProvider(timeout_s=2.0, max_tokens=32)
        gateway.register_provider(provider, priority=ProviderPriority.OLLAMA.value)

        chain = gateway.get_registry().get_providers()
        assert "ollama" in chain

    @pytest.mark.asyncio
    async def test_ollama_last_in_chain(self):
        gateway = LLMGateway()
        provider = OllamaProvider(timeout_s=2.0, max_tokens=32)
        gateway.register_provider(provider, priority=ProviderPriority.OLLAMA.value)

        chain = gateway.get_registry().get_providers()
        assert chain[-1] == "ollama"

    @pytest.mark.asyncio
    async def test_gateway_uses_ollama_when_only_provider(self):
        gateway = LLMGateway()
        provider = OllamaProvider(timeout_s=5.0, max_tokens=64)
        gateway.register_provider(provider, priority=0)

        mock_resp = _mock_response(json_data={"message": {"content": "Paris is the capital of France."}})
        req = LLMRequest(prompt="What is the capital of France?", max_tokens=64, timeout_s=5.0)

        with _patch_ollama(mock_response=mock_resp):
            result = await gateway.generate(req)

            assert result.success is True
            assert result.provider == "ollama"
            assert "Paris" in result.content

    @pytest.mark.asyncio
    async def test_gateway_falls_through_on_ollama_failure(self):
        gateway = LLMGateway()
        provider = OllamaProvider(timeout_s=2.0, max_tokens=32)
        gateway.register_provider(provider, priority=0)

        with _patch_ollama(side_effect=httpx.ConnectError("Connection refused")):
            req = LLMRequest(prompt="test", max_tokens=16, timeout_s=2.0)
            result = await gateway.generate(req)

            assert result.success is False
            assert result.status == LLMStatus.DEGRADED
            assert "unable to connect" in result.content.lower()


class TestChainPosition:
    def test_priority_8_is_lowest(self):
        cloud_priorities = [
            ProviderPriority.GEMINI.value,
            ProviderPriority.GROQ.value,
            ProviderPriority.CEREBRAS.value,
            ProviderPriority.SAMBANOVA.value,
            ProviderPriority.FIREWORKS.value,
            ProviderPriority.HUGGINGFACE.value,
            ProviderPriority.OPENROUTER.value,
            ProviderPriority.TOGETHER_AI.value,
        ]
        assert all(p < ProviderPriority.OLLAMA.value for p in cloud_priorities)


class TestClientCleanup:
    @pytest.mark.asyncio
    async def test_close_client(self, provider):
        await provider.close()
