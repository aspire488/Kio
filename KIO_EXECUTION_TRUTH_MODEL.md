# KIO Execution Truth Model

What actually happens when a user sends a message — no handwaving, no "the function exists therefore it works."

## Classification Chain (Definitive)

Pipeline runs in `Pipeline.run()` → `_dispatch_single_message()` → `_classify_and_resolve()`.

Classifiers execute in this exact order. **First non-None wins.**

| # | Classifier | What it catches | Fail-through behavior |
|---|---|---|---|
| 1 | `_classify_multi_step` | "compare X and Y", "X vs Y with YTMusic" | Returns multi-step RoutingDecision or None |
| 2 | `_classify_deterministic` | All desktop/browser/operational/file intents | Returns DESKTOP_ACTION, DESKTOP_OPEN, BROWSER_*, etc. |
| 3 | `_detect_now_playing` | "now playing", "what's playing" | Returns DESKTOP_ACTION/now_playing or None |
| 4 | `_classify_media_transport` | "play X", "watch X", "search for X on YTMusic" | Returns MEDIA_PLAY, MEDIA_SEARCH, MEDIA_ADD |
| 5 | `_classify_memory` | "remember X", "what's my X", "forget X" | Returns MEMORY/store, MEMORY/recall, MEMORY/forget |
| 6 | `_classify_pragmatics_social` | Greetings, gratitude, apology, closings | Returns PRAGMATICS/SOCIAL_* |
| 7 | `_classify_curiosity` | "what's trending", "latest news" | Returns CURIOSITY/TRENDING, CURIOSITY/NEWS |
| 8 | `_classify_opinion` | "what do you think about X" | Returns OPINION/ASK |
| 9 | `_classify_emotion` | "I'm sad", "I'm happy" | Returns EMOTION/RECOGNIZE |
| 10 | `_classify_context_followup` | "tell me more", "and then?" | Returns CONTEXT/FOLLOWUP if entity is loaded |
| 11 | `_classify_entity_query` | Proper nouns, capitalized questions | Returns ENTITY_QUERY |
| 12 | `_classify_conversational` | Everything else | Returns CONVERSATIONAL/CHITCHAT |

**Key guards in `_classify_deterministic`:**
- Simulation → `re.match(r"^simulate|dry.?run|preview|what if I")`
- Navigation → `re.match(r"^go to|navigate to|visit|browse")`
- Search → `first_word == "search"`
- Browser webapp → `re.search(r"(?:open|go to|browse|visit)\s+(?:url|link|web)")`
- Create new instance → `re.search(r"(?:create|make)\s+(?:a\s+)?(?:new|another)")`
- Document creation → `_CREATE_DOC_RE` (word/document/report/essay on X)

**Key guard in `_classify_entity_query`:**
- Capital-letter heuristic: `orig_first[0].isupper() and len(orig_first) > 1 and first_w not in skip`
- Sentence-initial stop: `first_w in two_word_stop`
- This correctly catches "What is Quantum Physics?" but NOT "Create a Word document about AI" (because deterministic catches it first)

## Resolution Chain

After classification, `resolve()` is called on the winning intent's resolver.

