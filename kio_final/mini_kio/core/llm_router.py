"""
llm_router.py — Conversational Authority Bridge

Unifies the legacy core with the modern LLM gateway.
Ensures ONE authoritative path for conversational Gemini dispatch.
"""

import asyncio
import logging
from typing import Optional

from mini_kio.core import config
from mini_kio.llm.llm_gateway import LLMGateway
from mini_kio.llm.gemini_provider import GeminiProvider
from mini_kio.llm.models import LLMRequest

logger = logging.getLogger(__name__)

# Singleton gateway for the runtime
_GATEWAY: Optional[LLMGateway] = None


def _get_gateway() -> LLMGateway:
    """Initialize and return the singleton LLM gateway."""
    global _GATEWAY
    if _GATEWAY is None:
        _GATEWAY = LLMGateway()
    
    # Ensure Gemini provider is registered if key is available and not already present
    if config.GEMINI_API_KEY and "gemini" not in _GATEWAY._providers:
        provider = GeminiProvider(
            api_key=config.GEMINI_API_KEY,
            timeout_s=config.GEMINI_TIMEOUT_S,
            max_tokens=config.GEMINI_MAX_TOKENS,
            model_name=config.GEMINI_MODEL
        )
        _GATEWAY.register_provider(provider)
        logger.info(f"Gemini provider registered with model: {config.GEMINI_MODEL}")
        
    return _GATEWAY


async def ask_llm(query: str, timeout: float = 8.0, max_tokens: int = 200) -> Optional[str]:
    """
    Authoritative entry point for conversational LLM requests.
    Routes through LLMGateway -> GeminiProvider.
    """
    gateway = _get_gateway()
    
    request = LLMRequest(
        prompt=query,
        max_tokens=max_tokens,
        timeout_s=timeout,
        provider="gemini"
    )
    
    try:
        response = await gateway.generate(request)
        if response.success and response.content:
            return response.content.strip()
    except Exception as e:
        logger.warning(f"Unified LLM path failed: {e}")
        
    return None
