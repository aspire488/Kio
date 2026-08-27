# HARDCODED_ROUTING — Every Static Routing Rule

## Intent → Subsystem Routing (pipeline/__init__.py)

| Intent | Subsystem | Hardcoded Rule | Should Be External |
|---|---|---|---|
| greeting | companion | `if intent == "greeting"` | YES |
| identity | companion | `if intent == "identity"` | YES |
| social | companion | `if intent == "social"` | YES |
| media_play | media_manager | `if intent == "media_play"` | YES |
| media_pause | media_manager | `if intent == "media_pause"` | YES |
| media_stop | media_manager | `if intent == "media_stop"` | YES |
| media_next | media_manager | `if intent == "media_next"` | YES |
| media_previous | media_manager | `if intent == "media_previous"` | YES |
| media_volume | media_manager | `if intent == "media_volume"` | YES |
| browser_open | browser_connector | `if intent == "browser_open"` | YES |
| browser_search | browser_connector | `if intent == "browser_search"` | YES |
| browser_screenshot | browser_connector | `if intent == "browser_screenshot"` | YES |
| memory_save | memory | `if intent == "memory_save"` | YES |
| memory_recall | memory | `if intent == "memory_recall"` | YES |
| context_update | context | `if intent == "context_update"` | YES |
| general | llm | `else: (fallback)` | YES |

## State Machine Transitions (pipeline/__init__.py)

| Current State | Input | Next State | Hardcoded Rule |
|---|---|---|---|
| STATE_IDLE | media_play | STATE_MEDIA_PLAYING | `if state == IDLE and intent == media_play` |
| STATE_MEDIA_PLAYING | media_stop | STATE_IDLE | `if state == MEDIA_PLAYING and intent == media_stop` |
| STATE_MEDIA_PLAYING | media_pause | STATE_MEDIA_PAUSED | `if state == MEDIA_PLAYING and intent == media_pause` |
| STATE_MEDIA_PAUSED | media_play | STATE_MEDIA_PLAYING | `if state == MEDIA_PAUSED and intent == media_play` |
| STATE_MEDIA_PAUSED | media_stop | STATE_IDLE | `if state == MEDIA_PAUSED and intent == media_stop` |
| STATE_IDLE | browser_open | STATE_BROWSER_ACTIVE | `if state == IDLE and intent == browser_open` |
| STATE_BROWSER_ACTIVE | browser_close | STATE_IDLE | `if state == BROWSER_ACTIVE and intent == browser_close` |
| STATE_MEDIA_PLAYING | browser_open | STATE_BOTH | `if state == MEDIA_PLAYING and intent == browser_open` |

## LLM Provider Routing (llm_router.py)

| Priority | Provider | Condition | Hardcoded |
|---|---|---|---|
| 1 | Gemini | API key available | YES |
| 2 | Groq | API key available | YES |
| 3 | OpenRouter | API key available | YES |
| 4 | Together | API key available | YES |
| 5 | Cerebras | API key available | YES |

## Media Provider Routing (media_registry.py)

| Priority | Provider | Condition | Hardcoded |
|---|---|---|---|
| 1 | YouTube | yt-dlp available | YES |
| 2 | Spotify | spotifydl available | YES |
| 3 | Browser | browser connected | YES |
| 4 | Local | files exist | YES |

## MCP Server Routing (core/mcp/servers.py)

| Tool Category | MCP Server | Hardcoded Mapping |
|---|---|---|
| file operations | filesystem | YES |
| git operations | git | YES |
| terminal commands | terminal | YES |
| database queries | sqlite | YES |
| docker operations | docker | YES |
| github operations | github | YES |
| postgres operations | postgres | YES |
| redis operations | redis | YES |
| memory operations | memory | YES |
| web search | web_search | YES |

## Adapter Routing (adapters/)

| Intent Category | Adapter | Hardcoded Priority |
|---|---|---|
| media_* | media_adapter | 1 |
| browser_* | browser_adapter | 2 |
| memory_* | memory_adapter | 3 |
| context_* | context_adapter | 4 |
| intelligence_* | intelligence_adapter | 5 |
| llm_* | llm_adapter | 6 |

## Response Formatting Routing (runtime_response_formatter.py)

| Intent | Response Template | Hardcoded |
|---|---|---|
| greeting | GREETING_TEMPLATE | YES |
| identity | IDENTITY_TEMPLATE | YES |
| social | SOCIAL_TEMPLATE | YES |
| media_* | MEDIA_TEMPLATE | YES |
| browser_* | BROWSER_TEMPLATE | YES |
| error | ERROR_TEMPLATE | YES |
| general | GENERAL_TEMPLATE | YES |
