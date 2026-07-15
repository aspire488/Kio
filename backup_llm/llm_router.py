"""
llm_router.py — Direct Provider Orchestration

Gate 5.7: Removed FreeLLM from production cognition path.
KIO directly orchestrates providers in priority order:

    0: Gemini (Google AI direct)
    1: Groq (direct OpenAI-compatible API)
    2: OpenRouter (multi-model gateway)
    3: Together AI
    4: Cerebras

FreeLLM is optional experimental backend (ENABLE_FREELLM=true).
KIO fully boots without freellm server, npm, or localhost gateway.

Chain-based failover through LLMGateway.
Each provider is tried once; on failure the next is attempted.
All exhausted → deterministic offline fallback.
"""

import inspect
import os
import asyncio
import logging
import time
from typing import Optional

from mini_kio.core import config
from mini_kio.llm.llm_gateway import LLMGateway
from mini_kio.llm.gemini_provider import GeminiProvider
from mini_kio.llm.direct_providers import DirectHTTPProvider
from mini_kio.llm.huggingface_provider import HuggingFaceProvider
from mini_kio.llm.models import LLMRequest
from mini_kio.llm.provider_registry import ProviderPriority

logger = logging.getLogger(__name__)

_GATEWAY: Optional[LLMGateway] = None

# ── FreeLLM gating — OFF by default, strictly optional ────────────
_ENABLE_FREELLM = os.getenv("ENABLE_FREELLM", "false").lower() == "true"


def _get_gateway() -> LLMGateway:
    global _GATEWAY
    if _GATEWAY is None:
        _GATEWAY = LLMGateway()
        _register_providers(_GATEWAY)
    return _GATEWAY


def _register_providers(gateway: LLMGateway) -> None:
    """Register all configured providers in priority order."""

    # Priority 0: Gemini direct (primary cognition provider)
    if config.GEMINI_ENABLED:
        provider = GeminiProvider(
            api_key=config.GEMINI_API_KEY,
            timeout_s=config.GEMINI_TIMEOUT_S,
            max_tokens=config.GEMINI_MAX_TOKENS,
            model_name=config.GEMINI_MODEL,
            fallback_model_name=config.GEMINI_FALLBACK_MODEL,
        )
        gateway.register_provider(provider, priority=ProviderPriority.GEMINI.value)
        logger.info(
            f"Registered Gemini provider (priority {ProviderPriority.GEMINI.value}): "
            f"model={config.GEMINI_MODEL}"
        )

    # Priority 1: Groq (direct OpenAI-compatible API)
    if config.GROQ_ENABLED:
        provider = DirectHTTPProvider(
            name="groq",
            base_url=config.GROQ_BASE_URL,
            api_key=config.GROQ_API_KEY,
            model=config.GROQ_MODEL,
            timeout_s=config.GROQ_TIMEOUT_S,
            max_tokens=config.GROQ_MAX_TOKENS,
        )
        gateway.register_provider(provider, priority=ProviderPriority.GROQ.value)
        logger.info(
            f"Registered Groq provider (priority {ProviderPriority.GROQ.value}): "
            f"model={config.GROQ_MODEL}"
        )

    # Priority 2: Hugging Face (via OpenAI-compatible endpoint)
    if config.HUGGINGFACE_ENABLED:
        provider = HuggingFaceProvider(
            api_key=config.HUGGINGFACE_API_KEY,
            timeout_s=config.HUGGINGFACE_TIMEOUT_S,
            max_tokens=config.HUGGINGFACE_MAX_TOKENS,
            model_name=config.HUGGINGFACE_MODEL,
        )
        gateway.register_provider(provider, priority=ProviderPriority.HUGGINGFACE.value)
        logger.info(
            f"Registered Hugging Face provider (priority {ProviderPriority.HUGGINGFACE.value}): "
            f"model={config.HUGGINGFACE_MODEL}"
        )

    # Priority 3: OpenRouter (multi-model gateway)
    if config.OPENROUTER_ENABLED:
        provider = DirectHTTPProvider(
            name="openrouter",
            base_url=config.OPENROUTER_BASE_URL,
            api_key=config.OPENROUTER_API_KEY,
            model=config.OPENROUTER_MODEL,
            timeout_s=config.OPENROUTER_TIMEOUT_S,
            max_tokens=config.OPENROUTER_MAX_TOKENS,
        )
        gateway.register_provider(provider, priority=ProviderPriority.OPENROUTER.value)
        logger.info(
            f"Registered OpenRouter provider (priority {ProviderPriority.OPENROUTER.value}): "
            f"model={config.OPENROUTER_MODEL}"
        )

    # Priority 4: Together AI
    if config.TOGETHER_AI_ENABLED:
        provider = DirectHTTPProvider(
            name="together_ai",
            base_url=config.TOGETHER_AI_BASE_URL,
            api_key=config.TOGETHER_AI_API_KEY,
            model=config.TOGETHER_AI_MODEL,
            timeout_s=config.TOGETHER_AI_TIMEOUT_S,
            max_tokens=config.TOGETHER_AI_MAX_TOKENS,
        )
        gateway.register_provider(provider, priority=ProviderPriority.TOGETHER_AI.value)
        logger.info(
            f"Registered Together AI provider (priority {ProviderPriority.TOGETHER_AI.value}): "
            f"model={config.TOGETHER_AI_MODEL}"
        )

    # Priority 5: Cerebras
    if config.CEREBRAS_ENABLED:
        provider = DirectHTTPProvider(
            name="cerebras",
            base_url=config.CEREBRAS_BASE_URL,
            api_key=config.CEREBRAS_API_KEY,
            model=config.CEREBRAS_MODEL,
            timeout_s=config.CEREBRAS_TIMEOUT_S,
            max_tokens=config.CEREBRAS_MAX_TOKENS,
        )
        gateway.register_provider(provider, priority=ProviderPriority.CEREBRAS.value)
        logger.info(
            f"Registered Cerebras provider (priority {ProviderPriority.CEREBRAS.value}): "
            f"model={config.CEREBRAS_MODEL}"
        )

    # Priority 3: SambaNova
    if config.SAMBANOVA_ENABLED:
        provider = DirectHTTPProvider(
            name="sambanova",
            base_url=config.SAMBANOVA_BASE_URL,
            api_key=config.SAMBANOVA_API_KEY,
            model=config.SAMBANOVA_MODEL,
            timeout_s=config.SAMBANOVA_TIMEOUT_S,
            max_tokens=config.SAMBANOVA_MAX_TOKENS,
        )
        gateway.register_provider(provider, priority=ProviderPriority.SAMBANOVA.value)
        logger.info(
            f"Registered SambaNova provider (priority {ProviderPriority.SAMBANOVA.value}): "
            f"model={config.SAMBANOVA_MODEL}"
        )

    # Priority 4: Fireworks
    if config.FIREWORKS_ENABLED:
        provider = DirectHTTPProvider(
            name="fireworks",
            base_url=config.FIREWORKS_BASE_URL,
            api_key=config.FIREWORKS_API_KEY,
            model=config.FIREWORKS_MODEL,
            timeout_s=config.FIREWORKS_TIMEOUT_S,
            max_tokens=config.FIREWORKS_MAX_TOKENS,
        )
        gateway.register_provider(provider, priority=ProviderPriority.FIREWORKS.value)
        logger.info(
            f"Registered Fireworks provider (priority {ProviderPriority.FIREWORKS.value}): "
            f"model={config.FIREWORKS_MODEL}"
        )

    # Optional: FreeLLM experimental backend (off by default)
    if _ENABLE_FREELLM and config.FREELLMAPI_ENABLED:
        try:
            from mini_kio.llm.freellm_provider import FreeLLMProvider  # noqa: delayed import
            provider = FreeLLMProvider(
                base_url=config.FREELLMAPI_BASE_URL,
                api_key=config.FREELLMAPI_API_KEY,
                model=config.FREELLMAPI_MODEL,
                timeout_s=config.FREELLMAPI_TIMEOUT_S,
                max_tokens=config.FREELLMAPI_MAX_TOKENS,
            )
            gateway.register_provider(provider, priority=99)  # lowest priority
            logger.info(
                "Registered FreeLLM experimental backend "
                f"(priority 99): endpoint={config.FREELLMAPI_BASE_URL}"
            )
        except Exception as exc:
            logger.warning(f"FreeLLM experimental backend skipped: {exc}")

    registered = gateway.get_registry().get_providers()
    logger.info(
        f"Provider chain: {len(registered)} provider(s) registered "
        f"in order: {', '.join(registered) if registered else 'none'}"
    )
    _log_provider_health_report(gateway)


