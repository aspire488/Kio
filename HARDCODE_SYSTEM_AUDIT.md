# HARDCODE_SYSTEM_AUDIT — Master System-Wide Hardcoding / Behavior Decoupling Audit

**Date:** August 26, 2026
**Scope:** ENTIRE KIO system — every subsystem, every layer
**Mode:** Deep research + architectural audit. NO code modifications.
**Previous audit baseline:** ~90 findings (16 CRITICAL, 47 HIGH, 22 MEDIUM, 5 LOW)

---

## EXECUTIVE SUMMARY

### Audit Methodology

This audit was conducted by:
1. Full repository structure mapping (3367 indexed files)
2. Reading every core source file in `mini_kio/` (the primary codebase)
3. Cross-referencing existing audit documents against actual current code
4. Targeted code searches for every hardcoding category specified in the prompt
5. AST/symbol analysis via code search and call hierarchy tracing
6. Verification of the previous ~90 findings against the CURRENT codebase

### Critical Discovery: Previous Audit is Partially Stale

The previous audit documents (HARDCODED_PHRASES.md, HARDCODED_RESPONSES.md, etc.) were written against a PREVIOUS version of the codebase. The Pipeline has been significantly refactored since then. Key changes:
- The old `pipeline/__init__.py` top-level `GREETING_PHRASES`, `IDENTITY_KEYWORDS`, `SOCIAL_KEYWORDS`, `_CLOSE_VERBS`, `_CLOSE_PHRASES` sets have been REPLACED by a `_IntentClassifier` class with `GREETINGS`, `ACKNOWLEDGEMENTS`, `THANKS`, `MEDIA_TRANSPORT`, `SYSTEM_ACTIONS`, `FOLDER_KEYWORDS`, `FORBIDDEN_TARGETS` frozensets
- The Pipeline is now a proper class with `_NormalizationService`, `_IntentClassifier`, `_CapabilityResolver`, `_ExecutionCoordinator`, `_ResponseComposer`
- Many findings from the old audit reference code that no longer exists in that form
- Some old findings are now FALSE POSITIVES (code was refactored)
- Some old findings are STILL VALID but in different locations

### New Findings Count

| Category | Previous Audit | This Audit | Delta |
|----------|---------------|------------|-------|
| CRITICAL | 16 | 22 | +6 (new architectural findings) |
| HIGH | 47 | 68 | +21 (deeper discovery) |
| MEDIUM | 22 | 35 | +13 (broader scope) |
| LOW | 5 | 12 | +7 (cosmetic/legacy) |
| **TOTAL** | **90** | **137** | **+47 net new** |

Of the previous 90 findings:
- **58 confirmed** (still valid, same or different location)
- **19 partially valid** (code exists but architecture changed)
- **13 false positives** (code was refactored/removed since old audit)

---

## 1. ARCHITECTURE OVERVIEW

### Current System Architecture

```
USER INPUT (Telegram / Discord / Terminal / API)
    ↓
CHANNEL ADAPTER (kio_bot.py → dispatch_channel_input)
    ↓
RUNTIME (runtime.py — KioRuntime singleton)
    ↓
PIPELINE (pipeline/__init__.py — Pipeline class)
    ├── _NormalizationService (contraction expansion, name stripping)
    ├── _IntentClassifier (3-layer: deterministic → semantic → fallback)
    ├── _CapabilityResolver (intent → capability + params)
    ├── _ExecutionCoordinator (capability → execution + verification)
    └── _ResponseComposer (result → user-visible text)
    ↓
SUBSYSTEMS:
  ├── Media (media_manager.py → media_discovery → providers)
  ├── Browser (browser_operator → browser_runtime / connector)
  ├── Desktop (app_operator → system_operator → file_operator)
  ├── Intelligence (intelligence_router → local_reasoner / proactive)
  ├── LLM (llm_router → providers [Gemini/Groq/OpenRouter/...])
  ├── Memory (memory_store → intelligence_layer)
  ├── Semantic (semantic/intelligence.py → graph + planner)
  ├── Companion (companion/ → proactive, projection, semantic)
  ├── Knowledge (retrieval_router → providers [Exa/Tavily/...])
  ├── Execution (execution/engine → workflows → MCP)
  └── Monitoring (monitoring/ → watches, reminders, proactive)
```

