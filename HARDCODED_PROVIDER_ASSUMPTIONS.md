# HARDCODED_PROVIDER_ASSUMPTIONS — Every Provider Assumption

## LLM Provider Assumptions

### Gemini (google-generativeai)

| Assumption | Value | File | Should Be External |
|---|---|---|---|
| API endpoint | generativelanguage.googleapis.com | llm/providers/ | NO (API spec) |
| Model name | gemini-pro | llm/providers/ | YES |
| Max tokens | 8192 | llm/providers/ | YES |
| Rate limit | 60 RPM | llm/providers/ | YES |
| Timeout | 30s | llm/providers/ | YES |
| Supports streaming | True | llm/providers/ | NO (API spec) |
| Supports function calling | True | llm/providers/ | NO (API spec) |
| API key env var | GEMINI_API_KEY | llm/providers/ | YES |

### Groq

| Assumption | Value | File | Should Be External |
|---|---|---|---|
| API endpoint | api.groq.com | llm/providers/ | NO (API spec) |
| Model name | llama2-70b-4096 | llm/providers/ | YES |
| Max tokens | 4096 | llm/providers/ | YES |
| Rate limit | 30 RPM | llm/providers/ | YES |
| Timeout | 30s | llm/providers/ | YES |
| Supports streaming | True | llm/providers/ | NO (API spec) |
| API key env var | GROQ_API_KEY | llm/providers/ | YES |

### OpenRouter

| Assumption | Value | File | Should Be External |
|---|---|---|---|
| API endpoint | openrouter.ai/api | llm/providers/ | NO (API spec) |
| Model name | auto | llm/providers/ | YES |
| Max tokens | 4096 | llm/providers/ | YES |
| Rate limit | 20 RPM | llm/providers/ | YES |
| Timeout | 30s | llm/providers/ | YES |
| Supports streaming | True | llm/providers/ | NO (API spec) |
| API key env var | OPENROUTER_API_KEY | llm/providers/ | YES |

### Together

| Assumption | Value | File | Should Be External |
|---|---|---|---|
| API endpoint | api.together.xyz | llm/providers/ | NO (API spec) |
| Model name | togethercomputer/llama-2-70b-chat | llm/providers/ | YES |
| Max tokens | 4096 | llm/providers/ | YES |
| Rate limit | 60 RPM | llm/providers/ | YES |
| Timeout | 30s | llm/providers/ | YES |
| Supports streaming | True | llm/providers/ | NO (API spec) |
| API key env var | TOGETHER_API_KEY | llm/providers/ | YES |

### Cerebras

| Assumption | Value | File | Should Be External |
|---|---|---|---|
| API endpoint | api.cerebras.ai | llm/providers/ | NO (API spec) |
| Model name | cerebras/demo | llm/providers/ | YES |
| Max tokens | 4096 | llm/providers/ | YES |
| Rate limit | 30 RPM | llm/providers/ | YES |
| Timeout | 30s | llm/providers/ | YES |
| Supports streaming | True | llm/providers/ | NO (API spec) |
| API key env var | CEREBRAS_API_KEY | llm/providers/ | YES |

## Media Provider Assumptions

### YouTube (yt-dlp)

| Assumption | Value | File | Should Be External |
|---|---|---|---|
| Command | yt-dlp | media_discovery.py | YES |
| JSON output flag | --dump-json | media_discovery.py | YES |
| No download flag | --no-download | media_discovery.py | YES |
| Flat playlist flag | --flat-playlist | media_discovery.py | YES |
| Search prefix | ytsearch | media_discovery.py | YES |
| Default count | 10 | media_discovery.py | YES |
| Audio format | mp3 | providers/youtube_provider.py | YES |
| Available check | `shutil.which("yt-dlp")` | media_discovery.py | NO (runtime check) |

### Spotify (spotifydl)

| Assumption | Value | File | Should Be External |
|---|---|---|---|
| Command | spotifydl | providers/spotify_provider.py | YES |
| Output flag | -o | providers/spotify_provider.py | YES |
| Available check | `shutil.which("spotifydl")` | media_discovery.py | NO (runtime check) |

### Browser

| Assumption | Value | File | Should Be External |
|---|---|---|---|
| YouTube URL | https://youtube.com | providers/browser_provider.py | YES |
| Play button selector | .ytp-play-button | browser/ | YES |
| Next button selector | .ytp-next-button | browser/ | YES |
| Prev button selector | .ytp-prev-button | browser/ | YES |
| Volume selector | .ytp-volume-panel | browser/ | YES |

## Browser Connector Assumptions

| Assumption | Value | File | Should Be External |
|---|---|---|---|
| WebSocket URL | ws://localhost:9877 | browser_connector/ws_handler.py | YES |
| Chrome extension ID | [hardcoded] | browser_connector/extension.py | YES |
| Edge extension ID | [hardcoded] | browser_connector/extension.py | YES |
| Chrome path (Windows) | C:\Program Files\Google\Chrome\Application\chrome.exe | browser_connector/ | YES |
| Firefox path (Windows) | C:\Program Files\Mozilla Firefox\firefox.exe | browser_connector/ | YES |
| Edge path (Windows) | C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe | browser_connector/ | YES |
| Chrome process name | chrome | desktop_state.py | YES |
| Firefox process name | firefox | desktop_state.py | YES |
| Edge process name | msedge | desktop_state.py | YES |

## MCP Server Assumptions

| Assumption | Value | File | Should Be External |
|---|---|---|---|
| filesystem server name | filesystem | core/mcp/servers.py | YES |
| git server name | git | core/mcp/servers.py | YES |
| terminal server name | terminal | core/mcp/servers.py | YES |
| sqlite server name | sqlite | core/mcp/servers.py | YES |
| docker server name | docker | core/mcp/servers.py | YES |
| github server name | github | core/mcp/servers.py | YES |
| postgres server name | postgres | core/mcp/servers.py | YES |
| redis server name | redis | core/mcp/servers.py | YES |
| memory server name | memory | core/mcp/servers.py | YES |
| web_search server name | web_search | core/mcp/servers.py | YES |
| Server timeout | 10 seconds | core/mcp/ | YES |
| Max concurrent | 5 | core/mcp/ | YES |

## Embedding Model Assumptions

| Assumption | Value | File | Should Be External |
|---|---|---|---|
| Model | all-MiniLM-L6-v2 | semantic/ | YES |
| Dimension | 384 | semantic/ | YES |
| Cache directory | .cache/embeddings | semantic/ | YES |
