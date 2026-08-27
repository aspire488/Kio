# HARDCODED_DEFAULTS — Every Default Value

## Configuration Defaults (config.py)

| Setting | Default Value | File | Line | Should Be External |
|---|---|---|---|---|
| WebSocket port | 9877 | browser_connector/ws_handler.py | various | YES |
| LLM timeout | 30 seconds | llm/constants.py | various | YES |
| Max response length | 2000 chars | llm/constants.py | various | YES |
| Session timeout | 3600 seconds (1 hour) | media_manager.py | various | YES |
| Max history entries | 500 | media_manager.py | various | YES |
| Volume step | 10% | media_session.py | various | YES |
| Playlist item limit | 100 | media_discovery.py | various | YES |
| Memory retention | 30 days | memory/ | various | YES |
| Context window size | 10 messages | context/ | various | YES |
| Retry attempts | 3 | various | various | YES |
| Retry delay | 1 second | various | various | YES |
| Log level | INFO | various | various | YES |
| Debug mode | False | various | various | YES |

## Media Defaults

| Setting | Default Value | File | Should Be External |
|---|---|---|---|
| Default provider | YouTube | media_registry.py | YES |
| Search result count | 10 | media_discovery.py | YES |
| Audio format | mp3 | providers/youtube_provider.py | YES |
| Video quality | best | providers/youtube_provider.py | YES |
| Autoplay | True | media_session.py | YES |
| Shuffle | False | media_session.py | YES |
| Repeat | False | media_session.py | YES |
| Crossfade | 0 seconds | media_session.py | YES |

## Browser Defaults

| Setting | Default Value | File | Should Be External |
|---|---|---|---|
| Default browser | Chrome | browser_connector/ | YES |
| Window width | 1280 | browser/ | YES |
| Window height | 720 | browser/ | YES |
| Page load timeout | 30 seconds | browser/ | YES |
| Screenshot format | png | browser/ | YES |
| Headless mode | False | browser/ | YES |

## LLM Defaults

| Setting | Default Value | File | Should Be External |
|---|---|---|---|
| Temperature | 0.7 | llm/gateway.py | YES |
| Max tokens | 1024 | llm/constants.py | YES |
| Top-p | 0.9 | llm/gateway.py | YES |
| Frequency penalty | 0.0 | llm/gateway.py | YES |
| Presence penalty | 0.0 | llm/gateway.py | YES |
| Stop sequences | [] | llm/gateway.py | YES |

## Memory Defaults

| Setting | Default Value | File | Should Be External |
|---|---|---|---|
| Default category | "general" | memory/ | YES |
| Importance threshold | 0.5 | memory/ | YES |
| Decay rate | 0.1 | memory/ | YES |
| Max memories per query | 5 | memory/ | YES |
| Similarity threshold | 0.7 | memory/ | YES |

## Intelligence Defaults

| Setting | Default Value | File | Should Be External |
|---|---|---|---|
| Proactive suggestions | True | proactive_evaluator.py | YES |
| Suggestion cooldown | 300 seconds | proactive_evaluator.py | YES |
| Max suggestions per hour | 5 | proactive_evaluator.py | YES |
| Retrieval score weight | 0.5 | retrieval.py | YES |
| Recency weight | 0.3 | retrieval.py | YES |
| Importance weight | 0.2 | retrieval.py | YES |

## MCP Defaults

| Setting | Default Value | File | Should Be External |
|---|---|---|---|
| Server timeout | 10 seconds | core/mcp/ | YES |
| Max concurrent tools | 5 | core/mcp/ | YES |
| Tool retry count | 2 | core/mcp/ | YES |

## Defaults That Are Legitimate (Should NOT Be External)

| Setting | Value | Reason |
|---|---|---|
| Intent type enum values | Various strings | Part of type system |
| State machine states | IDLE, MEDIA_PLAYING, etc. | Part of state machine definition |
| Command names | play, pause, stop, etc. | Part of command interface |
| File extensions for media | .mp3, .wav, .flac, etc. | Platform constraints |
| Browser process names | chrome, firefox, edge | OS-level identifiers |
| API protocol versions | HTTP/1.1, WebSocket | Protocol specs |