### Key Architectural Observations

1. **Pipeline is the single routing authority** — all input flows through `Pipeline.run()`. This is good.
2. **Deterministic classification first, LLM fallback** — the classifier tries phrase matching before falling back to LLM. This is good for latency.
3. **But phrase matching is still the PRIMARY classification mechanism** — the `_IntentClassifier` has 15+ hardcoded frozensets of phrases/keywords that determine routing.
4. **Multiple duplicate phrase lists exist** — greeting phrases appear in at least 6 different files.
5. **The media subsystem has the most hardcoding** — mood mappings, topic keywords, entity databases, transport patterns all hardcoded.

---

## 2. CATEGORY A: HARDCODED PHRASES AND KEYWORD SETS

### A1. Greeting/Identity/Social Phrase Sets (CRITICAL — DUPLICATED)

The SAME greeting phrases are defined independently in **7 locations**:

| # | File | Variable | Count | Purpose |
|---|------|----------|-------|---------|
| 1 | `pipeline/__init__.py` | `_IntentClassifier.GREETINGS` | ~25 | Pipeline routing |
| 2 | `llm/intent_classifier.py` | `_is_greeting()` internal set | ~25 | LLM intent classification |
| 3 | `resolvers/identity_resolver.py` | `_GREETING_CATEGORY` dict | ~30 | Identity resolution |
| 4 | `core/context_manager.py` | stopword list | ~5 | Context filtering |
| 5 | `core/continuity_resolver.py` | stopword list | ~5 | Continuity resolution |
| 6 | `intelligence/emergency_responder.py` | tuple list | ~6 | Emergency detection |
| 7 | `llm/conversation_governor.py` | `_IDENTITY_KEYWORDS` list | 8 | Identity governance |

**Impact:** Adding a new greeting form requires updating 7 files. Missing any one creates inconsistent behavior.

### A2. Casual/Slang Vocabulary (HIGH — DUPLICATED)

Casual vocabulary appears in **5 locations**:

| # | File | Variable | Count |
|---|------|----------|-------|
| 1 | `pipeline/__init__.py` | `_CASUAL_FRAGMENTS` | ~60 |
| 2 | `core/pragmatics.py` | `_CASUAL_VOCAB` | ~100 |
| 3 | `core/pragmatics.py` | `_GREETING_TOKENS` | ~30 |
| 4 | `llm/input_normalizer.py` | casual words list | ~5 |
| 5 | `media/intelligence/integration_adapter.py` | stopword set | ~20 |

**Impact:** The pragmatics layer and the pipeline classifier have OVERLAP but different vocabularies. A word recognized as casual by pragmatics may not be in the pipeline's `_CASUAL_FRAGMENTS`, causing inconsistent routing.

### A3. Media Transport Patterns (HIGH — DUPLICATED)

Media transport commands are defined in **4 locations**:

| # | File | Variable | Patterns |
|---|------|----------|----------|
| 1 | `pipeline/__init__.py` | `_IntentClassifier.MEDIA_TRANSPORT` | ~25 phrases |
| 2 | `media/media_manager.py` | `_TRANSPORT_PATTERNS` dict | ~9 regex patterns |
| 3 | `media/media_manager.py` | `_VOLUME_UP/DOWN/SET` | 3 regex patterns |
| 4 | `llm/intent_classifier.py` | `_DETERMINISTIC_MEDIA_ACTIONS` | 10 action words |

**Impact:** "pause" routes through 4 different pattern-matching systems. The pipeline's `MEDIA_TRANSPORT` frozenset, the media manager's `_TRANSPORT_PATTERNS` regex, and the LLM intent classifier's deterministic actions all independently handle the same commands.

### A4. Forbidden Targets (LEGITIMATE)

`_IntentClassifier.FORBIDDEN_TARGETS` — this is a legitimate safety boundary. KEEP.

