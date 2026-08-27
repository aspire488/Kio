# HARDCODED_FALLBACKS — Every Fallback Trigger Path

## LLM Provider Fallback Chain

**File:** `llm_router.py`

```
Primary: Gemini
  │
  ├─→ Timeout/Error
  │     ▼
  │   Fallback 1: Groq
  │     │
  │     ├─→ Timeout/Error
  │     │     ▼
  │     │   Fallback 2: OpenRouter
  │     │     │
  │     │     ├─→ Timeout/Error
  │     │     │     ▼
  │     │     │   Fallback 3: Together
  │     │     │     │
  │     │     │     ├─→ Timeout/Error
  │     │     │     │     ▼
  │     │     │     │   Fallback 4: Cerebras
  │     │     │     │     │
  │     │     │     │     ├─→ Timeout/Error
  │     │     │     │     │     ▼
  │     │     │     │     │   Hardcoded Error Response:
  │     │     │     │     │   "Sorry, I'm having trouble connecting."
  │     │     │     │     │
  │     │     │     │     └─→ Success → Return response
  │     │     │     │
  │     │     │     └─→ Success → Return response
  │     │     │
  │     │     └─→ Success → Return response
  │     │
  │     └─→ Success → Return response
  │
  └─→ Success → Return response
```

**Hardcoded error messages in chain:**
- "Sorry, I'm having trouble connecting."
- "No provider available"
- "All providers failed"

## Media Provider Fallback Chain

**File:** `media_discovery.py`

```
Primary: YouTube (yt-dlp)
  │
  ├─→ No results / Error
  │     ▼
  │   Fallback 1: Spotify (spotifydl)
  │     │
  │     ├─→ No results / Error
  │     │     ▼
  │     │   Fallback 2: Browser (YouTube web)
  │     │     │
  │     │     ├─→ Error
  │     │     │     ▼
  │     │     │   Fallback 3: Local media files
  │     │     │     │
  │     │     │     ├─→ No results
  │     │     │     │     ▼
  │     │     │     │   Hardcoded: "No music results found for X"
  │     │     │     │
  │     │     │     └─→ Success → Return local file
  │     │     │
  │     │     └─→ Success → Return browser result
  │     │
  │     └─→ Success → Return Spotify result
  │
  └─→ Success → Return YouTube result
```

**Hardcoded fallback messages:**
- "No music results found for X"
- "Sorry, I couldn't find any music for that."

## Intent Classification Fallback

**File:** `pipeline/__init__.py`

```
User Input
  │
  ├─→ Matches GREETING_PHRASES → intent = "greeting"
  ├─→ Matches IDENTITY_KEYWORDS → intent = "identity"
  ├─→ Matches SOCIAL_KEYWORDS → intent = "social"
  ├─→ Matches _CLOSE_VERBS → intent = "media_stop"
  ├─→ Matches _CLOSE_PHRASES → intent = "media_stop"
  ├─→ Matches IDENTITY_PATTERNS → intent = "identity"
  ├─→ Matches media keywords → intent = "media_*"
  ├─→ Matches browser keywords → intent = "browser_*"
  ├─→ Matches memory keywords → intent = "memory_*"
  │
  └─→ No match
        ▼
      Fallback: intent = "general_conversation"
        │
        ├─→ Send to LLM for general response
        └─→ If LLM fails → hardcoded: "I'm not sure what you mean."
```

## Browser Fallback Chain

**File:** `browser_connector/`

```
Primary: WebSocket connection to extension
  │
  ├─→ Connection failed
  │     ▼
  │   Fallback 1: Try CDP directly
  │     │
  │     ├─→ CDP failed
  │     │     ▼
  │     │   Fallback 2: Try launching browser
  │     │     │
  │     │     ├─→ Launch failed
  │     │     │     ▼
  │     │     │   Hardcoded: "Sorry, I couldn't connect to the browser."
  │     │     │
  │     │     └─→ Launched → Reconnect
  │     │
  │     └─→ CDP connected → Proceed
  │
  └─→ WS connected → Proceed
```

## Memory Fallback

**File:** `memory/`

```
Memory Query
  │
  ├─→ Exact match found → Return
  ├─→ Fuzzy match found (score > 0.7) → Return with confidence flag
  │
  └─→ No match
        ▼
      Fallback: Return empty + log
        │
        └─→ If memory system fails → hardcoded: "I don't have that information."
```

## Context Fallback

**File:** `context/`

```
Context Request
  │
  ├─→ Context available → Return
  │
  └─→ No context
        ▼
      Fallback: Return empty context
        │
        └─→ Hardcoded: "I don't have previous context for this."
```

## Activation Detection Fallback

**File:** `activation_detection.py`

```
User Input
  │
  ├─→ Matches activation phrases → activated = True
  ├─→ Matches activation patterns → activated = True
  │
  └─→ No match
        ▼
      Fallback: activated = False
        │
        └─→ If in conversation mode → Still process
            If not → Ignore input
```
