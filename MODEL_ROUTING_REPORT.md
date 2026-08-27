# MODEL_ROUTING_REPORT.md

## Audit Findings
- Provider registration (`mini_kio/core/llm_router.py:52-222`): Gemini(0), Groq(1), Cerebras(2),
  SambaNova(3), Fireworks(4), HF Qwen3-32B(5), OpenRouter(6), Together(7), Ollama(8), FreeLLM(99).
- Routing was a single fixed priority chain (`LLMGateway.generate` →
  `registry.get_chain()`): every request tried providers in the same order, so cheap
  conversational turns could consume a large reasoning model's quota/latency.
- The `mini_kio/llm/providers/` v2 abstraction (provider_metadata.py etc.) has zero callers — dead code.
- Task-tier routing did not exist.

## Fix (minimal, non-breaking)
1. `LLMRequest` gained optional `preferred_provider: str = ""` (`models.py`).
2. `LLMGateway.generate()` moves `preferred_provider` to the front of the try-chain when it is
   registered and try-able, then falls through to the normal priority chain on failure —
   full failover preserved.
3. `ask_llm(..., task="")` maps task → preferred provider via `_TASK_PROVIDER_PREFERENCE`:
   - `conversation` / `greeting` / `summarize` → `groq` (fast, cheap)
   - `reasoning` / `analysis` / `code` / `media` / `memory` → `gemini` (capable)
4. `ask_llm_sync` threads `task=` through; `_chat_converse` now calls with `task="conversation"`.

Default behavior is unchanged when `task=""` (chain order identical to before).

## Design Notes
- Tiering is a *preference hint*, not a hard pin — the failover chain still guarantees an answer.
- Provider names must match what `_register_providers` registers; unknown names are silently
  ignored (chain unchanged).

## Verification
```
_TASK_PROVIDER_PREFERENCE → {'conversation': 'groq', 'reasoning': 'gemini', ...}
LLMRequest(preferred_provider='groq') → round-trips; gateway prepends it when healthy.
```
Full suite: no regression (identical failure set).

## Remaining
- NVIDIA (Maverick/GPT-OSS/Vision) providers from the task brief are not wired; add as new
  `DirectHTTPProvider` registrations + `_TASK_PROVIDER_PREFERENCE` entries when keys exist.
- The dead `providers/` v2 package should be deleted or wired; neither is required by this slice.