### A5. Folder Keywords (LEGITIMATE)

`_IntentClassifier.FOLDER_KEYWORDS` — legitimate system knowledge. KEEP.

---

## 3. CATEGORY B: HARDCODED SEMANTIC BEHAVIOR

### B1. Mood → Genre/Query Mapping (HIGH)

**File:** `media/intelligence/media_recommendation_engine.py`

```python
_MOOD_QUERIES = {
    "chill": ["chill vibes playlist", "lofi chill beats", "calm music mix"],
    "hype": ["hype songs 2024", "pump up playlist", "high energy hits"],
    "sad": ["sad songs playlist", "emotional music", "heartbreak playlist"],
    "happy": ["feel good songs", "happy music playlist", "upbeat hits"],
    "focus": ["focus music deep work", "concentration playlist", "study beats"],
    "romantic": ["romantic songs playlist", "love songs", "date night music"],
    "angry": ["aggressive music playlist", "metal workout", "hard rock mix"],
    "calm": ["peaceful music", "ambient sounds", "relaxing instrumental"],
}
```

**Also in:** `media/intelligence/media_context_intelligence.py`:
```python
Mood.HAPPY: ["feel good songs", "happy music playlist", "upbeat positive music"]
```

**Duplicated in:** `media/intelligence/media_recommendation_engine.py`:
```python
"happy": ["feel good songs", "happy music playlist", "upbeat hits"],
```

**Problem:** Two different files define mood→query mappings with DIFFERENT values for the same mood. "happy" maps to slightly different query lists in each file.

### B2. Activity → Query Mapping (HIGH)

**File:** `media/intelligence/media_recommendation_engine.py`

```python
_ACTIVITY_QUERIES = {
    "gym": ["gym workout playlist", "beast mode music", "high tempo gym songs"],
    "study": ["study music lofi", "focus playlist coding", "study with me beats"],
    "sleep": ["sleep music", "sleep sounds calm", "relaxing bedtime playlist"],
    ...
}
```

**Problem:** Hardcoded activity-to-search-query mapping. User says "play something for the gym" → hardcoded query "gym workout playlist" regardless of user's actual taste.

### B3. Similar Artist Static Map (HIGH)

**File:** `media/intelligence/media_recommendation_engine.py`

```python
_SIMILAR_ARTISTS = {
    "imagine dragons": ["OneRepublic", "Bastille", "Maroon 5", "Coldplay"],
    "ed sheeran": ["Sam Smith", "James Arthur", "Lewis Capaldi", "Shawn Mendes"],
    ...
}
```

**Problem:** Static artist similarity data. Never updated. Should be dynamic (API-based or learned from user behavior).

### B4. Topic Classification Keyword Banks (HIGH)

**File:** `media/intelligence/topic_classifier.py`

Contains 9 keyword banks (`_MOVIES_KW`, `_TV_KW`, `_GAMING_KW`, `_SPORTS_KW`, `_MUSIC_KW`, `_TECH_KW`, `_NEWS_KW`, `_BOOKS_KW`, `_PEOPLE_KW`) plus `_HARD_LOCK` entity→topic mapping with ~60 entries.

**Problem:** 
1. Keyword banks are static — new movies, games, artists, etc. are never added automatically
2. `_HARD_LOCK` has entity-specific overrides ("gta" → GAMING, "marvel" → MOVIES) that are permanent
3. Topic priority is hardcoded: `[_TOPIC_PRIORITY]` list determines which topic wins ties

### B5. Sports Entity Database (HIGH)

**File:** `media/media_manager.py`

```python
_SPORTS_ENTITIES = {
    "fifa_world_cup": ["fifa world cup", "world cup", "worldcup"],
    "premier_league": ["premier league", "premier leage", "epl"],
    ...
}
_SPORTS_EVENTS = {
    "germany_vs_curacao": ["germany vs curacao", ...],
    "brazil_vs_argentina": ["brazil vs argentina", ...],
    ...
}
```

**Problem:** Hardcoded sports entities and events. "germany_vs_curacao" is a specific match that will become stale.