| Intent | Resolver | What it does |
|---|---|---|
| DESKTOP_ACTION | `_resolve_desktop_action` | Dispatches to `app_operator.py` |
| DESKTOP_OPEN | `_resolve_desktop_open` | Launches app via `app_operator.py` |
| MEDIA_PLAY | `_resolve_media_transport` | Calls `media_manager.py` → YouTube provider |
| MEDIA_SEARCH | `_resolve_media_transport` | Calls `media_manager.py` → YouTube search |
| MEMORY/* | `MemoryResolver` | Reads/writes `FactStore` via `memory_store.py` |
| KNOWLEDGE/* | `KnowledgeResolver` | Reads/writes via `KnowledgeRouter` |
| CURIOSITY/* | `_resolve_curiosity` | Freshness check → multi-source search |
| CONVERSATIONAL | `_resolve_conversational` | LLM-only, no search |
| ENTITY_QUERY | `_resolve_entity_query` | Search + LLM synthesis |
| OPINION/* | `_resolve_opinion` | LLM-only (no web search) |
| EMOTION/* | `_resolve_emotion` | LLM empathy response |
| PRAGMATICS/* | `_resolve_pragmatics_social` | LLM response |
| CONTEXT/FOLLOWUP | `_resolve_context_followup` | Continuity context + LLM |

## Research Provider Cascade

**`KnowledgeRouter.route()` (default path):**
1. Exa (if configured)
2. Tavily (if configured)
3. DuckDuckGo
4. Wikipedia (evergreen fallback)

**`KnowledgeRouter.route_freshness()` (freshness queries):**
1. Exa (if configured)
2. Tavily (if configured)
3. DuckDuckGo

**`KnowledgeRouter.route_for_topic()` (topic-aware path):**
1. Topic-specific provider order from `_TOPIC_PROVIDER_ORDER`
2. Falls through to Wikipedia on failure

## LLM Provider Chain

Gateway: `llm_gateway.py`

```
Gemini (gemini-2.5-flash) → Groq (llama-4-scout) → Fireworks (llama3) →
SambaNova (DeepSeek-R1) → Cerebras (llama-4-scout) → Hopper →
OpenRouter (mistralai/mistral-small) → Together (meta-llama) → Ollama
```

- Timeout per provider: 8s
- Total chain timeout: 12-20s
- Retry gap after transient: 2.5s
- Circuit breaker: 3 failures → skip for 5 min

## Memory Store

**`FactStore` (SQLite-backed):**
- Keys: `favorite_{topic}`, `preference_{topic}`, `my_{topic}`, raw key
- Values: String (may be JSON-encoded)
- Display: Prefix-aware — `"favorite_"` → `"Your favorite {topic} is {value}"`
- Old behavior (fixed): Naive `matched_key.replace("_", " ")` leaked raw keys

**`PatternMemoryExtractor`:**
- Extracts key-value pairs from user messages
- Templates: `"favorite_{0}"`, `"preference_{1}"`, `"my_{2}"`

## Continuity State

**Per-session isolation (fixed):**
- `_ContinuityResolver._states: dict[str, ContinuityState]` keyed by session_id
- `_get_state()` returns per-session state, defaulting to bootstrap state
- Old behavior (fixed): Single `_state` class variable shared across all sessions

## YouTube Playback

**`play_youtube()` flow:**
1. `_MediaManager.play_youtube(query)` called
2. `YouTubeProvider.search_and_rank(query)` finds video
3. `_BrowserOperator.play_youtube(query)` opens YouTube search page
4. **Message sent:** `"Opened YouTube for: {query}. Click the first video to play."`
5. Old behavior (fixed): Message said `"Playing on YouTube: {query}"` — false claim

## Execution Boundaries

**`execution_boundary.py`:**
- `play_youtube` gets `noop_probe` — no verification, honest message
- Desktop apps get `pid_probe` — `psutil.pid_exists()` confirms launch
- Browser gets `tab_probe` — new tab detected
- All probes log to `probes.jsonl`

## Error Handling

**Three-tier dispatch:**
1. Try resolver
2. Catch exception → log → try fallback resolver
3. Catch all → `"Something went wrong. What would you like to try?"`

**No bare `except:` blocks** — all catches log with `exc_info=True`.

## Stale-Response Guard

**`kio_bot.py` `dispatch_channel_input()`:**
- Each message gets `_msg_seq` (monotonic counter)
- Before sending reply, checks if `_msg_seq` still matches channel's latest
- If stale: reply discarded, `logger.debug("[STALE_RESPONSE_DISCARDED]")`
- Thread pool: `max_workers=3` to prevent OOM
