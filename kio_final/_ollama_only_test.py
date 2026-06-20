"""
Standalone Ollama failover test — disables cloud providers.
Patches config values before gateway initializes.
"""
import os, sys, time

# Clear any cached mini_kio modules
for mod in list(sys.modules.keys()):
    if "mini_kio" in mod:
        del sys.modules[mod]

# Import config and force-disable all cloud providers
from mini_kio.core import config
config.GEMINI_ENABLED = False
config.GROQ_ENABLED = False
config.CEREBRAS_ENABLED = False
config.SAMBANOVA_ENABLED = False
config.FIREWORKS_ENABLED = False
config.HUGGINGFACE_ENABLED = False
config.OPENROUTER_ENABLED = False
config.TOGETHER_AI_ENABLED = False
config.FREELLMAPI_ENABLED = False
config.OLLAMA_ENABLED = True

import asyncio
from mini_kio.core.llm_router import _get_gateway, ask_llm

g = _get_gateway()
r = g.get_registry()
print("Provider chain:", r.get_providers())
print()

# Test single query
r.clear_diagnostics()
result = asyncio.run(ask_llm("Who directed Interstellar? Answer in one short sentence.", timeout=30.0, max_tokens=128))
print(f"Answer: {result}")
print()
print("Diagnostics:")
for d in r.get_diagnostics():
    print(f"  [{d.event:<30}] {d.provider:<15} {d.detail[:80]}")