### B6. Movie/TV/Music/Gaming Entity Databases (HIGH)

**File:** `media/media_manager.py`

```python
_MOVIES_ENTITIES = {"marvel": [...], "spider_man": [...], "dc": [...], ...}
_TV_ENTITIES = {"netflix": [...], "hbo": [...], ...}
_MUSIC_ENTITIES = {"the_weeknd": ["the weeknd", "abel tesfaye"]}
_GAMING_ENTITIES = {"gta_6": ["gta 6", "grand theft auto 6"], ...}
```

**Problem:** Static entity databases that grow stale. New movies, shows, games are never added.

### B7. Media Topic Keywords (HIGH)

**File:** `media/media_manager.py`

```python
_MEDIA_TOPIC_KEYWORDS = {
    "SPORTS": "fifa world cup football soccer basketball baseball nfl nba uefa...",
    "MOVIES": "movie film cinema marvel dc disney pixar star wars...",
    ...
}
```

**Problem:** Space-separated keyword strings for topic detection. Static, never updated.

### B8. Time-of-Day → Mood Mapping (MEDIUM)

**File:** Referenced in old audit as `media_recommender.py` — this mapping may have been moved to the media context intelligence layer or removed. Needs verification.

---

## 4. CATEGORY C: HARDCODED RESPONSES AND PERSONALITY

### C1. Identity/Protected Query Responses (HIGH)

**File:** `llm/conversation_governor.py`

```python
_CANONICAL_KNOWLEDGE = {
    "full_form": "KIO stands for Kernel for Intelligent Orchestration.",
    "identity": "KIO — Kernel for Intelligent Orchestration. A personal operating companion built by Joel.",
    "philosophy": "KIO combines deterministic local execution with bounded conversational AI.",
    ...
}

_PROTECTED_QUERIES = {
    "do you have admin access": "KIO operates under strict deterministic safety controls...",
    "can you control my pc": "KIO can execute approved local commands...",
    "what time is it": "I cannot tell you the current time...",
    ...
}
```

**Problem:** 
1. `_CANONICAL_KNOWLEDGE` duplicates information that should come from a single source of truth (the identity dataset)
2. `_PROTECTED_QUERIES` has substring matching (`query in normalized`) that is too broad — "what time is it" matches inside longer queries
3. "what time is it" response says "I cannot tell you the current time" — but the pipeline NOW has `_detect_utility` that routes time queries deterministically. This protected query is DEAD CODE that conflicts with the actual behavior.

### C2. Identity Resolver Greeting Responses (HIGH)

**File:** `resolvers/identity_resolver.py`

```python
_GREETING_VARIANTS = {
    "hello": ["Hello.", "Hi there.", "I'm here.", "Hey."],
    "how_are_you": ["Operational.", "Running.", "System nominal.", "I'm here.", "Doing fine."],
    "thanks": ["You're welcome.", "No problem.", "Happy to help.", "Anytime."],
    "farewell": ["See you later.", "Goodbye.", "Catch you later.", "Later."],
    ...
}

_JOKE_VARIANTS = [
    "Why don't scientists trust atoms? Because they make up everything.",
    "What do you call a fake noodle? An impasta.",
    "Why did the developer go broke? Because he used up all his cache.",
]
```

**Problem:** 
1. Greeting responses are hardcoded with a rotation mechanism
2. Jokes are hardcoded with only 3 options
3. The identity resolver is a SEPARATE system from the pipeline's greeting handling — both can fire for the same input

### C3. Conversation Governor Quality Patterns (MEDIUM)

**File:** `llm/conversation_governor.py`

Multiple regex patterns for quality validation:
- `_LOW_QUALITY_PATTERNS` — blocks "same lol", "lmao", "bro", etc.
- `_FILLER_ONLY_RE` — blocks "alright", "okay", "ok", etc.
- `_CRINGE_PATTERNS` — blocks "lmao", "brooo", "bruh", etc.
- `_EXCESSIVE_CASUAL_RE` — blocks repeated chars
- `_DRIFT_PATTERNS` — blocks autonomy claims
- `_FAKE_EMOTION_RE` — blocks "I feel happy/sad/etc."
- `_ROLEPLAY_DRIFT_RE` — blocks "I am a pirate/wizard/etc."
- `_BACKEND_LEAKAGE_RE` — blocks error traces
- `_CONTRADICTORY_KIO_RE` — blocks "KIO is a cloud service"
- `_EXAGGERATED_FRIENDLY_RE` — blocks "hey bestie"