def _get_config_label(name: str, provider) -> str:
    """Return a human-readable config status for a provider.

    Uses a private event loop so we never touch the main-thread loop
    (which may be closed after a PTB run_polling restart).
    """
    try:
        hc = provider.health_check()
        if inspect.isawaitable(hc):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                healthy = loop.run_until_complete(hc)
            finally:
                loop.close()
                asyncio.set_event_loop(None)
        else:
            healthy = bool(hc)
    except Exception:
        healthy = False
    if not healthy:
        if "gemini" in name.lower():
            return "INVALID_CONFIG"
        return "MISSING_KEY"
    return "OK"


def _log_provider_health_report(gateway: LLMGateway) -> None:
    """Log a startup health report showing each provider's state."""
    registry = gateway.get_registry()
    providers = registry.get_providers()
    lines = ["Provider Health Report"]
    lines.append("=" * 40)
    for name in providers:
        state = registry.get_state(name)
        failures = registry.get_failure_count(name)
        display = state.value.upper()
        cd_until = registry._cooldown_until.get(name, 0)
        cd_info = ""
        if cd_until > time.time():
            remaining = int(cd_until - time.time())
            cd_info = f" (cooldown {remaining}s remaining)"
        # HEALTHY + 0 failures = untested / registered-only state
        if state.value == "healthy" and failures == 0 and cd_until == 0.0:
            provider = gateway._providers.get(name)
            if provider:
                config = _get_config_label(name, provider)
                display = config if config != "OK" else "REGISTERED"
        lines.append(f"  {name:<20} {display:<12} failures={failures}{cd_info}")
    if not providers:
        lines.append("  (no providers registered)")
    lines.append("=" * 40)
    logger.info("\n".join(lines))


async def ask_llm(query: str, timeout: float = 8.0, max_tokens: int = 200) -> Optional[str]:
    """
    Authoritative entry point for conversational LLM requests.
    Routes through LLMGateway → multi-provider failover chain.
    """
    gateway = _get_gateway()

    request = LLMRequest(
        prompt=query,
        max_tokens=max_tokens,
        timeout_s=timeout,
        provider="",  # Let chain decide
    )

    try:
        response = await gateway.generate(request)
        if response.success and response.content:
            return response.content.strip()
    except Exception as e:
        logger.warning(f"Unified LLM path failed: {e}")

    return None
