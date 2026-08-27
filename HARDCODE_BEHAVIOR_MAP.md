# HARDCODE_BEHAVIOR_MAP — User Language → Behavior Flow

This map traces how user language flows through every hardcoded layer to produce a response.

## Full Flow

```
User Input
  │
  ▼
┌─────────────────────────────────────────┐
│ 1. ACTIVATION DETECTION                 │
│   Hardcoded: activation phrases/patterns│
│   File: activation_detection.py         │
│   Decision: "Is Kio being addressed?"   │
├─────────────────────────────────────────┤
│ 2. INTENT CLASSIFICATION                │
│   Hardcoded: GREETING_PHRASES,          │
│   IDENTITY_KEYWORDS, SOCIAL_KEYWORDS,   │
│   _CLOSE_VERBS, _CLOSE_PHRASES,         │
│   IDENTITY_PATTERNS                     │
│   File: pipeline/__init__.py            │
│   Decision: intent_type (string enum)   │
├─────────────────────────────────────────┤
│ 3. COMMAND ROUTING                      │
│   Hardcoded: routing table,             │
│   priority chain, if/elif rules         │
│   Files: command_router.py,             │
│   pipeline/__init__.py                  │
│   Decision: which subsystem handles     │
├─────────────────────────────────────────┤
│ 4. STATE MACHINE                        │
│   Hardcoded: STATE_IDLE,                │
│   STATE_MEDIA_PLAYING,                  │
│   STATE_BROWSER_ACTIVE, transitions     │
│   File: pipeline/__init__.py            │
│   Decision: current state context       │
├─────────────────────────────────────────┤
│ 5. MOOD/TRIGGER MAPPING                │
│   Hardcoded: mood → genre, time → mood  │
│   File: pipeline/__init__.py,           │
│   media_recommender.py                  │
│   Decision: mood state for media        │
├─────────────────────────────────────────┤
│ 6. PROVIDER SELECTION                   │
│   Hardcoded: LLM provider chain         │
│   (Gemini→Groq→OpenRouter→Together→     │
│   Cerebras), media provider registry    │
│   Files: llm_router.py,                 │
│   provider_registry.py,                 │
│   media_registry.py                     │
│   Decision: which provider to use       │
├─────────────────────────────────────────┤
│ 7. MEDIA DISCOVERY                      │
│   Hardcoded: yt-dlp commands,           │
│   Spotify API calls, URL patterns,      │
│   DOM selectors                         │
│   Files: media_discovery.py,            │
│   providers/youtube_provider.py,        │
│   providers/spotify_provider.py,        │
│   providers/browser_provider.py         │
│   Decision: find and return media       │
├─────────────────────────────────────────┤
│ 8. SESSION MANAGEMENT                   │
│   Hardcoded: volume step (10%),         │
│   session timeout (3600s),              │
│   max history (500),                    │
│   state transitions                     │
│   Files: media_session.py,              │
│   media_manager.py                      │
│   Decision: session state               │
├─────────────────────────────────────────┤
│ 9. INTELLIGENCE ROUTING                 │
│   Hardcoded: routing rules,             │
│   scoring weights, thresholds           │
│   Files: intelligence_router.py,        │
│   local_reasoner.py,                    │
│   proactive_evaluator.py, retrieval.py  │
│   Decision: response intelligence       │
├─────────────────────────────────────────┤
│ 10. LLM ORCHESTRATION                   │
│    Hardcoded: system prompt,            │
│    canonical knowledge, max length,     │
│    provider URLs, model names           │
│    Files: llm/gateway.py,               │
│    llm/constants.py,                    │
│    llm/orchestrator.py                  │
│    Decision: generate response text     │
├─────────────────────────────────────────┤
│ 11. RESPONSE FORMATTING                 │
│    Hardcoded: templates,                │
│    response phrase construction         │
│    Files: runtime_response_formatter.py,│
│    media_manager.py                     │
│    Decision: final user-visible text    │
├─────────────────────────────────────────┤
│ 12. PERSONALITY INJECTION               │
│    Hardcoded: identity responses,       │
│    help text, emergency responses,      │
│    _COMMAND_EXPLANATIONS                │
│    Files: companion/, personality/      │
│    Decision: personality tone           │
└─────────────────────────────────────────┘
  │
  ▼
User-Visible Response
```

## Media-Specific Flow

```
User: "play some music"
  │
  ▼
Activation Detection (hardcoded phrases)
  │
  ▼
Intent Classification (SOCIAL_KEYWORDS contains "play music")
  │
  ▼
Mood Mapping (hardcoded: "play music" → "happy")
  │
  ▼
Media Discovery
  ├── YouTube: yt-dlp --dump-json --no-download --flat-playlist "ytsearch10:happy music"
  ├── Spotify: spotifydl search "happy music"
  └── Browser: navigate to YouTube, click play
  │
  ▼
Session State (hardcoded: STATE_MEDIA_PLAYING)
  │
  ▼
Response: "🎵 Now playing X by Y"
```

## Browser Automation Flow

```
User: "open YouTube"
  │
  ▼
Activation Detection
  │
  ▼
Intent: browser_open
  │
  ▼
Desktop State (hardcoded: check for chrome/firefox/edge processes)
  │
  ▼
Browser Connector
  ├── WebSocket: ws://localhost:9877 (hardcoded port)
  ├── Extension: Chrome extension ID (hardcoded)
  └── CDP: Browser.navigate (hardcoded command)
  │
  ▼
Response: "Opening YouTube for you."
```

## LLM Fallback Flow

```
User: "tell me about quantum physics"
  │
  ▼
Intent: general_conversation
  │
  ▼
LLM Router (hardcoded priority):
  1. Try Gemini
  2. If fail → Try Groq
  3. If fail → Try OpenRouter
  4. If fail → Try Together
  5. If fail → Try Cerebras
  6. If all fail → hardcoded fallback response
  │
  ▼
System Prompt (hardcoded: _ASYSTEM_PROMPT with Kio identity)
  │
  ▼
Canonical Knowledge (hardcoded: _CANONICAL_KNOWLEDGE dict)
  │
  ▼
Response (truncated to _MAX_RESPONSE_LENGTH)
```