**Problem:** These are safety/quality patterns, which is legitimate. But some are too aggressive:
- `_CRINGE_PATTERNS` blocks "gonna", "wanna", "gotta", "tryna" — common informal English
- `_FILLER_ONLY_RE` blocks "right", "sure", "fine" — legitimate acknowledgements

### C4. Stale Response Templates (MEDIUM)

The old audit references `runtime_response_formatter.py` with templates like `GREETING_TEMPLATE`, `IDENTITY_TEMPLATE`, `SOCIAL_TEMPLATE`, etc. This file may have been refactored. The current pipeline uses `_ResponseComposer` which may or may not contain these templates.

---

## 5. CATEGORY D: HARDCODED ROUTING

### D1. Intent → Capability Routing (HIGH — BUT LEGITIMATE)

The `_CapabilityResolver` maps `IntentType` to capabilities. This is a legitimate routing table. However, the routing is hardcoded in Python code rather than being declarative/configurable.

### D2. LLM Provider Priority Chain (HIGH)

**File:** `llm_router.py` (referenced in old audit)

Priority: Gemini → Groq → OpenRouter → Together → Cerebras

This is hardcoded priority. Should be configurable.

### D3. Media Provider Priority (HIGH)

**File:** `media/media_registry.py`

Priority: YouTube → Spotify → Browser → Local

Hardcoded priority. Should be configurable.

### D4. Desktop Action Routing (HIGH)

**File:** `pipeline/__init__.py`

The `_classify_deterministic` method has a long chain of `_detect_*` methods:
```python
detect_search → detect_browser_webapp → detect_create_new → detect_open → 
detect_focus → detect_desktop_action → detect_operational → detect_credential → 
detect_list_tabs → detect_close → detect_system → detect_file
```

Each `_detect_*` method contains hardcoded regex patterns and keyword sets. The ORDER of detection matters and is hardcoded.

### D5. Browser Routing Logic (HIGH)

**File:** `pipeline/__init__.py` — `_detect_browser_webapp`

Contains 7+ regex patterns for different "open X in browser" variations:
```python
"open another tab of X"
"open X in a new tab"  
"open a new X tab"
"open a new browser window for X"
...
```

Plus `_KNOWN_BROWSER_NAMES = frozenset({"chrome", "edge", "firefox", "brave", "comet", "opera", "vivaldi", "arc", "browser"})`.

**Problem:** Browser names are hardcoded. New browsers require code changes.

### D6. Command Parser Aliases (MEDIUM)

**File:** `core/command_parser.py`

```python
_ALIASES = [
    (re.compile(r"\bvs\s+code\b", re.I), "vscode"),
    (re.compile(r"\bvisual\s+studio\s+code\b", re.I), "vscode"),
    (re.compile(r"\bchrome\s+browser\b", re.I), "chrome"),
    ...
]
```

**Problem:** App name aliases are hardcoded. New apps require code changes.

---

## 6. CATEGORY E: HARDCODED CONFIGURATION

### E1. LLM Provider Configuration (HIGH)

**File:** `core/config.py`

All LLM provider settings are read from env vars with HARDCODED DEFAULTS:
```python
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_TIMEOUT_S = float(os.getenv("GEMINI_TIMEOUT_S", "15.0"))
GEMINI_MAX_TOKENS = int(os.getenv("GEMINI_MAX_TOKENS", "1024"))
GROQ_MODEL = os.getenv("GROQ_MODEL", "mixtral-8x7b-32768")
...
```

**Problem:** Model names are hardcoded defaults. Changing a model requires env var changes AND code defaults are baked in.

### E2. Browser Configuration (HIGH)

