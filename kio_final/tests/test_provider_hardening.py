import pytest
from mini_kio.core import llm_router, config
from mini_kio.llm.provider_registry import ProviderPriority
from mini_kio.llm.models import LLMResponse, LLMStatus
from unittest.mock import patch, AsyncMock
import httpx
import asyncio

# Fixture to reset the LLM gateway singleton before each test
@pytest.fixture(autouse=True)
def reset_llm_gateway():
    llm_router._GATEWAY = None

# Fixture to mock _log_provider_health_report to prevent asyncio.run issues
@pytest.fixture(autouse=True)
def mock_provider_health_report():
    with patch("mini_kio.core.llm_router._log_provider_health_report") as mock_log:
        yield mock_log

@pytest.fixture
def mock_gemini_provider_generate():
    """Mocks GeminiProvider.generate to return a successful LLM response."""
    with patch("mini_kio.llm.gemini_provider.GeminiProvider.generate", new_callable=AsyncMock) as mock_generate:
        mock_generate.return_value = LLMResponse(
            success=True, status=LLMStatus.SUCCESS, content="mocked gemini response", provider="gemini"
        )
        yield mock_generate

@pytest.fixture
def mock_direct_http_provider_generate():
    """Mocks DirectHTTPProvider.generate to return a successful LLM response."""
    with patch("mini_kio.llm.direct_providers.DirectHTTPProvider.generate", new_callable=AsyncMock) as mock_generate:
        mock_generate.return_value = LLMResponse(
            success=True, status=LLMStatus.SUCCESS, content="mocked direct http response", provider="mocked_provider"
        )
        yield mock_generate

def test_provider_registry_loads_correctly(monkeypatch):
    """Verify that the LLMGateway can be initialized and registers providers without errors."""
    # Ensure all providers are enabled for this test to check registry loading
    monkeypatch.setenv("GEMINI_API_KEY", "test_gemini_key")
    monkeypatch.setenv("GEMINI_ENABLED", "true")
    monkeypatch.setenv("GROQ_API_KEY", "test_groq_key")
    monkeypatch.setenv("GROQ_ENABLED", "true")
    monkeypatch.setenv("CEREBRAS_API_KEY", "test_cerebras_key")
    monkeypatch.setenv("CEREBRAS_ENABLED", "true")
    monkeypatch.setenv("SAMBANOVA_API_KEY", "test_sambanova_key")
    monkeypatch.setenv("SAMBANOVA_ENABLED", "true")
    monkeypatch.setenv("FIREWORKS_API_KEY", "test_fireworks_key")
    monkeypatch.setenv("FIREWORKS_ENABLED", "true")
    config._reset_env_loaded()
    config._ensure_env_loaded()

    gateway = llm_router._get_gateway()
    assert gateway is not None
    registry = gateway.get_registry()
    assert registry is not None
    assert len(registry.get_providers()) > 0, "No providers were registered."

def test_provider_count_names_and_priorities(monkeypatch):
    """
    Verify the count, names, and priorities of registered providers match the expected configuration.
    Expected order: Gemini, Groq, Cerebras, SambaNova, Fireworks.
    """
    # Ensure all providers are enabled for this test to check registry order
    monkeypatch.setenv("GEMINI_API_KEY", "test_gemini_key")
    monkeypatch.setenv("GEMINI_ENABLED", "true")
    monkeypatch.setenv("GROQ_API_KEY", "test_groq_key")
    monkeypatch.setenv("GROQ_ENABLED", "true")
    monkeypatch.setenv("CEREBRAS_API_KEY", "test_cerebras_key")
    monkeypatch.setenv("CEREBRAS_ENABLED", "true")
    monkeypatch.setenv("SAMBANOVA_API_KEY", "test_sambanova_key")
    monkeypatch.setenv("SAMBANOVA_ENABLED", "true")
    monkeypatch.setenv("FIREWORKS_API_KEY", "test_fireworks_key")
    monkeypatch.setenv("FIREWORKS_ENABLED", "true")
    config._reset_env_loaded()
    config._ensure_env_loaded()

    gateway = llm_router._get_gateway()
    registry = gateway.get_registry()

    expected_providers = [
        ("gemini", ProviderPriority.GEMINI.value),
        ("groq", ProviderPriority.GROQ.value),
        ("cerebras", ProviderPriority.CEREBRAS.value),
        ("sambanova", ProviderPriority.SAMBANOVA.value),
        ("fireworks", ProviderPriority.FIREWORKS.value),
    ]

    registered_providers = registry.get_providers()
    
    assert len(registered_providers) == len(expected_providers), (
        f"Expected {len(expected_providers)} providers, but got {len(registered_providers)}: "
        f"{registered_providers}"
    )

    for i, (name, priority) in enumerate(expected_providers):
        actual_name = registered_providers[i]
        actual_priority = registry._priority_map.get(actual_name)

        assert actual_name == name, (
            f"Provider at index {i} is '{actual_name}', but expected '{name}'."
        )
        assert actual_priority == priority, (
            f"Provider '{actual_name}' has priority {actual_priority}, but expected {priority}."
        )

@pytest.mark.asyncio
async def test_smoke_test_gemini(monkeypatch, mock_gemini_provider_generate):
    """Verify Gemini provider can process a 'hello' prompt and return content."""
    monkeypatch.setenv("GEMINI_API_KEY", "test_gemini_key")
    monkeypatch.setenv("GEMINI_ENABLED", "true")
    monkeypatch.setenv("GROQ_ENABLED", "false")
    monkeypatch.setenv("CEREBRAS_ENABLED", "false")
    monkeypatch.setenv("SAMBANOVA_ENABLED", "false")
    monkeypatch.setenv("FIREWORKS_ENABLED", "false")
    config._reset_env_loaded()
    config._ensure_env_loaded()

    response = await llm_router.ask_llm("hello")
    assert response == "mocked gemini response"
    mock_gemini_provider_generate.assert_called_once()

