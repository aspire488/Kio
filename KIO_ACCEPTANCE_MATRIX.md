# KIO Acceptance Matrix

What must be true for each capability to be considered **actually working** — not just that the function exists, but that the end-to-end path produces the correct user-visible result.

## Classification

| Capability | Acceptance Criteria | How to Verify |
|---|---|---|
| MEDIA_PLAY | "play X" → YouTube open with query | `play_youtube()` opens tab; user sees video list; honest message about manual play |
| DESKTOP_OPEN | "open chrome" → app launches + verified | `psutil.pid_exists()` confirms process; user sees app |
| DESKTOP_ACTION | "create a Word doc about AI" → routed to `create_document` | `_classify_deterministic` returns `DESKTOP_ACTION/create_document` |
| MEMORY_STORE | "remember X is Y" → persists in FactStore | `_classify_memory` returns `MEMORY/store`; `FactStore.set()` called |
| MEMORY_RECALL | "what's my favorite color" → human-readable answer | `MemoryResolver` returns `"Your favorite color is blue"` not `"favorite_color: blue"` |
| KNOWLEDGE | "what is X" → DDG/Exa/Tavily/Wikipedia tried in order | `KnowledgeRouter.route()` iterates all providers; first hit returned |
| FRESHNESS | "latest news about X" → Exa/Tavily attempted before DDG | `route_freshness()` tries Exa → Tavily → DDG |

## Resolution

| Capability | Acceptance Criteria | How to Verify |
|---|---|---|
| MEMORY_RECALL_DISPLAY | No raw keys (`favorite_color`) visible in Telegram response | `MemoryResolver.resolve()` uses prefix-aware display; sends "Your favorite color is blue" |
| MEMORY_RECALL_PREFIX | "My X is Y" → extracts key without "my" prefix | `clean.removeprefix("my ").removeprefix("your ")` before lookup |
| CONTINUITY_ISOLATION | Two concurrent sessions don't share state | `_ContinuityResolver._get_state(session_id)` returns per-session dict; no cross-session bleed |
| CONTINUITY_FALLBACK | `_continuity_singleton()` fallback preserves per-session isolation | Singleton uses `_states` dict, not single `_state` object |

## Browser

| Capability | Acceptance Criteria | How to Verify |
|---|---|---|
| YOUTUBE_PLAY | `play_youtube()` doesn't claim video is playing | Message says "Opened YouTube for X. Click the first video to play." |
| YOUTUBE_VERIFY | `play_youtube` has `noop_probe` verification (no false success) | `verify_execution=False` in probe dispatch for play_youtube |
| WEB_APP_OPEN | "open github.com" → browser navigates | `_detect_browser_webapp` returns truthy; tab opened |

## Research

| Capability | Acceptance Criteria | How to Verify |
|---|---|---|
| MULTI_PROVIDER | Default knowledge path tries Exa, Tavily, DDG before Wikipedia | `route()` loops `["Exa", "Tavily", "DuckDuckGo"]`; logs show provider attempts |
| TOPIC_PROVIDER | `route_for_topic()` uses `_TOPIC_PROVIDER_ORDER` for domain-specific ordering | Provider order matches topic config (e.g., SPORTS → Exa first) |
| RESEARCH_BRIEF | Pipeline research path uses `intelligence/retrieval_router.py` System A | `_resolve_research_knowledge()` calls `route_for_topic()` |

## LLM

| Capability | Acceptance Criteria | How to Verify |
|---|---|---|
| CHAIN_ORDER | Providers tried in declared order: Gemini → Groq → Fireworks → SambaNova → Cerebras → Hopper → OpenRouter → Together → Ollama | `llm_gateway.py` `_PROVIDERS` list order matches |
| CIRCUIT_BREAKER | Provider fails 3× → skipped for 5 min | `_CIRCUIT_BREAKERS` dict tracks failures; `circuit_is_open()` returns True after 3 fails |
| TIMEOUT | Provider timeout ≤ 8s; total chain ≤ 20s | `_PROVIDER_TIMEOUT = 8`; retry gap = 2.5s |

## Truth Model

| Capability | Acceptance Criteria | How to Verify |
|---|---|---|
| NO_FALSE_CLAIMS | Play message doesn't say "Playing" when it only opened YouTube | Message text verified: no verb claiming playback started |
| NO_RAW_KEYS | Memory display never shows raw store keys | `_memory_resolver.resolve()` format step applied |
| HONEST_FAILURES | Provider timeout → "I couldn't reach [provider]" not silent retry | `llm_gateway.py` logs timeout; returns fallback message |