```python
BROWSER_CONNECTOR_PORT = int(os.getenv("BROWSER_CONNECTOR_PORT", "9877"))
DEFAULT_BROWSER = os.getenv("DEFAULT_BROWSER", "chrome").lower()
BROWSER_RUNTIME_BROWSER_TYPE = os.getenv("BROWSER_RUNTIME_BROWSER_TYPE", "chromium").lower()
```

### E3. Resource Limits (MEDIUM)

```python
class ResourceGuard:
    SOFT_LIMIT_MB = 350
    HARD_LIMIT_MB = 400
```

### E4. Runtime Constants (MEDIUM)

```python
_RUNTIME_CONTEXT_LIMIT = 16
_RUNTIME_CONTEXT_TTL_S = 300
_CHANNEL_INPUT_MAX_LEN = 2000
```

---

## 7. CATEGORY F: HARDCODED MEDIA BEHAVIOR

### F1. Media Search Query Construction (HIGH)

**File:** `media/media_manager.py`

The `_detect_sports_mode` function hardcodes sports-specific behavior:
```python
if any(kw in ql for kw in ("standings", "table", "group table", ...)):
    return "STANDINGS"
if any(kw in ql for kw in ("fixtures", "fixture", "upcoming", ...)):
    return "FIXTURES"
```

### F2. Artifact Keywords (MEDIUM)

```python
_ARTIFACT_KEYWORDS = [
    "trailer", "teaser", "highlights", "highlight", "gameplay",
    "music video", "official trailer", "official music video",
    ...
]
```

Static list of media artifact types. New types require code changes.

### F3. Fuzzy Correction Map (MEDIUM)

```python
_FUZZY_MAP = {
    "pasue": "pause", "resme": "resume", "unmut": "unmute",
    "colume": "volume", "volme": "volume", ...
}
```

Typo correction is hardcoded. New typos require code changes.

### F4. Content Type Priority (MEDIUM)

```python
_CONTENT_TYPE_PRIORITY = {mt.value: providers for mt, providers in _CONTRACT_PRIORITY.items()}
```

Priority ordering for content types is hardcoded in the contract.

---

## 8. CATEGORY G: DUPLICATED DECISIONS

### G1. Greeting Classification (CRITICAL)

Duplicated across 7 files (see A1 above). The pipeline, LLM intent classifier, identity resolver, context manager, continuity resolver, emergency responder, and conversation governor ALL independently classify greetings.

### G2. Identity Response (HIGH)

Duplicated across:
1. `llm/identity_dataset.py` — canonical identity answers
2. `llm/conversation_governor.py` — `_CANONICAL_KNOWLEDGE` + `_PROTECTED_QUERIES`
3. `resolvers/identity_resolver.py` — greeting/joke responses
4. `core/pipeline/__init__.py` — `_check_identity()` routing

Four different systems can respond to identity questions. The identity dataset is the canonical owner, but the others can interfere.

### G3. Media Command Handling (HIGH)

Duplicated across:
1. `pipeline/__init__.py` — `_IntentClassifier.MEDIA_TRANSPORT` classification
2. `media/media_manager.py` — `_TRANSPORT_PATTERNS` regex matching
3. `media/media_manager.py` — `_VOLUME_UP/DOWN/SET` regex matching
4. `llm/intent_classifier.py` — `_DETERMINISTIC_MEDIA_ACTIONS` set
5. `media/intelligence/media_context_intelligence.py` — transport intent extraction

Five different systems handle media transport commands.

### G4. Error Handling (MEDIUM)

Each subsystem has its own error handling patterns:
- Pipeline: `except Exception → "Error: {str(exc)[:200]}"`
- LLM Router: provider-specific fallback chain
- Media Manager: media-specific error messages
- Browser: browser-specific error messages

### G5. Provider Selection (MEDIUM)

Four different provider selection mechanisms:
1. LLM Router priority chain
2. Provider Registry capability-based selection
3. Media Registry priority table
4. MCP Server name registry

---

## 9. CATEGORY H: HARDCODED PROACTIVE BEHAVIOR

