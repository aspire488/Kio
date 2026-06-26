"""
llm_router.py — Direct Provider Orchestration

Two-phase routing:

  Phase 1 — NVIDIA PRIMARY: Deterministic NVIDIA-first routing.
  All standard cognition task types (chat, reasoning, planning, coding,
  debugging, vision) route to NVIDIA NIM first. Model selection is
  task-aware: chat/reasoning/planning → Maverick, coding/debugging →
  GPT-OSS, vision → Qwen.

  Phase 2 — FAILOVER CHAIN: When NVIDIA fails, KIO falls through to the
  multi-provider failover chain. Primary + hot failover registered at
  startup; the rest are lazy-loaded on first use.

Provider order (Phase 2 failover chain):
    0: Gemini (Google AI direct)
    1: Groq (direct OpenAI-compatible API)
    2: NVIDIA NIM
    3: Cerebras
    4: SambaNova
    5: Fireworks
    6: Hugging Face
    7: OpenRouter
    8: Together AI
    9: Ollama (local)

FreeLLM is optional experimental backend (ENABLE_FREELLM=true).
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
from mini_kio.llm.nvidia_provider import NvidiaProvider
from mini_kio.llm.models import LLMRequest
from mini_kio.llm.provider_registry import ProviderPriority

logger = logging.getLogger(__name__)

_GATEWAY: Optional[LLMGateway] = None
_LAZY_LOCKED = False

_NVIDIA_PRIMARY_TASKS = frozenset({
    "chat", "reasoning", "planning",
    "coding", "debugging", "vision",
})

_ENABLE_FREELLM = os.getenv("ENABLE_FREELLM", "false").lower() == "true"


def _get_gateway() -> LLMGateway:
    global _GATEWAY
    if _GATEWAY is None:
        _GATEWAY = LLMGateway()
        _register_primary_providers(_GATEWAY)
    return _GATEWAY


def _register_primary_providers(gateway: LLMGateway) -> None:
    """Register only PRIMARY + HOT FAILOVER providers at startup.

    Primary:
      - NVIDIA

    Hot failover (registered at startup):
      - Groq
      - Cerebras

    Lazy-loaded (on first use):
      - Gemini, OpenRouter, Together, Fireworks, SambaNova,
        HuggingFace, Ollama
    """
    # ── PRIMARY: NVIDIA ──────────────────────────────────────────────
    if config.NVIDIA_ENABLED:
        provider = NvidiaProvider(
            api_key=config.NVIDIA_API_KEY,
            base_url=config.NVIDIA_BASE_URL,
            primary_model=config.NVIDIA_PRIMARY_MODEL,
            code_model=config.NVIDIA_CODE_MODEL,
            vision_model=config.NVIDIA_VISION_MODEL,
            fallback_model=config.NVIDIA_FALLBACK_MODEL,
            timeout_s=config.NVIDIA_TIMEOUT_S,
            max_tokens=config.NVIDIA_MAX_TOKENS,
        )
        gateway.register_provider(provider, priority=ProviderPriority.NVIDIA.value)
        logger.info(
            "Registered NVIDIA provider (priority %d): "
            "primary=%s, code=%s, vision=%s",
            ProviderPriority.NVIDIA.value,
            config.NVIDIA_PRIMARY_MODEL,
            config.NVIDIA_CODE_MODEL,
            config.NVIDIA_VISION_MODEL,
        )

    # ── HOT FAILOVER 1: Groq ─────────────────────────────────────────
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
            "Registered Groq provider (priority %d): model=%s",
            ProviderPriority.GROQ.value, config.GROQ_MODEL,
        )

    # ── HOT FAILOVER 2: Cerebras ─────────────────────────────────────
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
            "Registered Cerebras provider (priority %d): model=%s",
            ProviderPriority.CEREBRAS.value, config.CEREBRAS_MODEL,
        )

    _log_startup_summary(gateway)


def _lazy_register_remaining(gateway: LLMGateway) -> None:
    """Lazy-register non-primary providers on first failover use."""
    global _LAZY_LOCKED
    if _LAZY_LOCKED:
        return
    _LAZY_LOCKED = True

    # Priority 0: Gemini
    if config.GEMINI_ENABLED and not gateway.get_provider("gemini"):
        try:
            provider = GeminiProvider(
                api_key=config.GEMINI_API_KEY,
                timeout_s=config.GEMINI_TIMEOUT_S,
                max_tokens=config.GEMINI_MAX_TOKENS,
                model_name=config.GEMINI_MODEL,
                fallback_model_name=config.GEMINI_FALLBACK_MODEL,
            )
            gateway.register_provider(provider, priority=ProviderPriority.GEMINI.value)
            logger.info("Lazy-loaded Gemini (priority %d)", ProviderPriority.GEMINI.value)
        except Exception as exc:
            logger.warning("Lazy-load Gemini failed: %s", exc)

    # Priority 4: SambaNova
    if config.SAMBANOVA_ENABLED and not gateway.get_provider("sambanova"):
        try:
            provider = DirectHTTPProvider(
                name="sambanova",
                base_url=config.SAMBANOVA_BASE_URL,
                api_key=config.SAMBANOVA_API_KEY,
                model=config.SAMBANOVA_MODEL,
                timeout_s=config.SAMBANOVA_TIMEOUT_S,
                max_tokens=config.SAMBANOVA_MAX_TOKENS,
            )
            gateway.register_provider(provider, priority=ProviderPriority.SAMBANOVA.value)
            logger.info("Lazy-loaded SambaNova (priority %d)", ProviderPriority.SAMBANOVA.value)
        except Exception as exc:
            logger.warning("Lazy-load SambaNova failed: %s", exc)

    # Priority 5: Fireworks
    if config.FIREWORKS_ENABLED and not gateway.get_provider("fireworks"):
        try:
            provider = DirectHTTPProvider(
                name="fireworks",
                base_url=config.FIREWORKS_BASE_URL,
                api_key=config.FIREWORKS_API_KEY,
                model=config.FIREWORKS_MODEL,
                timeout_s=config.FIREWORKS_TIMEOUT_S,
                max_tokens=config.FIREWORKS_MAX_TOKENS,
            )
            gateway.register_provider(provider, priority=ProviderPriority.FIREWORKS.value)
            logger.info("Lazy-loaded Fireworks (priority %d)", ProviderPriority.FIREWORKS.value)
        except Exception as exc:
            logger.warning("Lazy-load Fireworks failed: %s", exc)

    # Priority 6: Hugging Face
    if config.HUGGINGFACE_ENABLED and not gateway.get_provider("huggingface"):
        try:
            provider = HuggingFaceProvider(
                api_key=config.HUGGINGFACE_API_KEY,
                timeout_s=config.HUGGINGFACE_TIMEOUT_S,
                max_tokens=config.HUGGINGFACE_MAX_TOKENS,
                model_name=config.HUGGINGFACE_MODEL,
            )
            gateway.register_provider(provider, priority=ProviderPriority.HUGGINGFACE.value)
            logger.info("Lazy-loaded HuggingFace (priority %d)", ProviderPriority.HUGGINGFACE.value)
        except Exception as exc:
            logger.warning("Lazy-load HuggingFace failed: %s", exc)

    # Priority 7: OpenRouter
    if config.OPENROUTER_ENABLED and not gateway.get_provider("openrouter"):
        try:
            provider = DirectHTTPProvider(
                name="openrouter",
                base_url=config.OPENROUTER_BASE_URL,
                api_key=config.OPENROUTER_API_KEY,
                model=config.OPENROUTER_MODEL,
                timeout_s=config.OPENROUTER_TIMEOUT_S,
                max_tokens=config.OPENROUTER_MAX_TOKENS,
            )
            gateway.register_provider(provider, priority=ProviderPriority.OPENROUTER.value)
            logger.info("Lazy-loaded OpenRouter (priority %d)", ProviderPriority.OPENROUTER.value)
        except Exception as exc:
            logger.warning("Lazy-load OpenRouter failed: %s", exc)

    # Priority 8: Together AI
    if config.TOGETHER_AI_ENABLED and not gateway.get_provider("together_ai"):
        try:
            provider = DirectHTTPProvider(
                name="together_ai",
                base_url=config.TOGETHER_AI_BASE_URL,
                api_key=config.TOGETHER_AI_API_KEY,
                model=config.TOGETHER_AI_MODEL,
                timeout_s=config.TOGETHER_AI_TIMEOUT_S,
                max_tokens=config.TOGETHER_AI_MAX_TOKENS,
            )
            gateway.register_provider(provider, priority=ProviderPriority.TOGETHER_AI.value)
            logger.info("Lazy-loaded TogetherAI (priority %d)", ProviderPriority.TOGETHER_AI.value)
        except Exception as exc:
            logger.warning("Lazy-load TogetherAI failed: %s", exc)

    # Priority 9: Ollama
    if config.OLLAMA_ENABLED and not gateway.get_provider("ollama"):
        try:
            from mini_kio.llm.ollama_provider import OllamaProvider
            provider = OllamaProvider(
                base_url=config.OLLAMA_BASE_URL,
                model=config.OLLAMA_MODEL,
                timeout_s=config.OLLAMA_TIMEOUT_S,
                max_tokens=config.OLLAMA_MAX_TOKENS,
            )
            gateway.register_provider(provider, priority=ProviderPriority.OLLAMA.value)
            logger.info("Lazy-loaded Ollama (priority %d)", ProviderPriority.OLLAMA.value)
        except Exception as exc:
            logger.warning("Lazy-load Ollama failed: %s", exc)

    # FreeLLM experimental
    if _ENABLE_FREELLM and config.FREELLMAPI_ENABLED and not gateway.get_provider("freellm"):
        try:
            from mini_kio.llm.freellm_provider import FreeLLMProvider
            provider = FreeLLMProvider(
                base_url=config.FREELLMAPI_BASE_URL,
                api_key=config.FREELLMAPI_API_KEY,
                model=config.FREELLMAPI_MODEL,
                timeout_s=config.FREELLMAPI_TIMEOUT_S,
                max_tokens=config.FREELLMAPI_MAX_TOKENS,
            )
            gateway.register_provider(provider, priority=99)
            logger.info("Lazy-loaded FreeLLM (priority 99)")
        except Exception as exc:
            logger.warning("Lazy-load FreeLLM failed: %s", exc)

    registry = gateway.get_registry()
    registered = registry.get_providers()
    logger.info(
        "Provider chain after lazy-load: %d provider(s) in order: %s",
        len(registered), ", ".join(registered),
    )


def _log_startup_summary(gateway: LLMGateway) -> None:
    """Log concise startup provider summary."""
    registry = gateway.get_registry()
    providers = registry.get_providers()
    logger.info(
        "Startup providers (%d): %s",
        len(providers), ", ".join(providers) if providers else "none",
    )


async def ask_llm(
    query: str,
    timeout: float = 8.0,
    max_tokens: int = 200,
    task_type: str = "chat",
) -> Optional[str]:
    """
    Authoritative entry point for conversational LLM requests.

    Two-phase routing:
      Phase 1 — NVIDIA PRIMARY: For standard task types, try NVIDIA first
      Phase 2 — FAILOVER CHAIN: If NVIDIA fails, fall through the
                multi-provider failover chain
    """
    gateway = _get_gateway()

    # ── Phase 1: NVIDIA-first routing ────────────────────────────────
    if task_type in _NVIDIA_PRIMARY_TASKS and config.NVIDIA_ENABLED:
        nvidia = gateway.get_provider("nvidia")
        if nvidia is not None:
            request = LLMRequest(
                prompt=query,
                max_tokens=max_tokens,
                timeout_s=timeout,
                provider="nvidia",
                metadata={"task_type": task_type},
            )
            try:
                start_t = time.monotonic()
                response = await asyncio.wait_for(
                    nvidia.generate(request),
                    timeout=timeout,
                )
                latency_ms = (time.monotonic() - start_t) * 1000
                if response.success and response.content:
                    model = nvidia.resolve_model(task_type)
                    logger.info(
                        "[NVIDIA_PRIMARY_ROUTE] task_type=%s provider=nvidia model=%s",
                        task_type, model,
                    )
                    logger.info(
                        "[NVIDIA_SUCCESS] latency=%.0f model=%s",
                        latency_ms, model,
                    )
                    return response.content.strip()

                err = response.error_code or "unknown"
                logger.info(
                    "[NVIDIA_FAILOVER] from=nvidia to=provider_chain reason=%s",
                    err,
                )
            except asyncio.TimeoutError:
                logger.info("[NVIDIA_FAILOVER] from=nvidia to=provider_chain reason=timeout")
            except Exception as e:
                logger.info(
                    "[NVIDIA_FAILOVER] from=nvidia to=provider_chain reason=%s",
                    type(e).__name__,
                )

    # ── Phase 2: Failover chain — lazy-load remaining providers ──────
    _lazy_register_remaining(gateway)

    request = LLMRequest(
        prompt=query,
        max_tokens=max_tokens,
        timeout_s=timeout,
        provider="",
        metadata={"task_type": task_type},
    )

    try:
        response = await gateway.generate(request)
        if response.success and response.content:
            logger.info(
                "[NVIDIA_FAILOVER] resolved=provider_chain selected=%s",
                response.provider,
            )
            return response.content.strip()
    except Exception as e:
        logger.warning("Unified LLM path failed: %s", e)

    return None
