"""
LLM Router - Multi-provider fallback system.

Supports Claude, Gemini, OpenAI, Perplexity with automatic fallback.
All requests have timeout=8 seconds, max_tokens=200.
"""

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Provider priority order
PROVIDERS = ["claude", "openai", "gemini", "perplexity"]

# API endpoints and models
ENDPOINTS = {
    "claude": {
        "url": "https://api.anthropic.com/v1/messages",
        "model": "claude-3-haiku-20240307",
        "key_env": "CLAUDE_API_KEY",
    },
    "gemini": {
        "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent",
        "model": "gemini-1.5-flash",
        "key_env": "GEMINI_API_KEY",
    },
    "openai": {
        "url": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-3.5-turbo",
        "key_env": "OPENAI_API_KEY",
    },
    "perplexity": {
        "url": "https://api.perplexity.ai/chat/completions",
        "model": "llama-3.1-sonar-small-128k-online",
        "key_env": "PERPLEXITY_API_KEY",
    },
}


async def _ask_claude(query: str, api_key: str, timeout: float, max_tokens: int) -> Optional[str]:
    """Ask Claude API."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                ENDPOINTS["claude"]["url"],
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": ENDPOINTS["claude"]["model"],
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": query}],
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["content"][0]["text"].strip()
    except Exception as e:
        logger.debug(f"Claude failed: {e}")
        return None


async def _ask_gemini(query: str, api_key: str, timeout: float, max_tokens: int) -> Optional[str]:
    """Ask Gemini API."""
    try:
        import httpx
        url = f"{ENDPOINTS['gemini']['url']}?key={api_key}"
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url,
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{
                        "parts": [{"text": query}]
                    }],
                    "generationConfig": {
                        "maxOutputTokens": max_tokens,
                    }
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        logger.debug(f"Gemini failed: {e}")
        return None


async def _ask_openai(query: str, api_key: str, timeout: float, max_tokens: int) -> Optional[str]:
    """Ask OpenAI API."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                ENDPOINTS["openai"]["url"],
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": ENDPOINTS["openai"]["model"],
                    "messages": [{"role": "user", "content": query}],
                    "max_tokens": max_tokens,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.debug(f"OpenAI failed: {e}")
        return None


async def _ask_perplexity(query: str, api_key: str, timeout: float, max_tokens: int) -> Optional[str]:
    """Ask Perplexity API."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                ENDPOINTS["perplexity"]["url"],
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": ENDPOINTS["perplexity"]["model"],
                    "messages": [{"role": "user", "content": query}],
                    "max_tokens": max_tokens,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.debug(f"Perplexity failed: {e}")
        return None


async def ask_llm(query: str, timeout: float = 8.0, max_tokens: int = 200) -> Optional[str]:
    """
    Ask LLM providers in priority order until one succeeds.
    
    Args:
        query: The question to ask
        timeout: Request timeout in seconds (default 8)
        max_tokens: Maximum tokens in response (default 200)
        
    Returns:
        Response string or None if all fail
    """
    provider_funcs = {
        "claude": _ask_claude,
        "gemini": _ask_gemini,
        "openai": _ask_openai,
        "perplexity": _ask_perplexity,
    }
    
    for provider in PROVIDERS:
        api_key = os.getenv(ENDPOINTS[provider]["key_env"])
        if not api_key:
            continue
            
        try:
            logger.debug(f"Trying {provider}")
            func = provider_funcs[provider]
            result = await func(query, api_key, timeout, max_tokens)
            if result:
                logger.info(f"LLM success: {provider}")
                return result
        except Exception as e:
            logger.debug(f"{provider} error: {e}")
            continue
    
    logger.warning("All LLM providers failed")
    return None