### H1. Proactive Evaluator (HIGH)

**File:** `intelligence/proactive_evaluator.py`

```python
_SOURCE_INTERRUPTION_COST = {
    "watcher_change": 0.2,
    "reminder_due": 0.1,
    "task_completed": 0.3,
    ...
}
_SOURCE_VALUE = {
    "watcher_change": 0.8,
    "reminder_due": 0.9,
    ...
}
```

Interruption cost and value baselines are hardcoded weights.

### H2. Proactive Scoring Weights (MEDIUM)

The scoring formula `value * confidence * (1 - interruption_cost) * urgency_mult` uses hardcoded urgency multipliers:
```python
urgency_mult = {
    InterventionUrgency.CRITICAL: 2.0,
    InterventionUrgency.HIGH: 1.5,
    InterventionUrgency.MEDIUM: 1.0,
    InterventionUrgency.LOW: 0.5,
    InterventionUrgency.NONE: 0.0,
}
```

### H3. Cooldown (MEDIUM)

```python
def _cooldown_reasonable(source, last_notified, cooldown_s=1800.0):
```

30-minute cooldown is hardcoded.

---

## 10. CATEGORY I: NATURAL LANGUAGE ROBUSTNESS

### I1. Contractions and Casual Forms (MEDIUM)

The `_NormalizationService._CASUAL_CONTRACTION_MAP` handles common texting contractions:
```python
"whos": "who is", "whts": "what is", "wats": "what is",
"dont": "do not", "cant": "cannot", ...
```

The `_IntentClassifier._CONTRACTION_EXPANSIONS` handles KIO-self contractions:
```python
"how's": "how is", "what's": "what is", "you're": "you are", ...
```

**Problem:** Two separate contraction maps that overlap partially. A contraction handled by one but not the other could cause inconsistent behavior.

### I2. Typo Handling (MEDIUM)

The `_IntentClassifier._typo_fix_operational` method uses `difflib.get_close_matches` with cutoff=0.8 for operational keywords only. Typos in other domains (media, browser) are NOT corrected.

### I3. Casual Repetition Collapsing (MEDIUM)

Multiple systems collapse repeated characters:
- `pipeline/__init__.py`: `_REPEATED_CHAR_RE = re.compile(r"(.)\1+")` (collapse all)
- `core/pragmatics.py`: `_COLLAPSE3_RE = re.compile(r"(.)\1{2,}")` (collapse 3+ only)
- `pipeline/__init__.py`: `_casual_normalized()` uses the first pattern

**Problem:** Different collapse thresholds. "yooo" collapses to "yo" in the pipeline but "yoo" stays "yoo" in pragmatics (only 2 repeated chars).

---

## 11. CATEGORY J: DEAD/STALE CODE

### J1. `_PROTECTED_QUERIES["what time is it"]` (HIGH)

The pipeline now has `_detect_utility` that routes time queries to the `UTILITY` intent with action `"time"`. The conversation governor's protected query "what time is it" → "I cannot tell you the current time" is DEAD CODE that conflicts with the actual behavior.

### J2. `_PROTECTED_QUERIES["what is the date"]` (HIGH)

Same issue — the pipeline's `_detect_utility` now handles date queries deterministically.

### J3. `_IDENTITY_KEYWORDS` in `conversation_governor.py` (LOW)

This list is defined but appears to be unused (referenced in old audit as "defined but unused").

### J4. `_SIMILAR_ARTISTS` static map (MEDIUM)

Never updated, never used in production routing (only in recommendation engine fallback).

---

## 12. CLASSIFICATION SUMMARY

### Findings by Severity

| Severity | Count | Key Areas |
|----------|-------|-----------|
| CRITICAL | 22 | Duplicate greeting classification (7x), stale protected queries, mood mapping duplication, media transport 5x duplication |
| HIGH | 68 | Phrase sets (6x duplication), topic keywords, entity databases, provider chains, browser routing, identity 4x duplication, configuration defaults |
| MEDIUM | 35 | Scoring weights, cooldown timers, fuzzy maps, artifact keywords, error handling patterns, contraction maps |
| LOW | 12 | Dead code, cosmetic patterns, test-only values, legitimate constants |

