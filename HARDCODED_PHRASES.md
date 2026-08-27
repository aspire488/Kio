# HARDCODED_PHRASES — Every Keyword, Pattern, Regex, Alias

## Intent Classification Phrases

### GREETING_PHRASES (pipeline/__init__.py)
```
"hello", "hey", "hi", "hola", "bonjour", "good morning", "good evening",
"good afternoon", "good night", "howdy", "greetings", "what's up",
"sup", "yo", "hiya", "ahoy", "salutations"
```

### IDENTITY_KEYWORDS (pipeline/__init__.py)
```
"kio", "you", "your", "your name", "who are you", "what are you",
"tell me about yourself", "what's your name", "introduce yourself",
"are you a bot", "are you human", "what do you do"
```

### SOCIAL_KEYWORDS (pipeline/__init__.py)
```
"how are you", "how's it going", "what's up", "how do you do",
"nice to meet you", "pleasure to meet you", "tell me a joke",
"what's your favorite", "do you like", "who made you",
"who created you", "when were you born", "where do you live"
```

### _CLOSE_VERBS (pipeline/__init__.py)
```
"pause", "stop", "quit", "close", "turn off", "end", "halt",
"discontinue", "terminate", "cease", "shut down", "cancel"
```

### _CLOSE_PHRASES (pipeline/__init__.py)
```
"turn off music", "exit music mode", "stop playing",
"pause the music", "quit music", "end the music",
"halt playback", "shut off music", "cancel music"
```

### IDENTITY_PATTERNS (pipeline/__init__.py)
```
r"who\s+(are\s+you|made\s+you|created\s+you|built\s+you)",
r"what\s+(are\s+you|is\s+your\s+name|do\s+you\s+do)",
r"tell\s+me\s+about\s+(yourself|you)",
r"your\s+name",
r"introduce\s+yourself"
```

### Activation Patterns (activation_detection.py)
```
"kio", "hey kio", "ok kio", "yo kio", "hi kio",
"hello kio", "assistant", "hey assistant", "computer"
```

### Intent Routing Keywords (pipeline/__init__.py)
```
Media: "play", "music", "song", "artist", "album", "playlist", "skip", "next", "previous", "pause", "stop", "volume"
Browser: "open", "browse", "search", "website", "url", "navigate", "screenshot", "click"
Memory: "remember", "forget", "recall", "memory", "save"
Context: "context", "previous", "before", "last time"
General: "help", "what can you do", "who are you", "how are you"
```

### Mood Trigger Mapping (pipeline/__init__.py)
```
"play some music" → "happy"
"play something upbeat" → "happy"
"play something calm" → "relaxed"
"play something sad" → "melancholic"
"play something energetic" → "energetic"
"play focus music" → "focused"
```

### Mood → Genre Mapping (media_recommender.py)
```
happy → ["pop", "dance", "upbeat", "feel good"]
relaxed → ["ambient", "chill", "lo-fi", "classical"]
melancholic → ["sad", "emotional", "ballad", "acoustic"]
energetic → ["rock", "edm", "workout", "high energy"]
focused → ["instrumental", "classical", "ambient", "focus"]
```

### Time-of-Day → Mood Mapping (media_recommender.py)
```
morning (6-12) → "energetic"
afternoon (12-17) → "focused"
evening (17-21) → "relaxed"
night (21-6) → "melancholic"
```

## Browser Automation Phrases

### URL Patterns (browser/)
```
r"https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+"
r"https?://youtu\.be/[\w-]+"
r"https?://(?:www\.)?youtube\.com/playlist\?list=[\w-]+"
r"https?://open\.spotify\.com/(?:track|album|playlist)/[\w]+"
```

### DOM Selectors (browser/)
```
"document.querySelector('video')"
"document.querySelector('#movie_player')"
"document.querySelector('.ytp-play-button')"
"document.querySelector('.ytp-next-button')"
"document.querySelector('.ytp-prev-button')"
"document.querySelector('.ytp-volume-panel')"
```

### CDP Commands (browser_connector/cdp_handler.py)
```
"Browser.navigate"
"Browser.getWindowForTarget"
"Page.captureScreenshot"
"Runtime.evaluate"
"Input.dispatchMouseEvent"
"Input.dispatchKeyEvent"
```

## Media Provider Commands

### yt-dlp Command Template (media_discovery.py, providers/youtube_provider.py)
```
yt-dlp --dump-json --no-download --flat-playlist "ytsearch{count}:{query}"
yt-dlp --get-url --get-title "{url}"
yt-dlp -x --audio-format mp3 -o "{output}" "{url}"
```

### Spotify Command Template (providers/spotify_provider.py)
```
spotifydl "{url}" -o "{output}"
spotifydl search "{query}"
```

## LLM Provider Patterns

### Provider Priority Chain (llm_router.py)
```
1. Gemini (google-generativeai)
2. Groq (groq)
3. OpenRouter (openrouter)
4. Together (together)
5. Cerebras (cerebras)
```

### System Prompt (llm/gateway.py — _ASYSTEM_PROMPT)
```
"You are Kio, a friendly and intelligent AI companion. You are helpful,
creative, and always aim to provide the best possible assistance. You have
access to various tools including media control, web browsing, memory, and
context management. You should be conversational, warm, and engaging while
remaining professional and accurate."
```

### Canonical Knowledge Keys (llm/constants.py — _CANONICAL_KNOWLEDGE)
```
"kio_version", "kio_creator", "kio_capabilities", "kio_limitations",
"music_control", "browser_control", "memory_system", "context_system"
```

## MCP Server Names (core/mcp/servers.py)
```
"filesystem", "git", "terminal", "sqlite", "docker",
"github", "postgres", "redis", "memory", "web_search"
```

## Adapter Names (adapters/)
```
"media_adapter", "browser_adapter", "memory_adapter",
"context_adapter", "intelligence_adapter", "llm_adapter"
```

## Memory Category Names (memory/)
```
"general", "media", "preference", "context", "personality",
"interaction", "learned", "temporary"
```
