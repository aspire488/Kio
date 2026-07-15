"""
Diagnose Gemini provider initialization.
"""
import os, sys, logging

logging.basicConfig(level=logging.DEBUG)

for mod in list(sys.modules.keys()):
    if "mini_kio" in mod:
        del sys.modules[mod]

from mini_kio.core import config
print("=== CONFIG ===")
print("GEMINI_ENABLED =", config.GEMINI_ENABLED)
print("GEMINI_MODEL =", repr(config.GEMINI_MODEL))
print("GEMINI_FALLBACK_MODEL =", repr(config.GEMINI_FALLBACK_MODEL))
print("GEMINI_API_KEY =", "SET" if config.GEMINI_API_KEY else "EMPTY")
print()

print("=== CONSTRUCTING PROVIDER ===")
try:
    from mini_kio.llm.gemini_provider import GeminiProvider
    provider = GeminiProvider(
        api_key=config.GEMINI_API_KEY,
        timeout_s=config.GEMINI_TIMEOUT_S,
        max_tokens=config.GEMINI_MAX_TOKENS,
        model_name=config.GEMINI_MODEL,
        fallback_model_name=config.GEMINI_FALLBACK_MODEL,
    )
    print("_model_name   =", repr(provider._model_name))
    print("_model        =", provider._model)
    print("_fallback_model =", provider._fallback_model)
    print()

    print("=== HEALTH CHECK ===")
    import asyncio, inspect
    hc = provider.health_check()
    print("health_check() returned coroutine:", inspect.iscoroutine(hc))
    # Run it
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        healthy = loop.run_until_complete(asyncio.ensure_future(hc))
        print("health_check result =", healthy)
    finally:
        loop.close()
        asyncio.set_event_loop(None)
    print()

    print("=== GENERATE ===")
    from mini_kio.llm.models import LLMRequest
    req = LLMRequest(prompt="say hello", max_tokens=16, timeout_s=10.0)
    loop2 = asyncio.new_event_loop()
    asyncio.set_event_loop(loop2)
    try:
        result = loop2.run_until_complete(provider.generate(req))
        print("generate success =", result.success)
        print("generate error   =", result.error_code)
        print("generate content =", result.content[:100] if result.content else "(empty)")
    finally:
        loop2.close()
        asyncio.set_event_loop(None)

except Exception as e:
    import traceback
    traceback.print_exc()