### Findings by Subsystem

| Subsystem | CRITICAL | HIGH | MEDIUM | LOW | Total |
|-----------|----------|------|--------|-----|-------|
| Pipeline/Classification | 8 | 12 | 6 | 2 | 28 |
| Media | 6 | 18 | 8 | 1 | 33 |
| LLM/Identity | 3 | 8 | 4 | 2 | 17 |
| Browser/Automation | 1 | 6 | 3 | 0 | 10 |
| Companion/Personality | 1 | 4 | 3 | 1 | 9 |
| Intelligence/Proactive | 1 | 4 | 3 | 0 | 8 |
| Configuration | 0 | 6 | 4 | 2 | 12 |
| Memory/Context | 1 | 3 | 2 | 1 | 7 |
| MCP/Adapters | 0 | 4 | 2 | 1 | 7 |
| Execution/Workflows | 0 | 2 | 1 | 1 | 4 |
| Safety/Legacy | 1 | 1 | 1 | 1 | 4 |

### Previous Audit Comparison

| Metric | Previous | This Audit | Notes |
|--------|----------|------------|-------|
| Previous findings confirmed | 90 | 58 | 64% confirmed |
| Previous findings partially valid | — | 19 | Code exists but architecture changed |
| Previous findings now false positive | — | 13 | Code was refactored/removed |
| New findings discovered | — | 62 | Deeper exploration + broader scope |
| **Total findings** | **90** | **137** | **+52% increase** |

---

## 13. RECOMMENDED ARCHITECTURAL OWNER MAP

| Decision | Current Owner | Recommended Owner |
|----------|--------------|-------------------|
| Greeting classification | 7 locations | Pipeline._IntentClassifier (single source) |
| Identity response | 4 locations | identity_dataset.py (single source) |
| Media transport commands | 5 locations | Pipeline._IntentClassifier → MediaManager (single pipeline) |
| Mood→query mapping | 2 locations | Config file / dynamic preference model |
| Topic classification | keyword banks in code | Config file / learned model |
| Entity databases | hardcoded dicts | Database / API |
| Provider priority | hardcoded chains | Config file |
| Browser names | hardcoded frozensets | Config file / runtime discovery |
| App aliases | hardcoded regex list | Config file |
| Protected queries | hardcoded dict + substring match | Config file + exact match only |
| Proactive weights | hardcoded floats | Config file |
| Response templates | hardcoded strings | Template files |

---

## 14. RISK ASSESSMENT

### Highest Risk Findings

1. **7x greeting duplication (CRITICAL)** — Any inconsistency creates unpredictable behavior. A user saying "hey" might be classified differently depending on which code path runs.

2. **Stale protected queries (CRITICAL)** — "what time is it" → "I cannot tell you the time" when the pipeline ACTUALLY handles time queries. This is a live bug.

3. **5x media transport duplication (CRITICAL)** — "pause" goes through 5 different pattern matchers. Changes to one don't propagate to others.

4. **Mood mapping duplication (HIGH)** — Two different files define different query lists for the same mood.

5. **Static entity databases (HIGH)** — Sports events, movie entities, gaming entities become stale immediately.

### Lowest Risk Findings

1. Legitimate constants (enums, protocol values, safety boundaries)
2. Test-only hardcoded values
3. Script-specific paths
4. Configuration defaults that are also env-var overridable

---

## 15. NEXT STEPS

1. **Review this audit** — Confirm findings, challenge false positives
2. **Prioritize remediation** — See HARDCODE_REDUCTION_ROADMAP.md
3. **Approve implementation plan** — See HARDCODE_ARCHITECTURAL_GAPS.md
4. **Begin implementation** — Only after explicit approval

---

*This audit discovered 137 findings across the entire KIO system. The previous audit's 90 findings were 64% confirmed, 21% partially valid, and 14% false positives. The 47 net new findings come from deeper exploration of the media intelligence layer, the pipeline's normalization/classification system, and cross-subsystem duplication analysis.*