@pytest.mark.asyncio
async def test_smoke_test_groq(monkeypatch, mock_direct_http_provider_generate):
    """Verify Groq provider can process a 'hello' prompt and return content."""
    monkeypatch.setenv("GEMINI_ENABLED", "false")
    monkeypatch.setenv("GROQ_API_KEY", "test_groq_key")
    monkeypatch.setenv("GROQ_ENABLED", "true")
    monkeypatch.setenv("CEREBRAS_ENABLED", "false")
    monkeypatch.setenv("SAMBANOVA_ENABLED", "false")
    monkeypatch.setenv("FIREWORKS_ENABLED", "false")
    config._reset_env_loaded()
    config._ensure_env_loaded()

    response = await llm_router.ask_llm("hello")
    assert response == "mocked direct http response"
    mock_direct_http_provider_generate.assert_called_once()


@pytest.mark.asyncio
async def test_smoke_test_cerebras(monkeypatch, mock_direct_http_provider_generate):
    """Verify Cerebras provider can process a 'hello' prompt and return content."""
    monkeypatch.setenv("GEMINI_ENABLED", "false")
    monkeypatch.setenv("GROQ_ENABLED", "false")
    monkeypatch.setenv("CEREBRAS_API_KEY", "test_cerebras_key")
    monkeypatch.setenv("CEREBRAS_ENABLED", "true")
    monkeypatch.setenv("SAMBANOVA_ENABLED", "false")
    monkeypatch.setenv("FIREWORKS_ENABLED", "false")
    config._reset_env_loaded()
    config._ensure_env_loaded()

    response = await llm_router.ask_llm("hello")
    assert response == "mocked direct http response"
    mock_direct_http_provider_generate.assert_called_once()


@pytest.mark.asyncio
async def test_smoke_test_sambanova(monkeypatch, mock_direct_http_provider_generate):
    """Verify SambaNova provider can process a 'hello' prompt and return content."""
    monkeypatch.setenv("GEMINI_ENABLED", "false")
    monkeypatch.setenv("GROQ_ENABLED", "false")
    monkeypatch.setenv("CEREBRAS_ENABLED", "false")
    monkeypatch.setenv("SAMBANOVA_API_KEY", "test_sambanova_key")
    monkeypatch.setenv("SAMBANOVA_ENABLED", "true")
    monkeypatch.setenv("FIREWORKS_ENABLED", "false")
    config._reset_env_loaded()
    config._ensure_env_loaded()

    response = await llm_router.ask_llm("hello")
    assert response == "mocked direct http response"
    mock_direct_http_provider_generate.assert_called_once()


@pytest.mark.asyncio
async def test_smoke_test_fireworks(monkeypatch, mock_direct_http_provider_generate):
    """Verify Fireworks provider can process a 'hello' prompt and return content."""
    monkeypatch.setenv("GEMINI_ENABLED", "false")
    monkeypatch.setenv("GROQ_ENABLED", "false")
    monkeypatch.setenv("CEREBRAS_ENABLED", "false")
    monkeypatch.setenv("SAMBANOVA_ENABLED", "false")
    monkeypatch.setenv("FIREWORKS_API_KEY", "test_fireworks_key")
    monkeypatch.setenv("FIREWORKS_ENABLED", "true")
    config._reset_env_loaded()
    config._ensure_env_loaded()

    response = await llm_router.ask_llm("hello")
    assert response == "mocked direct http response"
    mock_direct_http_provider_generate.assert_called_once()

@pytest.mark.asyncio
async def test_provider_failover(
    monkeypatch,
    mock_gemini_provider_generate,
    mock_direct_http_provider_generate
):
    """
    Verify that if the first provider fails, the system attempts to use the next one.
    Scenario: Gemini fails, Groq succeeds.
    """
    # Configure env vars to enable both Gemini and Groq
    monkeypatch.setenv("GEMINI_API_KEY", "test_gemini_key")
    monkeypatch.setenv("GEMINI_ENABLED", "true")
    monkeypatch.setenv("GROQ_API_KEY", "test_groq_key")
    monkeypatch.setenv("GROQ_ENABLED", "true")
    monkeypatch.setenv("CEREBRAS_ENABLED", "false")
    monkeypatch.setenv("SAMBANOVA_ENABLED", "false")
    monkeypatch.setenv("FIREWORKS_ENABLED", "false")
    config._reset_env_loaded()
    config._ensure_env_loaded()

    # Make Gemini's generate method fail
    mock_gemini_provider_generate.return_value = LLMResponse(
        success=False, status=LLMStatus.ERROR, content="", error_code="GEMINI_ERROR", provider="gemini"
    )
    # Make DirectHTTPProvider's generate method succeed (this will be Groq)
    mock_direct_http_provider_generate.return_value = LLMResponse(
        success=True, status=LLMStatus.SUCCESS, content="mocked groq response", provider="groq"
    )

    response = await llm_router.ask_llm("hello")

    # Assert that Gemini's generate was called and failed
    mock_gemini_provider_generate.assert_called_once()
    # Assert that DirectHTTPProvider's generate (Groq) was called and succeeded
    mock_direct_http_provider_generate.assert_called_once()
    assert response == "mocked groq response"
